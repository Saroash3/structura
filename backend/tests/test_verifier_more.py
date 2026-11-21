from verifier import check_narration, facts, simulate, verify_plan


def test_bfs_narration_checks_current_and_front():
    scenes = [{"ops": [{"op": "add_edge", "args": [1, 2]}, {"op": "add_edge", "args": [1, 3]}]},
              {"ops": [{"op": "start_bfs", "args": [1]}]},
              {"ops": [{"op": "visit", "args": []}]}]
    sim = simulate("graph_bfs", scenes)[2]
    assert check_narration("We dequeue 1 and enqueue 2 and 3. The front is 2.", facts(sim)) == []
    assert check_narration("We dequeue 2. The front is 3.", facts(sim))


def test_tree_root_and_height_claims():
    scenes = [{"ops": [{"op": "insert_bst", "args": [8]}]}, {"ops": [{"op": "insert_bst", "args": [3]}]}]
    sim = simulate("binary_tree", scenes)[1]
    assert check_narration("We insert 3 to the left. The root is 8 and the height is 2.", facts(sim)) == []
    assert check_narration("The root is 3.", facts(sim))


def test_bubble_sort_compare_and_swap_claims():
    scenes = [{"ops": [{"op": "load", "args": [4, 2, 7]}]}, {"ops": [{"op": "step", "args": []}]},
              {"ops": [{"op": "step", "args": []}]}]
    first, second = simulate("bubble_sort", scenes)[1:]
    assert check_narration("We compare 4 and 2. 4 is bigger, so we swap them.", facts(first)) == []
    assert check_narration("We compare 4 and 7. They are in order, so no swap is needed.", facts(second)) == []
    assert check_narration("We compare 2 and 7 and swap them.", facts(second))  # wrong pair, wrong swap
    assert check_narration("We compare 4 and 7 and swap them.", facts(second))  # right pair, wrong swap


def test_number_words_cannot_dodge_the_check():
    scenes = [{"ops": [{"op": "enqueue", "args": [5]}]}, {"ops": [{"op": "enqueue", "args": [21]}]}]
    sim = simulate("queue", scenes)[1]
    assert check_narration("We add twenty one. The front is five.", facts(sim)) == []
    assert check_narration("The front is twenty one.", facts(sim))  # front is 5
    assert check_narration("Now forty two joins.", facts(sim))  # 42 is invented
    assert check_narration("The one at the back just arrived.", facts(sim)) == []  # pronoun, not a number


def test_false_sorted_claim_is_caught():
    scenes = [{"ops": [{"op": "load", "args": [2, 1, 4]}]}]
    sim = simulate("bubble_sort", scenes)[0]
    assert check_narration("The list is now fully sorted as one, two, four.", facts(sim))


def test_plan_rejects_compare_swap_for_bubble_sort():
    import pytest
    from planner import Plan
    with pytest.raises(ValueError):
        Plan.model_validate({"topic": "b", "structure": "bubble_sort", "scenes": [
            {"ops": [{"op": "load", "args": [2, 1]}], "narration": "x"},
            {"ops": [{"op": "swap", "args": [0]}], "narration": "y"}]})


def test_templates_verify_for_every_structure():
    plans = {
        "linked_list": [{"op": "insert_head", "args": [4]}, {"op": "insert_tail", "args": [9]}, {"op": "delete_value", "args": [4]}],
        "binary_tree": [{"op": "insert_bst", "args": [8]}, {"op": "insert_bst", "args": [3]}, {"op": "search_bst", "args": [3]}],
        "graph_bfs": [{"op": "add_edge", "args": [1, 2]}, {"op": "start_bfs", "args": [1]}, {"op": "visit", "args": []}, {"op": "visit", "args": []}],
        "bubble_sort": [{"op": "load", "args": [3, 1, 2]}, {"op": "step", "args": []}, {"op": "step", "args": []}],
    }
    for structure, ops in plans.items():
        scenes = [{"id": i, "ops": [op], "narration": "The value is 999."} for i, op in enumerate(ops, 1)]
        for s in verify_plan({"structure": structure, "scenes": scenes}):
            assert s["narration_source"] == "template", (structure, s["narration"])
