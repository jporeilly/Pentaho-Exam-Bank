"""The course pages a question is about, for an AI operation to ground on.

Generation grounds a question on the lab it was written from. Once the
question is in the bank that lab is named by its citation (``source_file``)
and its module by its topic, so the same text can be found again:

1. the lab the citation names. Citations come in several shapes - the lab's
   title (``One Pipeline, Many Files``), a label and the title (``Lab 1 — Your
   First Win``), or the course, module and page an adopted question carries
   (``Pentaho BI Developer - CT Practitioner: Community Data Access — Creating
   a CDA (Parameters)``) - so each part is tried as a lab title;
2. else every lab the course's contents file under the question's module;
3. else nothing, and the caller says the answer was not grounded.

A question outside any course, or whose course is not on this machine, gets
nothing. The text is capped: it goes into one prompt beside the question.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .bank import Certification, Question
from .course_filing import course_map, course_slug
from .pcm_reader import load_pcm_course

#: About three thousand words: enough for a lab, small enough for any model.
MAX_CHARS = 12_000


@dataclass
class Grounding:
    """Course text to ground on, and what it is, for the author to see."""

    text: str = ""
    label: str = ""


def _citation_parts(citation: str) -> list[str]:
    """The pieces of a citation that might be a lab's title, most specific first."""
    c = (citation or "").strip()
    if ": " in c:                                   # "Course title: Module — Page"
        c = c.split(": ", 1)[1]
    parts = [p.strip() for p in c.split(" — ") if p.strip()]
    out = []
    for p in reversed(parts):
        out.append(p)
        bare = re.sub(r"\s*\([^)]*\)\s*$", "", p).strip()   # "Creating a CDA (Parameters)"
        if bare and bare != p:
            out.append(bare)
    return out


def grounding_for(question: Question, cert: Certification | None, courses_dir,
                  max_chars: int = MAX_CHARS) -> Grounding:
    """The course text the question is about, or an empty Grounding."""
    slug = course_slug(cert)
    if not slug or not courses_dir:
        return Grounding()
    cmap = course_map(courses_dir, slug)

    labs: list[str] = []
    label = ""
    for part in [question.source_file or ""] + _citation_parts(question.source_file or ""):
        lab = cmap.lab_for(part)
        if lab:
            labs, label = [lab], cmap.title_of_lab.get(lab, part)
            break
    if not labs and question.topic:
        labs = [lab for lab, module in cmap.module_of_lab.items() if module == question.topic]
        label = f"the {question.topic} module" if labs else ""
    if not labs:
        return Grounding()

    parts = []
    for lab in labs:
        for section in load_pcm_course(courses_dir, slug, lab_slug=lab):
            if section.speaker_notes.strip():
                parts.append(section.speaker_notes.strip())
    text = "\n\n".join(parts)[:max_chars]
    return Grounding(text, label) if text else Grounding()
