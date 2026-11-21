"""Complexity questions: "what is the time complexity of bubble sort" must be answered with a derivation, not a demo.

PRIORITY RULE: the answer to the user's question comes first. A lesson that does not contain the answer is a failed
lesson even if every sentence is verified. BEFORE this change the question produced a "how does bubble sort work"
lesson (cut off mid-sort, no complexity, no O(n^2), no comparison count); these tests pin the new answer.

Every number comes from code: the counting functions run the real algorithms, and the verifier rejects any count,
sum, formula value, table row, doubling ratio or Big-O that does not match them. No LLM call is made.
"""
import pytest

import complexity
import eval_lessons
import focus
import lesson
import llm
import planner
import quiz
from structures import count_work, run_bubble, run_bfs
from verifier import answer_missing, check_scene, lesson_errors, simulate

BEFORE_BUBBLE = [t for _role, _op, t in eval_lessons.BEFORE_NARRATION["complexity_bubble"]]


@pytest.fixture
def no_llm(monkeypatch):
    calls = []

    def fake(prompt, schema=None):
        calls.append(prompt)
        if "Rewrite the narration of these scenes" in prompt:
            return {"scenes": []}  # a repair that fixes nothing: the code alone must produce the answer
        raise llm.LLMError("offline", "ai_busy")

    monkeypatch.setattr(llm, "generate_json", fake)
    monkeypatch.setattr(lesson.tts, "synthesize", lambda text: {"id": "x", "path": None, "duration": len(text.split()) / 2.5})
    lesson._scene_cache.clear()
    return calls


def _texts(r):
    return [s["narration"] for s in r["scenes"]]


# ---------------------------------------------------------------- golden cases
@pytest.mark.parametrize("name", ["complexity_bubble", "complexity_linear", "complexity_bfs"])
def test_golden_complexity_lessons(no_llm, name):
    r = lesson.build_lesson(eval_lessons.CASES[name])
    assert eval_lessons.CHECKS[name](r) == []
    assert len(no_llm) == 1  # the analysis call failed (offline); the code-built answer made no other call


def test_bubble_sort_complexity_answers_the_question(no_llm):
    r = lesson.build_lesson("what is time complexity of bubble sort")
    text = " ".join(_texts(r))
    # the test the spec asks for: a complexity lesson without these words fails
    assert "complexity" in text and "O(" in text
    kinds = [s["kind"] for s in r["scenes"]]
    assert kinds == ["goal", "measure", "demo", "demo", "demo", "derive", "big_o", "growth", "best", "worst", "recap"]
    demo = [s for s in r["scenes"] if s["kind"] == "demo"]
    assert [s["state"]["pass_counts"][-1] for s in demo] == [3, 2, 1]  # grouped by pass: 3, 2, 1
    assert demo[-1]["state"]["is_sorted"]  # run to completion, never cut off
    derive = next(s["narration"] for s in r["scenes"] if s["kind"] == "derive")
    assert "3 + 2 + 1 = 6" in derive and "n(n - 1) / 2" in derive and "(n - 1) + (n - 2) + ... + 1" in derive
    big_o = next(s["narration"] for s in r["scenes"] if s["kind"] == "big_o")
    assert "O(n²)" in big_o and "about 4 times" in big_o
    growth = next(s for s in r["scenes"] if s["kind"] == "growth")
    assert [(row["n"], row["count"]) for row in growth["state"]["rows"]] == [(4, 6), (8, 28), (16, 120), (100, 4950)]
    best = next(s for s in r["scenes"] if s["kind"] == "best")["state"]
    worst = next(s for s in r["scenes"] if s["kind"] == "worst")["state"]
    assert best["comparisons"] == 3 and best["early_exit"] and worst["comparisons"] == 6 and worst["swaps"] == 6
    assert "uses" not in kinds and "classroom" not in text  # no use-case scene: the question did not ask for uses
    assert all(s["verified"] for s in r["scenes"])
    q = r["quiz"]
    assert [x["kind"] for x in q] == ["complexity"] * 3
    assert q[0]["options"][q[0]["answer_index"]] == "10"  # comparisons for 5 items
    assert q[1]["options"][q[1]["answer_index"]] == "about 4 times as much"  # 8 -> 16 items
    assert q[2]["options"][q[2]["answer_index"]] == "a list that is already sorted"


def test_user_values_that_stop_early_still_get_the_worst_case(no_llm):
    r = lesson.build_lesson("time complexity of bubble sort on [3, 1, 2, 4, 5]")
    demo = [s for s in r["scenes"] if s["kind"] == "demo"]
    assert demo[0]["ops"] == [{"op": "step", "args": []}] * 4 and demo[-1]["state"]["early_exit"]
    derive = next(s["narration"] for s in r["scenes"] if s["kind"] == "derive")
    assert "stopped early" in derive and "4 + 3 + 2 + 1 = 10" in derive
    assert eval_lessons.check_complexity(r, "bubble_sort") == []


# ---------------------------------------------------------------- 1. the answer-coverage gate
def test_gate_flags_the_before_lesson():
    ctx = focus.context(focus.analyze("what is time complexity of bubble sort").to_dict())
    missing = {name for name, _kind, _hint in answer_missing(BEFORE_BUBBLE, ctx)}
    assert {"the word complexity", "the Big-O answer", "the formula n(n - 1) / 2"} <= missing


def test_gate_repairs_a_plan_that_never_answers(no_llm):
    """Gemini-style narration without the answer (the BEFORE wording) must not ship: it is repaired, then templated."""
    plan = planner.make_plan("what is time complexity of bubble sort")
    for s in plan["scenes"]:
        s["narration"] = "Bubble sort compares neighbours and swaps them when they are out of order."
    r = lesson.build_from_plan(plan)
    text = " ".join(_texts(r))
    assert "complexity" in text and "O(" in text and "n(n - 1) / 2" in text
    ctx = focus.context(r["analysis"])
    assert answer_missing(_texts(r), ctx) == []


def test_complexity_claim_needs_a_derivation():
    plan = planner.make_plan("what is time complexity of bubble sort")
    ctx = focus.context(plan["analysis"])
    sims = simulate(plan["structure"], plan["scenes"])
    texts = [complexity.narrate("bubble_sort", s, sim) for s, sim in zip(plan["scenes"], sims)]
    d = next(i for i, s in enumerate(plan["scenes"]) if s["kind"] == "derive")
    assert lesson_errors(texts, plan["scenes"], sims, ctx) == {}
    texts[d] = "Bubble sort does a lot of comparisons, and that is why it is slow."
    assert any("derivation" in e for e in lesson_errors(texts, plan["scenes"], sims, ctx)[d])


# ---------------------------------------------------------------- 4. every number must match the counting code
@pytest.mark.parametrize("kind,bad,why", [
    ("growth", "Counted for real: n = 4 needs 6 comparisons, n = 8 needs 30, n = 16 needs 120, and n = 100 needs 4950.", "real count is 28"),
    ("derive", "Add up the passes: 3 + 2 + 1 = 7 comparisons.", "the sum is 6"),
    ("derive", "Add up the passes: 3 + 2 + 1 = 6 comparisons, which is n(n - 1) / 2 = 4 × 3 / 2 = 5.", "wrong"),
    ("big_o", "Big O keeps the fastest-growing part, so bubble sort is O(n log n).", "not the complexity"),
    ("big_o", "Big O keeps the fastest-growing part, so bubble sort is O(n²). Double the items and the work grows about 2 times.", "about [4]"),
    ("best", "Best case: an already sorted list, [1, 2, 4, 5]. Pass 1 makes 6 comparisons and no swaps, so bubble sort stops early.", "count 6"),
    ("worst", "Worst case: a reversed list, [5, 4, 2, 1]. All 3 passes run: 3 + 2 = 5 comparisons. Array is now [1, 2, 4, 5].", "not this run"),
])
def test_wrong_complexity_numbers_are_rejected(kind, bad, why):
    plan = planner.make_plan("what is time complexity of bubble sort")
    ctx = focus.context(plan["analysis"])
    sims = simulate(plan["structure"], plan["scenes"])
    i = next(i for i, s in enumerate(plan["scenes"]) if s["kind"] == kind)
    good = complexity.narrate("bubble_sort", plan["scenes"][i], sims[i])
    kind_of = sims[i]["state"]["kind"]
    assert check_scene(kind_of, {**plan["scenes"][i], "narration": good}, sims[i], False, ctx) == []
    errors = check_scene(kind_of, {**plan["scenes"][i], "narration": bad}, sims[i], False, ctx)
    assert any(why in e for e in errors), errors


def test_counting_functions_run_the_real_algorithms():
    assert [count_work("bubble_sort", n) for n in complexity.SIZES] == [6, 28, 120, 4950]
    assert [count_work("bubble_sort", n, "best") for n in complexity.SIZES] == [3, 7, 15, 99]
    assert run_bubble([5, 1, 4, 2])["pass_counts"] == [3, 2, 1]
    assert run_bubble([1, 2, 4, 5]) == {"comparisons": 3, "swaps": 0, "pass_counts": [3], "early_exit": True}
    assert [count_work("linear_search", n) for n in complexity.SIZES] == complexity.SIZES
    assert count_work("linear_search", 100, "best") == 1
    assert run_bfs([("A", "B"), ("A", "C"), ("B", "D"), ("C", "E")], "A") == {"visits": 5, "checks": 8, "edges": 4}
    assert [count_work("bfs", n) for n in complexity.SIZES] == [3 * n - 2 for n in complexity.SIZES]  # V + 2E on a chain
    assert {count_work("stack_push", n) for n in complexity.SIZES} == {1}


# ---------------------------------------------------------------- 2. the new intent
@pytest.mark.parametrize("question,algo", [
    ("what is time complexity of bubble sort", "bubble_sort"), ("why is bubble sort n squared", "bubble_sort"),
    ("what is the big o of bubble sort", "bubble_sort"), ("best case of bubble sort", "bubble_sort"),
    ("how fast is bubble sort", "bubble_sort"), ("is bubble sort O(n^2)?", "bubble_sort"),
    ("time complexity of linear search", "linear_search"), ("time complexity of BFS", "bfs"),
    ("worst case of breadth first search", "bfs"), ("how fast is searching a linked list", "linked_list_search"),
    ("time complexity of stack push", "stack_push"), ("time complexity of pop", "stack_pop"),
    ("big o of dequeue", "queue_dequeue"), ("how fast is reading an array by index", "array_access"),
])
def test_complexity_intent(question, algo):
    a = focus.analyze(question)
    assert (a.intent, a.algorithm) == ("complexity", algo)


def test_other_questions_keep_their_intent():
    assert focus.analyze("what is a stack").intent == "what_is"
    assert focus.analyze("how does bubble sort work").intent == "how_op"
    assert focus.analyze("how do I delete a node from the middle of a linked list").intent == "how_op"


def test_unsupported_complexity_questions_say_what_is_supported():
    with pytest.raises(focus.UnsupportedTopic, match="bubble sort, linear search"):
        focus.analyze("time complexity of insertion sort")


@pytest.mark.parametrize("question", ["time complexity of linear search", "time complexity of BFS", "how fast is searching a linked list",
                                      "time complexity of stack push", "big o of dequeue", "how fast is reading an array by index",
                                      "how fast is inserting at the head of a linked list", "time complexity of pop",
                                      "time complexity of BFS on this graph: A-B, B-C, C-D, starting from B"])
def test_every_supported_algorithm_builds_a_verified_answer(no_llm, question):
    r = lesson.build_lesson(question)
    algo = r["analysis"]["algorithm"]
    assert eval_lessons.check_complexity(r, algo) == []
    assert all(s["narration_source"] == "template" for s in r["scenes"]) and len(no_llm) == 1


def test_quiz_is_computed_by_code():
    for question, first, ratio in [("time complexity of linear search", "5", "about 2 times as much"),
                                   ("time complexity of BFS", "13", "about 2 times as much"),
                                   ("time complexity of stack push", "1", "about the same")]:
        plan = planner.make_plan(question)
        q = quiz.make_quiz_from_plan(plan, seed=question)
        assert q[0]["options"][q[0]["answer_index"]] == first and q[1]["options"][q[1]["answer_index"]] == ratio


def test_math_is_spoken_in_words():
    assert lesson.spoken("so bubble sort is O(n²).") == "so bubble sort is O of n squared."
    assert lesson.spoken("n(n - 1) / 2 = 4 × 3 / 2 = 6") == "n times n minus 1, over 2 equals 4 times 3 over 2 equals 6"
    assert lesson.spoken("O(V + E)") == "O of V plus E" and lesson.spoken("head -> 10 -> null") == "head, then 10, then null"
