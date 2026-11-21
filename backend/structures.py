"""Real data structure implementations.

Every operation mutates a real structure and returns the true state afterwards.
The animation and the verifier only ever use these states, never LLM output.
"""
from __future__ import annotations

import math
import re
from collections import deque
from typing import Any

ANY = -1  # op takes a variable number of args (at least 2)
ANY1 = -2  # op takes one or more args


class OpError(ValueError):
    """Raised when an operation is invalid (bad args, pop on empty, ...)."""


def _ints(args: list, n: int, op: str) -> list[int]:
    if n == ANY1:
        if len(args) < 1:
            raise OpError(f"{op} expects at least 1 argument")
    elif n == ANY:
        if len(args) < 2:
            raise OpError(f"{op} expects at least 2 arguments")
    elif len(args) != n:
        raise OpError(f"{op} expects {n} argument(s), got {len(args)}")
    try:
        return [int(a) for a in args]
    except (TypeError, ValueError):
        raise OpError(f"{op} arguments must be integers, got {args}")


VARIANT_NAMES = {"linked_list": ("singly", "doubly", "circular"), "queue": ("simple", "circular", "priority", "deque")}


class Structure:
    name = ""
    ops: dict[str, int] = {}  # op name -> number of args

    def __init__(self) -> None:
        self.last: dict[str, Any] = {}

    def apply(self, op: str, args: list | None = None) -> dict:
        args = args or []
        if op not in self.ops:
            raise OpError(f"'{op}' is not allowed for {self.name}. Allowed: {sorted(self.ops)}")
        values = self.parse_args(args, self.ops[op], op)
        self.last = {"op": op, "args": values}
        getattr(self, "op_" + op)(*values)
        return self.state()

    def parse_args(self, args: list, n: int, op: str) -> list:
        if op == "variant":  # the one op whose argument is a word: which kind of this structure to show
            names = VARIANT_NAMES.get(self.name, ())
            word = str(args[0]).strip().lower() if len(args) == 1 else ""
            if word not in names:
                raise OpError(f"variant expects one of {list(names)}, got {args}")
            return [word]
        return _ints(args, n, op)

    def op_reset(self) -> None:
        """Start again with an empty structure (a lesson that shows several kinds of one structure)."""
        last = {"op": "reset", "args": []}
        type(self).__init__(self)
        self.last = last

    def state(self) -> dict:
        raise NotImplementedError


# ---------------------------------------------------------------- queue / stack
class Queue(Structure):
    name = "queue"
    ops = {"init": ANY1, "enqueue": 1, "dequeue": 0, "peek": 0, "variant": 1, "push_front": 1, "pop_back": 0, "reset": 0}

    def __init__(self) -> None:
        super().__init__()
        self.items: deque[int] = deque()
        self.variant = "simple"

    def op_variant(self, name: str) -> None:
        """Which kind of queue: simple, circular (the back wraps round to the front of a fixed ring), priority (the smallest
        value is served first), deque (join and leave at both ends)."""
        self.variant = name
        if name == "priority":
            self.items = deque(sorted(self.items))
        self.last.update(variant=name)

    def op_push_front(self, value: int) -> None:
        if self.variant != "deque":
            raise OpError("push_front: only a deque (double-ended queue) lets items join at the front")
        self.items.appendleft(value)
        self.last.update(value=value, index=0, touched=1)

    def op_pop_back(self) -> None:
        if self.variant != "deque":
            raise OpError("pop_back: only a deque (double-ended queue) lets items leave from the back")
        if not self.items:
            raise OpError("pop_back on an empty queue")
        self.last.update(removed=self.items.pop(), index=len(self.items), touched=1)

    def op_init(self, *values: int) -> None:
        if self.items:
            raise OpError("init can only fill an empty queue")
        self.items.extend(values)
        self.last.update(values=list(values))

    def op_enqueue(self, value: int) -> None:
        if self.variant == "priority":  # served by priority: the smallest value waits at the front
            at = next((i for i, x in enumerate(self.items) if value < x), len(self.items))
            self.items.insert(at, value)
            self.last.update(value=value, index=at, touched=1)
            return
        self.items.append(value)
        self.last.update(value=value, index=len(self.items) - 1, touched=1)

    def op_dequeue(self) -> None:
        if not self.items:
            raise OpError("dequeue on an empty queue")
        self.last.update(removed=self.items.popleft(), index=0, touched=1)

    def op_peek(self) -> None:
        if not self.items:
            raise OpError("peek on an empty queue")
        self.last.update(value=self.items[0], index=0)

    def state(self) -> dict:
        items = list(self.items)
        return {"kind": "queue", "items": items, "front": items[0] if items else None,
                "back": items[-1] if items else None, "size": len(items), "variant": self.variant, "last": dict(self.last)}


class Stack(Structure):
    name = "stack"
    ops = {"init": ANY1, "push": 1, "pop": 0, "peek": 0, "reset": 0}

    def __init__(self) -> None:
        super().__init__()
        self.items: list[int] = []

    def op_init(self, *values: int) -> None:
        if self.items:
            raise OpError("init can only fill an empty stack")
        self.items.extend(values)
        self.last.update(values=list(values))

    def op_push(self, value: int) -> None:
        self.items.append(value)
        self.last.update(value=value, index=len(self.items) - 1, touched=1)

    def op_pop(self) -> None:
        if not self.items:
            raise OpError("pop on an empty stack")
        self.last.update(removed=self.items.pop(), index=len(self.items), touched=1)

    def op_peek(self) -> None:
        if not self.items:
            raise OpError("peek on an empty stack")
        self.last.update(value=self.items[-1], index=len(self.items) - 1)

    def state(self) -> dict:
        items = list(self.items)  # bottom -> top
        return {"kind": "stack", "items": items, "top": items[-1] if items else None,
                "size": len(items), "last": dict(self.last)}


# ---------------------------------------------------------------- linked list
class _Node:
    def __init__(self, value: int, nxt: "_Node | None" = None):
        self.value, self.next = value, nxt


class LinkedList(Structure):
    """Singly linked list with a real `current` cursor, so a lesson can walk it hop by hop."""
    name = "linked_list"
    ops = {"init": ANY1, "insert_head": 1, "insert_tail": 1, "insert_after": 2, "delete_value": 1, "search": 1, "walk": 1,
           "variant": 1, "reset": 0}

    def __init__(self) -> None:
        super().__init__()
        self.head: _Node | None = None
        self.cur: _Node | None = None  # node the walk is standing on
        self.variant = "singly"

    def op_variant(self, name: str) -> None:
        """Which kind of list: singly (each box points forward), doubly (forward and back), circular (the tail points
        back to the head instead of null)."""
        self.variant = name
        self.last.update(variant=name)

    def _nodes(self) -> list[_Node]:
        out, node = [], self.head
        while node:
            out.append(node)
            node = node.next
        return out

    def _values(self) -> list[int]:
        return [n.value for n in self._nodes()]

    @staticmethod
    def _val(node: "_Node | None"):
        return node.value if node else None

    def op_init(self, *values: int) -> None:
        if self.head:
            raise OpError("init can only build an empty list; use insert ops afterwards")
        for v in reversed(values):
            self.head = _Node(v, self.head)
        self.cur = None
        self.last.update(values=list(values))

    def op_insert_head(self, value: int) -> None:
        old = self.head
        self.head = _Node(value, old)
        self.last.update(value=value, index=0, next=self._val(old), touched=1)

    def op_insert_tail(self, value: int) -> None:
        new = _Node(value)
        nodes = self._nodes()
        if not nodes:
            self.head = new
        else:
            nodes[-1].next = new
        self.last.update(value=value, index=len(nodes), prev=self._val(nodes[-1]) if nodes else None, next=None)

    def op_insert_after(self, target: int, value: int) -> None:
        nodes = self._nodes()
        node = next((n for n in nodes if n.value == target), None)
        if node is None:
            raise OpError(f"insert_after: {target} is not in the list {self._values()}")
        old_next = node.next
        node.next = _Node(value, old_next)
        self.last.update(value=value, index=nodes.index(node) + 1, prev=target, next=self._val(old_next))

    def op_delete_value(self, value: int) -> None:
        prev, node, i = None, self.head, 0
        while node and node.value != value:
            prev, node, i = node, node.next, i + 1
        if not node:  # nothing to delete: the walk reached null (taught as an edge case)
            self.last.update(value=value, found=False, path=self._values())
            return
        if prev:
            prev.next = node.next
        else:
            self.head = node.next
        if self.cur is node:
            self.cur = None
        self.last.update(removed=value, index=i, prev=self._val(prev), next=self._val(node.next), found=True)

    def op_search(self, value: int) -> None:
        values = self._values()
        if value in values:
            i = values.index(value)
            self.last.update(value=value, index=i, path=values[: i + 1], found=True)
        else:
            self.last.update(value=value, path=values, found=False)

    def op_walk(self, value: int) -> None:
        """Move the cursor ONE hop: onto the head (to start a walk) or onto the node after the current one."""
        if not self.head:
            raise OpError("walk: the list is empty")
        ahead = self.cur.next if self.cur else self.head
        if ahead is not None and ahead.value == value:
            prev = self._val(self.cur)
            self.cur = ahead
        elif self.head.value == value:  # start a new walk from the head
            prev, self.cur = None, self.head
        else:
            at = f"from {self.cur.value} the next node is {self._val(self.cur.next) or 'null'}" if self.cur else f"the head is {self.head.value}"
            raise OpError(f"walk: can only move one hop at a time ({at}), not to {value}")
        index = self._nodes().index(self.cur)
        self.last.update(value=value, index=index, prev=prev, next=self._val(self.cur.next), checked=index + 1)

    def state(self) -> dict:
        nodes = self._nodes()
        items = [n.value for n in nodes]
        return {"kind": "linked_list", "items": items, "head": items[0] if items else None,
                "tail": items[-1] if items else None, "size": len(items),
                "pointers": [{"value": n.value, "next": self._val(n.next) if n.next or self.variant != "circular" else items[0],
                              **({"prev": items[i - 1] if i else None} if self.variant == "doubly" else {})}
                             for i, n in enumerate(nodes)],
                "current": self._val(self.cur), "current_index": nodes.index(self.cur) if self.cur in nodes else None,
                "variant": self.variant, "last": dict(self.last)}


# ---------------------------------------------------------------- binary search tree
class _TreeNode:
    def __init__(self, value: int):
        self.value = value
        self.left: _TreeNode | None = None
        self.right: _TreeNode | None = None


class BinaryTree(Structure):
    name = "binary_tree"
    ops = {"init": ANY1, "insert_bst": 1, "search_bst": 1, "reset": 0}

    def __init__(self) -> None:
        super().__init__()
        self.root: _TreeNode | None = None

    def op_init(self, *values: int) -> None:
        if self.root:
            raise OpError("init can only build an empty tree")
        for v in values:
            self.op_insert_bst(v)
        self.last = {"op": "init", "args": list(values), "values": list(values)}

    def op_insert_bst(self, value: int) -> None:
        path, parent, node = [], None, self.root
        while node:
            if value == node.value:
                raise OpError(f"insert_bst: {value} is already in the tree")
            path.append(node.value)
            parent, node = node, node.left if value < node.value else node.right
        new = _TreeNode(value)
        if parent is None:
            self.root = new
        elif value < parent.value:
            parent.left = new
        else:
            parent.right = new
        self.last.update(value=value, path=path + [value], parent=parent.value if parent else None)

    def op_search_bst(self, value: int) -> None:
        path, node = [], self.root
        while node:
            path.append(node.value)
            if value == node.value:
                self.last.update(value=value, path=path, found=True)
                return
            node = node.left if value < node.value else node.right
        raise OpError(f"search_bst: {value} is not in the tree")

    def state(self) -> dict:
        nodes: list[dict] = []
        order: list[int] = []

        def walk(n: _TreeNode | None, depth: int) -> int:  # returns height
            if not n:
                return 0
            hl = walk(n.left, depth + 1)
            order.append(n.value)
            nodes.append({"value": n.value, "depth": depth,
                          "left": n.left.value if n.left else None,
                          "right": n.right.value if n.right else None})
            hr = walk(n.right, depth + 1)
            return 1 + max(hl, hr)

        height = walk(self.root, 0)
        # layout: x = in-order position, y = depth (both normalised to 0..1)
        n = len(order)
        for node in nodes:
            node["x"] = (order.index(node["value"]) + 0.5) / n
            node["y"] = (node["depth"] + 0.5) / max(height, 1)
        return {"kind": "binary_tree", "items": order, "nodes": nodes,
                "root": self.root.value if self.root else None,
                "size": n, "height": height, "last": dict(self.last)}


# ---------------------------------------------------------------- graph BFS
LABEL_RE = re.compile(r"^[A-Za-z0-9]{1,12}$")


def label_key(label: str):
    """Natural order: numbers numerically (2 before 10), then text alphabetically."""
    return (0, int(label), "") if label.isdigit() else (1, 0, label)


class GraphBFS(Structure):
    """Undirected graph + breadth first search. Nodes are LABELS (the user's own "A", "B" or "1", "2")."""
    name = "graph_bfs"
    ops = {"add_edge": 2, "start_bfs": 1, "visit": 0, "reset": 0}

    def __init__(self) -> None:
        super().__init__()
        self.adj: dict[str, set[str]] = {}
        self.queue: deque[str] = deque()
        self.discovered: list[str] = []  # marked when enqueued
        self.order: list[str] = []  # processed (dequeued) order
        self.current: str | None = None
        self.start: str | None = None
        self.started = False
        self.checks = 0  # neighbour checks so far: every visit looks at each neighbour of the visited node once

    def parse_args(self, args: list, n: int, op: str) -> list:
        if len(args) != n:
            raise OpError(f"{op} expects {n} argument(s), got {len(args)}")
        labels = [str(a).strip() for a in args]
        for lab in labels:
            if not LABEL_RE.match(lab):
                raise OpError(f"{op}: node labels must be 1 to 12 letters or digits, got {lab!r}")
        return labels

    def op_reset(self) -> None:
        """Throw the graph away and start a new one (complexity lessons compare two graphs)."""
        self.__init__()
        self.last = {"op": "reset", "args": []}

    def op_add_edge(self, u: str, v: str) -> None:
        if self.started:
            raise OpError("add_edge after start_bfs is not allowed; add all edges first")
        if u == v:
            raise OpError("add_edge: self loops are not allowed")
        self.adj.setdefault(u, set()).add(v)
        self.adj.setdefault(v, set()).add(u)
        self.last.update(edge=[u, v])

    def op_start_bfs(self, start: str) -> None:
        if start not in self.adj:
            raise OpError(f"start_bfs: node {start} is not in the graph")
        if self.started:
            raise OpError("start_bfs can only be called once")
        self.started = True
        self.start = start
        self.queue.append(start)
        self.discovered.append(start)
        self.last.update(value=start, enqueued=[start])

    def op_visit(self) -> None:
        if not self.started:
            raise OpError("visit before start_bfs")
        if not self.queue:
            raise OpError("visit: the BFS queue is empty, the search is finished")
        node = self.queue.popleft()
        self.current = node
        self.order.append(node)
        new = [n for n in sorted(self.adj[node], key=label_key) if n not in self.discovered]
        self.checks += len(self.adj[node])
        for n in new:
            self.queue.append(n)
            self.discovered.append(n)
        self.last.update(removed=node, value=node, enqueued=new, neighbours=len(self.adj[node]))

    def _levels(self) -> dict[str, int]:
        """BFS distance from the start (or the first node added), used for a level-by-level layout."""
        if not self.adj:
            return {}
        root = self.start or next(iter(self.adj))
        level, frontier = {root: 0}, [root]
        while frontier:
            nxt = []
            for u in frontier:
                for v in sorted(self.adj[u], key=label_key):
                    if v not in level:
                        level[v] = level[u] + 1
                        nxt.append(v)
            frontier = nxt
        far = max(level.values(), default=0) + 1
        for n in self.adj:  # unreachable nodes go in a last column
            level.setdefault(n, far)
        return level

    def state(self) -> dict:
        nodes = sorted(self.adj, key=label_key)
        level = self._levels()
        n_levels = max(level.values(), default=0) + 1
        columns: dict[int, list[str]] = {}
        for n in nodes:
            columns.setdefault(level[n], []).append(n)
        pos = {}
        for lv, col in columns.items():
            for i, n in enumerate(col):
                pos[n] = [round((lv + 0.5) / n_levels, 4), round((i + 0.5) / len(col), 4)]
        edges = sorted({tuple(sorted((u, v), key=label_key)) for u in self.adj for v in self.adj[u]}, key=lambda e: (label_key(e[0]), label_key(e[1])))
        q = list(self.queue)
        return {"kind": "graph_bfs", "items": nodes, "nodes": [{"value": n, "x": pos[n][0], "y": pos[n][1]} for n in nodes],
                "edges": [list(e) for e in edges], "queue": q, "front": q[0] if q else None,
                "discovered": list(self.discovered), "order": list(self.order), "current": self.current,
                "start": self.start, "visits": len(self.order), "checks": self.checks,
                "edge_count": len(edges), "last": dict(self.last)}


# ---------------------------------------------------------------- bubble sort
class BubbleSort(Structure):
    name = "bubble_sort"
    ops = {"load": ANY, "compare": 1, "swap": 1, "step": 0, "reload": ANY}

    def __init__(self) -> None:
        super().__init__()
        self.items: list[int] = []
        self.passes = 0  # completed passes; the last `passes` items are in final position
        self.j = 0  # next comparison index for `step`
        self.swapped_this_pass = False
        self.done = False
        self.comparisons = 0  # every `step` compares exactly one pair
        self.swaps = 0
        self.pass_counts: list[int] = []  # comparisons made in each pass (the last one may still be running)
        self.early_exit = False  # finished because a pass made no swaps, before n - 1 passes

    def _check_index(self, i: int) -> None:
        if not 0 <= i < len(self.items) - 1:
            raise OpError(f"index {i} out of range for {len(self.items)} items")

    def op_load(self, *values: int) -> None:
        if self.items:
            raise OpError("load can only be called once")
        self.items = list(values)
        self.last.update(values=list(values))

    def op_reload(self, *values: int) -> None:
        """Start a fresh sort on new values (complexity lessons run the best and the worst case for real)."""
        self.__init__()
        self.last = {"op": "reload", "args": list(values)}
        self.op_load(*values)

    def op_compare(self, i: int) -> None:
        self._check_index(i)
        a, b = self.items[i], self.items[i + 1]
        self.last.update(compared=[i, i + 1], values=[a, b], out_of_order=a > b)

    def op_swap(self, i: int) -> None:
        self._check_index(i)
        a, b = self.items[i], self.items[i + 1]
        if a <= b:
            raise OpError(f"swap {i}: bubble sort does not swap {a} and {b}, they are already in order")
        self.items[i], self.items[i + 1] = b, a
        self.last.update(compared=[i, i + 1], values=[a, b], swapped=True)

    def op_step(self) -> None:
        """One real bubble-sort step: compare items[j] and items[j+1], swap if out of order."""
        n = len(self.items)
        if n < 2:
            raise OpError("step: load at least 2 values first")
        if self.done:  # extra steps after the sort finished change nothing
            self.last.update(finished=True)
            return
        a, b = self.items[self.j], self.items[self.j + 1]
        swapped = a > b
        if self.j == 0:
            self.pass_counts.append(0)
        self.comparisons += 1
        self.pass_counts[-1] += 1
        if swapped:
            self.items[self.j], self.items[self.j + 1] = b, a
            self.swapped_this_pass = True
            self.swaps += 1
        self.last.update(compared=[self.j, self.j + 1], values=[a, b], swapped=swapped)
        self.j += 1
        if self.j >= n - 1 - self.passes:  # end of pass: largest remaining value is in place
            self.passes += 1
            self.done = not self.swapped_this_pass or self.passes >= n - 1
            self.early_exit = not self.swapped_this_pass and self.passes < n - 1
            self.last.update(pass_done=True, pass_swapped=self.swapped_this_pass)
            self.j, self.swapped_this_pass = 0, False

    def state(self) -> dict:
        items = list(self.items)
        n = len(items)
        return {"kind": "bubble_sort", "items": items, "size": n,
                "sorted_from": 0 if self.done else n - self.passes,  # items[sorted_from:] are final
                "is_sorted": self.done, "comparisons": self.comparisons, "swaps": self.swaps,
                "pass_counts": list(self.pass_counts), "passes": self.passes, "early_exit": self.early_exit,
                "last": dict(self.last)}



class InsertionSort(Structure):
    """Insertion sort with adjacent swaps: each `step` compares the item being inserted with its left neighbour once."""
    name = "insertion_sort"
    ops = {"load": ANY, "step": 0, "reload": ANY}

    def __init__(self) -> None:
        super().__init__()
        self.items: list[int] = []
        self.i = 1  # index of the item being inserted (items[:i] are sorted among themselves)
        self.j = 1  # where that item is now
        self.done = False
        self.comparisons = 0
        self.swaps = 0
        self.pass_counts: list[int] = []  # comparisons made while inserting each item

    def op_load(self, *values: int) -> None:
        if self.items:
            raise OpError("load can only be called once")
        self.items = list(values)
        self.done = len(values) < 2
        self.last.update(values=list(values))

    def op_reload(self, *values: int) -> None:
        self.__init__()
        self.last = {"op": "reload", "args": list(values)}
        self.op_load(*values)

    def op_step(self) -> None:
        if len(self.items) < 2:
            raise OpError("step: load at least 2 values first")
        if self.done:
            self.last.update(finished=True)
            return
        j = self.j
        a, b = self.items[j - 1], self.items[j]
        if j == self.i:
            self.pass_counts.append(0)
        self.comparisons += 1
        self.pass_counts[-1] += 1
        swapped = a > b
        if swapped:
            self.items[j - 1], self.items[j] = b, a
            self.swaps += 1
            self.j -= 1
        self.last.update(compared=[j - 1, j], values=[a, b], swapped=swapped, inserting=b)
        if not swapped or self.j == 0:  # the item is in place among the sorted part
            self.i += 1
            self.j = self.i
            self.last["pass_done"] = True
            self.done = self.i >= len(self.items)

    def state(self) -> dict:
        n = len(self.items)
        return {"kind": "insertion_sort", "items": list(self.items), "size": n, "sorted_upto": n if self.done else self.i,
                "sorted_from": 0 if self.done else n, "is_sorted": self.done, "comparisons": self.comparisons, "swaps": self.swaps,
                "pass_counts": list(self.pass_counts), "passes": len(self.pass_counts) if self.done or not self.pass_counts
                else len(self.pass_counts) - (0 if self.last.get("pass_done") else 1), "early_exit": False, "last": dict(self.last)}


class GraphDFS(GraphBFS):
    """Undirected graph + depth first search with a STACK: visit pops the top node and pushes its undiscovered neighbours,
    in reverse alphabetical order so the alphabetically first neighbour is visited next."""
    name = "graph_dfs"
    ops = {"add_edge": 2, "start_dfs": 1, "visit": 0, "reset": 0}

    def op_start_dfs(self, start: str) -> None:
        self.op_start_bfs(start)

    def op_visit(self) -> None:
        if not self.started:
            raise OpError("visit before start_dfs")
        if not self.queue:
            raise OpError("visit: the DFS stack is empty, the search is finished")
        node = self.queue.pop()  # the top of the stack
        self.current = node
        self.order.append(node)
        new = [n for n in sorted(self.adj[node], key=label_key) if n not in self.discovered]
        self.checks += len(self.adj[node])
        for n in reversed(new):
            self.queue.append(n)
            self.discovered.append(n)
        self.last.update(removed=node, value=node, pushed=new, neighbours=len(self.adj[node]))

    def state(self) -> dict:
        st = super().state()
        stack = st.pop("queue")
        st.pop("front", None)
        return {**st, "kind": "graph_dfs", "stack": stack, "top": stack[-1] if stack else None}


class Array(Structure):
    """A dynamic array (like a Python list): index-based access, inserts and deletes shift elements."""
    name = "array"
    ops = {"init": ANY1, "append": 1, "insert_at": 2, "delete_at": 1, "set": 2, "get": 1, "scan": 1, "reset": 0}

    def __init__(self) -> None:
        super().__init__()
        self.items: list[int] = []
        self.scan_at: int | None = None  # linear search cursor: the index checked last
        self.scan_target: int | None = None
        self.scan_done = True

    def _check(self, i: int, allow_end: bool = False) -> None:
        hi = len(self.items) if allow_end else len(self.items) - 1
        if not 0 <= i <= hi:
            raise OpError(f"index {i} is out of range for an array of size {len(self.items)}")

    def op_init(self, *values: int) -> None:
        if self.items:
            raise OpError("init can only fill an empty array")
        self.items.extend(values)
        self.last.update(values=list(values))

    def op_append(self, value: int) -> None:
        self.items.append(value)
        self.last.update(value=value, index=len(self.items) - 1)

    def op_insert_at(self, index: int, value: int) -> None:
        self._check(index, allow_end=True)
        self.items.insert(index, value)
        self.last.update(value=value, index=index, shifted=len(self.items) - 1 - index)

    def op_delete_at(self, index: int) -> None:
        self._check(index)
        removed = self.items.pop(index)
        self.last.update(removed=removed, index=index, shifted=len(self.items) - index)

    def op_set(self, index: int, value: int) -> None:
        self._check(index)
        self.last.update(old=self.items[index], value=value, index=index)
        self.items[index] = value

    def op_get(self, index: int) -> None:
        self._check(index)
        self.last.update(value=self.items[index], index=index, touched=1)

    def op_scan(self, target: int) -> None:
        """Linear search, ONE comparison per op: check the next index against the target (a new target starts at index 0)."""
        if not self.items:
            raise OpError("scan: the array is empty")
        if self.scan_done or target != self.scan_target:
            self.scan_at, self.scan_target = -1, target
        self.scan_at += 1
        i = self.scan_at
        found = self.items[i] == target
        self.scan_done = found or i == len(self.items) - 1
        self.last.update(index=i, value=self.items[i], target=target, found=found, checked=i + 1,
                         finished=self.scan_done)

    def state(self) -> dict:
        items = list(self.items)
        st = {"kind": "array", "items": items, "size": len(items), "last": dict(self.last)}
        if self.scan_at is not None:
            st["scan"] = {"target": self.scan_target, "checked": list(range(self.scan_at + 1)), "done": self.scan_done}
        return st


# ---------------------------------------------------------------- kinds of array (2D grid, static vs dynamic, jagged)
class ArrayGrid(Structure):
    """A two-dimensional array: rows and columns, read by (row, column), both counted from 0."""
    name = "array_2d"
    ops = {"grid": ANY, "get2": 2, "set2": 3, "reset": 0}

    def __init__(self) -> None:
        super().__init__()
        self.cells: list[list[int]] = []

    def op_grid(self, rows: int, cols: int, *values: int) -> None:
        if self.cells:
            raise OpError("grid can only fill an empty 2D array")
        if not (1 <= rows <= 6 and 1 <= cols <= 8):
            raise OpError("grid: rows 1..6 and columns 1..8")
        vals = list(values) or [10 * (i + 1) for i in range(rows * cols)]
        if len(vals) != rows * cols:
            raise OpError(f"grid {rows} x {cols} needs {rows * cols} values, got {len(vals)}")
        self.cells = [vals[r * cols:(r + 1) * cols] for r in range(rows)]
        self.last.update(rows=rows, cols=cols, values=vals)

    def _check(self, r: int, c: int) -> None:
        if not (self.cells and 0 <= r < len(self.cells) and 0 <= c < len(self.cells[0])):
            raise OpError(f"cell ({r}, {c}) is outside the grid")

    def op_get2(self, r: int, c: int) -> None:
        self._check(r, c)
        self.last.update(row=r, col=c, value=self.cells[r][c], touched=1)

    def op_set2(self, r: int, c: int, value: int) -> None:
        self._check(r, c)
        self.last.update(row=r, col=c, old=self.cells[r][c], value=value)
        self.cells[r][c] = value

    def state(self) -> dict:
        rows = [list(r) for r in self.cells]
        return {"kind": "array_2d", "cells": rows, "rows": len(rows), "cols": len(rows[0]) if rows else 0,
                "items": [x for r in rows for x in r], "last": dict(self.last)}


class DynArray(Structure):
    """Static versus dynamic arrays. A static array has a fixed number of slots: adding to a full one is refused. A dynamic
    array that is full moves to a new block twice as big, copying every value (the counts are recorded)."""
    name = "dyn_array"
    ops = {"init_static": ANY1, "init_dynamic": ANY1, "append": 1, "get": 1, "reset": 0}

    def __init__(self) -> None:
        super().__init__()
        self.items: list[int] = []
        self.capacity = 0
        self.mode = ""
        self.copies = 0
        self.resizes = 0

    def _init(self, mode: str, capacity: int, values: tuple) -> None:
        if self.mode:
            raise OpError("init can only fill an empty array")
        if not 1 <= capacity <= 16 or len(values) > capacity:
            raise OpError(f"init: capacity {capacity} must be 1..16 and hold the {len(values)} values")
        self.mode, self.capacity, self.items = mode, capacity, list(values)
        self.last.update(capacity=capacity, values=list(values), mode=mode)

    def op_init_static(self, capacity: int, *values: int) -> None:
        self._init("static", capacity, values)

    def op_init_dynamic(self, capacity: int, *values: int) -> None:
        self._init("dynamic", capacity, values)

    def op_append(self, value: int) -> None:
        if not self.mode:
            raise OpError("append: create the array first (init_static or init_dynamic)")
        if len(self.items) < self.capacity:
            self.items.append(value)
            self.last.update(value=value, index=len(self.items) - 1, resized=False)
        elif self.mode == "static":  # a full static array has no room: nothing changes
            self.last.update(value=value, refused=True, resized=False)
        else:
            old = self.capacity
            copied = len(self.items)
            self.capacity, self.copies, self.resizes = old * 2, self.copies + copied, self.resizes + 1
            self.items.append(value)
            self.last.update(value=value, index=len(self.items) - 1, resized=True, old_capacity=old,
                             new_capacity=self.capacity, copied=copied)

    def op_get(self, index: int) -> None:
        if not 0 <= index < len(self.items):
            raise OpError(f"index {index} is out of range for {len(self.items)} values")
        self.last.update(value=self.items[index], index=index, touched=1)

    def state(self) -> dict:
        return {"kind": "dyn_array", "items": list(self.items), "size": len(self.items), "capacity": self.capacity,
                "mode": self.mode, "copies": self.copies, "resizes": self.resizes, "full": len(self.items) >= self.capacity > 0,
                "last": dict(self.last)}


class JaggedArray(Structure):
    """A jagged array: an array of rows, where each row can have a different length."""
    name = "jagged_array"
    ops = {"row": ANY1, "get2": 2, "reset": 0}

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[int]] = []

    def op_row(self, *values: int) -> None:
        if len(self.rows) >= 6:
            raise OpError("row: at most 6 rows")
        self.rows.append(list(values))
        self.last.update(row=len(self.rows) - 1, values=list(values), length=len(values))

    def op_get2(self, r: int, c: int) -> None:
        if not (0 <= r < len(self.rows) and 0 <= c < len(self.rows[r])):
            raise OpError(f"cell ({r}, {c}) does not exist in this jagged array")
        self.last.update(row=r, col=c, value=self.rows[r][c], touched=1)

    def state(self) -> dict:
        rows = [list(r) for r in self.rows]
        return {"kind": "jagged_array", "cells": rows, "rows": len(rows), "lengths": [len(r) for r in rows],
                "items": [x for r in rows for x in r], "last": dict(self.last)}


# ---------------------------------------------------------------- counting: the real work each algorithm does
# Every count below comes from RUNNING the real implementation above, never from a formula, so a complexity lesson's
# numbers (comparisons per pass, totals, growth-table rows, best and worst case) can be checked against them.
def run_bubble(values) -> dict:
    """Bubble sort to completion: comparisons, swaps, comparisons per pass, and whether it stopped early."""
    b = BubbleSort()
    b.apply("load", list(values))
    while not b.done:
        b.apply("step")
    return {"comparisons": b.comparisons, "swaps": b.swaps, "pass_counts": list(b.pass_counts), "early_exit": b.early_exit}


def run_insertion(values) -> dict:
    """Insertion sort to completion: comparisons, swaps, comparisons per inserted item."""
    s = InsertionSort()
    s.apply("load", list(values))
    while not s.done:
        s.apply("step")
    return {"comparisons": s.comparisons, "swaps": s.swaps, "pass_counts": list(s.pass_counts)}


def run_scan(values, target: int) -> int:
    """Linear search on an array: how many items were compared with the target."""
    a = Array()
    a.apply("init", list(values))
    while True:
        a.apply("scan", [target])
        if a.last["finished"]:
            return a.last["checked"]


def run_list_search(values, target: int) -> int:
    """Linked list search, hop by hop from the head: how many nodes were checked."""
    ll = LinkedList()
    ll.apply("init", list(values))
    for v in values:
        ll.apply("walk", [v])
        if v == target:
            break
    return ll.last["checked"]


def run_bfs(edges, start: str, dfs: bool = False) -> dict:
    """Breadth (or depth) first search to completion: node visits and neighbour checks."""
    g = GraphDFS() if dfs else GraphBFS()
    for u, v in edges:
        g.apply("add_edge", [u, v])
    g.apply("start_dfs" if dfs else "start_bfs", [start])
    while g.queue:
        g.apply("visit")
    return {"visits": len(g.order), "checks": g.checks, "edges": len(edges)}


ONE_OP = {  # algorithm -> (structure, op, args): an op that touches a fixed number of items
    "stack_push": ("stack", "push", [99]), "stack_pop": ("stack", "pop", []),
    "queue_enqueue": ("queue", "enqueue", [99]), "queue_dequeue": ("queue", "dequeue", []),
    "array_access": ("array", "get", None), "linked_list_insert_head": ("linked_list", "insert_head", [99]),
}


def run_one_op(algo: str, n: int, case: str = "worst") -> int:
    structure, op, args = ONE_OP[algo]
    ds = make(structure)
    ds.apply("init", list(range(1, n + 1)))
    ds.apply(op, args if args is not None else [n - 1 if case == "worst" else 0])
    return ds.last["touched"]


def chain_edges(n: int) -> list[tuple[str, str]]:
    return [(str(i), str(i + 1)) for i in range(1, n)]


def count_work(algo: str, n: int, case: str = "worst") -> int:
    """The work `algo` really does on n items, for its worst (or best) input."""
    worst = case == "worst"
    if algo == "bubble_sort":
        return run_bubble(range(n, 0, -1) if worst else range(1, n + 1))["comparisons"]
    if algo == "insertion_sort":
        return run_insertion(range(n, 0, -1) if worst else range(1, n + 1))["comparisons"]
    if algo == "linear_search":
        return run_scan(range(1, n + 1), 0 if worst else 1)
    if algo == "linked_list_search":
        return run_list_search(list(range(1, n + 1)), n if worst else 1)
    if algo in ("bfs", "dfs"):  # every reachable node is visited once; a chain of n nodes has n - 1 edges
        w = run_bfs(chain_edges(n), "1", dfs=algo == "dfs")
        return w["visits"] + w["checks"]
    if algo in ONE_OP:
        return run_one_op(algo, n, case)
    raise OpError(f"no counting function for {algo}")


COUNTED = ("bubble_sort", "insertion_sort", "dfs", "linear_search", "linked_list_search", "bfs", *ONE_OP)


class Growth(Structure):
    """A growth table: the real work of one algorithm for several input sizes n (rows from count_work)."""
    name = "growth"
    ops = {algo: ANY1 for algo in COUNTED}

    def __init__(self) -> None:
        super().__init__()
        self.algo: str | None = None
        self.rows: list[dict] = []

    def apply(self, op: str, args: list | None = None) -> dict:
        if op not in self.ops:
            raise OpError(f"'{op}' is not allowed for growth. Allowed: {sorted(self.ops)}")
        sizes = _ints(args or [], ANY1, op)
        if any(not 2 <= n <= 200 for n in sizes):
            raise OpError(f"{op}: table sizes must be between 2 and 200, got {sizes}")
        self.algo = op
        self.rows = [{"n": n, "count": count_work(op, n)} for n in sizes]
        self.last = {"op": op, "args": sizes}
        return self.state()

    def state(self) -> dict:
        return {"kind": "growth", "algo": self.algo, "items": [r["n"] for r in self.rows], "rows": [dict(r) for r in self.rows],
                "last": dict(self.last)}


STRUCTURES: dict[str, type[Structure]] = {
    "array": Array,
    "queue": Queue,
    "stack": Stack,
    "linked_list": LinkedList,
    "binary_tree": BinaryTree,
    "graph_bfs": GraphBFS,
    "bubble_sort": BubbleSort,
    "insertion_sort": InsertionSort,
    "graph_dfs": GraphDFS,
    "growth": Growth,
    "array_2d": ArrayGrid,
    "dyn_array": DynArray,
    "jagged_array": JaggedArray,
}

ALLOWED_OPS: dict[str, list[str]] = {k: sorted(v.ops) for k, v in STRUCTURES.items()}


def make(structure: str) -> Structure:
    if structure not in STRUCTURES:
        raise OpError(f"Unknown structure '{structure}'. Allowed: {sorted(STRUCTURES)}")
    return STRUCTURES[structure]()
