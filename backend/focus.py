"""What did the user actually ask? Question analysis, scene roles and plan shaping.

    analyze("how do I delete a node from the middle of a linked list")
      -> structure linked_list, intent how_op, focus delete (middle),
         must_answer "How do you remove a node from the middle of a linked list without breaking the chain?",
         core_ops [walk, delete_value]

Everything after the analysis is organised around the focus:
  * every scene has a role: setup | core | edge_case | recap
  * setup is at most 2 scenes (the intro + ONE `init` scene that builds the data), unless the question is about inserting
  * the core ops are guaranteed in code (e.g. a hop-by-hop walk to the node before the target, then the delete)
  * the intro leads into the question, the recap restates the answer, and unrelated facts are rejected
  * required concepts and the quiz come from the focus, not from a fixed per-structure checklist
"""
from __future__ import annotations

import copy
import re
from dataclasses import asdict, dataclass, field

import complexity
from concepts import GLOSSARY, USES, WHAT_IS, WHAT_IS_DEMO, WHAT_IS_POINTS, principle_for
from structures import OpError, make

INTENTS = ("what_is", "how_op", "compare", "trace_on_input", "why", "complexity")
ROLES = ("setup", "core", "edge_case", "recap")
PLACEHOLDER = "-"  # narration of scenes built in code; always fails the checks, so the batched repair writes it
MIN_CORE_SHARE = 0.5


class UnsupportedTopic(ValueError):
    """The topic (or the operation asked about) is not something Structura can run for real."""


NAMES = {"array": "an array", "queue": "a queue", "stack": "a stack", "linked_list": "a linked list",
         "binary_tree": "a binary search tree", "graph_bfs": "a graph", "bubble_sort": "bubble sort"}

# ---------------------------------------------------------------- 1. question analysis (deterministic)
STRUCT_PATTERNS = [  # checked in order; each match is removed so "linked list" never also counts as "list"
    ("linked_list", r"linked[\s-]*lists?|\bsingly\b"),
    ("binary_tree", r"\bbsts?\b|binary\s+(?:search\s+)?trees?|\btrees?\b"),
    ("graph_bfs", r"\bbfs\b|breadth[\s-]*first|\bgraphs?\b"),
    ("bubble_sort", r"\bbubble\b|\bsort(?:ing)?\s+(?:\[|these|this|the|my|\d)|^\s*sort\b"),
    ("queue", r"\bqueues?\b|\bfifo\b|\benqueu\w*|\bdequeu\w*"),
    ("stack", r"\bstacks?\b|\blifo\b"),
    ("array", r"\barrays?\b|\blists?\b|\blinear\s+search\w*|\bsequential\s+search\w*"),
]
UNSUPPORTED_WORDS = re.compile(r"\bhash|\bheaps?\b|\btries\b|\btrie\b|\bavl\b|red[\s-]*black|\bdfs\b|depth[\s-]*first|quick\s*sort|"
                               r"merge\s*sort|insertion\s+sort|selection\s+sort|dijkstra|doubly|circular|\bdeque\b", re.I)
VERBS = [  # generic focus verbs, checked in order
    ("delete", r"\bdelet\w*|\bremov\w*|\beras\w*|\bpop(?:s|ped|ping)?\b|\bdequeu\w*"),
    ("insert", r"\binsert\w*|\badd(?:s|ed|ing)?\b|\bpush(?:es|ed|ing)?\b|\benqueu\w*|\bappend\w*|\bprepend\w*"),
    ("search", r"\bsearch\w*|\bfind\w*|\blook(?:s|ing)?\s+(?:up|for)\b|\bcontains?\b|\blookup\b"),
    ("peek", r"\bpeek\w*"),
    ("traverse", r"\btravers\w*|\bwalk\w*|\biterat\w*|\bloop\w*\s+(?:through|over)|\bprint\w*\s+(?:all|every|each|the)"),
    ("access", r"\baccess\w*|\bget(?:ting)?\s+(?:an?|the)\s+(?:item|element|value)|\bread(?:ing)?\s+(?:an?|the)\b|\bby index\b"),
    ("update", r"\bupdat\w*|\breplac\w*|\bchang\w*\s+(?:an?\s+|the\s+)?(?:value|item|element)|\bset\s+(?:an?|the)\s+(?:value|item|index)"),
    ("reverse", r"\brevers\w*"),
]
COMPARE_WORDS = re.compile(r"\bdifferen\w*|\bcompar\w*|\bvs\.?\b|\bversus\b|\binstead of\b|\bbetter than\b|\bor an?\b", re.I)
WHY_WORDS = re.compile(r"^\s*why\b|\bwhy (?:do|does|is|are|would|should|use|we)\b", re.I)
WHAT_WORDS = re.compile(r"\bwhat\s+(?:is|are)\b|\bdefin\w*|\bexplain\b|\bintro\w*", re.I)
POSITIONS = [("middle", r"\bmiddle\b|\bbetween\b|\bcent(?:er|re)\b|\bafter\b"),
             ("head", r"\bhead\b|\bfront\b|\bbeginning\b|\bstart of\b|\bfirst (?:node|element|item)\b"),
             ("tail", r"\btail\b|\bend\b|\blast (?:node|element|item)\b|\bback\b")]

# Which focus each structure supports, and the ops that demonstrate it.
VERB_ALIAS = {
    "linked_list": {"access": "traverse"},
    "queue": {"access": "peek"},
    "stack": {"access": "peek"},
    "array": {"traverse": "access"},
}


def core_ops_for(structure: str, focus: str, position: str | None) -> list[str] | None:
    table = {
        "linked_list": {"what_is": ["walk"], "delete": ["walk", "delete_value"],
                        "search": ["walk", "search"], "traverse": ["walk"], "compare": ["get", "insert_at", "walk", "insert_after"],
                        "insert": {"head": ["insert_head"], "tail": ["walk", "insert_tail"], "middle": ["walk", "insert_after"]}.get(position or "head")},
        "array": {"what_is": ["get", "insert_at"], "insert": ["append"] if position == "tail" else ["insert_at"],
                  "delete": ["delete_at"], "access": ["get"], "update": ["set"]},
        "queue": {"what_is": ["enqueue", "dequeue"], "insert": ["enqueue"], "delete": ["dequeue"], "peek": ["peek"]},
        "stack": {"what_is": ["push", "pop"], "insert": ["push"], "delete": ["pop"], "peek": ["peek"]},
        "binary_tree": {"what_is": ["insert_bst", "search_bst"], "insert": ["insert_bst"], "search": ["search_bst"]},
        "graph_bfs": {"bfs": ["start_bfs", "visit"]},
        "bubble_sort": {"sort": ["step"]},
    }
    return table.get(structure, {}).get(focus)


@dataclass
class Analysis:
    structure: str
    intent: str
    focus: str
    position: str | None
    focus_text: str
    must_answer: str
    core_ops: list[str] = field(default_factory=list)
    compare_with: str | None = None
    algorithm: str | None = None  # complexity questions: what is counted (bubble_sort, linear_search, bfs, stack_push, ...)

    def to_dict(self) -> dict:
        return asdict(self)


def detect_structures(text: str) -> list[str]:
    if UNSUPPORTED_WORDS.search(text):
        return []
    found, rest = [], text.lower()
    for name, pat in STRUCT_PATTERNS:
        if re.search(pat, rest, re.I):
            found.append(name)
            rest = re.sub(pat, " ", rest, flags=re.I)
    return found


def _verb(text: str) -> str | None:
    hits = [(m.start(), name) for name, pat in VERBS for m in [re.search(pat, text, re.I)] if m]
    return min(hits)[1] if hits else None


def _position(text: str) -> str | None:
    hits = [(m.start(), name) for name, pat in POSITIONS for m in [re.search(pat, text, re.I)] if m]
    return min(hits)[1] if hits else None


def analyze(topic: str, given=None, structure: str | None = None) -> Analysis | None:
    """Structure, intent, focus, must_answer and core ops of the user's question. None if no structure is recognised
    (the LLM then picks one and this is called again with `structure`)."""
    text = topic.strip()
    asks_complexity = bool(complexity.COMPLEXITY_WORDS.search(text))
    if asks_complexity and UNSUPPORTED_WORDS.search(text):
        raise UnsupportedTopic(COMPLEXITY_SUPPORTED)
    found = detect_structures(text)
    if structure and structure not in found and not UNSUPPORTED_WORDS.search(text):
        found = [structure] + found
    if given is not None and getattr(given, "edges", None):
        found = ["graph_bfs"]
    if not found and asks_complexity and re.search(r"\bpush(?:es|ed|ing)?\b|\bpop(?:s|ped|ping)?\b", text, re.I):
        found = ["stack"]  # "time complexity of pop": push and pop are stack operations
    if not found:
        return None
    s = found[0]
    has_data = bool(given is not None and (getattr(given, "edges", None) or getattr(given, "values", None)))

    if len(found) >= 2 and ({found[0], found[1]} == {"array", "linked_list"}) and (COMPARE_WORDS.search(text) or WHY_WORDS.search(text)):
        return _make("linked_list", "compare", "compare", None, compare_with="array")
    if len(found) >= 2 and COMPARE_WORDS.search(text):
        raise UnsupportedTopic("Structura can compare arrays and linked lists so far. Try \"difference between an array and a linked list\".")
    if asks_complexity:  # "what is the time complexity of bubble sort", "why is bubble sort n squared", "how fast is push"
        verb = _verb(re.sub(r"binary\s+search\s+trees?|breadth[\s-]*first\s+search|linear\s+search|sequential\s+search", " ", text, flags=re.I))
        verb = VERB_ALIAS.get(s, {}).get(verb, verb)
        algo = complexity.algorithm_for(s, verb, text)
        if algo is None:
            raise UnsupportedTopic(COMPLEXITY_SUPPORTED)
        spec = complexity.catalogue(algo)
        return Analysis(structure=complexity.ALGOS[algo]["structure"], intent="complexity", focus="complexity", position=None,
                        focus_text=spec["text"], must_answer=spec["answer"], core_ops=[], algorithm=algo)

    if s in ("graph_bfs", "bubble_sort"):
        f = "bfs" if s == "graph_bfs" else "sort"
        intent = "trace_on_input" if has_data else "what_is" if WHAT_WORDS.search(text) else "how_op"
        return _make(s, intent, f, None)

    # "binary SEARCH tree" / "breadth first SEARCH" are names, not the verb "search"
    verb = _verb(re.sub(r"binary\s+search\s+trees?|breadth[\s-]*first\s+search", " ", text, flags=re.I))
    verb = VERB_ALIAS.get(s, {}).get(verb, verb)
    position = _position(text) if s in ("linked_list", "array") and verb in ("insert", "delete") else None
    if verb and s == "linked_list" and verb in ("delete", "insert") and position is None:
        position = "middle" if verb == "delete" else "head"
    if verb and core_ops_for(s, verb, position) is None:
        can = [f for f in ("insert", "delete", "search", "traverse", "access", "update", "peek") if core_ops_for(s, f, "head")]
        raise UnsupportedTopic(f"Structura cannot run \"{verb}\" on {NAMES[s]} yet. For {NAMES[s]} it can show: what it is, "
                               + ", ".join(can) + ".")
    if WHY_WORDS.search(text):
        intent = "why"
    elif has_data:
        intent = "trace_on_input"
    elif verb:
        intent = "how_op"
    else:
        intent = "what_is"
    return _make(s, intent, verb or "what_is", position)


COMPLEXITY_SUPPORTED = ("Structura can explain the time complexity of bubble sort, linear search, searching a linked list, breadth first "
                        "search, and stack, queue, array and linked list operations so far. Try \"what is the time complexity of bubble sort\".")


def _make(s: str, intent: str, focus: str, position: str | None, compare_with: str | None = None) -> Analysis:
    spec = catalogue(s, focus, position)
    return Analysis(structure=s, intent=intent, focus=focus, position=position, focus_text=spec["text"],
                    must_answer=spec["answer"], core_ops=core_ops_for(s, focus, position) or [], compare_with=compare_with)


# ---------------------------------------------------------------- 2. what a lesson about each focus must say
# Sentences here are spoken as-is when the LLM's narration fails, so they contain NO numbers (they must verify on any state).
OFF_TOPIC = {
    "how fast inserting at the head is": r"\binsert\w*\b[^.]{0,40}\bhead\b[^.]{0,40}\b(?:instant\w*|fast|quick\w*|constant|O\(1\)|cheap)\b"
                                         r"|\b(?:instant\w*|fast|quick\w*|constant time)\b[^.]{0,30}\binsert\w*[^.]{0,20}\bhead\b",
    "how long searching takes": r"\bsearch\w*\b[^.]{0,40}\b(?:slow\w*|linear|O\(n\)|every node|proportional)",
}

_LL_EDGE_HEAD = "Edge case: if the target is the head, there is no node before it, so we simply move the head pointer to the second node."
_LL_EDGE_TAIL = "Edge case: if the target is the tail, the node before it becomes the new tail and its next pointer is set to null."
_LL_EDGE_MISSING = "Edge case: if the value is not in the list, the walk reaches null without finding it, so nothing changes."


def catalogue(s: str, focus: str, position: str | None = None) -> dict:
    """text, answer (must_answer), terms (regex the intro and recap must hit), intro, recap, concepts
    [(name, regex, sentence, role)], details (core sentences), edges, edges_combined, off_topic names."""
    from verifier import CONCEPT  # definitions + analogies used for what_is intros

    base = {"edges": [], "edges_combined": None, "off_topic": [], "details": [], "concepts": []}
    key = (s, focus)
    if key == ("linked_list", "what_is"):
        return {**base, "text": "what a linked list is", "answer": "What is a linked list, and how do its nodes and pointers work?",
                "terms": r"\bnodes?\b|\bpointers?\b|\bnext\b", "intro": CONCEPT[s][0],
                "recap": "A linked list is a chain of nodes: each node holds a value and a next pointer, the head points to the first node, "
                         "and the last node points to null. To reach a node you walk from the head, but inserting or deleting only rewires pointers.",
                "concepts": [("a node holds a value and a next pointer", r"\bnodes?\b[^.]*\b(?:value|next|pointer)",
                              "Each node holds a value and a next pointer that says which node comes after it.", "core"),
                             ("the head is the entry point", r"\bhead\b",
                              "The head is the entry point: it points to the first node, and every walk starts there.", "core"),
                             ("the last node points to null", r"\bnull\b",
                              "The last node is the tail, and its next pointer is null, which marks the end of the list.", "core"),
                             ("no jumping by index", r"\bwalk\w*|\bfollow\w*|\bno index\b|\bcannot jump\b|\bcan't jump\b",
                              "There is no index to jump to: to reach a node deep in the list you follow the next pointers from the head, node after node.", "core")],
                "details": ["Nodes do not sit side by side in memory; only the next pointers hold the chain together.",
                            "There is no index to jump to, so reaching a node means following next pointers from the head, node after node."]}
    if key == ("linked_list", "delete"):
        text = {"middle": "delete a node from the middle of a linked list", "head": "delete the head node of a linked list",
                "tail": "delete the last node of a linked list"}[position or "middle"]
        answer = {"middle": "How do you remove a node from the middle of a linked list without breaking the chain?",
                  "head": "How do you delete the first node of a linked list?",
                  "tail": "How do you delete the last node of a linked list?"}[position or "middle"]
        intro = {"middle": "How do we delete a node from the middle of a linked list without breaking the chain? Let's watch every pointer change.",
                 "head": "How do we delete the first node of a linked list? Let's watch the head pointer move.",
                 "tail": "How do we delete the last node of a linked list? Let's walk to it and watch the pointers change."}[position or "middle"]
        return {**base, "text": text, "answer": answer, "terms": r"\bdelet\w*|\bremov\w*", "intro": intro,
                "recap": "To delete a node: walk to the node before it, then point its next pointer past the target, so the target is skipped.",
                "concepts": [("find the node before the target", r"\bprevious\b|\bbefore (?:it|the target|the node)\b|\bnode before\b",
                              "We stop at the node before the target, because that node holds the next pointer we must change.", "core"),
                             ("rewire its next pointer", r"\bpoint\w*", "Changing where that node's next pointer leads is what removes the target from the chain.", "core"),
                             ("the removed node is skipped", r"\bskip\w*|\bbypass\w*|no longer (?:reachable|linked|part)|\bunreachable\b",
                              "Once nothing points to the target, it is skipped and no longer reachable from the head.", "core"),
                             ("edge case: deleting the head", r"\b(?:delet|remov)\w*\s+(?:the\s+)?(?:head|first node)\b|\btarget is the head\b|\bthe head is (?:the target|deleted|removed)\b",
                              _LL_EDGE_HEAD, "edge_case"),
                             ("edge case: deleting the tail", r"\btail\b|\blast node\b", _LL_EDGE_TAIL, "edge_case"),
                             ("edge case: a value that is not there", r"\bnot (?:in|there|found)\b|\bmissing\b|\bdoes(?:n't| not) exist", _LL_EDGE_MISSING, "edge_case")],
                "details": ["We stop at the node before the target, not at the target itself, because only the previous node holds the next pointer we need to change.",
                            "A singly linked list has no backward pointers, so while walking we always look at the node ahead to see if it is the target.",
                            "Changing that single pointer is the whole deletion: no other node moves or changes.",
                            "We must find the previous node by walking, because a node does not know which node points to it."],
                "edges": [_LL_EDGE_HEAD, _LL_EDGE_TAIL, _LL_EDGE_MISSING],
                "edges_combined": "Edge cases: deleting the head just moves the head pointer to the second node, deleting the tail makes the node before it "
                                  "point to null, and a missing value means the walk reaches null and nothing changes.",
                "off_topic": ["how fast inserting at the head is", "how long searching takes"]}
    if key == ("linked_list", "insert"):
        p = position or "head"
        where = {"head": "at the head", "tail": "at the tail", "middle": "in the middle"}[p]
        intro = {"head": "How do we insert a new node at the head of a linked list? Let's watch the pointers change.",
                 "tail": "How do we insert a new node at the tail of a linked list? Let's walk to the end and attach it.",
                 "middle": "How do we insert a new node in the middle of a linked list? Let's walk there and rewire the pointers."}[p]
        concepts = [("the new node points to what follows it", r"\bnew node\b[^.]*\bpoint\w*|\bpoint\w*[^.]*\bnew node\b",
                     "First the new node's next pointer is set to the node that should come after it, so the rest of the list is never lost.", "core")]
        if p == "head":
            concepts.append(("the head moves to the new node", r"\bhead\b", "Then the head pointer moves to the new node, which becomes the first node.", "core"))
        else:
            concepts.append(("the node before it points to the new node", r"\bbefore\b|\bprevious\b|\btail\b",
                             "Then the node before it changes its next pointer to the new node.", "core"))
        return {**base, "text": f"insert a node {where} of a linked list", "answer": f"How do you insert a new node {where} of a linked list?",
                "terms": r"\binsert\w*|\badd\w*", "intro": intro,
                "recap": "To insert a node, first point the new node at the node that should follow it, then point the node before it, or the head, at the new node. "
                         "In this order the rest of the list is never lost.",
                "concepts": concepts,
                "details": ["The order matters: if we changed the earlier pointer first, the rest of the list would be lost.",
                            "No other node moves; inserting only rewires a couple of pointers."],
                "edges": ["Edge case: inserting into an empty list makes the new node both the head and the tail, and its next pointer is null."],
                "off_topic": ["how long searching takes"]}
    if key in (("linked_list", "search"), ("linked_list", "traverse")):
        search = focus == "search"
        return {**base, "text": "search a linked list for a value" if search else "walk through every node of a linked list",
                "answer": "How do you search a linked list for a value?" if search else "How do you walk through every node of a linked list?",
                "terms": r"\bsearch\w*|\bfind\w*|\blook\w* for" if search else r"\bwalk\w*|\btravers\w*|\bfollow\w*|\bvisit\w*",
                "intro": "How do we search a linked list for a value? Let's start at the head and check the nodes in order." if search
                else "How do we walk through every node of a linked list? Let's follow the pointers from the head to null.",
                "recap": "To search a linked list, start at the head and compare each node with the target, following next pointers until you find it or reach null." if search
                else "To walk a linked list, start at the head and keep following each node's next pointer until it is null; that visits every node in order.",
                "concepts": [("start at the head", r"\bhead\b", "Every walk starts at the head, because the head is the only node we can reach directly.", "core"),
                             *([("compare each node", r"\bcompar\w*|\bcheck\w*|\bmatch\w*|\bequal\w*", "At each node we compare its value with the target.", "core")] if search else []),
                             ("follow the next pointers", r"\bnext\b|\bpoint\w*|\bfollow\w*", "To move on, we follow the next pointer to the following node.", "core"),
                             ("stop at null", r"\bnull\b|\bnot (?:in|there|found)\b",
                              "Edge case: if the value is not in the list, we check every node and reach null, so the search reports that it is not found." if search
                              else "The walk ends when a next pointer is null, because there is no node after the tail.", "edge_case" if search else "core")],
                "details": ["At each node we ask: is this value the target? If not, its next pointer tells us where to look next.",
                            "There is no index to jump to, so the only way through a linked list is to follow the next pointers node after node.",
                            "In the worst case we check every node, so a search takes longer as the list grows." if search
                            else "Every node is visited in order, because each node only knows the node right after it."],
                "edges": ["Edge case: if the list is empty, there is no first node, so the walk stops at once."],
                "off_topic": ["how fast inserting at the head is"]}
    if key == ("linked_list", "compare"):
        return {**base, "text": "how an array and a linked list differ", "answer": "What is the difference between an array and a linked list?",
                "terms": r"^(?=[\s\S]*\barrays?\b)(?=[\s\S]*\blinked lists?\b)",
                "intro": "Arrays and linked lists can hold the same values, so what is the difference? Let's put them side by side.",
                "recap": "An array jumps straight to any index but shifts items on insert; a linked list must walk from the head but inserts by rewiring pointers.",
                "concepts": [("arrays jump straight to an index", r"\binstant\w*|\bdirectly\b|\bjump\w* straight\b|\bstraight to\b|\bconstant time\b",
                              "An array can jump straight to any index, because its slots sit side by side in memory.", "core"),
                             ("linked lists must walk", r"\bwalk\w*|\bfollow\w*", "A linked list has no index, so it must walk from the head, node after node.", "core"),
                             ("array inserts shift items", r"\bshift\w*", "Inserting into the middle of an array shifts every later item over by a slot.", "core"),
                             ("linked list inserts rewire pointers", r"\bpoint\w*|\brewir\w*",
                              "Inserting into a linked list only changes a couple of pointers; no other node moves.", "core")],
                "details": ["Array items sit side by side in memory, which is why the computer can jump straight to any index.",
                            "Linked list nodes can live anywhere in memory; only the next pointers hold the chain together."]}
    if s == "array":
        what = {**base, "text": "what an array is", "answer": "What is an array, and why is reading by index fast?", "terms": r"\bindex\w*|\bslots?\b",
                "intro": CONCEPT[s][0],
                "recap": "An array is a row of numbered slots: indexes start at 0, reading any index is instant, and inserting or deleting in the middle shifts the later items.",
                "concepts": [("index starts at 0", r"\bindex(?:es)?\s+(?:start|begin)s?\s+at\s+(?:0|zero)\b|\bindex\s+(?:0|zero)\b",
                              "Indexes start at 0, so the first item is always at index 0.", "core"),
                             ("fixed slots", r"\bfixed\b|\bslots?\b|\bside by side\b|\bcontiguous\b", "An array is a fixed row of slots stored side by side in memory.", "core"),
                             ("instant access by index", r"\binstant\w*|\bconstant time\b|\bdirectly\b|\bjump(?:s)? straight\b|\bstraight to\b",
                              "Reading any index is instant, because the computer can jump straight to that slot.", "core"),
                             ("inserts shift items", r"\bshift", "Inserting or deleting in the middle is slower, because every later item has to shift over to make room.", "core")],
                "details": [CONCEPT[s][1], "Because the slots are numbered, the computer finds any slot with simple arithmetic instead of searching."]}
        specs = {
            "what_is": what,
            "insert": {**base, "text": "insert a value into an array", "answer": "How do you insert a value into the middle of an array?",
                       "terms": r"\binsert\w*|\badd\w*|\bappend\w*",
                       "intro": "How do we insert a value into the middle of an array? Let's watch every later item shift over.",
                       "recap": "To insert into an array at an index, every item from that index onward shifts right by a slot to make room, then the new value goes "
                                "into the free slot. Appending at the end needs no shifting.",
                       "concepts": [("later items shift right", r"\bshift\w*", "Every item from that index onward shifts right by a slot to make room.", "core"),
                                    ("the index decides the slot", r"\bindex\w*", "We choose the index where the new value should land.", "core")],
                       "details": ["The more items come after the insert position, the more items have to shift, so inserting near the front is the slowest.",
                                   "Appending at the end is fast, because no item has to move."],
                       "edges": ["Edge case: inserting at the end is just an append, and inserting past the end is not allowed."]},
            "delete": {**base, "text": "delete a value from an array", "answer": "How do you delete a value from the middle of an array?",
                       "terms": r"\bdelet\w*|\bremov\w*",
                       "intro": "How do we delete a value from the middle of an array? Let's watch the later items shift back to close the gap.",
                       "recap": "To delete from an array at an index, the value is taken out and every later item shifts left by a slot to close the gap, so the array never has holes.",
                       "concepts": [("later items shift left", r"\bshift\w*", "Every later item shifts left by a slot to close the gap.", "core"),
                                    ("the index decides the slot", r"\bindex\w*", "We name the index of the value we want to delete.", "core")],
                       "details": ["Arrays keep their items side by side, so a gap is never left behind: later items always move to fill it."],
                       "edges": ["Edge case: deleting the last item needs no shifting at all."]},
            "access": {**base, "text": "read a value from an array by index", "answer": "How do you read the value at a given index of an array?",
                       "terms": r"\bindex\w*|\bread\w*|\baccess\w*",
                       "intro": "How do we read the value at a given index of an array? Let's jump straight there.",
                       "recap": "To read an array, you name the index and the computer jumps straight to that slot, so every read is instant no matter how long the array is.",
                       "concepts": [what["concepts"][0], what["concepts"][2]],
                       "details": ["The computer works out where a slot lives from its index with simple arithmetic, so it never looks through other items."],
                       "edges": ["Edge case: asking for an index past the end is an error, because that slot does not exist."]},
            "update": {**base, "text": "change a value stored in an array", "answer": "How do you change a value stored in an array?",
                       "terms": r"\bset\b|\bupdat\w*|\bchang\w*|\breplac\w*|\boverwrit\w*",
                       "intro": "How do we change a value stored in an array? Let's overwrite a slot.",
                       "recap": "To update an array, jump to the index and overwrite the value in that slot; nothing else moves.",
                       "concepts": [what["concepts"][2]], "details": ["Only that slot changes, so an update is as fast as a read."]},
        }
        return specs[focus]
    if s in ("queue", "stack"):
        q = s == "queue"
        end = "front" if q else "top"
        rule = what_rule = (r"first (?:item )?in,? (?:is )?(?:the )?first (?:item )?out|\bFIFO\b" if q
                            else r"last (?:item )?in,? (?:is )?(?:the )?first (?:item )?out|\bLIFO\b")
        rule_sentence = ("A queue is first in, first out: items leave in the same order they arrived." if q
                         else "A stack is last in, first out: the newest item is always the next to leave.")
        add, rem = ("enqueue", "dequeue") if q else ("push", "pop")
        specs = {
            "what_is": {**base, "text": f"what a {s} is", "answer": f"What is a {s}, and in what order do items leave it?",
                        "terms": rf"\b{end}\b|\bfirst in\b|\blast in\b", "intro": CONCEPT[s][0],
                        "recap": ("A queue is first in, first out: new items join at the back, items leave from the front, and nothing in the middle is ever touched." if q
                                  else "A stack is last in, first out: items are pushed onto the top and popped off the top, and nothing below the top is ever touched."),
                        "concepts": [("order rule", what_rule, rule_sentence, "core")], "details": [CONCEPT[s][1]]},
            "insert": {**base, "text": f"{add} an item onto a {s}", "answer": f"What happens when you {add} an item onto a {s}?",
                       "terms": rf"\b{add}\w*|\badd\w*|\bjoin\w*",
                       "intro": (f"What happens when we enqueue a new item? Let's watch it join the back of the queue." if q
                                 else "What happens when we push a new item onto a stack? Let's watch it land on top."),
                       "recap": ("Enqueue always adds the new item at the back of the queue, behind everything already waiting, so the front stays the same." if q
                                 else "Push always puts the new item on the top of the stack, so it becomes the new top and everything else stays below it."),
                       "concepts": [("where it lands", r"\bback\b|\brear\b" if q else r"\btop\b",
                                     "The new item always goes to the back of the queue." if q else "The new item always goes on the top of the stack.", "core")],
                       "details": [f"Only the {'back' if q else 'top'} changes, so {add} takes the same short time no matter how many items there are."],
                       "edges": [f"Edge case: {add}ing onto an empty {s} makes the new item the only item, so it is both ends at once."]},
            "delete": {**base, "text": f"{rem} an item from a {s}", "answer": f"Which item leaves when you {rem} a {s}, and what comes next?",
                       "terms": rf"\b{rem}\w*|\bremov\w*|\bleav\w*",
                       "intro": (f"What happens when we dequeue from a queue? Let's watch the front item leave." if q
                                 else "What happens when we pop a stack? Let's watch the top item come off."),
                       "recap": ("Dequeue removes the item at the front, the one that has waited longest, and the next item in line becomes the new front." if q
                                 else "Pop removes the item on the top, the newest one, and the item below it becomes the new top."),
                       "concepts": [("it leaves from the " + end, rf"\b{end}\b", f"Items only ever leave from the {end}.", "core"),
                                    ("order rule", rule, rule_sentence, "core")],
                       "details": [f"Only the {end} changes, so {rem} takes the same short time no matter how many items there are."],
                       },
            "peek": {**base, "text": f"peek at a {s}", "answer": f"How do you look at the {end} of a {s} without removing it?",
                     "terms": r"\bpeek\w*|\blook\w*",
                     "intro": f"How do we look at the {end} of a {s} without removing it? That is what peek does.",
                     "recap": f"Peek reads the item at the {end} of the {s} without removing it, so the {s} stays exactly the same.",
                     "concepts": [("nothing changes", r"\bwithout remov\w*|\bstays?\b|\bunchanged\b|\bnothing (?:is )?removed",
                                   f"Peek does not change the {s} at all; it only reads the {end}.", "core")]},
        }
        return specs[focus]
    if s == "binary_tree":
        specs = {
            "what_is": {**base, "text": "what a binary search tree is", "answer": "What is a binary search tree, and why is searching it fast?",
                        "terms": r"\bleft\b|\bright\b|\bsmaller\b|\blarger\b", "intro": CONCEPT[s][0],
                        "recap": "A binary search tree keeps smaller values to the left and larger values to the right of every node, so each comparison picks a side and skips the other.",
                        "concepts": [("smaller left, larger right", r"\b(?:smaller|less)\b.*\bleft\b|\bleft\b.*\b(?:smaller|less)\b",
                                      "Smaller values always go to the left of a node and larger values to the right.", "core")],
                        "details": [CONCEPT[s][1]]},
            "insert": {**base, "text": "insert a value into a binary search tree", "answer": "How does a new value find its place in a binary search tree?",
                       "terms": r"\binsert\w*|\badd\w*",
                       "intro": "How does a new value find its place in a binary search tree? Let's follow its path from the root.",
                       "recap": "To insert into a binary search tree, start at the root and go left when the new value is smaller and right when it is larger, "
                                "until you reach an empty spot; the new value becomes a leaf there.",
                       "concepts": [("compare and go left or right", r"\bleft\b|\bright\b", "At each node we go left if the new value is smaller and right if it is larger.", "core"),
                                    ("it becomes a leaf", r"\bleaf\b|\bempty spot\b|\bempty (?:child|place)\b", "When there is no child on that side, the new value becomes a leaf there.", "core")],
                       "details": ["Each comparison skips a whole side of the tree, so an insert only touches the nodes on a single path."]},
            "search": {**base, "text": "search a binary search tree", "answer": "How do you find a value in a binary search tree?",
                       "terms": r"\bsearch\w*|\bfind\w*",
                       "intro": "How do we find a value in a binary search tree? Let's follow the path from the root.",
                       "recap": "To search a binary search tree, compare the target with the current node and go left if it is smaller or right if it is larger, until you find it or run out of nodes.",
                       "concepts": [("compare and go left or right", r"\bleft\b|\bright\b", "At each node we go left if the target is smaller and right if it is larger.", "core")],
                       "details": ["Each comparison skips a whole side of the tree, so a search only follows a single path."],
                       "edges": ["Edge case: if we reach an empty spot, the value is not in the tree."]},
        }
        return specs[focus]
    if s == "graph_bfs":
        return {**base, "text": "how breadth first search explores a graph", "answer": "In what order does breadth first search visit the nodes, and why?",
                "terms": r"\bbreadth\b|\bBFS\b|\blevels?\b|\bqueue\b", "intro": CONCEPT[s][0], "intro_short": "Let's run breadth first search step by step, using a queue to remember which node to visit next.",
                "recap": "Breadth first search took each node from the front of the queue, visited it, and added its unvisited neighbours to the back, so nodes were visited level by level.",
                "concepts": [("uses a queue", r"\bqueue\b", "Breadth first search keeps a queue of discovered nodes waiting to be visited.", "core"),
                             ("level by level", r"\blevel", "Nodes are visited level by level: all neighbours of the start before anything further away.", "core")],
                "details": [CONCEPT[s][1], "Because the queue lets the earliest found node leave first, every node near the start is visited before any node farther away."]}
    if s == "bubble_sort":
        return {**base, "text": "how bubble sort orders the values", "answer": "How does bubble sort put the values in order?",
                "terms": r"\bswap\w*|\bcompar\w*|\bpass\w*|\bbubble\b", "intro": CONCEPT[s][0],
                "intro_short": "Let's sort these values with bubble sort, comparing neighbours and swapping them when they are out of order.",
                "recap": "Bubble sort compares each neighbouring pair and swaps it when it is out of order; every pass carries the largest remaining value to the end, until a pass makes no swaps.",
                "concepts": [("passes", r"\bpass", "Each pass moves the largest remaining value to the end of the array.", "core")],
                "details": [CONCEPT[s][1]]}
    raise UnsupportedTopic(f"Structura cannot run that on {NAMES.get(s, s)} yet.")


def context(analysis: dict) -> dict:
    """Everything the verifier and the lesson builder need to keep a lesson on the question."""
    if analysis["intent"] == "complexity":
        algo = analysis["algorithm"]
        spec = complexity.catalogue(algo)
        return {"intent": "complexity", "focus": "complexity", "focus_text": analysis["focus_text"], "structure": analysis["structure"],
                "must_answer": analysis["must_answer"], "terms": spec["terms"], "intro": spec["intro"], "recap": spec["recap"],
                "intro_words": 30, "concepts": [], "details": [], "edges": [], "edges_combined": None, "off_topic": [],
                "outline": False, "uses": None, "principle": None, "complexity": algo, "must_cover": complexity.must_cover(algo)}
    spec = catalogue(analysis["structure"], analysis["focus"], analysis.get("position"))
    what_is = analysis["intent"] == "what_is"
    intro = spec["intro"] if what_is else spec.get("intro_short", spec["intro"])
    s = analysis["structure"]
    ctx = {"intent": analysis["intent"], "focus": analysis["focus"], "focus_text": analysis["focus_text"], "structure": s,
           "must_answer": analysis["must_answer"], "terms": spec["terms"], "intro": intro, "recap": spec["recap"],
           "intro_words": 45 if what_is else 30,
           "concepts": [list(c) for c in spec["concepts"]], "details": spec["details"], "edges": spec["edges"],
           "edges_combined": spec["edges_combined"], "off_topic": [[n, OFF_TOPIC[n]] for n in spec["off_topic"]],
           "outline": False, "uses": None}
    principle = principle_for(s, analysis["focus"], analysis["intent"])
    ctx["principle"] = {k: principle[k] for k in ("name", "groups", "proof_ops", "proof")} if principle else None
    if what_is and s in WHAT_IS:  # answer-first outline: definition, analogy, rule, demo, uses, recap
        w = WHAT_IS[s]
        ctx.update(outline=True, intro=w["definition"], recap=w["recap"], analogy=w["analogy"], rule=w["rule"],
                   uses=USES[s]["pattern"], uses_sentence=USES[s]["sentence"], intro_words=30, rule_vocab=RULE_VOCAB.get(s, []),
                   concepts=[], details=[], edges=[], edges_combined=None)
    # ANSWER-COVERAGE GATE: [name, regex, scene kind that should say it, number-free hint]. The question's own words must
    # appear. (A "what is" rule is already enforced by the rule scene and the demo-proves-the-rule check; complexity
    # lessons have their own list, see complexity.must_cover.)
    ctx["must_cover"] = [["the answer to the question", spec["terms"], "recap", ctx["recap"]]]
    return ctx


# words the rule scene must introduce (each is explained in plain words in the rule template)
RULE_VOCAB = {"stack": [r"\bpush\w*", r"\bpop\w*"], "queue": [r"\benqueu\w*", r"\bdequeu\w*"], "linked_list": [r"\bhead\b", r"\bnull\b"],
              "array": [r"\bindex\w*", r"\b(?:start|begin)s?\s+at\s+(?:0|zero)\b|\bindex\s+(?:0|zero)\b"], "binary_tree": [r"\broot\b"], "graph_bfs": [r"\bqueue\b"], "bubble_sort": [r"\bpass\w*"]}


# ---------------------------------------------------------------- 3. shaping the LLM's plan around the focus
BUILD_OPS = {"init", "append", "enqueue", "push", "insert_head", "insert_tail", "insert_bst", "add_edge", "load"}
DEFAULT_VALUES = {"linked_list": [10, 20, 30, 40], "array": [10, 20, 30, 40], "queue": [10, 20, 30], "stack": [10, 20, 30],
                  "binary_tree": [50, 30, 70, 20, 40], "bubble_sort": [5, 1, 4, 2, 8]}
DEFAULT_EDGES = [("A", "B"), ("A", "C"), ("B", "D"), ("C", "E")]


def _scene(ops: list[dict], role: str, narration: str | None = None, structure: str | None = None, note: str | None = None) -> dict:
    return {"id": 0, "ops": ops, "narration": narration or PLACEHOLDER, "speed": 1.0, "role": role,
            "structure": structure, "note": note}


def _op(name: str, *args) -> dict:
    return {"op": name, "args": list(args)}


def _sk(scene: dict, primary: str) -> str:
    return scene.get("structure") or primary


def _replay(scenes: list[dict], primary: str, upto: int, kind: str):
    """The real structure `kind` after running scenes[:upto]."""
    ds = make(kind)
    for sc in scenes[:upto]:
        if _sk(sc, primary) == kind:
            for o in sc.get("ops", []):
                ds.apply(o["op"], o.get("args", []))
    return ds


def _infer_role(scene: dict, i: int, n: int, core: set[str]) -> str:
    ops = [o["op"] for o in scene.get("ops", [])]
    if not ops:
        return "setup" if i == 0 else "recap" if i == n - 1 else "core"
    if any(o in core for o in ops):
        return "core"
    return "setup" if all(o in BUILD_OPS for o in ops) else "core"


def _normalise(scenes: list[dict], a: Analysis, primary: str) -> list[dict]:
    core = set(a.core_ops)
    out = []
    for i, sc in enumerate(scenes):
        sc = {**sc, "ops": [dict(o) for o in sc.get("ops", [])]}
        if sc.get("role") not in ROLES:
            sc["role"] = _infer_role(sc, i, len(scenes), core)
        out.append(sc)
    if not out or out[0]["ops"]:
        out.insert(0, _scene([], "setup", note="intro: lead straight into the question"))
    out[0]["role"] = "setup"
    if len(out) < 2 or out[-1]["ops"]:
        out.append(_scene([], "recap", note="recap: restate the answer to the question"))
    out[-1]["role"] = "recap"
    for sc in out[1:-1]:  # only the last scene recaps; the intro is the only no-op setup scene
        if sc["role"] == "recap" or (sc["role"] == "setup" and not sc["ops"]):
            sc["role"] = "core" if a.intent == "what_is" else "drop"
    return [sc for sc in out if sc["role"] != "drop"]


def _merge_setup(scenes: list[dict], a: Analysis, primary: str) -> list[dict]:
    """Leading data-building scenes become ONE `init` scene per structure (unless the question is about inserting)."""
    if a.focus == "insert" and a.intent != "what_is":
        return scenes
    i = 1
    while i < len(scenes) and scenes[i]["ops"] and all(o["op"] in BUILD_OPS for o in scenes[i]["ops"]):
        i += 1
    lead = scenes[1:i]
    if len(lead) <= 1:  # already a single data scene
        for sc in lead:
            sc["role"] = "setup"
        return scenes
    merged = []
    for kind in dict.fromkeys(_sk(sc, primary) for sc in lead):
        ops = [o for sc in lead if _sk(sc, primary) == kind for o in sc["ops"]]
        if kind == "graph_bfs":
            new_ops = ops
        elif kind == "bubble_sort":
            new_ops = [o for o in ops if o["op"] == "load"][:1]
        elif kind == "binary_tree":
            vals = [v for o in ops for v in o["args"]]
            new_ops = [_op("init", *vals)]
        else:
            ds = make(kind)
            for o in ops:
                ds.apply(o["op"], o["args"])
            new_ops = [_op("init", *ds.state()["items"])]
        if new_ops and (len(new_ops[0]["args"]) >= 2 or kind == "graph_bfs"):
            merged.append(_scene(new_ops, "setup", structure=None if kind == primary else kind,
                                 note="setup: show the whole starting data in one go"))
    return [scenes[0], *merged, *scenes[i:]]


def _drop_off_focus(scenes: list[dict], a: Analysis, primary: str) -> list[dict]:
    """Op scenes after the setup that use none of the focus ops are not about the question."""
    allowed = set(a.core_ops) | ({"init", "load", "add_edge"} if a.focus != "insert" else BUILD_OPS)
    if a.intent == "what_is":
        return scenes
    return [sc for sc in scenes if not sc["ops"] or sc["role"] == "setup" or any(o["op"] in allowed for o in sc["ops"])]


def _items(scenes, primary, upto, kind) -> list:
    return _replay(scenes, primary, upto, kind).state()["items"]


def _setup_end(scenes: list[dict]) -> int:
    i = 1
    while i < len(scenes) and scenes[i]["role"] == "setup":
        i += 1
    return i


def _fresh_value(items: list[int]) -> int:
    nums = [int(x) for x in items] or [0]
    v = max(nums) + 10 if all(n % 10 == 0 for n in nums) else max(nums) + 5
    return v if v < 100 else next(x for x in range(1, 100) if x not in nums)


def _between(items: list[int], i: int) -> int:
    a, b = items[i], items[i + 1] if i + 1 < len(items) else items[i] + 10
    v = (a + b) // 2
    return v if v not in items and v != a else _fresh_value(items)


def _walk_scenes(values: list, target_note: str) -> list[dict]:
    return [_scene([_op("walk", v)], "core", note=f"core hop {k + 1}: move the current pointer to {v}; say what {v} points to and why we keep going or stop "
                                                     f"({target_note})") for k, v in enumerate(values)]


def _ensure_walk_before(scenes: list[dict], idx: int, walk: list, note: str) -> list[dict]:
    """Make sure the scenes right before scenes[idx] walk exactly `walk`, hop by hop."""
    j = idx
    while j > 0 and scenes[j - 1]["ops"] and all(o["op"] == "walk" for o in scenes[j - 1]["ops"]):
        j -= 1
    existing = [o["args"][0] for sc in scenes[j:idx] for o in sc["ops"]]
    if [str(x) for x in existing] == [str(x) for x in walk]:
        return scenes
    return scenes[:j] + _walk_scenes(walk, note) + scenes[idx:]


def _first(scenes, primary, kind, ops: set[str], start: int = 0) -> int | None:
    return next((i for i in range(start, len(scenes)) if _sk(scenes[i], primary) == kind and any(o["op"] in ops for o in scenes[i]["ops"])), None)


def _insert_core(scenes: list[dict], new: list[dict]) -> list[dict]:
    pos = next((i for i, sc in enumerate(scenes) if sc["role"] in ("edge_case", "recap") and i > 0), len(scenes))
    return scenes[:pos] + new + scenes[pos:]


def _ensure_core(scenes: list[dict], a: Analysis, primary: str) -> list[dict]:
    s = a.structure
    if s not in ("graph_bfs", "bubble_sort", "linked_list") and a.focus != "insert" and not _items(scenes, primary, _setup_end(scenes), s):
        scenes = [scenes[0], _scene([_op("init", *DEFAULT_VALUES[s])], "setup", note="setup: show the whole starting data in one go"), *scenes[1:]]
    if s == "linked_list" and a.focus != "compare":
        return _ensure_core_ll(scenes, a, primary)
    if s == "graph_bfs":
        ds = _replay(scenes, primary, len(scenes), s)
        st = ds.state()
        if not st["items"]:
            return scenes
        if st["start"] is None:
            scenes = _insert_core(scenes, [_scene([_op("start_bfs", st["items"][0])], "core", note="core: start the search, the start node enters the queue")])
            ds = _replay(scenes, primary, len(scenes), s)
        extra = []
        while ds.queue:
            ds.apply("visit")
            extra.append(_scene([_op("visit")], "core", note="core: visit the front node of the queue and enqueue its unvisited neighbours"))
        return _insert_core(scenes, extra)
    if s == "bubble_sort":
        ds = _replay(scenes, primary, len(scenes), s)
        extra = []
        while ds.items and not ds.done and len(extra) < 30:
            ds.apply("step")
            extra.append(_scene([_op("step")], "core", note="core: compare the next adjacent pair and swap if out of order"))
        return _insert_core(scenes, extra)
    if _first(scenes, primary, s, set(a.core_ops), 1) is not None and a.intent != "what_is":
        return scenes
    have = {o["op"] for sc in scenes for o in sc["ops"]}
    for op in a.core_ops:
        if op in have:
            continue
        items = _items(scenes, primary, len(scenes), s)
        if not items:
            continue
        mid = len(items) // 2
        new = {"get": [_op("get", mid)], "insert_at": [_op("insert_at", mid, _between(items, mid - 1 if mid else 0))],
               "delete_at": [_op("delete_at", mid)], "set": [_op("set", mid, _fresh_value(items))], "append": [_op("append", _fresh_value(items))],
               "enqueue": [_op("enqueue", _fresh_value(items))], "dequeue": [_op("dequeue")], "peek": [_op("peek")],
               "push": [_op("push", _fresh_value(items))], "pop": [_op("pop")],
               "insert_bst": [_op("insert_bst", next(v for v in range(int(items[0]) + 1, 100) if v not in items))],
               "search_bst": [_op("search_bst", items[-1])]}.get(op)
        if new:
            scenes = _insert_core(scenes, [_scene(new, "core", note=f"core: show {op.replace('_', ' ')} on the real {s.replace('_', ' ')}")])
    return scenes


def _ensure_core_ll(scenes: list[dict], a: Analysis, primary: str) -> list[dict]:
    kind = "linked_list"
    start = _setup_end(scenes)
    items = _items(scenes, primary, start, kind)
    if len(items) < 2:  # nothing to walk: give the lesson real data first
        scenes = [scenes[0], _scene([_op("init", *DEFAULT_VALUES[kind])], "setup", note="setup: show the whole list in one go"),
                  *[sc for sc in scenes[1:] if not sc["ops"]]]
        start, items = 2, list(DEFAULT_VALUES[kind])
    if a.focus == "delete":
        idx = _first(scenes, primary, kind, {"delete_value"}, start)
        target = scenes[idx]["ops"][0]["args"][0] if idx is not None else None
        before = _items(scenes, primary, idx, kind) if idx is not None else items
        want_middle = a.position == "middle" and len(before) >= 3
        if idx is None or target not in before or (want_middle and target in (before[0], before[-1])) \
                or (a.position == "head" and target != before[0]) or (a.position == "tail" and target != before[-1]):
            before = items
            target = {"head": before[0], "tail": before[-1]}.get(a.position or "middle", before[len(before) // 2])
            new = _scene([_op("delete_value", target)], "core",
                         note=f"core: rewire the previous node's next pointer past {target}; say which node now points where and that {target} is skipped")
            if idx is None:
                scenes = scenes[:start] + [new] + scenes[start:]
                idx = start
            else:
                scenes = scenes[:idx] + [new] + scenes[idx + 1:]
        scenes[idx]["role"] = "core"
        pos = [str(x) for x in before].index(str(target))
        return _ensure_walk_before(scenes, idx, before[:pos], f"we want the node BEFORE {target}, whose next pointer leads to {target}") if pos else scenes
    if a.focus == "search":
        idx = _first(scenes, primary, kind, {"search"}, start)
        before = _items(scenes, primary, idx, kind) if idx is not None else items
        if idx is None or scenes[idx]["ops"][0]["args"][0] not in before:
            target = before[min(2, len(before) - 1)]
            new = _scene([_op("search", target)], "core", note=f"core: the search reaches {target} and finds it")
            if idx is None:
                scenes = scenes[:start] + [new] + scenes[start:]
                idx = start
            else:
                scenes = scenes[:idx] + [new] + scenes[idx:]
        target = scenes[idx]["ops"][0]["args"][0]
        scenes[idx]["role"] = "core"
        pos = [str(x) for x in before].index(str(target))
        return _ensure_walk_before(scenes, idx, before[:pos], f"we are looking for {target}; compare each node with {target}")
    if a.focus == "traverse":
        if _first(scenes, primary, kind, {"walk"}, start) is None:
            scenes = scenes[:start] + _walk_scenes(items, "visit every node until next is null") + scenes[start:]
        return scenes
    if a.focus == "insert":
        op = {"head": "insert_head", "tail": "insert_tail", "middle": "insert_after"}[a.position or "head"]
        idx = _first(scenes, primary, kind, {op}, start)
        if idx is None:
            v = _between(items, len(items) // 2 - 1) if op == "insert_after" else _fresh_value(items)
            ops = [_op(op, items[len(items) // 2 - 1], v)] if op == "insert_after" else [_op(op, v)]
            scenes = scenes[:start] + [_scene(ops, "core", note=f"core: {op.replace('_', ' ')}; say which pointers change, in order")] + scenes[start:]
            idx = start
        scenes[idx]["role"] = "core"
        before = _items(scenes, primary, idx, kind)
        if op == "insert_tail" and before:
            return _ensure_walk_before(scenes, idx, before, "walk to the tail, the node whose next pointer is null")
        if op == "insert_after":
            t = scenes[idx]["ops"][0]["args"][0]
            pos = [str(x) for x in before].index(str(t))
            return _ensure_walk_before(scenes, idx, before[: pos + 1], f"walk to {t}, the node the new node goes after")
        return scenes
    if a.focus == "what_is":  # demos: a walk (no index jumping), an insert, a delete
        have = {o["op"] for sc in scenes for o in sc["ops"]}
        if "walk" not in have:
            scenes = scenes[:start] + _walk_scenes(items[:3], "show that we can only move one node at a time from the head") + scenes[start:]
        if not have & {"insert_head", "insert_after", "insert_tail"}:
            scenes = _insert_core(scenes, [_scene([_op("insert_head", _fresh_value(items))], "core", note="core demo: insert at the head; say which pointers change")])
        if "delete_value" not in have:
            now = _items(scenes, primary, len(scenes), kind)
            scenes = _insert_core(scenes, [_scene([_op("delete_value", now[len(now) // 2])], "core",
                                                  note="core demo: delete a middle node; say which node's next pointer is rewired and that the node is skipped")])
        return scenes
    return scenes


def _cap_setup(scenes: list[dict]) -> list[dict]:
    """At most 2 setup scenes (the intro + one data scene); later setup scenes are really core."""
    seen = 0
    for sc in scenes:
        if sc["role"] == "setup":
            seen += 1
            if seen > 2:
                sc["role"] = "core"
    return scenes


def compare_skeleton(values: list[int] | None = None) -> list[dict]:
    """Array vs linked list on the SAME values, side by side (ops only; narration is written with the true states)."""
    v = [x for x in (values or []) if isinstance(x, int)][:5]
    v = v if len(v) >= 3 else DEFAULT_VALUES["linked_list"]
    k = min(2, len(v) - 1)
    new = _between(v, k - 1)
    return [
        _scene([], "setup", note="intro: lead straight into the question"),
        _scene([_op("init", *v)], "setup", structure="array", note="setup: the values stored in an array, side by side in numbered slots"),
        _scene([_op("get", k)], "core", structure="array", note=f"core: the array reads index {k} directly, a single jump, because slots sit side by side"),
        _scene([_op("init", *v), _op("walk", v[0])], "core", structure="linked_list",
               note="core: the same values as a linked list; nodes are joined by next pointers and we can only start at the head"),
        *[_scene([_op("walk", x)], "core", structure="linked_list", note=f"core hop: follow the next pointer to {x}; reaching index {k} takes {k} hops, not a jump")
          for x in v[1:k + 1]],
        _scene([_op("insert_at", k, new)], "core", structure="array", note=f"core: inserting {new} at index {k} of the array shifts every later item right"),
        _scene([_op("insert_after", v[k - 1], new)], "core", structure="linked_list",
               note=f"core: inserting {new} after {v[k - 1]} in the linked list only rewires pointers; nothing shifts"),
        _scene([], "recap", note="recap: restate the difference"),
    ]


def skeleton(a: Analysis, values: list[int] | None = None, edges: list | None = None, start: str | None = None) -> list[dict]:
    """A whole lesson built in code from the analysis (used when the LLM's plan cannot be shaped)."""
    if a.focus == "compare":
        return compare_skeleton(values)
    s = a.structure
    if s == "graph_bfs":
        e = edges or DEFAULT_EDGES
        scenes = [_scene([], "setup"), _scene([_op("add_edge", u, w) for u, w in e], "setup", note="setup: build the graph"),
                  _scene([_op("start_bfs", start or e[0][0])], "core", note="core: start the search"), _scene([], "recap")]
    elif s == "bubble_sort":
        scenes = [_scene([], "setup"), _scene([_op("load", *(values or DEFAULT_VALUES[s]))], "setup", note="setup: load the values"), _scene([], "recap")]
    else:
        vals = values or DEFAULT_VALUES[s]
        if a.focus == "insert" and s in ("queue", "stack"):
            vals = vals[:2]
        scenes = [_scene([], "setup"), _scene([_op("init", *vals)], "setup", note="setup: show the whole starting data in one go"), _scene([], "recap")]
    return _cap_setup(_ensure_core(scenes, a, s))


def outline_mode(a: Analysis) -> bool:
    return a.intent == "what_is" and a.structure in WHAT_IS


def _llm_points(plan: dict) -> dict[str, dict]:
    """The LLM's answer points by id (kind + one-line point), when it gave usable ones."""
    out = {}
    for pt in plan.get("answer_points") or []:
        if isinstance(pt, dict) and isinstance(pt.get("id"), str) and isinstance(pt.get("point"), str):
            out[pt["id"]] = {"kind": str(pt.get("kind") or ""), "point": pt["point"].strip(), "visual": str(pt.get("visual") or "none")}
    return out


def _llm_kind(scene: dict, points: dict) -> str | None:
    pid = scene.get("point_id")
    return points.get(pid, {}).get("kind") if pid else None


def shape(plan: dict, a: Analysis) -> dict:
    """Plan the ANSWER first, then the visuals: answer points, then scenes derived from them (each scene teaches one point)."""
    points = _llm_points(plan)
    if outline_mode(a):
        shaped = {**plan, "structure": a.structure, "scenes": _shape_what_is(plan, a, points), "analysis": a.to_dict()}
    else:
        shaped = _shape_ops(plan, a)
    shaped["answer_points"] = assign_points(shaped["scenes"], a, points)
    return shaped


def _shape_what_is(plan: dict, a: Analysis, points: dict) -> list[dict]:
    """definition -> analogy -> rule (with vocabulary) -> demo that proves the rule -> real-world uses -> recap."""
    s = a.structure
    llm = plan.get("scenes", [])
    by_kind: dict[str, dict] = {}
    for sc in llm:
        k = _llm_kind(sc, points)
        if k and k not in by_kind and not sc.get("ops"):
            by_kind[k] = sc
    if s in WHAT_IS_DEMO:
        vals = list(dict.fromkeys(x for sc in llm for o in sc.get("ops", []) if o.get("op") in BUILD_OPS
                                  for x in o.get("args", []) if isinstance(x, int) and 0 < x < 100))
        need = {"stack": 3, "queue": 3, "binary_tree": 4}.get(s, 4)
        vals = (vals + [d for d in DEFAULT_VALUES[s] if d not in vals])[:need]
        demo = [_scene([_op(name, *args)], "setup" if name == "init" else "core", note=_demo_note(s, name)) for name, args in WHAT_IS_DEMO[s](vals)]
    else:  # graphs and sorting: the shaped run of the algorithm is the demo
        demo = [sc for sc in _shape_ops(plan, a)["scenes"] if sc["ops"]]
    llm_ops = [sc for sc in llm if sc.get("ops")]
    for sc in demo:  # keep the LLM's wording where it planned exactly this step
        match = next((x for x in llm_ops if [(o["op"], list(o.get("args", []))) for o in x["ops"]] == [(o["op"], o["args"]) for o in sc["ops"]]), None)
        if match is not None and match.get("narration"):
            sc["narration"] = match["narration"]
            llm_ops.remove(match)
    out = []
    for kind, role, desc in WHAT_IS_POINTS:
        if kind == "demo":
            for sc in demo:
                out.append({**sc, "kind": "demo"})
            continue
        llm_sc = by_kind.get(kind)
        out.append({**_scene([], role, (llm_sc or {}).get("narration"), note=f"{kind}: {desc}"), "kind": kind})
    return out


def _demo_note(s: str, op: str) -> str:
    p = principle_for(s, "what_is", "what_is")
    if p and op in p["proof_ops"]:
        return f"demo that PROVES the rule ({p['name']}): say what this step shows about the rule, with the real values"
    return f"demo step: {op.replace('_', ' ')}, simplest first; name the values and the new state"


POINT_TEXT = {"definition": "What it is, in plain words", "analogy": "An everyday analogy", "rule": "The key rule and its vocabulary",
              "demo": "A demo that proves the rule", "uses": "Where it is used in real life", "recap": "The takeaways",
              "goal": "The question we are answering", "steps": "The answer, step by step", "explain": "Why it works", "edge": "An edge case"}


def assign_points(scenes: list[dict], a: Analysis, llm_points: dict) -> list[dict]:
    """Give every scene exactly one answer point. Only the demo (the run of operations) may span several scenes."""
    points: list[dict] = []

    def add(kind: str, text: str | None = None) -> str:
        pid = f"p{len(points) + 1}"
        points.append({"id": pid, "kind": kind, "point": text or POINT_TEXT.get(kind, kind), "visual": "none"})
        return pid

    demo_id = None
    for i, sc in enumerate(scenes):
        llm_text = llm_points.get(sc.get("point_id") or "", {}).get("point")
        kind = sc.get("kind")
        if not kind:
            if i == 0 and not sc["ops"]:
                kind = "definition" if a.intent == "what_is" else "goal"
            elif sc.get("role") == "recap":
                kind = "recap"
            elif sc.get("role") == "edge_case":
                kind = "edge"
            elif sc["ops"]:
                kind = "demo" if a.intent == "what_is" else "steps"
            else:
                kind = "explain"
        sc["kind"] = kind
        if kind in ("demo", "steps"):
            if demo_id is None:
                demo_id = add(kind, llm_text or (f"Step by step: how to {a.focus_text}" if kind == "steps" else None))
            sc["point_id"] = demo_id
        else:
            sc["point_id"] = add(kind, llm_text or (a.must_answer if kind == "goal" else None))
    for pt in points:  # what each point shows on stage
        ops = list(dict.fromkeys(o["op"] for sc in scenes if sc["point_id"] == pt["id"] for o in sc["ops"]))
        pt["visual"] = "ops: " + ", ".join(ops) if ops else "current state" if pt["kind"] not in ("definition", "goal") else "none"
    return points


def _shape_ops(plan: dict, a: Analysis) -> dict:
    """Organise the LLM's plan around the question: roles, one setup scene, guaranteed core ops, no off-focus scenes."""
    from verifier import simulate

    primary = plan["structure"]
    if a.focus == "compare":
        llm_values = [x for sc in plan["scenes"] for o in sc.get("ops", []) if o["op"] in ("init", "append", "insert_tail", "insert_head")
                      for x in o.get("args", []) if isinstance(x, int)]
        scenes = compare_skeleton(list(dict.fromkeys(llm_values)))
        _keep_bookends(plan["scenes"], scenes)
        return {**plan, "structure": "linked_list", "scenes": scenes, "analysis": a.to_dict()}
    if primary != a.structure:  # the LLM answered about a different structure: rebuild in code, keep nothing of it
        scenes = skeleton(a)
        return {**plan, "structure": a.structure, "scenes": _mark_edges(scenes, a, a.structure), "analysis": a.to_dict()}
    scenes = copy.deepcopy(plan["scenes"])
    try:
        scenes = _normalise(scenes, a, primary)
        scenes = _merge_setup(scenes, a, primary)
        scenes = _drop_off_focus(scenes, a, primary)
        scenes = _ensure_core(scenes, a, primary)
        scenes = _cap_setup(scenes)
        scenes = _mark_edges(scenes, a, primary)  # also proves every op runs on the real structure
    except (OpError, ValueError, IndexError, StopIteration):
        values = [x for sc in plan["scenes"] for o in sc.get("ops", []) if o["op"] in BUILD_OPS for x in o.get("args", []) if isinstance(x, int)]
        scenes = _mark_edges(skeleton(a, list(dict.fromkeys(values))[:6] or None), a, primary)
        _keep_bookends(plan["scenes"], scenes)
    return {**plan, "structure": primary, "scenes": scenes, "analysis": a.to_dict()}


def _mark_edges(scenes: list[dict], a: Analysis, primary: str) -> list[dict]:
    """A lookup that finds nothing, or a second delete/search after the main one, is an edge case, not the core."""
    from verifier import simulate

    sims = simulate(primary, scenes)
    main_done = False
    for sc, sim in zip(scenes, sims):
        lasts = [st.get("last", {}) for st in sim["steps"]]
        if any(l.get("found") is False for l in lasts):
            sc["role"] = "edge_case"
        elif a.structure == "linked_list" and a.focus in ("delete", "search") and any(l.get("op") in ("delete_value", "search") for l in lasts):
            if main_done and sc["role"] == "core":
                sc["role"] = "edge_case"
            main_done = True
    return scenes


def _keep_bookends(old: list[dict], new: list[dict]) -> None:
    """Reuse the LLM's intro and recap wording on a rebuilt plan (they are verified like everything else)."""
    if old and not old[0].get("ops") and new and not new[0]["ops"]:
        new[0]["narration"] = old[0].get("narration") or PLACEHOLDER
    if len(old) > 1 and not old[-1].get("ops") and not new[-1]["ops"]:
        new[-1]["narration"] = old[-1].get("narration") or PLACEHOLDER


# ---------------------------------------------------------------- 4. budget helpers (used after audio is made)
def duration(scene: dict) -> float:
    return scene.get("duration", 0) / scene.get("speed", 1.0)


def core_share(scenes: list[dict]) -> float:
    total = sum(duration(s) for s in scenes)
    return sum(duration(s) for s in scenes if s.get("role") == "core") / total if total else 0.0
