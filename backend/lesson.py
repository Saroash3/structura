"""Builds a full lesson: plan -> verify (+batched fix) -> required concepts -> Piper audio -> min length -> quiz.

Lessons made from a question analysis (every new lesson) are organised around the user's focus:
  * required concepts come from the focus (a delete lesson needs "find the previous node", "rewire its next
    pointer", "the node is skipped", and the head/tail/missing edge cases) and never from an unrelated checklist
  * padding to 30 s uses sentences about the focus, never generic facts
  * core scenes must fill at least half of the lesson's duration
Old saved plans without an analysis keep the original behaviour.
"""
from __future__ import annotations

import hashlib
import json
import re

import answer
import focus
import llm
import planner
import quiz
import tts
from topic_parser import parse_topic
from verifier import CONCEPT, _lower_first, _safe, answer_missing, check_scene, simulate, template_narration, verify_scenes

MIN_SECONDS = 30

# Ideas a lesson about this structure must teach somewhere (old plans without a question analysis only).
REQUIRED_CONCEPTS: dict[str, list[tuple[str, str, str]]] = {
    "array": [
        ("index starts at 0", r"\bindex(?:es)?\s+(?:start|begin)s?\s+at\s+(?:0|zero)\b|\bindex\s+(?:0|zero)\b",
         "Indexes start at 0, so the first item is always at index 0."),
        ("fixed slots", r"\bfixed\b|\bslots?\b|\bside by side\b|\bcontiguous\b",
         "An array is a fixed row of slots stored side by side in memory."),
        ("instant access by index", r"\binstant\w*|\bconstant time\b|\bdirectly\b|\bjump(?:s)? straight\b|\bstraight to\b",
         "Reading any index is instant, because the computer can jump straight to that slot."),
        ("inserts shift items", r"\bshift",
         "Inserting or deleting in the middle is slower, because every later item has to shift over to make room."),
    ],
    "queue": [("first in, first out", r"first (?:item )?in,? (?:is )?(?:the )?first (?:item )?out|\bFIFO\b",
               "A queue is first in, first out: items leave in the same order they arrived.")],
    "stack": [("last in, first out", r"last (?:item )?in,? (?:is )?(?:the )?first (?:item )?out|\bLIFO\b",
               "A stack is last in, first out: the newest item is always the next to leave.")],
    "graph_bfs": [("uses a queue", r"\bqueue\b", "Breadth first search keeps a queue of discovered nodes waiting to be visited."),
                  ("level by level", r"\blevel", "Nodes are visited level by level: all neighbours of the start before anything further away.")],
    "bubble_sort": [("passes", r"\bpass", "Each pass moves the largest remaining value to the end of the array.")],
}

_scene_cache: dict[str, dict] = {}


def scene_key(structure: str, scene: dict, before: dict, is_intro: bool, extra: str = "") -> str:
    blob = json.dumps([structure, scene.get("ops", []), scene.get("narration", ""), before, is_intro, extra], sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


SPOKEN_MATH = [  # shown on screen as math, read aloud in words
    (r"O\(\s*n\s*(?:²|\^\s*2)\s*\)", "O of n squared"), (r"O\(\s*V\s*\+\s*E\s*\)", "O of V plus E"), (r"O\(\s*([^)]+?)\s*\)", r"O of \1"),
    (r"n\(n - 1\) / 2", "n times n minus 1, over 2"), (r"n²\s*/\s*2", "n squared over 2"), (r"n²", "n squared"),
    (r"\b2E\b", "2 E"), (r"(?<=\d)\s*×\s*(?=\d)", " times "), (r"\s+/\s+", " over "), (r"\b1/2\b", "one half"),
    (r"\s+\+\s+", " plus "), (r"\s+-\s+", " minus "), (r"\s+=\s+", " equals "), (r"\.\.\.", "and so on"),
]


def spoken(text: str) -> str:
    """What Piper reads: "head -> 10 -> null" is shown on screen but spoken as "head, then 10, then null", and
    "O(n²)" as "O of n squared"."""
    text = re.sub(r"\s*(?:->|→)\s*", ", then ", text)
    for pattern, words in SPOKEN_MATH:
        text = re.sub(pattern, words, text)
    return text


def _with_audio(scene: dict) -> dict:
    audio = tts.synthesize(spoken(scene["narration"]))
    return {**scene, "audio_url": f"/audio/{audio['id']}.wav", "duration": audio["duration"]}


def verify_all(plan: dict, ctx: dict | None = None, rounds: int = 2) -> list[dict]:
    """Verify every scene. Unchanged scenes (same content hash) come from the cache; the rest are checked
    together and all failing scenes are repaired in one batched LLM call that includes their true states."""
    structure = plan["structure"]
    scenes = plan["scenes"]
    sims = simulate(structure, scenes)
    intro = [i == 0 and not sims[i]["steps"] for i in range(len(scenes))]
    ctx_key = json.dumps(ctx, sort_keys=True) if ctx else ""
    keys = [scene_key(structure, s, sim["before"], intro[i], ctx_key + "|" + str(s.get("role")) + "|" + str(s.get("structure")) + "|" + str(s.get("kind")) + "|" + str(s.get("point_id")))
            for i, (s, sim) in enumerate(zip(scenes, sims))]
    # Question-driven lessons are checked as a WHOLE (jargon explained before use, a demo that proves the rule, a recap that is
    # not a copy of the intro), so every scene is re-checked together. That costs no extra LLM call when nothing fails, and
    # audio is still cached per sentence by tts.
    todo = list(range(len(scenes))) if ctx else [i for i, k in enumerate(keys) if k not in _scene_cache]
    if todo:
        fixer = lambda items: planner.fix_scenes_batch(structure, items, ctx)
        verified = verify_scenes(structure, [scenes[i] for i in todo], [sims[i] for i in todo], fixer, max_rounds=rounds,
                                 intro_index=todo.index(0) if 0 in todo and intro[0] else None, ctx=ctx)
        for i, v in zip(todo, verified):
            _scene_cache[keys[i]] = _with_audio(v)
    return [{**_scene_cache[k], "speed": s.get("speed", 1.0), "role": s.get("role"), "structure": s.get("structure"), "note": s.get("note"),
             "point_id": s.get("point_id"), "kind": s.get("kind")} for k, s in zip(keys, scenes)]


def _concept_scene(structure: str, text: str, state: dict, role: str | None = None, ctx: dict | None = None) -> dict | None:
    sim = {"before": state, "steps": [], "state": state}
    scene = {"ops": [], "narration": text, "role": role}
    if check_scene(state.get("kind", structure), scene, sim, ctx=ctx):  # never ship an unverified sentence
        return None
    return _with_audio({"id": 0, "ops": [], "narration": text, "before": state, "steps": [], "state": state,
                        "verified": True, "narration_source": "template", "speed": 1.0, "role": role, "structure": None})


def missing_concepts(structure: str, scenes: list[dict]) -> list[tuple[str, str, str]]:
    text = " ".join(s["narration"] for s in scenes)
    return [c for c in REQUIRED_CONCEPTS.get(structure, []) if not re.search(c[1], text, re.I)]


def ensure_concepts(structure: str, scenes: list[dict]) -> list[dict]:
    """Insert a short concept scene for every required idea the narration never mentioned (old plans)."""
    pos = 1
    for _name, _pattern, sentence in missing_concepts(structure, scenes):
        scene = _concept_scene(structure, sentence, scenes[0]["before"])
        if scene:
            scenes.insert(pos, scene)
            pos += 1
    return scenes


def total(scenes: list[dict]) -> float:
    return round(sum(s["duration"] / s.get("speed", 1.0) for s in scenes), 2)


def pad_to_min_length(structure: str, scenes: list[dict]) -> list[dict]:
    """Insert concept scenes after the intro until the lesson is >= 30 s, then renumber (old plans)."""
    extras = iter(CONCEPT.get(structure, [])[1:])
    while total(scenes) < MIN_SECONDS and (text := next(extras, None)):
        if text not in (s["narration"] for s in scenes) and (scene := _concept_scene(structure, text, scenes[0]["before"])):
            scenes.insert(1, scene)
    _stretch(scenes)
    for i, s in enumerate(scenes, 1):
        s["id"] = i
    return scenes


def _stretch(scenes: list[dict]) -> None:
    if total(scenes) < MIN_SECONDS:  # last resort: slow every scene evenly (never below 0.5x)
        factor = total(scenes) / MIN_SECONDS * 0.999
        for sc in scenes:
            sc["speed"] = max(0.5, round(sc.get("speed", 1.0) * factor, 3))


# ---------------------------------------------------------------- lessons organised around the question
def _core_slot(scenes: list[dict]) -> int:
    """Where a core explanation goes: after the last core scene, before edge cases and the recap."""
    last_core = max((i for i, s in enumerate(scenes) if s.get("role") == "core"), default=None)
    if last_core is not None:
        return last_core + 1
    return next((i for i, s in enumerate(scenes) if i > 0 and s.get("role") != "setup"), len(scenes))


def _edge_slot(scenes: list[dict]) -> int:
    return len(scenes) - 1 if scenes and scenes[-1].get("role") == "recap" else len(scenes)


def _insert_sentence(scenes: list[dict], text: str, role: str, ctx: dict, pos: int | None = None) -> bool:
    if any(s["narration"] == text for s in scenes):
        return False
    pos = pos if pos is not None else (_core_slot(scenes) if role == "core" else _edge_slot(scenes))
    state = scenes[pos - 1]["state"] if pos > 0 else scenes[0]["before"]
    scene = _concept_scene(state.get("kind", ""), text, state, role, ctx)
    if scene:
        scenes.insert(pos, scene)
    return scene is not None


def ensure_focus_concepts(scenes: list[dict], ctx: dict) -> list[dict]:
    """Every concept of THIS question must be taught; missing ones become short verified scenes (core or edge case)."""
    text = " ".join(s["narration"] for s in scenes)
    for _name, pattern, sentence, role in ctx["concepts"]:
        if not re.search(pattern, text, re.I | re.S):
            if _insert_sentence(scenes, sentence, role, ctx):
                text += " " + sentence
    return scenes


def _unused(pool: list[str], scenes: list[dict]) -> list[str]:
    said = {s["narration"] for s in scenes}
    return [t for t in pool if t not in said]


def enforce_budget(scenes: list[dict], ctx: dict) -> list[dict]:
    """Core scenes must fill >= 50% of the duration, and the lesson must last >= 30 s, using focus sentences only."""
    details = iter(_unused(ctx["details"], scenes))
    while focus.core_share(scenes) < focus.MIN_CORE_SHARE and (t := next(details, None)):
        _insert_sentence(scenes, t, "core", ctx)
    edge_noop = [s for s in scenes if s.get("role") == "edge_case" and not s["ops"]]
    if focus.core_share(scenes) < focus.MIN_CORE_SHARE and len(edge_noop) >= 2 and ctx.get("edges_combined"):
        pos = scenes.index(edge_noop[0])
        scenes[:] = [s for s in scenes if s not in edge_noop]
        _insert_sentence(scenes, ctx["edges_combined"], "edge_case", ctx, pos)
    extras = iter([*(("core", t) for t in _unused(ctx["details"], scenes)), *(("edge_case", t) for t in _unused(ctx["edges"], scenes))])
    while total(scenes) < MIN_SECONDS and (item := next(extras, None)):
        _insert_sentence(scenes, item[1], item[0], ctx)
    _stretch(scenes)
    for i, s in enumerate(scenes, 1):
        s["id"] = i
    return scenes


def ensure_answer(scenes: list[dict], ctx: dict) -> list[dict]:
    """ANSWER-COVERAGE GATE (last line of defence): an element of the answer the verified lesson still never says becomes a
    short verified scene before the recap. A lesson that does not answer the question is a failed lesson."""
    for name, _kind, hint in answer_missing([s["narration"] for s in scenes], ctx):
        if not _insert_sentence(scenes, hint, "core", ctx, _edge_slot(scenes)):
            llm.log.warning("lesson: the answer element %r is missing and its hint did not verify", name)
    return scenes


def _complete_points(scenes: list[dict], points: list[dict]) -> list[dict]:
    """Scenes added after planning (a missing concept, an edge case) teach their own new point; points nobody teaches are dropped."""
    points = [dict(p) for p in points]
    for s in scenes:
        if not s.get("point_id") or not any(p["id"] == s["point_id"] for p in points):
            pid = f"p{len(points) + 1}"
            while any(p["id"] == pid for p in points):
                pid += "b"
            kind = s.get("kind") or ("edge" if s.get("role") == "edge_case" else "explain")
            first = re.split(r"(?<=[.!?])\s", re.sub(r"^\s*edge cases?:\s*", "", s["narration"], flags=re.I))[0]
            points.append({"id": pid, "kind": kind, "point": (first[:1].upper() + first[1:])[:120], "visual": "current state"})
            s["point_id"], s["kind"] = pid, kind
    used = {s["point_id"] for s in scenes}
    return [p for p in points if p["id"] in used]


def _plan_scene(s: dict) -> dict:
    return {"id": s["id"], "ops": s["ops"], "narration": s["narration"], "speed": s["speed"],
            **({"role": s["role"]} if s.get("role") else {}),
            **({"point_id": s["point_id"], "kind": s["kind"]} if s.get("point_id") else {}),
            **({"structure": s["structure"]} if s.get("structure") else {}),
            **({k: s[k] for k in ("item", "line") if s.get(k)})}


NAMING = re.compile(r",\s*(?:which is\s+|which we\s+)?called\s+(?:an?\s+|the\s+)?([a-z][\w -]{1,30}?),\s*", re.I)
CALLED = re.compile(r"\bcalled\s+(?:an?\s+|the\s+)?([a-z][\w -]{1,30}?)\s*[,.;!?]", re.I)


def trim_repeats(scenes: list[dict], ctx: dict) -> list[dict]:
    """Beginner lessons: say a name once and never repeat a whole sentence. "The waiting line, called a queue, now holds C"
    becomes "The waiting line now holds C" after the first time, and a sentence already said word for word in an earlier
    scene is dropped. A trimmed scene ships only if it still verifies; its audio is regenerated."""
    import clarity
    named: set[str] = set()
    said: set[str] = set()
    out = []
    for i, s in enumerate(scenes):
        text = s["narration"]

        def drop_name(m: re.Match) -> str:
            name = m.group(1).lower()
            if name in named:
                return " "
            named.add(name)
            return m.group(0)
        new = re.sub(r"\s+", " ", NAMING.sub(drop_name, text)).strip()
        sents = clarity.sentences(new)
        if len(sents) > 1:
            kept = [x for x in sents if _norm(x) not in said] or sents[:1]
            new = " ".join(kept)
        said |= {_norm(x) for x in clarity.sentences(new)}
        named |= {m.lower() for m in CALLED.findall(new)}  # "..., which is called a queue." names it too
        if new != text:
            cand = {**s, "narration": new}
            sim = {"before": s["before"], "steps": s["steps"], "state": s["state"]}
            kind = s["state"]["kind"] if s["steps"] or i else ctx.get("structure", s["state"]["kind"])
            if not check_scene(kind, cand, sim, i == 0 and not s["steps"], ctx):
                s = _with_audio(cand)
        out.append(s)
    return out


def _norm(sentence: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", sentence.lower()).strip()


def split_scenes(scenes: list[dict], ctx: dict) -> list[dict]:
    """Beginner mode, one idea per scene: an explanation scene (no ops) longer than 2 sentences becomes consecutive scenes of
    at most 2 sentences each, on the same state and point. Each part is verified on its own; if one fails, the scene stays whole."""
    import clarity
    out: list[dict] = []
    for s in scenes:
        chunks = clarity.split_text(s["narration"]) if not s["ops"] else [s["narration"]]
        parts: list[dict] | None = []
        if len(chunks) > 1:
            sim = {"before": s["before"], "steps": [], "state": s["state"]}
            for k, chunk in enumerate(chunks):
                role = s.get("role") if s.get("role") != "recap" or k == len(chunks) - 1 else "core"
                part = {**s, "narration": chunk, "role": role}
                if check_scene(s["state"]["kind"], part, sim, not out and k == 0, ctx):
                    parts = None
                    break
                parts.append(part)
        if len(chunks) > 1 and parts:
            out.extend(_with_audio(p) for p in parts)
        else:
            out.append(s)
    for i, s in enumerate(out, 1):
        s["id"] = i
    return out


def tag_analogies(scenes: list[dict], ctx: dict) -> None:
    """The running analogy, shown as a small tag on every scene that uses it (beginner lessons only)."""
    import clarity
    for s in scenes:
        tag = clarity.analogy_tag(s["narration"], s["state"]["kind"], ctx.get("structure")) if ctx.get("beginner") else None
        if tag:
            s["analogy"] = tag
        else:
            s.pop("analogy", None)
        shown, _ = clarity.named_parts(s["narration"], s["state"])  # the stage highlights what the narration names
        if shown:
            s["named"] = shown
        else:
            s.pop("named", None)


def build_from_plan(plan: dict, rounds: int = 2) -> dict:
    analysis = plan.get("analysis")
    points: list[dict] = []
    if analysis and analysis.get("intent") == "question":  # question-driven: requirements -> points -> scenes
        ctx = answer.context(plan)
        scenes = verify_all(plan, ctx, rounds=1)  # one batched repair call at most (the LLM budget is 3 calls per lesson)
        if ctx.get("beginner"):
            scenes = trim_repeats(split_scenes(scenes, ctx), ctx)
        scenes = enforce_budget(scenes, ctx)
        tag_analogies(scenes, ctx)
        points = _complete_points(scenes, plan.get("answer_points") or [])
    elif analysis:
        ctx = focus.context(analysis)
        ctx["points"] = {p["id"]: p["point"] for p in plan.get("answer_points") or []}
        scenes = verify_all(plan, ctx, rounds=rounds)
        if not ctx["outline"]:  # an answer-first "what is" outline already teaches its concepts; never pad it
            scenes = ensure_focus_concepts(scenes, ctx)
        scenes = ensure_answer(scenes, ctx)
        scenes = enforce_budget(scenes, ctx)
        points = _complete_points(scenes, plan.get("answer_points") or [])
    if not analysis:
        scenes = pad_to_min_length(plan["structure"], ensure_concepts(plan["structure"], verify_all(plan)))
    clean_plan = {"topic": plan["topic"], "structure": plan["structure"], "scenes": [_plan_scene(s) for s in scenes]}
    if analysis:
        clean_plan["analysis"] = analysis
        clean_plan["answer_points"] = points
    result = {"topic": plan["topic"], "structure": plan["structure"], "plan": clean_plan,
              "scenes": [{k: v for k, v in s.items() if k != "note"} for s in scenes], "total_duration": total(scenes)}
    if analysis:
        result["analysis"] = analysis
        result["answer_points"] = points
        result["core_share"] = round(focus.core_share(scenes), 3)
    return result


def _add_answer_scene(scenes: list[dict], plan: dict, text: str, point_id: str, ctx: dict, role: str = "core",
                      at: int | None = None) -> bool:
    """Insert a short explanation scene (no ops, on the current state) just before the recap (or at `at`); only if it verifies."""
    import clarity
    if at is None:
        at = len(scenes) - 1 if scenes and scenes[-1].get("role") == "recap" else len(scenes)
    state = scenes[at - 1]["state"] if at > 0 else scenes[0]["before"]
    if ctx.get("beginner"):
        text = clarity.plain_text(text, ctx, state.get("kind"))
    scene = {"id": 0, "ops": [], "narration": text, "before": state, "steps": [], "state": state, "speed": 1.0, "role": role,
             "point_id": point_id, "kind": "explain", "structure": None, "verified": True, "narration_source": "template"}
    if not text or check_scene(state.get("kind", ""), scene, {"before": state, "steps": [], "state": state}, False, ctx):
        return False
    scenes.insert(at, _with_audio(scene))
    plan["scenes"].insert(at, _plan_scene(scene))
    for k, s in enumerate(scenes, 1):
        s["id"] = k
    return True


def answer_gate(topic: str, result: dict) -> dict:
    """ANSWER-COVERAGE GATE after narration: the deterministic checks, then ONE judge call (temperature 0) that also rewrites
    the scenes of uncovered requirements. Rewrites ship only if they verify. A lesson that still does not answer the question
    raises NotAnswered: the user gets an honest notice instead of a bad lesson."""
    import clarity
    plan, scenes = result["plan"], result["scenes"]
    ctx = answer.context(plan)
    problems = answer.gate(plan, scenes, ctx)
    point_req = {p["id"]: p.get("requirement_id") for p in plan.get("answer_points") or []}

    def unclear(texts: list[str]) -> dict[int, list[str]]:
        found = clarity.lesson_clarity(texts, scenes, [s["state"]["kind"] for s in scenes], ctx, [s["state"] for s in scenes]) if ctx.get("beginner") else {}
        return {i: e for i, e in found.items() if e}

    notes = [f"scene {i} is unclear: {e[0]}" for i, e in unclear([s["narration"] for s in scenes]).items()]
    try:
        verdict = answer.judge(topic, plan, scenes, problems + notes)  # the clarity judge rides on the same call
    except llm.LLMError:
        verdict = None
    repaired, clarified, follow, fixed_reqs, proposed = [], [], {}, set(), []
    uncovered_ids = {r.get("id") for r in (verdict or {}).get("requirements") or [] if isinstance(r, dict) and not r.get("covered")}

    def needed(i: int) -> bool:  # a fix for an uncovered requirement or a gate problem (else it only improves clarity)
        return point_req.get(scenes[i].get("point_id")) in uncovered_ids or bool(problems and scenes[i].get("role") == "recap")

    if isinstance(verdict, dict):
        for fix in verdict.get("fixes") or []:
            i, text = fix.get("index"), fix.get("narration")
            if not (isinstance(i, int) and 0 <= i < len(scenes) and isinstance(text, str) and text.strip()):
                continue
            sc = scenes[i]
            sim = {"before": sc["before"], "steps": sc["steps"], "state": sc["state"]}
            kind = plan["structure"] if i == 0 and not sc["steps"] else sc["state"]["kind"]
            errors = check_scene(kind, {**sc, "narration": text.strip()}, sim, i == 0, ctx)
            if not errors and ctx.get("beginner"):  # the rewrite must also be clear (explanation scenes are split later)
                def unclear_at(t: str) -> list[str]:
                    texts = [s["narration"] for s in scenes]
                    texts[i] = t
                    return [e for e in unclear(texts).get(i, []) if sc["ops"] or not e.startswith("Beginner style: at most")]
                errors = unclear_at(text.strip())
                defined = clarity.define_first(text.strip(), errors, ctx, sc["state"]["kind"]) if errors else text
                if errors and defined != text.strip() and not unclear_at(defined) \
                        and not check_scene(kind, {**sc, "narration": defined}, sim, i == 0, ctx):
                    text, errors = defined, []  # it only missed a definition: the glossary's plain one goes first
                if errors and needed(i):  # ANSWER FIRST: a verified answer is never dropped for clarity; explain what we can
                    best = clarity.define_first(text.strip(), errors, ctx, sc["state"]["kind"], strict=False)
                    best = " ".join(clarity.short_sentences(best))  # long sentences cut at a clause boundary (same words)
                    if best != text.strip() and not check_scene(kind, {**sc, "narration": best}, sim, i == 0, ctx):
                        text = best
                    llm.log.info("judge: the fix for scene %d answers the question but is not fully clear (%s); kept", i,
                                 "; ".join(unclear_at(text.strip()))[:300])
                    errors = []
            if not errors and not needed(i):  # a clarity rewrite must not lose part of the answer (a key term, a requirement)
                trial = [dict(s) for s in scenes]
                trial[i]["narration"] = text.strip()
                if len(answer.gate(plan, trial, ctx)) > len(answer.gate(plan, scenes, ctx)):
                    errors = ["the rewrite drops part of the answer"]
            if errors and not needed(i):  # a clarity rewrite that does not verify: the verified scene stays as it was
                llm.log.info("judge: the clarity fix for scene %d is rejected (%s)", i, "; ".join(errors)[:300])
                continue
            if not needed(i):
                scenes[i] = {**_with_audio({**sc, "narration": text.strip()}), "narration_source": "llm-judge-fixed"}
                plan["scenes"][i]["narration"] = text.strip()
                clarified.append(i)
                continue
            if errors:  # the rewrite does not verify: the scene's own template states its point instead (always verified)
                llm.log.info("judge: the fix for scene %d does not verify (%s); using its template", i, "; ".join(errors)[:300])
                text, source = template_narration(kind, sc, sim, i == 0, ctx, i), "template"
            else:
                source = "llm-judge-fixed"
            scenes[i] = {**_with_audio({**sc, "narration": text.strip()}), "narration_source": source}
            plan["scenes"][i]["narration"] = text.strip()
            point = _safe(ctx["points"].get(sc.get("point_id"), ""))
            if source == "template" and ctx.get("beginner") and sc["ops"] and point and point[:40].lower() not in text.lower():
                # beginner demo templates tell the step in the analogy; the point itself follows in its own short scene
                said = clarity.plain_text(point, ctx, sc["state"]["kind"])
                extra = {**sc, "ops": [], "narration": said, "before": sc["state"], "steps": [], "role": "core" if sc.get("role") == "recap" else sc.get("role")}
                if said and not check_scene(sc["state"]["kind"], extra, {"before": sc["state"], "steps": [], "state": sc["state"]}, False, ctx):
                    follow[i] = {**_with_audio(extra), "narration_source": "template"}
                    text = text + " " + point  # counts as stating the point (the follow-up scene says it)
            if source == "llm-judge-fixed" or (point and point[:40].lower() in text.lower()):
                repaired.append(i)  # a template counts as a repair only if it really states the requirement's point
        fixed_reqs = {point_req.get(scenes[i].get("point_id")) for i in repaired}
        proposed = [f for f in verdict.get("fixes") or [] if isinstance(f, dict) and isinstance(f.get("index"), int)
                    and 0 <= f["index"] < len(scenes) and needed(f["index"])]
        repaired = [i + sum(1 for j in follow if j < i) for i in repaired]
        for i in sorted(follow, reverse=True):  # follow-up scenes go in after all fixes, so indices stay valid above
            scenes.insert(i + 1, follow[i])
            plan["scenes"].insert(i + 1, {**_plan_scene({**follow[i], "id": 0})})
        for k, s in enumerate(scenes, 1):
            s["id"] = k
        result["total_duration"] = total(scenes)
    reqs = (verdict or {}).get("requirements") or []
    uncovered = [r.get("id") for r in reqs if isinstance(r, dict) and not r.get("covered")]
    # SAFETY NET (no LLM call): a requirement still not covered gets a short verified scene stating its own answer (the plan's
    # point and evidence detail, e.g. "O(1) at the end versus O(n) in the middle"), and a key term still never said goes in a
    # short scene before the recap. The honest notice is kept for lessons even this cannot make answer the question.
    safety = []
    for r in plan["analysis"].get("requirements", []):
        if r["id"] in uncovered and r["id"] not in fixed_reqs:
            pid = next((p["id"] for p in plan.get("answer_points") or [] if p.get("requirement_id") == r["id"]), None)
            point = _safe(ctx["points"].get(pid, "")).strip()
            # a sentence can only repair what a sentence can show: the point itself (never glued-on notes), and only when
            # the requirement needs no evidence or its evidence (a scene with real ops) is already in the lesson
            has_evidence = r.get("evidence") in ("none", "state") or any(
                sc["ops"] and point_req.get(sc.get("point_id")) == r["id"] for sc in scenes)
            if pid and has_evidence and len(point.split()) >= 4 and _add_answer_scene(scenes, plan, point.rstrip(".") + ".", pid, ctx):
                fixed_reqs.add(r["id"])
                safety.append(r["id"])
    import concepts
    for name, _kind, hint in answer_missing([s["narration"] for s in scenes], ctx):
        term = re.sub(r'^the key term "|"$', "", name)
        said = concepts.name_sentence(term, plan["structure"])  # picture first, then the word
        if _add_answer_scene(scenes, plan, said, "recap", ctx, role="core"):
            safety.append(name)
    a = plan["analysis"]  # what the question's SHAPE needs and the lesson still lacks: built by code from domain knowledge
    last_pid = next((p["id"] for p in reversed(plan.get("answer_points") or []) if p.get("requirement_id")), "recap")
    first_pid = next((p["id"] for p in plan.get("answer_points") or [] if p.get("requirement_id")), "recap")
    for prob in answer.shape_problems(a, scenes):
        if prob.startswith("no verdict") and a.get("sides"):
            text = answer.verdict_sentence(a["sides"])
            if text and _add_answer_scene(scenes, plan, text, last_pid, ctx):
                safety.append("verdict")
                # the verdict is what a "when to choose each" requirement asks for
                fixed_reqs |= {r["id"] for r in a.get("requirements", []) if r["id"] in uncovered
                               and re.search(r"\bwhen\b|\bchoos|\bchoice|\brule\b|\buse\b|\bpick|\bdecid|\bverdict", r["text"], re.I)}
        elif prob.startswith("the question's claim") and isinstance(a.get("premise_correct"), bool):
            text = answer.premise_sentence(topic, a["premise_correct"])
            if _add_answer_scene(scenes, plan, text, first_pid, ctx, at=1 if len(scenes) > 1 else None):
                safety.append("premise")
                fixed_reqs |= {r["id"] for r in a.get("requirements", []) if r["id"] in uncovered
                               and re.search(r"\bnot\b|\bwrong\b|\bpremise\b|\bclaim\b|\bmyth\b|\bcorrect", r["text"], re.I)}
        elif prob.startswith("the recap does not restate") and a.get("recap_text") and scenes and scenes[-1].get("role") == "recap":
            if scenes[-1]["narration"] != a["recap_text"]:
                scenes[-1] = _with_audio({**scenes[-1], "narration": a["recap_text"], "narration_source": "template"})
                plan["scenes"][-1] = _plan_scene(scenes[-1])
                safety.append("recap names")
    if safety:
        result["total_duration"] = total(scenes)
    after = answer.gate(plan, scenes, ctx)
    says_yes = bool((verdict or {}).get("does_lesson_answer_question"))
    covered_all = not uncovered or set(uncovered) <= fixed_reqs
    # the judge's per-requirement verdicts decide: every requirement it found uncovered must now be covered
    ok = not after and (verdict is None or covered_all)
    if ctx.get("beginner"):  # one idea per scene, and the analogy tag, after the judge's rewrites
        scenes = split_scenes(scenes, ctx)
        tag_analogies(scenes, ctx)
        result["scenes"] = scenes
        plan["scenes"] = [_plan_scene(s) for s in scenes]
        result["total_duration"] = total(scenes)
    result["judge"] = {"verdict": says_yes if verdict is not None else None, "requirements": reqs, "repaired_scenes": repaired,
                       "clarity": (verdict or {}).get("clarity") or [], "clarified_scenes": clarified,
                       "unclear_after": [f"scene {i + 1}: {e[0]}" for i, e in unclear([s["narration"] for s in scenes]).items()]
                       if ctx.get("beginner") else [],
                       "deterministic_before": problems, "deterministic_after": after, "safety_net": safety, "passed": ok}
    if not ok:
        missing = [r["text"] for r in plan["analysis"].get("requirements", []) if r["id"] in uncovered] or after
        raise answer.NotAnswered(f"Sorry, Structura could not build a lesson that fully answers \"{topic}\". "
                                 f"It could not cover: {'; '.join(missing[:3])}. Try asking it a different way.")
    point_req = {p["id"]: p.get("requirement_id") for p in plan.get("answer_points") or []}
    result["answer_check"] = {  # "Verified" = the facts are true; this = the question is answered (shown separately in the UI)
        "passed": True, "shape": plan["analysis"].get("shape"), "judge": result["judge"]["verdict"],
        "requirements": [{"id": r["id"], "text": r["text"],
                          "scenes": [s["id"] for s in scenes if point_req.get(s.get("point_id")) == r["id"]]}
                         for r in plan["analysis"].get("requirements", [])]}
    return result


def _evidence_fallback(topic: str, given, notice: Exception) -> dict:
    """When the question-driven lesson still does not answer the question, a lesson built entirely from computed evidence
    (counted runs, derivation, growth table, best and worst case; no LLM call) is used if the algorithm is one the counting
    engine covers. Otherwise the user gets the honest notice."""
    try:
        a = focus.analyze(topic, given)
    except focus.UnsupportedTopic:
        a = None
    if a is None or a.intent != "complexity":
        raise notice
    result = build_from_plan(planner.complexity_plan(topic, a, given))
    result["judge"] = {"verdict": None, "passed": True, "fallback": "counted-evidence lesson",
                       "reason": str(notice)}
    return result


def build_lesson(topic: str, level: str = "beginner") -> dict:
    """Question-driven pipeline (at most 3 LLM calls: analysis + plan, one narration repair batch, the judge). If the
    analysis call does not produce a usable answer plan, the same response feeds the older focus pipeline (no extra call)."""
    given = parse_topic(topic)
    shape = answer.question_shape(topic, given)
    if shape == "vague":  # never build an unrelated lesson to look helpful: ask what they mean
        raise answer.NeedsClarification(answer.CLARIFY)
    try:
        raw = answer.analyze_and_plan(topic, level, given)
    except llm.LLMError:
        raw = None
    a = (raw or {}).get("analysis") if isinstance(raw, dict) else None
    if isinstance(a, dict) and a.get("shape") == "vague" and str(a.get("clarify") or "").strip() and shape not in answer.STRONG_SHAPES:
        raise answer.NeedsClarification(str(a["clarify"]).strip())
    subject = answer.subject_from_text(topic)
    unsupported = isinstance(raw, dict) and (raw.get("unsupported") is True or raw.get("structure") == "unsupported")
    if not answer.usable(raw) and shape == "list" and subject:
        # ROOT CAUSE of "types of array" turning into a generic "what is an array" lesson: the analysis call answered
        # {"unsupported": true} and the old pipeline silently built a definition lesson. A list question about a supported
        # structure is answered from its known kinds instead, and still goes through the coverage gate.
        raw = {"structure": subject, "analysis": {"subject": subject, "shape": "list", "requirements": []}, "scenes": []}
    if answer.usable(raw) or (isinstance(raw, dict) and (raw.get("analysis") or {}).get("shape") == "list" and subject):
        plan = planner.Plan.model_validate(answer.build_plan(topic, raw, given)).model_dump()
        plan["analysis"]["level"] = level  # beginner lessons go through the clarity gate
        try:
            result = answer_gate(topic, build_from_plan(plan))
        except answer.NotAnswered as notice:
            result = _evidence_fallback(topic, given, notice)  # a lesson built from counted evidence, else the honest notice
        result["level"] = level
        result["quiz"] = quiz.make_quiz_from_plan(result["plan"], seed=f"{plan['structure']}:{topic.lower().strip()}", level=level)
        return result
    if unsupported and not subject and not given.edges:
        closest = [str(c) for c in (raw.get("closest") or []) if isinstance(c, str)][:3]
        raise planner.UnsupportedTopic(f'Structura cannot show "{topic}" on a real data structure yet. '
                                       + (f"Closest topics it can show: {', '.join(closest)}. " if closest else "")
                                       + f"It can explain {planner.SUPPORTED_NAMES}.")
    if shape not in OLD_PIPELINE_SHAPES:  # the old pipeline only answers definitions, how-to, comparisons, traces and why
        raise answer.NotAnswered(f'Sorry, Structura could not build a lesson that answers "{topic}". Try asking it a different way.')
    plan = planner.make_plan(topic, level, first_raw=raw)
    result = build_from_plan(plan, rounds=1)  # one repair round: the analysis call was the first of 3 LLM calls
    missing = answer.missing_nouns(topic, [s["narration"] for s in result["scenes"]])
    if missing:  # the coverage gate blocks here too: a lesson that never mentions what was asked does not ship
        raise answer.NotAnswered(f'Sorry, Structura could not build a lesson that answers "{topic}": it never covered '
                                 f'{", ".join(missing)}. Try asking it a different way.')
    result["level"] = level
    result["answer_check"] = {"passed": True, "shape": shape, "requirements": [], "method": "key words of the question"}
    # The quiz is built from THIS lesson's data, operations and focus (same list, graph, labels and values).
    result["quiz"] = quiz.make_quiz_from_plan(result["plan"], seed=f"{plan['structure']}:{topic.lower().strip()}", level=level,
                                              reword=False)
    return result


OLD_PIPELINE_SHAPES = ("definition", "how", "compare", "data", "why", "complexity")
