"""Tests for QTI 2.1 and Moodle XML import."""

import pytest
from pathlib import Path
from question_bank.core.question_importer import (
    import_from_qti21, import_from_moodle_xml, detect_xml_format,
)


class TestDetectXmlFormat:
    def test_detect_qti(self, tmp_path):
        xml = '''<?xml version="1.0"?>
        <assessmentTest xmlns="http://www.imsglobal.org/xsd/imsqti_v2p1" identifier="test1" title="Test">
            <testPart identifier="tp1">
                <assessmentSection identifier="s1" title="Section">
                </assessmentSection>
            </testPart>
        </assessmentTest>'''
        f = tmp_path / "test.xml"
        f.write_text(xml)
        assert detect_xml_format(f) == "qti"

    def test_detect_moodle(self, tmp_path):
        xml = '''<?xml version="1.0"?>
        <quiz>
            <question type="multichoice">
                <name><text>Q1</text></name>
                <questiontext format="html"><text>What is 1+1?</text></questiontext>
                <answer fraction="100"><text>2</text></answer>
                <answer fraction="0"><text>3</text></answer>
            </question>
        </quiz>'''
        f = tmp_path / "test.xml"
        f.write_text(xml)
        assert detect_xml_format(f) == "moodle"


class TestQTI21Import:
    def test_basic_import(self, tmp_path):
        xml = '''<?xml version="1.0"?>
        <assessmentTest xmlns="http://www.imsglobal.org/xsd/imsqti_v2p1" identifier="test1" title="Test">
            <testPart identifier="tp1">
                <assessmentSection identifier="s1" title="Section">
                    <assessmentItem identifier="q1" title="Q1">
                        <responseDeclaration identifier="RESPONSE" cardinality="single" baseType="identifier">
                            <correctResponse><value>choice_key</value></correctResponse>
                        </responseDeclaration>
                        <itemBody>
                            <choiceInteraction responseIdentifier="RESPONSE" maxChoices="1">
                                <prompt>What is the capital of France?</prompt>
                                <simpleChoice identifier="choice_key">Paris</simpleChoice>
                                <simpleChoice identifier="choice_d1">London</simpleChoice>
                                <simpleChoice identifier="choice_d2">Berlin</simpleChoice>
                            </choiceInteraction>
                        </itemBody>
                    </assessmentItem>
                </assessmentSection>
            </testPart>
        </assessmentTest>'''
        f = tmp_path / "test.xml"
        f.write_text(xml)
        questions = import_from_qti21(f)
        assert len(questions) == 1
        q = questions[0]
        assert "capital of France" in q.stem
        assert q.key == "Paris"
        assert "London" in q.distractors
        assert "Berlin" in q.distractors

    def test_empty_file(self, tmp_path):
        xml = '''<?xml version="1.0"?><assessmentTest xmlns="http://www.imsglobal.org/xsd/imsqti_v2p1" identifier="t" title="T"><testPart identifier="tp"><assessmentSection identifier="s" title="S"></assessmentSection></testPart></assessmentTest>'''
        f = tmp_path / "test.xml"
        f.write_text(xml)
        questions = import_from_qti21(f)
        assert questions == []


class TestMoodleImport:
    def test_basic_import(self, tmp_path):
        xml = '''<?xml version="1.0"?>
        <quiz>
            <question type="multichoice">
                <name><text>Test Question</text></name>
                <questiontext format="html"><text><![CDATA[<p>What is 2+2?</p>]]></text></questiontext>
                <generalfeedback><text>Basic arithmetic</text></generalfeedback>
                <answer fraction="100" format="html"><text>4</text></answer>
                <answer fraction="0" format="html"><text>3</text></answer>
                <answer fraction="0" format="html"><text>5</text></answer>
                <tags><tag><text>Math</text></tag></tags>
            </question>
        </quiz>'''
        f = tmp_path / "test.xml"
        f.write_text(xml)
        questions = import_from_moodle_xml(f)
        assert len(questions) == 1
        q = questions[0]
        assert "2+2" in q.stem
        assert q.key == "4"
        assert "3" in q.distractors
        assert "5" in q.distractors
        assert q.explanation == "Basic arithmetic"
        assert q.topic == "Math"

    def test_skips_non_multichoice(self, tmp_path):
        xml = '''<?xml version="1.0"?>
        <quiz>
            <question type="truefalse">
                <name><text>TF</text></name>
                <questiontext><text>True?</text></questiontext>
            </question>
        </quiz>'''
        f = tmp_path / "test.xml"
        f.write_text(xml)
        questions = import_from_moodle_xml(f)
        assert questions == []
