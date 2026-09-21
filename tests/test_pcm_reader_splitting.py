"""Sub-splitting a section that is too long for the model to read.

Ollama truncates an over-long section silently, so a workshop guide with no H2
headings — one H1 title and a dozen H3s — becomes a single 100k-character
section that the model reads the first fifth of. Splitting deeper fixes the
cause; the tests here pin the two properties that matter:

  * a section that already fits is never touched, and
  * a section that does not fit is split on the headings it actually has.
"""

import json

import pytest

from exam_bank.core.pcm_reader import (
    is_front_matter, list_pcm_labs, load_pcm_course,
)


def build(tmp_path, guide: str, *, slug: str = "demo", lab: str = "01-lab"):
    course = tmp_path / slug
    (course / lab).mkdir(parents=True)
    (course / "course.json").write_text(json.dumps({"title": "Demo"}), encoding="utf-8")
    (course / lab / "guide.md").write_text(guide, encoding="utf-8")
    return tmp_path


def prose(word: str, n: int) -> str:
    return (f"{word} " * n).strip()


@pytest.fixture
def workshop(tmp_path):
    """A guide shaped like the real workshops: an H1 and H3s, no H2 at all."""
    return build(tmp_path, "\n\n".join([
        "# Key Concepts Workshop",
        "### Prompt", prose("prompt", 400),
        "### Embedding", prose("embedding", 400),
        "### Search", prose("search", 400),
    ]))


class TestNothingChangesForMaterialThatFits:
    def test_no_budget_means_no_sub_splitting(self, workshop):
        """The default is off, so every existing caller keeps the behaviour it
        had: split on H2, and nothing else."""
        sections = load_pcm_course(workshop, "demo")
        assert len(sections) == 1, "with no H2 the whole guide is one section"

    def test_a_section_within_budget_is_left_alone(self, workshop):
        big = load_pcm_course(workshop, "demo", max_chars=1_000_000)
        assert len(big) == 1

    def test_an_h2_course_is_untouched_when_its_sections_fit(self, tmp_path):
        guide = "\n\n".join([
            "## First", prose("alpha", 40),
            "### A detail", prose("detail", 40),
            "## Second", prose("beta", 40),
        ])
        built = build(tmp_path, guide)
        assert [s.title for s in load_pcm_course(built, "demo")] == [
            s.title for s in load_pcm_course(built, "demo", max_chars=5000)
        ], "a course whose sections already fit must not be re-cut"


class TestSplittingWhenItDoesNotFit:
    def test_a_headingless_workshop_is_split_on_its_h3s(self, workshop):
        sections = load_pcm_course(workshop, "demo", max_chars=1200)
        titles = [s.title for s in sections]
        assert len(titles) == 3
        assert any("Prompt" in t for t in titles)
        assert any("Embedding" in t for t in titles)
        assert any("Search" in t for t in titles)

    def test_every_piece_now_fits(self, workshop):
        # The budget has to be above the largest H3, or the split cannot
        # satisfy it and the pieces come back whole — which is
        # `test_a_long_run_with_no_headings_is_yielded_whole`, not a failure
        # of this one. Derived from the guide rather than guessed, so the
        # fixture can change without quietly making this test vacuous.
        budget = 5000
        whole = load_pcm_course(workshop, "demo")
        assert len(whole) == 1 and len(whole[0].speaker_notes) > budget, (
            "the fixture must start as one section that is too long"
        )

        pieces = load_pcm_course(workshop, "demo", max_chars=budget)
        assert len(pieces) > 1, "it should have been split"
        for section in pieces:
            assert len(section.speaker_notes) <= budget

    def test_the_title_still_says_where_it_came_from(self, tmp_path):
        """A question's topic comes from the title, so a sub-section has to
        keep its parent — "Components" alone says nothing."""
        guide = "\n\n".join([
            "## Carrier Dashboard", prose("intro", 20),
            "### Components", prose("component", 400),
        ])
        sections = load_pcm_course(build(tmp_path, guide), "demo", max_chars=1200)
        assert any("Carrier Dashboard — Components" in s.title for s in sections)

    def test_it_goes_deeper_when_a_sub_section_is_still_too_long(self, tmp_path):
        """One over-long H3 inside an over-long H2 is common: a Components
        section is a list of components, each its own H4."""
        guide = "\n\n".join([
            "## Dashboard", prose("intro", 20),
            "### Components",
            "#### Chart", prose("chart", 300),
            "#### Table", prose("table", 300),
        ])
        titles = [s.title for s in load_pcm_course(build(tmp_path, guide), "demo",
                                                   max_chars=1000)]
        assert any("Chart" in t for t in titles)
        assert any("Table" in t for t in titles)

    def test_prose_before_the_first_sub_heading_is_kept(self, tmp_path):
        guide = "\n\n".join([
            "## Overview", prose("lead", 100),
            "### Detail", prose("detail", 400),
        ])
        sections = load_pcm_course(build(tmp_path, guide), "demo", max_chars=900)
        assert any("lead" in s.speaker_notes for s in sections), (
            "the introduction was dropped when its section was split"
        )

    def test_a_long_run_with_no_headings_is_yielded_whole(self, tmp_path):
        """Half a section is worse than a long one. The caller flags what
        still does not fit rather than cutting mid-sentence."""
        guide = "## Solid\n\n" + prose("unbroken", 2000)
        sections = load_pcm_course(build(tmp_path, guide), "demo", max_chars=500)
        assert len(sections) == 1
        assert len(sections[0].speaker_notes) > 500

    def test_it_stops_before_headings_become_steps(self, tmp_path):
        """H5 and below are procedure, not subject matter — splitting there
        makes thin, procedural questions."""
        guide = "\n\n".join([
            "## Lab", "### Part", "#### Task",
            "##### Step one", prose("one", 300),
            "##### Step two", prose("two", 300),
        ])
        titles = [s.title for s in load_pcm_course(build(tmp_path, guide), "demo",
                                                   max_chars=800)]
        assert not any("Step one" in t for t in titles)


class TestFrontMatterIsNotExamined:
    """Course furniture is not subject matter.

    "Before You Start" explains how to use the guide and check the
    environment. Generating from it produced "What is the primary purpose of
    the Before You Start section?" — an exam about the training material.
    Twelve courses have one, and between them they carried 86 sections.
    """

    def build_course(self, tmp_path, labs: dict[str, str]):
        course = tmp_path / "demo"
        (course / "course.json").parent.mkdir(parents=True, exist_ok=True)
        (course / "course.json").write_text(json.dumps({"title": "Demo"}), encoding="utf-8")
        for slug, title in labs.items():
            lab = course / slug
            lab.mkdir(parents=True)
            (lab / "manifest.json").write_text(
                json.dumps({"title": title}), encoding="utf-8")
            (lab / "guide.md").write_text(
                f"## {title} matter\n\n" + prose("content", 40), encoding="utf-8")
        return tmp_path

    def test_before_you_start_is_skipped(self, tmp_path):
        built = self.build_course(tmp_path, {
            "00-before-you-start": "Before You Start",
            "01-real": "Building a Transformation",
        })
        groups = {s.group for s in load_pcm_course(built, "demo")}
        assert groups == {"Building a Transformation"}

    def test_a_welcome_lab_is_skipped(self, tmp_path):
        built = self.build_course(tmp_path, {
            "00-welcome": "Welcome", "01-real": "Real Content",
        })
        assert {s.group for s in load_pcm_course(built, "demo")} == {"Real Content"}

    def test_asking_for_it_by_name_still_reads_it(self, tmp_path):
        """Naming that lab is a clear instruction; answering with nothing
        would be obtuse."""
        built = self.build_course(tmp_path, {
            "00-before-you-start": "Before You Start", "01-real": "Real Content",
        })
        sections = load_pcm_course(built, "demo", lab_slug="00-before-you-start")
        assert sections and sections[0].group == "Before You Start"

    def test_it_is_still_listed_so_it_has_not_just_vanished(self, tmp_path):
        built = self.build_course(tmp_path, {
            "00-before-you-start": "Before You Start", "01-real": "Real Content",
        })
        labs = list_pcm_labs(built, "demo")
        assert [l["title"] for l in labs] == ["Before You Start", "Real Content"]
        assert [l["frontMatter"] for l in labs] == [True, False]

    def test_overview_of_something_is_real_content(self, tmp_path):
        """Thirteen labs are called exactly "Overview" but thirty-five more
        are "Overview of Schemas" and the like. A loose match on the word
        would have thrown away the real ones."""
        assert not is_front_matter("Overview of Schemas", "05-overview-of-schemas")
        assert not is_front_matter("Overview", "02-overview")

    def test_a_welcome_screen_is_not_front_matter(self, tmp_path):
        """Report Designer's Welcome Screen is a product feature. Matching
        the word inside a section heading would have lost it."""
        assert not is_front_matter("Navigating Report Designer", "03-navigating")
