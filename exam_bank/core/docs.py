"""The app's own documentation: pages to read, sections to search.

Three jobs. The Documentation screen lists the pages by section and renders
one; search finds the parts that discuss a word; and AI Chat retrieves the same
sections to ground an answer, citing each by page and heading so the author can
open exactly what the model read.

**The pages are files, not a manifest.** The root documents (README, INSTALL,
the How-To Guide hub, CHANGELOG, VERSION) plus every ``docs/<folder>/*.md`` in
a known folder. A page's title is its first ``# `` line; the folder is its
section; the order inside a folder is the filename's, which is why the files
carry a number. Adding a page is adding a file. Anything else under ``docs/``
(the Bloom review notes, the port audit) is working material for developers
and is not served.

**Heading ids are decided here, once.** GitHub's rule — lower-case, drop
punctuation, spaces to hyphens, ``-1``, ``-2`` for repeats — so a link written
as ``README.md#what-it-connects-to`` works both on GitHub and in the app. The
interface does not re-derive them: it matches each rendered heading to this
list by its source line. Two implementations of one slug rule would disagree
about the first heading with an ampersand in it.

**Tokenising properly is most of the search quality.** The first matcher
split on whitespace, so a word kept whatever punctuation or markdown was
attached to it: in this repo's own guide "certification" appeared 88 times as
text but only 34 times as a bare whitespace token, because the rest were
``certification.``, ``**certification**``, ``(certification)``.

**And stop words decided the ranking.** Scoring by raw overlap with every word
of the question meant "How do I publish back to a course?" was ranked mostly
on *do*, *a*, *to* and *I*.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from pathlib import Path

from ..utils.config import PROJECT_ROOT

#: The root documents: file, title in the navigation, section. The titles are
#: written here rather than taken from the file, because each file's own
#: ``# `` line is written for someone reading it on GitHub ("Pentaho Exam Bank
#: — How-To Guide") and is too long for a sidebar.
ROOT_DOCS = (
    ("README.md", "README", "Start here"),
    ("INSTALL.md", "Install & Setup", "Start here"),
    ("HOW_TO_GUIDE.md", "How-To Guide", "Start here"),
    ("CHANGELOG.md", "Changelog", "Project"),
    ("VERSION.md", "Version", "Project"),
)

#: ``docs/<folder>`` -> the section it appears under. A folder not listed here
#: is not served.
FOLDERS = (
    ("guides", "Using the Exam Bank"),
    ("writing", "Writing questions"),
    ("ai", "AI"),
    ("admin", "Administration"),
    ("reference", "Reference"),
)

SECTION_ORDER = (
    "Start here",
    "Using the Exam Bank",
    "Writing questions",
    "AI",
    "Administration",
    "Reference",
    "Project",
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

_HEADING = re.compile(r"^(#{1,3})\s+(\S.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class Page:
    """One document, as the Documentation screen lists it."""

    slug: str       # repo-relative path without ".md": "README", "docs/guides/02-courses"
    path: str       # repo-relative, forward slashes
    title: str
    section: str
    text: str       # the markdown, less its own leading "# " title line

    @property
    def words(self) -> int:
        return len(self.text.split())

    @property
    def summary(self) -> str:
        """The first line of prose, for a tooltip or a search result."""
        for line in self.text.splitlines():
            s = line.strip()
            # Headings, tables, quotes, fences and list items are not prose. A
            # list marker needs its space: "**Bold** lead" is a paragraph.
            if not s or re.match(r"^([#|>`]|[-*+]\s|\d+\.\s)", s):
                continue
            s = re.sub(r"[*_`]", "", re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s))
            return s if len(s) <= 180 else s[:180].rsplit(" ", 1)[0] + "…"
        return ""


@dataclass(frozen=True)
class DocSection:
    """One heading's worth of a page: what search ranks and chat cites."""

    document: str   # the page's title
    heading: str
    text: str
    score: int = 0
    slug: str = ""
    anchor: str = ""  # the heading's id on the page; "" is the top of the page

    @property
    def snippet(self) -> str:
        """Enough to recognise the section by, cut at a word boundary."""
        if len(self.text) <= 280:
            return self.text
        cut = self.text[:280].rsplit(" ", 1)[0]
        return f"{cut}…"


# --- pages -------------------------------------------------------------------


def _strip_title(text: str) -> tuple[str | None, str]:
    """The page's own ``# `` title, and the text without it.

    Removed because the screen shows the title above the page; left in, it
    would be printed twice.
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        m = re.match(r"^#\s+(\S.*?)\s*$", line)
        if m:
            return m.group(1), "\n".join(lines[i + 1:]).lstrip("\n")
        break
    return None, text


def _fallback_title(path: Path) -> str:
    stem = re.sub(r"^\d+[-_]", "", path.stem)
    return stem.replace("-", " ").replace("_", " ").strip().capitalize()


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").replace("\r\n", "\n")
    except (OSError, UnicodeDecodeError):
        return None


def list_pages(root: Path | None = None) -> list[Page]:
    """Every page that is present, in the order the screen lists them.

    A missing file is skipped rather than raising: the app is usable without
    its CHANGELOG, and the alternative is a Documentation screen that fails
    whole because one file was not shipped.
    """
    base = root or PROJECT_ROOT
    pages: list[Page] = []

    def root_doc(filename: str, title: str, section: str) -> None:
        text = _read(base / filename)
        if text is None:
            return
        _, body = _strip_title(text)
        pages.append(Page(filename[:-3], filename, title, section, body))

    for filename, title, section in ROOT_DOCS:
        if section == "Start here":
            root_doc(filename, title, section)

    for folder, section in FOLDERS:
        directory = base / "docs" / folder
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            text = _read(path)
            if text is None:
                continue
            title, body = _strip_title(text)
            rel = f"docs/{folder}/{path.name}"
            pages.append(Page(rel[:-3], rel, title or _fallback_title(path), section, body))

    for filename, title, section in ROOT_DOCS:
        if section != "Start here":
            root_doc(filename, title, section)
    return pages


def find_page(slug: str, root: Path | None = None) -> Page | None:
    """The page with exactly this slug, or None.

    A lookup among the listed pages, never a path built from the request, so
    nothing outside the documentation can be read through it.
    """
    return next((p for p in list_pages(root) if p.slug == slug), None)


def slugify_heading(text: str) -> str:
    """GitHub's anchor for a heading: what ``page.md#this`` refers to."""
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)   # a link keeps its words
    t = re.sub(r"[`*]", "", t).strip().lower()
    t = re.sub(r"[^\w\- ]", "", t)
    return t.replace(" ", "-")


def headings(text: str) -> list[dict]:
    """The page's ``#``–``###`` headings with their ids and 1-based lines.

    Fence-aware: a ``# comment`` inside a code block is not a heading.
    """
    out: list[dict] = []
    seen: dict[str, int] = {}
    fenced = False
    for number, line in enumerate(text.splitlines(), start=1):
        if _FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        m = _HEADING.match(line)
        if not m:
            continue
        label = m.group(2)
        base = slugify_heading(label)
        n = seen.get(base, 0)
        seen[base] = n + 1
        out.append({
            "level": len(m.group(1)),
            "text": re.sub(r"[`*]", "", label),
            "id": base if n == 0 else f"{base}-{n}",
            "line": number,
        })
    return out


# --- sections, search and retrieval -------------------------------------------


def tokens(text: str) -> list[str]:
    """Lower-cased words, with punctuation and markdown stripped off.

    ``[a-z0-9]+`` rather than ``split()``: the difference is every occurrence
    that happens to be followed by a full stop, wrapped in asterisks, or
    inside backticks — which in a markdown document is most of them.
    """
    return re.findall(r"[a-z0-9]+", text.lower())


def stem(word: str) -> str:
    """A word's crude root, so "publish", "publishing" and "published" match.

    Deliberately small: a plural or an ``-ing`` / ``-ed``, then a final ``e``,
    which is what makes "course"/"courses" and "approve"/"approved" meet. Found
    necessary on the real docs: "publish push courses repo" ranked a Changelog
    list above the page called *Publishing to a Course*, which shared none of
    those four words exactly. ``-us`` / ``-is`` / ``-ss`` keep their ``s``
    (status, analysis, class).
    """
    if len(word) <= 3 or word.isdigit():
        return word
    if word.endswith("ses") and word[:-2].endswith(("us", "ss")):
        word = word[:-2]                       # statuses -> status, classes -> class
    elif word.endswith("ing") and len(word) >= 6:
        word = word[:-3]
    elif word.endswith("ed") and len(word) >= 5:
        word = word[:-2]
    elif word.endswith("s") and not word.endswith(("ss", "us", "is")):
        word = word[:-1]
    if word.endswith("e") and len(word) > 3:
        word = word[:-1]
    return word


def query_terms(query: str) -> list[str]:
    """The words in a query worth ranking on.

    Stop words are dropped, but only if something survives: a question made
    entirely of common words is better answered on those than on nothing.
    """
    found = tokens(query)
    meaningful = [t for t in found if t not in STOP_WORDS]
    return meaningful or found


def split_sections(document: str, text: str, slug: str = "") -> list[DocSection]:
    """Split a page on its headings.

    Anything before the first heading is kept under the page's own name
    rather than discarded — in a README that is the part explaining what the
    thing is, which is exactly what a newcomer searches for.
    """
    by_line = {h["line"]: h for h in headings(text)}
    sections: list[DocSection] = []
    heading, anchor = document, ""
    body: list[str] = []

    def close() -> None:
        if "".join(body).strip():
            sections.append(DocSection(document, heading, "\n".join(body).strip(),
                                       slug=slug, anchor=anchor))

    for number, line in enumerate(text.splitlines(), start=1):
        h = by_line.get(number)
        if h:
            close()
            heading, anchor, body = h["text"], h["id"], []
        else:
            body.append(line)
    close()
    return sections


def load_sections(root: Path | None = None) -> list[DocSection]:
    """Every section of every page that is present."""
    out: list[DocSection] = []
    for page in list_pages(root):
        out.extend(split_sections(page.title, page.text, page.slug))
    return out


def search(query: str, sections: list[DocSection], limit: int = 8) -> list[DocSection]:
    """Sections matching the query, best first.

    Scored on DISTINCT query terms rather than total hits, so a section that
    mentions one term twenty times does not outrank one that covers every term
    in the question.
    """
    terms = {stem(t) for t in query_terms(query)}
    if not terms:
        return []

    scored: list[DocSection] = []
    for section in sections:
        heading_terms = {stem(t) for t in tokens(section.heading)}
        body_terms = {stem(t) for t in tokens(section.text)}
        score = (
            HEADING_WEIGHT * len(terms & heading_terms)
            + len(terms & body_terms)
        )
        if score:
            scored.append(dataclasses.replace(section, score=score))

    scored.sort(key=lambda s: (-s.score, s.document, s.heading))
    return scored[:limit]


def context_for(
    query: str, sections: list[DocSection], *, budget: int = 6000, limit: int = 12
) -> list[DocSection]:
    """The sections to put in front of the model, within a character budget.

    Returns them rather than a formatted string so the caller can show the
    author which parts of the documentation the answer was built from. An
    answer about their own app is only worth anything if they can check what
    it read.
    """
    chosen: list[DocSection] = []
    used = 0
    for section in search(query, sections, limit=limit):
        cost = len(section.heading) + len(section.text)
        if used + cost > budget and chosen:
            break
        chosen.append(section)
        used += cost
    return chosen
