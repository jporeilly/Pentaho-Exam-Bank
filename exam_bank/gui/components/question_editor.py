"""Question editor: form for creating/editing individual questions with lifecycle."""


import string
import threading
from typing import List

from nicegui import ui

from ..state import AppState, UIRefs, EVT_QUESTIONS_CHANGED, EVT_BANK_CHANGED, EVT_STATS_CHANGED
from ..styles import format_explanation_html
from .docs_chat import _MERMAID_BLOCK_RE, _render_rich_content
from ...core.bank import (
    Question, BLOOM_LEVELS, DIFFICULTIES, STATUSES, STATUS_LABELS,
)
from ...core.question_generator import improve_question, regen_stem, regen_key, regen_distractor, qa_check_question, qa_fix_question
from ...utils.config import config


def build_question_editor(state: AppState, refs: UIRefs):
    """Build the question editor form and generated questions list."""

    # ── Section header with help ──
    with ui.expansion("Generated Questions", icon="quiz").classes("w-full").props(
        "default-opened dense header-class=section-title"
    ):
        with ui.row().classes("w-full items-start gap-1 q-mb-sm"):
            ui.icon("help_outline", size="xs").classes("text-grey-5 q-mt-xs")
            ui.label(
                "Questions appear here after you click Generate. Review, refine with AI, "
                "then save to the bank. Use Ctrl+S to save all at once."
            ).classes("text-xs text-grey-6")

        gen_container = ui.column().classes("w-full gap-2")
    editor_container = ui.column().classes("w-full gap-2 q-mt-md")
    # Hidden anchor for scheduling main-thread callbacks from background threads
    _callback_anchor = ui.column().style("display: none;")

    def refresh_questions():
        gen_container.clear()
        with gen_container:
            if not state.generated_questions:
                # ── Friendly empty state ──
                with ui.column().classes("w-full items-center q-pa-lg gap-2"):
                    ui.icon("auto_awesome", size="48px").classes("text-grey-4")
                    ui.label("No questions yet").classes("text-base text-grey-5")
                    with ui.column().classes("items-start gap-1"):
                        with ui.row().classes("items-center gap-2"):
                            ui.badge("1").props("color=primary").classes("text-xs").style("min-width: 20px; text-align: center")
                            ui.label("Select a slide or docs topic in the sidebar").classes("text-xs text-grey-5")
                        with ui.row().classes("items-center gap-2"):
                            ui.badge("2").props("color=primary").classes("text-xs").style("min-width: 20px; text-align: center")
                            ui.label("Adjust difficulty and question count above").classes("text-xs text-grey-5")
                        with ui.row().classes("items-center gap-2"):
                            ui.badge("3").props("color=primary").classes("text-xs").style("min-width: 20px; text-align: center")
                            ui.label("Click Generate in the slide preview").classes("text-xs text-grey-5")
                return

            # ── Header with count and bulk actions ──
            total = len(state.generated_questions)
            error_count = sum(1 for q in state.generated_questions if q.validate_detailed()[0])
            warn_count = sum(1 for q in state.generated_questions if q.validate_detailed()[1] and not q.validate_detailed()[0])

            with ui.row().classes("w-full justify-between items-center"):
                with ui.row().classes("items-center gap-2"):
                    ui.label(f"{total} question(s) generated").classes("font-medium")
                    if error_count:
                        ui.badge(f"{error_count} with errors", color="red").classes("text-xs")
                    if warn_count:
                        ui.badge(f"{warn_count} with warnings", color="orange").classes("text-xs")
                with ui.row().classes("gap-1"):
                    ui.button("Save All", icon="save",
                              on_click=_confirm_save_all).props(
                        "flat dense size=sm color=positive"
                    ).classes("text-xs").tooltip("Save all valid questions to the bank (Ctrl+S)")
                    ui.button("Clear All", icon="delete_sweep",
                              on_click=_confirm_clear_all).props(
                        "flat dense size=sm color=negative"
                    ).classes("text-xs").tooltip("Remove all generated questions")

            for i, q in enumerate(state.generated_questions):
                _render_question_card(q, i, total)

    def _render_question_card(q: Question, idx: int, total: int):
        errors, warnings = q.validate_detailed()

        with ui.card().classes(f"w-full question-card status-{q.status}"):
            # ── Header: question number + metadata + actions ──
            with ui.row().classes("w-full items-center justify-between"):
                with ui.row().classes("gap-2 items-center"):
                    # Question number and source
                    label_parts = [f"Q{idx + 1} of {total}"]
                    # PCM/docs sources aren't slides — cite the section/source.
                    if q.source_type == "pcm":
                        label_parts.append(f"from {q.topic}" if q.topic else "from PCM course")
                    elif q.source_type == "docs":
                        label_parts.append("from Docs")
                    elif q.source_slides:
                        slides_str = ", ".join(str(s + 1) for s in q.source_slides)
                        label_parts.append(f"from Slide {slides_str}")
                    ui.label(" · ".join(label_parts)).classes("text-xs text-grey-5 font-mono")

                with ui.row().classes("gap-2 items-center"):
                    ui.badge(q.difficulty).classes(f"badge-{q.difficulty.lower()}")
                    ui.badge(q.bloom_level).props("color=purple outline")
                    ui.badge(q.format_label).props("color=grey outline")
                    if q.topic:
                        ui.badge(q.topic).props("color=primary outline")

            # ── Action buttons with labels ──
            with ui.row().classes("w-full gap-1 q-mt-xs"):
                ui.button("Edit", icon="edit", on_click=lambda _, i=idx: _edit_question(i)).props(
                    "flat dense size=sm"
                ).tooltip("Open full editor")
                ui.button("AI Improve", icon="auto_fix_high", on_click=lambda _, i=idx: _ai_improve(i)).props(
                    "flat dense size=sm color=purple"
                ).tooltip("Rewrite with AI for better quality")
                ui.button("QA Check", icon="spellcheck", on_click=lambda _, i=idx: _qa_check(i)).props(
                    "flat dense size=sm color=teal"
                ).tooltip("Check spelling, grammar, and clarity")
                ui.space()
                ui.button("Save", icon="save", on_click=lambda _, i=idx: _save_one(i)).props(
                    "flat dense size=sm color=positive"
                ).tooltip("Save this question to the bank")
                ui.button("Delete", icon="delete", on_click=lambda _, i=idx: _remove_one(i)).props(
                    "flat dense size=sm color=negative"
                ).tooltip("Remove this question")

            # ── Scenario ──
            if q.scenario:
                ui.label(q.scenario).classes("text-sm italic text-grey-7 q-mt-xs")

            # ── Stem + regen button ──
            with ui.row().classes("w-full items-start gap-1 q-mt-xs"):
                ui.label(q.stem).classes("font-medium").style("flex: 1;")
                ui.button(icon="refresh", on_click=lambda _, i=idx: _regen_stem(i)).props(
                    "flat round dense size=xs color=primary"
                ).tooltip("Regenerate stem (keep choices)")

            # ── Choices — exam-style with letter labels ──
            correct_set = set(q.correct_answers)
            all_choices = q.all_choices
            with ui.column().classes("q-ml-md gap-0 q-mt-xs"):
                for j, choice in enumerate(all_choices):
                    letter = string.ascii_uppercase[j] if j < 26 else str(j + 1)
                    is_correct = choice in correct_set
                    if is_correct:
                        key_list = list(q.correct_answers)
                        orig_idx = key_list.index(choice) if choice in key_list else 0
                        with ui.row().classes("items-center gap-1"):
                            ui.label(f"{letter}: {choice}").classes("text-sm text-positive font-medium")
                            ui.button(icon="refresh", on_click=lambda _, i=idx, ki=orig_idx: _regen_key_btn(i, ki)).props(
                                "flat round dense size=xs color=positive"
                            ).tooltip("Regenerate this correct answer")
                    else:
                        dist_idx = q.distractors.index(choice) if choice in q.distractors else 0
                        with ui.row().classes("items-center gap-1"):
                            ui.label(f"{letter}: {choice}").classes("text-sm text-grey-7")
                            ui.button(icon="refresh", on_click=lambda _, i=idx, di=dist_idx: _regen_dist_btn(i, di)).props(
                                "flat round dense size=xs color=grey"
                            ).tooltip("Regenerate this distractor")
                # Show answer key below
                answer_letters = [
                    string.ascii_uppercase[j] for j, c in enumerate(all_choices)
                    if c in correct_set and j < 26
                ]
                if answer_letters:
                    ui.label(f"Answer: {', '.join(answer_letters)}").classes(
                        "text-xs font-bold text-positive q-mt-xs"
                    )

            # ── Key source info ──
            if q.source_type == "docs":
                if q.key_source_text:
                    with ui.row().classes("gap-1 q-mt-xs items-start"):
                        ui.icon("auto_stories", size="xs", color="teal")
                        ui.label(f"Source (docs): {q.key_source_text}").classes(
                            "text-xs text-teal-8 italic"
                        )
                elif q.source_file:
                    ui.label(f"Source: {q.source_file}").classes("text-xs text-grey-6 q-mt-xs")
            elif q.source_type == "pcm":
                # PCM grounds on course prose, not a slide — cite the section, no slide number.
                if q.key_source_text:
                    with ui.row().classes("gap-1 q-mt-xs items-start"):
                        ui.icon("menu_book", size="xs", color="purple")
                        label = f"Source ({q.topic}): {q.key_source_text}" if q.topic else f"Source: {q.key_source_text}"
                        ui.label(label).classes("text-xs text-purple-8 italic")
                elif q.topic:
                    ui.label(f"Source: {q.topic}").classes("text-xs text-grey-6 q-mt-xs")
            elif q.key_source_text:
                with ui.row().classes("gap-1 q-mt-xs items-start"):
                    ui.icon("format_quote", size="xs", color="blue")
                    ui.label(f"Source (slide {q.key_source_slide + 1}): {q.key_source_text}").classes(
                        "text-xs text-blue-8 italic"
                    )
            elif q.source_slides:
                ui.label(f"Source slide(s): {', '.join(str(s + 1) for s in q.source_slides)}").classes(
                    "text-xs text-grey-6 q-mt-xs"
                )

            # ── Explanation — expanded by default for review workflow ──
            if q.explanation:
                with ui.expansion("Explanation", icon="info").classes("w-full text-sm").props("default-opened"):
                    if _MERMAID_BLOCK_RE.search(q.explanation):
                        _render_rich_content(q.explanation)
                    else:
                        ui.html(format_explanation_html(q.explanation))

            # ── Errors (block save) ──
            if errors:
                with ui.row().classes("gap-2 q-mt-xs flex-wrap"):
                    ui.icon("error", color="red", size="xs")
                    for e in errors:
                        ui.label(e).classes("text-xs text-red")

            # ── Warnings (advisory) ──
            if warnings:
                with ui.row().classes("gap-2 q-mt-xs flex-wrap"):
                    ui.icon("warning", color="orange", size="xs")
                    for w in warnings:
                        ui.label(w).classes("validation-warning")

            # ── QA check results ──
            qa_tags = [t for t in q.tags if t.startswith("qa:")]
            if qa_tags:
                with ui.expansion("QA Results", icon="spellcheck").classes("w-full q-mt-xs").props("dense default-opened"):
                    for tag in qa_tags:
                        parts = tag.split(":", 3)
                        if len(parts) == 4:
                            _, sev, field, issue = parts
                            color = "red" if sev == "error" else "orange"
                            ui.label(f"[{field}] {issue}").classes(f"text-xs text-{color}")

    def _edit_question(idx: int):
        if idx < len(state.generated_questions):
            state.editing_question = state.generated_questions[idx]
            _show_editor(idx)

    def _show_editor(idx: int):
        q = state.editing_question
        if not q:
            return
        editor_container.clear()
        with editor_container:
            ui.label("Edit Question").classes("section-title")
            with ui.card().classes("w-full q-pa-md"):
                scenario_input = ui.textarea(
                    label="Scenario (real-world context before the question)", value=q.scenario
                ).classes("w-full").props("dense outlined autogrow")

                type_select = ui.select(
                    {"single": "Single Select  —  one correct answer",
                     "multi": "Multi-Select  —  two or more correct answers"},
                    value=q.question_type, label="Question Type",
                ).classes("w-full").props("dense outlined")

                stem_input = ui.textarea(
                    label="Stem (the question itself)", value=q.stem
                ).classes("w-full").props("dense outlined autogrow")

                # ── Unified Answer Options with Key/Distractor toggle ──
                correct_set = set(q.correct_answers)
                all_options_data: list = []
                if q.option_order:
                    for opt in q.option_order:
                        all_options_data.append({"text": opt, "is_key": opt in correct_set})
                else:
                    key_vals = q.keys if (q.keys and len(q.keys) > 1) else ([q.key] if q.key else [])
                    dist_vals = q.distractors if q.distractors else []
                    for k in key_vals:
                        all_options_data.append({"text": k, "is_key": True})
                    for d in dist_vals:
                        all_options_data.append({"text": d, "is_key": False})
                if not all_options_data:
                    all_options_data.append({"text": "", "is_key": False})

                option_rows: list = []
                options_container = ui.column().classes("w-full gap-1 q-mt-sm")

                def _rebuild_options():
                    options_container.clear()
                    option_rows.clear()
                    with options_container:
                        with ui.row().classes("w-full items-center justify-between"):
                            key_count = sum(1 for o in all_options_data if o["is_key"])
                            dist_count = sum(1 for o in all_options_data if not o["is_key"])
                            ui.label("Answer Options").classes("text-sm font-bold")
                            ui.label(
                                f"{key_count} correct, {dist_count} wrong"
                            ).classes("text-xs text-grey-6")
                        ui.label(
                            "Click Key/Dist to toggle. Use arrows to reorder."
                        ).classes("text-xs text-grey-5 q-mb-xs")
                        for j, opt in enumerate(all_options_data):
                            with ui.row().classes("w-full gap-1 items-center"):
                                letter = chr(65 + j) if j < 26 else str(j + 1)
                                ui.label(f"{letter}:").classes("text-sm font-bold").style("min-width: 24px")
                                inp = ui.input(
                                    value=opt["text"],
                                    placeholder=f"Option {letter}",
                                ).classes("flex-grow").props("dense outlined")
                                is_key = opt["is_key"]
                                btn = ui.button(
                                    "Key" if is_key else "Dist",
                                    icon="check_circle" if is_key else "cancel",
                                    on_click=lambda _, jj=j: _toggle_option(jj),
                                ).props(
                                    f"{'color=positive' if is_key else 'color=grey'} "
                                    f"dense size=sm flat"
                                ).tooltip("Click to toggle between correct answer and distractor")
                                if j > 0:
                                    ui.button(
                                        icon="arrow_upward",
                                        on_click=lambda _, jj=j: _move_option(jj, -1),
                                    ).props("flat round dense size=xs color=grey").tooltip("Move up")
                                else:
                                    ui.label("").style("width: 28px")
                                if j < len(all_options_data) - 1:
                                    ui.button(
                                        icon="arrow_downward",
                                        on_click=lambda _, jj=j: _move_option(jj, 1),
                                    ).props("flat round dense size=xs color=grey").tooltip("Move down")
                                else:
                                    ui.label("").style("width: 28px")
                                option_rows.append((inp, btn))

                def _sync_options_text():
                    for j, (inp, _) in enumerate(option_rows):
                        if j < len(all_options_data):
                            all_options_data[j]["text"] = inp.value

                def _toggle_option(j: int):
                    _sync_options_text()
                    all_options_data[j]["is_key"] = not all_options_data[j]["is_key"]
                    _rebuild_options()

                def _move_option(j: int, direction: int):
                    _sync_options_text()
                    new_j = j + direction
                    if 0 <= new_j < len(all_options_data):
                        all_options_data[j], all_options_data[new_j] = all_options_data[new_j], all_options_data[j]
                    _rebuild_options()

                def _sync_options_to_q():
                    _sync_options_text()
                    new_keys = [o["text"] for o in all_options_data if o["is_key"] and o["text"].strip()]
                    new_dists = [o["text"] for o in all_options_data if not o["is_key"] and o["text"].strip()]
                    if len(new_keys) > 1:
                        q.keys = new_keys
                        q.key = new_keys[0]
                        q.question_type = "multi"
                    elif new_keys:
                        q.key = new_keys[0]
                        q.keys = []
                    else:
                        q.key = ""
                        q.keys = []
                    q.distractors = new_dists
                    q.option_order = [o["text"] for o in all_options_data if o["text"].strip()]

                _rebuild_options()

                key_source_input = ui.textarea(
                    label="Key Source Text (exact quote from speaker notes that proves the answer)",
                    value=q.key_source_text,
                ).classes("w-full").props("dense outlined autogrow")

                explanation_input = ui.textarea(
                    label="Explanation (why each answer is correct or incorrect)", value=q.explanation
                ).classes("w-full").props("dense outlined autogrow")

                with ui.row().classes("gap-2"):
                    diff_sel = ui.select(DIFFICULTIES, value=q.difficulty, label="Difficulty").props("dense outlined")
                    bloom_sel = ui.select(BLOOM_LEVELS, value=q.bloom_level, label="Bloom Level").props("dense outlined")
                    topic_input = ui.input(label="Topic", value=q.topic).props("dense outlined")

                with ui.row().classes("gap-2 q-mt-sm"):
                    def apply_edits():
                        q.scenario = scenario_input.value
                        q.question_type = type_select.value
                        q.stem = stem_input.value
                        _sync_options_to_q()
                        q.key_source_text = key_source_input.value
                        q.explanation = explanation_input.value
                        q.difficulty = diff_sel.value
                        q.bloom_level = bloom_sel.value
                        q.topic = topic_input.value
                        state.editing_question = None
                        editor_container.clear()
                        refresh_questions()

                    def cancel_edit():
                        state.editing_question = None
                        editor_container.clear()

                    ui.button("Apply Changes", icon="check", on_click=apply_edits).props("color=positive")
                    ui.button("Cancel", icon="close", on_click=cancel_edit).props("flat")

    def _do_save(q):
        """Actually save a question to the bank."""
        q.created_by = config.sme_name or "AI"
        # Strip temporary QA tags before persisting
        q.tags = [t for t in q.tags if not t.startswith("qa:")]
        state.db.save(q)

    def _show_duplicate_dialog(q, idx, similar):
        """Show a comparison dialog when similar questions exist in the bank."""
        with ui.dialog() as dlg, ui.card().classes("q-pa-md").style("min-width: 600px; max-width: 800px;"):
            ui.label("Similar Question(s) Found").classes("text-base font-bold")
            ui.label(
                f"{len(similar)} existing question(s) have a similar stem. "
                "Compare below and decide whether to save anyway or skip."
            ).classes("text-xs text-grey-6 q-mb-sm")

            # New question
            with ui.card().classes("w-full q-pa-sm").style("border-left: 3px solid #4caf50;"):
                ui.label("New Question").classes("text-xs font-bold text-positive")
                ui.label(q.stem).classes("text-sm")
                with ui.row().classes("gap-1 q-mt-xs"):
                    for ans in (q.keys if q.keys else [q.key]):
                        if ans:
                            ui.badge(f"Key: {ans[:50]}").props("color=positive outline").classes("text-xs")
                    for d in q.distractors:
                        ui.badge(f"D: {d[:50]}").props("color=grey outline").classes("text-xs")

            # Existing similar questions
            for eq in similar:
                with ui.card().classes("w-full q-pa-sm q-mt-xs").style("border-left: 3px solid #ff9800;"):
                    ui.label(f"Existing ({eq.status})").classes("text-xs font-bold text-warning")
                    ui.label(eq.stem).classes("text-sm")
                    with ui.row().classes("gap-1 q-mt-xs"):
                        for ans in (eq.keys if eq.keys else [eq.key]):
                            if ans:
                                ui.badge(f"Key: {ans[:50]}").props("color=positive outline").classes("text-xs")
                        for d in eq.distractors:
                            ui.badge(f"D: {d[:50]}").props("color=grey outline").classes("text-xs")
                        if eq.topic:
                            ui.badge(eq.topic).props("color=primary outline").classes("text-xs")

            with ui.row().classes("gap-2 justify-end q-mt-sm"):
                ui.button("Skip", icon="close", on_click=dlg.close).props("flat dense")

                def save_anyway():
                    if idx is not None and idx < len(state.generated_questions):
                        state.generated_questions.pop(idx)
                    _do_save(q)
                    ui.notify("Saved question to bank", type="positive")
                    state.bus.emit(EVT_QUESTIONS_CHANGED)
                    state.bus.emit(EVT_STATS_CHANGED)
                    state.bus.emit(EVT_BANK_CHANGED)
                    dlg.close()

                ui.button("Save Anyway", icon="save", on_click=save_anyway).props(
                    "dense color=positive"
                )
        dlg.open()

    def _commit_generated(idx: int):
        """Commit generated question at idx to the bank (past all checks)."""
        if idx >= len(state.generated_questions):
            return
        q = state.generated_questions[idx]
        # Check for similar questions in the bank
        similar = state.db.find_similar_stems(q.stem)
        if similar:
            _show_duplicate_dialog(q, idx, similar)
        else:
            state.generated_questions.pop(idx)
            _do_save(q)
            ui.notify("Saved question to bank", type="positive")
            state.bus.emit(EVT_QUESTIONS_CHANGED)
            state.bus.emit(EVT_STATS_CHANGED)
            state.bus.emit(EVT_BANK_CHANGED)

    def _save_one(idx: int):
        if idx >= len(state.generated_questions):
            return
        q = state.generated_questions[idx]

        # Validation gate — block if errors
        errors, warnings = q.validate_detailed()
        if errors:
            ui.notify(f"Cannot save — {len(errors)} error(s): {errors[0]}", type="negative")
            return

        # If warnings exist, show confirmation dialog
        if warnings:
            _show_save_warnings(idx, q, warnings)
        else:
            _commit_generated(idx)

    def _show_save_warnings(idx: int, q, warnings: list):
        """Show warnings and require confirmation before saving."""
        with ui.dialog() as dlg, ui.card().classes("q-pa-md").style("min-width: 500px; max-width: 700px;"):
            ui.label("Review Before Saving").classes("text-base font-bold")
            ui.label(q.stem[:100] + ("..." if len(q.stem) > 100 else "")).classes("text-sm text-grey-7 q-mb-sm")

            ui.label(f"{len(warnings)} warning(s) found:").classes("text-sm font-medium text-orange")
            with ui.column().classes("w-full gap-1 q-ml-sm"):
                for w in warnings:
                    with ui.row().classes("gap-1 items-center"):
                        ui.icon("warning", color="orange", size="xs")
                        ui.label(w).classes("text-xs text-orange")

            ui.separator().classes("q-my-sm")
            ui.label(
                "These warnings won't block the save but may indicate quality issues. "
                "Use Edit to fix, or save anyway."
            ).classes("text-xs text-grey-6")

            with ui.row().classes("gap-2 justify-end q-mt-sm"):
                ui.button("Cancel", icon="close", on_click=dlg.close).props("flat")
                ui.button("Edit First", icon="edit",
                          on_click=lambda: (dlg.close(), _edit_question(idx))).props("flat color=primary")

                def confirm_save():
                    dlg.close()
                    _commit_generated(idx)

                ui.button("Save Anyway", icon="save", on_click=confirm_save).props("color=positive")
        dlg.open()

    def _confirm_save_all():
        """Show confirmation before saving all questions."""
        total = len(state.generated_questions)
        if not total:
            return
        error_count = sum(1 for q in state.generated_questions if q.validate_detailed()[0])
        saveable = total - error_count

        if saveable == 0:
            ui.notify("No questions can be saved — all have validation errors", type="warning")
            return

        with ui.dialog() as dlg, ui.card().classes("q-pa-md").style("min-width: 400px"):
            ui.label("Save All Questions").classes("text-base font-semibold")
            with ui.column().classes("gap-1 q-mt-xs"):
                ui.label(f"{saveable} question(s) will be saved to the bank.").classes("text-sm")
                if error_count:
                    ui.label(
                        f"{error_count} question(s) have errors and will be kept for manual review."
                    ).classes("text-sm text-orange")
                ui.label(
                    "Duplicates will also be kept for review."
                ).classes("text-xs text-grey-5")

            with ui.row().classes("gap-2 justify-end q-mt-md"):
                ui.button("Cancel", on_click=dlg.close).props("flat dense")
                def do_save():
                    dlg.close()
                    _save_all()
                ui.button("Save All", icon="save", on_click=do_save).props("dense color=positive")
        dlg.open()

    def _save_all():
        saved = 0
        skipped = 0
        blocked = 0
        to_save = list(state.generated_questions)
        state.generated_questions.clear()
        for q in to_save:
            # Validation gate — skip questions with errors
            errors, _ = q.validate_detailed()
            if errors:
                blocked += 1
                state.generated_questions.append(q)  # keep for manual fix
                continue
            similar = state.db.find_similar_stems(q.stem)
            if similar:
                skipped += 1
                state.generated_questions.append(q)  # keep for manual review
            else:
                _do_save(q)
                saved += 1
        msg = f"Saved {saved} question(s) to bank"
        if skipped:
            msg += f" — {skipped} duplicate(s) kept for review"
        if blocked:
            msg += f" — {blocked} blocked (validation errors)"
        ui.notify(msg, type="positive" if saved else "warning")
        state.bus.emit(EVT_QUESTIONS_CHANGED)
        state.bus.emit(EVT_STATS_CHANGED)
        state.bus.emit(EVT_BANK_CHANGED)

    def _remove_one(idx: int):
        if idx < len(state.generated_questions):
            state.generated_questions.pop(idx)
            refresh_questions()

    def _confirm_clear_all():
        """Show confirmation before clearing all generated questions."""
        total = len(state.generated_questions)
        if not total:
            return
        with ui.dialog() as dlg, ui.card().classes("q-pa-md").style("min-width: 400px"):
            ui.label("Clear All Questions").classes("text-base font-semibold")
            with ui.row().classes("items-start gap-2 q-mt-xs"):
                ui.icon("warning", color="orange", size="sm")
                ui.label(
                    f"This will remove all {total} generated question(s). "
                    "Unsaved questions will be lost."
                ).classes("text-sm")
            with ui.row().classes("gap-2 justify-end q-mt-md"):
                ui.button("Keep", on_click=dlg.close).props("flat dense")
                def do_clear():
                    dlg.close()
                    _clear_all()
                ui.button("Clear All", icon="delete_sweep", on_click=do_clear).props("dense color=negative")
        dlg.open()

    def _clear_all():
        state.generated_questions.clear()
        refresh_questions()

    def _auto_qa_one(idx: int):
        """Auto-run QA check on a single question after regen/improve."""
        if idx >= len(state.generated_questions):
            return
        if not config.ollama_enabled or not config.ollama_model:
            return

        q = state.generated_questions[idx]

        def do_qa():
            return qa_check_question(
                question=q, model=config.ollama_model,
                base_url=config.ollama_url,
            )

        def on_done(issues):
            if idx >= len(state.generated_questions):
                return
            q_ref = state.generated_questions[idx]
            q_ref.tags = [t for t in q_ref.tags if not t.startswith("qa:")]
            if issues:
                for issue in issues:
                    tag = f"qa:{issue.get('severity', 'warning')}:{issue.get('field', 'general')}:{issue['issue']}"
                    q_ref.tags.append(tag)
                error_count = sum(1 for i in issues if i.get("severity") == "error")
                warn_count = len(issues) - error_count
                ui.notify(f"Auto-QA: {error_count} error(s), {warn_count} warning(s)", type="warning" if error_count else "info")
            else:
                ui.notify("Auto-QA: passed", type="positive")
            refresh_questions()

        thread = threading.Thread(target=lambda: _run_threaded(do_qa, on_done), daemon=True)
        thread.start()

    def _ai_improve(idx: int):
        if idx >= len(state.generated_questions):
            return
        if not config.ollama_enabled or not config.ollama_model:
            ui.notify("Ollama not configured — check AI & Docs tab", type="warning")
            return

        q = state.generated_questions[idx]
        ui.notify("Improving question with AI...", type="info")

        def do_improve():
            return improve_question(
                question=q,
                model=config.ollama_model,
                base_url=config.ollama_url,
                system_prompt=config.system_prompt,
            )

        def on_done(result):
            if result:
                state.generated_questions[idx] = result
                ui.notify("Question improved — running QA...", type="positive")
                _auto_qa_one(idx)
            else:
                ui.notify("AI improvement failed — try again or edit manually", type="negative")
                refresh_questions()

        thread = threading.Thread(target=lambda: _run_threaded(do_improve, on_done), daemon=True)
        thread.start()

    def _qa_check(idx: int):
        if idx >= len(state.generated_questions):
            return
        if not config.ollama_enabled or not config.ollama_model:
            ui.notify("Ollama not configured — check AI & Docs tab", type="warning")
            return

        q = state.generated_questions[idx]
        ui.notify("Running QA check...", type="info")

        def do_qa():
            return qa_check_question(
                question=q,
                model=config.ollama_model,
                base_url=config.ollama_url,
            )

        def on_done(issues):
            if not issues:
                ui.notify("QA passed — no issues found", type="positive")
                # Clear any old QA tags
                q.tags = [t for t in q.tags if not t.startswith("qa:")]
                refresh_questions()
            else:
                error_count = sum(1 for i in issues if i.get("severity") == "error")
                warn_count = len(issues) - error_count
                msg = f"QA found {error_count} error(s), {warn_count} warning(s) — auto-fixing..."
                ui.notify(msg, type="warning" if error_count else "info")
                # Auto-fix the question based on QA issues
                _qa_auto_fix(idx, issues)

        thread = threading.Thread(target=lambda: _run_threaded(do_qa, on_done), daemon=True)
        thread.start()

    def _qa_auto_fix(idx: int, issues: List[dict], attempt: int = 1, max_attempts: int = 3):
        """Auto-fix a question based on QA issues, then re-run QA. Loops until clean or max attempts."""
        if idx >= len(state.generated_questions):
            return
        q = state.generated_questions[idx]

        def do_fix():
            return qa_fix_question(
                question=q,
                issues=issues,
                model=config.ollama_model,
                base_url=config.ollama_url,
                system_prompt=config.system_prompt,
            )

        def on_fixed(result):
            if not result:
                ui.notify(f"Auto-fix failed (attempt {attempt}) — manual review needed", type="negative")
                q.tags = [t for t in q.tags if not t.startswith("qa:")]
                for issue in issues:
                    tag = f"qa:{issue.get('severity', 'warning')}:{issue.get('field', 'general')}:{issue['issue']}"
                    q.tags.append(tag)
                refresh_questions()
                return

            state.generated_questions[idx] = result
            ui.notify(f"Auto-fixed (attempt {attempt}) — verifying...", type="positive")

            # Re-run QA to check if fix worked
            def do_recheck():
                return qa_check_question(
                    question=result,
                    model=config.ollama_model,
                    base_url=config.ollama_url,
                )

            def on_rechecked(new_issues):
                if idx >= len(state.generated_questions):
                    return
                q_ref = state.generated_questions[idx]
                q_ref.tags = [t for t in q_ref.tags if not t.startswith("qa:")]

                if not new_issues:
                    ui.notify(f"QA passed after {attempt} fix(es)", type="positive")
                    refresh_questions()
                elif attempt < max_attempts:
                    error_count = sum(1 for i in new_issues if i.get("severity") == "error")
                    warn_count = len(new_issues) - error_count
                    ui.notify(
                        f"Still {error_count} error(s), {warn_count} warning(s) — retrying fix ({attempt + 1}/{max_attempts})...",
                        type="info",
                    )
                    _qa_auto_fix(idx, new_issues, attempt + 1, max_attempts)
                else:
                    # Max attempts reached, store remaining issues
                    for issue in new_issues:
                        tag = f"qa:{issue.get('severity', 'warning')}:{issue.get('field', 'general')}:{issue['issue']}"
                        q_ref.tags.append(tag)
                    ui.notify(
                        f"Auto-fix reached max attempts ({max_attempts}) — {len(new_issues)} issue(s) remain",
                        type="warning",
                    )
                    refresh_questions()

            threading.Thread(target=lambda: _run_threaded(do_recheck, on_rechecked), daemon=True).start()

        threading.Thread(target=lambda: _run_threaded(do_fix, on_fixed), daemon=True).start()

    def _regen_stem(idx: int):
        if idx >= len(state.generated_questions):
            return
        if not config.ollama_enabled or not config.ollama_model:
            ui.notify("Ollama not configured — check AI & Docs tab", type="warning")
            return
        q = state.generated_questions[idx]
        ui.notify("Regenerating stem...", type="info")

        def do_work():
            return regen_stem(
                question=q, model=config.ollama_model,
                base_url=config.ollama_url, system_prompt=config.system_prompt,
            )

        def on_done(result):
            if result:
                ui.notify("Stem regenerated — running QA...", type="positive")
                _auto_qa_one(idx)
            else:
                ui.notify("Stem regeneration failed — try again", type="negative")
                refresh_questions()

        thread = threading.Thread(target=lambda: _run_threaded(do_work, on_done), daemon=True)
        thread.start()

    def _regen_key_btn(idx: int, key_index: int):
        if idx >= len(state.generated_questions):
            return
        if not config.ollama_enabled or not config.ollama_model:
            ui.notify("Ollama not configured — check AI & Docs tab", type="warning")
            return
        q = state.generated_questions[idx]
        ui.notify("Regenerating correct answer...", type="info")

        def do_work():
            return regen_key(
                question=q, key_index=key_index,
                model=config.ollama_model, base_url=config.ollama_url,
                system_prompt=config.system_prompt,
            )

        def on_done(result):
            if result:
                ui.notify("Correct answer regenerated — running QA...", type="positive")
                _auto_qa_one(idx)
            else:
                ui.notify("Key regeneration failed — try again", type="negative")
                refresh_questions()

        thread = threading.Thread(target=lambda: _run_threaded(do_work, on_done), daemon=True)
        thread.start()

    def _regen_dist_btn(idx: int, dist_index: int):
        if idx >= len(state.generated_questions):
            return
        if not config.ollama_enabled or not config.ollama_model:
            ui.notify("Ollama not configured — check AI & Docs tab", type="warning")
            return
        q = state.generated_questions[idx]
        ui.notify("Regenerating distractor...", type="info")

        def do_work():
            return regen_distractor(
                question=q, distractor_index=dist_index,
                model=config.ollama_model, base_url=config.ollama_url,
                system_prompt=config.system_prompt,
            )

        def on_done(result):
            if result:
                ui.notify("Distractor regenerated — running QA...", type="positive")
                _auto_qa_one(idx)
            else:
                ui.notify("Distractor regeneration failed — try again", type="negative")
                refresh_questions()

        thread = threading.Thread(target=lambda: _run_threaded(do_work, on_done), daemon=True)
        thread.start()

    def _run_threaded(work_fn, callback):
        result = work_fn()
        with _callback_anchor:
            ui.timer(0, lambda: (callback(result), False), once=True)

    state.bus.on(EVT_QUESTIONS_CHANGED, refresh_questions)
    refs.save_all_questions = _save_all
    refresh_questions()
