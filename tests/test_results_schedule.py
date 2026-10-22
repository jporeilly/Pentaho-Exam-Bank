"""The daily (and manual) load of the results workbook into the results database."""
import sqlite3
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from exam_bank.api.app import app
from exam_bank.api.deps import get_db
from exam_bank.core import results_export as rx
from exam_bank.core import results_schedule as rs
from exam_bank.core.bank import ExamBankDB
from tests.test_results_workbook import workbook


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "SETTINGS_FILE", tmp_path / "sched.json")
    monkeypatch.setattr(rs, "DB_PATH", tmp_path / "bank.db")
    xlsx = tmp_path / "results.xlsx"
    xlsx.write_bytes(workbook())
    bank = tmp_path / "bank.db"
    ExamBankDB(bank).close()
    return tmp_path, xlsx, bank


def test_run_loads_idempotently_and_records_the_outcome(env):
    tmp, xlsx, bank = env
    rs.save_settings(True, str(xlsx), str(tmp / "out.db"), "02:00", (bank,))
    first = rs.run_load(bank, (bank,))
    assert first["appended"]["addedAttempts"] == 4
    again = rs.run_load(bank, (bank,))
    assert again["appended"]["addedAttempts"] == 0 and again["appended"]["totalAttempts"] == 4
    s = rs.load()
    assert s["lastOk"] is True and "4 attempts in all" in s["lastMessage"]
    assert sqlite3.connect(tmp / "out.db").execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 4


def test_a_missing_workbook_is_recorded_not_raised_by_the_scheduler(env):
    tmp, xlsx, bank = env
    rs.save_settings(True, str(tmp / "nope.xlsx"), str(tmp / "out.db"), "00:00", (bank,))
    with pytest.raises(rx.ResultsExportError, match="not there"):
        rs.run_load(bank, (bank,))
    assert rs.load()["lastOk"] is False
    assert rs.run_if_due() is False                    # failed minutes ago: retried hourly, not now


def test_due_rules(env):
    tmp, xlsx, bank = env
    s = {**rs.DEFAULTS, "enabled": True, "workbookPath": "w.xlsx", "targetPath": "t.db", "time": "02:00"}
    at = lambda h: datetime(2026, 10, 22, h, 0)
    assert not rs.due(s, at(1)) and rs.due(s, at(3))
    assert not rs.due({**s, "enabled": False}, at(3))
    assert not rs.due({**s, "lastSuccess": "2026-10-22T02:00:05"}, at(9))
    assert rs.due({**s, "lastSuccess": "2026-10-21T02:00:05"}, at(9))
    failed = {**s, "lastOk": False, "lastAttempt": "2026-10-22T08:30:00"}
    assert not rs.due(failed, datetime(2026, 10, 22, 9, 0)) and rs.due(failed, datetime(2026, 10, 22, 9, 31))


def test_the_api_saves_validates_and_runs_manually(env):
    tmp, xlsx, bank = env

    def override():
        d = ExamBankDB(bank)
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[get_db] = override
    try:
        c = TestClient(app)
        body = {"enabled": True, "workbook_path": str(xlsx), "target_path": str(tmp / "o.db"), "time": "03:30"}
        assert c.put("/api/admin/results-schedule", json={**body, "time": "3pm"}).status_code == 422
        assert c.put("/api/admin/results-schedule", json={**body, "workbook_path": "x.csv"}).status_code == 422
        assert c.put("/api/admin/results-schedule", json={**body, "target_path": str(bank)}).status_code == 422
        assert c.put("/api/admin/results-schedule", json=body).json()["time"] == "03:30"
        got = c.get("/api/admin/results-schedule").json()
        assert got["enabled"] is True and got["defaultTarget"].endswith("exam_results.db")
        ran = c.post("/api/admin/results-schedule/run").json()
        assert ran["appended"]["addedAttempts"] == 4
        xlsx.unlink()
        assert c.post("/api/admin/results-schedule/run").status_code == 409
        assert c.get("/api/admin/results-schedule").json()["lastOk"] is False
    finally:
        app.dependency_overrides.clear()
