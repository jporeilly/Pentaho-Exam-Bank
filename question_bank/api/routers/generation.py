"""Generate questions from course content, and commit the ones worth keeping.

Generation runs as a background job (see ``api.jobs``): a course is dozens of
model calls and minutes of work. Nothing reaches the bank until the author
commits it — a generated question is a draft proposal, not a saved one.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ...core.context_budget import source_budget_chars
from ...core.generation_prompts import specs_from_rows
from ...core.pcm_reader import list_pcm_courses, load_pcm_course
from ...core.question_bank import BLOOM_LEVELS, DIFFICULTIES, QuestionBankDB
from ...core.question_generation import generate_questions_batch
from ...utils.config import config
from .. import jobs
from ..deps import courses_dir, get_db, question_json

router = APIRouter(tags=["generation"])


class QuestionFormat(BaseModel):
    """One question shape: how many answers are right, and how many wrong."""

    keys: int = Field(1, ge=1, le=4)
    distractors: int = Field(3, ge=1, le=6)


class GenerateRequest(BaseModel):
    course_slug: str
    lab_slug: str = ""
    certification_id: str = ""
    # How many questions in total, spread across the course's sections. The
    # alternative — a fixed count per section — makes the size of the pool an
    # accident of how the guide happens to be split up.
    total: int = Field(20, ge=1, le=500)
    difficulty: str = "Medium"
    bloom_levels: list[str] = Field(default_factory=lambda: ["Apply"])
    num_keys: int = Field(1, ge=1, le=4)
    num_distractors: int = Field(3, ge=1, le=5)
    # Question shapes to cycle through, so one run can mix "choose one of
    # four" with "choose two of five". Empty means every question takes the
    # single num_keys/num_distractors shape above — which is also why
    # shuffle_formats does nothing without this: shuffling one repeated shape
    # changes nothing.
    formats: list[QuestionFormat] = Field(default_factory=list)
    custom_instructions: str = ""
    shuffle_formats: bool = False
    # Empty means "whatever the configured provider is set to". Naming one
    # here is how two models are compared on the same material.
    model: str = ""


@router.post("/api/generate", status_code=202)
def start_generation(req: GenerateRequest) -> dict[str, Any]:
    """Start generating, and return the job to poll.

    The course is resolved and read **before** the job starts, so a bad slug
    or an empty course is a 4xx the author sees at once rather than a job that
    starts, runs and fails.
    """
    root = courses_dir()
    known = {c["slug"] for c in list_pcm_courses(root)}
    if req.course_slug not in known:
        raise HTTPException(
            404,
            f"No course '{req.course_slug}'. Available: {', '.join(sorted(known)) or 'none'}",
        )
    if req.difficulty not in DIFFICULTIES:
        raise HTTPException(400, f"difficulty must be one of {DIFFICULTIES}")
    unknown = [b for b in req.bloom_levels if b not in BLOOM_LEVELS]
    if unknown:
        raise HTTPException(400, f"unknown Bloom level(s) {unknown}; expected {BLOOM_LEVELS}")

    # The same split the Courses pane lists, so an author generates from
    # exactly the sections they were shown.
    budget = source_budget_chars(int(getattr(config, "ollama_num_ctx", 0) or 0))
    sections = load_pcm_course(
        root, req.course_slug, lab_slug=req.lab_slug, max_chars=budget
    )
    if not sections:
        where = f"{req.course_slug}/{req.lab_slug}" if req.lab_slug else req.course_slug
        raise HTTPException(
            422,
            f"{where} has no sections with enough prose to write a question from.",
        )

    # Built here, not in the job, so a request asking only for shapes that
    # make no sense is a 400 the author sees rather than a run that quietly
    # falls back to the default shape.
    specs = specs_from_rows([f.model_dump() for f in req.formats])
    if req.formats and not specs:
        raise HTTPException(
            400, "Every question format needs at least one correct and one wrong answer."
        )

    def work(job: jobs.Job) -> list:
        job.progress(0, len(sections), f"Reading {req.course_slug}…")
        return generate_questions_batch(
            slides=sections,
            model=req.model,
            base_url=config.ollama_url,
            difficulty=req.difficulty,
            bloom_level=req.bloom_levels or ["Apply"],
            certification_id=req.certification_id,
            source_file=f"pcm:{req.course_slug}",
            num_keys=req.num_keys,
            num_distractors=req.num_distractors,
            custom_instructions=req.custom_instructions,
            target_total=req.total,
            shuffle_formats=req.shuffle_formats,
            question_specs=specs or None,
            progress_callback=job.progress,
        )

    job = jobs.start("generate", work, requested=req.total)
    return {"jobId": job.id, "sections": len(sections), "status": job.status}


@router.get("/api/jobs")
def list_jobs() -> list[dict[str, Any]]:
    """Jobs without their results — a list for a status area, not a payload."""
    return [j.as_json() for j in jobs.all_jobs()]


@router.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"No job '{job_id}'")
    return job.as_json(serialise=question_json)


@router.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, Any]:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"No job '{job_id}'")
    if not jobs.cancel(job_id):
        raise HTTPException(409, f"Job is already {job.status}")
    return {"ok": True, "id": job_id}


class CommitRequest(BaseModel):
    # Which of the job's questions to keep, by id. Empty means all of them.
    question_ids: list[str] = Field(default_factory=list)
    certification_id: str = ""


@router.post("/api/jobs/{job_id}/commit")
def commit_job(
    job_id: str, body: CommitRequest, db: QuestionBankDB = Depends(get_db)
) -> dict[str, Any]:
    """Save a finished job's questions into the bank.

    Committing is separate from generating because a model's output is a
    proposal. A question is saved when the author has looked at it, and
    generating a hundred must not put a hundred into the bank.
    """
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"No job '{job_id}'")
    if job.status == jobs.RUNNING:
        raise HTTPException(409, "That job is still running.")
    if job.status == jobs.ERROR:
        raise HTTPException(409, f"That job failed: {job.error}")

    wanted = set(body.question_ids)
    chosen = [q for q in job.result if not wanted or q.id in wanted]
    missing = wanted - {q.id for q in job.result}
    if missing:
        raise HTTPException(404, f"Job has no question(s) {sorted(missing)}")

    for question in chosen:
        if body.certification_id:
            question.certification_id = body.certification_id
        db.save(question)

    return {"ok": True, "saved": len(chosen), "jobId": job_id}
