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


class TestBalanceAcrossTopics:
    """Sections are not evenly distributed between a course's labs.

    On developer-ai-specialty one lab is 21 sections and twelve others are a
    single section each. Spreading questions evenly over SECTIONS therefore
    gave that one workshop four questions and twelve labs none — two thirds
    of the syllabus unexamined. A topic is a topic whether it took one page
    to explain or twenty.
    """

    def lopsided(self, sizes: dict[str, int]) -> list[SlideInfo]:
        """A course whose labs are wildly different sizes."""
        out, index = [], 0
        for lab, n in sizes.items():
            for _ in range(n):
                out.append(SlideInfo(index=index, group=lab, title=f"{lab} bit {index}",
                                     speaker_notes=f"Prose about {lab}. " * 10))
                index += 1
        return out

    def counts_by_lab(self, slides, total) -> dict[str, int]:
        eligible = list(range(len(slides)))
        per_section = gen._distribute(slides, eligible, total)
        out: dict[str, int] = {}
        for i, n in per_section.items():
            if n:
                out[slides[i].group] = out.get(slides[i].group, 0) + n
        return out

    SIZES = {"Huge": 21, "Big": 9, "Medium": 6, "One": 1, "Two": 1, "Three": 1, "Four": 1}

    def test_a_big_lab_no_longer_takes_the_exam(self):
        by_lab = self.counts_by_lab(self.lopsided(self.SIZES), 7)
        assert by_lab.get("Huge", 0) == 1, f"the 21-section lab took {by_lab}"

    def test_every_lab_is_covered_when_there_is_room(self):
        by_lab = self.counts_by_lab(self.lopsided(self.SIZES), 7)
        assert len(by_lab) == 7, f"only {len(by_lab)} of 7 labs covered: {by_lab}"

    def test_single_section_labs_are_not_squeezed_out(self):
        by_lab = self.counts_by_lab(self.lopsided(self.SIZES), 7)
        for small in ("One", "Two", "Three", "Four"):
            assert by_lab.get(small, 0) == 1, f"{small} got nothing: {by_lab}"

    def test_the_total_is_still_exact(self):
        for total in (3, 7, 14, 40):
            by_lab = self.counts_by_lab(self.lopsided(self.SIZES), total)
            assert sum(by_lab.values()) == total, (total, by_lab)

    def test_fewer_questions_than_labs_still_spreads_them(self):
        by_lab = self.counts_by_lab(self.lopsided(self.SIZES), 3)
        assert len(by_lab) == 3 and max(by_lab.values()) == 1

    def test_more_questions_than_labs_stacks_evenly(self):
        by_lab = self.counts_by_lab(self.lopsided(self.SIZES), 21)
        assert min(by_lab.values()) == 3 and max(by_lab.values()) == 3

    def test_sections_with_no_topic_fall_back_to_a_flat_spread(self):
        """A PPTX or a docs search has no labs, so there is nothing to
        balance over and the old behaviour is correct."""
        slides = [SlideInfo(index=i, speaker_notes="Prose. " * 10) for i in range(10)]
        per_section = gen._distribute(slides, list(range(10)), 4)
        assert sum(per_section.values()) == 4
        chosen = [i for i, n in per_section.items() if n]
        assert chosen[0] < 3 and chosen[-1] > 6, "not spread across the run"
