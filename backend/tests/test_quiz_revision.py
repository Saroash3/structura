import json
import re

import pytest

import lesson
import quiz
import revision
from structures import make


def _offline_llm(*args, **kwargs):
    raise RuntimeError("offline")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(lesson.tts, "synthesize", lambda text: {"id": "x", "path": None, "duration": len(text.split()) / 2.5})
    monkeypatch.setattr(quiz.llm, "generate_json", _offline_llm)
    lesson._scene_cache.clear()


@pytest.mark.parametrize("structure", list(quiz.ASKS))
def test_quiz_answers_are_computed(structure):
    qs = quiz.make_quiz(structure, seed="t")
    assert len(qs) == 3
    for q in qs:
        assert len(q["options"]) == 4 and len(set(q["options"])) == 4
        assert q["options"][q["answer_index"]] in q["explanation"]


def test_queue_quiz_uses_lesson_ops_and_real_answers():
    plan = {"structure": "queue", "scenes": [{"ops": [{"op": "enqueue", "args": [v]}]} for v in (11, 22, 33)]
            + [{"ops": [{"op": "dequeue", "args": []}]}]}
    qs = quiz.lesson_questions(plan, "seed-1")
    assert qs and len(qs) == 3
    first = qs[0]["question"]  # asks about the state after ALL the lesson's ops, never a "first k ops" prefix
    ops_txt = first.split("operations (")[1].split("), what")[0]
    ds = make("queue")
    for part in ops_txt.split(", "):
        op, *arg = part.split()
        st = ds.apply(op, [int(a) for a in arg])
    assert len(ops_txt.split(", ")) == 4
    assert qs[0]["options"][qs[0]["answer_index"]] == str(st["front"])
    for q in qs:  # only the lesson's own values appear as data
        assert set(re.findall(r"\b\d{2}\b", q["question"])) <= {"11", "22", "33"}


def test_quiz_rejects_rewording_that_changes_numbers(monkeypatch):
    monkeypatch.setattr(quiz.llm, "generate_json", lambda *a, **k: {"questions": ["Totally different 1?", "x", "y"]})
    templates = quiz.template_questions("stack", "s")
    assert [q["question"] for q in quiz.make_quiz("stack", "s")] == [q["question"] for q in templates]


PLAN = {"topic": "queue", "structure": "queue", "scenes": [
    {"id": 1, "ops": [], "narration": "A queue is first in, first out, like a line of people waiting for a bus to arrive at the stop."},
    {"id": 2, "ops": [{"op": "enqueue", "args": [5]}], "narration": "We enqueue 5. The front is 5 and the size is 1."},
    {"id": 3, "ops": [{"op": "enqueue", "args": [6]}], "narration": "We enqueue 6. The front is 5 and the back is 6."},
    {"id": 4, "ops": [{"op": "dequeue", "args": []}], "narration": "We dequeue 5. The front is 6 and the size is 1."},
    {"id": 5, "ops": [], "narration": "That is a queue: items leave in the same order they arrive, from the front to the back of the line."},
]}


def test_revise_speed_changes_only_that_scene():
    base = lesson.build_from_plan(PLAN)
    out = revision.revise(base["plan"], None, "slow down step 4")
    assert out["revised"]["scene_id"] == 4 and out["revised"]["change"] == "speed"
    for a, b in zip(base["scenes"], out["scenes"]):
        if a["id"] == 4:
            assert b["speed"] == 0.75
        else:
            assert a == b


def _fake_rewrites(monkeypatch, *texts):
    """The LLM answers each rewrite request with the next text (the last one repeats)."""
    calls = []
    def fake(prompt, *a, **k):
        calls.append(prompt)
        return {"narration": texts[min(len(calls), len(texts)) - 1]}
    monkeypatch.setattr(revision.llm, "generate_json", fake)
    return calls


def _dequeue_id(base):
    return next(s["id"] for s in base["scenes"] if s["ops"] and s["ops"][0]["op"] == "dequeue")


def test_revise_simpler_really_changes_the_text_and_nothing_else(monkeypatch):
    base = lesson.build_from_plan(PLAN)
    sid = _dequeue_id(base)
    simple = "The person at the front of the line, 5, leaves first. Now the front is 6, and the size is 1."
    _fake_rewrites(monkeypatch, simple)
    out = revision.revise(base["plan"], sid, "explain step %d in simpler words for a beginner" % sid, base["scenes"])
    old, new = base["scenes"][sid - 1], out["scenes"][sid - 1]
    assert out["revised"]["change"] == "narration"
    assert new["narration"] == simple and new["narration"] != old["narration"]
    assert revision.similarity(new["narration"], old["narration"]) <= revision.SAME_RATIO
    assert out["revised"]["before"] == old["narration"] and out["revised"]["after"] == simple
    assert new["ops"] == old["ops"] and new["state"] == old["state"] and new["steps"] == old["steps"] and new["verified"]
    for i, (a, b) in enumerate(zip(base["scenes"], out["scenes"])):
        if i != sid - 1:
            assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)  # byte-identical
    assert out["plan"]["scenes"][sid - 1]["narration"] == simple


def test_revise_retries_once_with_the_reasons_when_the_first_try_is_wrong(monkeypatch):
    base = lesson.build_from_plan(PLAN)
    sid = _dequeue_id(base)
    simple = "The person at the front of the line, 5, leaves first. Now the front is 6, and the size is 1."
    calls = _fake_rewrites(monkeypatch, "We dequeue 99. Wrong on purpose.", simple)
    out = revision.revise(base["plan"], sid, "make it simpler", base["scenes"])
    assert len(calls) == 2 and "rejected" in calls[1]
    assert out["scenes"][sid - 1]["narration"] == simple and "99" not in out["scenes"][sid - 1]["narration"]


def test_revise_that_cannot_change_the_text_says_so_honestly(monkeypatch):
    base = lesson.build_from_plan(PLAN)
    sid = _dequeue_id(base)
    old = base["scenes"][sid - 1]["narration"]
    calls = _fake_rewrites(monkeypatch, old.replace(".", "!"))  # a near-copy, both times
    out = revision.revise(base["plan"], sid, "explain step %d in simpler words for a beginner" % sid, base["scenes"])
    assert len(calls) == 2  # one retry with a stronger instruction
    assert "Be stricter" in calls[1] and "almost the same" in calls[1]
    assert out["revised"]["change"] == "none" and out["revised"]["message"] == revision.NO_CHANGE
    assert [json.dumps(s, sort_keys=True) for s in out["scenes"]] == [json.dumps(s, sort_keys=True) for s in base["scenes"]]


def test_revise_wrong_facts_are_never_shipped_and_never_called_rewritten(monkeypatch):
    base = lesson.build_from_plan(PLAN)
    sid = _dequeue_id(base)
    _fake_rewrites(monkeypatch, "We dequeue 99. Wrong on purpose.")
    out = revision.revise(base["plan"], sid, "explain for a beginner")
    assert out["revised"]["change"] == "none"
    assert out["scenes"][sid - 1]["narration"] == base["scenes"][sid - 1]["narration"]


def test_simplify_prompt_carries_the_beginner_rules(monkeypatch):
    base = lesson.build_from_plan(PLAN)
    sid = _dequeue_id(base)
    calls = _fake_rewrites(monkeypatch, "x")
    revision.revise(base["plan"], sid, "simpler please")
    p = calls[0]
    assert "At most 2 sentences" in p and "20 words" in p and "line" in p  # the queue's analogy
    assert "front is 6" in p or "6" in p


def test_revise_rejects_bad_scene():
    base = lesson.build_from_plan(PLAN)
    with pytest.raises(revision.RevisionError):
        revision.revise(base["plan"], None, "slow down step 40")


def test_lesson_is_padded_to_30_seconds():
    short = {**PLAN, "scenes": PLAN["scenes"][:2]}
    out = lesson.build_from_plan(short)
    assert out["total_duration"] >= 30


def test_quiz_distractors_are_plausible_answers_to_the_same_question():
    """Wrong options must be believable answers to THIS question, never another structure's behaviour."""
    import concepts
    import random
    plan = {"structure": "binary_tree", "scenes": [{"ops": [{"op": "init", "args": [50, 30, 70]}]}, {"ops": [{"op": "insert_bst", "args": [60]}]}]}
    sims = quiz.simulate("binary_tree", plan["scenes"])
    q = quiz._principle_question(random.Random(1), "binary_tree", plan, sims)
    assert set(q["options"]) == {"left", "right", "it becomes the new root", "it goes to whichever side has fewer values"}
    silly = re.compile(r"end of a list|sorts? the (?:stack|queue)|undoing|\bitself\b", re.I)
    for table in (concepts.REAL_WORLD_QUIZ, concepts.VOCAB_QUIZ):
        for name, (_q, _a, wrong, _e) in table.items():
            assert not any(silly.search(w) for w in wrong), (name, wrong)
