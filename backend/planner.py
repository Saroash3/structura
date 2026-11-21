"""Topic -> validated JSON scene plan (operations only, never states).

First the question is analysed in code (focus.analyze): structure, intent (what_is | how_op | compare |
trace_on_input | why), focus, must_answer and core ops. The LLM plans a lesson around THAT, with a role per scene
(setup | core | edge_case | recap), and focus.shape enforces it: one setup scene with an `init` op, the core ops
(e.g. a hop-by-hop walk to the node before the target), no off-focus scenes.

If the topic contains the user's own data (graph edges and a start node, or a list of values), the plan is
forced to use exactly that data: the LLM is told to, and `conform_to_given` rebuilds the op skeleton in code
when it does not. The LLM only invents small example data when the user gave none.
"""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

import complexity
import focus
import llm
from concepts import GLOSSARY, JARGON
from focus import ROLES, UnsupportedTopic  # noqa: F401  (UnsupportedTopic is re-exported for main.py)
from structures import ALLOWED_OPS, OpError
from topic_parser import GivenData, parse_topic
from verifier import compact_state, simulate

Level = Literal["beginner", "intermediate"]

SUPPORTED_NAMES = "arrays, stacks, queues, linked lists, binary search trees, breadth first search on graphs, and bubble sort"
PLACEHOLDER = "-"  # narration for scenes rebuilt in code; always fails the checks, so it gets repaired


OP_HELP = {
    "array": "a dynamic array with 0-based indexes. init [v1, v2, ...] fills an empty array in one step; append [value]; insert_at [index, value] "
             "(shifts later items right); delete_at [index] (shifts later items left); set [index, value]; get [index]. Indexes must be in range.",
    "queue": "init [v1, v2, ...] fills an empty queue (front first); enqueue [value] adds at the back; dequeue [] removes the front; peek [] looks at the front.",
    "stack": "init [v1, v2, ...] fills an empty stack (bottom first); push [value] adds on top; pop [] removes the top; peek [] looks at the top.",
    "linked_list": "a singly linked list. init [v1, v2, ...] builds the whole starting list in ONE step; walk [value] moves the current pointer ONE hop "
                   "(onto the head to start, then onto the next node each time); insert_head [value]; insert_tail [value]; insert_after [target, value]; "
                   "delete_value [value] (unlinks it; a value that is not there changes nothing); search [value].",
    "binary_tree": "a binary SEARCH tree. init [v1, v2, ...] inserts the values in order in one step; insert_bst [value] (no duplicates); "
                   "search_bst [value] (must exist). Insert a middle value first so the tree is balanced.",
    "graph_bfs": "undirected graph + breadth first search. Node labels are STRINGS such as \"A\" or \"1\". First add_edge [u, v] for every edge "
                 "(all edges in ONE scene), then start_bfs [start] once, then visit [] once per reachable node (each visit dequeues one node "
                 "and enqueues its unvisited neighbours in alphabetical order). If the user gave no graph, use 5 or 6 nodes labelled A to F.",
    "bubble_sort": "load [v1, v2, ...] once in the first op scene with 4 or 5 values; then step [] repeatedly "
                   "(each step compares the next adjacent pair and swaps it if out of order). Never invent swaps.",
}

# Narration style per structure: what each scene must name (the verifier enforces it).
STYLE = {
    "array": 'Name the index and the value every time, e.g. "Insert 15 at index 1; later items shift right. Array is now [10, 15, 20]."',
    "queue": 'Name the item moved and the new front, e.g. "Dequeue 10 from the front. The front is now 20."',
    "stack": 'Name the item moved and the new top, e.g. "Pop 7 off the top. The top is now 3."',
    "linked_list": "Describe nodes and next POINTERS, never a bracketed list. Walk: \"Move to 20. 20 points to 30, our target, so 20 is the node before it.\" "
                   "Delete: \"20's next pointer now points to 40, so 30 is skipped and no longer reachable. The list is now head -> 10 -> 20 -> 40 -> null.\"",
    "binary_tree": 'Name the value and the path taken, e.g. "Insert 6: go left at 8, right at 3." Never mention size.',
    "graph_bfs": 'Visit scenes must say the node visited and the whole queue, e.g. "Visit B. Enqueue D. Queue is now [C, D]." '
                 "Use the node labels exactly. Never mention size.",
    "bubble_sort": 'Name the pair compared, the decision and the array, e.g. "Compare 7 and 3. 7 is bigger, so swap. Array is now [3, 7, 5]."',
}

NARRATION_RULES = """Narration rules (a program checks every sentence against the real data structure):
- Scene 1 (intro) says what the structure IS and why it exists, in plain words, with an everyday analogy ("like ..."). It does not talk about size.
- Every scene with ops names the concrete values or labels it changed and the resulting state. Never write vague lines like "we continue exploring".
- Narration describes the state at the END of the scene, after its ops ran.
- Write every number as digits (7, not seven). Mention only numbers that are data values, indexes, or a queue/stack/array size.
- When an item is removed, put its value right after the verb, e.g. "we dequeue 10" or "we pop 7 off the top".
- Never say something is empty unless it is."""


# Ops a plan may use (and the LLM is shown). For bubble sort only `step`: the real algorithm picks each pair.
# Ops only code-built lessons use (complexity lessons re-run inputs, scan one item at a time, and show growth tables).
CODE_ONLY_OPS = {"bubble_sort": {"reload", "compare", "swap"}, "graph_bfs": {"reset"}, "array": {"scan"}}
PROMPT_OPS = {s: [o for o in ops if o not in CODE_ONLY_OPS.get(s, set())] for s, ops in ALLOWED_OPS.items() if s != "growth"}
INSERT_OP = {"array": "append", "stack": "push", "queue": "enqueue", "linked_list": "insert_tail", "binary_tree": "insert_bst"}


class Op(BaseModel):
    op: str
    args: list[int | str] = []


class Scene(BaseModel):
    model_config = ConfigDict(extra="allow")  # visual, ...
    id: int = 0
    ops: list[Op] = []
    narration: str = Field(min_length=1)
    speed: float = Field(default=1.0, ge=0.25, le=3.0)
    role: Literal["setup", "core", "edge_case", "recap"] | None = None
    structure: str | None = None  # only in compare lessons, when this scene runs on the other structure
    note: str | None = None  # what a scene built in code must explain (sent to the narration repair)
    point_id: str | None = None  # the ONE answer point this scene teaches
    kind: str | None = None  # kind of that point: definition, analogy, rule, demo, uses, recap, goal, steps, explain, edge


class Analysis(BaseModel):
    model_config = ConfigDict(extra="allow")  # question-driven lessons: subject, requirements, key_terms, jargon
    structure: str
    intent: Literal["what_is", "how_op", "compare", "trace_on_input", "why", "complexity", "question"]
    focus: str
    position: str | None = None
    focus_text: str
    must_answer: str
    core_ops: list[str] = []
    compare_with: str | None = None
    algorithm: str | None = None


class AnswerPoint(BaseModel):
    model_config = ConfigDict(extra="allow")  # requirement_id
    id: str
    kind: str = ""
    point: str
    visual: str = "none"


class Plan(BaseModel):
    topic: str
    structure: str
    scenes: list[Scene] = Field(min_length=2, max_length=28)
    analysis: Analysis | None = None
    answer_points: list[AnswerPoint] | None = None

    @model_validator(mode="after")
    def check_ops(self):
        if self.structure not in ALLOWED_OPS:
            raise ValueError(f"structure must be one of {sorted(ALLOWED_OPS)}, got '{self.structure}'")
        for i, s in enumerate(self.scenes, 1):
            s.id = i  # normalise ids
            kind = s.structure or self.structure
            if kind not in ALLOWED_OPS:
                raise ValueError(f"scene {i}: structure must be one of {sorted(ALLOWED_OPS)}, got '{kind}'")
            code_built = self.analysis is not None and self.analysis.intent in ("complexity", "question")
            allowed = ALLOWED_OPS[kind] if code_built else PROMPT_OPS.get(kind, [])
            for o in s.ops:
                if o.op not in allowed:
                    raise ValueError(f"scene {i}: op '{o.op}' is not allowed for {kind}; allowed: {allowed}")
        return self


PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string"},
        "structure": {"type": "string", "enum": sorted(PROMPT_OPS) + ["unsupported"]},
        "answer_points": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "kind": {"type": "string"}, "point": {"type": "string"}, "visual": {"type": "string"}},
            "required": ["id", "kind", "point", "visual"]}},
        "analysis": {"type": "object", "properties": {
            "intent": {"type": "string"}, "focus": {"type": "string"}, "must_answer": {"type": "string"},
            "core_ops": {"type": "array", "items": {"type": "string"}}}},
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "role": {"type": "string", "enum": list(ROLES)},
                    "point_id": {"type": "string"},
                    "structure": {"type": "string"},
                    "ops": {"type": "array", "items": {"type": "object", "properties": {
                        "op": {"type": "string"}, "args": {"type": "array", "items": {"type": ["integer", "string"]}}}, "required": ["op", "args"]}},
                    "narration": {"type": "string"},
                },
                "required": ["id", "point_id", "role", "ops", "narration"],
            },
        },
    },
    "required": ["topic", "structure", "answer_points", "scenes"],
}


def given_prompt(given: GivenData) -> str:
    if given.edges:
        edges = ", ".join(f'["{u}", "{v}"]' for u, v in given.edges)
        return (f"\nThe user gave their own graph. Use EXACTLY these edges with these labels: {edges}, and start_bfs [\"{given.start}\"]. "
                "Do not rename, add or drop nodes or edges. Choose structure graph_bfs.")
    if given.values:
        return f"\nThe user gave their own values: {given.values}. Use exactly these values, in this order, as the data of the lesson."
    return "\nThe user gave no data, so invent small example data (values 1 to 99, or graph labels A to F)."


# ---------------------------------------------------------------- lesson templates by intent
TEMPLATES = {
    "what_is": "Answer points, in this order: (1) definition: what it is, ONE plain sentence (setup, no ops). (2) analogy: an everyday comparison "
               "(core, no ops). (3) rule: the single key rule, introducing its vocabulary in plain words (stack: last in, first out; push = add on top, "
               "pop = take the top off) (core, no ops). (4) demo: a short demo that PROVES the rule, simplest operations first (stack: push, push, push, "
               "then pop) - the proving step says what it shows (\"We pop. 25 was the last one in, so it is the first one out. The top is now 12.\"); "
               "do not demonstrate operations the answer does not need (no peek before push and pop). (5) uses: where it is used in real life "
               "(stack: the undo button, the browser back button, function calls) (core, no ops). (6) recap: 2 or 3 takeaways in NEW wording, "
               "1 or 2 sentences, never a copy of the definition. No edge cases unless the question asks for them.",
    "how_op": "(1) setup, no ops: ONE short sentence (at most 25 words) that states the goal and leads into the question; no textbook definition. "
              "(2) setup: ONE init scene that builds the starting data (never several insert scenes, unless the question is about inserting). "
              "(3) core: the operation step by step. For a linked list walk hop by hop, ONE walk op per scene, to the node BEFORE the target "
              "(or to the target, for a search), saying at each hop what the current node points to and why we keep going or stop. "
              "(4) core: the change itself, naming the pointer that is rewired, before and after (\"20's next pointer now points to 40, so 30 is skipped\"). "
              "(5) edge_case: the edge cases (for example the head, the tail, a value that is not there), in one or two short scenes. "
              "(6) recap: restate the ANSWER to the question (the steps), never unrelated facts.",
    "why": "Like how_op: the first scene leads into the why-question, the core scenes SHOW the reason with real ops, and the recap answers the why.",
    "compare": "(1) setup, no ops: one short sentence leading into the comparison. (2) setup: init the array. (3+) core: alternate scenes between "
               "the two structures (give each scene its \"structure\") doing the SAME task on the same values: read the item at an index (array get: "
               "one jump; linked list: init the list, then walk hop by hop), then insert in the middle (array insert_at shifts later items; linked list "
               "insert_after only rewires pointers). (last) recap: the difference in two sentences.",
    "trace_on_input": "(1) setup, no ops: one short sentence saying what we will do with the user's data. (2) setup: ONE scene that builds the user's "
                      "data. (3) core: run the asked operation on it, one op per scene, naming the state each time. (4) edge_case: optional. "
                      "(5) recap: what the trace showed and why.",
}

EXAMPLE_QUEUE = {"topic": "what happens when I dequeue", "structure": "queue",
                 "analysis": {"intent": "how_op", "focus": "dequeue from a queue", "must_answer": "Which item leaves when you dequeue, and what becomes the front?",
                              "core_ops": ["dequeue"]},
                 "scenes": [
                     {"id": 1, "role": "setup", "ops": [], "narration": "What happens when we dequeue? Let's watch which item leaves the queue."},
                     {"id": 2, "role": "setup", "ops": [{"op": "init", "args": [4, 9, 6]}],
                      "narration": "Here is our queue [4, 9, 6]. The front is 4, the item that has waited longest, and the back is 6."},
                     {"id": 3, "role": "core", "ops": [{"op": "dequeue", "args": []}],
                      "narration": "Dequeue removes 4 from the front, because it arrived first. The front is now 9, and the queue is [9, 6]."},
                     {"id": 4, "role": "core", "ops": [{"op": "dequeue", "args": []}],
                      "narration": "Dequeue again: 9 leaves from the front. Everyone behind it moves up, so the front is now 6."},
                     {"id": 5, "role": "edge_case", "ops": [], "narration": "Edge case: if the queue is empty, there is nothing to dequeue, so a real queue reports an error."},
                     {"id": 6, "role": "recap", "ops": [],
                      "narration": "Dequeue always removes the item at the front, the one that waited longest, and the next item in line becomes the new front."}]}
EXAMPLE_LINKED = {"topic": "remove 9 from a linked list", "structure": "linked_list",
                  "analysis": {"intent": "how_op", "focus": "delete a node from the middle", "must_answer": "How do you remove 9 without breaking the chain?",
                               "core_ops": ["walk", "delete_value"]},
                  "scenes": [
                      {"id": 1, "role": "setup", "ops": [], "narration": "How do we remove a node from the middle of a linked list without breaking the chain?"},
                      {"id": 2, "role": "setup", "ops": [{"op": "init", "args": [7, 3, 9, 5]}],
                       "narration": "Here is our list: head -> 7 -> 3 -> 9 -> 5 -> null. We want to remove 9."},
                      {"id": 3, "role": "core", "ops": [{"op": "walk", "args": [7]}],
                       "narration": "We can only start at the head, 7. 7 points to 3, not to 9, so we keep walking."},
                      {"id": 4, "role": "core", "ops": [{"op": "walk", "args": [3]}],
                       "narration": "Move to 3. 3 points to 9, our target, so 3 is the node before it. We stop here, because 3 holds the pointer we must change."},
                      {"id": 5, "role": "core", "ops": [{"op": "delete_value", "args": [9]}],
                       "narration": "Rewire: 3's next pointer now points to 5, skipping 9. Nothing points to 9 any more, so it is no longer reachable. "
                                    "The list is now head -> 7 -> 3 -> 5 -> null."},
                      {"id": 6, "role": "edge_case", "ops": [],
                       "narration": "Edge cases: deleting the head just moves the head pointer; deleting the tail makes the node before it point to null."},
                      {"id": 7, "role": "recap", "ops": [],
                       "narration": "To delete a middle node, walk to the node before it and point its next pointer past the target. The target is skipped."}]}


EXAMPLE_WHAT_IS_QUEUE = {
    "topic": "what is a queue", "structure": "queue",
    "answer_points": [
        {"id": "p1", "kind": "definition", "point": "A queue is a line where items join at the back and leave from the front.", "visual": "none"},
        {"id": "p2", "kind": "analogy", "point": "It works like people waiting at a ticket counter.", "visual": "none"},
        {"id": "p3", "kind": "rule", "point": "First in, first out; enqueue joins at the back, dequeue leaves from the front.", "visual": "none"},
        {"id": "p4", "kind": "demo", "point": "Enqueue three items, then dequeue: the first one in leaves first.", "visual": "ops: enqueue, enqueue, enqueue, dequeue"},
        {"id": "p5", "kind": "uses", "point": "Printer queues, lines at a counter, tasks handled in arrival order.", "visual": "none"},
        {"id": "p6", "kind": "recap", "point": "Join at the back, leave from the front, longest wait goes next.", "visual": "none"}],
    "scenes": [
        {"id": 1, "point_id": "p1", "role": "setup", "ops": [], "narration": "A queue is a line of items where new items join at the back and items leave from the front."},
        {"id": 2, "point_id": "p2", "role": "core", "ops": [], "narration": "Think of people waiting at a ticket counter: newcomers join the end, and the person at the front is served next."},
        {"id": 3, "point_id": "p3", "role": "core", "ops": [],
         "narration": "The key rule is first in, first out. Joining at the back is called enqueue, and leaving from the front is called dequeue."},
        {"id": 4, "point_id": "p4", "role": "core", "ops": [{"op": "enqueue", "args": [4]}], "narration": "We enqueue 4. It is the only item, so 4 is the front."},
        {"id": 5, "point_id": "p4", "role": "core", "ops": [{"op": "enqueue", "args": [9]}], "narration": "We enqueue 9 at the back. The front is still 4."},
        {"id": 6, "point_id": "p4", "role": "core", "ops": [{"op": "enqueue", "args": [6]}], "narration": "We enqueue 6 at the back. The line is now 4, 9, 6."},
        {"id": 7, "point_id": "p4", "role": "core", "ops": [{"op": "dequeue", "args": []}],
         "narration": "We dequeue 4 from the front. 4 arrived first, so it is the first to leave. The front is now 9."},
        {"id": 8, "point_id": "p5", "role": "core", "ops": [],
         "narration": "Queues are everywhere: documents wait in a printer queue, and a computer handles tasks in the order they arrive."},
        {"id": 9, "point_id": "p6", "role": "recap", "ops": [], "narration": "Takeaways: join at the back, leave from the front, and whoever waited longest goes next."}]}
EXAMPLE_WHAT_IS_STACK = {**EXAMPLE_WHAT_IS_QUEUE, "topic": "what is a stack", "structure": "stack", "answer_points": [
    {"id": "p1", "kind": "definition", "point": "A stack is a pile where you add and remove only at the top.", "visual": "none"},
    {"id": "p2", "kind": "analogy", "point": "It works like a stack of plates.", "visual": "none"},
    {"id": "p3", "kind": "rule", "point": "Last in, first out; push adds on top, pop takes the top off.", "visual": "none"},
    {"id": "p4", "kind": "demo", "point": "Push three items, then pop: the last one in leaves first.", "visual": "ops: push, push, push, pop"},
    {"id": "p5", "kind": "uses", "point": "The undo button, the browser back button, function calls.", "visual": "none"},
    {"id": "p6", "kind": "recap", "point": "Only the top is touched, and the newest item leaves first.", "visual": "none"}],
    "scenes": [
        {"id": 1, "point_id": "p1", "role": "setup", "ops": [], "narration": "A stack is a pile of items where you can only add or remove at a single end, called the top."},
        {"id": 2, "point_id": "p2", "role": "core", "ops": [], "narration": "Think of a stack of plates: a new plate goes on top, and you take plates from the top."},
        {"id": 3, "point_id": "p3", "role": "core", "ops": [],
         "narration": "The key rule is last in, first out. Adding on top is called push, and taking the top item off is called pop."},
        {"id": 4, "point_id": "p4", "role": "core", "ops": [{"op": "push", "args": [12]}], "narration": "We push 12. The top is now 12."},
        {"id": 5, "point_id": "p4", "role": "core", "ops": [{"op": "push", "args": [7]}], "narration": "We push 7 on top of 12. The top is now 7."},
        {"id": 6, "point_id": "p4", "role": "core", "ops": [{"op": "push", "args": [25]}], "narration": "We push 25. The top is now 25."},
        {"id": 7, "point_id": "p4", "role": "core", "ops": [{"op": "pop", "args": []}],
         "narration": "We pop. 25 was the last one in, so it is the first one out. The top is now 7."},
        {"id": 8, "point_id": "p5", "role": "core", "ops": [],
         "narration": "Stacks are everywhere: the undo button takes back your newest change first, and the back button returns to the page you saw last."},
        {"id": 9, "point_id": "p6", "role": "recap", "ops": [], "narration": "Takeaways: only the top is touched, push adds and pop removes, and the newest item leaves first."}]}


def _vocab_prompt(structure: str) -> str:
    words = GLOSSARY.get(structure, {})
    vocab = "; ".join(f"{w} = {m}" for w, m in words.items())
    return (f"Plain words: define every technical word the first time you use it ({vocab}). Never use jargon such as "
            f"{', '.join(JARGON)} unless the same sentence explains it in plain words (\"constant time means it is always a single quick step, "
            "no matter how many items there are\").")


def analysis_prompt(a: "focus.Analysis | None") -> str:
    if a is None:
        return "\nNo analysis was possible in code: work out the structure, intent, focus and must_answer yourself and organise the lesson around them."
    if a.intent == "what_is":
        example = EXAMPLE_WHAT_IS_STACK if a.structure == "queue" else EXAMPLE_WHAT_IS_QUEUE
    else:
        example = EXAMPLE_QUEUE if a.structure == "linked_list" else EXAMPLE_LINKED
    return f"""
QUESTION ANALYSIS (already done; organise the WHOLE lesson around it):
- structure: {a.structure}{f" compared with {a.compare_with}" if a.compare_with else ""}
- intent: {a.intent}
- focus: {a.focus_text}
- must_answer: "{a.must_answer}"
- core ops that demonstrate the focus: {a.core_ops}
Template for intent {a.intent}: {TEMPLATES[a.intent]}

PLAN THE ANSWER FIRST, THEN THE VISUALS. Answer quality comes first; animation only supports the answer.
1. "answer_points": 4 to 6 short teaching points that together fully answer the question, as a good teacher would. Each has an "id"
   ("p1", ...), a "kind" (definition, analogy, rule, demo, uses, recap, goal, steps, explain, edge), the "point" in one line, and a
   "visual" (an op sequence, "current state", or "none").
2. "scenes": each scene has a "point_id" naming EXACTLY ONE answer point. Every point is covered; only the demo/steps point may take more than
   one scene. Never add a scene just to show an operation. Scenes without ops are fine (analogy, uses, the rule).
3. Every demo step says what it shows about the rule, using the real values.
{_vocab_prompt(a.structure)}
Scene roles (every scene has one): setup (at most 2 scenes: the opening sentence and ONE init scene), core (teaches the answer, 2 or 3 sentences;
core scenes must take at least half of the lesson), edge_case (short, only if it serves the question), recap (the last scene; restates the
answer in NEW wording, never a copy of the first scene). Do not add facts about other operations (for a delete lesson: nothing about insert
speed or search cost). Return "analysis" with your own one-sentence must_answer.

Example of a good plan for a DIFFERENT question (copy its shape, not its data):
{json.dumps(example)}
"""


def plan_prompt(topic: str, level: Level, given: GivenData | None = None, a: "focus.Analysis | None" = None) -> str:
    ops = "\n".join(f"- {s}: ops {PROMPT_OPS[s]}. {OP_HELP.get(s, '')}" for s in PROMPT_OPS)
    styles = "\n".join(f"- {s}: {STYLE[s]}" for s in STYLE)
    return f"""You are planning an animated lesson that answers a student's question about a data structure.
Question from the user: "{topic}"
Audience level: {level}
{analysis_prompt(a)}
Pick the structure the question is about and output a scene plan of OPERATIONS only.
If the topic is NOT about one of the allowed structures below (for example hash maps, heaps, tries, AVL trees, DFS, quicksort),
do NOT substitute a different structure. Return exactly {{"topic": "<topic>", "structure": "unsupported", "scenes": []}}. You never describe or draw states; a program runs your ops on a real structure.
Allowed structures and their ops:
{ops}
{given_prompt(given or GivenData())}

Plan rules:
- 7 to 14 scenes. Scene 1 has no ops. The last scene is the recap with no ops.
- Build the starting data with ONE init scene (graphs: all add_edge ops in one scene; bubble sort: one load).
- Middle scenes usually have exactly one op (except init and add_edge).
- Never remove from an empty structure.
- Each narration is 1 to 3 sentences, 15 to 45 words, {"simple words, no jargon" if level == "beginner" else "precise terminology and complexity notes"}.
{NARRATION_RULES}
Narration style per structure:
{styles}

Return JSON: {{"topic": str, "structure": str, "analysis": {{"intent": str, "focus": str, "must_answer": str, "core_ops": [str]}},
"answer_points": [{{"id": str, "kind": str, "point": str, "visual": str}}],
"scenes": [{{"id": int, "point_id": str, "role": "setup"|"core"|"edge_case"|"recap", "structure": str (compare lessons only), "ops": [{{"op": str, "args": [int or str]}}], "narration": str}}]}}"""


# ---------------------------------------------------------------- forcing the user's data into the plan
def _scene(ops: list[dict], narration: str | None) -> dict:
    return {"id": 0, "ops": ops, "narration": narration or PLACEHOLDER, "speed": 1.0}


def _bookends(scenes: list[dict]) -> tuple[str | None, str | None]:
    intro = scenes[0]["narration"] if scenes and not scenes[0]["ops"] else None
    recap = scenes[-1]["narration"] if len(scenes) > 1 and not scenes[-1]["ops"] else None
    return intro, recap


def _narrations_with(scenes: list[dict], op_name: str) -> list[str]:
    return [s["narration"] for s in scenes if any(o["op"] == op_name for o in s["ops"])]


def _graph_matches(plan: dict, given: GivenData) -> bool:
    ops = [o for s in plan["scenes"] for o in s["ops"]]
    edges = {frozenset(map(str, o["args"])) for o in ops if o["op"] == "add_edge"}
    starts = [str(o["args"][0]) for o in ops if o["op"] == "start_bfs"]
    if plan["structure"] != "graph_bfs" or edges != {frozenset(e) for e in given.edges} or starts != [given.start]:
        return False
    try:  # the plan must visit until the queue is empty
        final = simulate("graph_bfs", plan["scenes"])[-1]["state"]
    except OpError:
        return False
    return not final["queue"] and len(final["order"]) > 0


def conform_to_given(plan: dict, given: GivenData) -> dict:
    """Make the plan use exactly the user's data. Reuses the LLM's narration where the ops line up;
    rebuilt scenes get a placeholder that the verifier repairs with the true state."""
    scenes = plan["scenes"]
    intro, recap = _bookends(scenes)
    if given.edges:
        if _graph_matches(plan, given):
            return plan
        n_visits = _count_reachable(given)
        visits = _narrations_with(scenes, "visit")
        new = [_scene([], intro),
               _scene([{"op": "add_edge", "args": [u, v]} for u, v in given.edges], (_narrations_with(scenes, "add_edge") or [None])[0]),
               _scene([{"op": "start_bfs", "args": [given.start]}], (_narrations_with(scenes, "start_bfs") or [None])[0])]
        new += [_scene([{"op": "visit", "args": []}], visits[i] if i < len(visits) else None) for i in range(n_visits)]
        new.append(_scene([], recap))
        return {**plan, "structure": "graph_bfs", "scenes": new}
    if given.values and plan["structure"] == "bubble_sort":
        loads = [o for s in scenes for o in s["ops"] if o["op"] == "load"]
        if loads and [int(a) for a in loads[0]["args"]] == given.values:
            return plan
        steps = _narrations_with(scenes, "step")
        new = [_scene([], intro), _scene([{"op": "load", "args": list(given.values)}], None)]
        new += [_scene([{"op": "step", "args": []}], steps[i] if i < len(steps) else None) for i in range(_steps_to_sort(given.values))]
        new.append(_scene([], recap))
        return {**plan, "scenes": new}
    if given.values and plan["structure"] in INSERT_OP:
        ins = INSERT_OP[plan["structure"]]
        values = list(dict.fromkeys(given.values)) if plan["structure"] == "binary_tree" else list(given.values)
        inserted = [int(o["args"][0]) for s in scenes for o in s["ops"] if o["op"] == ins and o["args"]]
        if inserted[: len(values)] == values:
            return plan
        ins_narr = _narrations_with(scenes, ins)
        new = [_scene([], intro)] + [_scene([{"op": ins, "args": [v]}], ins_narr[i] if i < len(ins_narr) else None) for i, v in enumerate(values)]
        # keep the LLM's other operations when they still make sense on the user's data
        for s in scenes:
            if s["ops"] and all(o["op"] != ins for o in s["ops"]):
                try:
                    simulate(plan["structure"], new + [s])
                    new.append({**s})
                except OpError:
                    pass
        new.append(_scene([], recap))
        return {**plan, "scenes": new}
    return plan


def _count_reachable(given: GivenData) -> int:
    adj: dict[str, set[str]] = {}
    for u, v in given.edges:
        adj.setdefault(u, set()).add(v)
        adj.setdefault(v, set()).add(u)
    seen, stack = {given.start}, [given.start]
    while stack:
        for n in adj.get(stack.pop(), ()):
            if n not in seen:
                seen.add(n)
                stack.append(n)
    return len(seen)


def _steps_to_sort(values: list[int]) -> int:
    from structures import BubbleSort

    b = BubbleSort()
    b.apply("load", values)
    n = 0
    while not b.done and n < 200:
        b.apply("step")
        n += 1
    return n


def _salvage_what_is(topic: str, a: "focus.Analysis", raw) -> dict | None:
    """Keep the narration and answer points of a 'what is' plan whose ops were invalid; the demo ops come from code."""
    if not isinstance(raw, dict) or not isinstance(raw.get("scenes"), list):
        return None
    scenes = []
    for sc in raw["scenes"]:
        if not isinstance(sc, dict):
            continue
        ops = [{"op": o["op"], "args": list(o.get("args") or [])} for o in sc.get("ops") or []
               if isinstance(o, dict) and isinstance(o.get("op"), str) and isinstance(o.get("args", []), list)]
        scenes.append({"ops": ops, "narration": str(sc.get("narration") or ""), "point_id": sc.get("point_id") if isinstance(sc.get("point_id"), str) else None})
    try:
        plan = {"topic": topic, "structure": a.structure, "scenes": scenes, "answer_points": raw.get("answer_points")}
        return Plan.model_validate(focus.shape(plan, _with_llm_answer(a, raw))).model_dump()
    except (ValidationError, OpError, ValueError, KeyError, TypeError):
        return None


def _with_llm_answer(a: "focus.Analysis", raw) -> "focus.Analysis":
    """Use the LLM's wording of must_answer when it is a short question-like sentence; everything else stays from code."""
    llm_a = raw.get("analysis") if isinstance(raw, dict) else None
    text = llm_a.get("must_answer") if isinstance(llm_a, dict) else None
    if isinstance(text, str) and 5 <= len(text.split()) <= 30 and not any(ch.isdigit() for ch in text):
        a.must_answer = text.strip()
    return a


def focused_skeleton(topic: str, a: "focus.Analysis", given: GivenData) -> dict:
    scenes = focus.skeleton(a, list(given.values) or None, list(given.edges) or None, given.start)
    plan = {"topic": topic, "structure": a.structure, "scenes": scenes, "analysis": a.to_dict()}
    return Plan.model_validate(focus.shape(plan, a)).model_dump()


def skeleton_plan(topic: str, given: GivenData) -> dict | None:
    """A plan built entirely in code from the user's data (used if the LLM never produced a valid plan)."""
    if given.edges:
        return conform_to_given({"topic": topic, "structure": "graph_bfs", "scenes": [_scene([], None), _scene([], None)]}, given)
    return None


def complexity_plan(topic: str, a: "focus.Analysis", given: GivenData) -> dict:
    """A time complexity lesson, built and narrated in code (no LLM call): every count comes from running the real algorithm."""
    if a.algorithm == "bfs":
        data = [tuple(e) for e in given.edges] or None
        if data and given.start:  # BFS starts at the user's start node: put one of its edges first
            data.sort(key=lambda e: given.start not in e)
            if data[0][0] != given.start:
                data[0] = (data[0][1], data[0][0])
    else:
        data = list(given.values) or None
    points, scenes = complexity.build_scenes(a.algorithm, data)
    plan = Plan.model_validate({"topic": topic, "structure": a.structure, "scenes": scenes, "analysis": a.to_dict(),
                                "answer_points": points}).model_dump()
    for scene, sim in zip(plan["scenes"], simulate(plan["structure"], plan["scenes"])):
        scene["narration"] = complexity.narrate(a.algorithm, scene, sim)
    return plan


_ASK = object()


def make_plan(topic: str, level: Level = "beginner", max_retries: int = 2, first_raw=_ASK) -> dict:
    """Ask the LLM for a plan; validate shape, op names and op feasibility; retry with the error;
    then force the user's own data (labels, edges, values) into it.
    `first_raw`: a response already in hand (the question-driven call); it is used instead of a new call, with no retries,
    so falling back to this pipeline costs no extra LLM call (None = the LLM was unavailable)."""
    if first_raw is not _ASK:
        max_retries = 0
    given = parse_topic(topic)
    analysis = focus.analyze(topic, given)  # raises UnsupportedTopic for operations Structura cannot run
    if analysis is not None and analysis.intent == "complexity":
        return complexity_plan(topic, analysis, given)
    prompt = plan_prompt(topic, level, given, analysis)
    error = None
    for _ in range(max_retries + 1):
        p = prompt if error is None else (f"{prompt}\n\nYour previous answer was invalid: {error}\n"
                                          "Use only the ops listed above with exactly the listed arguments. Return the full JSON again.")
        try:
            if first_raw is not _ASK:
                if first_raw is None:
                    raise llm.LLMError("The AI is unavailable.", "ai_busy")
                raw = first_raw
            else:
                raw = llm.generate_json(p, PLAN_SCHEMA)
        except llm.LLMError:
            # the user's own graph is enough to build the lesson in code if Gemini is down
            if (fallback := skeleton_plan(topic, given)) is not None:
                return Plan.model_validate(fallback).model_dump()
            if first_raw is not _ASK and analysis is not None:
                return focused_skeleton(topic, analysis, given)
            raise
        if isinstance(raw, dict) and (raw.get("structure") == "unsupported" or raw.get("unsupported") is True) and not given.edges:
            if analysis is None:
                raise UnsupportedTopic(f'Structura cannot run "{topic}" on a real data structure yet. '
                                       f"It can explain {SUPPORTED_NAMES}. Try one of those.")
            return focused_skeleton(topic, analysis, given)  # the code knows the structure even if the LLM did not
        try:
            plan = Plan.model_validate({k: v for k, v in raw.items() if k not in ("analysis", "answer_points")} if isinstance(raw, dict) else raw).model_dump()
            if isinstance(raw, dict) and isinstance(raw.get("answer_points"), list):
                plan["answer_points"] = raw["answer_points"]
            simulate(plan["structure"], plan["scenes"])  # impossible ops raise OpError
            plan = conform_to_given(plan, given)
            simulate(plan["structure"], plan["scenes"])
            a = analysis or focus.analyze(topic, given, structure=plan["structure"])
            if a is not None:
                a = _with_llm_answer(a, raw)
                plan = focus.shape(plan, a)
            plan = Plan.model_validate(plan).model_dump()
            simulate(plan["structure"], plan["scenes"])
            return plan
        except UnsupportedTopic:
            raise
        except (ValidationError, OpError, ValueError) as e:
            error = str(e)[:800]
            # a "what is" answer builds its demo in code, so one bad op must not throw away Gemini's teaching text (and no retry call)
            if analysis is not None and focus.outline_mode(analysis) and (salvaged := _salvage_what_is(topic, analysis, raw)):
                llm.log.info("planner: kept the answer text of a plan with an invalid op (%s)", error[:120])
                return salvaged
    fallback = skeleton_plan(topic, given)
    if fallback:
        return Plan.model_validate(fallback).model_dump()
    if analysis is not None:  # the LLM never produced a valid plan: build the ops in code; narration is still written and verified
        llm.log.warning("planner: no valid plan after %d tries, using the focused skeleton: %s", max_retries + 1, error)
        return focused_skeleton(topic, analysis, given)
    llm.log.warning("planner: no valid plan after %d tries: %s", max_retries + 1, error)
    raise llm.LLMError("The AI could not plan this lesson. Please try again or rephrase the topic.", "bad_plan")


# ---------------------------------------------------------------- narration repair (true state included)
def fix_scenes_batch(structure: str, items: list[dict], ctx: dict | None = None) -> dict[int, str]:
    """ONE LLM call that rewrites every failing scene, given each scene's true state, role, purpose and the problems found."""
    blocks = []
    ctx_points = (ctx or {}).get("points", {})
    for it in items:
        scene, sim = it["scene"], it["sim"]
        role = scene.get("role") or ("recap or concept" if not scene.get("ops") else "operation scene")
        blocks.append({
            "index": it["index"],
            "role": "intro (first scene, no ops)" if it.get("intro") else role,
            **({"purpose": scene["note"]} if scene.get("note") else {}),
            **({"teaches": f"{scene['kind']}: {ctx_points.get(scene.get('point_id'), '')}".strip(": ")} if scene.get("kind") else {}),
            **({"structure": it["structure"]} if it.get("structure") and it.get("structure") != structure else {}),
            "ops": scene.get("ops", []),
            "true_state_before": compact_state(sim["before"]),
            "true_state_after_each_op": [compact_state(s) for s in sim["steps"]],
            "current_narration": scene.get("narration", ""),
            "problems": it["errors"],
        })
    question = ""
    if ctx:
        question = (f"The lesson answers the question: \"{ctx['must_answer']}\" (focus: {ctx['focus_text']}).\n"
                    "Roles: intro = at most 25 words leading into the question"
                    + (" (ONE plain definition sentence; the analogy has its own scene)" if ctx.get("outline")
                       else " (definition + analogy)" if ctx["intent"] == "what_is" else ", no textbook definition")
                    + "; setup = short, names the data; core = explains the mechanism step by step in " + ("1 or 2 short sentences" if ctx.get("beginner") else "2 or 3 sentences, naming pointers and links") + "; "
                    "edge_case = one short edge case; recap = restates the ANSWER (the steps or key ideas), not numbers.\n"
                    "Every sentence must serve that question; never add facts about unrelated operations. "
                    "Each scene teaches ONE answer point (\"teaches\"): an analogy compares to something familiar, the rule scene states the rule "
                    "and its vocabulary, a demo step says what it shows about the rule, a uses scene names real-world uses, and the recap gives "
                    "takeaways in new wording.\n"
                    + _vocab_prompt(ctx.get("structure", structure)) + "\n")
    beginner = bool(ctx and ctx.get("beginner"))
    if beginner:
        import answer
        style = answer.style_guide(ctx.get("question") or ctx.get("must_answer") or structure)
    prompt = f"""Rewrite the narration of these scenes of a {structure.replace('_', ' ')} lesson.
{question}Each scene comes with its TRUE state from a real data structure. Use those exact values and labels; never invent others.
Fix every listed problem. Each narration is {"1 or 2 short sentences (at most 25 words each)" if beginner else "1 to 3 sentences"}.
{NARRATION_RULES}
{style if beginner else "Style for this structure: " + STYLE.get(structure, "")}

Scenes:
{json.dumps(blocks, indent=1)}

Return JSON: {{"scenes": [{{"index": int, "narration": str}}]}} with one entry per scene above."""
    data = llm.generate_json(prompt, {"type": "object", "properties": {"scenes": {"type": "array", "items": {
        "type": "object", "properties": {"index": {"type": "integer"}, "narration": {"type": "string"}}, "required": ["index", "narration"]}}}})
    out: dict[int, str] = {}
    for row in data.get("scenes", []) if isinstance(data, dict) else []:
        if isinstance(row, dict) and isinstance(row.get("index"), int) and isinstance(row.get("narration"), str):
            out[row["index"]] = row["narration"].strip()
    return out


def fix_scene_narration(structure: str, scene: dict, sim: dict, errors: list[str], instruction: str = "") -> str:
    """Ask the LLM to rewrite ONE scene's narration (used by revisions), with its true state."""
    goal = (f"Rewrite the narration of one scene of a {structure} lesson following this instruction from the viewer: "
            f"\"{instruction}\". Keep it factually correct, 1 to 3 sentences, 20 to 50 words.")
    if not instruction:
        goal = f"Rewrite the narration of one scene of a {structure} lesson so it is factually correct and specific."
    prompt = f"""{goal}
Ops in this scene: {json.dumps(scene.get("ops", []))}
True state before the scene: {json.dumps(compact_state(sim["before"]))}
True state after each op: {json.dumps([compact_state(s) for s in sim["steps"]])}
Current narration: "{scene.get("narration", "")}"
{"Problems found: " + "; ".join(errors) if errors else ""}
{NARRATION_RULES}
Style for this structure: {STYLE.get(structure, "")}
Return JSON: {{"narration": str}} with 1 to 3 sentences."""
    data = llm.generate_json(prompt, {"type": "object", "properties": {"narration": {"type": "string"}}, "required": ["narration"]})
    return str(data["narration"]).strip()
