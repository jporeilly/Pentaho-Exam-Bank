"""Question search, read, edit, lifecycle and delete."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ...core import providers, question_refinement
from ...core.bank import STATUS_TRANSITIONS, STATUSES, ExamBankDB
from ...core.course_filing import refile_id
from ...core.stem_text import form_notes
from ...core.validation import problems_with
from ...utils.config import config
from ..deps import courses_dir_if_any, get_db, question_json

router = APIRouter(tags=["questions"])

# Fields a client may change. Everything else about a question is either
# derived (the timestamps), structural (its certification), or part of the
# audit trail, and none of those are a PUT's business.
_EDITABLE = (
    "scenario", "stem", "question_type", "key", "keys", "key_source_text",
    "distractors", "option_order", "explanation", "topic", "tags",
    "difficulty", "bloom_level", "assigned_sme",
)


@router.get("/api/lifecycle")
def lifecycle() -> dict[str, Any]:
    """The question lifecycle, as the model defines it.

    Served rather than restated in the front end. The transitions are
    enforced by `Question.transition`, which raises on an illegal move;
    a UI holding its own copy of the table would offer buttons the model
    refuses, and the user would meet a 409 they cannot do anything with.
    One table, asked at run time.
    """
    return {"statuses": list(STATUSES), "transitions": {
        status: list(moves) for status, moves in STATUS_TRANSITIONS.items()
    }}


@router.get("/api/questions")
def list_questions(
    db: ExamBankDB = Depends(get_db),
    text: str = "",
    topic: str = "",
    difficulty: str = "",
    bloom_level: str = "",
    status: str = "",
    certification_id: str = "",
    assigned_sme: str = "",
    tags: str = "",
    sort: str = "course",
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """A page of questions plus the unpaged total, so a client can show
    "showing 50 of 398" without asking twice."""
    filters = dict(
        text=text, topic=topic, difficulty=difficulty, bloom_level=bloom_level,
        status=status, certification_id=certification_id,
        assigned_sme=assigned_sme, tags=tags,
    )
    # sort is deliberately NOT in filters: search_count shares that dict
    # and takes no ordering - a count does not have one.
    items = db.search(limit=limit, offset=offset, sort=sort, **filters)
    return {
        "items": [question_json(q) for q in items],
        "total": db.search_count(**filters),
        "limit": limit,
        "offset": offset,
    }


@router.get("/api/questions/{question_id}")
def get_question(question_id: str, db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    question = db.get(question_id)
    if not question:
        raise HTTPException(404, f"No question '{question_id}'")
    return question_json(question)


@router.put("/api/questions/{question_id}")
def update_question(
    question_id: str, body: dict[str, Any], db: ExamBankDB = Depends(get_db)
) -> dict[str, Any]:
    """Update the editable fields, recording each change in the question's
    version history so an edit can be traced afterwards."""
    question = db.get(question_id)
    if not question:
        raise HTTPException(404, f"No question '{question_id}'")

    editor = str(body.get("editor") or "").strip()
    topic_before = question.topic
    for field in _EDITABLE:
        if field not in body:
            continue
        old = getattr(question, field)
        new = body[field]
        if old == new:
            continue
        question.record_edit(field, old, new, editor=editor)
        setattr(question, field, new)

    if not (question.stem or "").strip():
        raise HTTPException(400, "A question needs a stem")
    # A course question's id names its module (<course>-m<module>-q<n>), so
    # moving it to another module gives it that module's next number - the
    # row is renamed and the change recorded, and the reply carries the new
    # id for the editor to follow.
    if question.topic != topic_before and question.certification_id:
        refile_id(db, question, db.get_certification(question.certification_id),
                  courses_dir=courses_dir_if_any(), editor=editor)
    db.save(question)
    return question_json(question)


class StatusChange(BaseModel):
    status: str
    sme_name: str = ""
    comment: str = ""


@router.post("/api/questions/{question_id}/status")
def change_status(
    question_id: str, body: StatusChange, db: ExamBankDB = Depends(get_db)
) -> dict[str, Any]:
    """Move a question through its lifecycle.

    The transition is validated by the model, which knows which moves are
    legal from where; an illegal one is the caller's error, not a 500.
    """
    question = db.get(question_id)
    if not question:
        raise HTTPException(404, f"No question '{question_id}'")
    if body.status not in STATUSES:
        raise HTTPException(400, f"Unknown status '{body.status}'")
    try:
        question.transition(body.status, sme_name=body.sme_name, comment=body.comment)
    except ValueError as e:
        raise HTTPException(409, str(e))
    db.save(question)
    return question_json(question)


@router.delete("/api/questions/{question_id}")
def delete_question(question_id: str, db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    if not db.get(question_id):
        raise HTTPException(404, f"No question '{question_id}'")
    db.delete(question_id)
    return {"ok": True, "id": question_id}


# --- AI assistance -------------------------------------------------------
#
# Both endpoints are READ-ONLY. They return a proposal or a list of findings
# and never touch the bank: accepting a rewrite is an ordinary save the author
# makes, through the editor they were already looking at.
#
# That is the same look-then-act shape as publishing and importing, and here
# it is not a nicety. A model that rewrites a question in place would be the
# one contributor to the bank whose work nobody reviewed.


class AiRewriteRequest(BaseModel):
    """What to ask for. The default instruction is the module's own."""

    instruction: str = ""


def _ai_model() -> str:
    """The model to use, or a 409 naming what is missing.

    Resolved per request rather than held: the provider and model are
    settings the author can change while the app is running, and a cached
    handle would keep answering with the old one.
    """
    model = providers.model_for(providers.active_provider())
    if not model:
        raise HTTPException(
            409,
            "No AI model is configured. Pick a provider and model in "
            "Settings first.",
        )
    return model


@router.post("/api/questions/{question_id}/ai/rewrite")
def ai_rewrite_question(
    question_id: str, body: AiRewriteRequest, db: ExamBankDB = Depends(get_db)
) -> dict[str, Any]:
    """Propose a rewritten question. Writes nothing."""
    question = db.get(question_id)
    if question is None:
        raise HTTPException(404, f"No question '{question_id}'.")

    kwargs = {"question": question, "model": _ai_model(), "base_url": config.ollama_url}
    if body.instruction.strip():
        kwargs["instruction"] = body.instruction.strip()

    proposed = question_refinement.improve_question(**kwargs)
    if proposed is None:
        raise HTTPException(
            502,
            "The model did not return a usable question. Try again, or a "
            "larger model.",
        )

    # The problems are reported against the PROPOSAL, because the author is
    # about to decide whether to take it and an improvement that cannot be
    # graded is not an improvement.
    return {
        "proposed": question_json(proposed),
        "problems": [
            {"field": p.field, "message": p.message} for p in problems_with(proposed)
        ],
        # Where the proposal breaks the house form - a question in the
        # scenario, statements in the stem. Advice, not a block: a model can
        # ignore the rule it was given, and the author should see that
        # before taking the rewrite rather than after.
        "notes": [
            {"field": f, "message": m}
            for f, m in form_notes(proposed.scenario, proposed.stem)
        ],
        "unchanged": question_json(proposed) == question_json(question),
    }


@router.post("/api/questions/{question_id}/ai/review")
def ai_review_question(
    question_id: str, db: ExamBankDB = Depends(get_db)
) -> dict[str, Any]:
    """Check the answers, and proofread. Writes nothing."""
    question = db.get(question_id)
    if question is None:
        raise HTTPException(404, f"No question '{question_id}'.")

    model = _ai_model()
    answers = question_refinement.review_answers(
        question, model, base_url=config.ollama_url
    )
    prose = question_refinement.qa_check_question(
        question, model, base_url=config.ollama_url
    )

    # Kept apart in the response. "The key is also true of option C" and "a
    # comma is missing" are not the same kind of news, and a flat list buries
    # the first under the second.
    return {
        "answers": answers,
        "prose": prose,
        # What the bank's own deterministic validator says, which owes
        # nothing to a model and is worth showing beside its opinion.
        "gradeable": [
            {"field": p.field, "message": p.message} for p in problems_with(question)
        ],
        "form": [
            {"field": f, "message": m} for f, m in form_notes(question.scenario, question.stem)
        ],
    }
