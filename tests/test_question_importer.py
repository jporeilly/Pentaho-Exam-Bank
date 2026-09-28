"""Tests for core/question_importer.py — CSV and JSON import + validation."""

import csv
import json

import pytest

from exam_bank.core.question_importer import (
    import_from_csv, import_from_json, validate_question_against_pptx,
    validate_batch,
)
from exam_bank.core.bank import Question
from exam_bank.core.pptx_reader import PPTXReader
from exam_bank.core.source import SlideInfo


# ── CSV Import ─────────────────────────────────────────


class TestCSVImport:
    def _write_csv(self, path, headers, rows):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for row in rows:
                writer.writerow(row)

    def test_simple_csv(self, tmp_path):
        path = tmp_path / "simple.csv"
        self._write_csv(path, ["Stem", "Key", "Distractor 1", "Distractor 2"], [
            ["What is 2+2? (Choose one.)", "4", "3", "5"],
            ["What color is the sky? (Choose one.)", "Blue", "Red", "Green"],
        ])
        questions = import_from_csv(path)
        assert len(questions) == 2
        assert questions[0].stem == "What is 2+2? (Choose one.)"
        assert questions[0].key == "4"
        assert len(questions[0].distractors) == 2

    def test_full_roundtrip_csv(self, tmp_path):
        path = tmp_path / "full.csv"
        self._write_csv(path, [
            "ID", "Scenario", "Stem", "Question Type", "Key", "Keys",
            "Key Source Text",
            "Distractor 1", "Distractor 2", "Distractor 3", "Distractor 4",
            "Explanation", "Topic", "Difficulty", "Bloom Level",
            "Certification ID", "Status", "Reject Reason",
            "Created By", "Assigned SME",
            "Source File", "Source Slides", "Key Source Slide",
            "Created At", "Reviewed At", "Approved At", "Tags",
        ], [
            [
                "id-123", "Context.", "Q? (Choose one.)", "single", "Answer", "",
                "Source text",
                "Wrong1", "Wrong2", "Wrong3", "",
                "Explanation", "TopicA", "Hard", "Analyze",
                "cert-1", "approved", "",
                "AI", "Jane",
                "deck.pptx", "1; 3", "1",
                "2026-01-01", "2026-01-05", "2026-01-10", "qa:passed; reviewed",
            ],
        ])
        questions = import_from_csv(path)
        assert len(questions) == 1
        q = questions[0]
        assert q.id == "id-123"
        assert q.status == "approved"
        assert q.difficulty == "Hard"
        assert q.source_slides == [0, 2]  # 1-based CSV → 0-based internal
        assert q.key_source_slide == 0
        assert "qa:passed" in q.tags

    def test_multi_select_csv(self, tmp_path):
        path = tmp_path / "multi.csv"
        self._write_csv(path, [
            "Stem", "Question Type", "Key", "Keys",
            "Distractor 1", "Distractor 2",
        ], [
            ["Q? (Choose two.)", "multi", "", "Ans A|Ans B", "Wrong1", "Wrong2"],
        ])
        questions = import_from_csv(path)
        assert questions[0].question_type == "multi"
        assert questions[0].keys == ["Ans A", "Ans B"]
        assert questions[0].key == "Ans A"

    def test_pipe_separated_key(self, tmp_path):
        path = tmp_path / "pipe.csv"
        self._write_csv(path, ["Stem", "Key", "Distractor 1", "Distractor 2"], [
            ["Q?", "A|B", "W1", "W2"],
        ])
        questions = import_from_csv(path)
        assert questions[0].question_type == "multi"
        assert questions[0].keys == ["A", "B"]

    def test_skip_empty_stem(self, tmp_path):
        path = tmp_path / "empty.csv"
        self._write_csv(path, ["Stem", "Key", "Distractor 1", "Distractor 2"], [
            ["", "4", "3", "5"],
            ["Valid? (Choose one.)", "Yes", "No", "Maybe"],
        ])
        questions = import_from_csv(path)
        assert len(questions) == 1

    def test_invalid_status_defaults_to_draft(self, tmp_path):
        path = tmp_path / "badstatus.csv"
        self._write_csv(path, ["Stem", "Key", "Distractor 1", "Distractor 2", "Status"], [
            ["Q?", "A", "B", "C", "invalid_status"],
        ])
        questions = import_from_csv(path)
        assert questions[0].status == "draft"

    def test_empty_file(self, tmp_path):
        path = tmp_path / "empty.csv"
        path.write_text("", encoding="utf-8")
        questions = import_from_csv(path)
        assert questions == []

    def test_fuzzy_headers(self, tmp_path):
        path = tmp_path / "fuzzy.csv"
        self._write_csv(path, ["Question", "Answer", "Wrong 1", "Wrong 2"], [
            ["What is 1+1?", "2", "3", "4"],
        ])
        questions = import_from_csv(path)
        assert len(questions) == 1
        assert questions[0].key == "2"


# ── JSON Import ────────────────────────────────────────


class TestJSONImport:
    def test_basic_json(self, tmp_path):
        path = tmp_path / "questions.json"
        data = [
            {
                "stem": "What is Python?",
                "key": "A programming language",
                "distractors": ["A snake", "A movie"],
                "topic": "Programming",
            },
        ]
        path.write_text(json.dumps(data), encoding="utf-8")
        questions = import_from_json(path)
        assert len(questions) == 1
        assert questions[0].topic == "Programming"
        assert questions[0].status == "draft"
        assert questions[0].created_by == "Import"

    def test_multi_select_json(self, tmp_path):
        path = tmp_path / "multi.json"
        data = [{
            "stem": "Q?", "question_type": "multi",
            "keys": ["A", "B"], "distractors": ["C", "D"],
        }]
        path.write_text(json.dumps(data), encoding="utf-8")
        questions = import_from_json(path)
        assert questions[0].question_type == "multi"
        assert questions[0].keys == ["A", "B"]

    def test_invalid_json(self, tmp_path):
        path = tmp_path / "invalid.json"
        path.write_text('{"not": "a list"}', encoding="utf-8")
        questions = import_from_json(path)
        assert questions == []

    def test_empty_array(self, tmp_path):
        path = tmp_path / "empty.json"
        path.write_text("[]", encoding="utf-8")
        questions = import_from_json(path)
        assert questions == []


# ── Validation against PPTX ───────────────────────────


class MockPPTXReader:
    """A mock PPTXReader for validation tests (avoids needing real PPTX files)."""

    def __init__(self, slides):
        self._slides = slides

    @property
    def slide_count(self):
        return len(self._slides)

    @property
    def slides(self):
        return self._slides


class TestValidation:
    def test_exact_match(self):
        reader = MockPPTXReader([
            SlideInfo(index=0, speaker_notes="HTTPS is used for secure web communication."),
        ])
        q = Question(stem="Q?", key="HTTPS is used for secure web communication.")
        passed, match, slide_idx, detail = validate_question_against_pptx(q, reader)
        assert passed
        assert slide_idx == 0
        assert "Exact match" in detail

    def test_fuzzy_match(self):
        reader = MockPPTXReader([
            SlideInfo(index=0, speaker_notes="The AES algorithm provides strong symmetric encryption for data at rest."),
        ])
        q = Question(stem="Q?", key="AES algorithm provides symmetric encryption")
        passed, _, slide_idx, detail = validate_question_against_pptx(q, reader)
        assert passed
        assert "overlap" in detail.lower() or "exact" in detail.lower()

    def test_no_match(self):
        reader = MockPPTXReader([
            SlideInfo(index=0, speaker_notes="Topic about databases."),
        ])
        q = Question(stem="Q?", key="Quantum computing is the future")
        passed, _, _, detail = validate_question_against_pptx(q, reader)
        assert not passed
        assert "No match" in detail

    def test_fallback_to_body_text(self):
        reader = MockPPTXReader([
            SlideInfo(index=0, speaker_notes="", body_text="Body text with HTTPS info."),
        ])
        q = Question(stem="Q?", key="HTTPS info")
        passed, _, _, _ = validate_question_against_pptx(q, reader)
        assert passed

    def test_empty_reader(self):
        reader = MockPPTXReader([])
        q = Question(stem="Q?", key="Answer")
        passed, _, _, detail = validate_question_against_pptx(q, reader)
        assert not passed
        assert "No PPTX" in detail

    def test_validate_batch(self):
        reader = MockPPTXReader([
            SlideInfo(index=0, speaker_notes="HTTPS is secure. AES is symmetric."),
        ])
        q1 = Question(stem="Q1?", key="HTTPS is secure")
        q2 = Question(stem="Q2?", key="Completely unrelated topic")
        results = validate_batch([q1, q2], reader)
        assert results[0][1] is True   # q1 passed
        assert results[1][1] is False  # q2 failed
        assert "key-not-validated" in results[1][0].tags  # failed validation gets this tag


class TestOptionOrder:
    def _write_csv(self, path, headers, rows):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for row in rows:
                writer.writerow(row)

    def test_csv_option_order_default(self, tmp_path):
        """CSV without option_order column gets keys+distractors order."""
        path = tmp_path / "q.csv"
        self._write_csv(path, ["Stem", "Key", "Distractor 1", "Distractor 2"], [
            ["Q?", "Correct", "Wrong1", "Wrong2"],
        ])
        q = import_from_csv(path)[0]
        assert q.option_order == ["Correct", "Wrong1", "Wrong2"]

    def test_csv_option_order_column(self, tmp_path):
        """CSV with explicit option_order column preserves interleaved order."""
        path = tmp_path / "q.csv"
        self._write_csv(path, ["Stem", "Key", "Distractor 1", "Distractor 2", "Option Order"], [
            ["Q?", "Correct", "Wrong1", "Wrong2", "Wrong1|Correct|Wrong2"],
        ])
        q = import_from_csv(path)[0]
        assert q.option_order == ["Wrong1", "Correct", "Wrong2"]

    def test_csv_multi_option_order(self, tmp_path):
        """Multi-select CSV preserves option_order."""
        path = tmp_path / "q.csv"
        self._write_csv(path, ["Stem", "Question Type", "Keys", "Distractor 1", "Distractor 2"], [
            ["Q? (Choose two.)", "multi", "A|B", "W1", "W2"],
        ])
        q = import_from_csv(path)[0]
        assert q.option_order == ["A", "B", "W1", "W2"]

    def test_all_choices_uses_option_order(self):
        """Question.all_choices returns option_order when available."""
        q = Question(
            stem="Q?", key="C", distractors=["A", "B"],
            option_order=["A", "C", "B"],
        )
        assert q.all_choices == ["A", "C", "B"]

    def test_all_choices_fallback(self):
        """Question.all_choices falls back to keys+distractors without option_order."""
        q = Question(stem="Q?", key="C", distractors=["A", "B"])
        assert q.all_choices == ["C", "A", "B"]

    def test_json_option_order(self, tmp_path):
        """JSON import preserves option_order field."""
        path = tmp_path / "q.json"
        path.write_text(json.dumps([{
            "stem": "Q?", "key": "C", "distractors": ["A", "B"],
            "option_order": ["A", "C", "B"],
        }]))
        q = import_from_json(path)[0]
        assert q.option_order == ["A", "C", "B"]

    def test_json_option_order_default(self, tmp_path):
        """JSON import without option_order builds from keys+distractors."""
        path = tmp_path / "q.json"
        path.write_text(json.dumps([{
            "stem": "Q?", "key": "C", "distractors": ["A", "B"],
        }]))
        q = import_from_json(path)[0]
        assert q.option_order == ["C", "A", "B"]


class TestBloomOnImport:
    """Every importer reads the Bloom level the same way (_bloom_of): the same
    three spellings, any case, and nothing outside BLOOM_LEVELS written through.

    Before, CSV wrote an unvalidated "apply" straight into the column, and JSON
    read only `bloom_level`, so a file saying `bloom` - what CSV accepts and a
    PCM exam.json writes - silently took the default."""

    def _csv(self, tmp_path, header, value):
        path = tmp_path / "b.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Stem", "Key", "Distractor 1", "Distractor 2", header])
            writer.writerow(["Q?", "A", "B", "C", value])
        return import_from_csv(path)[0].bloom_level

    def _json(self, tmp_path, item):
        path = tmp_path / "b.json"
        path.write_text(json.dumps([{"stem": "Q?", "key": "A", "distractors": ["B", "C"], **item}]),
                        encoding="utf-8")
        return import_from_json(path)[0].bloom_level

    def test_csv_normalises_case(self, tmp_path):
        assert self._csv(tmp_path, "Bloom", "apply") == "Apply"

    def test_csv_refuses_a_level_that_does_not_exist(self, tmp_path):
        assert self._csv(tmp_path, "Bloom", "Synthesis") == "Understand"

    def test_json_reads_bloom_as_well_as_bloom_level(self, tmp_path):
        assert self._json(tmp_path, {"bloom": "Analyze"}) == "Analyze"
        assert self._json(tmp_path, {"bloom_level": "evaluate"}) == "Evaluate"

    def test_json_refuses_a_level_that_does_not_exist(self, tmp_path):
        assert self._json(tmp_path, {"bloom_level": "Synthesis"}) == "Understand"
