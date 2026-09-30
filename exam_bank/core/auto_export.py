"""Auto-export on save: the whole bank, written to the export folder.

With **Export after each change** on (Settings), every change to the bank - an
edit, a status move, a delete, an import, a generation commit, a course sync,
a restored backup - is followed by an export of the whole bank, in the
default export format, to the export folder. It is a copy for people and
tools outside the app: a spreadsheet, a folder a colleague syncs, a backup a
file-history tool picks up.

The export runs a couple of seconds after the LAST change of a burst, on a
background thread, so saving twenty questions writes the file once and no
save waits for it. It is written beside the target and renamed over it, so a
reader never sees half a file. The file name says the format, and a change of
format writes a new file rather than overwriting one of another kind.

``api/app.py`` decides which requests change the bank and calls ``schedule``.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime
from pathlib import Path

from ..utils.config import DB_PATH, config
from .bank import ExamBankDB
from .exporter import FORMATS

#: Seconds to wait after a change before exporting: long enough to catch a
#: burst of saves, short enough that the file is current when you look.
DELAY = 2.0

_lock = threading.Lock()
_timer: threading.Timer | None = None

#: The last export, for Settings to show: when, where, how many, or the error.
last: dict = {"at": "", "path": "", "count": 0, "error": ""}


def format_in_use() -> str:
    fmt = (config.default_export_format or "").strip()
    return fmt if fmt in FORMATS else "csv"


def target(fmt: str = "") -> Path:
    """Where the export goes: ``exam-bank.csv``, ``exam-bank-qti.xml`` ..."""
    fmt = fmt or format_in_use()
    extension = FORMATS[fmt][1]
    stem = "exam-bank" if extension == fmt else f"exam-bank-{fmt}"
    return Path(config.output_folder).expanduser() / f"{stem}.{extension}"


def export_now(db_path: Path | str = DB_PATH) -> Path:
    """Write the whole bank now, in the default format. Raises on failure."""
    fmt = format_in_use()
    write = FORMATS[fmt][0]
    path = target(fmt)
    path.parent.mkdir(parents=True, exist_ok=True)

    db = ExamBankDB(db_path)
    try:
        questions = db.search(limit=1_000_000, sort="course")
    finally:
        db.close()

    partial = path.with_name(f".{path.name}.writing")
    write(questions, partial)
    os.replace(partial, path)
    last.update(at=datetime.now().isoformat(timespec="seconds"), path=str(path),
                count=len(questions), error="")
    return path


def _run() -> None:
    global _timer
    with _lock:
        _timer = None
    try:
        export_now()
    except Exception as e:  # noqa: BLE001 - reported in Settings, never raised into a save
        last.update(at=datetime.now().isoformat(timespec="seconds"), error=str(e))


def schedule() -> bool:
    """Export after the current burst of changes, if the setting is on."""
    global _timer
    if not config.auto_export_on_save:
        return False
    with _lock:
        if _timer is not None:
            _timer.cancel()
        _timer = threading.Timer(DELAY, _run)
        _timer.daemon = True
        _timer.start()
    return True


def changes_bank(method: str, path: str) -> bool:
    """Whether a successful request of this shape changed the questions."""
    if method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return False
    if path.startswith("/api/questions/"):
        return "/ai/" not in path                   # the AI buttons only propose
    if path.startswith("/api/jobs/"):
        return path.endswith("/commit")
    if path.startswith("/api/admin/backups/"):
        return path.endswith("/restore")
    return path in {"/api/import/commit", "/api/courses/sync", "/api/admin/questions/delete"}
