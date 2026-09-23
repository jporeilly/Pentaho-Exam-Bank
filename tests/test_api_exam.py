"""Building a weighted exam paper, over HTTP.

The selection itself is tested in `test_exam_builder.py`. What matters here is
the protocol around it: that a weighting which cannot be met is *reported*
rather than quietly delivered as something else, and that the plan an author
approves describes the paper they get.
"""

import pytest
from fastapi.testclient import TestClient

from exam_bank.api import deps
from exam_bank.api.app import app
from exam_bank.core.bank import Certification, ExamBankDB, Question

# Deliberately lopsided: Cloud cannot fill a large weight, which is the case
# the report exists for.
TOPICS = {"Networking": 10, "Security": 8, "Cloud": 3}


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "exam.db"


@pytest.fixture
def seeded(db_path):
    database = ExamBankDB(db_path)
    certification = database.save_certification(
        Certification(name="Exam Cert", source_type="pptx")
    )
    for topic, count in TOPICS.items():
        for i in range(count):
            database.save(Question(
                stem=f"{topic} question {i + 1}? (Choose one.)",
                key=f"{topic} answer {i + 1}",
                distractors=["Wrong A", "Wrong B", "Wrong C"],
                topic=topic, difficulty="Medium", bloom_level="Apply",
                certification_id=certification.id, status="approved",
            ))
    database.close()
    return certification


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


def body(cert, **kw):
    return {
        "certification_ids": [cert.id],
        "total_questions": 9,
        "topic_weights": {"Networking": 34, "Security": 33, "Cloud": 33},
        **kw,
    }


# --- what can be built on --------------------------------------------------


def test_topics_reports_what_has_questions(client, seeded):
    rows = client.get("/api/exam/topics",
                      params={"certification_ids": seeded.id}).json()

    assert {r["topic"]: r["questionCount"] for r in rows} == TOPICS


def test_topics_is_empty_without_a_certification(client, seeded):
    """Rather than every topic in the bank: a weighting is built against the
    certifications being drawn from, and any other topic would be a row that
    can only ever contribute zero."""
    assert client.get("/api/exam/topics").json() == []


def test_topics_respects_the_status_filter(client, seeded):
    rows = client.get("/api/exam/topics", params={
        "certification_ids": seeded.id, "statuses": "draft",
    }).json()

    assert rows == []


# --- the plan --------------------------------------------------------------


def test_a_weighting_the_bank_can_meet_is_reported_as_honoured(client, seeded):
    plan = client.post("/api/exam/plan", json=body(seeded)).json()

    assert plan["honoured"] is True
    assert plan["selected"] == 9
    assert plan["shortfall"] == 0


def test_a_topic_too_small_for_its_weight_is_named(client, seeded):
    """Cloud has 3 questions. Asked for 10, it supplies 3 and the rest comes
    from elsewhere — which is a different exam from the one requested."""
    plan = client.post("/api/exam/plan", json=body(
        seeded, total_questions=20,
        topic_weights={"Networking": 25, "Security": 25, "Cloud": 50},
    )).json()

    cloud = next(t for t in plan["topics"] if t["topic"] == "Cloud")
    assert cloud["wanted"] == 10
    assert cloud["available"] == 3
    assert cloud["short"] == 7
    assert plan["honoured"] is False
    assert plan["redistributed"] > 0


def test_the_plan_builds_no_pdf(client, seeded):
    response = client.post("/api/exam/plan", json=body(seeded))

    assert response.headers["content-type"].startswith("application/json")


def test_a_selection_matching_nothing_is_refused(client, seeded):
    """Not an empty paper: a PDF with no questions is a thing somebody prints
    and hands out before noticing."""
    response = client.post("/api/exam/plan", json=body(seeded, statuses=["rejected"]))

    assert response.status_code == 409
    assert "drafts" in response.json()["detail"]


# --- refusals --------------------------------------------------------------


def test_weights_that_do_not_total_100_are_refused(client, seeded):
    response = client.post("/api/exam/plan", json=body(
        seeded, topic_weights={"Networking": 40, "Security": 30, "Cloud": 10},
    ))

    assert response.status_code == 400
    assert "80%" in response.json()["detail"]

    client.post("/api/exam/plan", json=body(seeded)).raise_for_status()


def test_a_three_way_split_is_not_refused_over_rounding(client, seeded):
    """34/33/33 is what an author gets for splitting three ways, and refusing
    it would make the tool unusable for the commonest case."""
    response = client.post("/api/exam/plan", json=body(
        seeded, topic_weights={"Networking": 34, "Security": 33, "Cloud": 33},
    ))

    assert response.status_code == 200


def test_a_negative_weight_is_refused(client, seeded):
    response = client.post("/api/exam/plan", json=body(
        seeded, topic_weights={"Networking": 120, "Security": -20},
    ))

    assert response.status_code == 400
    assert "negative" in response.json()["detail"]


def test_no_certification_is_refused(client, seeded):
    response = client.post("/api/exam/plan", json=body(seeded, certification_ids=[]))

    assert response.status_code == 400


def test_no_topics_is_refused_and_says_where_to_get_them(client, seeded):
    response = client.post("/api/exam/plan", json=body(seeded, topic_weights={}))

    assert response.status_code == 400
    assert "/api/exam/topics" in response.json()["detail"]


def test_no_difficulties_is_refused(client, seeded):
    response = client.post("/api/exam/plan", json=body(seeded, difficulties=[]))

    assert response.status_code == 400


# --- the paper -------------------------------------------------------------


def test_the_pdf_is_a_pdf(client, seeded):
    response = client.post("/api/exam/pdf", json=body(seeded))

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content[:4] == b"%PDF"


def test_the_pdf_uses_the_filename_that_was_asked_for(client, seeded):
    response = client.post("/api/exam/pdf",
                           json=body(seeded, filename="networking-midterm.pdf"))

    assert "networking-midterm.pdf" in response.headers["content-disposition"]


def test_the_pdf_is_refused_on_the_same_terms_as_the_plan(client, seeded):
    """Otherwise an author who cannot get a plan can still get a paper, and
    the plan stops being the thing that decides."""
    response = client.post("/api/exam/pdf", json=body(
        seeded, topic_weights={"Networking": 40, "Security": 30, "Cloud": 10},
    ))

    assert response.status_code == 400


def test_a_seed_reproduces_the_same_paper(client, seeded):
    """A paper handed out and then reprinted has to be the same paper."""
    first = client.post("/api/exam/plan", json=body(seeded, seed=11)).json()
    second = client.post("/api/exam/plan", json=body(seeded, seed=11)).json()

    assert first["topics"] == second["topics"]
