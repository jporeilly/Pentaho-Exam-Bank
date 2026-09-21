"""Settings tab: SME identity, reassignment tools, export, quality, and app info."""

import sqlite3
from pathlib import Path

from nicegui import ui

from ...utils.config import AppConfig, config, DB_PATH, BACKUP_DIR
from ..state import EVT_BANK_CHANGED, EVT_STATS_CHANGED, EVT_CERTIFICATIONS_CHANGED


def build_settings(state, refs):
    """Build the settings panel with collapsible sections.

    Generation settings are in the Slides tab.
    Ollama AI and MCP Documentation Servers are configured in the AI & Docs tab.
    """

    # ── helpers ────────────────────────────────────────────
    def _save_field(field: str, value):
        setattr(config, field, value)
        config.save()
        ui.notify("Saved", type="positive", position="bottom-right", timeout=800)

    def _open_folder():
        import subprocess
        folder = Path(config.output_folder)
        folder.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["explorer", str(folder)])

    def _section_help(text: str):
        """Render a section description with a help icon."""
        with ui.row().classes("w-full items-start gap-1 q-mb-sm"):
            ui.icon("help_outline", size="xs").classes("text-grey-5 q-mt-xs")
            ui.label(text).classes("text-xs text-grey-6")

    # ══════════════════════════════════════════════════════
    # ── 1. SME Identity ──────────────────────────────────
    # ══════════════════════════════════════════════════════
    with ui.expansion("SME Identity", icon="badge").classes("w-full").props(
        "default-opened dense header-class=section-title"
    ):
        with ui.card().classes("w-full q-pa-md"):
            _section_help(
                "Set who is currently working. The active SME name is stamped on every "
                "question you create, review, approve, or reject — so other team members "
                "can see who did what."
            )

            # Active SME selector
            sme_select = ui.select(
                options=config.sme_names or [],
                value=config.sme_name if config.sme_name in (config.sme_names or []) else None,
                label="Who is working right now?",
                on_change=lambda e: _set_active_sme(e.value),
            ).classes("w-full").props("dense outlined clearable").tooltip(
                "Select your name — it will appear in the audit trail for every action you take"
            )

            # Add new SME — with Enter key support
            with ui.row().classes("w-full gap-1 items-end q-mt-xs"):
                new_sme_input = ui.input(
                    placeholder="Type a name and press Enter or click +",
                ).classes("flex-grow").props("dense outlined")
                new_sme_input.on("keydown.enter", lambda: _add_sme())
                ui.button(icon="person_add", on_click=lambda: _add_sme()).props(
                    "flat round dense size=sm color=primary"
                ).tooltip("Add a new SME")

            # SME list with edit/remove
            sme_list_container = ui.column().classes("w-full gap-0 q-mt-sm")
            _extra_refresh = {"fn": None}

            def _refresh_sme_list():
                if _extra_refresh["fn"]:
                    _extra_refresh["fn"]()
                sme_list_container.clear()
                with sme_list_container:
                    if not config.sme_names:
                        with ui.column().classes("w-full items-center q-pa-sm"):
                            ui.icon("group_add", size="md").classes("text-grey-4")
                            ui.label("No SMEs yet").classes("text-sm text-grey-5")
                            ui.label(
                                "Add your name above to start tracking who creates and reviews questions."
                            ).classes("text-xs text-grey-5 text-center")
                        return
                    for name in config.sme_names:
                        is_active = (name == config.sme_name)
                        with ui.row().classes(
                            "w-full items-center gap-1 px-2 py-1 rounded"
                            + (" bg-primary/5" if is_active else "")
                        ):
                            if is_active:
                                ui.icon("person", size="xs", color="primary")
                            else:
                                ui.icon("person_outline", size="xs").classes("text-grey-5")
                            ui.label(name).classes(
                                "text-xs flex-grow" + (" font-bold text-primary" if is_active else "")
                            )
                            cnt = state.db.count_by_sme(name) if hasattr(state.db, 'count_by_sme') else 0
                            if cnt:
                                ui.badge(f"{cnt} questions").props("color=primary outline").classes("text-xs")
                            else:
                                ui.label("0 questions").classes("text-xs text-grey-4")
                            ui.button(icon="edit", on_click=lambda _, n=name: _edit_sme(n)).props(
                                "flat round dense size=xs"
                            ).tooltip(f"Rename {name}")
                            ui.button(icon="delete", on_click=lambda _, n=name: _confirm_remove_sme(n)).props(
                                "flat round dense size=xs color=negative"
                            ).tooltip(f"Remove {name}")

            def _set_active_sme(name):
                config.sme_name = name or ""
                config.save()
                _refresh_sme_list()
                if name:
                    ui.notify(f"Active SME: {name}", type="positive", timeout=1200)

            def _add_sme():
                name = new_sme_input.value.strip()
                if not name:
                    ui.notify("Please enter a name first", type="warning")
                    return
                if name in config.sme_names:
                    ui.notify(f"'{name}' is already in the list", type="warning")
                    return
                config.sme_names.append(name)
                config.sme_name = name
                config.save()
                new_sme_input.value = ""
                sme_select.options = config.sme_names
                sme_select.update()
                sme_select.set_value(name)
                _refresh_sme_list()
                ui.notify(f"Welcome, {name}! You are now the active SME.", type="positive")

            def _confirm_remove_sme(name):
                cnt = state.db.count_by_sme(name) if hasattr(state.db, 'count_by_sme') else 0
                with ui.dialog() as dlg, ui.card().classes("q-pa-md").style("min-width:400px"):
                    ui.label("Remove SME").classes("text-base font-semibold")
                    if cnt:
                        with ui.row().classes("items-start gap-2 q-mt-xs"):
                            ui.icon("warning", color="orange", size="sm")
                            ui.label(
                                f"'{name}' has {cnt} question(s) assigned. You can reassign "
                                "them to another SME before removing, or leave them unassigned."
                            ).classes("text-sm")
                        reassign_select = ui.select(
                            options=[n for n in config.sme_names if n != name],
                            label="Reassign questions to...",
                        ).props("dense outlined clearable").classes("w-full q-mt-xs")
                    else:
                        ui.label(f"Remove '{name}' from the SME list?").classes("text-sm q-mt-xs")
                        reassign_select = None

                    with ui.row().classes("gap-2 justify-end q-mt-md"):
                        ui.button("Keep", on_click=dlg.close).props("flat dense")

                        def do_remove():
                            if reassign_select and reassign_select.value:
                                moved = state.db.reassign_sme(name, reassign_select.value)
                                ui.notify(f"Moved {moved} question(s) to {reassign_select.value}", type="info")
                            _remove_sme(name)
                            dlg.close()

                        ui.button("Remove", icon="delete", on_click=do_remove).props(
                            "dense color=negative size=sm"
                        )
                dlg.open()

            def _remove_sme(name):
                config.sme_names = [n for n in config.sme_names if n != name]
                if config.sme_name == name:
                    config.sme_name = config.sme_names[0] if config.sme_names else ""
                config.save()
                sme_select.options = config.sme_names
                sme_select.update()
                sme_select.set_value(config.sme_name or None)
                _refresh_sme_list()
                ui.notify(f"Removed {name}", type="info")

            def _edit_sme(old_name):
                with ui.dialog() as dlg, ui.card().classes("q-pa-md").style("min-width:400px"):
                    ui.label("Rename SME").classes("text-base font-semibold")
                    ui.label(
                        "Changing the name here can also update all existing questions so the "
                        "audit trail stays consistent."
                    ).classes("text-xs text-grey-6 q-mt-xs")
                    rename_input = ui.input(label="New name", value=old_name).classes("w-full q-mt-xs").props("dense outlined")
                    reassign_cb = ui.checkbox(
                        "Update all existing questions to use the new name", value=True
                    ).classes("text-xs q-mt-xs")
                    with ui.row().classes("gap-2 justify-end q-mt-md"):
                        ui.button("Cancel", on_click=dlg.close).props("flat dense")

                        def do_rename():
                            new_name = rename_input.value.strip()
                            if not new_name or new_name == old_name:
                                dlg.close()
                                return
                            if new_name in config.sme_names:
                                ui.notify(f"'{new_name}' already exists", type="warning")
                                return
                            config.sme_names = [new_name if n == old_name else n for n in config.sme_names]
                            if config.sme_name == old_name:
                                config.sme_name = new_name
                            config.save()
                            if reassign_cb.value:
                                count = state.db.reassign_sme(old_name, new_name)
                                ui.notify(
                                    f"Renamed to '{new_name}' and updated {count} question(s)",
                                    type="positive",
                                )
                            else:
                                ui.notify(f"Renamed to '{new_name}'", type="positive")
                            sme_select.options = config.sme_names
                            sme_select.update()
                            sme_select.set_value(config.sme_name or None)
                            _refresh_sme_list()
                            dlg.close()

                        rename_input.on("keydown.enter", lambda: do_rename())
                        ui.button("Save", icon="check", on_click=do_rename).props("dense color=primary size=sm")
                dlg.open()

            _refresh_sme_list()

    # ══════════════════════════════════════════════════════
    # ── 2. Reassignment Tools ─────────────────────────────
    # ══════════════════════════════════════════════════════
    with ui.expansion("Reassignment Tools", icon="swap_horiz").classes("w-full").props(
        "dense header-class=section-title"
    ):
        with ui.card().classes("w-full q-pa-md"):
            _section_help(
                "Move questions in bulk from one SME to another, or between certifications. "
                "Handy when someone leaves the team or when you restructure certification tracks."
            )

            # ── By SME ──
            ui.label("By SME").classes("text-xs font-semibold q-mt-xs")
            with ui.row().classes("w-full gap-2 items-end"):
                from_sme = ui.select(
                    options=config.sme_names or [], label="Move from...",
                ).props("dense outlined").classes("flex-grow")
                ui.icon("arrow_forward", size="xs").classes("text-grey-5 q-mb-sm")
                to_sme = ui.select(
                    options=config.sme_names or [], label="Move to...",
                ).props("dense outlined").classes("flex-grow")
                ui.button("Move", icon="swap_horiz", on_click=lambda: _do_reassign_sme()).props(
                    "dense color=primary size=sm"
                ).tooltip("Move all questions from one SME to another")

            def _refresh_reassign_dropdowns():
                from_sme.options = config.sme_names or []
                from_sme.update()
                to_sme.options = config.sme_names or []
                to_sme.update()

            def _do_reassign_sme():
                f = from_sme.value
                t = to_sme.value
                if not f or not t:
                    ui.notify("Please select both a source and destination SME", type="warning")
                    return
                if f == t:
                    ui.notify("Source and destination must be different", type="warning")
                    return
                count = state.db.reassign_sme(f, t)
                ui.notify(f"Moved {count} question(s) from {f} to {t}", type="positive")
                _refresh_sme_list()
                state.bus.emit_many(EVT_BANK_CHANGED, EVT_STATS_CHANGED)

            # ── By Certification ──
            ui.separator().classes("q-my-sm")
            ui.label("By Certification").classes("text-xs font-semibold")

            certs = state.db.list_certifications()
            cert_options = {c.id: f"{c.name} ({state.db.count_by_certification(c.id)} Q)" for c in certs}

            with ui.row().classes("w-full gap-2 items-end"):
                from_cert = ui.select(
                    options=cert_options, label="Move from...",
                ).props("dense outlined").classes("flex-grow")
                ui.icon("arrow_forward", size="xs").classes("text-grey-5 q-mb-sm")
                to_cert = ui.select(
                    options=cert_options, label="Move to...",
                ).props("dense outlined").classes("flex-grow")
                ui.button("Move", icon="swap_horiz", on_click=lambda: _do_reassign_cert()).props(
                    "dense color=primary size=sm"
                ).tooltip("Move all questions from one certification to another")

            def _refresh_cert_dropdowns():
                updated_certs = state.db.list_certifications()
                opts = {c.id: f"{c.name} ({state.db.count_by_certification(c.id)} Q)" for c in updated_certs}
                from_cert.options = opts
                from_cert.update()
                to_cert.options = opts
                to_cert.update()

            def _do_reassign_cert():
                fc = from_cert.value
                tc = to_cert.value
                if not fc or not tc:
                    ui.notify("Please select both a source and destination certification", type="warning")
                    return
                if fc == tc:
                    ui.notify("Source and destination must be different", type="warning")
                    return
                count = state.db.reassign_certification(fc, tc)
                from_name = from_cert.options.get(fc, fc)
                to_name = to_cert.options.get(tc, tc)
                ui.notify(f"Moved {count} question(s) from {from_name} to {to_name}", type="positive")
                _refresh_cert_dropdowns()
                state.bus.emit_many(EVT_CERTIFICATIONS_CHANGED, EVT_BANK_CHANGED, EVT_STATS_CHANGED)

            _extra_refresh["fn"] = _refresh_reassign_dropdowns

    # ══════════════════════════════════════════════════════
    # ── 3. Questions Export Settings ──────────────────────
    # ══════════════════════════════════════════════════════
    with ui.expansion("Questions Export Settings", icon="file_download").classes("w-full").props(
        "default-opened dense header-class=section-title"
    ):
        with ui.card().classes("w-full q-pa-md"):
            _section_help(
                "Choose where question files are saved when you export from the Bank tab, "
                "and pick your preferred file format. You can also enable automatic CSV "
                "export every time a question is saved to the bank."
            )

            # Output folder with browse button
            ui.label("Output folder").classes("text-xs font-semibold")
            with ui.row().classes("w-full gap-1 items-end"):
                output_input = ui.input(
                    value=config.output_folder,
                    on_change=lambda e: _save_field("output_folder", e.value),
                ).classes("flex-grow").props("dense outlined").tooltip(
                    "All exported question files (CSV, JSON, QTI, Moodle XML, DOCX, Text) "
                    "are saved here"
                )
                ui.button(icon="folder", on_click=lambda: _browse_folder()).props(
                    "flat round dense size=sm"
                ).tooltip("Browse for a folder")
                ui.button(icon="folder_open", on_click=lambda: _open_folder()).props(
                    "flat round dense size=sm"
                ).tooltip("Open this folder in Explorer")

            # PCM courses directory with browse — source for the "PCM Course"
            # generation option (sidebar).
            ui.label("PCM courses directory").classes("text-xs font-semibold q-mt-sm")
            with ui.row().classes("w-full gap-1 items-end"):
                ui.input(
                    value=config.pcm_courses_dir,
                    on_change=lambda e: _save_field("pcm_courses_dir", e.value),
                ).classes("flex-grow").props("dense outlined").tooltip(
                    "Folder of Pentaho Content Manager courses (each subdir a course with "
                    "course.json + lab guide.md). Powers the PCM Course generation source."
                )
                ui.button(icon="folder", on_click=lambda: _browse_pcm_dir()).props(
                    "flat round dense size=sm"
                ).tooltip("Browse for the PCM courses folder")

            # Default format
            ui.label("Default format").classes("text-xs font-semibold q-mt-sm")
            ui.select(
                {"csv": "CSV  —  spreadsheet-friendly",
                 "json": "JSON  —  machine-readable",
                 "qti": "QTI 2.1  —  LMS standard",
                 "moodle": "Moodle XML  —  Moodle import",
                 "text": "Text  —  plain text",
                 "docx": "DOCX  —  Word document"},
                value=config.default_export_format,
                label="When you click Export, use this format by default",
                on_change=lambda e: _save_field("default_export_format", e.value),
            ).props("dense outlined").classes("w-full").tooltip(
                "You can always choose a different format at export time"
            )

            # Auto-export toggle
            ui.separator().classes("q-my-sm")
            with ui.row().classes("w-full items-center gap-2"):
                ui.switch(
                    "Auto-export CSV on save",
                    value=config.auto_export_on_save,
                    on_change=lambda e: _save_field("auto_export_on_save", e.value),
                ).props("dense")
                ui.icon("help_outline", size="xs").classes("text-grey-5 cursor-pointer").tooltip(
                    "When enabled, every question you save to the bank is also written to a "
                    "CSV file at assets/questions/{Certification}/{Topic}.csv — useful for "
                    "keeping a file-based backup alongside the database."
                )

            # Reset
            with ui.row().classes("w-full justify-end q-mt-sm"):
                ui.button("Reset to Defaults", icon="restart_alt", on_click=lambda: _reset_export()).props(
                    "flat dense size=sm color=grey-7"
                ).tooltip("Restore all export settings to their original values")

    def _browse_folder():
        import subprocess
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null; "
                 "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
                 "$d.Description = 'Select Questions Output Folder'; "
                 f"$d.SelectedPath = '{config.output_folder}'; "
                 "if ($d.ShowDialog() -eq 'OK') { $d.SelectedPath }"],
                capture_output=True, text=True, timeout=60
            )
            chosen = result.stdout.strip()
            if chosen:
                _save_field("output_folder", chosen)
                ui.run_javascript("location.reload()")
        except Exception as exc:
            ui.notify(f"Could not open folder picker: {exc}", type="negative")

    def _browse_pcm_dir():
        import subprocess
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null; "
                 "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
                 "$d.Description = 'Select PCM Courses Folder'; "
                 f"$d.SelectedPath = '{config.pcm_courses_dir}'; "
                 "if ($d.ShowDialog() -eq 'OK') { $d.SelectedPath }"],
                capture_output=True, text=True, timeout=60
            )
            chosen = result.stdout.strip()
            if chosen:
                _save_field("pcm_courses_dir", chosen)
                ui.run_javascript("location.reload()")
        except Exception as exc:
            ui.notify(f"Could not open folder picker: {exc}", type="negative")

    def _reset_export():
        defaults = AppConfig.defaults()
        config.output_folder = defaults.output_folder
        config.default_export_format = defaults.default_export_format
        config.auto_export_on_save = defaults.auto_export_on_save
        config.save()
        ui.notify("Export settings restored to defaults", type="info")
        ui.run_javascript("location.reload()")

    # ══════════════════════════════════════════════════════
    # ── 4. Display ────────────────────────────────────────
    # ══════════════════════════════════════════════════════
    with ui.expansion("Display", icon="view_list").classes("w-full").props(
        "dense header-class=section-title"
    ):
        with ui.card().classes("w-full q-pa-md"):
            _section_help(
                "Adjust how many questions appear per page in the Bank and Admin tabs. "
                "Fewer per page loads faster; more per page means less paging."
            )

            ui.select(
                {10: "10  —  fast loading", 25: "25  —  balanced (default)", 50: "50  —  less paging", 100: "100  —  show all"},
                value=config.questions_per_page,
                label="Questions per page",
                on_change=lambda e: _save_field("questions_per_page", int(e.value or 25)),
            ).props("dense outlined").classes("w-full").tooltip(
                "Takes effect the next time you visit the Bank or Admin tab"
            )

            with ui.row().classes("w-full justify-end q-mt-sm"):
                ui.button("Reset to Defaults", icon="restart_alt", on_click=lambda: _reset_display()).props(
                    "flat dense size=sm color=grey-7"
                )

    def _reset_display():
        defaults = AppConfig.defaults()
        config.questions_per_page = defaults.questions_per_page
        config.save()
        ui.notify("Display settings restored to defaults", type="info")
        ui.run_javascript("location.reload()")

    # ══════════════════════════════════════════════════════
    # ── 5. Quality & Detection ────────────────────────────
    # ══════════════════════════════════════════════════════
    with ui.expansion("Quality & Detection", icon="verified").classes("w-full").props(
        "dense header-class=section-title"
    ):
        with ui.card().classes("w-full q-pa-md"):
            _section_help(
                "Control how strictly the app detects duplicate questions and validates "
                "imported questions against source material. Higher percentages are "
                "stricter — raise them to reduce false positives, lower them to catch more."
            )

            # Duplicate threshold
            ui.label("Duplicate detection").classes("text-xs font-semibold")
            with ui.row().classes("w-full items-center gap-2"):
                ui.number(
                    label="Similarity threshold (%)",
                    value=int(config.duplicate_threshold * 100),
                    min=50, max=100, step=5,
                    on_change=lambda e: _save_threshold("duplicate_threshold", e.value, 50, 100, 85),
                ).classes("w-40").props("dense outlined").tooltip(
                    "Two questions are flagged as duplicates when their stems are this similar (default: 85%)"
                )
                ui.label(
                    "85% catches most duplicates with few false alarms"
                ).classes("text-xs text-grey-5")

            # Validation threshold
            ui.label("Import validation").classes("text-xs font-semibold q-mt-sm")
            with ui.row().classes("w-full items-center gap-2"):
                ui.number(
                    label="Word overlap threshold (%)",
                    value=int(config.validation_threshold * 100),
                    min=50, max=100, step=5,
                    on_change=lambda e: _save_threshold("validation_threshold", e.value, 50, 100, 70),
                ).classes("w-40").props("dense outlined").tooltip(
                    "Imported questions must overlap this much with the source speaker notes or docs (default: 70%)"
                )
                ui.label(
                    "70% confirms the answer key appears in the source"
                ).classes("text-xs text-grey-5")

            with ui.row().classes("w-full justify-end q-mt-sm"):
                ui.button("Reset to Defaults", icon="restart_alt", on_click=lambda: _reset_quality()).props(
                    "flat dense size=sm color=grey-7"
                )

    def _save_threshold(field: str, value, min_val: int, max_val: int, fallback: int):
        v = value if value is not None else fallback
        v = max(min_val, min(max_val, int(v)))
        setattr(config, field, v / 100)
        config.save()
        ui.notify("Saved", type="positive", position="bottom-right", timeout=800)

    def _reset_quality():
        defaults = AppConfig.defaults()
        config.duplicate_threshold = defaults.duplicate_threshold
        config.validation_threshold = defaults.validation_threshold
        config.save()
        ui.notify("Quality settings restored to defaults", type="info")
        ui.run_javascript("location.reload()")

    # ══════════════════════════════════════════════════════
    # ── 6. App Info & Maintenance ─────────────────────────
    # ══════════════════════════════════════════════════════
    with ui.expansion("App Info & Maintenance", icon="info").classes("w-full").props(
        "dense header-class=section-title"
    ):
        with ui.card().classes("w-full q-pa-md"):
            _section_help(
                "See where your data lives, how big the database is, and when the last "
                "backup was made. You can also run maintenance to keep the database healthy."
            )

            from ...utils.config import CONFIG_FILE
            db_size = DB_PATH.stat().st_size / 1024 if DB_PATH.exists() else 0
            q_count = state.db.count()
            cert_count = len(state.db.list_certifications())

            # Stats at a glance
            with ui.row().classes("w-full gap-4 q-mb-sm"):
                with ui.column().classes("items-center"):
                    ui.label(f"{q_count}").classes("text-lg font-bold")
                    ui.label("Questions").classes("text-xs text-grey-5")
                with ui.column().classes("items-center"):
                    ui.label(f"{cert_count}").classes("text-lg font-bold")
                    ui.label("Certifications").classes("text-xs text-grey-5")
                with ui.column().classes("items-center"):
                    ui.label(f"{db_size:.0f} KB").classes("text-lg font-bold")
                    ui.label("DB Size").classes("text-xs text-grey-5")

            # Last backup
            from ...core.db_backup import list_backups
            backups = list_backups()
            if backups:
                latest = backups[0]
                with ui.row().classes("w-full items-center gap-1"):
                    ui.icon("backup", size="xs").classes("text-positive")
                    ui.label(
                        f"Last backup: {latest['created']}  ({latest['size_kb']:.0f} KB)"
                    ).classes("text-xs text-grey-6")
            else:
                with ui.row().classes("w-full items-center gap-1"):
                    ui.icon("warning", size="xs").classes("text-orange")
                    ui.label(
                        "No backups yet — go to the Admin tab to create one"
                    ).classes("text-xs text-orange")

            # File paths (collapsible to reduce clutter)
            with ui.expansion("File paths", icon="folder").classes("w-full q-mt-xs").props("dense"):
                with ui.column().classes("gap-1 q-pa-xs"):
                    with ui.row().classes("gap-1 items-center"):
                        ui.label("Database:").classes("text-xs text-grey-5")
                        ui.label(str(DB_PATH)).classes("text-xs text-grey-6 font-mono")
                    with ui.row().classes("gap-1 items-center"):
                        ui.label("Config:").classes("text-xs text-grey-5")
                        ui.label(str(CONFIG_FILE)).classes("text-xs text-grey-6 font-mono")
                    with ui.row().classes("gap-1 items-center"):
                        ui.label("Backups:").classes("text-xs text-grey-5")
                        ui.label(str(BACKUP_DIR)).classes("text-xs text-grey-6 font-mono")

            # Database maintenance
            ui.separator().classes("q-my-sm")
            ui.label("Database Maintenance").classes("text-xs font-semibold")
            ui.label(
                "Run these after deleting many questions, or if the app feels slow."
            ).classes("text-xs text-grey-5 q-mb-xs")
            with ui.row().classes("gap-2"):
                ui.button("Vacuum Database", icon="compress", on_click=lambda: _vacuum_db()).props(
                    "flat dense size=sm"
                ).tooltip("Shrinks the database file by reclaiming unused space")
                ui.button("Check Integrity", icon="health_and_safety", on_click=lambda: _integrity_check()).props(
                    "flat dense size=sm"
                ).tooltip("Verifies the database is not corrupted")

    def _vacuum_db():
        try:
            old_size = DB_PATH.stat().st_size / 1024
            conn = sqlite3.connect(str(DB_PATH))
            conn.execute("VACUUM")
            conn.close()
            new_size = DB_PATH.stat().st_size / 1024
            saved = old_size - new_size
            if saved > 1:
                ui.notify(f"Done — freed {saved:.0f} KB", type="positive")
            else:
                ui.notify("Database is already compact, nothing to reclaim", type="info")
        except Exception as exc:
            ui.notify(f"Vacuum failed: {exc}", type="negative")

    def _integrity_check():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
            conn.close()
            if result == "ok":
                ui.notify("All good — database is healthy", type="positive")
            else:
                ui.notify(f"Problem found: {result}", type="negative")
        except Exception as exc:
            ui.notify(f"Check failed: {exc}", type="negative")

    # ── Footer ────────────────────────────────────────────
    ui.separator().classes("q-my-xs")
    with ui.row().classes("w-full items-center gap-1"):
        ui.icon("lightbulb", size="xs").classes("text-grey-5")
        ui.label(
            "AI model and documentation server settings are in the AI & Docs tab."
        ).classes("text-xs text-grey-5")
