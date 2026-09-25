"""Where the key sits in a published question.

`all_choices` is correct answers followed by distractors, so a question the
bank authored publishes with its key at option A every time. Across the live
courses that had already reached 94% in pdi-2hr-lab. The Content Manager now
shuffles at render, so no learner sees the stored order - this is about the
file, and about anything else that reads it.
"""

import collections

from exam_bank.core.bank import Question
from exam_bank.core.exporter import stable_option_order, pcm_exam_items


def _authored(qid, key="KEY"):
    """A question created in the bank: no recorded option order."""
    return Question(
        id=qid, stem=f"{qid}? (Choose one.)", question_type="single",
        key=key, distractors=["wrong-1", "wrong-2", "wrong-3"],
        explanation="KEY - Correct. wrong-1 - Incorrect.",
    )


def test_the_key_is_not_always_first():
    items = [pcm_exam_items([_authored(f"q-{i}")])[0] for i in range(200)]
    at_a = sum(1 for it in items if it["correct"] == 0)
    assert at_a < 80, (
        f"{at_a} of 200 keys landed at option A; unscattered this is 200"
    )


def test_the_key_reaches_every_position():
    seen = collections.Counter(
        pcm_exam_items([_authored(f"q-{i}")])[0]["correct"]
        for i in range(400)
    )
    assert set(seen) == {0, 1, 2, 3}, f"only reached {sorted(seen)}"
    for pos, n in seen.items():
        assert 60 < n < 140, f"position {pos} got {n} of 400; expected about 100"


def test_correct_still_points_at_the_key():
    """The whole thing is worthless if the index and the option disagree."""
    for i in range(50):
        item = pcm_exam_items([_authored(f"q-{i}")])[0]
        assert item["options"][item["correct"]] == "KEY"
        assert sorted(item["options"]) == sorted(
            ["KEY", "wrong-1", "wrong-2", "wrong-3"]
        )


def test_publishing_the_same_question_twice_writes_the_same_order():
    """Deterministic, not random. A fresh permutation on every publish would
    rewrite every option of every question each time - an unreadable diff,
    and a plan claiming the whole pool changed when nothing did."""
    first = pcm_exam_items([_authored("q-stable")])[0]
    second = pcm_exam_items([_authored("q-stable")])[0]
    assert first["options"] == second["options"]
    assert first["correct"] == second["correct"]


def test_a_question_adopted_from_a_course_keeps_its_authored_order():
    """That order is the author's decision. Rewriting it would churn the
    file and override a choice the bank was not asked to make."""
    q = _authored("q-adopted")
    q.option_order = ["wrong-2", "KEY", "wrong-1", "wrong-3"]
    item = pcm_exam_items([q])[0]
    assert item["options"] == ["wrong-2", "KEY", "wrong-1", "wrong-3"]
    assert item["correct"] == 1


def test_a_single_option_question_is_left_alone():
    q = Question(id="q-one", stem="Only one? (Choose one.)", question_type="single",
                 key="KEY", distractors=[], explanation="KEY - Correct.")
    item = pcm_exam_items([q])[0]
    assert item["options"] == ["KEY"] and item["correct"] == 0


def test_the_permutation_is_a_permutation():
    for n in (2, 3, 4, 5, 8):
        order = stable_option_order("q-x", n)
        assert sorted(order) == list(range(n))


def test_the_docx_export_does_not_label_every_answer_A(tmp_path):
    """The PDF paper and the text export both shuffled; the Word one wrote
    `[key] + distractors` straight out, so it read "the answer is A" all the
    way down."""
    from docx import Document

    from exam_bank.core.exporter import export_docx

    out = tmp_path / "bank.docx"
    export_docx([_authored(f"q-{i}") for i in range(40)], out)

    text = "\n".join(p.text for p in Document(str(out)).paragraphs)
    at_a = sum(1 for line in text.splitlines() if line.strip() == "A: KEY")
    assert at_a < 20, f"{at_a} of 40 keys labelled A; unscattered this is 40"
    assert "KEY" in text


def test_a_question_is_written_the_same_way_in_both_outputs():
    """One permutation, so the Word document and the published exam.json
    agree about where a question's key sits."""
    q = _authored("q-consistent")
    published = pcm_exam_items([q])[0]
    order = stable_option_order(q.id, 4)
    expected_first = (["KEY"] + q.distractors)[order[0]]
    assert published["options"][0] == expected_first
