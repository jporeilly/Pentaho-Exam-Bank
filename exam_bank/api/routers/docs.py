"""The app's own documentation, for the Documentation screen.

List the pages by section, search their sections, and return one page to
render. No model is involved here: asking about the documentation is AI
Chat's job (``routers/chat.py``), which retrieves from the same sections.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ...core import docs as docs_core

router = APIRouter(tags=["docs"])


def _item(page: docs_core.Page) -> dict[str, Any]:
    return {
        "slug": page.slug,
        "title": page.title,
        "section": page.section,
        "summary": page.summary,
        "words": page.words,
        "path": page.path,
    }


@router.get("/api/docs")
def list_documents() -> dict[str, Any]:
    """Every page, grouped by section in the navigation's order."""
    pages = docs_core.list_pages()
    sections = [
        {"name": name, "items": [_item(p) for p in pages if p.section == name]}
        for name in docs_core.SECTION_ORDER
    ]
    return {"sections": [s for s in sections if s["items"]], "count": len(pages)}


@router.get("/api/docs/page")
def read_page(slug: str) -> dict[str, Any]:
    """One page's markdown, with its headings' ids for the table of contents
    and for links that point into it."""
    page = docs_core.find_page(slug)
    if page is None:
        raise HTTPException(404, f"There is no documentation page '{slug}'.")
    return {
        **_item(page),
        "content": page.text,
        "headings": docs_core.headings(page.text),
    }


@router.get("/api/docs/search")
def search_documents(
    q: str = "", limit: int = Query(20, ge=1, le=50)
) -> dict[str, Any]:
    """Sections matching a query, best first, each with the page and heading
    it opens at."""
    pages = {p.slug: p for p in docs_core.list_pages()}
    sections = [
        s for p in pages.values()
        for s in docs_core.split_sections(p.title, p.text, p.slug)
    ]
    results = docs_core.search(q, sections, limit=limit)
    return {
        "query": q,
        "sectionsSearched": len(sections),
        "results": [
            {
                "slug": s.slug,
                "page": s.document,
                "section": pages[s.slug].section,
                "heading": s.heading,
                "anchor": s.anchor,
                "snippet": s.snippet,
                "score": s.score,
            }
            for s in results
        ],
    }
