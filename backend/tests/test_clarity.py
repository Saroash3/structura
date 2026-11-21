"""CLARITY GATE (Beginner mode): every explanation must be understandable to a total beginner who has never programmed.

Golden lessons for "what is a linked list and why do we use it", "what is a queue", "what is stack", "what is array",
"how does a binary search tree work" and "show BFS step by step on a small graph".
The fake LLM plans them the way the real one did before this gate: a jargon wall in one scene ("Node means a container
holding a value and a pointer ... Pointer means a reference ... in memory"), FIFO before any picture, filler ("extremely
efficient ... instantly"), steps told only in technical words, and no problem shown for "why". The repair call fixes
nothing (the weakest case), so the clarity gate, the plain templates and the scene split alone must make the lesson clear.
"""
import re

import pytest

import answer
import clarity
import concepts
import lesson
import llm
from verifier import check_scene

LL_WHY = "what is a linked list and why do we use it"


def _plan(q: str, subject: str, reqs: list[tuple[str, str]], scenes: list[tuple[str, list, str]]) -> dict:
    requirements = [{"id": f"r{i}", "text": t, "evidence": e, "structure": subject} for i, (t, e) in enumerate(reqs, 1)]
    points = [{"id": f"p{i}", "requirement_id": f"r{i}", "kind": "explain", "point": t[0].upper() + t[1:] + "."} for i, (t, _e) in enumerate(reqs, 1)]
    out = [{"point_id": pid, "role": "setup" if pid == "intro" else "recap" if pid == "recap" else "core",
            "ops": [{"op": o, "args": a} for o, a in ops], "narration": text} for pid, ops, text in scenes]
    return {"topic": q, "structure": subject, "analysis": {"subject": subject, "ask": q[0].upper() + q[1:] + "?", "key_terms": [subject.replace("_", " ")],
                                                          "jargon": [], "requirements": requirements}, "answer_points": points, "scenes": out}


BAD_PLANS = {
    LL_WHY: _plan(LL_WHY, "linked_list",
                  [("a linked list is a chain of nodes, each holding a value and a pointer to the next node", "state"),
                   ("we use it because inserting needs no shifting of other items", "trace")],
                  [("intro", [], "Let us explore what a linked list is and why we use it."),
                   ("p1", [("init", [10, 20, 30])],
                    "Here is our list: head -> 10 -> 20 -> 30 -> null. This shows: a linked list is a chain of nodes where each node holds a value "
                    "and a pointer to the next node. Node means a container holding a value and a pointer to the next item. Pointer means a reference "
                    "or link that tells us where to find the next item in memory."),
                   ("p2", [("insert_head", [5])],
                    "We use linked lists because adding new items is extremely efficient. By inserting 5 at the head, the new node points directly to 10, "
                    "updating the chain instantly without shifting any other items: head -> 5 -> 10 -> 20 -> 30 -> null."),
                   ("recap", [], "In summary, a linked list connects discrete nodes using pointers, allowing us to insert items quickly without "
                                 "rearranging the entire collection.")]),
    "what is a queue": _plan("what is a queue", "queue",
                             [("a queue is a line where items join at the back and leave from the front", "state"),
                              ("enqueue adds an item at the back", "trace"), ("dequeue removes the item at the front", "trace")],
                             [("intro", [], "Let's explore how a queue organizes data just like a line of people waiting for tickets."),
                              ("p1", [("init", [10, 20, 30])], "A queue is a data structure that follows FIFO, which means First In, First Out. "
                                                               "The items are now 10, 20, and 30, with 10 at the front."),
                              ("p2", [("enqueue", [40])], "Enqueue 40 at the back. The front is 10, the back is 40. This shows: enqueue adds new items "
                                                          "to the back of the queue. Enqueue means adding an item to the back of the line."),
                              ("p3", [("dequeue", [])], "Dequeue 10 from the front. The front is now 20. This shows: dequeue removes items from the front "
                                                        "of the queue. Dequeue means removing an item from the front of the line."),
                              ("recap", [], "In summary, a queue manages items in a strict arrival order where newcomers wait at the back and the oldest "
                                            "members leave from the front.")]),
    "what is stack": _plan("what is stack", "stack",
                           [("a stack only lets you add or remove at the top", "state"), ("push adds an item on the top", "trace"),
                            ("pop removes the top item, so the last in is the first out", "trace")],
                           [("intro", [], "A stack is a LIFO data structure that leverages a robust top pointer."),
                            ("p1", [("init", [10, 20, 30])], "We push 10, 20 and 30 onto the stack, so the top is 30."),
                            ("p2", [("push", [40])], "Push 40. The top is now 40."),
                            ("p3", [("pop", [])], "Pop 40. The top is now 30, which demonstrates LIFO behaviour seamlessly."),
                            ("recap", [], "In summary, a stack is a LIFO structure where push and pop work at the top.")]),
    "what is array": _plan("what is array", "array",
                           [("an array keeps values in numbered slots side by side", "state"), ("any slot can be read directly by its index", "trace"),
                            ("inserting in the middle shifts later items", "trace")],
                           [("intro", [], "An array stores elements in contiguous memory, indexed from 0."),
                            ("p1", [("init", [10, 20, 30, 40])], "The array holds elements 10, 20, 30 and 40 in contiguous memory locations addressed by an index."),
                            ("p2", [("get", [2])], "Accessing index 2 returns 30 instantly in constant time because of pointer arithmetic on the base address."),
                            ("p3", [("insert_at", [1, 15])], "Insert 15 at index 1; later elements shift right. Array is now [10, 15, 20, 30, 40]."),
                            ("recap", [], "Arrays give O(1) access but O(n) insertion.")]),
    "how does a binary search tree work": _plan("how does a binary search tree work", "binary_tree",
                           [("smaller values go left and larger values go right at every node", "trace"),
                            ("searching follows one path from the root, skipping half of the tree at each step", "trace")],
                           [("intro", [], "A binary search tree is a robust hierarchical structure where every leaf and the root obey the BST property."),
                            ("p1", [("init", [50, 30, 70])], "We insert 50, 30 and 70. The root node is 50, and nodes with no children are leaves leaves."),
                            ("p1", [("insert_bst", [60])], "Insert 60: compare with the root 50, go right to 70, then go left. 60 becomes a leaf node."),
                            ("p2", [("search_bst", [60])], "Searching 60 is extremely efficient: 50, 70, 60, in logarithmic time time complexity."),
                            ("recap", [], "In summary, a leaf is a node with no children, and BSTs search in O(log n).")]),
    "show BFS step by step on a small graph": _plan("show BFS step by step on a small graph", "graph_bfs",
                           [("BFS visits the start, then all its neighbours, then their neighbours, using a queue", "trace")],
                           [("intro", [], "BFS is an algorithm that uses a FIFO queue to traverse the nodes and edges of a graph instantly."),
                            ("p1", [("add_edge", ["A", "B"]), ("add_edge", ["A", "C"]), ("add_edge", ["B", "D"]), ("add_edge", ["C", "D"])],
                             "Edges A-B, A-C, B-D and C-D are added to the adjacency list of the graph."),
                            ("p1", [("start_bfs", ["A"])], "Start at A, then visit A."),
                            ("p1", [("visit", [])], "Dequeue A and enqueue its unvisited neighbours B and C."),
                            ("p1", [("visit", [])], "Dequeue B and enqueue D."),
                            ("p1", [("visit", [])], "Dequeue C. D is already queued."),
                            ("p1", [("visit", [])], "Dequeue D. The queue is empty, so BFS terminates seamlessly."),
                            ("recap", [], "In summary, BFS explores the graph level by level using a queue.")]),
}


def _run(monkeypatch, q: str, plan: dict, judge=None) -> tuple[dict, list]:
    calls = []

    def fake(prompt, schema=None):
        calls.append(prompt)
        if "You check whether a short lesson answers" in prompt:
            return judge(prompt) if judge else {"requirements": [], "does_lesson_answer_question": True, "clarity": [], "fixes": []}
        if "Rewrite the narration" in prompt:
            return {"scenes": []}  # the weakest repair: nothing is fixed by the LLM
        return plan
    monkeypatch.setattr(llm, "generate_json", fake)
    monkeypatch.setattr(lesson.tts, "synthesize", lambda text: {"id": "x", "path": None, "duration": len(text.split()) / 2.5})
    lesson._scene_cache.clear()
    return lesson.build_lesson(q, "beginner"), calls


def _ctx(r: dict) -> dict:
    return answer.context(r["plan"])


def assert_clear(r: dict, q: str) -> None:
    scenes, ctx = r["scenes"], _ctx(r)
    assert ctx.get("beginner")
    for s in scenes:
        sents = clarity.sentences(s["narration"])
        assert len(sents) <= 2, f"scene {s['id']} has {len(sents)} sentences: {s['narration']}"
        for sent in sents:
            assert clarity.word_count(sent) <= 25, f"scene {s['id']}: {sent}"
        assert not re.search(concepts.FILLER, s["narration"], re.I), s["narration"]
    texts = [s["narration"] for s in scenes]
    problems = clarity.lesson_clarity(texts, scenes, [s["state"]["kind"] for s in scenes], ctx, [s["state"] for s in scenes])
    assert not problems, problems  # no term before its plain definition, no circular definition, analogy in >= 70% of demos
    for s in scenes:
        assert not clarity.repeated_word(s["narration"]), s["narration"]  # no "time time"
        shown, missing = clarity.named_parts(s["narration"], s["state"])
        assert not missing, (s["narration"], missing)  # every named part (root, leaf, head, tail) is on screen
        assert sorted(s.get("named", [])) == sorted(shown)  # ... and handed to the stage to highlight
        assert not re.search(r"\bstart at (\w+), then visit \1\b", s["narration"], re.I), s["narration"]  # never "start at A, then visit A"
    demo = [s for s in scenes if s["ops"]]
    words = concepts.ANALOGY[r["structure"]]["words"]
    with_analogy = [s for s in demo if re.search(words, s["narration"], re.I) or s.get("analogy")]
    assert len(with_analogy) >= 0.7 * len(demo)
    for i, s in enumerate(scenes):  # every sentence still verified against the true state
        sim = {"before": s["before"], "steps": s["steps"], "state": s["state"]}
        kind = r["plan"]["structure"] if i == 0 and not s["steps"] else s["state"]["kind"]
        assert not check_scene(kind, s, sim, i == 0, ctx), (s["narration"], check_scene(kind, s, sim, i == 0, ctx))
    if re.search(concepts.WHY_QUESTION, q, re.I):
        kinds = [s.get("kind") for s in scenes]
        assert "problem" in kinds and "fix" in kinds and kinds.index("problem") < len(kinds) - 1 - kinds[::-1].index("fix"), kinds


@pytest.mark.parametrize("q", list(BAD_PLANS))
def test_golden_lessons_are_clear_for_a_total_beginner(monkeypatch, q):
    r, calls = _run(monkeypatch, q, BAD_PLANS[q])
    assert len(calls) <= 3
    assert r["judge"]["passed"]
    assert_clear(r, q)


def test_the_why_question_shows_the_problem_before_the_fix(monkeypatch):
    r, _ = _run(monkeypatch, LL_WHY, BAD_PLANS[LL_WHY])
    problem = next(s for s in r["scenes"] if s.get("kind") == "problem")
    fix = next(s for s in r["scenes"] if s.get("kind") == "fix")
    assert problem["state"]["kind"] == "array" and any(o["op"] == "insert_at" for o in problem["ops"])  # the real shifting
    assert re.search(r"\bmoves? a locker\b|\bshift", problem["narration"], re.I)
    assert fix["state"]["kind"] == "linked_list" and any(o["op"] in ("insert_after", "insert_head", "insert_tail", "delete_value") for o in fix["ops"])
    assert r["scenes"].index(problem) < r["scenes"].index(fix)


def test_scenes_show_the_analogy_tag(monkeypatch):
    r, _ = _run(monkeypatch, "what is a queue", BAD_PLANS["what is a queue"])
    tagged = [s for s in r["scenes"] if s.get("analogy")]
    assert tagged and all(s["analogy"] == "like a line of people" for s in tagged)


def test_good_beginner_narration_is_kept(monkeypatch):
    good = _plan("what is a queue", "queue", [("a queue is a line: join at the back, leave from the front", "trace")],
                 [("intro", [], "What is a queue? Picture people waiting in a line."),
                  ("p1", [("init", [10, 20, 30])], "Picture a line of people: 10, 20 and 30 wait in that order, with 10 at the front."),
                  ("p1", [("enqueue", [40])], "A new person, 40, joins the back of the line, and we call this enqueue. "
                                              "40 waits behind everyone else, so 10 is still at the front."),
                  ("p1", [("dequeue", [])], "The person at the front, 10, leaves the line, and we call this dequeue. "
                                            "10 arrived first, so 10 leaves first, and 20 is now at the front."),
                  ("recap", [], "To sum up, people join the back of a queue and leave from the front.")])
    r, _ = _run(monkeypatch, "what is a queue", good)
    assert [s["narration_source"] for s in r["scenes"]] == ["llm"] * len(r["scenes"])
    assert_clear(r, "what is a queue")


def test_intermediate_lessons_skip_the_beginner_gate(monkeypatch):
    plan = BAD_PLANS["what is a queue"]
    calls = []
    monkeypatch.setattr(llm, "generate_json", lambda p, s=None: calls.append(p) or (
        {"requirements": [], "does_lesson_answer_question": True, "fixes": []} if "You check whether" in p else {"scenes": []} if "Rewrite" in p else plan))
    monkeypatch.setattr(lesson.tts, "synthesize", lambda text: {"id": "x", "path": None, "duration": len(text.split()) / 2.5})
    lesson._scene_cache.clear()
    r = lesson.build_lesson("what is a queue", "intermediate")
    assert not answer.context(r["plan"]).get("beginner")
    assert "BEGINNER STYLE GUIDE" not in calls[0]
    assert not any(s.get("analogy") for s in r["scenes"])


def test_the_beginner_prompts_carry_the_style_guide(monkeypatch):
    _, calls = _run(monkeypatch, "what is a queue", BAD_PLANS["what is a queue"])
    plan_prompt, repair_prompt, judge_prompt = calls[0], calls[1], calls[-1]
    for p in (plan_prompt, repair_prompt, judge_prompt):
        assert "BEGINNER STYLE GUIDE" in p and "a line of people" in p
    assert "12-year-old" in judge_prompt


# ---------------------------------------------------------------- the gate catches each problem found in real lessons
def _flags(texts: list[str], structure: str, ops_at=(), question: str = "") -> dict[int, list[str]]:
    scenes = [{"ops": [{"op": "x"}] if i in ops_at else []} for i in range(len(texts))]
    return clarity.lesson_clarity(texts, scenes, [structure] * len(texts), {"structure": structure, "question": question})


def test_a_jargon_wall_is_flagged():
    text = BAD_PLANS[LL_WHY]["scenes"][1]["narration"]
    flags = " ".join(_flags(["Intro.", text], "linked_list", ops_at=(1,))[1])
    assert "at most 2 short sentences" in flags
    assert "explained with another unexplained word" in flags  # "Pointer means a reference ... in memory"


def test_a_circular_definition_is_flagged():
    flags = _flags(["Pointer means a reference or link that tells us where to find the next item in memory."], "linked_list")
    assert any("memory" in f and "unexplained" in f for f in flags[0])


def test_fifo_before_the_picture_is_flagged():
    flags = _flags(["A queue follows FIFO, which means First In, First Out.", "40 joins the line."], "queue", ops_at=(1,))
    assert any("Picture first" in f for f in flags[0])


def test_a_garbled_gloss_is_flagged():
    flags = _flags(["Add 15 between 10 and 20 in memory, which means the computer storage space for data."], "linked_list")
    assert any("garbled" in f for f in flags[0])


def test_filler_and_long_sentences_are_flagged():
    flags = _flags(["Adding is extremely efficient and happens instantly.",
                    "This sentence is far too long for a beginner because it keeps going and going with clause after clause after clause and never stops anywhere at all."],
                   "linked_list")
    assert any("filler" in f for f in flags[0]) and any("words (max 25)" in f for f in flags[1])


def test_steps_without_the_analogy_are_flagged():
    flags = _flags(["What is a queue?", "Enqueue 40 at the back.", "Dequeue 10 from the front.", "The person 20 is now at the front of the line."],
                   "queue", ops_at=(1, 2, 3), question="what is a queue")
    assert any("running analogy" in f for f in flags.get(1, []))


def test_picture_first_definitions_pass():
    texts = ["What is a linked list?",
             "Picture boxes in a treasure hunt: each box holds a note saying where the next box is. That note is called a pointer.",
             "Box 10's pointer leads to box 20."]
    assert not _flags(texts, "linked_list", ops_at=(1, 2), question="what is a linked list")


def test_the_question_may_name_its_own_terms_in_the_intro():
    assert not _flags(["How do pointers work in a linked list?"], "linked_list", question="how do pointers work in a linked list")


@pytest.mark.parametrize("q", ["what is a stack", "how does bubble sort work", "how do I delete a node from the middle of a linked list",
                               "what is the difference between BFS and DFS", "when should I use an array instead of a linked list",
                               "trace BFS on this graph: A-B, A-C, B-D, C-D starting from A", "best and worst case of insertion sort"])
def test_varied_questions_stay_short_and_explained(monkeypatch, q):
    import test_question_driven as qd
    r, _ = _run(monkeypatch, q, qd._raw(q))
    for s in r["scenes"]:
        sents = clarity.sentences(s["narration"])
        assert len(sents) <= 2 and all(clarity.word_count(x) <= 25 for x in sents), s["narration"]
    assert not r["judge"].get("unclear_after"), r["judge"]["unclear_after"]


def test_a_glossary_sentence_glued_to_the_step_is_flagged():
    texts = ["What is an array?", "Picture a row of lockers holding 10, 20 and 30.",
             "The value inside a locker is called an element, so at index 2 the element is 30."]
    flags = _flags(texts, "array", ops_at=(1, 2), question="what is an array")
    assert any("glued" in f for f in flags.get(2, []))
    ok = ["What is a stack?", "We put plate 40 on top of the pile, and we call this push. So 40 is now the top plate."]
    assert not _flags(ok, "stack", ops_at=(1,), question="what is a stack")


def test_a_fix_scene_labelled_by_the_llm_gets_the_real_fix_ops(monkeypatch):
    plan = _plan(LL_WHY, "linked_list", [("a linked list is boxes joined by notes", "state"), ("an array must shift values to insert", "trace"),
                                         ("a linked list changes only notes", "trace")],
                 [("intro", [], "What is a linked list, and why do we use it?"),
                  ("p1", [("init", [10, 20, 30])], "Picture boxes 10, 20 and 30 in a treasure hunt."),
                  ("p2", [], "An array must shift values."), ("p3", [("walk", [10])], "We walk to box 10."),
                  ("recap", [], "To sum up, a linked list changes notes instead of moving boxes.")])
    plan["answer_points"][1]["kind"], plan["answer_points"][2]["kind"] = "problem", "fix"
    r, _ = _run(monkeypatch, LL_WHY, plan)
    problem = next(s for s in r["scenes"] if s.get("kind") == "problem")
    fix = next(s for s in r["scenes"] if s.get("kind") == "fix")
    assert problem["state"]["kind"] == "array" and fix["point_id"] == "p3"  # the LLM's own scenes, with real ops
    assert any(o["op"] == "insert_after" for o in fix["ops"]) and r["scenes"].index(problem) < r["scenes"].index(fix)


@pytest.mark.parametrize("text", ["Putting a new plate on top of the pile is called push, so 25 goes on top.",
                                  "The lockers stand side by side in the computer's storage space, which is called memory, so index 0 holds 10."])
def test_more_glued_definitions_are_flagged(text):
    structure = "stack" if "plate" in text else "array"
    flags = _flags(["Intro?", "Picture it.", text], structure, ops_at=(1, 2), question="what is it")
    assert any("glued" in f for f in flags.get(2, [])), flags


def test_a_step_on_the_other_structure_uses_its_own_analogy():
    texts = ["Why use a linked list?", "Picture a treasure hunt with boxes 10 and 30.",
             "In a treasure hunt with values 10 and 30, inserting in the middle forces later items to shift."]
    scenes = [{"ops": []}, {"ops": [{"op": "init"}]}, {"ops": [{"op": "init"}]}]
    flags = clarity.lesson_clarity(texts, scenes, ["linked_list", "linked_list", "array"], {"structure": "linked_list", "question": "why use a linked list"})
    assert any("not the linked list" in f for f in flags.get(2, []))


def test_a_correct_answer_is_kept_even_if_not_perfectly_clear(monkeypatch):
    """Regression ("what is time complexity for insertion a new element an array"): the judge's fix stated the answer,
    O(1) at the end and O(n) in the middle, but used "time complexity" and Big-O unexplained. Answer first: the fix is kept,
    with the plain definitions put in front, and "value" counts for the key term "element"."""
    q = "what is time complexity for insertion a new element an array"
    plan = _plan(q, "array", [("insertion at the end needs no shifting", "trace"), ("insertion in the middle shifts later items", "trace"),
                              ("state the time complexity for both cases", "none")],
                 [("intro", [("init", [10, 20, 30])], "Picture a row of lockers holding 10, 20 and 30, numbered from 0 on the left."),
                  ("p1", [("append", [40])], "We put 40 in the next free locker, position 3."),
                  ("p2", [("insert_at", [1, 99])], "We squeeze 99 into the locker in position 1, so every later value moves a locker to the right."),
                  ("p3", [], "Adding at the end is quick, and adding in the middle takes more work."),
                  ("recap", [], "To sum up, adding at the end is quick and adding in the middle is slow.")])
    plan["analysis"]["key_terms"] = ["time complexity", "insert", "element", "array"]
    fix = "Adding at the end takes constant time complexity, O(1), for an array. Inserting in the middle takes linear time complexity, O(n)."

    def judge(prompt):
        idx = next(i for i, line in enumerate(re.findall(r'"narration": "([^"]*)"', prompt)) if "more work" in line)
        return {"requirements": [{"id": "r3", "covered": False, "reason": "never states the time complexity"}],
                "does_lesson_answer_question": False, "clarity": [], "fixes": [{"index": idx, "narration": fix}]}
    r, calls = _run(monkeypatch, q, plan, judge=judge)
    assert len(calls) <= 3 and r["judge"]["passed"]
    text = " ".join(s["narration"] for s in r["scenes"])
    assert "O(1)" in text and "O(n)" in text
    assert text.index("is called time complexity") < text.index("constant time complexity")  # explained before use


def test_a_missing_key_term_is_introduced_with_a_real_sentence():
    """Never "This is about the BFS.": the safety net says what the short name stands for."""
    assert concepts.name_sentence("BFS", "graph_bfs") == "The way we just explored has a short name: BFS, which stands for breadth first search."
    assert "This is about" not in concepts.name_sentence("anything", None)
    assert re.search(concepts.KEY_TERM_PLAIN["bfs"], "breadth first search visits the nearest places first", re.I)


def test_a_phrase_said_twice_in_one_scene_is_flagged():
    taut = "The first one in is the first one out, like a real line, and this is called first in, first out, like a real line."
    assert clarity.repeated_phrase(taut) == "out like a real line"
    assert clarity.repeated_phrase("To add 60, we start at the top and follow the forks: 50, then 70, then 60.") is None


def test_a_name_is_said_once_even_when_first_named_at_the_end_of_a_sentence():
    state = {"kind": "queue", "items": []}
    base = {"ops": [], "steps": [], "before": state, "state": state, "speed": 1.0, "duration": 1.0}
    scenes = [{**base, "id": 1, "narration": "The places waiting their turn form a waiting line, which is called a queue."},
              {**base, "id": 2, "narration": "The waiting line, called a queue, is now empty."}]
    import lesson as L
    out = L.trim_repeats(scenes, {})
    assert out[1]["narration"] == "The waiting line is now empty."
