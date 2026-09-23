"""Tests for core/exam_builder.py — question selection and PDF generation."""

import pytest

from exam_bank.core.bank import DIFFICULTIES, Question, Certification, ExamBankDB
from exam_bank.core.exam_builder import (
    select_exam_questions, generate_exam_pdf, get_available_topics, ExamPDF,
    plan_exam,
)


@pytest.fixture
def exam_db(tmp_path):
    """Build a DB with questions across multiple topics for exam selection."""
    db = ExamBankDB(tmp_path / "exam.db")
    cert = db.save_certification(Certification(name="Exam Cert", source_type="pptx"))

    topics = {
        "Networking": 10,
        "Security": 8,
        "Cloud": 5,
    }
    for topic, count in topics.items():
        for i in range(count):
            q = Question(
                stem=f"{topic} question {i + 1}? (Choose one.)",
                key=f"{topic} answer {i + 1}",
                distractors=["Wrong A", "Wrong B", "Wrong C"],
                topic=topic,
                difficulty="Medium" if i % 3 == 0 else ("Easy" if i % 3 == 1 else "Hard"),
                bloom_level="Apply",
                certification_id=cert.id,
                status="approved",
            )
            db.save(q)

    yield db, cert
    db.close()


class TestSelectExamQuestions:
    def test_basic_selection(self, exam_db):
        db, cert = exam_db
        questions = select_exam_questions(
            db=db,
            certification_ids=[cert.id],
            total_questions=10,
            difficulties=["Easy", "Medium", "Hard"],
            topic_weights={"Networking": 50, "Security": 30, "Cloud": 20},
        )
        assert len(questions) == 10

    def test_topic_weighting(self, exam_db):
        db, cert = exam_db
        questions = select_exam_questions(
            db=db,
            certification_ids=[cert.id],
            total_questions=10,
            difficulties=["Easy", "Medium", "Hard"],
            topic_weights={"Networking": 60, "Security": 40},
        )
        net_count = sum(1 for q in questions if q.topic == "Networking")
        sec_count = sum(1 for q in questions if q.topic == "Security")
        assert net_count >= 5  # ~60% of 10
        assert sec_count >= 3  # ~40% of 10

    def test_deterministic_with_seed(self, exam_db):
        db, cert = exam_db
        kwargs = dict(
            db=db, certification_ids=[cert.id], total_questions=8,
            difficulties=["Easy", "Medium", "Hard"],
            topic_weights={"Networking": 50, "Security": 50},
            seed=42,
        )
        run1 = select_exam_questions(**kwargs)
        run2 = select_exam_questions(**kwargs)
        assert [q.id for q in run1] == [q.id for q in run2]

    def test_non_deterministic_without_seed(self, exam_db):
        db, cert = exam_db
        kwargs = dict(
            db=db, certification_ids=[cert.id], total_questions=10,
            difficulties=["Easy", "Medium", "Hard"],
            topic_weights={"Networking": 50, "Security": 50},
            randomize=True,
        )
        # Run multiple times — at least one should differ (statistically near-certain)
        results = [tuple(q.id for q in select_exam_questions(**kwargs)) for _ in range(5)]
        assert len(set(results)) > 1

    def test_difficulty_filter(self, exam_db):
        db, cert = exam_db
        questions = select_exam_questions(
            db=db,
            certification_ids=[cert.id],
            total_questions=5,
            difficulties=["Easy"],
            topic_weights={"Networking": 100},
        )
        for q in questions:
            assert q.difficulty == "Easy"

    def test_shortfall_redistribution(self, exam_db):
        """If a topic has fewer questions than requested, surplus is taken from others."""
        db, cert = exam_db
        questions = select_exam_questions(
            db=db,
            certification_ids=[cert.id],
            total_questions=15,
            difficulties=["Easy", "Medium", "Hard"],
            topic_weights={"Cloud": 80, "Networking": 20},
        )
        # Cloud has only 5, so Networking should pick up the slack
        assert len(questions) <= 15

    def test_empty_db(self, tmp_path):
        db = ExamBankDB(tmp_path / "empty.db")
        cert = db.save_certification(Certification(name="Empty"))
        questions = select_exam_questions(
            db=db,
            certification_ids=[cert.id],
            total_questions=10,
            difficulties=["Medium"],
            topic_weights={"X": 100},
        )
        assert len(questions) == 0
        db.close()


class TestGetAvailableTopics:
    def test_returns_topics_with_counts(self, exam_db):
        db, cert = exam_db
        topics = get_available_topics(db, [cert.id])
        assert topics["Networking"] == 10
        assert topics["Security"] == 8
        assert topics["Cloud"] == 5

    def test_empty_certs(self, exam_db):
        db, _ = exam_db
        assert get_available_topics(db, []) == {}


class TestExamPDF:
    def test_generate_pdf(self, exam_db, tmp_path):
        db, cert = exam_db
        questions = select_exam_questions(
            db=db,
            certification_ids=[cert.id],
            total_questions=5,
            difficulties=["Easy", "Medium", "Hard"],
            topic_weights={"Networking": 60, "Security": 40},
            seed=42,
        )
        output = tmp_path / "exam.pdf"
        result = generate_exam_pdf(
            questions=questions,
            title="Test Exam",
            institution="Test University",
            time_limit=60,
            include_answer_key=True,
            output_path=output,
        )
        assert result.exists()
        assert result.stat().st_size > 0

    def test_generate_pdf_with_explanations(self, exam_db, tmp_path):
        db, cert = exam_db
        questions = select_exam_questions(
            db=db,
            certification_ids=[cert.id],
            total_questions=3,
            difficulties=["Medium"],
            topic_weights={"Security": 100},
        )
        output = tmp_path / "exam_explain.pdf"
        result = generate_exam_pdf(
            questions=questions,
            title="Explained Exam",
            include_answer_key=True,
            include_explanations=True,
            output_path=output,
        )
        assert result.exists()

    def test_generate_pdf_no_answer_key(self, exam_db, tmp_path):
        db, cert = exam_db
        questions = select_exam_questions(
            db=db,
            certification_ids=[cert.id],
            total_questions=2,
            difficulties=["Easy", "Medium", "Hard"],
            topic_weights={"Cloud": 100},
        )
        output = tmp_path / "exam_no_key.pdf"
        result = generate_exam_pdf(
            questions=questions,
            title="No Key Exam",
            include_answer_key=False,
            output_path=output,
        )
        assert result.exists()

    def test_unicode_safe(self, tmp_path):
        """PDF should handle unicode chars in questions."""
        q = Question(
            stem="What is the em-dash \u2014 used for? (Choose one.)",
            scenario="A typographer reviews \u201csmart quotes\u201d and other characters\u2026",
            key="Separating clauses",
            distractors=["Nothing", "Decoration", "Line break"],
            topic="Typography",
            difficulty="Easy",
        )
        output = tmp_path / "unicode.pdf"
        result = generate_exam_pdf(
            questions=[q],
            title="Unicode \u2014 Test",
            output_path=output,
        )
        assert result.exists()


class TestPlanExam:
    """What the weighting actually did, as opposed to what was asked for.

    The selection redistributes silently: a topic whose pool is too small
    contributes what it has, and the difference is taken from topics with
    spare questions. So a 40/30/30 exam can come back 40/45/15 with nothing
    anywhere saying so, and the author finds out by reading the paper.
    """

    def test_a_weighting_the_bank_can_meet_is_reported_as_honoured(self, exam_db):
        db, cert = exam_db
        plan = plan_exam(
            db, [cert.id], total_questions=9, difficulties=DIFFICULTIES,
            topic_weights={"Networking": 34, "Security": 33, "Cloud": 33},
        )

        assert plan.honoured
        assert plan.shortfall == 0
        assert plan.redistributed == 0
        assert len(plan.questions) == 9

    def test_a_topic_too_small_for_its_weight_is_named(self, exam_db):
        """Cloud has 5 questions. Asking it for 10 is a fact about the bank,
        and the author needs it before printing rather than after."""
        db, cert = exam_db
        plan = plan_exam(
            db, [cert.id], total_questions=20, difficulties=DIFFICULTIES,
            topic_weights={"Networking": 25, "Security": 25, "Cloud": 50},
        )

        cloud = next(t for t in plan.topics if t.topic == "Cloud")
        assert cloud.wanted == 10
        assert cloud.available == 5
        assert cloud.short == 5
        assert not plan.honoured

    def test_the_topics_that_covered_the_shortfall_are_named(self, exam_db):
        """Knowing the mix is wrong is half of it; the other half is which
        topic the learner will now see more of."""
        db, cert = exam_db
        plan = plan_exam(
            db, [cert.id], total_questions=20, difficulties=DIFFICULTIES,
            topic_weights={"Networking": 25, "Security": 25, "Cloud": 50},
        )

        lenders = {t.topic: t.lent for t in plan.topics if t.lent}
        assert lenders, "nothing reported as covering Cloud's shortfall"
        assert set(lenders) <= {"Networking", "Security"}
        assert sum(lenders.values()) == plan.redistributed

    def test_a_bank_too_small_overall_reports_a_shortfall(self, exam_db):
        """23 questions exist. Asking for 40 cannot be redistributed away."""
        db, cert = exam_db
        plan = plan_exam(
            db, [cert.id], total_questions=40, difficulties=DIFFICULTIES,
            topic_weights={"Networking": 34, "Security": 33, "Cloud": 33},
        )

        assert plan.requested == 40
        assert len(plan.questions) == 23
        assert plan.shortfall == 17
        assert not plan.honoured

    def test_every_weighted_topic_appears_in_the_account(self, exam_db):
        """Including one the bank has nothing for — a topic silently missing
        from the report reads as a topic that was fine."""
        db, cert = exam_db
        plan = plan_exam(
            db, [cert.id], total_questions=10, difficulties=DIFFICULTIES,
            topic_weights={"Networking": 50, "Nonexistent": 50},
        )

        reported = {t.topic for t in plan.topics}
        assert reported == {"Networking", "Nonexistent"}
        missing = next(t for t in plan.topics if t.topic == "Nonexistent")
        assert missing.available == 0
        assert missing.selected == 0

    def test_selected_counts_add_up_to_the_questions_returned(self, exam_db):
        """The account has to describe the paper that was actually built."""
        db, cert = exam_db
        plan = plan_exam(
            db, [cert.id], total_questions=20, difficulties=DIFFICULTIES,
            topic_weights={"Networking": 25, "Security": 25, "Cloud": 50},
        )

        assert sum(t.selected for t in plan.topics) == len(plan.questions)

    def test_the_wrapper_returns_exactly_the_planned_questions(self, exam_db):
        """`select_exam_questions` delegates here, so the two cannot diverge
        — but only if the same seed produces the same paper."""
        db, cert = exam_db
        args = dict(
            certification_ids=[cert.id], total_questions=9,
            difficulties=DIFFICULTIES,
            topic_weights={"Networking": 34, "Security": 33, "Cloud": 33},
            seed=7,
        )
        planned = plan_exam(db, **args).questions
        direct = select_exam_questions(db, **args)

        assert [q.id for q in planned] == [q.id for q in direct]
