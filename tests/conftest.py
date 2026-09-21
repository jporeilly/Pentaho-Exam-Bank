"""Shared fixtures for Exam Bank tests."""

import tempfile
from pathlib import Path

import pytest

from exam_bank.core.bank import (
    Question, Certification, ExamBankDB, STATUSES, STATUS_TRANSITIONS,
)


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary ExamBankDB for testing."""
    db_path = tmp_path / "test.db"
    db = ExamBankDB(db_path)
    yield db
    db.close()


@pytest.fixture
def sample_question():
    """Return a minimal valid Question."""
    return Question(
        scenario="A network engineer is configuring a new firewall rule.",
        stem="Which protocol is used for secure web traffic? (Choose one.)",
        question_type="single",
        key="HTTPS",
        key_source_text="HTTPS is used for secure web communication.",
        distractors=["FTP", "SMTP", "Telnet"],
        explanation="HTTPS — Correct: it encrypts web traffic. FTP — Incorrect: for file transfer.",
        topic="Networking",
        difficulty="Medium",
        bloom_level="Remember",
        certification_id="cert-123",
        source_file="test.pptx",
        source_slides=[0],
        key_source_slide=0,
    )


@pytest.fixture
def sample_multi_question():
    """Return a valid multi-select Question."""
    return Question(
        scenario="A developer is choosing a CI/CD pipeline tool.",
        stem="Which two tools are commonly used for CI/CD? (Choose two.)",
        question_type="multi",
        key="Jenkins",
        keys=["Jenkins", "GitHub Actions"],
        key_source_text="Jenkins and GitHub Actions are popular CI/CD tools.",
        distractors=["Photoshop", "Excel", "Notepad"],
        explanation="Jenkins — Correct. GitHub Actions — Correct. Others are not CI/CD tools.",
        topic="DevOps",
        difficulty="Easy",
        bloom_level="Remember",
    )


@pytest.fixture
def sample_certification():
    """Return a sample Certification."""
    return Certification(
        name="Test Certification 2026",
        description="A test certification for unit tests",
        source_type="pptx",
    )


@pytest.fixture
def populated_db(tmp_db, sample_question, sample_certification):
    """A DB pre-populated with one certification and a few questions."""
    cert = tmp_db.save_certification(sample_certification)
    sample_question.certification_id = cert.id

    q1 = tmp_db.save(sample_question)

    q2 = Question(
        scenario="An admin is reviewing server logs.",
        stem="What does HTTP status code 404 indicate? (Choose one.)",
        question_type="single",
        key="Not Found",
        distractors=["Server Error", "Unauthorized", "OK"],
        topic="Web Development",
        difficulty="Easy",
        bloom_level="Remember",
        certification_id=cert.id,
        status="approved",
    )
    tmp_db.save(q2)

    q3 = Question(
        scenario="A security analyst is evaluating encryption standards.",
        stem="Which algorithm provides symmetric encryption? (Choose one.)",
        question_type="single",
        key="AES",
        distractors=["RSA", "DSA", "Diffie-Hellman"],
        topic="Security",
        difficulty="Hard",
        bloom_level="Analyze",
        certification_id=cert.id,
        status="sme_review",
        assigned_sme="John Doe",
    )
    tmp_db.save(q3)

    return tmp_db, cert, [q1, q2, q3]
