"""Question search, read, edit, lifecycle and delete."""

from __future__ import annotations

import copy
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ...core import providers, question_refinement
from ...core.bank import BLOOM_LEVELS, DIFFICULTIES, STATUS_LABELS, STATUS_TRANSITIONS, STATUSES, ExamBankDB
from ...core.course_filing import refile_id
from ...core.explanation_style import explanation_notes
from ...core.generation_prompts import (
    EXPLANATION_REWRITE_RULES,
    EXPLANATION_RULES,
    PROOFREAD_RULES,
    REWRITE_CHECK_RULES,
    SCENARIO_AND_STEM_RULES,
    WRITING_RULES,
)
from ...core.grounding import Grounding, grounding_for
from ...core.rewrite_checks import preservation_notes
from ...core.writing_style import flow_notes, style_notes, text_notes
from ...core.stem_text import form_notes
from .. import jobs
from ...core.validation import problems_with
from ...utils.config import config
from ..deps import courses_dir_if_any, get_db, question_json

router = APIRouter(tags=["questions"])

# Fields a client may change. Everything else about a question is either
# derived (the timestamps), structural (its certification), or part of the
# audit trail, and none of those are a PUT's business.
_EDITABLE = (
    "scenario", "stem", "question_type", "key", "keys", "key_source_text",
    "distractors", "option_order", "explanation", "topic", "tags",
    "difficulty", "bloom_level", "assigned_sme",
)


@router.get("/api/vocabulary")
def vocabulary() -> dict[str, Any]:
    """The bank's fixed lists, exactly as the server validates them.

    Every screen that offers a status, a difficulty or a Bloom level reads
    them from here (frontend/src/vocabulary.ts). Five screens used to type
    their own copies, and the Admin bulk delete's had drifted.
    """
    return {
        "statuses": list(STATUSES),
        "statusLabels": dict(STATUS_LABELS),
        "difficulties": list(DIFFICULTIES),
        "bloomLevels": list(BLOOM_LEVELS),
    }


@router.get("/api/house-style")
def house_style() -> dict[str, Any]:
    """The template every question is written to, as the prompts carry it.

    Generation, the AI rewrite (single and bulk), the AI fix and the AI
    explanation all read these same constants (core/generation_prompts.py),
    so a new question and a rewritten one come out alike. The app shows them
    from here rather than keeping a copy that could drift from what the
    model is actually told.
    """
    return {
        "sections": [
            {"title": "Scenario and question", "rules": SCENARIO_AND_STEM_RULES},
            {"title": "Explanation", "rules": EXPLANATION_RULES},
            {"title": "Quotes, names and punctuation", "rules": WRITING_RULES},
            {"title": "When a question is rewritten",
             "rules": PROOFREAD_RULES + "\n" + EXPLANATION_REWRITE_RULES},
            {"title": "What every rewrite is checked for", "rules": REWRITE_CHECK_RULES},
        ]
    }


@router.get("/api/lifecycle")
def lifecycle() -> dict[str, Any]:
    """The question lifecycle, as the model defines it.

    Served rather than restated in the front end. The transitions are
    enforced by `Question.transition`, which raises on an illegal move;
    a UI holding its own copy of the table would offer buttons the model
    refuses, and the user would meet a 409 they cannot do anything with.
    One table, asked at run time.
    """
    return {"statuses": list(STATUSES), "transitions": {
        status: list(moves) for status, moves in STATUS_TRANSITIONS.items()
    }}


@router.get("/api/topics")
def list_topics(certification_id: str = "", db: ExamBankDB = Depends(get_db)) -> list[dict[str, Any]]:
    """Every topic with questions, in the order the course teaches them -
    for the Bank's topic filter. One certification's when given."""
    counts = db.get_topic_counts(certification_id)
    return [{"topic": topic, "questionCount": n} for topic, n in counts.items()]


@router.get("/api/questions")
def list_questions(
    db: ExamBankDB = Depends(get_db),
    text: str = "",
    topic: str = "",
    difficulty: str = "",
    bloom_level: str = "",
    status: str = "",
    certification_id: str = "",
    assigned_sme: str = "",
    tags: str = "",
    question_id: str = Query("", alias="id"),
    exact_topic: str = "",
    sort: str = "course",
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """A page of questions plus the unpaged total, so a client can show
    "showing 50 of 398" without asking twice."""
    filters = dict(
        text=text, topic=topic, difficulty=difficulty, bloom_level=bloom_level,
        status=status, certification_id=certification_id,
        assigned_sme=assigned_sme, tags=tags, id=question_id, exact_topic=exact_topic,
    )
    # sort is deliberately NOT in filters: search_count shares that dict
    # and takes no ordering - a count does not have one.
    items = db.search(limit=limit, offset=offset, sort=sort, **filters)
    return {
        "items": [question_json(q) for q in items],
        "total": db.search_count(**filters),
        "limit": limit,
        "offset": offset,
    }


@router.get("/api/questions/{question_id}")
def get_question(question_id: str, db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    question = db.get(question_id)
    if not question:
        raise HTTPException(404, f"No question '{question_id}'")
    return question_json(question)


@router.put("/api/questions/{question_id}")
def update_question(
    question_id: str, body: dict[str, Any], db: ExamBankDB = Depends(get_db)
) -> dict[str, Any]:
    """Update the editable fields, recording each change in the question's
    version history so an edit can be traced afterwards."""
    question = db.get(question_id)
    if not question:
        raise HTTPException(404, f"No question '{question_id}'")

    editor = str(body.get("editor") or "").strip()
    _apply_edits(db, question, body, editor)
    return question_json(question)


def _apply_edits(db: ExamBankDB, question, changes: dict[str, Any], editor: str) -> None:
    """Apply the editable fields in `changes` to `question` and save it,
    recording each change in its version history. Raises HTTPException(400)
    for a question that could not be graded, saving nothing.

    Shared by the editor's save and the bulk rewrite's accept, so an accepted
    rewrite is recorded, validated and saved exactly as a hand edit is.
    """
    topic_before = question.topic
    for field in _EDITABLE:
        if field not in changes:
            continue
        old = getattr(question, field)
        new = changes[field]
        if old == new:
            continue
        question.record_edit(field, old, new, editor=editor)
        setattr(question, field, new)

    if not (question.stem or "").strip():
        raise HTTPException(400, "A question needs a stem")
    # The same rules the editor applies before it lets Save be pressed
    # (pinned to one fixture with core/validation.py), so this refuses only
    # what the editor would never send - a script, or a client out of step.
    problems = problems_with(question)
    if problems:
        raise HTTPException(400, "This question could not be graded: "
                                 + "; ".join(p.message for p in problems))
    # A course question's id names its module (<course>-m<module>-q<n>), so
    # moving it to another module gives it that module's next number - the
    # row is renamed and the change recorded, and the reply carries the new
    # id for the editor to follow.
    if question.topic != topic_before and question.certification_id:
        refile_id(db, question, db.get_certification(question.certification_id),
                  courses_dir=courses_dir_if_any(), editor=editor)
    db.save(question)


class StatusChange(BaseModel):
    status: str
    sme_name: str = ""
    comment: str = ""


@router.post("/api/questions/{question_id}/status")
def change_status(
    question_id: str, body: StatusChange, db: ExamBankDB = Depends(get_db)
) -> dict[str, Any]:
    """Move a question through its lifecycle.

    The transition is validated by the model, which knows which moves are
    legal from where; an illegal one is the caller's error, not a 500.
    """
    question = db.get(question_id)
    if not question:
        raise HTTPException(404, f"No question '{question_id}'")
    if body.status not in STATUSES:
        raise HTTPException(400, f"Unknown status '{body.status}'")
    try:
        question.transition(body.status, sme_name=body.sme_name, comment=body.comment)
    except ValueError as e:
        raise HTTPException(409, str(e))
    db.save(question)
    return question_json(question)


@router.delete("/api/questions/{question_id}")
def delete_question(question_id: str, db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    if not db.get(question_id):
        raise HTTPException(404, f"No question '{question_id}'")
    db.delete(question_id)
    return {"ok": True, "id": question_id}


# --- AI assistance -------------------------------------------------------
#
# Every endpoint here is READ-ONLY. They return a proposal or a list of findings
# and never touch the bank: accepting a rewrite is an ordinary save the author
# makes, through the editor they were already looking at.
#
# That is the same look-then-act shape as publishing and importing, and here
# it is not a nicety. A model that rewrites a question in place would be the
# one contributor to the bank whose work nobody reviewed.


class AiRewriteRequest(BaseModel):
    """What to ask for. The default instruction is the module's own."""

    instruction: str = ""


def _ai_model() -> str:
    """The model to use, or a 409 naming what is missing.

    Resolved per request rather than held: the provider and model are
    settings the author can change while the app is running, and a cached
    handle would keep answering with the old one.
    """
    model = providers.model_for(providers.active_provider())
    if not model:
        raise HTTPException(
            409,
            "No AI model is configured. Pick a provider and model in "
            "Settings first.",
        )
    return model


@router.post("/api/questions/{question_id}/ai/rewrite")
def ai_rewrite_question(
    question_id: str, body: AiRewriteRequest, db: ExamBankDB = Depends(get_db)
) -> dict[str, Any]:
    """Propose a rewritten question. Writes nothing."""
    question = db.get(question_id)
    if question is None:
        raise HTTPException(404, f"No question '{question_id}'.")

    kwargs = {"question": question, "model": _ai_model(), "base_url": config.ollama_url}
    if body.instruction.strip():
        kwargs["instruction"] = body.instruction.strip()

    proposed = question_refinement.improve_question(**kwargs)
    if proposed is None:
        raise HTTPException(
            502,
            "The model did not return a usable question. Try again, or a "
            "larger model.",
        )
    checks = question_refinement.check_rewrite(
        question, proposed, model=kwargs["model"], base_url=kwargs["base_url"],
        source_text=_grounding(db, question).text)
    return _proposal_json(question, proposed, checks)


def _proposal_json(question, proposed, checks=()) -> dict[str, Any]:
    """A rewrite as the editor and the bulk review show it.

    The problems are reported against the PROPOSAL, because the author is
    about to decide whether to take it and an improvement that cannot be
    graded is not an improvement.
    """
    return {
        "proposed": question_json(proposed),
        "problems": [
            {"field": p.field, "message": p.message} for p in problems_with(proposed)
        ],
        # Where the proposal breaks the house form - a question in the
        # scenario, statements in the stem, an explanation that still judges
        # every option. Advice, not a block: a model can ignore the rule it
        # was given, and the author should see that before taking it.
        "notes": [
            {"field": f, "message": m}
            for f, m in form_notes(proposed.scenario, proposed.stem)
        ] + [
            {"field": "explanation", "message": m}
            for m in explanation_notes(proposed.explanation)
        ] + [
            # The writing standard: what tidy could not settle on its own.
            {"field": f, "message": m} for f, m in style_notes(proposed)
        ] + [
            # What the rewrite took out or put in, word for word (1.17.0).
            {"field": f, "message": m} for f, m in preservation_notes(question, proposed)
        ] + [
            # The second pass: correct answer, correct explanation, nothing
            # lost or added, clean language (check_rewrite, 1.17.0).
            {"field": f, "message": m} for f, m in checks
        ],
        "unchanged": question_json(proposed) == question_json(question),
    }


# --- The bulk rewrite ------------------------------------------------------
#
# The AI rewrite, over every question the Bank is showing. Still a proposal:
# it runs as a job (minutes, one model call per question), the review list
# grows as it goes, and nothing reaches the bank until the author accepts a
# question - one at a time or all at once. Accepting is the editor's own save
# (_apply_edits), recorded in each question's history as the bulk rewrite's.

# A ceiling, not a target: the bank holds under 500 today.
BULK_REWRITE_LIMIT = 1000
BULK_EDITOR = "AI rewrite (bulk)"


class AiRewriteAllRequest(BaseModel):
    """The Bank's filters, so the rewrite covers exactly the list on screen."""

    text: str = ""
    topic: str = ""
    difficulty: str = ""
    bloom_level: str = ""
    status: str = ""
    certification_id: str = ""
    id: str = ""
    exact_topic: str = ""
    sort: str = "course"
    instruction: str = ""


@router.post("/api/questions/ai/rewrite-all", status_code=202)
def ai_rewrite_all(body: AiRewriteAllRequest, db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    """Start rewriting every question the filters match. Writes nothing."""
    model = _ai_model()
    filters = dict(
        text=body.text, topic=body.topic, difficulty=body.difficulty,
        bloom_level=body.bloom_level, status=body.status,
        certification_id=body.certification_id, id=body.id,
        exact_topic=body.exact_topic,
    )
    total = db.search_count(**filters)
    if total == 0:
        raise HTTPException(409, "No questions match those filters, so there is nothing to rewrite.")
    if total > BULK_REWRITE_LIMIT:
        raise HTTPException(409, f"{total} questions match. Narrow the filters to "
                                 f"{BULK_REWRITE_LIMIT} or fewer - one certification at a time, say.")
    questions = db.search(limit=BULK_REWRITE_LIMIT, offset=0, sort=body.sort, **filters)
    instruction = body.instruction.strip() or question_refinement.REWRITE_INSTRUCTION
    base_url = config.ollama_url
    # The check reads the course pages. The certifications are looked up now:
    # the job runs after this request, and its database handle, have ended.
    certs = {cid: db.get_certification(cid) for cid in {q.certification_id for q in questions} if cid}
    courses_dir = courses_dir_if_any()

    def work(job: jobs.Job) -> list[dict[str, Any]]:
        # Appended to the job's own list as each one finishes, so a client
        # polling the job sees the review list grow and can start accepting.
        out = job.result
        for i, question in enumerate(questions):
            job.progress(i, len(questions), f"Rewriting {question.id} ({i + 1} of {len(questions)})")
            entry: dict[str, Any] = {
                "id": question.id,
                # What the rewrite started from. Accepting refuses a question
                # that no longer matches it: someone edited it meanwhile.
                "original": question_json(question),
                "proposed": None, "problems": [], "notes": [],
                "unchanged": False, "error": "", "accepted": False,
            }
            try:
                proposed = question_refinement.improve_question(
                    question=question, model=model, base_url=base_url, instruction=instruction)
                if proposed is None:
                    # One more go. A local model now and then returns JSON it
                    # cannot close (one in seven in the 2026-10-10 trial), and
                    # a second call usually comes back clean.
                    job.progress(i, len(questions), f"Rewriting {question.id} again")
                    proposed = question_refinement.improve_question(
                        question=question, model=model, base_url=base_url, instruction=instruction)
            except jobs.JobCancelled:
                raise
            except Exception as e:  # one failed call must not end the run
                entry["error"] = f"The model call failed: {e}"
            else:
                if proposed is None:
                    entry["error"] = "The model did not return a usable question."
                else:
                    job.progress(i, len(questions), f"Checking {question.id} ({i + 1} of {len(questions)})")
                    source = grounding_for(question, certs.get(question.certification_id), courses_dir).text
                    checks = question_refinement.check_rewrite(
                        question, proposed, model=model, base_url=base_url, source_text=source)
                    entry.update(_proposal_json(question, proposed, checks))
            out.append(entry)
        job.progress(len(questions), len(questions), f"Rewrote {len(questions)}")
        return out

    job = jobs.start("rewrite", work, requested=len(questions))
    return {"jobId": job.id, "total": len(questions), "status": job.status}


class AcceptRewritesRequest(BaseModel):
    question_ids: list[str] = Field(default_factory=list)


@router.post("/api/questions/ai/rewrite-jobs/{job_id}/accept")
def accept_rewrites(
    job_id: str, body: AcceptRewritesRequest, db: ExamBankDB = Depends(get_db)
) -> dict[str, Any]:
    """Save the named proposals of a bulk rewrite. Allowed while the job is
    still running: a finished entry is final, and the author may be reading
    the first while the last are being written."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"No job '{job_id}'")
    if job.kind != "rewrite":
        raise HTTPException(409, "That job is not a rewrite.")
    if not body.question_ids:
        raise HTTPException(400, "Name the questions to accept.")

    entries = {e["id"]: e for e in list(job.result)}
    saved: list[str] = []
    skipped: list[dict[str, str]] = []

    def skip(qid: str, reason: str) -> None:
        skipped.append({"id": qid, "reason": reason})

    for qid in dict.fromkeys(body.question_ids):
        entry = entries.get(qid)
        if entry is None:
            skip(qid, "It has not been rewritten (yet).")
            continue
        if entry.get("accepted"):
            skip(qid, "It was already accepted.")
            continue
        if entry.get("error") or not entry.get("proposed"):
            skip(qid, entry.get("error") or "There is no proposal for it.")
            continue
        if entry.get("unchanged"):
            skip(qid, "The rewrite changed nothing.")
            continue
        if entry.get("problems"):
            skip(qid, "The rewrite could not be graded: "
                      + "; ".join(p["message"] for p in entry["problems"]))
            continue
        current = db.get(qid)
        if current is None:
            skip(qid, "It has been deleted.")
            continue
        if question_json(current) != entry["original"]:
            skip(qid, "It has changed since it was rewritten. Open it and rewrite it again.")
            continue
        changes = {f: entry["proposed"][f] for f in _EDITABLE if f in entry["proposed"]}
        try:
            _apply_edits(db, current, changes, BULK_EDITOR)
        except HTTPException as e:
            skip(qid, str(e.detail))
            continue
        entry["accepted"] = True
        saved.append(qid)
    return {"saved": saved, "skipped": skipped}


@router.post("/api/questions/{question_id}/ai/review")
def ai_review_question(
    question_id: str, db: ExamBankDB = Depends(get_db)
) -> dict[str, Any]:
    """Check the answers, and proofread. Writes nothing."""
    question = db.get(question_id)
    if question is None:
        raise HTTPException(404, f"No question '{question_id}'.")

    model = _ai_model()
    answers = question_refinement.review_answers(
        question, model, base_url=config.ollama_url
    )
    prose = question_refinement.qa_check_question(
        question, model, base_url=config.ollama_url
    )

    # Kept apart in the response. "The key is also true of option C" and "a
    # comma is missing" are not the same kind of news, and a flat list buries
    # the first under the second.
    return {
        "answers": answers,
        "prose": prose,
        # What the bank's own deterministic validator says, which owes
        # nothing to a model and is worth showing beside its opinion.
        "gradeable": [
            {"field": p.field, "message": p.message} for p in problems_with(question)
        ],
        "form": [
            {"field": f, "message": m} for f, m in form_notes(question.scenario, question.stem)
        ],
    }


def _grounding(db: ExamBankDB, question) -> Grounding:
    """The course pages the question was written from, if it is a course's."""
    cert = db.get_certification(question.certification_id) if question.certification_id else None
    return grounding_for(question, cert, courses_dir_if_any())


def _options_of(question) -> list[str]:
    keys = question.keys if question.question_type == "multi" and question.keys else [question.key]
    return [o for o in dict.fromkeys([*keys, *question.distractors]) if o]


@router.post("/api/questions/{question_id}/ai/explanation")
def ai_write_explanation(question_id: str, db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    """Propose the explanation, grounded on the course's pages. Writes nothing."""
    question = db.get(question_id)
    if question is None:
        raise HTTPException(404, f"No question '{question_id}'.")
    if not _options_of(question) or not (question.key or question.keys):
        raise HTTPException(409, "Mark the correct answer first: an explanation says why it is right.")

    grounding = _grounding(db, question)
    text = question_refinement.generate_explanation(
        question, _ai_model(), base_url=config.ollama_url, source_text=grounding.text)
    if not text:
        raise HTTPException(502, "The model did not return an explanation. Try again, or a larger model.")
    return {
        "explanation": text,
        # What it was grounded on, so the author knows how far to trust it.
        "groundedOn": grounding.label,
        # Where it breaks the house rule (correct answer only, paragraphs).
        # Until 1.14.0 this listed the options the text never named, when
        # the rule was to name every one.
        "notes": explanation_notes(text) + text_notes(text) + flow_notes(text),
    }


@router.post("/api/questions/{question_id}/ai/answer")
def ai_answer_key(question_id: str, db: ExamBankDB = Depends(get_db)) -> dict[str, Any]:
    """Propose which options are correct, grounded on the course's pages. Writes nothing."""
    question = db.get(question_id)
    if question is None:
        raise HTTPException(404, f"No question '{question_id}'.")

    grounding = _grounding(db, question)
    found = question_refinement.ai_assign_keys(
        question, _ai_model(), base_url=config.ollama_url, source_text=grounding.text)
    if found is None:
        raise HTTPException(
            502,
            "The model did not return a usable answer - none, or not the number of "
            "correct answers the question asks for. Try again, or a larger model.",
        )

    proposed = copy.deepcopy(question)
    keys = found["keys"]
    proposed.key = keys[0]
    proposed.keys = keys if len(keys) > 1 else []
    proposed.question_type = "multi" if len(keys) > 1 else "single"
    proposed.distractors = found["distractors"]
    if found["keySourceText"]:
        proposed.key_source_text = found["keySourceText"]
    # Taking the proposal is the author checking the answer.
    proposed.tags = [t for t in proposed.tags if t != "key-unverified"]
    current = set(question.keys if question.question_type == "multi" and question.keys else [question.key])
    return {
        "proposed": question_json(proposed),
        "changed": set(keys) != current,
        "analysis": found["analysis"],
        "groundedOn": grounding.label,
    }
