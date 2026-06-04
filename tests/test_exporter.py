"""Tests for core/exporter.py — CSV, JSON, QTI 2.1, Moodle XML, and text export."""

import csv
import json
import xml.etree.ElementTree as ET

import pytest

from question_bank.core.question_bank import Question
from question_bank.core.exporter import (
    export_csv, export_json, export_qti21, export_moodle_xml, export_text,
    export_pcm_exam_json,
)


@pytest.fixture
def questions():
    return [
        Question(
            scenario="Company A needs to migrate data.",
            stem="Which tool is best for ETL? (Choose one.)",
            question_type="single",
            key="Pentaho Data Integration",
            key_source_text="PDI is the ETL tool.",
            distractors=["Excel", "Notepad", "Paint"],
            explanation="PDI — Correct. Others — Incorrect.",
            topic="Data Integration",
            difficulty="Medium",
            bloom_level="Apply",
            certification_id="cert-1",
            source_file="test.pptx",
            source_slides=[2, 3],
            key_source_slide=2,
            tags=["qa:passed"],
        ),
        Question(
            scenario="A team reviews security policies.",
            stem="Which two are encryption algorithms? (Choose two.)",
            question_type="multi",
            key="AES",
            keys=["AES", "RSA"],
            distractors=["HTTP", "FTP"],
            explanation="AES, RSA — Correct. Others — Incorrect.",
            topic="Security",
            difficulty="Hard",
            bloom_level="Analyze",
        ),
    ]


class TestCSVExport:
    def test_csv_creates_file(self, tmp_path, questions):
        path = tmp_path / "export.csv"
        export_csv(questions, path)
        assert path.exists()

    def test_csv_has_header_and_rows(self, tmp_path, questions):
        path = tmp_path / "export.csv"
        export_csv(questions, path)
        with open(path, encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
        assert len(rows) == 3  # header + 2 questions
        assert rows[0][0] == "ID"
        assert "Stem" in rows[0]

    def test_csv_content_correct(self, tmp_path, questions):
        path = tmp_path / "export.csv"
        export_csv(questions, path)
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert rows[0]["Key"] == "Pentaho Data Integration"
        assert rows[0]["Topic"] == "Data Integration"
        assert rows[0]["Source Slides"] == "3; 4"  # 0-based → 1-based

    def test_csv_multi_keys(self, tmp_path, questions):
        path = tmp_path / "export.csv"
        export_csv(questions, path)
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert rows[1]["Keys"] == "AES|RSA"

    def test_csv_tags(self, tmp_path, questions):
        path = tmp_path / "export.csv"
        export_csv(questions, path)
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert "qa:passed" in rows[0]["Tags"]


class TestJSONExport:
    def test_json_creates_file(self, tmp_path, questions):
        path = tmp_path / "export.json"
        export_json(questions, path)
        assert path.exists()

    def test_json_content(self, tmp_path, questions):
        path = tmp_path / "export.json"
        export_json(questions, path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data) == 2
        assert data[0]["stem"] == questions[0].stem
        assert data[0]["key"] == "Pentaho Data Integration"
        assert data[0]["topic"] == "Data Integration"

    def test_json_roundtrip_fields(self, tmp_path, questions):
        path = tmp_path / "export.json"
        export_json(questions, path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "source_slides" in data[0]
        assert "key_source_slide" in data[0]
        assert "tags" in data[0]


class TestQTI21Export:
    def test_qti_creates_file(self, tmp_path, questions):
        path = tmp_path / "export.xml"
        export_qti21(questions, path)
        assert path.exists()

    def test_qti_valid_xml(self, tmp_path, questions):
        path = tmp_path / "export.xml"
        export_qti21(questions, path)
        tree = ET.parse(path)
        root = tree.getroot()
        # QTI namespace
        assert "assessmentTest" in root.tag or root.tag.endswith("assessmentTest")

    def test_qti_has_items(self, tmp_path, questions):
        path = tmp_path / "export.xml"
        export_qti21(questions, path)
        content = path.read_text(encoding="utf-8")
        assert "assessmentItem" in content
        assert "choiceInteraction" in content


class TestMoodleXMLExport:
    def test_moodle_creates_file(self, tmp_path, questions):
        path = tmp_path / "moodle.xml"
        export_moodle_xml(questions, path)
        assert path.exists()

    def test_moodle_valid_xml(self, tmp_path, questions):
        path = tmp_path / "moodle.xml"
        export_moodle_xml(questions, path)
        tree = ET.parse(path)
        root = tree.getroot()
        assert root.tag == "quiz"

    def test_moodle_has_questions(self, tmp_path, questions):
        path = tmp_path / "moodle.xml"
        export_moodle_xml(questions, path)
        tree = ET.parse(path)
        q_elements = tree.findall(".//question")
        assert len(q_elements) == 2

    def test_moodle_correct_answer_fraction(self, tmp_path, questions):
        path = tmp_path / "moodle.xml"
        export_moodle_xml(questions, path)
        tree = ET.parse(path)
        q1 = tree.findall(".//question")[0]
        answers = q1.findall("answer")
        fractions = [a.get("fraction") for a in answers]
        assert "100" in fractions
        assert fractions.count("0") == 3  # 3 distractors

    def test_moodle_has_tags(self, tmp_path, questions):
        path = tmp_path / "moodle.xml"
        export_moodle_xml(questions, path)
        content = path.read_text(encoding="utf-8")
        assert "Data Integration" in content


class TestTextExport:
    def test_text_creates_file(self, tmp_path, questions):
        path = tmp_path / "export.txt"
        export_text(questions, path)
        assert path.exists()

    def test_text_has_questions(self, tmp_path, questions):
        path = tmp_path / "export.txt"
        export_text(questions, path)
        content = path.read_text(encoding="utf-8")
        assert "Question 1" in content
        assert "Question 2" in content

    def test_text_includes_answers(self, tmp_path, questions):
        path = tmp_path / "export.txt"
        export_text(questions, path, include_answers=True)
        content = path.read_text(encoding="utf-8")
        assert "Correct Answer:" in content

    def test_text_excludes_answers(self, tmp_path, questions):
        path = tmp_path / "export.txt"
        export_text(questions, path, include_answers=False)
        content = path.read_text(encoding="utf-8")
        assert "Correct Answer:" not in content

    def test_text_shuffles_choices(self, tmp_path, questions):
        """Choices should be present (A-D) but order varies."""
        path = tmp_path / "export.txt"
        export_text(questions, path)
        content = path.read_text(encoding="utf-8")
        assert "A)" in content
        assert "B)" in content


class TestPCMExamJSON:
    def _exam(self, tmp_path, questions):
        path = tmp_path / "exam.json"
        export_pcm_exam_json(questions, path, title="PDI Exam", pass_mark=75,
                             questions_per_attempt=2)
        return json.loads(path.read_text(encoding="utf-8"))

    def test_top_level_shape(self, tmp_path, questions):
        exam = self._exam(tmp_path, questions)
        assert exam["title"] == "PDI Exam"
        assert exam["passMark"] == 75
        assert exam["shuffle"] is True
        assert exam["webhookUrl"] == ""
        assert exam["questionsPerAttempt"] == 2
        assert len(exam["questions"]) == 2
        assert exam["questionsPerAttempt"] <= len(exam["questions"])

    def test_single_select_maps_to_correct_index(self, tmp_path, questions):
        exam = self._exam(tmp_path, questions)
        q = exam["questions"][0]
        assert q["prompt"] == questions[0].stem
        assert q["module"] == "Data Integration"
        assert q["scenario"] == "Company A needs to migrate data."
        # key is at the index it occupies in options
        assert q["options"][q["correct"]] == "Pentaho Data Integration"
        assert "correctIndices" not in q
        assert q["source"]  # key_source_text carried through

    def test_multi_select_maps_to_correct_indices(self, tmp_path, questions):
        exam = self._exam(tmp_path, questions)
        q = exam["questions"][1]
        assert "correct" not in q
        chosen = sorted(q["options"][i] for i in q["correctIndices"])
        assert chosen == ["AES", "RSA"]
        assert len(q["correctIndices"]) == 2

    def test_options_contain_keys_and_distractors(self, tmp_path, questions):
        exam = self._exam(tmp_path, questions)
        q2 = exam["questions"][1]
        assert set(q2["options"]) == {"AES", "RSA", "HTTP", "FTP"}
