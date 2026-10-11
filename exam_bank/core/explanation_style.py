"""Does an explanation follow the house rule? Advice, never a block.

The rule (generation_prompts.EXPLANATION_RULES, since 1.14.0): an
explanation says why the correct answer is right, in one to three short
paragraphs, and leaves the wrong options alone. Until 1.14.0 it addressed
every option - "'X' - Correct: ... 'Y' - Incorrect: ..." - and the bank still
holds hundreds written that way, and a model asked for the new form can slip
back into the old one.

So the AI rewrite, the bulk rewrite and the AI explanation report these next
to their proposal, for the author to see before taking it. Deterministic on
purpose: whether a model followed its instructions is not a question to ask
another model.
"""

from __future__ import annotations

import re
from typing import List

from .inline_format import blocks

# "Correct:" / "Incorrect:" used as a verdict on an option: followed by a
# colon ("'X' - Incorrect: ...") or after a dash ("X - Correct."). Prose such
# as "the correct setting is" is neither.
_VERDICT = re.compile(r"(?i)(?:[-–—]\s*(?:in)?correct\b|\b(?:in)?correct\s*:)")

# "option B", "answer (c)", "choice D" - a letter means nothing once the
# options are shuffled. Single capital letters only, so "a choice" is not one.
_LETTER = re.compile(r"\b(?:[Oo]ption|[Aa]nswer|[Cc]hoice)\s*\(?([A-F])\)?(?![\w'])")

# Past this with no paragraph break, it reads as a wall of text.
_LONG_PARAGRAPH = 700


def explanation_notes(text: str | None) -> List[str]:
    """What the author should look at in this explanation; [] when nothing.
    The prose only: a code block (1.16.0) is read as code, not as writing."""
    paragraphs = [b[1] for b in blocks(text) if b[0] == "p"]
    text = "\n\n".join(paragraphs)
    if not text:
        return []
    notes: List[str] = []
    if _VERDICT.search(text):
        notes.append(
            "It still labels options Correct/Incorrect. The explanation should "
            "say only why the correct answer is right."
        )
    if _LETTER.search(text):
        notes.append(
            "It refers to an answer by its letter. The options are shuffled, "
            "so name it by what it says."
        )
    if any(len(p) > _LONG_PARAGRAPH for p in paragraphs):
        notes.append(
            "One paragraph runs past 700 characters. Split it with a blank line "
            "so it reads easily."
        )
    padding = _PADDING.search(text)
    if padding:
        notes.append(
            f"A sentence opens \"{padding.group(0)}\": padding. State the fact directly, "
            "or drop the sentence if it only restates another."
        )
    return notes


# Padding (1.18.1). The gated re-run of 2026-10-11 approved rewrites that
# swapped reviewed sentences for "This ensures that...", "This approach
# allows...", "This design allows the process to continue..." - words that
# restate the paragraph before them, or bury a fact behind a formula. One
# opener per explanation is enough to send it back.
_PADDING = re.compile(
    r"(?:^|(?<=[.!?:]\s))This (?:ensures|approach|design|functionality|configuration|method|"
    r"process|allows|enables|makes it|helps|guarantees|setup|practice|mechanism|"
    r"centralization|modularity)\b",
    re.M,
)
