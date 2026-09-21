"""The database rename must carry the live bank across, not abandon it.

`assets/db/question_bank.db` holds every question the app has ever generated.
The Exam Bank rename moved it to `exam_bank.db`, and the whole of that move is
one `rename` in `utils/config.py` — which a find-and-replace sweep across the
repo silently turned into `exam_bank.db -> exam_bank.db` while it was being
written. It read fine and did nothing. These tests pin the old name so the next
sweep fails loudly instead.
"""

import sqlite3

import pytest

from exam_bank.utils.config import (
    PRE_RENAME_DB_NAME,
    PRE_RENAME_HOME_DIR,
    adopt_pre_rename_db,
)


def _make_db(path, marker: str) -> None:
    """A real SQLite file, so a test can prove WHICH database survived."""
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE marker (value TEXT)")
    conn.execute("INSERT INTO marker VALUES (?)", (marker,))
    conn.commit()
    conn.close()


def _marker(path) -> str:
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute("SELECT value FROM marker").fetchone()[0]
    finally:
        conn.close()


def test_the_pre_rename_names_are_the_ones_that_shipped():
    """Literal, not derived. A sweep that rewrites these breaks the migration."""
    assert PRE_RENAME_DB_NAME == "question_bank.db"
    assert PRE_RENAME_HOME_DIR == ".question_bank"


def test_old_database_is_moved_to_the_new_name(tmp_path):
    old = tmp_path / PRE_RENAME_DB_NAME
    new = tmp_path / "exam_bank.db"
    _make_db(old, "the live bank")

    assert adopt_pre_rename_db(tmp_path, new) is True
    assert not old.exists(), "the old file must not be left behind as a second live-looking bank"
    assert _marker(new) == "the live bank"


def test_an_existing_new_database_wins_and_the_old_one_is_left_alone(tmp_path):
    """Never overwrite a bank that is already under the new name."""
    old = tmp_path / PRE_RENAME_DB_NAME
    new = tmp_path / "exam_bank.db"
    _make_db(old, "stale")
    _make_db(new, "current")

    assert adopt_pre_rename_db(tmp_path, new) is False
    assert _marker(new) == "current"
    assert old.exists(), "the old file is evidence; leave it for the user to remove"


def test_nothing_to_adopt_is_not_an_error(tmp_path):
    assert adopt_pre_rename_db(tmp_path, tmp_path / "exam_bank.db") is False


def test_the_configured_db_path_uses_the_new_name():
    from exam_bank.utils.config import DB_PATH

    assert DB_PATH.name == "exam_bank.db"
