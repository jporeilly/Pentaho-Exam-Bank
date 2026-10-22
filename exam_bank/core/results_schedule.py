"""A daily incremental load of the results workbook into the results database.

Each day, at a set time while the app is open (or at the next check after it
was missed), the workbook at a fixed path is imported - the existing
upsert-by-attempt-id import, so only new attempts and answers are added - and
the records are then appended to the results database
(`results_export.append`, which skips what the file already holds). Running it
twice, or on an unchanged workbook, changes nothing.

The settings and the last outcome live in one small JSON file beside the
app's config. A failed run is retried at most hourly, so a workbook that is
not there yet does not become a stream of errors.
"""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from ..utils.config import CONFIG_DIR, DB_PATH
from . import results_export, results_workbook
from .bank import ExamBankDB
from .item_analysis import ResultsImportError

SETTINGS_FILE = CONFIG_DIR / "results_schedule.json"
CHECK_EVERY = 60
RETRY_AFTER = timedelta(hours=1)
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_lock = threading.Lock()

DEFAULTS: dict[str, Any] = {
    "enabled": False, "workbookPath": "", "targetPath": "", "time": "02:00",
    "lastAttempt": "", "lastSuccess": "", "lastMessage": "", "lastOk": None,
}


def load() -> dict[str, Any]:
    try:
        data = json.loads(Path(SETTINGS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {**DEFAULTS, **{k: data[k] for k in DEFAULTS if k in data}}


def _save(settings: dict[str, Any]) -> None:
    Path(SETTINGS_FILE).write_text(json.dumps(settings, indent=1), encoding="utf-8")


def validate(workbook: str, target: str, time: str, protected: tuple[Path, ...] = ()) -> tuple[str, str]:
    """The cleaned workbook path and the resolved target, or ResultsExportError."""
    if not _TIME.match(time or ""):
        raise results_export.ResultsExportError("The time must be HH:MM, 24-hour.")
    wb = (workbook or "").strip().strip('"')
    if not wb or Path(wb).suffix.lower() != ".xlsx":
        raise results_export.ResultsExportError("Give the path of the results workbook (.xlsx).")
    return wb, str(results_export.resolve_target(target, protected))


def save_settings(enabled: bool, workbook: str, target: str, time: str,
                  protected: tuple[Path, ...] = ()) -> dict[str, Any]:
    wb, tgt = validate(workbook, target, time, protected)
    s = {**load(), "enabled": bool(enabled), "workbookPath": wb, "targetPath": tgt, "time": time}
    _save(s)
    return s


def run_load(db_path: Path, protected: tuple[Path, ...] = ()) -> dict[str, Any]:
    """One load now. Records the outcome; raises ResultsExportError on failure."""
    with _lock:
        s = load()
        now = datetime.now().isoformat(timespec="seconds")
        try:
            wb, tgt = validate(s["workbookPath"], s["targetPath"], s["time"], protected)
            path = Path(wb)
            if not path.is_file():
                raise results_export.ResultsExportError(f"The workbook is not there: {wb}")
            try:
                data = path.read_bytes()
            except OSError as e:
                raise results_export.ResultsExportError(f"The workbook could not be read: {e}") from e
            db = ExamBankDB(Path(db_path), same_thread_only=False)
            try:
                try:
                    imported = results_workbook.import_workbook(db.conn, data)
                except ResultsImportError as e:
                    raise results_export.ResultsExportError(str(e)) from e
                appended = results_export.append(db.conn, Path(tgt), results_workbook.Filters())
            finally:
                db.close()
        except results_export.ResultsExportError as e:
            _save({**s, "lastAttempt": now, "lastOk": False, "lastMessage": str(e)})
            raise
        msg = (f"Read {imported['attempts']} attempts and {imported['answers']} answers; "
               f"added {appended['addedAttempts']} attempts and {appended['addedAnswers']} answers "
               f"to the results database ({appended['totalAttempts']} attempts in all).")
        _save({**s, "lastAttempt": now, "lastSuccess": now, "lastOk": True, "lastMessage": msg})
        return {"message": msg, "imported": imported, "appended": appended}


def due(settings: dict[str, Any], now: Optional[datetime] = None) -> bool:
    if not settings["enabled"] or not settings["workbookPath"] or not settings["targetPath"]:
        return False
    now = now or datetime.now()
    h, m = (int(x) for x in settings["time"].split(":"))
    if now < now.replace(hour=h, minute=m, second=0, microsecond=0):
        return False
    if settings["lastSuccess"] and settings["lastSuccess"][:10] == now.date().isoformat():
        return False
    if settings["lastOk"] is False and settings["lastAttempt"]:
        try:
            if now - datetime.fromisoformat(settings["lastAttempt"]) < RETRY_AFTER:
                return False
        except ValueError:
            pass
    return True


def run_if_due(now: Optional[datetime] = None) -> bool:
    if not due(load(), now):
        return False
    try:
        run_load(DB_PATH, (DB_PATH,))
    except results_export.ResultsExportError:
        pass                      # recorded in the settings file for the Admin page
    except Exception as e:        # noqa: BLE001 - never stop the app
        s = load()
        _save({**s, "lastAttempt": datetime.now().isoformat(timespec="seconds"), "lastOk": False,
               "lastMessage": f"Unexpected error: {e}"})
    return True


def start() -> threading.Event:
    stop = threading.Event()

    def loop() -> None:
        while not stop.is_set():
            run_if_due()
            stop.wait(CHECK_EVERY)

    threading.Thread(target=loop, name="results-schedule", daemon=True).start()
    return stop
