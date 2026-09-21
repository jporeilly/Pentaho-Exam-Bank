"""Shared request dependencies."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterator

from ..core.question_bank import Question, QuestionBankDB
from ..utils.config import DB_PATH


def get_db() -> Iterator[QuestionBankDB]:
    """A database handle for the life of one request.

    Deliberately per-request rather than one shared connection. ``sqlite3``
    connections are bound to the thread that opened them, and FastAPI runs
    sync endpoints on a worker threadpool — a module-level connection would
    raise ``ProgrammingError`` as soon as a second thread touched it, which
    surfaces as an intermittent 500 under concurrent requests rather than as
    an obvious bug. Opening a SQLite connection is cheap.
    """
    db = QuestionBankDB(DB_PATH)
    try:
        yield db
    finally:
        db.close()


def question_json(question: Question) -> dict[str, Any]:
    """A question as JSON.

    Serialised straight from the dataclass rather than through a parallel
    response model: the model would be a second definition of the same shape,
    and the two would drift the first time a field was added.
    """
    return asdict(question)
