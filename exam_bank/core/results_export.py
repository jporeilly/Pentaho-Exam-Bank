"""Export candidate results to a separate SQLite file, and administer it.

The bank keeps imported results in its own database (`attempts`, `responses`).
An author who wants them kept apart from the bank (to share, archive, or point
a BI tool at) exports them to a **results database**: a plain SQLite file with
the same two tables. This module owns that file: append records to it, back it
up, truncate it, and delete records from it.

Safeguards, because most of this destroys data:

- The file is only ever one this module made. A target that already exists
  must carry the marker row this module writes; any other SQLite file (the
  bank itself, a stranger's database) is refused, so a mistyped path cannot
  be appended to or truncated.
- Destructive operations take the count the caller was shown and refuse if it
  has changed, and each takes a safety backup first.
- Names, emails and notes are not in the source tables, so none can be here.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import item_analysis as ia
from . import results_workbook as rw

KIND = "pentaho-exam-bank-results"
SUFFIXES = {".db", ".sqlite", ".sqlite3"}
DEFAULT_NAME = "exam_results.db"

_META = "CREATE TABLE IF NOT EXISTS export_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
_ATTEMPT_COLS = ("attempt_id", "candidate_id", "course_id", "course_tab", "role", "submitted_at",
                 "company", "score", "total", "percentage", "passed", "partner_id")
_RESPONSE_COLS = ("attempt_id", "question_id", "course_id", "submitted_at", "user_answer",
                  "correct_answer", "was_correct", "imported_at")


class ResultsExportError(ValueError):
    """The target is unusable, or the operation was refused; the message says why."""


def default_target(bank_db_path: Path) -> Path:
    return Path(bank_db_path).parent / DEFAULT_NAME


def resolve_target(raw: str, protected: tuple[Path, ...] = ()) -> Path:
    """The path to use, or ResultsExportError. Does not create anything."""
    raw = (raw or "").strip().strip('"')
    if not raw:
        raise ResultsExportError("Give the results database a file path.")
    path = Path(raw).expanduser()
    if path.suffix.lower() not in SUFFIXES:
        raise ResultsExportError("The results database must be a .db, .sqlite or .sqlite3 file.")
    if not path.parent.is_dir():
        raise ResultsExportError(f"The folder does not exist: {path.parent}")
    resolved = path.resolve()
    for p in protected:
        if resolved == Path(p).resolve():
            raise ResultsExportError("That is the exam bank's own database; pick a separate file.")
    if path.exists() and not path.is_file():
        raise ResultsExportError("That path is not a file.")
    return resolved


def _is_ours(conn) -> bool:
    try:
        row = conn.execute("SELECT value FROM export_meta WHERE key='kind'").fetchone()
    except sqlite3.DatabaseError:
        return False
    return bool(row) and row[0] == KIND


def connect(path: Path, create: bool = False) -> Optional[sqlite3.Connection]:
    """Open the results database. None when it does not exist and `create` is
    false. A file that is not one of ours is refused, never written to."""
    if not path.exists():
        if not create:
            return None
        conn = sqlite3.connect(str(path))
        conn.executescript(ia.SCHEMA)
        conn.execute(_META)
        conn.execute("INSERT OR REPLACE INTO export_meta (key, value) VALUES ('kind', ?)", (KIND,))
        conn.commit()
        return conn
    conn = sqlite3.connect(str(path))
    if not _is_ours(conn):
        conn.close()
        raise ResultsExportError(
            "That file exists but is not a results database made here, so it was left alone. "
            "Pick a new file name, or one this app created."
        )
    conn.executescript(ia.SCHEMA)
    return conn


def _counts(conn) -> dict[str, int]:
    return {
        "attempts": conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0],
        "answers": conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0],
    }


def backup_dir(path: Path) -> Path:
    return path.parent / f"{path.stem}_backups"


def list_backups(path: Path) -> list[dict[str, Any]]:
    folder = backup_dir(path)
    out = []
    for f in sorted(folder.glob("*.db"), reverse=True) if folder.is_dir() else []:
        st = f.stat()
        out.append({"name": f.name, "sizeKb": round(st.st_size / 1024, 1),
                    "created": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")})
    return out


def status(path: Path) -> dict[str, Any]:
    conn = connect(path)
    if conn is None:
        return {"path": str(path), "exists": False, "attempts": 0, "answers": 0, "sizeKb": 0,
                "backups": list_backups(path)}
    try:
        return {"path": str(path), "exists": True, **_counts(conn),
                "sizeKb": round(path.stat().st_size / 1024, 1), "backups": list_backups(path)}
    finally:
        conn.close()


def backup(path: Path, label: str = "") -> Path:
    """A timestamped copy of the results database, in `<name>_backups` beside it."""
    conn = connect(path)
    if conn is None:
        raise ResultsExportError("There is no results database to back up yet.")
    folder = backup_dir(path)
    folder.mkdir(exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in label.strip())[:40]
    base = f"{path.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}" + (f"_{safe}" if safe else "")
    target, n = folder / f"{base}.db", 2
    while target.exists():
        target = folder / f"{base}-{n}.db"
        n += 1
    dst = sqlite3.connect(str(target))
    try:
        conn.backup(dst)
    finally:
        dst.close()
        conn.close()
    return target


def append(source, path: Path, flt: rw.Filters) -> dict[str, Any]:
    """Copy the attempts (and their answers) that pass the filters into the
    results database, creating it if need be. Records it already holds are
    skipped, not overwritten, so appending twice adds nothing the second time."""
    ia.ensure_schema(source)
    ids = rw.matching_attempt_ids(source, flt)
    attempt_rows = source.execute(f"SELECT {', '.join(_ATTEMPT_COLS)} FROM attempts").fetchall()
    response_rows = source.execute(f"SELECT {', '.join(_RESPONSE_COLS)} FROM responses").fetchall()
    # An attempt known only from its answers (a CSV import) has no attempts row;
    # its answers are still exported.
    if ids is not None:
        attempt_rows = [r for r in attempt_rows if r[0] in ids]
        response_rows = [r for r in response_rows if r[0] in ids]
    conn = connect(path, create=True)
    try:
        before = _counts(conn)
        conn.executemany(
            f"INSERT OR IGNORE INTO attempts ({', '.join(_ATTEMPT_COLS)}) "
            f"VALUES ({', '.join('?' * len(_ATTEMPT_COLS))})", attempt_rows)
        conn.executemany(
            f"INSERT OR IGNORE INTO responses ({', '.join(_RESPONSE_COLS)}) "
            f"VALUES ({', '.join('?' * len(_RESPONSE_COLS))})", response_rows)
        conn.commit()
        after = _counts(conn)
    finally:
        conn.close()
    return {
        "offeredAttempts": len(attempt_rows), "offeredAnswers": len(response_rows),
        "addedAttempts": after["attempts"] - before["attempts"],
        "addedAnswers": after["answers"] - before["answers"],
        "skippedAttempts": len(attempt_rows) - (after["attempts"] - before["attempts"]),
        "totalAttempts": after["attempts"], "totalAnswers": after["answers"],
    }


def truncate(path: Path, expect_attempts: int) -> dict[str, Any]:
    """Remove every record. `expect_attempts` is the count the caller saw."""
    conn = connect(path)
    if conn is None:
        raise ResultsExportError("There is no results database yet.")
    try:
        have = _counts(conn)["attempts"]
        if have != expect_attempts:
            raise ResultsExportError(
                f"This was going to remove {expect_attempts} attempts but the database now holds "
                f"{have}. Nothing was removed; look again.")
    finally:
        conn.close()
    saved = backup(path, "before_truncate")
    conn = connect(path)
    try:
        counts = _counts(conn)
        conn.execute("DELETE FROM responses")
        conn.execute("DELETE FROM attempts")
        conn.commit()
        conn.execute("VACUUM")
    finally:
        conn.close()
    return {"removedAttempts": counts["attempts"], "removedAnswers": counts["answers"],
            "safetyBackup": saved.name}


def plan_delete(path: Path, flt: rw.Filters) -> dict[str, Any]:
    """How many attempts the filters would remove from the results database."""
    if not flt.active:
        raise ResultsExportError("Set at least one filter. To remove everything, use Truncate.")
    conn = connect(path)
    if conn is None:
        raise ResultsExportError("There is no results database yet.")
    try:
        ids = rw.matching_attempt_ids(conn, flt) or set()
        answers = sum(1 for (a,) in conn.execute("SELECT attempt_id FROM responses") if a in ids)
        sample = [a for a in rw.attempt_index(conn) if a["attempt_id"] in ids]
        sample.sort(key=lambda a: (a["submitted_at"] or "", a["attempt_id"]), reverse=True)
        return {
            "attempts": len(ids), "answers": answers,
            "sample": [{"attemptId": a["attempt_id"], "candidateId": a["candidate_id"], "day": a["day"],
                        "courseId": a["course_id"]} for a in sample[:5]],
        }
    finally:
        conn.close()


def delete(path: Path, flt: rw.Filters, expect_attempts: int) -> dict[str, Any]:
    plan = plan_delete(path, flt)
    if plan["attempts"] != expect_attempts:
        raise ResultsExportError(
            f"This was going to remove {expect_attempts} attempts but the filters now match "
            f"{plan['attempts']}. Nothing was removed; look again.")
    if plan["attempts"] == 0:
        raise ResultsExportError("Nothing matches those filters, so there is nothing to remove.")
    saved = backup(path, "before_delete")
    conn = connect(path)
    try:
        ids = sorted(rw.matching_attempt_ids(conn, flt) or set())
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            marks = ", ".join("?" * len(chunk))
            conn.execute(f"DELETE FROM responses WHERE attempt_id IN ({marks})", chunk)
            conn.execute(f"DELETE FROM attempts WHERE attempt_id IN ({marks})", chunk)
        conn.commit()
    finally:
        conn.close()
    return {"removedAttempts": plan["attempts"], "removedAnswers": plan["answers"],
            "safetyBackup": saved.name}
