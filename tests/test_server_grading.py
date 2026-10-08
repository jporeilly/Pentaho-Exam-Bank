"""Server grading (1.13.0): a server-graded exam is published WITHOUT its keys,
which go to the results service first; nothing reads them back from a course.

The results service itself is never contacted here - results_service's HTTP is
replaced - but every decision the bank makes around it is exercised."""
import json

import pytest
from fastapi.testclient import TestClient

from exam_bank.api import deps
from exam_bank.api.app import app
from exam_bank.core import course_sync, publisher, results_service
from exam_bank.core.bank import Certification, ExamBankDB, Question
from exam_bank.core.question_importer import import_from_pcm_exam_json

EXAM = {
    "title": "Demo Exam",
    "passMark": 75,
    "questionsPerAttempt": 2,
    "shuffle": True,
    "webhookUrl": "https://script.google.com/macros/s/EXAMPLE/exec",
    "questions": [
        {"id": "m1-q0", "prompt": "Question 0?", "options": ["Right", "Wrong"], "correct": 0,
         "explanation": "Right is right.", "module": "Getting Started",
         "source": "Lab 1 - Getting Started", "bloom": "Apply"},
        {"id": "m1-q1", "prompt": "Question 1?", "options": ["Right", "Wrong"], "correct": 0,
         "explanation": "Right again.", "module": "Getting Started",
         "source": "Lab 1 - Getting Started", "bloom": "Understand"},
    ],
}


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "grading.db"


@pytest.fixture
def client(db_path):
    def override():
        d = ExamBankDB(db_path)
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[deps.get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def course(tmp_path, monkeypatch):
    from exam_bank.utils.config import config

    root = tmp_path / "courses"
    d = root / "demo-course"
    d.mkdir(parents=True)
    (d / "course.json").write_text(json.dumps({"title": "Demo", "level": {"number": 3, "name": "Certified"}}),
                                   encoding="utf-8")
    (d / "exam.json").write_text(json.dumps(EXAM, indent=2) + "\n", encoding="utf-8", newline="\n")
    monkeypatch.setattr(config, "pcm_courses_dir", str(root))
    return d


@pytest.fixture
def cert(db_path):
    d = ExamBankDB(db_path)
    c = Certification(name="Demo Certified", source_type="pcm", source_ref="demo-course")
    d.save_certification(c)
    for i, expl in enumerate(["Right is right.", "Right again."]):
        d.save(Question(id=f"m1-q{i}", stem=f"Question {i}?", key="Right", distractors=["Wrong"],
                        option_order=["Right", "Wrong"], explanation=expl, topic="Getting Started",
                        certification_id=c.id, pool_order=i, status="approved", source_type="pcm",
                        bloom_level=["Apply", "Understand"][i], source_file="Lab 1 - Getting Started"))
    d.close()
    return c


@pytest.fixture
def uploads(monkeypatch):
    """Record what would go to the results service instead of sending it."""
    sent = []

    def fake(url, course_id, pass_mark, level, items):
        sent.append({"url": url, "course": course_id, "passMark": pass_mark, "level": level,
                     "keys": results_service.keys_from_items(items)})
        return len(items)

    monkeypatch.setattr(results_service, "upload_keys", fake)
    return sent


def publish(client, cert, **kw):
    req = {"certification_id": cert.id, **kw}
    plan = client.post("/api/courses/demo-course/exam/questions/plan", json=req)
    assert plan.status_code == 200, plan.text
    return plan.json(), client.post("/api/courses/demo-course/exam/questions",
                                    json={**req, "expect_sha": plan.json()["sourceSha"]})


def exam_on_disk(course):
    return json.loads((course / "exam.json").read_text(encoding="utf-8"))


def test_switching_to_server_grading_publishes_without_keys_after_uploading_them(client, course, cert, uploads):
    plan, done = publish(client, cert, grading="server")
    assert plan["grading"] == "server" and plan["gradingBefore"] == "app" and not plan["isNoop"]
    assert done.status_code == 200, done.text
    assert done.json()["keysStored"] == 2
    written = exam_on_disk(course)
    assert written["grading"] == "server"
    for q in written["questions"]:
        assert not {"correct", "correctIndices", "explanation"} & set(q), q
        assert q["options"] and q["prompt"] and q["source"]
    assert uploads == [{
        "url": EXAM["webhookUrl"], "course": "demo-course", "passMark": 75, "level": 3,
        "keys": [
            {"id": "m1-q0", "module": "Getting Started", "options": ["Right", "Wrong"],
             "correct": ["Right"], "explanation": "Right is right."},
            {"id": "m1-q1", "module": "Getting Started", "options": ["Right", "Wrong"],
             "correct": ["Right"], "explanation": "Right again."},
        ],
    }]


def test_a_failed_upload_writes_nothing(client, course, cert, monkeypatch):
    def refuse(*a, **k):
        raise results_service.ResultsServiceError("The results service refused the admin secret.")

    monkeypatch.setattr(results_service, "upload_keys", refuse)
    before = (course / "exam.json").read_bytes()
    _, done = publish(client, cert, grading="server")
    assert done.status_code == 409 and "Nothing was written" in done.json()["detail"]
    assert (course / "exam.json").read_bytes() == before


def test_a_server_graded_exam_stays_server_graded_and_can_switch_back(client, course, cert, uploads):
    publish(client, cert, grading="server")
    plan, done = publish(client, cert)            # no switch: keep the exam's own
    assert plan["grading"] == "server" and done.status_code == 200
    assert len(uploads) == 2, "every server-graded publish refreshes the keys"
    plan, done = publish(client, cert, grading="app")
    written = exam_on_disk(course)
    assert "grading" not in written and written["questions"][0]["correct"] == 0
    assert written["questions"][0]["explanation"] == "Right is right."


def test_server_grading_needs_a_results_service(client, course, cert, uploads):
    doc = exam_on_disk(course)
    doc["webhookUrl"] = ""
    (course / "exam.json").write_text(json.dumps(doc), encoding="utf-8")
    plan = client.post("/api/courses/demo-course/exam/questions/plan",
                       json={"certification_id": cert.id, "grading": "server"})
    assert plan.status_code == 409 and "results service" in plan.json()["detail"]


def test_upload_keys_alone_writes_nothing(client, course, cert, uploads):
    before = (course / "exam.json").read_bytes()
    r = client.post("/api/courses/demo-course/exam/keys", json={"certification_id": cert.id})
    assert r.status_code == 200 and r.json() == {"courseId": "demo-course", "keysStored": 2, "level": 3}
    assert (course / "exam.json").read_bytes() == before and len(uploads) == 1


def test_nothing_reads_keys_back_from_a_server_graded_course(client, course, cert, uploads, db_path):
    publish(client, cert, grading="server")
    with pytest.raises(ValueError, match="no answer keys"):
        import_from_pcm_exam_json(course / "exam.json")
    d = ExamBankDB(db_path)
    try:
        outcome = next(c for c in course_sync.plan(course.parent, d).courses if c.slug == "demo-course")
    finally:
        d.close()
    assert outcome.note and not (outcome.new or outcome.changed or outcome.unusable)


def test_keys_are_texts_for_single_and_multi():
    keys = results_service.keys_from_items([
        {"id": "a", "options": ["x", "y", "z"], "correct": 2},
        {"id": "b", "options": ["p", "q", "r"], "correctIndices": [0, 2], "explanation": "e"},
    ])
    assert keys[0]["correct"] == ["z"] and keys[1]["correct"] == ["p", "r"]


def test_the_admin_secret_is_needed_and_never_shown(client, monkeypatch):
    monkeypatch.delenv(results_service.ENV, raising=False)
    assert client.get("/api/results/service").json() == {"configured": False, "env": results_service.ENV}
    with pytest.raises(results_service.ResultsServiceError, match=results_service.ENV):
        results_service.upload_keys("https://script.google.com/x", "c", 80, 1,
                                    [{"id": "a", "options": ["x"], "correct": 0}])
    monkeypatch.setenv(results_service.ENV, "s3cret-value")
    status = client.get("/api/results/service").json()
    assert status["configured"] is True and "s3cret" not in json.dumps(status)


def test_an_unauthorized_answer_says_what_to_fix(monkeypatch):
    monkeypatch.setenv(results_service.ENV, "wrong")

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"ok": false, "error": "unauthorized"}'

    monkeypatch.setattr(results_service.urllib.request, "urlopen", lambda req, timeout: Reply())
    with pytest.raises(results_service.ResultsServiceError, match="ADMIN_SECRET"):
        results_service.export_results("https://script.google.com/x")


def test_pull_imports_what_the_service_exports(client, course, monkeypatch):
    monkeypatch.setattr(results_service, "export_results", lambda url: [
        {"attempt_id": "a1", "question_id": "m1-q0", "course_id": "demo-course", "submitted_at": "",
         "user_answer": "Right", "correct_answer": "Right", "was_correct": 1}])
    r = client.post("/api/results/pull")
    assert r.status_code == 200 and r.json()["added"] == 1 and r.json()["services"] == 1
