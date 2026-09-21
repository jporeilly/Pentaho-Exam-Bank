"""Round-trip safety net for a PCM ``exam.json``.

The bank is not the only writer of a course's exam: the Content Editor owns
the delivery/grading settings and the bank owns ``questions``. So the bank
must be able to read a live pool, hold it, and write it back **without
changing anything it did not mean to change**.

Two things this guards that were both silently lossy before:

* **Question ids.** PCM treats them as durable external keys — they go into
  the results payload posted to the webhook, and an in-progress attempt is
  keyed on the ids it was dealt. The live pools use hand-authored ids
  (``m1-q1``, ``q-preview``), so minting uuids on import would destroy
  meaningful keys and orphan every recorded result.
* **The ``source`` citation.** It is richer than ``module`` ("Lab 1 — Your
  First Win" vs "See It Work"). The exporter used to rebuild it from
  ``topic``, downgrading it to the module name on every round-trip.
"""

import json

import pytest

from question_bank.core.exporter import export_pcm_exam_json
from question_bank.core.question_importer import (
    import_from_pcm_exam_json,
    is_pcm_exam_json,
)


# Mirrors the real shape of a PCM pool: hand-authored ids, a module, a
# citation that is NOT just the module, and one of each question type.
EXAM = {
    "title": "Wrap-Up Check",
    "description": "20 questions drawn from a pool of 20. Pass mark is 60%.",
    "passMark": 60,
    "questionsPerAttempt": 20,
    "shuffle": True,
    "webhookUrl": "",
    "questions": [
        {
            "id": "q-preview",
            "prompt": "Which step reads a delimited file? (Choose one.)",
            "options": ["CSV file input", "Table output", "Sort rows", "Dummy"],
            "scenario": "A developer is building their first transformation.",
            "module": "See It Work",
            "correct": 0,
            "explanation": "'CSV file input' reads delimited text.",
            "source": "Lab 1 — Your First Win",
        },
        {
            "id": "m1-q2",
            "prompt": "Which two steps write to a database? (Choose two.)",
            "options": ["Table output", "Insert / Update", "Sort rows", "Dummy"],
            "scenario": "A developer needs to persist rows.",
            "module": "Getting Started",
            "correctIndices": [0, 1],
            "explanation": "Both write; the others do not.",
            "source": "Pentaho Developer - Practitioner: Getting Started",
        },
    ],
}


@pytest.fixture
def exam_path(tmp_path):
    path = tmp_path / "exam.json"
    path.write_text(json.dumps(EXAM, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def test_recognised_as_a_pcm_exam(exam_path):
    assert is_pcm_exam_json(exam_path)


def test_authored_ids_survive_import(exam_path):
    questions = import_from_pcm_exam_json(exam_path)
    assert [q.id for q in questions] == ["q-preview", "m1-q2"]


def test_a_question_with_no_id_still_gets_one(tmp_path):
    exam = json.loads(json.dumps(EXAM))
    del exam["questions"][0]["id"]
    path = tmp_path / "exam.json"
    path.write_text(json.dumps(exam), encoding="utf-8")

    minted = import_from_pcm_exam_json(path)[0].id
    assert minted, "a question with no id must still get one"
    # Never positional: PCM's own fallback for a missing id is `q1`, `q2`,
    # ... and an id that depends on a question's place in the list breaks
    # the moment the pool is reordered.
    assert minted not in ("q1", "1", "0")


def test_authored_source_citation_survives(exam_path, tmp_path):
    questions = import_from_pcm_exam_json(exam_path)
    out = tmp_path / "out.json"
    export_pcm_exam_json(questions, out, title=EXAM["title"])

    sources = [q["source"] for q in json.loads(out.read_text(encoding="utf-8"))["questions"]]
    assert sources == ["Lab 1 — Your First Win",
                       "Pentaho Developer - Practitioner: Getting Started"]


def test_round_trip_preserves_every_question(exam_path, tmp_path):
    """import -> export reproduces the `questions` array exactly."""
    questions = import_from_pcm_exam_json(exam_path)
    out = tmp_path / "out.json"
    export_pcm_exam_json(
        questions, out,
        title=EXAM["title"],
        description=EXAM["description"],
        pass_mark=EXAM["passMark"],
        questions_per_attempt=EXAM["questionsPerAttempt"],
        shuffle=EXAM["shuffle"],
    )
    after = json.loads(out.read_text(encoding="utf-8"))

    assert after["questions"] == EXAM["questions"]


def test_pool_order_is_recorded_on_import(exam_path):
    questions = import_from_pcm_exam_json(exam_path)
    assert [q.pool_order for q in questions] == [0, 1]


def test_export_restores_the_authored_order(exam_path, tmp_path):
    """The bank returns questions newest-first, so the exporter must put an
    adopted pool back in the order its author wrote it."""
    questions = import_from_pcm_exam_json(exam_path)
    out = tmp_path / "out.json"
    export_pcm_exam_json(list(reversed(questions)), out, title=EXAM["title"])

    ids = [q["id"] for q in json.loads(out.read_text(encoding="utf-8"))["questions"]]
    assert ids == ["q-preview", "m1-q2"]


def test_generated_questions_keep_the_caller_order(tmp_path):
    """Questions with no authored position (pool_order -1) must not be
    reordered — only an adopted pool has an order to restore."""
    from question_bank.core.question_bank import Question

    made = [
        Question(id="b", stem="Second?", key="k", distractors=["d"]),
        Question(id="a", stem="First?", key="k", distractors=["d"]),
    ]
    assert all(q.pool_order == -1 for q in made)

    out = tmp_path / "gen.json"
    export_pcm_exam_json(made, out, title="Generated")
    ids = [q["id"] for q in json.loads(out.read_text(encoding="utf-8"))["questions"]]
    assert ids == ["b", "a"]


def test_round_trip_preserves_the_settings_the_editor_owns(exam_path, tmp_path):
    """passMark / questionsPerAttempt / description are the Content
    Editor's to own; a republish must hand them back unchanged."""
    questions = import_from_pcm_exam_json(exam_path)
    out = tmp_path / "out.json"
    export_pcm_exam_json(
        questions, out,
        title=EXAM["title"],
        description=EXAM["description"],
        pass_mark=EXAM["passMark"],
        questions_per_attempt=EXAM["questionsPerAttempt"],
        shuffle=EXAM["shuffle"],
    )
    after = json.loads(out.read_text(encoding="utf-8"))

    for key in ("title", "description", "passMark", "questionsPerAttempt", "shuffle"):
        assert after[key] == EXAM[key], f"{key} changed across the round-trip"
