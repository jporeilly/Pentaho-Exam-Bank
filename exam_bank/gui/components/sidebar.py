"""Left sidebar: file loading, certification assignment."""

import shutil
import threading
from pathlib import Path

from nicegui import ui

from ..state import (
    AppState, UIRefs, LoadedFile,
    EVT_CERTIFICATIONS_CHANGED, EVT_FILES_CHANGED,
    EVT_SLIDE_CHANGED, EVT_STATS_CHANGED,
)
from ..styles import PPTX_CACHE_DIR
from ...core.bank import Certification
from ...utils.config import config


def build_sidebar(state: AppState, refs: UIRefs):
    """Build the left sidebar with file management, certifications, and generation settings."""

    # ── Certifications Section ────────────────────────────
    ui.label("Certifications").classes("section-title q-mt-sm")

    # Dropdown with explicit Save button
    with ui.row().classes("w-full gap-1 items-end"):
        def _on_cert_change(e):
            state.active_cert_id = e.value or ""
            # For docs certs, restore saved topic or clear
            if state.active_cert_id:
                cert = state.db.get_certification(state.active_cert_id)
                if cert and cert.source_type == "docs":
                    saved = config.file_certifications.get(f"cert:{state.active_cert_id}:topic", "")
                    topic_input.set_value(saved)
                    state.active_topic = saved
            _update_topic_label()
            # Refresh slide preview to show docs-generation UI if applicable
            state.bus.emit(EVT_SLIDE_CHANGED)

        cert_select = ui.select(
            options={},
            label="Active Certification",
            on_change=_on_cert_change,
        ).classes("flex-grow").props("dense outlined clearable")
        ui.button(icon="save", on_click=lambda: _save_cert()).props(
            "flat round dense size=sm color=positive"
        ).tooltip("Save certification for this file")

    # Add new certification (stays outside refreshable area)
    with ui.row().classes("w-full gap-1 items-end"):
        new_cert_name = ui.input(placeholder="New certification name").classes("flex-grow").props("dense outlined")
        new_cert_type = ui.select(
            {"pptx": "PPTX", "docs": "Docs", "pcm": "PCM"},
            value="pptx", label="Source",
        ).classes("w-24").props("dense outlined")
        ui.button(icon="add", on_click=lambda: _add_cert()).props(
            "flat round dense size=sm color=primary"
        )

    # List of existing certifications (refreshable)
    cert_list_container = ui.column().classes("w-full gap-0")

    def refresh_certifications():
        certs = state.db.list_certifications()
        cert_options = {c.id: f"{c.name} ({state.db.count_by_certification(c.id)} Q)" for c in certs}

        # Update dropdown options without destroying it
        prev = cert_select.value
        cert_select.options = cert_options
        cert_select.update()
        if prev and prev in cert_options:
            cert_select.set_value(prev)

        # Rebuild cert list
        cert_list_container.clear()
        with cert_list_container:
            for c in certs:
                with ui.row().classes("w-full items-center gap-2 px-1 q-py-xs"):
                    ui.label(c.name).classes("text-xs flex-grow truncate")
                    src_label = {"docs": "Docs", "pcm": "PCM"}.get(c.source_type, "PPTX")
                    src_color = {"docs": "teal", "pcm": "purple"}.get(c.source_type, "blue")
                    ui.badge(src_label).props(f"color={src_color}").classes("text-xs").style(
                        "min-width: 42px; text-align: center; display: inline-block;"
                    )
                    cnt = state.db.count_by_certification(c.id)
                    ui.badge(str(cnt)).props("color=primary").classes("text-xs")
                    ui.button(icon="delete", on_click=lambda _, cid=c.id: _delete_cert(cid)).props(
                        "flat round dense size=xs color=negative"
                    )

    def _add_cert():
        name = new_cert_name.value.strip()
        if not name:
            ui.notify("Certification name required", type="warning")
            return
        cert = Certification(name=name, source_type=new_cert_type.value or "pptx")
        state.db.save_certification(cert)
        new_cert_name.value = ""
        refresh_certifications()
        # Auto-select the newly created certification
        cert_select.set_value(cert.id)
        ui.notify(f"Created certification: {name}", type="positive")

    def _delete_cert(cert_id):
        cnt = state.db.count_by_certification(cert_id)
        if cnt > 0:
            ui.notify(f"Cannot delete — {cnt} questions assigned. Reassign first.", type="warning")
            return
        state.db.delete_certification(cert_id)
        if cert_select.value == cert_id:
            cert_select.set_value(None)
        ui.notify("Certification deleted", type="info")
        refresh_certifications()
        refresh_topics()
        refresh_file_list()
        refresh_recent()

    def _save_cert():
        f = state.selected_file
        if not f:
            ui.notify("No file selected", type="warning")
            return
        cert_id = cert_select.value
        f.certification_id = cert_id or ""
        if cert_id:
            config.file_certifications[f.path.name] = cert_id
        else:
            config.file_certifications.pop(f.path.name, None)
        config.save()
        state.bus.emit(EVT_FILES_CHANGED)
        # Show cert name in notification
        cert_name = ""
        if cert_id:
            cert = state.db.get_certification(cert_id)
            cert_name = cert.name if cert else cert_id
        ui.notify(f"Certification saved: {cert_name or '(cleared)'}", type="positive")

    def refresh_sidebar():
        """Full sidebar refresh — certifications, topics, file list, and recent."""
        refresh_certifications()
        refresh_topics()
        refresh_file_list()
        refresh_recent()

    state.bus.on(EVT_CERTIFICATIONS_CHANGED, refresh_sidebar)
    refresh_certifications()

    # ── PCM Course Section ─────────────────────────────────
    # Pick a Pentaho Content Manager course to generate questions from its
    # content. Picking a course find-or-creates a "pcm" certification bound
    # to that course (source_ref = slug) and makes it active.
    from ...core.pcm_reader import list_pcm_courses, list_pcm_labs

    ui.label("PCM Course").classes("section-title q-mt-md")

    def _pcm_options():
        return {c["slug"]: c["title"] for c in list_pcm_courses(config.pcm_courses_dir)}

    def _lab_options(course_slug):
        # "" = whole course; then one entry per lab/module.
        opts = {"": "(Whole course)"}
        for lab in list_pcm_labs(config.pcm_courses_dir, course_slug):
            opts[lab["slug"]] = lab["title"]
        return opts

    def _refresh_labs(course_slug):
        pcm_lab_select.options = _lab_options(course_slug)
        pcm_lab_select.set_value("")
        pcm_lab_select.update()
        state.pcm_lab_slug = ""   # reset scope to whole course on course change

    def _pick_pcm_course(slug):
        if not slug:
            return
        existing = next(
            (c for c in state.db.list_certifications()
             if c.source_type == "pcm" and c.source_ref == slug),
            None,
        )
        if existing:
            cert = existing
        else:
            title = _pcm_options().get(slug, slug)
            cert = Certification(name=title, source_type="pcm", source_ref=slug)
            state.db.save_certification(cert)
            refresh_certifications()
        cert_select.set_value(cert.id)  # make it the active certification
        _refresh_labs(slug)
        ui.notify(f"PCM course selected: {slug}", type="positive")

    def _refresh_pcm():
        pcm_course_select.options = _pcm_options()
        pcm_course_select.update()
        ui.notify("Rescanned PCM courses", type="info")

    with ui.row().classes("w-full gap-1 items-end"):
        pcm_course_select = ui.select(
            options=_pcm_options(),
            label="Generate from course",
            on_change=lambda e: _pick_pcm_course(e.value),
        ).classes("flex-grow").props("dense outlined clearable")
        ui.button(icon="refresh", on_click=lambda: _refresh_pcm()).props(
            "flat round dense size=sm"
        ).tooltip("Rescan the PCM courses directory")

    # Optional: scope generation to one lab/module instead of the whole course.
    pcm_lab_select = ui.select(
        options={"": "(Whole course)"},
        value="",
        label="Lab / module (optional)",
        on_change=lambda e: setattr(state, "pcm_lab_slug", e.value or ""),
    ).classes("w-full").props("dense outlined")

    if not config.pcm_courses_dir:
        ui.label("Set the PCM courses directory in Settings.").classes(
            "text-xs text-grey q-px-xs"
        )

    # ── Topic Assignment ───────────────────────────────────
    def _get_recent_topics():
        """Collect unique topics from config and the exam bank."""
        topics = set()
        for key, val in config.file_certifications.items():
            if key.endswith(":topic") and val:
                topics.add(val)
        # Also pull distinct topics from saved questions
        try:
            rows = state.db.conn.execute(
                "SELECT DISTINCT topic FROM questions WHERE topic IS NOT NULL AND topic != ''"
            ).fetchall()
            for row in rows:
                topics.add(row[0])
        except Exception:
            pass
        return sorted(topics)

    topic_label = ui.label("Topic").classes("text-xs font-semibold q-mt-xs")

    with ui.row().classes("w-full gap-1 items-end"):
        topic_input = ui.select(
            options=_get_recent_topics(),
            label="Search topic / question tag",
            new_value_mode="add",
        ).classes("flex-grow").props("dense outlined clearable").tooltip(
            "For Docs certs: MCP search query. For PPTX: topic tag for generated questions."
        )
        ui.button(icon="save", on_click=lambda: _save_topic()).props(
            "flat round dense size=sm color=positive"
        ).tooltip("Save topic")

    def refresh_topics():
        """Refresh the topic dropdown options from the database."""
        prev = topic_input.value
        topic_input.options = _get_recent_topics()
        topic_input.update()
        if prev and prev in topic_input.options:
            topic_input.set_value(prev)

    def _on_topic_change(e):
        state.active_topic = (e.value or "").strip()
        # Refresh slide preview so docs mode shows updated topic
        state.bus.emit(EVT_SLIDE_CHANGED)

    topic_input.on_value_change(_on_topic_change)

    # ── MCP Server Selector (for docs mode) ─────────────────
    mcp_server_select = ui.select(
        options={},
        label="MCP Servers",
        multiple=True,
    ).classes("w-full").props("dense outlined use-chips")
    mcp_server_select.set_visibility(False)

    def _on_mcp_server_change(e):
        urls = e.value or []
        if isinstance(urls, str):
            urls = [urls]
        state.active_mcp_servers = urls

    mcp_server_select.on_value_change(_on_mcp_server_change)

    def _update_topic_label():
        """Update topic label, placeholder, and MCP server selector based on current cert type."""
        is_docs = False
        if state.active_cert_id:
            cert = state.db.get_certification(state.active_cert_id)
            is_docs = cert and cert.source_type == "docs"
        if is_docs:
            topic_label.set_text("Search Topic (Docs)")
            topic_input.props(remove="label")
            topic_input.props(add='label="Search topic for docs generation"')
            # Show and populate MCP server selector
            server_opts = {s.get("url", ""): s.get("name", s.get("url", "?")) for s in config.mcp_servers}
            mcp_server_select.options = server_opts
            mcp_server_select.update()
            # Default to all servers if none selected
            if not state.active_mcp_servers:
                all_urls = list(server_opts.keys())
                mcp_server_select.set_value(all_urls)
                state.active_mcp_servers = all_urls
            mcp_server_select.set_visibility(True)
        else:
            topic_label.set_text("Topic")
            topic_input.props(remove="label")
            topic_input.props(add='label="Topic tag for generated questions"')
            mcp_server_select.set_visibility(False)

    def _save_topic():
        f = state.selected_file
        topic_val = (topic_input.value or "").strip()
        state.active_topic = topic_val

        # Save per-file if a file is selected
        if f:
            f.topic = topic_val
            if f.topic:
                config.file_certifications[f.path.name + ":topic"] = f.topic
            else:
                config.file_certifications.pop(f.path.name + ":topic", None)
            config.save()
            state.bus.emit(EVT_FILES_CHANGED)

        # Also save per-certification for docs mode (no file needed)
        if state.active_cert_id:
            cert = state.db.get_certification(state.active_cert_id)
            if cert and cert.source_type == "docs":
                key = f"cert:{state.active_cert_id}:topic"
                if topic_val:
                    config.file_certifications[key] = topic_val
                else:
                    config.file_certifications.pop(key, None)
                config.save()

        ui.notify(f"Topic saved: {topic_val or '(cleared)'}", type="positive")

    # ── Files Section ─────────────────────────────────────
    ui.separator().classes("q-my-xs")
    ui.label("Files").classes("section-title")

    def _export_slide_images(lf: LoadedFile):
        """Export slide images in background thread using PowerPoint COM."""
        try:
            from ...core.pptx_exporter import PPTXExporter
            images_dir = PPTX_CACHE_DIR / lf.path.stem
            images_dir.mkdir(parents=True, exist_ok=True)
            exporter = PPTXExporter(lf.path, images_dir)
            for exp in exporter.export_slides_as_images():
                if 0 <= exp.index < len(lf.slide_images):
                    lf.slide_images[exp.index] = exp.image_path
            print(f"[PREVIEW] Exported {lf.slide_count} slide images for {lf.path.name}")
        except Exception as e:
            print(f"[PREVIEW] Could not export slide images (PowerPoint may not be installed): {e}")

    def _load_file(p: Path):
        """Load a file into the app, cache it, and export slide images."""
        if p.suffix.lower() not in (".pptx", ".pdf"):
            ui.notify("Only .pptx and .pdf files are supported", type="warning")
            return

        # Copy to assets/pptx/ cache (like pptx_to_video does)
        if p.suffix.lower() == ".pptx":
            PPTX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cached = PPTX_CACHE_DIR / p.name
            if cached != p:
                shutil.copy(p, cached)
            p = cached

        # Replace if same name already loaded
        existing = [f for f in state.files if f.path.name == p.name]
        if existing:
            state.files[:] = [f for f in state.files if f.path.name != p.name]
            state.preview_cache_bust += 1

        lf = LoadedFile(path=p)
        if lf.load():
            # Restore saved certification, or use active dropdown selection
            saved_cert = config.file_certifications.get(p.name, "")
            if saved_cert and state.db.get_certification(saved_cert):
                lf.certification_id = saved_cert
                cert_select.set_value(saved_cert)
            elif cert_select and cert_select.value:
                lf.certification_id = cert_select.value
                config.file_certifications[p.name] = cert_select.value
                config.save()
            # Restore saved topic
            saved_topic = config.file_certifications.get(p.name + ":topic", "")
            lf.topic = saved_topic
            topic_input.set_value(saved_topic)
            state.files.append(lf)
            state.selected_file_idx = len(state.files) - 1
            # Update recent files: remove any entry with same filename, then add to front
            filename = p.name
            config.recent_files = [r for r in config.recent_files if Path(r).name != filename]
            config.recent_files.insert(0, str(p))
            config.recent_files = config.recent_files[:10]
            config.save()

            # Check if images already exist from previous session
            images_dir = PPTX_CACHE_DIR / lf.path.stem
            _load_existing_images(lf, images_dir)

            state.bus.emit(EVT_FILES_CHANGED)
            state.bus.emit(EVT_SLIDE_CHANGED)
            state.bus.emit(EVT_STATS_CHANGED)
            refresh_recent()
            ui.notify(f"Loaded: {p.name} ({lf.slide_count} slides)")

            # Export slide images in background if not already cached
            if not all(lf.slide_images):
                def _bg_export():
                    _export_slide_images(lf)
                    state.preview_cache_bust += 1

                threading.Thread(target=_bg_export, daemon=True).start()
        else:
            ui.notify(f"Failed to load: {p.name}", type="negative")

    def _load_existing_images(lf: LoadedFile, images_dir: Path):
        """Load already-exported slide images from cache."""
        if not images_dir.exists():
            return
        for idx in range(lf.slide_count):
            img = images_dir / f"slide_{idx + 1:03d}.png"
            if img.exists():
                lf.slide_images[idx] = img

    # File list (above drop area, matching pptx_to_video)
    file_list_container = ui.column().classes("w-full q-gutter-xs")

    def refresh_file_list():
        file_list_container.clear()
        with file_list_container:
            if not state.files:
                ui.label("No files loaded").classes("muted text-xs q-pa-sm")
                return
            for idx, lf in enumerate(state.files):
                is_selected = (idx == state.selected_file_idx)

                # Look up certification name
                cert_name = ""
                if lf.certification_id:
                    cert = state.db.get_certification(lf.certification_id)
                    if cert:
                        cert_name = cert.name

                row_cls = "file-row file-row-selected" if is_selected else "file-row"
                with ui.row().classes(
                    f"w-full items-center gap-2 {row_cls}"
                ) as row:
                    ui.icon("description", size="xs").classes("themed-icon" if not is_selected else "")
                    with ui.column().classes("flex-grow gap-0").style(
                        "overflow: hidden; min-width: 0;"
                    ):
                        ui.label(lf.path.name).classes("text-sm font-medium").style(
                            "overflow: hidden; text-overflow: ellipsis; white-space: nowrap;"
                        )
                        info = f"{lf.slide_count} slides"
                        if cert_name:
                            info += f" | {cert_name}"
                        if lf.topic:
                            info += f" | {lf.topic}"
                        ui.label(info).classes("text-xs muted")
                    ui.space()
                    ui.label(f"{lf.slide_count}").classes("muted text-xs")

                    def on_select(i=idx):
                        state.selected_file_idx = i
                        state.current_slide_idx = 0
                        f = state.files[i]
                        if cert_select and f.certification_id:
                            cert_select.value = f.certification_id
                        topic_input.set_value(f.topic or "")
                        refresh_file_list()
                        state.bus.emit(EVT_SLIDE_CHANGED)

                    row.on("click", on_select)

    state.bus.on(EVT_FILES_CHANGED, refresh_file_list)
    refresh_file_list()

    # Drag & drop upload area
    async def _on_upload(e):
        import tempfile
        name = e.file.name
        tmp = Path(tempfile.gettempdir()) / name
        await e.file.save(tmp)
        _load_file(tmp)

    ui.upload(
        label="Drag & Drop .pptx / .pdf",
        on_upload=_on_upload,
        auto_upload=True,
    ).props('accept=".pptx,.pdf" flat bordered dense').classes("w-full drop-area")

    # Recent files (rebuilt dynamically)
    recent_container = ui.column().classes("w-full gap-0")

    def refresh_recent():
        recent_container.clear()
        # Deduplicate by filename (keep first = most recent), filter non-existent
        seen_names = set()
        deduped = []
        for p in config.recent_files:
            name = Path(p).name
            if name not in seen_names and Path(p).exists():
                seen_names.add(name)
                deduped.append(p)
        # Persist cleaned list if it changed
        if deduped != config.recent_files:
            config.recent_files = deduped
            config.save()
        if not deduped:
            return
        recent_names = {p: Path(p).name for p in deduped}
        with recent_container:
            recent_select = ui.select(
                options=recent_names, label="Recent",
            ).props("dense outlined").classes("w-full")

            def on_recent(e):
                if e.value:
                    _load_file(Path(e.value))
                    recent_select.value = None

            recent_select.on_value_change(on_recent)

    refresh_recent()

    # Add / Remove / Clear buttons (matching pptx_to_video)
    with ui.row().classes("w-full gap-1"):
        def _add_from_path():
            with ui.dialog() as dialog, ui.card().classes("q-pa-lg"):
                ui.label("Add File").classes("text-base font-semibold")
                path_input = ui.input(
                    label="File path",
                    placeholder=r"C:\path\to\presentation.pptx",
                ).classes("w-96").props("outlined dense")

                with ui.row().classes("q-mt-md gap-2 justify-end"):
                    ui.button("Cancel", on_click=dialog.close).props("flat dense")

                    def do_add():
                        path = path_input.value.strip()
                        if not path:
                            return
                        p = Path(path)
                        if not p.exists():
                            ui.notify(f"File not found: {path}", type="negative")
                            return
                        _load_file(p)
                        dialog.close()

                    ui.button("Add", on_click=do_add, icon="add").props("color=primary dense")
            dialog.open()

        ui.button("Add", on_click=_add_from_path, icon="add").props(
            "dense flat color=primary size=sm"
        ).tooltip("Add a file by path")

        def _remove_selected():
            if not state.files:
                return
            idx = state.selected_file_idx
            if 0 <= idx < len(state.files):
                state.files.pop(idx)
                if state.selected_file_idx >= len(state.files):
                    state.selected_file_idx = len(state.files) - 1
                refresh_file_list()
                state.bus.emit(EVT_SLIDE_CHANGED)

        ui.button("Remove", on_click=_remove_selected, icon="delete_outline").props(
            "dense flat color=red size=sm"
        ).tooltip("Remove selected file")

        def _clear_all():
            state.files.clear()
            state.selected_file_idx = -1
            refresh_file_list()
            state.bus.emit(EVT_SLIDE_CHANGED)

        ui.button("Clear", on_click=_clear_all, icon="clear_all").props(
            "dense flat size=sm"
        ).tooltip("Remove all files")


