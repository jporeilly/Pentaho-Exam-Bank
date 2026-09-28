"""The question is the stem; how many to choose is presentation.

A course's exam.json prompt holds only the question. Pentaho Content Manager
counts the correct answers and adds its own "(Choose one)" / "(Choose two)"
when it shows the question, and the bank's printed exam adds its own count
too. A count written into the stem therefore reaches the learner twice -
"... (PDI)? Choose One. (Choose one)" - because PCM strips only a
parenthesised directive, and only when it is the very last thing.

So the bank strips a trailing count directive wherever a stem crosses a
boundary: when it is published to a course, printed, compared with a course
during sync, or generated. Everything that decides what a directive looks
like lives here, so those places cannot disagree.
"""

from __future__ import annotations

import re

# What may follow "choose" / "select" / "pick" for the phrase to be a count
# directive rather than the question itself. "Choose two steps that run in
# parallel." is a question and must survive; "Choose two." and "Select all
# that apply." are directives.
_COUNT = (
    r"(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+"
    r"|all(?:\s+that\s+apply)?"
    r"|the\s+(?:best|correct)\s+(?:answer|option|response)s?)"
)
_NOUN = r"(?:\s+(?:correct\s+|best\s+)?(?:answer|option|response|choice)s?)?"

_DIRECTIVE = re.compile(
    r"(?:"
    # "(Choose two.)", "[Select all that apply]" - bracketed, any wording.
    r"\s*[\(\[]\s*(?:choose|select|pick)\b[^\)\]]*[\)\]]"
    r"|"
    # "Choose One." - bare, but only as its own sentence after the question,
    # and only a count: never a sentence that carries the question itself.
    r"(?<=[?.!:)\s])\s*(?:choose|select|pick)\s+" + _COUNT + _NOUN + r"\b"
    r")\s*[.!]?\s*$",
    re.IGNORECASE,
)


def question_only(stem: str) -> str:
    """Return the stem without any trailing count directive.

    Strips repeatedly, so "...? (Choose one.) Choose One." loses both. A stem
    that would come out empty is returned as it was: a directive with no
    question in front of it is a broken question, and hiding the evidence
    would not mend it.
    """
    text = (stem or "").rstrip()
    while True:
        cut = _DIRECTIVE.sub("", text, count=1).rstrip()
        if cut == text:
            break
        if not cut:
            return (stem or "").rstrip()
        text = cut
    return text


def has_choose_directive(stem: str) -> bool:
    """True when the stem ends with a count directive that publishing drops."""
    return question_only(stem) != (stem or "").rstrip()


# Abbreviations whose full stop is not the end of a sentence. Without this,
# "e.g. a CSV file" would read as a statement followed by more text.
_ABBREVIATIONS = re.compile(r"\b(?:e\.g|i\.e|etc|vs|approx|incl|no)\.", re.IGNORECASE)

COUNT_MESSAGE = ("Stem ends with a 'Choose …' count; the course adds its own, "
                 "so Publish removes it")


def form_notes(scenario: str, stem: str) -> list[tuple[str, str]]:
    """Where a question breaks the house form, as (field, message) pairs.

    The form: the scenario is statements that set the scene, and the stem is
    the question and nothing else. Advice, not an error - a question that
    breaks it can still be graded - so the editor shows it beside the field
    and lets the author decide. Mirrored in the editor as ``formNotes`` so it
    can be shown while typing; tests/test_stem_text.py and
    QuestionEditor.test.tsx pin the same cases.
    """
    notes: list[tuple[str, str]] = []
    if "?" in (scenario or ""):
        notes.append(("scenario",
                      "The scenario asks a question. A scenario is statements that set "
                      "the scene; the question belongs in the Question field."))

    question = question_only(stem).strip()
    if has_choose_directive(stem):
        notes.append(("stem", COUNT_MESSAGE))
    if not question:
        return notes
    body = _ABBREVIATIONS.sub("", question)
    if body.count("?") > 1:
        notes.append(("stem", "The Question field asks more than one question. Ask one."))
    elif not question.endswith("?"):
        notes.append(("stem", "The question should be a question, ending in “?”."))
    if re.search(r"[.!]\s+\S", body):
        notes.append(("stem",
                      "The question opens with statements. Move them into the scenario "
                      "and keep only the question here."))
    return notes
