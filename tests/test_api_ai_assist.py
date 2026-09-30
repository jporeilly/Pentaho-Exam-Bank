"""AI rewrite and AI review, over HTTP.

The model is stubbed throughout. What is being tested is the wiring, and the
wiring is where the danger is: `question_refinement` has carried eight AI
operations since the NiceGUI days with no test and no caller, and the first
one wired up turned out to assign the model's output straight onto the
Question it was handed.

The rule these pin: **an AI endpoint writes nothing.** It proposes, and an
author accepts by saving, which is the same look-then-act shape publishing
and importing already use. Here it is not a nicety — a model that edited the
bank directly would be the only contributor whose work nobody reviewed.
"""

import json

import pytest
from fastapi.testclient import TestClient

from exam_bank.api import deps
from exam_bank.api.app import app
from exam_bank.core import providers, question_refinement
from exam_bank.core.bank import ExamBankDB, Question


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "ai.db"


@pytest.fixture
def question(db_path):
    q = Question(
        id="q-ai", stem="What does a transformation do? (Choose one.)",
        question_type="single", key="Moves and shapes rows",
        distractors=["Prints a report", "Installs the server", "Backs up a database"],
        explanation="Moves and shapes rows - Correct. Prints a report - Incorrect.",
        topic="Basics",
    )
    database = ExamBankDB(db_path)
    try:
        database.save(q)
    finally:
        database.close()
    return q


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


@pytest.fixture(autouse=True)
def a_model_is_configured(monkeypatch):
    monkeypatch.setattr(providers, "active_provider", lambda: "ollama")
    monkeypatch.setattr(providers, "model_for", lambda _p: "a-model")


def _stub_generate(monkeypatch, reply: str):
    """Answer every model call with one canned reply."""
    monkeypatch.setattr(providers, "generate", lambda **kw: reply)


# --- rewrite -------------------------------------------------------------


REWRITE = json.dumps({
    "scenario": "A developer is building their first pipeline.",
    "stem": "What is a transformation responsible for? (Choose one.)",
    "key": "Moving and shaping rows",
    "distractors": ["Printing a report", "Installing the server", "Backing up a database"],
    "explanation": "Moving and shaping rows - Correct. Printing a report - Incorrect.",
})


def test_a_rewrite_is_returned_and_nothing_is_saved(client, question, db_path, monkeypatch):
    _stub_generate(monkeypatch, REWRITE)

    r = client.post("/api/questions/q-ai/ai/rewrite", json={})
    assert r.status_code == 200
    # The model is asked to state its count; the bank keeps the question only.
    assert r.json()["proposed"]["stem"] == "What is a transformation responsible for?"

    database = ExamBankDB(db_path)
    try:
        assert database.get("q-ai").stem == "What does a transformation do? (Choose one.)", (
            "the bank must be untouched until the author saves"
        )
    finally:
        database.close()


def test_the_stored_question_is_not_mutated_in_memory(question, monkeypatch):
    """`improve_question` used to assign onto its argument, so the caller's
    Question came back already rewritten - and anything that saved it
    afterwards persisted an AI edit nobody had accepted."""
    _stub_generate(monkeypatch, REWRITE)
    before = question.stem

    proposed = question_refinement.improve_question(question, "a-model")

    assert proposed is not question
    assert proposed.stem != before
    assert question.stem == before, "the input must come back untouched"


def test_a_rewrite_that_cannot_be_graded_says_so(client, question, monkeypatch):
    """The proposal is validated before the author is offered it: an
    'improvement' with no distractors cannot be got wrong."""
    _stub_generate(monkeypatch, json.dumps({
        "stem": "What is a transformation responsible for? (Choose one.)",
        "key": "Moving and shaping rows",
        "distractors": [],
    }))

    body = client.post("/api/questions/q-ai/ai/rewrite", json={}).json()
    assert body["problems"], "an ungradeable proposal must be flagged, not offered silently"


def test_an_unusable_model_reply_is_a_bad_gateway(client, question, monkeypatch):
    _stub_generate(monkeypatch, "I'm afraid I can't help with that.")

    r = client.post("/api/questions/q-ai/ai/rewrite", json={})
    assert r.status_code == 502


def test_no_model_configured_is_a_conflict_not_a_crash(client, question, monkeypatch):
    monkeypatch.setattr(providers, "model_for", lambda _p: "")

    r = client.post("/api/questions/q-ai/ai/rewrite", json={})
    assert r.status_code == 409
    assert "Settings" in r.json()["detail"]


def test_a_missing_question_is_404(client, question, monkeypatch):
    _stub_generate(monkeypatch, REWRITE)
    assert client.post("/api/questions/nope/ai/rewrite", json={}).status_code == 404


# --- review --------------------------------------------------------------


def test_the_review_separates_answer_faults_from_proofreading(client, question, monkeypatch):
    """"The key is also true of option C" and "a comma is missing" are not
    the same kind of news; a flat list buries the first under the second."""
    _stub_generate(monkeypatch, json.dumps([
        {"field": "distractor", "value": "Prints a report",
         "issue": "This is also correct in some contexts.", "severity": "error"},
    ]))

    body = client.post("/api/questions/q-ai/ai/review").json()
    assert body["answers"][0]["field"] == "distractor"
    assert body["answers"][0]["severity"] == "error"
    assert "prose" in body and "gradeable" in body


def test_the_review_writes_nothing(client, question, db_path, monkeypatch):
    _stub_generate(monkeypatch, "[]")
    before = ExamBankDB(db_path)
    try:
        snapshot = before.get("q-ai").stem
    finally:
        before.close()

    client.post("/api/questions/q-ai/ai/review")

    after = ExamBankDB(db_path)
    try:
        assert after.get("q-ai").stem == snapshot
    finally:
        after.close()


def test_a_reviewer_that_finds_nothing_returns_an_empty_list(client, question, monkeypatch):
    """An empty array is a valid and common answer, not a failure."""
    _stub_generate(monkeypatch, "[]")
    body = client.post("/api/questions/q-ai/ai/review").json()
    assert body["answers"] == []


def test_a_finding_with_an_unknown_field_is_kept_not_dropped(question, monkeypatch):
    """Silently discarding a model's answer is how a reviewer stops being
    one. An unrecognised field is reported against the option set."""
    _stub_generate(monkeypatch, json.dumps([
        {"field": "vibes", "issue": "Something is off about this.", "severity": "warning"},
    ]))

    found = question_refinement.review_answers(question, "a-model")
    assert len(found) == 1 and found[0]["field"] == "options"


def test_a_finding_with_no_issue_text_is_dropped(question, monkeypatch):
    """A row that says nothing is noise on a review screen."""
    _stub_generate(monkeypatch, json.dumps([
        {"field": "key", "issue": "   ", "severity": "error"},
        {"field": "key", "issue": "The key is wrong.", "severity": "error"},
    ]))

    found = question_refinement.review_answers(question, "a-model")
    assert [f["issue"] for f in found] == ["The key is wrong."]


def test_an_unrecognised_severity_becomes_a_warning(question, monkeypatch):
    """Not an error: only the model's explicit "error" earns that, or every
    malformed row would read as a fault in the question."""
    _stub_generate(monkeypatch, json.dumps([
        {"field": "key", "issue": "Possibly imprecise.", "severity": "catastrophic"},
    ]))

    assert question_refinement.review_answers(question, "a-model")[0]["severity"] == "warning"


def test_model_prose_that_is_not_json_is_not_a_finding(question, monkeypatch):
    _stub_generate(monkeypatch, "Looks good to me!")
    assert question_refinement.review_answers(question, "a-model") == []


# --- explanation and answer key (1.9.0) --------------------------------------
#
# The two NiceGUI-era operations kept when the other four were deleted. Both
# used to be unreachable; ai_assign_keys also wrote its answer straight onto
# the question. Both now propose, and are grounded on the course's own pages.


from exam_bank.core import grounding as grounding_mod  # noqa: E402
from exam_bank.core.bank import Certification  # noqa: E402
from exam_bank.utils.config import config  # noqa: E402


def _capture(monkeypatch, reply: str) -> list[dict]:
    calls: list[dict] = []

    def fake(**kw):
        calls.append(kw)
        return reply

    monkeypatch.setattr(providers, "generate", fake)
    return calls


EXPLANATION = ("Moves and shapes rows is right: a transformation reads, changes and writes "
               "rows. Prints a report is what Report Designer does. Installs the server is "
               "the installer's job. Backs up a database is a DBA task.")


def test_an_explanation_is_proposed_and_nothing_is_saved(client, question, db_path, monkeypatch):
    calls = _capture(monkeypatch, EXPLANATION)

    body = client.post("/api/questions/q-ai/ai/explanation").json()

    assert body["explanation"] == EXPLANATION
    assert body["unnamed"] == [] and body["groundedOn"] == ""
    prompt = calls[0]["prompt"]
    for option in ("Moves and shapes rows", "Prints a report", "Installs the server", "Backs up a database"):
        assert option in prompt
    assert "Never refer to an option by a letter" in prompt
    database = ExamBankDB(db_path)
    try:
        assert database.get("q-ai").explanation == question.explanation
    finally:
        database.close()


def test_an_explanation_that_skips_an_option_says_which(client, question, monkeypatch):
    _capture(monkeypatch, "Moves and shapes rows is right. Prints a report is wrong.")

    body = client.post("/api/questions/q-ai/ai/explanation").json()

    assert body["unnamed"] == ["Installs the server", "Backs up a database"]


def test_the_answer_key_is_proposed_by_option_text_and_nothing_is_saved(client, question, db_path, monkeypatch):
    # A B C D = the key, then the distractors, as the author sees them.
    _capture(monkeypatch, json.dumps({
        "analysis": {"B": {"quote": "Reports are printed.", "supported": True}},
        "correct_letters": ["B"], "key_source_text": "Reports are printed."}))

    body = client.post("/api/questions/q-ai/ai/answer").json()

    assert body["proposed"]["key"] == "Prints a report"
    assert "Moves and shapes rows" in body["proposed"]["distractors"]
    assert body["changed"] is True
    assert [a["option"] for a in body["analysis"] if a["correct"]] == ["Prints a report"]
    database = ExamBankDB(db_path)
    try:
        assert database.get("q-ai").key == "Moves and shapes rows"
    finally:
        database.close()


def test_an_answer_of_the_wrong_size_is_refused(client, question, monkeypatch):
    _capture(monkeypatch, json.dumps({"correct_letters": ["A", "B"]}))

    assert client.post("/api/questions/q-ai/ai/answer").status_code == 502


def test_taking_the_answer_clears_the_guessed_at_import_tag(client, db_path, monkeypatch):
    database = ExamBankDB(db_path)
    try:
        database.save(Question(id="q-guess", stem="Which step reads a CSV file?", key="Sort rows",
                               distractors=["CSV file input", "Table output"], tags=["key-unverified"]))
    finally:
        database.close()
    _capture(monkeypatch, json.dumps({"correct_letters": ["B"]}))

    body = client.post("/api/questions/q-guess/ai/answer").json()

    assert body["proposed"]["key"] == "CSV file input"
    assert "key-unverified" not in body["proposed"]["tags"]


def test_ai_assign_keys_changes_nothing_it_is_given(monkeypatch):
    q = Question(id="x", stem="Which two steps write rows?", question_type="multi",
                 key="", keys=[], distractors=["Table output", "Insert / Update", "Sort rows", "Filter rows"])
    before = json.dumps(q.__dict__, default=str, sort_keys=True)
    monkeypatch.setattr(providers, "generate",
                        lambda **kw: json.dumps({"correct_letters": ["A", "B"]}))

    found = question_refinement.ai_assign_keys(q, "a-model")

    assert found["keys"] == ["Table output", "Insert / Update"]
    assert json.dumps(q.__dict__, default=str, sort_keys=True) == before


@pytest.mark.parametrize("stem,qtype,keys,expected", [
    ("Which two steps write rows?", "multi", [], 2),
    ("Which three settings apply?", "multi", ["a", "b"], 3),
    ("What does it do? (Choose two.)", "multi", [], 2),
    ("Which step reads a file?", "single", [], 1),
    ("Which of these apply?", "multi", [], 2),
    ("Which of these apply?", "multi", ["a", "b", "c"], 3),
])
def test_the_number_of_answers_comes_from_the_question(stem, qtype, keys, expected):
    q = Question(stem=stem, question_type=qtype, keys=keys, key=keys[0] if keys else "")
    assert question_refinement.expected_key_count(q) == expected


# --- grounding --------------------------------------------------------------------


@pytest.fixture
def course(tmp_path, monkeypatch):
    root = tmp_path / "courses"
    c = root / "bi-developer-ct-practitioner"
    for lab, title in [("04-community-data-access", "Overview of Community Data Access"),
                       ("05-community-data-access-creating-a-cda", "Creating a CDA")]:
        (c / lab).mkdir(parents=True)
        (c / lab / "manifest.json").write_text(json.dumps({"title": title}), encoding="utf-8")
        (c / lab / "guide.md").write_text(
            f"## Section\n\n{title} prose: a parameter is written ${{name}} and declared "
            "with a type and a default. " * 3, encoding="utf-8")
    (c / "SUMMARY.md").write_text(
        "# Table of contents\n\n## Community Data Access\n\n"
        "* [Overview](04-community-data-access/guide.md)\n"
        "* [Creating a CDA](05-community-data-access-creating-a-cda/guide.md)\n", encoding="utf-8")
    (c / "course.json").write_text(json.dumps({"title": "CT"}), encoding="utf-8")
    monkeypatch.setattr(config, "pcm_courses_dir", str(root))
    return root


CT = Certification(name="CT Practitioner", source_type="pcm", source_ref="bi-developer-ct-practitioner")


def test_an_adopted_citation_finds_its_page(course):
    q = Question(source_file="Pentaho BI Developer - CT Practitioner: Community Data Access — "
                             "Creating a CDA (Parameters)", topic="Community Data Access")

    g = grounding_mod.grounding_for(q, CT, course)

    assert g.label == "Creating a CDA"
    assert "Creating a CDA prose" in g.text and "Overview of Community Data Access prose" not in g.text


def test_no_matching_page_falls_back_to_the_module(course):
    g = grounding_mod.grounding_for(Question(source_file="Something else", topic="Community Data Access"),
                                    CT, course)

    assert g.label == "the Community Data Access module"
    assert "Creating a CDA prose" in g.text and "Overview of Community Data Access prose" in g.text


def test_a_question_outside_any_course_is_not_grounded(course):
    assert grounding_mod.grounding_for(Question(topic="x"), Certification(name="Slides"), course).text == ""


def test_the_explanation_prompt_carries_the_course_page(client, db_path, course, monkeypatch):
    database = ExamBankDB(db_path)
    try:
        database.save_certification(CT)
        database.save(Question(id="ct-m2-q3", stem="How is the query written?", key="With ${status}",
                               distractors=["Concatenated", "One DataAccess per status"],
                               certification_id=CT.id, topic="Community Data Access",
                               source_file="Community Data Access — Creating a CDA"))
    finally:
        database.close()
    calls = _capture(monkeypatch, "With ${status} is right. Concatenated is wrong. One DataAccess per status is wrong.")

    body = client.post("/api/questions/ct-m2-q3/ai/explanation").json()

    assert body["groundedOn"] == "Creating a CDA"
    assert "Creating a CDA prose" in calls[0]["prompt"]
