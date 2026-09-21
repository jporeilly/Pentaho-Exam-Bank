"""How a target number of questions is spread across a course's sections.

Asking for fewer questions than there are sections used to mean questions
about the course's OPENING: the remainder went to the first N sections and
everything after got nothing. On developer-ai-specialty that silently
excluded "Deploy & Run the Agent" and the whole Key Concepts Workshop — the
end of a course being, often, the part most worth examining.
"""

import pytest

from question_bank.core import question_generation as gen
from question_bank.core.source import SlideInfo


@pytest.fixture
def spread(monkeypatch):
    """Run the batch with the model stubbed out, and report how many questions
    each section was asked for."""
    asked: dict[int, int] = {}

    def fake_generate(slide, model, num_questions=2, **kwargs):
        asked[slide.index] = num_questions
        return []

    monkeypatch.setattr(gen, "generate_questions", fake_generate)

    def run(sections: int, total: int) -> list[int]:
        slides = [
            SlideInfo(index=i, speaker_notes=f"Prose for section {i}. " * 10)
            for i in range(sections)
        ]
        asked.clear()
        gen.generate_questions_batch(slides, model="test", target_total=total)
        return [asked.get(i, 0) for i in range(sections)]

    return run


def test_asking_for_one_per_section_covers_everything(spread):
    assert spread(10, 10) == [1] * 10


def test_the_total_is_honoured(spread):
    for sections, total in ((63, 20), (63, 36), (10, 7), (10, 25)):
        assert sum(spread(sections, total)) == total, (sections, total)


def test_the_end_of_a_course_is_not_skipped(spread):
    """The bug this fixes. 20 across 63 gave sections 20-62 nothing."""
    counts = spread(63, 20)
    assert sum(counts[:21]) < 20, "the opening should not take almost all of them"
    assert sum(counts[42:]) > 0, "the last third of the course got nothing"


def test_questions_land_across_the_whole_run(spread):
    counts = spread(63, 20)
    covered = [i for i, n in enumerate(counts) if n]
    assert covered[0] < 5, "nothing near the start"
    assert covered[-1] > 55, "nothing near the end"


def test_no_section_is_asked_twice_while_others_get_none(spread):
    """The remainder is dealt one per section, so with fewer questions than
    sections nothing gets two while a neighbour gets zero."""
    counts = spread(63, 20)
    assert max(counts) == 1


def test_more_questions_than_sections_stacks_evenly(spread):
    counts = spread(10, 25)
    assert sum(counts) == 25
    # Two each, with the five extra spread out rather than all at the front.
    assert min(counts) == 2 and max(counts) == 3
    assert counts[-1] > 0


def test_sections_with_no_prose_are_left_out(spread, monkeypatch):
    asked: dict[int, int] = {}

    def fake_generate(slide, model, num_questions=2, **kwargs):
        asked[slide.index] = num_questions
        return []

    monkeypatch.setattr(gen, "generate_questions", fake_generate)
    slides = [
        SlideInfo(index=0, speaker_notes="Real prose here. " * 10),
        SlideInfo(index=1, speaker_notes="   "),
        SlideInfo(index=2, speaker_notes="More real prose. " * 10),
    ]
    gen.generate_questions_batch(slides, model="test", target_total=2)
    assert 1 not in asked, "an empty section should not be asked for a question"
    assert sum(asked.values()) == 2
