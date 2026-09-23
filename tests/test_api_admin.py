"""Backups and bulk deletion, over HTTP.

This is the only part of the app with no undo short of a backup, so the tests
are mostly about refusals: deleting a different number than was shown,
deleting the whole bank by leaving filters blank, and restoring a "backup"
that is really a path to somewhere else.

Both the database and the backup directory are redirected to a temporary one.
Without that a test run would back up, delete from, and restore the
developer's real bank.
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from exam_bank.api import deps
from exam_bank.api.app import app
from exam_bank.core import db_backup
from exam_bank.core.bank import Certification, ExamBankDB, Question


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "admin.db"


@pytest.fixture(autouse=True)
def sandboxed_files(tmp_path, db_path, monkeypatch):
    """Point the backup module at a temporary database and directory."""
    backups = tmp_path / "backups"
    backups.mkdir()
    monkeypatch.setattr(db_backup, "DB_PATH", db_path)
    monkeypatch.setattr(db_backup, "BACKUP_DIR", backups)
    return backups


@pytest.fixture
def seeded(db_path):
    database = ExamBankDB(db_path)
    cert = database.save_certification(Certification(name="DI Practitioner"))
    other = database.save_certification(Certification(name="Other"))
    for i in range(6):
        database.save(Question(
            id=f"draft-{i}", stem=f"Draft question {i}?", key="Right",
            distractors=["Wrong"], topic="Getting Started",
            certification_id=cert.id, status="draft",
        ))
    for i in range(4):
        database.save(Question(
            id=f"approved-{i}", stem=f"Approved question {i}?", key="Right",
            distractors=["Wrong"], topic="Advanced",
            certification_id=other.id, status="approved",
        ))
    database.close()
    return cert


@pytest.fixture
def client(db_path):
    def override():
        database = ExamBankDB(db_path)
        try:
            yield database
        finally:
            database.close()

    app.dependency_overrides[deps.get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def count_in(db_path):
    database = ExamBankDB(db_path)
    try:
        return len(database.search(limit=5000))
    finally:
        database.close()


# --- previewing a deletion -------------------------------------------------


def test_a_preview_counts_what_would_go(client, seeded, db_path):
    body = client.post("/api/admin/questions/delete/preview",
                       json={"status": "draft"}).json()

    assert body["total"] == 6
    assert body["everything"] is False
    assert count_in(db_path) == 10, "the preview deleted something"


def test_a_preview_breaks_the_set_down(client, seeded):
    """A number alone is not something an author can check. The breakdown is
    what tells them they are looking at the set they meant."""
    body = client.post("/api/admin/questions/delete/preview", json={}).json()

    assert body["byStatus"] == {"draft": 6, "approved": 4}
    names = {c["name"]: c["count"] for c in body["byCertification"]}
    assert names == {"DI Practitioner": 6, "Other": 4}


def test_a_preview_shows_a_few_of_the_actual_questions(client, seeded):
    body = client.post("/api/admin/questions/delete/preview",
                       json={"topic": "Advanced"}).json()

    assert body["sample"], "no sample to recognise the set by"
    assert all("Approved question" in stem for stem in body["sample"])


def test_an_unfiltered_preview_says_it_is_everything(client, seeded):
    """Looking is allowed; it is the deletion that has to be asked for."""
    body = client.post("/api/admin/questions/delete/preview", json={}).json()

    assert body["total"] == 10
    assert body["everything"] is True


def test_a_question_with_no_certification_is_named_not_blank(client, db_path):
    database = ExamBankDB(db_path)
    database.save(Question(id="orphan", stem="Whose is this?", key="k",
                           distractors=["d"]))
    database.close()

    body = client.post("/api/admin/questions/delete/preview", json={}).json()

    assert body["byCertification"][0]["name"] == "(no certification)"


# --- deleting --------------------------------------------------------------


def test_a_filtered_deletion_removes_exactly_that_set(client, seeded, db_path):
    response = client.post("/api/admin/questions/delete",
                           json={"status": "draft", "expect_count": 6})

    assert response.json()["deleted"] == 6
    assert count_in(db_path) == 4


def test_deleting_without_a_preview_is_refused(client, seeded, db_path):
    response = client.post("/api/admin/questions/delete", json={"status": "draft"})

    assert response.status_code == 400
    assert "preview" in response.json()["detail"]
    assert count_in(db_path) == 10


def test_a_count_that_no_longer_matches_is_refused(client, seeded, db_path):
    """The bank changed after the author was shown the number — generation
    finishing, an import landing, another window."""
    response = client.post("/api/admin/questions/delete",
                           json={"status": "draft", "expect_count": 3})

    assert response.status_code == 409
    assert "now matches 6" in response.json()["detail"]
    assert count_in(db_path) == 10


def test_an_unfiltered_deletion_is_refused_unless_asked_for(client, seeded, db_path):
    """An empty filter is far more often a cleared one than a request to
    empty the bank."""
    response = client.post("/api/admin/questions/delete", json={"expect_count": 10})

    assert response.status_code == 409
    assert "every question" in response.json()["detail"]
    assert count_in(db_path) == 10


def test_the_whole_bank_can_be_deleted_when_it_is_asked_for(client, seeded, db_path):
    response = client.post("/api/admin/questions/delete",
                           json={"expect_count": 10, "everything": True})

    assert response.json()["deleted"] == 10
    assert count_in(db_path) == 0


def test_a_selection_matching_nothing_is_refused(client, seeded, db_path):
    response = client.post("/api/admin/questions/delete",
                           json={"status": "rejected", "expect_count": 0})

    assert response.status_code == 409
    assert "nothing to delete" in response.json()["detail"]


def test_deleting_leaves_the_questions_that_did_not_match(client, seeded, db_path):
    client.post("/api/admin/questions/delete",
                json={"certification_id": seeded.id, "expect_count": 6})

    database = ExamBankDB(db_path)
    try:
        assert {q.status for q in database.search(limit=50)} == {"approved"}
    finally:
        database.close()


# --- backups ---------------------------------------------------------------


def test_a_backup_can_be_made_and_is_listed(client, seeded):
    made = client.post("/api/admin/backups", json={"label": "before the cull"})

    assert made.status_code == 201
    name = made.json()["name"]
    assert "before-the-cull" in name, "the label is what it gets recognised by"
    assert name in {b["name"] for b in client.get("/api/admin/database").json()["backups"]}


def test_the_database_status_reports_what_is_in_it(client, seeded):
    body = client.get("/api/admin/database").json()

    assert body["database"]["exists"] is True
    assert body["database"]["questions"] == 10


def test_restoring_brings_back_what_was_deleted(client, seeded, db_path):
    name = client.post("/api/admin/backups", json={}).json()["name"]
    client.post("/api/admin/questions/delete",
                json={"expect_count": 10, "everything": True})
    assert count_in(db_path) == 0

    client.post(f"/api/admin/backups/{name}/restore")

    assert count_in(db_path) == 10


def test_restoring_backs_up_what_it_is_about_to_replace(client, seeded, db_path):
    """The difference between an undoable mistake and a lost bank. Its name is
    returned rather than left for the author to find."""
    name = client.post("/api/admin/backups", json={}).json()["name"]
    client.post("/api/admin/questions/delete",
                json={"expect_count": 10, "everything": True})

    body = client.post(f"/api/admin/backups/{name}/restore").json()

    assert "pre_restore" in body["safetyBackup"]
    # And it really is the emptied bank, so the restore itself is undoable.
    client.post(f"/api/admin/backups/{body['safetyBackup']}/restore")
    assert count_in(db_path) == 0


def test_a_backup_can_be_deleted(client, seeded):
    name = client.post("/api/admin/backups", json={}).json()["name"]

    body = client.delete(f"/api/admin/backups/{name}").json()

    assert name not in {b["name"] for b in body["backups"]}


# --- what a backup name may be ---------------------------------------------


@pytest.mark.parametrize("name", [
    "../../../etc/passwd",
    "..%2F..%2Fsecrets",
    "sub/dir",
    "back\\slash",
])
def test_a_path_cannot_be_passed_off_as_a_backup_name(
    client, name, seeded, db_path, sandboxed_files
):
    """A client that could hand over a path could restore the bank from any
    file on the machine.

    Asserted on the EFFECT rather than the status code. Several of these do
    not match the route at all and come back 405, which is a perfectly safe
    outcome — the property that matters is that the bank is untouched and
    nothing new appeared in the backup directory.
    """
    before = {p.name for p in sandboxed_files.glob("*.db")}

    response = client.post(f"/api/admin/backups/{name}/restore")

    assert response.status_code >= 400, response.text
    assert count_in(db_path) == 10, "the bank was restored from somewhere"
    assert {p.name for p in sandboxed_files.glob("*.db")} == before


def test_deleting_by_a_path_leaves_the_file_alone(client, sandboxed_files, tmp_path):
    outside = tmp_path / "not-a-backup.db"
    outside.write_bytes(b"important")

    response = client.delete("/api/admin/backups/..%2Fnot-a-backup")

    assert response.status_code >= 400
    assert outside.exists(), "a file outside the backup directory was deleted"
    assert outside.read_bytes() == b"important"


def test_an_unknown_backup_is_a_404(client, seeded):
    assert client.post("/api/admin/backups/nope/restore").status_code == 404


def test_a_restored_database_is_readable_afterwards(client, seeded, db_path):
    """A restore that leaves a corrupt file passes every check above and fails
    on the next query."""
    name = client.post("/api/admin/backups", json={}).json()["name"]
    client.post(f"/api/admin/backups/{name}/restore")

    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()
