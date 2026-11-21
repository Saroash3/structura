"""What a good answer contains, per structure: the outline of a "what is X" answer, the key rule and how a demo
proves it, real-world uses, plain-words vocabulary, jargon that must be explained before use, and quiz answer keys.

PRIORITY RULE: answer quality comes first. Animations only support the answer; every scene teaches one point.

Every sentence here may be spoken as-is (as a fallback when the LLM's narration fails), so it contains NO numbers
and no unexplained jargon, and it must pass the verifier on any state.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------- jargon: must be explained in plain words before (or where) it is used
# term -> (pattern that finds the term, pattern that shows it is being explained right there)
JARGON: dict[str, tuple[str, str]] = {
    "constant time": (r"\bconstant[- ]time\b|\bO\(1\)", r"(?:constant[- ]time|O\(1\))\W+(?:means|meaning|which means|that is|i\.e\.)|\b(?:a single|just a|always a) (?:quick )?step\b|\bno matter how (?:many|long|big)"),
    "linear time": (r"\blinear[- ]time\b|\bO\(n\)", r"(?:linear[- ]time|O\(n\))\W+(?:means|meaning|which means|that is)|\b(?:grows?|longer|more steps?) (?:with|as)\b"),
    "logarithmic time": (r"\blogarithmic\b|\bO\(log", r"(?:logarithmic|O\(log\s*n\))\W+(?:means|meaning|which means|that is)|\bhalf\b"),
    "underflow": (r"\bunderflow\w*", r"\bunderflow\w*\W+(?:means|meaning|which means|that is|is what)|\bunderflow\b[^.]*\bempty\b|\bempty\b[^.]*\bunderflow\b"),
    "overflow": (r"\boverflow\w*", r"\boverflow\w*\W+(?:means|meaning|which means|that is|is what)|\boverflow\b[^.]*\bfull\b|\bfull\b[^.]*\boverflow\b"),
    "LIFO": (r"\bLIFO\b", r"last (?:item )?in,? (?:is )?(?:the )?first (?:item )?out"),
    "FIFO": (r"\bFIFO\b", r"first (?:item )?in,? (?:is )?(?:the )?first (?:item )?out"),
    "traversal": (r"\btraversal\b|\btraverse\w*", r"\btravers\w*\W+(?:means|meaning|which means|that is)|\btravers\w*\b[^.]*\b(?:visit\w*|walk\w*|go\w* through)\b"),
    "amortized": (r"\bamortized\b", r"\bamortized\W+(?:means|meaning|which means|that is)|\bon average\b"),
    "contiguous": (r"\bcontiguous\b", r"\bcontiguous\W+(?:means|meaning|which means|that is)|\bside by side\b|\bnext to each other\b"),
    "dereference": (r"\bdereferenc\w*", r"\bdereferenc\w*\W+(?:means|meaning|which means|that is)"),
}

# Vocabulary each structure uses; given to the planner so it defines each word in plain words on first use.
GLOSSARY: dict[str, dict[str, str]] = {
    "stack": {"push": "add an item on the top", "pop": "take the top item off", "top": "the most recently added item, the only one you can reach",
              "peek": "look at the top item without taking it off"},
    "queue": {"enqueue": "join at the back of the line", "dequeue": "leave from the front of the line", "front": "the item that has waited longest",
              "back": "where new items join", "peek": "look at the front item without removing it"},
    "linked_list": {"node": "one box holding a value and a pointer", "pointer": "an arrow saying which node comes next",
                    "head": "the pointer to the first node", "null": "the empty pointer that marks the end of the list"},
    "array": {"index": "the slot number, starting at 0", "slot": "one numbered place that holds a value"},
    "binary_tree": {"root": "the node at the very top", "leaf": "a node with no children", "child": "a node directly below another node"},
    "graph_bfs": {"node": "one point in the graph", "edge": "a line joining two nodes", "neighbour": "a node joined to this one by an edge",
                  "queue": "the waiting line of nodes to visit next"},
    "bubble_sort": {"pass": "one sweep from the start to the end of the unsorted part", "swap": "two neighbours trade places"},
}

# ---------------------------------------------------------------- the key rule, and how a demo proves it
# groups: every group must match inside ONE demo scene. proof_ops: the steps that prove it. proof: sentence added to that
# step's narration (formatted with the step's true `last` fields), so a demo always says what it shows.
PRINCIPLE: dict[str, dict] = {
    "stack": {"name": "last in, first out",
              "groups": [r"\blast\b[^.]*\b(?:in|added|pushed|on)\b|\bnewest\b|\bmost recent\w*", r"\bfirst\b[^.]*\b(?:out|off|to leave|to go|removed)\b|\bcomes? (?:out|off) first\b|\bleaves? first\b"],
              "proof_ops": ["pop"], "proof": "{removed} was the last one in, so it is the first one out."},
    "queue": {"name": "first in, first out",
              "groups": [r"\b(?:first|earliest)\b[^.]*\b(?:in|arriv\w*|join\w*)\b|\barrived first\b|\bwaited (?:the )?longest\b",
                         r"\bfirst\b[^.]*\b(?:out|to leave|served|to go)\b|\bleaves? first\b|\bserved first\b"],
              "proof_ops": ["dequeue"], "proof": "{removed} arrived first, so it is the first to leave."},
    "linked_list": {"name": "no index: you walk the pointers from the head",
                    "groups": [r"\bno index\b|\bcannot jump\b|\bcan't jump\b|\bonly (?:way|start)\b|\bmust (?:walk|follow|start)\b|\bwalk\w*\b|\bfollow\w*\b",
                               r"\bpointer\w*\b|\bnext\b"],
                    "proof_ops": ["walk"], "proof": "There is no index to jump to, so the only way on is to follow the next pointer."},
    "array": {"name": "jump straight to any index",
              "groups": [r"\bindex\b", r"\bjump\w*\b|\bdirect\w*\b|\bstraight\b|\binstant\w*\b|\bwithout (?:looking|checking|walking)\b"],
              "proof_ops": ["get"], "proof": "The index lets us jump straight to {value} without looking at any other item."},
    "binary_tree": {"name": "smaller goes left, larger goes right",
                    "groups": [r"\b(?:smaller|less|lower)\b[^.]*\bleft\b|\bleft\b[^.]*\b(?:smaller|less|lower)\b",
                               r"\b(?:larger|bigger|greater|higher)\b[^.]*\bright\b|\bright\b[^.]*\b(?:larger|bigger|greater|higher)\b"],
                    "proof_ops": ["insert_bst", "search_bst"], "proof": "Smaller values always go left and larger values go right."},
    "graph_bfs": {"name": "visit level by level using a queue",
                  "groups": [r"\bqueue\b", r"\blevels?\b|\bcloser\b|\bnearest\b|\bneighbou?rs? (?:first|before)\b"],
                  "proof_ops": ["visit"], "proof": "Taking nodes from the front of the queue means closer nodes are visited before farther ones, level by level."},
    "bubble_sort": {"name": "neighbours swap until the largest bubbles to the end",
                    "groups": [r"\bswap\w*\b|\bstay\w*\b", r"\blarg\w*\b|\bbigg\w*\b|\bout of order\b|\bin order\b"],
                    "proof_ops": ["step"], "proof": ""},  # the step template already says "a is bigger, so swap"
}

# ---------------------------------------------------------------- real-world uses (what_is answers must include them)
USES: dict[str, dict] = {
    "stack": {"pattern": r"\bundo\b|\bback button\b|\bbrowser\b|\bfunction calls?\b|\bcall stack\b",
              "sentence": "Stacks are everywhere: the undo button takes back your most recent change first, the browser back button returns to the page you saw last, "
                          "and programs keep track of function calls on a stack."},
    "queue": {"pattern": r"\bprint\w*\b|\bline\b|\bticket\w*\b|\bcustomer\w*\b|\btasks?\b|\bjobs?\b|\bkeyboard\b|\bmessages?\b",
              "sentence": "Queues are everywhere: documents wait in a printer queue, customers wait in line at a ticket counter, and a computer handles tasks "
                          "and messages in the order they arrive."},
    "linked_list": {"pattern": r"\bplaylist\w*\b|\bsongs?\b|\bhistory\b|\btrain\b|\bimage viewer\b|\bphotos?\b|\bnext (?:song|photo|page)\b",
                    "sentence": "Linked lists show up in a music playlist where each song knows the next song, in a photo viewer's next button, "
                                "and in programs that insert and remove items often."},
    "array": {"pattern": r"\bscores?\b|\bpixels?\b|\bseats?\b|\bdays?\b|\bspreadsheet\w*\b|\btable\w*\b|\bgrades?\b|\blist of\b",
              "sentence": "Arrays are everywhere: a list of game scores, the seats in a row at the cinema, the days of the week, and the pixels of an image "
                          "are all stored in numbered slots."},
    "binary_tree": {"pattern": r"\bdictionar\w*\b|\bphone ?book\b|\bdatabase\w*\b|\bautocomplete\b|\bguessing game\b|\bfile ?system\w*\b",
                    "sentence": "Binary search trees help wherever we look things up by order: a dictionary or phone book, database indexes, and autocomplete "
                                "suggestions all narrow the search by going left or right."},
    "graph_bfs": {"pattern": r"\bmaps?\b|\bgps\b|\bshortest\b|\bfriends?\b|\bsocial\b|\bnetwork\w*\b|\bweb ?pages?\b",
                  "sentence": "Breadth first search finds the shortest route in maps and networks, suggests friends of friends on social apps, "
                              "and lets web crawlers explore pages close to the start first."},
    "bubble_sort": {"pattern": r"\bcards?\b|\bclassroom\w*\b|\bteach\w*\b|\bsmall lists?\b|\bnearly sorted\b",
                    "sentence": "Bubble sort is mostly used for teaching and for tiny or nearly sorted lists, like tidying a hand of cards by swapping neighbours."},
}

# ---------------------------------------------------------------- the outline of a "what is X" answer
# kind -> (role, template sentence). The "demo" point is built from real ops in code.
WHAT_IS: dict[str, dict[str, str]] = {
    "stack": {
        "definition": "A stack is a pile of items where you can only add or remove at a single end, called the top.",
        "analogy": "Think of a stack of plates: you put a new plate on top, and you also take plates from the top, never from the middle.",
        "rule": "The key rule is last in, first out: the item added most recently is always the first to leave. Adding an item is called push, "
                "taking the top item off is called pop, and the top is the most recently added item.",
        "recap": "Takeaways: you only ever touch the top, push adds and pop removes, and whatever went in most recently comes out first.",
    },
    "queue": {
        "definition": "A queue is a line of items where new items join at the back and items leave from the front.",
        "analogy": "Think of people waiting at a ticket counter: newcomers join the end of the line, and the person at the front is served next.",
        "rule": "The key rule is first in, first out: the item that arrived first is always the first to leave. Joining at the back is called enqueue, "
                "leaving from the front is called dequeue, and the front is the item that has waited longest.",
        "recap": "Takeaways: items join at the back and leave from the front, enqueue adds and dequeue removes, and whoever waited longest goes next.",
    },
    "linked_list": {
        "definition": "A linked list is a chain of nodes, where each node holds a value and a pointer to the node after it.",
        "analogy": "Think of a treasure hunt: each clue tells you where the next clue is hidden, so you must follow them in order.",
        "rule": "The key rule is that there is no index: the head points to the first node, each next pointer leads to the following node, "
                "and the last node points to null, which marks the end. To reach a node you walk the pointers from the head.",
        "recap": "Takeaways: nodes are joined by next pointers, every walk starts at the head and ends at null, and reaching a node means following pointers, not jumping.",
    },
    "array": {
        "definition": "An array is a row of numbered slots stored side by side in memory, each holding a value.",
        "analogy": "Think of lockers in a hallway: every locker has a number, so you can walk straight to the one you want.",
        "rule": "The key rule is that every slot has an index, and indexes start at 0, so the computer can jump straight to any index without looking at the others. "
                "The price is that inserting in the middle shifts every later item over.",
        "recap": "Takeaways: slot numbers start at 0, reading any slot is a single quick step, and inserting in the middle makes later items shift.",
    },
    "binary_tree": {
        "definition": "A binary search tree is a tree of nodes where each node has at most a left child and a right child, kept in sorted order.",
        "analogy": "Think of a guessing game where every answer tells you higher or lower, so each question rules out a whole side.",
        "rule": "The key rule is that smaller values always go left and larger values go right. The root is the node at the very top, and every "
                "search follows a single path down from it.",
        "recap": "Takeaways: left means smaller and right means larger, every search follows a single path from the root, and each step skips a whole side.",
    },
    "graph_bfs": {
        "definition": "Breadth first search is a way to visit every node of a graph, starting from a single node and spreading outwards.",
        "analogy": "Think of ripples spreading from a stone dropped in a pond: the nearest ring comes first, then the next ring out.",
        "rule": "The key rule is level by level: first the start node, then all its neighbours, then their neighbours. A queue, a waiting line of nodes, "
                "remembers who is next, and every node is marked when found so it is never visited twice.",
        "recap": "Takeaways: the queue decides the order, closer nodes always come before farther ones, and no node is visited twice.",
    },
    "bubble_sort": {
        "definition": "Bubble sort puts values in order by repeatedly comparing neighbours and swapping them when they are out of order.",
        "analogy": "Think of bubbles rising in water: on every sweep, the largest remaining value floats up to the end.",
        "rule": "The key rule is that neighbours swap when the left value is larger. Each pass, a sweep from start to end, carries the largest "
                "remaining value to its final place, and the sort stops when a pass makes no swaps.",
        "recap": "Takeaways: compare neighbours, swap when the left is larger, and each pass fixes the largest remaining value at the end.",
    },
}
WHAT_IS_POINTS = [  # (kind, role, one-line description of the point)
    ("definition", "setup", "what it is, in one plain sentence"),
    ("analogy", "core", "an everyday analogy"),
    ("rule", "core", "the single key rule, with its vocabulary in plain words"),
    ("demo", "core", "a short demo that proves the rule on real data"),
    ("uses", "core", "where it is used in real life"),
    ("recap", "recap", "the takeaways, in new wording"),
]
# Demo ops for a "what is" answer, simplest first; `{v}` are the lesson's values. The proving op comes last.
WHAT_IS_DEMO = {
    "stack": lambda v: [("push", [v[0]]), ("push", [v[1]]), ("push", [v[2]]), ("pop", [])],
    "queue": lambda v: [("enqueue", [v[0]]), ("enqueue", [v[1]]), ("enqueue", [v[2]]), ("dequeue", [])],
    "linked_list": lambda v: [("init", list(v)), ("walk", [v[0]]), ("walk", [v[1]]), ("walk", [v[2]])],
    "array": lambda v: [("init", list(v)), ("get", [len(v) // 2]), ("insert_at", [1, (v[0] + v[1]) // 2 if (v[0] + v[1]) // 2 not in v else max(v) + 5])],
    "binary_tree": lambda v: [("insert_bst", [x]) for x in v] + [("search_bst", [v[-1]])],
}

# ---------------------------------------------------------------- quiz answer keys (fixed, per structure)
REAL_WORLD_QUIZ: dict[str, tuple[str, str, list[str], str]] = {  # question, answer, distractors, explanation
    "stack": ("Which everyday feature works like a stack?", "The undo button: your most recent change is undone first",
              ["A printer queue: the first document sent prints first", "A phone book sorted by name", "A shuffled music playlist"],
              "Undo always takes back the newest change first, which is last in, first out."),
    "queue": ("Which everyday situation works like a queue?", "People waiting in line at a ticket counter",
              ["A pile of plates where you take the top one", "A dictionary sorted by word", "Lockers you open by number"],
              "The person who joined the line first is served first, which is first in, first out."),
    "linked_list": ("Which of these is most like a linked list?", "A playlist where each song knows which song comes next",
                    ["Numbered lockers you can open directly", "A pile of plates", "People waiting in line"],
                    "Each song points to the next one, just like a node's next pointer."),
    "array": ("Which of these is most like an array?", "A row of numbered lockers you can open directly",
              ["A treasure hunt where each clue points to the next", "A pile of plates", "A family tree"],
              "Each locker has a number, so you can go straight to it, just like an index."),
    "binary_tree": ("Which everyday task works like searching a binary search tree?", "Looking up a word in a dictionary by going earlier or later",
                    ["Reading a book from the first page to the last", "Opening random pages until the word turns up", "Checking the words in the order they were added"],
                    "Each comparison tells you which side to keep searching, like left and right in the tree."),
    "graph_bfs": ("Which task is breadth first search good at?", "Finding the shortest route in a map or network",
                  ["Going as deep as possible down one road before trying another", "Sorting a list of numbers", "Finding the largest number in a list"],
                  "Because it explores level by level, the first time it reaches a node is along a shortest route."),
    "bubble_sort": ("Where is bubble sort mostly used?", "Teaching, and sorting tiny or nearly sorted lists",
                    ["Sorting millions of records in a big database", "Sorting the results of every web search", "Sorting huge files that do not fit in memory"],
                    "It is simple to follow but slow on big lists, so it is mainly used for teaching and tiny lists."),
}
VOCAB_QUIZ: dict[str, tuple[str, str, list[str], str]] = {
    "stack": ("What does pop do on a stack?", "It takes the top item off", ["It adds an item on the top", "It removes the bottom item", "It looks at the top item without removing it"],
              "Pop always removes the top item, the one added most recently."),
    "queue": ("What does dequeue do on a queue?", "It removes the item at the front", ["It adds an item at the back", "It removes the item at the back", "It looks at the front item without removing it"],
              "Dequeue always removes the front item, the one that waited longest."),
    "linked_list": ("What does the last node of a linked list point to?", "null, which marks the end", ["the head", "the node before it", "the next free spot in memory"],
                    "The tail's next pointer is null: there is no node after it."),
    "array": ("What index does the first item of an array have?", "0", ["1", "-1", "it has no index"], "Indexes start at 0, so the first item is at index 0."),
}


def uses_ok(structure: str, text: str) -> bool:
    u = USES.get(structure)
    return bool(u and re.search(u["pattern"], text, re.I))


def principle_ok(structure: str, text: str) -> bool:
    p = PRINCIPLE.get(structure)
    return bool(p and principle_ok_groups(p["groups"], text))


def principle_ok_groups(groups: list[str], text: str) -> bool:
    return all(re.search(g, text, re.I | re.S) for g in groups)


def undefined_jargon(texts: list[str]) -> dict[int, list[str]]:
    """Scene index -> jargon terms used there before any scene (that one included) explained them in plain words."""
    out: dict[int, list[str]] = {}
    defined: set[str] = set()
    for i, text in enumerate(texts):
        for term, (find, explain) in JARGON.items():
            explained_here = re.search(explain, text, re.I) is not None
            if re.search(find, text, re.I if term not in ("LIFO", "FIFO") else 0) and term not in defined and not explained_here:
                out.setdefault(i, []).append(term)
            if explained_here:
                defined.add(term)
    return out


STOP = set("a an the and or but so of to is are was were be been it its this that these those as we you they can also then than "
           "into by for with from at on there here what which who how when where why our your their".split())  # function words only


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


def content_words(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-z]+", text.lower()) if w not in STOP and len(w) > 1}


def overlap(a: str, b: str) -> float:
    """Jaccard similarity of content words (0 = nothing shared, 1 = same words)."""
    x, y = content_words(a), content_words(b)
    return len(x & y) / len(x | y) if x | y else 0.0


MAX_RECAP_OVERLAP = 0.5


# ---------------------------------------------------------------- the rule a demo must prove, for focused questions (how_op / why / compare)
PRINCIPLE_FOCUS: dict[tuple[str, str], dict] = {
    ("linked_list", "delete"): {"name": "rewire the previous node's pointer past the target",
                                "groups": [r"\bpoint\w*\b|\bnext\b", r"\bskip\w*\b|\bno longer\b|\bunreachable\b|\bbypass\w*\b"],
                                "proof_ops": ["delete_value"], "proof": ""},
    ("linked_list", "search"): {"name": "compare each node, follow next pointers",
                                "groups": [r"\bcompar\w*\b|\bcheck\w*\b|\bmatch\w*\b|\btarget\b", r"\bnext\b|\bpointer\w*\b|\bfollow\w*\b"],
                                "proof_ops": ["walk", "search"], "proof": "We compare each node with the target and follow the next pointer when it does not match."},
    ("linked_list", "traverse"): PRINCIPLE["linked_list"],
    ("linked_list", "insert"): {"name": "only pointers change",
                                "groups": [r"\bpoint\w*\b", r"\bno other node\b|\bnothing (?:else )?(?:moves|shifts)\b|\bonly (?:the )?pointers?\b|\brewir\w*\b"],
                                "proof_ops": ["insert_head", "insert_after", "insert_tail"], "proof": "Only pointers change: no other node moves."},
    ("linked_list", "compare"): {"name": "an array jumps, a linked list walks",
                                 "groups": [r"\bjump\w*\b|\bindex\b|\bdirect\w*\b", r"\bwalk\w*\b|\bfollow\w*\b|\bhops?\b"],
                                 "proof_ops": ["walk"], "proof": "An array could jump straight to an index, but a linked list must follow the pointers."},
    ("array", "insert"): {"name": "later items shift", "groups": [r"\bshift\w*\b"], "proof_ops": ["insert_at"], "proof": ""},
    ("array", "delete"): {"name": "later items shift", "groups": [r"\bshift\w*\b"], "proof_ops": ["delete_at"], "proof": ""},
    ("array", "access"): {**PRINCIPLE["array"], "proof": "The index lets us jump straight to that slot without looking at any other item."},
    ("array", "update"): {**PRINCIPLE["array"], "proof_ops": ["set"], "proof": "The index lets us jump straight to that slot without looking at any other item."},
    ("stack", "insert"): {"name": "the newest item leaves first", "groups": PRINCIPLE["stack"]["groups"], "proof_ops": ["push"],
                          "proof": "{value} is now the newest item, so it will be the first one out."},
    ("stack", "delete"): PRINCIPLE["stack"],
    ("stack", "peek"): {"name": "peek only looks", "groups": [r"\bwithout\b|\bstays?\b|\bunchanged\b|\bnothing (?:is )?removed\b", r"\btop\b"],
                        "proof_ops": ["peek"], "proof": "Peek only looks at the top: nothing is removed."},
    ("queue", "insert"): {"name": "new items wait behind everyone", "groups": [r"\bback\b|\bbehind\b|\bend of the line\b", r"\bafter\b|\bwait\w*\b"],
                          "proof_ops": ["enqueue"], "proof": "{value} waits behind everyone already in line, so it will leave after them."},
    ("queue", "delete"): PRINCIPLE["queue"],
    ("queue", "peek"): {"name": "peek only looks", "groups": [r"\bwithout\b|\bstays?\b|\bunchanged\b|\bnothing (?:is )?removed\b", r"\bfront\b"],
                        "proof_ops": ["peek"], "proof": "Peek only looks at the front: nothing is removed."},
}


def principle_for(structure: str, focus: str, intent: str) -> dict | None:
    """The rule this lesson's demo must prove (keyword groups, the steps that prove it, the sentence that says so)."""
    if focus in ("what_is", "bfs", "sort") or intent == "what_is":
        return PRINCIPLE.get(structure)
    return PRINCIPLE_FOCUS.get((structure, focus)) or PRINCIPLE.get(structure)


def proof_sentence(principle: dict, last: dict) -> str:
    """The rule sentence for one step, filled with that step's true values (empty if the template already says it)."""
    text = principle.get("proof") or ""
    try:
        return text.format_map({k: v for k, v in last.items() if isinstance(v, (int, str))}) if text else ""
    except (KeyError, IndexError, ValueError):
        return ""


# ---------------------------------------------------------------- BEGINNER MODE: every explanation must suit a total beginner
# ONE running analogy per structure, used in every demo scene: the step is said in analogy words first, then named.
# tag: shown on screen; words: proof that a sentence uses the analogy; picture: given to the LLM.
ANALOGY: dict[str, dict[str, str]] = {
    "stack": {"tag": "like a pile of plates", "words": r"\bplates?\b|\bpile\b",
              "picture": "a pile of plates, where you add and take plates only at the top"},
    "queue": {"tag": "like a line of people", "words": r"\bline\b|\bpeople\b|\bperson\b",
              "picture": "a line of people, where newcomers join the back and the front person leaves first"},
    "linked_list": {"tag": "like a treasure hunt of boxes", "words": r"\bbox(?:es)?\b|\bclues?\b|\btreasure\b",
                    "picture": "a treasure hunt, where each box holds a value and a note saying where the next box is"},
    "array": {"tag": "like a row of numbered lockers", "words": r"\blockers?\b",
              "picture": "a row of lockers numbered from 0, so you can walk straight to any locker"},
    "binary_tree": {"tag": "like forks in a road", "words": r"\bforks?\b|\broads?\b",
                    "picture": "a road with forks, where smaller values turn left and larger values turn right"},
    "graph_bfs": {"tag": "like a map of places and roads", "words": r"\bplaces?\b|\broads?\b|\bmap\b|\bripples?\b|\bwaiting line\b",
                  "picture": "a map of places joined by roads: from the start we visit the nearest places first, then the next ones out, like a ripple"},
    "array_2d": {"tag": "like a grid of lockers", "words": r"\blockers?\b|\bgrid\b|\bseats?\b",
                 "picture": "lockers in a grid, like seats in a cinema: pick a row, then a column"},
    "dyn_array": {"tag": "like a row of lockers", "words": r"\blockers?\b",
                  "picture": "a row of lockers: a static row is bolted down, a dynamic row moves to a bigger row when full"},
    "jagged_array": {"tag": "like rows of lockers of different lengths", "words": r"\blockers?\b|\brows?\b",
                     "picture": "rows of lockers where each row has its own length"},
    "graph_dfs": {"tag": "like exploring a maze", "words": r"\bmaze\b|\bcorridors?\b|\bto-do pile\b",
                  "picture": "exploring a maze: follow one corridor as deep as it goes, then back up and try the next"},
    "bubble_sort": {"tag": "like children lining up by height", "words": r"\bchild(?:ren)?\b|\btall\w*\b|\bheights?\b",
                    "picture": "children lining up by height, where neighbours swap places when the left one is taller"},
    "insertion_sort": {"tag": "like sorting a hand of cards", "words": r"\bcards?\b|\bhand\b",
                       "picture": "sorting a hand of cards, sliding each new card left until it fits"},
}

# Terms a total beginner does not know. Each must be explained in plain words BEFORE (or in the sentence where) it is
# first used, and never with another term from this list. term -> (pattern, case-sensitive?)
NEEDS_DEFINITION: dict[str, tuple[str, bool]] = {
    "pointer": (r"\bpointers?\b", False), "node": (r"\bnodes?\b", False), "memory": (r"\bmemory\b", False),
    "reference": (r"\breferences?\b", False), "head": (r"\bhead\b", False), "tail": (r"\btail\b", False),
    "null": (r"\bnull\b", False), "index": (r"\bindex(?:es)?\b|\bindices\b", False), "element": (r"\belements?\b", False),
    "enqueue": (r"\benqueu\w*", False), "dequeue": (r"\bdequeu\w*", False), "push": (r"\bpush(?:es|ed|ing)?\b", False),
    "pop": (r"\bpop(?:s|ped|ping)?\b", False), "peek": (r"\bpeek\w*", False), "FIFO": (r"\bFIFO\b", True), "LIFO": (r"\bLIFO\b", True),
    "traverse": (r"\btravers\w*", False), "data structure": (r"\bdata structures?\b", False), "algorithm": (r"\balgorithms?\b", False),
    "root": (r"\broot\b", False), "leaf": (r"\bleaf\b", False), "vertex": (r"\bvert(?:ex|ices)\b", False),
    "edge": (r"\bedges?\b(?![\s-]+cases?)", False), "contiguous": (r"\bcontiguous\b", False), "iterate": (r"\biterat\w*", False),
    "time complexity": (r"\b(?:time )?complexity\b", False), "Big-O": (r"\bbig[\s-]?o\b|\bO\(", False),
    "queue": (r"\bqueues?\b", False), "stack": (r"\bstacks?\b", False), "array": (r"\barrays?\b", False),
    "linked list": (r"\blinked lists?\b", False), "graph": (r"\bgraphs?\b", False),
}
SUBJECT_TERMS = {"queue": "queue", "stack": "stack", "array": "array", "linked_list": "linked list",
                 "graph_bfs": "graph", "graph_dfs": "graph"}  # the lesson's own subject is named by the question itself

# Plain words from the analogy, picture first and name second, per structure; "*" holds the defaults for any lesson.
PLAIN: dict[str, dict[str, str]] = {
    "*": {"pointer": "Each item keeps a note saying where the next item is, and that note is called a pointer.",
          "node": "A single box holding a value and a note to the next box is called a node.",
          "memory": "The computer keeps values in its storage space, which is called memory.",
          "reference": "A note that says where something is kept is called a reference.",
          "head": "The sign that shows where the first box is, is called the head.",
          "tail": "The very last box is called the tail.",
          "null": "A note that leads nowhere, marking the end, is called null.",
          "index": "The number of a position is called an index.",
          "element": "A single value stored inside is called an element.",
          "data structure": "A way to organise values in a computer is called a data structure.",
          "algorithm": "A fixed list of steps to follow is called an algorithm.",
          "traverse": "Going through every item in turn is called traversing.",
          "iterate": "Repeating a step for each item in turn is called iterating.",
          "time complexity": "How the amount of work grows as the list gets longer is called time complexity.",
          "Big-O": "A short way to write how the work grows with the number of items, n, is called Big-O.",
          "queue": "A line where the first to join is the first to leave is called a queue.",
          "stack": "A pile where the last one put on is the first taken off is called a stack.",
          "array": "A row of numbered lockers, where you can go straight to any number, is called an array.",
          "linked list": "A chain of boxes, each with a note saying where the next box is, is called a linked list.",
          "graph": "Places joined by roads are called a graph.",
          "edge": "A road joining a pair of places is called an edge.",
          "vertex": "A single place on the map is called a vertex.",
          "root": "The value at the very top, where every path starts, is called the root.",
          "leaf": "A value with nothing below it is called a leaf.",
          "contiguous": "Lockers standing side by side with no gaps are called contiguous.",
          "enqueue": "Joining the back of the line is called enqueue.",
          "dequeue": "Leaving from the front of the line is called dequeue.",
          "push": "Putting a new one on top is called push.",
          "pop": "Taking the top item off is called pop.",
          "peek": "Looking at the next one without removing it is called peek.",
          "FIFO": "The first one in is the first one out, like a real line, and this is called FIFO.",
          "LIFO": "The last one in is the first one out, like a pile of plates, and this is called LIFO."},
    "stack": {"push": "Putting a new plate on top of the pile is called push.", "pop": "Taking the top plate off the pile is called pop.",
              "peek": "Looking at the top plate without taking it off is called peek."},
    "queue": {"peek": "Looking at the front person without removing them is called peek."},
    "linked_list": {"pointer": "Each box holds a note saying where the next box is, and that note is called a pointer.",
                    "node": "A single box, holding a value and a note, is called a node.",
                    "null": "The last box's note leads nowhere, and that empty note is called null.",
                    "memory": "Boxes can sit anywhere in the computer's storage space, which is called memory."},
    "array": {"index": "The number on each locker is called an index.",
              "element": "The value inside a locker is called an element.",
              "memory": "The lockers stand side by side in the computer's storage space, which is called memory."},
    "graph_bfs": {"queue": "The places waiting their turn form a waiting line, which is called a queue.",
                  "node": "A single place on the map is called a node."},
    "graph_dfs": {"stack": "The places waiting their turn form a to-do pile, which is called a stack.",
                  "push": "Putting a place on top of the to-do pile is called push.", "pop": "Taking the top place off the pile is called pop.",
                  "node": "A single place on the map is called a node."},
    "binary_tree": {"node": "A single stop on the road, holding a value, is called a node."},
}

# A key term from the question is also said by its everyday word (beginner lessons use the plain word on purpose)
KEY_TERM_PLAIN: dict[str, str] = {
    "element": r"\belements?\b|\bvalues?\b|\bitems?\b", "elements": r"\belements?\b|\bvalues?\b|\bitems?\b",
    "node": r"\bnodes?\b|\bbox(?:es)?\b", "nodes": r"\bnodes?\b|\bbox(?:es)?\b",
    "pointer": r"\bpointers?\b|\bnotes?\b", "pointers": r"\bpointers?\b|\bnotes?\b",
    "index": r"\bindex(?:es)?\b|\bpositions?\b|\blocker numbers?\b", "memory": r"\bmemory\b|\bstorage\b",
    "vertex": r"\bvert(?:ex|ices)\b|\bplaces?\b|\bnodes?\b", "edge": r"\bedges?\b|\broads?\b",
    "head": r"\bhead\b|\bfirst box\b", "insertion": r"\binsert\w*|\badd\w*|\bput\w*|\bsqueez\w*",
    "bfs": r"\bbfs\b|\bbreadth[- ]first\b", "dfs": r"\bdfs\b|\bdepth[- ]first\b",
}

# what a short name stands for, so a lesson that never said it can say it plainly (never "This is about the BFS.")
SHORT_NAMES = {"bfs": "breadth first search", "dfs": "depth first search", "bst": "binary search tree",
               "fifo": "first in, first out", "lifo": "last in, first out"}


def name_sentence(term: str, structure: str | None) -> str:
    """A plain sentence that introduces a key term the lesson never said."""
    d = plain_definition(term, structure)
    if d:
        return d
    full = SHORT_NAMES.get(term.lower())
    if full:
        return f"The way we just explored has a short name: {term}, which stands for {full}." if term.lower() in ("bfs", "dfs") \
            else f"{term} stands for {full}."
    return f"What we just saw has a name: {term}."

FILLER = (r"\b(?:extremely|incredibly|instantly|instant|seamless\w*|robust\w*|leverag\w*|effortless\w*|blazing\w*|"
          r"lightning[- ]fast|super[- ]fast|magic\w*|powerful)\b")

# WHY questions: the problem first (what is hard without the structure, on a real alternative), then the fix (real steps).
# The ops builders take the lesson's values and a fresh value; narration is written later from the true states.
WHY: dict[str, dict] = {
    "linked_list": {"alt": "array",
                    "problem": "In an array, putting a value in the middle forces every later value to shift over by one place.",
                    "fix": "In a linked list, putting a value in the middle changes only a couple of notes, and no other box moves.",
                    "problem_ops": lambda v, new: [("init", list(v)), ("insert_at", [1, new])],
                    "fix_ops": lambda v, new: [("insert_after", [v[0], new])]},
    "array": {"alt": "linked_list",
              "problem": "In a linked list, reaching the last value means following every note in order, starting from the first box.",
              "fix": "In an array, every locker has a number, so we go straight to the last one in a single step.",
              "problem_ops": lambda v, new: [("init", list(v)), *(("walk", [x]) for x in v)],
              "fix_ops": lambda v, new: [("get", [len(v) - 1])]},
    "queue": {"alt": "stack",
              "problem": "With a pile, the person who arrived last would be served first, which is unfair to the one who waited longest.",
              "fix": "With a line, the person who arrived first is served first, so nobody is skipped.",
              "problem_ops": lambda v, new: [("init", list(v)), ("pop", [])],
              "fix_ops": lambda v, new: [("dequeue", [])]},
    "stack": {"alt": "queue",
              "problem": "If undo used a line, it would undo your oldest change first instead of your newest change.",
              "fix": "With a pile, the newest change is on top, so undo takes back the newest change first.",
              "problem_ops": lambda v, new: [("init", list(v)), ("dequeue", [])],
              "fix_ops": lambda v, new: [("pop", [])]},
}
WHY_QUESTION = (r"\bwhy\b|\bwhat (?:is it|are they|is an? \w+(?: \w+)?) (?:used )?for\b|\bbenefits?\b|\badvantages?\b|\bpoint of\b"
                r"|\bwhen (?:should|would|do|to) (?:i |we |you )?use\b")


def analogy_for(structure: str | None) -> dict | None:
    return ANALOGY.get(structure or "")


def plain_definition(term: str, structure: str | None) -> str:
    return PLAIN.get(structure or "", {}).get(term) or PLAIN["*"].get(term, "")


# LIST questions ("how many types of array", "kinds of linked list"): the well-known kinds of each structure. Domain
# knowledge, like the glossary, not a rule for one question: the analysis call names the items, code validates them
# against this list and fills in any it missed. Each kind has a plain line (picture first, NO numbers or number words,
# since narration numbers must be facts) and real ops that build it, on its own structure kind when it needs a new view.
VARIANTS: dict[str, list[dict]] = {
    "array": [
        {"name": "1D array", "pattern": r"\b1-?d\b|\bone[- ]dimension\w*|\bsingle[- ]dimension\w*|\blinear arrays?\b|\bsimple arrays?\b",
         "line": "A 1D array is a single row of lockers, each with its own number.",
         "structure": "array", "build": [("reset", []), ("init", [10, 20, 30, 40])], "demo": [("get", [2])]},
        {"name": "2D array", "pattern": r"\b2-?d\b|\btwo[- ]dimension\w*|\bmulti[- ]?dimension\w*|\bmatri(?:x|ces)\b|\bgrids?\b",
         "line": "A 2D array is a grid of lockers in rows and columns, like seats in a cinema.",
         "structure": "array_2d", "build": [("reset", []), ("grid", [2, 3, 10, 20, 30, 40, 50, 60])], "demo": [("get2", [1, 2])]},
        {"name": "static array", "pattern": r"\bstatic\b|\bfixed[- ](?:size|length)\w*",
         "line": "A static array has a fixed number of lockers, so when it is full there is no room for more.",
         "structure": "dyn_array", "build": [("reset", []), ("init_static", [4, 10, 20, 30, 40])], "demo": [("append", [50])]},
        {"name": "dynamic array", "pattern": r"\bdynamic\b|\bresizable\b|\bgrowable\b|\bvectors?\b|\barraylists?\b",
         "line": "A dynamic array can grow: when it is full, it moves everything into a bigger row.",
         "structure": "dyn_array", "build": [("reset", []), ("init_dynamic", [4, 10, 20, 30, 40])], "demo": [("append", [50])]},
        {"name": "jagged array", "pattern": r"\bjagged\b|\bragged\b",
         "line": "A jagged array is rows of lockers where each row can have a different length.",
         "structure": "jagged_array", "build": [("reset", []), ("row", [10, 20, 30]), ("row", [40]), ("row", [50, 60])], "demo": []},
    ],
    "linked_list": [
        {"name": "singly linked list", "pattern": r"\bsingly\b|\bsingle[- ]linked\b",
         "line": "In a singly linked list, each box has a note pointing forward to the next box.",
         "structure": "linked_list", "build": [("reset", []), ("init", [10, 20, 30]), ("variant", ["singly"])], "demo": []},
        {"name": "doubly linked list", "pattern": r"\bdoubly\b|\bdouble[- ]linked\b",
         "line": "In a doubly linked list, each box has a note forward and a note back.",
         "structure": "linked_list", "build": [("reset", []), ("init", [10, 20, 30]), ("variant", ["doubly"])], "demo": []},
        {"name": "circular linked list", "pattern": r"\bcircular\b",
         "line": "In a circular linked list, the last box points back to the first box.",
         "structure": "linked_list", "build": [("reset", []), ("init", [10, 20, 30]), ("variant", ["circular"])], "demo": []},
    ],
    "queue": [
        {"name": "simple queue", "pattern": r"\bsimple\b|\blinear queues?\b|\bordinary\b|\bnormal queues?\b",
         "line": "A simple queue is an ordinary line: people join at the back and leave from the front.",
         "structure": "queue", "build": [("reset", []), ("init", [10, 20, 30]), ("variant", ["simple"])], "demo": []},
        {"name": "circular queue", "pattern": r"\bcircular\b|\bring buffer\b",
         "line": "A circular queue is a ring of seats, where the back wraps round to the front.",
         "structure": "queue", "build": [("reset", []), ("init", [10, 20, 30]), ("variant", ["circular"])], "demo": []},
        {"name": "priority queue", "pattern": r"\bpriority\b",
         "line": "A priority queue serves the most important person first, not the one who came first.",
         "structure": "queue", "build": [("reset", []), ("variant", ["priority"]), ("init", [20, 30])], "demo": [("enqueue", [10])]},
        {"name": "deque", "pattern": r"\bdeques?\b|\bdouble[- ]ended\b",
         "line": "A deque, a double-ended queue, lets people join and leave at both ends.",
         "structure": "queue", "build": [("reset", []), ("variant", ["deque"]), ("init", [10, 20])], "demo": [("push_front", [5])]},
    ],
    "binary_tree": [
        {"name": "perfect binary tree", "pattern": r"\bperfect\b|\bfull\b",
         "line": "A perfect binary tree has every fork filled, so each level is complete.",
         "structure": "binary_tree", "build": [("reset", []), ("init", [50, 30, 70, 20, 40, 60, 80])], "demo": []},
        {"name": "complete binary tree", "pattern": r"\bcomplete\b",
         "line": "A complete binary tree fills each level from the left before starting the next level.",
         "structure": "binary_tree", "build": [("reset", []), ("init", [50, 30, 70, 20])], "demo": []},
        {"name": "skewed binary tree", "pattern": r"\bskewed\b|\bdegenerate\b|\bunbalanced\b",
         "line": "A skewed binary tree leans to one side, like a long road with no other turns.",
         "structure": "binary_tree", "build": [("reset", []), ("init", [10, 20, 30, 40])], "demo": []},
    ],
}


def variants_for(structure: str | None) -> list[dict]:
    return VARIANTS.get(structure or "", [])


# COMPARE / WHEN-TO-USE questions: when each structure is the right choice, in plain words (no numbers). Used to build the
# verdict ("use X when ..., use Y when ...") when the lesson has none.
USE_WHEN = {
    "array": "you need to jump straight to any position",
    "linked_list": "you add and remove items in the middle often",
    "stack": "the newest item must come out first, like undo",
    "queue": "the oldest item must come out first, like a waiting line",
    "binary_tree": "you need to find values quickly and keep them in order",
    "graph_bfs": "you need the shortest route, counted in steps",
    "graph_dfs": "you want to follow one path all the way, like solving a maze",
    "bubble_sort": "the list is tiny or you are learning how sorting works",
    "insertion_sort": "the list is small or already almost sorted",
    "dyn_array": "you do not know in advance how many items you will store",
}


# COMPARE questions: what sets each structure apart, in plain words (no numbers), for the recap of a comparison.
COMPARE_DIFF = {
    "stack": "takes out the newest item first",
    "queue": "takes out the oldest item first",
    "array": "jumps straight to any position, but must shift items to insert",
    "linked_list": "walks from the start, but inserts by changing a single note",
    "graph_bfs": "visits the nearest places first",
    "graph_dfs": "follows one path as deep as it goes first",
    "bubble_sort": "swaps neighbours pass after pass",
    "insertion_sort": "slides each new item into its place",
}
