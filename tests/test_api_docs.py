"""Browsing, searching and asking about the app's own documentation.

The asking is what these tests are mostly about. A model asked a question
answers *something* whether or not it was given anything to read, and a
confident invention about a tool somebody is about to use is worse than no
answer — so the tests assert that the model is not called at all when
retrieval finds nothing.
"""

import pytest
from fastapi.testclient import TestClient

from exam_bank.api.app import app
from exam_bank.api.routers import docs as docs_router
from exam_bank.core import docs as docs_core
from exam_bank.core.providers import ProviderError

GUIDE = """\
Pentaho Exam Bank helps you build certification exams.

## Importing Existing Questions

Drop a CSV into the Import pane. A duplicate is flagged rather than imported.

## Database Backup & Restore

Take a backup before deleting anything.
"""


@pytest.fixture(autouse=True)
def docs_on_disk(tmp_path, monkeypatch):
    """Point the loader at a temporary guide, so the tests do not depend on
    whatever the real documentation currently says."""
    (tmp_path / "HOW_TO_GUIDE.md").write_text(GUIDE, encoding="utf-8")
    monkeypatch.setattr(docs_core, "PROJECT_ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def model(monkeypatch):
    """Record what the model was asked, and answer predictably."""
    asked = {}

    def fake_generate(prompt, **kwargs):
        asked["prompt"] = prompt
        asked["kwargs"] = kwargs
        return "  Use the Import pane.  "

    monkeypatch.setattr(docs_router, "generate", fake_generate)
    return asked


# --- browsing --------------------------------------------------------------


def test_the_documents_are_listed_with_their_sections(client):
    body = client.get("/api/docs").json()

    assert [d["document"] for d in body] == ["How-To Guide"]
    headings = [s["heading"] for s in body[0]["sections"]]
    assert "Importing Existing Questions" in headings


def test_a_document_that_is_not_there_is_simply_absent(client):
    body = client.get("/api/docs").json()

    assert "README" not in [d["document"] for d in body]


# --- searching -------------------------------------------------------------


def test_search_ranks_the_subject_of_the_question(client):
    body = client.get("/api/docs/search", params={"q": "How do I import a CSV?"}).json()

    assert body["results"][0]["heading"] == "Importing Existing Questions"


def test_search_says_how_much_it_looked_through(client):
    """So an empty result reads as "not in the docs" rather than "docs not
    loaded", which look identical otherwise."""
    body = client.get("/api/docs/search", params={"q": "nothing matches this"}).json()

    assert body["results"] == []
    assert body["sectionsSearched"] > 0


def test_search_returns_a_snippet_not_the_whole_section(client):
    body = client.get("/api/docs/search", params={"q": "backup"}).json()

    assert "snippet" in body["results"][0]


# --- asking ----------------------------------------------------------------


def test_an_answer_comes_back_with_what_it_was_built_from(client, model):
    body = client.post("/api/docs/ask", json={"question": "How do I import a CSV?"}).json()

    assert body["answered"] is True
    assert body["answer"] == "Use the Import pane."
    assert [s["heading"] for s in body["sources"]] == ["Importing Existing Questions"]


def test_the_model_is_given_the_documentation(client, model):
    client.post("/api/docs/ask", json={"question": "How do I import a CSV?"})

    assert "Drop a CSV into the Import pane" in model["prompt"]
    assert "Question: How do I import a CSV?" in model["prompt"]


def test_a_question_the_docs_do_not_cover_never_reaches_the_model(client, model):
    """The whole point. Asked with no documentation, a model answers from what
    it knows about apps of this kind, and that reads exactly like an answer
    about this one."""
    body = client.post("/api/docs/ask", json={"question": "kubernetes helm chart"}).json()

    assert body["answered"] is False
    assert "Nothing in the documentation covers that" in body["answer"]
    assert body["sources"] == []
    assert "prompt" not in model, "the model was called with nothing to read"


def test_an_empty_question_is_refused(client, model):
    response = client.post("/api/docs/ask", json={"question": "   "})

    assert response.status_code == 400
    assert "prompt" not in model


def test_missing_documentation_is_reported_rather_than_answered(
    client, model, tmp_path, monkeypatch
):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(docs_core, "PROJECT_ROOT", empty)

    response = client.post("/api/docs/ask", json={"question": "How do I import a CSV?"})

    assert response.status_code == 409
    assert "No documentation" in response.json()["detail"]
    assert "prompt" not in model


def test_a_provider_failure_keeps_its_own_message(client, monkeypatch):
    """The provider names the thing to fix — an absent key, a model that was
    never pulled — and that is more useful than anything invented here."""
    def failing(prompt, **kwargs):
        raise ProviderError("ANTHROPIC_API_KEY is not set in the environment.")

    monkeypatch.setattr(docs_router, "generate", failing)

    response = client.post("/api/docs/ask", json={"question": "How do I import a CSV?"})

    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


def test_the_answer_says_which_model_produced_it(client, model):
    body = client.post("/api/docs/ask", json={"question": "backup"}).json()

    assert "provider" in body and "model" in body
