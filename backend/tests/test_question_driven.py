"""Question-driven lessons: properties that must hold for ANY question, checked on 12 varied ones.

The fake LLM answers the analysis call with requirements, key terms and jargon, but scenes WITHOUT ops and with placeholder
narration ("-"); the narration repair fixes nothing. That is the weakest plan an LLM could return: the generic code alone
(evidence builders, complete runs, verifier templates, the coverage gate) must still produce a lesson that covers every
requirement, says the question's key terms, states only numbers computed by code, does not repeat its intro in the recap,
quizzes the core point, and stays within 3 LLM calls. The real judge is exercised by eval_lessons.py (live).
"""
import re

import pytest

import answer
import eval_lessons
import concepts
import lesson
import llm
from verifier import check_scene

# question -> (subject, [(requirement, evidence, algorithm, structure)], key terms, jargon)
QUESTIONS = {
    "what is a stack": ("stack", [("a stack adds and removes items at the top only", "none", "", ""),
                                  ("last in, first out: the newest item leaves first", "trace", "", ""),
                                  ("push adds on the top and pop takes the top item off", "trace", "", "")], ["stack"], ["push", "pop"]),
    "what is a queue": ("queue", [("a queue is a line: join at the back, leave from the front", "none", "", ""),
                                  ("first in, first out: the oldest item leaves first", "trace", "", ""),
                                  ("enqueue adds at the back and dequeue removes the front", "trace", "", "")], ["queue"], ["enqueue"]),
    "how does bubble sort work": ("bubble_sort", [("bubble sort compares neighbouring items and swaps them when out of order", "trace", "", ""),
                                                  ("each pass carries the largest value to the end", "count", "bubble_sort", ""),
                                                  ("it stops when a pass makes no swaps", "none", "", "")], ["bubble sort"], ["pass"]),
    "why is bubble sort O(n^2)": ("bubble_sort", [("count the comparisons of each pass on a real run", "count", "bubble_sort", ""),
                                                  ("the counts grow like n(n-1)/2 for bigger n", "table", "bubble_sort", ""),
                                                  ("so bubble sort is O(n²): doubling n gives about 4 times the work", "none", "", ""),
                                                  ("best case sorted, worst case reversed", "compare", "bubble_sort", "")], ["O("], ["O(n²)"]),
    "how do I delete a node from the middle of a linked list": (
        "linked_list", [("walk from the head to the node before the target", "trace", "", ""),
                        ("delete: point its next pointer past the target, so the target is skipped", "trace", "", ""),
                        ("edge case: deleting the head moves the head pointer", "none", "", "")], ["delete", "linked list"], ["pointer"]),
    "compare a stack and a queue": ("stack", [("a stack removes the newest item", "trace", "", "stack"),
                                              ("a queue removes the oldest item", "trace", "", "queue"),
                                              ("use a stack for undo and a queue for waiting lines", "none", "", "")], ["stack", "queue"], []),
    "what is the difference between BFS and DFS": ("graph_bfs", [("BFS uses a queue and visits level by level", "trace", "", "graph_bfs"),
                                                                 ("DFS uses a stack and goes deep first", "trace", "", "graph_dfs"),
                                                                 ("on the same graph the visit orders differ", "compare", "", "")], ["BFS", "DFS"], ["queue"]),
    "best and worst case of insertion sort": ("insertion_sort", [("insertion sort slides each item left into the sorted part", "trace", "", ""),
                                                                 ("best case: a sorted list needs n - 1 comparisons", "compare", "insertion_sort", ""),
                                                                 ("worst case: a reversed list needs n(n-1)/2 comparisons", "table", "insertion_sort", "")],
                                              ["best case", "worst case"], []),
    "when should I use an array instead of a linked list": (
        "array", [("an array jumps straight to any index", "trace", "", "array"),
                  ("a linked list must walk from the head", "trace", "", "linked_list"),
                  ("use an array to read by index, a linked list to insert often", "none", "", "")], ["array", "linked list"], ["index"]),
    "trace BFS on this graph: A-B, A-C, B-D, C-D starting from A": (
        "graph_bfs", [("start at A with A in the queue", "trace", "", ""),
                      ("visit nodes in queue order, adding unvisited neighbours", "trace", "", ""),
                      ("the visit order is level by level", "none", "", "")], ["BFS", "queue"], []),
    "what is the time complexity of linear search": ("array", [("count the comparisons of a real search", "count", "linear_search", ""),
                                                               ("the count grows in step with n", "table", "linear_search", ""),
                                                               ("so linear search is O(n)", "none", "", "")], ["time complexity", "O("], []),
    "how does insertion sort work": ("insertion_sort", [("take the next item and compare it with its left neighbour", "trace", "", ""),
                                                        ("slide it left until it is in place", "count", "insertion_sort", ""),
                                                        ("the sorted part grows by one item each time", "none", "", "")], ["insertion sort"], []),
}


def _raw(q: str) -> dict:
    subject, reqs, terms, jargon = QUESTIONS[q]
    requirements = [{"id": f"r{i}", "text": t, "evidence": e, "algorithm": a, "structure": s or subject}
                    for i, (t, e, a, s) in enumerate(reqs, 1)]
    points = [{"id": f"p{i}", "requirement_id": f"r{i}", "kind": "explain", "point": t[0].upper() + t[1:] + "."}
              for i, (t, _e, _a, _s) in enumerate(reqs, 1)]
    scenes = ([{"point_id": "intro", "role": "setup", "ops": [], "narration": "-"}]
              + [{"point_id": p["id"], "role": "core", "ops": [], "narration": "-"} for p in points]
              + [{"point_id": "recap", "role": "recap", "ops": [], "narration": "-"}])
    return {"topic": q, "structure": subject, "analysis": {
        "subject": subject, "ask": q[0].upper() + q[1:] + "?", "key_terms": terms,
        "jargon": [{"term": j, "plain": f"the word for this idea in a {subject.replace('_', ' ')}"} for j in jargon],
        "requirements": requirements}, "answer_points": points, "scenes": scenes}


@pytest.fixture
def weak_llm(monkeypatch):
    calls = []

    def fake(prompt, schema=None):
        calls.append(prompt)
        if "Rewrite the narration of these scenes" in prompt:
            return {"scenes": []}
        if "You check whether a short lesson answers" in prompt:  # stand-in judge: every requirement has a scene
            return {"requirements": [], "does_lesson_answer_question": True, "fixes": []}
        q = prompt.split('Question from the user: "')[1].split('"\n')[0]
        return _raw(q)

    monkeypatch.setattr(llm, "generate_json", fake)
    monkeypatch.setattr(lesson.tts, "synthesize", lambda text: {"id": "x", "path": None, "duration": len(text.split()) / 2.5})
    lesson._scene_cache.clear()
    return calls


@pytest.mark.parametrize("question", list(QUESTIONS))
def test_any_question_gets_an_answer(weak_llm, question):
    r = lesson.build_lesson(question)
    plan, scenes = r["plan"], r["scenes"]
    assert r["analysis"]["intent"] == "question"
    ctx = answer.context(plan)
    # 1. every answer requirement is covered by a scene, and no scene is unmapped
    point_req = {p["id"]: p.get("requirement_id") for p in r["answer_points"]}
    covered = {point_req.get(s["point_id"]) for s in scenes}
    assert all(req["id"] in covered for req in r["analysis"]["requirements"])
    assert all(s["point_id"] in point_req for s in scenes)
    # 2. the question's key terms appear in the narration (the deterministic gate passes)
    assert answer.gate(plan, scenes, ctx) == []
    # 3. every number and claim matches the computed evidence (re-checked on the final lesson)
    for i, s in enumerate(scenes):
        sim = {"before": s["before"], "steps": s["steps"], "state": s["state"]}
        kind = plan["structure"] if i == 0 and not s["steps"] else s["state"]["kind"]
        assert check_scene(kind, s, sim, i == 0, ctx) == [], (i, s["narration"])
    # 4. evidence is computed by code: requirements that need it have a scene that runs ops
    for req in r["analysis"]["requirements"]:
        if req["evidence"] in ("trace", "count", "table", "compare"):
            assert any(s["ops"] for s in scenes if point_req.get(s["point_id"]) == req["id"]), req
    # 5. no demo cut off mid-algorithm
    for s in scenes:
        st = s["state"]
        if s["ops"] and st["kind"] in ("bubble_sort", "insertion_sort") and s is _last_of_run(scenes, s):
            assert st["is_sorted"], s["narration"]
        if s["ops"] and st["kind"] in ("graph_bfs", "graph_dfs") and st.get("started", True) and st.get("visits"):
            assert not (st.get("queue") or st.get("stack")) or s is not _last_of_run(scenes, s)
    # 6. the recap does not repeat the intro
    assert concepts.overlap(scenes[0]["narration"], scenes[-1]["narration"]) <= concepts.MAX_RECAP_OVERLAP
    # 7. the quiz has a question on the core point, about this lesson only
    assert r["quiz"] and r["quiz"][0]["kind"] == "core"
    # 8. the gate passed and the LLM budget held: analysis + plan, one repair batch, the judge
    assert r["judge"]["passed"] and len(weak_llm) <= 3
    assert eval_lessons.check_question(r) == []  # the same property check the live eval prints


def _last_of_run(scenes, s):
    """The last scene of the run that scene `s` belongs to (same structure, until the next reload / reset)."""
    kind = s["state"]["kind"]
    i = scenes.index(s)
    j = i
    for k in range(i + 1, len(scenes)):
        if scenes[k]["ops"] and scenes[k]["state"]["kind"] == kind:
            if scenes[k]["ops"][0]["op"] in ("reload", "reset"):
                break
            j = k
    return scenes[j]


def _uncovered_judge(prompt, raw):
    if "You check whether a short lesson answers" in prompt:
        return {"requirements": [{"id": "r2", "covered": False, "reason": "never explains it"}],
                "does_lesson_answer_question": False, "fixes": []}
    if "Rewrite the narration" in prompt:
        return {"scenes": []}
    return raw


def test_an_uncovered_requirement_gets_a_verified_answer_scene(monkeypatch):
    """The judge finds a requirement not covered and proposes nothing: the safety net states that requirement's own point."""
    monkeypatch.setattr(llm, "generate_json", lambda p, s=None: _uncovered_judge(p, _raw("what is a stack")))
    monkeypatch.setattr(lesson.tts, "synthesize", lambda text: {"id": "x", "path": None, "duration": len(text.split()) / 2.5})
    lesson._scene_cache.clear()
    r = lesson.build_lesson("what is a stack")
    assert r["judge"]["passed"] and "r2" in r["judge"]["safety_net"]
    assert any("newest item leaves first" in s["narration"].lower() and s["point_id"] == "p2" for s in r["scenes"])


def test_a_lesson_that_cannot_be_made_to_answer_gets_an_honest_notice(monkeypatch):
    """If not even the safety net can state the missing point truthfully, the user sees a notice, not a bad lesson."""
    raw = _raw("what is a stack")
    raw["answer_points"][1]["point"] = "The top is 999."  # the only statement of r2 is false, so it can never verify
    raw["analysis"]["requirements"][1]["text"] = "the top is 999"
    monkeypatch.setattr(llm, "generate_json", lambda p, s=None: _uncovered_judge(p, raw))
    monkeypatch.setattr(lesson.tts, "synthesize", lambda text: {"id": "x", "path": None, "duration": len(text.split()) / 2.5})
    lesson._scene_cache.clear()
    with pytest.raises(answer.NotAnswered, match="could not build a lesson that fully answers"):
        lesson.build_lesson("what is a stack")


def test_judge_fix_that_verifies_is_kept(monkeypatch):
    def fake(prompt, schema=None):
        if "You check whether a short lesson answers" in prompt:
            return {"requirements": [{"id": "r1", "covered": False, "reason": "too vague"}], "does_lesson_answer_question": False,
                    "fixes": [{"index": 1, "narration": "A stack only lets you add or remove items at the top, like a pile of plates."}]}
        if "Rewrite the narration" in prompt:
            return {"scenes": []}
        return _raw("what is a stack")
    monkeypatch.setattr(llm, "generate_json", fake)
    monkeypatch.setattr(lesson.tts, "synthesize", lambda text: {"id": "x", "path": None, "duration": len(text.split()) / 2.5})
    lesson._scene_cache.clear()
    r = lesson.build_lesson("what is a stack")
    assert r["judge"]["repaired_scenes"] == [1] and r["judge"]["passed"]
    assert r["scenes"][1]["narration_source"] == "llm-judge-fixed"


def test_plan_normalisation_is_generic():
    """Unmapped scenes are dropped, impossible ops removed, missing evidence built and runs completed, whatever the question."""
    raw = _raw("how does bubble sort work")
    raw["scenes"].insert(2, {"point_id": "nowhere", "role": "core", "ops": [{"op": "load", "args": [9, 8]}], "narration": "A random demo."})
    raw["scenes"][1]["ops"] = [{"op": "load", "args": [3, 1, 2]}, {"op": "step", "args": []}, {"op": "fly", "args": []}]
    plan = answer.build_plan("how does bubble sort work", raw, answer.GivenData())
    assert not any(s["narration"] == "A random demo." for s in plan["scenes"])
    ops = [o["op"] for s in plan["scenes"] for o in s["ops"]]
    assert "fly" not in ops and ops.count("step") >= 3  # the run on [3, 1, 2] is completed, never cut off
    count_req = next(r for r in plan["analysis"]["requirements"] if r["evidence"] == "count")
    pids = [p["id"] for p in plan["answer_points"] if p.get("requirement_id") == count_req["id"]]
    assert any(s["ops"] for s in plan["scenes"] if s["point_id"] in pids)


def test_key_terms_of_the_question_are_required():
    terms = dict(answer.key_terms("why is bubble sort O(n^2) in the worst case", {"key_terms": []}))
    assert {"O(", "worst case", "sort"} <= set(terms)
    assert re.search(terms["O("], "it is O(n²)") and not re.search(terms["O("], "it is quadratic")


def test_a_judge_fix_that_does_not_verify_falls_back_to_the_verified_template(monkeypatch):
    def fake(prompt, schema=None):
        if "You check whether a short lesson answers" in prompt:
            return {"requirements": [{"id": "r2", "covered": False, "reason": "vague"}], "does_lesson_answer_question": False,
                    "fixes": [{"index": 2, "narration": "The top is 999."}]}
        if "Rewrite the narration" in prompt:
            return {"scenes": []}
        return _raw("what is a stack")
    monkeypatch.setattr(llm, "generate_json", fake)
    monkeypatch.setattr(lesson.tts, "synthesize", lambda text: {"id": "x", "path": None, "duration": len(text.split()) / 2.5})
    lesson._scene_cache.clear()
    r = lesson.build_lesson("what is a stack")
    assert "999" not in r["scenes"][2]["narration"] and r["scenes"][2]["narration_source"] == "template"
    assert r["judge"]["passed"] and r["judge"]["repaired_scenes"] == [2]
