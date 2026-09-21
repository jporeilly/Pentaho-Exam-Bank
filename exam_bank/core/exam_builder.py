"""Exam Builder: select questions by topic weighting and generate formatted PDF exams."""

import random
import string
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fpdf import FPDF

from .bank import Question, ExamBankDB


def select_exam_questions(
    db: ExamBankDB,
    certification_ids: List[str],
    total_questions: int,
    difficulties: List[str],
    topic_weights: Dict[str, float],
    statuses: List[str] = None,
    randomize: bool = True,
    seed: Optional[int] = None,
) -> List[Question]:
    """Select questions from the bank according to topic weighting.

    Args:
        db: exam bank database
        certification_ids: certifications to draw from
        total_questions: desired number of questions
        difficulties: which difficulty levels to include
        topic_weights: {topic_name: percentage} — must sum to ~100
        statuses: which statuses to include (default: approved only)
        randomize: shuffle within each topic group
        seed: optional random seed for reproducibility

    Returns:
        Ordered list of selected questions, grouped by topic.
    """
    if statuses is None:
        statuses = ["approved"]
    rng = random.Random(seed)

    # Calculate per-topic targets
    targets = {}
    for topic, weight in topic_weights.items():
        targets[topic] = round(total_questions * weight / 100)

    # Adjust rounding to hit exact total
    diff = total_questions - sum(targets.values())
    if diff != 0:
        # Add/remove from the topic with the largest weight
        largest = max(topic_weights, key=topic_weights.get)
        targets[largest] += diff

    # Collect question pools per topic
    pools: Dict[str, List[Question]] = {}
    for topic in topic_weights:
        topic_qs = []
        for cert_id in certification_ids:
            for status in statuses:
                for difficulty in difficulties:
                    results = db.search(
                        topic=topic,
                        certification_id=cert_id,
                        difficulty=difficulty,
                        status=status,
                        limit=500,
                    )
                    topic_qs.extend(results)
        # Deduplicate by ID
        seen = set()
        unique = []
        for q in topic_qs:
            if q.id not in seen:
                seen.add(q.id)
                unique.append(q)
        pools[topic] = unique

    # Select from each pool, redistribute shortfalls
    selected: Dict[str, List[Question]] = {}
    shortfall = 0
    surplus_topics = []

    for topic, target in targets.items():
        pool = pools.get(topic, [])
        if len(pool) <= target:
            selected[topic] = list(pool)
            shortfall += target - len(pool)
        else:
            if randomize:
                selected[topic] = rng.sample(pool, target)
            else:
                selected[topic] = pool[:target]
            surplus_topics.append(topic)

    # Redistribute shortfall to topics with surplus
    if shortfall > 0 and surplus_topics:
        for topic in surplus_topics:
            if shortfall <= 0:
                break
            pool = pools[topic]
            already = {q.id for q in selected[topic]}
            available = [q for q in pool if q.id not in already]
            take = min(shortfall, len(available))
            if take > 0:
                extras = rng.sample(available, take) if randomize else available[:take]
                selected[topic].extend(extras)
                shortfall -= take

    # Build final list, grouped by topic
    result = []
    for topic in topic_weights:
        group = selected.get(topic, [])
        if randomize:
            rng.shuffle(group)
        result.extend(group)

    return result


class ExamPDF(FPDF):
    """Custom PDF with headers and footers for exam papers."""

    # Theme colours
    ACCENT = (41, 65, 122)        # deep navy
    ACCENT_LIGHT = (88, 130, 196) # lighter blue
    MUTED = (130, 130, 130)
    RULE = (210, 210, 210)

    def __init__(self, title: str = "Exam", **kwargs):
        super().__init__(**kwargs)
        self.exam_title = title
        self._in_answer_key = False
        self._is_cover = True

    def header(self):
        if self._is_cover:
            return
        # Left: title, Right: section label
        self.set_font("Helvetica", "", 7.5)
        self.set_text_color(*self.MUTED)
        self.cell(0, 5, self.exam_title, align="L")
        section = "ANSWER KEY" if self._in_answer_key else "QUESTIONS"
        self.cell(0, 5, section, align="R", new_x="LMARGIN", new_y="NEXT")
        # Thin accent rule
        self.set_draw_color(*self.ACCENT_LIGHT)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y() + 1, self.w - self.r_margin, self.get_y() + 1)
        self.set_line_width(0.2)
        self.set_draw_color(0, 0, 0)
        self.set_text_color(0, 0, 0)
        self.ln(5)

    def footer(self):
        if self._is_cover:
            return
        self.set_y(-14)
        self.set_draw_color(*self.RULE)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.set_draw_color(0, 0, 0)
        self.set_y(-12)
        self.set_font("Helvetica", "", 7.5)
        self.set_text_color(*self.MUTED)
        self.cell(0, 8, f"Page {self.page_no()} of {{nb}}", align="C")
        self.set_text_color(0, 0, 0)


def _latin1_safe(text: str) -> str:
    """Replace Unicode characters unsupported by Helvetica (latin-1) with safe equivalents."""
    replacements = {
        '\u2014': '-',   # em dash
        '\u2013': '-',   # en dash
        '\u2018': "'",   # left single quote
        '\u2019': "'",   # right single quote
        '\u201c': '"',   # left double quote
        '\u201d': '"',   # right double quote
        '\u2026': '...', # ellipsis
        '\u2022': '-',   # bullet
        '\u00b7': '-',   # middle dot
        '\u2010': '-',   # hyphen
        '\u2011': '-',   # non-breaking hyphen
        '\u2012': '-',   # figure dash
        '\u00a0': ' ',   # non-breaking space
        '\u200b': '',    # zero-width space
        '\u2003': ' ',   # em space
        '\u2002': ' ',   # en space
    }
    for ch, repl in replacements.items():
        text = text.replace(ch, repl)
    # Fallback: replace any remaining non-latin-1 chars
    return text.encode('latin-1', errors='replace').decode('latin-1')


def _rule(pdf: FPDF, y: float = None, margin: float = 0, color=None):
    """Draw a thin horizontal line across the page."""
    if y is None:
        y = pdf.get_y()
    c = color or ExamPDF.RULE
    pdf.set_draw_color(*c)
    pdf.line(pdf.l_margin + margin, y, pdf.w - pdf.r_margin - margin, y)
    pdf.set_draw_color(0, 0, 0)


def _accent_bar(pdf: FPDF, x: float, y: float, h: float, w: float = 0.7):
    """Draw a vertical accent bar."""
    pdf.set_draw_color(*ExamPDF.ACCENT)
    pdf.set_line_width(w)
    pdf.line(x, y, x, y + h)
    pdf.set_line_width(0.2)
    pdf.set_draw_color(0, 0, 0)


def generate_exam_pdf(
    questions: List[Question],
    title: str = "Practice Exam",
    institution: str = "",
    time_limit: int = 0,
    include_answer_key: bool = True,
    randomize_choices: bool = True,
    include_scenarios: bool = True,
    include_explanations: bool = False,
    seed: Optional[int] = None,
    output_path: Optional[Path] = None,
) -> Path:
    """Generate a formatted PDF exam paper.

    Returns the path to the generated PDF file.
    """
    if output_path is None:
        output_path = Path("exam_output.pdf")

    ACCENT = ExamPDF.ACCENT
    ACCENT_LIGHT = ExamPDF.ACCENT_LIGHT
    MUTED = ExamPDF.MUTED

    # Sanitize all user-facing strings for latin-1 compatibility
    title = _latin1_safe(title)
    institution = _latin1_safe(institution)

    rng = random.Random(seed)
    pdf = ExamPDF(title=title)
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=18)

    # ── Cover Page ──────────────────────────────────────
    pdf.add_page()
    pdf._is_cover = True
    page_w = pdf.w - pdf.l_margin - pdf.r_margin

    # Top accent band — double line
    pdf.ln(15)
    y = pdf.get_y()
    pdf.set_draw_color(*ACCENT)
    pdf.set_line_width(1.2)
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.set_draw_color(*ACCENT_LIGHT)
    pdf.set_line_width(0.3)
    pdf.line(pdf.l_margin, y + 2.5, pdf.w - pdf.r_margin, y + 2.5)
    pdf.set_line_width(0.2)
    pdf.set_draw_color(0, 0, 0)
    pdf.ln(12)

    # Institution / Course
    if institution:
        pdf.set_font("Helvetica", "", 12)
        pdf.set_text_color(*MUTED)
        pdf.cell(0, 8, institution.upper(), align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(3)

    # Exam title
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(*ACCENT)
    pdf.cell(0, 16, title, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    # Decorative centre rule
    center_x = pdf.w / 2
    pdf.set_draw_color(*ACCENT_LIGHT)
    pdf.set_line_width(0.4)
    pdf.line(center_x - 30, pdf.get_y(), center_x + 30, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.set_draw_color(0, 0, 0)
    pdf.ln(8)

    # Summary pills — question count, time
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*MUTED)
    parts = [f"{len(questions)} Questions"]
    if time_limit:
        parts.append(f"{time_limit} Minutes")
    pdf.cell(0, 7, "    |    ".join(parts), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)

    # Topic breakdown (if multiple topics)
    topic_counts = {}
    for q in questions:
        t = q.topic or "General"
        topic_counts[t] = topic_counts.get(t, 0) + 1
    if len(topic_counts) > 1:
        pdf.ln(1)
        pdf.set_font("Helvetica", "I", 8.5)
        pdf.set_text_color(*MUTED)
        topics_str = "   |   ".join(f"{t} ({c})" for t, c in sorted(topic_counts.items()))
        pdf.multi_cell(0, 5, topics_str, align="C")
        pdf.set_text_color(0, 0, 0)

    # ── Candidate Information ────────────────────────────
    pdf.ln(18)

    # Section label with small caps feel
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*ACCENT)
    pdf.cell(0, 6, "CANDIDATE INFORMATION", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    field_label_w = 32
    field_line_w = page_w - field_label_w
    fields = [
        ("Full Name", ""),
        ("Company", ""),
        ("Business Unit", ""),
        ("Date", datetime.now().strftime("%B %d, %Y")),
    ]
    for label, default_val in fields:
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(60, 60, 60)
        pdf.cell(field_label_w, 9, label)
        pdf.set_text_color(0, 0, 0)
        # Dotted underline for write-in
        line_y = pdf.get_y() + 8.5
        line_x = pdf.l_margin + field_label_w
        pdf.set_draw_color(*ExamPDF.RULE)
        pdf.set_dash_pattern(dash=1, gap=1)
        pdf.line(line_x, line_y, line_x + field_line_w, line_y)
        pdf.set_dash_pattern()
        pdf.set_draw_color(0, 0, 0)
        if default_val:
            pdf.set_font("Helvetica", "I", 9)
            pdf.set_text_color(*MUTED)
            pdf.cell(field_line_w, 9, f"  {default_val}")
            pdf.set_text_color(0, 0, 0)
        pdf.ln(11)

    # ── Instructions ─────────────────────────────────────
    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*ACCENT)
    pdf.cell(0, 6, "INSTRUCTIONS", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 9.5)
    multi_count = sum(1 for q in questions if q.question_type == "multi")
    instructions = [
        "Read each question carefully before selecting your answer.",
        "Choose the best answer for each question.",
    ]
    if multi_count:
        instructions.append(
            f"{multi_count} question(s) require multiple answers - marked with 'Choose N'."
        )
    if time_limit:
        instructions.append(f"You have {time_limit} minutes to complete this exam.")
    instructions.append("Do not leave any questions unanswered.")

    for instr in instructions:
        y_b = pdf.get_y() + 2
        # Small square bullet
        pdf.set_fill_color(*ACCENT_LIGHT)
        pdf.rect(pdf.l_margin + 4, y_b, 1.8, 1.8, style="F")
        pdf.set_fill_color(255, 255, 255)
        pdf.set_x(pdf.l_margin + 10)
        pdf.multi_cell(page_w - 10, 5.5, instr)
        pdf.ln(1)

    # Bottom accent band — mirror of top
    pdf.ln(8)
    y = pdf.get_y()
    pdf.set_draw_color(*ACCENT_LIGHT)
    pdf.set_line_width(0.3)
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.set_draw_color(*ACCENT)
    pdf.set_line_width(1.2)
    pdf.line(pdf.l_margin, y + 2.5, pdf.w - pdf.r_margin, y + 2.5)
    pdf.set_line_width(0.2)
    pdf.set_draw_color(0, 0, 0)

    # ── Questions (start on page 2) ──────────────────────
    pdf._is_cover = False
    pdf.add_page()

    answer_key = []  # [(question_num, answer_letters, explanation)]
    current_topic = None

    for qi, q in enumerate(questions):
        qnum = qi + 1

        # Topic section header
        topic_label = _latin1_safe(q.topic or "General")
        if topic_label != current_topic:
            current_topic = topic_label
            if pdf.get_y() > pdf.h - 60:
                pdf.add_page()
            elif qnum > 1:
                pdf.ln(8)

            y_top = pdf.get_y()
            # Shaded banner with left accent bar
            pdf.set_fill_color(240, 244, 250)
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*ACCENT)
            pdf.cell(0, 8, f"   {current_topic}", fill=True, new_x="LMARGIN", new_y="NEXT")
            _accent_bar(pdf, pdf.l_margin, y_top, 8, w=1.0)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(5)

        # Space check
        if pdf.get_y() > pdf.h - 55:
            pdf.add_page()

        # Scenario
        if include_scenarios and q.scenario:
            pdf.set_font("Helvetica", "I", 9)
            pdf.set_text_color(90, 90, 90)
            # Indent with a subtle left border
            y_sc = pdf.get_y()
            pdf.set_x(pdf.l_margin + 8)
            pdf.multi_cell(page_w - 8, 5, _latin1_safe(q.scenario))
            _accent_bar(pdf, pdf.l_margin + 4, y_sc, pdf.get_y() - y_sc, w=0.4)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(2)

        # Question number + stem
        num_correct = len(q.correct_answers)

        # Number badge
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*ACCENT)
        num_text = f"{qnum}."
        num_w = pdf.get_string_width(num_text) + 2
        pdf.cell(num_w, 6, num_text)

        # Stem text in dark
        pdf.set_text_color(30, 30, 30)
        pdf.set_font("Helvetica", "B", 10)
        stem_text = _latin1_safe(q.stem)
        if num_correct > 1:
            stem_text += f"  (Choose {num_correct})"
        pdf.multi_cell(0, 6, f" {stem_text}")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)

        # Shuffle choices
        correct_set = set(q.correct_answers)
        all_choices = list(q.correct_answers) + list(q.distractors)
        if randomize_choices:
            rng.shuffle(all_choices)

        # Render choices with circle bullets
        correct_letters = []
        for ci, choice in enumerate(all_choices):
            letter = string.ascii_uppercase[ci] if ci < 26 else str(ci + 1)
            y_ch = pdf.get_y()

            # Open circle bullet
            pdf.set_draw_color(*ACCENT_LIGHT)
            pdf.ellipse(pdf.l_margin + 10, y_ch + 1.5, 3, 3, style="D")
            pdf.set_draw_color(0, 0, 0)

            # Letter inside circle
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(*ACCENT)
            pdf.set_xy(pdf.l_margin + 10, y_ch + 1)
            pdf.cell(3, 3.5, letter, align="C")

            # Choice text
            pdf.set_xy(pdf.l_margin + 16, y_ch)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(40, 40, 40)
            pdf.multi_cell(page_w - 16, 5.5, _latin1_safe(choice))
            pdf.set_text_color(0, 0, 0)
            pdf.ln(1)

            if choice in correct_set:
                correct_letters.append(letter)

        answer_key.append((qnum, ", ".join(correct_letters), q.explanation or ""))
        pdf.ln(3)

        # Subtle dotted separator between questions in the same topic
        if qi < len(questions) - 1:
            next_topic = questions[qi + 1].topic or "General"
            if next_topic == current_topic:
                y_sep = pdf.get_y()
                pdf.set_draw_color(*ExamPDF.RULE)
                pdf.set_dash_pattern(dash=1.5, gap=1.5)
                pdf.line(pdf.l_margin + 15, y_sep, pdf.w - pdf.r_margin - 15, y_sep)
                pdf.set_dash_pattern()
                pdf.set_draw_color(0, 0, 0)
                pdf.ln(3)

    # ── Answer Key ──────────────────────────────────────
    if include_answer_key:
        pdf._in_answer_key = True
        pdf.add_page()

        # Title
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(*ACCENT)
        pdf.cell(0, 10, "ANSWER KEY", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(1)
        _rule(pdf, color=ACCENT_LIGHT)
        pdf.ln(6)

        if include_explanations:
            # Full-width layout with explanations
            for idx, (qnum, letters, explanation) in enumerate(answer_key):
                if pdf.get_y() > pdf.h - 30:
                    pdf.add_page()

                y_top = pdf.get_y()
                # Question number
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(*ACCENT)
                pdf.cell(14, 6, f"{qnum}.")
                # Answer letters
                pdf.set_text_color(30, 30, 30)
                pdf.cell(0, 6, letters, new_x="LMARGIN", new_y="NEXT")

                # Explanation
                if explanation:
                    pdf.set_font("Helvetica", "", 9)
                    pdf.set_text_color(80, 80, 80)
                    pdf.set_x(pdf.l_margin + 14)
                    pdf.multi_cell(page_w - 14, 5, _latin1_safe(explanation))
                    pdf.set_text_color(0, 0, 0)

                # Left accent bar spanning the entry
                _accent_bar(pdf, pdf.l_margin + 4, y_top, pdf.get_y() - y_top, w=0.3)
                pdf.ln(3)

                # Separator between entries
                if idx < len(answer_key) - 1:
                    _rule(pdf, margin=10)
                    pdf.ln(3)
        else:
            # Compact three-column grid
            col_count = 3
            col_w = page_w / col_count
            col = 0
            row_y = pdf.get_y()

            for idx, (qnum, letters, _) in enumerate(answer_key):
                x = pdf.l_margin + col * col_w

                if col == 0 and pdf.get_y() > pdf.h - 18:
                    pdf.add_page()
                    row_y = pdf.get_y()

                pdf.set_xy(x, row_y)
                pdf.set_font("Helvetica", "B", 9.5)
                pdf.set_text_color(*ACCENT)
                pdf.cell(12, 7, f"{qnum}.")
                pdf.set_font("Helvetica", "", 9.5)
                pdf.set_text_color(40, 40, 40)
                pdf.cell(col_w - 12, 7, letters)
                pdf.set_text_color(0, 0, 0)

                col += 1
                if col >= col_count:
                    col = 0
                    row_y += 7
                    pdf.set_y(row_y)

            if col != 0:
                pdf.set_y(row_y + 7)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(output_path))
    return output_path


def get_available_topics(
    db: ExamBankDB,
    certification_ids: List[str],
    statuses: Optional[List[str]] = None,
) -> Dict[str, int]:
    """Get topics and question counts for given certifications.

    Returns {topic_name: count} sorted by topic name.
    """
    if not certification_ids:
        return {}
    if statuses is None:
        statuses = ["approved"]
    cert_ph = ",".join("?" * len(certification_ids))
    status_ph = ",".join("?" * len(statuses))
    params = certification_ids + statuses
    rows = db.conn.execute(
        f"SELECT topic, COUNT(*) FROM questions "
        f"WHERE certification_id IN ({cert_ph}) AND topic IS NOT NULL AND topic != '' "
        f"AND status IN ({status_ph}) "
        f"GROUP BY topic ORDER BY topic",
        params,
    ).fetchall()
    return {row[0]: row[1] for row in rows}
