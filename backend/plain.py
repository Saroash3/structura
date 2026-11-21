"""Beginner narration written by code (the fallback when an LLM sentence fails verification or the clarity gate).

Every demo step is told in the running analogy first, then given its technical name, then the true state:
"A new person, 40, joins the back of the line, and we call this enqueue. 40 waits behind everyone else, so 10 is still at
the front." At most 2 sentences of at most 25 words; terms are always explained where they appear (picture first, name
second). Every value comes from the real state, and verifier.generic_template still checks the result before using it.
"""
from __future__ import annotations

import re

import clarity


def _join(xs) -> str:
    xs = [str(x) for x in xs]
    if not xs:
        return ""
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def _then(xs) -> str:
    return ", then ".join(str(x) for x in xs)


def _lower(s: str) -> str:
    return s if not s or re.match(r"[A-Z]{2,}\b", s) else s[:1].lower() + s[1:]


def _box(v) -> str:
    return "nothing" if v is None else f"box {v}"


# ---------------------------------------------------------------- the last op of a scene, in analogy words: (sentence 1, sentence 2)
QUEUE_VARIANT = {
    "simple": ("This is a simple queue, like an ordinary line of people.", "People join at the back and leave from the front."),
    "circular": ("Picture seats around a round table: after the last seat comes the first seat again.",
                 "A line that wraps round like this is called a circular queue."),
    "priority": ("Picture a line where the smallest number is served first, wherever that person joined.",
                 "A line served by importance like this is called a priority queue."),
    "deque": ("Picture a line where people can join or leave at either end.",
              "A line open at both ends is called a deque, short for double-ended queue."),
}
LIST_VARIANT = {
    "singly": ("Each box's note points only forward, to the next box.", "A chain like this is called a singly linked list."),
    "doubly": ("Each box now has a pair of notes: a note to the next box and a note back to the box before.",
               "A chain like this is called a doubly linked list."),
    "circular": ("The last box's note points back to the first box instead of to nothing.",
                 "A chain that loops like this is called a circular linked list."),
}


def _queue(last: dict, st: dict) -> tuple[str, str] | None:
    op, items = last["op"], st["items"]
    if op == "variant":
        return QUEUE_VARIANT.get(last["variant"])
    if op == "push_front":
        return f"A new person, {last['value']}, joins the front of the line.", f"Only a deque allows this, so {last['value']} is now at the front."
    if op == "pop_back":
        rest = f"Now {st['back']} is at the back." if items else "Now the line is empty."
        return f"The person at the back, {last['removed']}, leaves the line.", f"Only a deque allows this. {rest}"
    if op == "enqueue" and st.get("variant") == "priority":
        return (f"A new person, {last['value']}, joins and stands before everyone with a larger number.",
                f"So {st['front']} is at the front and is served first.")
    if op == "init":
        return (f"Picture a line of people: {_join(last['values'])} wait in that order, with {st['front']} at the front.",
                f"New people join at the back, behind {st['back']}.")
    if op == "enqueue":
        v = last["value"]
        rest = (f"The line was empty, so {v} is also at the front." if len(items) == 1
                else f"{v} waits behind everyone else, so {st['front']} is still at the front.")
        return f"A new person, {v}, joins the back of the line, and we call this enqueue.", rest
    if op == "dequeue":
        r = last["removed"]
        rest = f"and {st['front']} is now at the front." if items else "and the line is now empty."
        return f"The person at the front, {r}, leaves the line, and we call this dequeue.", f"{r} arrived first, so {r} leaves first, {rest}"
    if op == "peek":
        return f"We look at the front person, {last['value']}, without removing them, and we call this peek.", "So the line stays the same."
    return None


def _stack(last: dict, st: dict) -> tuple[str, str] | None:
    op, items = last["op"], st["items"]
    if op == "init":
        return (f"Picture a pile of plates: {_join(last['values'])} were put down in that order, so {st['top']} is on top.",
                "We can only add or take plates at the top.")
    if op == "push":
        v = last["value"]
        return f"We put plate {v} on top of the pile, and we call this push.", f"Plates only go on top, so {v} is now the top plate."
    if op == "pop":
        r = last["removed"]
        rest = f"and {st['top']} is now on top." if items else "and the pile is now empty."
        return f"We take the top plate, {r}, off the pile, and we call this pop.", f"{r} was the last plate put on, so it comes off first, {rest}"
    if op == "peek":
        return f"We look at the top plate, {last['value']}, without taking it off, and we call this peek.", "So the pile stays the same."
    return None


def _linked(last: dict, st: dict) -> tuple[str, str] | None:
    op, items = last["op"], st["items"]
    if op == "variant":
        return LIST_VARIANT.get(last["variant"])
    if op == "init":
        return (f"Picture a treasure hunt with boxes {_join(last['values'])}: each box holds a note saying where the next box is.",
                "That note is called a pointer.")
    if op == "insert_after":
        v, prev = last["value"], last["prev"]
        return (f"We put new box {v} after box {prev}: box {v}'s note points to {_box(last.get('next'))}, and box {prev}'s note now points to box {v}.",
                "No other box moves, so only those notes change.")
    if op == "insert_head":
        v = last["value"]
        return f"We put new box {v} at the start, and its note points to {_box(last.get('next'))}.", f"No other box moves, so box {v} is now the first box."
    if op == "insert_tail":
        v, prev = last["value"], last.get("prev")
        first = (f"We put new box {v} at the end: box {prev}'s note now points to box {v}, and box {v}'s note points to nothing."
                 if prev is not None else f"We put new box {v} into the empty chain, and its note points to nothing.")
        return first, "No other box moves."
    if op == "delete_value" and last.get("found") is False:
        return (f"We open boxes {_then(last.get('path', [])) or 'none'} and reach the end without finding {last['value']}, so nothing changes.", "")
    if op == "delete_value":
        r, prev, nxt = last["removed"], last.get("prev"), last.get("next")
        rest = f"No other box moves, so the boxes now go {_join(items)}." if items else "The chain is now empty."
        if prev is None:
            where = f"box {nxt}" if nxt is not None else "nothing, so the chain is empty"
            return f"The sign showing the first box is called the head; to remove box {r}, the head now points to {where}, and box {r} is skipped.", (rest if items else "")
        return f"To remove box {r}, box {prev}'s note now points to {_box(nxt)}, so box {r} is skipped.", rest
    if op == "search" and last.get("found") is False:
        return f"We open boxes {_then(last.get('path', [])) or 'none'} and reach the end without finding {last['value']}.", f"So {last['value']} is not in the chain."
    if op == "search":
        return (f"We open the boxes in order, {_then(last['path'])}, and box {last['value']} holds what we want.",
                "We cannot jump ahead, so we follow the notes one at a time.")
    return None


def _walks(steps: list[dict]) -> tuple[str, str]:
    lasts = [s["last"] for s in steps]
    path = [l["value"] for l in lasts]
    end = lasts[-1]
    nxt = end.get("next")
    if len(path) == 1 and end.get("prev") is None:
        first = f"We always start at the first box, {path[0]}, and its note points to {_box(nxt)}."
    elif len(path) == 1:
        first = f"We follow the note from box {end['prev']} to box {path[0]}, and box {path[0]}'s note points to {_box(nxt)}."
    else:
        first = f"We start at box {path[0]} and follow each note in turn: {_then(path)}."
    second = (f"Box {path[-1]}'s note says nothing, so this is the end of the chain." if nxt is None
              else f"There is no shortcut, so box {nxt} comes next.")
    return first, second


def _array(last: dict, st: dict) -> tuple[str, str] | None:
    op, items = last["op"], st["items"]
    if op == "init":
        return f"Picture a row of lockers holding {_join(last['values'])}, numbered from 0 on the left.", "The locker number is called an index."
    if op == "get":
        return (f"We go straight to the locker in position {last['index']} and find {last['value']}, without opening any other locker.",
                "Every locker has a number, so no searching is needed.")
    if op == "insert_at":
        return (f"We squeeze {last['value']} into the locker in position {last['index']}, so every later value moves a locker to the right.",
                f"The lockers now hold {_join(items)}.")
    if op == "delete_at":
        return (f"We empty the locker in position {last['index']}, which held {last['removed']}, so every later value moves a locker to the left.",
                f"The lockers now hold {_join(items)}.")
    if op == "append":
        return f"We put {last['value']} in the next free locker, position {last['index']}.", f"Nothing else moves, so the lockers now hold {_join(items)}."
    if op == "set":
        return f"We open the locker in position {last['index']} and replace {last['old']} with {last['value']}.", f"The lockers now hold {_join(items)}."
    if op == "scan":
        end = "so we have found it." if last.get("found") else "so we try the next locker."
        return f"We open the locker in position {last['index']}: it holds {last['value']}, and we want {last['target']}, {end}", ""
    return None


def _tree(last: dict, st: dict) -> tuple[str, str] | None:
    op = last["op"]
    if op == "init":
        return f"We add {_join(last['values'])} one at a time, starting with {st['root']} at the top.", "At each fork, smaller values go left and larger values go right."
    if op == "insert_bst":
        return (f"To add {last['value']}, we start at the top and follow the forks: {_then(last['path'])}.",
                f"Smaller goes left and larger goes right, so {last['value']} lands at the end of that road.")
    if op == "search_bst":
        return (f"To find {last['value']}, we start at the top and follow the forks: {_then(last['path'])}.",
                "Each fork rules out a whole side, so we never look at the other side.")
    return None


def _graph(steps: list[dict], st: dict) -> tuple[str, str] | None:
    dfs = st["kind"] == "graph_dfs"
    waiting = "to-do pile" if dfs else "waiting line"
    lasts = [s["last"] for s in steps if s["last"].get("op") != "reset"]
    if not lasts:
        return None
    edges = ["-".join(map(str, l["edge"])) for l in lasts if l.get("op") == "add_edge"]
    start = next((l for l in lasts if l.get("op") in ("start_bfs", "start_dfs")), None)
    visits = [l["removed"] for l in lasts if l.get("op") == "visit"]
    front = [str(x) for x in (st.get("stack") if dfs else st.get("queue")) or []]
    parts = []
    if edges:
        parts.append(f"we draw roads {_join(edges)}")
    if start:  # never "start at A, then visit A": say that A first goes into the waiting line
        parts.append(f"put {start['value']} in the {waiting}" if edges or visits else f"start at {start['value']} by putting it in the {waiting}")
    if visits:
        parts.append(("then visit " if parts else "we visit ") + ", ".join(map(str, visits)))
    first = (parts[0][:1].upper() + parts[0][1:] + (", " + ", ".join(parts[1:]) if len(parts) > 1 else "") + ".") if parts else ""
    if lasts[-1].get("op") == "add_edge":
        return first, "Each road joins a pair of places."
    named = f"The {waiting}, called a {'stack' if dfs else 'queue'},"  # picture first, then its name
    if front:
        second = (f"{named} now holds {_join(front)}, so " + ("we go deep down one corridor of the maze first." if dfs
                  else "nearer places come first, like a ripple."))
    else:
        second = f"{named} is now empty, so " + ("the whole maze is explored." if dfs else "the ripple has reached every place.")
    if len(visits) == 1 and not edges and not start:
        new = lasts[-1].get("pushed" if dfs else "enqueued") or []
        nb = "neighbour" if len(new) == 1 else "neighbours"
        put = ((f"put its new {nb} {_join(new)} on top of the {waiting}" if dfs else f"add its new {nb} {_join(new)} to the back of the {waiting}")
               if new else "it has no new neighbours")
        first = f"We visit {visits[0]}, the next place in the {waiting}, and {put}."
    return first, second


def _sort(steps: list[dict], st: dict) -> tuple[str, str] | None:
    cards = st["kind"] == "insertion_sort"
    who = "cards" if cards else "children"
    lasts = [s["last"] for s in steps]
    run = [l for l in lasts if l.get("op") == "step"]
    load = next((l for l in reversed(lasts) if l.get("op") in ("load", "reload")), None)
    if not run and load:
        return (f"We start with {who} {_join(load['values'])}.", "Each number is " + ("a card in your hand." if cards else "a child's height."))
    if not run:
        return None
    end = run[-1]
    if len(run) > 1:
        sweep = " + ".join(map(str, st.get("pass_counts", [])))
        first = f"We compare neighbours along the {who}: {sweep} = {st['comparisons']} comparisons so far."
        second = (f"Now the {who} stand in order: {_join(st['items'])}." if not cards else f"Now the hand is in order: {_join(st['items'])}.") \
            if st.get("is_sorted") else f"So far the {who} are {_join(st['items'])}."
        return first, second
    if end.get("finished"):
        return f"The {who} {_join(st['items'])} are already in order, so nothing changes.", ""
    a, b = end["values"]
    if cards:
        first = (f"We compare card {b} with {a} on its left: {b} is smaller, so it slides left past {a}." if end.get("swapped")
                 else f"We compare card {b} with {a} on its left: {b} is not smaller, so it stays put.")
        return first, f"The hand is now {_join(st['items'])}."
    first = (f"We compare {a} and {b}: {a} is taller, so the children swap places." if end.get("swapped")
             else f"We compare {a} and {b}: {a} is shorter, so they stay in place.")
    return first, f"The line is now {_join(st['items'])}."


def _grid(last: dict, st: dict) -> tuple[str, str] | None:
    op = last["op"]
    if op == "grid":
        return (f"Picture lockers in a grid, like seats in a cinema: {st['rows']} rows and {st['cols']} columns, both numbered from 0.",
                "A grid like this is called a 2D array, and each locker is found by its row and its column.")
    if op == "get2":
        return (f"We go straight to row {last['row']}, column {last['col']} and find {last['value']}.",
                "The row and the column together pick a single locker, so no searching is needed.")
    if op == "set2":
        return f"We open row {last['row']}, column {last['col']} and replace {last['old']} with {last['value']}.", ""
    return None


def _jagged(last: dict, st: dict) -> tuple[str, str] | None:
    op = last["op"]
    if op == "row":
        return (f"We add row {last['row']}: a row of {last['length']} locker{'s' if last['length'] != 1 else ''} holding {_join(last['values'])}.",
                "Rows of different lengths like these make a jagged array.")
    if op == "get2":
        return (f"We open row {last['row']}, column {last['col']} and find {last['value']}.",
                "Each row has its own length, so we only open lockers that exist.")
    return None


def _dyn(last: dict, st: dict) -> tuple[str, str] | None:
    op = last["op"]
    if op == "init_static":
        return (f"Picture a row of {st['capacity']} lockers bolted to the wall, holding {_join(st['items'])}.",
                "Its size never changes, so it is called a static array.")
    if op == "init_dynamic":
        return (f"Picture a row of {st['capacity']} lockers holding {_join(st['items'])}, which can move to a bigger row when full.",
                "An array that can grow like this is called a dynamic array.")
    if op == "append" and last.get("refused"):
        return (f"We try to add {last['value']}, but every locker is full and the row cannot grow.",
                f"So {last['value']} does not fit: that is the limit of a static array.")
    if op == "append" and last.get("resized"):
        return (f"Every locker is full, so we move to a new row of {last['new_capacity']} lockers and carry over the {last['copied']} old values.",
                f"Then {last['value']} goes into position {last['index']}.")
    if op == "append":
        return f"We put {last['value']} in the next free locker, position {last['index']}.", f"This row has {st['capacity']} lockers."
    if op == "get":
        return f"We go straight to the locker in position {last['index']} and find {last['value']}.", ""
    return None


BRIEF = {  # earlier ops of a scene, as short clauses in analogy words
    "queue": {"init": lambda l: f"people {_join(l['values'])} line up", "enqueue": lambda l: f"{l['value']} joins the back",
              "dequeue": lambda l: f"{l['removed']} leaves the front", "peek": lambda l: f"we look at {l['value']}"},
    "stack": {"init": lambda l: f"plates {_join(l['values'])} are piled up", "push": lambda l: f"plate {l['value']} goes on top",
              "pop": lambda l: f"plate {l['removed']} comes off", "peek": lambda l: f"we look at {l['value']}"},
    "linked_list": {"init": lambda l: f"boxes {_join(l['values'])} are laid out", "insert_after": lambda l: f"box {l['value']} goes after box {l['prev']}",
                    "insert_head": lambda l: f"box {l['value']} goes first", "insert_tail": lambda l: f"box {l['value']} goes last",
                    "delete_value": lambda l: f"we look for box {l['value']}", "search": lambda l: f"we look for box {l['value']}"},
    "array": {"init": lambda l: f"the lockers hold {_join(l['values'])}", "append": lambda l: f"{l['value']} goes in the next locker",
              "insert_at": lambda l: f"{l['value']} squeezes into position {l['index']}", "delete_at": lambda l: f"position {l['index']} is emptied",
              "set": lambda l: f"position {l['index']} changes to {l['value']}", "get": lambda l: f"we open position {l['index']}",
              "scan": lambda l: f"we check position {l['index']}"},
    "binary_tree": {"init": lambda l: f"we add {_join(l['values'])}", "insert_bst": lambda l: f"we add {l['value']}",
                    "search_bst": lambda l: f"we look for {l['value']}"},
}
DESCRIBE = {"queue": _queue, "stack": _stack, "linked_list": _linked, "array": _array, "binary_tree": _tree,
            "array_2d": _grid, "jagged_array": _jagged, "dyn_array": _dyn}


def op_narration(sim: dict) -> str | None:
    """Beginner narration for a scene with ops, from its true states, or None when this kind of scene has no plain template."""
    steps = [s for s in sim["steps"] if s["last"].get("op") != "reset"]
    if not steps:
        return None
    st = sim["state"]
    kind = st["kind"]
    if kind in ("graph_bfs", "graph_dfs"):
        pair = _graph(sim["steps"], st)
    elif kind in ("bubble_sort", "insertion_sort"):
        pair = _sort(steps, st)
    elif kind == "linked_list" and steps[-1]["last"].get("op") == "walk":
        k = len(steps)
        while k > 0 and steps[k - 1]["last"].get("op") == "walk":
            k -= 1
        pair = _walks(steps[k:])
        steps = steps[: k + 1]  # the walks are described together; earlier ops are summarised below
        if k:
            first, second = pair
            pre = [BRIEF["linked_list"].get(s["last"]["op"]) for s in steps[:k]]
            brief = ", then ".join(b(s["last"]) for b, s in zip(pre, steps[:k]) if b)
            joined = f"After {brief}, {_lower(first)}" if brief else first
            return _finish(joined if clarity.word_count(joined) <= clarity.MAX_WORDS else first, second)
        return _finish(*pair)
    elif kind in DESCRIBE:
        pair = DESCRIBE[kind](steps[-1]["last"], st)
    else:
        return None
    if not pair:
        return None
    first, second = pair
    if kind in BRIEF and len(steps) > 1:
        briefs = [BRIEF[kind].get(s["last"]["op"]) for s in steps[:-1]]
        if all(briefs):
            joined = f"After {', then '.join(b(s['last']) for b, s in zip(briefs, steps[:-1]))}, {_lower(first)}"
            if clarity.word_count(joined) <= clarity.MAX_WORDS:
                first = joined
    return _finish(first, second)


def _finish(first: str, second: str) -> str:
    return " ".join(p for p in (first, second) if p).strip()
