"""The app's own documentation, split into sections and searchable.

Two jobs. One is search: an author types a word and gets the parts of the
guide that discuss it. The other is retrieval for the model — the same search,
feeding what it finds to a question.

**Tokenising properly is most of the quality here.** The previous matcher
split on whitespace, so a word kept whatever punctuation or markdown was
attached to it: in this repo's own guide "certification" appears 88 times as
text but only 34 times as a bare whitespace token, because the rest are
``certification.``, ``**certification**``, ``(certification)``. Two thirds of
the occurrences were invisible to the search.

**And stop words decided the ranking.** Scoring by raw overlap with every word
of the question meant "How do I publish back to a course?" was ranked mostly
on *do*, *a*, *to* and *I* — the top hit was a section about two independent
checks, which contains those words and nothing about publishing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..utils.config import PROJECT_ROOT

#: The documents, in the order they are offered. Titles are what an author
#: sees, so they are written here rather than derived from a filename.
DOCUMENTS = (
    ("How-To Guide", "HOW_TO_GUIDE.md"),
    ("README", "README.md"),
    ("Changelog", "CHANGELOG.md"),
)

#: Words too common to say anything about which section is relevant. Kept
#: deliberately short: this is for ranking, not for understanding, and a long
#: list starts discarding terms that matter in a technical document ("all",
#: "new" and "set" all appear in real queries here).
STOP_WORDS = frozenset("""
a an and are as at be but by can do does for from get got how i if in into is
it its me my of on or our so than that the their them then there these they
this to us was we what when where which who why will with you your
""".split())

#: A heading match says more about relevance than a body match, so it counts
#: for more. Not by much — a section whose body discusses a term ten times is
#: genuinely relevant too.
HEADING_WEIGHT = 3


@dataclass(frozen=True)
class DocSection:
    """One ``##``-level chunk of a document."""

    document: str
    heading: str
    text: str
    score: int = 0

    @property
    def snippet(self) -> str:
        """Enough to recognise the section by, cut at a word boundary."""
        if len(self.text) <= 280:
            return self.text
        cut = self.text[:280].rsplit(" ", 1)[0]
        return f"{cut}…"


def tokens(text: str) -> list[str]:
    """Lower-cased words, with punctuation and markdown stripped off.

    ``[a-z0-9]+`` rather than ``split()``: the difference is every occurrence
    that happens to be followed by a full stop, wrapped in asterisks, or
    inside backticks — which in a markdown document is most of them.
    """
    return re.findall(r"[a-z0-9]+", text.lower())


def query_terms(query: str) -> list[str]:
    """The words in a query worth ranking on.

    Stop words are dropped, but only if something survives: a question made
    entirely of common words is better answered on those than on nothing.
    """
    found = tokens(query)
    meaningful = [t for t in found if t not in STOP_WORDS]
    return meaningful or found


def split_sections(document: str, text: str) -> list[DocSection]:
    """Split a markdown document on its headings.

    Anything before the first heading is kept under the document's own name
    rather than discarded — in a README that is the part explaining what the
    thing is, which is exactly what a newcomer searches for.
    """
    sections: list[DocSection] = []
    heading = document
    body: list[str] = []

    for line in text.splitlines():
        if re.match(r"^#{1,3}\s+\S", line):
            if "".join(body).strip():
                sections.append(DocSection(document, heading, "\n".join(body).strip()))
            heading = line.lstrip("# ").strip()
            body = []
        else:
            body.append(line)

    if "".join(body).strip():
        sections.append(DocSection(document, heading, "\n".join(body).strip()))
    return sections


def load_sections(root: Path | None = None) -> list[DocSection]:
    """Every section of every document that is present.

    A missing document is skipped rather than raising: the app is usable
    without its README, and the alternative is a docs pane that fails whole
    because one file was not shipped.
    """
    base = root or PROJECT_ROOT
    sections: list[DocSection] = []
    for title, filename in DOCUMENTS:
        path = base / filename
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        sections.extend(split_sections(title, text))
    return sections


def search(query: str, sections: list[DocSection], limit: int = 8) -> list[DocSection]:
    """Sections matching the query, best first.

    Scored on DISTINCT query terms rather than total hits, so a section that
    mentions one term twenty times does not outrank one that covers every term
    in the question.
    """
    terms = set(query_terms(query))
    if not terms:
        return []

    scored: list[DocSection] = []
    for section in sections:
        heading_terms = set(tokens(section.heading))
        body_terms = set(tokens(section.text))
        score = (
            HEADING_WEIGHT * len(terms & heading_terms)
            + len(terms & body_terms)
        )
        if score:
            scored.append(
                DocSection(section.document, section.heading, section.text, score)
            )

    scored.sort(key=lambda s: (-s.score, s.document, s.heading))
    return scored[:limit]


def context_for(
    query: str, sections: list[DocSection], *, budget: int = 6000
) -> list[DocSection]:
    """The sections to put in front of the model, within a character budget.

    Returns them rather than a formatted string so the caller can show the
    author which parts of the documentation the answer was built from. An
    answer about their own app is only worth anything if they can check what
    it read.
    """
    chosen: list[DocSection] = []
    used = 0
    for section in search(query, sections, limit=12):
        cost = len(section.heading) + len(section.text)
        if used + cost > budget and chosen:
            break
        chosen.append(section)
        used += cost
    return chosen


def as_prompt(sections: list[DocSection]) -> str:
    """The retrieved sections, formatted for a prompt."""
    return "\n\n".join(
        f"## {s.heading}  ({s.document})\n{s.text}" for s in sections
    )
