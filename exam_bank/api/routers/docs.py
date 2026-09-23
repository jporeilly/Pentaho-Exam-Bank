"""The app's own documentation: browse it, search it, ask about it.

The asking is the part worth being careful about. A model asked "how do I
publish back to a course?" will answer *something* whether or not it was given
anything to read — it knows what apps like this generally do, and a confident
invention about a tool somebody is about to use is worse than no answer.

So retrieval decides. If nothing in the documentation matches the question,
this says so and never calls the model. If something does, the answer comes
back with the sections it was built from, because an answer about your own app
is only worth anything if you can check what it read.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ...core import docs as docs_core
from ...core.providers import ProviderError, active_provider, generate, model_for
from ...utils.config import config

router = APIRouter(tags=["docs"])

SYSTEM = (
    "You answer questions about the Pentaho Exam Bank, a desktop app for "
    "writing and managing certification exam questions. Answer only from the "
    "documentation you are given. If it does not cover the question, say so "
    "plainly rather than guessing — the person asking is about to act on your "
    "answer. Be concise and practical, and name the part of the app involved."
)


def _section_json(section: docs_core.DocSection) -> dict[str, Any]:
    return {
        "document": section.document,
        "heading": section.heading,
        "snippet": section.snippet,
        "score": section.score,
    }


@router.get("/api/docs")
def list_documents() -> list[dict[str, Any]]:
    """Every document, with its sections in order, for browsing."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for section in docs_core.load_sections():
        grouped.setdefault(section.document, []).append({
            "heading": section.heading,
            "text": section.text,
        })
    return [
        {"document": title, "sections": grouped[title]}
        for title, _ in docs_core.DOCUMENTS
        if title in grouped
    ]


@router.get("/api/docs/search")
def search_documents(
    q: str = "", limit: int = Query(8, ge=1, le=50)
) -> dict[str, Any]:
    """Sections matching a query, best first. No model involved."""
    sections = docs_core.load_sections()
    results = docs_core.search(q, sections, limit=limit)
    return {
        "query": q,
        "sectionsSearched": len(sections),
        "results": [_section_json(s) for s in results],
    }


class AskRequest(BaseModel):
    question: str


@router.post("/api/docs/ask")
def ask(body: AskRequest) -> dict[str, Any]:
    """Answer a question from the documentation, or say it is not covered."""
    question = body.question.strip()
    if not question:
        raise HTTPException(400, "Ask a question.")

    sections = docs_core.load_sections()
    if not sections:
        raise HTTPException(
            409,
            "No documentation was found to answer from. The guide and README "
            "should sit beside the app.",
        )

    found = docs_core.context_for(question, sections)
    if not found:
        # Deliberately not a model call. Asked with no documentation, the
        # model answers from what it knows about apps of this kind, which
        # reads exactly like an answer about this one.
        return {
            "answered": False,
            "answer": (
                "Nothing in the documentation covers that. Try different words, "
                "or search the guide directly — the answer is not being guessed "
                "at from outside it."
            ),
            "sources": [],
        }

    prompt = (
        "--- Documentation ---\n"
        f"{docs_core.as_prompt(found)}\n"
        "--- End documentation ---\n\n"
        f"Question: {question}"
    )

    try:
        answer = generate(
            prompt,
            system=SYSTEM,
            base_url=config.ollama_url,
            num_ctx=int(getattr(config, "ollama_num_ctx", 0) or 0),
        )
    except ProviderError as e:
        # The provider's own message names the thing to fix — an absent key, a
        # model that was never pulled — so it is passed through rather than
        # replaced with something generic.
        raise HTTPException(503, str(e)) from e

    return {
        "answered": True,
        "answer": answer.strip(),
        # What the answer was built from, so it can be checked.
        "sources": [_section_json(s) for s in found],
        "provider": active_provider(),
        "model": model_for(active_provider()),
    }
