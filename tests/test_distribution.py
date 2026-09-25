"""Tests for pushing a published exam to the courses repo.

Real git, real repositories, all local: an authoring repo (the Content
Manager) with a bare remote, and a bare "courses" repo standing in for
Pentaho-Courses. What is asserted is what lands on the REMOTES - which paths
a commit touched and what the files say afterwards - because that is what an
installed app syncs from.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from exam_bank.core import distribution
from exam_bank.core.distribution import DistributionRefused, preflight, release

GIT = distribution.find_git()
pytestmark = pytest.mark.skipif(GIT is None, reason="git is not installed")

PUBLIC_SECRET = "pub-analytics-secret-123"


def git(cwd, *args):
    return subprocess.run([GIT, *args], cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout.strip()


@pytest.fixture(autouse=True)
def identity(monkeypatch):
    for k, v in (("GIT_AUTHOR_NAME", "Test"), ("GIT_AUTHOR_EMAIL", "t@example.com"),
                 ("GIT_COMMITTER_NAME", "Test"), ("GIT_COMMITTER_EMAIL", "t@example.com")):
        monkeypatch.setenv(k, v)


def write_json(path: Path, data, crlf=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2) + "\n"
    path.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))


def bare(path: Path) -> Path:
    git(path.parent, "init", "--quiet", "--bare", "--initial-branch=main", str(path))
    return path


@pytest.fixture
def repos(tmp_path):
    """authoring (clone of authoring.git) and courses.git, both on main."""
    a_remote = bare(tmp_path / "authoring.git")
    authoring = tmp_path / "authoring"
    git(tmp_path, "clone", "--quiet", str(a_remote), str(authoring))
    git(authoring, "checkout", "--quiet", "-b", "main")
    (authoring / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\nNothing yet.\n\n## [0.5.0] - 2026-09-25\n\n- older\n",
        encoding="utf-8")
    write_json(authoring / "courses/lab/course.json",
               {"id": "lab", "title": "The Lab", "version": "0.1.10",
                "analytics": {"apiSecret": PUBLIC_SECRET}, "unpublishedSetting": True}, crlf=True)
    write_json(authoring / "courses/lab/exam.json",
               {"passMark": 80, "questions": [{"id": "q1", "prompt": "Old?"}]})
    write_json(authoring / "courses/other/course.json", {"id": "other", "version": "1.0.0"})
    git(authoring, "add", "-A")
    git(authoring, "commit", "--quiet", "-m", "seed")
    git(authoring, "push", "--quiet", "-u", "origin", "main")

    c_remote = bare(tmp_path / "courses.git")
    seed = tmp_path / "courses-seed"
    git(tmp_path, "clone", "--quiet", str(c_remote), str(seed))
    git(seed, "checkout", "--quiet", "-b", "main")
    write_json(seed / "lab/course.json",
               {"id": "lab", "title": "The Lab (as published)", "version": "0.1.9",
                "analytics": {"apiSecret": PUBLIC_SECRET}})
    write_json(seed / "lab/exam.json", {"passMark": 80, "questions": [{"id": "q1", "prompt": "Old?"}]})
    write_json(seed / "other/course.json", {"id": "other", "version": "1.0.0"})
    git(seed, "add", "-A")
    git(seed, "commit", "--quiet", "-m", "published")
    git(seed, "push", "--quiet", "-u", "origin", "main")
    return {"authoring": authoring, "a_remote": a_remote, "c_remote": c_remote, "tmp": tmp_path}


def pre(r, slug="lab"):
    return preflight(r["authoring"] / "courses", slug, repo_url=str(r["c_remote"]), repo_ref="main", git=GIT)


def publish_new_exam(r, questions=None, extra=None):
    """What the bank's publish does before the push: rewrite exam.json."""
    data = {"passMark": 80, "questions": questions or [{"id": "q1", "prompt": "New?"}]}
    data.update(extra or {})
    write_json(r["authoring"] / "courses/lab/exam.json", data)


def remote_show(remote: Path, ref_path: str) -> str:
    return git(remote.parent, "--git-dir", str(remote), "show", f"main:{ref_path}")


def last_commit_paths(remote: Path) -> set[str]:
    out = git(remote.parent, "--git-dir", str(remote), "show", "--name-only", "--format=", "main")
    return set(out.split())


SUMMARY = {"added": [], "changed": ["q1"], "removed": [], "afterCount": 1}


# ── preflight: refuse before anything is written ────────────────────────────

def test_preflight_names_the_version_it_will_publish(repos):
    p = pre(repos)
    assert (p.version_from, p.version_to) == ("0.1.10", "0.1.11")


def test_preflight_refuses_uncommitted_changes_a_commit_would_sweep_in(repos):
    cj = repos["authoring"] / "courses/lab/course.json"
    cj.write_bytes(cj.read_bytes().replace(b'"The Lab"', b'"Edited in the editor"'))
    with pytest.raises(DistributionRefused, match="uncommitted changes"):
        pre(repos)


def test_preflight_refuses_when_the_repo_is_behind_its_remote(repos, tmp_path):
    other = tmp_path / "someone-else"
    git(tmp_path, "clone", "--quiet", str(repos["a_remote"]), str(other))
    (other / "note.txt").write_text("x", encoding="utf-8")
    git(other, "add", "note.txt")
    git(other, "commit", "--quiet", "-m", "elsewhere")
    git(other, "push", "--quiet")
    with pytest.raises(DistributionRefused, match="behind its remote"):
        pre(repos)


def test_preflight_refuses_a_folder_that_is_not_a_repository(tmp_path):
    write_json(tmp_path / "plain/courses/lab/course.json", {"version": "0.1.0"})
    with pytest.raises(DistributionRefused, match="not a git repository"):
        preflight(tmp_path / "plain/courses", "lab", repo_url="x", repo_ref="main", git=GIT)


# ── release: what lands on the remotes ──────────────────────────────────────

def test_the_push_carries_exactly_the_exam_and_the_version(repos):
    p = pre(repos)
    publish_new_exam(repos)
    result = release(p, "lab", "The Lab", SUMMARY, repos["tmp"] / "cache")

    assert result["authoring"]["pushed"] and result["courses"]["pushed"], result
    assert "error" not in result

    # Authoring: exactly the three files, version bumped, changelog written.
    assert last_commit_paths(repos["a_remote"]) == {
        "courses/lab/exam.json", "courses/lab/course.json", "CHANGELOG.md"}
    authored = json.loads(remote_show(repos["a_remote"], "courses/lab/course.json"))
    assert authored["version"] == "0.1.11"
    changelog = remote_show(repos["a_remote"], "CHANGELOG.md")
    unreleased = changelog.split("## [0.5.0]")[0]
    assert "Nothing yet." not in unreleased
    assert "### Changed" in unreleased and "The Lab exam published from the Exam Bank" in unreleased
    assert "1 question —" in unreleased  # singular
    assert "edited: q1" in unreleased and "0.1.10 → 0.1.11" in unreleased

    # Distribution: exactly the two files; the published course.json changes
    # ONLY its version - its own title stays, the authoring-only setting does
    # not leak in.
    assert last_commit_paths(repos["c_remote"]) == {"lab/exam.json", "lab/course.json"}
    published = json.loads(remote_show(repos["c_remote"], "lab/course.json"))
    assert published == {"id": "lab", "title": "The Lab (as published)", "version": "0.1.11",
                         "analytics": {"apiSecret": PUBLIC_SECRET}}
    assert json.loads(remote_show(repos["c_remote"], "lab/exam.json"))["questions"][0]["prompt"] == "New?"


def test_the_authoring_course_json_keeps_its_line_endings(repos):
    p = pre(repos)
    publish_new_exam(repos)
    release(p, "lab", "The Lab", SUMMARY, repos["tmp"] / "cache")
    raw = (repos["authoring"] / "courses/lab/course.json").read_bytes()
    assert b"\r\n" in raw and b'"version": "0.1.11"' in raw


def test_a_secret_new_to_the_public_repo_stops_everything(repos):
    """Nothing bumped, nothing committed, nothing pushed - on either side."""
    before_a = git(repos["tmp"], "--git-dir", str(repos["a_remote"]), "rev-parse", "main")
    before_c = git(repos["tmp"], "--git-dir", str(repos["c_remote"]), "rev-parse", "main")
    p = pre(repos)
    publish_new_exam(repos, extra={"webhookSecret": "brand-new-secret-value"})
    with pytest.raises(DistributionRefused, match="webhookSecret"):
        release(p, "lab", "The Lab", SUMMARY, repos["tmp"] / "cache")
    assert git(repos["tmp"], "--git-dir", str(repos["a_remote"]), "rev-parse", "main") == before_a
    assert git(repos["tmp"], "--git-dir", str(repos["c_remote"]), "rev-parse", "main") == before_c
    course = json.loads((repos["authoring"] / "courses/lab/course.json").read_text(encoding="utf-8"))
    assert course["version"] == "0.1.10"
    assert "Nothing yet." in (repos["authoring"] / "CHANGELOG.md").read_text(encoding="utf-8")


def test_a_secret_already_public_is_allowed(repos):
    p = pre(repos)
    publish_new_exam(repos, extra={"apiSecret": PUBLIC_SECRET})
    result = release(p, "lab", "The Lab", SUMMARY, repos["tmp"] / "cache")
    assert result["courses"]["pushed"]


def test_a_course_never_published_is_refused_before_anything_changes(repos):
    write_json(repos["authoring"] / "courses/fresh/course.json", {"id": "fresh", "version": "0.1.0"})
    write_json(repos["authoring"] / "courses/fresh/exam.json", {"questions": []})
    git(repos["authoring"], "add", "-A")
    git(repos["authoring"], "commit", "--quiet", "-m", "fresh")
    git(repos["authoring"], "push", "--quiet")
    p = pre(repos, "fresh")
    with pytest.raises(DistributionRefused, match="never been published"):
        release(p, "fresh", "Fresh", SUMMARY, repos["tmp"] / "cache")
    assert json.loads((repos["authoring"] / "courses/fresh/course.json").read_text())["version"] == "0.1.0"


def test_staging_outside_the_exam_stops_the_push(repos, monkeypatch):
    """The guard against a partial clone recording other courses as deleted."""
    real = distribution._run

    def run(git_, args, cwd):
        out = real(git_, args, cwd)
        if args[:3] == ["diff", "--cached", "--name-only"]:
            return out + "\nother/course.json"
        return out

    monkeypatch.setattr(distribution, "_run", run)
    p = pre(repos)
    publish_new_exam(repos)
    with pytest.raises(DistributionRefused, match="outside this course's exam"):
        release(p, "lab", "The Lab", SUMMARY, repos["tmp"] / "cache")


# ── the changelog line ──────────────────────────────────────────────────────

@pytest.mark.parametrize("unreleased, expect_before", [
    ("## [Unreleased]\n\nNothing yet.\n", None),
    ("## [Unreleased]\n\n### Changed\n\n- earlier change\n", "- earlier change"),
    ("## [Unreleased]\n\n### Fixed\n\n- a fix\n", "### Fixed"),
])
def test_the_line_goes_at_the_top_of_unreleased_changed(tmp_path, unreleased, expect_before):
    path = tmp_path / "CHANGELOG.md"
    path.write_text(f"# Changelog\n\n{unreleased}\n## [1.0.0] - x\n\n- old\n", encoding="utf-8")
    distribution._add_changelog_line(path, "- NEW LINE")
    text = path.read_text(encoding="utf-8")
    section = text.split("## [1.0.0]")[0]
    assert section.count("### Changed") == 1
    assert "- NEW LINE" in section and "Nothing yet." not in section
    if expect_before:
        assert section.index("- NEW LINE") < section.index(expect_before)
    assert "## [1.0.0] - x\n\n- old\n" in text


# ── through the HTTP layer ──────────────────────────────────────────────────

@pytest.fixture
def client(repos, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from exam_bank.api import deps
    from exam_bank.api.app import app
    from exam_bank.core.bank import Certification, ExamBankDB, Question
    from exam_bank.utils import config as config_module

    monkeypatch.setattr(config_module.config, "pcm_courses_dir", str(repos["authoring"] / "courses"))
    monkeypatch.setattr(config_module.config, "courses_repo_url", str(repos["c_remote"]))
    monkeypatch.setattr(config_module.config, "courses_repo_ref", "main")
    import exam_bank.api.routers.courses as courses_router
    monkeypatch.setattr(courses_router, "ASSETS_DIR", tmp_path / "state")

    db_path = tmp_path / "bank.db"
    seed = ExamBankDB(db_path)
    cert = Certification(name="The Lab", source_type="pcm", source_ref="lab")
    seed.save_certification(cert)
    seed.save(Question(id="q1", stem="Which step previews rows?", key="Preview",
                       distractors=["Run", "Debug", "Export"], certification_id=cert.id,
                       status="approved", scenario="You are building a transformation."))
    seed.close()

    def override():
        database = ExamBankDB(db_path)
        try:
            yield database
        finally:
            database.close()

    app.dependency_overrides[deps.get_db] = override
    yield TestClient(app), cert.id
    app.dependency_overrides.clear()


def test_the_plan_says_whether_and_to_which_version_it_would_push(client):
    http, cert_id = client
    plan = http.post("/api/courses/lab/exam/questions/plan",
                     json={"certification_id": cert_id, "status": "approved"}).json()
    assert plan["push"]["available"] is True
    assert (plan["push"]["versionFrom"], plan["push"]["versionTo"]) == ("0.1.10", "0.1.11")


def test_publish_with_push_writes_the_course_and_both_repos(client, repos):
    http, cert_id = client
    plan = http.post("/api/courses/lab/exam/questions/plan",
                     json={"certification_id": cert_id, "status": "approved"}).json()
    done = http.post("/api/courses/lab/exam/questions",
                     json={"certification_id": cert_id, "status": "approved",
                           "expect_sha": plan["sourceSha"], "push": True}).json()
    assert done["written"] is True
    assert done["push"]["authoring"]["pushed"] and done["push"]["courses"]["pushed"], done["push"]
    published = json.loads(remote_show(repos["c_remote"], "lab/exam.json"))
    assert published["questions"][0]["prompt"] == "Which step previews rows?"
    assert json.loads(remote_show(repos["c_remote"], "lab/course.json"))["version"] == "0.1.11"


def test_a_push_that_cannot_happen_is_refused_before_the_file_is_written(client, repos):
    http, cert_id = client
    cj = repos["authoring"] / "courses/lab/course.json"
    cj.write_bytes(cj.read_bytes().replace(b'"The Lab"', b'"Mid-edit"'))
    exam_before = (repos["authoring"] / "courses/lab/exam.json").read_bytes()
    plan = http.post("/api/courses/lab/exam/questions/plan",
                     json={"certification_id": cert_id, "status": "approved"}).json()
    assert plan["push"]["available"] is False and "uncommitted" in plan["push"]["reason"]
    r = http.post("/api/courses/lab/exam/questions",
                  json={"certification_id": cert_id, "status": "approved",
                        "expect_sha": plan["sourceSha"], "push": True})
    assert r.status_code == 409
    assert (repos["authoring"] / "courses/lab/exam.json").read_bytes() == exam_before
