"""Revise ONE scene of an existing plan. Every other scene stays byte-for-byte the same.

A narration revision is only reported as a change when the text really changed: the candidate is checked by the verifier
(and the beginner clarity gate) BEFORE it goes into the lesson, retried once with the real problems, and refused honestly
when it still fails or is a near-copy of the old text. Templates never stand in for a requested rewrite, because the
template is usually exactly the text the viewer asked us to change.
"""
from __future__ import annotations

import difflib
import json
import re

import lesson
import llm
import planner
from verifier import check_scene, compact_state, lesson_errors, required_facts, simulate

SLOWER = re.compile(r"\bslow(?:er)?\b|\bslow down\b", re.I)
FASTER = re.compile(r"\bfast(?:er)?\b|\bspeed up\b|\bquick(?:er)?\b", re.I)
NORMAL = re.compile(r"\bnormal speed\b|\breset speed\b", re.I)
SCENE_REF = re.compile(r"\b(?:step|scene)\s*#?\s*(\d+)\b", re.I)
SIMPLER = re.compile(r"\bsimpl\w*|\bbeginners?\b|\beas(?:y|ier)\b|\bexplain\w*|\bplain\b|\bclear\w*|\bunderstand\w*|\bconfus\w*|"
                     r"\bkids?\b|\bchild\w*\b|\bhard\b|\bdifficult\b|\bjargon\b", re.I)
SAME_RATIO = 0.9
NO_CHANGE = "I couldn't make this step simpler, try describing what confused you."


class RevisionError(ValueError):
    pass


def parse_scene_id(instruction: str) -> int | None:
    m = SCENE_REF.search(instruction)
    return int(m.group(1)) if m else None


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _context(plan: dict) -> dict | None:
    """The same verification context build_from_plan uses for this plan."""
    analysis = plan.get("analysis")
    if not analysis:
        return None
    if analysis.get("intent") == "question":
        import answer
        return answer.context(plan)
    import focus
    ctx = focus.context(analysis)
    ctx["points"] = {p["id"]: p["point"] for p in plan.get("answer_points") or []}
    return ctx


def candidate_errors(plan: dict, idx: int, text: str, ctx: dict | None) -> list[str]:
    """Everything the verifier would object to if scene idx said `text`, including problems it would cause in OTHER scenes
    (e.g. it drops a definition a later scene relies on), since those would make the rebuild rewrite the other scenes."""
    structure, scenes = plan["structure"], plan["scenes"]
    sims = simulate(structure, scenes)
    intro = idx == 0 and not sims[0]["steps"]
    kind = structure if intro else sims[idx]["state"]["kind"]
    errs = list(check_scene(kind, {**scenes[idx], "narration": text}, sims[idx], intro, ctx))
    if ctx:
        texts = [s.get("narration", "") or "" for s in scenes]
        base = lesson_errors(texts, scenes, sims, ctx)
        texts[idx] = text
        new = lesson_errors(texts, scenes, sims, ctx)
        errs += new.get(idx, [])
        for j, e in new.items():
            if j != idx and set(e) - set(base.get(j, [])):
                errs.append(f"this change breaks step {j + 1}: " + "; ".join(sorted(set(e) - set(base.get(j, [])))))
    return sorted(set(errs))


def _simplify_prompt(plan: dict, idx: int, sim: dict, instruction: str, beginner: bool, problems: list[str], attempt: int) -> str:
    from concepts import ANALOGY, NEEDS_DEFINITION, plain_definition
    scene = plan["scenes"][idx]
    kind = sim["state"].get("kind") or plan["structure"]
    analogy = ANALOGY.get(kind) or ANALOGY.get(plan["structure"]) or {}
    facts = [desc for _, desc in required_facts(sim)]
    glossary = [f"  {t}: {plain_definition(t, kind)}" for t in NEEDS_DEFINITION if plain_definition(t, kind)]
    old = scene.get("narration", "")
    rules = [
        "At most 2 sentences. Each sentence at most 20 words.",
        "Everyday words a 12-year-old who has never coded knows. No filler words (extremely, instantly, seamlessly, robust, leverages).",
        "Never use a technical word before explaining it in plain words, and never explain it with another technical word.",
    ] if beginner else ["1 to 3 sentences, at most 25 words each, clearer and more concrete than before."]
    if analogy:
        rules.append(f"Tell the step in this lesson's picture first ({analogy.get('picture', '')}), then give the technical name once.")
    if facts:
        rules.append("It must still state these true facts, with the same values: " + "; ".join(facts) + ".")
    rules.append("Keep every value and label exactly as in the true state. Do not describe steps that are not in this scene.")
    rules.append("It must be clearly DIFFERENT from the current narration: new wording, simpler words, not a copy.")
    lines = [
        f"Rewrite the narration of ONE scene (step {idx + 1}) of a {plan['structure'].replace('_', ' ')} lesson.",
        f"The lesson answers: \"{plan['topic']}\". The viewer asked: \"{instruction}\".",
        f"Ops in this scene (unchanged): {json.dumps(scene.get('ops', []))}",
        f"True state before the scene: {json.dumps(compact_state(sim['before']))}",
        f"True state after each op: {json.dumps([compact_state(s) for s in sim['steps']])}",
        f"Current narration (the viewer found it hard): \"{old}\"",
        "Rules:", *[f"- {r}" for r in rules],
    ]
    if beginner and glossary:
        lines += ["Plain-words glossary (use these definitions when you need a term):", *glossary[:12]]
    if problems:
        lines.append(f"Your previous attempt was rejected for these reasons, fix all of them: {'; '.join(problems)}")
    if attempt:
        lines.append("Be stricter this time: shorter sentences, only words from the glossary or everyday speech, every listed fact kept.")
    lines.append('Return JSON: {"narration": str}')
    return "\n".join(lines)


def _rewrite(plan: dict, idx: int, instruction: str, ctx: dict | None, beginner: bool) -> tuple[str | None, list[str]]:
    """Up to 2 LLM attempts. Returns (narration, []) for a candidate that verifies and really differs, else (None, problems)."""
    import clarity
    sim = simulate(plan["structure"], plan["scenes"])[idx]
    old = plan["scenes"][idx].get("narration", "")
    problems: list[str] = []
    schema = {"type": "object", "properties": {"narration": {"type": "string"}}, "required": ["narration"]}
    for attempt in range(2):
        prompt = _simplify_prompt(plan, idx, sim, instruction, beginner, problems, attempt)
        with llm.temperature(0.4 + 0.3 * attempt):  # a retry of the same prompt must not come back from the cache unchanged
            text = str(llm.generate_json(prompt, schema).get("narration", "")).strip()
        if not text:
            problems = ["the narration was empty"]
            continue
        errs = candidate_errors(plan, idx, text, ctx)
        if errs and ctx and ctx.get("beginner"):  # only missed a plain definition: put it first (no LLM call)
            kind = sim["state"].get("kind") or plan["structure"]
            fixed = clarity.define_first(text, errs, ctx, kind)
            if fixed != text and not candidate_errors(plan, idx, fixed, ctx):
                text, errs = fixed, []
        if not errs and similarity(text, old) > SAME_RATIO:
            errs = ["it is almost the same as the current narration; change the wording and make it simpler"]
        if not errs:
            return text, []
        problems = errs
    return None, problems


def revise(plan: dict, scene_id: int | None, instruction: str, current_scenes: list[dict] | None = None) -> dict:
    plan = planner.Plan.model_validate(plan).model_dump()  # same validation as new plans
    scene_id = parse_scene_id(instruction) or scene_id
    if scene_id is None:
        raise RevisionError("Say which scene to change, e.g. 'slow down step 4'.")
    idx = scene_id - 1
    if not 0 <= idx < len(plan["scenes"]):
        raise RevisionError(f"There is no step {scene_id}. This lesson has {len(plan['scenes'])} steps.")
    scene = plan["scenes"][idx]
    old_text = scene.get("narration", "")

    if NORMAL.search(instruction):
        scene["speed"], change = 1.0, "speed"
    elif SLOWER.search(instruction):
        scene["speed"], change = max(0.5, round(scene["speed"] * 0.75, 3)), "speed"
    elif FASTER.search(instruction):
        scene["speed"], change = min(2.0, round(scene["speed"] * 1.25, 3)), "speed"
    else:
        ctx = _context(plan)
        beginner = bool(SIMPLER.search(instruction)) or (plan.get("analysis") or {}).get("level") == "beginner"
        text, problems = _rewrite(plan, idx, instruction, ctx, beginner)
        if text is None:
            return _unchanged(plan, scene_id, old_text, current_scenes, problems)
        scene["narration"] = text
        change = "narration"

    result = lesson.build_from_plan(plan)
    new_scene = result["scenes"][idx] if idx < len(result["scenes"]) else None
    if change == "narration" and (new_scene is None or similarity(new_scene["narration"], old_text) > SAME_RATIO):
        # the rebuild put the old words back (a whole-lesson check failed): do not claim a rewrite
        return _unchanged(plan, scene_id, old_text, current_scenes, ["the rebuilt lesson rejected the new wording"])
    result = _splice(result, idx, current_scenes)
    result["revised"] = {"scene_id": scene_id, "change": change, "before": old_text, "after": result["scenes"][idx]["narration"]}
    return result


def _splice(result: dict, idx: int, current: list[dict] | None) -> dict:
    """Keep every other scene exactly as the viewer has it (byte-identical), replacing only the revised one."""
    if not current or len(current) != len(result["scenes"]):
        return result
    scenes = [dict(s) for s in current]
    scenes[idx] = result["scenes"][idx]
    plan = dict(result["plan"])
    plan["scenes"] = [lesson._plan_scene(s) for s in scenes] if "scenes" in plan else plan.get("scenes")
    return {**result, "scenes": scenes, "plan": plan, "total_duration": lesson.total(scenes)}


def _unchanged(plan: dict, scene_id: int, old_text: str, current: list[dict] | None, problems: list[str]) -> dict:
    """Honest result: nothing changed. The lesson is returned as it was."""
    import logging
    logging.getLogger(__name__).info("revision of step %d refused: %s", scene_id, "; ".join(problems)[:400])
    if current:
        result = {"topic": plan["topic"], "structure": plan["structure"], "plan": plan, "scenes": current,
                  "total_duration": lesson.total(current)}
        for k in ("analysis", "answer_points"):
            if plan.get(k) is not None:
                result[k] = plan[k]
    else:
        result = lesson.build_from_plan(plan)
    result["revised"] = {"scene_id": scene_id, "change": "none", "before": old_text, "after": old_text, "message": NO_CHANGE}
    return result
