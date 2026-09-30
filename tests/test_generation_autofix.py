"""Generation's auto-fix: which defects it rewrites, and what it asks for.

Until 1.9.0 the auto-fix chose what to fix from `Question.validate_detailed`,
a third set of gradeability rules that disagreed with the editor's and
import's (it wanted two or more distractors, and passed a stem ending in "."),
and it told the model to explain each option "by letter" - in exams whose
options are shuffled, so a letter names a different option for every
candidate.
"""

from exam_bank.core import providers, question_generation as qg
from exam_bank.core.bank import Question


def q(**kw):
    base = dict(stem="Which step reads a CSV file?", key="CSV file input",
                distractors=["Table output", "Sort rows", "Filter rows"])
    base.update(kw)
    return Question(**base)


def test_a_clean_question_has_nothing_to_fix():
    assert qg._get_fixable_warnings(q()) == []


def test_a_distractor_that_repeats_the_key_is_fixed():
    found = qg._get_fixable_warnings(q(distractors=["csv file input", "Sort rows"]))
    assert found == ['"csv file input" is both correct and a distractor.']


def test_a_repeated_distractor_is_fixed():
    assert qg._get_fixable_warnings(q(distractors=["Sort rows", "sort rows", "Filter rows"])) == [
        '"sort rows" appears 2 times.']


def test_all_or_none_of_the_above_is_fixed():
    assert qg._get_fixable_warnings(q(distractors=["Table output", "None of the above."])) == [
        "'All/None of the above' is a weak distractor."]


def test_unbalanced_lengths_are_left_alone():
    assert qg._get_fixable_warnings(q(key="A step that reads delimited text files row by row",
                                      distractors=["Sort", "Join", "Filter"])) == []


def test_the_fix_asks_for_options_by_their_text_never_by_letter(monkeypatch):
    prompts = []

    def fake(**kw):
        prompts.append(kw["prompt"])
        return "{}"

    monkeypatch.setattr(providers, "generate", fake)
    bad = q(distractors=["CSV file input", "Sort rows"])

    qg._auto_fix_question(bad, qg._get_fixable_warnings(bad), "a-model")

    assert "Never refer to an option by a letter" in prompts[0]
    assert "by letter" not in prompts[0] and "(A, B, C, D)" not in prompts[0]
