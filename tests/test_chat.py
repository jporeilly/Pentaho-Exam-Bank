"""AI Chat: grounded in this app's docs and docs.pentaho.com, or not answered.

The rule these tests hold the router to: the model answers only from what the
two searches found, and is not called at all when they found nothing. A model
asked with nothing to read answers from what it knows about tools in general,
and that reads exactly like an answer about this one.
"""

import pytest
from fastapi.testclient import TestClient

from exam_bank.api.app import app
from exam_bank.api.routers import chat as chat_router
from exam_bank.core import chat as chat_core
from exam_bank.core import docs as docs_core
from exam_bank.core import mcp_client
from exam_bank.core.mcp_client import McpError, SearchResult
from exam_bank.core.providers import ProviderError
from exam_bank.utils.config import config

PUBLISHING = """\
# Publishing to a Course

The Publish screen writes the bank's questions into a course's exam.json.

## The push

Publish and push commits the exam and pushes it to the courses repo.
"""

HITS = [
    SearchResult("Archive installation", "https://docs.pentaho.com/install/archive",
                 "An archive installation requires a supported operating system. " * 30),
    SearchResult("Ports", "https://docs.pentaho.com/install/ports", "Pentaho Server listens on 8080."),
]


@pytest.fixture(autouse=True)
def docs_on_disk(tmp_path, monkeypatch):
    guides = tmp_path / "docs" / "guides"
    guides.mkdir(parents=True)
    (guides / "09-publishing.md").write_text(PUBLISHING, encoding="utf-8")
    monkeypatch.setattr(docs_core, "PROJECT_ROOT", tmp_path)


@pytest.fixture(autouse=True)
def mcp_on(monkeypatch):
    monkeypatch.setattr(config, "docs_mcp_enabled", True)
    monkeypatch.setattr(config, "docs_mcp_url", "https://docs.pentaho.com/~gitbook/mcp")


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def model(monkeypatch):
    """Record what the model was asked, and answer predictably."""
    asked = {}

    def fake_chat(messages, **kwargs):
        asked["messages"] = messages
        asked["kwargs"] = kwargs
        return asked.get("reply", "  Use Publish and push [A1]. The server listens on 8080 [P2].  ")

    monkeypatch.setattr(chat_router, "chat", fake_chat)
    return asked


@pytest.fixture
def pentaho(monkeypatch):
    """The docs server: returns HITS, or raises what the test puts in 'error'."""
    calls = {"n": 0}

    def fake_search(query, url, limit=5, timeout=15.0):
        calls["n"] += 1
        calls["query"], calls["url"], calls["limit"] = query, url, limit
        if "error" in calls:
            raise calls["error"]
        return calls.get("hits", HITS)[:limit]

    monkeypatch.setattr(mcp_client, "search", fake_search)
    return calls


def ask(client, question, history=(), **body):
    messages = [*history, {"role": "user", "content": question}]
    return client.post("/api/chat", json={"messages": messages, **body})


# --- grounding ----------------------------------------------------------------


def test_an_answer_comes_back_with_both_sources_numbered(client, model, pentaho):
    body = ask(client, "How do I publish and push an exam?").json()

    assert body["answered"] is True
    assert body["answer"] == "Use Publish and push [A1]. The server listens on 8080 [P2]."
    ids = [s["id"] for s in body["sources"]]
    assert ids[0] == "A1" and "P1" in ids and "P2" in ids


def test_an_app_source_opens_at_its_page_and_heading(client, model, pentaho):
    body = ask(client, "How do I publish and push an exam?").json()
    push = next(s for s in body["sources"] if s["kind"] == "app" and s["heading"] == "The push")

    assert push["slug"] == "docs/guides/09-publishing"
    assert push["anchor"] == "the-push"
    assert push["title"] == "Publishing to a Course"


def test_a_pentaho_source_carries_its_url(client, model, pentaho):
    body = ask(client, "How do I publish and push an exam?").json()
    p1 = next(s for s in body["sources"] if s["id"] == "P1")

    assert p1["kind"] == "pentaho"
    assert p1["url"] == "https://docs.pentaho.com/install/archive"


def test_which_sources_the_answer_cites_is_marked(client, model, pentaho):
    """Shown fainter when given to the model and not used."""
    body = ask(client, "How do I publish and push an exam?").json()
    cited = {s["id"]: s["cited"] for s in body["sources"]}

    assert cited["A1"] is True and cited["P2"] is True and cited["P1"] is False


def test_the_model_is_given_the_sources_and_the_question(client, model, pentaho):
    ask(client, "How do I publish and push an exam?")
    last = model["messages"][-1]["content"]

    assert last.endswith("Question: How do I publish and push an exam?")
    assert "[A1] Exam Bank documentation — Publishing to a Course" in last
    assert "[P2] Pentaho documentation — Ports (https://docs.pentaho.com/install/ports)" in last
    assert "Pentaho Server listens on 8080." in last


def test_a_long_pentaho_page_is_cut(client, model, pentaho):
    ask(client, "How do I publish and push an exam?")
    last = model["messages"][-1]["content"]
    p1 = last.split("[P1]")[1].split("[P2]")[0]

    assert len(p1) < chat_core.PENTAHO_CHARS + 200


def test_the_system_prompt_forbids_answering_from_outside_the_sources(client, model, pentaho):
    ask(client, "How do I publish and push an exam?")
    system = model["kwargs"]["system"]

    assert "Answer only from the sources" in system
    assert "[A1]" in system and "[P1]" in system


def test_only_the_question_text_goes_to_the_docs_server(client, model, pentaho):
    ask(client, "How do I publish and push an exam?")

    assert pentaho["query"] == "How do I publish and push an exam?"
    assert pentaho["url"] == "https://docs.pentaho.com/~gitbook/mcp"
    assert pentaho["limit"] == chat_core.PENTAHO_HITS


# --- conversation ---------------------------------------------------------------


def test_earlier_turns_go_to_the_model_without_their_sources(client, model, pentaho):
    history = [
        {"role": "user", "content": "How do I publish and push an exam?"},
        {"role": "assistant", "content": "Use Publish and push [A1]."},
    ]
    ask(client, "What does the push commit to the courses repo?", history)

    assert model["messages"][0] == {"role": "user", "content": "How do I publish and push an exam?"}
    assert model["messages"][1]["role"] == "assistant"
    assert "Sources for this question" in model["messages"][2]["content"]
    assert len(model["messages"]) == 3


def test_a_short_follow_up_is_searched_with_the_question_before_it(client, model, pentaho):
    history = [
        {"role": "user", "content": "Which port does Pentaho Server use?"},
        {"role": "assistant", "content": "8080 [P2]."},
    ]
    ask(client, "and HTTPS?", history)

    assert pentaho["query"] == "Which port does Pentaho Server use? and HTTPS?"


def test_a_long_history_is_trimmed(client, model, pentaho):
    history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"turn {i} publish"}
               for i in range(30)]
    ask(client, "How do I publish and push an exam?", history)

    assert len(model["messages"]) == chat_core.HISTORY_TURNS + 1


# --- not answering ----------------------------------------------------------------


def test_nothing_found_anywhere_never_reaches_the_model(client, model, pentaho):
    """The whole point."""
    pentaho["hits"] = []
    body = ask(client, "kubernetes helm chart").json()

    assert body["answered"] is False
    assert "Neither this app's documentation nor docs.pentaho.com" in body["answer"]
    assert body["sources"] == []
    assert "messages" not in model, "the model was called with nothing to read"


def test_an_unreachable_docs_server_degrades_to_the_app_docs(client, model, pentaho):
    pentaho["error"] = McpError("Could not reach the server: getaddrinfo failed.")
    body = ask(client, "How do I publish and push an exam?").json()

    assert body["answered"] is True
    assert all(s["kind"] == "app" for s in body["sources"])
    assert body["grounding"]["pentaho"]["error"] == "Could not reach the server: getaddrinfo failed."


def test_unreachable_and_nothing_local_says_both(client, model, pentaho):
    pentaho["error"] = McpError("No answer within 15 seconds.")
    body = ask(client, "kubernetes helm chart").json()

    assert body["answered"] is False
    assert "could not be searched: No answer within 15 seconds." in body["answer"]
    assert "messages" not in model


def test_the_settings_switch_stops_every_call_to_the_docs_server(client, model, pentaho, monkeypatch):
    monkeypatch.setattr(config, "docs_mcp_enabled", False)
    body = ask(client, "How do I publish and push an exam?").json()

    assert pentaho["n"] == 0
    assert body["grounding"]["pentaho"]["searched"] is False
    assert all(s["kind"] == "app" for s in body["sources"])


def test_the_chat_switch_for_pentaho_is_respected(client, model, pentaho):
    ask(client, "How do I publish and push an exam?", pentahoDocs=False)

    assert pentaho["n"] == 0


def test_pentaho_only_does_not_read_the_app_docs(client, model, pentaho):
    body = ask(client, "How do I publish and push an exam?", appDocs=False).json()

    assert body["answered"] is True
    assert all(s["kind"] == "pentaho" for s in body["sources"])


def test_both_sources_off_is_refused(client, model, pentaho):
    response = ask(client, "anything", appDocs=False, pentahoDocs=False)

    assert response.status_code == 400
    assert "messages" not in model


def test_the_last_message_must_be_a_question(client, model, pentaho):
    response = client.post("/api/chat", json={"messages": [{"role": "assistant", "content": "hi"}]})

    assert response.status_code == 400


def test_a_provider_failure_is_a_503_with_its_own_message(client, pentaho, monkeypatch):
    def broken(messages, **kwargs):
        raise ProviderError("No Ollama model is configured.")

    monkeypatch.setattr(chat_router, "chat", broken)
    response = ask(client, "How do I publish and push an exam?")

    assert response.status_code == 503
    assert response.json()["detail"] == "No Ollama model is configured."


# --- the pure pieces ----------------------------------------------------------------


@pytest.mark.parametrize("answer, ids", [
    ("See [A1].", {"A1"}),
    ("Both [A1, P3] and [P2; A4].", {"A1", "P3", "P2", "A4"}),
    ("No citations [here] or [1].", set()),
])
def test_cited_ids(answer, ids):
    assert chat_core.cited_ids(answer) == ids


# --- the docs server's status, for Settings ------------------------------------------


def test_status_reports_the_server_and_its_tools(client, monkeypatch):
    monkeypatch.setattr(mcp_client, "probe", lambda url, timeout=8.0: {
        "server": "Pentaho MCP Server", "version": "0.27.2",
        "tools": ["searchDocumentation", "getPage"], "ms": 312,
    })
    body = client.get("/api/docs-mcp/status").json()

    assert body["ok"] is True and body["searchTool"] is True
    assert body["server"] == "Pentaho MCP Server" and body["ms"] == 312
    assert body["url"] == "https://docs.pentaho.com/~gitbook/mcp"


def test_status_can_test_an_address_before_it_is_saved(client, monkeypatch):
    seen = {}

    def probe(url, timeout=8.0):
        seen["url"] = url
        return {"server": "x", "version": "", "tools": [], "ms": 1}

    monkeypatch.setattr(mcp_client, "probe", probe)
    body = client.get("/api/docs-mcp/status", params={"url": "https://other.example/~gitbook/mcp"}).json()

    assert seen["url"] == "https://other.example/~gitbook/mcp"
    assert body["searchTool"] is False


def test_status_names_the_reason_it_failed(client, monkeypatch):
    def probe(url, timeout=8.0):
        raise McpError("The server answered HTTP 404 Not Found.")

    monkeypatch.setattr(mcp_client, "probe", probe)
    body = client.get("/api/docs-mcp/status").json()

    assert body["ok"] is False
    assert body["error"] == "The server answered HTTP 404 Not Found."


# --- opening a Pentaho page -------------------------------------------------------------


def test_a_docs_page_is_opened_in_the_browser(client, monkeypatch):
    opened = []
    monkeypatch.setattr(chat_router.webbrowser, "open", opened.append)
    response = client.post("/api/open-url", json={"url": "https://docs.pentaho.com/install/ports"})

    assert response.status_code == 204
    assert opened == ["https://docs.pentaho.com/install/ports"]


def test_a_link_in_the_documentation_opens_too(client, monkeypatch):
    """README and INSTALL link to GitHub and ollama.com."""
    opened = []
    monkeypatch.setattr(chat_router.webbrowser, "open", opened.append)

    assert client.post("/api/open-url", json={"url": "https://ollama.com"}).status_code == 204
    assert opened == ["https://ollama.com"]


@pytest.mark.parametrize("url", [
    "http://docs.pentaho.com/install",          # not https
    "file:///C:/Windows/System32/calc.exe",
    "ms-settings:privacy",
    "javascript:alert(1)",
    "https:///no-host",
])
def test_nothing_but_an_https_page_is_opened(client, monkeypatch, url):
    """A file: URL or another scheme runs whatever Windows associates with it."""
    opened = []
    monkeypatch.setattr(chat_router.webbrowser, "open", opened.append)
    response = client.post("/api/open-url", json={"url": url})

    assert response.status_code == 400
    assert opened == []

# --- the streamed answer (1.10.0) ------------------------------------------------------------
#
# The same turn, delivered as it is written: the sources first, then the text
# piece by piece, then the answer whole. Grounded exactly as /api/chat is -
# the two share the search - so only the delivery is tested here.


import json as _json


@pytest.fixture
def streamed(monkeypatch):
    asked = {}

    def fake_stream(messages, **kwargs):
        asked["messages"] = messages
        if "error" in asked:
            yield "Use Publish "
            raise asked["error"]
        yield from asked.get("pieces", ["Use Publish ", "and push [A1]. ", "It listens on 8080 [P2]."])

    monkeypatch.setattr(chat_router, "chat_stream", fake_stream)
    return asked


def stream(client, question, **body):
    response = client.post("/api/chat/stream",
                           json={"messages": [{"role": "user", "content": question}], **body})
    return response, [_json.loads(line) for line in response.text.splitlines() if line.strip()]


def test_the_stream_sends_sources_then_the_text_then_the_whole_answer(client, streamed, pentaho):
    response, events = stream(client, "How do I publish and push an exam?")

    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert [e["type"] for e in events] == ["sources", "token", "token", "token", "done"]
    assert {s["id"] for s in events[0]["sources"]} >= {"A1", "P1", "P2"}
    assert "".join(e["text"] for e in events if e["type"] == "token") == \
        "Use Publish and push [A1]. It listens on 8080 [P2]."
    done = events[-1]
    assert done["answered"] is True and done["answer"].endswith("[P2].")
    assert {s["id"] for s in done["sources"] if s["cited"]} == {"A1", "P2"}


def test_nothing_found_streams_the_reason_and_never_calls_the_model(client, streamed, pentaho):
    pentaho["hits"] = []
    _, events = stream(client, "What colour is the sky on Mars?")

    assert [e["type"] for e in events] == ["sources", "done"]
    assert events[-1]["answered"] is False
    assert "messages" not in streamed


def test_a_model_that_fails_part_way_says_so_in_the_stream(client, streamed, pentaho):
    streamed["error"] = ProviderError("Ollama request failed: connection reset")
    _, events = stream(client, "How do I publish and push an exam?")

    assert [e["type"] for e in events] == ["sources", "token", "error"]
    assert "connection reset" in events[-1]["message"]


def test_a_turn_that_cannot_be_asked_is_refused_before_the_stream(client, streamed, pentaho):
    response, _ = stream(client, "Anything?", appDocs=False, pentahoDocs=False)
    assert response.status_code == 400
