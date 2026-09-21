"""Save/commit/export logic for imported questions."""


from nicegui import ui

from ...core.bank import Question
from ...core.question_importer import import_from_csv
from ...core.exporter import export_csv
from ...utils.config import config
from ..state import EVT_BANK_CHANGED, EVT_STATS_CHANGED
from .import_context import ImportContext

from ...utils.config import ASSETS_DIR

QUESTIONS_DIR = ASSETS_DIR / "questions"


def auto_export_csv(ctx: ImportContext, saved_questions: list):
    """Export saved questions to assets/questions/{CertName}/{Topic}.csv."""
    if not saved_questions or not config.auto_export_on_save:
        return
    groups: dict[tuple[str, str], list] = {}
    for q in saved_questions:
        cert_name = "Uncategorized"
        if q.certification_id:
            cert = ctx.state.db.get_certification(q.certification_id)
            if cert:
                cert_name = cert.name
        safe_cert = "".join(c if c.isalnum() or c in " -_" else "_" for c in cert_name).strip()
        topic = q.topic or "General"
        safe_topic = "".join(c if c.isalnum() or c in " -_" else "_" for c in topic).strip()
        groups.setdefault((safe_cert, safe_topic), []).append(q)

    exported = []
    for (cert_dir, topic_name), questions in groups.items():
        out_dir = QUESTIONS_DIR / cert_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        csv_path = out_dir / f"{topic_name}.csv"
        existing = []
        if csv_path.exists():
            try:
                existing = import_from_csv(csv_path)
            except Exception:
                pass
        existing_ids = {q.id for q in existing if q.id}
        merged = list(existing)
        for q in questions:
            if q.id not in existing_ids:
                merged.append(q)
        export_csv(merged, csv_path)
        exported.append(f"{cert_dir}/{topic_name}.csv")

    if exported:
        ui.notify(f"CSV exported: {', '.join(exported)}", type="info")


def do_commit(ctx: ImportContext, idx: int):
    """Actually commit question at idx to the bank."""
    q = ctx.imported_questions[idx][0]
    q.tags = [t for t in q.tags
              if not t.startswith("qa:") and t not in ("key-unverified", "key-not-validated")]
    q.created_by = config.sme_name or "Import"
    ctx.state.db.save(q)
    auto_export_csv(ctx, [q])
    ctx.imported_questions.pop(idx)
    ui.notify("Saved to bank", type="positive")
    ctx.refresh()
    ctx.state.bus.emit_many(EVT_BANK_CHANGED, EVT_STATS_CHANGED)


def is_duplicate(ctx: ImportContext, q: Question) -> bool:
    """Check if a question is a duplicate of one already in the bank."""
    similar = ctx.state.db.find_similar_stems_scored(q.stem, threshold=0.95)
    if not similar:
        return False
    for existing, score in similar:
        if score >= 0.98:
            return True
    return False


def save_one(ctx: ImportContext, idx: int, edit_one_fn=None):
    """Save a single imported question to the bank (with validation)."""
    if idx >= len(ctx.imported_questions):
        return
    entry = ctx.imported_questions[idx]
    q, passed_flag, details = entry[0], entry[1], entry[2]

    errors, warnings = q.validate_detailed()
    if errors:
        ui.notify(f"Cannot save — {len(errors)} error(s): {errors[0]}", type="negative")
        return

    if is_duplicate(ctx, q):
        ui.notify("Skipped — duplicate question already in bank", type="warning")
        return

    if q.source_type != "docs":
        if passed_flag is False:
            warnings.insert(0, "PPTX validation failed — key not found in speaker notes")
        elif passed_flag is None:
            warnings.insert(0, "Not validated against PPTX yet")

    if warnings:
        show_save_confirmation(ctx, idx, q, warnings, edit_one_fn)
    else:
        do_commit(ctx, idx)


def show_save_confirmation(ctx: ImportContext, idx: int, q: Question, warnings: list, edit_one_fn=None):
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
            if edit_one_fn:
                ui.button("Edit First", icon="edit", on_click=lambda: (dlg.close(), edit_one_fn(idx))).props(
                    "flat color=primary"
                )

            def confirm_save():
                dlg.close()
                if idx < len(ctx.imported_questions):
                    do_commit(ctx, idx)

            ui.button("Save Anyway", icon="save", on_click=confirm_save).props("color=positive")
    dlg.open()


def save_passed(ctx: ImportContext):
    """Save all validated (passed) questions to the bank."""
    saved = 0
    skipped_dup = 0
    blocked = 0
    saved_qs = []
    to_remove = []
    for i, entry in enumerate(ctx.imported_questions):
        q, passed = entry[0], entry[1]
        if passed is True:
            errors, _ = q.validate_detailed()
            if errors:
                blocked += 1
                continue
            if is_duplicate(ctx, q):
                skipped_dup += 1
                continue
            q.tags = [t for t in q.tags
                      if not t.startswith("qa:") and t not in ("key-unverified", "key-not-validated")]
            q.created_by = config.sme_name or "Import"
            ctx.state.db.save(q)
            saved_qs.append(q)
            to_remove.append(i)
            saved += 1
    for i in reversed(to_remove):
        ctx.imported_questions.pop(i)

    auto_export_csv(ctx, saved_qs)
    msg = f"Saved {saved} passed question(s)"
    if skipped_dup:
        msg += f", skipped {skipped_dup} duplicate(s)"
    if blocked:
        msg += f", {blocked} blocked (validation errors)"
    ui.notify(msg, type="positive")
    ctx.refresh()
    ctx.state.bus.emit_many(EVT_BANK_CHANGED, EVT_STATS_CHANGED)


def save_all(ctx: ImportContext):
    """Save all imported questions to the bank."""
    saved = 0
    skipped_dup = 0
    blocked = 0
    saved_qs = []
    to_keep = []
    for entry in ctx.imported_questions:
        q, p, d = entry[0], entry[1], entry[2]
        errors, _ = q.validate_detailed()
        if errors:
            blocked += 1
            dupe_info = entry[3] if len(entry) > 3 else ""
            to_keep.append((q, p, d, dupe_info))
            continue
        if is_duplicate(ctx, q):
            skipped_dup += 1
            continue
        q.tags = [t for t in q.tags
                  if not t.startswith("qa:") and t not in ("key-unverified", "key-not-validated")]
        q.created_by = config.sme_name or "Import"
        ctx.state.db.save(q)
        saved_qs.append(q)
        saved += 1
    ctx.imported_questions.clear()
    ctx.imported_questions.extend(to_keep)
    auto_export_csv(ctx, saved_qs)
    msg = f"Saved {saved} question(s)"
    if skipped_dup:
        msg += f", skipped {skipped_dup} duplicate(s)"
    if blocked:
        msg += f", {blocked} blocked (validation errors)"
    ui.notify(msg, type="positive")
    ctx.refresh()
    ctx.state.bus.emit_many(EVT_BANK_CHANGED, EVT_STATS_CHANGED)
