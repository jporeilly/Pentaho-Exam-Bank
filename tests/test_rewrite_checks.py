"""What a rewrite took out or put in, checked word for word (1.17.0).

The cases are from the first 100 reviewed rewrites (2026-10-11): each fault
here was found by a reviewer, in a rewrite a 12B model called a proofread.
"""

from exam_bank.core.bank import Question
from exam_bank.core.rewrite_checks import keep_capitals, preservation_notes


def _q(**over):
    base = dict(id="q", scenario="", stem="What is the most likely cause?", question_type="single",
                key="The query does not sort the rows", distractors=["The cache is full", "The driver is old"])
    base.update(over)
    return Question(**base)


def _messages(original, proposed):
    return " | ".join(m for _, m in preservation_notes(original, proposed))


def test_a_dropped_clue_is_noted():
    # rd/2hr-m3-q4: the sentence that says the files arrive unsorted was cut.
    before = _q(scenario="A Merge join step combines a region file and a sales file. The files are "
                         "processed in the order they are written, and some matches are missing.")
    after = _q(scenario="A Merge join step combines a region file and a sales file, and some matches "
                        "are missing.")
    assert "dropped words from the scenario: processed, order, written" in _messages(before, after)


def test_an_added_reason_is_noted():
    # 2hr-m4-q7: the rewrite told the candidate why - the answer.
    before = _q(scenario="A developer runs a transformation with 10 steps and finds a date error in the "
                         "third step, which took effort to debug.")
    after = _q(scenario="A developer runs a transformation with 10 steps and finds a date error in the "
                        "third step, which took effort to debug because it was only caught after the "
                        "transformation finished running.")
    assert "added to the scenario: because, caught, finished, running" in _messages(before, after)


def test_a_changed_word_in_an_answer_is_noted():
    # 2hr-m2-q6: "decoded" became "deployed" in a wrong answer.
    before = _q(distractors=["Serialized Java objects decoded by the IDE", "The driver is old"])
    after = _q(distractors=["Serialized Java objects deployed by the IDE", "The driver is old"])
    assert "An answer's words changed" in _messages(before, after)


def test_a_light_proofread_is_not_noted():
    before = _q(scenario="Forty reports share the company's colours, and the licence is renewed.",
                key="The query doesn't sort the rows.", distractors=["the cache is full", "The driver is old"])
    after = _q(scenario="Forty reports share the company's colors, and the license is renewed.",
               key="The query does not sort the rows", distractors=["The cache is full.", "The driver is old"])
    assert preservation_notes(before, after) == []


def test_a_lost_number_is_noted_even_alone():
    before = _q(scenario="The reference table holds 40 million rows.")
    after = _q(scenario="The reference table holds many rows.")
    assert "dropped words from the scenario" in _messages(before, after)


def test_lowercased_answers_get_their_capitals_back_everywhere():
    # rd-m8-q2: "A url-formula ..." came back as "a url-formula ...".
    before = _q(key="A url-formula using DRILLDOWN", distractors=["A sub-report", "3-D bars"])
    after = _q(key="a url-formula using DRILLDOWN", distractors=["a sub-report", "3-D bars"],
               option_order=["a sub-report", "a url-formula using DRILLDOWN", "3-D bars"])
    fixed = keep_capitals(before, after)
    assert fixed.key == "A url-formula using DRILLDOWN"
    assert fixed.distractors == ["A sub-report", "3-D bars"]
    assert fixed.option_order == ["A sub-report", "A url-formula using DRILLDOWN", "3-D bars"]
    assert after.key == "a url-formula using DRILLDOWN", "the proposal given is not changed"


def test_an_answer_that_began_in_lower_case_keeps_it():
    before = _q(key="`$.customers[*].id`", distractors=["iPhone sync", "The driver is old"])
    after = _q(key="`$.customers[*].id`", distractors=["iPhone sync", "The driver is old"])
    assert keep_capitals(before, after).distractors[0] == "iPhone sync"


def test_a_mangled_topic_filter_is_noted():
    # SD rerun: the wrong answer "+/sensor/#" came back as "+/sensor_#".
    before = _q(distractors=["+/sensor/#", "industrial/#"])
    after = _q(distractors=["+/sensor_#", "industrial/#"])
    assert "An answer's words changed" in _messages(before, after)
    same = _q(distractors=["`+/sensor/#`", "industrial/#."])
    assert _messages(before, same) == "", "code marks and a full stop are not a change"
