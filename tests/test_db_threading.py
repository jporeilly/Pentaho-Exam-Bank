"""The database handle and threads.

A FastAPI dependency's setup and its teardown are not guaranteed to run on the
same worker thread. The request then succeeds and `db.close()` raises
afterwards, so the failure lands in a traceback after the response has gone
out — which is exactly how this was found, in the log of a real generation
run rather than from a test.
"""

import sqlite3
import threading

import pytest

from exam_bank.core.bank import Question, ExamBankDB


def in_another_thread(fn):
    """Run `fn` on a fresh thread; return its value or re-raise its error."""
    box: dict = {}

    def run():
        try:
            box["value"] = fn()
        except BaseException as e:  # noqa: BLE001 — re-raised below
            box["error"] = e

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box.get("value")


def test_the_guard_is_on_by_default(tmp_path):
    """sqlite3's check is a real guard against concurrent use corrupting
    state. Anything that opens a database gets it unless it says otherwise."""
    db = ExamBankDB(tmp_path / "guarded.db")
    try:
        with pytest.raises(sqlite3.ProgrammingError):
            in_another_thread(lambda: db.count())
    finally:
        # On THIS thread — the one that opened it. close() is guarded too,
        # which is the whole point of the test above.
        db.close()


def test_a_request_scoped_handle_can_be_closed_from_another_thread(tmp_path):
    """The actual bug: closing on a different worker than the one that
    opened it."""
    db = ExamBankDB(tmp_path / "request.db", same_thread_only=False)
    db.save(Question(id="q1", stem="Does it close?", key="yes", distractors=["no"]))
    in_another_thread(db.close)  # must not raise


def test_a_request_scoped_handle_still_works_across_threads(tmp_path):
    db = ExamBankDB(tmp_path / "request.db", same_thread_only=False)
    db.save(Question(id="q1", stem="Readable?", key="yes", distractors=["no"]))
    try:
        assert in_another_thread(lambda: db.count()) == 1
    finally:
        db.close()


def test_the_api_dependency_survives_a_cross_thread_teardown(tmp_path, monkeypatch):
    """Drive the real dependency the way anyio can: next() on one thread,
    exhaustion on another."""
    from exam_bank.api import deps

    monkeypatch.setattr(deps, "DB_PATH", tmp_path / "dep.db")
    generator = deps.get_db()
    db = next(generator)
    db.save(Question(id="q1", stem="Anything?", key="yes", distractors=["no"]))

    def finish():
        with pytest.raises(StopIteration):
            next(generator)

    in_another_thread(finish)  # the teardown must not raise
