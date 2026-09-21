"""Tests for the launch handover — PEB_COURSE and PCM_REPO.

The Content Editor spawns this app with a course in mind. Both variables are
hints: the slug is resolved every time it is read, and a disagreement about
which checkout to use is reported rather than silently settled.
"""

import json

import pytest
from fastapi.testclient import TestClient

from exam_bank.api import deps, launch
from exam_bank.api.app import app
from exam_bank.core.bank import ExamBankDB
from exam_bank.utils.config import config


@pytest.fixture
def courses(tmp_path, monkeypatch):
    root = tmp_path / "pcm" / "courses"
    for slug, title in (("pdi-2hr-lab", "PDI in 2 Hours"), ("developer-di-practitioner", "DI")):
        (root / slug).mkdir(parents=True)
        (root / slug / "course.json").write_text(
            json.dumps({"title": title}), encoding="utf-8")
    monkeypatch.setattr(config, "pcm_courses_dir", str(root))
    return root


@pytest.fixture
def clean_env(monkeypatch):
    for name in launch.COURSE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("PCM_REPO", raising=False)


@pytest.fixture
def client(tmp_path):
    def override():
        db = ExamBankDB(tmp_path / "launch.db")
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[deps.get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestTheCourseHandover:
    def test_nothing_handed_over(self, courses, clean_env):
        context = launch.launch_context()
        assert context["course"] == ""
        assert context["courseKnown"] is False

    def test_a_course_that_resolves(self, courses, clean_env, monkeypatch):
        monkeypatch.setenv("PEB_COURSE", "pdi-2hr-lab")
        context = launch.launch_context()
        assert context["course"] == "pdi-2hr-lab"
        assert context["courseKnown"] is True
        assert context["courseTitle"] == "PDI in 2 Hours"

    def test_a_course_that_no_longer_resolves_is_reported_not_guessed(
        self, courses, clean_env, monkeypatch
    ):
        """This is the failure the whole module exists for: a slug that
        stopped resolving after the course was renamed under it. The bank's
        original two certifications died that way, silently."""
        monkeypatch.setenv("PEB_COURSE", "developer-practitioner")  # renamed long ago
        context = launch.launch_context()
        assert context["course"] == "developer-practitioner"
        assert context["courseKnown"] is False, "an unresolvable slug must not look fine"

    def test_whitespace_is_not_a_course(self, courses, clean_env, monkeypatch):
        monkeypatch.setenv("PEB_COURSE", "   ")
        assert launch.launch_context()["course"] == ""

    def test_the_pre_rename_variable_is_still_honoured(
        self, courses, clean_env, monkeypatch
    ):
        """A Content Editor installed before the Exam Bank rename sends
        PQB_COURSE. Ignoring it gives a Questions button that opens on no
        course at all, with nothing on screen to say why."""
        monkeypatch.setenv("PQB_COURSE", "pdi-2hr-lab")
        context = launch.launch_context()
        assert context["course"] == "pdi-2hr-lab"
        assert context["courseKnown"] is True

    def test_the_new_variable_wins_when_both_are_set(
        self, courses, clean_env, monkeypatch
    ):
        monkeypatch.setenv("PEB_COURSE", "pdi-2hr-lab")
        monkeypatch.setenv("PQB_COURSE", "developer-di-practitioner")
        assert launch.launch_context()["course"] == "pdi-2hr-lab"

    def test_an_empty_new_variable_does_not_mask_the_old_one(
        self, courses, clean_env, monkeypatch
    ):
        """An empty PEB_COURSE is not a choice of course; it is no answer.
        Reading it as one would break the very handover it replaces."""
        monkeypatch.setenv("PEB_COURSE", "")
        monkeypatch.setenv("PQB_COURSE", "pdi-2hr-lab")
        assert launch.launch_context()["course"] == "pdi-2hr-lab"

    def test_it_reports_rather_than_raising_with_no_courses_directory(
        self, clean_env, monkeypatch
    ):
        monkeypatch.setattr(config, "pcm_courses_dir", "")
        monkeypatch.setenv("PEB_COURSE", "pdi-2hr-lab")
        context = launch.launch_context()
        assert context["courseKnown"] is False


class TestTheRepoHandover:
    def test_silent_when_the_paths_agree(self, courses, clean_env, monkeypatch):
        monkeypatch.setenv("PCM_REPO", str(courses.parent))
        assert launch.repo_disagreement() is None

    def test_a_trailing_slash_is_not_a_conflict(self, courses, clean_env, monkeypatch):
        monkeypatch.setenv("PCM_REPO", str(courses.parent) + "\\")
        assert launch.repo_disagreement() is None

    def test_a_real_disagreement_names_both_and_says_which_is_used(
        self, courses, clean_env, monkeypatch, tmp_path
    ):
        """Two checkouts on one machine is the case this catches. Editing one
        course's questions while the author believes they are looking at
        another's is the kind of mistake that is only noticed much later."""
        other = tmp_path / "other-pcm"
        (other / "courses").mkdir(parents=True)
        monkeypatch.setenv("PCM_REPO", str(other))

        conflict = launch.repo_disagreement()
        assert conflict is not None
        assert conflict["handedOver"] == str(other / "courses")
        assert conflict["configured"] == str(courses)
        assert conflict["using"] == str(courses), "the bank reads its own configuration"

    def test_silent_when_nothing_was_handed_over(self, courses, clean_env):
        assert launch.repo_disagreement() is None


class TestOverHttp:
    def test_health_carries_the_handover(self, client, courses, clean_env, monkeypatch):
        monkeypatch.setenv("PEB_COURSE", "developer-di-practitioner")
        body = client.get("/api/health").json()
        assert body["launch"]["course"] == "developer-di-practitioner"
        assert body["launch"]["courseKnown"] is True
        assert body["launch"]["courseTitle"] == "DI"

    def test_health_still_works_with_no_handover(self, client, courses, clean_env):
        body = client.get("/api/health").json()
        assert body["launch"]["course"] == ""
        assert body["launch"]["repoDisagreement"] is None

    def test_a_bad_handover_never_breaks_health(self, client, clean_env, monkeypatch):
        """Health is what the UI asks first. If a malformed handover could
        500 it, a bad env var would make the whole app look dead."""
        monkeypatch.setattr(config, "pcm_courses_dir", "")
        monkeypatch.setenv("PEB_COURSE", "anything")
        monkeypatch.setenv("PCM_REPO", "Z:\\does\\not\\exist")
        response = client.get("/api/health")
        assert response.status_code == 200
