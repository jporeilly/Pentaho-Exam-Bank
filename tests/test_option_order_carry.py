"""An answer keeps its position when it is reworded (1.15.0).

The display order (option_order) names the answers by their text. Editing an
answer used to leave a hole that the next remaining text filled - right for
one edit, but when every answer was reworded at once every slot was a hole
and the correct answer, first in line, landed first: 23 of the bank's 27
stale orders showed it there. A rewrite now carries the order across, and a
stale order fills its holes by likeness.
"""

import json

from exam_bank.core import providers, question_refinement
from exam_bank.core.bank import Question


def _q(**over):
    base = dict(
        id="q", stem="Why are matches missing?", question_type="single",
        key="Neither input is sorted on region_code before the join",
        distractors=[
            "The join type is LEFT OUTER, which skips some matches",
            "Merge join holds only a fixed number of keys in memory",
            "The region file is read only after the sales file ends",
        ],
    )
    base.update(over)
    q = Question(**base)
    # The author's order: the correct answer third.
    q.option_order = [q.distractors[0], q.distractors[1], q.key, q.distractors[2]]
    return q


def test_a_stale_order_fills_each_hole_with_its_own_edit():
    # 2hr-m3-q4 as the bank holds it: every answer reworded since the order
    # was recorded.
    q = _q()
    q.key = "Neither input stream is sorted on region_code before the join."
    q.distractors = [
        "The join type is configured as LEFT OUTER, resulting in the exclusion of certain matches.",
        "The Merge join step has a limited in-memory buffer, preventing it from holding all required keys.",
        "The region file is only read after the entire sales file has been processed.",
    ]
    shown = q.all_choices
    assert shown.index(q.key) == 2, "the correct answer stays where the author put it, not first"
    assert shown[0].startswith("The join type")


def test_one_edit_still_takes_its_own_slot():
    q = _q()
    q.distractors = [q.distractors[0], "Merge join keeps a fixed number of keys in memory", q.distractors[2]]
    assert q.all_choices[1] == "Merge join keeps a fixed number of keys in memory"
    assert q.all_choices[2] == q.key


def test_an_edit_nothing_like_the_old_text_still_finds_a_slot():
    q = _q()
    q.distractors = [q.distractors[0], q.distractors[1], "Completely different"]
    assert sorted(q.all_choices) == sorted([q.key, *q.distractors])


def test_a_rewrite_carries_the_order_to_the_new_wording(monkeypatch):
    q = _q()
    monkeypatch.setattr(providers, "generate", lambda **kw: json.dumps({
        "scenario": "", "stem": q.stem,
        "key": "Neither input stream is sorted on `region_code` before the join.",
        "distractors": [
            "The join is LEFT OUTER, which skips some matches.",
            "The Merge join step holds a fixed number of keys in memory.",
            "The region file is read after the sales file ends.",
        ],
        "explanation": "",
    }))

    p = question_refinement.improve_question(q, model="m")

    assert p.option_order[2] == p.key, "the correct answer keeps its third place"
    assert sorted(p.option_order) == sorted([p.key, *p.distractors])
    assert p.option_order[0] == p.distractors[0]


def test_a_question_with_no_order_keeps_none(monkeypatch):
    # The exports scatter such a question's answers by its id; a recorded
    # key-first list would undo that.
    q = _q()
    q.option_order = []
    monkeypatch.setattr(providers, "generate", lambda **kw: json.dumps({
        "scenario": "", "stem": q.stem, "key": q.key + ".",
        "distractors": [d + "." for d in q.distractors], "explanation": "",
    }))
    assert question_refinement.improve_question(q, model="m").option_order == []
