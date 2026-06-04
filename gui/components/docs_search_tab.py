"""AI & Docs tab: Ollama AI + MCP config (top row) and Docs Chat (below, full width)."""

import asyncio

from nicegui import ui

from ..state import AppState, UIRefs
from ...utils.config import config
from ...core import mcp_client
from .ollama_settings import build_ollama_settings
from .mcp_settings import build_mcp_settings
from .docs_chat import build_docs_chat


def build_docs_search_tab(state: AppState, refs: UIRefs):
    """Build the AI & Docs tab — settings side-by-side on top, chat below."""

    # ── Section help ──
    with ui.row().classes("w-full items-start gap-1 q-mb-sm"):
        ui.icon("help_outline", size="xs").classes("text-grey-5 q-mt-xs")
        ui.label(
            "Configure your local AI model (Ollama) and documentation servers (MCP) above, "
            "then use the Docs Chat below to research topics before writing questions."
        ).classes("text-xs text-grey-6")

    # ── Top row: Ollama AI | MCP Servers (side by side) ──
    # Use raw div to avoid .nicegui-row { flex-wrap: wrap !important } from styles.py
    with ui.element("div").classes("w-full").style(
        "display: flex; flex-wrap: nowrap !important; gap: 16px; align-items: stretch;"
    ):
        with ui.column().classes("gap-2").style("flex: 1 1 50%; min-width: 0;"):
            refresh_models = build_ollama_settings(refs)
        with ui.column().classes("gap-2").style("flex: 1 1 50%; min-width: 0;"):
            mcp_status = build_mcp_settings()

    # ── Bottom: Docs Chat (full width) ──
    ui.separator().classes("q-my-sm")
    build_docs_chat(state, refs)

    # Auto-check connections on load
    async def _initial_check():
        await asyncio.sleep(0.5)
        try:
            await refresh_models()
        except Exception:
            pass
        servers = config.mcp_servers
        if servers:
            connected_count = 0
            for srv in servers:
                try:
                    ok = await asyncio.to_thread(mcp_client.check_connection, srv.get("url", ""))
                    if ok:
                        connected_count += 1
                except Exception:
                    pass
            if connected_count > 0:
                mcp_status.set_text(f"{connected_count}/{len(servers)} connected")
                mcp_status.props("color=green-7")
            else:
                mcp_status.set_text(f"0/{len(servers)} connected")
                mcp_status.props("color=red-7")

    ui.timer(0.5, _initial_check, once=True)
