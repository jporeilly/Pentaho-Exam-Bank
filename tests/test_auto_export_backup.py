"""Auto-export on save, the default export format, and automatic backups.

All three were settings with nothing behind them until 1.10.0: saved, shown
(until 1.8.1 removed the controls as inert), and never read.
"""

import csv
import time
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from exam_bank.api import deps
from exam_bank.api.app import app
from exam_bank.core import auto_backup, auto_export, db_backup
from exam_bank.core.bank import ExamBankDB, Question
from exam_bank.utils import config as config_module
from exam_bank.utils.config import config


@pytest.fixture
def bank(tmp_path):
    path = tmp_path / "bank.db"
    db = ExamBankDB(path)
    for n in range(3):
        db.save(Question(id=f"t-m1-q{n + 1}", stem=f"Question {n}?", key="a", distractors=["b", "c"]))
    db.close()
    return path


@pytest.fixture
def export_to(tmp_path, monkeypatch):
    out = tmp_path / "exports"
    monkeypatch.setattr(config, "output_folder", str(out))
    return out


# --- which requests change the bank ------------------------------------------------------


@pytest.mark.parametrize("method,path,changes", [
    ("PUT", "/api/questions/t-m1-q1", True),
    ("POST", "/api/questions/t-m1-q1/status", True),
    ("DELETE", "/api/questions/t-m1-q1", True),
    ("POST", "/api/questions/t-m1-q1/ai/rewrite", False),       # proposes only
    ("POST", "/api/questions/t-m1-q1/ai/explanation", False),
    ("GET", "/api/questions/t-m1-q1", False),
    ("POST", "/api/jobs/j1/commit", True),
    ("POST", "/api/jobs/j1/cancel", False),
    ("POST", "/api/import/commit", True),
    ("POST", "/api/import/preview", False),
    ("POST", "/api/courses/sync", True),
    ("POST", "/api/courses/sync/plan", False),
    ("POST", "/api/admin/questions/delete", True),
    ("POST", "/api/admin/questions/delete/preview", False),
    ("POST", "/api/admin/backups/x.db/restore", True),
    ("POST", "/api/admin/backups", False),
])
def test_only_a_change_to_the_questions_triggers_an_export(method, path, changes):
    assert auto_export.changes_bank(method, path) is changes


# --- the export ---------------------------------------------------------------------------


def test_the_whole_bank_is_written_in_the_default_format(bank, export_to, monkeypatch):
    monkeypatch.setattr(config, "default_export_format", "csv")

    path = auto_export.export_now(bank)

    assert path == export_to / "exam-bank.csv"
    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert len(rows) == 4                               # header + three questions
    assert auto_export.last["count"] == 3 and auto_export.last["error"] == ""
    assert not list(export_to.glob(".*writing"))        # written beside, then renamed


def test_the_file_name_says_the_format(export_to, monkeypatch):
    names = {}
    for fmt in ("csv", "json", "qti", "moodle", "text", "docx"):
        monkeypatch.setattr(config, "default_export_format", fmt)
        names[fmt] = auto_export.target().name
    assert names == {"csv": "exam-bank.csv", "json": "exam-bank.json", "qti": "exam-bank-qti.xml",
                     "moodle": "exam-bank-moodle.xml", "text": "exam-bank-text.txt",
                     "docx": "exam-bank.docx"}


def test_an_unknown_format_falls_back_to_csv(export_to, monkeypatch):
    monkeypatch.setattr(config, "default_export_format", "pptx")
    assert auto_export.target().name == "exam-bank.csv"


def test_a_burst_of_changes_exports_once_and_only_when_on(monkeypatch):
    runs = []
    monkeypatch.setattr(auto_export, "export_now", lambda *a, **k: runs.append(1))
    monkeypatch.setattr(auto_export, "DELAY", 0.1)

    assert auto_export.schedule() is False             # off: nothing scheduled
    monkeypatch.setattr(config, "auto_export_on_save", True)
    for _ in range(5):
        assert auto_export.schedule() is True
    time.sleep(0.5)

    assert runs == [1]


def test_a_save_through_the_api_schedules_an_export_and_a_failed_one_does_not(bank, monkeypatch):
    scheduled = []
    monkeypatch.setattr(auto_export, "schedule", lambda: scheduled.append(1))

    def override():
        db = ExamBankDB(bank)
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[deps.get_db] = override
    try:
        client = TestClient(app)
        assert client.put("/api/questions/t-m1-q1", json={"stem": "Changed?"}).status_code == 200
        assert client.put("/api/questions/no-such", json={"stem": "x?"}).status_code == 404
        assert client.get("/api/questions/t-m1-q1").status_code == 200
    finally:
        app.dependency_overrides.clear()

    assert scheduled == [1]


# --- automatic backups --------------------------------------------------------------------


@pytest.fixture
def backups(tmp_path, bank, monkeypatch):
    folder = tmp_path / "backups"
    folder.mkdir()
    monkeypatch.setattr(db_backup, "DB_PATH", bank)
    monkeypatch.setattr(db_backup, "BACKUP_DIR", folder)
    monkeypatch.setattr(auto_backup, "BACKUP_DIR", folder)
    monkeypatch.setattr(config, "auto_backup_enabled", True)
    monkeypatch.setattr(config, "auto_backup_interval_hours", 24)
    monkeypatch.setattr(config, "auto_backup_max_count", 3)
    return folder


def test_nothing_is_backed_up_while_the_setting_is_off(backups, monkeypatch):
    monkeypatch.setattr(config, "auto_backup_enabled", False)
    assert auto_backup.run_if_due() is None
    assert list(backups.iterdir()) == []


def test_a_backup_is_taken_when_due_and_not_again_until_the_interval_passes(backups):
    first = auto_backup.run_if_due()

    assert first is not None and first.name.endswith("_auto.db")
    assert auto_backup.run_if_due() is None
    assert auto_backup.due(datetime.now() + timedelta(hours=25)) is True


def test_only_the_newest_automatic_backups_are_kept_and_yours_never_go(backups):
    base = datetime(2026, 9, 1, 12, 0, 0)
    for day in range(6):
        stamp = (base + timedelta(days=day)).strftime("%Y%m%d_%H%M%S")
        (backups / f"exam_bank_{stamp}_auto.db").write_bytes(b"x")
    mine = backups / "exam_bank_20260801_120000_before-the-cull.db"
    mine.write_bytes(b"x")
    safety = backups / "exam_bank_20260802_120000_pre_restore.db"
    safety.write_bytes(b"x")

    assert auto_backup.prune() == 3

    left = sorted(p.name for p in backups.iterdir())
    assert mine.name in left and safety.name in left
    assert [n for n in left if n.endswith("_auto.db")] == [
        "exam_bank_20260904_120000_auto.db", "exam_bank_20260905_120000_auto.db",
        "exam_bank_20260906_120000_auto.db"]


# --- settings -------------------------------------------------------------------------------


@pytest.fixture
def settings_client(tmp_path, monkeypatch):
    before = {f: getattr(config, f) for f in config.__dataclass_fields__}
    monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / "config.json")
    yield TestClient(app)
    for field, value in before.items():
        setattr(config, field, value)


def test_the_new_settings_are_writable_and_checked(settings_client):
    put = lambda **s: settings_client.put("/api/settings", json={"settings": s})

    assert put(default_export_format="docx").status_code == 200
    assert put(default_export_format="pdf").status_code == 400
    assert put(auto_backup_enabled=True, auto_backup_interval_hours=6,
               auto_backup_max_count=10).status_code == 200
    assert put(auto_backup_interval_hours=0).status_code == 400
    assert put(auto_backup_max_count=500).status_code == 400

    body = settings_client.get("/api/settings").json()
    assert body["settings"]["default_export_format"] == "docx"
    assert {f["format"] for f in body["choices"]["exportFormats"]} == {
        "csv", "json", "qti", "moodle", "text", "docx"}
    assert body["autoExport"]["target"].endswith("exam-bank.docx")
    assert "error" in body["autoBackup"]
