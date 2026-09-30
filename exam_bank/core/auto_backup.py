"""Automatic backups of the bank, on a schedule.

With **Back up automatically** on (Settings), the bank is copied every N
hours - checked when the app starts and every few minutes while it runs - and
only the newest M automatic backups are kept. A backup you take yourself, and
the safety copy a restore takes, are never pruned: only files this module
made, which carry the ``auto`` label, are ever deleted.

The copy is ``db_backup.create_backup``, the same SQLite online backup the
Admin screen uses, so it is consistent while the app is writing.
"""

from __future__ import annotations

import re
import threading
from datetime import datetime, timedelta
from pathlib import Path

from ..utils.config import BACKUP_DIR, config
from . import db_backup

LABEL = "auto"
#: How often the running app looks at the clock. Backups are hours apart; this
#: only bounds how late one can be.
CHECK_EVERY = 600

_NAME = re.compile(r"^exam_bank_(\d{8}_\d{6})_auto(?:-\d+)?\.db$")

#: The last run, for Settings to show.
last: dict = {"at": "", "path": "", "pruned": 0, "error": ""}


def _auto_backups() -> list[tuple[datetime, Path]]:
    """This module's backups, newest first."""
    out = []
    for p in Path(BACKUP_DIR).glob("exam_bank_*_auto*.db"):
        m = _NAME.match(p.name)
        if m:
            out.append((datetime.strptime(m.group(1), "%Y%m%d_%H%M%S"), p))
    return sorted(out, reverse=True)


def due(now: datetime | None = None) -> bool:
    if not config.auto_backup_enabled:
        return False
    now = now or datetime.now()
    newest = _auto_backups()
    hours = max(1, int(config.auto_backup_interval_hours or 24))
    return not newest or now - newest[0][0] >= timedelta(hours=hours)


def prune() -> int:
    """Delete automatic backups beyond the newest ``auto_backup_max_count``."""
    keep = max(1, int(config.auto_backup_max_count or 5))
    removed = 0
    for _, path in _auto_backups()[keep:]:
        db_backup.delete_backup(path)
        removed += 1
    return removed


def run_if_due(now: datetime | None = None) -> Path | None:
    """Back up if the interval has passed, then prune. Returns the new file."""
    if not due(now):
        return None
    try:
        path = db_backup.create_backup(LABEL)
        pruned = prune()
    except Exception as e:  # noqa: BLE001 - reported in Settings; the app goes on
        last.update(at=datetime.now().isoformat(timespec="seconds"), error=str(e))
        return None
    last.update(at=datetime.now().isoformat(timespec="seconds"), path=str(path),
                pruned=pruned, error="")
    return path


def start() -> threading.Event:
    """Check now and then every ``CHECK_EVERY`` seconds until the event is set."""
    stop = threading.Event()

    def loop() -> None:
        while not stop.is_set():
            run_if_due()
            stop.wait(CHECK_EVERY)

    threading.Thread(target=loop, name="auto-backup", daemon=True).start()
    return stop
