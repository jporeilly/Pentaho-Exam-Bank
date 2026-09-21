"""Version, health and the state of the configured model provider."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ... import __version__
from ...core import providers
from ...core.bank import ExamBankDB
from ...utils.config import DB_PATH, config
from .. import launch
from ..deps import get_db

router = APIRouter(tags=["system"])


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
