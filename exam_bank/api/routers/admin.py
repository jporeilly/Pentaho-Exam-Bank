"""Database administration: backups, and bulk deletion.

Everything here either destroys data or is the thing that gets it back, so the
two are deliberately in one place: an author about to delete four hundred
questions should be looking at the backup list while they do it.

Backups are addressed **by name, never by path**. The name is resolved inside
the backup directory and checked to be there — a client that could hand over a
path could restore the bank from, or delete, any file on the machine.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ...core import db_backup, results_export, results_schedule, results_workbook
from ...core.admin import DeletionRefused, delete_questions, plan_deletion
from ...core.bank import ExamBankDB
from ..deps import get_db

router = APIRouter(tags=["admin"])

#: A backup name as `list_backups` reports it: the file stem, nothing else.
#: Anything with a separator or a dot is not a name this app produced.
SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


def _backup_path(name: str) -> Path:
    """Resolve a backup name inside the backup directory, or refuse.

    Two checks rather than one. The pattern rejects the obvious traversal, and
    resolving the parent catches what it would miss — a symlink, a name that
    is somehow absolute on this platform. Either alone has been enough to get
    something wrong before.
    """
    if not name or not SAFE_NAME.match(name):
        raise HTTPException(400, f"Not a backup name: {name!r}")

    # Asked of db_backup rather than imported from config: that module writes
    # and deletes in this directory, and two independent bindings to it are
    # two things to keep in step.
    root = db_backup.BACKUP_DIR
    candidate = (root / f"{name}.db").resolve()
    if candidate.parent != root.resolve():
        raise HTTPException(400, f"Not a backup name: {name!r}")
    if not candidate.is_file():
        raise HTTPException(404, f"No backup called '{name}'.")
    return candidate


def _backups() -> list[dict[str, Any]]:
    return [
        {
            "name": b["name"],
            "sizeKb": b["size_kb"],
            "created": b["created"],
        }
        for b in db_backup.list_backups()
    ]


@router.get("/api/admin/database")
def database_status() -> dict[str, Any]:
    """The live database, and every backup of it."""
    return {"database": db_backup.get_db_info(), "backups": _backups()}


class BackupRequest(BaseModel):
    #: Shows up in the filename, so it is what the backup is recognised by
    #: later. Restricted to the characters a filename can carry.
    label: str = ""


@router.post("/api/admin/backups", status_code=201)
def make_backup(body: BackupRequest) -> dict[str, Any]:
    label = re.sub(r"[^A-Za-z0-9_-]+", "-", body.label.strip())[:40].strip("-")
    try:
        path = db_backup.create_backup(label=label)
    except FileNotFoundError as e:
        raise HTTPException(409, str(e)) from e
    return {"name": path.stem, "backups": _backups()}


@router.post("/api/admin/backups/{name}/restore")
def restore(name: str) -> dict[str, Any]:
    """Replace the live database with a backup.

    The current database is backed up first, labelled ``pre_restore``, by
    ``db_backup.restore_backup``. That is the difference between an undoable
    mistake and a lost bank, so the new backup's name is returned for the UI
    to show rather than left for the author to find.
    """
    path = _backup_path(name)
    before = {b["name"] for b in db_backup.list_backups()}
    try:
        db_backup.restore_backup(path)
    except (OSError, FileNotFoundError) as e:
        raise HTTPException(409, f"{name} could not be restored: {e}") from e

    after = _backups()
    made = sorted({b["name"] for b in after} - before)
    return {
        "restored": name,
        # What the previous bank is now called, so it can be restored back.
        "safetyBackup": made[0] if made else "",
        "database": db_backup.get_db_info(),
        "backups": after,
    }


@router.delete("/api/admin/backups/{name}")
def remove_backup(name: str) -> dict[str, Any]:
    path = _backup_path(name)
    db_backup.delete_backup(path)
    return {"deleted": name, "backups": _backups()}


class DeletionRequest(BaseModel):
    """Which questions, and how many the caller was told that was."""

    status: str = ""
    topic: str = ""
    certification_id: str = ""
    difficulty: str = ""
    bloom_level: str = ""
    #: From the preview. A mismatch means the bank changed in between.
    expect_count: int = Field(-1)
    #: Required to delete an unfiltered set, which is the whole bank.
    everything: bool = False

    def filters(self) -> dict[str, str]:
        return {
            "status": self.status,
            "topic": self.topic,
            "certification_id": self.certification_id,
            "difficulty": self.difficulty,
            "bloom_level": self.bloom_level,
        }


def _plan_json(plan) -> dict[str, Any]:
    return {
        "total": plan.total,
        "everything": plan.everything,
        "byStatus": plan.by_status,
        "byCertification": plan.by_certification,
        "sample": plan.sample,
    }


@router.post("/api/admin/questions/delete/preview")
def preview_deletion(
    body: DeletionRequest, db: ExamBankDB = Depends(get_db)
) -> dict[str, Any]:
    """What a bulk deletion would remove. Deletes nothing."""
    return _plan_json(plan_deletion(db, body.filters()))


@router.post("/api/admin/questions/delete")
def bulk_delete(
    body: DeletionRequest, db: ExamBankDB = Depends(get_db)
) -> dict[str, Any]:
    """Delete the matching questions, having been told how many to expect."""
    if body.expect_count < 0:
        raise HTTPException(
            400,
            "Deleting needs the count from a preview. Ask "
            "/api/admin/questions/delete/preview first and pass back its total.",
        )
    try:
        deleted = delete_questions(
            db, body.filters(),
            expect_count=body.expect_count,
            everything=body.everything,
        )
    except DeletionRefused as e:
        raise HTTPException(409, str(e)) from e
    return {"deleted": deleted}


# -- the results database (1.20.0) -------------------------------------------
# A separate SQLite file the Results tab exports to. The same Admin page holds
# it because it has the same shape of risk as the bank: backups, and deletion
# that is count-first and refused if the count has moved.


class ResultsDbRequest(BaseModel):
    #: The results database file. Empty means the default beside the bank.
    path: str = ""
    course: str = ""
    candidate: str = ""
    passed: str = ""
    attempt_no: int = 0
    date_from: str = ""
    date_to: str = ""
    label: str = ""
    #: From the preview or status. A mismatch means it changed in between.
    expect_count: int = Field(-1)


def _results_target(db: ExamBankDB, raw: str) -> Path:
    try:
        default = results_export.default_target(db.db_path)
        return results_export.resolve_target(raw or str(default), (Path(db.db_path), db_backup.DB_PATH))
    except results_export.ResultsExportError as e:
        raise HTTPException(422, str(e)) from e


def _results_filters(body: ResultsDbRequest) -> results_workbook.Filters:
    try:
        return results_workbook.Filters(body.course, body.candidate, body.passed, body.attempt_no,
                                        body.date_from, body.date_to)
    except ValueError as e:
        raise HTTPException(422, f"Bad filter: {e}") from e


def _refusing(work):
    try:
        return work()
    except results_export.ResultsExportError as e:
        raise HTTPException(409, str(e)) from e


@router.get("/api/admin/results-db")
def results_db_status(path: str = "", db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    target = _results_target(db, path)
    return {**_refusing(lambda: results_export.status(target)),
            "defaultPath": str(results_export.default_target(db.db_path))}


@router.post("/api/admin/results-db/append")
def results_db_append(body: ResultsDbRequest, db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    """Copy the Results tab's records (under its filters) into the results database."""
    target = _results_target(db, body.path)
    flt = _results_filters(body)
    return _refusing(lambda: results_export.append(db.conn, target, flt))


@router.post("/api/admin/results-db/backup", status_code=201)
def results_db_backup(body: ResultsDbRequest, db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    target = _results_target(db, body.path)
    label = re.sub(r"[^A-Za-z0-9_-]+", "-", body.label.strip())[:40].strip("-")
    saved = _refusing(lambda: results_export.backup(target, label))
    return {"name": saved.name, "backups": results_export.list_backups(target)}


@router.post("/api/admin/results-db/truncate")
def results_db_truncate(body: ResultsDbRequest, db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    if body.expect_count < 0:
        raise HTTPException(400, "Truncating needs the attempt count from the status.")
    target = _results_target(db, body.path)
    return _refusing(lambda: results_export.truncate(target, body.expect_count))


@router.post("/api/admin/results-db/delete/preview")
def results_db_delete_preview(body: ResultsDbRequest, db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    target = _results_target(db, body.path)
    flt = _results_filters(body)
    return _refusing(lambda: results_export.plan_delete(target, flt))


@router.post("/api/admin/results-db/delete")
def results_db_delete(body: ResultsDbRequest, db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    if body.expect_count < 0:
        raise HTTPException(400, "Deleting needs the count from a preview.")
    target = _results_target(db, body.path)
    flt = _results_filters(body)
    return _refusing(lambda: results_export.delete(target, flt, body.expect_count))


class ScheduleRequest(BaseModel):
    enabled: bool = False
    workbook_path: str = ""
    target_path: str = ""
    time: str = "02:00"


def _protected(db: ExamBankDB) -> tuple[Path, ...]:
    return (Path(db.db_path), db_backup.DB_PATH)


@router.get("/api/admin/results-schedule")
def results_schedule_get(db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    return {**results_schedule.load(), "defaultTarget": str(results_export.default_target(db.db_path))}


@router.put("/api/admin/results-schedule")
def results_schedule_put(body: ScheduleRequest, db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    target = body.target_path or str(results_export.default_target(db.db_path))
    try:
        return results_schedule.save_settings(body.enabled, body.workbook_path, target, body.time, _protected(db))
    except results_export.ResultsExportError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/api/admin/results-schedule/run")
def results_schedule_run(db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    """Run the daily load now with the saved settings."""
    try:
        return results_schedule.run_load(Path(db.db_path), _protected(db))
    except results_export.ResultsExportError as e:
        raise HTTPException(409, str(e)) from e
