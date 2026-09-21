"""Database backup and restore utilities."""

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ..utils.config import DB_PATH, BACKUP_DIR


def list_backups() -> List[dict]:
    """Return list of backups sorted newest-first.

    Each dict has keys: name, path, size_kb, created.
    """
    backups = []
    for f in sorted(BACKUP_DIR.glob("*.db"), reverse=True):
        stat = f.stat()
        backups.append({
            "name": f.stem,
            "path": f,
            "size_kb": round(stat.st_size / 1024, 1),
            "created": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    return backups


def create_backup(label: str = "") -> Path:
    """Create a timestamped backup of the current database.

    Returns the path to the backup file.
    """
    if not DB_PATH.exists():
        raise FileNotFoundError("No database to back up.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{label}" if label else ""
    backup_name = f"exam_bank_{timestamp}{suffix}.db"
    backup_path = BACKUP_DIR / backup_name

    # Use SQLite online backup API for a safe, consistent copy
    src = sqlite3.connect(str(DB_PATH))
    dst = sqlite3.connect(str(backup_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    return backup_path


def restore_backup(backup_path: Path) -> None:
    """Restore a backup over the current database.

    Creates an auto-backup of the current DB before overwriting.
    """
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup not found: {backup_path}")

    # Safety: back up current DB before restoring
    if DB_PATH.exists():
        create_backup(label="pre_restore")

    # Use SQLite backup API for safe restore
    src = sqlite3.connect(str(backup_path))
    dst = sqlite3.connect(str(DB_PATH))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def delete_backup(backup_path: Path) -> None:
    """Delete a backup file."""
    if backup_path.exists() and backup_path.parent == BACKUP_DIR:
        backup_path.unlink()


def get_db_info() -> dict:
    """Return info about the current database."""
    if not DB_PATH.exists():
        return {"exists": False, "path": str(DB_PATH)}

    stat = DB_PATH.stat()
    conn = sqlite3.connect(str(DB_PATH))
    try:
        count = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        certs = conn.execute("SELECT COUNT(*) FROM certifications").fetchone()[0]
    except Exception:
        count = 0
        certs = 0
    finally:
        conn.close()

    return {
        "exists": True,
        "path": str(DB_PATH),
        "size_kb": round(stat.st_size / 1024, 1),
        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        "questions": count,
        "certifications": certs,
    }
