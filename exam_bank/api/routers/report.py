"""The Report pane: each exam's Bloom balance, bar check and review progress."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from ...core.bank import ExamBankDB
from ...core.report import build_report
from ...utils.config import config
from ..deps import get_db

router = APIRouter(tags=["report"])


@router.get("/api/report")
def report(db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    """Bloom level and review status for the bank, each exam and each workshop.

    Read-only. The whole bank in one response, because the pane filters it in
    place and the three grains have to add up to the same totals.

    Not `deps.courses_dir()`: that raises 409 when no courses directory is
    configured, and the report is still worth having without one — it just
    cannot show the level bar or the draw, which only the course files know.
    """
    raw = (config.pcm_courses_dir or "").strip()
    courses = Path(raw) if raw and Path(raw).is_dir() else None
    return build_report(db, courses)
