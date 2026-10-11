"""What a rewrite changed that it should not have: exact checks, no model (1.17.0).

The first 100 reviewed rewrites (2026-10-11) showed a 12B model, told to
proofread, doing three things a second model pass cannot be trusted to report
about itself:

- cutting the detail a question turns on ("The files are processed in the
  order they are written" - the clue that they are unsorted) or adding the
  answer's reason ("...because it was only caught after the run finished");
- changing a word in an answer ("decoded" -> "deployed"), which changes
  what the answer claims;
- lowercasing every answer ("A url-formula" -> "a url-formula").

So the rewrite is compared with what it started from, word for word.
A capital it took away is put back (no word changes); everything else is a
note, and a proposal with notes waits for the author.
"""

from __future__ import annotations

import copy
import re
from typing import List, Tuple

# Words that carry no fact of their own.
_STOP = set("""
a an the and or but if then than that this these those there their they them
it its is are was were be been being has have had do does did of in on at to
for from by with without into onto over under about above below after before
as so such each every any all some both either neither not no nor only also
very more most less least much many own same other another which who whom
whose what when where why how can could should would may might must will
shall one two three four five six seven eight nine ten while whether
""".split())

# What the writing standard itself changes is not a change of content: US
# spelling, and numbers 10 and up in digits (WRITING_RULES).
_SPELLING = [
    (re.compile(r"\blicen[cs]e"), "license"), (re.compile(r"\bcatalogue"), "catalog"),
    (re.compile(r"(\w)our(s|ed|ing)?\b"), r"\1or\2"),
    (re.compile(r"(\w{3,})is(e|es|ed|ing|ation|ations)\b"), r"\1iz\2"),
    (re.compile(r"(\w{2,})yse(s|d)?\b"), r"\1yze\2"),
]
_NUMBERS = {"ten": "10", "eleven": "11", "twelve": "12", "fifteen": "15", "twenty": "20",
            "thirty": "30", "forty": "40", "fifty": "50", "hundred": "100"}


def _norm(text: str) -> str:
    t = (text or "").lower().replace("’", "'").replace("`", "")
    t = t.replace("can't", "cannot").replace("won't", "will not")
    t = re.sub(r"n't\b", " not", t)
    for pattern, repl in _SPELLING:
        t = pattern.sub(repl, t)
    return re.sub(r"\b(" + "|".join(_NUMBERS) + r")\b", lambda m: _NUMBERS[m.group(1)], t)


def _stem(w: str) -> str:
    for suffix in ("ingly", "edly", "ing", "ies", "ied", "ed", "es", "ly", "s"):
        if len(w) > len(suffix) + 3 and w.endswith(suffix):
            return w[: -len(suffix)]
    return w


def _content(text: str) -> dict:
    """Content word stem -> the word as written, for words of four letters or more and numbers."""
    out = {}
    for w in re.findall(r"[a-z0-9]+(?:[._'-][a-z0-9]+)*", _norm(text)):
        if w in _STOP or (len(w) < 4 and not w.isdigit()):
            continue
        out.setdefault(_stem(w), w)
    return out


def _words(text: str) -> List[str]:
    """An answer's content words in order, ignoring case, punctuation, code
    marks and words that carry no claim ("the", "and", "their")."""
    return [_stem(w) for w in re.findall(r"[a-z0-9]+(?:[._'-][a-z0-9]+)*", _norm(text)) if w not in _STOP]


# How much a proofread may move before it is worth a look. Tuned on the
# 2026-10-11 reviews: a clean proofread of a scenario swaps a word or two
# ("examine" -> "verify"); the damaging ones lost or gained three or more.
_LOST_AT = {"scenario": 3, "stem": 2}
_ADDED_AT = {"scenario": 4, "stem": 3}


def preservation_notes(original, proposed) -> List[Tuple[str, str]]:
    """(field, message) for what the rewrite took out of, or put into, the question."""
    notes: List[Tuple[str, str]] = []
    for field, label in (("scenario", "scenario"), ("stem", "question")):
        before, after = _content(getattr(original, field)), _content(getattr(proposed, field))
        lost = [before[s] for s in before if s not in after]
        added = [after[s] for s in after if s not in before]
        numbers = [w for w in lost if any(c.isdigit() for c in w)]
        if len(lost) >= _LOST_AT[field] or numbers:
            notes.append((field, f"The rewrite dropped words from the {label}: {', '.join(lost[:8])}. "
                                 "Check no detail the question needs was lost."))
        if len(added) >= _ADDED_AT[field]:
            notes.append((field, f"The rewrite added to the {label}: {', '.join(added[:8])}. "
                                 "Check it gives no hint and states nothing new."))
    for label, before, after in _answer_pairs(original, proposed):
        if _changed(before, after):
            notes.append(("options", f"An answer's words changed: \"{before}\" -> \"{after}\". "
                                     "Check it still claims the same thing."))
    return notes


# An answer that is a topic filter, a path or an expression is compared
# character for character: `+/sensor/#` became `+/sensor_#` in the SD rerun
# (2026-10-11), and as words the two are the same.
_SYMBOLS = re.compile(r"[/#+*$\\\[\]{}=<>|%]")


def _changed(before: str, after: str) -> bool:
    if _SYMBOLS.search(before) or _SYMBOLS.search(after):
        def bare(s):
            return (s or "").replace("`", "").strip().rstrip(".").lower()
        return bare(before) != bare(after)
    return _words(before) != _words(after)


def _answer_pairs(original, proposed):
    ok, pk = original.correct_answers, proposed.correct_answers
    od, pd = list(original.distractors), list(proposed.distractors)
    pairs = []
    if len(ok) == len(pk):
        pairs += [("key", a, b) for a, b in zip(ok, pk)]
    if len(od) == len(pd):
        pairs += [("distractor", a, b) for a, b in zip(od, pd)]
    return pairs


def keep_capitals(original, proposed):
    """A copy of the proposal with each answer's lost capital first letter put back.

    Only where the original began with a capital and the rewrite begins with
    the same letter in lower case; every copy of the answer (key, keys,
    distractors, the shuffled order) is changed alike.
    """
    q = copy.deepcopy(proposed)
    fixed = {}
    for _label, before, after in _answer_pairs(original, proposed):
        if before[:1].isupper() and after[:1].islower() and before[:1].lower() == after[:1]:
            fixed[after] = after[:1].upper() + after[1:]
    if not fixed:
        return q
    q.key = fixed.get(q.key, q.key)
    q.keys = [fixed.get(k, k) for k in (q.keys or [])]
    q.distractors = [fixed.get(d, d) for d in (q.distractors or [])]
    q.option_order = [fixed.get(o, o) for o in (q.option_order or [])]
    return q
