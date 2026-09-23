"""The Python half of the gradeability contract.

Every case comes from ``tests/fixtures/question_problems.json``, which the
front end's suite reads too. This file asserts that Python produces exactly
the messages in that fixture, in that order; `questionProblems.test.ts`
asserts the same of TypeScript. Neither implementation can move without the
other's suite going red.

There is deliberately no case here that the fixture does not contain. A rule
tested only on this side is a rule that can drift.
"""

import json
from pathlib import Path

import pytest

from exam_bank.core.bank import Question
from exam_bank.core.validation import is_gradeable, problems_with

FIXTURE = Path(__file__).parent / "fixtures" / "question_problems.json"
CASES = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_matches_the_shared_fixture(case):
    """Python's verdict, message for message and in order."""
    question = Question(**case["question"])
    actual = [p.as_dict() for p in problems_with(question)]

    assert actual == case["problems"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_is_gradeable_agrees_with_the_problem_list(case):
    assert is_gradeable(Question(**case["question"])) == (not case["problems"])


def test_the_fixture_covers_both_outcomes():
    """A corpus of only-bad cases would pass a rule that fires on everything,
    and a corpus of only-good ones would pass a rule that never fires."""
    good = [c for c in CASES if not c["problems"]]
    bad = [c for c in CASES if c["problems"]]

    assert good, "no case expects a clean question"
    assert bad, "no case expects a problem"


def test_every_field_named_in_the_fixture_is_one_the_editor_renders():
    """A problem filed under a field the form does not show is invisible:
    the editor renders problems per field, so an unknown one is dropped."""
    rendered = {"stem", "keys", "distractors"}
    for case in CASES:
        for problem in case["problems"]:
            assert problem["field"] in rendered, (
                f"{case['name']}: no field named {problem['field']!r} is rendered"
            )


def test_it_reads_anything_shaped_like_a_question():
    """Import checks rows before they are model objects, so the rules must
    not require a `Question` - only its attributes."""

    class Row:
        stem = "Which step reads a delimited file?"
        question_type = "single"
        key = ""
        keys = []
        distractors = ["Table output"]

    assert [p.field for p in problems_with(Row())] == ["keys"]


def test_a_partial_object_does_not_raise():
    """A half-parsed row from a malformed file still has to get an answer,
    because the alternative is an import that dies on one bad line."""

    class Bare:
        pass

    problems = problems_with(Bare())
    assert [p.field for p in problems] == ["stem", "keys", "distractors"]
