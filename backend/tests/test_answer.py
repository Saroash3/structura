"""Answer-first lessons: the planner outlines the ANSWER (answer_points) and scenes are derived from it.

PRIORITY RULE: answer quality comes first; animation only supports the answer; every scene teaches one point.

The fake planner returns the plans seen in the browser BEFORE this change (for "what is stack": peek before push/pop,
a pop that never ties back to last-in-first-out, "constant time" and "underflow" unexplained, a recap that repeats
the intro, no real-world uses). The repair returns nothing, so the code alone must produce a good answer.
"""
import json

import pytest

import concepts
import eval_lessons
import focus
import lesson
import llm
import planner
from verifier import check_scene, lesson_errors, simulate


def _sc(ops, narration, role=None):
    return {"ops": [{"op": o, "args": a} for o, a in ops], "narration": narration, **({"role": role} if role else {})}


BEFORE = {
    "stack": [
        _sc([], "A stack is a pile where the last item in is the first item out, like a stack of plates: you only add to or take from the top."),
        _sc([("init", [3, 7, 12])], "Here is our starting stack with 3 at the bottom, 7 in the middle, and 12 at the top."),
        _sc([("peek", [])], "We peek at the stack to see the top item. The top is 12."),
        _sc([("push", [25])], "We push 25 onto the stack. The top is now 25."),
        _sc([("pop", [])], "We pop 25 off the top. The top is now 12."),
        _sc([("pop", [])], "We pop 12 off the top. The top is now 7."),
        _sc([], "Push and pop both take constant time, because only the top of the stack is ever touched."),
        _sc([], "If you try to pop from an empty stack, it causes an underflow error because no items are left to remove."),
        _sc([], "A stack is last in, first out: items are pushed onto the top and popped off the top, and nothing below the top is ever touched.")],
    "queue": [
        _sc([], "A queue is a line where the first item in is the first item out, like people waiting at a ticket counter."),
        _sc([("init", [10, 20])], "We initialize the queue with 10 and 20. The front is 10 and the back is 20."),
        _sc([("peek", [])], "Using peek, we look at the front of the queue without removing anything. We see 10 is still at the front."),
        _sc([("enqueue", [30])], "We enqueue 30, which adds it to the back of the line."),
        _sc([("dequeue", [])], "We dequeue 10 from the front. The front of the queue is now 20."),
        _sc([], "Enqueue and dequeue both take constant time, because we only ever touch the ends of the queue."),
        _sc([], "A queue follows a first-in, first-out rule. We add items to the back with enqueue and remove them from the front with dequeue.")],
    "linked_list": [
        _sc([], "A linked list is a chain of nodes, like a treasure hunt where each clue points to the next."),
        *[_sc([op], f"We insert {op[1][0]}.") for op in [("insert_head", [10]), ("insert_tail", [20]), ("insert_tail", [30]), ("insert_tail", [40])]],
        _sc([], "The list is now [10, 20, 30, 40].")],
    "array": [
        _sc([], "The array is empty and its size is 0."),
        _sc([("append", [4])], "We add a number."), _sc([("append", [9])], "We add another number."), _sc([("append", [7])], "And one more."),
        _sc([("get", [1])], "We read a value."), _sc([], "That was an array.")],
    "delete": [
        _sc([], "A linked list is a chain of nodes where each one points to the next, like a treasure hunt."),
        *[_sc([op], f"We add {op[1][0]}.") for op in [("insert_head", [10]), ("insert_tail", [20]), ("insert_tail", [30]), ("insert_tail", [40])]],
        _sc([("search", [20])], "We search for 20 to find the node before the one we want to remove."),
        _sc([("delete_value", [30])], "We delete 30 from the middle of the list. The list is now [10, 20, 40]."),
        _sc([], "Inserting at the head is instant, but finding a value means walking the chain from the head.")],
    "bfs": [
        _sc([], "Let us look at a graph."),
        _sc([("add_edge", ["A", "B"]), ("add_edge", ["A", "C"]), ("add_edge", ["B", "D"]), ("add_edge", ["C", "D"])], "We build a graph."),
        _sc([("start_bfs", ["A"])], "We begin the search."), _sc([("visit", [])], "We keep exploring."), _sc([], "The size is 4.")],
}
CASE_OF = {"what_is_stack": "stack", "what_is_queue": "queue", "what_is_ll": "linked_list", "array": "array", "delete": "delete", "bfs": "bfs"}


@pytest.fixture
def fake_llm(monkeypatch):
    calls = {"plan": 0, "repair": 0}

    def fake(prompt, schema=None):
        if "Rewrite the narration of these scenes" in prompt:
            calls["repair"] += 1
            return {"scenes": []}
        if "Reword these" in prompt:
            raise RuntimeError("offline")
        calls["plan"] += 1
        q = prompt.split('Question from the user: "')[1].split('"')[0]
        key = next(CASE_OF[k] for k, t in eval_lessons.CASES.items() if t == q and k in CASE_OF)
        structure = {"delete": "linked_list", "bfs": "graph_bfs"}.get(key, key)
        return json.loads(json.dumps({"topic": q, "structure": structure, "scenes": BEFORE[key]}))

    monkeypatch.setattr(llm, "generate_json", fake)
    monkeypatch.setattr(lesson.tts, "synthesize", lambda text: {"id": "x", "path": None, "duration": len(text.split()) / 2.5})
    lesson._scene_cache.clear()
    return calls


# ---------------------------------------------------------------- golden cases (offline)
@pytest.mark.parametrize("name", ["what_is_stack", "what_is_queue", "what_is_ll", "array", "delete", "bfs"])
def test_golden_answer_first_lessons(fake_llm, name):
    result = lesson.build_lesson(eval_lessons.CASES[name])
    assert eval_lessons.CHECKS[name](result) == []
    assert fake_llm["plan"] == 1 and fake_llm["repair"] <= 2  # one planning call, batched repairs only


def test_what_is_stack_answers_like_a_teacher(fake_llm):
    r = lesson.build_lesson("what is stack")
    kinds = [s["kind"] for s in r["scenes"]]
    assert kinds[:3] == ["definition", "analogy", "rule"] and kinds[-2:] == ["uses", "recap"]
    ops = [o["op"] for s in r["scenes"] for o in s["ops"]]
    assert ops == ["push", "push", "push", "pop"]  # simplest first, the proving step last, no peek
    pop = next(s for s in r["scenes"] if any(o["op"] == "pop" for o in s["ops"]))
    assert "last one in, so it is the first one out" in pop["narration"]  # the demo ties back to the rule
    text = " ".join(s["narration"] for s in r["scenes"])
    assert "constant time" not in text and "underflow" not in text
    assert "undo" in text and concepts.overlap(r["scenes"][0]["narration"], r["scenes"][-1]["narration"]) <= concepts.MAX_RECAP_OVERLAP
    q = next(q for q in r["quiz"] if q["kind"] == "principle")
    assert "comes out first" in q["question"] and q["options"][q["answer_index"]] == str(pop["steps"][-1]["last"]["removed"])
    assert {q["kind"] for q in r["quiz"]} == {"principle", "real_world", "trace"}
    points = {p["id"]: p for p in r["answer_points"]}
    assert all(s["point_id"] in points for s in r["scenes"]) and len(points) == 6


def test_good_llm_plan_is_kept(monkeypatch):
    """When Gemini plans the answer well, its own wording ships (no templates, no repair)."""
    good = json.loads(json.dumps(planner.EXAMPLE_WHAT_IS_STACK))
    calls = []
    monkeypatch.setattr(llm, "generate_json", lambda p, s=None: calls.append(p) or (good if "Question from the user" in p else {"scenes": []}))
    monkeypatch.setattr(lesson.tts, "synthesize", lambda text: {"id": "x", "path": None, "duration": len(text.split()) / 2.5})
    lesson._scene_cache.clear()
    r = lesson.build_lesson("what is stack")
    assert [s["narration_source"] for s in r["scenes"]].count("llm") == len(r["scenes"])
    assert not any("Rewrite the narration" in p for p in calls)
    assert eval_lessons.CHECKS["what_is_stack"](r) == []


# ---------------------------------------------------------------- the individual checks
def _stack_ctx():
    return focus.context(focus.analyze("what is stack").to_dict())


def test_jargon_must_be_explained_first():
    assert concepts.undefined_jargon(["Push takes constant time."]) == {0: ["constant time"]}
    assert concepts.undefined_jargon(["Push takes constant time, which means it is always a single quick step."]) == {}
    assert concepts.undefined_jargon(["It is LIFO."]) == {0: ["LIFO"]}
    assert concepts.undefined_jargon(["It is last in, first out.", "That is LIFO."]) == {}
    assert concepts.undefined_jargon(["Popping an empty stack is an underflow."]) == {}  # explained right there


def test_recap_that_repeats_the_intro_is_rejected():
    ctx = _stack_ctx()
    scenes = [{"ops": [], "role": "setup"}, {"ops": [], "role": "recap"}]
    st = simulate("stack", [{"ops": []}])[0]
    intro, old_recap = BEFORE["stack"][0]["narration"], BEFORE["stack"][-1]["narration"]  # the recap seen in the browser
    errors = lesson_errors([intro, old_recap], scenes, [st, st], ctx)
    assert any("repeats the intro" in e for e in errors.get(1, []))
    near_copy = "A pile where the last item in is the first item out, like plates: add to or take from the top."
    assert concepts.overlap(intro, near_copy) > concepts.MAX_RECAP_OVERLAP  # Jaccard on content words
    assert 1 in lesson_errors([intro, near_copy], scenes, [st, st], ctx)
    assert 1 not in lesson_errors([intro, ctx["recap"]], scenes, [st, st], ctx)  # takeaways in new wording pass


def test_demo_must_say_what_it_proves():
    ctx = _stack_ctx()
    scenes = [{"ops": [{"op": "push", "args": [v]}], "role": "core"} for v in (12, 7, 25)] + [{"ops": [{"op": "pop", "args": []}], "role": "core"}]
    sims = simulate("stack", scenes)
    plain = ["We push 12.", "We push 7.", "We push 25.", "We pop 25 off the top. The top is now 7."]
    errors = lesson_errors(plain, scenes, sims, ctx)
    assert 3 in errors and "25 was the last one in, so it is the first one out" in errors[3][0]
    proved = plain[:3] + ["We pop. 25 was the last one in, so it is the first one out. The top is now 7."]
    assert lesson_errors(proved, scenes, sims, ctx) == {}
    assert check_scene("stack", {**scenes[3], "narration": proved[3]}, sims[3]) == []  # "first one" is not the number 1


def test_each_point_kind_is_checked():
    ctx = _stack_ctx()
    st = simulate("stack", [{"ops": []}])[0]
    assert check_scene("stack", {"ops": [], "kind": "uses", "role": "core", "narration": "Stacks are useful."}, st, False, ctx)
    assert check_scene("stack", {"ops": [], "kind": "uses", "role": "core", "narration": ctx["uses_sentence"]}, st, False, ctx) == []
    assert check_scene("stack", {"ops": [], "kind": "rule", "role": "core", "narration": "Stacks are neat."}, st, False, ctx)
    assert check_scene("stack", {"ops": [], "kind": "rule", "role": "core", "narration": ctx["rule"]}, st, False, ctx) == []
    assert check_scene("stack", {"ops": [], "kind": "analogy", "role": "core", "narration": ctx["analogy"]}, st, False, ctx) == []
    assert check_scene("stack", {"ops": [], "role": "setup", "narration": "-"}, st, True, ctx)  # placeholders never ship


@pytest.mark.parametrize("structure", list(concepts.WHAT_IS))
def test_what_is_templates_verify(structure):
    topic = {"linked_list": "what is a linked list", "binary_tree": "what is a binary search tree", "graph_bfs": "what is breadth first search",
             "bubble_sort": "what is bubble sort"}.get(structure, f"what is a {structure}")
    a = focus.analyze(topic)
    assert a.structure == structure and a.intent == "what_is"
    ctx = focus.context(a.to_dict())
    st = simulate(structure, [{"ops": []}])[0]
    for kind, role, _ in concepts.WHAT_IS_POINTS:
        if kind == "demo":
            continue
        text = {"definition": ctx["intro"], "analogy": ctx["analogy"], "rule": ctx["rule"], "uses": ctx["uses_sentence"], "recap": ctx["recap"]}[kind]
        assert check_scene(structure, {"ops": [], "kind": kind, "role": role, "narration": text}, st, kind == "definition", ctx) == [], (kind, text)
    assert concepts.overlap(ctx["intro"], ctx["recap"]) <= concepts.MAX_RECAP_OVERLAP
    assert concepts.undefined_jargon([ctx["intro"], ctx["analogy"], ctx["rule"], ctx["uses_sentence"], ctx["recap"]]) == {}


def test_what_is_plan_with_a_bad_op_keeps_the_answer_text(monkeypatch):
    """Live, Gemini planned an invalid op for "what is stack" and three whole plans were thrown away. Now the answer text is kept
    (the demo ops come from code anyway) and no retry call is made."""
    plan = json.loads(json.dumps(planner.EXAMPLE_WHAT_IS_STACK))
    plan["scenes"][3]["ops"] = [{"op": "pop", "args": []}]  # pop on an empty stack: impossible
    calls = []
    monkeypatch.setattr(llm, "generate_json", lambda p, s=None: calls.append(p) or plan)
    out = planner.make_plan("what is stack")
    assert len(calls) == 1
    texts = {s["kind"]: s["narration"] for s in out["scenes"] if not s["ops"]}
    assert texts["analogy"].startswith("Think of a stack of plates") and "undo" in texts["uses"]
    assert [o["op"] for s in out["scenes"] for o in s["ops"]] == ["push", "push", "push", "pop"]
