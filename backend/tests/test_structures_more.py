import pytest

from structures import BinaryTree, BubbleSort, GraphBFS, LinkedList, OpError


def test_linked_list_insert_delete_search():
    ll = LinkedList()
    ll.apply("insert_tail", [3])
    ll.apply("insert_tail", [7])
    s = ll.apply("insert_head", [1])
    assert s["items"] == [1, 3, 7] and s["head"] == 1 and s["tail"] == 7
    s = ll.apply("delete_value", [3])
    assert s["items"] == [1, 7] and s["last"]["removed"] == 3 and s["last"]["index"] == 1
    s = ll.apply("search", [7])
    assert s["last"]["path"] == [1, 7]
    # deleting a missing value is a real edge case: the walk reaches null and nothing changes
    s = ll.apply("delete_value", [99])
    assert s["items"] == [1, 7] and s["last"]["found"] is False and "removed" not in s["last"]
    assert ll.apply("search", [99])["last"]["found"] is False


def test_linked_list_init_walk_and_pointer_details():
    ll = LinkedList()
    s = ll.apply("init", [10, 20, 30, 40])
    assert s["pointers"][1] == {"value": 20, "next": 30} and s["current"] is None
    ll.apply("walk", [10])
    s = ll.apply("walk", [20])
    assert s["current"] == 20 and s["last"]["prev"] == 10 and s["last"]["next"] == 30
    with pytest.raises(OpError):  # one hop at a time: 20 -> 40 skips 30
        ll.apply("walk", [40])
    s = ll.apply("delete_value", [30])
    assert s["items"] == [10, 20, 40] and s["last"]["prev"] == 20 and s["last"]["next"] == 40
    assert {"value": 20, "next": 40} in s["pointers"] and s["current"] == 20
    s = ll.apply("insert_after", [20, 25])
    assert s["items"] == [10, 20, 25, 40] and s["last"]["prev"] == 20 and s["last"]["next"] == 40
    with pytest.raises(OpError):
        ll.apply("init", [1, 2])  # init only builds an empty list


def test_bst_insert_layout_and_search():
    t = BinaryTree()
    for v in [50, 30, 70, 20, 40]:
        s = t.apply("insert_bst", [v])
    assert s["items"] == [20, 30, 40, 50, 70]  # in-order is sorted
    assert s["root"] == 50 and s["height"] == 3 and s["size"] == 5
    node30 = next(n for n in s["nodes"] if n["value"] == 30)
    assert node30["left"] == 20 and node30["right"] == 40
    assert s["last"]["path"] == [50, 30, 40] and s["last"]["parent"] == 30
    s = t.apply("search_bst", [40])
    assert s["last"]["path"] == [50, 30, 40]
    with pytest.raises(OpError):
        t.apply("insert_bst", [30])
    with pytest.raises(OpError):
        t.apply("search_bst", [99])


def test_bfs_uses_a_real_queue():
    g = GraphBFS()
    for u, v in [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D"), ("D", "E")]:
        g.apply("add_edge", [u, v])
    s = g.apply("start_bfs", ["A"])
    assert s["queue"] == ["A"]
    s = g.apply("visit")
    assert s["current"] == "A" and s["queue"] == ["B", "C"] and s["last"]["enqueued"] == ["B", "C"]
    s = g.apply("visit")
    assert s["current"] == "B" and s["queue"] == ["C", "D"]
    s = g.apply("visit")
    assert s["queue"] == ["D"]  # D already discovered, not enqueued twice
    g.apply("visit")
    s = g.apply("visit")
    assert s["order"] == ["A", "B", "C", "D", "E"] and s["queue"] == []
    # numeric labels keep natural order (2 before 10)
    h = GraphBFS()
    h.apply("add_edge", [1, 10]); h.apply("add_edge", [1, 2]); h.apply("start_bfs", [1])
    assert h.apply("visit")["queue"] == ["2", "10"]
    with pytest.raises(OpError):
        g.apply("visit")


def test_bubble_sort_steps_match_real_algorithm():
    b = BubbleSort()
    b.apply("load", [5, 1, 4, 2])
    s = b.apply("step")
    assert s["items"] == [1, 5, 4, 2] and s["last"]["swapped"] is True
    for _ in range(20):
        if b.state()["sorted_from"] == 0:
            break
        s = b.apply("step")
    assert s["items"] == [1, 2, 4, 5] and s["is_sorted"]
    s = b.apply("step")  # extra steps after the sort finished are harmless no-ops
    assert s["items"] == [1, 2, 4, 5] and s["last"]["finished"]


def test_bubble_sort_refuses_wrong_swap():
    b = BubbleSort()
    b.apply("load", [1, 5, 3])
    with pytest.raises(OpError):
        b.apply("swap", [0])  # 1 and 5 are already in order
    assert b.apply("swap", [1])["items"] == [1, 3, 5]
