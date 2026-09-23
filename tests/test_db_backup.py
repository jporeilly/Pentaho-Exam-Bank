"""Tests for core/db_backup.py — backup, restore, and info utilities."""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from exam_bank.core import db_backup
from exam_bank.core.bank import ExamBankDB, Question



def _sandbox(tmp_path, monkeypatch):
    """Point the backup module at a temporary database and directory."""
    db = tmp_path / "bank.db"
    backups = tmp_path / "backups"
    backups.mkdir()
    monkeypatch.setattr(db_backup, "DB_PATH", db)
    monkeypatch.setattr(db_backup, "BACKUP_DIR", backups)
    return db, backups


def _seed(db_path, n):
    bank = ExamBankDB(db_path)
    for i in range(n):
        bank.save(Question(id=f"q{i}", stem=f"Question {i}?", key="k", distractors=["d"]))
    bank.close()


def _empty(db_path):
    bank = ExamBankDB(db_path)
    for q in bank.search(limit=500):
        bank.delete(q.id)
    bank.close()


def _count(backup_path):
    conn = sqlite3.connect(str(backup_path))
    try:
        return conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    finally:
        conn.close()


def _sandbox_backups(tmp_path):
    return sorted((tmp_path / "backups").glob("*.db"))


def _count_db(db_path):
    bank = ExamBankDB(db_path)
    try:
        return len(bank.search(limit=500))
    finally:
        bank.close()



class TestDBBackup:
    """Tests for backup/restore. Uses monkeypatch to override DB_PATH and BACKUP_DIR."""

    @pytest.fixture
    def db_env(self, tmp_path):
        """Set up a temp DB and backup dir, patching the module-level constants."""
        db_path = tmp_path / "test.db"
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        # Create a DB with some data
        db = ExamBankDB(db_path)
        db.save(Question(stem="Q1?", key="A", distractors=["B", "C"]))
        db.save(Question(stem="Q2?", key="X", distractors=["Y", "Z"]))
        db.close()

        with patch("exam_bank.core.db_backup.DB_PATH", db_path), \
             patch("exam_bank.core.db_backup.BACKUP_DIR", backup_dir):
            yield db_path, backup_dir

    def test_create_backup(self, db_env):
        from exam_bank.core.db_backup import create_backup
        db_path, backup_dir = db_env
        backup_path = create_backup(label="test")
        assert backup_path.exists()
        assert "test" in backup_path.name
        assert backup_path.parent == backup_dir

    def test_list_backups(self, db_env):
        from exam_bank.core.db_backup import create_backup, list_backups
        db_path, backup_dir = db_env
        create_backup(label="first")
        create_backup(label="second")
        backups = list_backups()
        assert len(backups) == 2
        # Should be sorted newest-first
        assert "second" in backups[0]["name"]

    def test_restore_backup(self, db_env):
        from exam_bank.core.db_backup import create_backup, restore_backup
        db_path, backup_dir = db_env

        # Create backup
        backup_path = create_backup(label="before_delete")

        # Modify the DB
        db = ExamBankDB(db_path)
        # Delete all questions
        for q in db.search():
            db.delete(q.id)
        assert db.count() == 0
        db.close()

        # Restore
        restore_backup(backup_path)

        # Verify data is back
        db = ExamBankDB(db_path)
        assert db.count() == 2
        db.close()

    def test_restore_creates_safety_backup(self, db_env):
        from exam_bank.core.db_backup import create_backup, restore_backup, list_backups
        db_path, backup_dir = db_env

        backup_path = create_backup(label="original")
        restore_backup(backup_path)

        backups = list_backups()
        names = [b["name"] for b in backups]
        assert any("pre_restore" in n for n in names)

    def test_delete_backup(self, db_env):
        from exam_bank.core.db_backup import create_backup, delete_backup, list_backups
        db_path, backup_dir = db_env

        backup_path = create_backup(label="to_delete")
        assert backup_path.exists()
        delete_backup(backup_path)
        assert not backup_path.exists()

    def test_get_db_info(self, db_env):
        from exam_bank.core.db_backup import get_db_info
        db_path, _ = db_env
        info = get_db_info()
        assert info["exists"] is True
        assert info["questions"] == 2
        assert info["size_kb"] > 0

    def test_get_db_info_no_db(self, tmp_path):
        with patch("exam_bank.core.db_backup.DB_PATH", tmp_path / "nonexistent.db"):
            from exam_bank.core.db_backup import get_db_info
            info = get_db_info()
            assert info["exists"] is False

    def test_restore_nonexistent_raises(self, db_env):
        from exam_bank.core.db_backup import restore_backup
        db_path, backup_dir = db_env
        with pytest.raises(FileNotFoundError):
            restore_backup(backup_dir / "no_such_backup.db")

    def test_create_backup_no_db_raises(self, tmp_path):
        with patch("exam_bank.core.db_backup.DB_PATH", tmp_path / "nonexistent.db"):
            from exam_bank.core.db_backup import create_backup
            with pytest.raises(FileNotFoundError):
                create_backup()


class TestBackupNamesAreUnique:
    """Two backups in the same second used to be one backup.

    The timestamp has one-second resolution and `sqlite3.connect` on an
    existing path overwrites it, so an author who took a backup, changed
    something and took another was left with a single file holding the later
    state. The restore path made it worse: `restore_backup` writes a
    `pre_restore` copy before reading its source, so restoring twice in the
    same second could land that copy on the file being restored from.
    """

    def test_two_backups_in_the_same_second_are_two_files(self, tmp_path, monkeypatch):
        db, backups = _sandbox(tmp_path, monkeypatch)
        _seed(db, 3)

        first = db_backup.create_backup(label="full")
        _empty(db)
        second = db_backup.create_backup(label="full")

        assert first != second
        assert {p.name for p in backups.glob("*.db")} == {first.name, second.name}

    def test_the_earlier_backup_still_holds_what_it_captured(self, tmp_path, monkeypatch):
        db, _ = _sandbox(tmp_path, monkeypatch)
        _seed(db, 3)

        first = db_backup.create_backup(label="full")
        _empty(db)
        db_backup.create_backup(label="full")

        assert _count(first) == 3, "the first backup was overwritten by the second"

    def test_restoring_a_pre_restore_backup_does_not_eat_it(self, tmp_path, monkeypatch):
        """The catastrophic path, and the reason the collision mattered.

        `restore_backup` writes a `pre_restore` copy BEFORE reading its
        source. Restoring a backup that is itself a `pre_restore` therefore
        generates the same name in the same second — so the safety copy landed
        on the very file being restored from, replacing the old bank with the
        current one. The restore then "succeeded" and changed nothing, and the
        backup it was reading no longer existed.
        """
        db, _ = _sandbox(tmp_path, monkeypatch)
        _seed(db, 3)
        full = db_backup.create_backup(label="full")

        _empty(db)                              # bank is now 0
        db_backup.restore_backup(full)          # back to 3; pre_restore holds 0
        assert _count_db(db) == 3

        saved = [p for p in _sandbox_backups(tmp_path) if "pre_restore" in p.name]
        assert len(saved) == 1
        rollback = saved[0]
        assert _count(rollback) == 0, "the safety copy did not capture the empty bank"

        # Roll back to it: a second pre_restore is written in the same second.
        db_backup.restore_backup(rollback)
        assert _count_db(db) == 0, "rolling back restored the wrong state"
