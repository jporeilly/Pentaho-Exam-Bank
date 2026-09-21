"""Tests for core/pcm_reader.py — reading PCM course content as SlideInfo."""

import json

import pytest

from exam_bank.core.pcm_reader import (
    list_pcm_courses, list_pcm_labs, load_pcm_course, clean_markdown,
)


@pytest.fixture
def courses_dir(tmp_path):
    """Build a minimal PCM courses dir: one course with one lab + an _assets dir."""
    course = tmp_path / "developer-ai-speciality"
    course.mkdir()
    (course / "course.json").write_text(
        json.dumps({"id": "developer-ai-speciality", "title": "Developer – AI Speciality"}),
        encoding="utf-8",
    )
    lab = course / "03-llm-integration"
    lab.mkdir()
    (lab / "manifest.json").write_text(json.dumps({"title": "LLM Integration"}), encoding="utf-8")
    (lab / "guide.md").write_text(
        "Intro prose for the lab that is comfortably long enough to survive the "
        "minimum-section-length filter and become its own leading section.\n\n"
        "## Overview\n"
        "This explains <dfn>tokenisation</dfn> in depth, with enough words to pass "
        "the section length threshold so the section is retained for generation.\n\n"
        "![architecture diagram](./images/arch.png)\n\n"
        "See [the Pentaho docs](https://example.com/docs) for background.\n\n"
        '<button data-launch="spoon" data-path="files/x.ktr">Open in PDI</button>\n\n'
        '<div class="pcm-tabs-widget" data-tabs="%5B%7B%22title%22%3A%22A%22%7D%5D"></div>\n\n'
        "## Steps\n"
        "Step one configures the connection and is descriptive enough on its own to "
        "be a valid retained section with sufficient prose length.\n",
        encoding="utf-8",
    )
    # A second lab, so lab listing/filtering has something to choose between.
    lab2 = course / "04-langextract"
    lab2.mkdir()
    (lab2 / "manifest.json").write_text(json.dumps({"title": "LangExtract"}), encoding="utf-8")
    (lab2 / "guide.md").write_text(
        "## Extraction\n"
        "LangExtract turns free text into structured rows and has enough prose "
        "here to comfortably pass the minimum section length filter.\n",
        encoding="utf-8",
    )
    # A non-lab dir with no guide.md must be skipped.
    (course / "_assets").mkdir()
    (course / "_assets" / "note.txt").write_text("nope", encoding="utf-8")
    return tmp_path


class TestListCourses:
    def test_lists_course_with_title(self, courses_dir):
        courses = list_pcm_courses(courses_dir)
        assert courses == [{"slug": "developer-ai-speciality", "title": "Developer – AI Speciality"}]

    def test_missing_dir_returns_empty(self, tmp_path):
        assert list_pcm_courses(tmp_path / "nope") == []


class TestCleanMarkdown:
    def test_strips_widget_html_and_unwraps_dfn(self):
        out = clean_markdown(
            'x <dfn>token</dfn> y\n<div class="pcm-tabs-widget" data-tabs="ABC"></div>\n'
            '<button>go</button> [text](http://u) ![alt](p.png)'
        )
        assert "token" in out
        assert "<" not in out                 # no HTML tags
        assert "pcm-tabs-widget" not in out    # widget blob gone
        assert "http://u" not in out           # link target stripped
        assert "text" in out                   # link text kept
        assert "alt" in out                    # image alt kept


class TestLoadCourse:
    def test_yields_clean_sections(self, courses_dir):
        slides = load_pcm_course(courses_dir, "developer-ai-speciality")
        assert len(slides) >= 2  # intro + Overview + Steps (intro may merge)
        # No rendering markup leaks into the grounding text.
        for s in slides:
            assert "pcm-tabs-widget" not in s.speaker_notes
            assert "<button" not in s.speaker_notes
            assert "<dfn" not in s.speaker_notes
        joined = "\n".join(s.speaker_notes for s in slides)
        assert "tokenisation" in joined          # dfn unwrapped to its text
        titles = [s.title for s in slides]
        assert any("Overview" in t for t in titles)
        assert any("LLM Integration" in t for t in titles)  # lab title in section title

    def test_unknown_course_returns_empty(self, courses_dir):
        assert load_pcm_course(courses_dir, "no-such-course") == []


class TestLabs:
    def test_lists_labs_with_guides_only(self, courses_dir):
        labs = list_pcm_labs(courses_dir, "developer-ai-speciality")
        slugs = [l["slug"] for l in labs]
        assert slugs == ["03-llm-integration", "04-langextract"]  # _assets excluded
        assert {l["title"] for l in labs} == {"LLM Integration", "LangExtract"}

    def test_load_scoped_to_one_lab(self, courses_dir):
        only = load_pcm_course(courses_dir, "developer-ai-speciality", "04-langextract")
        assert only  # non-empty
        assert all("LangExtract" in s.title for s in only)
        joined = "\n".join(s.speaker_notes for s in only)
        assert "LangExtract" in joined and "tokenisation" not in joined

    def test_unknown_lab_returns_empty(self, courses_dir):
        assert load_pcm_course(courses_dir, "developer-ai-speciality", "99-nope") == []
