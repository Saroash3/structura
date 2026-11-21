"""CLARITY GATE (Beginner mode): verified facts are necessary but not sufficient; every sentence must also be clear to a
total beginner who has never programmed.

Deterministic checks over the whole lesson, in reading order:
  * at most 2 sentences per scene (scenes without ops are split instead, see split_scenes) and 25 words per sentence
    (a chain "head -> 10 -> null" or a bracketed list counts as one word);
  * every term a beginner does not know (concepts.NEEDS_DEFINITION) is explained in plain words before, or in the
    sentence where, it is first used, and never with another term that is still unexplained (no circular definitions);
  * no "in memory, which means ..." glosses hung on a word in the middle of a sentence (they read as garbled);
  * FIFO / LIFO only after the learner has seen the demo (picture first, name second);
  * no filler or marketing words ("extremely efficient", "instantly", ...);
  * the running analogy appears in at least 70% of the demo scenes;
  * no word repeated back to back ("constant time time complexity");
  * anything a scene names (root, leaf, head, tail) is visible in that scene's picture, and gets highlighted there.
The LLM clarity judge (a 12-year-old who has never coded) rides on the existing answer-judge call (answer.judge).
"""
from __future__ import annotations

import re

import concepts

MAX_WORDS = 25
MAX_SENTENCES = 2
MIN_ANALOGY_SHARE = 0.7
CHAIN_RX = re.compile(r"(?:\bhead\s*(?:->|→)\s*)?[\w-]+(?:\s*(?:->|→)\s*[\w-]+)+")
ACRONYMS = {"FIFO": r"first (?:one |item |person )?in,? (?:is )?(?:the )?first (?:one |item |person )?out",
            "LIFO": r"last (?:one |item |plate )?in,? (?:is )?(?:the )?first (?:one |item |plate )?out"}


REPEAT_RX = re.compile(r"\b([A-Za-z]{2,})\s+\1\b", re.I)
# a part of the picture that narration may name: term -> (pattern, structures whose picture can show it)
NAMED = {"root": (r"\broots?\b", ("binary_tree",)), "leaf": (r"\bleaf\b|\bleaves\b", ("binary_tree",)),
         "head": (r"\bhead\b", ("linked_list",)), "tail": (r"\btail\b", ("linked_list",))}


def repeated_word(text: str) -> str | None:
    """A word said twice in a row ("time time"), or None."""
    m = REPEAT_RX.search(text or "")
    return m.group(0) if m else None


def repeated_phrase(text: str, n: int = 5) -> str | None:
    """A phrase of 5+ words said twice in one scene ("..., like a real line, ... first out, like a real line"), or None.
    Chains and numbers do not count: "10, then 20, then 30" is a list, not a repeat."""
    words = re.findall(r"[a-z']+", (text or "").lower())
    seen: dict[tuple, int] = {}
    for i in range(len(words) - n + 1):
        gram = tuple(words[i:i + n])
        if gram in seen and i - seen[gram] >= n:
            return " ".join(gram)
        seen.setdefault(gram, i)
    return None


def named_parts(text: str, state: dict | None) -> tuple[list[str], list[str]]:
    """(named and visible, named but NOT visible) in this scene's picture. Tree words only count on a tree scene and list
    words only on a list scene ("the head of the line" in a queue lesson is everyday English, not a list's head)."""
    kind = (state or {}).get("kind", "")
    shown, missing = [], []
    for term, (pat, kinds) in NAMED.items():
        if term == "leaf" and kind not in kinds:
            pat = r"\bleaf\b"  # "10 leaves the line" is a verb, not tree leaves
        if not re.search(pat, text or "", re.I):
            continue
        if kind in kinds:
            filled = (state.get("nodes") or state.get("items")) if kind == "binary_tree" else state.get("items")
            (shown if filled else missing).append(term)
        elif term in ("root", "leaf") and kind not in ("", "growth"):
            missing.append(term)  # a tree word on a scene that shows no tree
    return shown, missing


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[\"'(\[]?[A-Z0-9])", (text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def word_count(sentence: str) -> int:
    s = CHAIN_RX.sub(" X ", sentence)
    s = re.sub(r"\[[^\]]*\]", " X ", s)
    return len([w for w in s.split() if re.search(r"[A-Za-z0-9]", w)])


def clarity_len(text: str) -> int:
    return word_count(text)


def terms_for(ctx: dict) -> dict[str, tuple[str, bool]]:
    """The needs-definition terms of this lesson: all of them except the subject's own name (the question names it)."""
    own = concepts.SUBJECT_TERMS.get(ctx.get("structure") or "")
    return {t: v for t, v in concepts.NEEDS_DEFINITION.items() if t != own}


def _rx(term: str, terms: dict) -> tuple[str, int]:
    pat, cs = terms[term]
    return f"(?:{pat})", 0 if cs else re.I


def uses(term: str, text: str, terms: dict) -> bool:
    pat, flags = _rx(term, terms)
    return re.search(pat, text, flags) is not None


def definition_clause(term: str, sentence: str, terms: dict, said: str = "") -> str | None:
    """The plain-words explanation this sentence gives for `term`, or None if it does not explain it.
    Picture first ("... is called a pointer"), or "X means ...", "X (...)", "X, a ...", "A pointer is a ..."."""
    if term in ACRONYMS:
        if re.search(ACRONYMS[term], said + " " + sentence, re.I) and uses(term, sentence, terms):
            return re.sub(ACRONYMS[term], "", sentence, flags=re.I)
        return None
    t, flags = _rx(term, terms)
    m = re.search(rf"\b(?:(?:is|are|was|were)\s+)?(?:called|call(?:ed)?\s+(?:this|it|that|them|these|each one)|known as|named)\s+"
                  rf"(?:an?\s+|the\s+)?[\"']?{t}", sentence, flags)
    if m:
        return sentence[: m.start()]
    for rx in (rf"{t}[\"']?\s*,?\s*(?:means|meaning|stands for|is short for)\b(.*)", rf"{t}\s*\(([^)]*)\)",
               rf"^\W*(?:an?\s+|the\s+)?{t}\s+(?:is|are)\s+(?:an?|the|just|like|when|where|what|how)\b(.*)",
               rf"{t},\s+(?:an?|the)\s+([^,.;]*)"):
        m = re.search(rx, sentence, flags)
        if m:
            return m.group(1)
    return None


def _structure_of(kinds: list[str], i: int, ctx: dict) -> str:
    return ctx.get("structure") or (kinds[i] if i < len(kinds) else "")


def lesson_clarity(texts: list[str], scenes: list[dict], kinds: list[str], ctx: dict,
                   states: list[dict] | None = None) -> dict[int, list[str]]:
    """Scene index -> clarity problems, each phrased as an instruction for the rewrite. `states` (the true state each
    scene shows) enables the check that every named part (root, leaf, head, tail) is visible in the picture."""
    out: dict[int, list[str]] = {}
    terms = terms_for(ctx)
    question = ctx.get("question") or ctx.get("must_answer") or ""
    asked = {t for t in terms if uses(t, question, terms)}
    defined: set[str] = set()
    said = ""
    first_demo = next((i for i, sc in enumerate(scenes) if sc.get("ops")), len(scenes))
    subject = ctx.get("structure")

    def add(i: int, msg: str) -> None:
        if msg not in out.setdefault(i, []):
            out[i].append(msg)

    for i, text in enumerate(texts):
        sents = sentences(text)
        has_ops = bool(scenes[i].get("ops")) if i < len(scenes) else False
        if has_ops and len(sents) > MAX_SENTENCES:
            add(i, f"Beginner style: at most {MAX_SENTENCES} short sentences per scene; this scene has {len(sents)}. "
                   "Keep only the one new idea of this step.")
        if re.search(concepts.FILLER, text, re.I):
            add(i, "Remove filler or marketing words (" + ", ".join(sorted({m.lower() for m in re.findall(concepts.FILLER, text, re.I)}))
                   + "); show what happens with the real values instead.")
        intro = i == 0 and not has_ops
        rep = repeated_word(text)
        if rep:
            add(i, f"A word is repeated back to back (\"{rep}\"). Say it once.")
        phrase = repeated_phrase(text)
        if phrase:
            add(i, f"The phrase \"{phrase}\" is said twice in this scene. Say each thing once, in short plain sentences.")
        if states is not None and i < len(states):
            _, missing = named_parts(text, states[i])
            if missing:
                add(i, f"This scene names {', '.join(missing)}, but the picture does not show one yet. Only name what the "
                       "viewer can see: name it in a scene where it is on screen, or describe what is shown instead.")
        for s in sents:
            n = word_count(s)
            if n > MAX_WORDS:
                add(i, f"Beginner style: this sentence has {n} words (max {MAX_WORDS}). Split it into short sentences: \"{s[:90]}\"")
            here = {}
            for t in terms:
                clause = definition_clause(t, s, terms, said)
                if clause is not None:
                    here[t] = clause
            for t, clause in here.items():
                pat, flags = _rx(t, terms)
                plain = concepts.plain_definition(t, _structure_of(kinds, i, ctx)).rstrip(".").lower()
                if re.search(rf"^(?:(?!\bwhich\b|\bwe call\b|\bwe name\b)[^;])*\bis called\s+(?:an?\s+|the\s+)?{pat}\w*\s*,?\s+(?:so|because)\b", s, flags) \
                        or re.search(rf"\bbecause\b[^.]*\b(?:is called|known as)\s+(?:an?\s+|the\s+)?{pat}", s, flags) \
                        or (plain and plain in s.lower() and clarity_len(s) > clarity_len(plain) + 3):  # a glossary sentence pasted into a step
                    add(i, f"The explanation of \"{t}\" is glued to the step with \"so\" or \"because\", which reads as a non-sequitur. "
                           "Tell the step in the analogy, then name it (\"..., and we call this X.\"), in separate short sentences.")
                circular =[u for u in terms if u != t and u not in defined and u not in here and uses(u, clause, terms)]
                if circular:
                    add(i, f"\"{t}\" is explained with another unexplained word ({', '.join(circular)}). Explain it with everyday "
                           f"words from the analogy, e.g. \"{concepts.plain_definition(t, _structure_of(kinds, i, ctx))}\"")
            for t in terms:
                if uses(t, s, terms) and t not in defined and t not in here and not (intro and t in asked):
                    add(i, f"\"{t}\" is used before it is explained. Describe the thing in everyday words first, then name it, in its "
                           f"own short sentence before the step, e.g. \"{concepts.plain_definition(t, _structure_of(kinds, i, ctx))}\" "
                           "(or tell the step in the analogy and end with \"we call this ...\"); or use an everyday word instead.")
                    defined.add(t)  # flag it once, where it first appears
                pat, flags = _rx(t, terms)
                if re.search(rf"\b(?:in|into|from|to|of|on|at|by|with)\s+(?:the\s+)?{pat}\s*,\s*which means\b", s, flags):
                    add(i, f"The sentence explains \"{t}\" in the middle with \"which means\", which reads as garbled. Say what it "
                           "is in its own short sentence first, then use the word.")
            if i < first_demo:
                for acro in ACRONYMS:
                    if re.search(rf"\b{acro}\b", s):
                        add(i, f"Picture first: show the demo before naming the rule {acro}; say it after the demo, "
                               "in plain words (e.g. \"first in, first out, like a real line\").")
            defined |= set(here)
            said += " " + s
    # one running analogy: restated in at least 70% of the demo scenes
    demo = [i for i, sc in enumerate(scenes) if sc.get("ops") and (kinds[i] if i < len(kinds) else "") != "growth"]
    if demo and subject in concepts.ANALOGY:
        def own(i: int) -> str:  # a scene on a second structure (a WHY problem, a comparison) uses THAT structure's analogy
            return kinds[i] if kinds[i] in concepts.ANALOGY and kinds[i] != subject else subject

        def has_analogy(i: int) -> bool:
            return re.search(concepts.ANALOGY[own(i)]["words"], texts[i], re.I) is not None
        with_it = [i for i in demo if has_analogy(i)]
        for i in demo:  # the subject's picture on another structure's step is misleading ("a treasure hunt ... must shift")
            if own(i) != subject and re.search(concepts.ANALOGY[subject]["words"], texts[i], re.I) and not has_analogy(i):
                add(i, f"This step is about a {own(i).replace('_', ' ')}, not the {subject.replace('_', ' ')}: picture it as "
                       f"{concepts.ANALOGY[own(i)]['picture']}.")
        if len(with_it) < MIN_ANALOGY_SHARE * len(demo):
            for i in demo:
                if i not in with_it:
                    add(i, f"Keep the running analogy ({concepts.ANALOGY[own(i)]['picture']}): say this step in analogy words first, "
                           "then give the technical name, then the values.")
    return out


# ---------------------------------------------------------------- making text clear without an LLM (templates)
SPLIT_AT = [r";\s+", r",\s+(?=(?:and|but|so|because|which|while|then)\b)", r",\s+", r"\s+(?=(?:because|so that|which|while)\b)"]


def short_sentences(text: str) -> list[str]:
    """Sentences of at most MAX_WORDS words: long ones are cut at a clause boundary near the middle."""
    out: list[str] = []
    todo = sentences(text)
    while todo:
        s = todo.pop(0)
        if word_count(s) <= MAX_WORDS:
            out.append(s)
            continue
        cut = None
        for rx in SPLIT_AT:
            spots = [m for m in re.finditer(rx, s) if 4 <= word_count(s[: m.start()]) and 4 <= word_count(s[m.end():])]
            if spots:
                mid = len(s) / 2
                cut = min(spots, key=lambda m: abs(m.start() - mid))
                break
        if cut is None:
            out.append(s)  # no clean place to cut: left as it is (flagged, never garbled)
            continue
        left, right = s[: cut.start()].rstrip(" ,;") + ".", s[cut.end():]
        right = re.sub(r"^(?:and|but|then)\s+", "", right)
        right = re.sub(r"^which\s+", "This ", right)
        todo[:0] = [left, right[:1].upper() + right[1:]]
    return out


def plain_text(text: str, ctx: dict, structure: str | None = None) -> str:
    """A fallback explanation made beginner-safe in code: filler removed, every needs-definition term it uses explained
    first in plain words (picture first, from the fixed glossary), long sentences cut. Never invents facts."""
    terms = terms_for(ctx)
    text = re.sub(r"\s{2,}", " ", re.sub(concepts.FILLER + r"\s*", "", text or "", flags=re.I)).strip()
    body = short_sentences(text)
    defs, done = [], set()
    for s in body:
        for t in terms:
            if t not in done and uses(t, s, terms) and definition_clause(t, s, terms) is None:
                plain = concepts.plain_definition(t, structure or ctx.get("structure"))
                if plain:
                    defs.append(plain)
                done.add(t)
    return " ".join(defs + body).strip()


UNDEFINED = re.compile(r'^"([^"]+)" (?:is used before it is explained|is new to a beginner)')


def define_first(text: str, errors: list[str], ctx: dict, structure: str | None = None, strict: bool = True) -> str:
    """A narration whose only clarity problem is a term used before it was explained keeps its words: the term's plain
    definition from the fixed glossary goes in front of it (picture first, name second). No LLM call. Strict: returns the
    text unchanged when another problem remains or a term has no glossary entry. Not strict: explains whatever it can."""
    terms = [m.group(1) for e in errors if (m := UNDEFINED.match(e))]
    if not terms or (strict and len(terms) != len(errors)):
        return text
    defs = []
    for t in dict.fromkeys(terms):
        plain = concepts.plain_definition(t, structure or ctx.get("structure"))
        if not plain and strict:
            return text
        if plain:
            defs.append(plain)
    return " ".join([*defs, text])


def split_text(text: str) -> list[str]:
    """Chunks of at most MAX_SENTENCES sentences, in order."""
    s = sentences(text)
    return [" ".join(s[k:k + MAX_SENTENCES]) for k in range(0, len(s), MAX_SENTENCES)] or [text]


def analogy_tag(text: str, kind: str, subject: str | None) -> str | None:
    """The analogy tag to show on a scene that uses the running analogy."""
    for k in (kind, subject):  # the scene's own picture first (a 2D array scene in an array lesson is a grid of lockers)
        a = concepts.ANALOGY.get(k or "")
        if a and re.search(a["words"], text or "", re.I):
            return a["tag"]
    return None
