"""Read a file of questions, show what is in it, then save what is chosen.

Two steps rather than one, for the same reason publishing is: an import is a
batch of other people's work landing in the bank, and the author needs to see
what came out of the file — what is unusable, what is already there — before
any of it is saved. ``/preview`` parses and reports; ``/commit`` writes what
the caller names. Nothing is written by the first step.

The uploaded file is parsed from a temporary copy and deleted immediately.
Nothing is kept between the two calls: ``/commit`` is given the questions to
save, not a handle on a server-side session, so a preview left open in a tab
for an hour cannot commit something the server has since forgotten.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from ...core.bank import Question, ExamBankDB
from ...core.importing import SUPPORTED, UnsupportedFile, import_any
from ...core.validation import problems_with
from ...core.intake import take_in
from ..deps import courses_dir_if_any, get_db, question_json

router = APIRouter(tags=["import"])

#: Refused before anything is read. Generous enough for a full certification's
#: worth of questions; a file larger than this is not a question bank.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

#: How alike two stems have to be before the author is warned. Matches the
#: bank browser's own threshold, so "possible duplicate" means the same thing
#: wherever it is said.
DUPLICATE_THRESHOLD = 0.85


class ImportedQuestion(BaseModel):
    """One question read out of a file, with everything known against it."""

    question: dict[str, Any]
    problems: list[dict[str, str]]
    duplicate_of: str = ""
    duplicate_stem: str = ""
    duplicate_score: int = 0


def _describe(db: ExamBankDB, question: Question) -> ImportedQuestion:
    """A parsed question plus the two things the author has to decide about:
    whether it can be graded at all, and whether the bank already has it."""
    duplicate_of = duplicate_stem = ""
    score = 0
    if question.stem.strip():
        similar = db.find_similar_stems_scored(question.stem, threshold=DUPLICATE_THRESHOLD)
        if similar:
            best, best_score = max(similar, key=lambda pair: pair[1])
            duplicate_of, duplicate_stem = best.id, best.stem
            score = int(best_score * 100)

    return ImportedQuestion(
        question=question_json(question),
        problems=[p.as_dict() for p in problems_with(question)],
        duplicate_of=duplicate_of,
        duplicate_stem=duplicate_stem,
        duplicate_score=score,
    )


@router.post("/api/import/preview")
def preview_import(
    file: UploadFile = File(...), db: ExamBankDB = Depends(get_db)
) -> dict[str, Any]:
    """Parse an uploaded file and report what is in it. Writes nothing.

    Deliberately sync, and reading ``file.file`` rather than awaiting
    ``file.read()``. Every step here blocks — parsing the upload, and one
    similarity scan per question against the whole bank — so on the event loop
    a four-hundred-question file would stall every other request for the
    duration. Sync means FastAPI runs it in the threadpool, which is also what
    ``get_db`` is built for: its connection is opened on a worker thread.
    """
    raw = file.file.read()
    if not raw:
        raise HTTPException(400, f"{file.filename or 'That file'} is empty.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413,
            f"{file.filename} is {len(raw) // (1024 * 1024)} MB. The limit is "
            f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB — a question file should be "
            "far smaller than that.",
        )

    # The readers take a path, and several of them sniff the file's content to
    # decide what it is, so the upload is spooled to disk under its own
    # extension. Deleted in `finally`: a failed parse must not leave the
    # author's file sitting in the temp directory.
    suffix = Path(file.filename or "upload").suffix
    handle = tempfile.NamedTemporaryFile(prefix="peb-import-", suffix=suffix, delete=False)
    tmp = Path(handle.name)
    try:
        handle.write(raw)
        handle.close()
        questions, detected = import_any(tmp)
    except UnsupportedFile as e:
        raise HTTPException(415, str(e)) from e
    except Exception as e:
        # A malformed file is the author's to fix, and the reader's message
        # names the row or tag, so it is worth more than "import failed".
        raise HTTPException(
            422, f"{file.filename} could not be read as questions: {e}"
        ) from e
    finally:
        tmp.unlink(missing_ok=True)

    if not questions:
        raise HTTPException(
            422,
            f"{file.filename} was read as {detected.label} but held no questions. "
            f"Supported formats: {', '.join(SUPPORTED)}.",
        )

    described = [_describe(db, q) for q in questions]
    return {
        "filename": file.filename,
        "format": detected.format,
        "formatLabel": detected.label,
        "formatNote": detected.note,
        "count": len(described),
        "gradeable": sum(1 for d in described if not d.problems),
        "duplicates": sum(1 for d in described if d.duplicate_of),
        "questions": [d.model_dump() for d in described],
    }


class CommitRequest(BaseModel):
    """The questions the author chose to keep, and where they belong."""

    questions: list[dict[str, Any]]
    certification_id: str = ""
    topic: str = ""
    # Questions arrive as drafts whatever the file said. An import is somebody
    # else's work entering the bank, and the review lifecycle is the point at
    # which it becomes this bank's.
    status: str = "draft"


@router.post("/api/import/commit")
def commit_import(
    body: CommitRequest, db: ExamBankDB = Depends(get_db)
) -> dict[str, Any]:
    """Save the chosen questions into the bank."""
    if not body.questions:
        raise HTTPException(400, "No questions were chosen.")

    if body.certification_id and db.get_certification(body.certification_id) is None:
        raise HTTPException(404, f"No certification '{body.certification_id}'.")

    # A row that is not a question at all is refused here; everything else
    # goes the one way in for new questions (core/intake): refused if it cannot
    # be graded - the bank's own editor will not save one of these, and an
    # import that could would make that rule a suggestion - else filed into
    # the course (an id in the course's format: one the file carried is kept
    # when it fits, else renumbered; module; place) and saved.
    questions, refused = [], []
    for raw in body.questions:
        try:
            questions.append(Question(**raw))
        except TypeError as e:
            refused.append({"stem": str(raw.get("stem", ""))[:80], "reason": str(e)})

    done = take_in(db, questions, certification_id=body.certification_id,
                   courses_dir=courses_dir_if_any(), topic=body.topic, status=body.status,
                   source_type_from_certification=True)
    return {"saved": len(done.saved), "ids": [q.id for q in done.saved],
            "refused": refused + done.refused}
