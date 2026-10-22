"""Candidate results: import the results Sheet's Detail tab, read the item analysis."""
from __future__ import annotations

import base64
import binascii
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...core import results_service, results_workbook
from ...core.bank import ExamBankDB
from ...core.item_analysis import ResultsImportError, analyse, import_rows, parse_detail_csv
from ...core.pcm_reader import read_course_json
from ..deps import courses_dir, get_db

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


class ImportWorkbookBody(BaseModel):
    #: The .xlsx file, base64. JSON like the CSV import, for the same reason.
    xlsx: str


@router.post("/api/results/import-xlsx")
def import_results_workbook(body: ImportWorkbookBody, db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    """Upsert every tab of the results workbook: attempts, and the Detail answers."""
    try:
        data = base64.b64decode(body.xlsx, validate=False)
    except (binascii.Error, ValueError) as e:
        raise HTTPException(422, "The file could not be read.") from e
    try:
        result = results_workbook.import_workbook(db.conn, data)
    except ResultsImportError as e:
        raise HTTPException(422, str(e)) from e
    if not result["attempts"] and not result["answers"]:
        raise HTTPException(422, "The workbook has the right columns but no attempts yet.")
    return result


def _filters(course: str, candidate: str, passed: str, attempt_no: int,
             date_from: str, date_to: str) -> results_workbook.Filters:
    try:
        return results_workbook.Filters(course, candidate, passed, attempt_no, date_from, date_to)
    except ValueError as e:
        raise HTTPException(422, f"Bad filter: {e}") from e


@router.get("/api/results/attempts")
def results_attempts(course: str = "", candidate: str = "", passed: str = "", attempt_no: int = 0,
                     date_from: str = "", date_to: str = "",
                     db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    """Each attempt (a candidate's repeats are separate rows), filtered, with the
    choices the filter controls offer."""
    flt = _filters(course, candidate, passed, attempt_no, date_from, date_to)
    names = {c.source_ref: c.name for c in db.list_certifications() if getattr(c, "source_ref", "")}
    return results_workbook.list_attempts(db.conn, flt, names)


@router.get("/api/results/service")
def results_service_status() -> dict[str, Any]:
    """Whether the admin secret is set - a boolean, never the value."""
    return {"configured": results_service.configured(), "env": results_service.ENV}


def _service_urls() -> list[str]:
    """Every distinct results service the courses post to (normally one)."""
    urls = []
    root = courses_dir()
    for exam in sorted(root.glob("*/exam.json")) if root else []:
        try:
            url = str(read_course_json(exam).get("webhookUrl") or "")
        except (OSError, ValueError):
            continue
        if url.startswith("https://") and url not in urls:
            urls.append(url)
    return urls


@router.post("/api/results/pull")
def pull_results(db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    """Read the Detail rows from the results service and import them, as the
    CSV import does. Needs the admin secret."""
    urls = _service_urls()
    if not urls:
        raise HTTPException(409, "No course posts its results anywhere: no exam.json has a webhookUrl.")
    rows = []
    try:
        for url in urls:
            rows.extend(results_service.export_results(url))
    except results_service.ResultsServiceError as e:
        raise HTTPException(409, str(e)) from e
    if not rows:
        return {"rows": 0, "added": 0, "attempts": 0, "courses": [], "services": len(urls),
                "totalResponses": db.conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0]}
    return {**import_rows(db.conn, rows), "services": len(urls)}


@router.get("/api/results/analysis")
def results_analysis(certification_id: str = "", course: str = "", candidate: str = "",
                     passed: str = "", attempt_no: int = 0, date_from: str = "", date_to: str = "",
                     db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    """Per exam, per question: attempts, % correct, discrimination, option use, flags.
    The filters narrow it to the attempts they let through."""
    flt = _filters(course, candidate, passed, attempt_no, date_from, date_to)
    return analyse(db, certification_id, results_workbook.matching_attempt_ids(db.conn, flt))
