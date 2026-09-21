"""Exam Builder tab: configure and generate PDF exam papers from the question bank."""

import time
from pathlib import Path

from nicegui import app, ui

from ..state import AppState, UIRefs
from ...core.question_bank import DIFFICULTIES
from ...core.exam_builder import (
    select_exam_questions,
    generate_exam_pdf,
    get_available_topics,
)
from ...utils.config import config


def build_exam_tab(state: AppState, refs: UIRefs):
    """Build the Exam Builder tab."""

    def _section_help(text: str):
        with ui.row().classes("w-full items-start gap-1 q-mb-sm"):
            ui.icon("help_outline", size="xs").classes("text-grey-5 q-mt-xs")
            ui.label(text).classes("text-xs text-grey-6")

    # ══════════════════════════════════════════════════════
    # ── 1. Exam Configuration ─────────────────────────────
    # ══════════════════════════════════════════════════════
    with ui.expansion("Exam Configuration", icon="tune").classes("w-full").props(
        "default-opened dense header-class=section-title"
    ):
        with ui.card().classes("w-full q-pa-md"):
            _section_help(
                "Configure your exam — set a title, select which questions to include, "
                "and distribute questions across topics by weight."
            )

            # ── 3-Column Layout ──
            with ui.row().classes("w-full gap-2 items-stretch"):

                # ── Column 1: Exam Details ──
                with ui.card().classes("q-pa-md").style("flex: 1; min-width: 220px;"):
                    ui.label("Exam Details").classes("text-xs font-semibold")
                    ui.label(
                        "Set the exam title, institution, and optional time limit."
                    ).classes("text-xs text-grey-5 q-mb-xs")

                    exam_title = ui.input(
                        label="Exam Title", value="Practice Exam",
                    ).classes("w-full").props("dense outlined").tooltip(
                        "This appears on the cover page of the PDF"
                    )
                    exam_institution = ui.input(
                        label="Institution / Course",
                    ).classes("w-full").props("dense outlined").tooltip(
                        "Optional — shown below the title on the cover page"
                    )
                    exam_time = ui.number(
                        label="Time Limit (minutes)", value=0, min=0, max=300, step=5,
                    ).classes("w-full").props("dense outlined").tooltip(
                        "Set to 0 for no time limit. Shown in the exam instructions."
                    )

                # ── Column 2: Question Source ──
                with ui.card().classes("q-pa-md").style("flex: 1; min-width: 250px;"):
                    ui.label("Question Source").classes("text-xs font-semibold")
                    ui.label(
                        "Choose certifications, difficulty levels, and approval statuses to draw questions from."
                    ).classes("text-xs text-grey-5 q-mb-xs")

                    certs = state.db.list_certifications()
                    cert_options = {c.id: f"{c.name} ({state.db.count_by_certification(c.id)} Q)" for c in certs}

                    cert_select = ui.select(
                        options=cert_options,
                        label="Certifications",
                        multiple=True,
                    ).classes("w-full").props("dense outlined use-chips").tooltip(
                        "Select one or more certifications to draw questions from"
                    )

                    with ui.row().classes("w-full gap-2"):
                        exam_total = ui.number(
                            label="Total Questions", value=20, min=1, max=500, step=1,
                        ).classes("w-36").props("dense outlined").tooltip(
                            "How many questions to include in the exam"
                        )

                        diff_select = ui.select(
                            options=DIFFICULTIES,
                            value=list(DIFFICULTIES),
                            label="Difficulties",
                            multiple=True,
                        ).classes("flex-grow").props("dense outlined use-chips").tooltip(
                            "Filter by difficulty — defaults to all levels"
                        )

                    ui.label("Include questions with status:").classes("text-xs text-grey-6 q-mt-xs")
                    with ui.row().classes("gap-2"):
                        status_draft = ui.checkbox("Draft", value=False, on_change=lambda e: _refresh_topics())
                        status_sme = ui.checkbox("SME Review", value=False, on_change=lambda e: _refresh_topics())
                        status_approved = ui.checkbox("Approved", value=True, on_change=lambda e: _refresh_topics())

                    status_fallback_label = ui.label("").classes("text-xs text-orange")

                    with ui.row().classes("items-center gap-1 q-mt-xs"):
                        ui.icon("info_outline", size="xs").classes("text-grey-5")
                        available_label = ui.label("").classes("text-xs text-grey-6")

                # ── Column 3: Topic Weighting ──
                with ui.card().classes("q-pa-md").style("flex: 1; min-width: 220px;"):
                    ui.label("Topic Weighting").classes("text-xs font-semibold")
                    ui.label(
                        "Set what percentage of questions should come from each topic. "
                        "Weights must sum to ~100%."
                    ).classes("text-xs text-grey-5 q-mb-xs")

                    with ui.row().classes("items-center gap-2"):
                        ui.button("Distribute Evenly", icon="balance", on_click=lambda: _distribute_evenly()).props(
                            "flat dense size=sm"
                        ).tooltip("Split weights equally across all topics")
                        ui.icon("scale", size="xs").classes("text-grey-5")
                        weight_total_label = ui.label("Total: 0%").classes("text-sm font-bold")

                    topics_container = ui.column().classes("w-full gap-1 q-mt-xs")
                    topic_weights_ui = {}

    # ══════════════════════════════════════════════════════
    # ── 2. PDF Options ────────────────────────────────────
    # ══════════════════════════════════════════════════════
    with ui.expansion("PDF Options", icon="settings").classes("w-full").props(
        "default-opened dense header-class=section-title"
    ):
        with ui.card().classes("w-full q-pa-md"):
            _section_help(
                "Control the format of the generated PDF — randomization, answer key, "
                "scenarios, and explanations."
            )
            with ui.row().classes("gap-4 flex-wrap"):
                opt_randomize = ui.switch("Randomize question order", value=True).tooltip(
                    "Shuffle questions within each topic section"
                )
                opt_randomize_choices = ui.switch("Randomize answer choices", value=True).tooltip(
                    "Shuffle A/B/C/D order for each question"
                )
                opt_answer_key = ui.switch("Include answer key", value=True).tooltip(
                    "Add an answer key page at the end of the PDF"
                )
                opt_scenarios = ui.switch("Include scenarios", value=True).tooltip(
                    "Show the real-world scenario context before each question"
                )
                opt_explanations = ui.switch("Include explanations in answer key", value=False).tooltip(
                    "Add detailed explanations to the answer key — only used when answer key is included"
                )

            # Disable explanations toggle when answer key is off
            def _on_answer_key_change(e):
                if not e.value:
                    opt_explanations.value = False
                    opt_explanations.set_enabled(False)
                else:
                    opt_explanations.set_enabled(True)
            opt_answer_key.on_value_change(_on_answer_key_change)

    # ── Generate Button & Status ──────────────────────────
    with ui.row().classes("w-full gap-2 items-center"):
        generate_btn = ui.button(
            "Generate Exam PDF", icon="picture_as_pdf",
            on_click=lambda: _generate_exam(),
        ).props("color=primary dense").tooltip(
            "Build a formatted PDF exam paper from your question bank"
        )
        status_label = ui.label("").classes("text-xs text-grey-6")

    # ══════════════════════════════════════════════════════
    # ── 3. PDF Preview ────────────────────────────────────
    # ══════════════════════════════════════════════════════
    with ui.expansion("PDF Preview", icon="picture_as_pdf").classes("w-full").props(
        "default-opened dense header-class=section-title"
    ):
        with ui.card().classes("w-full q-pa-md").style("min-height: 200px;"):
            pdf_preview_container = ui.column().classes("w-full items-center")
            with pdf_preview_container:
                # Friendly empty state
                ui.icon("picture_as_pdf", size="48px").classes("text-grey-4")
                ui.label("No exam generated yet").classes("text-base text-grey-5")
                with ui.column().classes("items-start gap-1 q-mt-xs"):
                    with ui.row().classes("items-center gap-2"):
                        ui.badge("1").props("color=primary").classes("text-xs").style("min-width: 20px; text-align: center")
                        ui.label("Select certifications and set topic weights above").classes("text-xs text-grey-5")
                    with ui.row().classes("items-center gap-2"):
                        ui.badge("2").props("color=primary").classes("text-xs").style("min-width: 20px; text-align: center")
                        ui.label("Configure PDF options (answer key, randomization)").classes("text-xs text-grey-5")
                    with ui.row().classes("items-center gap-2"):
                        ui.badge("3").props("color=primary").classes("text-xs").style("min-width: 20px; text-align: center")
                        ui.label("Click Generate Exam PDF").classes("text-xs text-grey-5")

    # ── Logic ─────────────────────────────────────────────

    def _refresh_topics():
        cert_ids = cert_select.value or []
        if isinstance(cert_ids, str):
            cert_ids = [cert_ids]

        statuses = _get_statuses()

        # Show fallback warning
        all_unchecked = not status_draft.value and not status_sme.value and not status_approved.value
        if all_unchecked:
            status_fallback_label.set_text("No status selected — defaults to Approved")
        else:
            status_fallback_label.set_text("")

        topics = get_available_topics(state.db, cert_ids, statuses=statuses)

        total_available = sum(topics.values())
        status_str = ", ".join(statuses)
        available_label.set_text(
            f"{total_available} question(s) ({status_str}) across {len(topics)} topic(s)"
        )

        topics_container.clear()
        topic_weights_ui.clear()

        if not topics:
            with topics_container:
                with ui.column().classes("w-full items-center q-pa-sm gap-1"):
                    ui.icon("topic", size="md").classes("text-grey-4")
                    ui.label("Select certifications above to see available topics and set weights.").classes(
                        "text-xs text-grey-5 text-center"
                    )
            _update_weight_total()
            return

        even_weight = round(100 / len(topics), 1) if topics else 0

        with topics_container:
            for topic_name, count in topics.items():
                with ui.row().classes("w-full items-center gap-2"):
                    ui.label(f"{topic_name} ({count} Q)").classes("text-xs flex-grow")
                    w = ui.number(
                        value=even_weight, min=0, max=100, step=0.5,
                        on_change=lambda e: _update_weight_total(),
                    ).classes("w-20").props("dense outlined suffix=%")
                    topic_weights_ui[topic_name] = w

        _update_weight_total()

    def _update_weight_total():
        total = sum(w.value or 0 for w in topic_weights_ui.values())
        is_ok = abs(total - 100) < 0.5
        color = "text-positive" if is_ok else "text-negative"
        icon_name = "check_circle" if is_ok else "warning"
        icon_color = "positive" if is_ok else "negative"
        weight_total_label.set_text(f"Total: {total:.1f}%")
        weight_total_label.classes(replace=f"text-sm font-bold {color}")

    def _distribute_evenly():
        if not topic_weights_ui:
            return
        even = round(100 / len(topic_weights_ui), 1)
        for w in topic_weights_ui.values():
            w.value = even
        _update_weight_total()

    def _get_statuses():
        statuses = []
        if status_draft.value:
            statuses.append("draft")
        if status_sme.value:
            statuses.append("sme_review")
        if status_approved.value:
            statuses.append("approved")
        return statuses or ["approved"]

    def _generate_exam():
        cert_ids = cert_select.value or []
        if isinstance(cert_ids, str):
            cert_ids = [cert_ids]
        if not cert_ids:
            ui.notify("Select at least one certification", type="warning")
            return

        difficulties = diff_select.value or list(DIFFICULTIES)
        if isinstance(difficulties, str):
            difficulties = [difficulties]

        weights = {topic: (w.value or 0) for topic, w in topic_weights_ui.items()}
        active_weights = {t: v for t, v in weights.items() if v > 0}

        if not active_weights:
            ui.notify("Set topic weights — at least one topic needs a weight above 0%", type="warning")
            return

        total_weight = sum(active_weights.values())
        if abs(total_weight - 100) > 1:
            ui.notify(f"Topic weights sum to {total_weight:.1f}% — adjust to be close to 100%", type="warning")
            return

        total_q = int(exam_total.value or 20)
        statuses = _get_statuses()

        status_label.set_text("Selecting questions...")

        try:
            questions = select_exam_questions(
                db=state.db,
                certification_ids=cert_ids,
                total_questions=total_q,
                difficulties=difficulties,
                topic_weights=active_weights,
                statuses=statuses,
                randomize=opt_randomize.value,
            )
        except Exception as e:
            ui.notify(f"Selection failed: {e}", type="negative")
            status_label.set_text("")
            return

        if not questions:
            ui.notify("No questions matched your criteria — try adjusting filters", type="warning")
            status_label.set_text("")
            return

        if len(questions) < total_q:
            ui.notify(
                f"Only {len(questions)} questions available (requested {total_q})",
                type="info",
            )

        status_label.set_text(f"Generating PDF with {len(questions)} questions...")

        out_dir = Path(config.output_folder)
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in (exam_title.value or "exam"))
        out_path = out_dir / f"{safe_title.strip().replace(' ', '_')}.pdf"

        try:
            path = generate_exam_pdf(
                questions=questions,
                title=exam_title.value or "Practice Exam",
                institution=exam_institution.value or "",
                time_limit=int(exam_time.value or 0),
                include_answer_key=opt_answer_key.value,
                randomize_choices=opt_randomize_choices.value,
                include_scenarios=opt_scenarios.value,
                include_explanations=opt_explanations.value,
                output_path=out_path,
            )
            ui.download(path)
            status_label.set_text(f"Exported {len(questions)} questions → {path.name}")
            ui.notify(f"Exam PDF generated: {path.name}", type="positive")
            _show_pdf_preview(path)

        except Exception as e:
            ui.notify(f"PDF generation failed: {e}", type="negative")
            status_label.set_text("")

    def _show_pdf_preview(pdf_path: Path):
        url_path = "/exam_output"
        try:
            app.add_static_files(url_path, str(pdf_path.parent))
        except Exception:
            pass

        cache_bust = int(time.time())
        pdf_url = f"{url_path}/{pdf_path.name}?t={cache_bust}"

        pdf_preview_container.clear()
        with pdf_preview_container:
            ui.html(
                f'<iframe src="{pdf_url}" '
                f'width="100%" height="700" '
                f'style="border: 1px solid #ccc; border-radius: 4px;" '
                f'loading="lazy"></iframe>'
            ).classes("w-full")

            with ui.row().classes("w-full justify-center gap-4 q-mt-xs"):
                ui.link("Open PDF in new tab", pdf_url, new_tab=True).classes("text-xs")
                ui.button("Download PDF", icon="download",
                          on_click=lambda: ui.download(pdf_path)).props("flat dense size=sm")

    # Wire up cert selection change to refresh topics
    cert_select.on_value_change(lambda e: _refresh_topics())

    # Initial state
    _refresh_topics()
