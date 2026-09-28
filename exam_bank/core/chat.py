"""AI Chat: a conversation grounded in two sets of documentation.

**Two sources, cited apart.** The app's own documentation says how the Exam
Bank works; the Pentaho product documentation at docs.pentaho.com says how
the products work, which is what an author needs when writing or checking a
question. Each retrieved section is numbered — ``A1``, ``A2`` for this app,
``P1``, ``P2`` for Pentaho — and the model is told to cite by number, so every
claim in an answer can be traced to the page it came from and opened.

**Retrieval decides, as it did for the old docs pane.** If neither source
finds anything, the router says so and never calls the model: asked with
nothing to read, a model answers from what it knows about tools in general,
which reads exactly like an answer about this one — and an exam question
written on a guess teaches the guess.

Pure functions only: the router does the I/O, so what the model is shown can
be tested without one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .docs import DocSection, query_terms
from .mcp_client import SearchResult

SYSTEM = (
    "You are the assistant inside the Pentaho Exam Bank, a desktop app in which "
    "authors write, review and publish the certification exam questions for "
    "Pentaho's courses. You answer two kinds of question: how to use the Exam "
    "Bank, and how Pentaho's products work, which authors need when they write "
    "or check a question.\n\n"
    "Answer only from the sources given with the question. Exam Bank "
    "documentation is numbered [A1], [A2] and so on; Pentaho product "
    "documentation from docs.pentaho.com is numbered [P1], [P2] and so on. Cite "
    "the sources you use by their number in square brackets, after the sentence "
    "each one supports. If the sources do not answer the question, say so "
    "plainly and do not fill the gap from general knowledge: the person asking "
    "will act on the answer, and an exam question written on a guess teaches "
    "the guess. Where the Pentaho sources describe different product versions, "
    "say which version a fact applies to. Be concise, use a short list for "
    "steps, and when the question is about the Exam Bank, name the screen or "
    "button involved."
)

#: How much of each source the model is shown. The app's sections go in whole
#: up to a budget (they are short and written for this); Pentaho hits are cut,
#: because a docs.pentaho.com page runs to thousands of characters and ten of
#: them would crowd out the question on a small local model.
APP_BUDGET = 5000
APP_SECTIONS = 8
PENTAHO_HITS = 5
PENTAHO_CHARS = 700

#: Earlier turns sent with a question, so a follow-up ("and on Linux?") has
#: something to follow. Each is capped: a long pasted answer should not push
#: the sources out of a small context window.
HISTORY_TURNS = 8
TURN_CHARS = 2000

#: A question with fewer meaningful words than this is searched together with
#: the question before it. "What about the draw?" retrieves nothing useful on
#: its own; with the previous question it retrieves what the author means.
SHORT_QUESTION_TERMS = 3


@dataclass(frozen=True)
class Source:
    id: str          # "A1" / "P1": what the model cites
    kind: str        # "app" | "pentaho"
    title: str       # the page
    heading: str     # the section within it; "" for a Pentaho page
    text: str        # what the model is shown
    slug: str = ""   # app pages: where Documentation opens
    anchor: str = ""
    url: str = ""    # Pentaho pages: where the browser opens

    @property
    def snippet(self) -> str:
        flat = re.sub(r"\s+", " ", self.text).strip()
        return flat if len(flat) <= 240 else flat[:240].rsplit(" ", 1)[0] + "…"

    def to_json(self, cited: set[str]) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "heading": self.heading,
            "slug": self.slug,
            "anchor": self.anchor,
            "url": self.url,
            "snippet": self.snippet,
            "cited": self.id in cited,
        }


def retrieval_query(history: list[dict], question: str) -> str:
    """What to search for: the question, or with a short follow-up, the
    previous question too."""
    if len(query_terms(question)) >= SHORT_QUESTION_TERMS:
        return question
    previous = next(
        (m["content"] for m in reversed(history) if m.get("role") == "user"), ""
    )
    return f"{previous} {question}".strip() if previous else question


def app_sources(sections: list[DocSection]) -> list[Source]:
    return [
        Source(
            id=f"A{i}",
            kind="app",
            title=s.document,
            heading=s.heading if s.heading != s.document else "",
            text=s.text,
            slug=s.slug,
            anchor=s.anchor,
        )
        for i, s in enumerate(sections, start=1)
    ]


def pentaho_sources(hits: list[SearchResult]) -> list[Source]:
    out = []
    for i, h in enumerate(hits, start=1):
        text = h.content if len(h.content) <= PENTAHO_CHARS else (
            h.content[:PENTAHO_CHARS].rsplit(" ", 1)[0] + " …"
        )
        out.append(Source(id=f"P{i}", kind="pentaho", title=h.title or h.link,
                          heading="", text=text, url=h.link))
    return out


def _source_block(s: Source) -> str:
    if s.kind == "app":
        where = f"{s.title} › {s.heading}" if s.heading else s.title
        return f"[{s.id}] Exam Bank documentation — {where}\n{s.text}"
    return f"[{s.id}] Pentaho documentation — {s.title} ({s.url})\n{s.text}"


def build_messages(
    history: list[dict], question: str, sources: list[Source]
) -> list[dict]:
    """The conversation as the model receives it.

    Earlier turns go as they were said, without their sources: re-sending every
    past turn's documentation would fill the context with pages the current
    question is not about. The current question carries its own.
    """
    turns = [
        {"role": m["role"], "content": m["content"][:TURN_CHARS]}
        for m in history[-HISTORY_TURNS:]
        if m.get("role") in ("user", "assistant") and m.get("content", "").strip()
    ]
    block = "\n\n".join(_source_block(s) for s in sources)
    turns.append({
        "role": "user",
        "content": (
            "Sources for this question:\n\n"
            f"{block}\n\n"
            f"Question: {question}"
        ),
    })
    return turns


def cited_ids(answer: str) -> set[str]:
    """The source numbers an answer actually cites: [A1], [P2], [A1, P3]."""
    ids: set[str] = set()
    for group in re.findall(r"\[([AP]\d+(?:\s*[,;]\s*[AP]\d+)*)\]", answer):
        ids.update(re.findall(r"[AP]\d+", group))
    return ids
