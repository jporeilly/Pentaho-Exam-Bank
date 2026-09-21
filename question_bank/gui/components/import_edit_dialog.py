"""Edit dialog for imported questions — unified Answer Options with Key/Distractor toggle."""

import threading

from nicegui import ui

from ...core.question_bank import Question, BLOOM_LEVELS, DIFFICULTIES
from ...core.question_generator import (
    improve_question, regen_stem, regen_key, regen_distractor,
    qa_check_question, qa_fix_question,
)
from ...utils.config import config
from .import_context import ImportContext


def run_threaded(ctx: ImportContext, work_fn, callback):
    """Run work_fn in a thread, schedule callback on main thread via _callback_anchor."""
    def _run():
        result = work_fn()
        with ctx.callback_anchor:
            ui.timer(0, lambda: (callback(result), False), once=True)
    threading.Thread(target=_run, daemon=True).start()


def edit_one(ctx: ImportContext, idx: int):
    """Open an edit dialog for an imported question with AI action buttons."""
    if idx >= len(ctx.imported_questions):
        return
    entry = ctx.imported_questions[idx]
    q, passed_flag, details = entry[0], entry[1], entry[2]

    with ui.dialog() as dlg, ui.card().classes("q-pa-md").style("min-width: 650px; max-width: 850px;"):
        ui.label("Edit Imported Question").classes("text-base font-bold")

        # AI action buttons
        has_ai = config.ollama_enabled and config.ollama_model
        with ui.row().classes("gap-1 q-mb-sm"):
            ui.button("AI Improve", icon="auto_fix_high",
                      on_click=lambda: _ai_improve(ctx, idx, dlg)).props(
                f"flat dense size=sm color=purple {'disabled' if not has_ai else ''}"
            ).tooltip("Rewrite with AI for better quality")
            ui.button("Regen Stem", icon="refresh",
                      on_click=lambda: _regen_stem(ctx, idx, dlg)).props(
                f"flat dense size=sm color=primary {'disabled' if not has_ai else ''}"
            ).tooltip("Regenerate stem (keep choices)")
            ui.button("QA Check", icon="spellcheck",
                      on_click=lambda: (_sync_form_to_q(), _qa_check_from_dialog(ctx, idx, dlg))).props(
                f"flat dense size=sm color=teal {'disabled' if not has_ai else ''}"
            ).tooltip("Check spelling, grammar, and clarity")
            if not has_ai:
                ui.label("AI features need Ollama — check AI & Docs tab").classes("text-xs text-grey-5")

        # ── Certification & Topic assignment ──
        certs = ctx.state.db.list_certifications()
        cert_options = {c.id: c.name for c in certs}
        with ui.row().classes("w-full gap-2 items-end q-mb-xs"):
            cert_sel = ui.select(
                options=cert_options,
                value=q.certification_id if q.certification_id in cert_options else None,
                label="Certification",
                with_input=True,
                clearable=True,
            ).classes("flex-grow").props("dense outlined").tooltip(
                "Assign this question to a certification"
            )
            topic_sel = ui.select(
                options=ctx.state.db.get_topics(),
                value=q.topic or None,
                label="Topic",
                with_input=True,
                new_value_mode="add-unique",
                clearable=True,
            ).classes("flex-grow").props("dense outlined").tooltip(
                "Assign or create a topic for this question"
            )

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

        # Unified answer options with key/distractor toggle
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

        option_rows: list = []  # [(input_el, toggle_el)]
        options_container = ui.column().classes("w-full gap-1")

        def _rebuild_options():
            """Rebuild the options UI from all_options_data."""
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
                        ).tooltip("Click to toggle between Key and Distractor")
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
            """Save current input values back to all_options_data before rebuild."""
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

        _rebuild_options()

        explanation_input = ui.textarea(
            label="Explanation (why each answer is correct or incorrect)", value=q.explanation
        ).classes("w-full").props("dense outlined autogrow")

        key_source_input = ui.textarea(
            label="Key Source Text (exact quote from speaker notes that proves the answer)",
            value=q.key_source_text,
        ).classes("w-full").props("dense outlined autogrow")

        with ui.row().classes("gap-2"):
            diff_sel = ui.select(DIFFICULTIES, value=q.difficulty, label="Difficulty").props("dense outlined")
            bloom_sel = ui.select(BLOOM_LEVELS, value=q.bloom_level, label="Bloom Level").props("dense outlined")

        # Slide assignment info
        if q.source_slides:
            ui.label(
                f"Assigned to slide(s): {', '.join(str(s + 1) for s in q.source_slides)}"
            ).classes("text-xs text-blue-8 q-mt-xs")
        if q.key_source_slide >= 0:
            ui.label(
                f"Key source: slide {q.key_source_slide + 1}"
            ).classes("text-xs text-blue-8")

        # Validation preview
        validation_container = ui.column().classes("w-full q-mt-sm")

        def _show_validation():
            validation_container.clear()
            with validation_container:
                q_errors, q_warnings = q.validate_detailed()
                if q_errors:
                    with ui.row().classes("gap-1 items-center flex-wrap"):
                        ui.icon("error", color="red", size="xs")
                        for e in q_errors:
                            ui.label(e).classes("text-xs text-red")
                if q_warnings:
                    with ui.row().classes("gap-1 items-center flex-wrap"):
                        ui.icon("warning", color="orange", size="xs")
                        for w in q_warnings:
                            ui.label(w).classes("text-xs text-orange")
                if not q_errors and not q_warnings:
                    with ui.row().classes("gap-1 items-center"):
                        ui.icon("check_circle", color="green", size="xs")
                        ui.label("All checks passed").classes("text-xs text-positive")

        _show_validation()

        # QA results
        qa_tags = [t for t in q.tags if t.startswith("qa:")]
        if qa_tags:
            errors = [t for t in qa_tags if t.startswith("qa:error:")]
            warnings = [t for t in qa_tags if t.startswith("qa:warning:")]
            label = f"QA: {len(errors)} error(s), {len(warnings)} warning(s)" if errors else f"QA: {len(warnings)} warning(s)"
            with ui.expansion(label, icon="spellcheck").classes("w-full q-mt-xs").props("dense"):
                for tag in qa_tags:
                    parts = tag.split(":", 4)
                    if len(parts) >= 4:
                        sev = parts[1]
                        fld = parts[2]
                        issue = parts[-1]
                        icon = "error" if sev == "error" else "warning"
                        color = "red" if sev == "error" else "orange"
                        with ui.row().classes("items-center gap-1 q-my-none"):
                            ui.icon(icon, color=color, size="xs")
                            ui.badge(fld, color=color).props("outline dense")
                            ui.label(issue).classes(f"text-xs text-{color}")

        def _sync_form_to_q():
            """Sync form field values back to the question object."""
            q.scenario = scenario_input.value
            q.question_type = type_select.value
            q.stem = stem_input.value
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
            q.explanation = explanation_input.value
            q.key_source_text = key_source_input.value
            q.difficulty = diff_sel.value
            q.bloom_level = bloom_sel.value
            # Certification & topic from header selects
            q.certification_id = cert_sel.value or ""
            if cert_sel.value:
                cert_obj = ctx.state.db.get_certification(cert_sel.value)
                if cert_obj:
                    q.source_type = cert_obj.source_type
            q.topic = topic_sel.value or ""

        with ui.row().classes("gap-2 justify-end q-mt-sm"):
            ui.button("Cancel", icon="close", on_click=dlg.close).props("flat")

            def apply_edits():
                _sync_form_to_q()
                errors, _ = q.validate_detailed()
                if errors:
                    ui.notify(f"{len(errors)} error(s) remain — fix before saving", type="warning")
                else:
                    ui.notify("Question updated", type="positive")
                dlg.close()
                ctx.refresh()

            ui.button("Apply", icon="check", on_click=apply_edits).props("color=positive")

    dlg.open()


# ── AI helpers (called from edit dialog) ──────────────────


def _ai_improve(ctx: ImportContext, idx: int, dlg):
    """AI Improve for an imported question — closes dialog, refreshes after."""
    if idx >= len(ctx.imported_questions):
        return
    if not config.ollama_enabled or not config.ollama_model:
        ui.notify("Ollama not configured", type="warning")
        return
    q = ctx.imported_questions[idx][0]
    dlg.close()
    ui.notify("Improving question with AI...", type="info")

    def do_work():
        return improve_question(
            question=q, model=config.ollama_model,
            base_url=config.ollama_url, system_prompt=config.system_prompt,
        )

    def on_done(result):
        if result:
            old = ctx.imported_questions[idx]
            ctx.imported_questions[idx] = (result, old[1], old[2], old[3] if len(old) > 3 else "")
            ui.notify("Question improved", type="positive")
        else:
            ui.notify("AI improvement failed", type="negative")
        ctx.refresh()

    run_threaded(ctx, do_work, on_done)


def _regen_stem(ctx: ImportContext, idx: int, dlg):
    """Regenerate stem for an imported question."""
    if idx >= len(ctx.imported_questions):
        return
    if not config.ollama_enabled or not config.ollama_model:
        ui.notify("Ollama not configured", type="warning")
        return
    q = ctx.imported_questions[idx][0]
    dlg.close()
    ui.notify("Regenerating stem...", type="info")

    def do_work():
        return regen_stem(
            question=q, model=config.ollama_model,
            base_url=config.ollama_url, system_prompt=config.system_prompt,
        )

    def on_done(result):
        if result:
            ui.notify("Stem regenerated", type="positive")
        else:
            ui.notify("Stem regeneration failed", type="negative")
        ctx.refresh()

    run_threaded(ctx, do_work, on_done)


def _regen_key_import(ctx: ImportContext, idx: int, key_index: int, dlg):
    """Regenerate correct answer for an imported question."""
    if idx >= len(ctx.imported_questions):
        return
    if not config.ollama_enabled or not config.ollama_model:
        ui.notify("Ollama not configured", type="warning")
        return
    q = ctx.imported_questions[idx][0]
    dlg.close()
    ui.notify("Regenerating correct answer...", type="info")

    def do_work():
        return regen_key(
            question=q, key_index=key_index,
            model=config.ollama_model, base_url=config.ollama_url,
            system_prompt=config.system_prompt,
        )

    def on_done(result):
        if result:
            ui.notify("Correct answer regenerated", type="positive")
        else:
            ui.notify("Key regeneration failed", type="negative")
        ctx.refresh()

    run_threaded(ctx, do_work, on_done)


def _regen_dist_import(ctx: ImportContext, idx: int, dist_index: int, dlg):
    """Regenerate a distractor for an imported question."""
    if idx >= len(ctx.imported_questions):
        return
    if not config.ollama_enabled or not config.ollama_model:
        ui.notify("Ollama not configured", type="warning")
        return
    q = ctx.imported_questions[idx][0]
    dlg.close()
    ui.notify("Regenerating distractor...", type="info")

    def do_work():
        return regen_distractor(
            question=q, distractor_index=dist_index,
            model=config.ollama_model, base_url=config.ollama_url,
            system_prompt=config.system_prompt,
        )

    def on_done(result):
        if result:
            ui.notify("Distractor regenerated", type="positive")
        else:
            ui.notify("Distractor regeneration failed", type="negative")
        ctx.refresh()

    run_threaded(ctx, do_work, on_done)


def _qa_check_from_dialog(ctx: ImportContext, idx: int, dlg):
    """Run QA check from inside the edit dialog."""
    if idx >= len(ctx.imported_questions):
        return
    if not config.ollama_enabled or not config.ollama_model:
        ui.notify("Ollama not configured", type="warning")
        return
    dlg.close()
    ui.notify("Running QA check...", type="info")
    # Delegate to the validation module's qa_check
    from .import_validation import qa_check
    qa_check(ctx, idx)
