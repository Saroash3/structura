import pytest

from structures import OpError
from verifier import check_narration, facts, simulate, verify_plan

QUEUE_PLAN = {
    "structure": "queue",
    "scenes": [
        {"id": 1, "ops": [], "narration": "A queue is first in, first out, like people waiting in line at a shop."},
        {"id": 2, "ops": [{"op": "enqueue", "args": [5]}], "narration": "We enqueue 5. The front is 5 and the size is 1."},
        {"id": 3, "ops": [{"op": "enqueue", "args": [8]}], "narration": "We enqueue 8 at the back. The front is still 5, the back is 8, the size is 2."},
        {"id": 4, "ops": [{"op": "dequeue", "args": []}], "narration": "We dequeue, removing 5. The front is 8."},
    ],
}


def test_true_states_carry_across_scenes():
    sims = simulate("queue", QUEUE_PLAN["scenes"])
    assert sims[0]["state"]["size"] == 0
    assert sims[2]["state"]["items"] == [5, 8]
    assert sims[3]["before"]["items"] == [5, 8]
    assert sims[3]["state"]["items"] == [8]


def test_correct_plan_verifies_without_changes():
    scenes = verify_plan(QUEUE_PLAN)
    assert all(s["verified"] and s["narration_source"] == "llm" for s in scenes)
    assert scenes[3]["narration"] == QUEUE_PLAN["scenes"][3]["narration"]


def test_wrong_narration_is_caught():
    sim = simulate("queue", QUEUE_PLAN["scenes"])[3]
    # Truth after the dequeue: removed 5, front 8, size 1. Every claim below is wrong.
    errors = check_narration("We dequeue, removing 8. The front is 5 and the size is 2.", facts(sim))
    assert any("removed" in e for e in errors)
    assert any("front is 5" in e for e in errors)
    assert any("size is 2" in e for e in errors)


def test_invented_number_is_caught():
    sim = simulate("queue", QUEUE_PLAN["scenes"])[2]
    assert check_narration("Now 42 joins the queue.", facts(sim))


def test_false_empty_claim_is_caught():
    sim = simulate("queue", QUEUE_PLAN["scenes"])[2]
    assert check_narration("The queue is now empty.", facts(sim))


def test_stack_top_claim():
    scenes = [{"ops": [{"op": "push", "args": [3]}]}, {"ops": [{"op": "push", "args": [7]}]}]
    sim = simulate("stack", scenes)[1]
    assert check_narration("We push 7. The top is 7 and the size is 2.", facts(sim)) == []
    assert check_narration("The top is 3.", facts(sim))


def test_fixer_called_only_for_failing_scene():
    plan = {**QUEUE_PLAN, "scenes": [dict(s) for s in QUEUE_PLAN["scenes"]]}
    plan["scenes"][3] = {**plan["scenes"][3], "narration": "We dequeue, removing 8. The front is 5."}
    calls = []

    def fixer(scene, sim, errors):
        calls.append(scene["id"])
        return "We dequeue, removing 5 from the front. The front is 8 and the size is 1."

    scenes = verify_plan(plan, fixer)
    assert calls == [4]
    assert scenes[3]["narration_source"] == "llm-fixed"
    assert "removing 5" in scenes[3]["narration"]


def test_falls_back_to_template_if_fixer_keeps_lying():
    plan = {**QUEUE_PLAN, "scenes": [dict(s) for s in QUEUE_PLAN["scenes"]]}
    plan["scenes"][3] = {**plan["scenes"][3], "narration": "We dequeue, removing 8."}
    scenes = verify_plan(plan, lambda *a: "Still wrong: removing 99.")
    s = scenes[3]
    assert s["narration_source"] == "template" and s["verified"]
    assert check_narration(s["narration"], facts({"before": s["before"], "steps": s["steps"], "state": s["state"]})) == []


def test_impossible_op_raises():
    with pytest.raises(OpError):
        verify_plan({"structure": "stack", "scenes": [{"id": 1, "ops": [{"op": "pop", "args": []}], "narration": "x"}]})
