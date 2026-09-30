"""The docs check on import: does docs.pentaho.com back each question's answer?

The search itself is stubbed; what is tested is how an answer is judged
against what comes back, and that a failure is never passed off as a verdict.
"""

import pytest
from fastapi.testclient import TestClient

from exam_bank.api.app import app
from exam_bank.core import docs_check, mcp_client
from exam_bank.core.bank import Question
from exam_bank.core.mcp_client import SearchResult
from exam_bank.utils.config import config

PAGE = SearchResult(
    title="Text File Input",
    link="https://docs.pentaho.com/pdi/text-file-input",
    content="The Text File Input step reads data from delimited text files such as CSV.",
)
OTHER = SearchResult(title="Sort rows", link="https://docs.pentaho.com/pdi/sort-rows",
                     content="Sort rows orders the stream by the fields you choose.")


@pytest.fixture
def docs(monkeypatch):
    queries = []

    def fake(query, url, limit=5, timeout=15.0):
        queries.append(query)
        return [OTHER, PAGE]

    monkeypatch.setattr(mcp_client, "search", fake)
    monkeypatch.setattr(config, "validation_threshold", 0.7)
    return queries


def q(key, stem="Which step reads a CSV file?", **kw):
    return Question(stem=stem, key=key, distractors=["Sort rows", "Table output"], **kw)


def test_an_answer_the_docs_carry_is_supported_and_the_page_named(docs):
    result = docs_check.check(q("Text File Input"))

    assert result["status"] == "supported"
    assert result["sources"][0] == {"title": "Text File Input", "link": PAGE.link}
    assert "Which step reads a CSV file?" in docs[0] and "Text File Input" in docs[0]


def test_an_answer_the_docs_do_not_carry_is_not_found(docs):
    result = docs_check.check(q("Microsoft Access Input"))

    assert result["status"] == "not-found"
    assert result["answers"][0]["score"] < 0.7


def test_filler_words_do_not_count():
    # "the", "of", "a" and "in" are on every page; counted, they let an answer
    # the docs never mention pass on grammar alone.
    assert docs_check._words("The step of a workbook in Excel") == {"step", "workbook", "excel"}


def test_a_multi_select_needs_every_answer_backed(docs):
    both = Question(stem="Which two steps?", question_type="multi",
                    keys=["Text File Input", "Sort rows"], key="Text File Input", distractors=["x"])
    one = Question(stem="Which two steps?", question_type="multi",
                   keys=["Text File Input", "Salesforce Upsert"], key="Text File Input", distractors=["x"])

    assert docs_check.check(both)["status"] == "supported"
    assert docs_check.check(one)["status"] == "not-found"


def test_a_failed_search_is_an_error_not_a_verdict(monkeypatch):
    def down(*a, **k):
        raise mcp_client.McpError("docs.pentaho.com did not answer")

    monkeypatch.setattr(mcp_client, "search", down)
    result = docs_check.check(q("Text File Input"))

    assert result["status"] == "error" and "did not answer" in result["detail"]


def test_a_question_with_nothing_marked_correct_is_not_searched(docs):
    assert docs_check.check(q(""))["status"] == "error"
    assert docs == []


def test_the_endpoint_answers_in_order_and_writes_nothing(docs, monkeypatch):
    monkeypatch.setattr(config, "docs_mcp_enabled", True)
    body = TestClient(app).post("/api/import/check-docs", json={"questions": [
        {"stem": "Which step reads a CSV file?", "key": "Text File Input", "distractors": ["a"]},
        {"not": "a question"},
        {"stem": "Which step reads Access?", "key": "Microsoft Access Input", "distractors": ["a"]},
    ]}).json()

    assert [r["status"] for r in body["results"]] == ["supported", "error", "not-found"]
    assert body["threshold"] == 0.7


def test_the_endpoint_says_when_the_docs_connection_is_off(monkeypatch):
    monkeypatch.setattr(config, "docs_mcp_enabled", False)
    response = TestClient(app).post("/api/import/check-docs", json={"questions": [{"stem": "x?"}]})

    assert response.status_code == 409 and "off in Settings" in response.json()["detail"]
