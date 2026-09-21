"""What this process was opened for.

The Content Editor's "Questions" button spawns the bank with two variables in
the child's environment:

    PQB_COURSE=<slug>     the course whose questions the author wants
    PCM_REPO=<root>       the Content Manager checkout it came from

Both are **hints**, not instructions. The slug is resolved against the courses
directory at read time and reported as unknown if it does not resolve — never
stored, and never trusted from a previous run. That is not caution for its own
sake: the bank's original two certifications died silently because they held a
slug that stopped resolving when the courses were renamed under them, and
`load_pcm_course` answered with an empty list rather than an error.

`PCM_REPO` is compared with the bank's own configured courses path. When they
disagree the bank keeps reading its own configuration and says both out loud,
because the alternative is editing one checkout's questions while the author
believes they are looking at another's.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..core.pcm_reader import list_pcm_courses
from ..utils.config import config


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _configured_courses_dir() -> Path | None:
    raw = (config.pcm_courses_dir or "").strip()
    return Path(raw) if raw else None


def _handed_over_courses_dir() -> Path | None:
    """PCM_REPO names the repository root; the courses live inside it."""
    root = _env("PCM_REPO")
    return Path(root) / "courses" if root else None


def repo_disagreement() -> dict[str, str] | None:
    """The two paths, when the handover disagrees with the configuration.

    None when nothing was handed over, or when the two agree. Comparison is by
    resolved path, so a trailing slash or a different spelling of the same
    directory is not reported as a conflict.
    """
    handed = _handed_over_courses_dir()
    configured = _configured_courses_dir()
    if handed is None or configured is None:
        return None
    try:
        same = handed.resolve() == configured.resolve()
    except OSError:
        same = str(handed) == str(configured)
    if same:
        return None
    return {
        "handedOver": str(handed),
        "configured": str(configured),
        # Said explicitly so an interface never has to guess which one the
        # questions on screen actually came from.
        "using": str(configured),
    }


def launch_context() -> dict[str, Any]:
    """The startup hint, resolved. Safe to call when nothing was handed over
    and when the courses directory is missing — it reports, never raises."""
    slug = _env("PQB_COURSE")
    context: dict[str, Any] = {
        "course": slug,
        "courseKnown": False,
        "courseTitle": "",
        "repoDisagreement": repo_disagreement(),
    }
    if not slug:
        return context

    root = _configured_courses_dir()
    if root is None or not root.is_dir():
        return context

    for course in list_pcm_courses(root):
        if course["slug"] == slug:
            context["courseKnown"] = True
            context["courseTitle"] = course["title"]
            break
    return context
