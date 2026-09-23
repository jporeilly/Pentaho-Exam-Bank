"""What makes a question gradeable, as the grader would see it.

These rules exist twice on purpose and that is the whole design problem here.
The editor checks them in the browser so an author sees a problem while they
are typing, which a round trip cannot do; import checks them on the server,
because a file of four hundred questions is not something to validate one
keystroke at a time. Neither copy can be deleted.

What CAN be prevented is the two drifting apart, which is the failure that
actually costs something: a question the editor refuses to save, imported
without complaint, or the reverse. So both implementations are driven from one
fixture — ``tests/fixtures/question_problems.json`` — and both test suites
assert against it, message for message and in order. Change a rule in one
language and the other language's suite goes red.

The messages are therefore part of the contract, not decoration. If one is
reworded here it must be reworded in ``frontend/src/QuestionEditor.tsx`` and in
the fixture, and the two suites are what make that impossible to forget.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Problem:
    """A field-level problem, shown inline and blocking a save."""

    field: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"field": self.field, "message": self.message}


def problems_with(question: Any) -> list[Problem]:
    """Everything wrong with a question, in the order the editor shows them.

    Takes anything with the question attributes rather than a ``Question``
    specifically, so an imported row can be checked before it is a model
    object and the same rules still apply.

    Order matters and is asserted: stem, then the correct answers, then the
    distractors. It is the reading order of the form, so a list of problems
    matches the order they appear on screen.
    """
    out: list[Problem] = []

    stem = (getattr(question, "stem", "") or "").strip()
    if not stem:
        out.append(Problem("stem", "A question needs a stem."))

    question_type = getattr(question, "question_type", "single")
    if question_type == "multi":
        keys = list(getattr(question, "keys", None) or [])
    else:
        keys = [getattr(question, "key", "") or ""]
    live = [k.strip() for k in keys if (k or "").strip()]

    if not live:
        out.append(Problem(
            "keys", "Nothing is marked correct, so the question cannot be graded."
        ))
    if question_type == "multi" and len(live) == 1:
        out.append(Problem(
            "keys",
            "A select-all question with one correct answer grades the same as a "
            "single-select one. Add another, or switch the type.",
        ))

    distractors = [(d or "").strip() for d in (getattr(question, "distractors", None) or [])]
    if any(not d for d in distractors):
        out.append(Problem("distractors", "An empty option cannot be chosen."))
    if not [d for d in distractors if d]:
        out.append(Problem(
            "distractors", "With no distractors the correct answer is the only option."
        ))

    # A distractor that equals a key is the defect that survives review most
    # often: it reads fine in a list and is impossible to answer.
    lowered_keys = {k.lower() for k in live}
    seen_clash: list[str] = []
    for d in distractors:
        if d and d.lower() in lowered_keys and d not in seen_clash:
            seen_clash.append(d)
    for d in seen_clash:
        out.append(Problem("distractors", f'"{d}" is both correct and a distractor.'))

    counts: dict[str, int] = {}
    for d in distractors:
        if d:
            key = d.lower()
            counts[key] = counts.get(key, 0) + 1
    for text, n in counts.items():
        if n > 1:
            out.append(Problem("distractors", f'"{text}" appears {n} times.'))

    return out


def is_gradeable(question: Any) -> bool:
    """True when nothing is wrong with the question."""
    return not problems_with(question)
