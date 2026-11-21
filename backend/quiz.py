"""Quiz built from THE LESSON: the same graph, labels, values and operations, run on the real structure.

When the lesson came from a question analysis, at least 2 of the 3 questions test the FOCUS of the user's question
(a delete lesson asks what the previous node points to after the delete, which pointer changes, and what happens
for the head), with distractors computed from the lesson's data (the deleted node, the node before it). Edge-case
questions are only asked when the lesson's narration taught that edge case.

Answers always come from code. The LLM may only reword question text, and a rewording is rejected if any
number or node label changes. Random example data is used only if a lesson has no usable operations.
"""
from __future__ import annotations

import hashlib
import random
import re

import llm
import concepts
from structures import label_key, make
from verifier import simulate

LABELS = ["A", "B", "C", "D", "E", "F"]


def _run(structure: str, ops: list[tuple[str, list]]) -> list[dict]:
    ds = make(structure)
    return [ds.apply(op, args) for op, args in ops]


def _fmt_ops(ops) -> str:
    return ", ".join(f"{op} {' '.join(map(str, a))}".strip() for op, a in ops)


def _list(xs) -> str:
    return ", ".join(map(str, xs))


def _options(rng, answer, pool) -> list[str]:
    """The correct answer first, then up to 3 distinct distractors drawn from the lesson's own data."""
    ans = str(answer)
    cands = [str(v) for v in dict.fromkeys(pool) if str(v) != ans]
    rng.shuffle(cands)
    return [ans] + cands[:3]


def _numeric_options(rng, answer: int, pool) -> list[str]:
    extra = [answer + 1, answer - 1, answer + 2]
    return _options(rng, answer, [v for v in list(pool) + extra if isinstance(v, int) and v >= 0])


def _list_options(rng, answer: list) -> list[str]:
    opts = {_list(answer)}
    for _ in range(60):
        if len(opts) == 4:
            break
        p = answer[:]
        rng.shuffle(p)
        opts.add(_list(p))
    opts.discard(_list(answer))
    return [_list(answer)] + sorted(opts)[:3]


def _queue_options(rng, answer: list[str], labels: list[str]) -> list[str]:
    """Distractors for 'which nodes are in the queue': plausible but wrong lists using the lesson's labels."""
    fmt = lambda xs: "[" + ", ".join(xs) + "]" if xs else "empty"
    cands = [list(reversed(answer)), answer[:-1], answer[1:], [l for l in labels if l not in answer][:2], answer + [l for l in labels if l not in answer][:1]]
    out = [fmt(answer)]
    for c in cands:
        if fmt(c) not in out:
            out.append(fmt(c))
    rng.shuffle(out[1:])
    return out[:4]


def _finish(rng, q: str, opts: list[str], expl: str, kind: str = "trace") -> dict:
    """kind: "principle" (the core rule in plain words), "real_world", "vocab" or "trace" (a short computed run)."""
    correct = opts[0]
    rng.shuffle(opts)
    return {"question": q, "options": opts, "answer_index": opts.index(correct), "explanation": expl, "kind": kind}


# ---------------------------------------------------------------- questions from the lesson's own data
def _lesson_ops(plan: dict) -> list[tuple[str, list]]:
    """The ops run on the lesson's main structure (scenes about a second structure, e.g. in a comparison, are left out;
    a reload / reset starts a fresh run, so only the last run counts)."""
    ops = [(o["op"], list(o.get("args", []))) for s in plan["scenes"] if s.get("structure") in (None, plan["structure"])
           for o in s.get("ops", [])]
    starts = [i for i, (op, _a) in enumerate(ops) if op in ("reload", "reset")]
    if starts:
        ops = ops[starts[-1]:]
        ops = [("load", a) if op == "reload" else (op, a) for op, a in ops if op != "reset"]
    return ops


def _bfs_from_lesson(rng, ops) -> list[dict] | None:
    edges = list(dict.fromkeys(tuple(map(str, a)) for op, a in ops if op == "add_edge"))  # same edges on two graphs: once
    starts = [str(a[0]) for op, a in ops if op == "start_bfs"]
    if not edges or not starts:
        return None
    start = starts[0]
    run = [("add_edge", list(e)) for e in edges] + [("start_bfs", [start])]
    states = _run("graph_bfs", run)
    ds = make("graph_bfs")
    for op, a in run:
        ds.apply(op, a)
    trace = []  # (visited node, queue after)
    while ds.queue:
        st = ds.apply("visit")
        trace.append((st["last"]["removed"], list(st["queue"])))
    order = [v for v, _ in trace]
    labels = sorted(states[-1]["items"], key=label_key)
    graph = f"the lesson's graph (edges {_list(f'{u}-{v}' for u, v in edges)})"
    rule = f"a breadth first search starts at {start} and takes neighbours in alphabetical order"
    qs = []
    if len(order) >= 2:
        qs.append(_finish(rng, f"In {graph}, {rule}. Which node is visited second?", _options(rng, order[1], labels),
                          f"The real BFS visit order is {_list(order)}, so the second node visited is {order[1]}."))
    if len(trace) >= 2:
        node, queue = trace[1]
        qs.append(_finish(rng, f"In {graph}, {rule}. Right after visiting {node}, which nodes are waiting in the queue?",
                          _queue_options(rng, queue, labels),
                          f"After visiting {node}, the real queue holds {('[' + ', '.join(queue) + ']') if queue else 'nothing'}.", "principle"))
    qs.append(_finish(rng, f"In {graph}, {rule}. Which node is visited last?", _options(rng, order[-1], labels),
                      f"The real BFS visit order is {_list(order)}, so the last node visited is {order[-1]}."))
    return qs


def _array_from_lesson(rng, ops) -> list[dict] | None:
    ops = [(op, a) for op, a in ops if op in ("init", "append", "insert_at", "delete_at", "set", "get")]
    if not ops:
        return None
    final = _run("array", ops)[-1]
    items = final["items"]
    if len(items) < 2:
        return None
    values = [v for v in dict.fromkeys(int(x) for op, a in ops for x in (a if op == "init" else a[-1:]) if op in ("init", "append", "insert_at", "set"))]
    desc = f"After the lesson's operations ({_fmt_ops(ops)})"
    k = rng.randrange(len(items))
    i = rng.randrange(len(items))
    v = rng.choice(values or items)
    after = _run("array", ops + [("insert_at", [i, v])])[-1]["items"]
    return [
        _finish(rng, f"{desc}, which value is at index {k}?", _options(rng, items[k], values + items),
                f"Running those operations on a real array gives [{_list(items)}], and index {k} holds {items[k]}."),
        _finish(rng, f"{desc}, how many items does the array hold?", _numeric_options(rng, len(items), []),
                f"The real array is [{_list(items)}], which holds {len(items)} items."),
        _finish(rng, f"{desc}, we insert {v} at index {i}. Which value is now at index {i + 1}?", _options(rng, after[i + 1], values + items),
                f"Inserting shifts later items right: the array becomes [{_list(after)}], so index {i + 1} holds {after[i + 1]}."),
    ]


LINEAR = {  # structure: (insert op, remove op, field to ask about, its name)
    "queue": ("enqueue", "dequeue", "front", "front"),
    "stack": ("push", "pop", "top", "top"),
    "linked_list": ("insert_tail", "delete_value", "head", "head"),
}


def _linear_from_lesson(rng, structure, ops) -> list[dict] | None:
    ins, rem, field, name = LINEAR[structure]
    ops = [(op, a) for op, a in ops if op in make(structure).ops and op not in ("peek", "search", "walk")]
    if len(ops) < 2:
        return None
    states = _run(structure, ops)
    values = [v for v in dict.fromkeys(int(x) for op, a in ops for x in a)]
    noun = structure.replace("_", " ")
    final = states[-1]
    qs = []
    if final[field] is not None:
        qs.append(_finish(rng, f"After all the lesson's operations ({_fmt_ops(ops)}), what is the {name}?",
                          _options(rng, final[field], values), f"Running them on a real {noun} gives [{_list(final['items'])}], so the {name} is {final[field]}."))
    qs.append(_finish(rng, f"After all the lesson's operations ({_fmt_ops(ops)}), how many items does the {noun} hold?",
                      _numeric_options(rng, final["size"], []),
                      f"The real {noun} ends as [{_list(final['items'])}], which holds {final['size']} items."))
    # one more step using a value from the lesson
    extra_v = rng.choice(values)
    extra = [(ins, [extra_v])]
    if structure != "linked_list" and final["size"] >= 1:
        extra.append((rem, []))
    after = _run(structure, ops + extra)[-1]
    if after[field] is not None:
        qs.append(_finish(rng, f"Continuing the lesson's {noun}, we then run: {_fmt_ops(extra)}. What is the {name} now?",
                          _options(rng, after[field], values), f"The real {noun} becomes [{_list(after['items'])}], so the {name} is {after[field]}."))
    return qs


def _tree_from_lesson(rng, ops) -> list[dict] | None:
    vals = [int(x) for op, a in ops if op in ("init", "insert_bst") for x in a]
    if len(vals) < 3:
        return None
    final = _run("binary_tree", [("insert_bst", [v]) for v in vals])[-1]
    target = rng.choice(vals[1:])
    path = _run("binary_tree", [("insert_bst", [v]) for v in vals] + [("search_bst", [target])])[-1]["last"]["path"]
    seq = _list(vals)
    return [
        _finish(rng, f"The lesson inserts {seq} into an empty binary search tree. What is the in-order traversal?", _list_options(rng, final["items"]),
                f"An in-order traversal of a binary search tree gives the values in sorted order: {_list(final['items'])}."),
        _finish(rng, f"In the lesson's tree (inserted {seq}), how many nodes does a search for {target} visit?",
                _numeric_options(rng, len(path), [len(path) + 2, 1, len(vals)]), f"The search path is {_list(path)}, which visits {len(path)} nodes."),
        _finish(rng, f"In the lesson's tree (inserted {seq}), what is the height, counting nodes on the longest path?",
                _numeric_options(rng, final["height"], [final["height"] + 2, 1, len(vals)]), f"The longest root to leaf path has {final['height']} nodes."),
    ]


def _sort_from_lesson(rng, ops) -> list[dict] | None:
    loads = [a for op, a in ops if op == "load"]
    if not loads:
        return None
    return [_finish(rng, *_sort_question(rng, [int(x) for x in loads[0]], ask)) for ask in ("after", "swaps", "last")]


def _sort_question(rng, vals: list[int], ask: str):
    ds = make("bubble_sort")
    ds.apply("load", vals)
    swaps = 0
    while True:
        st = ds.apply("step")
        swaps += bool(st["last"].get("swapped"))
        if st["last"].get("pass_done") or st["last"].get("finished"):
            break
    after = st["items"]
    if ask == "swaps":
        return (f"In the lesson, bubble sort runs on [{_list(vals)}]. How many swaps happen during the first pass?",
                _numeric_options(rng, swaps, [swaps + 2, 0, len(vals)]), f"Running one real pass gives [{_list(after)}] after {swaps} swaps.")
    if ask == "last":
        return (f"In the lesson, bubble sort runs on [{_list(vals)}]. Which value sits at the end after the first pass?",
                _options(rng, after[-1], vals), f"One pass bubbles the largest value to the end: [{_list(after)}].")
    return (f"In the lesson, bubble sort runs on [{_list(vals)}]. What does the array look like after the first full pass?",
            _list_options(rng, after), f"One pass bubbles the largest value to the end: [{_list(after)}].")


def lesson_questions(plan: dict, seed: str) -> list[dict] | None:
    rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16))
    ops, s = _lesson_ops(plan), plan["structure"]
    qs = (_bfs_from_lesson(rng, ops) if s == "graph_bfs" else _array_from_lesson(rng, ops) if s == "array"
          else _linear_from_lesson(rng, s, ops) if s in LINEAR else _tree_from_lesson(rng, ops) if s == "binary_tree"
          else _sort_from_lesson(rng, ops) if s == "bubble_sort" else None)
    return qs[:3] if qs else None


# ---------------------------------------------------------------- fallback: random example data
def _q_random(structure: str, rng) -> list[dict]:
    vals = rng.sample(range(1, 40), 5)
    if structure == "graph_bfs":
        edges = [("A", "B"), ("A", "C"), ("B", "D"), ("C", "E"), ("D", "F")]
        ops = [("add_edge", list(e)) for e in edges] + [("start_bfs", ["A"])]
    elif structure == "array":
        ops = [("append", [v]) for v in vals[:4]]
    elif structure == "binary_tree":
        ops = [("insert_bst", [v]) for v in vals]
    elif structure == "bubble_sort":
        ops = [("load", vals)]
    else:
        ins = LINEAR[structure][0]
        ops = [(ins, [v]) for v in vals[:4]]
    plan = {"structure": structure, "scenes": [{"ops": [{"op": o, "args": a} for o, a in ops]}]}
    return lesson_questions(plan, str(vals)) or []


ASKS = {s: [] for s in ("array", "queue", "stack", "linked_list", "binary_tree", "graph_bfs", "bubble_sort")}


def template_questions(structure: str, seed: str) -> list[dict]:
    """Random-data questions (only used when a lesson has no usable operations)."""
    rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16))
    return _q_random(structure, rng)


# ---------------------------------------------------------------- questions about THE QUESTION the lesson answered
def _chain(items) -> str:
    return " -> ".join(["head", *map(str, items), "null"])


def _pick(rng, answer, preferred: list, pool: list) -> list[str]:
    """Correct answer first, then plausible distractors: `preferred` ones first (e.g. the deleted node), then the pool."""
    ans = str(answer)
    out = [ans]
    for c in [*preferred, *rng.sample(list(pool), len(pool))]:
        if str(c) not in out:
            out.append(str(c))
        if len(out) == 4:
            break
    return out


def _core_steps(plan: dict, sims: list[dict], ops: set[str], role: str = "core"):
    """(before, after) states of every op in `ops` inside scenes with this role, in lesson order."""
    out = []
    for sc, sim in zip(plan["scenes"], sims):
        if sc.get("role", "core") != role:
            continue
        prev = sim["before"]
        for st in sim["steps"]:
            if st["last"].get("op") in ops:
                out.append((prev, st))
            prev = st
    return out


def _taught(text: str, pattern: str) -> bool:
    return re.search(pattern, text, re.I | re.S) is not None


def _ll_questions(rng, plan, sims, a, text) -> list[dict]:
    f = a["focus"]
    qs: list[dict] = []
    if f == "delete":
        steps = [(b, s) for b, s in _core_steps(plan, sims, {"delete_value"}) if s["last"].get("found")]
        if not steps:
            return []
        before, st = steps[0]
        items, last = before["items"], st["last"]
        t, prev, nxt = last["removed"], last.get("prev"), last.get("next")
        ch = _chain(items)
        nxt_s = "null" if nxt is None else nxt
        if prev is not None:
            qs.append(_finish(rng, f"After deleting {t} from {ch}, what does node {prev} point to?",
                              _pick(rng, nxt_s, [t, "null" if nxt is not None else items[0], prev], items),
                              f"{prev} was the node before {t}, so its next pointer is rewired past {t} to {nxt_s}. The list becomes {_chain(st['items'])}."))
            qs.append(_finish(rng, f"When deleting {t} from {ch}, which node's next pointer changes?",
                              _pick(rng, prev, [t, nxt_s if nxt is not None else items[0], items[0]], items),
                              f"Only the node before {t}, which is {prev}, changes its next pointer; {t} is skipped and no other node moves.", "principle"))
            if _taught(text, r"\bhead\b[^.]*\b(?:delet|remov)\w*|\b(?:delet|remov)\w*[^.]*\bthe head\b") and len(items) >= 2:
                qs.append(_finish(rng, f"If we delete the head {items[0]} from {ch} instead, what becomes the new head?",
                                  _pick(rng, items[1], [items[0], "null", items[-1]], items),
                                  f"There is no node before the head, so the head pointer simply moves to the second node, {items[1]}."))
            elif _taught(text, r"\btail\b|\blast node\b") and len(items) >= 2:
                qs.append(_finish(rng, f"If we delete the tail {items[-1]} from {ch} instead, what does {items[-2]} point to afterwards?",
                                  _pick(rng, "null", [items[-1], items[0]], items),
                                  f"{items[-2]} becomes the new tail, so its next pointer is set to null."))
            else:
                hops = [str(x) for x in items].index(str(prev)) + 1
                qs.append(_finish(rng, f"To delete {t} from {ch}, how many nodes do we walk through to reach the node before it?",
                                  _numeric_options(rng, hops, [hops + 1, len(items)]),
                                  f"We start at the head and walk to {prev}, the node before {t}: that is {hops} node(s)."))
        else:
            qs.append(_finish(rng, f"After deleting the head {t} from {ch}, what does the head point to?",
                              _pick(rng, nxt_s, [t, "null"], items), f"The head pointer moves past {t} to {nxt_s}."))
            qs.append(_finish(rng, f"When deleting the head {t} from {ch}, which pointer changes?",
                              ["the head pointer", f"{t}'s next pointer", f"the next pointer of {items[-1]}", "no pointer changes"],
                              f"There is no node before the head, so only the head pointer moves."))
        return qs
    if f in ("search", "traverse"):
        steps = _core_steps(plan, sims, {"search"}) or []
        found = [(b, s) for b, s in steps if s["last"].get("found")]
        if found:
            before, st = found[0]
            items, path, t = before["items"], st["last"]["path"], st["last"]["value"]
        else:  # a walk-only lesson: the last core walk is the target
            walks = _core_steps(plan, sims, {"walk"})
            if not walks:
                return []
            before, st = walks[-1]
            items, t = before["items"], st["last"]["value"]
            path = items[: [str(x) for x in items].index(str(t)) + 1]
        ch = _chain(items)
        fmt = lambda xs: ", ".join(map(str, xs))
        qs.append(_finish(rng, f"Searching {ch} for {t}, which nodes are checked, in order?",
                          [fmt(path), *dict.fromkeys(x for x in (fmt(list(reversed(path))), fmt(items), fmt(path[1:]) or "none", fmt([t])) if x != fmt(path))][:4],
                          f"A linked list can only be walked from the head, so the search checks {fmt(path)} before it finds {t}.", "principle"))
        qs.append(_finish(rng, f"Searching {ch} for {t}, how many nodes are checked?", _numeric_options(rng, len(path), [1, len(items)]),
                          f"The walk checks {fmt(path)}: {len(path)} node(s), because there is no index to jump to."))
        if _taught(text, r"\bnull\b|\bnot (?:in|there|found)\b"):
            qs.append(_finish(rng, f"If we search {ch} for a value that is not in it, where does the search stop?",
                              [f"at null, after checking {items[-1]}", f"at the head, {items[0]}", f"at {items[len(items) // 2]}", "it jumps straight to the end"],
                              f"The search follows next pointers until a pointer is null, so it stops at null, after checking {items[-1]}: every node is checked first."))
        return qs
    if f == "insert":
        steps = _core_steps(plan, sims, {"insert_head", "insert_after", "insert_tail"})
        if not steps:
            return []
        before, st = steps[0]
        items, last, op = before["items"], st["last"], st["last"]["op"]
        v, ch = last["value"], _chain(before["items"])
        if op == "insert_head":
            old = items[0] if items else "null"
            qs.append(_finish(rng, f"We insert {v} at the head of {ch}. What does the new node {v} point to?", _pick(rng, old, ["null", v], items),
                              f"The new node points to the old first node, {old}, so the rest of the list is kept."))
            qs.append(_finish(rng, f"After inserting {v} at the head of {ch}, what does the head point to?", _pick(rng, v, [old, "null"], items),
                              f"The head pointer moves to the new node {v}."))
        else:
            t = last["prev"]
            nxt = "null" if last.get("next") is None else last["next"]
            where = f"after {t}" if op == "insert_after" else "at the tail"
            qs.append(_finish(rng, f"After inserting {v} {where} in {ch}, what does {t} point to?", _pick(rng, v, [nxt, "null"], items),
                              f"{t} now points to the new node {v}."))
            qs.append(_finish(rng, f"After inserting {v} {where} in {ch}, what does the new node {v} point to?", _pick(rng, nxt, [t, v], items),
                              f"The new node takes over {t}'s old next pointer, so it points to {nxt}."))
        if _taught(text, r"\bfirst\b[^.]*\bnew node\b|\bnew node\b[^.]*\bfirst\b|\border matters\b"):
            qs.append(_finish(rng, "When inserting a node, which pointer is set first so the rest of the list is never lost?",
                              ["the new node's next pointer", "the head pointer", "the tail's next pointer", "no pointer changes"],
                              "The new node first points at the node that should follow it; only then is the earlier pointer moved to the new node."))
        return qs
    # what_is: anatomy, the no-index limitation and the lesson's own demos, on the lesson's own list
    inits = [s for _b, s in _core_steps(plan, sims, {"init"}, "setup")] or [s for s in (sim["state"] for sim in sims) if s.get("kind") == "linked_list" and s["items"]]
    if not inits or len(inits[0]["items"]) < 2:
        return []
    items = inits[0]["items"]
    ch = _chain(items)
    for before, st in _core_steps(plan, sims, {"delete_value"}):
        last = st["last"]
        if last.get("found") and last.get("prev") is not None:
            nxt = "null" if last.get("next") is None else last["next"]
            qs.append(_finish(rng, f"After deleting {last['removed']} from {_chain(before['items'])}, what does node {last['prev']} point to?",
                              _pick(rng, nxt, [last["removed"], "null" if nxt != "null" else before["items"][0]], before["items"]),
                              f"{last['prev']}'s next pointer is rewired past {last['removed']} to {nxt}."))
            break
    for before, st in _core_steps(plan, sims, {"insert_head"}):
        old = before["items"][0] if before["items"] else "null"
        qs.append(_finish(rng, f"We insert {st['last']['value']} at the head of {_chain(before['items'])}. What does the new node point to?",
                          _pick(rng, old, ["null", st["last"]["value"]], before["items"]),
                          f"The new node points to the old first node, {old}, and the head now points to the new node."))
        break
    if len(items) >= 3:
        k = min(3, len(items) - 1)
        qs.append(_finish(rng, f"In {ch}, how many next pointers do we follow from the head node to reach {items[k]}?",
                          _numeric_options(rng, k, [0, k + 1, len(items)]),
                          f"There is no index to jump to: from the head {items[0]} we follow {k} next pointer(s) to reach {items[k]}."))
    qs.append(_finish(rng, f"In {ch}, what does the last node, {items[-1]}, point to?", _pick(rng, "null", [items[0], items[-2]], items),
                      "The last node's next pointer is null, which marks the end of the list."))
    return qs[:3]


def _compare_questions(rng, plan, sims) -> list[dict]:
    arr = next((s["items"] for _b, s in _core_steps(plan, sims, {"init"}, "setup") if s["kind"] == "array"), None)
    gets = _core_steps(plan, sims, {"get"})
    ins = _core_steps(plan, sims, {"insert_at"})
    if not arr or not gets:
        return []
    k = gets[0][1]["last"]["index"]
    vals = ", ".join(map(str, arr))
    qs = [_finish(rng, f"In the lesson's array [{vals}], how many items must the computer step through before it can read index {k}?",
                  _numeric_options(rng, 0, [k, k + 1, len(arr)]),
                  f"An array jumps straight to index {k}: its slots sit side by side, so no other item is looked at.", "principle"),
          _finish(rng, f"In the lesson's linked list {_chain(arr)}, how many next pointers do we follow from the head node to reach {arr[k]}?",
                  _numeric_options(rng, k, [0, k + 1, len(arr)]),
                  f"A linked list has no index: from the head {arr[0]} we follow {k} next pointer(s) to reach {arr[k]}.")]
    if ins:
        b, st = ins[0]
        i, v = st["last"]["index"], st["last"]["value"]
        qs.append(_finish(rng, f"Inserting {v} at index {i} of the array [{', '.join(map(str, b['items']))}]: how many items shift right?",
                          _numeric_options(rng, st["last"]["shifted"], [0, 1, len(b["items"])]),
                          f"Every item from index {i} onward shifts right: {st['last']['shifted']} item(s). A linked list would only rewire pointers."))
    return qs


def _op_questions(rng, plan, sims, structure: str) -> list[dict]:
    """Questions about the core operations of an array, queue, stack or tree lesson, on the lesson's own data."""
    qs: list[dict] = []
    fmt = lambda xs: ", ".join(map(str, xs))
    for before, st in _core_steps(plan, sims, set(make(structure).ops) - {"init"}):
        last, items, after = st["last"], before["items"], st["items"]
        op = last["op"]
        pool = list(dict.fromkeys([*items, *after]))
        if structure == "queue" and op == "dequeue":
            ans = after[0] if after else "empty"
            qs.append(_finish(rng, f"The queue is [{fmt(items)}] (front first). After a dequeue, what is the new front?",
                              _pick(rng, ans, [last["removed"], items[-1]], pool), f"Dequeue removes {last['removed']} from the front, so the front becomes {ans}."))
        elif structure == "queue" and op == "enqueue":
            qs.append(_finish(rng, f"The queue is [{fmt(items) or 'empty'}] (front first). After enqueue {last['value']}, which item is at the back?",
                              _pick(rng, last["value"], [after[0]], pool), f"Enqueue adds {last['value']} at the back; the front stays {after[0]}."))
        elif structure == "stack" and op == "pop":
            ans = after[-1] if after else "empty"
            qs.append(_finish(rng, f"The stack is [{fmt(items)}] (bottom to top). After a pop, what is the new top?",
                              _pick(rng, ans, [last["removed"], items[0]], pool), f"Pop removes {last['removed']} from the top, so the top becomes {ans}."))
        elif structure == "stack" and op == "push" and items:
            qs.append(_finish(rng, f"The stack is [{fmt(items)}] (bottom to top). After push {last['value']}, which item is directly below the top?",
                              _pick(rng, items[-1], [last["value"], items[0]], pool), f"{last['value']} lands on top of the old top, {items[-1]}."))
        elif op == "peek":
            qs.append(_finish(rng, f"The {structure} holds [{fmt(items)}]. What does peek return?", _pick(rng, last["value"], [items[0], items[-1]], pool),
                              f"Peek reads {last['value']} without removing it."))
        elif op == "insert_at" and last["index"] + 1 < len(after):
            i = last["index"]
            qs.append(_finish(rng, f"The array is [{fmt(items)}]. After inserting {last['value']} at index {i}, which value is at index {i + 1}?",
                              _pick(rng, after[i + 1], [last["value"], items[i + 1] if i + 1 < len(items) else items[-1]], pool),
                              f"Later items shift right, so the array becomes [{fmt(after)}] and index {i + 1} holds {after[i + 1]}."))
            qs.append(_finish(rng, f"The array is [{fmt(items)}]. Inserting {last['value']} at index {i}: how many items shift right?",
                              _numeric_options(rng, last["shifted"], [0, len(items)]), f"Every item from index {i} onward moves: {last['shifted']} item(s)."))
        elif op == "delete_at":
            i = last["index"]
            ans = after[i] if i < len(after) else "nothing, it was the last slot"
            qs.append(_finish(rng, f"The array is [{fmt(items)}]. After deleting index {i}, which value is at index {i}?",
                              _pick(rng, ans, [last["removed"]], pool), f"Later items shift left to close the gap: [{fmt(after)}]."))
            qs.append(_finish(rng, f"The array is [{fmt(items)}]. Deleting index {i}: how many items shift left?",
                              _numeric_options(rng, last["shifted"], [0, len(items)]), f"Every item after index {i} moves: {last['shifted']} item(s)."))
        elif op == "get":
            i = last["index"]
            qs.append(_finish(rng, f"In the array [{fmt(items)}], which value is at index {i}?", _pick(rng, last["value"], [items[i - 1] if i else items[-1]], pool),
                              f"Indexes start at 0, so index {i} holds {last['value']}."))
            qs.append(_finish(rng, f"To read index {i} of [{fmt(items)}], how many other items does the computer look at?",
                              _numeric_options(rng, 0, [i, len(items)]), "None: an array jumps straight to the slot."))
        elif op == "set":
            qs.append(_finish(rng, f"The array is [{fmt(items)}]. After setting index {last['index']} to {last['value']}, what does it hold?",
                              _list_options(rng, after) if len(set(after)) > 1 else [fmt(after), fmt(items)], f"Only that slot changes: [{fmt(after)}]."))
        elif op == "append":
            qs.append(_finish(rng, f"The array is [{fmt(items) or 'empty'}]. At which index does {last['value']} land after append?",
                              _numeric_options(rng, last["index"], [0, len(items) + 1]), f"Append puts it in the next free slot, index {last['index']}."))
        elif op == "insert_bst":
            path = last["path"]
            if len(path) >= 2:
                qs.append(_finish(rng, f"Inserting {last['value']} into the lesson's tree (root {path[0]}), which node becomes its parent?",
                                  _pick(rng, path[-2], [path[0], *path], pool), f"The path is {fmt(path)}, so {last['value']} hangs under {path[-2]}."))
        elif op == "search_bst":
            path = last["path"]
            qs.append(_finish(rng, f"Searching the lesson's tree for {last['value']}, which nodes are visited, in order?",
                              [fmt(path), *dict.fromkeys(x for x in (fmt(sorted(path)), fmt(list(reversed(path))), fmt(path[:1])) if x != fmt(path))][:4],
                              f"Each comparison picks a side: {fmt(path)}."))
        if len(qs) >= 3:
            break
    return qs


# ---------------------------------------------------------------- "what is X": the rule, real-world use / vocabulary, a short trace
def _demo_values(plan: dict, ops: set[str]) -> list:
    return [o["args"][0] if len(o.get("args", [])) == 1 else o["args"][-1]
            for s in plan["scenes"] for o in s.get("ops", []) if o["op"] in ops and o.get("args")]


def _principle_question(rng, s: str, plan: dict, sims) -> dict | None:
    """The core rule in plain words, on the lesson's own values; the answer is computed by running the real structure."""
    if s in ("stack", "queue"):
        add = "push" if s == "stack" else "enqueue"
        vals = list(dict.fromkeys(_demo_values(plan, {add})))[:3]
        if len(vals) < 3:
            return None
        ds = make(s)
        for v in vals:
            ds.apply(add, [v])
        first_out = ds.apply("pop" if s == "stack" else "dequeue")["last"]["removed"]
        if s == "stack":
            return _finish(rng, f"You push {vals[0]}, then {vals[1]}, then {vals[2]}. Which one comes out first when you pop?",
                           [str(first_out), *(str(v) for v in vals if v != first_out)],
                           f"Last in, first out: {first_out} went in last, so it comes out first.", "principle")
        return _finish(rng, f"{vals[0]}, {vals[1]} and {vals[2]} join a queue in that order. Which one is served first?",
                       [str(first_out), *(str(v) for v in vals if v != first_out)],
                       f"First in, first out: {first_out} joined first, so it is served first.", "principle")
    if s == "linked_list":
        items = next((st["items"] for sim in sims for st in sim["steps"] if st["last"].get("op") == "init"), None)
        if not items or len(items) < 3:
            return None
        return _finish(rng, f"In the list {_chain(items)}, how does the computer reach {items[2]}?",
                       ["It follows the next pointers from the head", "It jumps straight to it by its index", "It starts from the tail and goes backwards",
                        "It looks in the middle first"],
                       f"A linked list has no index: from the head, it follows the next pointers until it reaches {items[2]}.", "principle")
    if s == "array":
        gets = [st for sim in sims for st in sim["steps"] if st["last"].get("op") == "get"]
        if not gets:
            return None
        k = gets[0]["last"]["index"]
        return _finish(rng, f"To read index {k} of [{', '.join(map(str, gets[0]['items']))}], what does the computer do?",
                       ["It jumps straight to that slot", "It checks every slot starting from index 0", "It starts from the last slot",
                        "It follows pointers from the first item"],
                       f"Every slot has an index, so the computer jumps straight to index {k} without looking at the others.", "principle")
    if s == "binary_tree":
        ins = [st for sim in sims for st in sim["steps"] if st["last"].get("op") in ("insert_bst", "init")]
        vals = [x for st in ins for x in (st["last"].get("values") or [st["last"].get("value")]) if x is not None]
        if len(vals) < 2:
            return None
        root, v = vals[0], vals[-1]
        side = "left" if v < root else "right"
        return _finish(rng, f"In the lesson's tree the root is {root}. Inserting {v}, which way does it go from the root?",
                       [side, "right" if side == "left" else "left", "it becomes the new root", "it goes to whichever side has fewer values"],
                       f"{v} is {'smaller' if side == 'left' else 'larger'} than {root}, so it goes {side}: smaller left, larger right.", "principle")
    return None


def _trace_question(rng, s: str, plan: dict, sims) -> dict | None:
    """A short trace (at most 3 operations) on the lesson's own values, answered by running the real structure."""
    if s in ("stack", "queue"):
        add, rem = ("push", "pop") if s == "stack" else ("enqueue", "dequeue")
        vals = list(dict.fromkeys(_demo_values(plan, {add})))[:3]
        if len(vals) < 3:
            return None
        ds = make(s)
        for v in vals:
            ds.apply(add, [v])
        ds.apply(rem)
        st = ds.apply(rem)
        end = "top" if s == "stack" else "front"
        ans = st[end]
        order = "bottom to top" if s == "stack" else "front first"
        return _finish(rng, f"The {s} holds [{', '.join(map(str, vals))}] ({order}). After {rem} twice, what is at the {end}?",
                       [str(ans), *(str(v) for v in vals if v != ans)],
                       f"Running it on a real {s}: two {rem}s leave [{', '.join(map(str, st['items']))}], so the {end} is {ans}.")
    if s == "linked_list":
        items = next((st["items"] for sim in sims for st in sim["steps"] if st["last"].get("op") == "init"), None)
        if not items or len(items) < 2:
            return None
        k = min(3, len(items) - 1)
        return _finish(rng, f"In {_chain(items)}, how many next pointers do we follow from the head node to reach {items[k]}?",
                       _numeric_options(rng, k, [0, k + 1, len(items)]), f"From the head {items[0]} we follow {k} next pointer(s) to reach {items[k]}.")
    if s == "array":
        for sim in sims:
            for st in sim["steps"]:
                last = st["last"]
                if last.get("op") == "insert_at" and last["index"] + 1 < len(st["items"]):
                    i = last["index"]
                    before = [x for j, x in enumerate(st["items"]) if j != i]
                    return _finish(rng, f"The array is [{', '.join(map(str, before))}]. After inserting {last['value']} at index {i}, which value is at index {i + 1}?",
                                   _pick(rng, st["items"][i + 1], [last["value"], before[i + 1] if i + 1 < len(before) else before[-1]], before),
                                   f"Later items shift right, so the array becomes [{', '.join(map(str, st['items']))}].")
    qs = _op_questions(rng, plan, sims, s)
    return qs[0] if qs else None


VOCAB_WORD = {"stack": r"\bpop\w*", "queue": r"\bdequeu\w*", "linked_list": r"\bnull\b", "array": r"\bindex"}  # taught -> may be asked


def what_is_questions(plan: dict, sims, seed: str) -> list[dict]:
    """Principle (plain words), real-world use or vocabulary (fixed answer key), and a short trace. Only what the lesson taught."""
    s = plan["structure"]
    rng = random.Random(int(hashlib.sha256(("what_is:" + seed).encode()).hexdigest()[:8], 16))
    text = " ".join(sc.get("narration", "") for sc in plan["scenes"])
    qs = []
    principle = _principle_question(rng, s, plan, sims)
    if principle is None and s in ("graph_bfs", "bubble_sort"):
        principle = next(iter(lesson_questions(plan, seed) or []), None)
        if principle:
            principle["kind"] = "principle"
    if principle:
        qs.append(principle)
    if concepts.uses_ok(s, text) and s in concepts.REAL_WORLD_QUIZ:
        q, a, wrong, expl = concepts.REAL_WORLD_QUIZ[s]
        qs.append(_finish(rng, q, [a, *wrong], expl, "real_world"))
    elif s in concepts.VOCAB_QUIZ and re.search(VOCAB_WORD.get(s, "^$"), text, re.I):
        q, a, wrong, expl = concepts.VOCAB_QUIZ[s]
        qs.append(_finish(rng, q, [a, *wrong], expl, "vocab"))
    trace = _trace_question(rng, s, plan, sims)
    if trace:
        qs.append(trace)
    return qs[:3]


def complexity_questions(plan: dict, seed: str) -> list[dict]:
    """A complexity lesson's quiz is only about complexity, and every answer is counted by running the real algorithm:
    the worst-case count for 5 items, how the work grows when the input doubles, and which input is the best case."""
    import complexity
    from structures import count_work

    algo = plan["analysis"]["algorithm"]
    a = complexity.ALGOS[algo]
    rng = random.Random(int(hashlib.sha256(("complexity:" + seed).encode()).hexdigest()[:8], 16))
    n = 5
    count = count_work(algo, n)
    if a["family"] == "graph":
        q1 = (f"Breadth first search runs on a chain of {n} nodes ({n - 1} edges). How many steps does it take, counting every "
              "visit and every neighbour check?")
        pool = [n, n + (n - 1), n * n, 2 * (n - 1)]
        expl = f"{n} visits, one per node, plus {count - n} neighbour checks, two per edge: {n} + {count - n} = {count}."
    else:
        q1 = f"In the worst case, how many {a['units']} does {a['name']} make on {n} items?"
        pool = [n, n * n, n * (n - 1), n - 1, 1, 2 * n]
        if a["family"] == "sort":
            expl = f"The passes make {' + '.join(map(str, range(n - 1, 0, -1)))} = {count} comparisons, which is n(n - 1) / 2 = {n} × {n - 1} / 2."
        elif a["family"] == "scan":
            expl = f"A missing target is compared with all {n} items: {count} comparisons."
        else:
            expl = f"{a['reason'].capitalize()}, so it is {count} step whatever the size."
    q1_opts = [str(count)] + [str(x) for x in dict.fromkeys(pool) if x != count][:3]
    lo, hi = count_work(algo, 8), count_work(algo, 16)
    ratio = round(hi / lo)
    words = {1: "about the same", 2: "about 2 times as much", 4: "about 4 times as much", 8: "about 8 times as much"}
    q2_opts = [words.get(ratio, f"about {ratio} times as much")] + [w for r, w in words.items() if r != ratio][:3]
    what = "nodes" if a["family"] == "graph" else "items"
    q2 = (f"If the input doubles from 8 to 16 {what}, how much work does {a['name']} do in the worst case, compared with before?")
    expl2 = f"Counted for real: {lo} {a['units']} for 8 {what} and {hi} for 16, about {ratio} times as much ({a['big_o']})."
    if ratio == 1:
        expl2 = f"Counted for real: {lo} {a['unit']} for 8 {what} and {hi} for 16: the work stays the same ({a['big_o']})."
    best = {
        "sort": (f"Which input is the best case for {a['name']}?",
                 ["a list that is already sorted", "a list in reverse order", "a list with the largest value first", "a list of random values"],
                 f"A sorted list needs no swaps at all: {count_work(algo, n, 'best')} comparisons for {n} items instead of {count}."),
        "scan": (f"Which search is the best case for {a['name']}?",
                 ["the target is the first item", "the target is the last item", "the target is not there at all", "the target is in the middle"],
                 f"The search stops at the first comparison: {count_work(algo, n, 'best')} comparison, {a['best_o']}."),
        "graph": ("Which graph is the best case for breadth first search, if the number of nodes and edges stays the same?",
                  ["none: every shape takes V + 2E steps", "a star, with every node joined to the start", "a chain of nodes in a line",
                   "a graph where the start is in the middle"],
                  "Every node is visited once and every edge is checked from both ends, whatever the shape: O(V + E)."),
        "one": (f"Which input is the best case for {a['name']}?",
                ["none: every size costs the same single step", "a small structure", "a large structure", "an empty structure"],
                f"{a.get('reason', '').capitalize()}, so the work never depends on n: {a['big_o']}."),
    }[a["family"]]
    return [_finish(rng, q1, q1_opts, expl, "complexity"), _finish(rng, q2, q2_opts, expl2, "complexity"),
            _finish(rng, best[0], list(best[1]), best[2], "complexity")]


# ---------------------------------------------------------------- question-driven lessons (no fixed intents)
def _step_question(rng, sim: dict) -> dict | None:
    """A short computed question about what ONE of the lesson's own steps did (answer = the true state)."""
    st = sim["state"]
    last = st.get("last", {})
    op = last.get("op")
    before_items = (sim["steps"][-2] if len(sim["steps"]) > 1 else sim["before"]).get("items", [])  # just before the last op
    if op == "delete_value" and last.get("found") and last.get("prev") is not None:
        nxt = "null" if last.get("next") is None else str(last["next"])
        return _finish(rng, f"In {_chain(before_items)}, after deleting {last['removed']}, what does {last['prev']} point to?",
                       _options(rng, nxt, [str(last["removed"]), str(last["prev"]), "null", *map(str, before_items)]),
                       f"{last['prev']} now points to {nxt}, so {last['removed']} is skipped.")
    if op in ("pop", "dequeue"):
        return _finish(rng, f"The {st['kind']} holds [{_list(before_items)}]. Which item does {op} remove?",
                       _options(rng, last["removed"], before_items),
                       f"{op.capitalize()} always removes the {'top' if op == 'pop' else 'front'}: {last['removed']}.")
    if op == "visit":
        name = "queue" if st["kind"] == "graph_bfs" else "stack"
        algo = "breadth first search" if st["kind"] == "graph_bfs" else "depth first search"
        if not (st.get("queue") if st["kind"] == "graph_bfs" else st.get("stack")) and len(st.get("order", [])) >= 3:
            order = [str(x) for x in st["order"]]  # the run finished: ask for its visit order (the point of a traversal)
            wrong = [order[:1] + order[1:][::-1], sorted(order), order[:1] + order[2:] + order[1:2]]
            return _finish(rng, f"Starting at {order[0]} on the lesson's graph, in what order does {algo} visit the nodes?",
                           _options(rng, ", ".join(order), [", ".join(w) for w in wrong]),
                           f"{algo.capitalize()} uses a {name}, so it visits {', '.join(order)}.")
        mid = next((s for s in sim["steps"] if s["last"].get("op") == "visit" and (s.get("queue") or s.get("stack"))), st)
        st, last = mid, mid["last"]
        q = st.get("queue") if st["kind"] == "graph_bfs" else st.get("stack")
        return _finish(rng, f"Right after visiting {last['removed']}, which nodes are waiting in the {name}?",
                       _queue_options(rng, [str(x) for x in q or []], [str(x) for x in st.get("items", [])]),
                       f"After visiting {last['removed']}, the {name} holds {'[' + _list(q) + ']' if q else 'nothing'}.")
    if op == "step" and st.get("comparisons"):
        return _finish(rng, f"Sorting [{_list(sim['steps'][0]['last'].get('values') or before_items) if sim['steps'][0]['last'].get('op') in ('reload', 'load') else _list(before_items)}]"
                       f" in the lesson, how many comparisons had been made at the end of this run?",
                       _numeric_options(rng, st["comparisons"], st.get("pass_counts", [])),
                       f"Counted by running the real algorithm: {' + '.join(map(str, st.get('pass_counts', [])))} = {st['comparisons']}.")
    if op == "scan":
        return _finish(rng, f"Linear search looks for {last['target']} in [{_list(st['items'])}]. How many comparisons does it make?",
                       _numeric_options(rng, last["checked"], [len(st["items"])]),
                       f"It compares one item per step and stops at index {last['index']}: {last['checked']} comparisons.")
    if op in ("push", "enqueue", "insert_head"):
        end = {"push": "top", "enqueue": "back", "insert_head": "head"}[op]
        truth = st.get("top") if op == "push" else st.get("back") if op == "enqueue" else st.get("head")
        return _finish(rng, f"After {op.replace('_', ' ')} {last['value']}, what is at the {end}?",
                       _options(rng, truth, before_items), f"The new item goes to the {end}: {truth}.")
    if st["kind"] == "growth" and st.get("rows"):
        r = st["rows"][min(2, len(st["rows"]) - 1)]
        return _finish(rng, f"In the lesson's table of real counts, what is the count for n = {r['n']}?",
                       _numeric_options(rng, r["count"], [x["count"] for x in st["rows"]] + [r["n"], r["n"] * r["n"]]),
                       f"Counted by running the real algorithm on n = {r['n']} items: {r['count']}.")
    return None


def question_questions(plan: dict, seed: str) -> list[dict]:
    """Quiz of a question-driven lesson, built from its answer points and real evidence: first a question on the CORE point
    (the first requirement), then short computed questions on the lesson's own steps. Nothing the lesson did not cover."""
    import complexity
    rng = random.Random(int(hashlib.sha256(("question:" + seed).encode()).hexdigest()[:8], 16))
    try:
        sims = simulate(plan["structure"], plan["scenes"])
    except Exception:  # noqa: BLE001
        return []
    text = " ".join(s.get("narration", "") for s in plan["scenes"])
    reqs = plan["analysis"].get("requirements", [])
    point_req = {p["id"]: p.get("requirement_id") for p in plan.get("answer_points") or []}
    order = {r["id"]: k for k, r in enumerate(reqs)}
    op_scenes = sorted((i for i, s in enumerate(plan["scenes"]) if s.get("ops") and point_req.get(s.get("point_id")) in order),
                       key=lambda i: (order[point_req[plan["scenes"][i]["point_id"]]], i))
    qs: list[dict] = []
    algo = next((a for i in op_scenes if (a := complexity.infer_algo([sims[i]["before"], *sims[i]["steps"]]))), None)
    if algo and re.search(r"\bO\(|\bcomplexit", text):  # the lesson answered a complexity question: ask about its answer
        cq = complexity_questions({"analysis": {"algorithm": algo}}, seed)
        qs.append({**cq[0], "kind": "core"})
        if re.search(r"\bdoubl|\btimes\b", text):
            qs.append(cq[1])
        if re.search(r"\bbest[\s-]+case", text, re.I):
            qs.append(cq[2])
    s = plan["structure"]
    if not qs and s in concepts.PRINCIPLE:
        proof = concepts.PRINCIPLE[s]["proof_ops"]
        if any(o["op"] in proof for sc in plan["scenes"] for o in sc.get("ops", [])):
            if (p := _principle_question(rng, s, plan, sims)):
                qs.append({**p, "kind": "core"})
    for i in op_scenes:
        if len(qs) >= 3:
            break
        q = _step_question(rng, sims[i])
        if q and q["question"] not in {x["question"] for x in qs}:
            qs.append({**q, "kind": "core"} if not qs else q)
    return qs[:3]


def focus_questions(plan: dict, seed: str) -> list[dict]:
    """At least 2 of 3 questions test the focus of the user's question, using the lesson's own data."""
    a = plan.get("analysis")
    if not a:
        return []
    if a.get("intent") == "question":
        return question_questions(plan, seed)
    if a.get("intent") == "complexity" and a.get("algorithm"):
        return complexity_questions(plan, seed)
    rng = random.Random(int(hashlib.sha256(("focus:" + seed).encode()).hexdigest()[:8], 16))
    try:
        sims = simulate(plan["structure"], plan["scenes"])
    except Exception:  # noqa: BLE001
        return []
    text = " ".join(s.get("narration", "") for s in plan["scenes"])
    if a["intent"] == "what_is" and any(s.get("kind") == "rule" for s in plan["scenes"]):  # answer-first "what is" lesson
        return what_is_questions(plan, sims, seed)
    if a["focus"] in ("delete", "insert") and a["structure"] in ("stack", "queue"):
        principle = _principle_question(rng, a["structure"], plan, sims)
        return ([principle] if principle else []) + _op_questions(rng, plan, sims, a["structure"])[:2]
    if a["focus"] == "compare":
        return _compare_questions(rng, plan, sims)
    if a["structure"] == "linked_list":
        return _ll_questions(rng, plan, sims, a, text)
    if a["structure"] in ("graph_bfs", "bubble_sort"):
        return lesson_questions(plan, seed) or []
    return _op_questions(rng, plan, sims, a["structure"])


# ---------------------------------------------------------------- optional LLM rewording
def _tokens(text: str, labels: set[str]) -> list[str]:
    nums = re.findall(r"\d+", text)
    labs = [t for t in re.findall(r"\b[A-Za-z0-9]{1,12}\b", text) if t in labels and not t.isdigit()]
    return sorted(nums + labs)


def _reword(qs: list[dict], structure: str, level: str, labels: set[str]) -> list[dict]:
    prompt = (
        f"Reword these {len(qs)} quiz questions about a {structure.replace('_', ' ')} for a {level} student so they read naturally. "
        "Keep every number, node label and operation exactly as given, in the same order. Do not add hints or answers.\n"
        + "\n".join(f"{i + 1}. {q['question']}" for i, q in enumerate(qs))
        + '\nReturn JSON: {"questions": [str, ...]}'
    )
    try:
        reworded = llm.generate_json(prompt, {"type": "object", "properties": {"questions": {"type": "array", "items": {"type": "string"}}}})
        for q, text in zip(qs, reworded.get("questions", [])):
            if isinstance(text, str) and _tokens(text, labels) == _tokens(q["question"], labels):
                q["question"] = text.strip()
    except Exception:
        pass  # templates are already correct; wording is optional
    return qs


def list_questions(plan: dict, seed: str) -> list[dict]:
    """A LIST lesson's quiz: which kind matches each plain description (the options are the lesson's own kinds), and how
    many kinds the lesson named. Answers come from the lesson itself, never from the LLM."""
    a = plan.get("analysis") or {}
    items = a.get("items") or []
    lines = {p.get("item"): p["point"] for p in plan.get("answer_points") or [] if p.get("item")}
    rng = random.Random(int(hashlib.sha256(("list:" + seed).encode()).hexdigest()[:8], 16))
    names = [it["name"] for it in items]
    noun = (plan["structure"] or "").replace("_", " ")
    qs = []
    for it in items:
        line = lines.get(it["name"], "")
        hidden = re.sub(it["pattern"], "this kind", line, flags=re.I) if line else ""
        if not hidden or "this kind" not in hidden or len(names) < 2:
            continue
        others = [n for n in names if n != it["name"]]
        rng.shuffle(others)
        qs.append(_finish(rng, f"Which kind of {noun} is described here? \"{hidden}\"", [it["name"], *others[:3]],
                          f"{line}", "principle"))
    rng.shuffle(qs)
    qs = qs[:2]
    if a.get("count_facts"):
        n = a["count_facts"][0]
        qs.append(_finish(rng, f"How many main kinds of {noun} did the lesson show?", _numeric_options(rng, n, [n + 2]),
                          f"The lesson showed {n}: {', '.join(names)}.", "core"))
    elif len(items) > 2:
        it = items[-1]
        others = [n for n in names if n != it["name"]][:3]
        qs.append(_finish(rng, f"Which of these is one of the kinds of {noun} in the lesson?", [it["name"], "a sorted " + noun,
                          "a random " + noun, "a hidden " + noun][: 1 + min(3, len(others) + 1)], f"The lesson named: {', '.join(names)}."))
    return qs[:3]


def make_quiz_from_plan(plan: dict, seed: str, level: str = "beginner", reword: bool = True) -> list[dict]:
    """3 questions about THIS lesson's data. Falls back to random data only if the lesson has no usable ops.
    reword=False keeps the wording computed by code (no LLM call), e.g. when the lesson's budget of 3 calls is spent."""
    if (plan.get("analysis") or {}).get("shape") == "list":
        return list_questions(plan, seed)
    qs = focus_questions(plan, seed)
    if (plan.get("analysis") or {}).get("intent") in ("complexity", "question"):
        if len(qs) < 3 and plan["analysis"]["intent"] == "question":  # top up with traces of the lesson's own data
            seen = {q["question"] for q in qs}
            qs += [q for q in (lesson_questions(plan, seed) or []) if q["question"] not in seen][: 3 - len(qs)]
        return qs  # computed by code, worded by code: no LLM call (the lesson's budget is 3 calls)
    if len(qs) < 3:  # top up with questions about the lesson's own data (never generic, never another structure)
        seen = {q["question"] for q in qs}
        qs += [q for q in (lesson_questions(plan, seed) or []) if q["question"] not in seen][: 3 - len(qs)]
    qs = qs[:3] or template_questions(plan["structure"], seed)
    labels = {str(a) for _op, args in _lesson_ops(plan) for a in args if isinstance(a, str)} if plan["structure"] == "graph_bfs" else set()
    return _reword(qs, plan["structure"], level, labels) if reword else qs


def make_quiz(structure: str, seed: str, level: str = "beginner") -> list[dict]:
    """Random-data quiz (kept for callers without a plan)."""
    return _reword(template_questions(structure, seed), structure, level, set(LABELS))
