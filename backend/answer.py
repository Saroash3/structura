"""Question-driven lessons: answer ANY question about data structures or algorithms, without a special case per question type.

PRIORITY RULE: the answer to the user's exact question comes first. Diagrams, animation and demos exist only to support
that answer. A lesson that does not answer the question is a failed lesson, even if every sentence is verified.

Pipeline (at most 3 LLM calls for a new lesson; cached prompts cost nothing):
  1. ONE call: question analysis + plan. The LLM restates the question, lists 3-6 answer REQUIREMENTS derived from it,
     says what EVIDENCE each needs (trace | count | table | compare | state | none), names key terms and jargon, then plans
     answer points (one per requirement, in teaching order) and scenes (one point each) with the ops that compute the evidence.
  2. Code normalises the plan, generically: invalid ops are dropped, unmapped scenes are rejected, runs are completed (no
     demo cut off mid-algorithm), and a requirement whose evidence is missing gets a scene built by an evidence builder
     (count -> a full counted run, table -> a growth table, compare -> a second run, trace/state -> a run of the subject).
     Every number then comes from the real structures; the verifier checks every sentence (one batched repair call).
  3. ANSWER-COVERAGE GATE: deterministic (every requirement covered, key terms said, no unmapped scene), then ONE judge
     call at temperature 0 that also rewrites the scenes of any uncovered requirement. Rewrites are verified like any
     narration. If the lesson still does not answer the question, the user gets an honest notice (NotAnswered).
"""
from __future__ import annotations

import copy
import json
import re

import complexity
import llm
from focus import UnsupportedTopic
from structures import ALLOWED_OPS, OpError, make
from topic_parser import GivenData
from verifier import answer_missing, check_scene, simulate

EVIDENCE = ("trace", "count", "table", "compare", "state", "none")
SHAPES = ("list", "compare", "why", "how", "complexity", "definition", "when", "misconception", "multipart", "data", "vague")
SUBJECTS = [s for s in ALLOWED_OPS if s != "growth"]
INTRO, RECAP = "intro", "recap"
SORTS, GRAPHS = ("bubble_sort", "insertion_sort"), ("graph_bfs", "graph_dfs")


class NotAnswered(UnsupportedTopic):
    """The lesson could not be made to answer the question; the user sees this honest notice instead of a bad lesson."""


OPS_HELP = {
    "array": "init [v1, v2, ...] (once, on an empty array); append [value]; insert_at [index, value] (shifts later items right); "
             "delete_at [index] (shifts later items left); set [index, value]; get [index] (touches 1 item); scan [target] "
             "(linear search: compares the NEXT index with target, one comparison per op; repeat until found or the end). reset [].",
    "array_2d": "a 2D array (grid): grid [rows, cols, v1, v2, ...] (row by row); get2 [row, col]; set2 [row, col, value]; reset [].",
    "dyn_array": "static vs dynamic array (a vector / ArrayList is a dynamic array): init_static [capacity, v1, ...] or "
                 "init_dynamic [capacity, v1, ...]; append [value] (a full static array refuses it; a full dynamic array moves to "
                 "a block twice as big, copying every value, and the counts are recorded); get [index]; reset [].",
    "jagged_array": "a jagged array: row [v1, ...] adds a row of any length; get2 [row, col]; reset [].",
    "queue": "init [v1, ...] (front first); enqueue [value]; dequeue []; peek []; variant [\"simple\"|\"circular\"|\"priority\"|\"deque\"] "
             "(priority: the smallest value is served first; deque: also push_front [value] and pop_back []); reset [].",
    "stack": "init [v1, ...] (bottom first); push [value]; pop []; peek [].",
    "linked_list": "init [v1, ...] builds the whole list; walk [value] moves the current pointer ONE hop (onto the head first, "
                   "then the next node each time; each walk is one comparison); insert_head [value]; insert_tail [value]; "
                   "insert_after [target, value]; delete_value [value]; search [value]; variant [\"singly\"|\"doubly\"|\"circular\"] "
                   "(how the boxes point: forward only, both ways, or the tail back to the head); reset [].",
    "binary_tree": "init [v1, ...] inserts in order; insert_bst [value]; search_bst [value] (must exist).",
    "graph_bfs": "labels are strings. add_edge [u, v] for every edge (all in ONE scene), start_bfs [start], then visit [] once per "
                 "reachable node (dequeues the front, enqueues unvisited neighbours alphabetically). reset [] starts a new graph. "
                 "States count visits and neighbour checks.",
    "graph_dfs": "same graph ops, but start_dfs [start] and a STACK: visit [] pops the top and pushes unvisited neighbours. "
                 "reset [] starts a new graph. States count visits and neighbour checks.",
    "bubble_sort": "load [v1, ...] once (4 or 5 values), then step [] repeatedly (compares the next adjacent pair, swaps if out of "
                   "order). reload [v1, ...] starts a fresh run (best/worst case). States count comparisons per pass.",
    "insertion_sort": "load [v1, ...] once, then step [] repeatedly (compares the item being inserted with its left neighbour, "
                      "swaps if smaller). reload [v1, ...] starts a fresh run. States count comparisons per inserted item.",
    "growth": "a table of REAL counts for growing n: one op named after the algorithm, args the sizes, e.g. bubble_sort [4, 8, 16, 100]. "
              f"Algorithms: {', '.join(complexity.ALGOS)}.",
}

SCHEMA = {"type": "object", "properties": {
    "unsupported": {"type": "boolean"},
    "closest": {"type": "array", "items": {"type": "string"}},
    "topic": {"type": "string"},
    "structure": {"type": "string"},
    "analysis": {"type": "object", "properties": {
        "subject": {"type": "string"}, "ask": {"type": "string"},
        "key_terms": {"type": "array", "items": {"type": "string"}},
        "jargon": {"type": "array", "items": {"type": "object", "properties": {
            "term": {"type": "string"}, "plain": {"type": "string"}}, "required": ["term", "plain"]}},
        "partial": {"type": "boolean"},
        "shape": {"type": "string", "enum": list(SHAPES)},
        "items": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "line": {"type": "string"}}, "required": ["name", "line"]}},
        "sides": {"type": "array", "items": {"type": "string"}},
        "premise_correct": {"type": "boolean"},
        "parts": {"type": "array", "items": {"type": "string"}},
        "clarify": {"type": "string"},
        "requirements": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "text": {"type": "string"},
            "evidence": {"type": "string", "enum": list(EVIDENCE)}, "evidence_detail": {"type": "string"},
            "algorithm": {"type": "string"}, "structure": {"type": "string"}}, "required": ["id", "text", "evidence"]}}},
        "required": ["subject", "ask", "key_terms", "requirements"]},
    "answer_points": {"type": "array", "items": {"type": "object", "properties": {
        "id": {"type": "string"}, "requirement_id": {"type": "string"}, "kind": {"type": "string"}, "point": {"type": "string"},
        "visual": {"type": "string"}}, "required": ["id", "requirement_id", "point"]}},
    "scenes": {"type": "array", "items": {"type": "object", "properties": {
        "point_id": {"type": "string"}, "role": {"type": "string", "enum": ["setup", "core", "edge_case", "recap"]},
        "structure": {"type": "string"}, "visual": {"type": "string"},
        "ops": {"type": "array", "items": {"type": "object", "properties": {
            "op": {"type": "string"}, "args": {"type": "array", "items": {"type": ["integer", "string"]}}}, "required": ["op", "args"]}},
        "narration": {"type": "string"}}, "required": ["point_id", "role", "ops", "narration"]}}},
    "required": ["analysis", "answer_points", "scenes"]}


def _guess_subjects(topic: str) -> list[str]:
    """Structures the question seems to mention (only to pick which analogies and glossary go into the prompt)."""
    pats = {"stack": r"\bstacks?\b|\bpush|\bpop\b|\blifo\b", "queue": r"\bqueues?\b|\benqueue|\bdequeue|\bfifo\b",
            "linked_list": r"\blinked\b|\bnodes?\b|\bpointers?\b", "array": r"\barrays?\b|\blinear search\b",
            "binary_tree": r"\btrees?\b|\bbst\b", "graph_bfs": r"\bbfs\b|\bbreadth\b|\bgraph", "graph_dfs": r"\bdfs\b|\bdepth\b",
            "bubble_sort": r"\bbubble\b", "insertion_sort": r"\binsertion\b"}
    return [s for s, p in pats.items() if re.search(p, topic, re.I)] or list(pats)


def style_guide(topic: str) -> str:
    """BEGINNER STYLE GUIDE: shared by the plan prompt, the repair prompt and the judge."""
    from concepts import ANALOGY, PLAIN, plain_definition
    subjects = _guess_subjects(topic)
    analogies = "\n".join(f"  {s}: {ANALOGY[s]['picture']}" for s in subjects if s in ANALOGY)
    relevant = {"stack": ["push", "pop", "peek", "LIFO"], "queue": ["enqueue", "dequeue", "peek", "FIFO"],
                "linked_list": ["node", "pointer", "head", "null", "memory"], "array": ["index", "element", "memory"],
                "binary_tree": ["root", "leaf", "node"], "graph_bfs": ["node", "edge", "queue"], "graph_dfs": ["node", "edge", "stack", "push", "pop"],
                "bubble_sort": ["algorithm"], "insertion_sort": ["algorithm"]}
    terms = list(dict.fromkeys(t for s in subjects for t in relevant.get(s, [])))
    glossary = "\n".join(f"  {t}: \"{plain_definition(t, next((s for s in subjects if t in PLAIN.get(s, {})), None))}\"" for t in terms)
    return f"""BEGINNER STYLE GUIDE (the learner is a total beginner who has never programmed; teach slowly and simply):
- One new idea per scene. At most 2 short sentences per scene, about 20 words each (never more than 25). If a scene would
  teach two ideas, make two scenes.
- Everyday words. Describe things the learner can picture. Never define a term with another undefined term.
- Picture first, name second: describe the thing in everyday words, THEN say "this is called X". Never open with a term.
- Keep ONE running analogy for the whole lesson and use it in EVERY demo scene: say the step in analogy words first, then
  give the technical name, then the values. Example: "A new person, 40, joins the back of the line, and we call this
  enqueue. 40 waits behind everyone else, so 10 is still at the front." Use exactly this analogy for the structure
  (never swap it for another picture, such as mailboxes for an array):
{analogies}
- Explain terms with these plain definitions (from the analogy), at or before first use:
{glossary}
  Explain only the words you actually use. Never add a scene just to define a word, and avoid textbook words
  ("data structure", "element", "memory") when an everyday word works. FIFO or LIFO only AFTER the demo, as
  "first in, first out, like a real line".
- If the question asks WHY (or what it is for), show the PROBLEM first: what is hard without the structure, on a real
  alternative with real steps (e.g. an array must shift every later value to insert in the middle), then show how the
  structure avoids it, with its real steps. Point kinds "problem" then "fix".
- Never use filler or marketing words: extremely, efficient(ly) without showing why, instantly, seamlessly, robust, leverages.
- Never say a word twice in a row ("constant time time"). Only name what the viewer can SEE in that scene's picture: say
  "root", "leaf", "head" or "tail" only in a scene whose picture shows that part (the stage highlights it).
- Linked lists for beginners: "box 20's note now points to box 40, so box 30 is skipped"; the boxes now go 10, 20, 40.
"""


# ---------------------------------------------------------------- question shape (what the ANSWER must contain)
SHAPE_HINT = {
    "list": "name EVERY item of the list, one scene each with one plain line and a small visual, and a recap that restates the names",
    "compare": "both sides on the same axes, side by side, ending with a verdict: \"use X when ..., use Y when ...\"",
    "why": "show the problem first, then the cause, with real counts or steps",
    "how": "ordered steps, with the true state after each step",
    "complexity": "count the real steps (counters, a tally per step, a growth table), derive the formula, then say the Big-O in plain words",
    "definition": "plain definition, the analogy, the key rule, a short demo that proves the rule, where it is used, recap",
    "when": "the deciding criteria first, then a recommendation for each case with a tiny real example",
    "misconception": "say clearly whether the premise is right or wrong, then show the real behaviour with real steps",
    "multipart": "split into the sub-questions (parts) and answer each in order, naming each part in the narration",
    "data": "use exactly the user's values, in order",
    "vague": "do not build a lesson: return one short clarifying question in \"clarify\"",
}
_STRUCTURE_WORDS = (r"\barrays?\b|\bvectors?\b|\barraylists?\b|\blists?\b|\bqueues?\b|\bdeques?\b|\bstacks?\b|\btrees?\b|\bbsts?\b|"
                    r"\bgraphs?\b|\bbfs\b|\bdfs\b|\bsort\w*|\bsearch\w*|\bnodes?\b|\bpointers?\b|\bhash\w*|\bheaps?\b|\btries?\b|\btrie\b|"
                    r"\bcomplexit\w*|\bbig[\s-]*o\b|\bO\(|\balgorithm\w*|\bdata structures?\b|\brecursion\b|\bmatri\w*")
SHAPE_RX = [  # checked in order; generic question forms, never a rule for one question
    ("list", r"\b(?:types?|kinds?|sorts?|varieties|variants|categories|forms|flavou?rs)\s+of\b|\bhow many (?:types|kinds|sorts|ways)\b|"
             r"\bways (?:to|of)\b|\blist (?:the|all)\b|\bexamples of\b"),
    ("compare", r"\bvs\.?\b|\bversus\b|\bdifferen\w* between\b|\bcompar\w*|\bbetter than\b|\binstead of\b|\bor an? \w+\s*\?$"),
    ("misconception", r"^\s*(?:is|are|isn't|aren't|does|doesn't|do|can|can't)\b[^?]*\b(?:O\(|always|never|faster|slower|constant|linear|"
                      r"quadratic|instant\w*|free|same|only)\b"),
    ("complexity", r"\bcomplexit\w*|\bbig[\s-]*o\b|\bO\s*\(|\bhow (?:fast|slow|efficient)\b|\bruntime\b|\brunning time\b"),
    ("when", r"\bwhen (?:should|to|would|do|can) (?:i|we|you|one)\b|\bwhen to use\b|\bwhich (?:one )?(?:is|should)\b|\bshould i use\b|"
             r"\bbest (?:for|choice|structure)\b"),
    ("why", r"^\s*why\b|\bhow come\b|\bwhat makes\b"),
    ("multipart", r"\b(?:and|also) (?:why|how|when|what)\b|\?\s*\w.*\?"),
    ("how", r"^\s*(?:how (?:do|does|to|can|is|are)|show|trace|walk me through|demonstrate|step)\b|\bstep[\s-]by[\s-]step\b"),
    ("definition", r"^\s*(?:what (?:is|are|'s)|what's|define|explain|describe|tell me about|meaning of)\b"),
]


def question_shape(topic: str, given: GivenData | None = None) -> str:
    """What the answer must contain, from the question's form (the analysis call says the same; code validates it)."""
    t = (topic or "").strip()
    words = re.findall(r"[A-Za-z0-9']+", t)
    if len(words) <= 1 or (len(words) <= 3 and not re.search(_STRUCTURE_WORDS, t, re.I)):
        return "vague"
    for shape, rx in SHAPE_RX:
        if re.search(rx, t, re.I):
            if shape in ("how", "definition") and given is not None and (given.values or given.edges):
                return "data"
            return shape
    if given is not None and (given.values or given.edges):
        return "data"
    return "definition" if re.search(_STRUCTURE_WORDS, t, re.I) else "vague"


class NeedsClarification(ValueError):
    """The question is too vague to answer: the UI asks this short question instead of building a lesson."""


CLARIFY = ("Which data structure or algorithm do you mean, and what would you like to know about it? For example: "
           "\"how does a queue work\" or \"types of linked list\".")


def subject_from_text(topic: str) -> str | None:
    """The supported structure a question names, if any (vectors and ArrayLists are dynamic arrays)."""
    for s, rx in (("linked_list", r"\blinked[\s-]*lists?\b|\bsingly\b|\bdoubly\b"), ("binary_tree", r"\bbsts?\b|\bbinary\b|\btrees?\b"),
                  ("graph_dfs", r"\bdfs\b|\bdepth[\s-]*first\b"), ("graph_bfs", r"\bbfs\b|\bbreadth[\s-]*first\b|\bgraphs?\b"),
                  ("bubble_sort", r"\bbubble\b"), ("insertion_sort", r"\binsertion sort\b"),
                  ("queue", r"\bqueues?\b|\bdeques?\b|\bfifo\b"), ("stack", r"\bstacks?\b|\blifo\b"),
                  ("array", r"\barrays?\b|\bvectors?\b|\barraylists?\b|\blinear search\b")):
        if re.search(rx, topic or "", re.I):
            return s
    return None


def list_items(subject: str, raw_items, topic: str = "") -> list[dict]:
    """The items a LIST answer must name: the analysis call's items, checked against the known kinds of the structure
    (concepts.VARIANTS). Known kinds the LLM missed are added; an unknown item the LLM named is kept (shown in words only)."""
    from concepts import variants_for
    known = variants_for(subject)
    names = [str(x.get("name") if isinstance(x, dict) else x).strip() for x in (raw_items or []) if x]
    lines = {str(x.get("name")).strip(): str(x.get("line") or "").strip() for x in (raw_items or []) if isinstance(x, dict) and x.get("name")}
    out, used = [], set()
    for v in known:  # in the known teaching order
        out.append({**v, "line": v["line"]})
        used.add(v["name"])
    for n in names:  # the LLM's own items that are none of the known kinds (e.g. "sparse array"): words only
        if n and not any(re.search(v["pattern"], n, re.I) or n.lower() == v["name"].lower() for v in known):
            line = lines.get(n) or ""
            if line and re.search(re.escape(n.split()[0]), line, re.I):
                out.append({"name": n, "pattern": r"\b" + r"\w*[\s-]+".join(map(re.escape, n.split())) + r"\w*", "line": line,
                            "structure": None, "build": [], "demo": []})
    return out[:6]


def compare_sides(topic: str) -> list[str]:
    """The two things a COMPARE question names ("X vs Y", "difference between X and Y")."""
    t = re.sub(r"[?.!]+$", "", topic or "").strip()
    m = (re.search(r"between\s+(?:an?\s+|the\s+)?(.+?)\s+and\s+(?:an?\s+|the\s+)?(.+)$", t, re.I)
         or re.search(r"(?:^|\b)(?:an?\s+|the\s+)?([\w\s-]+?)\s+(?:vs\.?|versus|or|compared to|instead of|better than)\s+(?:an?\s+|the\s+)?([\w\s-]+)$", t, re.I))
    if not m:
        return []
    clean = lambda x: re.sub(r"^(?:compare|what is|use|should i use|when should i use)\s+(?:an?\s+|the\s+)?", "", x.strip(), flags=re.I).strip()
    return [clean(m.group(1)), clean(m.group(2))]


def _side_pattern(side: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", side.lower()) if w not in ("a", "an", "the")]
    if not words:
        return r"^$"
    syn = {"bfs": r"bfs|breadth[\s-]*first", "dfs": r"dfs|depth[\s-]*first", "bst": r"bsts?|binary search trees?"}
    if len(words) == 1 and words[0] in syn:
        return rf"\b(?:{syn[words[0]]})\b"
    return r"\b" + r"\w*[\s-]+".join(map(re.escape, words)) + r"\w*"


def item_text(item: dict, state: dict) -> str:
    """An item scene's narration: the plain line, plus the values its picture shows (a build names every starting value)."""
    vals = []
    for op, args in item.get("build", []):
        if op in ("init", "init_static", "init_dynamic"):
            vals = args[1:] if op != "init" else args
        elif op == "grid":
            vals = args[2:]
        elif op == "row":
            vals = vals + args
    if not vals:
        return item["line"]
    vs = [str(v) for v in vals]
    return f"{item['line']} Here it holds {', '.join(vs[:-1]) + ' and ' + vs[-1] if len(vs) > 1 else vs[0]}."


def list_plan(topic: str, subject: str, items: list[dict], a: dict, raw_scenes: list[dict]) -> tuple[list, list, list]:
    """(requirements, answer points, scenes) for a LIST question: one requirement and one scene per item (its own small
    visual, built by real ops), plus a demo scene where an item's behaviour is the point (a static array refusing a value,
    a dynamic array doubling and copying). The LLM's narration for an item is kept when it names the item."""
    reqs, points, scenes = [], [], []
    for k, it in enumerate(items, 1):
        rid, pid = f"r_item{k}", f"p_item{k}"
        reqs.append({"id": rid, "text": f"names the {it['name']}: {it['line']}", "evidence": "state" if it.get("build") else "none",
                     "evidence_detail": "", "algorithm": "", "structure": it.get("structure") or subject, "item": it["name"]})
        points.append({"id": pid, "requirement_id": rid, "kind": "item", "point": it["line"], "visual": "highlight", "item": it["name"]})
        llm_text = next((str(s.get("narration") or "") for s in raw_scenes if isinstance(s, dict)
                         and re.search(it["pattern"], str(s.get("narration") or ""), re.I)), "")
        kind = it.get("structure") or subject
        sc = {"ops": [{"op": o, "args": list(x)} for o, x in it.get("build", [])], "narration": llm_text.strip() or "-",
              "role": "core", "point_id": pid, "item": it["name"], "line": it["line"]}
        if kind != subject:
            sc["structure"] = kind
        if not it.get("build"):
            sc["ops"] = []
            sc["note"] = "this kind is explained in words only: there is no picture of it in this lesson"
        scenes.append(sc)
        if it.get("demo"):
            demo = {"ops": [{"op": o, "args": list(x)} for o, x in it["demo"]], "narration": "-", "role": "core", "point_id": pid,
                    "item": it["name"]}
            if kind != subject:
                demo["structure"] = kind
            scenes.append(demo)
    return reqs, points, scenes


def _join_names(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def prompt(topic: str, level: str, given: GivenData) -> str:
    from planner import given_prompt
    ops = "\n".join(f"- {s}: {h}" for s, h in OPS_HELP.items())
    shapes = "\n".join(f"  {k}: {v}" for k, v in SHAPE_HINT.items())
    return f"""You are a teacher planning a short animated lesson that ANSWERS one student question about data structures or algorithms.
Question from the user: "{topic}"
Audience: {level} ({"a total beginner: plain words, every new term explained, see the style guide" if level == "beginner" else "precise terms, short technical sentences"}).
{style_guide(topic) if level == "beginner" else ""}{given_prompt(given)}
STEP 1, analyse THE QUESTION (not the topic in general):
- shape: what the ANSWER must contain, from the form of the question (not from the structure's name):
{shapes}
  Code checks your shape against the question's wording.
- subject: the structure or algorithm it is about, one of {SUBJECTS}. A comparison names the first one; scenes about the
  other set their own "structure". Questions about the KINDS, TYPES or VARIANTS of a supported structure ARE supported:
  types of array (1D, 2D, static, dynamic, jagged; scene structures array_2d, dyn_array, jagged_array), types of linked list
  (singly, doubly, circular: variant op), types of queue (simple, circular, priority, deque: variant op). A vector or an
  ArrayList is a dynamic array (subject array, scenes on dyn_array). Only if the question is about a structure or algorithm
  that is not in that list (hash maps, heaps, tries, AVL trees, quicksort, merge sort, Dijkstra, ...), return only
  {{"unsupported": true, "closest": [up to 3 supported topics nearest to it]}}.
- items (shape list): EVERY item of the list the answer must name, each with "line": one plain-words sentence naming it.
- sides (shape compare or when): the two things compared, in the question's words.
- premise_correct (shape misconception): true if the question's claim is right, false if it is wrong.
- parts (shape multipart): the sub-questions, in order.
- clarify (shape vague): one short question to ask the user instead of a lesson.
- ask: the question restated in one plain sentence.
- requirements: 3 to 6 concrete things a correct answer to THIS question must contain. Example for "why is bubble sort O(n^2)":
  "counts the comparisons in each pass", "adds them up to n(n-1)/2", "states O(n^2) and what it means", "best versus worst case".
  Example for "delete a node from the middle of a linked list": "walk to the node before the target", "point its next pointer past
  the target", "the target is skipped and the chain stays whole", "edge case: deleting the head".
  If the question asks WHY or HOW MUCH, the requirements include the reasoning that proves the answer, not only the claim.
  A Big-O answer needs: what is counted and why, the count on a real run, the formula derived from the real counts (a sum
  such as 3 + 2 + 1 = 6 = n(n-1)/2), what it means when n doubles, and best versus worst case when they differ.
  A comparison ("difference between", "X vs Y", "when to use") runs BOTH on the same input, side by side, and has a
  requirement that names the concrete difference that shows (e.g. the two visit orders), plus when to choose each.
- evidence per requirement: what real code must compute to prove it: trace (run ops, show the states), count (count the work of
  a full run), table (real counts for growing n), compare (two runs or two structures side by side), state (one before/after
  state) or none (purely conceptual). algorithm: for count/table, which one ({", ".join(complexity.ALGOS)}).
- key_terms: 1 to 4 words or symbols from the question the answer must use, e.g. "time complexity", "O(", "delete".
- jargon: words a beginner needs defined, each with a plain-words definition ("plain"); the narration explains each one in
  plain words where it is first used, picture first (e.g. "We take the top plate off, and we call this pop.").
- partial: true only if the question is about one single step, not a whole run.
STEP 2, answer_points: one per requirement (requirement_id), in teaching order: the plain-words answer first, then the proof,
then what it means, then an edge case if the question needs one.
STEP 3, scenes (6 to 12): each scene teaches exactly ONE point (point_id). Every requirement gets at least one scene. Only two
extra scenes are allowed: a 1-sentence intro (point_id "intro", first) that leads into the question, and a 1-sentence recap
(point_id "recap", last) that restates the answer in NEW words (never repeat the intro). No other scenes.
- visual per scene: trace | counter | table | highlight | none. Use only ops that serve the point. Never run a generic demo of
  the structure when the question asks for something else.
- A program runs your ops on the REAL structure, computes every count and checks every number you write; numbers come from code.
  Run algorithms to completion (never cut a demo off mid-algorithm) unless partial is true.
- A demo scene says what its step SHOWS about the point, e.g. "We pop 25 because 25 was the last in, so it comes out first."
- Narration: {"1 or 2 short sentences" if level == "beginner" else "1 to 3 sentences"} per scene, digits for numbers, names the concrete values and the state at the END of the scene
  (linked lists with pointers: {'"box 20' + "'s" + ' note now points to box 40, so box 30 is skipped"' if level == "beginner" else '"20 now points to 40, so 30 is skipped. head -> 10 -> 20 -> 40 -> null"'}; never a bracketed list).
  A bracketed list ("Array is now [1, 2, 4]", "the list [1, 2, 4]") always means the state at the END of the scene; name a
  starting input without brackets ("starting from 30, 20, 10").
Structures and ops (a scene may name its own "structure" for a second structure, e.g. growth tables or comparisons):
{ops}
Return JSON: {{"topic": str, "structure": subject, "analysis": {{"subject": str, "ask": str, "key_terms": [str],
"jargon": [{{"term": str, "plain": str}}], "partial": bool, "shape": str, "items": [{{"name": str, "line": str}}], "sides": [str],
"premise_correct": bool, "parts": [str], "clarify": str, "requirements": [{{"id": "r1", "text": str, "evidence": str, "evidence_detail": str, "algorithm": str, "structure": str}}]}},
"answer_points": [{{"id": "p1", "requirement_id": "r1", "kind": str, "point": str, "visual": str}}],
"scenes": [{{"point_id": str, "role": "setup"|"core"|"edge_case"|"recap", "structure": str, "visual": str,
"ops": [{{"op": str, "args": [int or str]}}], "narration": str}}]}}"""


# ---------------------------------------------------------------- 1. the analysis + plan call
def analyze_and_plan(topic: str, level: str, given: GivenData) -> dict:
    return llm.generate_json(prompt(topic, level, given), SCHEMA)


def usable(raw) -> bool:
    """A question-driven answer (requirements + points + scenes) rather than an old-style plan."""
    if not isinstance(raw, dict):
        return False
    a = raw.get("analysis")
    return (isinstance(a, dict) and isinstance(a.get("requirements"), list) and len(a["requirements"]) >= 1
            and isinstance(raw.get("scenes"), list) and raw.get("structure", a.get("subject")) in SUBJECTS + [None]
            and (a.get("subject") in SUBJECTS or raw.get("structure") in SUBJECTS))


# ---------------------------------------------------------------- 2. generic plan normalisation
def _clean_ops(ops) -> list[dict]:
    out = []
    for o in ops or []:
        if isinstance(o, dict) and isinstance(o.get("op"), str):
            out.append({"op": o["op"], "args": [a for a in (o.get("args") or []) if isinstance(a, (int, str))]})
    return out


def _sentences(text: str) -> int:
    return len([s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s])


def _simulate_ok(subject: str, scenes: list[dict]) -> bool:
    try:
        simulate(subject, scenes)
        return True
    except (OpError, KeyError, TypeError, ValueError):
        return False


def _drop_bad_ops(subject: str, scenes: list[dict]) -> None:
    """Keep the longest valid prefix of each scene's ops (an impossible op never ships; its narration gets repaired)."""
    for i, sc in enumerate(scenes):
        kind = sc.get("structure") or subject
        if kind not in ALLOWED_OPS or any(o["op"] not in ALLOWED_OPS[kind] for o in sc["ops"]):
            sc["ops"] = [o for o in sc["ops"] if kind in ALLOWED_OPS and o["op"] in ALLOWED_OPS[kind]]
            if kind not in ALLOWED_OPS:
                sc.pop("structure", None)
        while sc["ops"] and not _simulate_ok(subject, scenes[: i + 1]):
            sc["ops"].pop()
            sc["narration_stale"] = True


def _same_size_runs(subject: str, scenes: list[dict]) -> None:
    """Runs of the same sort in one lesson are compared with each other (best vs worst case), so they use the same n:
    a run on a different number of values keeps its shape (sorted, reversed or mixed) on the first run's values."""
    for kind in SORTS:
        loads = [(i, j) for i, sc in enumerate(scenes) if (sc.get("structure") or subject) == kind
                 for j, o in enumerate(sc["ops"]) if o["op"] in ("load", "reload") and o["args"]]
        if len(loads) < 2:
            continue
        base = [a for a in scenes[loads[0][0]]["ops"][loads[0][1]]["args"] if isinstance(a, int)]
        for i, j in loads[1:]:
            vals = scenes[i]["ops"][j]["args"]
            if len(vals) != len(base) and len(base) >= 2:
                new = sorted(base) if vals == sorted(vals) else sorted(base, reverse=True) if vals == sorted(vals, reverse=True) else list(base)
                scenes[i]["ops"][j] = {"op": scenes[i]["ops"][j]["op"], "args": new}
                scenes[i]["narration_stale"] = True


def _finish_runs(subject: str, scenes: list[dict]) -> None:
    """No demo is cut off mid-algorithm: every run of a sort or graph search (a run ends where a reload / reset starts the
    next one) is completed in the last scene of that run."""
    for kind in (*SORTS, *GRAPHS):
        idx = [i for i, sc in enumerate(scenes) if sc["ops"] and (sc.get("structure") or subject) == kind]
        runs, cur = [], []
        for i in idx:
            if cur and scenes[i]["ops"][0]["op"] in ("reload", "reset"):
                runs.append(cur)
                cur = []
            cur.append(i)
        if cur:
            runs.append(cur)
        for run in runs:
            end = run[-1]
            ds = _replay(subject, scenes, end + 1, kind)
            extra = []
            if kind in SORTS:
                while ds.items and not ds.done and len(extra) < 60:
                    ds.apply("step")
                    extra.append({"op": "step", "args": []})
            else:
                while ds.started and ds.queue and len(extra) < 30:
                    ds.apply("visit")
                    extra.append({"op": "visit", "args": []})
            if extra:
                scenes[end]["ops"] = scenes[end]["ops"] + extra
                scenes[end]["narration_stale"] = True


def _replay(subject: str, scenes: list[dict], upto: int, kind: str):
    ds = make(kind)
    for sc in scenes[:upto]:
        if (sc.get("structure") or subject) == kind or (not sc.get("structure") and kind == subject):
            for o in sc["ops"]:
                ds.apply(o["op"], o.get("args", []))
    return ds


ADD_WORDS = r"\b(?:push\w*|add\w*|insert\w*|enqueu\w*|append\w*|join\w*)\b"  # generic verbs, not per-question rules
REMOVE_WORDS = r"\b(?:pop\w*|remov\w*|delet\w*|dequeu\w*|leav\w*|take\w* off|comes? out)\b"
DEFAULT_VALUES = {"array": [10, 20, 30, 40], "queue": [10, 20, 30], "stack": [10, 20, 30], "linked_list": [10, 20, 30, 40],
                  "binary_tree": [50, 30, 70, 20], "bubble_sort": [5, 1, 4, 2], "insertion_sort": [5, 1, 4, 2]}
DEFAULT_EDGES = [("A", "B"), ("A", "C"), ("B", "D"), ("C", "E")]
SUBJECT_ALGO = {"bubble_sort": "bubble_sort", "insertion_sort": "insertion_sort", "graph_bfs": "bfs", "graph_dfs": "dfs",
                "array": "linear_search", "linked_list": "linked_list_search", "stack": "stack_push", "queue": "queue_enqueue"}


def _graph_run(kind: str, edges) -> list[dict]:
    start = "start_dfs" if kind == "graph_dfs" else "start_bfs"
    n = len({x for e in edges for x in e})
    return [{"op": "reset", "args": []}, *({"op": "add_edge", "args": list(e)} for e in edges),
            {"op": start, "args": [edges[0][0]]}, *({"op": "visit", "args": []} for _ in range(n))]


def _sort_run(kind: str, values) -> list[dict]:
    from structures import run_bubble, run_insertion
    steps = (run_bubble if kind == "bubble_sort" else run_insertion)(values)["comparisons"]
    return [{"op": "reload", "args": list(values)}, *({"op": "step", "args": []} for _ in range(steps))]


def evidence_scenes(req: dict, subject: str, given: GivenData, scenes: list[dict], at: int | None = None, topic: str = "") -> list[dict]:
    """Scenes (ops only; narration is written by the batched repair) that compute a requirement's evidence for real."""
    ev = req.get("evidence", "none")
    own = req.get("structure") if req.get("structure") in SUBJECTS else subject  # the structure THIS requirement is about
    algo = req.get("algorithm") if req.get("algorithm") in complexity.ALGOS else SUBJECT_ALGO.get(own)
    kind = complexity.ALGOS[algo]["structure"] if algo in complexity.ALGOS else own
    values = list(given.values) or DEFAULT_VALUES.get(kind, [10, 20, 30, 40])
    edges = list(given.edges) or DEFAULT_EDGES

    def scene(ops, structure=None):
        return {"ops": ops, "narration": "-", "role": "core", **({"structure": structure} if structure and structure != subject else {})}

    if ev == "table" and algo in complexity.ALGOS:
        return [scene([{"op": algo, "args": complexity.SIZES}], "growth")]
    if kind in SORTS:
        used = [o["args"] for sc in scenes if (sc.get("structure") or subject) == kind for o in sc["ops"]
                if o["op"] in ("load", "reload") and len(o["args"]) >= 2]
        if used and not given.values:  # the lesson's own values, so its runs can be compared
            values = sorted(used[0], key=lambda v: list(used[0]).index(v))
        if ev == "compare":
            return [scene(_sort_run(kind, sorted(values)), kind), scene(_sort_run(kind, sorted(values, reverse=True)), kind)]
        text = req.get("text", "") + " " + req.get("evidence_detail", "")
        if re.search(r"\bbest\b|\balready sorted\b|\bin order\b", text, re.I):  # general complexity words, not per-question rules
            values = sorted(values)
        elif re.search(r"\bworst\b|\brevers", text, re.I):
            values = sorted(values, reverse=True)
        return [scene(_sort_run(kind, values), kind)]
    if kind in GRAPHS:
        if ev == "compare":
            return [scene(_graph_run("graph_bfs", edges), "graph_bfs"), scene(_graph_run("graph_dfs", edges), "graph_dfs")]
        return [scene(_graph_run(kind, edges), kind)]
    if kind in ("dyn_array", "array_2d", "jagged_array"):  # a kind of array with its own view: build it and show its behaviour
        from concepts import variants_for
        text = req.get("text", "") + " " + req.get("evidence_detail", "")
        static = bool(re.search(r"\bstatic\b|\bfixed\b", text, re.I))
        v = next((v for v in variants_for("array") if v["structure"] == kind
                  and (kind != "dyn_array" or (v["name"] == "static array") == static)), None)
        return [scene([{"op": o, "args": list(a)} for o, a in v["build"] + v["demo"]], kind)] if v else []
    if ev in ("trace", "count", "state", "compare"):  # a linear structure: build it if needed, then run its main operation
        ds = _replay(subject, scenes, len(scenes) if at is None else at, kind)
        ops = [] if getattr(ds, "items", None) or getattr(ds, "head", None) else [{"op": "init", "args": values}]
        items = values if ops else list(ds.state().get("items", []))
        fresh = max([int(v) for v in items] or [0]) + 10
        text = req.get("text", "") + " " + req.get("evidence_detail", "") + " " + topic
        adds = bool(re.search(ADD_WORDS, text, re.I)) or not re.search(REMOVE_WORDS, text, re.I)
        removes = bool(re.search(REMOVE_WORDS, text, re.I)) or not re.search(ADD_WORDS, text, re.I)
        main = {"stack": [{"op": "push", "args": [fresh]}] * adds + [{"op": "pop", "args": []}] * removes,
                "queue": [{"op": "enqueue", "args": [fresh]}] * adds + [{"op": "dequeue", "args": []}] * removes,
                "array": ([{"op": "scan", "args": [items[-1]]} for _ in items] if ev == "count"
                          else [{"op": "insert_at", "args": [max(1, len(items) // 2), fresh]}] if re.search(ADD_WORDS, text, re.I)
                          else [{"op": "delete_at", "args": [max(1, len(items) // 2)]}] if re.search(REMOVE_WORDS, text, re.I)
                          else [{"op": "get", "args": [len(items) - 1]}]),
                "linked_list": [{"op": "walk", "args": [v]} for v in items],
                "binary_tree": [{"op": "search_bst", "args": [items[-1]]}]}.get(kind, [])
        return [scene(ops + main, kind)]
    return []


def _covered_evidence(ev: str, idx: list[int], scenes: list[dict], sims: list[dict]) -> bool:
    op_scenes = [i for i in idx if scenes[i]["ops"]]
    if ev == "none":
        return True
    if ev == "state":  # a scene without ops shows the current state: enough once the structure has been built
        return bool(op_scenes) or any(sc["ops"] for sc in scenes[: idx[0]])
    if ev == "table":
        return any(sims[i]["state"]["kind"] == "growth" for i in op_scenes)
    if ev == "count":
        return any(complexity.infer_algo([sims[i]["before"], *sims[i]["steps"]]) for i in op_scenes)
    if ev == "compare":
        kinds = {sims[i]["state"]["kind"] for i in op_scenes}
        reruns = any(o["op"] in ("reload", "reset") for i in op_scenes for o in scenes[i]["ops"])
        return len(op_scenes) >= 2 and (len(kinds) >= 2 or reruns or "growth" in kinds) or (len(kinds) >= 2)
    return bool(op_scenes)


def _jargon(items) -> list[dict]:
    out = []
    for j in items or []:
        if isinstance(j, str) and j.strip():
            out.append({"term": j.strip(), "plain": ""})
        elif isinstance(j, dict) and isinstance(j.get("term"), str) and j["term"].strip():
            out.append({"term": j["term"].strip(), "plain": str(j.get("plain") or "").strip()})
    return out


def _why_values(subject: str, scenes: list[dict], at: int, given: GivenData) -> tuple[list, list, int]:
    """The subject's items at that point (if built), the values the WHY runs use, and a fresh value not among them."""
    built = _replay(subject, scenes, at, subject).state().get("items") or []
    values = ([v for v in built if isinstance(v, int)] or [v for v in given.values if isinstance(v, int)] or DEFAULT_VALUES[subject])[:5]
    new = next(c for c in ((values[0] + values[1]) // 2 if len(values) > 1 else values[0] + 5, max(values) + 5, max(values) + 7) if c not in values)
    return built, values, new


def _ops(pairs) -> list[dict]:
    return [{"op": o, "args": list(a)} for o, a in pairs]


# "why is inserting into an array slow": the question is about the subject's OWN cost, so the problem is shown on the subject
NEGATIVE_WHY = re.compile(r"\bwhy\b.*\b(?:slow\w*|expensive|costly|bad|hard|harder|inefficient|take\w* (?:long|longer|more)|"
                          r"so many|waste\w*|problem\w*|drawback\w*|disadvantage\w*)\b", re.I)


def add_why_scenes(topic: str, subject: str, scenes: list[dict], points: list[dict], reqs: list[dict], given: GivenData) -> list[dict]:
    """A WHY question ("why do we use a linked list") is answered problem first: a real run on the alternative structure shows
    what is hard without the subject (concepts.WHY), then a real run on the subject shows how it avoids that.
    The plan's own scenes are used when their ops really show it (the problem op on the alternative, a fix op on the subject);
    a scene the LLM labelled "problem" or "fix" with the wrong ops gets the real ops (its narration is then rewritten from the
    true states); anything still missing is added as a new scene with its own requirement."""
    from concepts import WHY, WHY_QUESTION
    w = WHY.get(subject)
    if not w or not re.search(WHY_QUESTION, topic, re.I) or NEGATIVE_WHY.search(topic):
        return scenes
    alt = w["alt"]
    key_op = w["problem_ops"](DEFAULT_VALUES[subject], 0)[-1][0]  # the op that shows the problem (insert_at, walk, pop, dequeue)
    fix_key = {w["fix_ops"](DEFAULT_VALUES[subject], 0)[-1][0]} | (
        {"insert_after", "insert_head", "insert_tail", "delete_value"} if subject == "linked_list" else set())
    kind_of = {p["id"]: p["kind"] for p in points}
    labelled = {k: [i for i, sc in enumerate(scenes) if kind_of.get(sc["point_id"]) == k] for k in ("problem", "fix")}
    for p in points:  # scene kinds are decided below, from what the ops really show
        if p["kind"] in ("problem", "fix"):
            p["kind"] = "explain"

    def shows_problem(sc):
        return sc.get("structure") == alt and any(o["op"] == key_op for o in sc["ops"])

    def shows_fix(sc):
        return (sc.get("structure") or subject) == subject and any(o["op"] in fix_key for o in sc["ops"])

    # 1. the problem scene
    j = next((i for i, sc in enumerate(scenes) if shows_problem(sc)), None)
    if j is None:
        for i in labelled["problem"]:  # the LLM's problem scene, with the real problem ops
            _b, values, new = _why_values(subject, scenes, i, given)
            trial = copy.deepcopy(scenes)
            trial[i].update(ops=_ops(w["problem_ops"](values, new)), structure=alt, narration_stale=True)
            if _simulate_ok(subject, trial):
                scenes, j = trial, i
                break
    if j is None:
        first = {p["id"] for p in points if reqs and p["requirement_id"] == reqs[0]["id"]}
        idx = [i for i, sc in enumerate(scenes) if sc["point_id"] in first]
        at = min(idx[-1] + 1 if idx else 1, len(scenes) - 1)  # after the first requirement (usually "what it is"), before the recap
        _b, values, new = _why_values(subject, scenes, at, given)
        problem = {"ops": _ops(w["problem_ops"](values, new)), "narration": "-", "role": "core", "point_id": "p_problem", "structure": alt,
                   "note": f"show the PROBLEM, in the analogy: {w['problem']}"}
        trial = scenes[:at] + [problem] + scenes[at:]
        if not _simulate_ok(subject, trial):  # the alternative was already built earlier in this lesson
            problem["ops"] = [o for o in problem["ops"] if o["op"] != "init"]
            if not _simulate_ok(subject, trial):
                return scenes
        scenes, j = trial, at
        reqs.append({"id": "r_problem", "text": "the problem without it: " + w["problem"], "evidence": "trace", "evidence_detail": "",
                     "algorithm": "", "structure": alt})
        k = max((n for n, p in enumerate(points) if p["id"] in first), default=-1) + 1
        points[k:k] = [{"id": "p_problem", "requirement_id": "r_problem", "kind": "explain", "point": w["problem"], "visual": "trace"}]
    scenes[j]["kind_override"] = "problem"
    # 2. the fix scene, after the problem
    f = next((i for i, sc in enumerate(scenes) if i > j and shows_fix(sc)), None)
    if f is None:
        for i in [i for i in labelled["fix"] if i > j]:  # the LLM's fix scene, with the real fix ops
            built, values, new = _why_values(subject, scenes, i, given)
            trial = copy.deepcopy(scenes)
            trial[i].update(ops=_ops(([] if built else [("init", values)]) + list(w["fix_ops"](values, new))), narration_stale=True)
            trial[i].pop("structure", None)
            if _simulate_ok(subject, trial):
                scenes, f = trial, i
                break
    if f is None:
        built, values, new = _why_values(subject, scenes, j + 1, given)
        fixed = {"ops": _ops(([] if built else [("init", values)]) + list(w["fix_ops"](values, new))), "narration": "-", "role": "core",
                 "point_id": "p_fix", "note": f"show how the {subject.replace('_', ' ')} avoids that problem: {w['fix']}"}
        trial = scenes[: j + 1] + [fixed] + scenes[j + 1:]
        if not _simulate_ok(subject, trial):
            return scenes
        scenes, f = trial, j + 1
        reqs.append({"id": "r_fix", "text": "how it avoids that problem: " + w["fix"], "evidence": "trace", "evidence_detail": "",
                     "algorithm": "", "structure": subject})
        after = scenes[j]["point_id"]
        k = max((n for n, p in enumerate(points) if p["id"] == after), default=len(points) - 1) + 1
        points[k:k] = [{"id": "p_fix", "requirement_id": "r_fix", "kind": "explain", "point": w["fix"], "visual": "trace"}]
    scenes[f]["kind_override"] = "fix"
    return scenes


STRONG_SHAPES = ("list", "compare", "misconception", "data")  # question forms code recognises reliably from the wording
LIST_WORD = re.compile(r"\b(types?|kinds?|sorts?|varieties|variants|categories|forms|ways)\b", re.I)


def validated_shape(topic: str, given: GivenData, analysis: dict | None) -> str:
    """The analysis call's shape, checked against the wording: a clear question form in the text wins."""
    code = question_shape(topic, given)
    llm_shape = (analysis or {}).get("shape")
    if code in STRONG_SHAPES:
        return code
    if llm_shape in SHAPES and llm_shape != "vague":
        return llm_shape
    return code


def _list_plan_from(topic: str, raw: dict, given: GivenData, subject: str | None) -> dict:
    """A LIST question ("how many types of array"): one requirement, one scene and one small visual per item (real ops),
    a count when the question asks how many, and a recap that restates every name."""
    from verifier import _safe
    a = raw.get("analysis") or {}
    subject = subject if subject in SUBJECTS else subject_from_text(topic)
    if subject not in SUBJECTS:
        raise NotAnswered("Structura could not tell which data structure this list question is about. "
                          "Try naming it, for example \"types of linked list\".")
    items = list_items(subject, a.get("items"), topic)
    name = subject.replace("_", " ")
    if len(items) < 2:
        raise NotAnswered(f"Structura does not know the kinds of {name} well enough to list them honestly yet. "
                          "It can list the types of array, linked list, queue and binary tree.")
    reqs, points, item_scenes = list_plan(topic, subject, items, a, raw.get("scenes") or [])
    m = LIST_WORD.search(topic)
    word = (m.group(1).lower() if m else "types")
    word = word if word.endswith("s") else word + "s"
    names = [it["name"] for it in items]
    how_many = bool(re.search(r"\bhow many\b", topic, re.I))
    ask = _safe(str(a.get("ask") or topic)).rstrip("?. ")
    ask = ask[:1].upper() + ask[1:]
    intro = f"{ask}? There are {len(items)} main {word}." if how_many else f"{ask}? Here are the main {word}."
    recap = f"To sum up, the main {word} of {name} are the {_join_names(names)}."
    scenes = ([{"ops": [], "narration": intro, "role": "setup", "point_id": INTRO, "kind": "goal"}]
              + [{**sc, "kind": "item"} for sc in item_scenes]
              + [{"ops": [], "narration": recap, "role": "recap", "point_id": RECAP, "kind": "recap"}])
    points = [{"id": INTRO, "requirement_id": None, "kind": "goal", "point": "The question: " + ask, "visual": "none"},
              *points, {"id": RECAP, "requirement_id": None, "kind": "recap", "point": "The names, restated", "visual": "none"}]
    analysis = {"intent": "question", "focus": "question", "structure": subject, "focus_text": ask, "must_answer": ask,
                "core_ops": [], "subject": subject, "shape": "list",
                "key_terms": [t for t in (a.get("key_terms") or []) if isinstance(t, str) and t.strip()][:4],
                "jargon": _jargon(a.get("jargon"))[:6], "partial": True, "requirements": reqs,
                "items": [{"name": it["name"], "pattern": it["pattern"]} for it in items],
                "count_facts": [len(items)] if how_many else [], "intro_text": intro, "recap_text": recap}
    return {"topic": topic, "structure": subject, "scenes": scenes, "answer_points": points, "analysis": analysis}


# COMPARE: the same steps on both sides, axis by axis (per kind of structure, not per question)
def _axes(kind: str, values: list, edges: list) -> list[tuple[str, list]] | None:
    """(axis, ops on this structure) for the axes structures of this kind are compared on, or None."""
    v = list(values)
    if kind in ("stack", "queue"):
        out = "pop" if kind == "stack" else "dequeue"
        return [("add the same values in the same order", [{"op": "reset", "args": []}, {"op": "init", "args": v[:3]}]),
                ("take a single item out", [{"op": out, "args": []}])]
    if kind in ("array", "linked_list"):
        v4 = (v + [x * 10 for x in range(1, 5)])[:4] if len(v) < 4 else v[:4]
        read = [{"op": "get", "args": [2]}] if kind == "array" else [{"op": "walk", "args": [x]} for x in v4[:3]]
        new = max(v4) + 5
        insert = ([{"op": "insert_at", "args": [1, new]}] if kind == "array" else [{"op": "insert_after", "args": [v4[0], new]}])
        return [("hold the same values", [{"op": "reset", "args": []}, {"op": "init", "args": v4}]),
                (f"reach the value in position 2", read), ("put a new value near the start", insert)]
    if kind in GRAPHS:
        return [("explore the same graph from the same start", _graph_run(kind, edges))]
    if kind in SORTS:
        return [("sort the same values", [{"op": "load" if True else "reload", "args": v[:5]}] + _sort_run(kind, v[:5])[1:])]
    return None


KIND_NAME = {"array": "array", "linked_list": "linked list", "stack": "stack", "queue": "queue", "binary_tree": "binary search tree",
             "graph_bfs": "BFS", "graph_dfs": "DFS", "bubble_sort": "bubble sort", "insertion_sort": "insertion sort"}


def _sides_from_requirements(topic: str, a: dict, subject: str | None) -> list[str]:
    """"When should I use a linked list?": the question's structure, and the other structure its requirements weigh it against."""
    first = subject_from_text(topic) or subject
    kinds = [first] + [subject_from_text(str(r.get("text", "")) + " " + str(r.get("evidence_detail", ""))) or r.get("structure")
                       for r in a.get("requirements") or [] if isinstance(r, dict)]
    out = []
    for k in kinds:
        if k in KIND_NAME and KIND_NAME[k] not in out:
            out.append(KIND_NAME[k])
    if len(out) == 1:  # nothing to weigh it against: its usual alternative
        other = {"linked list": "array", "array": "linked list", "stack": "queue", "queue": "stack", "BFS": "DFS", "DFS": "BFS"}.get(out[0])
        if other:
            out.append(other)
    return out[:2]


def _compare_plan_from(topic: str, raw: dict, given: GivenData, sides: list[str]) -> dict | None:
    """A COMPARE question on two supported structures: both sides on the same axes, side by side (same values, same steps,
    computed by the real structures), then a verdict ("use X when ..., use Y when ...") and a recap of the difference."""
    from concepts import COMPARE_DIFF
    from verifier import _safe
    kinds = []
    for side in sides[:2]:
        k = subject_from_text(side)
        if k == "array" and re.search(r"\bdynamic|\bvector|\barraylist", side, re.I):
            return None
        kinds.append(k)
    if len(kinds) != 2 or None in kinds or kinds[0] == kinds[1]:
        return None
    values = list(given.values) or DEFAULT_VALUES.get(kinds[0], [10, 20, 30, 40])
    edges = list(given.edges) or DEFAULT_EDGES
    axes = [_axes(k, values, edges) for k in kinds]
    if not axes[0] or not axes[1] or [a for a, _ in axes[0]] != [a for a, _ in axes[1]]:
        return None
    verdict = verdict_sentence(sides)
    if not verdict or kinds[0] not in COMPARE_DIFF or kinds[1] not in COMPARE_DIFF:
        return None
    a = raw.get("analysis") or {}
    subject = kinds[0]
    reqs, points, scenes = [], [], []
    for k, (axis, _ops) in enumerate(axes[0], 1):
        rid, pid = f"r_axis{k}", f"p_axis{k}"
        reqs.append({"id": rid, "text": f"{axis}: what the {sides[0]} and the {sides[1]} do, side by side", "evidence": "compare",
                     "evidence_detail": "", "algorithm": "", "structure": subject})
        points.append({"id": pid, "requirement_id": rid, "kind": "compare", "point": f"Same steps on both: {axis}.", "visual": "trace"})
        for side, kind, ax in ((sides[0], kinds[0], axes[0]), (sides[1], kinds[1], axes[1])):
            sc = {"ops": ax[k - 1][1], "narration": "-", "role": "core", "point_id": pid, "kind": "compare",
                  "note": f"the {side} side of the comparison: {axis}. Say what the {side} does with these values."}
            if kind != subject:
                sc["structure"] = kind
            scenes.append(sc)
    reqs.append({"id": "r_verdict", "text": f"when to use the {sides[0]} and when to use the {sides[1]}", "evidence": "none",
                 "evidence_detail": "", "algorithm": "", "structure": subject})
    points.append({"id": "p_verdict", "requirement_id": "r_verdict", "kind": "verdict", "point": verdict, "visual": "none"})
    scenes.append({"ops": [], "narration": verdict, "role": "core", "point_id": "p_verdict", "kind": "verdict"})
    ask = _safe(str(a.get("ask") or topic)).rstrip("?. ")
    ask = ask[:1].upper() + ask[1:]
    intro = f"{ask}? We give both the same values and the same steps."
    art = lambda x: x if re.match(r"(?i)bfs|dfs|bubble|insertion|breadth|depth", x) else ("an " if x[:1].lower() in "aeiou" else "a ") + x
    second = art(sides[1])
    recap = f"To sum up, {art(sides[0])} {COMPARE_DIFF[kinds[0]]}. {second[:1].upper() + second[1:]} {COMPARE_DIFF[kinds[1]]}."
    scenes = ([{"ops": [], "narration": intro, "role": "setup", "point_id": INTRO, "kind": "goal"}] + scenes
              + [{"ops": [], "narration": recap, "role": "recap", "point_id": RECAP, "kind": "recap"}])
    points = [{"id": INTRO, "requirement_id": None, "kind": "goal", "point": "The question: " + ask, "visual": "none"},
              *points, {"id": RECAP, "requirement_id": None, "kind": "recap", "point": "The difference, restated", "visual": "none"}]
    analysis = {"intent": "question", "focus": "question", "structure": subject, "focus_text": ask, "must_answer": ask,
                "core_ops": [], "subject": subject, "shape": validated_shape(topic, given, a), "sides": sides[:2],
                "key_terms": [t for t in (a.get("key_terms") or []) if isinstance(t, str) and t.strip()][:4],
                "jargon": _jargon(a.get("jargon"))[:6], "partial": False, "requirements": reqs,
                "intro_text": intro, "recap_text": recap}
    return {"topic": topic, "structure": subject, "scenes": scenes, "answer_points": points, "analysis": analysis}


def build_plan(topic: str, raw: dict, given: GivenData) -> dict:
    """The LLM's answer plan, normalised in code: requirements -> points -> scenes, evidence computed for real."""
    a = raw["analysis"]
    subject = a.get("subject") if a.get("subject") in SUBJECTS else raw.get("structure")
    shape = validated_shape(topic, given, a)
    if shape == "list":
        return _list_plan_from(topic, raw, given, subject)
    if shape in ("compare", "when"):
        sides = [str(x).strip() for x in (a.get("sides") or []) if str(x).strip()][:2] or compare_sides(topic)
        if len(sides) < 2:
            sides = _sides_from_requirements(topic, a, subject)
        built = _compare_plan_from(topic, raw, given, sides) if len(sides) == 2 else None
        if built:
            return built
    reqs = []
    for i, r in enumerate(a.get("requirements") or [], 1):
        if isinstance(r, dict) and isinstance(r.get("text"), str) and r["text"].strip():
            reqs.append({"id": str(r.get("id") or f"r{i}"), "text": r["text"].strip(),
                         "evidence": r.get("evidence") if r.get("evidence") in EVIDENCE else "none",
                         "evidence_detail": str(r.get("evidence_detail") or ""), "algorithm": str(r.get("algorithm") or ""),
                         "structure": r.get("structure") if r.get("structure") in SUBJECTS else subject})
    reqs = reqs[:6]
    for r in reqs:  # never demo a structure the requirement does not mention ("why is an array slow" is not a linked list walk)
        if r["structure"] != subject and subject_from_text(r["text"] + " " + r["evidence_detail"]) != r["structure"] \
                and not re.search(r[ "structure"].replace("_", "[ _-]?"), r["text"] + " " + r["evidence_detail"], re.I):
            r["structure"] = subject
    req_ids = {r["id"] for r in reqs}
    req_structure = {r["id"]: r["structure"] for r in reqs}
    points, seen = [], set()
    for p in raw.get("answer_points") or []:
        if isinstance(p, dict) and isinstance(p.get("point"), str) and p.get("requirement_id") in req_ids and str(p.get("id")) not in seen:
            seen.add(str(p["id"]))
            points.append({"id": str(p["id"]), "requirement_id": p["requirement_id"], "kind": {"solution": "fix", "benefit": "fix"}.get(str(p.get("kind") or "explain").lower(), str(p.get("kind") or "explain").lower()),
                           "point": p["point"].strip(), "visual": str(p.get("visual") or "none")})
    for r in reqs:  # every requirement has a point
        if not any(p["requirement_id"] == r["id"] for p in points):
            points.append({"id": f"p_{r['id']}", "requirement_id": r["id"], "kind": "explain", "point": r["text"], "visual": "none"})
    order = {r["id"]: k for k, r in enumerate(reqs)}
    points.sort(key=lambda p: order[p["requirement_id"]])
    pids = {p["id"] for p in points}

    scenes = []
    raw_scenes = [s for s in raw.get("scenes") or [] if isinstance(s, dict)]
    for k, s in enumerate(raw_scenes):
        pid = str(s.get("point_id") or "")
        narration = str(s.get("narration") or "").strip() or "-"
        if pid not in pids:  # scenes that teach no requirement are rejected, except a short intro (may build the data) and recap
            if k == 0 and (pid == INTRO or (_sentences(narration) <= 1 and not s.get("ops"))):
                pid = INTRO
            elif k == len(raw_scenes) - 1 and (pid == RECAP or _sentences(narration) <= 2) and not s.get("ops"):
                pid = RECAP
            else:
                continue
        role = s.get("role") if s.get("role") in ("setup", "core", "edge_case", "recap") else "core"
        if pid == INTRO:
            role = "setup"
        elif pid == RECAP:
            role = "recap"
        elif role == "recap":
            role = "core"
        sc = {"ops": _clean_ops(s.get("ops")), "narration": narration, "role": role, "point_id": pid}
        st = s.get("structure")
        own = req_structure.get(next((p["requirement_id"] for p in points if p["id"] == pid), None))
        if isinstance(st, str) and st in ALLOWED_OPS and st != subject:
            if own and st != own and st != "growth":  # a demo on a structure its requirement never mentions: rebuilt by code
                sc["ops"], sc["narration"], sc["narration_stale"] = [], "-", True
            else:
                sc["structure"] = st
        scenes.append(sc)
    if not scenes or scenes[0]["point_id"] != INTRO:
        scenes.insert(0, {"ops": [], "narration": "-", "role": "setup", "point_id": INTRO})
    if scenes[-1]["point_id"] != RECAP:
        scenes.append({"ops": [], "narration": "-", "role": "recap", "point_id": RECAP})
    _same_size_runs(subject, scenes)
    _drop_bad_ops(subject, scenes)

    # every requirement: at least one scene, and its evidence computed by real code
    for r in reqs:
        rp = [p["id"] for p in points if p["requirement_id"] == r["id"]]
        idx = [i for i, sc in enumerate(scenes) if sc["point_id"] in rp]
        sims = simulate(subject, scenes)
        if not idx or not _covered_evidence(r["evidence"], idx, scenes, sims):
            at = (idx[-1] + 1) if idx else len(scenes) - 1
            bare = [i for i in idx if not scenes[i]["ops"]]
            spot = bare[-1] if bare else at
            new = evidence_scenes(r, subject, given, scenes, spot, topic) if r["evidence"] != "none" else []
            if not new and not idx:
                new = [{"ops": [], "narration": "-", "role": "core"}]
            if new and bare and len(new) == 1 and "structure" not in new[0]:  # show the evidence in the requirement's own scene
                trial = copy.deepcopy(scenes)
                trial[bare[-1]]["ops"] = new[0]["ops"]
                trial[bare[-1]]["narration_stale"] = True
                if _simulate_ok(subject, trial):
                    scenes = trial
                    continue
            for sc in new:
                sc["point_id"] = rp[0]
                trial = scenes[:at] + [sc] + scenes[at:]
                if _simulate_ok(subject, trial):
                    scenes, at = trial, at + 1
    _same_size_runs(subject, scenes)  # evidence scenes built above follow the same rule
    if not a.get("partial"):
        _finish_runs(subject, scenes)
    scenes = add_why_scenes(topic, subject, scenes, points, reqs, given)
    for sc in scenes:
        if sc.pop("narration_stale", False):
            sc["note"] = "the ops of this scene changed: describe what they really do"
        kind = next((p["kind"] for p in points if p["id"] == sc["point_id"]), None)
        sc["kind"] = sc.pop("kind_override", None) or {INTRO: "goal", RECAP: "recap"}.get(sc["point_id"], kind or "explain")
    points = [{"id": INTRO, "requirement_id": None, "kind": "goal", "point": "The question: " + str(a.get("ask") or topic), "visual": "none"},
              *points, {"id": RECAP, "requirement_id": None, "kind": "recap", "point": "The answer, restated in new words", "visual": "none"}]
    analysis = {"intent": "question", "focus": "question", "structure": subject, "focus_text": str(a.get("ask") or topic),
                "must_answer": str(a.get("ask") or topic), "core_ops": [], "subject": subject,
                "key_terms": [t for t in (a.get("key_terms") or []) if isinstance(t, str) and t.strip()][:4],
                "jargon": _jargon(a.get("jargon"))[:6],
                "partial": bool(a.get("partial")), "requirements": reqs, "shape": shape}
    if shape in ("compare", "when"):
        sides = [str(x).strip() for x in (a.get("sides") or []) if str(x).strip()][:2] or compare_sides(topic)
        if len(sides) == 2:
            analysis["sides"] = sides
    if shape == "misconception" and isinstance(a.get("premise_correct"), bool):
        analysis["premise_correct"] = a["premise_correct"]
    if shape == "multipart":
        analysis["parts"] = [str(x).strip() for x in (a.get("parts") or []) if str(x).strip()][:4]
    return {"topic": topic, "structure": subject, "scenes": scenes, "answer_points": points, "analysis": analysis}


# ---------------------------------------------------------------- context for the verifier (no fixed intents)
def _term_pattern(term: str) -> str:
    t = term.strip()
    if t.lower().startswith("o(") or t == "O(":
        return r"\bO\("
    words = [re.escape(w) for w in re.findall(r"[\w²]+", t)]
    return r"\b" + r"\w*[\s-]+".join(words) + r"\w*" if words else re.escape(t)  # "breadth first" = "breadth-first"


QUESTION_TERMS = [  # generic vocabulary: if the QUESTION uses it, the answer must too (not a per-question rule)
    (r"\bcomplexit", r"\bcomplexit", "complexity"), (r"\bbig[\s-]*o\b|\bO\s*\(", r"\bO\(", "O("),
    (r"\bdelet|\bremov", r"\bdelet\w*|\bremov\w*", "delete"), (r"\binsert", r"\binsert\w*", "insert"),
    (r"\bbest[\s-]+case", r"\bbest[\s-]+case", "best case"), (r"\bworst[\s-]+case", r"\bworst[\s-]+case", "worst case"),
    (r"\bsearch", r"\bsearch\w*|\bfind\w*", "search"), (r"\bsort", r"\bsort\w*", "sort"),
]


def key_terms(topic: str, analysis: dict) -> list[tuple[str, str]]:
    """(name, regex) the narration must contain: the LLM's key terms plus the question's own domain words."""
    complexity_q = re.search(r"\bcomplexit|\bbig[\s-]*o\b|\bO\s*\(|\bhow (?:fast|slow)\b", topic, re.I)
    out = [(t, _term_pattern(t)) for t in analysis.get("key_terms", [])  # the QUESTION's words only (the prompt asks for that)
           if re.search(_term_pattern(t), topic, re.I) or (_term_pattern(t) == r"\bO\(" and complexity_q)]
    for q, pattern, name in QUESTION_TERMS:
        if re.search(q, topic, re.I) and not any(name.lower() in n.lower() for n, _ in out):
            out.append((name, pattern))
    from concepts import KEY_TERM_PLAIN  # the everyday word counts too ("value" for "element", "box" for "node")
    return [(n, f"(?:{p})|{KEY_TERM_PLAIN[n.lower()]}" if n.lower() in KEY_TERM_PLAIN else p) for n, p in out]


def _recap_beginner(taught: list[str], terms: list[tuple[str, str]], structure: str) -> str:
    """The fallback recap for beginners: at most 2 short sentences taken from the taught points, with the key term."""
    import clarity
    from verifier import _safe
    picks = []
    hard = clarity.terms_for({"structure": structure})
    for p in taught:  # sentences without words a beginner would need explained (a recap explains nothing new)
        s = next(iter(clarity.short_sentences(_safe(p))), "")
        if s and clarity.word_count(s) <= 20 and s not in picks and not any(clarity.uses(t, s, hard) for t in hard):
            picks.append(s.rstrip(".") + ".")
    term_rx = "|".join(f"(?:{p})" for _, p in terms) or r"\w"
    from concepts import ANALOGY
    if not picks and structure in ANALOGY:  # nothing short and plain to repeat: the running analogy is the takeaway
        name = {"binary_tree": "a binary search tree", "graph_bfs": "breadth first search", "graph_dfs": "depth first search",
                "bubble_sort": "bubble sort", "insertion_sort": "insertion sort"}.get(structure, "a " + structure.replace("_", " "))
        picks = [f"{name} works like {ANALOGY[structure]['picture']}."]
    chosen = picks[:2]
    if terms and not re.search(term_rx, " ".join(chosen), re.I):
        chosen = chosen[:1] + [f"That is how the {terms[0][0]} works."]
    if not chosen:
        return ""
    first = chosen[0]
    body = first if re.match(r"[A-Z]{2,}\b", first) else first[:1].lower() + first[1:]
    lead = "To sum up, " if clarity.word_count("To sum up, " + body) <= clarity.MAX_WORDS else "Overall, "
    return " ".join([lead + body, *chosen[1:]])


def context(plan: dict) -> dict:
    a = plan["analysis"]
    terms = key_terms(plan["topic"], a)
    term_rx = "|".join(f"(?:{p})" for _, p in terms) or r"\w"
    ask = a.get("must_answer") or plan["topic"]
    from verifier import _safe
    words = _safe(ask).rstrip("?.").split()
    intro = " ".join(words[:24]) + "?"
    if len(words) < 3:  # e.g. "insert 5, 3, 8 into a BST": every number is dropped from a sentence code cannot verify
        intro = "Let's work through your question step by step, on a real structure."
    if not re.search(term_rx, intro, re.I):
        intro = f"{intro} Let's look at the {terms[0][0]}." if terms else intro
    reqs = a.get("requirements", [])
    taught = [p["point"].rstrip(".") for p in plan.get("answer_points") or [] if p.get("requirement_id")]
    recap = _safe("Takeaways: " + "; ".join(taught[:3] or [r["text"].rstrip(".") for r in reqs[:3]]) + ".")
    if not re.search(term_rx, recap, re.I) and terms:
        recap += f" That is the {terms[0][0]}."
    points = {p["id"]: p["point"] for p in plan.get("answer_points") or []}
    evidence_points = [p["id"] for p in plan.get("answer_points") or []
                       if any(r["id"] == p.get("requirement_id") and r["evidence"] != "none" for r in reqs)]
    if a.get("intro_text"):
        intro = a["intro_text"]
    if a.get("recap_text"):
        recap = a["recap_text"]
    beginner = a.get("level") == "beginner"  # lessons saved before levels were stored keep the old checks
    extra = {"beginner": True, "question": plan["topic"],
             "recap_beginner": a.get("recap_text") or _recap_beginner(taught, terms, plan["structure"])} if beginner else {}
    return {**extra, "intent": "question", "generic": True, "focus": "question", "focus_text": ask, "structure": plan["structure"],
            "must_answer": ask, "terms": term_rx, "intro": intro, "recap": recap, "intro_words": 35, "concepts": [], "details": [],
            "edges": [], "edges_combined": None, "off_topic": [], "outline": False, "uses": None, "principle": None,
            "points": points, "evidence_points": evidence_points, "jargon": [j["term"] for j in a.get("jargon", [])],
            "jargon_plain": {j["term"]: j["plain"] for j in a.get("jargon", []) if j.get("plain")},
            "must_cover": [[f"the key term \"{n}\"", p, "recap", f"{recap}"] for n, p in terms],
            "shape": a.get("shape"), "items": a.get("items") or [], "sides": a.get("sides") or [],
            "count_facts": a.get("count_facts") or [], "premise_correct": a.get("premise_correct")}


# ---------------------------------------------------------------- 3. the answer-coverage gate
def gate(plan: dict, scenes: list[dict], ctx: dict) -> list[str]:
    """Deterministic: every requirement covered by a scene, key terms in the narration, no unmapped scene."""
    problems = []
    reqs = plan["analysis"].get("requirements", [])
    point_req = {p["id"]: p.get("requirement_id") for p in plan.get("answer_points") or []}
    covered = {point_req.get(s.get("point_id")) for s in scenes}
    for r in reqs:
        if r["id"] not in covered:
            problems.append(f"requirement {r['id']} ({r['text']}) has no scene")
    for name, _kind, _hint in answer_missing([s["narration"] for s in scenes], ctx):
        problems.append(f"the narration never says {name}")
    stray = [s.get("id") for s in scenes if s.get("point_id") not in point_req]
    if stray:
        problems.append(f"scenes {stray} teach no answer point")
    return problems + shape_problems(plan["analysis"], scenes)


VERDICT = re.compile(r"\buse (?:an? |the )?[\w\s'-]{1,40}? (?:when|for|if|to)\b|\bchoose\b|\bpick\b|\bbetter (?:when|for|if)\b|"
                     r"\bgood (?:when|for)\b|\bbest (?:when|for)\b", re.I)
PREMISE_VERDICT = re.compile(r"\b(?:no|yes|wrong|right|correct|incorrect|true|false|myth|actually|not quite|that is not|isn't|is not|"
                             r"does not|doesn't)\b", re.I)


def verdict_sentence(sides: list[str]) -> str | None:
    """"Use X when ..., and use Y when ..." from what each side is good for (concepts.USE_WHEN), or None."""
    from concepts import USE_WHEN
    parts = []
    for side in sides[:2]:
        s = subject_from_text(side) or ("dyn_array" if re.search(r"\bdynamic|\bvector|\barraylist", side, re.I) else None)
        if s == "array" and re.search(r"\bdynamic|\bvector|\barraylist", side, re.I):
            s = "dyn_array"
        if s not in USE_WHEN:
            return None
        parts.append(f"use {'an' if side[:1].lower() in 'aeiou' else 'a'} {side} when {USE_WHEN[s]}"
                     if not re.match(r"(?i)bfs|dfs|bubble|insertion", side) else f"use {side} when {USE_WHEN[s]}")
    return (parts[0][:1].upper() + parts[0][1:] + ", and " + parts[1] + ".") if len(parts) == 2 else None


def premise_sentence(topic: str, correct: bool) -> str:
    """A plain verdict on a yes/no question's claim: "No: array access is not O(n)." (falls back to a plain yes / no)."""
    t = re.sub(r"[?.!\s]+$", "", topic or "").strip()
    m = re.match(r"(?i)^(is|are)\s+(.+?)\s+((?:O\s*\(.*\))|(?:always|never|faster|slower|constant|linear|quadratic|instant\w*|free|the same)\b.*)$", t)
    if m:
        verb = m.group(1).lower()
        claim = f"{m.group(2)} {verb} {'' if correct else 'not '}{m.group(3)}"
        return f"{'Yes' if correct else 'No'}: {claim}."
    return "Yes, that is right." if correct else "No, that is not right, and here is why."


def shape_problems(analysis: dict, scenes: list[dict]) -> list[str]:
    """What the question's SHAPE requires, checked on the narration: a list names every item in its own scene (and the
    recap restates them), a comparison names both sides and ends with a verdict, a wrong premise is answered plainly."""
    from verifier import words_to_digits
    shape, out = analysis.get("shape"), []
    texts = [s.get("narration", "") for s in scenes]
    body = [s for s in scenes if s.get("point_id") not in (INTRO, RECAP)]
    if shape == "list":
        recap = next((s["narration"] for s in reversed(scenes) if s.get("role") == "recap"), "")
        for it in analysis.get("items") or []:
            if not any(re.search(it["pattern"], s.get("narration", ""), re.I) for s in body):
                out.append(f"the list item \"{it['name']}\" is never named in a scene of its own")
            if not re.search(it["pattern"], recap, re.I):
                out.append(f"the recap does not restate \"{it['name']}\"")
        for n in analysis.get("count_facts") or []:
            if not any(re.search(rf"(?<![\w.]){n}(?!\w)", words_to_digits(t)) for t in texts):
                out.append(f"the question asks how many, but the lesson never says {n}")
    if shape in ("compare", "when"):
        for side in analysis.get("sides") or []:
            if not re.search(_side_pattern(side), " ".join(texts), re.I):
                out.append(f"the comparison never names \"{side}\"")
        if not any(VERDICT.search(t) for t in texts):
            out.append("no verdict: say when to use each (\"use X when ..., use Y when ...\")")
    if shape == "misconception" and not any(PREMISE_VERDICT.search(t) for t in texts[:3]):
        out.append("the question's claim is never answered plainly (say whether it is right or wrong first)")
    return out


def _clarity_judge(topic: str) -> str:
    return f"""CLARITY (the same answer): would a 12-year-old who has never coded understand EACH sentence? List in "clarity" every
scene with a garbled or circular sentence (a word explained with another hard word), jargon without a plain explanation
before it, a step told only in technical words (no analogy), or filler ("extremely efficient", "instantly"). Add a fix for
each flagged scene (same index) that follows this guide and keeps every value of its true state:
{style_guide(topic)}"""


JUDGE_SCHEMA = {"type": "object", "properties": {
    "requirements": {"type": "array", "items": {"type": "object", "properties": {
        "id": {"type": "string"}, "covered": {"type": "boolean"}, "reason": {"type": "string"}}, "required": ["id", "covered", "reason"]}},
    "does_lesson_answer_question": {"type": "boolean"},
    "clarity": {"type": "array", "items": {"type": "object", "properties": {
        "index": {"type": "integer"}, "problem": {"type": "string"}}, "required": ["index", "problem"]}},
    "fixes": {"type": "array", "items": {"type": "object", "properties": {
        "index": {"type": "integer"}, "narration": {"type": "string"}}, "required": ["index", "narration"]}}},
    "required": ["requirements", "does_lesson_answer_question"]}


def judge(topic: str, plan: dict, scenes: list[dict], problems: list[str]) -> dict:
    """ONE call at temperature 0: is each requirement covered, does the lesson answer the question, and rewrites for the
    scenes of any requirement that is not covered (only those)."""
    from verifier import compact_state
    beginner = plan["analysis"].get("level") == "beginner"
    point_req = {p["id"]: p.get("requirement_id") for p in plan.get("answer_points") or []}
    rows = [{"index": i, "requirement": point_req.get(s.get("point_id")), "narration": s["narration"],
             **({"true_state": compact_state(s["state"])} if s.get("ops") else {})} for i, s in enumerate(scenes)]
    text = f"""You check whether a short lesson answers a student's question. Be strict and literal.
Question from the student: "{topic}"
Requirements a correct answer must contain:
{json.dumps(plan["analysis"].get("requirements", []), indent=1)}
Automatic checks found: {problems or "nothing"}
Lesson scenes (narration in order; scenes with ops show the TRUE state computed by code):
{json.dumps(rows, indent=1)}
For each requirement say whether the narration covers it, with a one-line reason. Then say whether the lesson as a whole
answers the question. For every requirement that is NOT covered, rewrite the narration of ONE scene mapped to it (same index)
so it covers it; and fix every automatic-check problem (a missing key term goes into the recap, the last scene). Each rewrite:
{"1 or 2 short sentences (at most 25 words each)" if beginner else "1 to 3 sentences"}, plain words, digits only for numbers in its true state, keep what the scene already shows. A bracketed
list ("the list [1, 2, 4]") always means the state at the END of the scene; name a starting input without brackets
("starting from 30, 20, 10"). A scene with ops names the values of its last step and the final state.
{_clarity_judge(topic) if beginner else ""}Return JSON: {{"requirements": [{{"id": str, "covered": bool, "reason": str}}], "does_lesson_answer_question": bool,
"clarity": [{{"index": int, "problem": str}}], "fixes": [{{"index": int, "narration": str}}]}}"""
    with llm.temperature(0):
        return llm.generate_json(text, JUDGE_SCHEMA)


GENERIC_WORDS = set("""what whats is are a an the how does do did work works working many much there their of in on to and or why use
used using we i you me my explain show tell about type types kind kinds step steps by it its when should which better best
between difference vs versus can could would will data structure structures example examples simple simply please help
understand mean means meaning define definition into from with for this that these those one two some way ways main
basic idea concept concepts list lists happen happens start starting starts begin beginning fast faster slow slower quick
quickly efficient run runs trace tracing walk through demonstrate""".split())
NOUN_SYNONYMS = {"bfs": r"\bbfs\b|\bbreadth", "dfs": r"\bdfs\b|\bdepth", "bst": r"\bbsts?\b|\bbinary search tree",
                 "graph": r"\bgraphs?\b|\bmap\b|\bplaces\b", "graphs": r"\bgraphs?\b|\bmap\b|\bplaces\b",
                 "fifo": r"\bfifo\b|\bfirst in", "lifo": r"\blifo\b|\blast in"}


def missing_nouns(topic: str, texts: list[str]) -> list[str]:
    """Content words of the question the narration never says (any word form): "vector" in "what is a vector"."""
    said = " ".join(texts).lower()
    out = []
    for w in re.findall(r"[a-z][a-z0-9]+", (topic or "").lower()):
        if w in GENERIC_WORDS or len(w) < 3:
            continue
        stem = w[:-2] if len(w) > 5 and w.endswith(("es", "ed")) else w[:-1] if len(w) > 4 and w.endswith("s") else w
        if not re.search(NOUN_SYNONYMS.get(w, rf"\b{re.escape(stem)}"), said) and w not in out:
            out.append(w)
    return out
