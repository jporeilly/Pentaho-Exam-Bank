"""Adopt live PCM course exams into the bank.

The questions in PCM's `courses/<slug>/exam.json` have had no editing tool:
the bank never kept them, and the Content Editor deliberately refuses to
touch `questions`. This script brings a course's pool INTO the bank, ids
intact, so it can be edited and published back.

One certification is created per course, keyed to the course slug, and each
question is filed under it.

Usage (from the repo root):

    venv\\Scripts\\python.exe scripts\\migrate_pcm_exams.py <slug> [<slug> ...]
    venv\\Scripts\\python.exe scripts\\migrate_pcm_exams.py --clean <slug> ...

`--clean` empties the bank first. It takes a timestamped copy of the
database into assets/db/backups/ before deleting anything.

The slug is resolved against the courses directory at RUN TIME and the
course must exist. Nothing is cached: a stored slug that silently stopped
resolving is exactly how the bank's two original certifications died when
PCM renamed the courses under them.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from question_bank.core.question_bank import Certification, QuestionBankDB
from question_bank.core.question_importer import import_from_pcm_exam_json
from question_bank.utils.config import config, DB_PATH, BACKUP_DIR


def courses_dir() -> Path:
    raw = (config.pcm_courses_dir or "").strip()
    if not raw:
        sys.exit("No PCM courses directory configured. Set pcm_courses_dir in the config.")
    path = Path(raw)
    if not path.is_dir():
        sys.exit(f"PCM courses directory does not exist: {path}")
    return path


def course_title(course_dir: Path, slug: str) -> str:
    cj = course_dir / "course.json"
    if cj.is_file():
        try:
            data = json.loads(cj.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("title"):
                return str(data["title"]).strip()
        except (ValueError, OSError):
            pass
    return slug


def backup_db() -> Path | None:
    if not DB_PATH.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_DIR / f"question_bank-pre-clean-{stamp}.db"
    shutil.copy2(DB_PATH, dest)
    return dest


def clean(db: QuestionBankDB) -> tuple[int, int]:
    """Empty the bank. Returns (questions_removed, certifications_removed)."""
    conn: sqlite3.Connection = db.conn
    n_q = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    n_c = conn.execute("SELECT COUNT(*) FROM certifications").fetchone()[0]
    conn.execute("DELETE FROM questions")
    conn.execute("DELETE FROM certifications")
    conn.commit()
    return n_q, n_c


def adopt(db: QuestionBankDB, root: Path, slug: str) -> int:
    course_dir = root / slug
    exam = course_dir / "exam.json"
    if not course_dir.is_dir():
        sys.exit(f"No such course: {slug}  (looked in {root})")
    if not exam.is_file():
        sys.exit(f"Course '{slug}' has no exam.json")

    title = course_title(course_dir, slug)
    cert = Certification(
        name=title,
        description=f"Adopted from PCM course '{slug}'",
        source_type="pcm",
        source_ref=slug,
    )
    db.save_certification(cert)

    questions = import_from_pcm_exam_json(exam)
    source_ids = [q.get("id") for q in
                  json.loads(exam.read_text(encoding="utf-8")).get("questions", [])]

    for q in questions:
        q.certification_id = cert.id
        db.save(q)

    # Prove the ids landed unchanged rather than assuming it.
    stored = [row[0] for row in db.conn.execute(
        "SELECT id FROM questions WHERE certification_id = ?", (cert.id,)
    )]
    missing = [i for i in source_ids if i not in stored]
    if missing:
        sys.exit(f"{slug}: {len(missing)} ids did not survive the import: {missing[:5]}")

    print(f"  {slug:32} {len(questions):3} questions -> '{title}'")
    return len(questions)


def main() -> None:
    ap = argparse.ArgumentParser(description="Adopt PCM course exams into the bank.")
    ap.add_argument("slugs", nargs="+", help="PCM course slugs")
    ap.add_argument("--clean", action="store_true", help="empty the bank first")
    args = ap.parse_args()

    root = courses_dir()
    db = QuestionBankDB(DB_PATH)
    try:
        if args.clean:
            saved = backup_db()
            if saved:
                print(f"Backed up the database to {saved}")
            n_q, n_c = clean(db)
            print(f"Cleaned: removed {n_q} questions and {n_c} certifications\n")

        print("Adopting:")
        total = sum(adopt(db, root, slug) for slug in args.slugs)

        n_q = db.conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        n_c = db.conn.execute("SELECT COUNT(*) FROM certifications").fetchone()[0]
        print(f"\nBank now holds {n_q} questions across {n_c} certifications "
              f"({total} adopted this run).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
