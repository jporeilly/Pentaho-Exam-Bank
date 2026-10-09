"""The bundled courses (exam_bank/utils/seed.py) and where they rank.

A seeded installer lets the bank open onto real courses on a machine with no
Content Manager checkout. What these pin is what would hurt an author: that
their exams survive an upgrade, that a real checkout is never shadowed, and
that the bank and the Content Editor read ONE set of courses when both are
seeded rather than two that drift.
"""

import json
from pathlib import Path

import pytest

from exam_bank.core.pcm_reader import list_pcm_courses, list_pcm_labs
from exam_bank.utils import config, seed

from tests.test_api import client, db_path  # noqa: F401  (fixtures)


def make_seed(root: Path, courses=("alpha",), seed_id="one") -> Path:
    """A bundled seed as stage-seed.mjs lays it out."""
    for name in courses:
        course = root / "courses" / name
        (course / "01-intro").mkdir(parents=True, exist_ok=True)
        (course / "course.json").write_text(json.dumps({"id": name, "title": name.title()}))
        (course / "SUMMARY.md").write_text("# toc\n\n## Basics\n\n* [Intro](01-intro/guide.md)\n")
        (course / "01-intro" / "manifest.json").write_text(json.dumps({"title": "Intro", "order": 1}))
        (course / "01-intro" / "guide.md").write_text("# Intro\n\n## Step\n\nDo it.\n")
        (course / "exam.json").write_text(json.dumps({"questions": []}))
    (root / "manifest.json").write_text(json.dumps({"schema": 1, "id": seed_id, "pcmVersion": "0.7.21"}))
    return root


@pytest.fixture
def env(tmp_path, monkeypatch):
    """No real registry, no real Content Editor, no sibling checkout."""
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr(config, "ASSETS_DIR", state)
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path / "Pentaho-Exam-Bank")
    monkeypatch.setattr(config, "_installer_hint", lambda: None)
    monkeypatch.delenv("PCM_REPO", raising=False)
    monkeypatch.delenv("PEB_SEED_DIR", raising=False)
    monkeypatch.setenv("PEB_EDITOR_SEED_DIR", str(tmp_path / "no-editor"))
    return tmp_path


# ── seed.py ─────────────────────────────────────────────────────────

def test_no_seed_is_a_no_op(tmp_path):
    assert seed.seed_dir(tmp_path / "Pentaho-Exam-Bank") is None
    assert seed.ensure(tmp_path / "state", tmp_path / "Pentaho-Exam-Bank") is None


def test_a_checkout_never_mistakes_a_neighbouring_seed_for_its_own(tmp_path):
    # From a checkout the parent folder holds every repo.
    make_seed(tmp_path / "seed")
    assert seed.seed_dir(tmp_path / "Pentaho-Exam-Bank") is None


def test_the_installed_shape_finds_the_seed_beside_app(tmp_path):
    make_seed(tmp_path / "seed")
    assert seed.seed_dir(tmp_path / "app") == tmp_path / "seed"


def test_the_environment_can_name_the_seed(tmp_path, monkeypatch):
    make_seed(tmp_path / "elsewhere")
    monkeypatch.setenv("PEB_SEED_DIR", str(tmp_path / "elsewhere"))
    assert seed.seed_dir(tmp_path / "Pentaho-Exam-Bank") == tmp_path / "elsewhere"


def test_ensure_lays_the_courses_out_under_the_state_dir(tmp_path):
    make_seed(tmp_path / "seed", courses=("alpha", "beta"))
    got = seed.ensure(tmp_path / "state", tmp_path / "app")
    assert got == tmp_path / "state" / "pcm-seed" / "courses"
    assert [c["slug"] for c in list_pcm_courses(got)] == ["alpha", "beta"]
    assert not list(got.rglob("*.partial"))
    # ...and the bank's own reader accepts them: labs, with a guide each.
    assert [lab["slug"] for lab in list_pcm_labs(got, "alpha")] == ["01-intro"]


def test_an_authors_exam_survives_the_next_start_and_an_upgrade(tmp_path):
    make_seed(tmp_path / "seed")
    got = seed.ensure(tmp_path / "state", tmp_path / "app")
    exam = got / "alpha" / "exam.json"
    exam.write_text('{"questions": [{"id": "alpha-m1-q1"}]}')

    seed.ensure(tmp_path / "state", tmp_path / "app")
    assert "alpha-m1-q1" in exam.read_text()

    # A newer installer: the same course changed upstream, plus a new one.
    make_seed(tmp_path / "seed", courses=("alpha", "gamma"), seed_id="two")
    seed.ensure(tmp_path / "state", tmp_path / "app")
    assert "alpha-m1-q1" in exam.read_text()
    assert (got / "gamma" / "course.json").is_file()


def test_a_course_the_new_seed_dropped_is_left_on_disk(tmp_path):
    make_seed(tmp_path / "seed", courses=("alpha", "beta"))
    got = seed.ensure(tmp_path / "state", tmp_path / "app")
    import shutil
    shutil.rmtree(tmp_path / "seed" / "courses" / "beta")
    seed.ensure(tmp_path / "state", tmp_path / "app")
    assert (got / "beta" / "course.json").is_file()


def test_a_failed_copy_returns_none_instead_of_raising(tmp_path, monkeypatch):
    make_seed(tmp_path / "seed")

    def boom(*a, **k):
        raise PermissionError("denied")

    monkeypatch.setattr(seed.shutil, "copytree", boom)
    assert seed.ensure(tmp_path / "state", tmp_path / "app") is None


def test_the_editors_copy_needs_its_marker_and_a_course(tmp_path, monkeypatch):
    root = tmp_path / "pcm-seed"
    monkeypatch.setenv("PEB_EDITOR_SEED_DIR", str(root))
    assert seed.editor_courses_dir() is None                       # nothing there

    (root / "courses" / "alpha").mkdir(parents=True)
    (root / "courses" / "alpha" / "course.json").write_text("{}")
    assert seed.editor_courses_dir() is None                       # a folder, not the editor's

    (root / ".seed-state.json").write_text("{}")
    assert seed.editor_courses_dir() == root / "courses"

    (root / "courses" / "alpha" / "course.json").unlink()
    assert seed.editor_courses_dir() is None                       # nothing worth following


def test_is_seeded_recognises_both_copies_and_nothing_else(tmp_path, monkeypatch):
    own = seed.target_courses_dir(tmp_path / "state")
    own.mkdir(parents=True)
    assert seed.is_seeded(own, tmp_path / "state")
    assert not seed.is_seeded(tmp_path, tmp_path / "state")
    assert not seed.is_seeded("", tmp_path / "state")
    assert not seed.is_seeded(None, tmp_path / "state")

    root = tmp_path / "pcm-seed"
    (root / "courses" / "a").mkdir(parents=True)
    (root / "courses" / "a" / "course.json").write_text("{}")
    (root / ".seed-state.json").write_text("{}")
    monkeypatch.setenv("PEB_EDITOR_SEED_DIR", str(root))
    assert seed.is_seeded(root / "courses", tmp_path / "state")


# ── config.py: where the seed ranks ─────────────────────────────────

def test_the_own_seed_is_used_when_nothing_else_answers(env, monkeypatch):
    make_seed(env / "bundle")
    monkeypatch.setenv("PEB_SEED_DIR", str(env / "bundle"))
    got = config._default_pcm_courses_dir()
    assert got == str(env / "state" / "pcm-seed" / "courses")
    assert (Path(got) / "alpha" / "course.json").is_file()


def test_the_environment_beats_every_seed(env, monkeypatch):
    make_seed(env / "bundle")
    monkeypatch.setenv("PEB_SEED_DIR", str(env / "bundle"))
    repo = env / "mine"
    (repo / "courses" / "c").mkdir(parents=True)
    monkeypatch.setenv("PCM_REPO", str(repo))
    assert config._default_pcm_courses_dir() == str(repo / "courses")
    assert not (env / "state" / "pcm-seed").exists()   # and nothing was laid out


def test_the_installers_hint_beats_every_seed(env, monkeypatch):
    make_seed(env / "bundle")
    monkeypatch.setenv("PEB_SEED_DIR", str(env / "bundle"))
    repo = env / "hinted"
    (repo / "courses" / "c").mkdir(parents=True)
    monkeypatch.setattr(config, "_installer_hint", lambda: repo)
    assert config._default_pcm_courses_dir() == str(repo / "courses")


def test_the_editors_copy_beats_the_banks_own(env, monkeypatch):
    """Two seeded apps must read one set of courses, not two that drift."""
    make_seed(env / "bundle")
    monkeypatch.setenv("PEB_SEED_DIR", str(env / "bundle"))
    editor = env / "editor-pcm-seed"
    (editor / "courses" / "alpha").mkdir(parents=True)
    (editor / "courses" / "alpha" / "course.json").write_text("{}")
    (editor / ".seed-state.json").write_text("{}")
    monkeypatch.setenv("PEB_EDITOR_SEED_DIR", str(editor))
    assert config._default_pcm_courses_dir() == str(editor / "courses")


def test_without_any_seed_nothing_found_is_still_empty(env):
    assert config._default_pcm_courses_dir() == ""


def test_health_says_when_the_courses_are_seeded(env, client, monkeypatch):  # noqa: F811
    make_seed(env / "bundle")
    monkeypatch.setenv("PEB_SEED_DIR", str(env / "bundle"))
    own = config._default_pcm_courses_dir()
    monkeypatch.setattr(config.config, "pcm_courses_dir", own)
    # system.py bound ASSETS_DIR at import, so it is patched where it is used.
    from exam_bank.api.routers import system
    monkeypatch.setattr(system, "ASSETS_DIR", env / "state")
    assert client.get("/api/health").json()["courses"]["seeded"] is True

    monkeypatch.setattr(config.config, "pcm_courses_dir", str(env))
    assert client.get("/api/health").json()["courses"]["seeded"] is False
