"""JSON extraction and validation utilities for AI responses."""

import json
import re
from typing import Optional

from .bank import Question
from .source import SlideInfo


# A model wraps its JSON in a ```json fence. Since 1.16.0 an explanation can
# hold a fenced code block of its own, so the reply has fences INSIDE the JSON
# too, and taking the text between the first two fences cut the JSON in half
# (2hr-m3-q10 failed every rewrite that way). So the outermost fence - first
# to last - is tried first, then the first pair, then the bare text, and the
# first that parses wins.
_OUTER_FENCE = re.compile(r"```(?:json)?[ \t]*\n?(.*)\n?```", re.DOTALL)
_FIRST_FENCE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)


def _parse_between(text: str, open_ch: str, close_ch: str):
    for candidate in (
        *(m.group(1) for m in (_OUTER_FENCE.search(text), _FIRST_FENCE.search(text)) if m),
        text,
    ):
        start, end = candidate.find(open_ch), candidate.rfind(close_ch)
        if start == -1 or end <= start:
            continue
        try:
            return json.loads(candidate[start:end + 1])
        except json.JSONDecodeError:
            continue
    return None


def _extract_json_array(text: str) -> Optional[list]:
    """Extract a JSON array from AI response text, handling markdown fences."""
    parsed = _parse_between(text, "[", "]")
    return parsed if isinstance(parsed, list) else None


def _extract_json_object(text: str) -> Optional[dict]:
    """Extract a JSON object from AI response text, handling markdown fences."""
    parsed = _parse_between(text, "{", "}")
    return parsed if isinstance(parsed, dict) else None


def validate_key_against_notes(question: Question, slide: SlideInfo) -> bool:
    """Check that the key_source_text actually appears in the slide's speaker notes.

    Uses fuzzy substring matching (case-insensitive, whitespace-normalized) to account
    for minor AI paraphrasing while still enforcing traceability.
    Returns True if the key source text is found in the notes (or body text if no notes).

    **What a failure means changed.** ``key_source_text`` used to be the sentence
    containing the ANSWER, so a failure meant the model had invented one. It is
    now the passage showing the TOPIC is part of the course, so a failure means
    the question could not be anchored to the syllabus — it may be about
    something the course does not cover, or the model may have paraphrased too
    freely to match.

    Either way it is a flag for a reviewer, not a verdict. Nothing here can
    check whether the answer is TRUE: the question now draws on knowledge of
    the product rather than on the text, and no amount of string matching
    against a lab guide will catch a confident falsehood. That is a human's job.
    """
    source_text = question.key_source_text.strip()
    if not source_text:
        return False

    # Primary: check speaker notes
    notes = slide.speaker_notes.strip() if slide.speaker_notes else ""
    if notes:
        reference = notes
    elif slide.body_text:
        reference = slide.body_text
    else:
        return False

    # Normalize whitespace for comparison
    def normalize(s):
        return " ".join(s.lower().split())

    norm_ref = normalize(reference)
    norm_src = normalize(source_text)

    # Exact substring match
    if norm_src in norm_ref:
        return True

    # Fuzzy: check if most words from key_source_text appear in the reference
    src_words = set(norm_src.split())
    ref_words = set(norm_ref.split())
    if not src_words:
        return False
    overlap = len(src_words & ref_words) / len(src_words)
    return overlap >= 0.7  # 70% word overlap = close enough paraphrase
