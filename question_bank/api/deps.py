"""Shared request dependencies."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterator

from fastapi import HTTPException

from ..core.question_bank import Question, QuestionBankDB
from ..utils.config import DB_PATH, config


def get_db() -> Iterator[QuestionBankDB]:
    """A database handle for the life of one request.

    Deliberately per-request rather than one shared connection. ``sqlite3``
    connections are bound to the thread that opened them, and FastAPI runs
    sync endpoints on a worker threadpool — a module-level connection would
    raise ``ProgrammingError`` as soon as a second thread touched it, which
    surfaces as an intermittent 500 under concurrent requests rather than as
    an obvious bug. Opening a SQLite connection is cheap.

    ``same_thread_only=False`` because per-request is not the same as
    per-thread: anyio may run this generator's teardown on a different worker
    from the one that ran its setup, so the request succeeds and then
    ``db.close()`` raises. That was seen once in a real run before it was
    fixed, buried in a traceback after a response had already gone out. Safe
    here precisely because the connection is used by one request and shared
    with nothing.
    """
    db = QuestionBankDB(DB_PATH, same_thread_only=False)
    try:
        yield db
    finally:
        db.close()


def courses_dir() -> Path:
    """The configured Content Manager courses directory, or a 409 saying why not.

    One definition, used by every route that needs it. Written twice it was
    also written wrong the second time: ``Path(config.pcm_courses_dir or ".")``
    turns "not configured" into **the current working directory**, which is a
    real directory, so the guard never fires and the app goes looking for
    courses wherever it happens to have been started from.
    """
    raw = (config.pcm_courses_dir or "").strip()
    if not raw:
        raise HTTPException(409, "No Content Manager courses directory is configured.")
    path = Path(raw)
    if not path.is_dir():
        raise HTTPException(409, f"The configured courses directory does not exist: {path}")
    return path


def question_json(question: Question) -> dict[str, Any]:
    """A question as JSON.

    Serialised straight from the dataclass rather than through a parallel
    response model: the model would be a second definition of the same shape,
    and the two would drift the first time a field was added.
    """
    return asdict(question)
