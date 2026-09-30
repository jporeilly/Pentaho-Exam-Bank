"""Checking imported questions against docs.pentaho.com.

A file of questions from somewhere else - a partner's spreadsheet, an old
export - arrives with answers nobody here has checked. Before it is imported,
each question can be looked up in Pentaho's documentation through the same
GitBook MCP connection AI Chat uses (Settings > Pentaho documentation), and
the preview says, question by question, whether the docs back its answer.

How a question is checked: the docs are searched with the question and its
correct answer; then, for EACH correct answer, the share of its meaningful
words (not "the", "of", "a" ...) that appear in what came back. The question
counts as **supported** when every correct answer reaches the threshold in
Settings (Quality > Docs check threshold, 0.7 by default); an answer found
word for word counts in full. Otherwise it is **not found**: the docs may say
it differently, or not at all - a prompt to look, not a verdict. A search
that fails is reported as such, never as "not found".

It changes nothing: the result is shown in the preview, and the author
decides what to import.

This replaces ``question_importer.validate_question_against_docs``, which
searched a list of MCP servers nothing configured, scored every word
including "the", and wrote its match onto the question it was checking.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from ..utils.config import config
from . import mcp_client
from .bank import Question
from .docs import STOP_WORDS, tokens

#: Searches at once. GitBook answers in under a second; four keeps a file of
#: fifty questions to a few seconds without leaning on someone else's server.
WORKERS = 4
TIMEOUT = 15.0
HITS = 6


def _words(text: str) -> set[str]:
    return {t for t in tokens(text) if t not in STOP_WORDS and len(t) > 1}


def check(question: Question, url: str = "", threshold: float | None = None,
          timeout: float = TIMEOUT) -> dict:
    """``{status, detail, answers: [{answer, score}], sources: [{title, link}]}``.

    ``status`` is ``supported``, ``not-found`` or ``error``.
    """
    url = url or config.docs_mcp_url
    threshold = config.validation_threshold if threshold is None else threshold
    answers = [a for a in question.correct_answers if (a or "").strip()]
    if not answers:
        return {"status": "error", "detail": "Nothing is marked correct, so there is nothing to check.",
                "answers": [], "sources": []}

    query = f"{question.stem.strip()[:200]} {answers[0].strip()[:120]}"
    try:
        hits = mcp_client.search(query, url, limit=HITS, timeout=timeout)
    except mcp_client.McpError as e:
        return {"status": "error", "detail": f"The docs could not be searched: {e}",
                "answers": [], "sources": []}
    if not hits:
        return {"status": "not-found", "detail": "The docs search returned nothing for this question.",
                "answers": [{"answer": a, "score": 0.0} for a in answers], "sources": []}

    texts = [f"{h.title} {h.content}" for h in hits]
    corpus_words = set().union(*(_words(t) for t in texts))
    corpus_flat = " ".join(" ".join(t.lower().split()) for t in texts)

    scored = []
    for a in answers:
        flat = " ".join(a.lower().split())
        if flat and flat in corpus_flat:
            scored.append({"answer": a, "score": 1.0})
            continue
        words = _words(a)
        score = len(words & corpus_words) / len(words) if words else 0.0
        scored.append({"answer": a, "score": round(score, 2)})

    # The pages that carry most of the answer's words, as where to look.
    answer_words = set().union(*(_words(a) for a in answers))
    ranked = sorted(zip(hits, texts), key=lambda ht: -len(_words(ht[1]) & answer_words))
    sources = [{"title": h.title, "link": h.link} for h, _ in ranked[:2]]

    supported = all(s["score"] >= threshold for s in scored)
    detail = "; ".join(f"{s['answer'][:60]}: {round(s['score'] * 100)}%" for s in scored)
    return {"status": "supported" if supported else "not-found",
            "detail": detail, "answers": scored, "sources": sources}


def check_many(questions: list[Question], url: str = "", threshold: float | None = None) -> list[dict]:
    """``check`` for each question, a few at a time, in the order given."""
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        return list(pool.map(lambda q: check(q, url, threshold), questions))
