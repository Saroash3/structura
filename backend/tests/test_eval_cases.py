"""The two fixed evaluation cases, run offline with a deliberately bad fake LLM.

The fake planner uses the WRONG labels (1-4 instead of A-D) and vague narration ("We continue exploring"),
exactly the failures seen in the browser. The pipeline must still ship the user's graph, specific narration
and a quiz about the same graph.
"""
import json
import re

import pytest

import eval_lessons
import lesson
import llm
import planner
import quiz
from topic_parser import parse_topic
from verifier import check_scene, simulate

VAGUE_BFS_PLAN = {
    "topic": "BFS", "structure": "graph_bfs", "scenes": [
        {"id": 1, "ops": [], "narration": "Let us look at a graph."},
        {"id": 2, "ops": [{"op": "add_edge", "args": [1, 2]}, {"op": "add_edge", "args": [1, 3]}, {"op": "add_edge", "args": [2, 4]}],
         "narration": "We build a graph."},
        {"id": 3, "ops": [{"op": "start_bfs", "args": [1]}], "narration": "We begin the search."},
        {"id": 4, "ops": [{"op": "visit", "args": []}], "narration": "We continue exploring the remaining connected paths."},
        {"id": 5, "ops": [{"op": "visit", "args": []}], "narration": "We keep exploring."},
        {"id": 6, "ops": [], "narration": "The size is 4."},
    ]}

VAGUE_ARRAY_PLAN = {
    "topic": "array", "structure": "array", "scenes": [
        {"id": 1, "ops": [], "narration": "The array is empty and its size is 0."},
        {"id": 2, "ops": [{"op": "append", "args": [4]}], "narration": "We add a number."},
        {"id": 3, "ops": [{"op": "append", "args": [9]}], "narration": "We add another number."},
        {"id": 4, "ops": [{"op": "append", "args": [7]}], "narration": "And one more."},
        {"id": 5, "ops": [{"op": "get", "args": [1]}], "narration": "We read a value."},
        {"id": 6, "ops": [], "narration": "That was an array."},
    ]}


@pytest.fixture
def fake_llm(monkeypatch):
    prompts = []

    def fake(prompt, schema=None):
        prompts.append(prompt)
        if "Rewrite the narration of these scenes" in prompt:
            return {"scenes": []}  # repair gives nothing back: templates must take over
        if "Reword these" in prompt:
            raise RuntimeError("offline")
        return json.loads(json.dumps(VAGUE_BFS_PLAN if "graph" in prompt.split("Audience level")[0] else VAGUE_ARRAY_PLAN))

    monkeypatch.setattr(llm, "generate_json", fake)
    monkeypatch.setattr(lesson.tts, "synthesize", lambda text: {"id": "x", "path": None, "duration": len(text.split()) / 2.5})
    lesson._scene_cache.clear()
    return prompts


def test_topic_parser_reads_the_users_graph():
    g = parse_topic(eval_lessons.CASES["bfs"])
    assert g.edges == [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")] and g.start == "A"
    assert parse_topic("what is an array").values == []


def test_bfs_case_uses_user_graph_specific_narration_and_same_graph_quiz(fake_llm):
    result = lesson.build_lesson(eval_lessons.CASES["bfs"])
    assert eval_lessons.check_bfs_lesson(result) == []
    # vague lines were replaced; size talk is gone
    text = " ".join(s["narration"] for s in result["scenes"])
    assert "continue exploring" not in text and "size" not in text.lower()
    # the repair call got each scene's TRUE state (labels A-D and the queue)
    repair = next(p for p in fake_llm if "Rewrite the narration of these scenes" in p)
    assert '"true_state_after_each_op"' in repair and '"queue"' in repair and '"B"' in repair
    # the planner was told to use the user's graph
    assert '["A", "B"]' in fake_llm[0] and 'start_bfs ["A"]' in fake_llm[0]


def test_array_case_teaches_required_concepts_and_quiz_reuses_values(fake_llm):
    result = lesson.build_lesson(eval_lessons.CASES["array"])
    assert eval_lessons.check_array_lesson(result) == []
    intro = result["scenes"][0]["narration"]
    assert "array" in intro.lower() and "size" not in intro  # a plain definition, not "the size is 0"
    analogy = next(sc for sc in result["scenes"] if sc.get("kind") == "analogy")["narration"]
    assert re.search(r"\blike\b|\bthink of\b", analogy, re.I)  # the analogy has its own scene now


def test_vague_bfs_visit_is_rejected_and_specific_one_accepted():
    plan = {"structure": "graph_bfs", "scenes": [
        {"ops": [{"op": "add_edge", "args": e} for e in (["A", "B"], ["A", "C"], ["B", "D"], ["C", "D"])]},
        {"ops": [{"op": "start_bfs", "args": ["A"]}]},
        {"ops": [{"op": "visit", "args": []}]},
        {"ops": [{"op": "visit", "args": []}]}]}
    sim = simulate("graph_bfs", plan["scenes"])[3]  # visits B; queue is now [C, D]
    vague = {"ops": plan["scenes"][3]["ops"], "narration": "We continue exploring the remaining connected paths."}
    errors = check_scene("graph_bfs", vague, sim)
    assert any("node visited" in e for e in errors) and any("queue" in e for e in errors)
    good = {"ops": plan["scenes"][3]["ops"], "narration": "Visit B. Enqueue D. Queue is now [C, D]."}
    assert check_scene("graph_bfs", good, sim) == []
    wrong_queue = {"ops": plan["scenes"][3]["ops"], "narration": "Visit B. Queue is now [D, C]."}
    assert any("queue is [D, C]" in e for e in check_scene("graph_bfs", wrong_queue, sim))
    queued_not_visited = {"ops": plan["scenes"][3]["ops"], "narration": "Visit B. D is already visited. Queue is now [C, D]."}
    assert any("waiting in the queue" in e for e in check_scene("graph_bfs", queued_not_visited, sim))
    wrong_node = {"ops": plan["scenes"][3]["ops"], "narration": "Visit C. Queue is now [C, D]."}
    assert any("visits C" in e for e in check_scene("graph_bfs", wrong_node, sim))


def test_sort_narration_must_show_compare_and_array():
    scenes = [{"ops": [{"op": "load", "args": [7, 3, 5]}]}, {"ops": [{"op": "step", "args": []}]}]
    sim = simulate("bubble_sort", scenes)[1]
    ok = {"ops": scenes[1]["ops"], "narration": "Compare 7 and 3. 7 is bigger, so swap. Array is now [3, 7, 5]."}
    assert check_scene("bubble_sort", ok, sim) == []
    assert check_scene("bubble_sort", {"ops": scenes[1]["ops"], "narration": "We compare two numbers and swap them."}, sim)
    assert check_scene("bubble_sort", {"ops": scenes[1]["ops"], "narration": "Compare 7 and 3, swap. Array is now [7, 3, 5]."}, sim)


def test_no_size_talk_for_graphs_and_trees():
    scenes = [{"ops": [{"op": "insert_bst", "args": [8]}]}]
    sim = simulate("binary_tree", scenes)[0]
    assert any("size" in e for e in check_scene("binary_tree", {"ops": scenes[0]["ops"], "narration": "Insert 8. The size is 1."}, sim))


def test_user_values_are_forced_into_the_plan(monkeypatch):
    bad = {"topic": "stack", "structure": "stack", "scenes": [
        {"ops": [], "narration": "intro"}, {"ops": [{"op": "push", "args": [1]}], "narration": "x"},
        {"ops": [{"op": "pop", "args": []}], "narration": "y"}, {"ops": [], "narration": "recap"}]}
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: json.loads(json.dumps(bad)))
    plan = planner.make_plan("push 4, 7, 2 onto a stack")
    pushed = [o["args"][0] for s in plan["scenes"] for o in s["ops"] if o["op"] == "push"]
    assert pushed[:3] == [4, 7, 2]


def test_quiz_for_bfs_uses_lesson_labels():
    plan = {"structure": "graph_bfs", "scenes": [
        {"ops": [{"op": "add_edge", "args": e} for e in (["P", "Q"], ["P", "R"], ["Q", "S"])]},
        {"ops": [{"op": "start_bfs", "args": ["P"]}]}]}
    qs = quiz.lesson_questions(plan, "s")
    assert qs and all("P-Q" in q["question"] for q in qs)
    assert all(set(o) <= set("PQRS[], empty") for q in qs for o in q["options"])
