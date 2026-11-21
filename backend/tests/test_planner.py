import pytest

import planner


def test_plan_validation_rejects_wrong_op(monkeypatch):
    bad = {"topic": "q", "structure": "queue", "scenes": [
        {"id": 1, "ops": [], "narration": "intro"},
        {"id": 2, "ops": [{"op": "push", "args": [1]}], "narration": "push"}]}
    good = {"topic": "q", "structure": "queue", "scenes": [
        {"id": 1, "ops": [], "narration": "intro"},
        {"id": 2, "ops": [{"op": "enqueue", "args": [1]}], "narration": "We enqueue 1."}]}
    prompts = []

    def fake(prompt, schema=None):
        prompts.append(prompt)
        return bad if len(prompts) == 1 else good

    monkeypatch.setattr(planner.llm, "generate_json", fake)
    plan = planner.make_plan("how does enqueue work")  # how-to plans are retried with the error; what-is plans are salvaged
    assert any(o["op"] == "enqueue" for s in plan["scenes"] for o in s["ops"])
    assert len(prompts) == 2 and "not allowed" in prompts[1]


def test_plan_retries_on_impossible_op_then_builds_the_focused_plan_in_code(monkeypatch):
    bad = {"topic": "s", "structure": "stack", "scenes": [
        {"id": 1, "ops": [], "narration": "intro"},
        {"id": 2, "ops": [{"op": "pop", "args": []}], "narration": "pop"}]}
    calls = []
    monkeypatch.setattr(planner.llm, "generate_json", lambda p, s=None: calls.append(p) or bad)
    plan = planner.make_plan("how does pop work on a stack")
    assert len(calls) == 3  # first try + 2 retries with the error
    ops = [o["op"] for sc in plan["scenes"] for o in sc["ops"]]
    assert ops == ["init", "pop"] and plan["analysis"]["focus"] == "delete"
    assert [sc["role"] for sc in plan["scenes"]] == ["setup", "setup", "core", "recap"]


def test_plan_gives_up_when_the_question_cannot_be_analysed(monkeypatch):
    bad = {"topic": "s", "structure": "stack", "scenes": [
        {"id": 1, "ops": [], "narration": "intro"},
        {"id": 2, "ops": [{"op": "pop", "args": []}], "narration": "pop"}]}
    monkeypatch.setattr(planner.llm, "generate_json", lambda p, s=None: bad)
    with pytest.raises(planner.llm.LLMError):
        planner.make_plan("teach me something cool")
