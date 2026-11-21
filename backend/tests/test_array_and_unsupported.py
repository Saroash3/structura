import pytest

import planner
from structures import Array, OpError
from verifier import check_narration, facts, simulate, verify_plan


def test_array_insert_delete_set_get_shift_elements():
    a = Array()
    for v in [3, 5, 7]:
        a.apply("append", [v])
    s = a.apply("insert_at", [1, 9])
    assert s["items"] == [3, 9, 5, 7] and s["last"]["shifted"] == 2
    s = a.apply("delete_at", [0])
    assert s["items"] == [9, 5, 7] and s["last"]["removed"] == 3
    s = a.apply("set", [2, 8])
    assert s["items"] == [9, 5, 8] and s["last"]["old"] == 7
    assert a.apply("get", [1])["last"]["value"] == 5
    with pytest.raises(OpError):
        a.apply("get", [3])
    with pytest.raises(OpError):
        a.apply("insert_at", [5, 1])


def test_array_index_claims():
    scenes = [{"ops": [{"op": "append", "args": [3]}, {"op": "append", "args": [5]}]},
              {"ops": [{"op": "insert_at", "args": [1, 9]}]}]
    sim = simulate("array", scenes)[1]
    assert check_narration("We insert 9 at index 1. Index 2 now holds 5 and the size is 3.", facts(sim)) == []
    assert check_narration("Now 9 is at index 2.", facts(sim))  # 9 is at index 1
    assert check_narration("Index 0 holds 5.", facts(sim))  # index 0 holds 3


def test_delete_index_is_not_read_as_removed_value():
    scenes = [{"ops": [{"op": "append", "args": [4]}, {"op": "append", "args": [6]}, {"op": "append", "args": [8]}]},
              {"ops": [{"op": "delete_at", "args": [2]}]}]
    sim = simulate("array", scenes)[1]
    assert check_narration("We delete index 2, removing 8. The size is 2.", facts(sim)) == []


def test_array_template_verifies():
    scenes = [{"id": 1, "ops": [{"op": "append", "args": [4]}], "narration": "The value is 999."},
              {"id": 2, "ops": [{"op": "set", "args": [0, 6]}], "narration": "The value is 999."}]
    for s in verify_plan({"structure": "array", "scenes": scenes}):
        assert s["narration_source"] == "template"


def test_unsupported_topic_is_rejected_not_substituted(monkeypatch):
    monkeypatch.setattr(planner.llm, "generate_json",
                        lambda *a, **k: {"topic": "hash maps", "structure": "unsupported", "scenes": []})
    with pytest.raises(planner.UnsupportedTopic, match="arrays"):
        planner.make_plan("how does a hash map work")
