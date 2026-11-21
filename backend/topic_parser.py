"""Pull the user's own data out of the topic text, so lessons use THEIR labels and values.

    "show BFS on this graph: A-B, A-C, B-D, C-D, starting from A"
        -> GivenData(edges=[("A","B"),("A","C"),("B","D"),("C","D")], start="A")
    "sort [5, 2, 9, 1]"  /  "push 4, 7, 2 onto a stack"
        -> GivenData(values=[5, 2, 9, 1])

When nothing is found the planner may invent small example data.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

NODE = r"(?:[A-Za-z]|\d{1,2})"  # a single letter or a 1-2 digit number
EDGE_RE = re.compile(rf"(?<![\w-])({NODE})\s*(?:-|–|—|->|<->|to)\s*({NODE})(?![\w-])")
START_RE = re.compile(rf"\b(?:start(?:ing)?\s+(?:from|at)|from|source|beginning\s+at|begin\s+at)\s+(?:node\s+|vertex\s+)?({NODE})\b", re.I)
LIST_RE = re.compile(r"\[\s*(-?\d+(?:\s*,\s*-?\d+)+)\s*\]|(?<![\w-])(-?\d+(?:\s*,\s*-?\d+){1,})(?![\w-])")


@dataclass
class GivenData:
    edges: list[tuple[str, str]] = field(default_factory=list)
    start: str | None = None
    values: list[int] = field(default_factory=list)

    @property
    def nodes(self) -> list[str]:
        seen: list[str] = []
        for u, v in self.edges:
            for n in (u, v):
                if n not in seen:
                    seen.append(n)
        return seen

    def describe(self) -> str:
        if self.edges:
            e = ", ".join(f"{u}-{v}" for u, v in self.edges)
            return f"the graph with edges {e}, starting from {self.start}"
        if self.values:
            return "the values " + ", ".join(map(str, self.values))
        return ""


def parse_topic(topic: str) -> GivenData:
    data = GivenData()
    # graph: only when at least one edge is written as X-Y and the topic is about graphs/BFS
    if re.search(r"\b(graph|bfs|breadth|edges?|nodes?|vertex|vertices)\b", topic, re.I):
        seen = set()
        for u, v in EDGE_RE.findall(topic):
            u, v = u.strip(), v.strip()
            key = frozenset((u, v))
            if u != v and key not in seen:
                seen.add(key)
                data.edges.append((u, v))
        if data.edges:
            m = START_RE.search(topic)
            names = data.nodes
            data.start = m.group(1) if m and m.group(1) in names else names[0]
            return data
    # values: a bracketed list or a comma-separated run of 2+ integers
    m = LIST_RE.search(topic)
    if m:
        data.values = [int(x) for x in re.findall(r"-?\d+", m.group(1) or m.group(2))][:12]
    return data
