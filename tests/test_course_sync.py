"""Adopting the Content Manager's courses into the bank, repeatably.

A fresh install opens on an empty bank while the courses it just found hold
several hundred questions. `scripts/migrate_pcm_exams.py` already adopted
them once, but it mints a NEW certification on every run - right for a
one-off migration, wrong for anything that runs twice. The property these
tests exist for is therefore IDEMPOTENCE: syncing twice must leave the bank
exactly as syncing once did.
"""

import json

import pytest

from exam_bank.core import course_sync
from exam_bank.core.bank import Certification


def _question(qid, stem, key="Alpha", distractors=("Beta", "Gamma", "Delta")):
    return {
        "id": qid,
        "prompt": stem,
        "options": [key, *distractors],
        "correct": 0,
        "topic": "Basics",
        "explanation": f"{key} - Correct. Beta - Incorrect.",
    }


@pytest.fixture
def courses(tmp_path):
    """Two courses with exams, one without, and a _template to be ignored."""
    root = tmp_path / "courses"

    def course(slug, title, questions):
        d = root / slug
        d.mkdir(parents=True)
        (d / "course.json").write_text(json.dumps({"title": title}), encoding="utf-8")
        if questions is not None:
            (d / "exam.json").write_text(
                json.dumps({"title": f"{title} Exam", "questionsPerAttempt": 2,
                            "passMark": 80, "questions": questions}, indent=2),
                encoding="utf-8")

    course("alpha-practitioner", "Alpha Practitioner",
           [_question("a1", "What is Alpha? (Choose one.)"),
            _question("a2", "Which one is Alpha-ish? (Choose one.)")])
    course("beta-practitioner", "Beta Practitioner",
           [_question("b1", "What is Beta? (Choose one.)")])
    course("gamma-no-exam", "Gamma", None)
    course("_template", "Template", [_question("t1", "Template? (Choose one.)")])
    return root


def test_a_plan_writes_nothing_and_sees_every_course_with_an_exam(courses, tmp_db):
    p = course_sync.plan(courses, tmp_db)

    slugs = [c.slug for c in p.courses]
    assert slugs == ["alpha-practitioner", "beta-practitioner"], (
        "a course with no exam.json has nothing to adopt, and _template is "
        "scaffolding rather than a course anyone sits"
    )
    assert p.total_new == 3
    assert tmp_db.conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 0, (
        "plan() must not write"
    )


def test_apply_adopts_the_questions_with_their_ids_intact(courses, tmp_db):
    p = course_sync.plan(courses, tmp_db)
    result = course_sync.apply(courses, tmp_db, expect_token=p.token)

    assert result["added"] == 3
    stored = {row[0] for row in tmp_db.conn.execute("SELECT id FROM questions")}
    assert stored == {"a1", "a2", "b1"}, (
        "the ids are hand-authored and PCM keys webhook results and exam "
        "resume on them; a new id is a lost result"
    )
    certs = tmp_db.list_certifications()
    assert {c.source_ref for c in certs} == {"alpha-practitioner", "beta-practitioner"}
    assert all(c.source_type == "pcm" for c in certs)


def test_syncing_twice_changes_nothing(courses, tmp_db):
    """The property the old migration script did not have."""
    first = course_sync.apply(courses, tmp_db, expect_token=course_sync.plan(courses, tmp_db).token)
    assert first["added"] == 3

    second_plan = course_sync.plan(courses, tmp_db)
    assert second_plan.total_new == 0
    assert second_plan.total_changed == 0
    assert sum(len(c.unchanged) for c in second_plan.courses) == 3

    second = course_sync.apply(courses, tmp_db, expect_token=second_plan.token)
    assert second["added"] == 0 and second["updated"] == 0
    assert len(tmp_db.list_certifications()) == 2, (
        "a second sync must not mint a second certification per course"
    )


def test_a_renamed_course_title_does_not_mint_a_second_certification(courses, tmp_db):
    """Certifications are keyed on the slug, not the title. A course title is
    authored prose; matching on it would split a course in two the first time
    somebody rewords one."""
    course_sync.apply(courses, tmp_db, expect_token=course_sync.plan(courses, tmp_db).token)

    cj = courses / "alpha-practitioner" / "course.json"
    cj.write_text(json.dumps({"title": "Alpha Practitioner (2026 edition)"}), encoding="utf-8")

    course_sync.apply(courses, tmp_db, expect_token=course_sync.plan(courses, tmp_db).token)
    assert len(tmp_db.list_certifications()) == 2


def test_an_edit_in_the_bank_is_reported_and_not_reverted(courses, tmp_db):
    """The bank is an EDITING tool - these questions were adopted precisely
    because they had nowhere else to be edited. A routine refresh that
    silently overwrote that work would make the tool unsafe to use."""
    course_sync.apply(courses, tmp_db, expect_token=course_sync.plan(courses, tmp_db).token)

    edited = tmp_db.get("a1")
    edited.stem = "What is Alpha, precisely? (Choose one.)"
    tmp_db.save(edited)

    p = course_sync.plan(courses, tmp_db)
    alpha = next(c for c in p.courses if c.slug == "alpha-practitioner")
    assert alpha.changed == ["a1"]

    course_sync.apply(courses, tmp_db, expect_token=p.token)
    assert tmp_db.get("a1").stem == "What is Alpha, precisely? (Choose one.)", (
        "the author's edit must survive a sync that was not asked to overwrite"
    )


def test_overwriting_is_possible_but_keeps_the_review_state(courses, tmp_db):
    course_sync.apply(courses, tmp_db, expect_token=course_sync.plan(courses, tmp_db).token)

    edited = tmp_db.get("a1")
    edited.stem = "Locally reworded. (Choose one.)"
    edited.status = "approved"
    tmp_db.save(edited)

    p = course_sync.plan(courses, tmp_db)
    course_sync.apply(courses, tmp_db, expect_token=p.token, overwrite_changed=True)

    restored = tmp_db.get("a1")
    assert restored.stem == "What is Alpha? (Choose one.)", "the course's copy wins"
    assert restored.status == "approved", (
        "the course file has no opinion about review state; resetting an "
        "approved question to draft would undo work nobody asked to undo"
    )


def test_approving_an_adopted_question_does_not_make_it_look_changed(courses, tmp_db):
    """Status is the bank's own workmanship. If it counted as a difference,
    every sync would offer to undo every review ever done."""
    course_sync.apply(courses, tmp_db, expect_token=course_sync.plan(courses, tmp_db).token)

    q = tmp_db.get("b1")
    q.status = "approved"
    tmp_db.save(q)

    p = course_sync.plan(courses, tmp_db)
    beta = next(c for c in p.courses if c.slug == "beta-practitioner")
    assert beta.changed == [] and beta.unchanged == ["b1"]


def test_a_stale_token_is_refused(courses, tmp_db):
    """Between looking and acting, somebody may have pulled the courses repo."""
    p = course_sync.plan(courses, tmp_db)

    exam = courses / "beta-practitioner" / "exam.json"
    data = json.loads(exam.read_text(encoding="utf-8"))
    data["questions"].append(_question("b2", "And another Beta? (Choose one.)"))
    exam.write_text(json.dumps(data, indent=2), encoding="utf-8")

    with pytest.raises(ValueError, match="changed since"):
        course_sync.apply(courses, tmp_db, expect_token=p.token)
    assert tmp_db.conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 0, (
        "a refused apply must not have written half of itself first"
    )


def test_a_broken_course_is_reported_and_the_rest_still_sync(courses, tmp_db):
    """One malformed file must not cost the other eleven courses their sync."""
    (courses / "beta-practitioner" / "exam.json").write_text("{not json", encoding="utf-8")

    p = course_sync.plan(courses, tmp_db)
    beta = next(c for c in p.courses if c.slug == "beta-practitioner")
    assert beta.error, "the broken course must say so"

    result = course_sync.apply(courses, tmp_db, expect_token=p.token)
    assert result["added"] == 2, "alpha still adopted"


def test_an_ungradeable_question_is_refused_not_quietly_saved(courses, tmp_db):
    """Same rule as /api/import/commit: the bank's editor will not let an
    author save one of these, so a sync that can is a hole in that rule."""
    exam = courses / "beta-practitioner" / "exam.json"
    data = json.loads(exam.read_text(encoding="utf-8"))
    data["questions"].append({"id": "b-bad", "prompt": "", "options": [], "correct": 0})
    exam.write_text(json.dumps(data, indent=2), encoding="utf-8")

    p = course_sync.plan(courses, tmp_db)
    beta = next(c for c in p.courses if c.slug == "beta-practitioner")
    assert [u["id"] for u in beta.unusable] == ["b-bad"]

    course_sync.apply(courses, tmp_db, expect_token=p.token)
    assert tmp_db.get("b-bad") is None


def test_only_limits_the_sync_to_named_courses(courses, tmp_db):
    p = course_sync.plan(courses, tmp_db)
    result = course_sync.apply(courses, tmp_db, expect_token=p.token,
                               only=["beta-practitioner"])
    assert result["added"] == 1
    assert {row[0] for row in tmp_db.conn.execute("SELECT id FROM questions")} == {"b1"}


def test_a_missing_courses_directory_is_an_empty_plan_not_a_crash(tmp_path, tmp_db):
    p = course_sync.plan(tmp_path / "nowhere", tmp_db)
    assert p.courses == [] and p.total_new == 0


def test_bank_is_empty_is_stricter_than_no_questions(tmp_db):
    assert course_sync.bank_is_empty(tmp_db)

    tmp_db.save_certification(Certification(name="Started organising", source_type="pcm",
                                            source_ref="alpha-practitioner"))
    assert not course_sync.bank_is_empty(tmp_db), (
        "a bank with certifications but no questions is one somebody has "
        "started arranging; filling it unasked is not the same as filling an "
        "empty one"
    )


def test_an_id_two_courses_share_is_refused_by_both(courses, tmp_db):
    """Found with real data, not imagined: 30 ids in the live courses are
    used by TWO courses each - `m1-q1` belongs to both
    architect-install-certified and developer-di-practitioner.

    The questions table is keyed on that id and `save()` is INSERT OR
    REPLACE, so adopting both would write one course's question over the
    other's, move it to the wrong certification, and report a completely
    successful sync. 398 questions in git would arrive as 365 in the bank
    with no error and nothing to compare against.
    """
    exam = courses / "beta-practitioner" / "exam.json"
    data = json.loads(exam.read_text(encoding="utf-8"))
    data["questions"].append(_question("a1", "Beta's OWN question, same id. (Choose one.)"))
    exam.write_text(json.dumps(data, indent=2), encoding="utf-8")

    p = course_sync.plan(courses, tmp_db)
    alpha = next(c for c in p.courses if c.slug == "alpha-practitioner")
    beta = next(c for c in p.courses if c.slug == "beta-practitioner")

    assert [c["id"] for c in alpha.conflicts] == ["a1"]
    assert [c["id"] for c in beta.conflicts] == ["a1"]
    assert "beta-practitioner" in alpha.conflicts[0]["reason"], (
        "naming the other course is the whole value of the message - "
        "'duplicate id' leaves the author hunting for the pair"
    )
    assert "a1" not in alpha.new and "a1" not in beta.new

    course_sync.apply(courses, tmp_db, expect_token=p.token)
    assert tmp_db.get("a1") is None, "a contested id must not be written by either course"
    assert {row[0] for row in tmp_db.conn.execute("SELECT id FROM questions")} == {"a2", "b1"}


def test_a_shared_id_is_still_refused_when_one_course_already_holds_it(courses, tmp_db):
    """The dangerous ordering: adopt one course, then a second that reuses an
    id. Without the guard the second silently overwrites the first and moves
    the question to the wrong certification."""
    course_sync.apply(courses, tmp_db, expect_token=course_sync.plan(courses, tmp_db).token)
    before = tmp_db.get("a1")

    exam = courses / "beta-practitioner" / "exam.json"
    data = json.loads(exam.read_text(encoding="utf-8"))
    data["questions"].append(_question("a1", "Beta claims it later. (Choose one.)"))
    exam.write_text(json.dumps(data, indent=2), encoding="utf-8")

    p = course_sync.plan(courses, tmp_db)
    course_sync.apply(courses, tmp_db, expect_token=p.token, overwrite_changed=True)

    after = tmp_db.get("a1")
    assert after.stem == before.stem, "alpha's question survived"
    assert after.certification_id == before.certification_id, (
        "and did not migrate to beta's certification"
    )
