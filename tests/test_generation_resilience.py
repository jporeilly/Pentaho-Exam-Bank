"""One bad section must not end a whole run.

A course is dozens of model calls over an hour or more. Letting a single one
end the run throws away everything already generated, and the usual cause is a
slow section timing out — the least interesting reason imaginable to lose an
hour's work. This is what happened on the first real run of
developer-ai-specialty: it died on section 2 of 63 and kept nothing.
"""

import pytest

from question_bank.core import question_generation as gen
from question_bank.core.question_bank import Question
from question_bank.core.source import SlideInfo


def sections(n: int) -> list[SlideInfo]:
    return [
        SlideInfo(index=i, speaker_notes=f"Prose for section {i}. " * 10,
                  title=f"Section {i}")
        for i in range(n)
    ]


def question(i: int) -> Question:
    return Question(id=f"q{i}", stem=f"Question from {i}?", key="right",
                    distractors=["wrong"])


@pytest.fixture
def run(monkeypatch):
    """Generate across sections, with chosen ones raising instead of answering."""

    def go(count: int, failing: set[int], total=None, error=TimeoutError("timed out")):
        def fake(slide, model, **kwargs):
            if slide.index in failing:
                raise error
            return [question(slide.index)]

        monkeypatch.setattr(gen, "generate_questions", fake)
        messages: list[str] = []
        result = gen.generate_questions_batch(
            sections(count), model="test", target_total=total or count,
            progress_callback=lambda c, t, m="": messages.append(m),
        )
        return result, messages

    return go


def test_a_failing_section_is_skipped_and_the_rest_survive(run):
    questions, _ = run(5, failing={1})
    assert len(questions) == 4
    assert "q1" not in [q.id for q in questions]


def test_the_run_continues_past_an_early_failure(run):
    """The real case: it died on section 2 of 63 and kept nothing."""
    questions, _ = run(20, failing={1})
    assert len(questions) == 19, "everything after the failure was lost"


def test_several_failures_are_all_survived(run):
    questions, _ = run(10, failing={0, 4, 9})
    assert len(questions) == 7


def test_every_section_failing_returns_nothing_rather_than_raising(run):
    questions, _ = run(4, failing={0, 1, 2, 3})
    assert questions == []


def test_the_skipped_sections_are_named(run):
    """A skipped section leaves a hole in the course's coverage. Counting them
    is not enough — the author needs to know which part is missing."""
    _, messages = run(5, failing={2})
    final = messages[-1]
    assert "1 section(s) skipped" in final
    assert "Section 2" in final


def test_a_clean_run_says_nothing_about_skipping(run):
    _, messages = run(4, failing=set())
    assert "skipped" not in messages[-1]


def test_the_reason_reaches_the_progress_message(run):
    _, messages = run(3, failing={1}, error=TimeoutError("timed out"))
    assert any("timed out" in m for m in messages)


def test_cancellation_still_stops_the_run(monkeypatch):
    """Skipping failures must not make a run unstoppable — cancelling is
    meant to end it, and arrives as an exception from the progress callback."""

    class JobCancelled(Exception):
        pass

    def fake(slide, model, **kwargs):
        return [question(slide.index)]

    monkeypatch.setattr(gen, "generate_questions", fake)

    calls = {"n": 0}

    def cancel_after_two(current, total, message=""):
        calls["n"] += 1
        if calls["n"] > 2:
            raise JobCancelled()

    with pytest.raises(JobCancelled):
        gen.generate_questions_batch(
            sections(10), model="test", target_total=10,
            progress_callback=cancel_after_two,
        )


class TestSectionsThatReturnNothing:
    """A section the model answered, but with nothing the parser could read.

    Different from a section that failed, and different again from one that
    was never asked — but until this was counted all three looked identical
    from outside. The first real run asked for 12 questions, produced 7, and
    reported "Done — 7 questions generated" as though 7 had been the plan.
    """

    @pytest.fixture
    def run_empty(self, monkeypatch):
        def go(count: int, empty_on: set[int]):
            def fake(slide, model, **kwargs):
                if slide.index in empty_on:
                    return []          # unparseable response, swallowed
                return [question(slide.index)]

            monkeypatch.setattr(gen, "generate_questions", fake)
            messages: list[str] = []
            result = gen.generate_questions_batch(
                sections(count), model="test", target_total=count,
                progress_callback=lambda c, t, m="": messages.append(m),
            )
            return result, messages

        return go

    def test_the_shortfall_is_reported(self, run_empty):
        _, messages = run_empty(5, empty_on={1, 3})
        assert "2 section(s) returned nothing usable" in messages[-1]

    def test_the_sections_are_named(self, run_empty):
        _, messages = run_empty(5, empty_on={3})
        assert "Section 3" in messages[-1]

    def test_a_full_run_says_nothing_about_it(self, run_empty):
        _, messages = run_empty(4, empty_on=set())
        assert "nothing usable" not in messages[-1]

    def test_the_questions_that_did_come_back_are_kept(self, run_empty):
        questions, _ = run_empty(5, empty_on={1, 3})
        assert len(questions) == 3

    def test_empty_is_distinguished_from_failed(self, monkeypatch):
        """Both leave a hole, but for different reasons and with different
        fixes — one is a model that rambled, the other a call that died."""
        def fake(slide, model, **kwargs):
            if slide.index == 0:
                return []
            if slide.index == 1:
                raise TimeoutError("timed out")
            return [question(slide.index)]

        monkeypatch.setattr(gen, "generate_questions", fake)
        messages: list[str] = []
        gen.generate_questions_batch(
            sections(4), model="test", target_total=4,
            progress_callback=lambda c, t, m="": messages.append(m),
        )
        final = messages[-1]
        assert "returned nothing usable" in final
        assert "skipped" in final
