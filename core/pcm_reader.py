"""Read Pentaho Content Manager (PCM) course content as a generation source.

PCM courses live on disk as ``<courses_dir>/<slug>/`` with a ``course.json``
(title/id) at the root and one directory per lab, each holding a ``guide.md``
(the lab's markdown) and an optional ``manifest.json`` (title). This module turns
a course into the same ``SlideInfo`` list the PPTX/MCP sources produce, so the
existing generator can ground questions in the course content unchanged.

Each lab's ``guide.md`` is split on ``##`` headings into sections; every section
becomes one ``SlideInfo`` whose ``speaker_notes`` is the cleaned prose (PCM
rendering markup — tab widgets, HTML buttons, ``<dfn>`` tags, image/link syntax —
is stripped so the model grounds on plain text and ``key_source_text`` matches).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List

from .pptx_reader import SlideInfo


def _humanise(slug: str) -> str:
    """Turn a slug ("03-llm-integration") into a title ("Llm Integration")."""
    s = re.sub(r"^\d+[-_]*", "", slug)            # drop leading order prefix
    s = s.replace("-", " ").replace("_", " ").strip()
    return s.title() if s else slug


def list_pcm_courses(courses_dir) -> List[dict]:
    """List courses under ``courses_dir`` as ``[{"slug", "title"}]``.

    A course is any direct subdirectory containing a ``course.json``. Title
    comes from course.json ``title`` (then ``id``), else the humanised slug.
    Returns [] when the directory is missing/empty.
    """
    root = Path(courses_dir) if courses_dir else None
    if not root or not root.is_dir():
        return []
    out: List[dict] = []
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        cj = child / "course.json"
        if not cj.is_file():
            continue
        title = ""
        try:
            data = json.loads(cj.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                title = str(data.get("title") or data.get("id") or "").strip()
        except Exception:
            title = ""
        out.append({"slug": child.name, "title": title or _humanise(child.name)})
    return out


def clean_markdown(md: str) -> str:
    """Strip PCM rendering markup, leaving plain prose for LLM grounding."""
    if not md:
        return ""
    # Encoded tab-widget blobs (carry a big data-tabs attribute) — drop whole.
    md = re.sub(r'<div class="pcm-tabs-widget".*?</div>', "", md, flags=re.S)
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S)        # HTML comments
    md = re.sub(r"<dfn[^>]*>(.*?)</dfn>", r"\1", md, flags=re.S)  # unwrap glossary terms
    md = re.sub(r"<[^>]+>", "", md)                       # any remaining HTML tags
    md = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", md)     # images → alt text
    md = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", md)      # links → link text
    md = re.sub(r"^\s*:{3,}.*$", "", md, flags=re.M)      # ::: directive fences
    md = re.sub(r"\n{3,}", "\n\n", md)                    # collapse blank runs
    return md.strip()


def _split_sections(md: str):
    """Split markdown into (heading|None, body_text) on H2 (## ) headings.

    ### and deeper stay within their section. Text before the first H2 is a
    leading section with heading None.
    """
    sections = []
    cur_head = None
    cur: List[str] = []
    for ln in md.splitlines():
        m = re.match(r"^##(?!#)\s+(.+?)\s*$", ln)
        if m:
            if cur_head is not None or any(s.strip() for s in cur):
                sections.append((cur_head, "\n".join(cur)))
            cur_head = m.group(1).strip()
            cur = []
        else:
            cur.append(ln)
    if cur_head is not None or any(s.strip() for s in cur):
        sections.append((cur_head, "\n".join(cur)))
    return sections


def list_pcm_labs(courses_dir, slug: str) -> List[dict]:
    """List a course's labs as ``[{"slug","title"}]`` (dirs with a guide.md).

    Lets the caller scope generation to a single lab/module instead of the
    whole course. Returns [] when the course has no readable labs.
    """
    course_dir = Path(courses_dir) / slug if courses_dir else None
    if not course_dir or not course_dir.is_dir():
        return []
    out: List[dict] = []
    for lab_dir in sorted(course_dir.iterdir(), key=lambda p: p.name):
        if lab_dir.is_dir() and (lab_dir / "guide.md").is_file():
            out.append({"slug": lab_dir.name, "title": _lab_title(lab_dir)})
    return out


def _lab_title(lab_dir: Path) -> str:
    mf = lab_dir / "manifest.json"
    if mf.is_file():
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("title"):
                return str(data["title"]).strip()
        except Exception:
            pass
    return _humanise(lab_dir.name)


# Drop sections whose cleaned prose is too thin to write a question from.
_MIN_SECTION_CHARS = 60


def load_pcm_course(courses_dir, slug: str, lab_slug: str = "") -> List[SlideInfo]:
    """Read a PCM course into a list of SlideInfo (one per H2 section).

    Lab directories (any subdir of the course containing ``guide.md``) are read
    in sorted order; each guide is split into sections and cleaned. Sections
    with too little prose are skipped. When ``lab_slug`` is given, only that one
    lab/module is read (the rest of the course is skipped).
    """
    course_dir = Path(courses_dir) / slug
    slides: List[SlideInfo] = []
    if not course_dir.is_dir():
        return slides
    idx = 0
    for lab_dir in sorted(course_dir.iterdir(), key=lambda p: p.name):
        if not lab_dir.is_dir():
            continue
        if lab_slug and lab_dir.name != lab_slug:
            continue
        guide = lab_dir / "guide.md"
        if not guide.is_file():
            continue
        lab_title = _lab_title(lab_dir)
        try:
            raw = guide.read_text(encoding="utf-8")
        except Exception:
            continue
        for heading, body in _split_sections(raw):
            prose = clean_markdown(body)
            if len(prose) < _MIN_SECTION_CHARS:
                continue
            title = f"{lab_title} — {heading}" if heading else lab_title
            # Prepend the heading so the model sees the section topic in-context.
            notes = f"{heading}\n\n{prose}" if heading else prose
            slides.append(SlideInfo(index=idx, speaker_notes=notes, title=title))
            idx += 1
    return slides
