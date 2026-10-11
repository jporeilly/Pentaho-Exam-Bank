"""The gate between a question and approval, and the answer checks (1.18.0)."""
from exam_bank.core.bank import Question
from exam_bank.core.question_gate import GATE_REVIEWER, house_findings, pass_gate
from exam_bank.core.writing_style import answer_notes

CLEAN = ("A transformation **moves and shapes rows**: each step works on the rows the "
         "step before it produced.")


def _q(**fields) -> Question:
    base = dict(id="q-1", scenario="A team loads orders every night.", stem="What does a transformation do?",
                question_type="single", key="Moves and shapes rows",
                distractors=["Prints a report", "Installs the server", "Backs up a database"],
                explanation=CLEAN)
    base.update(fields)
    return Question(**base)


# --- answers cut short ---------------------------------------------------------


def test_an_answer_that_ends_on_a_word_no_phrase_ends_on_is_cut_short():
    # The owner's example (2026-10-11).
    q = _q(key="Text becomes tokens, and URLs and codes split into several",
           distractors=["Each word becomes one token, plus a token for every space",
                        "The model reads characters, so every letter is a unit of cost",
                        "URLs and codes are dropped before the model ever sees them"])

    notes = [m for _f, m in answer_notes(q)]

    assert any('ends on "several"' in m and "cut short" in m for m in notes)


def test_complete_answers_are_not_flagged():
    for answer in ["It runs as is", "Each runs on its own", "CA and OR", "Between 0 and 1.",
                   "The layout they render into", "`[Years].&[2004]`", "4 and 8"]:
        q = _q(key=answer, distractors=["Prints a report", "Installs the server", "Backs up a database"])
        assert not [m for _f, m in answer_notes(q) if "cut short" in m], answer


def test_a_key_much_longer_than_every_wrong_answer_gives_itself_away():
    q = _q(key="The complete row, with fields for the error description, codes and the fields in error",
           distractors=["Only the error message", "The Java stack trace", "The key fields and a flag"])

    assert any("much longer" in m for _f, m in answer_notes(q))
    level = _q(key="The complete row and its error fields",
               distractors=["Only the error message, as one field", "The Java stack trace of the insert",
                            "The key fields and an error flag"])
    assert not [m for _f, m in answer_notes(level) if "much longer" in m]


def test_the_house_checks_include_the_answer_checks():
    q = _q(key="Moves and shapes the")

    assert any("cut short" in m for _f, m in house_findings(q))


# --- the gate ------------------------------------------------------------------


def test_a_clean_draft_goes_to_approved_through_review():
    q = _q(status="draft")

    assert pass_gate(q, []) == "approved"
    assert q.status == "approved"
    assert [(h["from_status"], h["to_status"]) for h in q.review_history] == [
        ("draft", "sme_review"), ("sme_review", "approved")]
    assert {h["sme_name"] for h in q.review_history} == {GATE_REVIEWER}


def test_a_question_with_findings_is_held_for_review_with_the_reasons():
    q = _q(status="draft")

    assert pass_gate(q, [("options", "An answer is cut short.")]) == "review"
    assert q.status == "sme_review"
    assert "An answer is cut short." in q.review_history[-1]["comment"]


def test_an_approved_question_that_now_fails_goes_back_to_review():
    q = _q(status="approved")

    pass_gate(q, [("explanation", "The check doubts the explanation.")])

    assert q.status == "sme_review"


def test_rejected_and_retired_questions_are_left_where_they_are():
    for status in ("rejected", "retired"):
        q = _q(status=status)
        pass_gate(q, [])
        assert q.status == status and q.review_history == []
