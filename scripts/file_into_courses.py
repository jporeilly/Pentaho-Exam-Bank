"""File the course questions the bank never gave a course id or a place.

Before 1.7.1 a question generated for a course, or imported into one from a
file without ids, was saved with a random UUID for its id, the lab's title
for its module and no place in the course's order. 1.7.1 files new questions
properly (core/course_filing). This does the same for the ones already in the
bank.

Usage (from the repo root):

    venv\\Scripts\\python.exe scripts\\file_into_courses.py            # what would change
    venv\\Scripts\\python.exe scripts\\file_into_courses.py --apply    # change it

The dry run works on a temporary copy of the bank, because making room for a
question can move others. ``--apply`` takes a backup first (label
``pre-file-into-courses``) and records each id and module change in the
question's own history.

A question whose id is already in its course's exam.json is left alone and
reported: it has been published under that id, and a new one would make the
course's copy look like a different question.

Set PEB_STATE_DIR to %APPDATA%\\com.pentaho.exam-bank to work on the
installed app's bank; without it this is the checkout's own bank.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from exam_bank.core import db_backup  # noqa: E402
from exam_bank.core.bank import ExamBankDB  # noqa: E402
from exam_bank.core.course_filing import (  # noqa: E402
    course_slug, file_into_course, is_minted, is_standard, taken_ids,
)
from exam_bank.utils.config import DB_PATH, config  # noqa: E402


def _published(root: Path | None, slug: str) -> set[str]:
    exam = root / slug / "exam.json" if root else None
    try:
        data = json.loads(exam.read_text(encoding="utf-8")) if exam else {}
    except (OSError, ValueError):
        return set()
    return {str(q.get("id")) for q in data.get("questions", []) if isinstance(q, dict)}


def run(db: ExamBankDB, root: Path | None, editor: str) -> list[dict]:
    taken = taken_ids(db, root)
    report = []
    for cert in db.list_certifications():
        slug = course_slug(cert)
        if not slug:
            continue
        published = _published(root, slug)
        for q in db.search(certification_id=cert.id, limit=100000):
            if not (is_minted(q.id) or not is_standard(q.id) or q.pool_order < 0):
                continue
            if q.id in published:
                report.append({"course": slug, "id": q.id, "skipped": "already published under this id"})
                continue
            old = q.id
            result = file_into_course(db, q, cert, courses_dir=root, taken=taken,
                                      editor=editor, record=True)
            if q.id != old:
                db.rename_question(old, q.id)
            db.save(q)
            report.append({
                "course": slug, "id": old, "newId": q.id,
                "topic": [result.topic_from, result.topic_to],
                "poolOrder": result.pool_order, "moved": result.moved,
                "citation": q.source_file, "status": q.status,
            })
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true", help="change the bank (after a backup)")
    ap.add_argument("--editor", default="Exam Bank", help="the name recorded in each question's history")
    args = ap.parse_args()

    raw = (config.pcm_courses_dir or "").strip()
    root = Path(raw) if raw and Path(raw).is_dir() else None
    out = {"db": str(DB_PATH), "courses": str(root) if root else None, "applied": args.apply}

    if args.apply:
        out["backup"] = str(db_backup.create_backup("pre-file-into-courses"))
        db = ExamBankDB(DB_PATH)
        try:
            out["filed"] = run(db, root, args.editor)
        finally:
            db.close()
    else:
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "bank.db"
            # SQLite's own backup, not a file copy: consistent even while the
            # app has the bank open.
            src, dst = sqlite3.connect(str(DB_PATH)), sqlite3.connect(str(copy))
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()
            db = ExamBankDB(copy)
            try:
                out["filed"] = run(db, root, args.editor)
            finally:
                db.close()

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
