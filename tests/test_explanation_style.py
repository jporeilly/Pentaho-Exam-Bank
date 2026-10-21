"""The house rule for an explanation, checked without a model (1.14.0)."""

import pytest

from exam_bank.core.explanation_style import explanation_notes

CLEAN = ("A transformation **moves and shapes rows**: each step works on the rows the step "
         "before it produced.\n\nThat is why it sits between a source and a target.")


def test_an_explanation_in_the_house_form_has_nothing_to_note():
    assert explanation_notes(CLEAN) == []
    assert explanation_notes("") == [] and explanation_notes(None) == []


@pytest.mark.parametrize("text", [
    "'Moves rows' — Correct: it does. 'Prints a report' — Incorrect: no.",
    "Moves and shapes rows - Correct. Prints a report - Incorrect.",
    "Incorrect: a job does not move rows.",
])
def test_the_old_form_that_judges_every_option_is_noted(text):
    notes = explanation_notes(text)
    assert len(notes) == 1 and "Correct/Incorrect" in notes[0]


@pytest.mark.parametrize("text", [
    "The correct setting is **Lazy conversion**, which defers parsing.",
    "Incorrectly configured steps fail at run time, which is why validation matters.",
])
def test_the_word_correct_in_prose_is_not_a_verdict(text):
    assert explanation_notes(text) == []


@pytest.mark.parametrize("text, noted", [
    ("Option B is right because it streams.", True),
    ("Answer (C) is the one that streams.", True),
    ("This is a choice the designer makes.", False),
    ("Pick the answer that streams.", False),
])
def test_an_answer_named_by_its_letter_is_noted(text, noted):
    assert bool(explanation_notes(text)) is noted


def test_a_wall_of_text_is_noted_but_paragraphs_are_not():
    sentence = "A transformation moves and shapes rows on their way to a target. "
    wall = sentence * 12
    assert len(wall) > 700
    assert any("700 characters" in n for n in explanation_notes(wall))
    split = "\n\n".join([sentence * 6, sentence * 6])
    assert explanation_notes(split) == []
