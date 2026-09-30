"""Bringing new questions into the bank: one path for everything that adds them.

Generation's commit and import's commit did the same things in two loops -
check the question, stamp its certification, file it into the course, save it
- and disagreed on the first: import refused a question that could not be
graded, generation saved it. The editor refuses to save one (in the browser,
from rules pinned to the same fixture as ``core/validation.py``), and course
adoption lists one rather than adopting it, so generation was the one way
in for a question nobody can answer.

Now every write that adds questions goes through ``take_in``, with one policy:
a question that cannot be graded is refused, with the reason, and nothing
about it is saved or reserved.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .bank import ExamBankDB, Question
from .course_filing import Filed, file_into_course, taken_ids
from .validation import problems_with


@dataclass
class Intake:
    """What happened to each question offered."""

    saved: list[Question] = field(default_factory=list)
    filed: list[Filed] = field(default_factory=list)
    refused: list[dict] = field(default_factory=list)      # {"stem", "reason"}


def refusal(question: Question, reason: str) -> dict:
    return {"stem": (question.stem or "")[:80], "reason": reason}


def take_in(
    db: ExamBankDB,
    questions: list[Question],
    *,
    certification_id: str = "",
    courses_dir=None,
    topic: str = "",
    status: str = "",
    source_type_from_certification: bool = False,
) -> Intake:
    """Check, stamp, file and save each question; refuse what cannot be graded.

    ``certification_id``, ``topic`` and ``status`` override what each question
    carries when given. ``source_type_from_certification`` is import's rule: an
    imported question takes its certification's source type. One set of taken
    ids serves the whole batch, so two questions saved together cannot be
    given the same id.
    """
    out = Intake()
    taken = taken_ids(db, courses_dir)
    for question in questions:
        problems = problems_with(question)
        if problems:
            out.refused.append(refusal(question, "; ".join(p.message for p in problems)))
            continue

        if certification_id:
            question.certification_id = certification_id
        cert = db.get_certification(question.certification_id) if question.certification_id else None
        if cert and certification_id and source_type_from_certification:
            question.source_type = cert.source_type
        if topic:
            question.topic = topic
        if status:
            question.status = status

        filed = file_into_course(db, question, cert, courses_dir=courses_dir, taken=taken) if cert else None
        db.save(question)
        out.saved.append(question)
        if filed:
            out.filed.append(filed)
    return out
