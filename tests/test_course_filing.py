"""A question filed under a course takes the course's id, module and place.

Found in use (2026-09-29): a question generated for PDI in 2 Hours and saved
into the course came in as `03f2c063-39c7-…` among `q-preview` and `q-mi`,
with no place in the order and the lab's title ("One Pipeline, Many Files")
where the course files it under the module ("See It Scale"). One unplaced
question also switched the course order off for the whole publish.
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
    (other / "exam.json").write_text(json.dumps({"questions": [{"id": "q-metadata-injection"}]}),
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
    """The 2hr pool as it stood: q-hidden-data (See It Scale, 27) deleted."""
    cert = Certification(name="PDI in 2 Hours", source_type="pcm", source_ref="pdi-2hr-lab")
    db.save_certification(cert)
    layout = [("q-preview", "See It Work"), ("q-mi", "See It Scale"), ("q-join", "Make It Yours"),
              ("q-preview-loop", "See It Scale"), (None, None), ("q-reject-vs-error", "See It Work")]
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


def test_numbered_ids_continue_the_family_of_the_module():
    course = [Question(id=f"m3-q{n}", topic="Module 3") for n in range(1, 14)] + \
             [Question(id=f"m1-q{n}", topic="Module 1") for n in range(1, 6)]
    new = Question(stem="Which step?", topic="Module 3")

    assert cf.mint_id(new, course, set()) == "m3-q14"


def test_a_new_module_takes_the_courses_commonest_family():
    course = [Question(id=f"rd-q{n}", topic="A") for n in range(1, 13)] + \
             [Question(id=f"q{n}", topic="B") for n in range(1, 4)]

    assert cf.mint_id(Question(stem="x?", topic="New"), course, set()) == "rd-q13"


def test_a_numbered_id_skips_one_used_anywhere():
    course = [Question(id=f"ir-q{n}", topic="IR") for n in range(1, 11)]

    assert cf.mint_id(Question(stem="x?", topic="IR"), course, {"ir-q11"}) == "ir-q12"


def test_named_ids_get_the_course_prefix_and_the_questions_words():
    course = [Question(id=i) for i in ("q-preview", "q-mi", "q-hidden-data")]
    new = generated()

    assert cf.mint_id(new, course, set()) == "q-metadata-injection"
    assert cf.mint_id(new, course, {"q-metadata-injection"}) == "q-metadata-injection-2"


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

    # q-metadata-injection belongs to the other course's exam.json.
    assert q.id == "q-metadata-injection-2"
    assert q.topic == "See It Scale"
    assert q.source_type == "pcm" and q.source_file == "One Pipeline, Many Files"
    assert q.pool_order == 4 and result.moved == {}  # the slot q-hidden-data left


def test_an_adopted_question_keeps_its_module_and_citation(db, courses, two_hour):
    q = Question(id="q-kept", stem="x?", key="a", distractors=["b"], topic="See It Scale",
                 source_type="pcm", source_file="Lab 5 — One Pipeline", pool_order=3,
                 certification_id=two_hour.id)

    cf.file_into_course(db, q, two_hour, courses_dir=courses, taken=set())

    assert (q.id, q.topic, q.source_file, q.pool_order) == ("q-kept", "See It Scale", "Lab 5 — One Pipeline", 3)


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
        ("id", old, "q-metadata-injection-2"),
        ("topic", "One Pipeline, Many Files", "See It Scale"),
    }


def test_rename_refuses_an_id_that_exists(db, two_hour):
    with pytest.raises(ValueError):
        db.rename_question("q-mi", "q-preview")


def test_moving_to_make_room_is_not_an_edit(db, two_hour):
    before = db.get("q-reject-vs-error")
    db.set_pool_orders({"q-reject-vs-error": 6})
    after = db.get("q-reject-vs-error")

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

    assert body["filed"] == [{"id": "q-metadata-injection-2", "poolOrder": 4, "topic": "See It Scale"}]
    saved = db.get("q-metadata-injection-2")
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


def test_an_import_keeps_an_id_the_file_carried_and_replaces_one_it_made_up(client, db, courses, two_hour):
    kept = {"id": "from-the-file", "stem": "Kept?", "key": "a", "distractors": ["b"], "topic": "See It Work"}
    minted = {"id": "5d1e2f3a-0b1c-4d2e-8f90-123456789abc", "stem": "Which join keeps unmatched rows?",
              "key": "a", "distractors": ["b"], "topic": "See It Work"}

    body = client.post("/api/import/commit", json={"questions": [kept, minted],
                                                   "certification_id": two_hour.id}).json()

    assert "from-the-file" in body["ids"]
    assert not any(cf.is_minted(i) for i in body["ids"])
    assert db.get("from-the-file").pool_order >= 0
