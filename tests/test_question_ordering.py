"""The order a page of questions comes back in.

The bank browsed newest-first, which is the wrong default for a pool that
was authored as a sequence: `pool_order` is the position a question held in
its course's exam.json, and the courses are written lab by lab, so that
column already IS workshop order. Nothing was using it.
"""

import pytest

from exam_bank.core.bank import Certification, Question


def _q(stem, order, cert_id, topic=""):
    return Question(
        stem=stem, question_type="single", key="Right",
        distractors=["Wrong", "Other", "Another"],
        explanation="Right - Correct. Wrong - Incorrect.",
        topic=topic, certification_id=cert_id, pool_order=order,
    )


@pytest.fixture
def pool(tmp_db):
    cert = tmp_db.save_certification(
        Certification(name="A Course", source_type="pcm", source_ref="a-course"))
    # Saved out of order on purpose, and with the LAST lab's question saved
    # most recently - so "newest first" and "course order" disagree.
    for stem, order, topic in (
        ("Dashboards, the final lab? (Choose one.)", 20, "Dashboards"),
        ("Overview, the first lab? (Choose one.)", 0, "Overview"),
        ("Reports, the middle lab? (Choose one.)", 10, "Reports"),
    ):
        tmp_db.save(_q(stem, order, cert.id, topic))
    return cert


def test_course_order_is_the_default(pool, tmp_db):
    """What the workshops teach first comes first."""
    got = [q.topic for q in tmp_db.search(certification_id=pool.id)]
    assert got == ["Overview", "Reports", "Dashboards"]


def test_recently_updated_is_still_available(pool, tmp_db):
    got = [q.topic for q in tmp_db.search(certification_id=pool.id, sort="updated")]
    assert got[0] == "Reports", "the last one saved leads"


def test_a_question_with_no_pool_position_sorts_last(pool, tmp_db):
    """Authored here, never in a course: pool_order is -1. Ascending order
    would otherwise open every pool on the handful of unfiled drafts."""
    tmp_db.save(_q("Authored in the bank? (Choose one.)", -1, pool.id, "Unfiled"))

    got = [q.topic for q in tmp_db.search(certification_id=pool.id)]
    assert got == ["Overview", "Reports", "Dashboards", "Unfiled"]


def test_an_unknown_sort_falls_back_rather_than_raising(pool, tmp_db):
    """It arrives from a URL query string; a typo must not 500 a browse."""
    got = [q.topic for q in tmp_db.search(certification_id=pool.id, sort="sideways")]
    assert got == ["Overview", "Reports", "Dashboards"]


def test_topics_come_out_grouped_without_the_bank_knowing_about_labs(pool, tmp_db):
    """The grouping is a consequence of pool_order, not a feature: authors
    write each topic's questions together, so their positions are
    contiguous. Nothing here parses SUMMARY.md or lab numbers."""
    tmp_db.save(_q("Overview, second question? (Choose one.)", 1, pool.id, "Overview"))
    tmp_db.save(_q("Reports, second question? (Choose one.)", 11, pool.id, "Reports"))

    topics = [q.topic for q in tmp_db.search(certification_id=pool.id)]
    assert topics == ["Overview", "Overview", "Reports", "Reports", "Dashboards"]


def test_topics_are_listed_in_course_order_not_alphabetically(pool, tmp_db):
    """The topic dropdown listed A-Z, which put Dashboards before Overview -
    an order the course never taught in. A topic's place is the earliest
    pool position any of its questions holds."""
    assert tmp_db.get_topics(pool.id) == ["Overview", "Reports", "Dashboards"]
    assert sorted(tmp_db.get_topics(pool.id)) != tmp_db.get_topics(pool.id), (
        "if these ever coincide the test proves nothing - pick topics whose "
        "alphabetical order differs from their course order"
    )


def test_topic_counts_use_the_same_order(pool, tmp_db):
    """Two listings of the same thing must not disagree about its order."""
    assert list(tmp_db.get_topic_counts(pool.id)) == tmp_db.get_topics(pool.id)


def test_a_topic_authored_in_the_bank_does_not_jump_the_queue(pool, tmp_db):
    """pool_order -1 means "never in a course". Ranked naively it is the
    smallest number and would drag its topic to the front of every list."""
    tmp_db.save(_q("Authored here? (Choose one.)", -1, pool.id, "Extra"))

    assert tmp_db.get_topics(pool.id) == ["Overview", "Reports", "Dashboards", "Extra"]


def test_the_exam_paper_topic_mix_uses_course_order_too(pool, tmp_db):
    """The exam-paper pane is where an author actually SETS topic weights,
    and it reads its own query. Alphabetical put "Concepts & Terminology"
    above "Getting Started" in the DI mix - the reverse of how the course
    runs - while the Bank pane next door had already been fixed."""
    from exam_bank.core.exam_builder import get_available_topics

    got = list(get_available_topics(tmp_db, [pool.id], ["draft"]))
    assert got == ["Overview", "Reports", "Dashboards"]
    assert got == tmp_db.get_topics(pool.id), (
        "the two listings must not disagree about the order of the same "
        "topics - they share _TOPIC_ORDER for exactly that reason"
    )
