"""Version, health and the state of the configured model provider."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from ... import __version__
from ...core import providers
from ...core.bank import ExamBankDB
from ...utils.config import DB_PATH, config
from .. import launch
from ..deps import get_db

router = APIRouter(tags=["system"])


def content_manager_version(courses_dir: str) -> str:
    """The version of the Content Manager whose courses this bank reads.

    The courses directory is `<content-manager>/courses`, and the Content
    Manager's own package.json sits beside it. Shown in the status bar next to
    the bank's version, the same pairing the Content Editor makes with its
    "Engine": which build, reading which content. Empty when it cannot be read
    - an unconfigured or copied courses folder has no Content Manager beside
    it, and that is not an error worth reporting here.
    """
    if not courses_dir:
        return ""
    try:
        pkg = Path(courses_dir).parent / "package.json"
        return str(json.loads(pkg.read_text(encoding="utf-8")).get("version") or "")
    except (OSError, ValueError, AttributeError):
        return ""


@router.get("/api/version")
def version() -> dict[str, str]:
    return {"version": __version__}


@router.get("/api/health")
def health(db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    """Everything a client needs to tell the user what is and is not working.

    The provider check is included but never fatal: the bank, import and
    export all work with no model available, and a dead Ollama must not make
    the app look broken.
    """
    return {
        "version": __version__,
        "database": {
            "path": str(DB_PATH),
            "exists": DB_PATH.exists(),
            "questions": db.count(),
            "certifications": len(db.list_certifications()),
        },
        "provider": providers.health(),
        "courses": {
            "path": config.pcm_courses_dir,
            "configured": bool(config.pcm_courses_dir),
            "contentManagerVersion": content_manager_version(config.pcm_courses_dir),
        },
        # What the process was opened for, when something launched it with a
        # course in mind. Reported here because the client already asks for
        # health at startup, and this never changes while the process runs.
        "launch": launch.launch_context(),
    }


@router.get("/api/stats")
def stats(db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    return {
        "byStatus": db.get_status_counts(),
        "byTopic": db.get_topic_counts(),
        "byDifficulty": db.get_difficulty_counts(),
        "byBloom": db.get_bloom_counts(),
        "total": db.count(),
    }
