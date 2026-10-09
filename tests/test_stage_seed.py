"""desktop/scripts/stage-seed.mjs - what a seeded installer carries.

Run for real under Node against a small Content Manager built in a temp
directory. The distribution repo is public and an installer is a second
way out for a file git was told to ignore, so what these pin hardest is
what must NOT ship: lab files, anything git does not track, secret-shaped
names.

The last test stages a real checkout, when this machine has one, and feeds
the result to the bank's own course reader.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from exam_bank.core.pcm_reader import list_pcm_courses, list_pcm_labs, load_pcm_course

SCRIPT = Path(__file__).resolve().parents[1] / "desktop" / "scripts" / "stage-seed.mjs"
NODE = shutil.which("node")
GIT = shutil.which("git")

pytestmark = pytest.mark.skipif(NODE is None, reason="the staging script runs under Node")


def write(path: Path, text="x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_pcm(root: Path, *, git: bool) -> Path:
    write(root / "package.json", json.dumps({"name": "pcm", "version": "9.9.9"}))
    for cid in ("alpha", "beta", "_template"):
        c = root / "courses" / cid
        write(c / "course.json", json.dumps({"id": cid, "title": cid}))
        write(c / "SUMMARY.md", "# toc\n")
        write(c / "exam.json", "{}")
        write(c / "glossary.json", "{}")
        write(c / "01-lab" / "manifest.json", "{}")
        write(c / "01-lab" / "guide.md", "# lab\n")
        write(c / "01-lab" / "files" / "payload.json", '{"lab":"data"}')   # lab payload
        write(c / "01-lab" / "files" / "notes.md", "lab notes\n")
        write(c / "_assets" / "images" / "shot.png", "png")
        write(c / "01-lab" / "demo.ktr", "<transformation/>")
    if git:
        write(root / ".gitignore", ".env*\n")
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        subprocess.run([GIT, "init", "-q", str(root)], check=True)
        subprocess.run([GIT, "-C", str(root), "add", "-A"], check=True)
        subprocess.run([GIT, "-C", str(root), "commit", "-q", "-m", "init"], check=True, env=env)
    # On disk but never to ship.
    write(root / "courses" / "alpha" / ".env", "TOKEN=secret\n")
    write(root / "courses" / "alpha" / "01-lab" / "config.json", '{"password": "hunter2"}')  # untracked, not secret-shaped
    write(root / "courses" / "alpha" / "deploy.key", "secret\n")
    return root


def stage(pcm: Path, out: Path, *extra):
    return subprocess.run([NODE, str(SCRIPT), "--pcm", str(pcm), "--out", str(out), *extra],
                          capture_output=True, text=True)


def files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def pcm_git(tmp_path):
    if GIT is None:
        pytest.skip("needs git")
    return make_pcm(tmp_path / "pcm", git=True)


def test_only_what_the_bank_reads_ships(pcm_git, tmp_path):
    out = tmp_path / "seed"
    res = stage(pcm_git, out)
    assert res.returncode == 0, res.stderr
    got = files(out / "courses")
    for want in ("alpha/course.json", "alpha/SUMMARY.md", "alpha/exam.json", "alpha/glossary.json",
                 "alpha/01-lab/manifest.json", "alpha/01-lab/guide.md"):
        assert want in got, want
    # lab payload, images and anything that is not Markdown or JSON stay behind
    for nope in ("alpha/01-lab/files/payload.json", "alpha/01-lab/files/notes.md",
                 "alpha/_assets/images/shot.png", "alpha/01-lab/demo.ktr"):
        assert nope not in got, nope


def test_only_files_git_tracks_ship(pcm_git, tmp_path):
    out = tmp_path / "seed"
    assert stage(pcm_git, out).returncode == 0
    got = files(out / "courses")
    assert "alpha/.env" not in got
    assert "alpha/deploy.key" not in got
    # .json, so the file-type rule would let it through: only git's answer keeps it out.
    assert "alpha/01-lab/config.json" not in got


def test_outside_git_the_file_type_rule_and_skip_names_apply(tmp_path):
    pcm = make_pcm(tmp_path / "pcm", git=False)
    out = tmp_path / "seed"
    res = stage(pcm, out)
    assert res.returncode == 0, res.stderr
    assert "not a git checkout" in res.stdout
    got = files(out / "courses")
    assert "alpha/01-lab/guide.md" in got
    assert "alpha/.env" not in got
    assert "alpha/deploy.key" not in got
    assert "alpha/01-lab/files/payload.json" not in got


def test_underscore_courses_are_authoring_internal(pcm_git, tmp_path):
    out = tmp_path / "seed"
    assert stage(pcm_git, out).returncode == 0
    manifest = json.loads((out / "manifest.json").read_text())
    assert [c["id"] for c in manifest["courses"]] == ["alpha", "beta"]
    assert manifest["pcmVersion"] == "9.9.9"
    assert not any(f.startswith("_template/") for f in files(out / "courses"))


def test_a_subset_and_the_environment_both_pick_courses(pcm_git, tmp_path, monkeypatch):
    out = tmp_path / "seed"
    assert stage(pcm_git, out, "--courses", "beta").returncode == 0
    assert {f.split("/")[0] for f in files(out / "courses")} == {"beta"}

    monkeypatch.setenv("PEB_SEED_COURSES", "alpha")
    assert stage(pcm_git, out).returncode == 0
    assert {f.split("/")[0] for f in files(out / "courses")} == {"alpha"}


def test_an_unknown_course_is_an_error_naming_the_ones_there_are(pcm_git, tmp_path):
    res = stage(pcm_git, tmp_path / "seed", "--courses", "nope")
    assert res.returncode != 0
    assert "no course" in res.stderr and "alpha" in res.stderr


def test_it_will_not_delete_a_directory_that_is_not_a_seed(pcm_git, tmp_path):
    out = tmp_path / "precious"
    write(out / "thesis.docx", "irreplaceable")
    assert stage(pcm_git, out).returncode != 0
    assert (out / "thesis.docx").read_text() == "irreplaceable"


def test_it_will_not_stage_into_or_around_the_checkout(pcm_git, tmp_path):
    assert stage(pcm_git, pcm_git / "seed").returncode != 0
    assert stage(pcm_git, tmp_path).returncode != 0
    assert (pcm_git / "courses" / "alpha" / "course.json").is_file()


def test_the_manifest_id_tracks_content(pcm_git, tmp_path):
    out = tmp_path / "seed"
    assert stage(pcm_git, out).returncode == 0
    first = json.loads((out / "manifest.json").read_text())["id"]
    assert stage(pcm_git, out).returncode == 0
    assert json.loads((out / "manifest.json").read_text())["id"] == first
    write(pcm_git / "courses" / "alpha" / "01-lab" / "guide.md", "# changed\n")
    assert stage(pcm_git, out).returncode == 0
    assert json.loads((out / "manifest.json").read_text())["id"] != first


def test_the_staged_seed_is_what_the_bank_lays_out_and_reads(pcm_git, tmp_path):
    from exam_bank.utils import seed

    out = tmp_path / "seed"
    assert stage(pcm_git, out).returncode == 0
    os.environ["PEB_SEED_DIR"] = str(out)
    try:
        got = seed.ensure(tmp_path / "state", tmp_path / "app")
    finally:
        del os.environ["PEB_SEED_DIR"]
    assert got is not None
    assert [c["slug"] for c in list_pcm_courses(got)] == ["alpha", "beta"]
    assert [lab["slug"] for lab in list_pcm_labs(got, "alpha")] == ["01-lab"]


def real_pcm():
    for candidate in (os.environ.get("PCM_REPO"), str(Path(__file__).resolve().parents[2] / "Pentaho-Content-Manager")):
        if candidate and (Path(candidate) / "courses").is_dir():
            return Path(candidate)
    return None


@pytest.mark.skipif(real_pcm() is None, reason="needs a Content Manager checkout")
def test_a_real_checkout_stages_small_and_the_bank_can_read_every_course(tmp_path):
    from exam_bank.utils import seed

    pcm = real_pcm()
    out = tmp_path / "seed"
    res = stage(pcm, out)
    assert res.returncode == 0, res.stdout + res.stderr
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    assert size < 25 * 1024 * 1024, f"seed is {size / 1048576:.1f} MB - something heavy got through"
    assert not any(f.endswith((".png", ".ktr", ".db", ".zip")) for f in files(out))

    os.environ["PEB_SEED_DIR"] = str(out)
    try:
        got = seed.ensure(tmp_path / "state", tmp_path / "app")
    finally:
        del os.environ["PEB_SEED_DIR"]
    courses = list_pcm_courses(got)
    assert courses, "no courses read back"
    # Every staged course has labs the bank can list, and the source it
    # generates questions from reads back out of the seeded copy - the same
    # sections as out of the checkout it was staged from.
    for course in courses:
        assert list_pcm_labs(got, course["slug"]), course["slug"]
        assert len(load_pcm_course(got, course["slug"])) == len(load_pcm_course(pcm / "courses", course["slug"])), course["slug"]
