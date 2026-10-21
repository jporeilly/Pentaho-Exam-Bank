"""Reading the model's JSON out of its reply (1.16.0).

A model wraps its JSON in a ```json fence. An explanation may now hold a
fenced code block of its own, so the reply carries fences INSIDE the JSON as
well; taking the text between the first two fences cut it in half, and
2hr-m3-q10 failed every rewrite that way. These replies are its shape.
"""

import json

from exam_bank.core import providers, question_refinement
from exam_bank.core.bank import Question
from exam_bank.core.generation_parsing import _extract_json_array, _extract_json_object

EXPLANATION = "It walks the array:\n\n```json\n{\"customers\": [{\"region_code\": \"N\"}]}\n```"
OBJECT = {"key": "$.customers[*].region_code", "distractors": ["$.a", "$.b"], "explanation": EXPLANATION}


def _fenced(payload) -> str:
    return "```json\n" + json.dumps(payload, indent=2) + "\n```"


def test_an_object_whose_explanation_holds_a_code_block_is_read_whole():
    assert _extract_json_object(_fenced(OBJECT)) == OBJECT


def test_an_array_of_such_questions_is_read_whole():
    assert _extract_json_array(_fenced([OBJECT, OBJECT])) == [OBJECT, OBJECT]


def test_plain_and_unfenced_replies_still_read():
    assert _extract_json_object(json.dumps(OBJECT)) == OBJECT
    assert _extract_json_object("Here it is:\n" + _fenced({"a": 1}) + "\nDone.") == {"a": 1}
    assert _extract_json_array("not json at all") is None


def test_the_rewrite_reads_a_reply_with_a_code_block(monkeypatch):
    q = Question(id="q", stem="Which expression?", key="$.customers[*].region_code",
                 distractors=["$.a", "$.b"], explanation="Old.")
    reply = {"scenario": "", "stem": "Which expression?", **OBJECT}
    monkeypatch.setattr(providers, "generate", lambda **kw: _fenced(reply))

    p = question_refinement.improve_question(q, model="m")

    assert p is not None, "the reply was cut at the code block's fence"
    assert p.explanation == EXPLANATION
