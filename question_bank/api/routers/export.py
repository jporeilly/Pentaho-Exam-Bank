"""Export a filtered selection of the bank in any of its formats.

Every endpoint here **returns a file to the caller**. None of them writes into
a Content Manager course, and that is deliberate rather than unimplemented:
publishing back has to merge into the existing ``exam.json`` so it cannot
delete the settings the Content Editor owns — `intake` in particular, which
``export_pcm_exam_json`` has no parameter for and would silently drop. Until
that merge exists, the exam.json this produces is a download for the author to
place, which makes the overwrite a decision somebody takes rather than a side
effect of pressing Export. See PLAN.md §3.4.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from ...core import exporter
from ...core.exam_builder import generate_exam_pdf
from ...core.question_bank import Question, QuestionBankDB
from ..deps import get_db

router = APIRouter(tags=["export"])

# format -> (writer, file extension, media type)
_FORMATS: dict[str, tuple[Callable[..., Any], str, str]] = {
    "csv": (exporter.export_csv, "csv", "text/csv"),
    "json": (exporter.export_json, "json", "application/json"),
    "qti": (exporter.export_qti21, "xml", "application/xml"),
    "moodle": (exporter.export_moodle_xml, "xml", "application/xml"),
    "text": (exporter.export_text, "txt", "text/plain"),
    "docx": (
        exporter.export_docx, "docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
}


def _selection(
    db: QuestionBankDB, filters: dict[str, str], limit: int = 5000
) -> list[Question]:
    questions = db.search(limit=limit, **filters)
    if not questions:
        raise HTTPException(404, "No questions match that selection.")
    return questions


def _temp_path(suffix: str) -> Path:
    handle = tempfile.NamedTemporaryFile(prefix="qb-export-", suffix=f".{suffix}", delete=False)
    handle.close()
    return Path(handle.name)


def _cleanup(path: Path) -> Callable[[], None]:
    """Delete the temp file once the response has been sent. Without this,
    every export leaks a file into the temp directory for the life of the
    machine."""

    def remove() -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    return remove


@router.get("/api/export/formats")
def list_formats() -> list[dict[str, str]]:
    return [
        {"format": name, "extension": ext, "mediaType": media}
        for name, (_, ext, media) in _FORMATS.items()
    ]


@router.get("/api/export/{fmt}")
def export_questions(
    fmt: str,
    background: BackgroundTasks,
    db: QuestionBankDB = Depends(get_db),
    text: str = "",
    topic: str = "",
    difficulty: str = "",
    bloom_level: str = "",
    status: str = "",
    certification_id: str = "",
    assigned_sme: str = "",
    tags: str = "",
    filename: str = "",
) -> FileResponse:
    """Export the questions matching the filters, as a download.

    The filters are the same ones the question list takes, so what is exported
    is exactly what the author is looking at.
    """
    if fmt not in _FORMATS:
        raise HTTPException(404, f"Unknown format '{fmt}'. Try: {', '.join(_FORMATS)}")
    write, extension, media = _FORMATS[fmt]
    questions = _selection(db, dict(
        text=text, topic=topic, difficulty=difficulty, bloom_level=bloom_level,
        status=status, certification_id=certification_id,
        assigned_sme=assigned_sme, tags=tags,
    ))

    path = _temp_path(extension)
    write(questions, path)
    background.add_task(_cleanup(path))
    return FileResponse(
        path, media_type=media,
        filename=(filename.strip() or f"questions.{extension}"),
    )


@router.get("/api/export-exam/json")
def export_course_exam(
    background: BackgroundTasks,
    db: QuestionBankDB = Depends(get_db),
    certification_id: str = "",
    status: str = "",
    title: str = "Practitioner Exam",
    description: str = "",
    pass_mark: int = Query(80, ge=0, le=100),
    questions_per_attempt: int | None = Query(None, ge=1),
    shuffle: bool = True,
    filename: str = "exam.json",
) -> FileResponse:
    """A Content Manager ``exam.json`` for the selected questions — as a
    **download**, never written into a course. See this module's docstring.

    A pool adopted from a course is written back in its authored order, so the
    diff against the course's existing file is the questions that changed and
    nothing else.
    """
    questions = _selection(db, dict(certification_id=certification_id, status=status))
    if questions_per_attempt and questions_per_attempt > len(questions):
        # The learner app draws this many from the pool; asking for more than
        # exist is an exam that cannot be sat.
        raise HTTPException(
            400,
            f"questionsPerAttempt ({questions_per_attempt}) is more than the "
            f"{len(questions)} questions selected.",
        )

    path = _temp_path("json")
    exporter.export_pcm_exam_json(
        questions, path,
        title=title, description=description, pass_mark=pass_mark,
        questions_per_attempt=questions_per_attempt, shuffle=shuffle,
    )
    background.add_task(_cleanup(path))
    return FileResponse(path, media_type="application/json",
                        filename=filename.strip() or "exam.json")


@router.get("/api/export-exam/pdf")
def export_exam_paper(
    background: BackgroundTasks,
    db: QuestionBankDB = Depends(get_db),
    certification_id: str = "",
    topic: str = "",
    status: str = "",
    title: str = "Practice Exam",
    institution: str = "",
    time_limit: int = Query(0, ge=0),
    include_answer_key: bool = True,
    randomize_choices: bool = True,
    include_scenarios: bool = True,
    include_explanations: bool = False,
    seed: int | None = None,
    filename: str = "exam.pdf",
) -> FileResponse:
    """A printable exam paper."""
    questions = _selection(db, dict(
        certification_id=certification_id, topic=topic, status=status,
    ))
    path = _temp_path("pdf")
    generate_exam_pdf(
        questions, title=title, institution=institution, time_limit=time_limit,
        include_answer_key=include_answer_key, randomize_choices=randomize_choices,
        include_scenarios=include_scenarios, include_explanations=include_explanations,
        seed=seed, output_path=path,
    )
    background.add_task(_cleanup(path))
    return FileResponse(path, media_type="application/pdf",
                        filename=filename.strip() or "exam.pdf")
