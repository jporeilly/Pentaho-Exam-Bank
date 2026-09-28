"""The Documentation screen's API: pages by section, one page, search.

Asking questions about the documentation moved to AI Chat
(``tests/test_chat.py``); this is the reading side.
"""

import pytest
from fastapi.testclient import TestClient

from exam_bank.api.app import app
from exam_bank.core import docs as docs_core

GUIDE = """\
Pentaho Exam Bank helps you build certification exams.

## Importing Existing Questions

Drop a CSV into the Import pane. A duplicate is flagged rather than imported.

## Database Backup & Restore

Take a backup before deleting anything.
"""

FIRST = """\
# Getting Started

Open the app from its shortcut.

## The window

The side bar holds the screens.

## The window

A second heading with the same words.
"""

SETTINGS = """\
# Settings

Everything under System, section by section.
"""


@pytest.fixture(autouse=True)
def docs_on_disk(tmp_path, monkeypatch):
    """A small documentation tree, so the tests do not depend on whatever the
    real documentation currently says."""
    (tmp_path / "HOW_TO_GUIDE.md").write_text(GUIDE, encoding="utf-8")
    guides = tmp_path / "docs" / "guides"
    guides.mkdir(parents=True)
    (guides / "01-getting-started.md").write_text(FIRST, encoding="utf-8")
    admin = tmp_path / "docs" / "admin"
    admin.mkdir()
    (admin / "01-settings.md").write_text(SETTINGS, encoding="utf-8")
    # Working material that must NOT be served.
    (tmp_path / "docs" / "PORT-AUDIT.md").write_text("# Port audit\n\nInternal.\n", encoding="utf-8")
    notes = tmp_path / "docs" / "bloom-review"
    notes.mkdir()
    (notes / "README.md").write_text("# Bloom review\n\nInternal.\n", encoding="utf-8")
    monkeypatch.setattr(docs_core, "PROJECT_ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def client():
    return TestClient(app)


# --- the list ----------------------------------------------------------------


def test_pages_are_listed_by_section_in_order(client):
    body = client.get("/api/docs").json()

    assert [s["name"] for s in body["sections"]] == ["Start here", "Using the Exam Bank", "Administration"]
    assert body["count"] == 3


def test_a_page_title_is_its_own_heading(client):
    body = client.get("/api/docs").json()
    guides = next(s for s in body["sections"] if s["name"] == "Using the Exam Bank")

    assert guides["items"][0]["title"] == "Getting Started"
    assert guides["items"][0]["slug"] == "docs/guides/01-getting-started"
    assert guides["items"][0]["summary"] == "Open the app from its shortcut."


def test_working_material_under_docs_is_not_served(client):
    """The Bloom review notes and the port audit are for developers."""
    slugs = [i["slug"] for s in client.get("/api/docs").json()["sections"] for i in s["items"]]

    assert not any("bloom-review" in s or "PORT-AUDIT" in s for s in slugs)


def test_a_missing_root_document_is_simply_absent(client):
    slugs = [i["slug"] for s in client.get("/api/docs").json()["sections"] for i in s["items"]]

    assert "README" not in slugs and "HOW_TO_GUIDE" in slugs


# --- one page ----------------------------------------------------------------


def test_a_page_comes_without_its_title_line(client):
    """The screen prints the title above the page; left in, it would show twice."""
    page = client.get("/api/docs/page", params={"slug": "docs/guides/01-getting-started"}).json()

    assert page["title"] == "Getting Started"
    assert not page["content"].startswith("# ")
    assert page["content"].startswith("Open the app")


def test_a_page_carries_its_heading_ids_with_repeats_numbered(client):
    """GitHub's rule, so a link into the page works on GitHub and here."""
    page = client.get("/api/docs/page", params={"slug": "docs/guides/01-getting-started"}).json()

    assert [h["id"] for h in page["headings"]] == ["the-window", "the-window-1"]
    # Lines count within the content as served, which is how the screen
    # matches a rendered heading to its id.
    first = page["headings"][0]["line"]
    assert page["content"].splitlines()[first - 1] == "## The window"


def test_an_unknown_page_is_a_404(client):
    assert client.get("/api/docs/page", params={"slug": "docs/guides/nope"}).status_code == 404


@pytest.mark.parametrize("slug", [
    "../exam_bank/utils/config",
    "docs/../HOW_TO_GUIDE",
    "docs/PORT-AUDIT",
    "docs/bloom-review/README",
    "C:/Windows/win",
])
def test_nothing_outside_the_listed_pages_can_be_read(client, slug):
    """A lookup among the listed pages, never a path built from the request."""
    assert client.get("/api/docs/page", params={"slug": slug}).status_code == 404


# --- search ------------------------------------------------------------------


def test_search_ranks_the_subject_of_the_question(client):
    body = client.get("/api/docs/search", params={"q": "How do I import a CSV?"}).json()

    assert body["results"][0]["heading"] == "Importing Existing Questions"


def test_a_search_result_says_where_it_opens(client):
    body = client.get("/api/docs/search", params={"q": "side bar screens"}).json()
    top = body["results"][0]

    assert top["slug"] == "docs/guides/01-getting-started"
    assert top["page"] == "Getting Started"
    assert top["section"] == "Using the Exam Bank"
    assert top["anchor"] == "the-window"


def test_search_says_how_much_it_looked_through(client):
    """So an empty result reads as "not in the docs" rather than "docs not
    loaded", which look identical otherwise."""
    body = client.get("/api/docs/search", params={"q": "nothing matches this"}).json()

    assert body["results"] == []
    assert body["sectionsSearched"] > 0


def test_search_returns_a_snippet_not_the_whole_section(client):
    body = client.get("/api/docs/search", params={"q": "backup"}).json()

    assert "snippet" in body["results"][0] and "text" not in body["results"][0]


def test_the_old_ask_endpoint_is_gone(client):
    """Asking moved to AI Chat, which also searches docs.pentaho.com."""
    assert client.post("/api/docs/ask", json={"question": "x"}).status_code in (404, 405)
