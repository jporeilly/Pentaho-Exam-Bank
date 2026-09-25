"""Tests for the Report: each exam's Bloom balance, bar check and findings.

The numbers are the point of the pane, so they are pinned exactly — including
the cases that sit exactly on a bar, where a floating-point comparison would
flip a pass into a fail.
"""

import json

import pytest
from fastapi.testclient import TestClient

from exam_bank.api import deps
from exam_bank.api.app import app
from exam_bank.core.bank import Certification, ExamBankDB, Question
from exam_bank.core.report import BARS, UNFILED, build_report
from exam_bank.utils import config as config_module


@pytest.fixture
def db(tmp_path):
    database = ExamBankDB(tmp_path / "report.db")
    yield database
    database.close()


def course_files(root, slug, *, level=None, pool=0, draw=None, pass_mark=80):
    """A course directory holding just what the report reads."""
    d = root / slug
    d.mkdir(parents=True)
    course = {"title": slug}
    if level:
        course["level"] = {"number": level, "name": BARS[level]["name"]}
    (d / "course.json").write_text(json.dumps(course), encoding="utf-8")
    exam = {"questions": [{"id": f"{slug}-{i}"} for i in range(pool)], "passMark": pass_mark}
    if draw is not None:
        exam["questionsPerAttempt"] = draw
    (d / "exam.json").write_text(json.dumps(exam), encoding="utf-8")


def add_cert(db, name, slug):
    cert = Certification(name=name, source_type="pcm", source_ref=slug)
    db.save_certification(cert)
    return cert


def add(db, cert, qid, bloom, *, topic="T", pool=-1, scenario="", status="draft",
        multi=False, distractors=("w1", "w2", "w3")):
    q = Question(
        id=qid, stem=f"stem {qid}", key="k", distractors=list(distractors),
        bloom_level=bloom, topic=topic, pool_order=pool, scenario=scenario,
        certification_id=cert.id if cert else "", status=status,
        question_type="multi" if multi else "single",
        keys=["k", "k2"] if multi else [],
    )
    db.save(q)
    return q


def exam_named(report, name):
    return next(e for e in report["exams"] if e["name"] == name)


# ── counting ────────────────────────────────────────────────────────────────

def test_an_empty_bank_reports_nothing_rather_than_failing(db):
    r = build_report(db)
    assert r["questions"] == 0
    assert r["exams"] == [] and r["items"] == []
    assert r["levels"][:5] == ["Remember", "Understand", "Apply", "Analyze", "Evaluate"]


def test_every_level_and_status_is_present_even_at_zero(db):
    cert = add_cert(db, "Only", "only")
    add(db, cert, "a", "Apply")
    e = build_report(db)["exams"][0]
    assert e["byBloom"] == {"Remember": 0, "Understand": 0, "Apply": 1,
                            "Analyze": 0, "Evaluate": 0, "Create": 0}
    assert e["byStatus"]["approved"] == 0 and e["byStatus"]["draft"] == 1


def test_apply_plus_analyze_plus_and_recall_are_counted_from_the_levels(db):
    cert = add_cert(db, "Mix", "mix")
    for i, level in enumerate(["Remember", "Remember", "Understand", "Apply",
                               "Analyze", "Evaluate"]):
        add(db, cert, f"q{i}", level)
    e = build_report(db)["exams"][0]
    assert (e["applyPlus"], e["analyzePlus"], e["recall"], e["evaluate"]) == (3, 2, 2, 1)


def test_scenario_multi_and_thin_distractors(db):
    cert = add_cert(db, "Shape", "shape")
    add(db, cert, "s1", "Apply", scenario="A server stops after a patch.")
    add(db, cert, "s2", "Apply", scenario="   ")  # whitespace is not a scenario
    add(db, cert, "m1", "Apply", multi=True, distractors=("only-one",))
    e = build_report(db)["exams"][0]
    assert e["scenarioLed"] == 1
    assert e["multi"] == 1
    assert e["thin"] == 1


def test_an_unrecognised_level_is_counted_not_dropped(db):
    """A lower-case 'apply' is what an importer that did not validate writes.
    Dropping it would make the exam's bars add up to less than its size."""
    cert = add_cert(db, "Odd", "odd")
    add(db, cert, "ok", "Apply")
    add(db, cert, "bad", "apply")
    e = build_report(db)["exams"][0]
    assert e["questions"] == 2
    assert sum(e["byBloom"].values()) == 1
    assert e["unknownBloom"] == 1
    assert any("unrecognised Bloom level" in f["title"] for f in e["findings"])


# ── order ───────────────────────────────────────────────────────────────────

def test_workshops_come_in_course_order_not_alphabetically(db):
    cert = add_cert(db, "Course", "course")
    add(db, cert, "z1", "Apply", topic="Zeta intro", pool=0)
    add(db, cert, "z2", "Apply", topic="Zeta intro", pool=1)
    add(db, cert, "a1", "Apply", topic="Alpha later", pool=2)
    e = build_report(db)["exams"][0]
    assert [t["topic"] for t in e["topics"]] == ["Zeta intro", "Alpha later"]
    assert [t["questions"] for t in e["topics"]] == [2, 1]


def test_questions_come_in_authored_order_with_bank_authored_ones_last(db):
    cert = add_cert(db, "Course", "course")
    add(db, cert, "late", "Apply", pool=-1)
    add(db, cert, "second", "Apply", pool=1)
    add(db, cert, "first", "Apply", pool=0)
    assert [i["id"] for i in build_report(db)["items"]] == ["first", "second", "late"]


def test_unfiled_questions_are_counted_under_their_own_group_last(db):
    b = add_cert(db, "Bravo", "bravo")
    a = add_cert(db, "Alpha", "alpha")
    add(db, b, "b1", "Apply")
    add(db, a, "a1", "Apply")
    add(db, None, "loose", "Remember")
    r = build_report(db)
    assert [e["name"] for e in r["exams"]] == ["Alpha", "Bravo", UNFILED]
    assert r["questions"] == 3


def test_certifications_holding_no_questions_are_counted_not_listed(db):
    full = add_cert(db, "Full", "full")
    add_cert(db, "Empty one", "e1")
    add_cert(db, "Empty two", "e2")
    add(db, full, "q", "Apply")
    r = build_report(db)
    assert [e["name"] for e in r["exams"]] == ["Full"]
    assert r["emptyCourses"] == 2


# ── the bar ─────────────────────────────────────────────────────────────────

def level_one_exam(db, tmp_path, *, apply=10, analyze=3, evaluate=1, recall=6, n=20):
    """A Level 1 exam built to land where the test wants it. Apply+ counts
    Apply, Analyze and Evaluate together, as the bar does."""
    course_files(tmp_path, "l1", level=1, pool=n, draw=n - 5)
    cert = add_cert(db, "L1", "l1")
    levels = (["Evaluate"] * evaluate + ["Analyze"] * (analyze - evaluate)
              + ["Apply"] * (apply - analyze) + ["Remember"] * recall)
    levels += ["Understand"] * (n - len(levels))
    for i, level in enumerate(levels):
        # Scenarios on the Apply+ questions only, so scenario coverage matches
        # Apply+ and the scenario-gap finding stays out of what is being tested.
        situated = level in ("Apply", "Analyze", "Evaluate")
        add(db, cert, f"q{i}", level, pool=i, scenario="s" if situated else "")
    return build_report(db, tmp_path)["exams"][0]


def test_an_exam_exactly_on_every_line_clears(db, tmp_path):
    """50% Apply+, 15% Analyze+, 1 Evaluate, 30% recall out of 20: each figure
    is exactly on its line, which must count as a pass."""
    e = level_one_exam(db, tmp_path)
    assert e["level"] == {"number": 1, "name": "Practitioner"}
    assert e["bar"]["clears"] is True
    assert [c["ok"] for c in e["bar"]["criteria"]] == [True, True, True, True]
    assert e["findings"][0]["severity"] == "clear"


def test_one_question_either_side_of_the_line_fails_with_a_gap_of_one(db, tmp_path):
    e = level_one_exam(db, tmp_path, apply=9, recall=7)
    crit = {c["criterion"]: c for c in e["bar"]["criteria"]}
    assert crit["Apply+"]["ok"] is False and crit["Apply+"]["gap"] == 1
    assert crit["Recall"]["ok"] is False and crit["Recall"]["gap"] == 1
    assert e["bar"]["clears"] is False
    miss = next(f for f in e["findings"] if "Misses the Level 1" in f["title"])
    assert "on 2 of 4" in miss["title"]
    assert "counts twice" not in miss["action"]  # the action says it, in its own words
    assert "both gaps close together" in miss["action"]


def test_every_level_bar_is_the_one_the_review_used():
    assert {k: (v["applyPlus"], v["analyzePlus"], v["evaluate"], v["recall"])
            for k, v in BARS.items()} == {1: (50, 15, 1, 30), 2: (60, 30, 5, 20),
                                          3: (70, 40, 15, 15)}


def test_a_course_with_no_level_is_not_scored_and_says_so(db, tmp_path):
    course_files(tmp_path, "taster", level=None, pool=30, draw=20)
    cert = add_cert(db, "Taster", "taster")
    add(db, cert, "q", "Apply", scenario="s")
    e = build_report(db, tmp_path)["exams"][0]
    assert e["level"] is None and e["bar"] is None
    assert any(f["severity"] == "note" and "Not scored" in f["title"] for f in e["findings"])


def test_without_a_courses_directory_there_is_no_level_or_draw(db):
    cert = add_cert(db, "Anywhere", "anywhere")
    add(db, cert, "q", "Apply")
    r = build_report(db, None)
    assert r["coursesConfigured"] is False
    assert r["exams"][0]["level"] is None and r["exams"][0]["exam"] is None


# ── findings ────────────────────────────────────────────────────────────────

def test_a_draw_equal_to_the_pool_is_flagged(db, tmp_path):
    course_files(tmp_path, "nodraw", pool=12, draw=12)
    cert = add_cert(db, "No draw", "nodraw")
    add(db, cert, "q", "Apply", scenario="s")
    e = build_report(db, tmp_path)["exams"][0]
    assert e["exam"] == {"pool": 12, "draw": 12, "passMark": 80}
    assert any(f["title"] == "No draw headroom" for f in e["findings"])


def test_headroom_is_not_flagged_when_the_draw_is_smaller(db, tmp_path):
    course_files(tmp_path, "fine", pool=30, draw=20)
    cert = add_cert(db, "Fine", "fine")
    add(db, cert, "q", "Apply", scenario="s")
    e = build_report(db, tmp_path)["exams"][0]
    assert not any(f["title"] == "No draw headroom" for f in e["findings"])


def test_apply_without_scenarios_is_flagged_at_twenty_points(db):
    cert = add_cert(db, "Gap", "gap")
    for i in range(10):  # 100% Apply+, 80% scenario: a 20-point gap
        add(db, cert, f"q{i}", "Apply", scenario="s" if i < 8 else "")
    titles = [f["title"] for f in build_report(db)["exams"][0]["findings"]]
    assert "Reaches Apply without scenarios" in titles


def test_nineteen_points_is_not_a_gap(db):
    cert = add_cert(db, "Near", "near")
    # 21 questions, all Apply; 17 with a scenario is 81%, a 19-point gap.
    for i in range(17):
        add(db, cert, f"q{i}", "Apply", scenario="s")
    for i in range(4):
        add(db, cert, f"r{i}", "Apply", scenario="")
    titles = [f["title"] for f in build_report(db)["exams"][0]["findings"]]
    assert "Reaches Apply without scenarios" not in titles


# ── HTTP ────────────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "api.db"

    def override():
        database = ExamBankDB(db_path)
        try:
            yield database
        finally:
            database.close()

    app.dependency_overrides[deps.get_db] = override
    yield TestClient(app), db_path
    app.dependency_overrides.clear()


def test_the_endpoint_serves_the_report_with_course_facts(client, tmp_path, monkeypatch):
    http, db_path = client
    courses = tmp_path / "courses"
    course_files(courses, "pdi", level=None, pool=30, draw=20)
    monkeypatch.setattr(config_module.config, "pcm_courses_dir", str(courses))
    seed = ExamBankDB(db_path)
    cert = add_cert(seed, "PDI", "pdi")
    add(seed, cert, "q1", "Analyze", topic="Make It Yours", pool=0)
    seed.close()

    body = http.get("/api/report").json()
    assert body["coursesConfigured"] is True
    assert body["questions"] == 1
    exam = body["exams"][0]
    assert exam["sourceRef"] == "pdi"
    assert exam["exam"] == {"pool": 30, "draw": 20, "passMark": 80}
    assert body["items"][0]["bloom"] == "Analyze"


def test_the_endpoint_works_with_no_courses_directory(client, monkeypatch):
    http, _ = client
    monkeypatch.setattr(config_module.config, "pcm_courses_dir", "")
    body = http.get("/api/report").json()
    assert body["coursesConfigured"] is False
    assert body["questions"] == 0
