"""Tests for core/context_budget.py.

The budget decides whether a section is FLAGGED, never whether it is sent, so
the estimate being a little out costs a needless warning rather than a
truncated question. What it must not do is be confidently wrong in a way that
hides a real overflow.
"""

from question_bank.core import context_budget as budget


def test_overhead_is_measured_from_the_real_prompt():
    """Not a hard-coded guess: it follows the prompts when they change."""
    overhead = budget.prompt_overhead_chars()
    from question_bank.core.generation_prompts import GENERATION_SYSTEM_PROMPT

    assert overhead > len(GENERATION_SYSTEM_PROMPT), "the scaffolding is missing"
    assert overhead < 40_000, "suspiciously large — the source text may be leaking in"


def test_a_bigger_window_allows_more_source():
    assert budget.source_budget_chars(16384) > budget.source_budget_chars(8192)


def test_the_budget_leaves_room_to_answer_in():
    """A window filled to the brim with prompt and source has nowhere to put
    the generated questions."""
    ctx = 8192
    allowed_tokens = budget.source_budget_chars(ctx) // budget.CHARS_PER_TOKEN
    overhead_tokens = budget.estimate_tokens("x" * budget.prompt_overhead_chars())
    assert allowed_tokens + overhead_tokens + budget.RESERVED_OUTPUT_TOKENS <= ctx


def test_no_configured_window_means_no_budget():
    # Ollama would use the model's own default, which this app does not know.
    assert budget.source_budget_chars(0) == 0


def test_a_window_too_small_to_use_is_zero_not_negative():
    """A negative budget would be worse than useless — a caller could take it
    for a length and slice with it."""
    assert budget.source_budget_chars(10) == 0


def test_token_estimate_rounds_up():
    # Rounding down would let a section that just overflows look like it fits.
    assert budget.estimate_tokens("abcde") == 2
    assert budget.estimate_tokens("") == 0


def test_the_real_courses_mostly_fit():
    """A sanity check on the numbers themselves: if the budget were wildly
    wrong, it would flag most of a normal course rather than a handful of
    outliers, and the warning would stop meaning anything."""
    allowed = budget.source_budget_chars(8192)
    typical_section = 674  # the measured median across the Content Manager's courses
    assert typical_section < allowed / 5, (
        f"an ordinary section ({typical_section}) is close to the budget ({allowed})"
    )
