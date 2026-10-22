"""Item analysis: how each question performs with real candidates.

The results Sheet's "Detail" tab holds one row per question per attempt (the
Content Manager's exam webhook writes it): attempt id, course id, when, the
question id, the answer given, the correct answer, and whether it was right.
Imported here, that becomes, per question:

- **% correct** (the classical difficulty, *p*);
- **discrimination**: does the question separate strong candidates from weak
  ones? The correlation between getting it right and the rest of the attempt's
  score (point-biserial, with this question left out of the score it is
  compared with), plus the % correct among the strongest and weakest quarter;
- **how often each option is picked**, so a distractor nobody chooses, or one
  the strongest candidates prefer to the key, shows up.

Attempts draw different subsets of a pool, so ability is each attempt's
PERCENTAGE on the questions it drew, not a raw total.

Privacy: the Detail tab carries the candidate's email; the import never reads
it. An attempt is its id and nothing else.
"""
from __future__ import annotations

import csv
import io
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

#: Below this many attempts a question's numbers are shown but not judged:
#: with a dozen candidates one lucky guess moves % correct by eight points.
MIN_ATTEMPTS = 20
#: The share of attempts in each of the strongest and weakest groups.
GROUP_SHARE = 0.27
EASY_P = 0.90
HARD_P = 0.30
WEAK_DISCRIMINATION = 0.15
#: Below this, stronger candidates really do worse; between it and 0 is noise
#: at the cohort sizes these exams see, and is reported as weak, not wrong.
NEGATIVE_DISCRIMINATION = -0.10
#: A distractor picked by fewer than this share of candidates is doing no work.
DEAD_DISTRACTOR = 0.05

# The Detail tab's headings, as the webhook writes them (DETAIL_HEADERS in the
# Content Manager's docs/EXAM-RESULTS-SETUP.md). Matched case-insensitively.
REQUIRED = {
    "attempt id": "attempt_id",
    "course id": "course_id",
    "question id": "question_id",
    "user answer": "user_answer",
    "correct answer": "correct_answer",
    "was correct?": "was_correct",
}
OPTIONAL = {"submitted at": "submitted_at"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS responses (
    attempt_id TEXT NOT NULL,
    question_id TEXT NOT NULL,
    course_id TEXT NOT NULL DEFAULT '',
    submitted_at TEXT NOT NULL DEFAULT '',
    user_answer TEXT NOT NULL DEFAULT '',
    correct_answer TEXT NOT NULL DEFAULT '',
    was_correct INTEGER NOT NULL DEFAULT 0,
    imported_at TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (attempt_id, question_id)
);
CREATE INDEX IF NOT EXISTS idx_responses_course ON responses(course_id);
CREATE INDEX IF NOT EXISTS idx_responses_question ON responses(question_id);

-- One row per exam attempt, from the results workbook's attempt tabs (see
-- results_workbook.py). No name, email or notes: a candidate is an opaque id.
CREATE TABLE IF NOT EXISTS attempts (
    attempt_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL DEFAULT '',
    course_id TEXT NOT NULL DEFAULT '',
    course_tab TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT '',
    submitted_at TEXT NOT NULL DEFAULT '',
    company TEXT NOT NULL DEFAULT '',
    score REAL,
    total REAL,
    percentage REAL,
    passed INTEGER,
    partner_id TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_attempts_course ON attempts(course_id);
CREATE INDEX IF NOT EXISTS idx_attempts_candidate ON attempts(candidate_id);
"""


class ResultsImportError(ValueError):
    """The file is not a Detail export; the message says what is missing."""


def parse_detail_csv(text: str) -> list[dict[str, Any]]:
    """Rows of the Detail tab, by the fields analysis uses. Emails are skipped."""
    text = text.lstrip("﻿")
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise ResultsImportError("The file is empty.")
    index = {h.strip().lower(): i for i, h in enumerate(header)}
    missing = [h for h in REQUIRED if h not in index]
    if missing:
        raise ResultsImportError(
            "This is not the results Sheet's Detail tab: it has no "
            + ", ".join(f'"{m.title()}"' for m in missing)
            + " column. In the Sheet, open the Detail tab, then File > Download > "
            "Comma-separated values."
        )
    fields = {**REQUIRED, **{k: v for k, v in OPTIONAL.items() if k in index}}
    rows = []
    for line in reader:
        if not any(cell.strip() for cell in line):
            continue
        row = {name: (line[index[h]].strip() if index[h] < len(line) else "") for h, name in fields.items()}
        if not row["attempt_id"] or not row["question_id"]:
            continue
        mark = row["was_correct"].strip().upper()
        if mark == "-":
            # Not marked: the service graded this attempt against keys the
            # question no longer matches (edited since). Neither right nor wrong.
            continue
        row["was_correct"] = 1 if mark in ("Y", "YES", "TRUE", "1") else 0
        row.setdefault("submitted_at", "")
        rows.append(row)
    return rows


def ensure_schema(conn) -> None:
    conn.executescript(SCHEMA)


def import_rows(conn, rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Upsert by (attempt, question): importing the same export twice changes nothing."""
    ensure_schema(conn)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = list(rows)
    before = conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0]
    conn.executemany(
        "INSERT INTO responses (attempt_id, question_id, course_id, submitted_at, user_answer, "
        "correct_answer, was_correct, imported_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(attempt_id, question_id) DO UPDATE SET course_id=excluded.course_id, "
        "submitted_at=excluded.submitted_at, user_answer=excluded.user_answer, "
        "correct_answer=excluded.correct_answer, was_correct=excluded.was_correct, "
        "imported_at=excluded.imported_at",
        [(r["attempt_id"], r["question_id"], r["course_id"], r["submitted_at"], r["user_answer"],
          r["correct_answer"], r["was_correct"], now) for r in rows],
    )
    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0]
    return {
        "rows": len(rows),
        "added": after - before,
        "attempts": len({r["attempt_id"] for r in rows}),
        "courses": sorted({r["course_id"] for r in rows if r["course_id"]}),
        "totalResponses": after,
    }


def _pearson(xs: list[float], ys: list[float]) -> Optional[float]:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sxx * syy)


def split_answer(answer: str, options: list[str]) -> list[str]:
    """The options a recorded answer names. A multi-select answer is the
    chosen texts joined with "; ", but an option may itself contain "; ", so
    known options are matched whole (longest first) before splitting."""
    answer = answer.strip()
    if not answer:
        return []
    if answer in options:
        return [answer]
    found, rest = [], answer
    for opt in sorted(options, key=len, reverse=True):
        if opt and opt in rest:
            found.append(opt)
            rest = rest.replace(opt, "")
    leftover = [p.strip() for p in rest.split(";") if p.strip()]
    return found + leftover


def analyse(db, certification_id: str = "", attempt_ids: Optional[set[str]] = None) -> dict[str, Any]:
    """Per exam, per question: attempts, % correct, discrimination, option use, flags.

    `attempt_ids` narrows the analysis to those attempts (the Results view's
    filters); None means all of them.
    """
    conn = db.conn
    ensure_schema(conn)
    certs = {c.source_ref: c for c in db.list_certifications() if getattr(c, "source_ref", "")}
    rows = conn.execute(
        "SELECT attempt_id, question_id, course_id, submitted_at, user_answer, correct_answer, was_correct "
        "FROM responses"
    ).fetchall()
    if attempt_ids is not None:
        rows = [r for r in rows if r[0] in attempt_ids]

    by_course: dict[str, list] = defaultdict(list)
    for r in rows:
        by_course[r[2]].append(r)

    exams = []
    for course_id, course_rows in sorted(by_course.items()):
        cert = certs.get(course_id)
        if certification_id and (not cert or cert.id != certification_id):
            continue
        # Ability: each attempt's score on what it drew.
        per_attempt: dict[str, list[int]] = defaultdict(list)
        for r in course_rows:
            per_attempt[r[0]].append(r[6])
        totals = {a: (sum(v), len(v)) for a, v in per_attempt.items()}

        questions = {}
        if cert:
            for q in db.search(certification_id=cert.id, limit=100000):
                questions[q.id] = q

        by_question: dict[str, list] = defaultdict(list)
        for r in course_rows:
            by_question[r[1]].append(r)

        items = []
        for qid, qrows in by_question.items():
            q = questions.get(qid)
            n = len(qrows)
            correct = sum(r[6] for r in qrows)
            p = correct / n if n else None
            # Rest score: the attempt's % on everything it drew EXCEPT this
            # question, so a question is not compared with itself.
            rest = []  # (rest score, right 0/1, attempt id)
            for r in qrows:
                got, drawn = totals[r[0]]
                if drawn > 1:
                    rest.append(((got - r[6]) / (drawn - 1), float(r[6]), r[0]))
            disc = _pearson([c for _, c, _ in rest], [s for s, _, _ in rest])
            ranked = sorted(rest, key=lambda t: t[0])
            k = max(1, round(len(ranked) * GROUP_SHARE)) if len(ranked) >= 4 else 0
            lower_p = sum(c for _, c, _ in ranked[:k]) / k if k else None
            upper_p = sum(c for _, c, _ in ranked[-k:]) / k if k else None
            upper_attempts = {a for _, _, a in ranked[-k:]} if k else set()

            keys = (q.keys if q and q.question_type == "multi" and q.keys else ([q.key] if q else []))
            options = list(dict.fromkeys([*keys, *(q.distractors if q else [])]))
            counts: dict[str, int] = defaultdict(int)
            upper_counts: dict[str, int] = defaultdict(int)
            blank = 0
            for r in qrows:
                chosen = split_answer(r[4], options)
                if not chosen:
                    blank += 1
                for c in chosen:
                    counts[c] += 1
                    if r[0] in upper_attempts:
                        upper_counts[c] += 1
            other = {c: v for c, v in counts.items() if c not in options}
            option_rows = [{
                "text": o,
                "correct": o in keys,
                "chosen": counts.get(o, 0),
                "share": round(counts.get(o, 0) / n, 3) if n else 0,
                "upperChosen": upper_counts.get(o, 0),
            } for o in options]
            stale = sum(1 for r in qrows if q and r[5] and r[5] != "; ".join(keys) and r[5] not in keys)

            flags = []
            enough = n >= MIN_ATTEMPTS
            if q is None:
                flags.append({"level": "info", "text": "No longer in the bank under this id."})
            if not enough:
                flags.append({"level": "info", "text": f"{n} attempt{'s' if n != 1 else ''} so far; "
                              f"judged from {MIN_ATTEMPTS}."})
            else:
                if p is not None and p >= EASY_P:
                    flags.append({"level": "warn", "text": f"Very easy: {round(p * 100)}% get it right."})
                if p is not None and p <= HARD_P:
                    flags.append({"level": "warn", "text": f"Very hard: only {round(p * 100)}% get it right."})
                if disc is not None and disc < NEGATIVE_DISCRIMINATION:
                    flags.append({"level": "bad", "text": "Stronger candidates get it wrong more often than "
                                  "weaker ones. Check the key and the wording."})
                elif disc is not None and disc < WEAK_DISCRIMINATION:
                    flags.append({"level": "warn", "text": "Barely separates strong candidates from weak ones."})
                for o in option_rows:
                    if not o["correct"] and o["share"] < DEAD_DISTRACTOR:
                        flags.append({"level": "info", "text": f'Distractor rarely chosen ({o["chosen"]} of {n}): '
                                      f'"{o["text"][:60]}"'})
                key_upper = max((o["upperChosen"] for o in option_rows if o["correct"]), default=0)
                for o in option_rows:
                    if not o["correct"] and k and o["upperChosen"] > key_upper:
                        flags.append({"level": "bad", "text": f'The strongest candidates prefer a distractor to '
                                      f'the key: "{o["text"][:60]}". Check the key.'})
            if stale:
                flags.append({"level": "info", "text": f"{stale} of these attempts were marked against an "
                              "earlier correct answer; the question has been edited since."})
            if other:
                flags.append({"level": "info", "text": f"{sum(other.values())} answers name an option the "
                              "question no longer has."})

            items.append({
                "id": qid,
                "stem": q.stem if q else "",
                "topic": q.topic if q else "",
                "difficulty": q.difficulty if q else "",
                "poolOrder": q.pool_order if q else 10 ** 6,
                "attempts": n,
                "correct": correct,
                "p": round(p, 3) if p is not None else None,
                "discrimination": round(disc, 2) if disc is not None else None,
                "upperP": round(upper_p, 3) if upper_p is not None else None,
                "lowerP": round(lower_p, 3) if lower_p is not None else None,
                "suggestedDifficulty": (None if not enough or p is None
                                        else "Easy" if p >= 0.8 else "Hard" if p < 0.45 else "Medium"),
                "options": option_rows,
                "blank": blank,
                "flags": flags,
            })
        items.sort(key=lambda it: (it["poolOrder"], it["id"]))
        scores = [got / drawn for got, drawn in totals.values() if drawn]
        submitted = sorted(r[3] for r in course_rows if r[3])
        exams.append({
            "courseId": course_id,
            "certificationId": cert.id if cert else "",
            "name": cert.name if cert else course_id,
            "attempts": len(totals),
            "meanScore": round(sum(scores) / len(scores), 3) if scores else None,
            "firstAttempt": submitted[0] if submitted else "",
            "lastAttempt": submitted[-1] if submitted else "",
            "judged": sum(1 for it in items if it["attempts"] >= MIN_ATTEMPTS),
            "flagged": sum(1 for it in items if any(f["level"] in ("warn", "bad") for f in it["flags"])),
            "items": items,
        })
    return {
        "minAttempts": MIN_ATTEMPTS,
        "totalResponses": len(rows),
        "exams": exams,
    }
