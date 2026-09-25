"""Content Manager courses — what is available to generate from or adopt.

Everything here resolves the course against the configured courses directory
**at request time**. No slug is ever stored and trusted later: a cached slug
that quietly stopped resolving is how this app's original two certifications
died when the courses were renamed under them, and it failed by returning an
empty list rather than by saying anything.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...core import course_sync
from ...core.bank import ExamBankDB
from ...core.context_budget import source_budget_chars
from ...core.pcm_reader import list_pcm_courses, list_pcm_labs, load_pcm_course
from ...core import distribution
from ...core.publisher import PublishRefused, apply as apply_publish, plan as plan_publish
from ...utils.config import ASSETS_DIR, config
from ..deps import courses_dir, get_db

router = APIRouter(tags=["courses"])


def _course_dir(slug: str) -> Path:
    root = courses_dir()
    # Resolve and confine: a slug is a path segment from a client, and
    # "../../etc" must not escape the courses directory.
    candidate = (root / slug).resolve()
    if candidate.parent != root.resolve() or not candidate.is_dir():
        known = [c["slug"] for c in list_pcm_courses(root)]
        raise HTTPException(
            404, f"No course '{slug}' in {root}. Available: {', '.join(known) or 'none'}"
        )
    return candidate


@router.get("/api/courses")
def list_courses() -> list[dict[str, Any]]:
    """Every course, with whether it has an exam and how big its pool is."""
    root = courses_dir()
    out = []
    for course in list_pcm_courses(root):
        exam = root / course["slug"] / "exam.json"
        pool = 0
        if exam.is_file():
            try:
                data = json.loads(exam.read_text(encoding="utf-8"))
                questions = data.get("questions")
                pool = len(questions) if isinstance(questions, list) else 0
            except (ValueError, OSError):
                pool = 0
        out.append({**course, "hasExam": exam.is_file(), "questionCount": pool})
    return out


@router.get("/api/courses/{slug}/labs")
def list_labs(slug: str) -> list[dict[str, Any]]:
    _course_dir(slug)
    return list_pcm_labs(courses_dir(), slug)


@router.get("/api/courses/{slug}/sections")
def list_sections(slug: str, lab: str = "") -> dict[str, Any]:
    """The course read as the sections a question can be generated from.

    Returns what the generator would be given — the same split, the same
    cleaning — so an author can see the material before spending a model call
    on it, and can tell an empty result from a thin one.

    Each section also says whether it fits the model's context window. A
    section that does not is **truncated silently** by Ollama: the questions
    come back thinner than the material deserved, with nothing anywhere to say
    why. Reported rather than prevented, because the right fix depends on the
    material — a larger window, a smaller model, or splitting the section.
    """
    _course_dir(slug)
    num_ctx = int(getattr(config, "ollama_num_ctx", 0) or 0)
    budget = source_budget_chars(num_ctx)
    # Split with the same budget that is reported, so what is listed is what
    # the generator will actually be handed.
    sections = load_pcm_course(courses_dir(), slug, lab_slug=lab, max_chars=budget)

    return {
        "budget": {
            # 0 means no configured window: Ollama falls back to the model's
            # own default, which this app does not know, so nothing is flagged
            # rather than flagged against a number that was made up.
            "chars": budget,
            "numCtx": num_ctx,
            "model": config.ollama_model,
        },
        "sections": [
            {
                "index": s.index,
                "title": s.title,
                "characters": len(s.speaker_notes or ""),
                "exceedsContext": bool(budget) and len(s.speaker_notes or "") > budget,
                "preview": (s.speaker_notes or "")[:280],
            }
            for s in sections
        ],
    }


@router.get("/api/courses/{slug}/exam")
def get_course_exam(slug: str) -> dict[str, Any]:
    """A course's exam as it stands on disk — settings summary plus the pool.

    The settings are reported, never written: they belong to the Content
    Editor. This app owns `questions`.
    """
    course = _course_dir(slug)
    exam = course / "exam.json"
    if not exam.is_file():
        return {"exists": False, "questionCount": 0}
    try:
        data = json.loads(exam.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        raise HTTPException(422, f"{slug}/exam.json could not be read: {e}")
    questions = data.get("questions")
    questions = questions if isinstance(questions, list) else []
    return {
        "exists": True,
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "passMark": data.get("passMark"),
        "questionsPerAttempt": data.get("questionsPerAttempt"),
        "shuffle": data.get("shuffle"),
        "questionCount": len(questions),
        "questions": questions,
    }


class PublishRequest(BaseModel):
    """Which questions to put into a course's exam, and what the caller
    believes the file currently is."""

    certification_id: str = ""
    status: str = "approved"
    # The hash the caller was shown a plan for. Required on the write, so a
    # publish cannot happen without somebody having looked at one first.
    expect_sha: str = ""
    #: Also push the exam to the courses repo installed apps sync from. See
    #: core/distribution.py. Off unless asked for: it publishes to a remote.
    push: bool = False


def _publish_plan(slug: str, body: PublishRequest, db: ExamBankDB):
    """The shared half of plan-and-apply: select, check the pairing, plan.

    Written once because the plan the author reviews and the plan that gets
    written must be produced the same way. Two code paths here would mean the
    reviewed diff and the applied diff could differ, which is the one thing a
    dry run exists to rule out.
    """
    # Resolve the slug FIRST. A course that has been renamed away must say so
    # and name the ones that exist — otherwise the pairing check below answers
    # instead, and "adopted from demo-course, not renamed-away" reads as a
    # mismatched pair when the real problem is that the target is gone.
    exam_path = _course_dir(slug) / "exam.json"

    if not body.certification_id:
        raise HTTPException(
            400,
            "An exam.json belongs to one course, so publishing needs a "
            "certification to take the questions from.",
        )

    certification = db.get_certification(body.certification_id)
    if certification is None:
        raise HTTPException(404, f"No certification '{body.certification_id}'.")

    # A certification adopted from a course remembers which one. Publishing it
    # into a different course would overwrite a pool that has nothing to do
    # with it, and the ids would not collide, so the result would look like a
    # successful publish of the wrong questions.
    linked = (certification.source_ref or "").strip()
    if linked and linked != slug:
        raise HTTPException(
            409,
            f"'{certification.name}' was adopted from '{linked}', not '{slug}'. "
            "Publishing it here would replace a different course's pool.",
        )

    questions = db.search(
        certification_id=body.certification_id, status=body.status, limit=5000
    )
    try:
        return plan_publish(exam_path, questions, source_label=certification.name)
    except PublishRefused as e:
        # 409, not 400: the request is well formed and the caller is not wrong
        # to have made it - the course or the selection is in a state that
        # makes writing the wrong thing to do.
        raise HTTPException(409, str(e)) from e


def _plan_json(slug: str, made) -> dict[str, Any]:
    return {
        "courseId": slug,
        "path": str(made.path),
        # The caller hands this back on the write. See publisher.apply.
        "sourceSha": made.source_sha,
        "isNoop": made.is_noop,
        "beforeCount": made.before_count,
        "afterCount": made.after_count,
        "added": made.added,
        "removed": made.removed,
        "changed": [{"id": c.id, "fields": c.fields} for c in made.changed],
        "unchanged": made.unchanged,
        "reordered": made.reordered,
        # Key NAMES only. Several of these hold credentials, and the point is
        # to show the author they survived, not to show their values.
        "preservedKeys": made.preserved_keys,
        # Both empty unless the pool-size numeral in the description has to
        # move. Sent as before/after prose so the author reads the actual
        # sentence rather than being told a number changed somewhere.
        "descriptionBefore": made.description_before,
        "descriptionAfter": made.description_after,
    }


def _preflight(slug: str) -> "distribution.Preflight":
    return distribution.preflight(
        courses_dir(), slug,
        repo_url=config.courses_repo_url, repo_ref=config.courses_repo_ref,
    )


def _push_preview(slug: str) -> dict[str, Any]:
    """Whether the exam could also be pushed, and to which version - or, if
    not, the reason, in the author's terms. Never raises: a push that is not
    possible still leaves an ordinary publish possible."""
    try:
        return _preflight(slug).as_dict()
    except distribution.DistributionRefused as e:
        return {"available": False, "reason": str(e)}


def _course_title(slug: str) -> str:
    try:
        data = json.loads((_course_dir(slug) / "course.json").read_text(encoding="utf-8"))
        return str(data.get("title") or slug)
    except (OSError, ValueError):
        return slug


@router.post("/api/courses/{slug}/exam/questions/plan")
def plan_course_exam_questions(
    slug: str, body: PublishRequest, db: ExamBankDB = Depends(get_db)
) -> dict[str, Any]:
    """What publishing would change in the course's exam.json. Writes nothing."""
    return {**_plan_json(slug, _publish_plan(slug, body, db)), "push": _push_preview(slug)}


@router.post("/api/courses/{slug}/exam/questions")
def publish_course_exam_questions(
    slug: str, body: PublishRequest, db: ExamBankDB = Depends(get_db)
) -> dict[str, Any]:
    """Replace the course's ``questions`` array with the bank's.

    ``expect_sha`` is required rather than optional: it is the hash returned
    by the plan endpoint, so a write cannot be issued by a client that never
    asked what it was about to change. It also closes the race with the
    Content Editor, which writes this same file in whole.
    """
    if not body.expect_sha:
        raise HTTPException(
            400,
            "Publishing needs the sourceSha from a plan. Ask "
            f"/api/courses/{slug}/exam/questions/plan first, and pass back the "
            "sourceSha it returned.",
        )

    made = _publish_plan(slug, body, db)

    # Everything a push can know in advance is checked BEFORE the write, so a
    # refusal leaves the course file exactly as it was.
    pre = None
    if body.push:
        try:
            pre = _preflight(slug)
        except distribution.DistributionRefused as e:
            raise HTTPException(409, str(e)) from e

    try:
        apply_publish(made, expect_sha=body.expect_sha)
    except PublishRefused as e:
        raise HTTPException(409, str(e)) from e
    result = {**_plan_json(slug, made), "written": True}

    if pre is not None:
        summary = {
            "added": made.added,
            "changed": [c.id for c in made.changed],
            "removed": made.removed,
            "afterCount": made.after_count,
        }
        try:
            result["push"] = distribution.release(
                pre, slug, _course_title(slug), summary, ASSETS_DIR / "cache")
        except distribution.DistributionRefused as e:
            # The file is written; the push stopped before anything left the
            # machine. Said as such rather than as a failed publish.
            result["push"] = {"error": str(e), "failedAt": "before-push"}
    return result


class SyncRequest(BaseModel):
    """Which sync to run, and proof that one was looked at first."""

    #: The token from `/api/courses/sync/plan`. Required, for the same reason
    #: publishing requires a sourceSha: between looking and acting somebody
    #: may have pulled the courses repo.
    token: str = ""
    #: Overwrite questions the bank has since edited. Off by default, and
    #: deliberately awkward to reach: the bank is the editing tool for these
    #: questions, and a routine refresh that reverted an author's work would
    #: make it unsafe to use.
    overwrite_changed: bool = False
    #: Limit the sync to these course slugs. Empty means every course.
    only: list[str] = []


@router.post("/api/courses/sync/plan")
def plan_course_sync(db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    """What adopting every course's exam would do to the bank. Writes nothing."""
    return course_sync.plan(courses_dir(), db).as_dict()


@router.post("/api/courses/sync")
def run_course_sync(
    body: SyncRequest, db: ExamBankDB = Depends(get_db)
) -> dict[str, Any]:
    """Adopt what the plan described."""
    if not body.token:
        raise HTTPException(
            400,
            "Syncing needs the token from a plan. Ask "
            "/api/courses/sync/plan first, and pass back the token it returned.",
        )
    try:
        return course_sync.apply(
            courses_dir(), db,
            expect_token=body.token,
            overwrite_changed=body.overwrite_changed,
            only=body.only or None,
        )
    except ValueError as e:
        # 409, not 400: the request was well formed and was correct when it
        # was composed. The world moved.
        raise HTTPException(409, str(e)) from e
