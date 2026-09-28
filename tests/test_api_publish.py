"""Publishing the bank's questions back into a course, over HTTP.

The merge itself is tested in ``test_publisher.py``. What matters here is the
protocol around it: that a write cannot be issued without a plan, that the two
endpoints agree, and that a request which would put the wrong questions into a
course is refused before anything is written.
"""

import json

import pytest
from fastapi.testclient import TestClient

from exam_bank.api import deps
from exam_bank.api.app import app
from exam_bank.core.bank import Certification, ExamBankDB, Question

EXAM = {
    "title": "Demo Exam",
    "passMark": 80,
    "questionsPerAttempt": 2,
    "shuffle": True,
    "webhookUrl": "https://script.google.com/macros/s/EXAMPLE/exec",
    "webhookSecret": "pcm_exam_example",
    "intake": {"optional": True, "trackResults": True},
    # A course prompt holds the question only - PCM adds the count. The bank's
    # stems below still carry "(Choose one.)", as older bank questions do, so
    # every test here also checks that a count is never mistaken for an edit.
    "questions": [
        {"id": "m1-q0", "prompt": "Question 0?",
         "options": ["Right", "Wrong"], "correct": 0, "module": "Getting Started",
         "source": "Lab 1 - Getting Started"},
        {"id": "m1-q1", "prompt": "Question 1?",
         "options": ["Right", "Wrong"], "correct": 0, "module": "Getting Started",
         "source": "Lab 1 - Getting Started"},
    ],
}


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "publish.db"


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


@pytest.fixture
def course(tmp_path, monkeypatch):
    """A course on disk with an exam the bank is allowed to publish into."""
    from exam_bank.utils.config import config

    root = tmp_path / "courses"
    course_dir = root / "demo-course"
    course_dir.mkdir(parents=True)
    (course_dir / "course.json").write_text(
        json.dumps({"title": "Demo Course"}), encoding="utf-8")
    (course_dir / "exam.json").write_text(
        json.dumps(EXAM, indent=2) + "\n", encoding="utf-8", newline="\n")
    monkeypatch.setattr(config, "pcm_courses_dir", str(root))
    return course_dir


@pytest.fixture
def cert(db_path):
    """A certification adopted from demo-course, with its pool approved."""
    database = ExamBankDB(db_path)
    certification = Certification(
        name="Demo Practitioner", source_type="pcm", source_ref="demo-course")
    database.save_certification(certification)
    for i in range(2):
        database.save(Question(
            id=f"m1-q{i}", stem=f"Question {i}? (Choose one.)", key="Right",
            distractors=["Wrong"], option_order=["Right", "Wrong"],
            topic="Getting Started", certification_id=certification.id,
            pool_order=i, status="approved", source_type="pcm",
            # The authored citation an adopted question carries. Without it
            # the exporter builds one from the course and section, and every
            # question reads as changed on the first publish.
            source_file="Lab 1 - Getting Started",
        ))
    database.close()
    return certification


def body(cert, **kw):
    return {"certification_id": cert.id, **kw}


# --- the protocol ---------------------------------------------------------


def test_a_plan_writes_nothing(client, course, cert):
    before = (course / "exam.json").read_bytes()
    response = client.post(
        "/api/courses/demo-course/exam/questions/plan", json=body(cert))

    assert response.status_code == 200
    assert (course / "exam.json").read_bytes() == before


def test_a_plan_reports_what_would_change(client, course, cert, db_path):
    database = ExamBankDB(db_path)
    question = database.get("m1-q0")
    question.stem = "Reworded? (Choose one.)"
    database.save(question)
    database.close()

    plan = client.post(
        "/api/courses/demo-course/exam/questions/plan", json=body(cert)).json()

    assert plan["changed"] == [{"id": "m1-q0", "fields": ["prompt"]}]
    assert plan["isNoop"] is False
    assert plan["beforeCount"] == 2 and plan["afterCount"] == 2


def test_a_count_in_the_bank_stem_is_not_a_change(client, course, cert):
    """The bank's stems end "(Choose one.)" and the course's prompts do not.
    Publishing drops the count, so the two say the same thing."""
    plan = client.post(
        "/api/courses/demo-course/exam/questions/plan", json=body(cert)).json()

    assert plan["changed"] == []
    assert plan["isNoop"] is True


def test_a_bare_count_typed_in_review_never_reaches_the_course(client, course, cert, db_path):
    """Found in the live bank, 28 Sep 2026: "Choose One." typed on its own line
    during review. PCM strips only a bracketed count, so published as it was,
    a learner would have read "...? Choose One. (Choose one)"."""
    database = ExamBankDB(db_path)
    question = database.get("m1-q0")
    question.stem = "Reworded? \nChoose One."
    database.save(question)
    database.close()

    plan = client.post(
        "/api/courses/demo-course/exam/questions/plan", json=body(cert)).json()
    client.post("/api/courses/demo-course/exam/questions",
                json=body(cert, expect_sha=plan["sourceSha"]))

    after = json.loads((course / "exam.json").read_text(encoding="utf-8"))
    assert after["questions"][0]["prompt"] == "Reworded?"


def test_publishing_cleans_a_count_the_course_file_carried(client, course, cert):
    """A course written before the rule holds "(Choose one.)" in its prompts.
    The next publish leaves the question only, and says so in the plan."""
    exam = json.loads((course / "exam.json").read_text(encoding="utf-8"))
    for item in exam["questions"]:
        item["prompt"] += " (Choose one.)"
    (course / "exam.json").write_text(
        json.dumps(exam, indent=2) + "\n", encoding="utf-8", newline="\n")

    plan = client.post(
        "/api/courses/demo-course/exam/questions/plan", json=body(cert)).json()
    assert plan["changed"] == [{"id": "m1-q0", "fields": ["prompt"]},
                               {"id": "m1-q1", "fields": ["prompt"]}]

    client.post("/api/courses/demo-course/exam/questions",
                json=body(cert, expect_sha=plan["sourceSha"]))
    after = json.loads((course / "exam.json").read_text(encoding="utf-8"))
    assert [q["prompt"] for q in after["questions"]] == ["Question 0?", "Question 1?"]


def test_publishing_without_a_plan_is_refused(client, course, cert):
    """expect_sha is the plan's hash, so a client cannot write without having
    asked what it was about to change."""
    response = client.post("/api/courses/demo-course/exam/questions", json=body(cert))

    assert response.status_code == 400
    assert "plan" in response.json()["detail"]


def test_a_stale_hash_is_refused(client, course, cert):
    response = client.post(
        "/api/courses/demo-course/exam/questions",
        json=body(cert, expect_sha="0" * 64))

    assert response.status_code == 409
    assert "changed" in response.json()["detail"]


def test_plan_then_publish_writes_the_questions(client, course, cert, db_path):
    database = ExamBankDB(db_path)
    question = database.get("m1-q0")
    question.stem = "Reworded? (Choose one.)"
    database.save(question)
    database.close()

    plan = client.post(
        "/api/courses/demo-course/exam/questions/plan", json=body(cert)).json()
    response = client.post(
        "/api/courses/demo-course/exam/questions",
        json=body(cert, expect_sha=plan["sourceSha"]))

    assert response.status_code == 200
    assert response.json()["written"] is True
    after = json.loads((course / "exam.json").read_text(encoding="utf-8"))
    assert after["questions"][0]["prompt"] == "Reworded?"


def test_the_editors_settings_survive_the_round_trip(client, course, cert):
    plan = client.post(
        "/api/courses/demo-course/exam/questions/plan", json=body(cert)).json()
    client.post("/api/courses/demo-course/exam/questions",
                json=body(cert, expect_sha=plan["sourceSha"]))

    after = json.loads((course / "exam.json").read_text(encoding="utf-8"))
    for key in ("title", "passMark", "questionsPerAttempt", "shuffle",
                "webhookUrl", "webhookSecret", "intake"):
        assert after[key] == EXAM[key], f"{key} changed"


def test_the_plan_lists_preserved_keys_without_their_values(client, course, cert):
    """Several of these hold credentials. The author needs to see that they
    survived, not what they are."""
    plan = client.post(
        "/api/courses/demo-course/exam/questions/plan", json=body(cert)).json()

    assert "intake" in plan["preservedKeys"]
    assert "webhookSecret" in plan["preservedKeys"]
    assert EXAM["webhookSecret"] not in json.dumps(plan)


# --- refusals -------------------------------------------------------------


def test_publishing_needs_a_certification(client, course):
    response = client.post(
        "/api/courses/demo-course/exam/questions/plan", json={})

    assert response.status_code == 400
    assert "one course" in response.json()["detail"]


def test_an_unknown_certification_is_404(client, course):
    response = client.post(
        "/api/courses/demo-course/exam/questions/plan",
        json={"certification_id": "nope"})

    assert response.status_code == 404


def test_publishing_into_the_wrong_course_is_refused(client, tmp_path, cert, monkeypatch):
    """A certification adopted from one course must not overwrite another's
    pool: the ids would not collide, so it would look like a success."""
    from exam_bank.utils.config import config

    root = tmp_path / "courses"
    other = root / "other-course"
    other.mkdir(parents=True)
    (other / "course.json").write_text("{}", encoding="utf-8")
    (other / "exam.json").write_text(json.dumps(EXAM), encoding="utf-8")
    monkeypatch.setattr(config, "pcm_courses_dir", str(root))

    response = client.post(
        "/api/courses/other-course/exam/questions/plan", json=body(cert))

    assert response.status_code == 409
    assert "demo-course" in response.json()["detail"]


def test_a_status_with_no_questions_is_refused(client, course, cert):
    """Publishing the empty result of a filter would empty the course's pool."""
    response = client.post(
        "/api/courses/demo-course/exam/questions/plan",
        json=body(cert, status="rejected"))

    assert response.status_code == 409
    assert "cannot be sat" in response.json()["detail"]


def test_a_stale_intake_contact_block_is_refused_over_http(client, course, cert):
    """The block five published exam.json turned out to carry."""
    document = json.loads(json.dumps(EXAM))
    document["intake"]["contact"] = {"webhookSecret": "pcm_contact_example"}
    (course / "exam.json").write_text(json.dumps(document, indent=2), encoding="utf-8")

    response = client.post(
        "/api/courses/demo-course/exam/questions/plan", json=body(cert))

    assert response.status_code == 409
    assert "intake.contact" in response.json()["detail"]


def test_an_unknown_course_is_404(client, course, cert):
    response = client.post(
        "/api/courses/renamed-away/exam/questions/plan", json=body(cert))

    assert response.status_code == 404
