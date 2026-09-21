"""The unit of source material a question is generated from.

Every generation source — a Content Manager course's `guide.md` sections, the
Pentaho docs over MCP, a PowerPoint deck — is read into a list of these, so the
generator, the prompt builder and the key validator work the same way whatever
the material came from.

It lived in ``pptx_reader`` until 0.2.0, which meant importing the type dragged
in ``python-pptx`` and tied six modules that have nothing to do with slides to
the one that does. That is also why the fields are named for slides; they are
renamed once the PPTX reader is gone and the name is free to be honest.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class SlideInfo:
    """One section of source material.

    ``speaker_notes`` is the prose a question is grounded in and the text the
    key is validated against; ``title`` names the section for the question's
    topic. ``body_text`` is a secondary source used when there are no notes,
    and ``thumbnail_path`` is only ever set by the PPTX reader.
    """

    index: int  # 0-based position within the source
    speaker_notes: str
    title: Optional[str] = None
    body_text: Optional[str] = None
    thumbnail_path: Optional[Path] = None
