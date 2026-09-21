"""How much source material actually fits in the model's context window.

A section longer than the window is not rejected — it is silently truncated,
and the questions come back thinner than the material deserved with nothing to
say why. So the budget is computed and reported, and an author can see which
sections exceed it before spending a generation run on them.

The window has to cover four things, not just the source text:

  the system prompt  +  the prompt scaffolding  +  the source section
                     +  room for the model to WRITE its answer

The first two are measured from the real prompt builder rather than guessed,
so they follow the prompts when those change. The last is reserved: a window
with no room left to answer in produces nothing.
"""

from __future__ import annotations

from .generation_prompts import GENERATION_SYSTEM_PROMPT, build_prompt
from .source import SlideInfo

# English averages roughly four characters per token. This is an estimate and
# is treated as one: it decides whether a section is FLAGGED, never whether it
# is sent, so being a little out costs a needless warning rather than a
# truncated question.
CHARS_PER_TOKEN = 4

# Room for the model to answer in — which is NOT the size of the answer.
#
# A question with its scenario, options and per-choice explanation is only a
# few hundred tokens. But a reasoning model spends thousands more thinking
# first, and Ollama counts those against the same window while returning none
# of them: one measured call used 4,091 tokens to produce a 330-token answer.
#
# Reserving for the answer alone is what made generation flaky. A section
# whose prompt came to 8,769 of a 12,288 window left 3,519 for thinking, the
# model ran past it, and Ollama returned `done_reason: "length"` with an EMPTY
# response after two minutes of work. Reserving for the thinking too costs
# some source text and buys a reply that actually arrives.
RESERVED_OUTPUT_TOKENS = 4500


def estimate_tokens(text: str) -> int:
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


def prompt_overhead_chars() -> int:
    """The system prompt plus the scaffolding `build_prompt` wraps around the
    source. Measured against an empty section, so what is left is exactly the
    fixed cost."""
    empty = SlideInfo(index=0, speaker_notes="", title="")
    return len(GENERATION_SYSTEM_PROMPT) + len(build_prompt(empty))


def source_budget_chars(num_ctx: int) -> int:
    """Characters of source material that fit a context of `num_ctx` tokens.

    Returns 0 when the overhead and the reserved output already fill the
    window — which is the honest answer, and better than a negative number
    that a caller might use as a length.
    """
    if num_ctx <= 0:
        # No configured window: Ollama uses the model's own default and we
        # have no number to reason about, so nothing is flagged.
        return 0
    available = num_ctx - RESERVED_OUTPUT_TOKENS - estimate_tokens("x" * prompt_overhead_chars())
    return max(0, available * CHARS_PER_TOKEN)
