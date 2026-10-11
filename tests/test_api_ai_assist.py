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


EXPLANATION = ("A transformation **reads, changes and writes rows**: each step takes the rows "
               "the step before it produced.\n\nThat makes it the place where data is moved "
               "and shaped on its way to its target.")


def test_an_explanation_is_proposed_and_nothing_is_saved(client, question, db_path, monkeypatch):
    calls = _capture(monkeypatch, EXPLANATION)

    body = client.post("/api/questions/q-ai/ai/explanation").json()

    assert body["explanation"] == EXPLANATION
    assert body["notes"] == [] and body["groundedOn"] == ""
    prompt = calls[0]["prompt"]
    # The model sees every option, so it knows what was being chosen between...
    for option in ("Moves and shapes rows", "Prints a report", "Installs the server", "Backs up a database"):
        assert option in prompt
    # ...and is told to explain the correct one only, in paragraphs, with bold.
    assert "why the correct answer is correct, and nothing else" in prompt
    assert "do not discuss" in prompt and "**bold**" in prompt
    assert "never by a letter" in prompt
    database = ExamBankDB(db_path)
    try:
        assert database.get("q-ai").explanation == question.explanation
    finally:
        database.close()


def test_an_explanation_that_still_judges_every_option_says_so(client, question, monkeypatch):
    # The pre-1.14.0 form, which a model can slip back into.
    _capture(monkeypatch, "'Moves and shapes rows' — Correct: it does. "
                          "'Prints a report' — Incorrect: that is Report Designer.")

    body = client.post("/api/questions/q-ai/ai/explanation").json()

    assert "Correct/Incorrect" in body["notes"][0]
    # Quoting each option by its text breaks the writing standard too (1.15.0).
    assert any("Single quotes around 'Moves and shapes rows'" in n for n in body["notes"][1:])


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


# --- the rewrite's rules -------------------------------------------------------


def test_the_rewrite_asks_for_a_proofread_and_a_correct_only_explanation(question, monkeypatch):
    calls = _capture(monkeypatch, REWRITE)

    question_refinement.improve_question(question, "a-model")

    prompt = calls[0]["prompt"]
    # A polish: the reviewed wording stays unless it is wrong...
    assert "Fix every error; change nothing that is not one" in prompt
    assert "keep it word for word" in prompt
    assert "Change nothing else" in prompt and "Improve this question" not in prompt
    # ...every detail of the scenario and every answer kept (1.17.0)...
    assert "Never shorten, summarize or drop a detail" in prompt
    assert "Never add a reason, a cause or a hint" in prompt
    assert "copy each one exactly unless it holds an error" in prompt
    # ...and the explanation keeps its facts, about the correct answer only.
    assert "why the correct answer is correct, and nothing else" in prompt
    assert "Rewrite the CURRENT explanation" in prompt and "Add no claim" in prompt
    # The old house rule is gone: no "'X' - Correct/Incorrect" template.
    assert "Correct/Incorrect:" not in prompt


def test_an_empty_explanation_is_written_fresh_not_rewritten(monkeypatch):
    calls = _capture(monkeypatch, REWRITE)
    bare = Question(id="q-bare", stem="What does a job do?", question_type="single",
                    key="Orchestrates", distractors=["Stores rows", "Draws charts"])

    question_refinement.improve_question(bare, "a-model")

    assert "Rewrite the CURRENT explanation" not in calls[0]["prompt"]


def test_a_rewrite_that_still_judges_every_option_is_noted(client, question, monkeypatch):
    # REWRITE keeps the old "- Correct. ... - Incorrect." form.
    _stub_generate(monkeypatch, REWRITE)

    notes = client.post("/api/questions/q-ai/ai/rewrite", json={}).json()["notes"]

    assert any(n["field"] == "explanation" and "Correct/Incorrect" in n["message"] for n in notes)


# --- the bulk rewrite -------------------------------------------------------------

import time

from exam_bank.api import jobs as job_registry


def _add(db_path, **fields):
    database = ExamBankDB(db_path)
    try:
        database.save(Question(question_type="single", topic="Basics", **fields))
    finally:
        database.close()


def _bank(db_path, qid):
    database = ExamBankDB(db_path)
    try:
        return database.get(qid)
    finally:
        database.close()


def _finish(client, job_id, timeout=10.0):
    """Wait for a job, then return it as the client sees it."""
    deadline = time.time() + timeout
    while job_registry.get(job_id).status == job_registry.RUNNING:
        assert time.time() < deadline, "the rewrite job did not finish"
        time.sleep(0.02)
    return client.get(f"/api/jobs/{job_id}").json()


CLEAN = ("A transformation **moves and shapes rows**: each step works on the rows the "
         "step before it produced.\n\nThat is why it sits between a source and a target.")


CLEAN_CHECK = json.dumps({"answer_correct": True, "answer_problem": "", "also_correct": [],
                          "explanation_correct": True, "explanation_problem": "",
                          "lost": [], "added": [], "language": []})


def _by_stem(monkeypatch, replies, check=CLEAN_CHECK):
    """Answer each question's rewrite by a phrase in its stem, and the second
    pass (check_rewrite, 1.17.0) with `check`."""
    def fake(**kw):
        if kw["prompt"].startswith("You review a rewritten"):
            return check
        for phrase, reply in replies.items():
            if phrase in kw["prompt"]:
                return reply
        return "no idea"
    monkeypatch.setattr(providers, "generate", fake)


def _rewrite_of(stem, key, distractors, explanation=CLEAN):
    return json.dumps({"stem": stem, "key": key, "distractors": distractors,
                       "explanation": explanation})


# A clean polish keeps the answers word for word (PROOFREAD_RULES, 1.17.0).
TRANSFORMATION = _rewrite_of(
    "What is a transformation responsible for?", "Moves and shapes rows",
    ["Prints a report", "Installs the server", "Backs up a database"])


def test_a_bulk_rewrite_proposes_and_saves_nothing_until_accepted(client, question, db_path, monkeypatch):
    _add(db_path, id="q-two", stem="Where does a job run?", key="On Carte or locally",
         distractors=["Only in the browser", "Only on Linux", "Inside the database"],
         explanation="On Carte or locally - Correct.")
    _by_stem(monkeypatch, {
        "What does a transformation do": TRANSFORMATION,
        "Where does a job run": _rewrite_of(
            "Where can a job run?", "On Carte or locally",
            ["Only in the browser", "Only on Linux", "Inside the database"]),
    })

    started = client.post("/api/questions/ai/rewrite-all", json={"exact_topic": "Basics"})
    assert started.status_code == 202 and started.json()["total"] == 2
    job = _finish(client, started.json()["jobId"])

    assert job["status"] == "done" and job["kind"] == "rewrite"
    entries = {e["id"]: e for e in job["result"]}
    assert set(entries) == {"q-ai", "q-two"}
    assert entries["q-ai"]["proposed"]["explanation"] == CLEAN
    assert entries["q-ai"]["notes"] == [] and entries["q-ai"]["problems"] == []
    # Nothing has reached the bank.
    assert _bank(db_path, "q-ai").stem == question.stem

    accepted = client.post(f"/api/questions/ai/rewrite-jobs/{job['id']}/accept",
                           json={"question_ids": ["q-ai"]}).json()

    assert accepted == {"saved": ["q-ai"], "skipped": []}
    saved = _bank(db_path, "q-ai")
    assert saved.stem == "What is a transformation responsible for?"
    assert saved.explanation == CLEAN
    changed = [h for h in saved.version_history if h["field"] in ("stem", "explanation")]
    assert changed and {h["editor"] for h in changed} == {"AI rewrite (bulk)"}
    assert _bank(db_path, "q-two").stem == "Where does a job run?", "only what was accepted"


def test_accepting_refuses_a_question_edited_since_its_rewrite(client, question, db_path, monkeypatch):
    _by_stem(monkeypatch, {"What does a transformation do": TRANSFORMATION})
    job = _finish(client, client.post("/api/questions/ai/rewrite-all",
                                      json={"id": "q-ai"}).json()["jobId"])
    # The author edits it by hand while the rewrite sat in the review list.
    assert client.put("/api/questions/q-ai", json={"tags": ["edited"]}).status_code == 200

    body = client.post(f"/api/questions/ai/rewrite-jobs/{job['id']}/accept",
                       json={"question_ids": ["q-ai"]}).json()

    assert body["saved"] == [] and "changed since" in body["skipped"][0]["reason"]
    assert _bank(db_path, "q-ai").stem == question.stem


def test_accepting_skips_what_cannot_be_taken(client, question, db_path, monkeypatch):
    _add(db_path, id="q-same", stem="Same stem?", key="Yes", distractors=["No", "Maybe", "Never"],
         explanation=CLEAN)
    _add(db_path, id="q-bad", stem="Bad stem?", key="Yes", distractors=["No", "Maybe", "Never"])
    _add(db_path, id="q-junk", stem="Junk stem?", key="Yes", distractors=["No", "Maybe", "Never"])
    _by_stem(monkeypatch, {
        "What does a transformation do": TRANSFORMATION,
        "Same stem": _rewrite_of("Same stem?", "Yes", ["No", "Maybe", "Never"]),
        "Bad stem": _rewrite_of("Bad stem?", "Yes", []),  # nothing to get wrong
        # "Junk stem" is answered "no idea": not a question at all.
    })
    job = _finish(client, client.post("/api/questions/ai/rewrite-all",
                                      json={"exact_topic": "Basics"}).json()["jobId"])

    body = client.post(f"/api/questions/ai/rewrite-jobs/{job['id']}/accept",
                       json={"question_ids": ["q-ai", "q-same", "q-bad", "q-junk", "q-ai"]}).json()

    assert body["saved"] == ["q-ai"]
    reasons = {s["id"]: s["reason"] for s in body["skipped"]}
    assert "changed nothing" in reasons["q-same"]
    assert "could not be graded" in reasons["q-bad"]
    assert "usable question" in reasons["q-junk"]
    again = client.post(f"/api/questions/ai/rewrite-jobs/{job['id']}/accept",
                        json={"question_ids": ["q-ai"]}).json()
    assert "already accepted" in again["skipped"][0]["reason"]


def test_a_bulk_rewrite_with_nothing_to_rewrite_is_a_conflict(client, question, monkeypatch):
    _stub_generate(monkeypatch, REWRITE)

    r = client.post("/api/questions/ai/rewrite-all", json={"exact_topic": "No such topic"})

    assert r.status_code == 409


def test_a_rewrite_job_is_not_committed_as_new_questions(client, question, monkeypatch):
    _stub_generate(monkeypatch, REWRITE)
    job = _finish(client, client.post("/api/questions/ai/rewrite-all",
                                      json={"id": "q-ai"}).json()["jobId"])

    r = client.post(f"/api/jobs/{job['id']}/commit", json={})

    assert r.status_code == 409


def test_a_bulk_rewrite_tries_a_question_twice_before_giving_up(client, question, monkeypatch):
    replies = iter(["{ not json", TRANSFORMATION])
    monkeypatch.setattr(providers, "generate", lambda **kw: next(replies))

    job = _finish(client, client.post("/api/questions/ai/rewrite-all",
                                      json={"id": "q-ai"}).json()["jobId"])

    entry = job["result"][0]
    assert entry["error"] == "" and entry["proposed"]["stem"] == "What is a transformation responsible for?"


def test_the_house_style_is_the_rules_the_prompts_carry(client):
    from exam_bank.core import generation_prompts as gp

    sections = client.get("/api/house-style").json()["sections"]

    rules = "\n".join(s["rules"] for s in sections)
    for constant in (gp.SCENARIO_AND_STEM_RULES, gp.EXPLANATION_RULES,
                     gp.PROOFREAD_RULES, gp.EXPLANATION_REWRITE_RULES):
        assert constant in rules


# --- the writing standard (1.15.0) -------------------------------------------


def test_every_prompt_carries_the_writing_standard(question, monkeypatch):
    from exam_bank.core import generation_prompts as gp
    from exam_bank.core import question_refinement as qr

    assert gp.WRITING_RULES in gp.GENERATION_SYSTEM_PROMPT
    prompts = _capture(monkeypatch, REWRITE)
    qr.improve_question(question, model="m")
    qr.generate_explanation(question, model="m")
    assert len(prompts) == 2
    assert all(gp.WRITING_RULES in p["prompt"] for p in prompts)


def test_a_rewrite_comes_back_tidied_with_what_is_left_noted(client, question, monkeypatch):
    _stub_generate(monkeypatch, json.dumps({
        "scenario": "A team enriches 'sales' records with a 'Stream Lookup' step.",
        "stem": "Which field does the lookup match on?",
        "key": "The 'region_code' field",
        "distractors": ["The 'sales' table", "The 'row_id' field", "The file name"],
        "explanation": "A **Stream lookup** matches on the key field and doesn\u2019t filter rows.",
    }))

    body = client.post("/api/questions/q-ai/ai/rewrite", json={}).json()

    p = body["proposed"]
    assert p["scenario"] == "A team enriches 'sales' records with a Stream lookup step."
    assert p["key"] == "The `region_code` field"
    assert p["distractors"][1] == "The `row_id` field"
    assert p["explanation"] == "A **Stream lookup** matches on the key field and does not filter rows."
    quotes = [n for n in body["notes"] if "Single quotes around 'sales'" in n["message"]]
    assert {n["field"] for n in quotes} == {"scenario", "options"}


def test_the_house_style_shows_the_writing_standard(client):
    from exam_bank.core import generation_prompts as gp

    sections = client.get("/api/house-style").json()["sections"]
    assert {"title": "Quotes, names and punctuation", "rules": gp.WRITING_RULES} in sections


# --- the second pass and the exact checks (1.17.0) ----------------------------


def test_every_rewrite_is_checked_and_the_findings_are_notes(client, question, monkeypatch):
    finding = json.dumps({"answer_correct": False, "answer_problem": "a transformation does not schedule",
                          "also_correct": ["Prints a report"], "explanation_correct": True,
                          "explanation_problem": "", "lost": ["the caveat about hops"], "added": [],
                          "language": [{"field": "question", "text": "responsable", "fix": "responsible"}]})
    _by_stem(monkeypatch, {"What does a transformation do": TRANSFORMATION}, check=finding)

    body = client.post("/api/questions/q-ai/ai/rewrite", json={}).json()

    messages = " | ".join(n["message"] for n in body["notes"])
    assert "doubts the answer marked correct: a transformation does not schedule" in messages
    assert "may also be correct: Prints a report" in messages
    assert "may have lost: the caveat about hops" in messages
    assert '"responsable" -> "responsible"' in messages


def test_an_unreadable_check_is_a_note_not_a_pass(client, question, monkeypatch):
    _by_stem(monkeypatch, {"What does a transformation do": TRANSFORMATION}, check="I think it is fine.")

    body = client.post("/api/questions/q-ai/ai/rewrite", json={}).json()

    assert any("check did not run" in n["message"] for n in body["notes"])


def test_the_check_is_given_the_original_and_the_rewrite(question, monkeypatch):
    calls = _capture(monkeypatch, CLEAN_CHECK)
    proposed = Question(id="q-ai", stem="What is a transformation for?", key="Moves and shapes rows",
                        distractors=["Prints a report"], explanation="It **moves rows**.")

    assert question_refinement.check_rewrite(question, proposed, "m", source_text="Course text.") == []
    prompt = calls[0]["prompt"]
    assert "ORIGINAL (reviewed and approved)" in prompt and question.stem in prompt
    assert "REWRITE (to check)" in prompt and "What is a transformation for?" in prompt
    assert "- Moves and shapes rows (marked correct)" in prompt and "Course text." in prompt
