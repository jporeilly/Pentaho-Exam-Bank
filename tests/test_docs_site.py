"""The real documentation: every page titled, every link and anchor resolving.

The other docs tests use small trees of their own. This one reads the pages
the app actually ships, because the way documentation rots is a link to a page
that was renamed or a heading that was reworded - and the How-To Guide was
split into 17 pages in 1.7.0, which moved every cross-reference it had.
"""

import re
from pathlib import Path

import pytest

from exam_bank.core import docs
from exam_bank.utils.config import PROJECT_ROOT

PAGES = docs.list_pages(PROJECT_ROOT)
BY_PATH = {p.path: p for p in PAGES}
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")


def _links(page):
    text = re.sub(r"```.*?```", "", page.text, flags=re.S)  # not inside code blocks
    return [m.group(1) for m in LINK.finditer(text)]


def _resolve(page, href):
    """(target path, anchor) for a link inside the repo, or None for an
    external or mail link."""
    if re.match(r"^[a-z][a-z0-9+.-]*:", href, re.I):
        return None
    path, _, anchor = href.partition("#")
    if not path:
        return page.path, anchor
    target = (Path(page.path).parent / path).as_posix()
    parts = []
    for part in target.split("/"):
        if part == "..":
            parts.pop()
        elif part not in ("", "."):
            parts.append(part)
    return "/".join(parts), anchor


def test_the_guide_and_its_pages_are_all_there():
    sections = {p.section for p in PAGES}

    assert {"Start here", "Using the Exam Bank", "Writing questions", "AI",
            "Administration", "Reference", "Project"} <= sections
    assert len(PAGES) >= 20


@pytest.mark.parametrize("page", [p for p in PAGES if p.path.startswith("docs/")], ids=lambda p: p.path)
def test_every_docs_page_starts_with_its_title(page):
    """The title comes from the file's own "# " line; without one, the page
    would be named after its filename."""
    raw = (PROJECT_ROOT / page.path).read_text(encoding="utf-8")
    assert raw.lstrip().startswith("# ")


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.path)
def test_every_link_to_another_page_resolves(page):
    broken = []
    for href in _links(page):
        resolved = _resolve(page, href)
        if resolved is None:
            continue
        target, anchor = resolved
        if target.endswith(".md"):
            if target not in BY_PATH:
                broken.append(href)
                continue
            if anchor and anchor not in {h["id"] for h in docs.headings(BY_PATH[target].text)}:
                broken.append(href)
        elif not (PROJECT_ROOT / target).exists():
            broken.append(href)
    assert not broken, f"{page.path}: {broken}"


def test_the_how_to_guide_links_every_page():
    """The hub is the way into the guide on GitHub, where there is no sidebar."""
    hub = BY_PATH["HOW_TO_GUIDE.md"]
    linked = {_resolve(hub, h)[0] for h in _links(hub) if _resolve(hub, h)}
    pages = {p.path for p in PAGES if p.path.startswith("docs/")}

    assert pages - linked == set()
