"""Tests for core/db_backup.py — backup, restore, and info utilities."""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from exam_bank.core.bank import ExamBankDB, Question


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
