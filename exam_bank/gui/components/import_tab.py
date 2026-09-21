"""Import & Validate tab — thin orchestrator delegating to sub-modules.

Sub-modules:
  import_context.py      — shared mutable context (ImportContext)
  import_validation.py   — validation, QA check, explanation generation
  import_edit_dialog.py  — edit dialog with key/distractor toggle + AI actions
  import_save.py         — save/commit/export to bank + CSV auto-export
"""

import string
from pathlib import Path

from nicegui import ui

from ..state import AppState, UIRefs, LoadedFile, EVT_SLIDE_CHANGED, EVT_FILES_CHANGED
from ..styles import PPTX_CACHE_DIR, format_explanation_html as _format_explanation_html
from .docs_chat import _MERMAID_BLOCK_RE, _render_rich_content
from ...core.bank import Question
from ...core.question_importer import (
    import_from_csv, import_from_json, import_from_text, _is_text_format,
    import_from_qti21, import_from_moodle_xml, detect_xml_format,
    is_pcm_exam_json, import_from_pcm_exam_json,
)
from ...core.spreadsheet_converter import import_from_xlsx, HAS_OPENPYXL
from ...utils.config import config

from .import_context import ImportContext
from . import import_validation as iv
from . import import_edit_dialog as ied
from . import import_save as isv

from ...utils.config import ASSETS_DIR

QUESTIONS_DIR = ASSETS_DIR / "questions"


def build_import_tab(state: AppState, refs: UIRefs):
    """Build the import & validate UI panel."""

    # ── Shared context ────────────────────────────────────
    ctx = ImportContext(state=state, refs=refs)
    container = ui.column().classes("w-full gap-2")
    ctx.callback_anchor = ui.column().style("display: none;")

    # ── PPTX reader management ────────────────────────────

    def _load_reader_for_cert(cert_id: str):
        """Find and load the PPTX reader linked to a certification."""
        ctx.import_reader.update({"reader": None, "source_file": ""})
        if not cert_id:
            return

        pptx_filename = ""
        for fname, cid in config.file_certifications.items():
            if cid == cert_id and not fname.endswith(":topic"):
                pptx_filename = fname
                break
        if not pptx_filename:
            return

        for i, lf in enumerate(state.files):
            if lf.path.name == pptx_filename and lf.reader:
                ctx.import_reader.update({"reader": lf.reader, "source_file": pptx_filename})
                state.selected_file_idx = i
                state.current_slide_idx = 0
                return

        cached_path = PPTX_CACHE_DIR / pptx_filename
        if cached_path.exists():
            lf = LoadedFile(path=cached_path)
            if lf.load():
                lf.certification_id = cert_id
                ctx.import_reader.update({"reader": lf.reader, "source_file": pptx_filename})
                images_dir = PPTX_CACHE_DIR / lf.path.stem
                if images_dir.exists():
                    for idx in range(lf.slide_count):
                        img = images_dir / f"slide_{idx + 1:03d}.png"
                        if img.exists():
                            lf.slide_images[idx] = img
                state.files.append(lf)
                state.selected_file_idx = len(state.files) - 1
                state.current_slide_idx = 0

    # ── helpers ────────────────────────────────────────────

    def _section_help(text: str):
        with ui.row().classes("w-full items-start gap-1 q-mb-sm"):
            ui.icon("help_outline", size="xs").classes("text-grey-5 q-mt-xs")
            ui.label(text).classes("text-xs text-grey-6")

    def _get_cert_options():
        certs = state.db.list_certifications()
        return {c.id: c.name for c in certs}

    # ── Refresh / Render ──────────────────────────────────

    def _refresh():
        container.clear()
        with container:
            if not ctx.imported_questions:
                # ── Friendly empty state ──
                with ui.column().classes("w-full items-center q-pa-lg gap-2"):
                    ui.icon("upload_file", size="48px").classes("text-grey-4")
                    ui.label("No questions imported yet").classes("text-base text-grey-5")
                    with ui.column().classes("items-start gap-1"):
                        with ui.row().classes("items-center gap-2"):
                            ui.badge("1").props("color=primary").classes("text-xs").style("min-width: 20px; text-align: center")
                            ui.label("Select a certification and topic above (optional)").classes("text-xs text-grey-5")
                        with ui.row().classes("items-center gap-2"):
                            ui.badge("2").props("color=primary").classes("text-xs").style("min-width: 20px; text-align: center")
                            ui.label("Upload a file (CSV, JSON, Excel, QTI, or Moodle XML)").classes("text-xs text-grey-5")
                        with ui.row().classes("items-center gap-2"):
                            ui.badge("3").props("color=primary").classes("text-xs").style("min-width: 20px; text-align: center")
                            ui.label("Validate, review, then save to the bank").classes("text-xs text-grey-5")
                return

            total = len(ctx.imported_questions)
            passed = sum(1 for _, p, *_ in ctx.imported_questions if p is True)
            failed = sum(1 for _, p, *_ in ctx.imported_questions if p is False)
            validating = sum(1 for _, p, *_ in ctx.imported_questions if p == "validating")
            pending = total - passed - failed - validating

            # ── Summary badges ──
            with ui.row().classes("gap-2 items-center"):
                ui.label(f"{total} question(s) imported").classes("text-sm font-bold")
                if passed:
                    ui.badge(f"{passed} validated", color="positive").classes("text-xs")
                if failed:
                    ui.badge(f"{failed} failed", color="negative").classes("text-xs")
                if pending:
                    ui.badge(f"{pending} pending", color="grey").classes("text-xs")
                if validating:
                    ui.badge(f"{validating} in progress", color="blue").classes("text-xs")

            # ── Action bar with labels ──
            with ui.row().classes("gap-1 items-center flex-wrap"):
                ui.button("Validate All", icon="verified",
                          on_click=lambda: iv.validate_all(ctx)).props(
                    "flat dense size=sm color=primary"
                ).tooltip("Check all answers against PPTX speaker notes or documentation")
                ui.button("Explain", icon="auto_stories",
                          on_click=lambda: iv.generate_explanations_all(ctx)).props(
                    "flat dense size=sm color=blue"
                ).tooltip("Generate source-backed explanations for validated questions")
                ui.button("QA All", icon="spellcheck",
                          on_click=lambda: iv.qa_all(ctx)).props(
                    "flat dense size=sm color=teal"
                ).tooltip("Check spelling, grammar, and clarity on all questions")
                ui.space()
                ui.button("Save Passed", icon="save",
                          on_click=lambda: isv.save_passed(ctx)).props(
                    "flat dense size=sm color=positive"
                ).tooltip("Save only validated questions to the bank")
                ui.button("Save All", icon="save_alt",
                          on_click=lambda: _confirm_save_all()).props(
                    "flat dense size=sm color=positive outline"
                ).tooltip("Save all questions (including unvalidated) to the bank")
                ui.button("Clear All", icon="delete_sweep",
                          on_click=lambda: _confirm_clear()).props(
                    "flat dense size=sm color=negative"
                ).tooltip("Remove all imported questions")

            # Auto-export indicator
            if config.auto_export_on_save:
                with ui.row().classes("items-center gap-1"):
                    ui.icon("file_download", size="xs").classes("text-grey-5")
                    ui.label("Auto-export CSV is ON — questions will also be saved to assets/questions/").classes("text-xs text-grey-5")

            for i, entry in enumerate(ctx.imported_questions):
                q, passed_flag, details = entry[0], entry[1], entry[2]
                dupe_info = entry[3] if len(entry) > 3 else ""
                _render_import_card(q, passed_flag, details, i, dupe_info, total)

    ctx.refresh = _refresh

    def _render_import_card(q: Question, passed_flag, details: str, idx: int, dupe_info: str, total: int):
        is_validating = passed_flag == "validating"
        if is_validating:
            border = "border-left: 4px solid #3b82f6"
            icon_name, icon_color = "sync", "blue"
            status_text, status_color = "Validating...", "blue"
        elif passed_flag is True:
            border = "border-left: 4px solid #10b981"
            icon_name, icon_color = "check_circle", "green"
            status_text, status_color = "Validated", "positive"
        elif passed_flag is False:
            border = "border-left: 4px solid #ef4444"
            icon_name, icon_color = "cancel", "red"
            status_text, status_color = "Failed", "negative"
        else:
            border = "border-left: 4px solid #9ca3af"
            icon_name, icon_color = "help_outline", "grey"
            status_text, status_color = "Not validated", "grey"

        with ui.card().classes("w-full").style(border):
            # ── Header: question number + status + stem ──
            with ui.row().classes("w-full items-center justify-between"):
                with ui.row().classes("gap-2 items-center"):
                    ui.label(f"Q{idx + 1} of {total}").classes("text-xs text-grey-5 font-mono")
                    if is_validating:
                        ui.spinner("dots", size="sm", color="blue")
                    else:
                        ui.icon(icon_name, color=icon_color, size="sm")
                    ui.badge(status_text, color=status_color).classes("text-xs")
                    ui.label(q.stem[:80] + ("..." if len(q.stem) > 80 else "")).classes("font-medium text-sm")

                # ── Action buttons with labels ──
                with ui.row().classes("gap-1"):
                    ui.button("Edit", icon="edit", on_click=lambda _, i=idx: ied.edit_one(ctx, i)).props(
                        "flat dense size=sm"
                    ).tooltip("Open full editor")
                    ui.button("Validate", icon="verified", on_click=lambda _, i=idx: iv.validate_one(ctx, i)).props(
                        "flat dense size=sm color=primary"
                    ).tooltip("Check answer against source material")
                    ui.button("QA", icon="spellcheck", on_click=lambda _, i=idx: iv.qa_check(ctx, i)).props(
                        "flat dense size=sm color=teal"
                    ).tooltip("Check spelling, grammar, and clarity")
                    ui.button("Save", icon="save", on_click=lambda _, i=idx: isv.save_one(ctx, i, edit_one_fn=lambda j: ied.edit_one(ctx, j))).props(
                        "flat dense size=sm color=positive"
                    ).tooltip("Save to bank")
                    ui.button("Delete", icon="delete", on_click=lambda _, i=idx: _remove_one(i)).props(
                        "flat dense size=sm color=negative"
                    ).tooltip("Remove this question")

            # ── Metadata badges ──
            with ui.row().classes("gap-1 items-center flex-wrap q-mt-xs"):
                if q.certification_id:
                    cert_obj = state.db.get_certification(q.certification_id)
                    cert_label = cert_obj.name if cert_obj else q.certification_id[:8]
                    ui.badge(cert_label, color="blue").props("outline").classes("text-xs")
                if q.topic:
                    ui.badge(q.topic, color="teal").props("outline").classes("text-xs")
                ui.badge(q.difficulty, color="grey").props("outline").classes("text-xs")
                ui.badge(q.bloom_level, color="grey").props("outline").classes("text-xs")
                ui.badge(q.format_label, color="grey").props("outline").classes("text-xs")

            # ── Per-card certification/topic reassignment ──
            with ui.row().classes("gap-2 items-end q-mt-xs"):
                cert_opts = _get_cert_options()
                ui.select(
                    options=cert_opts,
                    value=q.certification_id if q.certification_id in cert_opts else None,
                    label="Certification",
                    on_change=lambda e, qq=q: _reassign_cert(qq, e.value),
                    with_input=True,
                    clearable=True,
                ).classes("min-w-[180px]").props("dense outlined").style("font-size: 0.75rem")
                ui.select(
                    options=state.db.get_topics(),
                    label="Topic",
                    value=q.topic or None,
                    on_change=lambda e, qq=q: _reassign_topic(qq, e.value),
                    with_input=True,
                    new_value_mode="add-unique",
                    clearable=True,
                ).classes("min-w-[160px]").props("dense outlined").style("font-size: 0.75rem")

            # ── Choices ──
            correct_set = set(q.correct_answers)
            all_choices = q.all_choices
            with ui.column().classes("q-ml-md gap-0 q-mt-xs"):
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

            # ── Explanation — expanded by default for review ──
            if q.explanation and q.explanation.strip():
                with ui.expansion("Explanation", icon="school").classes("w-full q-mt-xs").props("dense default-opened"):
                    if _MERMAID_BLOCK_RE.search(q.explanation):
                        _render_rich_content(q.explanation)
                    else:
                        ui.html(_format_explanation_html(q.explanation))

            # ── Validation details ──
            if details:
                with ui.row().classes("gap-1 items-start q-mt-xs"):
                    ui.icon("info_outline", size="xs").classes("text-grey-5 q-mt-xs")
                    ui.label(details).classes("text-xs text-grey-6 italic")

            # ── Duplicate warning — more prominent ──
            if dupe_info:
                with ui.row().classes("gap-1 items-center q-mt-xs q-pa-xs rounded").style(
                    "background: rgba(251, 146, 60, 0.08);"
                ):
                    ui.icon("content_copy", color="orange", size="xs")
                    ui.label(dupe_info).classes("text-xs text-orange")

            # ── QA tags ──
            qa_tags = [t for t in q.tags if t.startswith("qa:")]
            if qa_tags:
                with ui.expansion("QA Results", icon="spellcheck").classes("w-full q-mt-xs").props("dense default-opened"):
                    for tag in qa_tags:
                        parts = tag.split(":", 3)
                        if len(parts) == 4:
                            _, sev, field, issue = parts
                            color = "red" if sev == "error" else "orange"
                            ui.label(f"[{field}] {issue}").classes(f"text-xs text-{color}")

    def _reassign_cert(q: Question, cert_id):
        """Reassign a single question to a different certification."""
        q.certification_id = cert_id or ""
        if cert_id:
            cert_obj = state.db.get_certification(cert_id)
            if cert_obj:
                q.source_type = cert_obj.source_type

    def _reassign_topic(q: Question, topic):
        """Reassign a single question to a different topic."""
        q.topic = topic or ""

    # ── File upload & import ──────────────────────────────

    async def _on_upload(e):
        """Handle file upload."""
        import tempfile
        name = e.file.name
        suffix = Path(name).suffix.lower()

        tmp = Path(tempfile.gettempdir()) / name
        await e.file.save(tmp)

        try:
            ctx.imported_questions.clear()

            if suffix == ".csv":
                if _is_text_format(tmp):
                    questions = import_from_text(tmp)
                    ui.notify(
                        "Detected text-format questions (not CSV). "
                        "All options default to distractors — use the Key/Dist toggle to mark correct answers.",
                        type="info", timeout=6000,
                    )
                else:
                    questions = import_from_csv(tmp)
            elif suffix == ".json":
                # Auto-detect a PCM exam.json (object with questions[].prompt)
                # vs the bank's own export (top-level array of stem/key).
                if is_pcm_exam_json(tmp):
                    questions = import_from_pcm_exam_json(tmp)
                    ui.notify(
                        f"Detected PCM exam.json — imported {len(questions)} question(s) as PCM-sourced drafts.",
                        type="info", timeout=6000,
                    )
                else:
                    questions = import_from_json(tmp)
            elif suffix == ".xlsx":
                if not HAS_OPENPYXL:
                    ui.notify("openpyxl is required for Excel import. Install with: pip install openpyxl", type="negative")
                    _refresh()
                    return
                backup_dir = QUESTIONS_DIR
                questions = import_from_xlsx(tmp, backup_dir=backup_dir)
                ui.notify("Converted CSV backup saved to assets/questions/", type="info")
            elif suffix == ".xml":
                fmt = detect_xml_format(tmp)
                if fmt == 'qti':
                    questions = import_from_qti21(tmp)
                elif fmt == 'moodle':
                    questions = import_from_moodle_xml(tmp)
                else:
                    ui.notify("Unrecognized XML format — expected QTI 2.1 or Moodle XML", type="warning")
                    _refresh()
                    return
            else:
                ui.notify(f"Unsupported format: {suffix} (use CSV, JSON, Excel, or XML)", type="warning")
                _refresh()
                return

            dupe_count = 0
            for q in questions:
                selected_cert = ctx.import_cert_id["value"]
                if selected_cert:
                    q.certification_id = selected_cert
                    cert_obj = state.db.get_certification(selected_cert)
                    if cert_obj:
                        q.source_type = cert_obj.source_type
                elif not q.certification_id:
                    f = state.selected_file
                    if f and f.certification_id:
                        q.certification_id = f.certification_id
                        cert_obj = state.db.get_certification(f.certification_id)
                        if cert_obj:
                            q.source_type = cert_obj.source_type

                selected_topic = ctx.import_topic["value"]
                if selected_topic:
                    q.topic = selected_topic

                dupe_info = ""
                similar = state.db.find_similar_stems_scored(q.stem, threshold=0.85)
                if similar:
                    best_q, best_score = max(similar, key=lambda x: x[1])
                    pct = int(best_score * 100)
                    preview = best_q.stem[:60] + ("..." if len(best_q.stem) > 60 else "")
                    dupe_info = f'Possible duplicate ({pct}% match): "{preview}"'
                    dupe_count += 1

                if q.source_type == "docs":
                    ctx.imported_questions.append((q, True, "Docs-sourced — PPTX validation not needed", dupe_info))
                else:
                    ctx.imported_questions.append((q, None, "Not validated yet", dupe_info))

            msg = f"Imported {len(questions)} question(s) from {name}"
            if dupe_count:
                msg += f" — {dupe_count} possible duplicate(s) flagged"
            ui.notify(msg, type="positive" if not dupe_count else "warning")
        except Exception as ex:
            ui.notify(f"Import error: {ex}", type="negative")
        finally:
            tmp.unlink(missing_ok=True)

        _refresh()

    def _load_from_bank_csv(path_str: str):
        """Re-import questions from an auto-exported bank CSV."""
        p = Path(path_str)
        if not p.exists():
            ui.notify(f"File not found: {p.name}", type="warning")
            return
        ctx.imported_questions.clear()

        try:
            questions = import_from_csv(p)
            dupe_count = 0
            for q in questions:
                selected_cert = ctx.import_cert_id["value"]
                if selected_cert:
                    q.certification_id = selected_cert
                    cert_obj = state.db.get_certification(selected_cert)
                    if cert_obj:
                        q.source_type = cert_obj.source_type
                elif not q.certification_id:
                    f = state.selected_file
                    if f and f.certification_id:
                        q.certification_id = f.certification_id
                        cert_obj = state.db.get_certification(f.certification_id)
                        if cert_obj:
                            q.source_type = cert_obj.source_type

                selected_topic = ctx.import_topic["value"]
                if selected_topic:
                    q.topic = selected_topic

                dupe_info = ""
                similar = state.db.find_similar_stems_scored(q.stem, threshold=0.85)
                if similar:
                    best_q, best_score = max(similar, key=lambda x: x[1])
                    pct = int(best_score * 100)
                    preview = best_q.stem[:60] + ("..." if len(best_q.stem) > 60 else "")
                    dupe_info = f'Possible duplicate ({pct}% match): "{preview}"'
                    dupe_count += 1

                if q.source_type == "docs":
                    ctx.imported_questions.append((q, True, "Docs-sourced — PPTX validation not needed", dupe_info))
                else:
                    ctx.imported_questions.append((q, None, "Not validated yet", dupe_info))

            label = f"{p.parent.name} / {p.stem}" if p.parent.name != "questions" else p.stem
            msg = f"Loaded {len(questions)} question(s) from {label}"
            if dupe_count:
                msg += f" — {dupe_count} possible duplicate(s) flagged"
            ui.notify(msg, type="positive" if not dupe_count else "warning")
        except Exception as ex:
            ui.notify(f"Import error: {ex}", type="negative")

        _refresh()

    def _remove_one(idx: int):
        if idx < len(ctx.imported_questions):
            ctx.imported_questions.pop(idx)
            _refresh()

    def _confirm_clear():
        total = len(ctx.imported_questions)
        if not total:
            return
        with ui.dialog() as dlg, ui.card().classes("q-pa-md").style("min-width: 400px"):
            ui.label("Clear All Imported Questions").classes("text-base font-semibold")
            with ui.row().classes("items-start gap-2 q-mt-xs"):
                ui.icon("warning", color="orange", size="sm")
                ui.label(
                    f"This will remove all {total} imported question(s). "
                    "Unsaved questions will be lost."
                ).classes("text-sm")
            with ui.row().classes("gap-2 justify-end q-mt-md"):
                ui.button("Keep", on_click=dlg.close).props("flat dense")
                def do_clear():
                    dlg.close()
                    ctx.imported_questions.clear()
                    _refresh()
                ui.button("Clear All", icon="delete_sweep", on_click=do_clear).props("dense color=negative")
        dlg.open()

    def _confirm_save_all():
        total = len(ctx.imported_questions)
        if not total:
            return
        passed = sum(1 for _, p, *_ in ctx.imported_questions if p is True)
        unvalidated = total - passed
        with ui.dialog() as dlg, ui.card().classes("q-pa-md").style("min-width: 400px"):
            ui.label("Save All Questions").classes("text-base font-semibold")
            with ui.column().classes("gap-1 q-mt-xs"):
                ui.label(f"{total} question(s) will be saved to the bank.").classes("text-sm")
                if unvalidated:
                    with ui.row().classes("items-start gap-1"):
                        ui.icon("warning", color="orange", size="xs")
                        ui.label(
                            f"{unvalidated} question(s) have not been validated yet."
                        ).classes("text-sm text-orange")
                ui.label(
                    "Questions with errors will be kept for review. Duplicates will be skipped."
                ).classes("text-xs text-grey-5")
            with ui.row().classes("gap-2 justify-end q-mt-md"):
                ui.button("Cancel", on_click=dlg.close).props("flat dense")
                def do_save():
                    dlg.close()
                    isv.save_all(ctx)
                ui.button("Save All", icon="save_alt", on_click=do_save).props("dense color=positive")
        dlg.open()

    # ══════════════════════════════════════════════════════
    # ── Layout ────────────────────────────────────────────
    # ══════════════════════════════════════════════════════

    # ── 1. Import Settings (collapsible) ──────────────────
    with ui.expansion("Import Settings", icon="settings").classes("w-full").props(
        "default-opened dense header-class=section-title"
    ):
        with ui.card().classes("w-full q-pa-md"):
            _section_help(
                "Set a default certification and topic before uploading — they are applied "
                "automatically to all imported questions. You can also change them per question "
                "after import using the dropdowns on each card."
            )

            with ui.row().classes("w-full gap-4 items-end"):
                certs = state.db.list_certifications()
                cert_options = {c.id: c.name for c in certs}
                import_cert_select = ui.select(
                    options=cert_options,
                    label="Default certification",
                    with_input=True,
                    clearable=True,
                ).classes("min-w-[200px]").props("dense outlined").tooltip(
                    "Imported questions will be assigned to this certification"
                )

                import_topic_input = ui.select(
                    options=state.db.get_topics(),
                    label="Default topic",
                    with_input=True,
                    new_value_mode="add-unique",
                    clearable=True,
                ).classes("min-w-[200px]").props("dense outlined").tooltip(
                    "Imported questions will be assigned to this topic. Type to create a new one."
                )

            # ── Validation mode + auto-fix ──
            ui.separator().classes("q-my-sm")
            ui.label("Validation mode").classes("text-xs font-semibold")
            ui.label(
                "How should imported questions be validated? PPTX checks answers against "
                "slide speaker notes. Docs checks against MCP documentation servers."
            ).classes("text-xs text-grey-5 q-mb-xs")

            with ui.row().classes("w-full gap-4 items-center"):
                mode_toggle = ui.toggle(
                    {"pptx": "PPTX", "docs": "Docs"},
                    value="pptx",
                ).props("dense size=sm no-caps")

                mode_badge = ui.badge("", color="blue").props("outline").classes("text-xs")
                mode_badge.set_visibility(False)

                autofix_cb = ui.checkbox(
                    "Auto-fix warnings",
                    value=False,
                    on_change=lambda e: ctx.autofix_enabled.update({"value": e.value}),
                ).props("dense size=sm")
                ui.icon("help_outline", size="xs").classes("text-grey-5 cursor-pointer").tooltip(
                    "When enabled, AI may rewrite keys/distractors to fix quality warnings "
                    "(e.g. unbalanced length, duplicates). Off by default to preserve imported text."
                )

            def _update_mode_badge():
                mode = ctx.validation_mode["value"]
                if mode == "pptx":
                    if ctx.import_reader["reader"]:
                        mode_badge.set_text(f"PPTX: {ctx.import_reader['source_file']}")
                        mode_badge.props("color=blue")
                    else:
                        mode_badge.set_text("PPTX: no file linked — load one in the sidebar")
                        mode_badge.props("color=orange")
                    mode_badge.set_visibility(True)
                elif mode == "docs":
                    n = len(config.mcp_servers)
                    if config.mcp_enabled and n:
                        mode_badge.set_text(f"Docs: {n} MCP server(s) available")
                        mode_badge.props("color=teal")
                    else:
                        mode_badge.set_text("Docs: enable MCP servers in AI & Docs tab")
                        mode_badge.props("color=orange")
                    mode_badge.set_visibility(True)

            # Apply distinct styling to PPTX/Docs toggle buttons
            def _style_mode_toggle():
                mode = ctx.validation_mode["value"]
                if mode == "pptx":
                    mode_toggle.props("color=blue")
                else:
                    mode_toggle.props("color=teal")

            def _on_mode_toggle(e):
                ctx.validation_mode.update({"value": e.value or "pptx"})
                _style_mode_toggle()
                _update_mode_badge()

            mode_toggle.on_value_change(_on_mode_toggle)
            _style_mode_toggle()

            def _on_cert_change(e):
                cert_id = e.value or ""
                ctx.import_cert_id.update({"value": cert_id})
                if cert_id:
                    topics = state.db.get_topics(certification_id=cert_id)
                else:
                    topics = state.db.get_topics()
                import_topic_input.options = topics
                import_topic_input.update()
                if cert_id:
                    cert_obj = state.db.get_certification(cert_id)
                    if cert_obj:
                        detected_mode = cert_obj.source_type or "pptx"
                        ctx.validation_mode.update({"value": detected_mode})
                        mode_toggle.set_value(detected_mode)
                        _style_mode_toggle()
                        if detected_mode == "pptx":
                            _load_reader_for_cert(cert_id)
                            if ctx.import_reader["reader"]:
                                ui.notify(
                                    f"PPTX mode — loaded {ctx.import_reader['source_file']} "
                                    f"({state.selected_file.slide_count if state.selected_file else 0} slides)",
                                    type="info",
                                )
                                state.bus.emit_many(EVT_SLIDE_CHANGED, EVT_FILES_CHANGED)
                            else:
                                ui.notify("PPTX mode — no PPTX linked yet. Load one in the sidebar first.", type="warning")
                        else:
                            if config.mcp_enabled and config.mcp_servers:
                                ui.notify(f"Docs mode — will validate against {len(config.mcp_servers)} MCP server(s)", type="info")
                            else:
                                ui.notify("Docs mode — enable MCP servers in AI & Docs tab first", type="warning")
                _update_mode_badge()

            import_cert_select.on_value_change(_on_cert_change)
            import_topic_input.on_value_change(lambda e: ctx.import_topic.update({"value": e.value or ""}))

    # ── 2. Upload area ────────────────────────────────────
    with ui.expansion("Upload Questions", icon="upload_file").classes("w-full").props(
        "default-opened dense header-class=section-title"
    ):
        with ui.card().classes("w-full q-pa-md"):
            _section_help(
                "Drag and drop a file or click to browse. Supported formats: CSV, JSON, "
                "Excel (.xlsx), QTI 2.1 XML, and Moodle XML. Questions are loaded into "
                "the review list below."
            )

            ui.upload(
                label="Drop file here or click to browse  (CSV, JSON, Excel, QTI, Moodle XML)",
                on_upload=_on_upload,
                auto_upload=True,
            ).props('accept=".csv,.json,.xlsx,.xml" flat bordered').classes("w-full")

            # ── Recent Bank CSVs ──
            recent_container = ui.column().classes("w-full gap-0 q-mt-sm")

            def _refresh_recent():
                recent_container.clear()
                csv_files = sorted(
                    QUESTIONS_DIR.rglob("*.csv"),
                    key=lambda f: f.stat().st_mtime,
                    reverse=True,
                ) if QUESTIONS_DIR.exists() else []
                if not csv_files:
                    return
                from datetime import datetime
                options_map = {}
                for cf in csv_files[:20]:
                    mtime = datetime.fromtimestamp(cf.stat().st_mtime)
                    ts = mtime.strftime("%Y-%m-%d %H:%M")
                    name_part = f"{cf.parent.name} / {cf.stem}" if cf.parent != QUESTIONS_DIR else cf.stem
                    label = f"{name_part}  [{ts}]"
                    options_map[str(cf)] = label
                with recent_container:
                    ui.label("Or reload from a previous export:").classes("text-xs text-grey-5 q-mt-xs")
                    recent_sel = ui.select(
                        options=options_map, label="Recent bank CSVs",
                    ).props("dense outlined").classes("w-full")

                    def _on_recent(e):
                        if e.value:
                            _load_from_bank_csv(e.value)
                            recent_sel.value = None

                    recent_sel.on_value_change(_on_recent)

            _refresh_recent()

    # ── 3. Imported Questions ─────────────────────────────
    ui.separator().classes("q-my-sm")
    with ui.row().classes("w-full items-start gap-1 q-mb-xs"):
        ui.icon("help_outline", size="xs").classes("text-grey-5 q-mt-xs")
        ui.label(
            "Review imported questions below. Validate against source material, refine "
            "with AI, then save to the bank. You can reassign each question to a different "
            "certification or topic using the dropdowns on each card."
        ).classes("text-xs text-grey-6")

    _refresh()
