"""A question filed under a course takes the course's id, module and place.

Found in use (2026-09-29): a question generated for PDI in 2 Hours and saved
into the course came in as `03f2c063-39c7-…` among `q-preview` and `q-mi`,
with no place in the order and the lab's title ("One Pipeline, Many Files")
where the course files it under the module ("See It Scale"). One unplaced
question also switched the course order off for the whole publish.

Since 2026-09-30 every course question id reads <course>-m<module>-q<n>
(`2hr-m4-q3`, `di-m3-q14`), which PCM's verify-course enforces; the bank
files every question into that format, whatever id it arrived with.
"""

import json
import time

import pytest
from fastapi.testclient import TestClient

from exam_bank.api import deps, jobs
from exam_bank.api.app import app
from exam_bank.api.routers import generation as generation_router
from exam_bank.core import course_filing as cf
from exam_bank.core.bank import Certification, ExamBankDB, Question
from exam_bank.core.exporter import pcm_exam_items
from exam_bank.core.pcm_reader import load_pcm_course, summary_modules
from exam_bank.utils.config import config

SUMMARY = """\
# Table of contents

## Get Ready

* [Before You Start](00-before-you-start/guide.md)

## See It Work

* [Your First Win](01-first-win/guide.md)

## See It Scale

<!-- topic-page: 05-metadata-injection -->
* [One Pipeline, Many Files](05-metadata-injection/guide.md)

### Going further

* [Bring Your Own Data](09-bring-your-own-data/guide.md)
"""

PROSE = "Prose enough to ground a question on, and then some more of it. " * 4


@pytest.fixture
def courses(tmp_path, monkeypatch):
    root = tmp_path / "courses"
    course = root / "pdi-2hr-lab"
    for lab, title in [("00-before-you-start", "Before You Start"), ("01-first-win", "Your First Win"),
                       ("05-metadata-injection", "One Pipeline, Many Files"),
                       ("09-bring-your-own-data", "Bring Your Own Data")]:
        (course / lab).mkdir(parents=True)
        (course / lab / "guide.md").write_text(f"## Section\n\n{PROSE}\n", encoding="utf-8")
        (course / lab / "manifest.json").write_text(json.dumps({"title": title}), encoding="utf-8")
    (course / "SUMMARY.md").write_text(SUMMARY, encoding="utf-8")
    (course / "course.json").write_text(json.dumps({"title": "PDI in 2 Hours"}), encoding="utf-8")
    # Another course, not adopted: its ids are taken all the same.
    other = root / "other-course"
    other.mkdir()
    (other / "exam.json").write_text(json.dumps({"questions": [{"id": "oc-m1-q1", "module": "A"}]}),
                                     encoding="utf-8")
    monkeypatch.setattr(config, "pcm_courses_dir", str(root))
    return root


@pytest.fixture
def db(tmp_path):
    database = ExamBankDB(tmp_path / "bank.db")
    yield database
    database.close()


@pytest.fixture
def two_hour(db):
    """The 2hr pool in the standard format, a See It Scale question (order 4) deleted."""
    cert = Certification(name="PDI in 2 Hours", source_type="pcm", source_ref="pdi-2hr-lab")
    db.save_certification(cert)
    layout = [("2hr-m2-q1", "See It Work"), ("2hr-m4-q1", "See It Scale"), ("2hr-m3-q1", "Make It Yours"),
              ("2hr-m4-q2", "See It Scale"), (None, None), ("2hr-m2-q2", "See It Work")]
    for order, (qid, topic) in enumerate(layout):
        if qid:
            db.save(Question(id=qid, stem=f"{qid}?", key="a", distractors=["b"], topic=topic,
                             certification_id=cert.id, pool_order=order, source_type="pcm",
                             source_file="Lab"))
    return cert


def generated(**kw):
    """What generation made before 1.7.1: a UUID, the lab as topic, pptx."""
    base = dict(stem="How does metadata injection support this requirement?", key="a",
                distractors=["b"], topic="One Pipeline, Many Files", source_file="pcm:pdi-2hr-lab")
    base.update(kw)
    return Question(**base)


# --- the pieces ---------------------------------------------------------------


def test_a_uuid_is_an_id_the_bank_made_up():
    assert cf.is_minted("03f2c063-39c7-43da-ae6a-84d076979851")
    assert not cf.is_minted("q-mi") and not cf.is_minted("m3-q7")


def test_the_standard_format_is_token_module_question():
    assert cf.is_standard("di-m3-q7") and cf.is_standard("2hr-m4-q12")
    for old in ("m3-q7", "q-mi", "kc-q1", "install-ai-q12", "q1", "di-m0-q1", "DI-m1-q1"):
        assert not cf.is_standard(old), old


def test_labs_belong_to_the_module_heading_above_them(courses):
    modules = summary_modules(courses, "pdi-2hr-lab")

    assert modules["05-metadata-injection"] == "See It Scale"
    assert modules["01-first-win"] == "See It Work"
    # A ### sub-topic belongs to its ## - the exams file under the ##.
    assert modules["09-bring-your-own-data"] == "See It Scale"


def test_generation_reads_the_module_with_each_section(courses):
    sections = load_pcm_course(courses, "pdi-2hr-lab", lab_slug="05-metadata-injection")

    assert sections and all(s.module == "See It Scale" for s in sections)
    assert sections[0].group == "One Pipeline, Many Files"


def test_a_question_generated_from_a_course_is_filed_the_courses_way(monkeypatch):
    """Module as topic, lab as citation, "pcm" as source - as adopted ones are."""
    from exam_bank.core import providers
    from exam_bank.core.question_generation import generate_questions
    from exam_bank.core.source import SlideInfo

    reply = json.dumps([{"scenario": "A team loads four suppliers' files.",
                         "stem": "Which feature lets one transformation read them all?",
                         "question_type": "single", "key": "Metadata injection",
                         "distractors": ["Four copies", "A merge join", "A job loop"],
                         "explanation": "x"}])
    monkeypatch.setattr(providers, "generate", lambda **kw: reply)

    made = generate_questions(
        SlideInfo(index=0, speaker_notes=PROSE, title="One Pipeline, Many Files — Section",
                  group="One Pipeline, Many Files", module="See It Scale"),
        model="a-model", source_file="pcm:pdi-2hr-lab")

    assert [(q.topic, q.source_type, q.source_file) for q in made] == [
        ("See It Scale", "pcm", "One Pipeline, Many Files")]


def test_slides_with_no_module_keep_their_title_as_topic(monkeypatch):
    from exam_bank.core import providers
    from exam_bank.core.question_generation import generate_questions
    from exam_bank.core.source import SlideInfo

    reply = json.dumps([{"stem": "Which?", "question_type": "single", "key": "a",
                         "distractors": ["b"], "explanation": "x"}])
    monkeypatch.setattr(providers, "generate", lambda **kw: reply)

    made = generate_questions(SlideInfo(index=0, speaker_notes=PROSE, title="Slide 3"), model="m")

    assert (made[0].topic, made[0].source_type) == ("Slide 3", "pptx")


def test_a_new_question_takes_the_next_number_in_its_module():
    course = [Question(id=f"di-m3-q{n}", topic="Data Sources") for n in range(1, 14)] + \
             [Question(id=f"di-m1-q{n}", topic="Getting Started") for n in range(1, 6)]
    new = Question(stem="Which step?", topic="Data Sources")

    assert cf.mint_id(new, course, set()) == "di-m3-q14"


def test_a_module_with_no_questions_yet_takes_the_next_m():
    course = [Question(id="di-m1-q1", topic="Getting Started"), Question(id="di-m3-q1", topic="Data Sources")]

    assert cf.mint_id(Question(stem="x?", topic="Capstone Project"), course, set()) == "di-m4-q1"


def test_the_number_comes_after_the_highest_used_anywhere():
    """A gap is not refilled: a deleted question's number may still be in a
    published exam, a results row or a learner's saved attempt."""
    course = [Question(id=f"ba-m3-q{n}", topic="IR") for n in (1, 2, 5)]

    assert cf.mint_id(Question(stem="x?", topic="IR"), course, set()) == "ba-m3-q6"
    assert cf.mint_id(Question(stem="x?", topic="IR"), course, {"ba-m3-q9"}) == "ba-m3-q10"


def test_a_course_with_no_questions_takes_a_token_from_its_slug():
    new = Question(stem="x?", topic="Overview")

    assert cf.mint_id(new, [], set(), slug="architect-con-specialty") == "con-m1-q1"
    # Another course already uses `con`.
    assert cf.mint_id(new, [], {"con-m2-q4"}, slug="architect-con-specialty") == "con2-m1-q1"


def test_the_scheme_reads_the_courses_exam_json_as_well_as_the_bank(courses):
    (courses / "pdi-2hr-lab" / "exam.json").write_text(json.dumps({"questions": [
        {"id": "2hr-m5-q2", "module": "Make It Real"}]}), encoding="utf-8")

    assert cf.mint_id(Question(stem="x?", topic="Make It Real"), [], set(),
                      slug="pdi-2hr-lab", courses_dir=courses) == "2hr-m5-q1"
    taken = {"2hr-m5-q2"}
    assert cf.mint_id(Question(stem="x?", topic="Make It Real"), [], taken,
                      slug="pdi-2hr-lab", courses_dir=courses) == "2hr-m5-q3"


def test_an_id_fits_only_with_the_courses_token_and_its_modules_m():
    scheme = cf.IdScheme("2hr", {"See It Work": 2, "See It Scale": 4})

    assert scheme.fits("2hr-m2-q9", "See It Work")
    assert not scheme.fits("2hr-m4-q9", "See It Work")       # another module's m
    assert not scheme.fits("di-m2-q9", "See It Work")        # another course's token
    assert not scheme.fits("q-preview", "See It Work")       # the old schemes
    assert scheme.fits("2hr-m6-q1", "Make It Real")          # a new module, a free m
    assert not scheme.fits("2hr-m4-q1", "Make It Real")      # ...but not one in use


def test_it_goes_after_the_last_question_of_its_module_into_a_free_slot():
    course = [Question(id=i, topic=t, pool_order=o) for i, t, o in
              [("a", "W", 0), ("b", "S", 1), ("c", "S", 3), ("d", "W", 5)]]

    assert cf.placement(Question(topic="S"), course) == (4, {})


def test_making_room_moves_questions_only_as_far_as_the_next_gap():
    course = [Question(id=i, topic=t, pool_order=o) for i, t, o in
              [("a", "S", 0), ("b", "W", 1), ("c", "W", 2), ("d", "W", 4)]]

    order, moved = cf.placement(Question(topic="S"), course)
    assert order == 1
    assert moved == {"b": 2, "c": 3}  # d at 4 stays: 3 was free


def test_a_new_module_goes_last_and_an_empty_course_starts_at_zero():
    course = [Question(id="a", topic="W", pool_order=0), Question(id="b", topic="W", pool_order=1)]

    assert cf.placement(Question(topic="New"), course) == (2, {})
    assert cf.placement(Question(topic="New"), []) == (0, {})


# --- filing -------------------------------------------------------------------


def test_the_reported_question_is_filed_like_an_adopted_one(db, courses, two_hour):
    q = generated(certification_id=two_hour.id)
    taken = cf.taken_ids(db, courses)

    result = cf.file_into_course(db, q, two_hour, courses_dir=courses, taken=taken)

    # See It Scale is m4, and 2hr-m4-q2 its highest.
    assert q.id == "2hr-m4-q3"
    assert q.topic == "See It Scale"
    assert q.source_type == "pcm" and q.source_file == "One Pipeline, Many Files"
    assert q.pool_order == 4 and result.moved == {}  # the slot q-hidden-data left


def test_an_adopted_question_keeps_its_module_and_citation(db, courses, two_hour):
    q = Question(id="2hr-m4-q9", stem="x?", key="a", distractors=["b"], topic="See It Scale",
                 source_type="pcm", source_file="Lab 5 — One Pipeline", pool_order=3,
                 certification_id=two_hour.id)

    cf.file_into_course(db, q, two_hour, courses_dir=courses, taken=set())

    assert (q.id, q.topic, q.source_file, q.pool_order) == ("2hr-m4-q9", "See It Scale", "Lab 5 — One Pipeline", 3)


def test_a_certification_that_is_not_a_course_files_nothing(db, courses):
    cert = Certification(name="Slides")
    q = generated()
    before = q.id

    assert cf.file_into_course(db, q, cert, courses_dir=courses, taken=set()) is None
    assert q.id == before and q.pool_order == -1


def test_a_repair_writes_what_it_changed_into_the_history(db, courses, two_hour):
    q = generated(certification_id=two_hour.id)
    db.save(q)
    old = q.id

    cf.file_into_course(db, q, two_hour, courses_dir=courses, taken=cf.taken_ids(db, courses),
                        editor="Exam Bank", record=True)
    db.rename_question(old, q.id)
    db.save(q)

    saved = db.get(q.id)
    assert db.get(old) is None
    assert {(h["field"], h["old"], h["new"]) for h in saved.version_history} >= {
        ("id", old, "2hr-m4-q3"),
        ("topic", "One Pipeline, Many Files", "See It Scale"),
    }


def test_rename_refuses_an_id_that_exists(db, two_hour):
    with pytest.raises(ValueError):
        db.rename_question("2hr-m4-q1", "2hr-m2-q1")


def test_moving_to_make_room_is_not_an_edit(db, two_hour):
    before = db.get("2hr-m2-q2")
    db.set_pool_orders({"2hr-m2-q2": 6})
    after = db.get("2hr-m2-q2")

    assert after.pool_order == 6
    assert (after.version, after.version_history) == (before.version, before.version_history)


# --- the exporter -------------------------------------------------------------------


def test_one_unplaced_question_no_longer_scrambles_the_course_order():
    """Before 1.7.1 the exporter sorted only when EVERY question had a place."""
    qs = [Question(id="late", stem="late?", key="a", distractors=["b"], pool_order=-1),
          Question(id="two", stem="two?", key="a", distractors=["b"], pool_order=2),
          Question(id="zero", stem="zero?", key="a", distractors=["b"], pool_order=0)]

    assert [i["id"] for i in pcm_exam_items(qs)] == ["zero", "two", "late"]


# --- through the API -----------------------------------------------------------------


@pytest.fixture
def client(db):
    def override():
        database = ExamBankDB(db.db_path)
        try:
            yield database
        finally:
            database.close()

    app.dependency_overrides[deps.get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def _wait(client, job_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] != jobs.RUNNING:
            return body
        time.sleep(0.02)
    pytest.fail("job did not finish")


def test_a_generated_question_committed_to_a_course_is_filed(client, db, courses, two_hour, monkeypatch):
    monkeypatch.setattr(generation_router, "generate_questions_batch",
                        lambda **kw: [generated(id="03f2c063-39c7-43da-ae6a-84d076979851")])
    job = client.post("/api/generate", json={"course_slug": "pdi-2hr-lab"}).json()["jobId"]
    _wait(client, job)

    body = client.post(f"/api/jobs/{job}/commit", json={"certification_id": two_hour.id}).json()

    assert body["filed"] == [{"id": "2hr-m4-q3", "poolOrder": 4, "topic": "See It Scale"}]
    saved = db.get("2hr-m4-q3")
    assert saved.pool_order == 4 and saved.topic == "See It Scale"
    assert db.get("03f2c063-39c7-43da-ae6a-84d076979851") is None


def test_two_questions_committed_together_get_different_ids(client, db, courses, two_hour, monkeypatch):
    monkeypatch.setattr(generation_router, "generate_questions_batch",
                        lambda **kw: [generated(), generated()])
    job = client.post("/api/generate", json={"course_slug": "pdi-2hr-lab"}).json()["jobId"]
    _wait(client, job)

    filed = client.post(f"/api/jobs/{job}/commit", json={"certification_id": two_hour.id}).json()["filed"]

    assert len({f["id"] for f in filed}) == 2
    assert sorted(f["poolOrder"] for f in filed) == [4, 5]


def test_an_import_keeps_an_id_that_fits_and_renumbers_every_other(client, db, courses, two_hour):
    """A course's own id is how the course and the bank recognise a question,
    so it stays. An id carried from another file or course, and one the
    bank made up, both become the next number in the module."""
    fits = {"id": "2hr-m2-q7", "stem": "Kept?", "key": "a", "distractors": ["b"], "topic": "See It Work"}
    foreign = {"id": "from-the-file", "stem": "Which step reads a file?", "key": "a",
               "distractors": ["b"], "topic": "See It Work"}
    minted = {"id": "5d1e2f3a-0b1c-4d2e-8f90-123456789abc", "stem": "Which join keeps unmatched rows?",
              "key": "a", "distractors": ["b"], "topic": "See It Work"}

    body = client.post("/api/import/commit", json={"questions": [fits, foreign, minted],
                                                   "certification_id": two_hour.id}).json()

    assert body["ids"] == ["2hr-m2-q7", "2hr-m2-q8", "2hr-m2-q9"]
    assert db.get("from-the-file") is None
    assert db.get("2hr-m2-q8").pool_order >= 0


def test_moving_a_course_question_to_another_module_renumbers_it(client, db, courses, two_hour):
    body = client.put("/api/questions/2hr-m2-q2", json={"topic": "See It Scale", "editor": "SME"}).json()

    assert body["id"] == "2hr-m4-q3"
    assert db.get("2hr-m2-q2") is None
    saved = db.get("2hr-m4-q3")
    assert saved.topic == "See It Scale"
    assert ("id", "2hr-m2-q2", "2hr-m4-q3", "SME") in {
        (h["field"], h["old"], h["new"], h["editor"]) for h in saved.version_history}


def test_any_other_edit_keeps_the_id(client, db, courses, two_hour):
    body = client.put("/api/questions/2hr-m2-q2", json={"stem": "Which step reads a file now?"}).json()

    assert body["id"] == "2hr-m2-q2"
    assert db.get("2hr-m2-q2").stem == "Which step reads a file now?"


def test_a_question_outside_any_course_keeps_its_id_when_its_topic_changes(client, db):
    cert = Certification(name="Slides")
    db.save_certification(cert)
    db.save(Question(id="slide-q", stem="Which?", key="a", distractors=["b"], topic="A",
                     certification_id=cert.id))

    assert client.put("/api/questions/slide-q", json={"topic": "B"}).json()["id"] == "slide-q"


def test_ids_in_an_exam_json_saved_with_a_byte_order_mark_are_taken(db, courses, two_hour):
    """Before 1.8.1 `taken_ids` skipped such a file without a word, so the
    next question filed into that course could be given one of its ids."""
    (courses / "pdi-2hr-lab" / "exam.json").write_text(
        json.dumps({"questions": [{"id": "2hr-m4-q3", "module": "See It Scale"}]}),
        encoding="utf-8-sig")

    assert "2hr-m4-q3" in cf.taken_ids(db, courses)
    q = generated(certification_id=two_hour.id)
    cf.file_into_course(db, q, two_hour, courses_dir=courses, taken=cf.taken_ids(db, courses))
    assert q.id == "2hr-m4-q4"


# --- one way in, one policy (1.9.0) -------------------------------------------------
#
# Import refused a question that could not be graded; generation's commit saved
# it, and the editor's Save refused it only in the browser. Every path that adds
# or saves a question now applies the same rules (core/validation.py).


def test_a_generated_question_that_cannot_be_graded_is_refused(client, db, courses, two_hour, monkeypatch):
    monkeypatch.setattr(generation_router, "generate_questions_batch",
                        lambda **kw: [generated(key="", id="c0ffee00-0000-4000-8000-000000000001"),
                                      generated()])
    job = client.post("/api/generate", json={"course_slug": "pdi-2hr-lab"}).json()["jobId"]
    _wait(client, job)

    body = client.post(f"/api/jobs/{job}/commit", json={"certification_id": two_hour.id}).json()

    assert body["saved"] == 1
    assert len(body["refused"]) == 1 and "Nothing is marked correct" in body["refused"][0]["reason"]
    assert db.get("c0ffee00-0000-4000-8000-000000000001") is None
    # The refused question reserved nothing: the saved one takes the next number.
    assert body["filed"][0]["id"] == "2hr-m4-q3"


def test_the_editor_save_refuses_what_cannot_be_graded(client, db, courses, two_hour):
    response = client.put("/api/questions/2hr-m2-q2", json={"key": "", "stem": "Changed?"})

    assert response.status_code == 400
    assert "Nothing is marked correct" in response.json()["detail"]
    assert db.get("2hr-m2-q2").stem == "2hr-m2-q2?"


def test_import_and_generation_take_the_same_way_in(db, courses, two_hour):
    from exam_bank.core.intake import take_in

    done = take_in(db, [generated(key=""), generated(), Question(stem="x?", key="a", distractors=["a"])],
                   certification_id=two_hour.id, courses_dir=courses)

    assert [q.id for q in done.saved] == ["2hr-m4-q3"]
    assert [r["reason"] for r in done.refused] == [
        "Nothing is marked correct, so the question cannot be graded.",
        '"a" is both correct and a distractor.',
    ]
