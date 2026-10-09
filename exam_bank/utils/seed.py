"""Courses baked into the installer, for a machine with no Content Manager.

The bank reads a Content Manager course (course.json, the lab guides) and
writes its `exam.json` back. A clean laptop has no checkout, so a plain
install opens with every pane empty and a Settings field asking for a
folder that does not exist.

A **seeded** installer (`npm run dist:seeded`, built from
`desktop/scripts/stage-seed.mjs`) carries the text of some courses:

    <install>/seed/manifest.json
    <install>/seed/courses/<id>/course.json, SUMMARY.md, exam.json, glossary.json,
                                <lab>/manifest.json, <lab>/guide.md

`ensure()` lays that out once under the state directory, because the
install tree is read-only and the bank writes `exam.json` into the course.

Rules, matching the Content Editor's own seeded installer:

1. **Lowest priority.** `config._default_pcm_courses_dir` asks this only
   after `PCM_REPO`, a recorded installer hint and the editor's seeded
   copy, so a real checkout always wins. The path is not persisted by this
   module; see the note in config.py about what a settings save pins.
2. **Additive.** A course is copied only if missing. An author's exams
   survive every upgrade and nothing is ever deleted.
3. **Never raises.** `config.py` runs this at import. A failed copy
   returns None and the app falls through to "not configured", which the
   UI already reports.

**Shared with the Content Editor when both are seeded.** The editor lays
its own copy out at `%APPDATA%\\com.pentaho.content-editor\\pcm-seed`. If
the bank used a separate copy, an author would edit labs in one place and
generate exam questions from another's stale text, so the bank prefers the
editor's copy whenever it exists (`editor_courses_dir`).

What a seeded copy cannot do: *Publish and push* commits in the authoring
repository, and this is not one. Publishing still writes `exam.json`.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

log = logging.getLogger("exam_bank.seed")

TARGET_NAME = "pcm-seed"

# The Content Editor's identifier under Tauri's app_data_dir, and what it
# names its copy. A marker file proves a folder is that app's seed rather
# than any directory that happens to be called pcm-seed.
_EDITOR_APP_ID = "com.pentaho.content-editor"
_EDITOR_MARKER = ".seed-state.json"


def seed_dir(project_root: Path) -> Optional[Path]:
    """The bundled seed, or None when this build carries none.

    `PEB_SEED_DIR` first, for tests and for running the backend by hand.
    Otherwise the installed shape: the staged tree is `<install>/app`, so
    the seed sits beside it as `<install>/seed`. The `app` check keeps a
    checkout, whose parent folder holds every repo, from adopting a stray
    `seed` directory there.
    """
    override = os.environ.get("PEB_SEED_DIR", "").strip()
    if override:
        path = Path(override).expanduser()
    elif Path(project_root).name == "app":
        path = Path(project_root).parent / "seed"
    else:
        return None
    if (path / "manifest.json").is_file() and (path / "courses").is_dir():
        return path
    return None


def target_courses_dir(state_root: Path) -> Path:
    """Where the seeded courses are laid out: `<state>/pcm-seed/courses`."""
    return Path(state_root) / TARGET_NAME / "courses"


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _copy_course(src: Path, dst: Path) -> None:
    """Copy through a temp name, so an interrupted copy leaves no half course
    for "already exists" to protect."""
    partial = dst.with_name(f".{dst.name}.partial")
    _remove(partial)
    shutil.copytree(src, partial)
    partial.rename(dst)


def ensure(state_root: Path, project_root: Path) -> Optional[Path]:
    """Lay the seeded courses out; return the courses directory.

    None when this build has no seed or the copy failed.
    """
    src_root = seed_dir(project_root)
    if src_root is None:
        return None
    dst = target_courses_dir(state_root)
    try:
        dst.mkdir(parents=True, exist_ok=True)
        for course in sorted((src_root / "courses").iterdir()):
            if course.is_dir() and not (dst / course.name).exists():
                _copy_course(course, dst / course.name)
    except OSError as exc:
        log.warning("could not lay out the bundled courses at %s: %s", dst, exc)
        return None
    return dst


def is_seeded(courses_dir: str | os.PathLike | None, state_root: Path) -> bool:
    """Is `courses_dir` a seeded copy: this app's own, or the editor's?"""
    if not courses_dir or not str(courses_dir).strip():
        return False
    try:
        here = Path(courses_dir).resolve()
        own = target_courses_dir(state_root).resolve()
        if here == own:
            return True
        theirs = editor_courses_dir()
        return theirs is not None and here == theirs.resolve()
    except OSError:
        return False


def _editor_seed_root() -> Optional[Path]:
    override = os.environ.get("PEB_EDITOR_SEED_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    appdata = os.environ.get("APPDATA", "").strip()
    if os.name == "nt" and appdata:
        return Path(appdata) / _EDITOR_APP_ID / "pcm-seed"
    return None


def editor_courses_dir() -> Optional[Path]:
    """The Content Editor's seeded courses, when it has laid them out.

    Only when the marker file is there and at least one course is: a
    folder the editor never wrote, or an empty one, is not a copy worth
    following.
    """
    root = _editor_seed_root()
    if root is None or not (root / _EDITOR_MARKER).is_file():
        return None
    courses = root / "courses"
    try:
        if any((c / "course.json").is_file() for c in courses.iterdir() if c.is_dir()):
            return courses
    except OSError:
        return None
    return None


def manifest(project_root: Path) -> dict:
    """The bundled seed's manifest, or {} - for diagnostics."""
    src = seed_dir(project_root)
    if src is None:
        return {}
    try:
        value = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}
