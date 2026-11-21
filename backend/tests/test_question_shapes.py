"""ANSWER FIT for any question shape: properties checked on 15 varied questions (no per-question rules in the code).

The fake LLM is weak on purpose: the analysis call gives a shape, requirements and key terms (sometimes WITHOUT the list
items or the comparison verdict), scenes carry placeholder narration, the repair call fixes nothing, and the judge is a
stand-in. Code alone (shape validation, the known kinds of each structure, the coverage gate, the safety net and the
verifier templates) must make the lesson answer the question, or refuse honestly. Live behaviour: eval_lessons.py --shapes.
"""
import re

import pytest

import answer
import concepts
import lesson
import llm
import planner
from topic_parser import parse_topic
from verifier import check_scene

# question -> fake analysis (shape, subject, requirements [(text, evidence, structure)], key terms, extras)
Q = {
    "how many types of array there are": ("list", "array", [("names the kinds of array", "state", "")], ["array"],
                                          {"items": [{"name": "1D array", "line": "A 1D array is a single row of lockers."}]}),
    "types of linked list": ("list", "linked_list", [("names the kinds of linked list", "state", "")], ["linked list"], {}),
    "types of queue": ("list", "queue", [("names the kinds of queue", "state", "")], ["queue"], {}),
    "stack vs queue": ("compare", "stack", [("a stack removes the newest item", "trace", "stack"),
                                            ("a queue removes the oldest item", "trace", "queue")], ["stack", "queue"],
                       {"sides": ["stack", "queue"]}),
    "array vs linked list": ("compare", "array", [("an array jumps straight to any index", "trace", "array"),
                                                  ("a linked list walks from the head", "trace", "linked_list")], ["array", "linked list"], {}),
    "why is inserting in the middle of an array slow?": ("why", "array", [("inserting in the middle shifts every later item", "trace", ""),
                                                                          ("the more items after it, the more moves", "count", "")],
                                                         ["insert", "array"], {}),
    "when should I use a linked list?": ("when", "linked_list", [("a linked list inserts without shifting", "trace", "linked_list"),
                                                                 ("an array must shift later items", "trace", "array")],
                                         ["linked list"], {"sides": ["linked list", "array"]}),
    "is array access O(n)?": ("misconception", "array", [("reading by index is a single step", "trace", ""),
                                                         ("so access is O(1), not O(n)", "none", "")], ["array", "O("],
                              {"premise_correct": False}),
    "what is a vector": ("definition", "array", [("a vector is a dynamic array that grows when it is full", "trace", "dyn_array"),
                                                 ("when it is full it moves to a block twice as big", "trace", "dyn_array")],
                         ["vector"], {}),
    "insert 5, 3, 8 into a BST": ("data", "binary_tree", [("insert 5, then 3 to the left, then 8 to the right", "trace", "")],
                                  ["insert", "BST"], {}),
    "BFS on the graph A-B, A-C, B-D": ("data", "graph_bfs", [("start at A with A in the queue", "trace", ""),
                                                             ("visit in queue order, adding new neighbours", "trace", "")], ["BFS"], {}),
    "what is a linked list and why do we use it": ("multipart", "linked_list", [("a linked list is a chain of boxes with notes", "state", ""),
                                                                               ("we use it because inserting needs no shifting", "trace", "")],
                                                   ["linked list"], {"parts": ["what is a linked list", "why do we use it"]}),
    "how does a queue work": ("how", "queue", [("people join at the back", "trace", ""), ("people leave from the front", "trace", "")],
                              ["queue"], {}),
    "how does a stack work": ("how", "stack", [("plates go on the top", "trace", ""), ("the top plate comes off first", "trace", "")],
                              ["stack"], {}),
}
UNSUPPORTED = "what is a hash table"
VAGUE = "help"


def _raw(q: str) -> dict:
    if q == UNSUPPORTED:
        return {"unsupported": True, "closest": ["array", "linked list"]}
    shape, subject, reqs, terms, extra = Q[q]
    requirements = [{"id": f"r{i}", "text": t, "evidence": e, "structure": s or subject} for i, (t, e, s) in enumerate(reqs, 1)]
    points = [{"id": f"p{i}", "requirement_id": f"r{i}", "kind": "explain", "point": t[0].upper() + t[1:] + "."}
              for i, (t, _e, _s) in enumerate(reqs, 1)]
    scenes = ([{"point_id": "intro", "role": "setup", "ops": [], "narration": "-"}]
              + [{"point_id": p["id"], "role": "core", "ops": [], "narration": "-"} for p in points]
              + [{"point_id": "recap", "role": "recap", "ops": [], "narration": "-"}])
    return {"topic": q, "structure": subject, "analysis": {"subject": subject, "ask": q[0].upper() + q[1:].rstrip("?") + "?",
            "shape": shape, "key_terms": terms, "jargon": [], "requirements": requirements, **extra},
            "answer_points": points, "scenes": scenes}


class Calls(list):
    override: dict


@pytest.fixture
def weak_llm(monkeypatch):
    calls = Calls()
    override = {}

    def fake(prompt, schema=None):
        calls.append(prompt)
        if "Rewrite the narration of these scenes" in prompt:
            return {"scenes": []}
        if "You check whether a short lesson answers" in prompt:
            return {"requirements": [], "does_lesson_answer_question": True, "fixes": []}
        q = prompt.split('Question from the user: "')[1].split('"\n')[0]
        return override.get(q) or _raw(q)

    monkeypatch.setattr(llm, "generate_json", fake)
    monkeypatch.setattr(lesson.tts, "synthesize", lambda text: {"id": "x", "path": None, "duration": len(text.split()) / 2.5})
    lesson._scene_cache.clear()
    calls.override = override
    return calls


def _texts(r):
    return [s["narration"] for s in r["scenes"]]


@pytest.mark.parametrize("q", list(Q))
def test_every_question_shape_is_answered(weak_llm, q):
    r = lesson.build_lesson(q)
    plan, scenes = r["plan"], r["scenes"]
    shape = plan["analysis"].get("shape")
    assert shape == answer.validated_shape(q, parse_topic(q), _raw(q)["analysis"])
    assert len(weak_llm) <= 3
    # every requirement has a covering scene, and "Answers your question" is reported separately from "Verified"
    check = r["answer_check"]
    assert check["passed"] and all(req["scenes"] for req in check["requirements"]), check
    # no filler: every scene teaches an answer point (or is the intro / recap)
    point_req = {p["id"]: p.get("requirement_id") for p in r["answer_points"]}
    assert all(s["point_id"] in point_req for s in scenes)
    # the deterministic gate (including the shape checks) passes on the final lesson
    assert answer.gate(plan, scenes, answer.context(plan)) == []
    # every sentence still matches the true state
    ctx = answer.context(plan)
    for i, s in enumerate(scenes):
        sim = {"before": s["before"], "steps": s["steps"], "state": s["state"]}
        kind = plan["structure"] if i == 0 and not s["steps"] else s["state"]["kind"]
        assert check_scene(kind, s, sim, i == 0, ctx) == [], (i, s["narration"])
    text = " ".join(_texts(r))
    if shape == "list":  # every known kind is named in a scene of its own, and the recap restates them all
        names = [v["name"] for v in concepts.variants_for(plan["structure"])]
        assert len(names) >= 3
        for v in concepts.variants_for(plan["structure"]):
            own = [s for s in scenes if s.get("point_id") not in ("intro", "recap") and re.search(v["pattern"], s["narration"], re.I)]
            assert own, (v["name"], _texts(r))
            assert re.search(v["pattern"], scenes[-1]["narration"], re.I), scenes[-1]["narration"]
            assert any(s.get("ops") for s in scenes if s.get("item") == v["name"]), f"{v['name']} has no picture"
    if shape in ("compare", "when"):
        for side in plan["analysis"]["sides"]:
            assert re.search(answer._side_pattern(side), text, re.I), (side, text)
        assert answer.VERDICT.search(text), text
    if shape == "misconception":
        assert any(answer.PREMISE_VERDICT.search(t) for t in _texts(r)[:3]), _texts(r)[:3]
    if shape == "data":  # the user's values, exactly and in order
        given = parse_topic(q)
        ops = [a for s in plan["scenes"] for o in s["ops"] for a in o["args"]]
        if given.values:
            seen = [v for v in ops if v in given.values]
            assert seen[: len(given.values)] == list(given.values)
        for u, v in given.edges:
            assert u in ops and v in ops
    assert not answer.missing_nouns(q, _texts(r)), answer.missing_nouns(q, _texts(r))


def test_types_of_array_names_every_type_with_its_own_view(weak_llm):
    r = lesson.build_lesson("how many types of array there are")
    kinds = {s["state"]["kind"] for s in r["scenes"]}
    assert {"array", "array_2d", "dyn_array", "jagged_array"} <= kinds  # a real view per type, not a generic 1D array
    resize = [st["last"] for s in r["scenes"] for st in s["steps"] if st["last"].get("resized")]
    assert resize and resize[0]["new_capacity"] == 2 * resize[0]["old_capacity"] and resize[0]["copied"] == resize[0]["old_capacity"]
    refused = [st["last"] for s in r["scenes"] for st in s["steps"] if st["last"].get("refused")]
    assert refused  # the static array really refuses a value when it is full
    assert re.search(r"\b5\b", r["scenes"][0]["narration"])  # "how many": the count is said, and it is counted by code
    assert [q["question"] for q in r["quiz"]] and all(q["options"][q["answer_index"]] for q in r["quiz"])


def test_root_cause_an_unsupported_answer_for_a_list_question_is_not_turned_into_a_generic_lesson(weak_llm):
    """The live bug: the analysis call said {"unsupported": true} and the old pipeline built "what is an array"."""
    weak_llm.override["how many types of array there are"] = {"unsupported": True}
    r = lesson.build_lesson("how many types of array there are")
    assert r["plan"]["analysis"]["shape"] == "list"
    text = " ".join(_texts(r))
    for v in concepts.variants_for("array"):
        assert re.search(v["pattern"], text, re.I), v["name"]
    assert not re.search(r"\breal life\b|\bused (?:in|for)\b", text, re.I)  # no generic real-world filler
    assert len(weak_llm) <= 3


def test_an_unsupported_topic_gets_an_honest_notice_with_the_closest_topics(weak_llm):
    with pytest.raises(planner.UnsupportedTopic) as e:
        lesson.build_lesson(UNSUPPORTED)
    assert "Closest topics" in str(e.value) and "array" in str(e.value)


def test_a_vague_question_asks_one_short_clarifying_question(weak_llm):
    with pytest.raises(answer.NeedsClarification):
        lesson.build_lesson(VAGUE)
    assert weak_llm == []  # no LLM call and no lesson for a question that cannot be answered as asked


def test_a_lesson_that_never_names_the_list_items_is_blocked():
    plan = {"analysis": {"shape": "list", "items": [{"name": "2D array", "pattern": r"\b2-?d\b"}], "count_facts": []}}
    scenes = [{"narration": "An array is a row of lockers.", "point_id": "p1"}, {"narration": "To sum up, arrays.", "point_id": "recap", "role": "recap"}]
    problems = answer.shape_problems(plan["analysis"], scenes)
    assert any("never named" in p for p in problems) and any("recap" in p for p in problems)


def test_question_shapes_are_classified_from_the_wording():
    cases = {"how many types of array there are": "list", "kinds of trees": "list", "stack vs queue": "compare",
             "difference between BFS and DFS": "compare", "why is bubble sort slow": "why", "is array access O(n)?": "misconception",
             "when should I use a linked list?": "when", "what is a vector": "definition", "insert 5, 3, 8 into a BST": "data",
             "what is the time complexity of bubble sort": "complexity", "help": "vague", "how does a queue work": "how",
             "what is a linked list and why do we use it": "multipart"}
    for q, shape in cases.items():
        assert answer.question_shape(q, parse_topic(q)) == shape, q
