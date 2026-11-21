"""Time complexity lessons: "what is the time complexity of bubble sort?" is answered with a derivation, not a demo.

The answer is outlined first (answer points), and every scene teaches exactly one point:
  goal     the question, in one line                                         (setup)
  measure  what we count, and why that is the work; the input of size n      (setup)
  demo     the REAL algorithm run to completion with a live counter, grouped by pass / level   (core, may span scenes)
  derive   add up the counts and match the formula: 3 + 2 + 1 = 6 = n(n - 1) / 2               (core)
  big_o    Big-O in plain words: drop constants and smaller terms; doubling n -> about 4x work  (core)
  growth   growth table from the real counting function: n = 4, 8, 16, 100                     (core)
  best     best case, run for real (sorted input, early exit)                                  (core)
  worst    worst case, run for real (reversed input)                                           (core)
  recap    formula and takeaway in new wording                                                 (recap)

Every number is computed by code: the demo, best and worst case run the real structures (structures.py), the growth
table rows come from structures.count_work, and the formulas below are only used to check that both agree.
No LLM call is needed: the lesson is built and narrated in code, then verified like every other lesson.
"""
from __future__ import annotations

import re

from structures import ONE_OP, count_work

SIZES = [4, 8, 16, 100]  # growth table rows


def _w_bubble(n):
    return n * (n - 1) // 2


# Per algorithm: what we count, the formulas (only used to CHECK the real counts), Big-O, and its best / worst inputs.
ALGOS: dict[str, dict] = {
    "bubble_sort": {
        "structure": "bubble_sort", "family": "sort", "name": "bubble sort", "unit": "comparison", "units": "comparisons",
        "why": "the main work bubble sort does",
        "best_short": "an already sorted list", "worst_short": "a reversed list",
        "formula": "n(n - 1) / 2", "worst": _w_bubble, "best_formula": "n - 1", "best": lambda n: n - 1,
        "general": "(n - 1) + (n - 2) + ... + 1",
        "big_o": "O(n²)", "best_o": "O(n)", "growth_word": "quadratic time, which means the work grows with n squared", "double": 4,
        "best_input": "a list that is already sorted", "worst_input": "a list in reverse order", "default": [5, 1, 4, 2],
    },
    "linear_search": {
        "structure": "array", "family": "scan", "name": "linear search", "unit": "comparison", "units": "comparisons",
        "why": "the main work linear search does",
        "formula": "n", "worst": lambda n: n, "best_formula": "1", "best": lambda n: 1,
        "big_o": "O(n)", "best_o": "O(1)", "growth_word": "linear time, which means the work grows with n", "double": 2,
        "best_input": "the target is the first item", "worst_input": "the target is not in the array", "default": [10, 20, 30, 40],
    },
    "linked_list_search": {
        "structure": "linked_list", "family": "scan", "name": "searching a linked list", "unit": "comparison", "units": "comparisons",
        "why": "the main work, since we can only reach a node by walking from the head",
        "formula": "n", "worst": lambda n: n, "best_formula": "1", "best": lambda n: 1,
        "big_o": "O(n)", "best_o": "O(1)", "growth_word": "linear time, which means the work grows with n", "double": 2,
        "best_input": "the target is the head", "worst_input": "the target is not in the list", "default": [10, 20, 30, 40],
    },
    "bfs": {
        "structure": "graph_bfs", "family": "graph", "name": "breadth first search", "unit": "step", "units": "steps",
        "why": "visiting a node, and checking each neighbour of the node we visit",
        "formula": "V + 2E", "big_o": "O(V + E)", "best_o": "O(V + E)", "growth_word": "linear time, which means the work grows with the size of the graph",
        "double": 2, "default": [("A", "B"), ("A", "C"), ("B", "D"), ("C", "E")],
    },
}
ALGOS["insertion_sort"] = {**ALGOS["bubble_sort"], "structure": "insertion_sort", "name": "insertion sort",
                           "why": "the main work insertion sort does", "general": "1 + 2 + ... + (n - 1)",
                           "best_input": "a list that is already sorted", "worst_input": "a list in reverse order"}
ALGOS["dfs"] = {**ALGOS["bfs"], "structure": "graph_dfs", "name": "depth first search"}
_ONE = {  # constant-time operations: (name, what is touched, plain reason)
    "stack_push": ("push on a stack", "push", "push only ever touches the top"),
    "stack_pop": ("pop on a stack", "pop", "pop only ever touches the top"),
    "queue_enqueue": ("enqueue on a queue", "enqueue", "enqueue only ever touches the back"),
    "queue_dequeue": ("dequeue on a queue", "dequeue", "dequeue only ever touches the front"),
    "array_access": ("reading an array by index", "get", "the computer jumps straight to the slot from its index"),
    "linked_list_insert_head": ("inserting at the head of a linked list", "insert_head", "only the new node and the head pointer change"),
}
for _algo, (_name, _op, _why) in _ONE.items():
    ALGOS[_algo] = {"structure": ONE_OP[_algo][0], "family": "one", "name": _name, "op": _op, "unit": "step", "units": "steps",
                    "why": "every item read or moved", "reason": _why,
                    "formula": "1", "worst": lambda n: 1, "best_formula": "1", "best": lambda n: 1,
                    "big_o": "O(1)", "best_o": "O(1)", "growth_word": "constant time, which means a single step no matter how many items there are", "double": 1,
                    "default": [10, 20, 30, 40]}

BIG_O_TEXT = {"O(n²)": r"O\(\s*n\s*(?:²|\^\s*2|\*\*\s*2|\s+squared)\s*\)", "O(n)": r"O\(\s*n\s*\)", "O(1)": r"O\(\s*1\s*\)",
              "O(V + E)": r"O\(\s*V\s*\+\s*E\s*\)"}
UNIT_WORDS = r"comparisons?|steps?|checks?|visits?"


# ---------------------------------------------------------------- question analysis
COMPLEXITY_WORDS = re.compile(
    r"\bcomplexit\w*|\bbig[\s-]*o\b|\bhow\s+(?:fast|slow|efficient|quick(?:ly)?)\b|\brunning\s+time\b|\bO\s*\(\s*[^)]{1,12}\)"
    r"|\bn\s*(?:squared|\^\s*2|²|\*\s*n)\b|\bquadratic\b|\b(?:best|worst|average)[\s-]+case\b|\bhow\s+(?:long|much\s+work)\s+does\b"
    r"|\befficien(?:t|cy)\b|\bscal(?:e|es|ing)\b", re.I)
LINEAR_SEARCH = re.compile(r"\blinear\s+search\w*|\bsequential\s+search\w*", re.I)


def algorithm_for(structure: str, verb: str | None, text: str) -> str | None:
    """Which algorithm a complexity question is about (None: Structura cannot count it yet)."""
    if structure == "bubble_sort":
        return "bubble_sort"
    if structure == "graph_bfs":
        return "bfs"
    if structure == "array":
        if LINEAR_SEARCH.search(text) or verb == "search":
            return "linear_search"
        return "array_access" if verb in (None, "access", "update") else None
    if structure == "linked_list":
        if verb in (None, "search", "traverse", "access"):
            return "linked_list_search"
        return "linked_list_insert_head" if verb == "insert" else None
    if structure == "stack":
        return {None: "stack_push", "insert": "stack_push", "delete": "stack_pop"}.get(verb)
    if structure == "queue":
        return {None: "queue_enqueue", "insert": "queue_enqueue", "delete": "queue_dequeue"}.get(verb)
    return None


def catalogue(algo: str) -> dict:
    """What a complexity lesson about `algo` must say (used by focus.context)."""
    a = ALGOS[algo]
    return {"text": f"the time complexity of {a['name']}", "answer": f"What is the time complexity of {a['name']}, and why?",
            "terms": r"\bcomplexit\w*|\bO\(|\bgrow\w*|\b(?:" + UNIT_WORDS + r")\b",
            "intro": intro_text(algo), "recap": recap_text(algo)}


def must_cover(algo: str) -> list[list[str]]:
    """The elements a complexity answer MUST contain: [name, regex, the scene kind that should say it, hint]."""
    a = ALGOS[algo]
    return [
        ["the word complexity", r"\bcomplexit", "goal", intro_text(algo)],
        ["the Big-O answer", r"\bO\(", "big_o", f"so {a['name']} is {a['big_o']}"],
        [f"what is counted ({a['units']})", rf"\b{a['units'][:-1]}s?\b", "measure", f"We count {a['units']}, {a['why']}."],
        [f"the formula {a['formula']}", re.escape(a["formula"]), "derive", f"In the worst case that is {a['formula']} {a['units']}."],
        ["how the work grows", r"\bdoubl\w*|\btwice\b|\b\d+ times\b|\bgrows?\b|\bstays? (?:the same|flat)\b", "big_o",
         "Double the input and see how the work grows."],
    ]


# ---------------------------------------------------------------- lesson design (answer points first, then scenes)
def _pt(pid: str, kind: str, point: str, visual: str) -> dict:
    return {"id": pid, "kind": kind, "point": point, "visual": visual}


def _scene(ops: list[dict], role: str, kind: str, pid: str, structure: str | None = None) -> dict:
    s = {"ops": ops, "role": role, "kind": kind, "point_id": pid, "narration": "-"}
    if structure:
        s["structure"] = structure
    return s


def _op(name: str, *args) -> dict:
    return {"op": name, "args": list(args)}


def _fresh(values: list[int]) -> int:
    v = max(values) + 10
    return v - v % 10 if v % 10 else v


def build_scenes(algo: str, values: list | None = None) -> tuple[list[dict], list[dict]]:
    """(answer_points, scenes) for a complexity lesson. Only the demo may span several scenes."""
    a = ALGOS[algo]
    fam = a["family"]
    points = [_pt("p1", "goal", f"The question: what is the time complexity of {a['name']}, and why?", "none"),
              _pt("p2", "measure", f"What we measure: {a['units']}, {a['why']}.", "the input of size n"),
              _pt("p3", "demo", "Run the real algorithm to completion with a live counter.", "live counter, grouped by pass"),
              _pt("p4", "derive", f"Add up the counts and match the formula {a['formula']}.", "per-pass tally"),
              _pt("p5", "big_o", f"Big-O in plain words: keep the fastest-growing part, so {a['big_o']}.", "none"),
              _pt("p6", "growth", "The real counts for bigger inputs: n = " + ", ".join(map(str, SIZES)) + ".", "growth table")]
    scenes = [_scene([], "setup", "goal", "p1")]
    s = a["structure"]
    if fam == "sort":
        vals = list(values) if values and len(values) >= 2 else list(a["default"])
        scenes.append(_scene([_op("load", *vals)], "setup", "measure", "p2"))
        run = _passes(vals)
        for k in run:
            scenes.append(_scene([_op("step") for _ in range(k)], "core", "demo", "p3"))
        n = len(vals)
        best, worst = sorted(vals), sorted(vals, reverse=True)
        if len(set(vals)) < n:  # repeated values: use distinct ones so the best and worst cases are clear
            best, worst = list(range(1, n + 1)), list(range(n, 0, -1))
        tail = [_scene([_op("reload", *best)] + [_op("step")] * a["best"](n), "core", "best", "p7"),
                _scene([_op("reload", *worst)] + [_op("step")] * a["worst"](n), "core", "worst", "p8")]
    elif fam == "scan":
        vals = list(dict.fromkeys(values or [])) or list(a["default"])  # distinct values, the user's order
        vals = vals if len(vals) >= 2 else list(a["default"])
        build = _op("init", *vals)
        scenes.append(_scene([build], "setup", "measure", "p2"))
        target = vals[len(vals) // 2] if len(vals) > 2 else vals[-1]
        missing = _fresh(vals)
        scenes.append(_scene(_scan_ops(s, vals, target), "core", "demo", "p3"))
        tail = [_scene(_scan_ops(s, vals, vals[0]), "core", "best", "p7"),
                _scene(_scan_ops(s, vals, missing), "core", "worst", "p8")]
    elif fam == "graph":
        edges = [tuple(map(str, e)) for e in (values or a["default"])]
        start = edges[0][0]
        scenes.append(_scene([_op("add_edge", u, v) for u, v in edges] + [_op("start_bfs", start)], "setup", "measure", "p2"))
        for size in _levels(edges, start):
            scenes.append(_scene([_op("visit") for _ in range(size)], "core", "demo", "p3"))
        star = _star_like(edges)
        tail = [_scene([_op("reset")] + [_op("add_edge", u, v) for u, v in star] + [_op("start_bfs", star[0][0])]
                       + [_op("visit") for _ in range(len({x for e in star for x in e}))], "core", "cases", "p7")]
    else:  # one fixed-cost op on a growing structure
        vals = list(values or a["default"])[:6] if values and len(values) >= 2 else list(a["default"])
        op = a["op"]
        scenes.append(_scene([_op("init", *vals)], "setup", "measure", "p2"))
        more = [_fresh(vals) + 10 * i for i in range(len(vals))]
        if op in ("push", "enqueue", "insert_head"):
            first, second = [_op(op, more[0])], [_op(op, v) for v in more[1:]]
        elif op == "get":
            first, second = [_op("get", 0)], [_op("get", len(vals) - 1)]
        else:  # pop / dequeue: grow the structure first, then remove
            first = [_op(op)]
            grow = "push" if op == "pop" else "enqueue"
            second = [_op(grow, v) for v in more] + [_op(op)]
        scenes.append(_scene(first, "core", "demo", "p3"))
        scenes.append(_scene(second, "core", "demo", "p3"))
        tail = [_scene([], "core", "cases", "p7")]
    scenes.append(_scene([], "core", "derive", "p4"))
    scenes.append(_scene([], "core", "big_o", "p5"))
    scenes.append(_scene([_op(algo, *SIZES)], "core", "growth", "p6", structure="growth"))
    scenes.extend(tail)
    if fam in ("sort", "scan"):
        points += [_pt("p7", "best", f"Best case, run for real: {a['best_input']}, {a['best_o']}.", "the best input with its counter"),
                   _pt("p8", "worst", f"Worst case, run for real: {a['worst_input']}, {a['big_o']}.", "the worst input with its counter")]
    else:
        points.append(_pt("p7", "cases", "Best and worst case: does the input change the work?", "a second input with its counter"))
    rid = f"p{len(points) + 1}"
    points.append(_pt(rid, "recap", f"Takeaway: {a['big_o']}, and why.", "none"))
    scenes.append(_scene([], "recap", "recap", rid))
    return points, scenes


def _passes(values: list[int]) -> list[int]:
    from structures import run_bubble
    return run_bubble(values)["pass_counts"]


def _scan_ops(structure: str, values: list[int], target: int) -> list[dict]:
    stop = values.index(target) + 1 if target in values else len(values)
    if structure == "array":
        return [_op("scan", target) for _ in range(stop)]
    return [_op("walk", v) for v in values[:stop]]


def _levels(edges, start) -> list[int]:
    """How many nodes BFS visits at each level (the demo shows one level per scene)."""
    adj: dict = {}
    for u, v in edges:
        adj.setdefault(u, set()).add(v)
        adj.setdefault(v, set()).add(u)
    seen, frontier, out = {start}, [start], []
    while frontier:
        out.append(len(frontier))
        nxt = []
        for u in frontier:
            for w in sorted(adj[u]):
                if w not in seen:
                    seen.add(w)
                    nxt.append(w)
        frontier = nxt
    return out


def _star_like(edges) -> list[tuple[str, str]]:
    """A differently shaped graph with the same nodes and the same number of edges (a star when that is possible)."""
    nodes = sorted({x for e in edges for x in e})
    hub = nodes[0]
    star = [(hub, x) for x in nodes[1:]]
    extra = [e for e in edges if hub not in e][: max(0, len(edges) - len(star))]
    return star + extra


# ---------------------------------------------------------------- narration from the true state
def _list(xs) -> str:
    return "[" + ", ".join(map(str, xs)) + "]"


def _join(xs) -> str:
    xs = [str(x) for x in xs]
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def _plus(xs) -> str:
    return " + ".join(map(str, xs))


def _n(state: dict) -> int:
    return len(state.get("items", []))


def infer_algo(states: list[dict]) -> str | None:
    """Which counted algorithm a scene shows (so generic lessons get the same count checks), from its true states."""
    for st in reversed(states):
        kind, last = st.get("kind"), st.get("last", {})
        if kind == "growth" and st.get("algo"):
            return st["algo"]
        if kind in ("bubble_sort", "insertion_sort"):
            return kind
        if kind in ("graph_bfs", "graph_dfs") and st.get("visits"):
            return "bfs" if kind == "graph_bfs" else "dfs"
        if kind == "array" and last.get("op") == "scan":
            return "linear_search"
        if kind == "linked_list" and last.get("op") == "walk":
            return "linked_list_search"
        if isinstance(last.get("touched"), int):
            return next((a for a, (s, op, _args) in ONE_OP.items() if s == kind and op == last.get("op")), None)
    return None


def intro_text(algo: str) -> str:
    a = ALGOS[algo]
    what = {"sort": "the list", "scan": "the input", "graph": "the graph"}.get(a["family"], "the structure")
    return f"What is the time complexity of {a['name']}, and why? Let's count the work it really does as {what} grows."


def recap_text(algo: str) -> str:
    a = ALGOS[algo]
    if a["family"] == "sort":
        return (f"Takeaway: about n² / 2 {a['units']} in the worst case makes {a['name']} {a['big_o']}; "
                f"only a list that is already sorted lets it stop after its first pass, {a['best_o']}.")
    if a["family"] == "scan":
        return (f"Takeaway: in the worst case every item is checked once, so the work rises in step with n: {a['big_o']}. "
                f"It is {a['best_o']} only when the target happens to come first.")
    if a["family"] == "graph":
        return ("Takeaway: each node is visited once and each edge is checked from both ends, so the work rises in step with "
                f"the graph's size: {a['big_o']}, whatever its shape.")
    return f"Takeaway: {a['reason']}, so the work stays the same however many items there are: {a['big_o']}."


def narrate(algo: str, scene: dict, sim: dict) -> str:
    """The narration of one complexity scene, built only from its true state (always passes the checks)."""
    a = ALGOS[algo]
    kind, steps, st = scene.get("kind"), sim["steps"], sim["state"]
    fam = a["family"]
    if kind == "goal":
        return intro_text(algo)
    if kind == "recap":
        return recap_text(algo)
    if kind == "measure":
        return f"We measure time by counting {a['units']}: {a['why']}. " + _describe_input(fam, st)
    if kind == "demo":
        return {"sort": _demo_sort, "scan": _demo_scan, "graph": _demo_graph, "one": _demo_one}[fam](a, sim)
    if kind == "derive":
        return _derive(algo, st)
    if kind == "big_o":
        return _big_o(algo)
    if kind == "growth":
        rows = st["rows"]
        unit = a["units"]
        parts = [f"n = {r['n']} needs {r['count']}" for r in rows]
        parts[0] = f"n = {rows[0]['n']} needs {rows[0]['count']} {unit if rows[0]['count'] != 1 else a['unit']}"
        lo, hi = rows[1], rows[2]
        ratio = round(hi["count"] / lo["count"])
        where = "Counted for real on chains of n nodes: " if fam == "graph" else "Counted for real: "
        trend = (f"From n = {lo['n']} to n = {hi['n']}, the work grows about {ratio} times."
                 if ratio > 1 else "The work stays flat, however big n gets.")
        return where + ", ".join(parts[:-1]) + ", and " + parts[-1] + ". " + trend
    if kind in ("best", "worst"):
        return (_case_sort if fam == "sort" else _case_scan)(a, kind, sim)
    if kind == "cases":
        return _cases_graph(a, sim) if fam == "graph" else _cases_one(a, st)
    return ""


def _describe_input(fam: str, st: dict) -> str:
    items = st.get("items", [])
    if st["kind"] == "linked_list":
        return f"Here are n = {len(items)} nodes: " + " -> ".join(["head", *map(str, items), "null"]) + "."
    if st["kind"] == "graph_bfs":
        edges = ", ".join(f"{u}-{v}" for u, v in st["edges"])
        return (f"Here is a graph with V = {len(items)} nodes and E = {st['edge_count']} edges: {edges}. "
                f"BFS starts at {st['start']}. Queue is now {_list(st['queue'])}.")
    if st["kind"] == "stack":
        return f"Start with the stack {_list(items)}, bottom to top, so n = {len(items)}. The top is {st['top']}."
    if st["kind"] == "queue":
        return f"Start with the queue {_list(items)}, so n = {len(items)}. The front is {st['front']} and the back is {st['back']}."
    return f"Here are n = {len(items)} values: Array is now {_list(items)}."


def _demo_sort(a: dict, sim: dict) -> str:
    st, steps = sim["state"], sim["steps"]
    pairs = [f"{s['last']['values'][0]} and {s['last']['values'][1]} {'swap' if s['last']['swapped'] else 'stay'}" for s in steps]
    p = len(st["pass_counts"])
    k = st["pass_counts"][-1]
    n = st["size"]
    swapped = any(s["last"]["swapped"] for s in steps)
    text = f"Pass {p}: {', '.join(pairs)}. {k} {a['units'] if k != 1 else a['unit']}"
    text += f", {_plus(st['pass_counts'])} = {st['comparisons']} so far." if p > 1 else "."
    if not swapped:
        text += " No swaps in this pass."
    if st["is_sorted"]:
        stop = " so bubble sort stops early." if st["early_exit"] else ""
        return text + f" Array is now {_list(st['items'])}, and the list is sorted{',' + stop if stop else '.'}"
    placed = st["items"][n - st["passes"]]
    return text + f" {placed} is now in its final place. Array is now {_list(st['items'])}."


def _demo_scan(a: dict, sim: dict) -> str:
    st, steps = sim["state"], sim["steps"]
    last = steps[-1]["last"]
    if st["kind"] == "array":
        target = last["target"]
        checked = [st["items"][i] for i in range(last["checked"])]
        found = last["found"]
    else:
        target = last["value"]
        checked = st["items"][: last["checked"]]
        found = True
    k = len(checked)
    head = "check the head, " if st["kind"] == "linked_list" else "check "
    text = f"Search for {target}: {head}{_join(checked)}."
    if found:
        text += f" {target} is found after {k} {a['units'] if k != 1 else a['unit']}, because the search stops as soon as it finds the target."
    if st["kind"] == "linked_list":
        nxt = last.get("next")
        text += f" {target} points to {'null' if nxt is None else nxt}."
    return text


def _demo_graph(a: dict, sim: dict) -> str:
    st, steps = sim["state"], sim["steps"]
    visited = [s["last"]["removed"] for s in steps]
    checks = [f"{s['last']['removed']} has {s['last']['neighbours']} {'neighbour' if s['last']['neighbours'] == 1 else 'neighbours'}" for s in steps]
    q = f"Queue is now {_list(st['queue'])}." if st["queue"] else "The queue is now empty, so the search is finished."
    v, c = st["visits"], st["checks"]
    return (f"Visit {_join(visited)}, checking every neighbour: {', '.join(checks)}. {q} "
            f"{'Total work' if not st['queue'] else 'Work so far'}: {v} {'visit' if v == 1 else 'visits'} and {c} {'check' if c == 1 else 'checks'}.")


def _demo_one(a: dict, sim: dict) -> str:
    st, steps = sim["state"], sim["steps"]
    lasts = [s["last"] for s in steps]
    op = a["op"]
    main = [l for l in lasts if l["op"] == op]
    n = st.get("size", len(st.get("items", [])))
    if op == "get":
        l = main[-1]
        return (f"Read index {l['index']}: the computer jumps straight to that slot. Index {l['index']} holds {l['value']}, "
                f"and the read touched just {l['touched']} slot, out of n = {n}.")
    grow = [l for l in lasts if l["op"] != op]
    pre = ""
    if grow:
        pre = f"Add {_join([l['value'] for l in grow])} first, so n grows to {n + len(main)}. "
    if op in ("push", "enqueue", "insert_head"):
        vals = [l["value"] for l in main]
        what = {"push": "on the top", "enqueue": "at the back", "insert_head": "at the head"}[op]
        verb = {"push": "push", "enqueue": "enqueue", "insert_head": "insert"}[op]
        each = "it touches" if len(vals) == 1 else "each one touches"
        tail = {"push": f"The top is now {st.get('top')}.", "enqueue": f"The back is now {st.get('back')}.",
                "insert_head": "The list is now " + " -> ".join(["head", *map(str, st['items']), "null"]) + "."}[op]
        unit = "node" if op == "insert_head" else "slot"
        return f"{verb.capitalize()} {_join(vals)} {what}: {each} just {main[0]['touched']} {unit}, now with n = {n}. {tail}"
    l = main[-1]
    end = "top" if op == "pop" else "front"
    rest = f"The {end} is now {st.get(end)}." if st.get("items") else f"The {op == 'pop' and 'stack' or 'queue'} is now empty."
    return f"{pre}{op.capitalize()} {l['removed']} from the {end}: it touches just {l['touched']} slot. {rest}"


def _derive(algo: str, st: dict) -> str:
    a = ALGOS[algo]
    fam = a["family"]
    n = _n(st)
    if fam == "sort":
        worst = a["worst"](n)
        counts = list(range(n - 1, 0, -1))
        ran = st.get("pass_counts", [])
        text = f"Add up the passes: {_plus(counts)} = {worst} {a['units']}"
        if ran != counts:
            text = f"Our list stopped early, but in the worst case every pass runs: {_plus(counts)} = {worst} {a['units']}"
        return (text + f", which is {a['formula']} = {n} × {n - 1} / 2 = {worst}. For any n, the passes make "
                f"{a['general']}, which adds up to {a['formula']}.")
    if fam == "scan":
        return (f"Each comparison looks at a single item, so a target in position k takes k {a['units']}, and a missing target takes all "
                f"n = {n}. In the worst case the count is n, so the formula is simply {a['formula']} {a['units']}.")
    if fam == "graph":
        v, e = len(st["items"]), st["edge_count"]
        return (f"Every node is visited once: {st['visits']} visits for V = {v} nodes. Every edge is checked twice, once from each end: "
                f"{st['checks']} checks for E = {e} edges. Total work: {a['formula']} = {v} + {2 * e} = {v + 2 * e} {a['units']}.")
    return (f"The cost never depends on n: {a['reason']}, so it is {a['formula']} step now, with n = {n}, and it would still be "
            f"{a['formula']} step with a million items. Nothing is shifted, searched or copied.")


def _big_o(algo: str) -> str:
    a = ALGOS[algo]
    fam = a["family"]
    if fam == "sort":
        return (f"Big O keeps only the fastest-growing part: {a['formula']} is about n² / 2, and we drop the 1/2, so {a['name']} is "
                f"{a['big_o']}, {a['growth_word']}. In plain words: double the items and the work grows about {a['double']} times.")
    if fam == "scan":
        return (f"Big O keeps the part that grows: the worst case is n {a['units']}, so {a['name']} is {a['big_o']}, {a['growth_word']}. "
                "In plain words: double the items and the work doubles.")
    if fam == "graph":
        return (f"Big O drops the constant 2 in front of E, so {a['name']} is {a['big_o']}: {a['growth_word']}. "
                "In plain words: double the nodes and edges, and the work doubles.")
    return (f"A fixed amount of work is written {a['big_o']}: {a['growth_word']}. Double the items and the work stays the same.")


def _case_sort(a: dict, kind: str, sim: dict) -> str:
    st = sim["state"]
    start = sim["steps"][0]["last"]["values"]
    k = st["comparisons"]
    n = st["size"]
    if kind == "best":
        return (f"Best case: {a['best_short']}, {_list(start)}. Pass 1 makes {k} {a['units']} and no swaps, so bubble sort stops early: "
                f"{a['best_formula']} = {k}, which is {a['best_o']}: the work grows with n, not with n².")
    return (f"Worst case: {a['worst_short']}, {_list(start)}. Every comparison swaps and all {st['passes']} passes run: "
            f"{_plus(st['pass_counts'])} = {k} {a['units']}, the full {a['formula']}. Array is now {_list(st['items'])}.")


def _case_scan(a: dict, kind: str, sim: dict) -> str:
    st, last = sim["state"], sim["steps"][-1]["last"]
    is_array = st["kind"] == "array"
    k = last["checked"]
    if kind == "best":
        target = last["target"] if is_array else last["value"]
        where = "index 0" if is_array else "the head"
        link = "" if is_array else f" {target} points to {'null' if last.get('next') is None else last['next']}, but the walk can stop here."
        return (f"Best case: {a['best_input']}. Searching for {target} looks at {where}, which holds {target}, so {k} {a['unit']} is enough, "
                f"whatever n is: {a['best_o']}, a single step no matter how many items there are.{link}")
    target = last["target"] if is_array else _fresh(st["items"])
    checked = _join(st["items"][:k])
    end = "" if is_array else f" {st['items'][-1]} points to null, so the walk ends there."
    return (f"Worst case: {a['worst_input']}. Searching for {target} looks at all n = {k} items, {checked}, and never finds it.{end} "
            f"That is {k} {a['units']}, {a['big_o']}.")


def _cases_graph(a: dict, sim: dict) -> str:
    st = sim["state"]
    v, e = len(st["items"]), st["edge_count"]
    edges = ", ".join(f"{x}-{y}" for x, y in st["edges"])
    return (f"Best or worst case? BFS has no shortcut. On a differently shaped graph with the same V = {v} nodes and E = {e} edges, "
            f"{edges}, it still makes {st['visits']} visits and {st['checks']} checks, {st['visits'] + st['checks']} {a['units']} in total, "
            f"and the queue is now empty. The shape changes the visit order, not the work: {a['big_o']} in every case.")


def _cases_one(a: dict, st: dict) -> str:
    return (f"Best and worst case are the same: {a['reason']}, so no input can make it slower or faster. "
            f"Every call is {a['big_o']}.")


def _run_counts(st: dict) -> set[int]:
    """What a run has really counted by the end of a scene (its final state)."""
    if st.get("kind") in ("bubble_sort", "insertion_sort"):
        return {st.get("comparisons", 0), *st.get("pass_counts", [])}
    if st.get("kind") in ("graph_bfs", "graph_dfs"):
        return {st.get("visits", 0), st.get("checks", 0), st.get("visits", 0) + st.get("checks", 0)}
    return set()


def facts(algo: str, states: list[dict], run: dict | None = None) -> dict:
    """True numbers a complexity scene may state (used by the verifier).
    counts: what a count claim ("6 comparisons") may say. In a scene that RUNS the algorithm (`run` = its final state)
    only that run's own counts are allowed; a scene without ops (derivation, Big-O) may also use formula values.
    numbers: every number the scene may mention at all (counts, n, formula constants and values, growth rows)."""
    a = ALGOS[algo]
    formula_counts: set[int] = set()
    ns: set[int] = set()
    rows: dict[int, int] = {}
    numbers: set[int] = {1, 2}  # the constants of the formulas: n - 1, / 2, 1/2, 2E
    seen: set[int] = set()
    for st in states:
        kind = st.get("kind")
        if kind == "growth":
            rows.update({r["n"]: r["count"] for r in st.get("rows", [])})
            continue
        n = _n(st)
        if n:
            ns.add(n)
        seen |= _run_counts(st)
        if kind in ("graph_bfs", "graph_dfs"):
            e = st.get("edge_count", 0)
            numbers.update([e, 2 * e, n + 2 * e])
            formula_counts.add(n + 2 * e)
        if kind == "linked_list" and st.get("items"):
            numbers.add(_fresh(st["items"]))  # the missing target of the worst case (a walk never holds it)
        last = st.get("last", {})
        for key in ("checked", "touched", "neighbours"):
            if isinstance(last.get(key), int):
                seen.add(last[key])
    for n in list(ns):
        if "worst" in a:
            formula_counts.update([a["worst"](n), a["best"](n)])
            numbers.update([n - 1, a["worst"](n), a["best"](n), n * (n - 1)])
            if a["family"] == "sort":
                numbers.update(range(1, n))
                formula_counts.update(range(1, n))  # the worst-case passes n - 1, ..., 1
    if run is not None:
        counts = _run_counts(run) | {s.get("last", {}).get(k) for s in states[1:] for k in ("checked", "touched", "neighbours")
                                     if isinstance(s.get("last", {}).get(k), int)}
    else:
        counts = seen | formula_counts
    numbers |= seen | formula_counts | ns | set(rows) | set(rows.values())
    return {"counts": counts, "ns": ns, "rows": rows, "numbers": numbers}
