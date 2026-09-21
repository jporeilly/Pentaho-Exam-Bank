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

from fastapi import APIRouter, HTTPException

from ...core.context_budget import source_budget_chars
from ...core.pcm_reader import list_pcm_courses, list_pcm_labs, load_pcm_course
from ...utils.config import config
from ..deps import courses_dir

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
def list_labs(slug: str) -> list[dict[str, str]]:
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
