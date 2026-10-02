"""How alike the questions in one exam are: each question's nearest neighbour.

Two questions that ask the same thing waste a slot in the pool and, drawn
into the same paper, can give one another away. The report shows, for every
question, the most similar other question in its exam and how similar it is,
and lists the closest pairs.

The measure is lexical, on purpose: TF-IDF over the scenario, the question
and the correct answer(s), compared by cosine. It is deterministic, needs no
model, and can say WHY two questions match (the words that carry the score),
which a reviewer needs before deciding anything. Distractors are left out:
they are deliberately varied and would add noise rather than signal.

IDF is computed within the exam, not across the bank. A course's own
vocabulary (gbm, MQTT, Mondrian) appears in many of its questions; weighting
it by the whole bank would make every pair in that course look alike. The
smoothing (``ln((1 + n) / (1 + df)) + 1``) keeps a word that every question
shares from weighing nothing, so two identical questions still score 1.0.

The bands were calibrated on the eleven course exams in October 2026: the
median nearest neighbour scored 0.18, the 99th percentile 0.45, and the one
genuine duplicate found (the same scenario reworded, the same key) 0.62.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable, Sequence

from .bank import Question

#: At or above: very likely the same question twice. Review the pair.
DUPLICATE = 0.55
#: At or above (and below DUPLICATE): sharing a good deal of wording. Worth a
#: look to confirm the two test different things.
OVERLAP = 0.40

_STOPWORDS = frozenset("""
a an the and or of to in on for with by at from as is are was were be been being it its
this that these those which what who whom whose how why when where do does did can could
should would will may might must not no than then so such into onto over under about after
before between each every any all both either neither there their they them he she his her
you your we our i me my us one two three if but also only just more most
""".split())

_WORD = re.compile(r"[a-z0-9][a-z0-9_.$'-]*[a-z0-9]|[a-z0-9]")


def words(text: str) -> list[str]:
    """Lower-cased content words. Dots, underscores and dollar signs stay
    inside a word, so ``gbm.perf``, ``num_predict`` and ``${VAR}`` survive."""
    return [w for w in _WORD.findall((text or "").lower()) if w not in _STOPWORDS]


def question_text(q: Question) -> str:
    """What two questions are compared on: scenario, question, correct answer(s)."""
    keys = list(q.keys or []) if q.question_type == "multi" else [q.key]
    return " ".join([q.scenario or "", q.stem or "", *[k for k in keys if k]])


def _vectors(texts: Sequence[str]) -> list[dict[str, float]]:
    tfs = [Counter(words(t)) for t in texts]
    df = Counter(w for tf in tfs for w in tf)
    n = len(texts)
    out = []
    for tf in tfs:
        v = {w: (1 + math.log(c)) * (math.log((1 + n) / (1 + df[w])) + 1) for w, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        out.append({w: x / norm for w, x in v.items()})
    return out


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(w, 0.0) for w, x in a.items())


def _shared(a: dict[str, float], b: dict[str, float], n: int = 5) -> list[str]:
    """The words contributing most to a pair's score, largest first."""
    both = [(a[w] * b[w], w) for w in a.keys() & b.keys()]
    return [w for _, w in sorted(both, reverse=True)[:n]]


def band(score: float) -> str:
    if score >= DUPLICATE:
        return "duplicate"
    if score >= OVERLAP:
        return "overlap"
    return "distinct"


def analyse(questions: Iterable[Question], *, pair_limit: int = 10) -> dict:
    """Nearest neighbours and closest pairs for ONE exam's questions.

    Returns ``{"nearest": {id: {"id", "score", "band"}}, "pairs": [...],
    "duplicates", "overlaps", "median", "max"}`` with scores as whole
    percentages. ``pairs`` holds every pair at or above OVERLAP, closest first,
    capped at ``pair_limit``; ``duplicates`` and ``overlaps`` count all of them.
    """
    qs = list(questions)
    empty = {"nearest": {}, "pairs": [], "duplicates": 0, "overlaps": 0, "median": 0, "max": 0}
    if len(qs) < 2:
        return empty
    vs = _vectors([question_text(q) for q in qs])

    best: list[tuple[float, int]] = [(-1.0, -1)] * len(qs)
    flagged: list[tuple[float, int, int]] = []
    for i in range(len(qs)):
        for j in range(i + 1, len(qs)):
            s = _cosine(vs[i], vs[j])
            if s > best[i][0]:
                best[i] = (s, j)
            if s > best[j][0]:
                best[j] = (s, i)
            if s >= OVERLAP:
                flagged.append((s, i, j))

    def pct(s: float) -> int:
        return max(0, min(100, round(s * 100)))

    nearest = {
        qs[i].id: {"id": qs[j].id, "score": pct(s), "band": band(s)}
        for i, (s, j) in enumerate(best)
    }
    flagged.sort(key=lambda t: (-t[0], qs[t[1]].id, qs[t[2]].id))
    pairs = [
        {
            "a": qs[i].id, "b": qs[j].id,
            "aStem": qs[i].stem, "bStem": qs[j].stem,
            "score": pct(s), "band": band(s),
            "shared": _shared(vs[i], vs[j]),
        }
        for s, i, j in flagged[:pair_limit]
    ]
    scores = sorted(s for s, _ in best)
    return {
        "nearest": nearest,
        "pairs": pairs,
        "duplicates": sum(1 for s, _, _ in flagged if s >= DUPLICATE),
        "overlaps": sum(1 for s, _, _ in flagged if s < DUPLICATE),
        "median": pct(scores[len(scores) // 2]),
        "max": pct(scores[-1]),
    }
