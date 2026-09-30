"""Adopt every Content Manager course's exam into the bank, and keep it current.

A fresh install opens on an empty bank while 398 questions sit in the courses
the installer just found. Nothing was wrong with either half — the installer
ships no database (it is the author's data, not ours), and the questions live
in `courses/<slug>/exam.json` in git, which is the source of truth. They were
simply never introduced.

`scripts/migrate_pcm_exams.py` did this as a one-off and is left alone: it
mints a NEW certification on every run, which is right for a migration you
perform once and wrong for a sync you perform whenever the courses move. This
module is the repeatable half.

Look-then-act, like publishing: `plan()` reads and reports and writes nothing,
`apply()` takes the plan's token and refuses if the courses have changed since
it was produced. The token is a hash over each course's exam.json, so "the
files moved under you" is caught rather than silently applied.

**A sync never reverts an edit by default.** A question already in the bank
whose content differs from the course's copy is reported as `changed` and
SKIPPED unless the caller explicitly opts in. The bank is an editing tool; the
whole reason these questions were adopted is that they had nowhere else to be
edited. Quietly overwriting that on a routine refresh would make the tool
unsafe to use, and the author would have no way of knowing it had happened.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .bank import Certification, ExamBankDB, Question
from .pcm_reader import read_course_json
from .question_importer import import_from_pcm_exam_json
from .stem_text import question_only
from .validation import problems_with

#: Only these fields are compared when deciding whether a question has moved.
#: Deliberately NOT status, review history, assignee or timestamps: those are
#: the bank's own workmanship and a course file knows nothing about them. A
#: question adopted as a draft and since approved must read as `unchanged`,
#: or every sync would offer to undo the review.
#:
#: These are ATTRIBUTE names on Question, not column names in the questions
#: table, because `_fingerprint` reads them with getattr. The two differ:
#: the columns are `key_answer` and `keys_json`, the attributes `key` and
#: `keys`. This list held the column names until 2026-09-25, and since
#: getattr was given a default, both contributed None to every fingerprint
#: ever taken - ten named fields doing the work of eight.
#:
#: It never lost an answer-key change, and it is worth being exact about why,
#: because the reason is luck rather than design: for a PCM question the key
#: and the distractors partition the options, so moving `correct` changes the
#: distractor set too and `distractors` caught it. The fingerprint was right
#: about the answer by accident. `test_every_content_field_exists_on_question`
#: fails on a name that does not resolve, so the next one is caught when it is
#: written rather than whenever something stops being masked.
#:
#: `bloom_level` is here because a course file states it outright. Not
#: `difficulty`: no course sets one, so the importer's default would be the
#: only thing compared, and if it ever becomes an SME judgement in the bank
#: this list is where that decision gets made.
_CONTENT_FIELDS = (
    "scenario", "stem", "question_type", "key", "keys",
    "distractors", "option_order", "explanation", "topic", "pool_order",
    "bloom_level",
)


def _fingerprint(q: Question) -> str:
    # The stem is compared as the question only. Publishing drops a count
    # directive, so a bank stem ending "(Choose one.)" and the course prompt
    # it was published as say the same thing, and must not come back from
    # the course looking changed.
    parts = []
    for name in _CONTENT_FIELDS:
        value = getattr(q, name, None)
        if name == "stem":
            value = question_only(value or "")
        parts.append(json.dumps(value, sort_keys=True, default=str))
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _course_title(course_dir: Path, slug: str) -> str:
    cj = course_dir / "course.json"
    if cj.is_file():
        try:
            data = read_course_json(cj)
            if isinstance(data, dict) and str(data.get("title", "")).strip():
                return str(data["title"]).strip()
        except (ValueError, OSError):
            pass
    return slug


@dataclass
class CourseOutcome:
    """What a sync would do to one course's questions."""

    slug: str
    title: str = ""
    exam_sha: str = ""
    certification_id: str = ""
    certification_name: str = ""
    new: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    unusable: list[dict[str, str]] = field(default_factory=list)
    #: Ids this course shares with another course. Refused, never written.
    conflicts: list[dict[str, str]] = field(default_factory=list)
    error: str = ""

    @property
    def in_course(self) -> int:
        return (len(self.new) + len(self.changed) + len(self.unchanged)
                + len(self.unusable) + len(self.conflicts))

    def as_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "title": self.title,
            "examSha": self.exam_sha,
            "certificationId": self.certification_id,
            "certificationName": self.certification_name,
            "adopted": bool(self.certification_id),
            "inCourse": self.in_course,
            "new": len(self.new),
            "changed": len(self.changed),
            "unchanged": len(self.unchanged),
            "unusable": self.unusable,
            "conflicts": self.conflicts,
            "changedIds": self.changed[:50],
            "error": self.error,
        }


@dataclass
class SyncPlan:
    """Every course the bank can see, and what adopting them would do."""

    courses_dir: str
    courses: list[CourseOutcome] = field(default_factory=list)
    token: str = ""

    @property
    def total_new(self) -> int:
        return sum(len(c.new) for c in self.courses)

    @property
    def total_changed(self) -> int:
        return sum(len(c.changed) for c in self.courses)

    def as_dict(self) -> dict[str, Any]:
        return {
            "coursesDir": self.courses_dir,
            "token": self.token,
            "courses": [c.as_dict() for c in self.courses],
            "totalNew": self.total_new,
            "totalChanged": self.total_changed,
            "totalUnchanged": sum(len(c.unchanged) for c in self.courses),
            "totalUnusable": sum(len(c.unusable) for c in self.courses),
            "totalConflicts": sum(len(c.conflicts) for c in self.courses),
        }


def _token(courses: list[CourseOutcome]) -> str:
    """A hash over what was READ, so an apply can prove it saw this.

    Built from the exam.json hashes rather than from the plan's counts: two
    different sets of files can produce the same counts, and the point of the
    token is to detect the files moving, not the summary matching.
    """
    material = "\n".join(f"{c.slug}:{c.exam_sha}" for c in sorted(courses, key=lambda c: c.slug))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _read_course(course_dir: Path, db: ExamBankDB,
                 certs_by_ref: dict[str, Certification]) -> CourseOutcome | None:
    """One course's outcome, or None when it has no exam to adopt."""
    slug = course_dir.name
    exam = course_dir / "exam.json"
    if not exam.is_file():
        return None

    outcome = CourseOutcome(slug=slug, title=_course_title(course_dir, slug))
    try:
        raw = exam.read_bytes()
    except OSError as e:
        outcome.error = f"could not be read: {e}"
        return outcome
    outcome.exam_sha = hashlib.sha256(raw).hexdigest()

    cert = certs_by_ref.get(slug)
    if cert:
        outcome.certification_id = cert.id
        outcome.certification_name = cert.name

    try:
        questions = import_from_pcm_exam_json(exam)
    except Exception as e:  # a malformed course must not take the whole sync down
        outcome.error = f"could not be parsed: {e}"
        return outcome

    # What the FILE claims, against what the importer handed back. The
    # importer drops an entry it cannot make a question out of - an empty
    # prompt, no options - and says nothing. Without this the course holds
    # N questions, the bank adopts N-1, and the only evidence is two numbers
    # that nobody is comparing. Reported rather than raised: one unusable
    # entry should not cost the course its other forty-nine.
    returned = {q.id for q in questions}
    try:
        authored = read_course_json(exam).get("questions", [])
    except (ValueError, OSError):
        authored = []
    for entry in authored if isinstance(authored, list) else []:
        qid = str(entry.get("id", "")) if isinstance(entry, dict) else ""
        if qid and qid not in returned:
            outcome.unusable.append({
                "id": qid,
                "stem": str(entry.get("prompt", ""))[:80] if isinstance(entry, dict) else "",
                "reason": "the importer could not make a question out of it "
                          "(no prompt, or no options)",
            })

    for q in questions:
        problems = problems_with(q)
        if problems:
            # Refused for the same reason /api/import/commit refuses them: the
            # bank's editor will not let an author save one of these, and a
            # sync that can put them in anyway makes that rule a suggestion.
            outcome.unusable.append({
                "id": q.id,
                "stem": q.stem[:80],
                "reason": "; ".join(p.message for p in problems),
            })
            continue
        existing = db.get(q.id)
        if existing is None:
            outcome.new.append(q.id)
        elif _fingerprint(existing) == _fingerprint(q):
            outcome.unchanged.append(q.id)
        else:
            outcome.changed.append(q.id)
    return outcome


def _pcm_certifications(db: ExamBankDB) -> dict[str, Certification]:
    """Existing PCM certifications, keyed by the course slug they came from.

    Keyed on `source_ref` rather than on the name: a course's TITLE is
    authored prose and changes, and matching on it would mint a second
    certification for the same course the first time somebody rewords one.
    """
    out: dict[str, Certification] = {}
    for cert in db.list_certifications():
        if cert.source_type == "pcm" and cert.source_ref:
            out.setdefault(cert.source_ref, cert)
    return out


def _refuse_shared_ids(courses: list[CourseOutcome],
                       claimed: dict[str, list[str]]) -> None:
    """Refuse any question id that more than one course claims.

    Found with real data, not imagined: 30 ids in the live courses are used
    by TWO courses each - `m1-q1` belongs to both architect-install-certified
    and developer-di-practitioner. The ids are hand-authored per course and
    nothing has ever made them unique across courses, because nothing needed
    them to be.

    The bank's questions table is keyed on that id, and `save()` is
    INSERT OR REPLACE. Adopting both courses would therefore have written one
    course's question over the other's, moved it to the wrong certification,
    and reported a completely successful sync: 398 questions in git arriving
    as 365 in the bank, with no error and nothing to compare against.

    Refusing is the only honest option available here. Making them unique
    would mean either rewriting ids the Content Manager keys exam results and
    resume state on, or changing the table's primary key - both real changes
    that somebody has to choose, not something a sync should decide silently
    on their behalf.
    """
    for outcome in courses:
        if outcome.error:
            continue
        shared = []
        for bucket in (outcome.new, outcome.changed, outcome.unchanged):
            for qid in list(bucket):
                others = [c for c in claimed.get(qid, []) if c != outcome.slug]
                if not others:
                    continue
                bucket.remove(qid)
                shared.append({
                    "id": qid,
                    "stem": "",
                    "reason": "also used by " + ", ".join(sorted(others)),
                })
        outcome.conflicts.extend(shared)


def plan(courses_dir: Path | str, db: ExamBankDB) -> SyncPlan:
    """What adopting every course would do. Writes nothing."""
    root = Path(courses_dir)
    result = SyncPlan(courses_dir=str(root))
    if not root.is_dir():
        return result

    certs = _pcm_certifications(db)
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith((".", "_")):
            # `_template` is scaffolding, not a course anyone sits.
            continue
        outcome = _read_course(child, db, certs)
        if outcome is not None:
            result.courses.append(outcome)

    # Which course claims which id, across the whole set. Built here rather
    # than per course because a collision is by definition not visible from
    # inside one of them.
    claimed: dict[str, list[str]] = {}
    for outcome in result.courses:
        for bucket in (outcome.new, outcome.changed, outcome.unchanged):
            for qid in bucket:
                claimed.setdefault(qid, []).append(outcome.slug)
    _refuse_shared_ids(result.courses, claimed)

    result.token = _token(result.courses)
    return result


def apply(courses_dir: Path | str, db: ExamBankDB, expect_token: str = "",
          overwrite_changed: bool = False,
          only: list[str] | None = None) -> dict[str, Any]:
    """Adopt what the plan described.

    `expect_token` is the token from the plan the caller was shown. It is
    required unless empty-by-explicit-choice, and a mismatch refuses: between
    looking and acting, somebody may have pulled the courses repo.
    """
    fresh = plan(courses_dir, db)
    if expect_token and expect_token != fresh.token:
        raise ValueError(
            "The courses changed since that plan was made. Look again before syncing."
        )

    wanted = set(only) if only else None
    certs = _pcm_certifications(db)
    added = updated = skipped = 0
    touched: list[dict[str, Any]] = []

    for outcome in fresh.courses:
        if wanted is not None and outcome.slug not in wanted:
            continue
        if outcome.error:
            continue
        if not outcome.new and not (overwrite_changed and outcome.changed):
            continue

        cert = certs.get(outcome.slug)
        if cert is None:
            cert = Certification(
                name=outcome.title,
                description=f"Adopted from Content Manager course '{outcome.slug}'",
                source_type="pcm",
                source_ref=outcome.slug,
            )
            db.save_certification(cert)
            certs[outcome.slug] = cert

        write_ids = set(outcome.new)
        if overwrite_changed:
            write_ids |= set(outcome.changed)
        else:
            skipped += len(outcome.changed)

        course_added = course_updated = 0
        for q in import_from_pcm_exam_json(Path(courses_dir) / outcome.slug / "exam.json"):
            if q.id not in write_ids:
                continue
            q.certification_id = cert.id
            q.source_type = cert.source_type
            if q.id in outcome.new:
                course_added += 1
            else:
                # Keep the review state. The course file has no opinion about
                # it, and an overwrite that silently reset an approved
                # question to draft would undo review work nobody asked to
                # undo.
                existing = db.get(q.id)
                if existing is not None:
                    q.status = existing.status
                    q.assigned_sme = existing.assigned_sme
                    q.review_history = existing.review_history
                course_updated += 1
            db.save(q)

        added += course_added
        updated += course_updated
        touched.append({
            "slug": outcome.slug,
            "certificationId": cert.id,
            "added": course_added,
            "updated": course_updated,
            "skipped": len(outcome.changed) if not overwrite_changed else 0,
        })

    return {
        "added": added,
        "updated": updated,
        "skippedChanged": skipped,
        "courses": touched,
        "token": plan(courses_dir, db).token,
    }


def bank_is_empty(db: ExamBankDB) -> bool:
    """No questions and no certifications: a bank nothing can be lost from.

    The test for whether a first-run adopt is safe to do without asking. It is
    deliberately stricter than "no questions" — a bank with certifications but
    no questions is one somebody has started organising, and writing into it
    unasked is a different thing from filling an empty one.
    """
    n_q = db.conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    n_c = db.conn.execute("SELECT COUNT(*) FROM certifications").fetchone()[0]
    return n_q == 0 and n_c == 0
