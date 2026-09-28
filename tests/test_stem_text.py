"""The count directive is presentation: what question_only strips, and what it must not."""

import pytest

from exam_bank.core.stem_text import has_choose_directive, question_only


# Real stems, as they were saved in the live bank during review on 28 Sep
# 2026: a bare directive on its own line, which PCM does not strip, so a
# learner would have read the count twice.
@pytest.mark.parametrize("stem, question", [
    ("How do you inspect those rows in Pentaho Data Integration (PDI)? \nChoose One.",
     "How do you inspect those rows in Pentaho Data Integration (PDI)?"),
    ("What does the 'Get Fields' button do for you here?\nChoose One.",
     "What does the 'Get Fields' button do for you here?"),
    ("What must happen to the four sources before Pentaho Data Integration (PDI) can combine them?\nChoose One.",
     "What must happen to the four sources before Pentaho Data Integration (PDI) can combine them?"),
])
def test_bare_directive_from_review(stem, question):
    assert question_only(stem) == question
    assert has_choose_directive(stem)


@pytest.mark.parametrize("stem, question", [
    ("Which step reads a delimited file? (Choose one.)", "Which step reads a delimited file?"),
    ("Which two steps write rows? (Choose two)", "Which two steps write rows?"),
    ("Which apply? (Select all that apply.)", "Which apply?"),
    ("Which apply? [Select all that apply]", "Which apply?"),
    ("Which steps? Select all that apply.", "Which steps?"),
    ("Which option? Choose the best answer.", "Which option?"),
    ("Which option? choose ONE", "Which option?"),
    ("Which options? Pick 2 answers.", "Which options?"),
    ("Which option?   (Choose one.)   ", "Which option?"),
    # Two directives, one of each kind: both go.
    ("Which option? (Choose one.) Choose One.", "Which option?"),
])
def test_directives_are_stripped(stem, question):
    assert question_only(stem) == question


@pytest.mark.parametrize("stem", [
    "Which option would you choose?",
    "Which of these should you select first?",
    # The directive-like sentence IS the question here; stripping it would
    # leave a scenario with nothing to answer.
    "The job runs nightly. Choose two steps that run in parallel.",
    "Pick the step that writes to the table?",
    # A parenthesis that is not a directive.
    "How do you inspect rows in Pentaho Data Integration (PDI)?",
    "Which step reads a file (CSV or TXT)?",
])
def test_questions_are_left_alone(stem):
    assert question_only(stem) == stem
    assert not has_choose_directive(stem)


def test_a_stem_that_is_only_a_directive_is_kept():
    # Nothing would be left to ask; returning "" would hide a broken question.
    assert question_only("(Choose one.)") == "(Choose one.)"
    assert question_only("Choose two.") == "Choose two."


def test_empty_and_none():
    assert question_only("") == ""
    assert question_only(None) == ""
    assert not has_choose_directive("")


def test_generated_questions_are_stored_as_the_question_only(monkeypatch):
    """The model is told to end each stem "(Choose N.)"; the bank keeps the
    question and lets the course and the printed exam add their own count."""
    import json

    from exam_bank.core import providers
    from exam_bank.core.question_generation import generate_questions
    from exam_bank.core.source import SlideInfo

    reply = json.dumps([
        {"scenario": "A developer is loading a supplier file.",
         "stem": "Which step reads a delimited file? (Choose one.)",
         "question_type": "single", "key": "Text file input",
         "distractors": ["Table output", "Sort rows", "Dummy"],
         "explanation": "'Text file input' reads it; the others do not."},
        {"scenario": "A developer must write rows to a database.",
         "stem": "Which two steps write rows to a table?\nChoose two.",
         "question_type": "multi", "keys": ["Table output", "Insert / update"],
         "distractors": ["Sort rows", "Dummy"],
         "explanation": "Both write; the others do not."},
    ])
    monkeypatch.setattr(providers, "generate", lambda **kw: reply)

    made = generate_questions(
        SlideInfo(index=0, speaker_notes="Text file input reads delimited files.",
                  title="Reading files"),
        model="a-model")

    assert [q.stem for q in made] == ["Which step reads a delimited file?",
                                      "Which two steps write rows to a table?"]
