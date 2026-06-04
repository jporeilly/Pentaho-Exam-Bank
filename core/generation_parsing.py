"""JSON extraction and validation utilities for AI responses."""

import json
import re
from typing import Optional

from .question_bank import Question
from .pptx_reader import SlideInfo


def _extract_json_array(text: str) -> Optional[list]:
    """Extract a JSON array from AI response text, handling markdown fences."""
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)

    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def _extract_json_object(text: str) -> Optional[dict]:
    """Extract a JSON object from AI response text."""
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def validate_key_against_notes(question: Question, slide: SlideInfo) -> bool:
    """Check that the key_source_text actually appears in the slide's speaker notes.

    Uses fuzzy substring matching (case-insensitive, whitespace-normalized) to account
    for minor AI paraphrasing while still enforcing traceability.
    Returns True if the key source text is found in the notes (or body text if no notes).
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
