"""Run a plan's ops on the real structures and check narration against the true state.

Pipeline:
  1. simulate ops -> true state after every op (raises OpError on an impossible op)
  2. check each scene's narration:
       - every number and claim must match the true state ("removing 5", "the front is 8", "Queue is now [C, D]")
       - SPECIFICITY: a scene with ops must name its key facts (BFS: visited node + queue, sort: compared pair +
         array, stack/queue: moved item + new top/front, array: index + value). Vague sentences fail.
       - intros must define the structure in plain words with an analogy
  3. failing scenes go back to the LLM in ONE batched call that includes each scene's true state
  4. anything still failing gets a narration generated from the true state

So every shipped scene is verified and specific.
"""
from __future__ import annotations

import copy
import logging
import re
from typing import Callable

import concepts
from structures import COUNTED as COUNTED_OPS, make

log = logging.getLogger("structura.verifier")

# A "gap" between a keyword and a number: short, and never crossing punctuation.
GAP = r"[^\d.,;:!?]{0,20}?"
NUM = r"(-?\d+)"

CLAIMS = [
    ("removed", rf"\b(?:remov\w*|dequeu\w*|pop\w*|delet\w*|took out|takes? out){GAP}{NUM}"),
    ("front", rf"\bfront\b(?!\s+of\b){GAP}{NUM}"),
    ("back", rf"\b(?:back|rear)\b(?!\s+of\b){GAP}{NUM}"),
    ("top", rf"\btop\b(?!\s+of\b){GAP}{NUM}"),
    ("head", rf"\bhead\b(?!\s+of\b){GAP}{NUM}"),
    ("tail", rf"\btail\b(?!\s+of\b){GAP}{NUM}"),
    ("root", rf"\broot\b{GAP}{NUM}"),
    ("height", rf"\bheight\b{GAP}{NUM}"),
    ("size", rf"\b(?:size|length)\b{GAP}{NUM}"),
    ("size", rf"{NUM}\s+(?:items?|elements?|values?)\b"),
]
COMPARE = re.compile(r"\bcompar\w*\s+(-?\d+)\s+(?:and|with|to|against)\s+(-?\d+)", re.I)
SWAP = re.compile(r"\bswap", re.I)
NO_SWAP = re.compile(r"\b(?:no|not|n't|without|never|nothing)\b[^.]{0,25}\bswap|\balready in (?:the )?(?:correct |right )?order\b|\bstay(?:s)? (?:where|in place|put)\b", re.I)
INDEX_HOLDS = re.compile(r"\bindex\s+(\d+)\s+(?:now\s+)?(?:is|holds|contains|has|stores)\s+(?:the\s+)?(?:value\s+)?(-?\d+)", re.I)
VALUE_AT = re.compile(r"(-?\d+)\s+(?:is\s+)?(?:now\s+)?(?:at|in)\s+index\s+(\d+)", re.I)
EMPTY = re.compile(r"\b(?:is|now|becomes|left)\s+(?:completely\s+)?empty\b", re.I)
# "Queue is now [C, D]", "Array is now [3, 7, 5]", "list [4, 7]": checked item by item
LIST_CLAIM = re.compile(r"\b(queue|array|list|stack)\s+(?:is\s+)?(?:now\s+)?(?:holds\s+|contains\s+|becomes\s+|looks like\s+)?\[([^\]]*)\]", re.I)
VISIT_CLAIM = re.compile(r"\b(?i:visit)(?:s|ing|ed)?\s+(?:(?i:node)\s+)?([A-Za-z0-9]{1,12})\b")  # verb any case, label exact
ALREADY_VISITED = re.compile(r"\b([A-Za-z0-9]{1,12})\s+(?i:is|was|has been|had been)\s+(?i:already)\s+(?i:visited)\b")
# Linked list pointer claims: "20 points to 40", "20's next pointer now points to null", "head points to 10",
# "30 is skipped", and chains "head -> 10 -> 20 -> null". All are checked against the real pointers.
POINTS_TO = re.compile(r"\b(head|-?\d+)(?:'s)?,?\s+(?:next\s+)?(?:pointer\s+|link\s+|note\s+)?(now\s+)?(?:points?|links?|leads?)\s+"
                       r"(?:directly\s+|straight\s+|only\s+)?(?:to|at)\s+(?:(?:the\s+)?(?:node|box)\s+)?(-?\d+|null|nothing)\b", re.I)
NEXT_IS = re.compile(r"\b(head|-?\d+)'s\s+next(?:\s+pointer)?\s+(now\s+)?(?:is|becomes|=)\s+(?:now\s+)?(-?\d+|null|nothing)\b", re.I)
SKIPPED = re.compile(r"\b(-?\d+)\s+(?:is|becomes|gets)\s+(?:now\s+)?(?:simply\s+)?(?:skipped|bypassed|unreachable|left out|cut out|unlinked|"
                     r"no longer (?:reachable|linked|in the (?:list|chain)|part of the (?:list|chain))|removed from the (?:list|chain))", re.I)
CHAIN = re.compile(r"(?:\bhead\s*(?:->|→)\s*)?-?\d+(?:\s*(?:->|→)\s*(?:-?\d+|null))+|\bhead\s*(?:->|→)\s*null\b", re.I)
NOW_BEFORE = re.compile(r"\bnow\b[^.]{0,25}$", re.I)
POINTER_WORD = r"\bpoint\w*|\bnext\b|\blink\w*|\brewir\w*"
SKIP_WORD = r"\bskip\w*|\bbypass\w*|no longer (?:reachable|linked|part)|\bunreachable\b|\bleft out\b|\bjumps? over\b|\bgoes? around\b|\bunlink\w*"
NOT_FOUND = r"\bnot\b|\bnull\b|\bnowhere\b|\bmissing\b|\bnothing changes\b"
# A recap that opens by defining the structure again ("A stack is last in, first out...") repeats the intro.
RECAP_DEFINES = re.compile(r"^\W*(?:so,?\s+|in short,?\s+|to recap,?\s+)?(?:an?\s+|the\s+)?(?:stacks?|queues?|linked lists?|arrays?|binary search trees?|trees?|"
                           r"graphs?|breadth[- ]first search|bfs|bubble sort)\s+(?:is|are|follows?|uses?|works?|means?)\b", re.I)
# A lesson that is not "what is X" must not open with a textbook definition.
DEFINITION = re.compile(r"\b(?:an?)\s+(?:linked list|array|queue|stack|binary search tree|graph)\s+is\s+(?:an?|the|like)\b", re.I)

SIZE_WORDS = re.compile(r"\bsize\b|\b\d+\s+(?:nodes|vertices|items|elements)\b", re.I)
ANALOGY = re.compile(r"\b(?:like|imagine|think of|similar to|just as|picture)\b", re.I)

# What an intro must convey per structure (the definition, in plain words).
INTRO_TERMS = {
    "array": r"\bindex",
    "queue": r"first (?:item )?in,? (?:is )?(?:the )?first (?:item )?out|\bFIFO\b",
    "stack": r"last (?:item )?in,? (?:is )?(?:the )?first (?:item )?out|\bLIFO\b",
    "linked_list": r"\bnode.*\b(?:pointer|next|link)|\b(?:pointer|link).*\bnode",
    "binary_tree": r"\b(?:smaller|less)\b.*\bleft\b|\bleft\b.*\b(?:smaller|less)\b",
    "graph_bfs": r"\blevel\b|\bneighbou?r",
    "bubble_sort": r"\bswap|\bneighbou?r|\badjacent",
    "insertion_sort": r"\binsert\w*|\bsorted part\b|\bslide\w*",
    "graph_dfs": r"\bdeep\w*|\bstack\b|\bbacktrack\w*",
}
GRAPH_KINDS = ("graph_bfs", "graph_dfs")
SORT_KINDS = ("bubble_sort", "insertion_sort")


def frontier(state: dict) -> list:
    """The nodes waiting to be visited: the BFS queue or the DFS stack."""
    return state.get("queue") if state.get("kind") == "graph_bfs" else state.get("stack") or []

# First sentence = intro (definition + analogy). Second = extra concept. Both number-free except
# the array's index 0 (always a valid index).
CONCEPT = {
    "array": ["An array stores items in a row of numbered slots, like lockers in a hallway: each slot has an index starting at 0, so you can jump straight to any item.",
              "Inserting or deleting in the middle is slower, because every later item has to shift over to make room."],
    "queue": ["A queue is a line where the first item in is the first item out, like people waiting at a ticket counter: you join at the back and leave from the front.",
              "Enqueue and dequeue each take a single quick step, because we only ever touch the ends of the queue."],
    "stack": ["A stack is a pile where the last item in is the first item out, like a stack of plates: you only add to or take from the top.",
              "Push and pop each take a single quick step, because only the top of the stack is ever touched."],
    "linked_list": ["A linked list is a chain of nodes where each node holds a value and a pointer to the next node, like a treasure hunt where each clue tells you where the next clue is.",
                    "Inserting at the head is instant, but finding a value means walking the chain from the head."],
    "binary_tree": ["A binary search tree keeps values in branches where smaller values go left and larger values go right, like a guessing game where each answer rules out half of the choices.",
                    "Because each comparison discards half of a balanced tree, searching is fast."],
    "graph_bfs": ["Breadth first search explores a graph level by level, like ripples spreading out from a stone dropped in a pond: first the start node, then its neighbours, then theirs, with a queue remembering who is next.",
                  "Every node is marked when it is discovered, so no node is ever visited twice."],
    "bubble_sort": ["Bubble sort repeatedly compares neighbouring items and swaps them when they are out of order, like bubbles rising in water: the largest value moves to the end on each pass.",
                    "After each pass, the largest remaining value has bubbled to its final place at the end."],
}


# ---------------------------------------------------------------- simulation and facts
def simulate(structure: str, scenes: list[dict]) -> list[dict]:
    """Run every scene's ops in order. Returns per-scene step states and final state.
    A scene may name its own `structure` (compare lessons: an array and a linked list side by side); a scene
    without ops shows the structure of the scene before it."""
    dss: dict = {}
    shown = structure
    out = []
    for scene in scenes:
        kind = scene.get("structure") or (structure if scene.get("ops") else shown)
        ds = dss.get(kind) or dss.setdefault(kind, make(kind))
        shown = kind
        current = ds.state()
        before = copy.deepcopy(current)
        steps = []
        for op in scene.get("ops", []):
            current = ds.apply(op["op"], op.get("args", []))
            steps.append(current)
        out.append({"before": before, "steps": steps, "state": current})
    return out


def _ints_in(obj) -> set[int]:
    """All integers in a state (values, queue contents, numeric labels). Layout floats and bools excluded."""
    if isinstance(obj, bool):
        return set()
    if isinstance(obj, int):
        return {obj}
    if isinstance(obj, str):
        return {int(obj)} if obj.isdigit() else set()
    if isinstance(obj, dict):
        return set().union(*(_ints_in(v) for k, v in obj.items() if k not in ("x", "y", "depth", "index", "current_index", "kind", "op")))
    if isinstance(obj, (list, tuple)):
        return set().union(*(_ints_in(v) for v in obj)) if obj else set()
    return set()


def facts(sim: dict) -> dict:
    """Everything the narration of one scene is allowed to state."""
    states = [sim["before"], *sim["steps"]]
    numbers: set[int] = set()
    removed: set = set()
    for st in states:
        numbers.update(_ints_in(st))
        if st["kind"] == "array":  # every valid index (and the next free one) is a fact
            numbers.update(range(len(st["items"]) + 1))
        if st["kind"] in ("array_2d", "jagged_array"):  # every row and column position
            numbers.update(range(max([st.get("rows", 0), st.get("cols", 0), *st.get("lengths", [0])]) + 1))
        if st["kind"] == "dyn_array":
            numbers.update(range(st.get("capacity", 0) + 1))
    missing: set = set()
    for st in sim["steps"]:
        last = st.get("last", {})
        numbers.update(_ints_in(last))
        if "index" in last:
            numbers.add(last["index"])
        if "removed" in last:
            removed.add(last["removed"])
        if last.get("found") is False:
            missing.add(last.get("value"))
    lasts = [st.get("last", {}) for st in sim["steps"]]
    final = sim["state"]
    return {"numbers": numbers, "removed": removed, "missing": missing, "final": final, "states": states,
            "labels": set(map(str, final.get("items", []))) if final["kind"] in GRAPH_KINDS else set(),
            "visited": [l["removed"] for l in lasts if l.get("op") == "visit"],
            "pairs": [sorted(l["values"]) for l in lasts if "compared" in l],
            "swapped": any(l.get("swapped") for l in lasts)}


UNITS = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
NUMBER_WORD = re.compile(
    r"\b(" + "|".join(TENS) + r")(?:[\s-](" + "|".join(UNITS[1:10]) + r"))?\b|\b(" + "|".join(UNITS) + r")\b", re.I)
# "one" used as a pronoun ("the one at the front", "no one") is not a number
PRONOUN_ONE = re.compile(r"\b(?:the|this|that|no|any|each|every|which|another|next|last|new|first|only|just)\s+one\b"
                         r"|\bone\s+(?:of|at|by|after|another|end|side|place|direction|way|single)\b", re.I)
SORTED_CLAIM = re.compile(r"\b(?:is|are|now|fully|completely|totally|been)\s+(?:now\s+|fully\s+|completely\s+)?sorted\b|\bin (?:sorted|ascending) order\b", re.I)


def strip_formulas(text: str) -> str:
    """Algebra in n is not a claim about the data: "n - 1", "n(n - 1) / 2", "n²", "2n" and "O(...)" become N, so only the
    values they are said to equal ("= 6") are checked as numbers."""
    t = re.sub(r"\bO\([^)]*\)", " N ", text)
    for _ in range(3):
        t = re.sub(r"\(\s*[nN]\s*[-+]\s*\d+\s*\)", "N", t)
    return re.sub(r"\b(?:\d+\s*)?[nN]+\b(?:\s*(?:\^|\*\*)\s*\d+|²)?(?:\s*[-+*/×]\s*(?:\d+\b|[nN]+\b))*", "N", t)


def words_to_digits(text: str) -> str:
    """'twenty one' -> '21', 'four' -> '4', so number words cannot dodge the checks."""
    text = PRONOUN_ONE.sub(lambda m: m.group(0).replace("one", "~"), text)

    def repl(m: re.Match) -> str:
        if m.group(1):
            return str(TENS[m.group(1).lower()] + (UNITS.index(m.group(2).lower()) if m.group(2) else 0))
        return str(UNITS.index(m.group(3).lower()))

    return NUMBER_WORD.sub(repl, text)


def _list_for(kind: str, final: dict, noun: str) -> list | None:
    """Which true list a "<noun> is now [...]" claim refers to, for this structure."""
    noun = noun.lower()
    if noun == "queue":
        return final.get("queue") if kind == "graph_bfs" else final["items"] if kind == "queue" else None
    if noun == "stack" and kind == "graph_dfs":
        return final.get("stack")
    if noun in ("array", "list"):
        return final["items"] if kind in ("array", "linked_list", *SORT_KINDS) else None
    if noun == "stack":
        return final["items"] if kind == "stack" else None
    return None


# ---------------------------------------------------------------- factual checks
def check_narration(narration: str, f: dict) -> list[str]:
    """Every number and claim must match the true state. Returns mismatches (empty = correct)."""
    errors = []
    final = f["final"]
    kind = final["kind"]
    narration = words_to_digits(narration)
    if kind in SORT_KINDS and SORTED_CLAIM.search(narration) and not final.get("is_sorted"):
        errors.append(f"Narration says the list is sorted, but it is {final['items']} and the sort has not finished.")
    if kind in (*GRAPH_KINDS, "binary_tree") and SIZE_WORDS.search(narration) and not f.get("sizes_ok"):
        errors.append(f"Do not talk about size for a {kind.replace('_', ' ')}; name the nodes, the path or the queue instead.")
    for num in re.findall(r"(?<!\w)-?\d+", strip_formulas(narration)):  # "A-2" / "1-2" are labels joined by a hyphen, not "-2"
        if int(num) not in f["numbers"]:
            errors.append(f"The number {num} does not appear in the true state of this scene.")
    for name, pattern in CLAIMS:
        for m in re.finditer(pattern, narration, re.I):
            claimed = int(m.group(1))
            if name == "removed":
                if re.search(r"\b(?:index|position)\b", m.group(0), re.I):
                    continue  # "delete index 2" names a position, not a value
                if claimed in f.get("missing", set()):
                    continue  # "try to delete 99" when 99 is not there: checked by the not-found facts instead
                if claimed not in f["removed"] and str(claimed) not in map(str, f["removed"]):
                    truth = sorted(map(str, f["removed"])) or "nothing"
                    errors.append(f"Narration says {claimed} was removed, but the removed item is {truth}.")
            elif name in final and final[name] is not None and not isinstance(final[name], str):
                if final[name] != claimed:
                    errors.append(f"Narration says the {name} is {claimed}, but the true {name} is {final[name]}.")
    if kind == "linked_list":
        errors += _pointer_errors(narration, f)
    for m in LIST_CLAIM.finditer(narration):
        truth = _list_for(kind, final, m.group(1))
        if truth is None:
            continue
        if kind == "linked_list" and m.group(1).lower() == "list":
            errors.append(f"Describe the linked list with its pointers, e.g. \"{chain(truth)}\", not as a bracketed list.")
            continue
        said = [x.strip() for x in m.group(2).split(",") if x.strip()]
        if said != [str(x) for x in truth]:
            errors.append(f"Narration says the {m.group(1).lower()} is [{', '.join(said)}], but it is [{', '.join(map(str, truth))}].")
    if kind in GRAPH_KINDS and f["visited"]:
        for m in VISIT_CLAIM.finditer(narration):
            if m.group(1) in f["labels"] and m.group(1) not in map(str, f["visited"]):
                errors.append(f"Narration says it visits {m.group(1)}, but this step visits {', '.join(map(str, f['visited']))}.")
    if kind in GRAPH_KINDS:  # "D is already visited" must be true (discovered/queued is not visited)
        for m in ALREADY_VISITED.finditer(narration):
            if m.group(1) in f["labels"] and m.group(1) not in map(str, final.get("order", [])):
                queued = m.group(1) in map(str, frontier(final))
                errors.append(f"Narration says {m.group(1)} is already visited, but it has not been visited"
                              f"{' yet: it is waiting in the queue' if queued else ''}.")
    if kind == "array":
        claims = [(int(m.group(1)), int(m.group(2))) for m in INDEX_HOLDS.finditer(narration)]
        claims += [(int(m.group(2)), int(m.group(1))) for m in VALUE_AT.finditer(narration)]
        for i, v in claims:
            if not (0 <= i < len(final["items"]) and final["items"][i] == v):
                truth = final["items"][i] if 0 <= i < len(final["items"]) else "out of range"
                errors.append(f"Narration says index {i} holds {v}, but index {i} is {truth}.")
    for m in COMPARE.finditer(narration):
        pair = sorted([int(m.group(1)), int(m.group(2))])
        if pair not in f.get("pairs", []):
            truth = " and ".join(str(p) for p in f["pairs"][0]) if f.get("pairs") else "nothing"
            errors.append(f"Narration compares {pair[0]} and {pair[1]}, but this step compares {truth}.")
    if f.get("pairs") and SWAP.search(narration):
        says_no_swap = bool(NO_SWAP.search(narration))
        if f["swapped"] and says_no_swap:
            errors.append("Narration says nothing is swapped, but the values were swapped.")
        if not f["swapped"] and not says_no_swap:
            errors.append("Narration says the values are swapped, but they were already in order.")
    count = len(frontier(final)) if kind in GRAPH_KINDS else final.get("size", len(final.get("items", [])))
    if EMPTY.search(narration) and count != 0:
        errors.append(f"Narration says it is empty, but it holds {count} item(s).")
    return sorted(set(errors))


def _next_of(state: dict, x: str):
    """What node `x` (a value, or "head") points to in this state: a value, None (null), or "absent"."""
    if state.get("kind") != "linked_list":
        return "absent"
    if x.lower() == "head":
        return state["items"][0] if state["items"] else None
    for p in state.get("pointers", []):
        if str(p["value"]) == x:
            return p["next"]
    return "absent"


def _same(target: str, truth) -> bool:
    return (truth is None and target.lower() in ("null", "nothing")) or (truth not in (None, "absent") and str(truth) == target)


def _chain_ok(tokens: list[str], items: list) -> bool:
    head = tokens[0].lower() == "head"
    null = tokens[-1].lower() == "null"
    vals = [t for t in tokens if t.lower() not in ("head", "null")]
    items = [str(x) for x in items]
    if not vals:
        return not items
    for i in range(len(items) - len(vals) + 1):
        if items[i:i + len(vals)] == vals and (not head or i == 0) and (not null or i + len(vals) == len(items)):
            return True
    return False


def _pointer_errors(narration: str, f: dict) -> list[str]:
    """Pointer claims, 'X is skipped' and 'head -> 10 -> 20 -> null' chains, against the real linked list.
    A claim with "now" must hold at the END of the scene; other claims may describe any moment of the scene."""
    errors = []
    final = f["final"]
    states = [s for s in f.get("states", [final]) if s.get("kind") == "linked_list"] or [final]
    for rx in (POINTS_TO, NEXT_IS):
        for m in rx.finditer(narration):
            x, now, y = m.group(1), m.group(2), m.group(3)
            pool = [final] if now else states
            if not any(_same(y, _next_of(st, x)) for st in pool):
                truth = _next_of(final, x)
                said = "null" if y.lower() in ("null", "nothing") else y
                if truth == "absent":
                    errors.append(f"Narration says {x} points to {said}, but {x} is not in the list.")
                else:
                    errors.append(f"Narration says {x} points to {said}, but {x} points to {'null' if truth is None else truth}.")
    for m in SKIPPED.finditer(narration):
        x = m.group(1)
        if x in map(str, final["items"]) or not any(x in map(str, st["items"]) for st in states):
            errors.append(f"Narration says {x} is skipped or unreachable, but the list is {chain(final['items'])}.")
    for m in CHAIN.finditer(narration):
        tokens = re.findall(r"head|null|-?\d+", m.group(0), re.I)
        pool = [final] if NOW_BEFORE.search(narration[: m.start()]) else states
        if not any(_chain_ok(tokens, st["items"]) for st in pool):
            errors.append(f"Narration shows the chain {m.group(0)}, but the real list is {chain(final['items'])}.")
    return errors


# ---------------------------------------------------------------- specificity
Token = str | tuple  # a value/label, "empty", or ("index", i)


def required_facts(sim: dict) -> list[tuple[Token, str]]:
    """What a scene with ops MUST name: (token, description). Uses the state after the scene's last op."""
    steps = sim["steps"]
    if not steps:
        return []
    st, last = steps[-1], steps[-1]["last"]
    op = last.get("op")
    req: list[tuple[Token, str]] = []

    def add(tok, desc):
        if tok is not None and (tok, desc) not in req:
            req.append((tok, desc))

    def queue_contents(q, kind="graph_bfs"):
        name = "stack" if kind == "graph_dfs" else "queue"
        if q:
            for x in q:
                add(str(x), f"the {name} contents [{', '.join(map(str, q))}]")
        else:
            add("empty", f"that the {name} is now empty")

    if op == "init":
        for v in last.get("values", []):
            add(v, "every value of the starting data")
    elif op == "walk":
        add(last["value"], "the node the walk moves to")
        add(last["next"] if last.get("next") is not None else "null", "the node it points to next (or null)")
    elif op == "delete_value" and last.get("found") is False:
        add(last["value"], "the value we tried to delete"); add(("re", NOT_FOUND), "that the value is not in the list")
    elif op == "delete_value" and st["kind"] == "linked_list":
        add(last["removed"], "the value deleted")
        if last.get("prev") is not None:
            add(last["prev"], "the node before it, whose next pointer is rewired")
            add(last["next"] if last.get("next") is not None else "null", "where that next pointer now leads")
        else:
            add(("re", r"\bhead\b"), "that the head pointer moves")
            add(last["next"] if last.get("next") is not None else "empty", "the new head")
        add(("re", POINTER_WORD), "the pointer being rewired")
        add(("re", SKIP_WORD), "that the deleted node is skipped and no longer reachable")
    elif op == "search" and last.get("found") is False:
        add(last["value"], "the value searched for"); add(("re", NOT_FOUND), "that the value is not in the list")
    elif op == "insert_after":
        add(last["value"], "the value inserted"); add(last["prev"], "the node it goes after")
        add(("re", POINTER_WORD), "the pointers that change")
    elif op == "enqueue":
        add(last["value"], "the value enqueued"); add(st["front"], "the front")
    elif op == "dequeue":
        add(last["removed"], "the value dequeued")
        add(st["front"], "the new front") if st["items"] else add("empty", "that the queue is now empty")
    elif op == "push":
        add(last["value"], "the value pushed")
    elif op == "pop":
        add(last["removed"], "the value popped")
        add(st["top"], "the new top") if st["items"] else add("empty", "that the stack is now empty")
    elif op in ("peek", "get", "search", "search_bst", "insert_bst", "insert_head", "insert_tail"):
        add(last["value"], "the value")
        if op == "get":
            add(("index", last["index"]), f"index {last['index']}")
    elif op == "append" and last.get("refused"):  # a full static array: the refused value and that it is full
        add(last["value"], "the value that does not fit"); add(("re", r"\bfull\b|\bno room\b"), "that the array is full")
    elif op in ("append", "insert_at", "set"):
        add(("index", last["index"]), f"index {last['index']}"); add(last["value"], "the value")
        if last.get("resized"):
            add(last["new_capacity"], "the new number of slots"); add(last["copied"], "how many values are copied")
    elif op in ("get2", "set2"):
        add(last["value"], "the value"); add(last["row"], "the row"); add(last["col"], "the column")
    elif op == "push_front":
        add(last["value"], "the value pushed at the front")
    elif op == "pop_back":
        add(last["removed"], "the value taken off the back")
    elif op in ("delete_at",):
        add(("index", last["index"]), f"index {last['index']}"); add(last["removed"], "the value removed")
    elif op == "delete_value":
        add(last["removed"], "the value deleted")
    elif op == "add_edge":
        for s in steps:
            for n in s["last"].get("edge", []):
                add(str(n), "every node joined by the edges in this scene")
    elif op in ("start_bfs", "start_dfs"):
        add(str(last["value"]), "the start node"); queue_contents(frontier(st), st["kind"])
    elif op == "visit":
        add(str(last["removed"]), "the node visited"); queue_contents(frontier(st), st["kind"])
    elif op == "load":
        for v in last["values"]:
            add(v, "every value loaded")
    elif op in ("step", "compare", "swap") and not last.get("finished"):
        for v in last["values"]:
            add(v, "both values compared")
        for v in st["items"]:
            add(v, f"the array after this step [{', '.join(map(str, st['items']))}]")
    return req


def _mentions(text: str, token: Token) -> bool:
    if isinstance(token, tuple) and token[0] == "re":  # ("re", pattern): an idea that must be said in words
        return re.search(token[1], text, re.I) is not None
    if isinstance(token, tuple):  # ("index", i)
        i = token[1]
        return re.search(rf"\bindex(?:es)?\s+{i}\b|\[{i}\]|\bposition\s+{i}\b|\bslot\s+{i}\b", text, re.I) is not None
    s = str(token)
    if s == "empty":
        return re.search(r"\bempty\b", text, re.I) is not None
    if s == "null":
        return re.search(r"\bnull\b|\bnothing\b|\bnone\b|\bend of the (?:list|chain)\b", text, re.I) is not None
    if re.fullmatch(r"-?\d+", s):
        return re.search(rf"(?<![\w.]){re.escape(s)}(?!\w)", text) is not None
    return re.search(rf"\b{re.escape(s)}\b", text) is not None  # labels are case-sensitive ("A" not "a")


def compact_state(state: dict) -> dict:
    """The state fields that matter to a reader, for repair prompts and error messages."""
    keep = {
        "queue": ["items", "front", "back", "size"], "stack": ["items", "top", "size"], "array": ["items", "size"],
        "linked_list": ["items", "head", "tail"], "binary_tree": ["root", "items", "height"],
        "graph_bfs": ["queue", "order", "current", "edges"], "graph_dfs": ["stack", "order", "current", "edges"],
        "bubble_sort": ["items", "is_sorted", "comparisons", "pass_counts"], "insertion_sort": ["items", "is_sorted", "comparisons", "pass_counts"],
        "growth": ["algo", "rows"],
    }.get(state["kind"], ["items"])
    out = {k: state.get(k) for k in keep}
    if state["kind"] == "linked_list":
        out["pointers"] = chain(state["items"])
        if state.get("current") is not None:
            out["current_node"] = state["current"]
    elif state["kind"] in GRAPH_KINDS:
        adj: dict = {}
        for u, v in state.get("edges", []):
            adj.setdefault(u, []).append(v)
            adj.setdefault(v, []).append(u)
        out["adjacency"] = {k: sorted(v, key=str) for k, v in adj.items()}
    elif state["kind"] == "binary_tree":
        out["children"] = {str(n["value"]): {"left": n["left"], "right": n["right"]} for n in state.get("nodes", [])}
    last = {k: v for k, v in state.get("last", {}).items() if k not in ("args",)}
    if last:
        out["last_op"] = last
    return out


def focus_errors(narration: str, scene: dict, is_intro: bool, ctx: dict) -> list[str]:
    """Does this scene serve the user's question? The intro leads in, the recap answers, nothing is off-topic."""
    errors = []
    if is_intro:
        words = len(narration.split())
        if words > ctx["intro_words"]:
            errors.append(f"The first scene must be short (at most about {ctx['intro_words'] - 5} words); it has {words}.")
        if ctx.get("outline") and (words < 6 or not re.search(ctx["terms"], narration, re.I | re.S)):
            errors.append("The first scene defines the structure in ONE plain sentence, naming what makes it what it is "
                          f"(for example: \"{ctx['intro']}\").")
        if ctx["intent"] != "what_is":
            if not re.search(ctx["terms"], narration, re.I | re.S):
                errors.append(f"The first scene must lead straight into the question: \"{ctx['must_answer']}\"")
            if DEFINITION.search(narration) and not ctx.get("generic"):
                errors.append("Do not open with a generic definition; this lesson answers a specific question. Lead into it.")
    elif scene.get("role") == "recap" and not re.search(ctx["terms"], narration, re.I | re.S):
        errors.append(f"The recap must restate the ANSWER to the question \"{ctx['must_answer']}\" (the key steps or ideas), "
                      "not the final numbers or unrelated facts.")
    for name, pattern in ctx.get("off_topic", []):
        if re.search(pattern, narration, re.I):
            errors.append(f"This lesson is about how to {ctx['focus_text']}. Remove the unrelated point about {name}.")
    kind, principle = scene.get("kind"), ctx.get("principle")
    if kind == "analogy" and not ANALOGY.search(narration):
        errors.append("This scene is the everyday analogy: compare the structure to something familiar ('Think of ...', 'like ...').")
    if kind == "rule":
        if principle and not all(re.search(g, narration, re.I | re.S) for g in principle["groups"]):
            errors.append(f"This scene states the key rule ({principle['name']}) in plain words. Say the rule itself.")
        missing = [v for v in ctx.get("rule_vocab", []) if not re.search(v, narration, re.I)]
        if missing:
            errors.append("Introduce the vocabulary here, each word with its plain meaning: "
                          + ", ".join(re.sub(r"\\[bw]\*?|\W", "", v) for v in missing) + ".")
    if kind == "uses" and ctx.get("uses") and not re.search(ctx["uses"], narration, re.I):
        errors.append(f"This scene says where the structure is used in real life, with concrete examples. For example: {ctx.get('uses_sentence', '')}")
    return errors


def lesson_errors(texts: list[str], scenes: list[dict], sims: list[dict], ctx: dict) -> dict[int, list[str]]:
    """Checks that need the whole lesson: jargon explained before use, a demo that ties back to the rule, and a recap
    that is not a copy of the intro. Returns scene index -> problems (each attached to the scene that must change)."""
    out: dict[int, list[str]] = {}
    for i, terms in concepts.undefined_jargon(texts).items():
        out.setdefault(i, []).append(
            f"Explain {', '.join(terms)} in plain words where it is first used (e.g. 'constant time means it is always a single quick step, "
            "no matter how many items there are'), or use plain words instead.")
    recap = next((i for i in range(len(scenes) - 1, 0, -1) if scenes[i].get("role") == "recap"), None)
    if recap is not None and texts and (concepts.overlap(texts[0], texts[recap]) > concepts.MAX_RECAP_OVERLAP or RECAP_DEFINES.search(texts[recap])):
        out.setdefault(recap, []).append("The recap repeats the intro (it defines the structure again). Give 2 or 3 takeaways in new wording, "
                                         "in 1 or 2 sentences, e.g. \"Takeaways: ...\".")
    if ctx.get("generic"):
        for i, problems in generic_lesson_errors(texts, scenes, sims, ctx).items():
            out.setdefault(i, []).extend(problems)
    for i, sc in enumerate(scenes):  # a LIST lesson's item scene says the item's full name (picture first, then the name)
        name = sc.get("item") if sc.get("line") else None
        if name and not re.search(r"\b" + r"[\s-]+".join(map(re.escape, name.lower().split())), texts[i].lower()):
            out.setdefault(i, []).append(f"Say the name \"{name}\" in this scene: picture first, then \"... is called a {name}\".")
    if ctx.get("beginner"):  # CLARITY GATE: a total beginner must understand every sentence
        import clarity
        for i, problems in clarity.lesson_clarity(texts, scenes, [s["state"]["kind"] for s in sims], ctx, [s["state"] for s in sims]).items():
            out.setdefault(i, []).extend(problems)
    for name, kind, hint in answer_missing(texts, ctx):
        i = _scene_for(scenes, kind)
        out.setdefault(i, []).append(f"The lesson never says {name}, which the answer to \"{ctx['must_answer']}\" needs. "
                                     f"Say it here, for example: \"{hint}\"")
    if ctx.get("complexity"):
        import complexity
        formula = complexity.ALGOS[ctx["complexity"]]["formula"]
        derive = [i for i, sc in enumerate(scenes) if sc.get("kind") == "derive"]
        claims = [i for i, t in enumerate(texts) if re.search(r"\bO\(", t)]
        if claims and not any(formula in texts[i] and re.search(r"\d\s*=\s*\d|=\s*\d", texts[i]) for i in derive):
            i = derive[0] if derive else claims[0]
            out.setdefault(i, []).append(f"A complexity claim needs a derivation: add up the real counts and show they equal {formula} "
                                         "with the numbers of this lesson.")
    principle = ctx.get("principle")
    if principle:
        demo = [i for i, sc in enumerate(scenes) if sc.get("ops") and sc.get("role") == "core"]
        if demo and not any(all(re.search(g, texts[i], re.I | re.S) for g in principle["groups"]) for i in demo):
            proof = next((i for i in demo if any(st["last"].get("op") in principle["proof_ops"] for st in sims[i]["steps"])), demo[-1])
            example = concepts.proof_sentence(principle, sims[proof]["steps"][-1]["last"]) if sims[proof]["steps"] else ""
            out.setdefault(proof, []).append(
                f"This step must say what it shows about the rule ({principle['name']}), using the real values"
                + (f', e.g. "{example}"' if example else "") + ".")
    return out


# A demo step must say what it shows about its point, not only what happened.
SHOWS = re.compile(r"\b(?:so|because|which means|this shows|that shows|shows that|that is why|this is why|proves?|means|"
                   r"which is why|therefore|that's why|in other words)\b", re.I)


def jargon_explained(term: str, text: str) -> bool:
    t = re.escape(term)
    return re.search(rf"\b{t}\w*\b[^.]{{0,80}}\b(?:means?|meaning|is when|is the|is a|is an|are the|that is|i\.e\.|in other words|which)\b"
                     rf"|\b{t}\w*\s*(?:\(|,\s*(?:a|an|the|which|meaning|that is)\b|:|\s-\s|—)"
                     rf"|\b(?:called|known as|named)\s+(?:an?\s+|the\s+)?[\"']?{t}", text, re.I) is not None


def generic_lesson_errors(texts: list[str], scenes: list[dict], sims: list[dict], ctx: dict) -> dict[int, list[str]]:
    """Question-driven lessons: every demo says what it shows about its point, and the question's jargon is
    explained in plain words where it is first used."""
    out: dict[int, list[str]] = {}
    by_point: dict[str, list[int]] = {}
    for i, sc in enumerate(scenes):
        if sc.get("ops") and sc.get("role") == "core" and sc.get("point_id"):
            by_point.setdefault(sc["point_id"], []).append(i)
    for pid, idx in by_point.items():
        if pid in ctx.get("evidence_points", []) and not any(SHOWS.search(texts[i]) for i in idx):
            out.setdefault(idx[-1], []).append(
                f"Say what this step SHOWS about the point \"{ctx.get('points', {}).get(pid, '')}\", e.g. \"..., so ...\" or "
                "\"... because ...\", using the real values.")
    # A growth claim beyond linear (O(n²)) needs its derivation from the real counts; O(1) / O(n) / O(log n) are shown by the run
    claims = [i for i, t in enumerate(texts) if any(re.search(r"n\s*(?:²|\^\s*2|\*\*\s*2)|n\s*\*\s*n|n\s*squared", m.group(0), re.I)
                                                     for m in BIG_O.finditer(t))]
    if claims and not any(SUM_CLAIM.search(words_to_digits(t)) or PRODUCT_CLAIM.search(words_to_digits(t)) for t in texts):
        out.setdefault(claims[0], []).append(
            "A Big-O claim needs its derivation: add up the real counts of the lesson's run and show the formula they give "
            "(e.g. 3 + 2 + 1 = 6 = n(n - 1) / 2), then say the Big-O.")
    for term in ctx.get("jargon", []):
        first = next((i for i, t in enumerate(texts) if re.search(rf"\b{re.escape(term)}", t, re.I)), None)
        if first is not None and not jargon_explained(term, texts[first]):
            out.setdefault(first, []).append(f"\"{term}\" is new to a beginner: explain it in plain words here, where it is first "
                                             f"used (e.g. \"{term} means ...\").")
    return out


def _safe(text: str) -> str:
    """A fallback sentence that can never state a wrong number: n^2 kept as a symbol, other digits dropped."""
    text = re.sub(r"\^\s*2|\*\*\s*2", "²", text or "")
    keep = []
    for sentence in re.split(r"(?<=[.!?;])\s+", words_to_digits(text).replace("~", "one")):
        if not re.search(r"(?<![\w(])\d+(?:\.\d+)?(?![\w)])", strip_formulas(sentence)):  # a sentence with a number is dropped whole
            keep.append(sentence)
    return re.sub(r"\s+([,.;:?])", r"\1", re.sub(r"\s{2,}", " ", " ".join(keep))).strip()


def _lower_first(text: str) -> str:
    return text if len(text) > 1 and text[1].isupper() else text[:1].lower() + text[1:]


def ops_summary(steps: list[dict]) -> str:
    """What the earlier ops of a scene did, grouped by kind of op (the last op is described with its state separately)."""
    parts, edges, visits = [], [], []
    for st in steps:
        last = st["last"]
        op, args = last.get("op"), last.get("args", [])
        if op == "add_edge":
            edges.append("-".join(map(str, args)))
        elif op == "visit":
            visits.append(str(last.get("removed")))
        elif op == "reset":
            continue
        elif op in ("start_bfs", "start_dfs"):
            parts.append(f"start {'BFS' if op == 'start_bfs' else 'DFS'} at {args[0]}")
        elif op in ("init", "load", "reload"):
            parts.append(f"start with {_list(args)}")
        elif op == "step":
            if not parts or parts[-1] != "compare and swap neighbours":
                parts.append("compare and swap neighbours")
        else:
            parts.append(f"{op.replace('_', ' ')} {', '.join(map(str, args))}".strip())
    if edges:
        parts.insert(0, "build the graph with edges " + ", ".join(edges))
    if visits:
        parts.append("visit " + ", ".join(visits))
    return ("First, " + "; ".join(parts) + ". ") if parts else ""


def _item_template(scene: dict, sim: dict, is_intro: bool, ctx: dict) -> str | None:
    """A LIST lesson's item scene: its plain line (which names the item), plus the values its picture shows."""
    line = scene.get("line")
    if not line:
        return None
    items = [str(x) for x in sim["state"].get("items", [])] if sim["steps"] else []
    kind = sim["state"]["kind"] if sim["steps"] else ctx.get("structure", "")
    for text in ([f"{line} Here it holds {', '.join(items[:-1]) + ' and ' + items[-1] if len(items) > 1 else items[0]}."] if items else []) + [line]:
        if not check_scene(kind, {**scene, "narration": text}, sim, is_intro, ctx):
            return text
    return None


def generic_template(scene: dict, sim: dict, is_intro: bool, ctx: dict) -> str:
    """Fallback narration for a question-driven lesson, from the scene's own answer point, with every jargon word it uses
    explained in plain words (always passes the checks)."""
    item = _item_template(scene, sim, is_intro, ctx)
    if item:
        return item
    if ctx.get("beginner"):
        plain_text = _beginner_template(scene, sim, is_intro, ctx)
        if plain_text and not check_scene(sim["state"]["kind"] if sim["steps"] else ctx.get("structure", ""),
                                          {**scene, "narration": plain_text}, sim, is_intro, ctx):
            return plain_text
    text = _generic_template(scene, sim, is_intro, ctx)
    if sim["steps"] and " This shows: " in text and check_narration(text, facts(sim)):
        text = text.split(" This shows: ")[0]  # the point's wording contradicts the true state: say only what happened
    for term, plain in ({} if scene.get("role") == "recap" or is_intro else ctx.get("jargon_plain", {})).items():
        plain = _safe(plain).rstrip(".")
        if plain and re.search(rf"\b{re.escape(term)}", text, re.I) and not jargon_explained(term, text):
            candidate = f"{text} {term[0].upper() + term[1:]} means {plain[0].lower() + plain[1:]}."
            if not check_narration(candidate, facts(sim)):
                text = candidate
    return text


def _beginner_template(scene: dict, sim: dict, is_intro: bool, ctx: dict) -> str:
    """Beginner mode: a demo step in the running analogy (plain.op_narration); an explanation made plain in code (terms
    explained first from the fixed glossary, short sentences, no filler)."""
    import clarity
    import plain
    if sim["steps"]:
        return plain.op_narration(sim) or ""
    if is_intro:
        return ctx["intro"]
    if scene.get("role") == "recap":
        return ctx.get("recap_beginner") or ctx["recap"]
    point = _safe(ctx.get("points", {}).get(scene.get("point_id"), ""))
    return clarity.plain_text(point or ctx["recap"], ctx, sim["state"].get("kind"))


def _generic_template(scene: dict, sim: dict, is_intro: bool, ctx: dict) -> str:
    point = _safe(ctx.get("points", {}).get(scene.get("point_id"), ""))
    st = sim["state"]
    if sum(s["last"].get("op") == "step" for s in sim["steps"]) > 1 and st["kind"] in SORT_KINDS:  # a run: summarise it
        passes = " + ".join(map(str, st.get("pass_counts", [])))
        done = "The list is now sorted." if st.get("is_sorted") else ""
        text = f"Run the sort: {passes} = {st['comparisons']} comparisons so far. Array is now {_list(st['items'])}. {done}".strip()
        if point and scene.get("role") == "core":
            text += f" This shows: {_lower_first(point)}" + ("" if point.endswith(".") else ".")
        return text
    if sim["steps"]:  # earlier ops named briefly, the last one described with the state it leaves (claims hold at the end)
        head = ops_summary(sim["steps"][:-1])
        text = head + (_describe_op(sim["state"]["kind"], sim["state"]) or describe(sim["state"]))
        if point and scene.get("role") == "core":
            text += f" This shows: {_lower_first(point)}" + ("" if point.endswith(".") else ".")
        return text.strip()
    if is_intro:
        return ctx["intro"]
    if scene.get("role") == "recap":
        return ctx["recap"]
    text = point or ctx["recap"]
    if scene.get("kind") == "analogy" and not ANALOGY.search(text):
        text = "Think of it like this: " + text
    return text if text.endswith((".", "?", "!")) else text + "."


def answer_missing(texts: list[str], ctx: dict) -> list[tuple[str, str, str]]:
    """ANSWER-COVERAGE GATE: the must_answer elements (name, scene kind that should say it, hint) the lesson never says.
    A lesson without them does not answer the question, however correct each sentence is."""
    text = " ".join(texts)
    return [(name, kind, hint) for name, pattern, kind, hint in ctx.get("must_cover", []) if not re.search(pattern, text, re.I | re.S)]


def _scene_for(scenes: list[dict], kind: str) -> int:
    for k in (kind, "recap"):
        hit = next((i for i, s in enumerate(scenes) if s.get("kind") == k or (k == "recap" and s.get("role") == "recap")), None)
        if hit is not None:
            return hit
    return len(scenes) - 1


# ---------------------------------------------------------------- complexity claims (every number from the counting code)
COUNT_CLAIM = re.compile(r"(?<![\w.])(\d+)\s+(?:comparisons?|steps?|checks?|visits?)\b", re.I)
ROW_CLAIM = re.compile(r"\bn\s*=\s*(\d+)\s+(?:needs|takes|makes|costs|gives)\s+(\d+)\b", re.I)
N_CLAIM = re.compile(r"\bn\s*=\s*(\d+)\b(?!\s+(?:needs|takes|makes|costs|gives)\b)", re.I)
V_CLAIM = re.compile(r"\bV\s*=\s*(\d+)")
E_CLAIM = re.compile(r"\bE\s*=\s*(\d+)")
SUM_CLAIM = re.compile(r"(?<![\w.])(\d+(?:\s*\+\s*\d+)+)\s*=\s*(\d+)")
PRODUCT_CLAIM = re.compile(r"(?<![\w.])(\d+)\s*[×x*]\s*(\d+)\s*/\s*(\d+)\s*=\s*(\d+)")
RATIO_CLAIM = re.compile(r"\babout\s+(\d+)\s+times\b", re.I)
BIG_O = re.compile(r"\bO\([^)]*\)")


def complexity_errors(narration: str, sim: dict, cf: dict, algo: str) -> list[str]:
    """Counts, totals, sums, formula values, growth-table rows, doubling ratios and Big-O, against the real counts."""
    import complexity
    a = complexity.ALGOS[algo]
    text = words_to_digits(narration)
    errors = []
    rows = cf["rows"]
    for m in COUNT_CLAIM.finditer(strip_formulas(text)):  # "n(n - 1) / 2 comparisons" is a formula, not "2 comparisons"
        k = int(m.group(1))
        if k not in cf["counts"] and k not in rows.values():
            errors.append(f"The count {m.group(0)} does not match the real run: the true counts here are {sorted(cf['counts'])}.")
    for m in ROW_CLAIM.finditer(text):
        n, k = int(m.group(1)), int(m.group(2))
        if n not in rows:
            errors.append(f"\"n = {n}\" is not a row of the growth table {sorted(rows)}.")
        elif rows[n] != k:
            errors.append(f"For n = {n} the real count is {rows[n]}, not {k}.")
    for m in N_CLAIM.finditer(text):
        n = int(m.group(1))
        if n not in cf["ns"] and n not in rows:
            errors.append(f"n = {n} is not the size of the input here (n is {sorted(cf['ns'])}).")
    final = sim["state"]
    if final.get("kind") in GRAPH_KINDS:
        for rx, truth, what in ((V_CLAIM, len(final.get("items", [])), "V (nodes)"), (E_CLAIM, final.get("edge_count"), "E (edges)")):
            for m in rx.finditer(text):
                if int(m.group(1)) != truth:
                    errors.append(f"{what} is {truth}, not {m.group(1)}.")
        m = re.search(r"V\s*\+\s*2E\s*=\s*(\d+)\s*\+\s*(\d+)", text)
        if m and (int(m.group(1)), int(m.group(2))) != (len(final.get("items", [])), 2 * final.get("edge_count", 0)):
            errors.append(f"V + 2E is {len(final.get('items', []))} + {2 * final.get('edge_count', 0)} for this graph.")
    for m in SUM_CLAIM.finditer(text):
        terms = [int(x) for x in re.findall(r"\d+", m.group(1))]
        if sum(terms) != int(m.group(2)):
            errors.append(f"{m.group(0)} is wrong: the sum is {sum(terms)}.")
        elif final.get("kind") in SORT_KINDS and len(terms) > 1 and terms not in _pass_lists(final, cf):
            errors.append(f"The passes made {final.get('pass_counts')} comparisons, so \"{m.group(1)}\" is not this run.")
    for m in PRODUCT_CLAIM.finditer(text):
        x, y, d, r = map(int, m.groups())
        if d == 0 or x * y / d != r:
            errors.append(f"{m.group(0)} is wrong.")
    for formula, fn in ((a["formula"], a.get("worst")), (a.get("best_formula"), a.get("best"))):
        if not formula or not fn or re.fullmatch(r"\w+", formula):  # "n" or "1" alone is not a checkable formula claim
            continue
        for m in re.finditer(re.escape(formula) + r"\s*=\s*(?:[\d\s×x*/+\-]+?=\s*)?(\d+)\b", text):
            if not any(fn(n) == int(m.group(1)) for n in cf["ns"]):
                errors.append(f"{formula} is {sorted({fn(n) for n in cf['ns']})} for n = {sorted(cf['ns'])}, not {m.group(1)}.")
    ratios = {a["double"]} | {round(rows[2 * n] / rows[n]) for n in rows if 2 * n in rows and rows[n]}
    for m in RATIO_CLAIM.finditer(text):
        if int(m.group(1)) not in ratios:
            errors.append(f"Doubling n multiplies the work by about {sorted(ratios)}, not {m.group(1)}.")
    allowed = [complexity.BIG_O_TEXT[a["big_o"]], complexity.BIG_O_TEXT[a["best_o"]]]
    for m in BIG_O.finditer(narration):
        if re.search(r"\b(?:not|isn't|is not|never|instead of|rather than|than)\s*(?:an?\s+|the\s+)?$", narration[: m.start()], re.I):
            continue  # "O(1), not O(n)": a claim that is rejected is not a claim (wrong-premise questions)
        if not any(re.fullmatch(p, m.group(0)) for p in allowed):
            errors.append(f"{m.group(0)} is not the complexity of {a['name']}: it is {a['big_o']} (best case {a['best_o']}).")
    return errors


def _pass_lists(final: dict, cf: dict) -> list[list[int]]:
    """Pass-count lists a narration may add up: all of this run's passes so far, and the worst case n-1, ..., 1."""
    out = [final.get("pass_counts", [])]  # the passes so far, all of them ("3 + 2 = 5 so far")
    out += [list(range(n - 1, 0, -1)) for n in cf["ns"]]  # the worst case, n - 1 + ... + 1
    return out


def check_scene(structure: str, scene: dict, sim: dict, is_intro: bool = False, ctx: dict | None = None) -> list[str]:
    """Facts + specificity + intro quality (+ focus, when the lesson's question is known). Empty list = this narration can ship."""
    narration = scene.get("narration", "") or ""
    if len(narration.strip()) < 3:  # a placeholder ("-") from a scene built in code is never shippable
        return ["This scene has no narration yet: write it, using the true state."]
    f = facts(sim)
    algo = (ctx or {}).get("complexity")
    if not algo and (ctx or {}).get("generic"):  # question-driven lessons: whatever this scene counts, its numbers are checked
        import complexity
        algo = complexity.infer_algo([sim["before"], *sim["steps"]])
    if algo:  # a complexity scene may also state counts, n, formula values and growth-table rows, all computed by code
        import complexity
        cf = complexity.facts(algo, [sim["before"], *sim["steps"]], run=sim["state"] if sim["steps"] else None)
        f["numbers"] |= cf["numbers"]
        f["sizes_ok"] = True
    if ctx and ctx.get("count_facts"):  # e.g. how many kinds a LIST answer names: counted by code
        f["numbers"] |= set(ctx["count_facts"])
    errors = check_narration(narration, f)
    if algo:
        errors += complexity_errors(narration, sim, cf, algo)
    text = words_to_digits(narration)
    for token, desc in required_facts(sim):
        if not _mentions(text, token):
            shown = (f"index {token[1]}" if token[0] == "index" else "say it in words") if isinstance(token, tuple) else str(token)
            errors.append(f"Narration must name {desc} ({shown}). True state after this step: {compact_state(sim['state'])}.")
    if ctx:
        errors += focus_errors(narration, scene, is_intro and not sim["steps"], ctx)
    if is_intro and not sim["steps"] and (ctx is None or (ctx["intent"] == "what_is" and not ctx.get("outline"))):
        terms = INTRO_TERMS.get(structure)
        if (terms and not re.search(terms, narration, re.I | re.S)) or not ANALOGY.search(narration):
            errors.append(f"The intro must say what a {structure.replace('_', ' ')} is and why it is useful, "
                          "in plain words with an everyday analogy (for example 'like ...').")
    import clarity
    rep = clarity.repeated_word(narration)
    if rep:  # "constant time time complexity" passes every fact check but is garbled at any level
        errors.append(f"A word is repeated back to back (\"{rep}\"). Say it once.")
    return sorted(set(errors))


# ---------------------------------------------------------------- templates (always pass)
def _list(xs) -> str:
    return "[" + ", ".join(map(str, xs)) + "]"


def chain(items) -> str:
    """head -> 10 -> 20 -> null"""
    return " -> ".join(["head", *map(str, items), "null"])


VARIANT_TEXT = {
    ("linked_list", "singly"): "This is a singly linked list: each node points only to the next one, and the tail points to null.",
    ("linked_list", "doubly"): "This is a doubly linked list: each node points to the next node and back to the one before.",
    ("linked_list", "circular"): "This is a circular linked list: the tail points back to the head instead of null.",
    ("queue", "simple"): "This is a simple queue: items join at the back and leave from the front.",
    ("queue", "circular"): "This is a circular queue: a fixed ring of slots, where the back wraps round to the front.",
    ("queue", "priority"): "This is a priority queue: the smallest value is served first, wherever it joined.",
    ("queue", "deque"): "This is a deque, a double-ended queue: items can join and leave at both ends.",
}


def _rows_text(cells: list[list]) -> str:
    return "; ".join(f"row {r} holds {', '.join(map(str, row)) or 'nothing'}" for r, row in enumerate(cells))


def _describe_new(st: dict) -> str | None:
    """Templates for the kinds of array and the variants. None: not one of these ops."""
    last, kind = st["last"], st["kind"]
    op = last.get("op")
    if op == "variant":
        return VARIANT_TEXT.get((kind, last["variant"]))
    if kind == "array_2d":
        if op == "grid":
            return f"This 2D array has {st['rows']} rows and {st['cols']} columns: {_rows_text(st['cells'])}."
        if op == "get2":
            return f"Row {last['row']}, column {last['col']} holds {last['value']}, read in a single step."
        if op == "set2":
            return f"Row {last['row']}, column {last['col']} changes from {last['old']} to {last['value']}."
    if kind == "jagged_array":
        if op == "row":
            return f"Row {last['row']} holds {', '.join(map(str, last['values']))}, so it is {last['length']} long."
        if op == "get2":
            return f"Row {last['row']}, column {last['col']} holds {last['value']}."
    if kind == "dyn_array":
        if op in ("init_static", "init_dynamic"):
            what = "static" if op == "init_static" else "dynamic"
            return f"A {what} array with {st['capacity']} slots holds {', '.join(map(str, st['items']))}."
        if op == "append":
            if last.get("refused"):
                return f"The static array is full, so {last['value']} is refused: it only has {st['capacity']} slots."
            if last.get("resized"):
                return (f"The array is full, so it moves to a new block with {last['new_capacity']} slots, copying "
                        f"{last['copied']} old slots across, then adds {last['value']} at index {last['index']}.")
            return f"{last['value']} goes in at index {last['index']}, and there are {st['capacity']} slots."
        if op == "get":
            return f"Index {last['index']} holds {last['value']}."
    if kind == "queue" and op == "push_front":
        return f"Push {last['value']} at the front. The front is now {st['front']}."
    if kind == "queue" and op == "pop_back":
        rest = f"The back is now {st['back']}." if st["items"] else "The deque is now empty."
        return f"Take {last['removed']} off the back. {rest}"
    return None


def _describe_op(structure: str, st: dict) -> str:
    last = st["last"]
    op = last["op"]
    new = _describe_new(st)
    if new is not None:
        return new
    if op == "init":
        vals = last["values"]
        if st["kind"] == "linked_list":
            return f"Here is our list: {chain(vals)}."
        if st["kind"] == "queue":
            return f"Start with the queue {_list(vals)}. The front is {st['front']} and the back is {st['back']}."
        if st["kind"] == "stack":
            return f"Start with the stack {_list(vals)}, bottom to top. The top is {st['top']}."
        if st["kind"] == "binary_tree":
            return f"Build the tree by inserting {', '.join(map(str, vals))}. The root is {st['root']}."
        return f"Start with the array {_list(vals)}."
    if op == "walk":
        nxt = "null" if last.get("next") is None else last["next"]
        if last.get("prev") is None:
            return (f"We can only enter a linked list at the head, so the walk starts at {last['value']}. "
                    f"{last['value']} points to {nxt}, which tells us where to go next.")
        return (f"Follow the next pointer from {last['prev']} to {last['value']}. "
                f"Now we stand on {last['value']}, and {last['value']} points to {nxt}.")
    if op == "delete_value" and last.get("found") is False:
        path = " then ".join(map(str, last.get("path", []))) or "nothing"
        return f"Try to delete {last['value']}: we check {path} and reach null without finding {last['value']}, so nothing changes."
    if op == "delete_value":
        nxt = "null" if last.get("next") is None else last["next"]
        if last.get("prev") is None:
            new_head = f"the head pointer moves to {last['next']}" if last.get("next") is not None else "the head pointer becomes null"
            rest = f"The list is now {chain(st['items'])}." if st["items"] else "The list is now empty."
            return (f"Delete {last['removed']}, the first node. There is no node before it, so {new_head}, "
                    f"and {last['removed']} is skipped. {rest}")
        return (f"Delete {last['removed']}. The node before it, {last['prev']}, now points to {nxt}, so {last['removed']} is skipped "
                f"and no longer reachable. The list is now {chain(st['items'])}.")
    if op == "insert_after":
        nxt = "null" if last.get("next") is None else last["next"]
        return (f"Insert {last['value']} after {last['prev']}: the new node points to {nxt}, then {last['prev']} points to {last['value']}. "
                f"The list is now {chain(st['items'])}.")
    if op == "search" and last.get("found") is False:
        path = " then ".join(map(str, last.get("path", []))) or "nothing"
        return f"Search for {last['value']}: check {path}, then reach null. {last['value']} is not in the list."
    if op == "append":
        return f"Append {last['value']} at index {last['index']}. Array is now {_list(st['items'])}."
    if op == "insert_at":
        return f"Insert {last['value']} at index {last['index']}; later items shift right. Array is now {_list(st['items'])}."
    if op == "delete_at":
        return f"Delete index {last['index']}, which held {last['removed']}; later items shift left. Array is now {_list(st['items'])}."
    if op == "set":
        return f"Set index {last['index']} from {last['old']} to {last['value']}. Array is now {_list(st['items'])}."
    if op == "get":
        return f"Read index {last['index']} directly. Index {last['index']} holds {last['value']}."
    if op == "enqueue":
        return f"Enqueue {last['value']} at the back. The front is {st['front']}, the back is {st['back']}."
    if op == "dequeue":
        rest = f"The front is now {st['front']}." if st["items"] else "The queue is now empty."
        return f"Dequeue {last['removed']} from the front. {rest}"
    if op == "push":
        return f"Push {last['value']} onto the top. The top is now {st['top']}."
    if op == "pop":
        rest = f"The top is now {st['top']}." if st["items"] else "The stack is now empty."
        return f"Pop {last['removed']} off the top. {rest}"
    if op == "peek":
        return f"Peek without removing anything: we see {last['value']}."
    if op == "insert_head":
        old = "null" if last.get("next") is None else last["next"]
        return f"Insert {last['value']} at the head: the new node points to {old}, and the head now points to {last['value']}. The list is now {chain(st['items'])}."
    if op == "insert_tail":
        before = f"{last['prev']} now points to {last['value']}, and " if last.get("prev") is not None else ""
        return f"Insert {last['value']} after the tail: {before}{last['value']} points to null. The list is now {chain(st['items'])}."
    if op == "search":
        return f"Walk the chain node by node: {' then '.join(map(str, last['path']))}. Found {last['value']}."
    if op == "insert_bst":
        return f"Insert {last['value']}: follow the path {' to '.join(map(str, last['path']))}, going left for smaller and right for larger."
    if op == "search_bst":
        return f"Search for {last['value']}: follow the path {' to '.join(map(str, last['path']))}."
    if op == "add_edge":
        u, v = last["edge"]
        return f"Connect {u} and {v}."
    if op == "start_bfs":
        return f"Start at {last['value']} and put it in the queue. Queue is now {_list(st['queue'])}."
    if op == "start_dfs":
        return f"Start at {last['value']} and push it onto the stack. Stack is now {_list(st['stack'])}."
    if op == "visit" and st["kind"] == "graph_dfs":
        new = last.get("pushed") or []
        found = f"Push its unvisited neighbours {', '.join(map(str, new))}." if new else "It has no unvisited neighbours, so we backtrack."
        s = f"Stack is now {_list(st['stack'])}." if st["stack"] else "The stack is now empty, so the search is finished."
        return f"Visit {last['removed']}. {found} {s}"
    if op in ("reload", "reset"):
        return ""
    if op == "scan":
        return (f"Compare index {last['index']}, which holds {last['value']}, with {last['target']}: "
                + ("found." if last["found"] else "not a match."))
    if op in COUNTED_OPS:
        return "Counted for real: " + ", ".join(f"n = {r['n']} needs {r['count']}" for r in st.get("rows", [])) + "."
    if op == "visit":
        new = last["enqueued"]
        found = f"Enqueue its unvisited neighbours {', '.join(map(str, new))}." if new else "It has no unvisited neighbours."
        q = f"Queue is now {_list(st['queue'])}." if st["queue"] else "The queue is now empty, so the search is finished."
        return f"Visit {last['removed']}. {found} {q}"
    if op == "load":
        return f"Load the array {_list(last['values'])}."
    if op in ("compare", "step", "swap"):
        if last.get("finished"):
            return f"Array is now {_list(st['items'])}, already sorted, so this step changes nothing."
        a, b = last["values"]
        if last.get("swapped"):
            return f"Compare {a} and {b}. {a} is bigger, so swap. Array is now {_list(st['items'])}."
        return f"Compare {a} and {b}. They are in order, so they stay in place. Array is now {_list(st['items'])}."
    return ""


def describe(state: dict) -> str:
    """One sentence with the facts that matter for this structure (never 'size' for graphs or trees)."""
    kind, items = state["kind"], state.get("items", [])
    if not items:
        return ""
    if kind == "queue":
        return f"The front is {state['front']} and the back is {state['back']}."
    if kind == "stack":
        return f"The top is {state['top']}."
    if kind in ("array", *SORT_KINDS):
        return f"Array is now {_list(items)}."
    if kind == "linked_list":
        return f"The list is now {chain(items)}."
    if kind == "binary_tree":
        return f"The root is {state['root']}."
    if kind in ("array_2d", "jagged_array"):
        return f"Now {_rows_text(state['cells'])}." if state.get("cells") else ""
    if kind == "dyn_array":
        return f"It holds {', '.join(map(str, items))} in {state['capacity']} slots."
    if kind in GRAPH_KINDS:
        return f"Visit order: {', '.join(map(str, state['order']))}." if state.get("order") else ""
    return ""


def template_narration(structure: str, scene: dict, sim: dict, is_intro: bool = False, ctx: dict | None = None, k: int = 0) -> str:
    """Deterministic narration built only from the true state. Always passes check_scene."""
    if ctx and ctx.get("complexity"):
        import complexity
        return complexity.narrate(ctx["complexity"], scene, sim)
    if ctx and ctx.get("generic"):
        return generic_template(scene, sim, is_intro, ctx)
    if not sim["steps"] and ctx:
        role = scene.get("role")
        if is_intro:
            return ctx["intro"]
        if role == "recap":
            return ctx["recap"]
        if scene.get("kind") in ("analogy", "rule") and ctx.get(scene["kind"]):
            return ctx[scene["kind"]]
        if scene.get("kind") == "uses" and ctx.get("uses_sentence"):
            return ctx["uses_sentence"]
        pool = (ctx["edges"] if role == "edge_case" else ctx["details"]) or ctx["details"] or [ctx["recap"]]
        return pool[k % len(pool)]
    if not sim["steps"]:
        defs = CONCEPT.get(structure, ["", ""])
        return defs[0] if is_intro else " ".join(p for p in (defs[1], describe(sim["state"])) if p)
    if sim["steps"][-1]["last"].get("op") == "add_edge":
        edges = [f"{s['last']['edge'][0]}-{s['last']['edge'][1]}" for s in sim["steps"] if s["last"].get("op") == "add_edge"]
        return f"Build the graph with edges {', '.join(edges)}."
    text = " ".join(p for p in (_describe_op(structure, st) for st in sim["steps"]) if p)
    principle = (ctx or {}).get("principle")
    if principle and any(st["last"].get("op") in principle["proof_ops"] for st in sim["steps"]):
        proof = concepts.proof_sentence(principle, sim["steps"][-1]["last"])
        if proof and not all(re.search(g, text, re.I | re.S) for g in principle["groups"]):
            text = f"{text} {proof}"
    return text


# ---------------------------------------------------------------- verification loop
Fixer = Callable[[dict, dict, list[str]], str]
BatchFixer = Callable[[list[dict]], dict[int, str]]  # items: {index, scene, sim, errors} -> {index: narration}


def verify_scenes(structure: str, scenes: list[dict], sims: list[dict], batch_fixer: BatchFixer | None = None,
                  max_rounds: int = 2, intro_index: int | None = 0, ctx: dict | None = None) -> list[dict]:
    """Check every scene; send ALL failing scenes (with their true states) to the LLM in one call per round."""
    texts = [s.get("narration", "") or "" for s in scenes]
    sources = ["template" if ctx and ctx.get("complexity") else "llm"] * len(scenes)  # complexity lessons are written by code
    is_intro = [i == intro_index and not sims[i]["steps"] for i in range(len(scenes))]
    kinds = [structure if is_intro[i] else sims[i]["state"]["kind"] for i in range(len(scenes))]

    def check(i: int) -> list[str]:
        return check_scene(kinds[i], {**scenes[i], "narration": texts[i]}, sims[i], is_intro[i], ctx)

    def check_all() -> list[list[str]]:
        errs = [check(i) for i in range(len(scenes))]
        if ctx:
            for i, extra in lesson_errors(texts, scenes, sims, ctx).items():
                errs[i] = sorted(set(errs[i] + extra))
        return errs

    errors = check_all()
    for _ in range(max_rounds if batch_fixer else 0):
        failing = [i for i, e in enumerate(errors) if e]
        if not failing:
            break
        try:
            fixed = batch_fixer([{"index": i, "scene": {**scenes[i], "narration": texts[i]}, "sim": sims[i], "errors": errors[i],
                                  "intro": is_intro[i], "structure": kinds[i]} for i in failing])
        except Exception:  # LLM down: fall through to templates
            break
        for i in failing:
            if isinstance(fixed.get(i), str) and fixed[i].strip():
                texts[i] = fixed[i].strip()
                sources[i] = "llm-fixed"
        errors = check_all()
    if ctx and ctx.get("beginner"):  # a scene that only missed a definition keeps its words, with the plain definition first
        import clarity
        old = list(texts)
        for i, e in enumerate(errors):
            if e:
                texts[i] = clarity.define_first(texts[i], e, ctx, kinds[i])
        if texts != old:
            errors = check_all()
            for i, e in enumerate(errors):
                if e and texts[i] != old[i]:
                    texts[i] = old[i]
            errors = check_all()
    for i, (scene, sim) in enumerate(zip(scenes, sims)):
        if errors[i]:
            log.info("verifier: scene %d falls back to a template: %s", i, "; ".join(errors[i])[:400])
            texts[i] = template_narration(kinds[i], scene, sim, is_intro[i], ctx, i)
            sources[i] = "template"
    if ctx:  # a whole-lesson problem can remain only if the templates disagree with an LLM scene elsewhere: replace that scene too
        for i, extra in lesson_errors(texts, scenes, sims, ctx).items():
            texts[i] = template_narration(kinds[i], scenes[i], sims[i], is_intro[i], ctx, i)
            sources[i] = "template"
    for i, (scene, sim) in enumerate(zip(scenes, sims)):
        if sources[i] == "template":
            left = check(i)
            assert not left, f"template narration must always verify: {left}"
    out = []
    for i, (scene, sim) in enumerate(zip(scenes, sims)):
        out.append({**scene, "narration": texts[i], "before": sim["before"], "steps": sim["steps"], "state": sim["state"],
                    "verified": True, "narration_source": sources[i]})
    return out


def batch_from_single(fixer: Fixer) -> BatchFixer:
    """Adapt a one-scene fixer (scene, sim, errors) -> text into a batch fixer."""
    return lambda items: {it["index"]: fixer(it["scene"], it["sim"], it["errors"]) for it in items}


def verify_plan(plan: dict, fixer: Fixer | None = None, max_fixes: int = 2) -> list[dict]:
    """Simulate and verify every scene (scene 1 is treated as the intro). Raises OpError on impossible ops."""
    structure = plan["structure"]
    sims = simulate(structure, plan["scenes"])
    return verify_scenes(structure, plan["scenes"], sims, batch_from_single(fixer) if fixer else None, max_fixes)


def verify_scene(structure: str, scene: dict, sim: dict, fixer: Fixer | None = None, max_fixes: int = 2, is_intro: bool = False) -> dict:
    return verify_scenes(structure, [scene], [sim], batch_from_single(fixer) if fixer else None, max_fixes,
                         intro_index=0 if is_intro else None)[0]
