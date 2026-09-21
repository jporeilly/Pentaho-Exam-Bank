"""Exam bank browser: search, filter, lifecycle management, and export."""


import json
import string
from pathlib import Path

from nicegui import ui

from ..state import (
    AppState, UIRefs,
    EVT_BANK_CHANGED, EVT_STATS_CHANGED, EVT_ADMIN_CHANGED, EVT_CERTIFICATIONS_CHANGED,
)
from ...core.bank import (
    Question, BLOOM_LEVELS, DIFFICULTIES, STATUSES, STATUS_LABELS, STATUS_TRANSITIONS,
)
from ...core.exporter import export_csv, export_json, export_qti21, export_moodle_xml, export_text, export_docx, export_pcm_exam_json
from ...core.db_backup import list_backups, create_backup, restore_backup, delete_backup, get_db_info
from ..styles import format_explanation_html
from .docs_chat import _MERMAID_BLOCK_RE, _render_rich_content
from ...utils.config import config


def build_bank_browser(state: AppState, refs: UIRefs):
    """Build the exam bank browser with search, filters, lifecycle, and export."""

    def _section_help(text: str):
        with ui.row().classes("w-full items-start gap-1 q-mb-sm"):
            ui.icon("help_outline", size="xs").classes("text-grey-5 q-mt-xs")
            ui.label(text).classes("text-xs text-grey-6")

    # ══════════════════════════════════════════════════════
    # ── 1. Dashboard ──────────────────────────────────────
    # ══════════════════════════════════════════════════════
    with ui.expansion("Dashboard", icon="dashboard").classes("w-full").props(
        "default-opened dense header-class=section-title"
    ):
        with ui.card().classes("w-full q-pa-md"):
            _section_help(
                "Overview of your exam bank — status counts, approval progress, "
                "difficulty distribution, and topics that need more questions."
            )
            stats_container = ui.column().classes("w-full gap-0")

    def refresh_stats():
        stats_container.clear()
        with stats_container:
            total = state.db.count()
            if not total:
                with ui.column().classes("w-full items-center q-pa-md"):
                    ui.icon("storage", size="48px").classes("text-grey-4")
                    ui.label("No questions in the bank yet").classes("text-base text-grey-5")
                    ui.label(
                        "Generate questions from the Generate tab, or import existing ones from the Import tab."
                    ).classes("text-xs text-grey-5 text-center")
                return

            draft = state.db.count("draft")
            sme_review = state.db.count("sme_review")
            revised = state.db.count("revised")
            approved = state.db.count("approved")
            rejected = state.db.count("rejected")
            retired = state.db.count("retired")

            # Status badges
            with ui.row().classes("gap-2 flex-wrap"):
                ui.badge(f"{total} total").props("color=grey-7")
                ui.badge(f"{draft} draft").props("color=amber")
                ui.badge(f"{sme_review} SME review").props("color=blue")
                ui.badge(f"{revised} revised").props("color=cyan")
                ui.badge(f"{approved} approved").props("color=green")
                if rejected:
                    ui.badge(f"{rejected} rejected").props("color=red")
                if retired:
                    ui.badge(f"{retired} retired").props("color=grey")

            # Approval progress
            pct = int(approved / total * 100)
            with ui.row().classes("w-full items-center gap-2 q-mt-xs"):
                ui.label("Approved:").classes("text-xs text-grey-6")
                ui.linear_progress(value=approved / total, size="12px").props(
                    f"color={'positive' if pct >= 80 else 'warning' if pct >= 50 else 'negative'}"
                ).classes("flex-grow").style("max-width: 200px;")
                ui.label(f"{approved} of {total} ({pct}%)").classes("text-xs font-bold")

            # Difficulty distribution
            easy_c = state.db.search_count(difficulty="Easy")
            med_c = state.db.search_count(difficulty="Medium")
            hard_c = state.db.search_count(difficulty="Hard")
            if easy_c or med_c or hard_c:
                with ui.row().classes("gap-1 q-mt-xs"):
                    if easy_c:
                        ui.badge(f"Easy: {easy_c}", color="green").props("outline").classes("text-xs")
                    if med_c:
                        ui.badge(f"Medium: {med_c}", color="orange").props("outline").classes("text-xs")
                    if hard_c:
                        ui.badge(f"Hard: {hard_c}", color="red").props("outline").classes("text-xs")

            # Coverage alert
            topics = state.db.get_topics()
            low_topics = []
            for t in topics:
                tc = state.db.search_count(topic=t)
                if tc < 5:
                    low_topics.append(f"{t} ({tc})")
            if low_topics:
                with ui.row().classes("gap-1 items-center q-mt-xs"):
                    ui.icon("warning", color="orange", size="xs")
                    ui.label(f"Low coverage (< 5 questions): {', '.join(low_topics[:5])}").classes(
                        "text-xs text-orange"
                    )

    state.bus.on(EVT_STATS_CHANGED, refresh_stats)
    refresh_stats()

    # ══════════════════════════════════════════════════════
    # ── 2. Search & Filters ───────────────────────────────
    # ══════════════════════════════════════════════════════
    with ui.expansion("Search & Filters", icon="filter_list").classes("w-full").props(
        "default-opened dense header-class=section-title"
    ):
        with ui.card().classes("w-full q-pa-md"):
            _section_help(
                "Search by keyword and narrow results using any combination of filters. "
                "All filters are AND-combined. Click Search or press Enter to apply."
            )

            with ui.element("div").classes("w-full").style(
                "display: flex; flex-wrap: wrap; gap: 8px; align-items: flex-end;"
            ):
                search_input = ui.input(
                    placeholder="Search questions...",
                ).style("flex: 2 1 200px;").props("dense outlined clearable")
                search_input.on("keydown.enter", lambda: _reset_and_refresh())

                certs = state.db.list_certifications()
                cert_options = {"": "All"} | {c.id: c.name for c in certs}
                filter_cert = ui.select(
                    options=cert_options,
                    label="Certification",
                    on_change=lambda e: _reset_and_refresh(),
                ).props("dense outlined clearable").style("flex: 1 1 140px;")

                topic_options = {"": "All"} | {t: t for t in state.db.get_topics()}
                filter_topic = ui.select(
                    options=topic_options,
                    label="Topic",
                    on_change=lambda e: _reset_and_refresh(),
                ).props("dense outlined clearable").style("flex: 1 1 120px;")

                diff_options = {"": "All"} | {d: d for d in DIFFICULTIES}
                filter_diff = ui.select(
                    options=diff_options,
                    label="Difficulty",
                    on_change=lambda e: _reset_and_refresh(),
                ).props("dense outlined clearable").style("flex: 1 1 100px;")

                bloom_options = {"": "All"} | {b: b for b in BLOOM_LEVELS}
                filter_bloom = ui.select(
                    options=bloom_options,
                    label="Bloom",
                    on_change=lambda e: _reset_and_refresh(),
                ).props("dense outlined clearable").style("flex: 1 1 100px;")

                status_options = {s: STATUS_LABELS[s] for s in STATUSES}
                filter_status = ui.select(
                    options={"": "All", **status_options},
                    label="Status",
                    on_change=lambda e: _reset_and_refresh(),
                ).props("dense outlined clearable").style("flex: 1 1 110px;")

                sme_options = {"": "All"} | {s: s for s in state.db.get_smes()}
                filter_sme = ui.select(
                    options=sme_options,
                    label="SME",
                    on_change=lambda e: _reset_and_refresh(),
                ).props("dense outlined clearable").style("flex: 1 1 110px;")

                tag_options = {"": "All"} | {t: t for t in state.db.get_all_tags()}
                filter_tag = ui.select(
                    options=tag_options,
                    label="Tag",
                    on_change=lambda e: _reset_and_refresh(),
                ).props("dense outlined clearable").style("flex: 1 1 100px;")

                ui.button("Search", icon="search", on_click=lambda: _reset_and_refresh()).props(
                    "dense color=primary size=sm"
                )

    # ══════════════════════════════════════════════════════
    # ── 3. Bulk Actions & Export ──────────────────────────
    # ══════════════════════════════════════════════════════
    with ui.expansion("Bulk Actions & Export", icon="settings_applications").classes("w-full").props(
        "dense header-class=section-title"
    ):
        with ui.card().classes("w-full q-pa-md"):
            # ── Bulk Actions ──
            ui.label("Bulk Actions").classes("text-xs font-semibold")
            ui.label(
                "Select questions with checkboxes, then apply a status transition or SME assignment."
            ).classes("text-xs text-grey-5 q-mb-xs")

            with ui.row().classes("w-full gap-2 items-end flex-wrap"):
                bulk_status = ui.select(
                    {s: STATUS_LABELS[s] for s in STATUSES}, value="sme_review", label="Transition to"
                ).props("dense outlined").style("flex: 1 1 120px; max-width: 180px;")
                sme_opts_list = list(dict.fromkeys(config.sme_names))
                bulk_sme = ui.select(
                    options=sme_opts_list, value=config.sme_name or None,
                    label="Assign SME", with_input=True, new_value_mode="add-unique",
                ).props("dense outlined").style("flex: 1 1 130px; max-width: 200px;")
                ui.button("Apply to Selected", icon="check_circle",
                          on_click=lambda: _bulk_action()).props("flat dense color=primary size=sm")
                ui.button("Delete Selected", icon="delete",
                          on_click=lambda: _confirm_bulk_delete()).props("flat dense color=negative size=sm")

            # ── Workflow Help ──
            with ui.expansion("Workflow Reference", icon="help_outline").classes("w-full q-mt-sm").props("dense"):
                with ui.column().classes("gap-1 q-pa-xs"):
                    flows = [
                        ("Draft", "arrow_forward", "SME Review", "Submit for review"),
                        ("SME Review", "arrow_forward", "Approved / Revised / Rejected", "Reviewer decision"),
                        ("Revised", "arrow_forward", "SME Review", "Resubmit after changes"),
                        ("Rejected", "arrow_forward", "Draft", "Send back for rework"),
                        ("Approved", "arrow_forward", "Retired", "End of life"),
                    ]
                    for src, icon, dest, desc in flows:
                        with ui.row().classes("items-center gap-1"):
                            ui.label(src).classes("text-xs font-medium").style("min-width: 80px")
                            ui.icon(icon, size="xs").classes("text-grey-5")
                            ui.label(dest).classes("text-xs font-medium")
                            ui.label(f"({desc})").classes("text-xs text-grey-5")

            # ── Export ──
            ui.separator().classes("q-my-sm")
            ui.label("Export").classes("text-xs font-semibold")
            ui.label(
                "Export the current filtered view. All active filters are applied to the export."
            ).classes("text-xs text-grey-5 q-mb-xs")

            with ui.row().classes("gap-1 flex-wrap items-center"):
                ui.button("CSV", icon="download", on_click=lambda: _export("csv")).props(
                    "flat dense size=sm color=primary"
                ).tooltip("Spreadsheet-friendly format")
                ui.button("JSON", icon="download", on_click=lambda: _export("json")).props(
                    "flat dense size=sm color=primary"
                ).tooltip("Machine-readable format")
                ui.button("QTI", icon="download", on_click=lambda: _export("qti")).props(
                    "flat dense size=sm color=primary"
                ).tooltip("QTI 2.1 for Canvas, Blackboard, etc.")
                ui.button("Moodle", icon="download", on_click=lambda: _export("moodle")).props(
                    "flat dense size=sm color=primary"
                ).tooltip("Moodle XML import format")
                ui.button("Text", icon="download", on_click=lambda: _export("text")).props(
                    "flat dense size=sm color=primary"
                ).tooltip("Plain text study guide")
                ui.button("DOCX", icon="download", on_click=lambda: _export("docx")).props(
                    "flat dense size=sm color=primary"
                ).tooltip("Formatted Word document")
                ui.button("PCM Exam", icon="download", on_click=lambda: _export("pcm_exam")).props(
                    "flat dense size=sm color=secondary"
                ).tooltip("Pentaho Content Manager exam.json (drop into a course)")
                ui.space()
                ui.button("Student View", icon="school", on_click=lambda: _open_student_view()).props(
                    "flat dense size=sm color=purple"
                ).tooltip("Practice mode with score tracking")

    # ── Pagination state ──────────────────────────────────
    page_state = {"offset": 0, "limit": config.questions_per_page}

    # ── Undo-delete state ─────────────────────────────────
    _pending_deletes = {}  # {qid: (Question, timer)}

    # ── Table ─────────────────────────────────────────────
    selected_ids = set()
    undo_container = ui.column().classes("w-full")
    table_container = ui.column().classes("w-full q-mt-sm")

    def _search_filters():
        return dict(
            text=search_input.value or "",
            topic=filter_topic.value or "",
            difficulty=filter_diff.value or "",
            bloom_level=filter_bloom.value or "",
            status=filter_status.value or "",
            certification_id=filter_cert.value or "",
            assigned_sme=filter_sme.value or "",
            tags=filter_tag.value or "",
        )

    def _refresh():
        filters = _search_filters()
        total = state.db.search_count(**filters)
        questions = state.db.search(
            **filters,
            limit=page_state["limit"],
            offset=page_state["offset"],
        )
        filter_topic.options = {"": "All"} | {t: t for t in state.db.get_topics()}
        filter_topic.update()
        filter_sme.options = {"": "All"} | {s: s for s in state.db.get_smes()}
        filter_sme.update()
        filter_tag.options = {"": "All"} | {t: t for t in state.db.get_all_tags()}
        filter_tag.update()
        bulk_sme.options = list(dict.fromkeys(config.sme_names))
        bulk_sme.update()
        updated_certs = state.db.list_certifications()
        filter_cert.options = {"": "All"} | {c.id: c.name for c in updated_certs}
        filter_cert.update()

        table_container.clear()
        selected_ids.clear()

        with table_container:
            if not questions:
                with ui.column().classes("w-full items-center q-pa-lg gap-2"):
                    ui.icon("search_off", size="48px").classes("text-grey-4")
                    ui.label("No questions found").classes("text-base text-grey-5")
                    ui.label(
                        "Try adjusting your search terms or filters, or generate/import some questions first."
                    ).classes("text-xs text-grey-5 text-center")
                return

            # Pagination info
            page_num = (page_state["offset"] // page_state["limit"]) + 1
            total_pages = max(1, (total + page_state["limit"] - 1) // page_state["limit"])
            start_num = page_state["offset"] + 1
            end_num = min(page_state["offset"] + page_state["limit"], total)

            with ui.row().classes("w-full items-center gap-2"):
                ui.label(f"Showing {start_num}–{end_num} of {total} questions").classes("text-sm text-grey-6")
                ui.space()
                ui.button(icon="chevron_left", on_click=lambda: _page(-1)).props(
                    "flat dense round size=sm"
                ).set_enabled(page_state["offset"] > 0)
                ui.label(f"Page {page_num} of {total_pages}").classes("text-xs text-grey-6")
                ui.button(icon="chevron_right", on_click=lambda: _page(1)).props(
                    "flat dense round size=sm"
                ).set_enabled(page_state["offset"] + page_state["limit"] < total)

            for idx, q in enumerate(questions):
                _render_bank_row(q, idx, start_num, len(questions))

    def _page(direction: int):
        page_state["offset"] += direction * page_state["limit"]
        page_state["offset"] = max(0, page_state["offset"])
        _refresh()

    def _reset_and_refresh():
        page_state["offset"] = 0
        _refresh()

    def _render_bank_row(q: Question, idx: int, start_num: int, page_count: int):
        warnings = q.validate()
        status_color = {
            "draft": "amber", "sme_review": "blue", "revised": "cyan",
            "approved": "green", "rejected": "red", "retired": "grey",
        }.get(q.status, "grey")
        diff_color = {"Easy": "green", "Medium": "amber", "Hard": "red"}.get(q.difficulty, "grey")

        with ui.card().classes(f"w-full question-card status-{q.status} q-pa-sm").style("overflow: visible;"):
            with ui.row().classes("w-full items-start gap-2 flex-wrap"):
                cb = ui.checkbox(
                    value=q.id in selected_ids,
                    on_change=lambda e, qid=q.id: _toggle_select(qid, e.value),
                ).props("dense")

                with ui.column().classes("gap-0").style("flex: 1 1 0; min-width: 0;"):
                    # Question number + status + metadata
                    with ui.row().classes("gap-1 items-center flex-wrap"):
                        ui.label(f"Q{start_num + idx}").classes("text-xs text-grey-5 font-mono")
                        ui.badge(STATUS_LABELS.get(q.status, q.status)).props(f"color={status_color}")
                        ui.badge(q.difficulty).props(f"color={diff_color}")
                        ui.badge(q.bloom_level).props("color=purple outline")
                        ui.badge(q.format_label).props("color=grey outline")
                        if q.source_type == "docs":
                            ui.badge("Docs").props("color=teal outline")
                        if q.topic:
                            ui.label(q.topic).classes("text-xs text-grey-6")
                        if q.assigned_sme:
                            ui.badge(f"SME: {q.assigned_sme}").props("color=teal outline")
                        if q.source_slides:
                            ui.label(f"Slide {', '.join(str(s+1) for s in q.source_slides)}").classes(
                                "text-xs text-grey-6"
                            )
                        if q.tags:
                            for tag in q.tags:
                                if not tag.startswith("qa:") and not tag.startswith("key-"):
                                    ui.badge(tag, color="purple").props("outline").classes("text-xs")

                    # Scenario + Stem
                    if q.scenario:
                        ui.label(q.scenario).classes("text-xs italic text-grey-6 q-mt-xs")
                    ui.label(q.stem).classes("text-sm font-medium q-mt-xs")

                    # Choices
                    correct_set = set(q.correct_answers)
                    all_choices = q.all_choices
                    with ui.column().classes("gap-0 q-mt-xs"):
                        for j, choice in enumerate(all_choices):
                            letter = string.ascii_uppercase[j] if j < 26 else str(j + 1)
                            is_correct = choice in correct_set
                            if is_correct:
                                ui.label(f"{letter}: {choice}").classes("text-xs text-positive font-medium")
                            else:
                                ui.label(f"{letter}: {choice}").classes("text-xs text-grey-7")
                        answer_letters = [
                            string.ascii_uppercase[j] for j, c in enumerate(all_choices)
                            if c in correct_set and j < 26
                        ]
                        if answer_letters:
                            ui.label(f"Answer: {', '.join(answer_letters)}").classes(
                                "text-xs font-bold text-positive q-mt-xs"
                            )

                    if q.key_source_text:
                        ui.label(f'Source: "{q.key_source_text[:100]}..."' if len(q.key_source_text) > 100
                                 else f'Source: "{q.key_source_text}"').classes(
                            "text-xs text-blue-7 italic q-mt-xs"
                        )

                    # Explanation — expanded by default for review
                    if q.explanation and q.explanation.strip():
                        with ui.expansion("Explanation", icon="school").classes("w-full q-mt-xs").props("dense default-opened"):
                            if _MERMAID_BLOCK_RE.search(q.explanation):
                                _render_rich_content(q.explanation)
                            else:
                                ui.html(format_explanation_html(q.explanation))

                    # Reject reason
                    if q.status == "rejected" and q.reject_reason:
                        with ui.row().classes("gap-1 items-center q-mt-xs"):
                            ui.icon("block", color="red", size="xs")
                            ui.label(f"Rejected: {q.reject_reason}").classes("text-xs text-red")

                    # Timestamps
                    with ui.row().classes("gap-4 q-mt-xs"):
                        if q.created_by:
                            ui.label(f"By: {q.created_by}").classes("text-xs text-grey-5")
                        if q.reviewed_at:
                            ui.label(f"Reviewed: {q.reviewed_at[:10]}").classes("text-xs text-grey-5")
                        if q.approved_at:
                            ui.label(f"Approved: {q.approved_at[:10]}").classes("text-xs text-grey-5")

                    if warnings:
                        with ui.row().classes("gap-1 q-mt-xs"):
                            ui.icon("warning", color="orange", size="xs")
                            ui.label(f"{len(warnings)} warning(s)").classes("text-xs text-orange")

                # Actions column
                with ui.column().classes("gap-1 items-end").style("flex: 0 0 auto;"):
                    # Status transition dropdown
                    transitions = q.allowed_transitions()
                    if transitions:
                        options = {q.status: STATUS_LABELS.get(q.status, q.status)}
                        for ns in transitions:
                            options[ns] = f"→ {STATUS_LABELS.get(ns, ns)}"
                        current = q.status
                        ui.select(
                            options, value=current,
                            on_change=lambda e, qid=q.id, cur=current: _transition_question(qid, e.value) if e.value != cur else None,
                        ).props("dense outlined").classes("text-xs").style("min-width: 140px; max-width: 180px;")

                    with ui.row().classes("gap-1"):
                        ui.button("Edit", icon="edit", on_click=lambda _, qid=q.id: _edit_bank_question(qid)).props(
                            "flat dense size=sm"
                        ).tooltip("Open full editor with version history")
                        ui.button("Delete", icon="delete", on_click=lambda _, qid=q.id: _delete_one(qid)).props(
                            "flat dense size=sm color=negative"
                        ).tooltip("Delete (10s undo window)")

    def _toggle_select(qid: str, selected: bool):
        if selected:
            selected_ids.add(qid)
        else:
            selected_ids.discard(qid)

    def _transition_question(qid: str, new_status: str):
        q = state.db.get(qid)
        if not q:
            return
        if new_status == "rejected":
            _show_transition_dialog(q, new_status)
            return
        sme = config.sme_name or ""
        try:
            q.transition(new_status, sme_name=sme)
            if new_status == "sme_review" and sme:
                q.assigned_sme = sme
            state.db.save(q)
            ui.notify(f"→ {STATUS_LABELS.get(new_status, new_status)}", type="positive")
            _refresh()
            _notify_other_tabs()
        except ValueError as e:
            ui.notify(str(e), type="warning")

    def _show_transition_dialog(q: Question, new_status: str):
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-md q-pa-md"):
            ui.label(f"Transition to {STATUS_LABELS.get(new_status, new_status)}").classes("text-base font-semibold")
            comment_input = ui.textarea(
                label="Comment / Reason" if new_status == "rejected" else "Comment (optional)",
                placeholder="Why is this being rejected?" if new_status == "rejected" else "",
            ).classes("w-full").props("dense outlined autogrow")

            with ui.row().classes("gap-2 justify-end q-mt-sm"):
                ui.button("Cancel", on_click=dialog.close).props("flat dense")

                def confirm():
                    sme = config.sme_name or ""
                    try:
                        q.transition(new_status, sme_name=sme, comment=comment_input.value)
                        state.db.save(q)
                        dialog.close()
                        _refresh()
                        _notify_other_tabs()
                        ui.notify(f"→ {STATUS_LABELS.get(new_status, new_status)}", type="positive")
                    except ValueError as e:
                        ui.notify(str(e), type="warning")

                ui.button("Confirm", icon="check", on_click=confirm).props("color=primary dense size=sm")
        dialog.open()

    def _edit_bank_question(qid: str):
        q = state.db.get(qid)
        if not q:
            return

        with ui.dialog() as dialog, ui.card().classes("w-full max-w-2xl q-pa-md"):
            ui.label("Edit Question").classes("text-base font-semibold")

            scenario_in = ui.textarea(
                label="Scenario (real-world context)", value=q.scenario
            ).classes("w-full").props("dense outlined autogrow")
            stem_in = ui.textarea(
                label="Stem (the question itself)", value=q.stem
            ).classes("w-full").props("dense outlined autogrow")
            key_in = ui.input(
                label="Key (correct answer — must come from slide notes)", value=q.key
            ).classes("w-full").props("dense outlined")
            key_src_in = ui.textarea(
                label="Key Source Text (exact quote from speaker notes that proves the answer)",
                value=q.key_source_text
            ).classes("w-full").props("dense outlined autogrow")

            dist_inputs = []
            num_dist = max(4, len(q.distractors) + 1)
            for j in range(num_dist):
                val = q.distractors[j] if j < len(q.distractors) else ""
                dist_inputs.append(
                    ui.input(
                        label=f"Distractor {j + 1}",
                        value=val,
                        placeholder="Leave blank to omit",
                    ).classes("w-full").props("dense outlined")
                )

            explanation_in = ui.textarea(
                label="Explanation (why each answer is correct or incorrect)", value=q.explanation
            ).classes("w-full").props("dense outlined autogrow")

            with ui.row().classes("gap-2"):
                diff_s = ui.select(DIFFICULTIES, value=q.difficulty, label="Difficulty").props("dense outlined")
                bloom_s = ui.select(BLOOM_LEVELS, value=q.bloom_level, label="Bloom Level").props("dense outlined")
                topic_in = ui.input(label="Topic", value=q.topic).props("dense outlined")
                sme_opts = list(dict.fromkeys(config.sme_names))
                sme_in = ui.select(
                    options=sme_opts, value=q.assigned_sme or None,
                    label="Assigned SME", with_input=True, new_value_mode="add-unique",
                ).props("dense outlined")

            # Version history
            if q.version_history:
                with ui.expansion(f"Version History ({len(q.version_history)} edits)", icon="history_edu").classes("w-full q-mt-sm"):
                    for entry in reversed(q.version_history[-20:]):
                        with ui.row().classes("gap-2 text-xs items-center"):
                            ui.label(entry.get("timestamp", "")[:16]).classes("text-grey-6")
                            ui.badge(f"v{entry.get('version', '?')}").props("outline color=grey")
                            ui.label(entry.get("field", "")).classes("font-medium")
                            if entry.get("editor"):
                                ui.label(f"by {entry['editor']}").classes("text-grey-5")
                        old_val = entry.get("old", "")[:80]
                        new_val = entry.get("new", "")[:80]
                        if old_val:
                            ui.label(f"- {old_val}").classes("text-xs text-red").style("text-decoration: line-through;")
                        if new_val:
                            ui.label(f"+ {new_val}").classes("text-xs text-green")

            # Review history
            if q.review_history:
                with ui.expansion("Review History", icon="history").classes("w-full q-mt-sm"):
                    for entry in reversed(q.review_history):
                        with ui.row().classes("gap-2 text-xs"):
                            ui.label(entry.get("timestamp", "")[:16]).classes("text-grey-6")
                            ui.badge(STATUS_LABELS.get(entry.get("to_status", ""), "")).props("outline")
                            if entry.get("sme_name"):
                                ui.label(entry["sme_name"]).classes("font-medium")
                            if entry.get("comment"):
                                ui.label(entry["comment"]).classes("italic")

            with ui.row().classes("gap-2 q-mt-sm justify-end"):
                def save_edit():
                    editor = config.sme_name or ""
                    q.record_edit("scenario", q.scenario, scenario_in.value, editor)
                    q.record_edit("stem", q.stem, stem_in.value, editor)
                    q.record_edit("key", q.key, key_in.value, editor)
                    q.record_edit("key_source_text", q.key_source_text, key_src_in.value, editor)
                    q.record_edit("explanation", q.explanation, explanation_in.value, editor)
                    q.record_edit("difficulty", q.difficulty, diff_s.value, editor)
                    q.record_edit("bloom_level", q.bloom_level, bloom_s.value, editor)
                    q.record_edit("topic", q.topic, topic_in.value, editor)
                    q.record_edit("assigned_sme", q.assigned_sme, sme_in.value or "", editor)
                    new_dists = [d.value.strip() for d in dist_inputs if d.value.strip()]
                    q.record_edit("distractors", "|".join(q.distractors), "|".join(new_dists), editor)
                    q.scenario = scenario_in.value
                    q.stem = stem_in.value
                    q.key = key_in.value
                    q.key_source_text = key_src_in.value
                    q.distractors = new_dists
                    q.explanation = explanation_in.value
                    q.difficulty = diff_s.value
                    q.bloom_level = bloom_s.value
                    q.topic = topic_in.value
                    q.assigned_sme = sme_in.value or ""
                    if q.assigned_sme and q.assigned_sme not in config.sme_names:
                        config.sme_names.append(q.assigned_sme)
                        config.save()
                    state.db.save(q)
                    dialog.close()
                    _refresh()
                    _notify_other_tabs()
                    ui.notify("Question updated", type="positive")

                ui.button("Save", icon="check", on_click=save_edit).props("color=positive dense size=sm")
                ui.button("Cancel", on_click=dialog.close).props("flat dense size=sm")

        dialog.open()

    def _notify_other_tabs():
        state.bus.emit_many(EVT_STATS_CHANGED, EVT_ADMIN_CHANGED, EVT_CERTIFICATIONS_CHANGED)

    def _stage_delete(qid: str):
        q = state.db.get(qid)
        if not q:
            return
        state.db.delete(qid)

        def _finalize():
            _pending_deletes.pop(qid, None)
            _refresh_undo_bar()

        timer = ui.timer(10.0, _finalize, once=True)
        _pending_deletes[qid] = (q, timer)
        _refresh()
        _notify_other_tabs()
        _refresh_undo_bar()

    def _undo_delete(qid: str):
        entry = _pending_deletes.pop(qid, None)
        if entry:
            q, timer = entry
            timer.cancel()
            state.db.save(q)
            _refresh()
            _notify_other_tabs()
            ui.notify("Deletion undone", type="positive")
        _refresh_undo_bar()

    def _undo_all():
        for qid in list(_pending_deletes.keys()):
            _undo_delete(qid)

    def _refresh_undo_bar():
        undo_container.clear()
        if not _pending_deletes:
            return
        with undo_container:
            with ui.card().classes("w-full q-pa-sm").style("background: #fff3e0;"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("undo", color="orange")
                    count = len(_pending_deletes)
                    ui.label(f"{count} question(s) deleted").classes("text-sm")
                    ui.button("Undo All", icon="undo", on_click=_undo_all).props(
                        "flat dense color=orange size=sm"
                    )
                    ui.label("(auto-expires in 10s)").classes("text-xs text-grey-6")

    def _delete_one(qid: str):
        _stage_delete(qid)
        ui.notify("Question deleted — undo available for 10s", type="info")

    def _bulk_action():
        if not selected_ids:
            ui.notify("No questions selected — use the checkboxes to select", type="warning")
            return
        target_status = bulk_status.value
        sme = (bulk_sme.value or "").strip()
        if sme and sme not in config.sme_names:
            config.sme_names.append(sme)
            config.save()
        count = 0
        errors = 0
        for qid in list(selected_ids):
            q = state.db.get(qid)
            if not q:
                continue
            try:
                q.transition(target_status, sme_name=config.sme_name or "", comment="Bulk action")
                if sme:
                    q.assigned_sme = sme
                state.db.save(q)
                count += 1
            except ValueError:
                errors += 1
        msg = f"Updated {count} question(s) to '{STATUS_LABELS.get(target_status, target_status)}'"
        if errors:
            msg += f" ({errors} skipped — invalid transition)"
        ui.notify(msg, type="positive" if count else "warning")
        _refresh()
        _notify_other_tabs()

    def _confirm_bulk_delete():
        if not selected_ids:
            ui.notify("No questions selected — use the checkboxes to select", type="warning")
            return
        count = len(selected_ids)
        with ui.dialog() as dlg, ui.card().classes("q-pa-md").style("min-width: 400px"):
            ui.label("Delete Selected Questions").classes("text-base font-semibold")
            with ui.row().classes("items-start gap-2 q-mt-xs"):
                ui.icon("warning", color="orange", size="sm")
                ui.label(
                    f"Delete {count} selected question(s)? "
                    "You will have 10 seconds to undo."
                ).classes("text-sm")
            with ui.row().classes("gap-2 justify-end q-mt-md"):
                ui.button("Keep", on_click=dlg.close).props("flat dense")
                def do_delete():
                    dlg.close()
                    _bulk_delete()
                ui.button("Delete", icon="delete", on_click=do_delete).props("dense color=negative")
        dlg.open()

    def _bulk_delete():
        count = len(selected_ids)
        for qid in list(selected_ids):
            q = state.db.get(qid)
            if not q:
                continue
            state.db.delete(qid)

            def _finalize(id=qid):
                _pending_deletes.pop(id, None)
                _refresh_undo_bar()

            timer = ui.timer(10.0, _finalize, once=True)
            _pending_deletes[qid] = (q, timer)
        selected_ids.clear()
        _refresh()
        _notify_other_tabs()
        _refresh_undo_bar()
        ui.notify(f"Deleted {count} questions — undo available for 10s", type="info")

    def _export(fmt: str):
        filters = _search_filters()
        questions = state.db.search(**filters)
        if not questions:
            ui.notify("No questions to export — adjust your filters", type="warning")
            return

        # Show confirmation with count and applied filters
        active_filters = []
        if filters["text"]:
            active_filters.append(f'search: "{filters["text"]}"')
        if filters["certification_id"]:
            cert_obj = state.db.get_certification(filters["certification_id"])
            active_filters.append(f"cert: {cert_obj.name if cert_obj else filters['certification_id'][:8]}")
        if filters["topic"]:
            active_filters.append(f"topic: {filters['topic']}")
        if filters["status"]:
            active_filters.append(f"status: {STATUS_LABELS.get(filters['status'], filters['status'])}")
        if filters["difficulty"]:
            active_filters.append(f"difficulty: {filters['difficulty']}")

        filter_desc = ", ".join(active_filters) if active_filters else "no filters (all questions)"

        fmt_labels = {"csv": "CSV", "json": "JSON", "qti": "QTI 2.1", "moodle": "Moodle XML", "text": "Text", "docx": "DOCX", "pcm_exam": "PCM Exam JSON"}
        ui.notify(f"Exporting {len(questions)} questions as {fmt_labels.get(fmt, fmt)} ({filter_desc})...", type="info")

        out_dir = Path(config.output_folder)
        out_dir.mkdir(parents=True, exist_ok=True)

        ext_map = {"csv": ".csv", "json": ".json", "qti": ".xml", "moodle": ".xml", "text": ".txt", "docx": ".docx", "pcm_exam": ".json"}
        prefix_map = {"csv": "questions", "json": "questions", "qti": "qti_export",
                      "moodle": "moodle_export", "text": "questions", "docx": "questions",
                      "pcm_exam": "exam"}
        path = out_dir / f"{prefix_map[fmt]}{ext_map[fmt]}"

        try:
            if fmt == "csv":
                export_csv(questions, path)
            elif fmt == "json":
                export_json(questions, path)
            elif fmt == "qti":
                export_qti21(questions, path)
            elif fmt == "moodle":
                export_moodle_xml(questions, path)
            elif fmt == "text":
                export_text(questions, path)
            elif fmt == "docx":
                export_docx(questions, path)
            elif fmt == "pcm_exam":
                # Title the exam after the filtered certification (a PCM cert's
                # name is the course title); fall back to a generic label.
                exam_title = "Practitioner Exam"
                source_label = ""
                description = webhook_url = webhook_secret = ""
                qpa = None
                pass_mark = 80
                cert_id = filters.get("certification_id")
                cert_obj = state.db.get_certification(cert_id) if cert_id else None
                if cert_obj and cert_obj.name:
                    exam_title = f"{cert_obj.name} Exam"
                    source_label = cert_obj.name
                # For a PCM course, carry over settings from its existing exam.json
                # so regenerating questions doesn't wipe the webhook/description/
                # sampling config the course already ships with.
                if cert_obj and cert_obj.source_type == "pcm" and config.pcm_courses_dir:
                    existing = Path(config.pcm_courses_dir) / cert_obj.source_ref / "exam.json"
                    if existing.is_file():
                        try:
                            old = json.loads(existing.read_text(encoding="utf-8"))
                            description = old.get("description") or ""
                            webhook_url = old.get("webhookUrl") or ""
                            webhook_secret = old.get("webhookSecret") or ""
                            pass_mark = old.get("passMark") or 80
                            qpa = old.get("questionsPerAttempt")
                            # Don't sample more than we're exporting.
                            if qpa and qpa > len(questions):
                                qpa = None
                        except Exception:
                            pass
                export_pcm_exam_json(
                    questions, path,
                    title=exam_title, pass_mark=pass_mark,
                    questions_per_attempt=qpa, description=description,
                    webhook_url=webhook_url, webhook_secret=webhook_secret,
                    source_label=source_label,
                )
            ui.download(path)
            ui.notify(f"Exported {len(questions)} questions → {path.name}", type="positive")
        except Exception as e:
            ui.notify(f"Export failed: {e}", type="negative")

    def _open_student_view():
        from .student_view import open_student_view
        filters = _search_filters()
        questions = state.db.search(**filters, limit=100)
        if not questions:
            ui.notify("No questions to preview — adjust filters", type="warning")
            return
        open_student_view(questions)

    state.bus.on(EVT_BANK_CHANGED, _reset_and_refresh)
    _refresh()

    # ══════════════════════════════════════════════════════
    # ── 4. Database Backup & Restore ──────────────────────
    # ══════════════════════════════════════════════════════
    with ui.expansion("Database Backup & Restore", icon="backup").classes("w-full q-mt-md").props(
        "dense header-class=section-title"
    ):
        with ui.card().classes("w-full q-pa-md"):
            _section_help(
                "Create timestamped backups of your exam bank database. "
                "Restore from any backup if needed — a safety copy is made automatically before restoring."
            )
            db_info_container = ui.column().classes("w-full gap-1")
            backup_list_container = ui.column().classes("w-full gap-1 q-mt-sm")

        def _refresh_db_panel():
            db_info_container.clear()
            with db_info_container:
                info = get_db_info()
                if info["exists"]:
                    with ui.row().classes("gap-4 items-center text-xs"):
                        ui.label(f"Location: assets/db/exam_bank.db").classes("muted")
                        ui.label(f"Size: {info['size_kb']} KB").classes("muted")
                        ui.label(f"Modified: {info['modified']}").classes("muted")
                else:
                    ui.label("No database found.").classes("muted text-xs")

            backup_list_container.clear()
            with backup_list_container:
                backups = list_backups()
                with ui.row().classes("gap-2 items-center"):
                    backup_label = ui.input(placeholder="Label (optional)").props(
                        "dense outlined"
                    ).classes("w-40")
                    ui.button("Create Backup", icon="save",
                              on_click=lambda: _do_backup(backup_label.value.strip())).props(
                        "dense color=primary size=sm"
                    )
                if backups:
                    ui.label(f"{len(backups)} backup(s)").classes("text-xs muted q-mt-xs")
                    for b in backups:
                        with ui.row().classes("w-full items-center gap-2"):
                            ui.icon("inventory_2", size="xs").classes("text-grey-6")
                            ui.label(b["name"]).classes("text-xs flex-grow")
                            ui.label(f"{b['size_kb']} KB").classes("text-xs muted")
                            ui.label(b["created"]).classes("text-xs muted")
                            ui.button(icon="restore", on_click=lambda _, p=b["path"]: _do_restore(p)).props(
                                "flat round dense size=xs color=primary"
                            ).tooltip("Restore this backup")
                            ui.button(icon="delete", on_click=lambda _, p=b["path"]: _do_delete(p)).props(
                                "flat round dense size=xs color=negative"
                            ).tooltip("Delete this backup")
                else:
                    ui.label("No backups yet.").classes("text-xs muted q-mt-xs")

        def _do_backup(label: str):
            try:
                path = create_backup(label=label)
                ui.notify(f"Backup created: {path.name}", type="positive")
                _refresh_db_panel()
            except Exception as e:
                ui.notify(f"Backup failed: {e}", type="negative")

        def _do_restore(backup_path: Path):
            with ui.dialog() as dlg, ui.card().classes("q-pa-md").style("min-width: 400px"):
                ui.label("Restore Backup").classes("text-base font-semibold")
                ui.label(
                    f"This will replace the current database with:\n{backup_path.name}\n\n"
                    "A safety backup of the current DB will be created first."
                ).classes("text-sm whitespace-pre-wrap")
                with ui.row().classes("gap-2 justify-end q-mt-sm"):
                    ui.button("Cancel", on_click=dlg.close).props("flat dense")

                    def confirm():
                        try:
                            restore_backup(backup_path)
                            from ...utils.config import DB_PATH
                            state.db.conn.close()
                            import sqlite3
                            state.db.conn = sqlite3.connect(str(DB_PATH))
                            state.db.conn.row_factory = sqlite3.Row
                            dlg.close()
                            refresh_stats()
                            _refresh_db_panel()
                            _refresh()
                            ui.notify("Database restored successfully", type="positive")
                        except Exception as e:
                            ui.notify(f"Restore failed: {e}", type="negative")

                    ui.button("Restore", icon="restore", on_click=confirm).props(
                        "dense color=warning size=sm"
                    )
            dlg.open()

        def _do_delete(backup_path: Path):
            delete_backup(backup_path)
            ui.notify("Backup deleted", type="info")
            _refresh_db_panel()

        _refresh_db_panel()
