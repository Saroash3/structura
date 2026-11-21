"""End-to-end lesson evaluation on fixed (golden) cases.

    python eval_lessons.py                                   # run every case live (Gemini + Piper), PASS/FAIL per check
    python eval_lessons.py --save after.json                 # also save the lessons (scenes, roles, durations, quiz)
    python eval_lessons.py --before before.json              # print a BEFORE table from an older snapshot next to each case
    python eval_lessons.py --only delete --full              # one case, with the full narration scene by scene
    python eval_lessons.py --only complexity_bubble --full --full-case complexity_bubble   # BEFORE and AFTER narration
    python eval_lessons.py --questions                       # 12 varied questions: requirements, covering scenes, judge, narration
    python eval_lessons.py --before-after                    # BEFORE (eval_before.json) and AFTER for 3 questions

The named CASES and their CHECKS describe the focus pipeline (now the fallback when the question-driven call fails);
--questions checks the properties every answer must have, whatever the question (check_question).

For every lesson it prints, per scene: role, duration, its share of the lesson, and the total core share.
The same check functions are used by tests/test_eval_cases.py and tests/test_focus.py with a fake LLM (offline).
"""
from __future__ import annotations

import argparse
import json
import re
import sys

import complexity
import concepts
import focus
from structures import count_work
from verifier import POINTER_WORD, SKIP_WORD, _mentions, answer_missing, words_to_digits

CASES = {
    "what_is_stack": "what is stack",
    "what_is_queue": "what is queue",
    "what_is_ll": "what is linked list",
    "delete": "how do I delete a node from the middle of a linked list",
    "search": "how do I search a linked list",
    "compare": "difference between an array and a linked list",
    "bfs": "show BFS on this graph: A-B, A-C, B-D, C-D, starting from A",
    "array": "what is an array",
    "complexity_bubble": "what is time complexity of bubble sort",
    "complexity_linear": "time complexity of linear search",
    "complexity_bfs": "time complexity of BFS",
}

# The lesson the live app generated for "what is time complexity of bubble sort" BEFORE the complexity intent existed
# (captured 2026-11-20 with the previous code): a "how does bubble sort work" lesson, cut off mid-sort, that never
# mentions complexity, O(n^2) or a comparison count. Printed by --full next to the new lesson.
BEFORE_NARRATION = {"complexity_bubble": [
    ("setup", "-", "Bubble sort is a simple sorting method that puts items in order by checking neighbours and swapping them."),
    ("core", "-", "Think of it like heavier bubbles rising in water, where larger numbers slowly float toward the end of the line."),
    ("core", "-", "The key rule is that a pass compares every adjacent pair, swapping them if they are out of order."),
    ("core", "load", "Load the numbers 5, 1, 4, and 2 to start our sorting process. Array is now [5, 1, 4, 2]."),
    ("core", "step", "Compare 5 and 1. 5 is bigger, so swap. Array is now [1, 5, 4, 2]."),
    ("core", "step", "Compare 5 and 4. 5 is bigger, so swap. Array is now [1, 4, 5, 2]."),
    ("core", "step", "Compare 5 and 2. 5 is bigger, so swap. Array is now [1, 4, 2, 5]."),
    ("core", "step", "Compare 1 and 4. 1 is smaller, so do not swap. Array is now [1, 4, 2, 5]."),
    ("core", "step", "Compare 4 and 2. 4 is bigger, so swap. Array is now [1, 2, 4, 5]."),
    ("core", "step", "Compare 1 and 2. 1 is smaller, so do not swap. Array is now [1, 2, 4, 5]."),
    ("core", "-", "Bubble sort is used mainly in classrooms to teach how algorithms work and for very small lists."),
    ("recap", "-", "Takeaways: compare neighbours, swap out-of-order items, and repeat passes until everything is sorted."),
], "quiz": ["When bubble sort runs on [5, 1, 4, 2], what does the array look like after the first full pass?",
            "Where is bubble sort mostly used?",
            "When bubble sort runs on [5, 1, 4, 2], how many swaps happen during the first pass?"]}

BFS_EDGES = {frozenset(e) for e in [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")]}
BFS_NODES = {"A", "B", "C", "D"}

ARRAY_CONCEPTS = {
    "index starts at 0": r"\bindex(?:es)?\s+(?:start|begin)s?\s+at\s+(?:0|zero)\b|\bindex\s+(?:0|zero)\b",
    "fixed slots": r"\bfixed\b|\bslots?\b|\bside by side\b|\bcontiguous\b",
    "instant access by index": r"\binstant\w*|\bconstant time\b|\bdirectly\b|\bjump(?:s)? straight\b|\bstraight to\b",
    "inserts shift items": r"\bshift",
}
# what each case's quiz must be about (at least 2 of 3 questions)
QUIZ_FOCUS = {"what_is_ll": r"\bpoint\w*|\bnext\b|\bnode\b", "delete": r"\bdelet\w*", "search": r"\bsearch\w*",
              "compare": r"\barray\b|\blinked list\b"}
LL_WHAT_IS_CONCEPTS = {
    "node = value + next pointer": r"\bnodes?\b[^.]*\b(?:value|next|pointer)",
    "head": r"\bhead\b",
    "null at the end": r"\bnull\b",
    "no index jump, walk from the head": r"\bwalk\w*|\bfollow\w*|\bno index\b|\bcannot jump\b",
}


def _ops(lesson: dict) -> list[dict]:
    return [o for s in lesson["plan"]["scenes"] for o in s["ops"]]


def _dur(s: dict) -> float:
    return s["duration"] / s.get("speed", 1.0)


# ---------------------------------------------------------------- focus checks shared by every question-driven case
def check_answer(lesson: dict) -> list[str]:
    """Answer quality: answer points cover the lesson, demos prove the rule, no jargon, no repeated recap, a principle question."""
    fails = []
    scenes, points = lesson["scenes"], lesson.get("answer_points") or []
    if len(points) < 3:
        return [f"only {len(points)} answer point(s)"]
    ids = {p["id"]: p for p in points}
    stray = [s["id"] for s in scenes if s.get("point_id") not in ids]
    if stray:
        fails.append(f"scenes {stray} map to no answer point")
    for pid, pt in ids.items():
        n = sum(s.get("point_id") == pid for s in scenes)
        if n == 0:
            fails.append(f"answer point {pid} ({pt['kind']}) is not covered by any scene")
        elif n > 1 and pt["kind"] not in ("demo", "steps"):
            fails.append(f"answer point {pid} ({pt['kind']}) takes {n} scenes; only the demo may take more than one")
    texts = [s["narration"] for s in scenes]
    jargon = concepts.undefined_jargon(texts)
    if jargon:
        fails.append(f"jargon used before it is explained: {jargon}")
    recap = next((s for s in reversed(scenes) if s.get("role") == "recap"), None)
    if recap and concepts.overlap(scenes[0]["narration"], recap["narration"]) > concepts.MAX_RECAP_OVERLAP:
        fails.append(f"the recap repeats the intro (overlap {concepts.overlap(scenes[0]['narration'], recap['narration']):.2f})")
    ctx = focus.context(lesson["analysis"]) if lesson.get("analysis") else {}
    principle = ctx.get("principle")
    demo = [s for s in scenes if s["ops"] and s.get("role") == "core"]
    if principle and demo and not any(concepts.principle_ok_groups(principle["groups"], s["narration"]) for s in demo):
        fails.append(f"no demo scene says what it shows about the rule ({principle['name']})")
    if not any(q.get("kind") == "principle" for q in lesson.get("quiz") or []):
        fails.append("the quiz has no question on the core principle")
    return fails


def check_what_is(lesson: dict, structure: str) -> list[str]:
    """what is <structure>: definition, analogy, rule, demo that proves it, real-world uses, recap in new words."""
    if lesson["structure"] != structure:
        return [f"structure is {lesson['structure']}, expected {structure}"]
    fails = check_answer(lesson)
    kinds = [p["kind"] for p in lesson.get("answer_points") or []]
    for k in ("definition", "analogy", "rule", "demo", "uses", "recap"):
        if k not in kinds:
            fails.append(f"answer point missing: {k}")
    uses = [s for s in lesson["scenes"] if s.get("kind") == "uses"]
    if not uses or not concepts.uses_ok(structure, uses[0]["narration"]):
        fails.append("no real-world uses in the lesson")
    ops = [o["op"] for s in lesson["scenes"] for o in s["ops"]]
    if "peek" in ops:
        fails.append("the demo shows peek, which the answer does not need")
    proof = concepts.PRINCIPLE[structure]["proof_ops"]
    first_proof = next((i for i, op in enumerate(ops) if op in proof), None)
    if first_proof is None:
        fails.append(f"the demo never runs {proof}, the step that proves the rule")
    if not any(q.get("kind") in ("real_world", "vocab") for q in lesson.get("quiz") or []):
        fails.append("the quiz has no real-world or vocabulary question")
    if focus.core_share(lesson["scenes"]) < focus.MIN_CORE_SHARE:
        fails.append(f"core scenes are {focus.core_share(lesson['scenes']):.0%} of the duration, need at least 50%")
    if [s.get("role") for s in lesson["scenes"]].count("setup") > 2:
        fails.append("more than 2 setup scenes")
    return fails


def check_focus_lesson(lesson: dict, name: str) -> list[str]:
    fails = check_answer(lesson)
    scenes = lesson["scenes"]
    roles = [s.get("role") for s in scenes]
    bad = [f"{s['id']}:{s.get('role')}" for s in scenes if s.get("role") not in focus.ROLES]
    if bad:
        fails.append(f"scenes outside the allowed roles: {bad}")
    if roles.count("setup") > 2:
        fails.append(f"{roles.count('setup')} setup scenes, at most 2 allowed")
    share = focus.core_share(scenes)
    if share < focus.MIN_CORE_SHARE:
        fails.append(f"core scenes are {share:.0%} of the duration, need at least 50%")
    if not lesson.get("analysis"):
        return fails + ["lesson has no question analysis"]
    ctx = focus.context(lesson["analysis"])
    recap = scenes[-1]
    if recap.get("role") != "recap" or not re.search(ctx["terms"], recap["narration"], re.I | re.S):
        fails.append(f"the recap does not restate the answer ({ctx['focus_text']}): {recap['narration']!r}")
    first = scenes[0]["narration"]
    if lesson["analysis"]["intent"] != "what_is" and len(first.split()) > 30:
        fails.append(f"the first scene has {len(first.split())} words (about 25 max): {first!r}")
    body = " ".join(s["narration"] for s in scenes)
    for topic, pattern in ctx["off_topic"]:
        if re.search(pattern, body, re.I):
            fails.append(f"off-topic content in the lesson: {topic}")
    quiz = lesson.get("quiz") or []
    if name in QUIZ_FOCUS and lesson["analysis"]["intent"] != "what_is":
        on = [q for q in quiz if re.search(QUIZ_FOCUS[name], q["question"], re.I)]
        if len(on) < 2:
            fails.append(f"only {len(on)} quiz question(s) test the focus: {[q['question'] for q in quiz]}")
    if not quiz:
        fails.append("no quiz")
    return fails


def check_delete_lesson(lesson: dict) -> list[str]:
    """how do I delete a node from the middle of a linked list"""
    fails = check_focus_lesson(lesson, "delete")
    deletes = [s for s in lesson["scenes"] if s.get("role") == "core" and any(o["op"] == "delete_value" for o in s["ops"])]
    if not deletes:
        return fails + ["no core scene deletes a node"]
    s = deletes[0]
    last = s["steps"][-1]["last"]
    text = words_to_digits(s["narration"])
    if last.get("prev") is None or last.get("next") is None:
        fails.append(f"the core delete is not a middle node: {last}")
    else:
        if not (_mentions(text, last["prev"]) and _mentions(text, last["next"]) and re.search(POINTER_WORD, text, re.I)):
            fails.append(f"the delete scene does not say that {last['prev']}'s next pointer is rewired to {last['next']}: {s['narration']!r}")
        if not re.search(SKIP_WORD, text, re.I):
            fails.append(f"the delete scene does not say that {last['removed']} is skipped / no longer reachable: {s['narration']!r}")
    walks = [o["args"][0] for sc in lesson["scenes"] if sc.get("role") == "core" for o in sc["ops"] if o["op"] == "walk"]
    if last.get("prev") is not None and str(last["prev"]) not in map(str, walks):
        fails.append(f"the lesson never walks to the node before the target ({last['prev']}); walks: {walks}")
    setup_ops = [o["op"] for sc in lesson["scenes"] if sc.get("role") == "setup" for o in sc["ops"]]
    if any(op in ("insert_head", "insert_tail") for op in setup_ops):
        fails.append(f"setup builds the list with separate inserts instead of one init: {setup_ops}")
    return fails


def check_search_lesson(lesson: dict) -> list[str]:
    fails = check_focus_lesson(lesson, "search")
    walks = [s for s in lesson["scenes"] if s.get("role") == "core" and any(o["op"] == "walk" for o in s["ops"])]
    if len(walks) < 2:
        fails.append(f"the search is not shown hop by hop ({len(walks)} walk scene(s))")
    if not re.search(r"\bnull\b|\bnot (?:in|there|found)\b", " ".join(s["narration"] for s in lesson["scenes"]), re.I):
        fails.append("the lesson never says what happens when the value is not in the list")
    return fails


def check_what_is_ll_lesson(lesson: dict) -> list[str]:
    fails = check_what_is(lesson, "linked_list") + [f for f in check_focus_lesson(lesson, "what_is_ll") if f not in check_answer(lesson)]
    text = words_to_digits(" ".join(s["narration"] for s in lesson["scenes"]))
    for concept, pattern in LL_WHAT_IS_CONCEPTS.items():
        if not re.search(pattern, text, re.I | re.S):
            fails.append(f"concept missing from narration: {concept}")
    if re.search(r"\blist\s+(?:is\s+)?(?:now\s+)?\[", text, re.I):
        fails.append("narration shows the linked list as a bracketed array instead of pointers")
    return fails


def check_compare_lesson(lesson: dict) -> list[str]:
    fails = check_focus_lesson(lesson, "compare")
    kinds = {s["state"]["kind"] for s in lesson["scenes"]}
    if not {"array", "linked_list"} <= kinds:
        fails.append(f"the lesson does not show both structures: {sorted(kinds)}")
    ops = {o["op"] for o in _ops(lesson)}
    for op in ("get", "walk", "insert_at", "insert_after"):
        if op not in ops:
            fails.append(f"the comparison never runs {op}")
    return fails


def check_bfs_lesson(lesson: dict) -> list[str]:
    """Failures for: show BFS on this graph: A-B, A-C, B-D, C-D, starting from A."""
    fails = []
    if lesson["structure"] != "graph_bfs":
        return [f"structure is {lesson['structure']}, expected graph_bfs"]
    ops = _ops(lesson)
    edges = {frozenset(map(str, o["args"])) for o in ops if o["op"] == "add_edge"}
    if edges != BFS_EDGES:
        fails.append(f"edges are {sorted(map(sorted, edges))}, expected A-B, A-C, B-D, C-D")
    starts = [o["args"] for o in ops if o["op"] == "start_bfs"]
    if starts != [["A"]]:
        fails.append(f"start_bfs args are {starts}, expected [['A']]")
    final = lesson["scenes"][-1]["state"]
    if set(map(str, final["items"])) != BFS_NODES:
        fails.append(f"graph nodes are {final['items']}, expected A, B, C, D")
    if final.get("order") != ["A", "B", "C", "D"]:
        fails.append(f"visit order is {final.get('order')}, expected A, B, C, D")
    visit_scenes = [s for s in lesson["scenes"] if any(o["op"] == "visit" for o in s["ops"])]
    if len(visit_scenes) != 4:
        fails.append(f"{len(visit_scenes)} visit scenes, expected 4 (one per node)")
    for s in visit_scenes:
        text = words_to_digits(s["narration"])
        node = s["steps"][-1]["last"]["removed"]
        queue = s["state"]["queue"]
        if not _mentions(text, node):
            fails.append(f"scene {s['id']} does not name the visited node {node}: {s['narration']!r}")
        for q in queue or ["empty"]:
            if not _mentions(text, q):
                fails.append(f"scene {s['id']} does not name the queue {queue or 'empty'}: {s['narration']!r}")
                break
    for i, q in enumerate(lesson.get("quiz", []), 1):
        if not all(re.search(rf"\b{a}\s*-\s*{b}\b", q["question"]) for a, b in [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")]):
            fails.append(f"quiz Q{i} does not use the lesson's graph: {q['question']!r}")
        labels = set(re.findall(r"\b[A-Z]\b", " ".join(q["options"])))
        if not labels <= BFS_NODES:
            fails.append(f"quiz Q{i} options use labels outside A-D: {q['options']}")
    if not lesson.get("quiz"):
        fails.append("no quiz")
    if lesson.get("analysis"):
        share = focus.core_share(lesson["scenes"])
        if share < focus.MIN_CORE_SHARE:
            fails.append(f"core scenes are {share:.0%} of the duration, need at least 50%")
        if [s.get("role") for s in lesson["scenes"]].count("setup") > 2:
            fails.append("more than 2 setup scenes")
        fails += check_answer(lesson)
    return fails


def check_array_lesson(lesson: dict) -> list[str]:
    """Failures for: what is an array."""
    fails = []
    if lesson["structure"] != "array":
        return [f"structure is {lesson['structure']}, expected array"]
    text = " ".join(s["narration"] for s in lesson["scenes"])
    for name, pattern in ARRAY_CONCEPTS.items():
        if not re.search(pattern, words_to_digits(text), re.I):
            fails.append(f"concept missing from narration: {name}")
    ops = _ops(lesson)
    values = {int(x) for o in ops if o["op"] == "init" for x in o["args"]}
    values |= {int(o["args"][-1]) for o in ops if o["op"] in ("append", "insert_at", "set")}
    if not values:
        fails.append("the lesson puts no values in the array")
    max_len = max((len(s["state"]["items"]) for s in lesson["scenes"]), default=0)
    allowed = values | set(range(max_len + 3))  # the lesson's values, plus valid indexes and nearby counts
    for i, q in enumerate(lesson.get("quiz", []), 1):
        used = {int(n) for n in re.findall(r"\b\d+\b", q["question"] + " " + " ".join(q["options"]))}
        extra = sorted(used - allowed)
        if extra:
            fails.append(f"quiz Q{i} uses values that are not in the lesson: {extra}")
    if not lesson.get("quiz"):
        fails.append("no quiz")
    if lesson.get("analysis"):
        fails += [f for f in check_what_is(lesson, "array") if not f.startswith("structure is")]
    return fails


CHECKS = {"what_is_stack": lambda r: check_what_is(r, "stack"), "what_is_queue": lambda r: check_what_is(r, "queue"),
          "what_is_ll": check_what_is_ll_lesson, "delete": check_delete_lesson, "search": check_search_lesson,
          "compare": check_compare_lesson, "array": check_array_lesson, "bfs": check_bfs_lesson,
          "complexity_bubble": lambda r: check_complexity(r, "bubble_sort"),
          "complexity_linear": lambda r: check_complexity(r, "linear_search"),
          "complexity_bfs": lambda r: check_complexity(r, "bfs")}


# ---------------------------------------------------------------- question-driven lessons (any question)
QUESTIONS = [  # varied on purpose: the checks below are properties, not per-question rules
    "what is a stack", "how does bubble sort work", "why is bubble sort O(n^2)",
    "how do I delete a node from the middle of a linked list", "compare a stack and a queue",
    "what is the difference between BFS and DFS", "best and worst case of insertion sort",
    "when should I use an array instead of a linked list", "trace BFS on this graph: A-B, A-C, B-D, C-D starting from A",
    "what is the time complexity of linear search", "what is a queue", "how does insertion sort work",
]
BEFORE_AFTER = ["what is stack", "what is time complexity of bubble sort", "how do I delete a node from the middle of a linked list"]


def check_question(lesson: dict) -> list[str]:
    """Properties every answer must have: requirements covered, key terms said, numbers verified, no cut-off run,
    recap not a copy of the intro, a core-point quiz question, and the judge's verdict."""
    import answer
    from verifier import check_scene
    fails = []
    a = lesson.get("analysis") or {}
    if (lesson.get("judge") or {}).get("fallback") and a.get("intent") == "complexity":
        return check_complexity(lesson, a["algorithm"])  # the counted-evidence lesson replaced a failed generic one
    if a.get("intent") != "question":
        return [f"not built by the question-driven pipeline (intent {a.get('intent')})"]
    plan, scenes = lesson["plan"], lesson["scenes"]
    ctx = answer.context(plan)
    point_req = {p["id"]: p.get("requirement_id") for p in lesson.get("answer_points") or []}
    covered = {point_req.get(s.get("point_id")) for s in scenes}
    for r in a.get("requirements", []):
        if r["id"] not in covered:
            fails.append(f"requirement {r['id']} has no scene: {r['text']}")
    fails += [f"gate: {p}" for p in answer.gate(plan, scenes, ctx)]
    for i, s in enumerate(scenes):
        sim = {"before": s["before"], "steps": s["steps"], "state": s["state"]}
        kind = plan["structure"] if i == 0 and not s["steps"] else s["state"]["kind"]
        errs = check_scene(kind, s, sim, i == 0, ctx)
        if errs:
            fails.append(f"scene {s['id']} does not verify: {errs[0]}")
    for s in scenes:
        st = s["state"]
        nxt = next((t for t in scenes[scenes.index(s) + 1:] if t["ops"] and t["state"]["kind"] == st["kind"]), None)
        run_ends = nxt is None or nxt["ops"][0]["op"] in ("reload", "reset")
        if s["ops"] and run_ends and not a.get("partial"):
            if st["kind"] in ("bubble_sort", "insertion_sort") and not st.get("is_sorted"):
                fails.append(f"scene {s['id']}: the sort is cut off before the list is sorted")
            if st["kind"] in ("graph_bfs", "graph_dfs") and st.get("visits") and (st.get("queue") or st.get("stack")):
                fails.append(f"scene {s['id']}: the search is cut off before it finishes")
    if concepts.overlap(scenes[0]["narration"], scenes[-1]["narration"]) > concepts.MAX_RECAP_OVERLAP:
        fails.append("the recap repeats the intro")
    quiz = lesson.get("quiz") or []
    if not quiz or quiz[0].get("kind") != "core":
        fails.append("the quiz has no question on the core point")
    judge = lesson.get("judge") or {}
    if not judge.get("passed"):
        fails.append(f"the answer gate did not pass: {judge}")
    elif judge.get("verdict") is False and not judge.get("repaired_scenes"):
        fails.append("the judge says the lesson does not answer the question")
    return fails


def print_question(lesson: dict, title: str = "AFTER") -> None:
    a, scenes = lesson["analysis"], lesson["scenes"]
    point_req = {p["id"]: p.get("requirement_id") or p["id"] for p in lesson.get("answer_points") or []}
    print(f"  {title}: {len(scenes)} scenes, {lesson['total_duration']:.1f} s, key terms {a.get('key_terms')}")
    if (lesson.get("judge") or {}).get("fallback"):
        print(f"    FALLBACK to the {lesson['judge']['fallback']}, because: {lesson['judge']['reason']}")
        for p in lesson.get("answer_points") or []:
            print(f"    {p['id']} [{p['kind']}] scenes {[s['id'] for s in scenes if s.get('point_id') == p['id']]}  {p['point']}")
    verdicts = {r.get("id"): r for r in (lesson.get("judge") or {}).get("requirements") or []}
    for r in a.get("requirements", []):
        cov = [s["id"] for s in scenes if point_req.get(s.get("point_id")) == r["id"]]
        v = verdicts.get(r["id"], {})
        print(f"    {r['id']} [{r['evidence']}] scenes {cov}  judge: {'covered' if v.get('covered', True) else 'NOT covered'}"
              f"{' - ' + v['reason'] if v.get('reason') else ''}\n       {r['text']}")
    j = lesson.get("judge") or {}
    print(f"    judge: answers the question = {j.get('verdict')}, repaired scenes {j.get('repaired_scenes')}, passed {j.get('passed')}")
    for s in scenes:
        ops = ", ".join(f"{o['op']} {' '.join(map(str, o['args']))}".strip() for o in s["ops"])
        print(f"    {s['id']:>2} [{s.get('role')}, {s.get('point_id')} -> {point_req.get(s.get('point_id'))}, {s['narration_source']}]"
              f"{'  ops: ' + ops[:90] if ops else ''}\n       {s['narration']}")
    for q in lesson.get("quiz") or []:
        print(f"    quiz [{q.get('kind')}]: {q['question']}  -> {q['options'][q['answer_index']]}")


def print_before(snap: dict) -> None:
    print(f"  BEFORE: {len(snap['scenes'])} scenes, {snap['total']:.1f} s")
    for i, s in enumerate(snap["scenes"], 1):
        ops = ", ".join(f"{o['op']} {' '.join(map(str, o['args']))}".strip() for o in s["ops"])
        print(f"    {i:>2} [{s.get('role')}]{'  ops: ' + ops[:90] if ops else ''}\n       {s['narration']}")
    for q in snap.get("quiz", []):
        print(f"    quiz: {q}")


def run_questions(questions: list[str], before: dict) -> int:
    import time

    import lesson as lesson_mod
    import llm
    failed = 0
    for q in questions:
        print(f"\n=== {q!r}")
        if q in before:
            print_before(before[q])
        calls = []
        orig = llm.generate_json
        llm.generate_json = lambda p, s=None, _o=orig: calls.append(1) or _o(p, s)
        t0 = time.time()
        try:
            result = lesson_mod.build_lesson(q, "beginner")
        except Exception as e:  # noqa: BLE001
            print(f"  AFTER: {type(e).__name__}: {e}")
            failed += 1
            continue
        finally:
            llm.generate_json = orig
        print_question(result)
        fails = check_question(result)
        print(f"  generated in {time.time() - t0:.1f} s with {len(calls)} LLM call(s) (cached prompts count but cost nothing)")
        print("  PASS" if not fails else "  FAIL:\n    - " + "\n    - ".join(fails))
        failed += bool(fails)
    return failed


# ---------------------------------------------------------------- answer fit for any question shape (live)
SHAPE_QUESTIONS = ["how many types of array there are", "types of linked list", "types of queue", "stack vs queue",
                   "array vs linked list", "why is inserting in the middle of an array slow?", "when should I use a linked list?",
                   "is array access O(n)?", "what is a vector", "insert 5, 3, 8 into a BST", "BFS on the graph A-B, A-C, B-D",
                   "what is a linked list and why do we use it", "how does a queue work", "what is a hash table", "help"]
EXPECT_REFUSAL = {"what is a hash table": "UnsupportedTopic", "help": "NeedsClarification"}


def print_shape_before(snap: dict) -> None:
    print(f"  BEFORE: {len(snap['scenes'])} scenes, {snap['total']:.1f} s, requirements {len(snap.get('requirements') or [])}, "
          f"judge {snap.get('judge')}")
    for s in snap["scenes"]:
        print(f"     {s['id']:>2} [{s.get('role')}/{s.get('kind')}] {s['narration']}")


def check_shape(result: dict, q: str) -> list[str]:
    import re

    import answer
    from topic_parser import parse_topic
    fails = []
    plan, scenes = result["plan"], result["scenes"]
    a = plan["analysis"]
    check = result.get("answer_check") or {}
    if not check.get("passed"):
        fails.append("no passing answer check")
    fails += [f"requirement {r['id']} has no scene" for r in check.get("requirements", []) if not r["scenes"]]
    if a.get("intent") == "question":
        fails += answer.gate(plan, scenes, answer.context(plan))
        if not result.get("judge", {}).get("passed"):  # the judge's verdict is on the lesson BEFORE its repairs
            fails.append("the judge's flagged requirements were not all repaired")
    fails += [f"never says '{w}'" for w in answer.missing_nouns(q, [s["narration"] for s in scenes])]
    given = parse_topic(q)
    if given.values:
        ops = [x for s in plan["scenes"] for o in s["ops"] for x in o["args"]]
        if [v for v in ops if v in given.values][: len(given.values)] != list(given.values):
            fails.append(f"the user's values {list(given.values)} are not used in order")
    for u, v in given.edges:
        if not any(u in o["args"] and v in o["args"] for s in plan["scenes"] for o in s["ops"]):
            fails.append(f"the user's edge {u}-{v} is not used")
    return fails


def run_shapes(questions: list[str], before: dict) -> int:
    import time

    import lesson as lesson_mod
    import llm
    failed = 0
    for q in questions:
        print(f"\n=== {q!r}")
        if q in before:
            print_shape_before(before[q])
        calls = []
        orig = llm.generate_json
        llm.generate_json = lambda p, s=None, _o=orig: calls.append(1) or _o(p, s)
        t0 = time.time()
        try:
            result = lesson_mod.build_lesson(q, "beginner")
        except Exception as e:  # noqa: BLE001
            name = type(e).__name__
            ok = EXPECT_REFUSAL.get(q) == name
            print(f"  AFTER: {name}: {e}")
            print(f"  {len(calls)} LLM call(s)")
            print("  PASS (honest notice)" if ok else "  FAIL")
            failed += not ok
            continue
        finally:
            llm.generate_json = orig
        a = result["plan"]["analysis"]
        j = result.get("judge", {})
        print(f"  AFTER: shape={a.get('shape') or a.get('intent')}, {len(result['scenes'])} scenes, {result['total_duration']:.1f} s, "
              f"judge verdict before repair={j.get('verdict')}, repaired scenes={j.get('repaired_scenes')}, safety net={j.get('safety_net')}, "
              f"gate passed={j.get('passed')}, {len(calls)} LLM call(s), {time.time() - t0:.1f} s")
        for r in (result.get("answer_check") or {}).get("requirements", []):
            print(f"    requirement {r['id']}: {r['text'][:90]}  -> scenes {r['scenes']}")
        for s in result["scenes"]:
            ops = ", ".join(f"{o['op']} {' '.join(map(str, o['args']))}".strip() for o in s["ops"] if o["op"] != "reset")
            print(f"     {s['id']:>2} [{s.get('role')}/{s.get('kind')}] {s['state']['kind']}{'  ops: ' + ops[:60] if ops else ''}\n"
                  f"        {s['narration']}")
        fails = ([f"expected {EXPECT_REFUSAL[q]}"] if q in EXPECT_REFUSAL else []) + check_shape(result, q)
        print("  PASS" if not fails else "  FAIL:\n    - " + "\n    - ".join(fails))
        failed += bool(fails)
    print(f"\n{len(questions) - failed} of {len(questions)} passed")
    return failed


# ---------------------------------------------------------------- clarity for a total beginner
CLARITY_QUESTIONS = ["what is a linked list and why do we use it", "what is a queue", "what is stack", "what is array",
                     "how does a binary search tree work", "show BFS step by step on a small graph"]


def clarity_flags(topic: str, structure: str, scenes: list[dict]) -> dict[int, list[str]]:
    """The clarity gate's flags for any lesson (also a BEFORE snapshot), plus explanation scenes over 2 sentences."""
    import clarity
    kinds = [(s["state"]["kind"] if isinstance(s.get("state"), dict) else s.get("kind")) or structure for s in scenes]  # structure kinds
    states = [s["state"] for s in scenes] if all(isinstance(s.get("state"), dict) for s in scenes) else None
    flags = clarity.lesson_clarity([s["narration"] for s in scenes], scenes, kinds, {"structure": structure, "question": topic}, states)
    for i, s in enumerate(scenes):
        n = len(clarity.sentences(s["narration"]))
        if not s["ops"] and n > clarity.MAX_SENTENCES:
            flags.setdefault(i, []).append(f"Beginner style: at most {clarity.MAX_SENTENCES} short sentences per scene; this scene has {n}.")
    return flags


def print_clarity(title: str, topic: str, structure: str, scenes: list[dict], total: float) -> int:
    import clarity
    flags = clarity_flags(topic, structure, scenes)
    print(f"  {title}: {len(scenes)} scenes, {total:.1f} s, {sum(len(f) for f in flags.values())} clarity flag(s)")
    for i, s in enumerate(scenes):
        counts = [clarity.word_count(x) for x in clarity.sentences(s["narration"])]
        ops = ", ".join(f"{o['op']} {' '.join(map(str, o['args']))}".strip() for o in s["ops"])
        dur = s.get("duration", 0) / (s.get("speed") or 1.0)
        tag = (f"  tag: {s['analogy']}" if s.get("analogy") else "") + (f"  highlights: {', '.join(s['named'])}" if s.get("named") else "")
        print(f"    {i + 1:>2} [{s.get('role')}{', ' + s['kind'] if s.get('kind') in ('problem', 'fix') else ''}] {dur:.1f} s, "
              f"words per sentence {counts}{'  ops: ' + ops[:70] if ops else ''}{tag}\n       {s['narration']}")
        for f in flags.get(i, []):
            print(f"       ! {f[:160]}")
    return sum(len(f) for f in flags.values())


def check_clarity(lesson: dict, topic: str) -> list[str]:
    import clarity
    fails = []
    scenes = lesson["scenes"]
    for s in scenes:
        sents = clarity.sentences(s["narration"])
        if len(sents) > clarity.MAX_SENTENCES:
            fails.append(f"scene {s['id']} has {len(sents)} sentences")
        fails += [f"scene {s['id']}: a sentence has {clarity.word_count(x)} words" for x in sents if clarity.word_count(x) > clarity.MAX_WORDS]
    for i, f in clarity_flags(topic, lesson["structure"], scenes).items():
        fails += [f"scene {i + 1}: {x}" for x in f]
    if re.search(concepts.WHY_QUESTION, topic, re.I):
        kinds = [s.get("kind") for s in scenes]
        if "problem" not in kinds or "fix" not in kinds or kinds.index("problem") > max(i for i, k in enumerate(kinds) if k == "fix"):
            fails.append("a WHY question needs a problem scene before the fix scene")
    if not (lesson.get("judge") or {}).get("passed", True):
        fails.append("the answer gate did not pass")
    return fails


def run_clarity(questions: list[str], before: dict) -> int:
    import time

    import lesson as lesson_mod
    import llm
    failed = 0
    for q in questions:
        print(f"\n=== {q!r}")
        if q in before:
            b = before[q]
            print_clarity("BEFORE", q, b["structure"], b["scenes"], b["total"])
        calls = []
        orig = llm.generate_json
        llm.generate_json = lambda p, s=None, _o=orig: calls.append(1) or _o(p, s)
        t0 = time.time()
        try:
            result = lesson_mod.build_lesson(q, "beginner")
        except Exception as e:  # noqa: BLE001
            print(f"  AFTER: {type(e).__name__}: {e}")
            failed += 1
            continue
        finally:
            llm.generate_json = orig
        print_clarity("AFTER", q, result["structure"], result["scenes"], result["total_duration"])
        j = result.get("judge") or {}
        print(f"  judge: answers = {j.get('verdict')}, clarity flags from the judge {[c.get('index') for c in j.get('clarity') or []]}, "
              f"clarified scenes {j.get('clarified_scenes')}, sources {[s['narration_source'] for s in result['scenes']]}")
        fails = check_clarity(result, q)
        print(f"  generated in {time.time() - t0:.1f} s with {len(calls)} LLM call(s)")
        print("  PASS" if not fails else "  FAIL:\n    - " + "\n    - ".join(fails))
        failed += bool(fails)
    return failed


# ---------------------------------------------------------------- complexity lessons
def check_complexity(lesson: dict, algo: str) -> list[str]:
    """A complexity answer: the answer-coverage gate, a derivation with the formula, a growth table equal to the counting
    function, best and worst case run for real, a demo that is not cut off, and a quiz only about complexity."""
    fails = [f for f in check_answer(lesson) if "principle" not in f]
    a = lesson.get("analysis") or {}
    if a.get("intent") != "complexity" or a.get("algorithm") != algo:
        return fails + [f"analysed as {a.get('intent')}/{a.get('algorithm')}, expected complexity/{algo}"]
    spec = complexity.ALGOS[algo]
    scenes = lesson["scenes"]
    texts = [s["narration"] for s in scenes]
    text = " ".join(texts)
    for word in ("complexity", "O("):
        if word not in text:
            fails.append(f"the lesson never says {word!r}")
    missing = answer_missing(texts, focus.context(a))
    if missing:
        fails.append(f"answer elements missing: {[m[0] for m in missing]}")
    by_kind = {}
    for s in scenes:
        by_kind.setdefault(s.get("kind"), []).append(s)
    derive = by_kind.get("derive", [])
    if not derive or not any(spec["formula"] in s["narration"] and "=" in s["narration"] for s in derive):
        fails.append(f"no derivation scene that works out the formula {spec['formula']}")
    if spec["big_o"] not in text:
        fails.append(f"the lesson never gives the answer {spec['big_o']}")
    growth = by_kind.get("growth", [])
    if not growth:
        fails.append("no growth table")
    else:
        rows = growth[0]["state"]["rows"]
        for r in rows:
            if r["count"] != count_work(algo, r["n"]):
                fails.append(f"growth row n = {r['n']} shows {r['count']}, the counting function says {count_work(algo, r['n'])}")
            if "worst" in spec and r["count"] != spec["worst"](r["n"]):
                fails.append(f"growth row n = {r['n']} = {r['count']} does not match the formula {spec['formula']}")
            if f"n = {r['n']} needs {r['count']}" not in growth[0]["narration"]:
                fails.append(f"the growth scene does not say the row n = {r['n']}")
        if [r["n"] for r in rows] != complexity.SIZES:
            fails.append(f"growth table sizes are {[r['n'] for r in rows]}")
    demo = by_kind.get("demo", [])
    if not demo:
        fails.append("no demo of the real algorithm")
    elif spec["family"] == "sort" and not demo[-1]["state"]["is_sorted"]:
        fails.append("the demo is cut off before the list is sorted")
    elif spec["family"] == "graph" and demo[-1]["state"]["queue"]:
        fails.append("the demo is cut off before BFS finishes")
    if spec["family"] in ("sort", "scan"):
        for case in ("best", "worst"):
            sc = by_kind.get(case)
            if not sc or not sc[0]["ops"]:
                fails.append(f"the {case} case is not run for real")
                continue
            st = sc[0]["state"]
            n = st["size"]
            ran = st["comparisons"] if spec["family"] == "sort" else sc[0]["steps"][-1]["last"]["checked"]
            want = spec[case](n)
            if ran != want:
                fails.append(f"the {case} case ran {ran} {spec['units']}, expected {want} for n = {n}")
    elif not by_kind.get("cases"):
        fails.append("best / worst case is not discussed")
    if by_kind.get("uses") or by_kind.get("analogy"):
        fails.append("a complexity answer has uses / analogy scenes the question did not ask for")
    quiz = lesson.get("quiz") or []
    if len(quiz) != 3 or any(q.get("kind") != "complexity" for q in quiz):
        fails.append(f"the quiz is not only about complexity: {[q.get('kind') for q in quiz]}")
    elif quiz[0]["options"][quiz[0]["answer_index"]] != str(count_work(algo, 5)):
        fails.append(f"quiz answer for 5 items is {quiz[0]['options'][quiz[0]['answer_index']]}, the real count is {count_work(algo, 5)}")
    if focus.core_share(scenes) < focus.MIN_CORE_SHARE:
        fails.append(f"core scenes are {focus.core_share(scenes):.0%} of the duration, need at least 50%")
    if [s.get("role") for s in scenes].count("setup") > 2:
        fails.append("more than 2 setup scenes")
    return fails


# ---------------------------------------------------------------- printing
def snapshot(lesson: dict) -> dict:
    return {"structure": lesson["structure"], "total": lesson["total_duration"],
            "scenes": [{"ops": s["ops"], "narration": s["narration"], "duration": _dur(s), "role": s.get("role"),
                        "kind": s["state"]["kind"]} for s in lesson["scenes"]],
            "quiz": [q["question"] for q in lesson.get("quiz", [])],
            "quiz_kinds": [q.get("kind", "") for q in lesson.get("quiz", [])],
            "answer_points": lesson.get("answer_points") or [],
            "point_of_scene": [s.get("point_id") for s in lesson["scenes"]]}


def _old_role(topic: str, scenes: list[dict], i: int) -> str:
    """Old lessons had no roles: setup = intro + pure data-building scenes, recap = last no-op scene, everything else
    (including generic concept scenes and any non-insert op) is counted as core, which flatters the old pipeline."""
    s = scenes[i]
    if not s["ops"]:
        return "setup" if i == 0 else "recap" if i == len(scenes) - 1 else "core"
    return "setup" if all(o["op"] in focus.BUILD_OPS for o in s["ops"]) else "core"


def print_table(title: str, snap: dict, topic: str, inferred: bool = False) -> None:
    if "error" in snap:
        print(f"  {title}: ERROR {snap['error']}")
        return
    scenes = snap["scenes"]
    roles = [s.get("role") or _old_role(topic, scenes, i) for i, s in enumerate(scenes)]
    total = sum(s["duration"] for s in scenes) or 1
    core = sum(s["duration"] for s, r in zip(scenes, roles) if r == "core")
    print(f"  {title}: {len(scenes)} scenes, {total:.1f} s, core share {core / total:.0%}"
          f"{' (roles inferred: old lessons had none)' if inferred else ''}, setup scenes {roles.count('setup')}")
    for i, (s, r) in enumerate(zip(scenes, roles), 1):
        ops = ", ".join(f"{o['op']} {' '.join(map(str, o['args']))}".strip() for o in s["ops"]) or "-"
        text = s["narration"] if len(s["narration"]) <= 90 else s["narration"][:87] + "..."
        print(f"    {i:>2} {r:<9} {s['duration']:>5.1f}s {s['duration'] / total:>4.0%}  [{ops}]  {text}")
    if snap.get("answer_points"):
        print("    answer points -> scenes:")
        for pt in snap["answer_points"]:
            covering = [i for i, pid in enumerate(snap.get("point_of_scene", []), 1) if pid == pt["id"]]
            print(f"      {pt['id']} {pt['kind']:<10} scenes {covering}  {pt['point'][:80]}  (visual: {pt['visual']})")
    kinds = snap.get("quiz_kinds") or [""] * len(snap.get("quiz", []))
    for q, k in zip(snap.get("quiz", []), kinds):
        print(f"       quiz{f' [{k}]' if k else ''}: {q}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", help="JSON snapshot of the same topics from an older version")
    ap.add_argument("--save", help="write this run's lessons to a JSON snapshot")
    ap.add_argument("--only", help="comma-separated case names: " + ", ".join(CASES))
    ap.add_argument("--full", action="store_true", help="print the full narration of the delete lesson (or --full-case NAME)")
    ap.add_argument("--full-case", default="delete", help="which case --full prints scene by scene")
    ap.add_argument("--questions", action="store_true", help="run the 12 varied questions through the question-driven pipeline")
    ap.add_argument("--before-after", action="store_true", help="BEFORE (eval_before.json) and AFTER for the 3 comparison questions")
    ap.add_argument("--clarity", action="store_true", help="beginner clarity: BEFORE (eval_before_clarity.json) and AFTER narration, "
                                                           "with word counts and flags, for the linked list, queue, stack and array lessons")
    ap.add_argument("--shapes", action="store_true", help="answer fit: 15 varied question shapes live, with requirements, covering "
                                                          "scenes, judge verdict and narration; BEFORE (eval_before_shapes.json) for types of array")
    args = ap.parse_args(argv)
    if args.shapes:
        snap = json.load(open(args.before or "eval_before_shapes.json", encoding="utf-8"))
        return 1 if run_shapes(SHAPE_QUESTIONS, snap) else 0
    if args.clarity:
        snap = json.load(open(args.before or "eval_before_clarity.json", encoding="utf-8"))
        return 1 if run_clarity(CLARITY_QUESTIONS, snap) else 0
    if args.questions or args.before_after:
        snap = json.load(open(args.before or "eval_before.json", encoding="utf-8")) if (args.before or args.before_after) else {}
        return 1 if run_questions(BEFORE_AFTER if args.before_after else QUESTIONS, snap) else 0
    import lesson as lesson_mod

    before = json.load(open(args.before, encoding="utf-8")) if args.before else {}
    names = args.only.split(",") if args.only else list(CASES)
    saved, failed, results = {}, 0, {}
    for name in names:
        topic = CASES[name]
        print(f"\n=== {name}: {topic!r}")
        if topic in before:
            print_table("BEFORE", before[topic], topic, inferred=True)
        try:
            result = lesson_mod.build_lesson(topic, "beginner")
        except Exception as e:  # noqa: BLE001
            print(f"  AFTER: ERROR {type(e).__name__}: {e}")
            failed += 1
            continue
        results[name] = result
        saved[topic] = snapshot(result)
        print_table("AFTER ", saved[topic], topic)
        fails = CHECKS[name](result)
        print("  PASS" if not fails else "  FAIL:\n    - " + "\n    - ".join(fails))
        failed += bool(fails)
    full = args.full_case
    if args.full and full in BEFORE_NARRATION:
        print(f"\n=== BEFORE narration: {CASES[full]!r}")
        for i, (role, op, text) in enumerate(BEFORE_NARRATION[full], 1):
            print(f"\n  Scene {i} [{role}]  ops: {op}\n    {text}")
        print("\n  Quiz:\n" + "\n".join(f"    Q: {q}" for q in BEFORE_NARRATION["quiz"]))
    if args.full and full in results:
        print(f"\n=== {'AFTER' if full in BEFORE_NARRATION else 'Full'} narration: {CASES[full]!r}")
        for s in results[full]["scenes"]:
            print(f"\n  Scene {s['id']} [{s['role']}, {s.get('kind', '')} {s.get('point_id', '')}, {_dur(s):.1f} s]  ops: "
                  f"{', '.join(o['op'] + ' ' + ' '.join(map(str, o['args'])) for o in s['ops']) or '-'}")
            print(f"    {s['narration']}")
        print("\n  Quiz:")
        for q in results[full]["quiz"]:
            print(f"    Q [{q.get('kind', '')}]: {q['question']}\n       options: {q['options']}  answer: {q['options'][q['answer_index']]}")
    if args.save:
        json.dump(saved, open(args.save, "w", encoding="utf-8"), indent=1)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
