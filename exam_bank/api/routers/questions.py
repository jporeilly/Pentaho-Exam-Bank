"""Question search, read, edit, lifecycle and delete."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ...core.bank import STATUS_TRANSITIONS, STATUSES, ExamBankDB
from ..deps import get_db, question_json

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
    items = db.search(limit=limit, offset=offset, **filters)
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
