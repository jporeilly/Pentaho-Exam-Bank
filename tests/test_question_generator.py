"""Prompt building, JSON extraction and key validation.

These imported from `core/question_generator.py`, a re-export shim left from
splitting the generator into four modules; nothing else used it, so it was
deleted in 1.9.0 and the tests import the modules themselves.
"""

import json

import pytest

from exam_bank.core.generation_parsing import (
    _extract_json_array, _extract_json_object, validate_key_against_notes,
)
from exam_bank.core.generation_prompts import _build_question_specs, _num_word, build_prompt
from exam_bank.core.bank import Question
from exam_bank.core.source import SlideInfo


# ── Helper functions ───────────────────────────────────


class TestNumWord:
    def test_two(self):
        assert _num_word(2) == "two"

    def test_three(self):
        assert _num_word(3) == "three"

    def test_four(self):
        assert _num_word(4) == "four"

    def test_large(self):
        assert _num_word(10) == "10"


class TestBuildQuestionSpecs:
    def test_single_select(self):
        specs = _build_question_specs(3, num_keys=1, num_distractors=3)
        assert len(specs) == 3
        for s in specs:
            assert s["type"] == "single"
            assert s["num_choices"] == 4

    def test_multi_select(self):
        specs = _build_question_specs(2, num_keys=2, num_distractors=3)
        assert len(specs) == 2
        for s in specs:
            assert s["type"] == "multi"
            assert s["num_correct"] == 2
            assert s["num_choices"] == 5


# ── JSON extraction ────────────────────────────────────


class TestExtractJSONArray:
    def test_plain_array(self):
        result = _extract_json_array('[{"key": "value"}]')
        assert result == [{"key": "value"}]

    def test_markdown_fenced(self):
        text = '```json\n[{"key": "value"}]\n```'
        result = _extract_json_array(text)
        assert result == [{"key": "value"}]

    def test_with_surrounding_text(self):
        text = 'Here are the questions:\n[{"stem": "Q?"}]\nDone!'
        result = _extract_json_array(text)
        assert result[0]["stem"] == "Q?"

    def test_invalid_json(self):
        assert _extract_json_array("not json at all") is None

    def test_empty_array(self):
        assert _extract_json_array("[]") == []

    def test_no_brackets(self):
        assert _extract_json_array("just text") is None


class TestExtractJSONObject:
    def test_plain_object(self):
        result = _extract_json_object('{"key": "value"}')
        assert result == {"key": "value"}

    def test_fenced_object(self):
        text = '```json\n{"stem": "Q?"}\n```'
        result = _extract_json_object(text)
        assert result["stem"] == "Q?"

    def test_invalid(self):
        assert _extract_json_object("no json here") is None


# ── Prompt building ────────────────────────────────────


class TestBuildPrompt:
    def test_basic_prompt(self):
        slide = SlideInfo(
            index=0,
            title="Security Basics",
            body_text="Content about security",
            speaker_notes="AES is a symmetric encryption algorithm.",
        )
        prompt = build_prompt(slide, num_questions=2, difficulty="Medium", bloom_level="Apply")
        assert "Security Basics" in prompt
        assert "AES" in prompt
        assert "2 question" in prompt
        assert "Medium" in prompt
        assert "Apply" in prompt

    def test_prompt_with_certification(self):
        slide = SlideInfo(index=0, speaker_notes="Notes here.")
        prompt = build_prompt(slide, certification="SE Cert 2026")
        assert "SE Cert 2026" in prompt

    def test_prompt_with_custom_instructions(self):
        slide = SlideInfo(index=0, speaker_notes="Notes.")
        prompt = build_prompt(slide, custom_instructions="Focus on networking topics only.")
        assert "Focus on networking topics only" in prompt

    def test_prompt_multi_select_specs(self):
        slide = SlideInfo(index=0, speaker_notes="Notes.")
        specs = [{"type": "multi", "num_correct": 2, "num_choices": 5}]
        prompt = build_prompt(slide, question_specs=specs)
        assert "MULTI-SELECT" in prompt
        # The number is asked for in the question's words; a "(Choose two.)"
        # in the stem would be shown twice (see stem_text).
        assert "exactly two answers" in prompt
        assert "(Choose two.)" not in prompt

    def test_prompt_single_select_specs(self):
        slide = SlideInfo(index=0, speaker_notes="Notes.")
        specs = [{"type": "single", "num_choices": 4}]
        prompt = build_prompt(slide, question_specs=specs)
        assert "SINGLE-SELECT" in prompt
        assert "(Choose one.)" not in prompt

    def test_prompt_mixed_specs(self):
        slide = SlideInfo(index=0, speaker_notes="Notes.")
        specs = [
            {"type": "single", "num_choices": 4},
            {"type": "multi", "num_correct": 2, "num_choices": 5},
        ]
        prompt = build_prompt(slide, question_specs=specs)
        assert "Question 1: SINGLE-SELECT" in prompt
        assert "Question 2: MULTI-SELECT" in prompt


# ── Key validation against notes ───────────────────────


class TestValidateKeyAgainstNotes:
    def test_exact_match(self):
        q = Question(
            stem="Q?", key="A",
            key_source_text="AES is symmetric encryption",
        )
        slide = SlideInfo(index=0, speaker_notes="AES is symmetric encryption and widely used.")
        assert validate_key_against_notes(q, slide)

    def test_fuzzy_match(self):
        q = Question(
            stem="Q?", key="A",
            key_source_text="AES provides strong symmetric encryption for data",
        )
        slide = SlideInfo(
            index=0,
            speaker_notes="The AES algorithm provides strong symmetric encryption for data at rest.",
        )
        assert validate_key_against_notes(q, slide)

    def test_no_match(self):
        q = Question(
            stem="Q?", key="A",
            key_source_text="Quantum computing enables new paradigms",
        )
        slide = SlideInfo(index=0, speaker_notes="Simple topic about databases.")
        assert not validate_key_against_notes(q, slide)

    def test_empty_source_text(self):
        q = Question(stem="Q?", key="A", key_source_text="")
        slide = SlideInfo(index=0, speaker_notes="Some notes.")
        assert not validate_key_against_notes(q, slide)

    def test_empty_notes_fallback_to_body(self):
        q = Question(stem="Q?", key="A", key_source_text="Body content here")
        slide = SlideInfo(index=0, speaker_notes="", body_text="Body content here for reference.")
        assert validate_key_against_notes(q, slide)

    def test_empty_everything(self):
        q = Question(stem="Q?", key="A", key_source_text="Something")
        slide = SlideInfo(index=0, speaker_notes="", body_text="")
        assert not validate_key_against_notes(q, slide)
