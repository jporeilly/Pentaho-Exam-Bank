"""Build a printable exam paper from the bank, weighted across topics.

Distinct from ``/api/export-exam/pdf``, which prints whatever matches a set of
filters. This one is given a *shape* — forty questions, half Networking, a
quarter each of the other two — and has to reconcile that against a bank that
may not have the questions to fill it.

That reconciliation is the reason for two endpoints rather than one. The
selection silently redistributes: a topic whose pool is too small contributes
what it has and the difference is taken from topics with spare questions, so a
40/30/30 exam can come back 40/45/15 with nothing saying so. ``/plan`` says
what the mix would really be, and is the only place an author can find that
out before the paper is printed and handed to somebody.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi import BackgroundTasks
from pydantic import BaseModel, Field

from ...core.bank import DIFFICULTIES, ExamBankDB
from ...core.exam_builder import Selection, generate_exam_pdf, get_available_topics, plan_exam
from ..deps import get_db
from ..tempfiles import cleanup, temp_path

router = APIRouter(tags=["exam"])

#: Weights are percentages and the selection divides by their total, so they
#: have to add up. A point of slack each way absorbs the rounding an author
#: gets from splitting three ways (34/33/33) without letting 40/30/10 through.
WEIGHT_TOLERANCE = 1.0


class ExamRequest(BaseModel):
    """The shape of the paper, before the bank has had a say in it."""

    certification_ids: list[str] = Field(default_factory=list)
    total_questions: int = Field(20, ge=1, le=500)
    #: {topic: percentage}. Must total 100.
    topic_weights: dict[str, float] = Field(default_factory=dict)
    difficulties: list[str] = Field(default_factory=lambda: list(DIFFICULTIES))
    statuses: list[str] = Field(default_factory=lambda: ["approved"])
    randomize: bool = True
    #: Fixes which questions are drawn, so a paper can be reproduced exactly.
    seed: int | None = None


class PdfRequest(ExamRequest):
    """An exam request plus how it should be printed."""

    title: str = "Practice Exam"
    institution: str = ""
    time_limit: int = Field(0, ge=0)
    include_answer_key: bool = True
    randomize_choices: bool = True
    include_scenarios: bool = True
    include_explanations: bool = False
    filename: str = "exam.pdf"


def _selection(body: ExamRequest, db: ExamBankDB) -> Selection:
    """Validate the request and plan the paper. Shared by both endpoints, so
    the plan an author approved is the paper they get."""
    if not body.certification_ids:
        raise HTTPException(400, "Choose at least one certification to draw from.")
    if not body.topic_weights:
        raise HTTPException(
            400,
            "An exam needs at least one weighted topic. Ask "
            "/api/exam/topics which ones have questions.",
        )

    negative = sorted(t for t, w in body.topic_weights.items() if w < 0)
    if negative:
        raise HTTPException(400, f"A topic cannot have a negative weight: {', '.join(negative)}.")

    total = sum(body.topic_weights.values())
    if abs(total - 100.0) > WEIGHT_TOLERANCE:
        raise HTTPException(
            400,
            f"The topic weights add up to {total:g}%, not 100%. They are shares "
            "of one paper, so a total below 100 would print a shorter exam than "
            "asked for and one above it would silently drop questions.",
        )

    if not body.difficulties:
        raise HTTPException(400, "Choose at least one difficulty.")
    if not body.statuses:
        raise HTTPException(400, "Choose at least one status to draw from.")

    return plan_exam(
        db,
        certification_ids=body.certification_ids,
        total_questions=body.total_questions,
        difficulties=body.difficulties,
        topic_weights=body.topic_weights,
        statuses=body.statuses,
        randomize=body.randomize,
        seed=body.seed,
    )


def _plan_json(plan: Selection) -> dict[str, Any]:
    return {
        "requested": plan.requested,
        "selected": len(plan.questions),
        "shortfall": plan.shortfall,
        "redistributed": plan.redistributed,
        "honoured": plan.honoured,
        "topics": [
            {
                "topic": t.topic,
                "weight": t.weight,
                "wanted": t.wanted,
                "available": t.available,
                "selected": t.selected,
                "short": t.short,
                "lent": t.lent,
            }
            for t in plan.topics
        ],
    }


@router.get("/api/exam/topics")
def exam_topics(
    certification_ids: str = "",
    statuses: str = "approved",
    db: ExamBankDB = Depends(get_db),
) -> list[dict[str, Any]]:
    """Topics with questions, and how many — what a weighting can be built on.

    Comma-separated rather than repeated query parameters, matching the rest
    of the API's filters.
    """
    ids = [c for c in (certification_ids or "").split(",") if c.strip()]
    if not ids:
        return []
    status_list = [s for s in (statuses or "").split(",") if s.strip()] or ["approved"]
    counts = get_available_topics(db, ids, statuses=status_list)
    return [{"topic": topic, "questionCount": count} for topic, count in counts.items()]


@router.post("/api/exam/plan")
def plan_paper(body: ExamRequest, db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    """What the paper would actually contain. Builds no PDF."""
    plan = _selection(body, db)
    if not plan.questions:
        raise HTTPException(
            409,
            "No questions match that selection, so there is no paper to build. "
            "Check the statuses — questions adopted from a course are drafts "
            "until they are reviewed.",
        )
    return _plan_json(plan)


@router.post("/api/exam/pdf")
def build_paper(
    body: PdfRequest, background: BackgroundTasks, db: ExamBankDB = Depends(get_db)
) -> FileResponse:
    """The printable paper, as a download."""
    plan = _selection(body, db)
    if not plan.questions:
        raise HTTPException(409, "No questions match that selection.")

    path = temp_path("pdf", prefix="peb-exam-")
    generate_exam_pdf(
        plan.questions,
        title=body.title,
        institution=body.institution,
        time_limit=body.time_limit,
        include_answer_key=body.include_answer_key,
        randomize_choices=body.randomize_choices,
        include_scenarios=body.include_scenarios,
        include_explanations=body.include_explanations,
        seed=body.seed,
        output_path=path,
    )
    background.add_task(cleanup(path))
    return FileResponse(
        path, media_type="application/pdf",
        filename=body.filename.strip() or "exam.pdf",
    )
