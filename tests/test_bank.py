"""Tests for core/bank.py — Question model, validation, lifecycle, and DB CRUD."""

import pytest
from exam_bank.core.bank import (
    Question, Certification, ExamBankDB, ReviewEntry,
    STATUSES, STATUS_TRANSITIONS, BLOOM_LEVELS, DIFFICULTIES,
)


# ── Question model ─────────────────────────────────────────


class TestQuestionModel:
    def test_auto_id_and_timestamps(self):
        q = Question(stem="Test?")
        assert q.id
        assert q.created_at
        assert q.updated_at == q.created_at

    def test_correct_answers_single(self, sample_question):
        assert sample_question.correct_answers == ["HTTPS"]
        assert sample_question.num_correct == 1

    def test_correct_answers_multi(self, sample_multi_question):
        assert sample_multi_question.correct_answers == ["Jenkins", "GitHub Actions"]
        assert sample_multi_question.num_correct == 2

    def test_num_choices(self, sample_question):
        assert sample_question.num_choices == 4  # 1 key + 3 distractors

    def test_all_choices(self, sample_question):
        choices = sample_question.all_choices
        assert "HTTPS" in choices
        assert "FTP" in choices
        assert len(choices) == 4

    def test_format_label_single(self, sample_question):
        assert sample_question.format_label == "Single (4 choices)"

    def test_format_label_multi(self, sample_multi_question):
        assert sample_multi_question.format_label == "Select 2 (5 choices)"


# ── Lifecycle transitions ──────────────────────────────


class TestLifecycle:
    def test_draft_to_sme_review(self, sample_question):
        sample_question.transition("sme_review", sme_name="Alice")
        assert sample_question.status == "sme_review"
        assert sample_question.submitted_at
        assert len(sample_question.review_history) == 1
        assert sample_question.review_history[0]["sme_name"] == "Alice"

    def test_sme_review_to_approved(self, sample_question):
        sample_question.transition("sme_review", sme_name="Alice")
        sample_question.transition("approved", sme_name="Bob")
        assert sample_question.status == "approved"
        assert sample_question.approved_at

    def test_rejected_records_reason(self, sample_question):
        sample_question.transition("rejected", sme_name="Eve", comment="Poor distractors")
        assert sample_question.status == "rejected"
        assert sample_question.reject_reason == "Poor distractors"

    @pytest.mark.parametrize("back_to", ["sme_review", "draft"])
    def test_an_approved_question_can_be_sent_back(self, sample_question, back_to):
        # Edited after approval, it needs reviewing again - asked for 28 Sep
        # 2026, when approved could only be retired.
        sample_question.transition("sme_review", sme_name="A")
        sample_question.transition("approved", sme_name="B")
        assert sample_question.approved_at

        sample_question.transition(back_to, sme_name="C", comment="Reworded")

        assert sample_question.status == back_to
        assert sample_question.approved_at == "", "no longer approved, so no approval date"
        last = sample_question.review_history[-1]
        assert (last["from_status"], last["to_status"]) == ("approved", back_to)
        assert any(h["to_status"] == "approved" for h in sample_question.review_history), (
            "the history still says it was approved once"
        )

    def test_retiring_an_approved_question_keeps_its_approval_date(self, sample_question):
        sample_question.transition("sme_review")
        sample_question.transition("approved")
        sample_question.transition("retired")
        assert sample_question.approved_at

    def test_invalid_transition_raises(self, sample_question):
        with pytest.raises(ValueError, match="Cannot transition"):
            sample_question.transition("approved")  # draft -> approved not allowed

    def test_allowed_transitions(self, sample_question):
        assert "sme_review" in sample_question.allowed_transitions()
        assert "approved" not in sample_question.allowed_transitions()

    def test_full_lifecycle(self, sample_question):
        q = sample_question
        q.transition("sme_review", sme_name="A")
        q.transition("revised", sme_name="B", comment="Needs work")
        q.transition("sme_review", sme_name="A")
        q.transition("approved", sme_name="C")
        q.transition("retired", sme_name="D")
        assert q.status == "retired"
        assert len(q.review_history) == 5

    def test_rejected_to_draft_rework(self, sample_question):
        sample_question.transition("rejected", sme_name="X", comment="Bad")
        sample_question.transition("draft", sme_name="Y", comment="Reworking")
        assert sample_question.status == "draft"

    def test_all_status_transitions_valid(self):
        """Every defined transition must work without error."""
        for from_status, to_list in STATUS_TRANSITIONS.items():
            for to_status in to_list:
                q = Question(stem="Q?", key="A", distractors=["B", "C"], status=from_status)
                q.transition(to_status, sme_name="test")
                assert q.status == to_status


# ── ReviewEntry ────────────────────────────────────────


class TestReviewEntry:
    def test_auto_timestamp(self):
        entry = ReviewEntry(sme_name="Alice", action="approved")
        assert entry.timestamp
        assert entry.sme_name == "Alice"


# ── Database CRUD ──────────────────────────────────────


class TestDatabaseCRUD:
    def test_save_and_get(self, tmp_db, sample_question):
        saved = tmp_db.save(sample_question)
        loaded = tmp_db.get(saved.id)
        assert loaded is not None
        assert loaded.stem == sample_question.stem
        assert loaded.key == "HTTPS"
        assert loaded.distractors == ["FTP", "SMTP", "Telnet"]

    def test_delete(self, tmp_db, sample_question):
        tmp_db.save(sample_question)
        tmp_db.delete(sample_question.id)
        assert tmp_db.get(sample_question.id) is None

    def test_count(self, populated_db):
        db, cert, qs = populated_db
        assert db.count() == 3
        assert db.count(status="approved") == 1
        assert db.count(status="draft") == 1

    def test_search_text(self, populated_db):
        db, cert, _ = populated_db
        results = db.search(text="firewall")
        assert len(results) >= 1
        assert "firewall" in results[0].scenario.lower()

    def test_search_topic(self, populated_db):
        db, _, _ = populated_db
        results = db.search(topic="Security")
        assert len(results) == 1
        assert results[0].topic == "Security"

    def test_search_difficulty(self, populated_db):
        db, _, _ = populated_db
        results = db.search(difficulty="Hard")
        assert len(results) == 1

    def test_search_status(self, populated_db):
        db, _, _ = populated_db
        results = db.search(status="approved")
        assert len(results) == 1

    def test_search_certification(self, populated_db):
        db, cert, _ = populated_db
        results = db.search(certification_id=cert.id)
        assert len(results) == 3

    def test_search_sme(self, populated_db):
        db, _, _ = populated_db
        results = db.search(assigned_sme="John Doe")
        assert len(results) == 1

    def test_search_limit_offset(self, populated_db):
        db, _, _ = populated_db
        results = db.search(limit=2)
        assert len(results) == 2
        results2 = db.search(limit=2, offset=2)
        assert len(results2) == 1

    def test_get_topics(self, populated_db):
        db, _, _ = populated_db
        topics = db.get_topics()
        assert "Networking" in topics
        assert "Security" in topics
        assert "Web Development" in topics

    def test_get_smes(self, populated_db):
        db, _, _ = populated_db
        smes = db.get_smes()
        assert "John Doe" in smes

    def test_multi_select_roundtrip(self, tmp_db, sample_multi_question):
        tmp_db.save(sample_multi_question)
        loaded = tmp_db.get(sample_multi_question.id)
        assert loaded.question_type == "multi"
        assert loaded.keys == ["Jenkins", "GitHub Actions"]
        assert loaded.key == "Jenkins"

    def test_review_history_roundtrip(self, tmp_db, sample_question):
        sample_question.transition("sme_review", sme_name="Alice", comment="Submitting")
        tmp_db.save(sample_question)
        loaded = tmp_db.get(sample_question.id)
        assert len(loaded.review_history) == 1
        assert loaded.review_history[0]["sme_name"] == "Alice"

    def test_tags_roundtrip(self, tmp_db):
        q = Question(stem="Q?", key="A", distractors=["B", "C"],
                     tags=["qa:passed", "important"])
        tmp_db.save(q)
        loaded = tmp_db.get(q.id)
        assert "qa:passed" in loaded.tags
        assert "important" in loaded.tags

    def test_source_links_roundtrip(self, tmp_db):
        q = Question(
            stem="Q?", key="A", distractors=["B", "C"],
            source_type="docs",
            source_links=["https://docs.example.com/page1", "https://docs.example.com/page2"],
        )
        tmp_db.save(q)
        loaded = tmp_db.get(q.id)
        assert len(loaded.source_links) == 2

    def test_option_order_roundtrip(self, tmp_db):
        q = Question(
            stem="Q? (Choose three.)", question_type="multi",
            key="A", keys=["A", "C", "E"],
            distractors=["B", "D"],
            option_order=["A", "B", "C", "D", "E"],
        )
        tmp_db.save(q)
        loaded = tmp_db.get(q.id)
        assert loaded.option_order == ["A", "B", "C", "D", "E"]
        assert loaded.all_choices == ["A", "B", "C", "D", "E"]

    def test_option_order_empty_fallback(self, tmp_db):
        q = Question(stem="Q?", key="X", distractors=["Y", "Z"])
        tmp_db.save(q)
        loaded = tmp_db.get(q.id)
        assert loaded.option_order == []
        assert loaded.all_choices == ["X", "Y", "Z"]

    def test_update_question(self, tmp_db, sample_question):
        tmp_db.save(sample_question)
        sample_question.stem = "Updated stem? (Choose one.)"
        tmp_db.save(sample_question)
        loaded = tmp_db.get(sample_question.id)
        assert loaded.stem == "Updated stem? (Choose one.)"


# ── Certification CRUD ─────────────────────────────────


class TestCertificationCRUD:
    def test_save_and_get(self, tmp_db, sample_certification):
        saved = tmp_db.save_certification(sample_certification)
        loaded = tmp_db.get_certification(saved.id)
        assert loaded is not None
        assert loaded.name == "Test Certification 2026"

    def test_list_certifications(self, tmp_db):
        tmp_db.save_certification(Certification(name="Cert B"))
        tmp_db.save_certification(Certification(name="Cert A"))
        certs = tmp_db.list_certifications()
        assert len(certs) == 2
        assert certs[0].name == "Cert A"  # sorted by name

    def test_delete_certification(self, tmp_db, sample_certification):
        saved = tmp_db.save_certification(sample_certification)
        tmp_db.delete_certification(saved.id)
        assert tmp_db.get_certification(saved.id) is None

    def test_count_by_certification(self, populated_db):
        db, cert, _ = populated_db
        assert db.count_by_certification(cert.id) == 3


# ── Duplicate detection ────────────────────────────────


class TestDuplicateDetection:
    def test_exact_duplicate(self, populated_db):
        db, _, qs = populated_db
        assert db.has_similar_stem(qs[0].stem)

    def test_no_duplicate(self, populated_db):
        db, _, _ = populated_db
        assert not db.has_similar_stem("Completely unique unrelated question?")

    def test_fuzzy_duplicate(self, populated_db):
        db, _, _ = populated_db
        # Very similar to q1's stem — only minor word difference
        similar = "Which protocol is used for secure web traffic? (Choose one.)"
        assert db.has_similar_stem(similar, threshold=0.80)

    def test_find_similar_stems_scored(self, populated_db):
        db, _, qs = populated_db
        matches = db.find_similar_stems_scored(qs[0].stem)
        assert len(matches) >= 1
        assert matches[0][1] == 1.0  # exact match

    def test_empty_stem(self, populated_db):
        db, _, _ = populated_db
        assert not db.has_similar_stem("")
        assert not db.has_similar_stem("   ")


# ── SME helpers ────────────────────────────────────────


class TestSMEHelpers:
    def test_count_by_sme(self, populated_db):
        db, _, _ = populated_db
        assert db.count_by_sme("John Doe") == 1

    def test_reassign_sme(self, populated_db):
        db, _, _ = populated_db
        count = db.reassign_sme("John Doe", "Jane Smith")
        assert count == 1
        assert db.count_by_sme("John Doe") == 0
        assert db.count_by_sme("Jane Smith") == 1

    def test_reassign_certification(self, populated_db):
        db, cert, _ = populated_db
        new_cert = db.save_certification(Certification(name="New Cert"))
        count = db.reassign_certification(cert.id, new_cert.id)
        assert count == 3
        assert db.count_by_certification(new_cert.id) == 3
        assert db.count_by_certification(cert.id) == 0

    def test_bulk_update_status(self, populated_db):
        db, _, qs = populated_db
        ids = [qs[0].id, qs[2].id]
        db.bulk_update_status(ids, "retired")
        assert db.get(qs[0].id).status == "retired"
        assert db.get(qs[2].id).status == "retired"
