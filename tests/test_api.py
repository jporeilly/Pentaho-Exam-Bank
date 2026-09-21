"""Tests for the HTTP layer.

Every test drives the real app through a TestClient against a temporary
database, so what is exercised is the wiring — dependency, serialisation,
status codes — rather than the core logic, which has its own tests.
"""

import json

import pytest
from fastapi.testclient import TestClient

from exam_bank.api import deps
from exam_bank.api.app import app
from exam_bank.core.bank import Certification, Question, ExamBankDB


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "api.db"


@pytest.fixture
def db(db_path):
    """A handle for the test thread, used to seed and to assert directly."""
    database = ExamBankDB(db_path)
    yield database
    database.close()


@pytest.fixture
def client(db_path):
    """The app, wired to the temporary database.

    The override opens its own connection **per request**, exactly as
    ``deps.get_db`` does, because the reason is the same: TestClient runs the
    endpoint on a worker thread and a sqlite3 connection belongs to the thread
    that opened it. Handing the override one shared handle passes a fixture
    that looks reasonable and then fails every request with a
    ``ProgrammingError`` — which is how this was first written.

    It is overridden rather than repointed at a temporary ``DB_PATH`` so that
    a test can never write to the real bank, whatever the config says.
    """

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
def seeded(db):
    cert = Certification(name="DI Practitioner", source_type="pcm",
                         source_ref="developer-di-practitioner")
    db.save_certification(cert)
    for i in range(3):
        db.save(Question(
            id=f"m1-q{i}", stem=f"Question {i}? (Choose one.)", key="Right",
            distractors=["Wrong"], topic="Getting Started",
            certification_id=cert.id, pool_order=i,
        ))
    return cert


class TestSystem:
    def test_version_matches_the_package(self, client):
        from exam_bank import __version__

        assert client.get("/api/version").json() == {"version": __version__}

    def test_health_reports_the_database(self, client, seeded):
        body = client.get("/api/health").json()
        assert body["database"]["questions"] == 3
        assert body["database"]["certifications"] == 1

    def test_health_survives_an_unreachable_model(self, client, monkeypatch):
        """A dead Ollama must not make the app look broken — the bank, import
        and export all work without a model."""
        from exam_bank.core import ollama_client
        from exam_bank.utils.config import config

        monkeypatch.setattr(config, "ai_provider", "ollama")
        monkeypatch.setattr(ollama_client, "list_models", lambda url, **kw: [])
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["provider"]["ok"] is False


class TestQuestions:
    def test_list_returns_items_and_an_unpaged_total(self, client, seeded):
        body = client.get("/api/questions", params={"limit": 2}).json()
        assert len(body["items"]) == 2
        assert body["total"] == 3, "total must ignore the page size"

    def test_list_filters_by_certification(self, client, seeded, db):
        other = Certification(name="Other")
        db.save_certification(other)
        db.save(Question(id="x1", stem="Elsewhere?", key="k",
                         distractors=["d"], certification_id=other.id))

        body = client.get("/api/questions",
                          params={"certification_id": seeded.id}).json()
        assert body["total"] == 3
        assert all(q["certification_id"] == seeded.id for q in body["items"])

    def test_get_one(self, client, seeded):
        body = client.get("/api/questions/m1-q1").json()
        assert body["stem"] == "Question 1? (Choose one.)"
        assert body["pool_order"] == 1

    def test_get_unknown_is_404(self, client, seeded):
        assert client.get("/api/questions/nope").status_code == 404

    def test_update_edits_and_records_history(self, client, seeded):
        response = client.put("/api/questions/m1-q1",
                              json={"stem": "Rewritten?", "editor": "JP"})
        assert response.status_code == 200
        body = response.json()
        assert body["stem"] == "Rewritten?"
        assert body["version_history"], "an edit must be traceable afterwards"
        assert body["version_history"][-1]["editor"] == "JP"

    def test_update_ignores_fields_it_does_not_own(self, client, seeded):
        """A PUT must not be able to rewrite the audit trail or move a
        question between certifications."""
        before = client.get("/api/questions/m1-q1").json()
        client.put("/api/questions/m1-q1",
                   json={"certification_id": "somewhere-else",
                         "status": "approved",
                         "review_history": [{"forged": True}]})
        after = client.get("/api/questions/m1-q1").json()
        assert after["certification_id"] == before["certification_id"]
        assert after["status"] == before["status"]
        assert after["review_history"] == before["review_history"]

    def test_a_question_cannot_be_emptied(self, client, seeded):
        assert client.put("/api/questions/m1-q1", json={"stem": "  "}).status_code == 400

    def test_pool_order_survives_an_edit(self, client, seeded):
        """Publishing back writes the array in pool_order. If an edit reset it,
        the next publish would reorder the course's exam."""
        client.put("/api/questions/m1-q2", json={"stem": "Edited?"})
        assert client.get("/api/questions/m1-q2").json()["pool_order"] == 2

    def test_delete(self, client, seeded):
        assert client.delete("/api/questions/m1-q0").status_code == 200
        assert client.get("/api/questions/m1-q0").status_code == 404


class TestLifecycle:
    def test_a_legal_transition_is_recorded(self, client, seeded):
        response = client.post("/api/questions/m1-q1/status",
                               json={"status": "sme_review", "sme_name": "JP"})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "sme_review"
        assert body["review_history"][-1]["sme_name"] == "JP"

    def test_an_illegal_transition_is_a_conflict_not_a_crash(self, client, seeded):
        """draft cannot go straight to approved; the model knows the legal
        moves and the API must report that as the caller's error."""
        response = client.post("/api/questions/m1-q1/status",
                               json={"status": "approved"})
        assert response.status_code == 409
        assert "Cannot transition" in response.json()["detail"]

    def test_an_unknown_status_is_rejected(self, client, seeded):
        response = client.post("/api/questions/m1-q1/status",
                               json={"status": "banana"})
        assert response.status_code == 400


class TestCertifications:
    def test_list_includes_question_counts(self, client, seeded):
        body = client.get("/api/certifications").json()
        assert body[0]["questionCount"] == 3
        assert body[0]["sourceRef"] == "developer-di-practitioner"

    def test_create(self, client):
        response = client.post("/api/certifications",
                               json={"name": "New Course", "source_ref": "new-course"})
        assert response.status_code == 201
        assert response.json()["name"] == "New Course"

    def test_create_requires_a_name(self, client):
        assert client.post("/api/certifications", json={"name": "   "}).status_code == 400

    def test_deleting_one_that_holds_questions_needs_confirmation(self, client, seeded):
        """Deleting a certification orphans its questions rather than removing
        them — they keep pointing at a row that is gone and vanish from every
        filtered view without being deleted."""
        response = client.delete(f"/api/certifications/{seeded.id}")
        assert response.status_code == 428
        assert "orphaned" in response.json()["detail"]
        assert client.get("/api/certifications").json(), "nothing should have been deleted"

    def test_confirmed_delete_goes_through_and_says_what_it_orphaned(self, client, seeded):
        response = client.delete(f"/api/certifications/{seeded.id}",
                                 params={"confirm": "delete"})
        assert response.status_code == 200
        assert response.json()["orphanedQuestions"] == 3

    def test_an_empty_certification_deletes_without_ceremony(self, client, db):
        cert = Certification(name="Empty")
        db.save_certification(cert)
        assert client.delete(f"/api/certifications/{cert.id}").status_code == 200


class TestCourses:
    @pytest.fixture
    def courses(self, tmp_path, monkeypatch):
        from exam_bank.utils.config import config

        root = tmp_path / "courses"
        course = root / "demo-course"
        (course / "01-first-lab").mkdir(parents=True)
        (course / "course.json").write_text(
            json.dumps({"title": "Demo Course"}), encoding="utf-8")
        (course / "01-first-lab" / "guide.md").write_text(
            "## Opening\n\n" + ("Plenty of prose about the topic. " * 6),
            encoding="utf-8")
        (course / "exam.json").write_text(json.dumps({
            "title": "Demo Exam", "passMark": 80, "questionsPerAttempt": 1,
            "intake": {"optional": True},
            "questions": [{"id": "d-q1", "prompt": "Which?", "options": ["a", "b"],
                           "correct": 0}],
        }), encoding="utf-8")
        monkeypatch.setattr(config, "pcm_courses_dir", str(root))
        return root

    def test_list_courses_reports_pool_size(self, client, courses):
        body = client.get("/api/courses").json()
        assert body == [{"slug": "demo-course", "title": "Demo Course",
                         "hasExam": True, "questionCount": 1}]

    def test_labs(self, client, courses):
        assert client.get("/api/courses/demo-course/labs").json()[0]["slug"] == "01-first-lab"

    def test_sections_are_what_the_generator_would_see(self, client, courses):
        body = client.get("/api/courses/demo-course/sections").json()
        sections = body["sections"]
        assert sections and sections[0]["title"].endswith("Opening")
        assert sections[0]["characters"] > 60

    def test_sections_report_the_context_budget(self, client, courses, monkeypatch):
        from exam_bank.utils.config import config

        monkeypatch.setattr(config, "ollama_num_ctx", 8192)
        body = client.get("/api/courses/demo-course/sections").json()
        assert body["budget"]["numCtx"] == 8192
        assert body["budget"]["chars"] > 0
        assert body["sections"][0]["exceedsContext"] is False

    def test_a_section_too_long_for_the_window_is_flagged(
        self, client, tmp_path, monkeypatch
    ):
        """Ollama truncates an over-long section silently — the questions come
        back thinner than the material deserved with nothing to say why. The
        author has to be able to see it before spending a run."""
        from exam_bank.utils.config import config

        root = tmp_path / "big"
        lab = root / "big-course" / "01-lab"
        lab.mkdir(parents=True)
        (root / "big-course" / "course.json").write_text("{}", encoding="utf-8")
        (lab / "guide.md").write_text(
            "## Enormous\n\n" + ("This section runs on and on. " * 4000), encoding="utf-8")
        monkeypatch.setattr(config, "pcm_courses_dir", str(root))
        monkeypatch.setattr(config, "ollama_num_ctx", 8192)

        body = client.get("/api/courses/big-course/sections").json()
        assert body["sections"][0]["exceedsContext"] is True
        assert body["sections"][0]["characters"] > body["budget"]["chars"]

    def test_nothing_is_flagged_when_no_window_is_configured(
        self, client, courses, monkeypatch
    ):
        """With no num_ctx, Ollama uses the model's own default, which this app
        does not know. Flagging against a made-up number would be worse than
        not flagging."""
        from exam_bank.utils.config import config

        monkeypatch.setattr(config, "ollama_num_ctx", 0)
        body = client.get("/api/courses/demo-course/sections").json()
        assert body["budget"]["chars"] == 0
        assert all(s["exceedsContext"] is False for s in body["sections"])

    def test_exam_reports_settings_and_pool(self, client, courses):
        body = client.get("/api/courses/demo-course/exam").json()
        assert body["exists"] is True
        assert body["questionCount"] == 1
        assert body["passMark"] == 80

    def test_an_unknown_course_names_the_ones_that_exist(self, client, courses):
        """The failure mode this replaces was a silent empty list when a slug
        stopped resolving after the course was renamed."""
        response = client.get("/api/courses/renamed-away/labs")
        assert response.status_code == 404
        assert "demo-course" in response.json()["detail"]

    def test_a_slug_cannot_escape_the_courses_directory(self, client, courses):
        assert client.get("/api/courses/..%2F..%2Fetc/labs").status_code in (404, 400)

    def test_no_courses_directory_is_reported_not_crashed(self, client, monkeypatch):
        from exam_bank.utils.config import config

        monkeypatch.setattr(config, "pcm_courses_dir", "")
        assert client.get("/api/courses").status_code == 409


def test_the_api_never_imports_the_nicegui_layer():
    """Phase 1's exit criterion. The UI is being replaced; if the API grows a
    dependency on it, it cannot be."""
    import ast
    from pathlib import Path

    api = Path(__file__).resolve().parents[1] / "exam_bank" / "api"
    offenders = []
    for path in api.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            if any("gui" in n.split(".") or n == "nicegui" for n in names):
                offenders.append(f"{path.name}: {names}")
    assert not offenders, f"the API imports the UI: {offenders}"
