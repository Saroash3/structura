import pytest

from structures import OpError, Queue, Stack, make


def test_queue_fifo():
    q = Queue()
    q.apply("enqueue", [5])
    q.apply("enqueue", [8])
    s = q.apply("enqueue", [2])
    assert s["items"] == [5, 8, 2] and s["front"] == 5 and s["back"] == 2 and s["size"] == 3
    s = q.apply("dequeue")
    assert s["last"]["removed"] == 5
    assert s["items"] == [8, 2] and s["front"] == 8 and s["size"] == 2


def test_queue_peek_does_not_remove():
    q = Queue()
    q.apply("enqueue", [4])
    s = q.apply("peek")
    assert s["last"]["value"] == 4 and s["size"] == 1


def test_stack_lifo():
    st = Stack()
    st.apply("push", [1])
    s = st.apply("push", [9])
    assert s["top"] == 9 and s["items"] == [1, 9]
    s = st.apply("pop")
    assert s["last"]["removed"] == 9 and s["top"] == 1 and s["size"] == 1


@pytest.mark.parametrize("kind,op", [("queue", "dequeue"), ("stack", "pop"), ("queue", "peek")])
def test_remove_from_empty_raises(kind, op):
    with pytest.raises(OpError):
        make(kind).apply(op)


def test_disallowed_op_and_bad_args():
    with pytest.raises(OpError):
        make("queue").apply("push", [1])
    with pytest.raises(OpError):
        make("stack").apply("push", [])
    with pytest.raises(OpError):
        make("stack").apply("push", ["abc"])
    with pytest.raises(OpError):
        make("heap")
