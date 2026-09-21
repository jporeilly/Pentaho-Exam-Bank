"""Validation and QA checking logic for imported questions."""

import threading

from nicegui import ui

from ...core.bank import Question
from ...core.question_importer import (
    validate_question_against_pptx, validate_question_against_docs,
)
from ...core.question_generator import (
    ai_assign_keys, generate_explanation, _get_fixable_warnings, _auto_fix_question,
    qa_check_question, qa_fix_question,
)
from ...utils.config import config
from .import_context import ImportContext


def _qa_issue_tag(iss: dict) -> str:
    """Build a qa tag string from an issue dict."""
    sev = iss.get("severity", "warning")
    fld = iss.get("field", "general")
    return f"qa:{sev}:{fld}:{iss.get('issue', '')}"


def get_validation_reader(ctx: ImportContext):
    """Get the best available PPTX reader for validation.

    Priority: 1) import_reader (auto-loaded from certification), 2) sidebar file.
    Returns (reader, source_filename) or (None, "").
    """
    if ctx.import_reader["reader"]:
        return ctx.import_reader["reader"], ctx.import_reader["source_file"]
    f = ctx.state.selected_file
    if f and f.reader:
        return f.reader, f.path.name
    return None, ""


def _maybe_generate_explanation(ctx: ImportContext, q: Question, reader, slide_idx: int):
    """Generate an explanation from speaker notes if Ollama is available and question has none."""
    if q.explanation and q.explanation.strip():
        return
    if not config.ollama_enabled or not config.ollama_model:
        return
    if slide_idx < 0 or not reader or slide_idx >= reader.slide_count:
        return
    slide = reader.get_slide(slide_idx)
    notes = (slide.speaker_notes or "").strip() if slide else ""
    if not notes:
        return
    explanation = generate_explanation(
        question=q, speaker_notes=notes,
        model=config.ollama_model, base_url=config.ollama_url,
    )
    if explanation:
        q.explanation = explanation


def _get_slide_image(ctx: ImportContext, slide_idx: int) -> str:
    """Get the file path to a slide's exported PNG image, or empty string."""
    f = ctx.state.selected_file
    if f and 0 <= slide_idx < len(f.slide_images) and f.slide_images[slide_idx]:
        return str(f.slide_images[slide_idx])
    return ""


def _assign_cert_from_file(ctx: ImportContext, q: Question):
    """Assign certification from selected cert or loaded file."""
    selected_cert = ctx.import_cert_id["value"]
    if selected_cert:
        q.certification_id = selected_cert
    elif not q.certification_id:
        f = ctx.state.selected_file
        if f and f.certification_id:
            q.certification_id = f.certification_id

    selected_topic = ctx.import_topic["value"]
    if selected_topic:
        q.topic = selected_topic


def validate_one_pptx(ctx: ImportContext, idx: int, q: Question, dupe_info: str):
    """Validate a single question against PPTX speaker notes."""
    reader, source_file = get_validation_reader(ctx)
    if not reader:
        ui.notify("No PPTX linked — select a PPTX certification or load a file in the sidebar", type="warning")
        return

    needs_ai = (
        "key-unverified" in q.tags
        and not q.correct_answers
        and q.distractors
        and config.ollama_enabled
        and config.ollama_model
    )

    if needs_ai:
        slide_idx = q.key_source_slide
        if slide_idx < 0 and q.source_slides:
            slide_idx = q.source_slides[0]

        notes = ""
        if 0 <= slide_idx < reader.slide_count:
            slide = reader.slides[slide_idx]
            notes = (slide.speaker_notes or "").strip()
            if not notes:
                notes = (slide.body_text or "").strip()

        if not notes:
            for slide in reader.slides:
                n = (slide.speaker_notes or "").strip()
                if n:
                    notes = n
                    slide_idx = slide.index
                    break

        if notes:
            slide_image = _get_slide_image(ctx, slide_idx)
            success = ai_assign_keys(
                question=q,
                speaker_notes=notes,
                model=config.ollama_model,
                base_url=config.ollama_url,
                slide_image=slide_image,
            )
            if success:
                q.key_source_slide = slide_idx
                q.source_slides = list(set(q.source_slides + [slide_idx]))
                q.source_file = source_file
                _assign_cert_from_file(ctx, q)

                passed, match_text, v_slide, details = validate_question_against_pptx(
                    q, reader, source_file
                )
                if passed and v_slide >= 0:
                    details += f" → Slide {v_slide + 1} assigned"

                # Optional auto-fix loop (off by default — preserves imported text)
                if ctx.autofix_enabled["value"] and config.ollama_enabled and config.ollama_model:
                    for attempt in range(2):
                        fix_warnings = _get_fixable_warnings(q)
                        if not fix_warnings:
                            break
                        fixed = _auto_fix_question(
                            q, fix_warnings,
                            model=config.ollama_model, base_url=config.ollama_url,
                        )
                        if fixed:
                            q = fixed
                        else:
                            break

                ctx.imported_questions[idx] = (q, passed if passed else True, details if passed else (
                    f"AI assigned keys from slide {slide_idx + 1}"
                ), dupe_info)
                return

    # Standard text-match validation (or AI unavailable)
    passed, match_text, slide_idx, details = validate_question_against_pptx(
        q, reader, source_file
    )
    if passed:
        _assign_cert_from_file(ctx, q)
        if slide_idx >= 0:
            details += f" → Slide {slide_idx + 1} assigned"
        _maybe_generate_explanation(ctx, q, reader, slide_idx)
    ctx.imported_questions[idx] = (q, passed, details, dupe_info)


def validate_one_docs(ctx: ImportContext, idx: int, q: Question, dupe_info: str):
    """Validate a single question against MCP documentation servers."""
    if not config.mcp_enabled or not config.mcp_servers:
        ui.notify("MCP servers not enabled — configure in AI & Docs tab", type="warning")
        return
    servers = config.mcp_servers
    passed, match_text, details = validate_question_against_docs(q, servers)
    if passed:
        _assign_cert_from_file(ctx, q)
        q.source_type = "docs"
    ctx.imported_questions[idx] = (q, passed, details, dupe_info)


def validate_one(ctx: ImportContext, idx: int):
    """Validate a single imported question (dispatches to PPTX or Docs mode)."""
    if idx >= len(ctx.imported_questions):
        return
    entry = ctx.imported_questions[idx]
    q, dupe_info = entry[0], entry[3] if len(entry) > 3 else ""

    mode = ctx.validation_mode["value"]

    needs_ai = (
        "key-unverified" in q.tags
        and not q.correct_answers
        and q.distractors
        and config.ollama_enabled
        and config.ollama_model
    )

    if needs_ai:
        ui.notify(f"Q{idx + 1}: Starting AI key assignment…", type="info")
        ctx.imported_questions[idx] = (q, "validating", "AI key assignment in progress…", dupe_info)
        with ctx.callback_anchor:
            ui.timer(0, lambda: (ctx.refresh(), False), once=True)

        def _run():
            if mode == "docs":
                validate_one_docs(ctx, idx, q, dupe_info)
            else:
                validate_one_pptx(ctx, idx, q, dupe_info)

            def _done():
                result = ctx.imported_questions[idx][1] if idx < len(ctx.imported_questions) else None
                status = "passed" if result is True else "failed"
                ui.notify(f"Q{idx + 1} validation {status}", type="positive" if result is True else "warning")
                ctx.refresh()

            with ctx.callback_anchor:
                ui.timer(0, lambda: (_done(), False), once=True)

        threading.Thread(target=_run, daemon=True).start()
    else:
        if mode == "docs":
            validate_one_docs(ctx, idx, q, dupe_info)
        else:
            validate_one_pptx(ctx, idx, q, dupe_info)
        ctx.refresh()


def validate_all(ctx: ImportContext):
    """Validate all imported questions."""
    if not ctx.imported_questions:
        return

    mode = ctx.validation_mode["value"]

    has_unverified = any(
        "key-unverified" in entry[0].tags
        and not entry[0].correct_answers
        and entry[0].distractors
        for entry in ctx.imported_questions
    )
    has_ai = config.ollama_enabled and config.ollama_model

    if has_unverified and has_ai:
        total = len(ctx.imported_questions)
        ui.notify(f"Validating {total} question(s) with AI key assignment…", type="info")
        for i, entry in enumerate(ctx.imported_questions):
            q_entry = entry[0]
            di = entry[3] if len(entry) > 3 else ""
            ctx.imported_questions[i] = (q_entry, "validating", "Queued for AI validation…", di)
        with ctx.callback_anchor:
            ui.timer(0, lambda: (ctx.refresh(), False), once=True)

        def do_validate():
            passed_count = 0
            for i, entry in enumerate(ctx.imported_questions):
                q = entry[0]
                dupe_info = entry[3] if len(entry) > 3 else ""

                ctx.imported_questions[i] = (q, "validating", f"AI validating Q{i + 1}…", dupe_info)

                def _refresh_card():
                    ctx.refresh()
                with ctx.callback_anchor:
                    ui.timer(0, lambda cb=_refresh_card: (cb(), False), once=True)

                if mode == "pptx":
                    validate_one_pptx(ctx, i, q, dupe_info)
                else:
                    validate_one_docs(ctx, i, q, dupe_info)

                if ctx.imported_questions[i][1] is True:
                    passed_count += 1

                def _notify(done=i + 1, tot=total, pc=passed_count):
                    ui.notify(f"Validated {done}/{tot} ({pc} passed)", type="info")
                    ctx.refresh()
                with ctx.callback_anchor:
                    ui.timer(0, lambda cb=_notify: (cb(), False), once=True)

            return passed_count

        def on_done(passed_count):
            ui.notify(
                f"Validation complete — {passed_count}/{len(ctx.imported_questions)} passed ({mode.upper()} mode)",
                type="positive" if passed_count else "warning",
            )
            ctx.refresh()

        def run():
            result = do_validate()
            with ctx.callback_anchor:
                ui.timer(0, lambda: (on_done(result), False), once=True)

        threading.Thread(target=run, daemon=True).start()
    else:
        # Fast path: no AI needed, run synchronously
        reader, source_file = get_validation_reader(ctx)
        for i, entry in enumerate(ctx.imported_questions):
            q = entry[0]
            dupe_info = entry[3] if len(entry) > 3 else ""

            if mode == "pptx":
                passed, match_text, slide_idx, details = validate_question_against_pptx(
                    q, reader, source_file
                )
                if passed:
                    _assign_cert_from_file(ctx, q)
                    if slide_idx >= 0:
                        details += f" → Slide {slide_idx + 1} assigned"
                ctx.imported_questions[i] = (q, passed, details, dupe_info)
            else:
                passed, match_text, details = validate_question_against_docs(
                    q, config.mcp_servers
                )
                if passed:
                    _assign_cert_from_file(ctx, q)
                    q.source_type = "docs"
                ctx.imported_questions[i] = (q, passed, details, dupe_info)

        passed_count = sum(1 for _, p, *_ in ctx.imported_questions if p is True)
        ui.notify(f"Validation complete — {passed_count}/{len(ctx.imported_questions)} passed ({mode.upper()} mode)", type="info")
        ctx.refresh()


def generate_explanations_all(ctx: ImportContext):
    """Generate explanations from speaker notes for all validated PPTX questions (background)."""
    if not config.ollama_enabled or not config.ollama_model:
        ui.notify("Ollama not configured — check AI & Docs", type="warning")
        return
    reader, _ = get_validation_reader(ctx)
    if not reader:
        ui.notify("No PPTX loaded — validate questions first", type="warning")
        return

    targets = []
    for i, entry in enumerate(ctx.imported_questions):
        q = entry[0]
        if entry[1] is True and not (q.explanation and q.explanation.strip()):
            slide_idx = q.key_source_slide
            if slide_idx < 0 and q.source_slides:
                slide_idx = q.source_slides[0]
            if slide_idx >= 0 and slide_idx < reader.slide_count:
                targets.append((i, q, slide_idx))

    if not targets:
        ui.notify("No questions need explanations", type="info")
        return

    total = len(targets)
    ui.notify(f"Generating explanations for {total} question(s)…", type="info")

    def do_gen():
        done = 0
        for i, q, slide_idx in targets:
            slide = reader.get_slide(slide_idx)
            notes = (slide.speaker_notes or "").strip() if slide else ""
            if notes:
                explanation = generate_explanation(
                    question=q, speaker_notes=notes,
                    model=config.ollama_model, base_url=config.ollama_url,
                )
                if explanation:
                    q.explanation = explanation
            done += 1
            if done % 3 == 0 or done == total:
                def _notify(d=done, t=total):
                    ui.notify(f"Explanations: {d}/{t}", type="info")
                    ctx.refresh()
                with ctx.callback_anchor:
                    ui.timer(0, lambda cb=_notify: (cb(), False), once=True)

    def on_done():
        ui.notify(f"Generated explanations for {total} question(s)", type="positive")
        ctx.refresh()

    def run():
        do_gen()
        with ctx.callback_anchor:
            ui.timer(0, lambda: (on_done(), False), once=True)

    threading.Thread(target=run, daemon=True).start()


def qa_check(ctx: ImportContext, idx: int):
    """Run QA check on a single imported question."""
    if idx >= len(ctx.imported_questions):
        return
    if not config.ollama_enabled or not config.ollama_model:
        ui.notify("Ollama not configured — check AI & Docs", type="warning")
        return

    entry = ctx.imported_questions[idx]
    q = entry[0]
    dupe_info = entry[3] if len(entry) > 3 else ""

    ctx.imported_questions[idx] = (q, "validating", "Running QA check…", dupe_info)
    with ctx.callback_anchor:
        ui.timer(0, lambda: (ctx.refresh(), False), once=True)

    def do_qa():
        return qa_check_question(
            question=q, model=config.ollama_model,
            base_url=config.ollama_url,
        )

    def on_done(issues):
        if idx >= len(ctx.imported_questions):
            return
        q_ref = ctx.imported_questions[idx][0]
        q_ref.tags = [t for t in q_ref.tags if not t.startswith("qa:")]
        if not issues:
            ui.notify("QA passed — no issues found", type="positive")
            ctx.refresh()
        else:
            error_count = sum(1 for i in issues if i.get("severity") == "error")
            warn_count = len(issues) - error_count
            ui.notify(f"QA: {error_count} error(s), {warn_count} warning(s) — auto-fixing...",
                      type="warning" if error_count else "info")
            _import_qa_fix(ctx, idx, issues)

    def run_qa():
        result = do_qa()
        with ctx.callback_anchor:
            ui.timer(0, lambda: (on_done(result), False), once=True)

    threading.Thread(target=run_qa, daemon=True).start()


def _import_qa_fix(ctx: ImportContext, fix_idx: int, fix_issues: list, attempt: int = 1, max_attempts: int = 3):
    """Auto-fix QA issues and re-check, up to max_attempts."""
    if fix_idx >= len(ctx.imported_questions):
        return
    fix_q = ctx.imported_questions[fix_idx][0]

    def do_fix():
        return qa_fix_question(
            question=fix_q, issues=fix_issues,
            model=config.ollama_model, base_url=config.ollama_url,
            system_prompt=config.system_prompt,
        )

    def on_fixed(result):
        if not result:
            ui.notify(f"Auto-fix failed (attempt {attempt})", type="negative")
            fix_q.tags = [t for t in fix_q.tags if not t.startswith("qa:")]
            for iss in fix_issues:
                tag = _qa_issue_tag(iss)
                fix_q.tags.append(tag)
            ctx.refresh()
            return

        ui.notify(f"Auto-fixed (attempt {attempt}) — verifying...", type="positive")

        def do_recheck():
            return qa_check_question(
                question=result, model=config.ollama_model,
                base_url=config.ollama_url,
            )

        def on_rechecked(new_issues):
            if fix_idx >= len(ctx.imported_questions):
                return
            q_r = ctx.imported_questions[fix_idx][0]
            q_r.tags = [t for t in q_r.tags if not t.startswith("qa:")]
            if not new_issues:
                ui.notify(f"QA passed after {attempt} fix(es)", type="positive")
                ctx.refresh()
            elif attempt < max_attempts:
                ui.notify(f"Still issues — retrying ({attempt + 1}/{max_attempts})...", type="info")
                _import_qa_fix(ctx, fix_idx, new_issues, attempt + 1, max_attempts)
            else:
                for iss in new_issues:
                    tag = _qa_issue_tag(iss)
                    q_r.tags.append(tag)
                ui.notify(f"Max attempts reached — {len(new_issues)} issue(s) remain", type="warning")
                ctx.refresh()

        def run_recheck():
            res = do_recheck()
            with ctx.callback_anchor:
                ui.timer(0, lambda: (on_rechecked(res), False), once=True)
        threading.Thread(target=run_recheck, daemon=True).start()

    def run_fix():
        res = do_fix()
        with ctx.callback_anchor:
            ui.timer(0, lambda: (on_fixed(res), False), once=True)
    threading.Thread(target=run_fix, daemon=True).start()


def qa_all(ctx: ImportContext):
    """Run QA check on all imported questions in background."""
    if not config.ollama_enabled or not config.ollama_model:
        ui.notify("Ollama not configured — check AI & Docs", type="warning")
        return
    if not ctx.imported_questions:
        return

    total = len(ctx.imported_questions)
    ui.notify(f"Running QA on {total} question(s) in background...", type="info")

    qa_items = [(i, entry[0]) for i, entry in enumerate(ctx.imported_questions)]

    def do_qa():
        results = {}
        for n, (i, q) in enumerate(qa_items, 1):
            try:
                issues = qa_check_question(
                    question=q, model=config.ollama_model,
                    base_url=config.ollama_url,
                )
                results[i] = issues or []
            except Exception:
                results[i] = []
            if n % 5 == 0 or n == total:
                def _notify(count=n, tot=total):
                    ui.notify(f"QA progress: {count}/{tot}", type="info")
                with ctx.callback_anchor:
                    ui.timer(0, lambda cb=_notify: (cb(), False), once=True)
        return results

    def on_done(results):
        total_issues = 0
        for i, issues in results.items():
            if i >= len(ctx.imported_questions):
                continue
            q_ref = ctx.imported_questions[i][0]
            q_ref.tags = [t for t in q_ref.tags if not t.startswith("qa:")]
            for issue in issues:
                tag = _qa_issue_tag(issue)
                q_ref.tags.append(tag)
                total_issues += 1
        if total_issues:
            ui.notify(f"QA complete: {total_issues} issue(s) found across {len(results)} questions", type="warning")
        else:
            ui.notify("QA complete: all questions passed", type="positive")
        ctx.refresh()

    def run_qa():
        result = do_qa()
        with ctx.callback_anchor:
            ui.timer(0, lambda: (on_done(result), False), once=True)

    threading.Thread(target=run_qa, daemon=True).start()
