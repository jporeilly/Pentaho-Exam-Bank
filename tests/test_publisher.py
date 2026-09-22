"""Publishing the bank's questions into a live course's exam.json.

The thing under test is a MERGE, not a write. A course's exam.json belongs to
two owners — the Content Editor holds the delivery and grading settings, the
bank holds ``questions`` — so the interesting assertions here are mostly about
what does NOT change.

Each refusal is tested twice: that it fires on the bad case, and that the
same call succeeds once the bad part is removed. Without the second half,
deleting a guard still passes.
"""

import json

import pytest

from exam_bank.core.bank import Question
from exam_bank.core.publisher import (
    PublishRefused,
    apply,
    plan,
    stale_blocks,
    update_pool_numerals,
)

# A course's exam.json as actually authored: LF endings, indent 2, trailing
# newline, and settings the bank has no business touching. `intake` is the
# one that matters most — it decides whether the course collects a candidate
# at all, and the whole-document exporter has no parameter for it.
EXAM = {
    "title": "Wrap-Up Check",
    "description": "10 questions drawn from a pool. Pass mark is 60%.",
    "passMark": 60,
    "questionsPerAttempt": 2,
    "shuffle": True,
    "webhookUrl": "https://script.google.com/macros/s/EXAMPLE/exec",
    "webhookSecret": "pcm_exam_example",
    "intake": {
        "optional": False,
        "trackResults": True,
        "collectCandidate": True,
        "lead": "Tell us who you are.",
    },
    "questions": [
        {
            "id": "m1-q1",
            "prompt": "Which step reads a delimited file?",
            "options": ["CSV file input", "Table output", "Sort rows"],
            "module": "See It Work",
            "correct": 0,
            "source": "Lab 1 - Your First Win",
        },
        {
            "id": "m1-q2",
            "prompt": "Which two steps write to a database?",
            "options": ["Table output", "Insert / Update", "Sort rows"],
            "module": "Getting Started",
            "correctIndices": [0, 1],
            "source": "Lab 2 - Loading",
        },
    ],
}


def write_exam(tmp_path, document=None):
    path = tmp_path / "exam.json"
    path.write_text(
        json.dumps(document if document is not None else EXAM, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def adopted(qid, key, distractors, *, order=0, **kw):
    """A question as it would stand after adoption from a course."""
    return Question(
        id=qid,
        stem=kw.pop("stem", "Which step reads a delimited file?"),
        key=key,
        distractors=list(distractors),
        option_order=kw.pop("option_order", None) or [key, *distractors],
        pool_order=order,
        source_type="pcm",
        source_file=kw.pop("source_file", "Lab 1 - Your First Win"),
        topic=kw.pop("topic", "See It Work"),
        **kw,
    )


@pytest.fixture
def pool():
    """The two questions above, as the bank holds them."""
    return [
        adopted(
            "m1-q1", "CSV file input", ["Table output", "Sort rows"],
            order=0,
            option_order=["CSV file input", "Table output", "Sort rows"],
        ),
        adopted(
            "m1-q2", "", ["Sort rows"],
            order=1,
            stem="Which two steps write to a database?",
            question_type="multi",
            keys=["Table output", "Insert / Update"],
            option_order=["Table output", "Insert / Update", "Sort rows"],
            topic="Getting Started",
            source_file="Lab 2 - Loading",
        ),
    ]


# --- what must not change -------------------------------------------------


def test_the_settings_the_editor_owns_survive(tmp_path, pool):
    path = write_exam(tmp_path)
    apply(plan(path, pool))

    after = json.loads(path.read_text(encoding="utf-8"))
    for key in ("title", "description", "passMark", "questionsPerAttempt",
                "shuffle", "webhookUrl", "webhookSecret"):
        assert after[key] == EXAM[key], f"{key} changed"


def test_the_intake_block_survives_whole(tmp_path, pool):
    """The block the whole-document exporter would have dropped: it has no
    parameter for `intake`, and a course that stopped collecting a candidate
    would still look like a working exam."""
    path = write_exam(tmp_path)
    apply(plan(path, pool))

    assert json.loads(path.read_text(encoding="utf-8"))["intake"] == EXAM["intake"]


def test_an_unknown_future_key_survives(tmp_path, pool):
    """This app must not be the reason a key it has never heard of is lost."""
    document = dict(EXAM, somethingAddedLater={"nested": [1, 2, 3]})
    path = write_exam(tmp_path, document)
    apply(plan(path, pool))

    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["somethingAddedLater"] == {"nested": [1, 2, 3]}


def test_key_order_is_preserved(tmp_path, pool):
    """A course that lists passMark before description still does afterwards,
    so the diff is the questions and nothing else."""
    document = {"title": "T", "passMark": 60, "description": "d",
                "questions": EXAM["questions"]}
    path = write_exam(tmp_path, document)
    apply(plan(path, pool))

    assert list(json.loads(path.read_text(encoding="utf-8"))) == list(document)


def test_the_file_keeps_its_on_disk_conventions(tmp_path, pool):
    """LF, indent 2, trailing newline, no BOM - matching what PCM's courses
    are authored with, so publishing does not produce a whole-file diff."""
    path = write_exam(tmp_path)
    apply(plan(path, pool))

    raw = path.read_bytes()
    assert raw.endswith(b"\n")
    assert b"\r\n" not in raw
    assert raw[:3] != b"\xef\xbb\xbf"
    assert raw.decode("utf-8").splitlines()[1].startswith("  ")


def test_a_crlf_file_stays_crlf(tmp_path, pool):
    """The Content Manager repo has core.autocrlf=true, so a course file
    checked out afresh is CRLF while one written by tooling is LF. Imposing
    either turns a two-question edit into a whole-file diff — which is
    exactly what a `git checkout` of one of these files does today."""
    path = tmp_path / "exam.json"
    path.write_text(json.dumps(EXAM, indent=2) + "\n", encoding="utf-8", newline="\r\n")
    assert b"\r\n" in path.read_bytes()

    pool[0].stem = "Reworded?"
    apply(plan(path, pool))

    raw = path.read_bytes()
    assert b"\r\n" in raw
    assert b"\n" not in raw.replace(b"\r\n", b""), "mixed endings were produced"


def test_an_lf_file_stays_lf(tmp_path, pool):
    path = write_exam(tmp_path)
    pool[0].stem = "Reworded?"
    apply(plan(path, pool))

    assert b"\r\n" not in path.read_bytes()


def test_publishing_an_unchanged_pool_is_a_noop(tmp_path, pool):
    path = write_exam(tmp_path)
    before = path.read_bytes()
    made = plan(path, pool)

    assert made.is_noop
    apply(made)
    assert path.read_bytes() == before, "a no-op publish rewrote the file"


# --- the diff -------------------------------------------------------------


def test_a_changed_stem_is_reported_by_field(tmp_path, pool):
    pool[0].stem = "Which step reads a CSV?"
    made = plan(write_exam(tmp_path), pool)

    assert [c.id for c in made.changed] == ["m1-q1"]
    assert made.changed[0].fields == ["prompt"]
    assert made.unchanged == 1
    assert not made.added and not made.removed


def test_an_added_question_is_reported(tmp_path, pool):
    pool.append(adopted("m1-q3", "Dummy", ["Table input"], order=2))
    made = plan(write_exam(tmp_path), pool)

    assert made.added == ["m1-q3"]
    assert made.before_count == 2 and made.after_count == 3


def test_a_removed_question_is_reported(tmp_path, pool):
    # Without questionsPerAttempt: a course that draws every question it has
    # cannot shrink below its own draw, and that guard is tested on its own.
    document = {k: v for k, v in EXAM.items() if k != "questionsPerAttempt"}
    made = plan(write_exam(tmp_path, document), pool[:1])

    assert made.removed == ["m1-q2"]
    assert made.after_count == 1


def test_reordering_is_reported_on_its_own(tmp_path, pool):
    pool[0].pool_order, pool[1].pool_order = 1, 0
    made = plan(write_exam(tmp_path), pool)

    assert made.reordered
    assert not made.changed, "a move is not a content change"
    assert not made.is_noop


def test_appending_is_not_reported_as_a_reorder(tmp_path, pool):
    """Order is compared over the questions common to both sides - otherwise
    adding one at the end reads as 'the whole pool moved'."""
    pool.append(adopted("m1-q3", "Dummy", ["Table input"], order=2))
    made = plan(write_exam(tmp_path), pool)

    assert made.added == ["m1-q3"]
    assert not made.reordered


def test_preserved_keys_are_listed_for_the_author(tmp_path, pool):
    made = plan(write_exam(tmp_path), pool)

    assert "intake" in made.preserved_keys
    assert "questions" not in made.preserved_keys


# --- refusals -------------------------------------------------------------


def test_an_empty_selection_is_refused(tmp_path, pool):
    path = write_exam(tmp_path)
    with pytest.raises(PublishRefused, match="cannot be sat"):
        plan(path, [])

    plan(path, pool)  # and the same call succeeds with a selection


def test_a_missing_exam_json_is_refused(tmp_path, pool):
    """Creating one would mean inventing the pass mark, the webhook and the
    intake behaviour - every setting this app is careful not to own."""
    with pytest.raises(PublishRefused, match="does not create one"):
        plan(tmp_path / "exam.json", pool)

    write_exam(tmp_path)
    plan(tmp_path / "exam.json", pool)


def test_unreadable_json_is_refused_rather_than_replaced(tmp_path, pool):
    path = tmp_path / "exam.json"
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(PublishRefused, match="not readable JSON"):
        plan(path, pool)

    assert path.read_text(encoding="utf-8") == "{ not json", "the bad file was touched"


def test_a_pool_smaller_than_questions_per_attempt_is_refused(tmp_path, pool):
    """The exam draws 2; publishing 1 leaves an exam that cannot be sat."""
    path = write_exam(tmp_path)
    with pytest.raises(PublishRefused, match="cannot be sat"):
        plan(path, pool[:1])

    plan(path, pool)


def test_duplicate_ids_are_refused(tmp_path, pool):
    """PCM keys in-progress attempts and recorded results on the id."""
    pool[1].id = pool[0].id
    path = write_exam(tmp_path)
    with pytest.raises(PublishRefused, match="share an id"):
        plan(path, pool)

    pool[1].id = "m1-q2"
    plan(path, pool)


# --- the stale block the published courses turned out to carry ------------


def test_a_stale_intake_contact_block_is_refused(tmp_path, pool):
    """Five published exam.json carried the contact relay's secret inside a
    dead `intake.contact` block. Publishing over one would re-commit it."""
    document = json.loads(json.dumps(EXAM))
    document["intake"]["contact"] = {
        "to": "academy@example.com",
        "webhookSecret": "pcm_contact_example",
    }
    path = write_exam(tmp_path, document)

    with pytest.raises(PublishRefused, match="intake.contact"):
        plan(path, pool)

    del document["intake"]["contact"]
    plan(write_exam(tmp_path, document), pool)


def test_the_stale_block_is_refused_not_stripped(tmp_path, pool):
    """Dropping an authored key silently is the same failure in the other
    direction, and silence is what let the published copies sit for months."""
    document = json.loads(json.dumps(EXAM))
    document["intake"]["contact"] = {"webhookSecret": "pcm_contact_example"}
    path = write_exam(tmp_path, document)
    before = path.read_bytes()

    with pytest.raises(PublishRefused):
        plan(path, pool)
    assert path.read_bytes() == before


def test_a_nested_webhook_secret_is_refused_wherever_it_sits(tmp_path, pool):
    """The general form: a credential at a path no code reads."""
    document = json.loads(json.dumps(EXAM))
    document["results"] = {"relay": {"webhookSecret": "pcm_somewhere_else"}}
    path = write_exam(tmp_path, document)

    with pytest.raises(PublishRefused, match="results.relay.webhookSecret"):
        plan(path, pool)


def test_the_top_level_webhook_secret_is_not_mistaken_for_a_stale_one(tmp_path, pool):
    """The one at the top level is where it belongs and must not trip it."""
    assert stale_blocks(EXAM) == []
    plan(write_exam(tmp_path), pool)


def test_stale_blocks_reports_every_path_it_finds(tmp_path):
    document = json.loads(json.dumps(EXAM))
    document["intake"]["contact"] = {"webhookSecret": "x"}
    found = stale_blocks(document)

    assert "intake.contact" in found
    assert "intake.contact.webhookSecret" in found


# --- the race with the Content Editor -------------------------------------


def test_a_file_changed_after_planning_is_not_overwritten(tmp_path, pool):
    """The Content Editor writes this same file, and it writes its whole
    in-memory copy. A plan reviewed a minute ago can describe a file that no
    longer exists in that form."""
    path = write_exam(tmp_path)
    made = plan(path, pool)

    edited = dict(EXAM, title="Renamed in the Content Editor")
    write_exam(tmp_path, edited)

    with pytest.raises(PublishRefused, match="changed"):
        apply(made)
    assert json.loads(path.read_text(encoding="utf-8"))["title"] == edited["title"]


def test_the_callers_expected_hash_is_checked_too(tmp_path, pool):
    """A dry run hands the author a hash; passing it back turns the race into
    a refusal instead of a silent overwrite."""
    path = write_exam(tmp_path)
    made = plan(path, pool)

    with pytest.raises(PublishRefused, match="changed"):
        apply(made, expect_sha="not-the-hash")

    apply(made, expect_sha=made.source_sha)


def test_nothing_is_left_behind_when_a_write_is_refused(tmp_path, pool):
    path = write_exam(tmp_path)
    made = plan(path, pool)
    with pytest.raises(PublishRefused):
        apply(made, expect_sha="not-the-hash")

    assert [p.name for p in tmp_path.iterdir()] == ["exam.json"]


# --- the description's pool-size claim ------------------------------------
#
# `verify-course.mjs` FAILS the build when the prose misstates the pool size,
# so a publish that changes the pool and leaves the sentence alone hands back
# a course that will not verify. Only the numeral moves; the sentence is the
# author's.


@pytest.mark.parametrize(
    "before, after",
    [
        ("Drawn from a pool of 2.", "Drawn from a pool of 7."),
        ("A 2-question bank.", "A 7-question bank."),
        ("From a POOL OF 2 questions.", "From a POOL OF 7 questions."),
        # The verifier collapses whitespace before matching, so a claim split
        # across lines counts there and has to count here.
        ("Drawn from a pool\n  of 2.", "Drawn from a pool\n  of 7."),
    ],
)
def test_the_pool_numeral_is_updated_in_place(before, after):
    assert update_pool_numerals(before, 7) == after


@pytest.mark.parametrize(
    "text",
    [
        "10 questions per attempt.",       # questionsPerAttempt, not the pool
        "Pass mark is 60%.",               # passMark
        "A pool of questions, no number.",
        "",
    ],
)
def test_other_claims_are_left_to_the_author(text):
    """Publishing changes neither questionsPerAttempt nor passMark, so a
    disagreement there is a real one rather than something to paper over."""
    assert update_pool_numerals(text, 7) == text


def test_publishing_never_rewrites_the_app_name_in_prose():
    """A real description, pinned verbatim.

    `_N_QUESTION_BANK` is run over authored prose, and this sentence contains
    this app's own former name. The leading `(\\d+)-` is the only thing keeping
    the pattern off it: loosened to `(question\\s+bank)`, a publish would
    rewrite the product name inside an author's sentence and nothing would
    connect the two changes. The pool numeral moves; every other word stays.
    """
    authored = (
        "DRAFT for review - generated from the course content; review and "
        "refine in the Question Bank app before a real workshop. 15 questions "
        "per attempt from a pool of 18, pass mark 80%."
    )

    assert update_pool_numerals(authored, 18) == authored
    grown = update_pool_numerals(authored, 25)
    assert grown == authored.replace("pool of 18", "pool of 25")

    # Said directly, so the failure names the thing that went wrong.
    for untouched in ("DRAFT for review", "Question Bank app",
                      "15 questions per attempt", "pass mark 80%"):
        assert untouched in grown, f"publishing rewrote {untouched!r}"


def test_publishing_updates_the_pool_size_the_build_checks(tmp_path, pool):
    document = dict(EXAM, description="Drawn from a pool of 2. Pass mark is 60%.")
    document = {k: v for k, v in document.items() if k != "questionsPerAttempt"}
    path = write_exam(tmp_path, document)

    made = plan(path, pool[:1])
    assert made.description_after == "Drawn from a pool of 1. Pass mark is 60%."
    apply(made)

    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["description"] == "Drawn from a pool of 1. Pass mark is 60%."


def test_a_description_that_already_agrees_is_untouched(tmp_path, pool):
    document = dict(EXAM, description="Drawn from a pool of 2.")
    made = plan(write_exam(tmp_path, document), pool)

    assert made.description_after == ""
    assert "description" in made.preserved_keys


def test_a_description_change_alone_is_not_a_noop(tmp_path, pool):
    """Otherwise a course whose pool is right but whose prose is stale would
    report 'nothing to publish' and keep failing its own build."""
    document = dict(EXAM, description="Drawn from a pool of 99.")
    made = plan(write_exam(tmp_path, document), pool)

    assert not made.added and not made.removed and not made.changed
    assert not made.is_noop
    assert made.description_after == "Drawn from a pool of 2."


def test_a_rewritten_description_is_not_listed_as_preserved(tmp_path, pool):
    """It would be the one untrue item in a list whose whole job is to say
    what the merge did not touch."""
    document = dict(EXAM, description="Drawn from a pool of 99.")
    made = plan(write_exam(tmp_path, document), pool)

    assert "description" not in made.preserved_keys


# --- the edit that made this necessary ------------------------------------


def test_a_corrected_key_replaces_the_typo_rather_than_joining_it(tmp_path, pool):
    """End to end over the merge: the stale `option_order` defect must not
    reach a course file."""
    pool[0].key = "CSV file input step"
    path = write_exam(tmp_path)
    apply(plan(path, pool))

    item = json.loads(path.read_text(encoding="utf-8"))["questions"][0]
    assert item["options"] == ["CSV file input step", "Table output", "Sort rows"]
    assert item["correct"] == 0
