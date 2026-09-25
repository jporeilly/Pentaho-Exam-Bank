"""AI rewrite and AI review, over HTTP.

The model is stubbed throughout. What is being tested is the wiring, and the
wiring is where the danger is: `question_refinement` has carried eight AI
operations since the NiceGUI days with no test and no caller, and the first
one wired up turned out to assign the model's output straight onto the
Question it was handed.

The rule these pin: **an AI endpoint writes nothing.** It proposes, and an
author accepts by saving, which is the same look-then-act shape publishing
and importing already use. Here it is not a nicety — a model that edited the
bank directly would be the only contributor whose work nobody reviewed.
"""

import json

import pytest
from fastapi.testclient import TestClient

from exam_bank.api import deps
from exam_bank.api.app import app
from exam_bank.core import providers, question_refinement
from exam_bank.core.bank import ExamBankDB, Question


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "ai.db"


@pytest.fixture
def question(db_path):
    q = Question(
        id="q-ai", stem="What does a transformation do? (Choose one.)",
        question_type="single", key="Moves and shapes rows",
        distractors=["Prints a report", "Installs the server", "Backs up a database"],
        explanation="Moves and shapes rows - Correct. Prints a report - Incorrect.",
        topic="Basics",
    )
    database = ExamBankDB(db_path)
    try:
        database.save(q)
    finally:
        database.close()
    return q


@pytest.fixture
def client(db_path):
    def override():
        database = ExamBankDB(db_path)
        try:
            yield database
        finally:
            database.close()

    app.dependency_overrides[deps.get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def a_model_is_configured(monkeypatch):
    monkeypatch.setattr(providers, "active_provider", lambda: "ollama")
    monkeypatch.setattr(providers, "model_for", lambda _p: "a-model")


def _stub_generate(monkeypatch, reply: str):
    """Answer every model call with one canned reply."""
    monkeypatch.setattr(providers, "generate", lambda **kw: reply)


# --- rewrite -------------------------------------------------------------


REWRITE = json.dumps({
    "scenario": "A developer is building their first pipeline.",
    "stem": "What is a transformation responsible for? (Choose one.)",
    "key": "Moving and shaping rows",
    "distractors": ["Printing a report", "Installing the server", "Backing up a database"],
    "explanation": "Moving and shaping rows - Correct. Printing a report - Incorrect.",
})


def test_a_rewrite_is_returned_and_nothing_is_saved(client, question, db_path, monkeypatch):
    _stub_generate(monkeypatch, REWRITE)

    r = client.post("/api/questions/q-ai/ai/rewrite", json={})
    assert r.status_code == 200
    assert r.json()["proposed"]["stem"] == "What is a transformation responsible for? (Choose one.)"

    database = ExamBankDB(db_path)
    try:
        assert database.get("q-ai").stem == "What does a transformation do? (Choose one.)", (
            "the bank must be untouched until the author saves"
        )
    finally:
        database.close()


def test_the_stored_question_is_not_mutated_in_memory(question, monkeypatch):
    """`improve_question` used to assign onto its argument, so the caller's
    Question came back already rewritten - and anything that saved it
    afterwards persisted an AI edit nobody had accepted."""
    _stub_generate(monkeypatch, REWRITE)
    before = question.stem

    proposed = question_refinement.improve_question(question, "a-model")

    assert proposed is not question
    assert proposed.stem != before
    assert question.stem == before, "the input must come back untouched"


def test_a_rewrite_that_cannot_be_graded_says_so(client, question, monkeypatch):
    """The proposal is validated before the author is offered it: an
    'improvement' with no distractors cannot be got wrong."""
    _stub_generate(monkeypatch, json.dumps({
        "stem": "What is a transformation responsible for? (Choose one.)",
        "key": "Moving and shaping rows",
        "distractors": [],
    }))

    body = client.post("/api/questions/q-ai/ai/rewrite", json={}).json()
    assert body["problems"], "an ungradeable proposal must be flagged, not offered silently"


def test_an_unusable_model_reply_is_a_bad_gateway(client, question, monkeypatch):
    _stub_generate(monkeypatch, "I'm afraid I can't help with that.")

    r = client.post("/api/questions/q-ai/ai/rewrite", json={})
    assert r.status_code == 502


def test_no_model_configured_is_a_conflict_not_a_crash(client, question, monkeypatch):
    monkeypatch.setattr(providers, "model_for", lambda _p: "")

    r = client.post("/api/questions/q-ai/ai/rewrite", json={})
    assert r.status_code == 409
    assert "Settings" in r.json()["detail"]


def test_a_missing_question_is_404(client, question, monkeypatch):
    _stub_generate(monkeypatch, REWRITE)
    assert client.post("/api/questions/nope/ai/rewrite", json={}).status_code == 404


# --- review --------------------------------------------------------------


def test_the_review_separates_answer_faults_from_proofreading(client, question, monkeypatch):
    """"The key is also true of option C" and "a comma is missing" are not
    the same kind of news; a flat list buries the first under the second."""
    _stub_generate(monkeypatch, json.dumps([
        {"field": "distractor", "value": "Prints a report",
         "issue": "This is also correct in some contexts.", "severity": "error"},
    ]))

    body = client.post("/api/questions/q-ai/ai/review").json()
    assert body["answers"][0]["field"] == "distractor"
    assert body["answers"][0]["severity"] == "error"
    assert "prose" in body and "gradeable" in body


def test_the_review_writes_nothing(client, question, db_path, monkeypatch):
    _stub_generate(monkeypatch, "[]")
    before = ExamBankDB(db_path)
    try:
        snapshot = before.get("q-ai").stem
    finally:
        before.close()

    client.post("/api/questions/q-ai/ai/review")

    after = ExamBankDB(db_path)
    try:
        assert after.get("q-ai").stem == snapshot
    finally:
        after.close()


def test_a_reviewer_that_finds_nothing_returns_an_empty_list(client, question, monkeypatch):
    """An empty array is a valid and common answer, not a failure."""
    _stub_generate(monkeypatch, "[]")
    body = client.post("/api/questions/q-ai/ai/review").json()
    assert body["answers"] == []


def test_a_finding_with_an_unknown_field_is_kept_not_dropped(question, monkeypatch):
    """Silently discarding a model's answer is how a reviewer stops being
    one. An unrecognised field is reported against the option set."""
    _stub_generate(monkeypatch, json.dumps([
        {"field": "vibes", "issue": "Something is off about this.", "severity": "warning"},
    ]))

    found = question_refinement.review_answers(question, "a-model")
    assert len(found) == 1 and found[0]["field"] == "options"


def test_a_finding_with_no_issue_text_is_dropped(question, monkeypatch):
    """A row that says nothing is noise on a review screen."""
    _stub_generate(monkeypatch, json.dumps([
        {"field": "key", "issue": "   ", "severity": "error"},
        {"field": "key", "issue": "The key is wrong.", "severity": "error"},
    ]))

    found = question_refinement.review_answers(question, "a-model")
    assert [f["issue"] for f in found] == ["The key is wrong."]


def test_an_unrecognised_severity_becomes_a_warning(question, monkeypatch):
    """Not an error: only the model's explicit "error" earns that, or every
    malformed row would read as a fault in the question."""
    _stub_generate(monkeypatch, json.dumps([
        {"field": "key", "issue": "Possibly imprecise.", "severity": "catastrophic"},
    ]))

    assert question_refinement.review_answers(question, "a-model")[0]["severity"] == "warning"


def test_model_prose_that_is_not_json_is_not_a_finding(question, monkeypatch):
    _stub_generate(monkeypatch, "Looks good to me!")
    assert question_refinement.review_answers(question, "a-model") == []
