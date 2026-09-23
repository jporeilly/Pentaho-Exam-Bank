"""Importing a file of questions, over HTTP.

Two things are being tested and they are different. The first is that a file
is recognised for what it IS rather than for what its extension claims — a
plain-text dump saved as .csv, a Content Manager exam.json, a Moodle export —
because guessing wrong imports a plausible-looking wrong shape rather than
failing. The second is that preview writes nothing: an import is somebody
else's work landing in the bank, and the author decides after seeing it.
"""

import json

import pytest
from fastapi.testclient import TestClient

from exam_bank.api import deps
from exam_bank.api.app import app
from exam_bank.core.bank import Certification, ExamBankDB, Question

CSV = (
    "Stem,Key,Distractor1,Distractor2,Topic\n"
    "Which step reads a delimited file?,CSV file input,Table output,Sort rows,Getting Started\n"
    "Which step sorts rows?,Sort rows,Table output,Dummy,Getting Started\n"
)

# No header row, and the A:/B:/C: option pattern - a text dump that happens to
# be saved as .csv. Read as CSV it yields one column of nonsense.
TEXT_DUMP = (
    "Which step reads a delimited file?\n"
    "A:\n"
    "CSV file input\n"
    "B:\n"
    "Table output\n"
    "C:\n"
    "Sort rows\n"
)

PCM_EXAM = {
    "title": "Wrap-Up Check",
    "passMark": 60,
    "questions": [
        {
            "id": "m1-q1",
            "prompt": "Which step reads a delimited file?",
            "options": ["CSV file input", "Table output", "Sort rows"],
            "correct": 0,
            "module": "See It Work",
            "source": "Lab 1 - Your First Win",
        }
    ],
}


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "import.db"


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


def upload(client, name, content):
    data = content if isinstance(content, bytes) else content.encode("utf-8")
    return client.post("/api/import/preview", files={"file": (name, data)})


def count_in(db_path):
    database = ExamBankDB(db_path)
    try:
        return len(database.search(limit=5000))
    finally:
        database.close()


# --- recognising the file for what it is ----------------------------------


def test_a_csv_is_read_as_csv(client):
    body = upload(client, "questions.csv", CSV).json()

    assert body["format"] == "csv"
    assert body["count"] == 2
    assert body["questions"][0]["question"]["key"] == "CSV file input"


def test_a_text_dump_saved_as_csv_is_not_read_as_csv(client):
    """The extension says CSV and the content says otherwise. Read as CSV this
    yields one column of nonsense rather than an error, so the content wins."""
    body = upload(client, "questions.csv", TEXT_DUMP).json()

    assert body["format"] == "text"
    assert body["count"] == 1


def test_the_text_format_warns_that_the_key_was_guessed(client):
    """The format cannot mark a correct answer, so `import_from_text` takes
    the FIRST option as the key — positionally, silently.

    The resulting question is perfectly gradeable, so `problems` is empty and
    nothing else in the app will ever flag it. That makes this note the only
    warning an author gets, and it has to say what actually happened. The
    NiceGUI tab told authors the opposite ("all options default to
    distractors"), which is not what the importer does.
    """
    body = upload(client, "questions.csv", TEXT_DUMP).json()
    question = body["questions"][0]

    assert question["question"]["key"] == "CSV file input", "first option is the key"
    assert question["problems"] == [], "it is gradeable, which is the danger"
    note = body["formatNote"].lower()
    assert "first" in note and "key" in note, f"the note must say the key was guessed: {note}"


def test_a_pcm_exam_json_is_recognised(client):
    body = upload(client, "exam.json", json.dumps(PCM_EXAM)).json()

    assert body["format"] == "pcm-exam"
    assert body["questions"][0]["question"]["id"] == "m1-q1", "authored id lost"


def test_the_banks_own_json_export_is_not_mistaken_for_a_pcm_exam(client):
    """Both are .json. One is a top-level array, the other an object with
    questions[].prompt."""
    own = [{"id": "x1", "stem": "Which step?", "key": "A", "distractors": ["B"]}]
    body = upload(client, "export.json", json.dumps(own)).json()

    assert body["format"] == "json"


def test_an_unreadable_extension_names_what_is_supported(client):
    response = upload(client, "notes.docx", "irrelevant")

    assert response.status_code == 415
    assert "CSV" in response.json()["detail"]


def test_unrecognised_xml_is_refused_by_content(client):
    response = upload(client, "data.xml", "<root><thing/></root>")

    assert response.status_code == 415
    assert "QTI" in response.json()["detail"]


def test_an_empty_file_is_refused(client):
    response = upload(client, "empty.csv", "")

    assert response.status_code == 400


def test_a_file_that_parses_to_nothing_is_refused_not_reported_as_zero(client):
    """Nothing found and nothing readable look identical to a caller, and only
    one of them is the author's mistake to fix."""
    response = upload(client, "headers-only.csv", "Stem,Key,Distractor1\n")

    assert response.status_code == 422
    assert "held no questions" in response.json()["detail"]


def test_a_malformed_file_reports_the_readers_own_message(client):
    response = upload(client, "broken.json", "{ not json")

    assert response.status_code == 422
    assert "broken.json" in response.json()["detail"]


# --- what preview tells the author ----------------------------------------


def test_preview_writes_nothing(client, db_path):
    upload(client, "questions.csv", CSV)

    assert count_in(db_path) == 0


def test_ungradeable_questions_are_flagged_with_the_editors_own_words(client):
    """Same rules as the editor, from `core/validation.py`. A question the
    editor would refuse to save must not arrive unremarked."""
    csv = "Stem,Key,Distractor1\nWhich step reads a file?,,Table output\n"
    body = upload(client, "nokey.csv", csv).json()

    problems = body["questions"][0]["problems"]
    assert any("cannot be graded" in p["message"] for p in problems)
    assert body["gradeable"] == 0


def test_a_question_already_in_the_bank_is_flagged_as_a_duplicate(client, db_path):
    database = ExamBankDB(db_path)
    database.save(Question(
        id="existing", stem="Which step reads a delimited file?",
        key="CSV file input", distractors=["Table output"],
    ))
    database.close()

    body = upload(client, "questions.csv", CSV).json()
    first = body["questions"][0]

    assert first["duplicate_of"] == "existing"
    assert first["duplicate_score"] >= 85
    assert body["duplicates"] == 1


def test_nothing_is_flagged_as_a_duplicate_of_an_empty_bank(client):
    body = upload(client, "questions.csv", CSV).json()

    assert body["duplicates"] == 0


# --- committing -----------------------------------------------------------


def commit(client, preview, **kw):
    return client.post("/api/import/commit", json={
        "questions": [q["question"] for q in preview["questions"]], **kw,
    })


def test_commit_saves_the_chosen_questions(client, db_path):
    preview = upload(client, "questions.csv", CSV).json()
    response = commit(client, preview)

    assert response.status_code == 200
    assert response.json()["saved"] == 2
    assert count_in(db_path) == 2


def test_commit_refuses_a_question_the_editor_would_not_save(client, db_path):
    """An import that can put an ungradeable question in makes the editor's
    rule a suggestion."""
    csv = "Stem,Key,Distractor1\nWhich step reads a file?,,Table output\n"
    preview = upload(client, "nokey.csv", csv).json()
    body = commit(client, preview).json()

    assert body["saved"] == 0
    assert len(body["refused"]) == 1
    assert "cannot be graded" in body["refused"][0]["reason"]
    assert count_in(db_path) == 0


def test_a_mixed_file_saves_the_good_and_names_the_rest(client, db_path):
    csv = (
        "Stem,Key,Distractor1\n"
        "Which step reads a delimited file?,CSV file input,Table output\n"
        "Which step sorts rows?,,Table output\n"
    )
    preview = upload(client, "mixed.csv", csv).json()
    body = commit(client, preview).json()

    assert body["saved"] == 1
    assert len(body["refused"]) == 1
    assert count_in(db_path) == 1


def test_commit_assigns_the_certification_and_topic(client, db_path):
    database = ExamBankDB(db_path)
    certification = Certification(name="DI Practitioner", source_type="pcm",
                                  source_ref="developer-di-practitioner")
    database.save_certification(certification)
    database.close()

    preview = upload(client, "questions.csv", CSV).json()
    commit(client, preview, certification_id=certification.id, topic="Lab 1")

    database = ExamBankDB(db_path)
    try:
        saved = database.search(limit=10)
        assert {q.certification_id for q in saved} == {certification.id}
        assert {q.topic for q in saved} == {"Lab 1"}
        assert {q.source_type for q in saved} == {"pcm"}
    finally:
        database.close()


def test_imported_questions_land_as_drafts(client, db_path):
    """Somebody else's work entering the bank has not been reviewed here yet,
    whatever status the file claimed."""
    preview = upload(client, "questions.csv", CSV).json()
    for q in preview["questions"]:
        q["question"]["status"] = "approved"
    commit(client, preview)

    database = ExamBankDB(db_path)
    try:
        assert {q.status for q in database.search(limit=10)} == {"draft"}
    finally:
        database.close()


def test_committing_to_an_unknown_certification_is_refused(client, db_path):
    preview = upload(client, "questions.csv", CSV).json()
    response = commit(client, preview, certification_id="nope")

    assert response.status_code == 404
    assert count_in(db_path) == 0


def test_committing_nothing_is_refused(client):
    response = client.post("/api/import/commit", json={"questions": []})

    assert response.status_code == 400
