"""Syncing the courses into the bank, over HTTP, and the first-run adopt.

The sync itself is tested in ``test_course_sync.py``. What matters here is the
protocol around it - that a write cannot be issued without a plan, and that a
plan made before somebody pulled the courses repo is refused - and the one
piece of behaviour that happens with nobody watching: a brand-new bank filling
itself on the first launch.
"""

import json

import pytest
from fastapi.testclient import TestClient

from exam_bank.api import deps
from exam_bank.api.app import app, _adopt_courses_on_first_run
from exam_bank.core.bank import Certification, ExamBankDB, Question

EXAM = {
    "title": "Demo Exam",
    "passMark": 80,
    "questionsPerAttempt": 2,
    "questions": [
        {"id": "m1-q0", "prompt": "Question 0? (Choose one.)",
         "options": ["Right", "Wrong", "Other", "Another"], "correct": 0,
         "module": "Getting Started"},
        {"id": "m1-q1", "prompt": "Question 1? (Choose one.)",
         "options": ["Right", "Wrong", "Other", "Another"], "correct": 0,
         "module": "Getting Started"},
    ],
}


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "sync.db"


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


def test_a_plan_reports_the_pool_and_writes_nothing(client, course, db_path):
    r = client.post("/api/courses/sync/plan")
    assert r.status_code == 200
    body = r.json()
    assert body["totalNew"] == 2
    assert body["token"]
    assert [c["slug"] for c in body["courses"]] == ["demo-course"]

    database = ExamBankDB(db_path)
    try:
        assert database.conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 0
    finally:
        database.close()


def test_a_sync_without_a_token_is_refused(client, course):
    r = client.post("/api/courses/sync", json={})
    assert r.status_code == 400
    assert "plan" in r.json()["detail"].lower()


def test_a_sync_with_a_stale_token_is_a_conflict(client, course):
    token = client.post("/api/courses/sync/plan").json()["token"]

    exam = course / "exam.json"
    data = json.loads(exam.read_text(encoding="utf-8"))
    data["questions"].append({
        "id": "m1-q2", "prompt": "Question 2? (Choose one.)",
        "options": ["Right", "Wrong", "Other", "Another"], "correct": 0})
    exam.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")

    r = client.post("/api/courses/sync", json={"token": token})
    assert r.status_code == 409, (
        "the request was well formed and correct when it was composed; the "
        "world moved, which is a conflict rather than a bad request"
    )


def test_a_sync_adopts_the_pool(client, course, db_path):
    token = client.post("/api/courses/sync/plan").json()["token"]
    r = client.post("/api/courses/sync", json={"token": token})
    assert r.status_code == 200
    assert r.json()["added"] == 2

    database = ExamBankDB(db_path)
    try:
        ids = {row[0] for row in database.conn.execute("SELECT id FROM questions")}
        assert ids == {"m1-q0", "m1-q1"}
    finally:
        database.close()


# --- the first-run adopt -------------------------------------------------
#
# This is the half that runs with nobody watching, on a machine where the app
# has just been installed. It is also the only place in the app that writes
# without being asked, so what it refuses to do matters more than what it does.


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Point the app's module-level DB_PATH at a scratch file.

    The first-run adopt opens its own connection from `config.DB_PATH` rather
    than taking one from a request, so a dependency override cannot reach it.
    """
    path = tmp_path / "first-run.db"
    import exam_bank.utils.config as cfg
    monkeypatch.setattr(cfg, "DB_PATH", path)
    return path


def test_a_brand_new_bank_fills_itself_from_the_courses(course, isolated_db):
    _adopt_courses_on_first_run()

    database = ExamBankDB(isolated_db)
    try:
        ids = {row[0] for row in database.conn.execute("SELECT id FROM questions")}
        assert ids == {"m1-q0", "m1-q1"}
        certs = database.list_certifications()
        assert [c.source_ref for c in certs] == ["demo-course"]
    finally:
        database.close()


def test_a_bank_with_anything_in_it_is_left_alone(course, isolated_db):
    """The safety argument for writing unasked is that an empty bank has
    nothing to lose. It stops being true the moment the bank has content."""
    database = ExamBankDB(isolated_db)
    try:
        database.save_certification(Certification(
            name="Mine", source_type="pcm", source_ref="demo-course"))
    finally:
        database.close()

    _adopt_courses_on_first_run()

    database = ExamBankDB(isolated_db)
    try:
        assert database.conn.execute(
            "SELECT COUNT(*) FROM questions").fetchone()[0] == 0, (
            "a bank somebody has started arranging must not be written into "
            "without being asked"
        )
    finally:
        database.close()


def test_no_courses_directory_is_not_a_failure(isolated_db, monkeypatch):
    """An authoring tool that will not start because it could not read
    somebody else's courses directory is worse than one that starts empty."""
    from exam_bank.utils.config import config
    monkeypatch.setattr(config, "pcm_courses_dir", r"C:\nowhere\at\all")

    _adopt_courses_on_first_run()  # must not raise

    database = ExamBankDB(isolated_db)
    try:
        assert database.conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 0
    finally:
        database.close()
