"""Wrong answers by topic and module (1.20.0), and the AI reading of them."""
import json

import pytest
from fastapi.testclient import TestClient

from exam_bank.api.deps import get_db
from exam_bank.api.app import app
from exam_bank.core import item_analysis as ia
from exam_bank.core import providers, topic_advice, topic_report
from exam_bank.core.bank import Certification, ExamBankDB, Question

COURSE = "developer-di-practitioner"


def seed(path):
    db = ExamBankDB(path)
    cert = Certification(name="DI Practitioner", source_type="pcm", source_ref=COURSE)
    db.save_certification(cert)
    for qid, topic in (("di-m1-q1", "Steps"), ("di-m1-q2", "Steps"), ("di-m2-q1", "Jobs"), ("di-m2-q2", "")):
        q = Question(id=qid, stem=f"Stem {qid}?", key="K", distractors=["A", "B"], topic=topic)
        q.certification_id = cert.id
        db.save(q)
    ia.ensure_schema(db.conn)
    # 25 attempts, each answering all four; Steps is wrong 20/50, Jobs 5/25, no-topic 0/25,
    # plus one answer to a question that left the bank (always wrong).
    rows = []
    for i in range(25):
        a = f"att{i:02d}"
        day = "2026-10-01T09:00:00" if i < 15 else "2026-10-20T09:00:00"
        rows.append((a, "di-m1-q1", COURSE, day, "A", "K", 0 if i < 15 else 1))
        rows.append((a, "di-m1-q2", COURSE, day, "K", "K", 1 if i < 5 else 0 if i < 10 else 1))
        rows.append((a, "di-m2-q1", COURSE, day, "K", "K", 0 if i < 5 else 1))
        rows.append((a, "di-m2-q2", COURSE, day, "K", "K", 1))
    rows.append(("att00", "gone-m9-q1", COURSE, "2026-10-01T09:00:00", "A", "K", 0))
    db.conn.executemany(
        "INSERT INTO responses (attempt_id, question_id, course_id, submitted_at, user_answer, "
        "correct_answer, was_correct) VALUES (?,?,?,?,?,?,?)", rows)
    db.conn.commit()
    return db


@pytest.fixture
def db(tmp_path):
    d = seed(tmp_path / "t.db")
    yield d
    d.close()


def test_topics_are_ranked_by_wrong_answers(db):
    rep = topic_report.build(db)
    (course,) = rep["courses"]
    by = {t["label"]: t for t in course["topics"]}
    assert by["Steps"]["wrong"] == 15 + 5 and by["Steps"]["answers"] == 50
    assert by["Steps"]["questions"] == 2
    assert by["Jobs"]["wrong"] == 5
    assert by[topic_report.NO_TOPIC]["wrong"] == 0
    assert by[topic_report.NOT_IN_BANK]["wrong"] == 1
    assert [t["label"] for t in course["topics"]][0] == "Steps"
    assert by["Steps"]["worstQuestions"][0]["id"] == "di-m1-q1"
    assert rep["wrong"] == sum(t["wrong"] for t in course["topics"])


def test_modules_come_from_the_question_id(db):
    (course,) = topic_report.build(db)["courses"]
    by = {m["label"]: m for m in course["modules"]}
    assert set(by) == {"Module 1", "Module 2", "Module 9"}
    assert by["Module 1"]["wrong"] == 20
    assert course["modules"][0]["label"] == "Module 1"       # most wrong first


def test_the_filters_narrow_the_report(db):
    late = {f"att{i:02d}" for i in range(15, 25)}
    (course,) = topic_report.build(db, late)["courses"]
    assert {t["label"]: t["answers"] for t in course["topics"]}["Steps"] == 20
    assert topic_report.build(db, set())["courses"] == []


def test_thin_rows_are_marked(db):
    (course,) = topic_report.build(db)["courses"]
    by = {t["label"]: t for t in course["topics"]}
    assert by["Steps"]["thin"] is False and by[topic_report.NOT_IN_BANK]["thin"] is True


def test_the_prompt_carries_only_report_numbers(db):
    prompt = topic_advice.build_prompt(topic_report.build(db))
    assert "Steps" in prompt and "di-m1-q1" in prompt and "att00" not in prompt


def test_reply_is_checked_against_the_report(db):
    rep = topic_report.build(db)
    reply = json.dumps({"summary": "Steps is weak.", "suggestions": [
        {"course": "DI Practitioner", "topic": "Steps", "questionIds": ["di-m1-q1", "invented"],
         "priority": "HIGH", "advice": "Check the key."},
        {"course": "DI Practitioner", "topic": "Invented topic", "advice": "Nonsense."},
    ]})
    out = topic_advice.parse_reply("```json\n" + reply + "\n```", rep)
    assert out["summary"] == "Steps is weak." and out["dropped"] == 1
    assert out["suggestions"] == [{"course": "DI Practitioner", "topic": "Steps",
                                   "questionIds": ["di-m1-q1"], "priority": "high",
                                   "advice": "Check the key."}]
    assert topic_advice.parse_reply("plain prose", rep)["summary"] == "plain prose"


def test_endpoints(tmp_path, monkeypatch):
    path = tmp_path / "api.db"
    seed(path).close()

    def override():
        d = ExamBankDB(path)
        try:
            yield d
        finally:
            d.close()

    calls = []
    monkeypatch.setattr(providers, "active_provider", lambda: "ollama")
    monkeypatch.setattr(providers, "model_for", lambda _p: "m")
    monkeypatch.setattr(providers, "generate",
                        lambda **kw: calls.append(kw) or json.dumps({"summary": "ok", "suggestions": []}))
    app.dependency_overrides[get_db] = override
    try:
        c = TestClient(app)
        rep = c.get("/api/results/topics").json()
        assert rep["courses"][0]["topics"][0]["label"] == "Steps"
        late = c.get("/api/results/topics", params={"date_from": "2026-10-15"}).json()
        assert late["answers"] == 40
        assert c.get("/api/results/topics", params={"passed": "x"}).status_code == 422
        r = c.post("/api/results/topics/advice")
        assert r.status_code == 200 and r.json()["summary"] == "ok" and r.json()["model"] == "m"
        assert len(calls) == 1
        none = c.post("/api/results/topics/advice", params={"date_from": "2030-01-01"}).json()
        assert none["suggestions"] == [] and len(calls) == 1      # nothing to read: no model call

        def boom(**kw):
            raise providers.ProviderError("ANTHROPIC_API_KEY is not set")
        monkeypatch.setattr(providers, "generate", boom)
        bad = c.post("/api/results/topics/advice")
        assert bad.status_code == 503 and "ANTHROPIC_API_KEY" in bad.json()["detail"]
    finally:
        app.dependency_overrides.clear()
