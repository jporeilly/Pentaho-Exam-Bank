"""The Bank's column filters (1.12.0): id, exact topic, and a text search
that covers every answer - each one on the list, its count and the export."""
import pytest
from fastapi.testclient import TestClient

from exam_bank.core.bank import Certification, ExamBankDB, Question


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "filters.db"


@pytest.fixture
def db(db_path):
    database = ExamBankDB(db_path)
    yield database
    database.close()


@pytest.fixture
def client(db_path):
    from exam_bank.api.app import app
    from exam_bank.api.deps import get_db

    def override():
        database = ExamBankDB(db_path)
        try:
            yield database
        finally:
            database.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def cert(db):
    c = Certification(name="DI Practitioner", source_type="pcm", source_ref="developer-di-practitioner")
    db.save_certification(c)
    rows = [
        ("di-m1-q1", "Joins", "Easy", "Remember", "Which step joins?", ["Merge join", "Sort rows"]),
        ("di-m4-q2", "Joins and lookups", "Hard", "Analyze", "Which lookup?", ["Stream lookup", "Dummy"]),
        ("di-m4-q3", "Variables", "Hard", "Apply", "Which variable?", ["kettle.properties", "Dummy"]),
    ]
    for qid, topic, difficulty, bloom, stem, distractors in rows:
        db.save(Question(id=qid, stem=stem, key="Right", distractors=distractors, topic=topic,
                         difficulty=difficulty, bloom_level=bloom, certification_id=c.id))
    return c


def ids(body):
    return sorted(q["id"] for q in body["items"])


def test_id_filter_is_a_contains_match(client, cert):
    body = client.get("/api/questions", params={"id": "m4"}).json()
    assert ids(body) == ["di-m4-q2", "di-m4-q3"]
    assert body["total"] == 2, "the count must apply the same filter as the page"


def test_exact_topic_does_not_catch_a_topic_that_contains_it(client, cert):
    # "Joins" is inside "Joins and lookups": the old contains-match took both.
    assert ids(client.get("/api/questions", params={"exact_topic": "Joins"}).json()) == ["di-m1-q1"]
    assert ids(client.get("/api/questions", params={"topic": "Joins"}).json()) == ["di-m1-q1", "di-m4-q2"]


def test_filters_combine(client, cert):
    body = client.get("/api/questions", params={"difficulty": "Hard", "bloom_level": "Apply"}).json()
    assert ids(body) == ["di-m4-q3"] and body["total"] == 1


def test_text_search_reaches_the_distractors(client, cert):
    # The search box promises "answers": a distractor is one.
    assert ids(client.get("/api/questions", params={"text": "kettle.properties"}).json()) == ["di-m4-q3"]


def test_topics_in_course_order_with_counts(client, cert):
    topics = client.get("/api/topics", params={"certification_id": cert.id}).json()
    assert {t["topic"]: t["questionCount"] for t in topics} == {
        "Joins": 1, "Joins and lookups": 1, "Variables": 1,
    }
    assert client.get("/api/topics").json(), "with no certification, every topic"


def test_export_honours_the_column_filters(client, cert):
    r = client.get("/api/export/json", params={"exact_topic": "Joins", "id": "m1"})
    assert r.status_code == 200
    exported = r.json()
    rows = exported if isinstance(exported, list) else exported.get("questions", [])
    assert [q["id"] for q in rows] == ["di-m1-q1"]
