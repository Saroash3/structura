"""Lessons answer the user's actual question (question analysis, roles, pointer narration, focused quiz).

The fake planner returns the plans that were seen in the browser before this fix: the list built with 4 separate
inserts, a one-sentence delete, "List is now [10, 20, 40]" array notation, and a recap about head-insert speed.
The repair call returns nothing, so the code alone has to turn them into focused, verified lessons.
"""
import json
import re

import pytest

import eval_lessons
import focus
import lesson
import planner
import llm
import quiz
from structures import make
from topic_parser import parse_topic
from verifier import check_scene, simulate, template_narration, verify_plan


def _sc(ops, narration):
    return {"ops": [{"op": o, "args": a} for o, a in ops], "narration": narration}


INSERTS = [("insert_head", [10]), ("insert_tail", [20]), ("insert_tail", [30]), ("insert_tail", [40])]
OLD_PLANS = {
    "delete": [_sc([], "A linked list is a chain of nodes where each one points to the next, like a treasure hunt."),
               *[_sc([op], f"We add {op[1][0]}. The list is now [{', '.join(str(v) for _o, a in INSERTS[: i + 1] for v in a)}].")
                 for i, op in enumerate(INSERTS)],
               _sc([("search", [20])], "We search for 20 to find the node before the one we want to remove. We are now at 20."),
               _sc([("delete_value", [30])], "We delete 30 from the middle of the list. The list is now [10, 20, 40]."),
               _sc([], "Inserting at the head is instant, but finding a value means walking the chain from the head. List is now [10, 20, 40].")],
    "what_is_ll": [_sc([], "A linked list is a chain of nodes, like a treasure hunt where each clue points to the next."),
                   *[_sc([op], f"We insert {op[1][0]}.") for op in INSERTS],
                   _sc([], "The list is now [10, 20, 30, 40].")],
    "search": [_sc([], "A linked list is a chain of nodes, like a treasure hunt."),
               *[_sc([op], f"We insert {op[1][0]}.") for op in INSERTS],
               _sc([("search", [30])], "We search for 30 and find it."),
               _sc([], "Searching is slow. List is now [10, 20, 30, 40].")],
}


@pytest.fixture
def fake_llm(monkeypatch):
    prompts = []

    def fake(prompt, schema=None):
        prompts.append(prompt)
        if "Rewrite the narration of these scenes" in prompt:
            return {"scenes": []}  # the repair gives nothing back: templates must take over
        if "Reword these" in prompt:
            raise RuntimeError("offline")
        q = prompt.split('Question from the user: "')[1].split('"')[0]
        if "difference" in q:
            return {"topic": q, "structure": "unsupported", "scenes": []}  # what the old pipeline did
        key = "delete" if "delete" in q else "search" if "search" in q else "what_is_ll"
        return json.loads(json.dumps({"topic": q, "structure": "linked_list", "scenes": OLD_PLANS[key]}))

    monkeypatch.setattr(llm, "generate_json", fake)
    monkeypatch.setattr(lesson.tts, "synthesize", lambda text: {"id": "x", "path": None, "duration": len(text.split()) / 2.5})
    lesson._scene_cache.clear()
    return prompts


# ---------------------------------------------------------------- 1. question analysis
@pytest.mark.parametrize("topic,structure,intent,focus_,core", [
    ("what is linked list", "linked_list", "what_is", "what_is", ["walk"]),
    ("how do I delete a node from the middle of a linked list", "linked_list", "how_op", "delete", ["walk", "delete_value"]),
    ("how do I search a linked list", "linked_list", "how_op", "search", ["walk", "search"]),
    ("difference between an array and a linked list", "linked_list", "compare", "compare", ["get", "insert_at", "walk", "insert_after"]),
    ("show BFS on this graph: A-B, A-C, B-D, C-D, starting from A", "graph_bfs", "trace_on_input", "bfs", ["start_bfs", "visit"]),
    ("what is an array", "array", "what_is", "what_is", ["get", "insert_at"]),
    ("why is inserting into the middle of an array slow", "array", "why", "insert", ["insert_at"]),
    ("push 4, 7, 2 onto a stack", "stack", "trace_on_input", "insert", ["push"]),
])
def test_question_analysis(topic, structure, intent, focus_, core):
    a = focus.analyze(topic, parse_topic(topic))
    assert (a.structure, a.intent, a.focus, a.core_ops) == (structure, intent, focus_, core)
    assert a.must_answer.endswith("?")


def test_unsupported_operation_is_refused_not_replaced():
    with pytest.raises(focus.UnsupportedTopic, match="reverse"):
        focus.analyze("how do I reverse a linked list", parse_topic("how do I reverse a linked list"))


# ---------------------------------------------------------------- 2. shaping: roles, one setup scene, the core walk
def test_old_delete_plan_is_reshaped_around_the_question():
    a = focus.analyze(eval_lessons.CASES["delete"])
    plan = focus.shape({"topic": "t", "structure": "linked_list", "scenes": json.loads(json.dumps(OLD_PLANS["delete"]))}, a)
    roles = [s["role"] for s in plan["scenes"]]
    ops = [(o["op"], o["args"]) for s in plan["scenes"] for o in s["ops"]]
    assert roles.count("setup") == 2 and roles[0] == "setup" and roles[-1] == "recap"
    assert ops == [("init", [10, 20, 30, 40]), ("walk", [10]), ("walk", [20]), ("delete_value", [30])]  # the search scene was off-focus
    assert all(r in focus.ROLES for r in roles)


# ---------------------------------------------------------------- 4. pointer-aware verification
def _delete_sim():
    scenes = [_sc([("init", [10, 20, 30, 40])], ""), _sc([("walk", [10])], ""), _sc([("walk", [20])], ""), _sc([("delete_value", [30])], "")]
    return scenes, simulate("linked_list", scenes)


def test_pointer_claims_are_checked_against_the_real_list():
    scenes, sims = _delete_sim()
    good = ("Now rewire: 20's next pointer now points to 40, so 30 is skipped and no longer reachable. "
            "The list is now head -> 10 -> 20 -> 40 -> null.")
    assert check_scene("linked_list", {**scenes[3], "narration": good}, sims[3]) == []
    wrong_ptr = "We delete 30: 20 now points to 30, so 30 is skipped. The list is now head -> 10 -> 20 -> 40 -> null."
    assert any("20 points to 30" in e for e in check_scene("linked_list", {**scenes[3], "narration": wrong_ptr}, sims[3]))
    wrong_chain = "We delete 30. 20 now points to 40, so 30 is skipped. The list is now head -> 10 -> 30 -> 40 -> null."
    assert any("chain" in e for e in check_scene("linked_list", {**scenes[3], "narration": wrong_chain}, sims[3]))
    wrong_skip = "We delete 30. 20 now points to 40, so 20 is skipped."
    assert any("20 is skipped" in e for e in check_scene("linked_list", {**scenes[3], "narration": wrong_skip}, sims[3]))


def test_one_sentence_delete_is_rejected_with_the_reasons():
    scenes, sims = _delete_sim()
    vague = "We delete 30 from the middle of the list."
    errors = check_scene("linked_list", {**scenes[3], "narration": vague}, sims[3])
    text = " ".join(errors)
    assert "node before it" in text and "skipped" in text and "pointer being rewired" in text  # needs prev, skip and pointer talk
    bracket = check_scene("linked_list", {**scenes[3], "narration": "Delete 30: 20 now points to 40, so 30 is skipped. The list is now [10, 20, 40]."}, sims[3])
    assert any("with its pointers" in e for e in bracket)  # array notation is rejected for linked lists


def test_walk_hops_must_name_the_node_and_where_it_points():
    scenes, sims = _delete_sim()
    assert check_scene("linked_list", {**scenes[2], "narration": "We keep walking."}, sims[2])
    assert check_scene("linked_list", {**scenes[2], "narration": "Move to 20. 20 points to 30, our target, so we stop."}, sims[2]) == []


def test_focus_checks_intro_recap_and_off_topic():
    a = focus.analyze(eval_lessons.CASES["delete"])
    ctx = focus.context(a.to_dict())
    scenes, sims = _delete_sim()
    empty = {"before": sims[0]["before"], "steps": [], "state": sims[0]["before"]}
    generic_intro = {"ops": [], "role": "setup", "narration": "A linked list is a chain of nodes, like a treasure hunt where each clue leads on."}
    assert any("lead straight into the question" in e or "generic definition" in e for e in check_scene("linked_list", generic_intro, empty, True, ctx))
    end = {"before": sims[3]["state"], "steps": [], "state": sims[3]["state"]}  # the recap has no ops
    off = {"ops": [], "role": "recap", "narration": "Inserting at the head is instant, but finding a value means walking the chain."}
    errors = check_scene("linked_list", off, end, False, ctx)
    assert any("ANSWER" in e for e in errors) and any("inserting at the head" in e for e in errors)
    assert check_scene("linked_list", {"ops": [], "role": "recap", "narration": ctx["recap"]}, end, False, ctx) == []
    assert check_scene("linked_list", {"ops": [], "role": "setup", "narration": ctx["intro"]}, empty, True, ctx) == []


@pytest.mark.parametrize("structure,ops", [
    ("linked_list", [("init", [10, 20, 30]), ("walk", [10]), ("walk", [20]), ("delete_value", [30]), ("delete_value", [10]),
                     ("delete_value", [99]), ("search", [99]), ("search", [20]), ("insert_after", [20, 25]), ("insert_head", [5]),
                     ("insert_tail", [50]), ("delete_value", [5]), ("delete_value", [20]), ("delete_value", [25]), ("delete_value", [50])]),
    ("array", [("init", [1, 2, 3])]), ("queue", [("init", [1, 2, 3])]), ("stack", [("init", [1, 2, 3])]), ("binary_tree", [("init", [5, 3, 8])]),
])
def test_templates_for_new_ops_always_verify(structure, ops):
    scenes = [_sc([op], "nothing useful") for op in ops]
    for s in verify_plan({"structure": structure, "scenes": scenes}):
        assert s["narration_source"] == "template"
        assert "[" not in s["narration"] or structure != "linked_list"  # pointer form, never brackets


@pytest.mark.parametrize("name", ["what_is_ll", "delete", "search", "compare", "array", "bfs"])
def test_focus_templates_verify_in_every_role(name):
    topic = eval_lessons.CASES[name]
    a = focus.analyze(topic, parse_topic(topic))
    ctx = focus.context(a.to_dict())
    state = make(a.structure).state()
    sim = {"before": state, "steps": [], "state": state}
    assert check_scene(a.structure, {"ops": [], "role": "setup", "narration": template_narration(a.structure, {"role": "setup"}, sim, True, ctx)}, sim, True, ctx) == []
    for role in ("core", "edge_case", "recap"):
        for k in range(3):
            text = template_narration(a.structure, {"role": role}, sim, False, ctx, k)
            assert check_scene(a.structure, {"ops": [], "role": role, "narration": text}, sim, False, ctx) == [], text
    for _name, _pattern, sentence, role in ctx["concepts"]:
        assert check_scene(a.structure, {"ops": [], "role": role, "narration": sentence}, sim, False, ctx) == [], sentence


# ---------------------------------------------------------------- 7. golden cases, end to end (offline)
@pytest.mark.parametrize("name", ["what_is_ll", "delete", "search", "compare"])
def test_golden_linked_list_cases(fake_llm, name):
    result = lesson.build_lesson(eval_lessons.CASES[name])
    assert eval_lessons.CHECKS[name](result) == []
    assert len([p for p in fake_llm if "Question from the user" in p]) == 1  # one planning call
    assert len([p for p in fake_llm if "Rewrite the narration" in p]) <= 2  # batched repairs only


def test_delete_lesson_body_and_quiz(fake_llm):
    result = lesson.build_lesson(eval_lessons.CASES["delete"])
    text = " ".join(s["narration"] for s in result["scenes"])
    assert "instant" not in text and "[10, 20, 40]" not in text
    assert result["scenes"][-1]["role"] == "recap" and "next pointer" in result["scenes"][-1]["narration"]
    roles = [s["role"] for s in result["scenes"]]
    assert roles.count("setup") <= 2 and "edge_case" in roles
    qs = result["quiz"]
    q = next(q for q in qs if "what does node 20 point to" in q["question"])
    assert q["options"][q["answer_index"]] == "40" and "30" in q["options"]  # the deleted node is a distractor
    assert sum("delet" in q["question"] for q in qs) >= 2
    assert not any("insert_head" in q["question"] or "insert_tail" in q["question"] for q in qs)


def test_planner_prompt_carries_the_analysis_and_a_different_example(fake_llm):
    planner.make_plan(eval_lessons.CASES["delete"])  # the focus pipeline (now the fallback of the question-driven one)
    prompt = next(p for p in fake_llm if "Question from the user" in p and "Template for intent" in p)
    assert "must_answer" in prompt and "How do you remove a node from the middle" in prompt
    assert '"structure": "queue"' in prompt  # the few-shot example is for a different structure
    assert "Template for intent how_op" in prompt


def test_quiz_for_search_tests_the_search():
    a = focus.analyze(eval_lessons.CASES["search"])
    plan = focus.shape({"topic": "t", "structure": "linked_list", "scenes": json.loads(json.dumps(OLD_PLANS["search"]))}, a)
    plan["scenes"][-1]["narration"] = focus.context(a.to_dict())["recap"]
    qs = quiz.focus_questions(plan, "seed")
    assert len(qs) >= 2 and sum("search" in q["question"].lower() for q in qs) >= 2
    assert any(q["kind"] == "principle" for q in qs)


def test_arrows_are_spoken_as_words():
    assert lesson.spoken("The list is now head -> 10 -> 20 -> null.") == "The list is now head, then 10, then 20, then null."


def test_what_is_lesson_uses_enough_data_and_a_principle_quiz():
    """Live, Gemini once built the what-is lesson on a 2-node list. The answer-first outline tops the demo data up to 4 nodes
    (keeping Gemini's own values) and the quiz tests the rule, never op counts or walk commands."""
    a = focus.analyze(eval_lessons.CASES["what_is_ll"])
    scenes = [_sc([], "intro"), _sc([("init", [10, 20])], "x"), _sc([("walk", [10]), ("walk", [20])], "x"),
              _sc([("insert_head", [5])], "x"), _sc([("delete_value", [10])], "x"), _sc([], "recap")]
    plan = focus.shape({"topic": "t", "structure": "linked_list", "scenes": scenes}, a)
    init = next(o["args"] for s in plan["scenes"] for o in s["ops"] if o["op"] == "init")
    assert init[:3] == [10, 20, 5] and len(init) == 4  # the LLM's values first
    for sc in plan["scenes"]:  # give the no-op points their template text, as verification would
        sc["narration"] = {"uses": "Playlists: each song knows the next song.", "rule": "Follow pointers from the head to null."}.get(sc["kind"], sc["narration"])
    qs = quiz.focus_questions(plan, "seed")
    kinds = [q["kind"] for q in qs]
    assert "principle" in kinds and "real_world" in kinds and len(qs) == 3
    assert not any("walk" in q["question"] for q in qs)
