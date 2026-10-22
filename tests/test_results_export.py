"""Export results to a separate SQLite file, and administer it (1.20.0)."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from exam_bank.api.app import app
from exam_bank.api.deps import get_db
from exam_bank.core import item_analysis as ia
from exam_bank.core import results_export as rx
from exam_bank.core import results_workbook as rw
from exam_bank.core.bank import ExamBankDB

COURSE = "developer-di-practitioner"


def seed(path):
    db = ExamBankDB(path)
    ia.ensure_schema(db.conn)
    for i in range(6):
        day = "2026-10-01T09:00:00" if i < 3 else "2026-10-20T09:00:00"
        db.conn.execute(
            "INSERT INTO attempts (attempt_id, candidate_id, course_id, course_tab, submitted_at, score, total, "
            "percentage, passed) VALUES (?,?,?,?,?,?,?,?,?)",
            (f"a{i}", f"cand_{i % 3}", COURSE, "DI", day, 3, 4, 0.75, 1))
        for q in ("q1", "q2"):
            db.conn.execute(
                "INSERT INTO responses (attempt_id, question_id, course_id, submitted_at, was_correct) "
                "VALUES (?,?,?,?,?)", (f"a{i}", q, COURSE, day, 1))
    db.conn.commit()
    return db


@pytest.fixture
def db(tmp_path):
    d = seed(tmp_path / "bank.db")
    yield d
    d.close()


def test_append_creates_the_file_and_is_idempotent(db, tmp_path):
    target = rx.resolve_target(str(tmp_path / "out.db"))
    first = rx.append(db.conn, target, rw.Filters())
    assert first["addedAttempts"] == 6 and first["addedAnswers"] == 12
    again = rx.append(db.conn, target, rw.Filters())
    assert again["addedAttempts"] == 0 and again["skippedAttempts"] == 6 and again["totalAttempts"] == 6
    s = rx.status(target)
    assert s["exists"] and s["attempts"] == 6 and s["answers"] == 12


def test_append_honours_the_filters(db, tmp_path):
    target = rx.resolve_target(str(tmp_path / "out.db"))
    r = rx.append(db.conn, target, rw.Filters(date_from="2026-10-15"))
    assert r["addedAttempts"] == 3 and r["addedAnswers"] == 6


def test_targets_that_are_not_ours_are_refused(db, tmp_path):
    with pytest.raises(rx.ResultsExportError, match="not a results database"):
        rx.append(db.conn, rx.resolve_target(str(tmp_path / "bank.db")), rw.Filters())
    stranger = tmp_path / "other.sqlite"
    sqlite3.connect(stranger).execute("CREATE TABLE t (x)").connection.commit()
    with pytest.raises(rx.ResultsExportError, match="not a results database"):
        rx.truncate(stranger, 0)
    with pytest.raises(rx.ResultsExportError, match="exam bank's own"):
        rx.resolve_target(str(tmp_path / "bank.db"), (tmp_path / "bank.db",))
    with pytest.raises(rx.ResultsExportError, match=r"\.db"):
        rx.resolve_target(str(tmp_path / "x.txt"))
    with pytest.raises(rx.ResultsExportError, match="folder does not exist"):
        rx.resolve_target(str(tmp_path / "nope" / "x.db"))


def test_backup_then_truncate_keeps_a_safety_copy(db, tmp_path):
    target = rx.resolve_target(str(tmp_path / "out.db"))
    rx.append(db.conn, target, rw.Filters())
    saved = rx.backup(target, "my label!")
    assert saved.parent == tmp_path / "out_backups" and "my_label_" in saved.name
    with pytest.raises(rx.ResultsExportError, match="now holds 6"):
        rx.truncate(target, 5)
    assert rx.status(target)["attempts"] == 6
    done = rx.truncate(target, 6)
    assert done["removedAttempts"] == 6 and done["removedAnswers"] == 12
    assert rx.status(target)["attempts"] == 0
    safety = sqlite3.connect(tmp_path / "out_backups" / done["safetyBackup"])
    assert safety.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 6
    safety.close()


def test_delete_by_filter_is_count_first(db, tmp_path):
    target = rx.resolve_target(str(tmp_path / "out.db"))
    rx.append(db.conn, target, rw.Filters())
    with pytest.raises(rx.ResultsExportError, match="Truncate"):
        rx.plan_delete(target, rw.Filters())
    flt = rw.Filters(candidate="cand_0")
    plan = rx.plan_delete(target, flt)
    assert plan["attempts"] == 2 and plan["answers"] == 4
    with pytest.raises(rx.ResultsExportError, match="now match 2"):
        rx.delete(target, flt, 3)
    done = rx.delete(target, flt, 2)
    assert done["removedAttempts"] == 2 and done["safetyBackup"]
    s = rx.status(target)
    assert s["attempts"] == 4 and s["answers"] == 8
    with pytest.raises(rx.ResultsExportError, match="nothing to remove"):
        rx.delete(target, flt, 0)


def test_the_admin_api(db, tmp_path):
    bank_path = db.db_path
    target = str(tmp_path / "api_out.db")

    def override():
        d = ExamBankDB(bank_path)
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[get_db] = override
    try:
        c = TestClient(app)
        st = c.get("/api/admin/results-db", params={"path": target}).json()
        assert st["exists"] is False and st["defaultPath"].endswith("exam_results.db")
        added = c.post("/api/admin/results-db/append", json={"path": target}).json()
        assert added["addedAttempts"] == 6
        late = c.post("/api/admin/results-db/append", json={"path": target, "date_from": "2026-10-15"}).json()
        assert late["addedAttempts"] == 0 and late["skippedAttempts"] == 3
        assert c.post("/api/admin/results-db/backup", json={"path": target, "label": "x"}).status_code == 201
        # Refusals: the bank itself, a bad filter, a missing count, a stale count.
        assert c.post("/api/admin/results-db/append", json={"path": str(bank_path)}).status_code == 422
        assert c.post("/api/admin/results-db/append", json={"path": target, "passed": "x"}).status_code == 422
        assert c.post("/api/admin/results-db/truncate", json={"path": target}).status_code == 400
        assert c.post("/api/admin/results-db/truncate", json={"path": target, "expect_count": 1}).status_code == 409
        prev = c.post("/api/admin/results-db/delete/preview", json={"path": target, "candidate": "cand_1"}).json()
        assert prev["attempts"] == 2
        assert c.post("/api/admin/results-db/delete/preview", json={"path": target}).status_code == 409
        gone = c.post("/api/admin/results-db/delete",
                      json={"path": target, "candidate": "cand_1", "expect_count": 2}).json()
        assert gone["removedAttempts"] == 2
        cut = c.post("/api/admin/results-db/truncate", json={"path": target, "expect_count": 4}).json()
        assert cut["removedAttempts"] == 4
        assert c.get("/api/admin/results-db", params={"path": target}).json()["attempts"] == 0
    finally:
        app.dependency_overrides.clear()
