"""Tests for the generation and export routes.

No test here reaches a model. Generation is stubbed at
``question_generation.generate_questions_batch``, so what is exercised is the
job machinery, the validation in front of it, and the commit step.
"""

import json
import time

import pytest
from fastapi.testclient import TestClient

from exam_bank.api import deps, jobs
from exam_bank.api.app import app
from exam_bank.api.routers import generation as generation_router
from exam_bank.core.bank import Certification, Question, ExamBankDB
from exam_bank.utils.config import config


def _wait(client, job_id, *, timeout=5.0):
    """Poll until the job leaves `running`. The worker is a real thread, so a
    test must wait for it rather than assume it has finished."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] != jobs.RUNNING:
            return body
        time.sleep(0.02)
    pytest.fail(f"job {job_id} did not finish within {timeout}s")


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "gen.db"


@pytest.fixture
def db(db_path):
    database = ExamBankDB(db_path)
    yield database
    database.close()


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
    root = tmp_path / "courses"
    lab = root / "demo-course" / "01-lab"
    lab.mkdir(parents=True)
    (root / "demo-course" / "course.json").write_text(
        json.dumps({"title": "Demo"}), encoding="utf-8")
    (lab / "guide.md").write_text(
        "## Section One\n\n" + ("Prose enough to ground a question on. " * 5)
        + "\n\n## Section Two\n\n" + ("More prose for the second section. " * 5),
        encoding="utf-8")
    monkeypatch.setattr(config, "pcm_courses_dir", str(root))
    return root


@pytest.fixture
def fake_generator(monkeypatch):
    """Stand in for the model. Records the call and returns two questions."""
    seen = {}

    def fake_batch(**kwargs):
        seen.update(kwargs)
        callback = kwargs.get("progress_callback")
        if callback:
            callback(1, 2, "working")
        return [
            Question(id="gen-1", stem="Generated one?", key="A", distractors=["B"]),
            Question(id="gen-2", stem="Generated two?", key="A", distractors=["B"]),
        ]

    monkeypatch.setattr(generation_router, "generate_questions_batch", fake_batch)
    return seen


class TestGenerationValidation:
    """Everything checkable is checked before a job starts, so the author sees
    a mistake at once instead of a job that starts and then fails."""

    def test_unknown_course_is_rejected_up_front(self, client, course):
        response = client.post("/api/generate", json={"course_slug": "nope"})
        assert response.status_code == 404
        assert "demo-course" in response.json()["detail"]

    def test_unknown_difficulty_is_rejected(self, client, course):
        response = client.post("/api/generate",
                               json={"course_slug": "demo-course", "difficulty": "Spicy"})
        assert response.status_code == 400

    def test_unknown_bloom_level_is_rejected(self, client, course):
        response = client.post("/api/generate",
                               json={"course_slug": "demo-course",
                                     "bloom_levels": ["Apply", "Telepathy"]})
        assert response.status_code == 400
        assert "Telepathy" in response.json()["detail"]

    def test_a_course_with_no_usable_prose_is_422(self, client, tmp_path, monkeypatch):
        root = tmp_path / "thin"
        lab = root / "thin-course" / "01-lab"
        lab.mkdir(parents=True)
        (root / "thin-course" / "course.json").write_text("{}", encoding="utf-8")
        (lab / "guide.md").write_text("## Tiny\n\ntoo short", encoding="utf-8")
        monkeypatch.setattr(config, "pcm_courses_dir", str(root))

        response = client.post("/api/generate", json={"course_slug": "thin-course"})
        assert response.status_code == 422
        assert "prose" in response.json()["detail"]

    def test_no_courses_directory_is_409(self, client, monkeypatch):
        monkeypatch.setattr(config, "pcm_courses_dir", "")
        assert client.post("/api/generate",
                           json={"course_slug": "x"}).status_code == 409


class TestGenerationJob:
    def test_a_job_starts_and_finishes(self, client, course, fake_generator):
        started = client.post("/api/generate",
                              json={"course_slug": "demo-course", "total": 2})
        assert started.status_code == 202
        body = started.json()
        assert body["sections"] == 2

        finished = _wait(client, body["jobId"])
        assert finished["status"] == jobs.DONE
        assert finished["count"] == 2
        assert finished["result"][0]["stem"] == "Generated one?"

    def test_the_request_reaches_the_generator(self, client, course, fake_generator):
        client.post("/api/generate", json={
            "course_slug": "demo-course", "total": 7, "difficulty": "Hard",
            "bloom_levels": ["Analyze"], "num_keys": 2, "num_distractors": 4,
            "model": "qwen2.5:7b", "shuffle_formats": True,
        })
        # The job thread may not have run yet; wait for the call to land.
        deadline = time.monotonic() + 5
        while "target_total" not in fake_generator and time.monotonic() < deadline:
            time.sleep(0.02)

        assert fake_generator["target_total"] == 7
        assert fake_generator["difficulty"] == "Hard"
        assert fake_generator["bloom_level"] == ["Analyze"]
        assert fake_generator["num_keys"] == 2
        assert fake_generator["model"] == "qwen2.5:7b"
        assert fake_generator["shuffle_formats"] is True
        assert fake_generator["source_file"] == "pcm:demo-course"

    def test_progress_is_reported(self, client, course, fake_generator):
        body = client.post("/api/generate", json={"course_slug": "demo-course"}).json()
        finished = _wait(client, body["jobId"])
        assert finished["progress"]["total"] == 2

    def test_a_failing_generator_surfaces_as_an_error_job(self, client, course, monkeypatch):
        def boom(**kwargs):
            raise RuntimeError("model went away")

        monkeypatch.setattr(generation_router, "generate_questions_batch", boom)
        body = client.post("/api/generate", json={"course_slug": "demo-course"}).json()
        finished = _wait(client, body["jobId"])
        assert finished["status"] == jobs.ERROR
        assert "model went away" in finished["error"]

    def test_an_unknown_job_is_404(self, client):
        assert client.get("/api/jobs/not-a-job").status_code == 404

    def test_the_job_list_omits_results(self, client, course, fake_generator):
        body = client.post("/api/generate", json={"course_slug": "demo-course"}).json()
        _wait(client, body["jobId"])
        listed = [j for j in client.get("/api/jobs").json() if j["id"] == body["jobId"]]
        assert listed and listed[0]["count"] == 2
        assert listed[0]["result"] == [], "the list is a status view, not a payload"


class TestCommit:
    """Generating must not save. A model's output is a proposal."""

    def test_nothing_is_saved_until_commit(self, client, course, fake_generator):
        body = client.post("/api/generate", json={"course_slug": "demo-course"}).json()
        _wait(client, body["jobId"])
        assert client.get("/api/questions").json()["total"] == 0

    def test_commit_saves_all_by_default(self, client, course, fake_generator):
        body = client.post("/api/generate", json={"course_slug": "demo-course"}).json()
        _wait(client, body["jobId"])

        response = client.post(f"/api/jobs/{body['jobId']}/commit", json={})
        assert response.json()["saved"] == 2
        assert client.get("/api/questions").json()["total"] == 2

    def test_commit_can_keep_a_subset(self, client, course, fake_generator):
        body = client.post("/api/generate", json={"course_slug": "demo-course"}).json()
        _wait(client, body["jobId"])

        client.post(f"/api/jobs/{body['jobId']}/commit",
                    json={"question_ids": ["gen-2"]})
        kept = client.get("/api/questions").json()
        assert kept["total"] == 1
        assert kept["items"][0]["id"] == "gen-2"

    def test_commit_assigns_the_certification(self, client, course, fake_generator, db):
        cert = Certification(name="Demo")
        db.save_certification(cert)
        body = client.post("/api/generate", json={"course_slug": "demo-course"}).json()
        _wait(client, body["jobId"])

        client.post(f"/api/jobs/{body['jobId']}/commit",
                    json={"certification_id": cert.id})
        items = client.get("/api/questions").json()["items"]
        assert all(q["certification_id"] == cert.id for q in items)

    def test_commit_of_an_unknown_question_is_404(self, client, course, fake_generator):
        body = client.post("/api/generate", json={"course_slug": "demo-course"}).json()
        _wait(client, body["jobId"])
        response = client.post(f"/api/jobs/{body['jobId']}/commit",
                               json={"question_ids": ["never-generated"]})
        assert response.status_code == 404

    def test_a_failed_job_cannot_be_committed(self, client, course, monkeypatch):
        monkeypatch.setattr(generation_router, "generate_questions_batch",
                            lambda **kw: (_ for _ in ()).throw(RuntimeError("nope")))
        body = client.post("/api/generate", json={"course_slug": "demo-course"}).json()
        _wait(client, body["jobId"])
        assert client.post(f"/api/jobs/{body['jobId']}/commit", json={}).status_code == 409


class TestExport:
    @pytest.fixture
    def stocked(self, db):
        cert = Certification(name="DI", source_type="pcm", source_ref="di")
        db.save_certification(cert)
        for i in range(3):
            db.save(Question(
                id=f"e-q{i}", stem=f"Exported {i}? (Choose one.)", key="Right",
                distractors=["Wrong", "Also wrong"], topic="Topic",
                certification_id=cert.id, pool_order=2 - i, status="draft",
            ))
        return cert

    @pytest.mark.parametrize("fmt,marker", [
        ("csv", b"Stem"), ("json", b"stem"), ("qti", b"assessment"),
        ("moodle", b"quiz"), ("text", b"Exported"),
    ])
    def test_each_format_downloads(self, client, stocked, fmt, marker):
        response = client.get(f"/api/export/{fmt}")
        assert response.status_code == 200
        assert marker.lower() in response.content.lower()

    def test_an_unknown_format_lists_the_real_ones(self, client, stocked):
        response = client.get("/api/export/parquet")
        assert response.status_code == 404
        assert "csv" in response.json()["detail"]

    def test_export_honours_the_filters(self, client, stocked, db):
        db.save(Question(id="other", stem="Different topic?", key="k",
                         distractors=["d"], topic="Elsewhere"))
        body = client.get("/api/export/json", params={"topic": "Elsewhere"}).content
        assert b"Different topic?" in body
        assert b"Exported 0?" not in body

    def test_an_empty_selection_is_404_not_an_empty_file(self, client, stocked):
        assert client.get("/api/export/csv",
                          params={"topic": "nothing-matches"}).status_code == 404

    def test_exam_json_is_written_in_the_authored_order(self, client, stocked):
        """pool_order was seeded reversed; the export must restore it."""
        response = client.get("/api/export-exam/json",
                              params={"certification_id": stocked.id})
        assert response.status_code == 200
        ids = [q["id"] for q in json.loads(response.content)["questions"]]
        assert ids == ["e-q2", "e-q1", "e-q0"]

    def test_exam_json_refuses_to_span_two_courses(self, client, stocked, db):
        """Each course's pool_order starts at 0, so two pools in one file
        interleave rather than concatenate — a plausible-looking exam in an
        order nobody chose. It has to be refused, not merged."""
        other = Certification(name="Another Course")
        db.save_certification(other)
        db.save(Question(id="o-q0", stem="Other course?", key="k",
                         distractors=["d"], certification_id=other.id, pool_order=0))

        response = client.get("/api/export-exam/json")
        assert response.status_code == 400
        assert "one course" in response.json()["detail"]
        assert "Another Course" in response.json()["detail"]

    def test_exam_json_is_fine_when_scoped_to_one_course(self, client, stocked, db):
        other = Certification(name="Another Course")
        db.save_certification(other)
        db.save(Question(id="o-q0", stem="Other course?", key="k",
                         distractors=["d"], certification_id=other.id, pool_order=0))

        response = client.get("/api/export-exam/json",
                              params={"certification_id": stocked.id})
        assert response.status_code == 200
        assert len(json.loads(response.content)["questions"]) == 3

    def test_exam_json_rejects_more_per_attempt_than_exist(self, client, stocked):
        response = client.get("/api/export-exam/json",
                              params={"certification_id": stocked.id,
                                      "questions_per_attempt": 99})
        assert response.status_code == 400

    def test_exam_pdf_downloads(self, client, stocked):
        response = client.get("/api/export-exam/pdf",
                              params={"certification_id": stocked.id})
        assert response.status_code == 200
        assert response.content[:4] == b"%PDF"


def test_no_export_route_writes_into_a_course():
    """Publishing back must merge into the existing exam.json so it cannot
    drop the settings the Content Editor owns (`intake` especially). Until
    that exists, nothing here may take a course as a destination."""
    import inspect

    from exam_bank.api.routers import export as export_module

    source = inspect.getsource(export_module)
    for forbidden in ("pcm_courses_dir", "COURSES_DIR", "courses_dir"):
        assert forbidden not in source, (
            f"export references {forbidden} — it must not be able to target a course"
        )
