"""The gate between a question and approval (1.18.0).

The owner: "Each AI rewrite should have all the checks that pass the question
through the process to approved, passing all the checks." A question goes to
approved only when every check is clean: the bank's own validator (it can be
graded), the house form of the scenario and the question, the explanation
rule, the writing standard - which includes the answers being complete and
none giving itself away - and the model's checking pass. Anything else holds
it for review, with the reasons on its review history.

Every check here has a rule the model was given (generation_prompts), so a
question written to the rules passes. Deterministic checks first, then the
model's: what a rule can settle is not a question to ask a model.
"""
from __future__ import annotations

from typing import Iterable, List, Tuple

from .explanation_style import explanation_notes
from .stem_text import form_notes
from .validation import problems_with
from .writing_style import style_notes

#: Who the review history says moved the question.
GATE_REVIEWER = "AI checks"

PASSED = ("Passed every check: it can be graded, the scenario and question keep "
          "their form, every answer is complete and none gives itself away, the "
          "explanation and the writing meet the standard, and the model's check "
          "found the answer, the explanation and the language sound.")

# The lifecycle allows draft -> sme_review -> approved, and approved, revised
# -> sme_review. Rejected and retired questions are left where they are.
_TO_APPROVED = {"draft": ["sme_review", "approved"], "sme_review": ["approved"],
                "revised": ["approved"]}
_TO_REVIEW = {"draft": ["sme_review"], "approved": ["sme_review"], "revised": ["sme_review"]}


def house_findings(question) -> List[Tuple[str, str]]:
    """Every deterministic check on a question, as (field, message)."""
    found = [(p.field, p.message) for p in problems_with(question)]
    found += form_notes(question.scenario or "", question.stem or "")
    found += [("explanation", m) for m in explanation_notes(question.explanation)]
    found += style_notes(question)
    return found


def unique(findings: Iterable[Tuple[str, str]]) -> List[Tuple[str, str]]:
    return list(dict.fromkeys((f, m) for f, m in findings))


def pass_gate(question, findings: Iterable[Tuple[str, str]], *, passed: str = PASSED,
              held: str = "Held for review by the AI checks:") -> str:
    """Move `question` to approved if `findings` is empty, else to review.

    Changes the question's status and review history only; the caller saves
    it. Returns "approved", "review", or the status it was left in."""
    found = unique(findings)
    if not found:
        for status in _TO_APPROVED.get(question.status, []):
            question.transition(status, sme_name=GATE_REVIEWER, comment=passed)
        return "approved" if question.status == "approved" else question.status
    reasons = "; ".join(m for _f, m in found[:6]) + (" ..." if len(found) > 6 else "")
    for status in _TO_REVIEW.get(question.status, []):
        question.transition(status, sme_name=GATE_REVIEWER, comment=f"{held} {reasons}")
    return "review" if question.status == "sme_review" else question.status
