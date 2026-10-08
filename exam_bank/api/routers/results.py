"""Candidate results: import the results Sheet's Detail tab, read the item analysis."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...core.bank import ExamBankDB
from ...core.item_analysis import ResultsImportError, analyse, import_rows, parse_detail_csv
from ..deps import get_db

router = APIRouter(tags=["results"])


class ImportBody(BaseModel):
    #: The CSV text. Sent as JSON rather than a multipart upload: the client
    #: reads the file itself, and the API needs no form-parsing dependency.
    csv: str


@router.post("/api/results/import")
def import_results(body: ImportBody, db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    """Upsert the Detail tab's rows. Re-importing the same export changes nothing."""
    try:
        rows = parse_detail_csv(body.csv)
    except ResultsImportError as e:
        raise HTTPException(422, str(e)) from e
    if not rows:
        raise HTTPException(422, "The file has the Detail tab's columns but no rows.")
    return import_rows(db.conn, rows)


@router.get("/api/results/analysis")
def results_analysis(certification_id: str = "", db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    """Per exam, per question: attempts, % correct, discrimination, option use, flags."""
    return analyse(db, certification_id)
