"""Certifications — the grouping a question belongs to, usually one course."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...core.question_bank import Certification, QuestionBankDB
from ..deps import get_db

router = APIRouter(tags=["certifications"])


def _json(cert: Certification, db: QuestionBankDB) -> dict[str, Any]:
    return {
        "id": cert.id,
        "name": cert.name,
        "description": cert.description,
        "sourceType": cert.source_type,
        "sourceRef": cert.source_ref,
        "questionCount": db.count_by_certification(cert.id),
        "createdAt": cert.created_at,
        "updatedAt": cert.updated_at,
    }


@router.get("/api/certifications")
def list_certifications(db: QuestionBankDB = Depends(get_db)) -> list[dict[str, Any]]:
    return [_json(c, db) for c in db.list_certifications()]


class NewCertification(BaseModel):
    name: str
    description: str = ""
    source_type: str = "pcm"
    source_ref: str = ""


@router.post("/api/certifications", status_code=201)
def create_certification(
    body: NewCertification, db: QuestionBankDB = Depends(get_db)
) -> dict[str, Any]:
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "A certification needs a name")
    cert = Certification(
        name=name,
        description=body.description.strip(),
        source_type=body.source_type,
        source_ref=body.source_ref.strip(),
    )
    db.save_certification(cert)
    return _json(cert, db)


@router.delete("/api/certifications/{cert_id}")
def delete_certification(
    cert_id: str, confirm: str = "", db: QuestionBankDB = Depends(get_db)
) -> dict[str, Any]:
    """Delete a certification.

    Deleting one does **not** delete or reassign its questions — they keep a
    ``certification_id`` pointing at a row that no longer exists, and drop out
    of every filtered view without being gone. So a certification that still
    holds questions requires ``?confirm=delete``, which makes an interface ask
    before orphaning them rather than after.
    """
    cert = db.get_certification(cert_id)
    if not cert:
        raise HTTPException(404, f"No certification '{cert_id}'")
    held = db.count_by_certification(cert_id)
    if held and confirm.strip().lower() != "delete":
        raise HTTPException(
            428,
            f"'{cert.name}' still holds {held} questions, which would be left "
            f"orphaned. Reassign them first, or repeat with ?confirm=delete.",
        )
    db.delete_certification(cert_id)
    return {"ok": True, "id": cert_id, "orphanedQuestions": held}
