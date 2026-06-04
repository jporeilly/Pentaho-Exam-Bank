"""Export questions to multiple formats: CSV, QTI 2.1, Moodle XML, PDF, JSON, DOCX."""

import csv
import io
import json
import html
import random
from pathlib import Path
from typing import List
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom.minidom import parseString

try:
    from docx import Document
    from docx.shared import Pt, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

from .question_bank import Question


def export_csv(questions: List[Question], path: Path):
    """Export questions to CSV format."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "ID", "Scenario", "Stem", "Question Type", "Key", "Keys",
            "Key Source Text",
            "Distractor 1", "Distractor 2", "Distractor 3", "Distractor 4",
            "Explanation", "Topic", "Difficulty", "Bloom Level",
            "Certification ID", "Status", "Reject Reason",
            "Created By", "Assigned SME",
            "Source File", "Source Slides", "Key Source Slide",
            "Created At", "Reviewed At", "Approved At", "Tags",
            "Option Order",
        ])
        for q in questions:
            d = q.distractors + [""] * 4  # pad to at least 4
            writer.writerow([
                q.id, q.scenario, q.stem, q.question_type,
                q.key, "|".join(q.keys) if q.keys else "",
                q.key_source_text,
                d[0], d[1], d[2], d[3],
                q.explanation, q.topic, q.difficulty,
                q.bloom_level, q.certification_id, q.status,
                q.reject_reason,
                q.created_by, q.assigned_sme,
                q.source_file,
                "; ".join(str(s + 1) for s in q.source_slides),
                q.key_source_slide + 1,
                q.created_at, q.reviewed_at, q.approved_at,
                "; ".join(q.tags),
                "|".join(q.option_order) if q.option_order else "",
            ])


def export_json(questions: List[Question], path: Path):
    """Export questions to JSON format."""
    data = []
    for q in questions:
        data.append({
            "id": q.id,
            "scenario": q.scenario,
            "stem": q.stem,
            "key": q.key,
            "key_source_text": q.key_source_text,
            "distractors": q.distractors,
            "explanation": q.explanation,
            "topic": q.topic,
            "difficulty": q.difficulty,
            "bloom_level": q.bloom_level,
            "certification_id": q.certification_id,
            "status": q.status,
            "created_by": q.created_by,
            "assigned_sme": q.assigned_sme,
            "source_file": q.source_file,
            "source_slides": q.source_slides,
            "key_source_slide": q.key_source_slide,
            "tags": q.tags,
            "created_at": q.created_at,
            "reviewed_at": q.reviewed_at,
            "approved_at": q.approved_at,
        })
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def export_pcm_exam_json(
    questions: List[Question],
    path: Path,
    *,
    title: str = "Practitioner Exam",
    pass_mark: int = 80,
    questions_per_attempt: int = None,
    shuffle: bool = True,
    description: str = "",
    webhook_url: str = "",
    webhook_secret: str = "",
    source_label: str = "",
):
    """Export questions as a Pentaho Content Manager ``exam.json``.

    PCM's renderer expects each question as ``{ prompt, options[],
    correct | correctIndices, ... }``. Single-select emits ``correct``
    (one index); multi-select emits ``correctIndices`` (graded
    all-or-nothing). Drop the result straight into a course dir.

    ``source`` is the citation shown in the post-submission review
    ("Source: ..."). It is set to a concise location — ``source_label``
    (the course) plus the question's section/module — rather than the raw
    grounding passage, so it reads as a citation. ``description``,
    ``webhook_url``/``webhook_secret``, ``pass_mark`` and
    ``questions_per_attempt`` let the caller carry over a course's existing
    exam settings so regenerating questions doesn't wipe them.
    """
    items = []
    for q in questions:
        options = list(q.all_choices)

        def _idx_of(text: str) -> int:
            # Index of a choice in `options`; append if somehow missing
            # (e.g. a key not present in option_order) rather than fail.
            try:
                return options.index(text)
            except ValueError:
                options.append(text)
                return len(options) - 1

        correct_idx = [_idx_of(t) for t in q.correct_answers]

        item = {"id": q.id, "prompt": q.stem, "options": options}
        if q.scenario:
            item["scenario"] = q.scenario
        if q.topic:
            item["module"] = q.topic
        if q.question_type == "multi" or len(correct_idx) > 1:
            item["correctIndices"] = sorted(set(correct_idx))
        else:
            item["correct"] = correct_idx[0] if correct_idx else 0
        if q.explanation:
            item["explanation"] = q.explanation
        # Citation for the results review — a concise "where to look" location,
        # not the answer-bearing source text. Prefer course + section.
        cite = (q.topic or "").strip()
        if source_label and cite:
            item["source"] = f"{source_label}: {cite}"
        elif cite:
            item["source"] = cite
        elif q.source_file:
            item["source"] = q.source_file
        items.append(item)

    # Field order mirrors a hand-authored exam.json for readable diffs.
    exam = {"title": title}
    if description:
        exam["description"] = description
    exam["passMark"] = pass_mark
    if questions_per_attempt:
        exam["questionsPerAttempt"] = questions_per_attempt
    exam["shuffle"] = bool(shuffle)
    exam["webhookUrl"] = webhook_url
    if webhook_secret:
        exam["webhookSecret"] = webhook_secret
    exam["questions"] = items
    path.write_text(json.dumps(exam, indent=2, ensure_ascii=False), encoding="utf-8")


def export_qti21(questions: List[Question], path: Path):
    """Export questions to IMS QTI 2.1 XML format (industry standard for LMS import)."""
    root = Element("assessmentTest", {
        "xmlns": "http://www.imsglobal.org/xsd/imsqti_v2p1",
        "identifier": "question_bank_export",
        "title": "Question Bank Export",
    })

    test_part = SubElement(root, "testPart", {
        "identifier": "testPart1",
        "navigationMode": "nonlinear",
        "submissionMode": "individual",
    })
    section = SubElement(test_part, "assessmentSection", {
        "identifier": "section1",
        "title": "Questions",
        "visible": "true",
    })

    for q in questions:
        item = SubElement(section, "assessmentItem", {
            "identifier": q.id,
            "title": q.stem[:60],
            "adaptive": "false",
            "timeDependent": "false",
        })

        # Response declaration
        resp_decl = SubElement(item, "responseDeclaration", {
            "identifier": "RESPONSE",
            "cardinality": "single",
            "baseType": "identifier",
        })
        correct_value = SubElement(resp_decl, "correctResponse")
        SubElement(correct_value, "value").text = "choice_key"

        # Item body
        item_body = SubElement(item, "itemBody")

        if q.scenario:
            scenario_p = SubElement(item_body, "p")
            scenario_p.text = q.scenario

        choice_interaction = SubElement(item_body, "choiceInteraction", {
            "responseIdentifier": "RESPONSE",
            "shuffle": "true",
            "maxChoices": "1",
        })
        SubElement(choice_interaction, "prompt").text = q.stem

        # Key
        key_choice = SubElement(choice_interaction, "simpleChoice", {
            "identifier": "choice_key",
        })
        key_choice.text = q.key

        # Distractors
        for i, d in enumerate(q.distractors):
            dist_choice = SubElement(choice_interaction, "simpleChoice", {
                "identifier": f"choice_d{i + 1}",
            })
            dist_choice.text = d

        # Response processing
        resp_proc = SubElement(item, "responseProcessing", {
            "template": "http://www.imsglobal.org/question/qti_v2p1/rptemplates/match_correct",
        })

    # Pretty print
    xml_str = tostring(root, encoding="unicode")
    dom = parseString(xml_str)
    path.write_text(dom.toprettyxml(indent="  "), encoding="utf-8")


def export_moodle_xml(questions: List[Question], path: Path):
    """Export questions to Moodle XML format."""
    root = Element("quiz")

    for q in questions:
        question_el = SubElement(root, "question", {"type": "multichoice"})

        # Name
        name_el = SubElement(question_el, "name")
        SubElement(name_el, "text").text = q.stem[:80]

        # Question text (scenario + stem)
        qt = SubElement(question_el, "questiontext", {"format": "html"})
        body = ""
        if q.scenario:
            body += f"<p><em>{html.escape(q.scenario)}</em></p>"
        body += f"<p>{html.escape(q.stem)}</p>"
        SubElement(qt, "text").text = body

        # General feedback (explanation)
        if q.explanation:
            fb = SubElement(question_el, "generalfeedback", {"format": "html"})
            SubElement(fb, "text").text = f"<p>{html.escape(q.explanation)}</p>"

        SubElement(question_el, "defaultgrade").text = "1"
        SubElement(question_el, "penalty").text = "0.3333333"
        SubElement(question_el, "single").text = "true"
        SubElement(question_el, "shuffleanswers").text = "true"

        # Correct answer
        ans_key = SubElement(question_el, "answer", {"fraction": "100", "format": "html"})
        SubElement(ans_key, "text").text = html.escape(q.key)

        # Distractors
        for d in q.distractors:
            ans_d = SubElement(question_el, "answer", {"fraction": "0", "format": "html"})
            SubElement(ans_d, "text").text = html.escape(d)

        # Tags
        if q.topic:
            tags_el = SubElement(question_el, "tags")
            tag_el = SubElement(tags_el, "tag")
            SubElement(tag_el, "text").text = q.topic

    xml_str = tostring(root, encoding="unicode")
    dom = parseString(xml_str)
    path.write_text(dom.toprettyxml(indent="  "), encoding="utf-8")


def export_text(questions: List[Question], path: Path, include_answers: bool = True):
    """Export questions as a formatted text document."""
    lines = ["QUESTION BANK EXPORT", "=" * 60, ""]

    for i, q in enumerate(questions, 1):
        lines.append(f"Question {i}")
        lines.append("-" * 40)
        if q.topic:
            lines.append(f"Topic: {q.topic}")
        lines.append(f"Difficulty: {q.difficulty} | Bloom: {q.bloom_level}")
        lines.append("")

        if q.scenario:
            lines.append(f"Scenario: {q.scenario}")
            lines.append("")

        lines.append(q.stem)
        lines.append("")

        # Shuffle choices for display
        choices = list(enumerate(["key"] + [f"d{j}" for j in range(len(q.distractors))]))
        answers = [q.key] + q.distractors
        indices = list(range(len(answers)))
        random.shuffle(indices)

        key_letter = ""
        for letter_idx, answer_idx in enumerate(indices):
            letter = chr(65 + letter_idx)  # A, B, C, D
            lines.append(f"  {letter}) {answers[answer_idx]}")
            if answer_idx == 0:
                key_letter = letter
        lines.append("")

        if include_answers:
            lines.append(f"Correct Answer: {key_letter}")
            if q.explanation:
                lines.append(f"Explanation: {q.explanation}")
        lines.append("")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def export_docx(questions: List[Question], path: Path):
    """Export questions to a formatted Word (.docx) document.

    Requires the python-docx package (``pip install python-docx``).
    Raises ImportError with a helpful message when the package is missing.
    """
    if not HAS_DOCX:
        raise ImportError(
            "python-docx is required for DOCX export. "
            "Install it with: pip install python-docx"
        )

    doc = Document()

    # -- Title --
    title = doc.add_heading("Question Bank Export", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    for i, q in enumerate(questions, 1):
        # -- Question number and format label --
        heading_text = f"Question {i}  —  {q.format_label}"
        doc.add_heading(heading_text, level=2)

        # -- Metadata line: Topic, Difficulty, Bloom's --
        meta_parts = []
        if q.topic:
            meta_parts.append(f"Topic: {q.topic}")
        meta_parts.append(f"Difficulty: {q.difficulty}")
        meta_parts.append(f"Bloom's Level: {q.bloom_level}")
        meta_para = doc.add_paragraph()
        meta_run = meta_para.add_run("  |  ".join(meta_parts))
        meta_run.font.size = Pt(10)
        meta_run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)

        # -- Scenario (italic) --
        if q.scenario:
            scenario_para = doc.add_paragraph()
            scenario_run = scenario_para.add_run(q.scenario)
            scenario_run.italic = True

        # -- Stem (bold) --
        stem_para = doc.add_paragraph()
        stem_run = stem_para.add_run(q.stem)
        stem_run.bold = True

        # -- Build labelled choices --
        correct_set = set(q.correct_answers)
        all_answers = [q.key] + q.distractors if q.question_type == "single" else list(q.keys) + q.distractors
        labels = [chr(65 + idx) for idx in range(len(all_answers))]  # A, B, C, D, ...

        for label, answer in zip(labels, all_answers):
            choice_para = doc.add_paragraph(style="List Bullet")
            choice_run = choice_para.add_run(f"{label}: {answer}")
            if answer in correct_set:
                choice_run.font.color.rgb = RGBColor(0x00, 0x80, 0x00)  # green
                choice_run.bold = True

        # -- Explanation --
        if q.explanation:
            doc.add_paragraph()
            exp_para = doc.add_paragraph()
            exp_label = exp_para.add_run("Explanation: ")
            exp_label.bold = True
            exp_para.add_run(q.explanation)

        # -- Horizontal rule between questions (skip after last) --
        if i < len(questions):
            hr_para = doc.add_paragraph()
            hr_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            hr_run = hr_para.add_run("_" * 72)
            hr_run.font.size = Pt(8)
            hr_run.font.color.rgb = RGBColor(0xAA, 0xAA, 0xAA)

    doc.save(str(path))
