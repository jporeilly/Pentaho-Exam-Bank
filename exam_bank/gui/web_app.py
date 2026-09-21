"""Main NiceGUI web application for the Exam Bank app.

Layout:
- Left sidebar: file management, certifications, topic assignment
- Right main area: Slide preview on top, then tabs below
  (SETTINGS, GENERATE, IMPORT, BANK, AI & DOCS, EXAM, ADMIN)
"""

import asyncio
import shutil
from pathlib import Path

from nicegui import ui, app

from .state import AppState, UIRefs, EVT_FILES_CHANGED
from .styles import CUSTOM_CSS, THEME_APPLY_JS, MERMAID_INIT_JS, STATIC_DIR
from .components.header import build_header
from .components.sidebar import build_sidebar
from .components.slide_panel import build_slide_panel
from .components.generate_tab import build_generate_tab
from .components.generation_handler import setup_generation_handlers
from .components.bank_browser import build_bank_browser
from .components.settings_tab import build_settings
from .components.import_tab import build_import_tab
from .components.docs_search_tab import build_docs_search_tab
from .components.exam_tab import build_exam_tab
from .components.db_admin_tab import build_db_admin_tab
from ..utils.config import config


_connected_clients = {"count": 0}


def create_app():
    """Create and configure the NiceGUI application."""

    # Serve static files for slide image previews
    app.add_static_files("/static", str(STATIC_DIR))

    @ui.page("/")
    def main_page():
        state = AppState()
        refs = UIRefs()

        # Inject CSS and theme JS
        ui.add_head_html(CUSTOM_CSS)
        ui.add_head_html(THEME_APPLY_JS)
        ui.add_head_html(MERMAID_INIT_JS)

        # -- Header (gradient, theme selector, dark mode, exit) --
        build_header()

        # Hidden container for scheduling main-thread callbacks from background threads
        _callback_anchor = ui.column().style("display: none;")

        # Wire up generation handlers (on_generate, on_generate_batch)
        setup_generation_handlers(state, refs, _callback_anchor)

        # -- Two-panel layout (matching pptx_to_video) --
        with ui.row().classes("w-full two-panel").style(
            "flex-wrap: nowrap; margin: 0; padding: 0;"
        ):
            # === LEFT SIDEBAR ===
            with ui.column().classes("sidebar q-pa-md q-gutter-sm"):
                build_sidebar(state, refs)

            # === RIGHT MAIN AREA ===
            with ui.column().classes("main-content q-pa-md q-gutter-sm"):

                # Slide Preview (top, gets most space — hidden on Admin tab)
                slide_panel_wrapper = ui.column().classes("w-full")
                with slide_panel_wrapper:
                    build_slide_panel(state, refs)

                # Tabs below the slide preview
                with ui.column().classes("w-full"):
                    with ui.tabs().classes("w-full") as tabs:
                        settings_tab = ui.tab("Settings", icon="settings")
                        slides_tab = ui.tab("Generate", icon="auto_awesome")
                        import_tab_ref = ui.tab("Import", icon="upload_file")
                        bank_tab = ui.tab("Bank", icon="storage")
                        ai_docs_tab = ui.tab("AI & Docs", icon="smart_toy")
                        exam_tab = ui.tab("Exam", icon="quiz")
                        admin_tab = ui.tab("Admin", icon="admin_panel_settings")
                    refs.tabs = tabs
                    refs.generate_tab = slides_tab

                    # Slide preview only needed for the Generate tab
                    def _on_tab_change(e):
                        val = str(e.value) if e.value is not None else ""
                        slide_panel_wrapper.set_visibility(val == "Generate")

                    tabs.on_value_change(_on_tab_change)

                    with ui.tab_panels(tabs, value=settings_tab).classes("w-full"):

                        with ui.tab_panel(settings_tab):
                            build_settings(state, refs)

                        with ui.tab_panel(slides_tab):
                            build_generate_tab(state, refs)

                        with ui.tab_panel(import_tab_ref):
                            build_import_tab(state, refs)

                        with ui.tab_panel(bank_tab):
                            build_bank_browser(state, refs)

                        with ui.tab_panel(ai_docs_tab):
                            build_docs_search_tab(state, refs)

                        with ui.tab_panel(exam_tab):
                            build_exam_tab(state, refs)

                        with ui.tab_panel(admin_tab):
                            build_db_admin_tab(state, refs)

        # Initial file list refresh
        state.bus.emit(EVT_FILES_CHANGED)

        # ── Global keyboard shortcuts ─────────────────────────
        def _handle_key(e):
            if not e.action.keydown:
                return
            has_ctrl = e.modifiers.ctrl
            has_alt = e.modifiers.alt
            has_shift = e.modifiers.shift
            has_meta = e.modifiers.meta
            any_modifier = has_ctrl or has_alt or has_shift or has_meta

            if has_ctrl and not has_alt and not has_meta:
                if e.key == 'g':
                    if refs.on_generate:
                        refs.on_generate()
                elif e.key == 's':
                    if refs.save_all_questions:
                        refs.save_all_questions()
            elif not any_modifier:
                if e.key == 'ArrowLeft':
                    if refs.nav_slide:
                        refs.nav_slide(-1)
                elif e.key == 'ArrowRight':
                    if refs.nav_slide:
                        refs.nav_slide(1)

        ui.keyboard(on_key=_handle_key)

        # ── Auto-backup timer ─────────────────────────────────
        if config.auto_backup_enabled and config.auto_backup_interval_hours > 0:
            from ..core.db_backup import create_backup, list_backups

            def _auto_backup():
                try:
                    create_backup(label="auto")
                    # Prune old auto-backups beyond max count
                    backups = list_backups()
                    auto_backups = [b for b in backups if "_auto" in b["name"]]
                    while len(auto_backups) > config.auto_backup_max_count:
                        oldest = auto_backups.pop()
                        oldest["path"].unlink(missing_ok=True)
                    print(f"[AUTO-BACKUP] Created automatic backup")
                except Exception as e:
                    print(f"[AUTO-BACKUP] Failed: {e}")

            interval_seconds = config.auto_backup_interval_hours * 3600
            ui.timer(interval_seconds, _auto_backup)


def _find_free_port(start: int = 7777, end: int = 7877) -> int:
    """Find an available port in the given range."""
    import socket
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in range {start}-{end}.")


def cleanup_on_shutdown():
    """Clean up temporary static files when app closes."""
    if STATIC_DIR.exists():
        shutil.rmtree(STATIC_DIR, ignore_errors=True)
    STATIC_DIR.mkdir(exist_ok=True)


def run_app(port: int = 7777):
    """Start the NiceGUI server."""
    import logging
    import sys

    # Suppress harmless ConnectionResetError from stale WebSocket connections
    # (Windows proactor event loop raises these during/after long operations)
    _orig_exception_handler = asyncio.get_event_loop().get_exception_handler()

    def _quiet_exception_handler(loop, context):
        exc = context.get("exception")
        if isinstance(exc, ConnectionResetError):
            return  # silently ignore
        if _orig_exception_handler:
            _orig_exception_handler(loop, context)
        else:
            loop.default_exception_handler(context)

    asyncio.get_event_loop().set_exception_handler(_quiet_exception_handler)

    app.on_shutdown(cleanup_on_shutdown)

    # Track connected clients and auto-exit when the last browser tab closes
    @app.on_connect
    def _on_connect():
        _connected_clients["count"] += 1

    @app.on_disconnect
    def _on_disconnect():
        _connected_clients["count"] -= 1
        if _connected_clients["count"] <= 0:
            async def _delayed_shutdown():
                await asyncio.sleep(2.0)
                if _connected_clients["count"] <= 0:
                    print("[APP] All browser tabs closed — shutting down.")
                    app.shutdown()
                    import os
                    os._exit(0)
            asyncio.get_event_loop().create_task(_delayed_shutdown())

    port = _find_free_port(port)
    if port != 7777:
        print(f"Port 7777 is in use — starting on port {port} instead.")

    # Write actual port to temp file so run.bat can clean up the right port
    import tempfile
    port_file = Path(tempfile.gettempdir()) / "exam_bank_port.txt"
    port_file.write_text(str(port))

    create_app()
    ui.run(
        title="Pentaho Exam Bank",
        port=port,
        reload=False,
        show=True,
    )
