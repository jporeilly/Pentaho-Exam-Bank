"""MCP Documentation Servers settings component for the AI & Docs tab."""

import asyncio

from nicegui import ui

from ...utils.config import config
from ...core import mcp_client


def build_mcp_settings():
    """Build MCP server config card. Returns mcp_status badge for external updates."""

    with ui.card().classes("w-full q-pa-md"):
        with ui.row().classes("w-full items-center gap-2"):
            ui.icon("menu_book", size="16px").classes("themed-icon")
            ui.label("MCP Documentation Servers").classes("text-sm font-semibold")
            ui.space()
            _server_count = len(config.mcp_servers)
            _init_text = f"{_server_count} server(s)" if _server_count > 0 else "Not configured"
            _init_color = "blue-7" if _server_count > 0 else "grey-6"
            mcp_status = ui.badge(_init_text, color=_init_color).props("outline").classes("text-xs")

        # ── Help text ──
        with ui.row().classes("w-full items-start gap-1 q-mb-xs"):
            ui.icon("help_outline", size="xs").classes("text-grey-5 q-mt-xs")
            ui.label(
                "MCP (Model Context Protocol) servers provide documentation context for smarter "
                "question generation and validation. Add your GitBook or documentation server URL below."
            ).classes("text-xs text-grey-6")

        # ── Enable toggle ──
        with ui.row().classes("w-full items-center gap-2"):
            mcp_enabled_switch = ui.switch(
                "Use documentation servers for generation and validation",
                value=config.mcp_enabled,
            ).props("dense")

            def _toggle_mcp(e):
                config.mcp_enabled = e.value
                config.save()
            mcp_enabled_switch.on_value_change(_toggle_mcp)

        # ── Server list ──
        mcp_server_list = ui.column().classes("w-full gap-1 q-mt-xs")

        def _refresh_mcp_list():
            mcp_server_list.clear()
            servers = config.mcp_servers
            count = len(servers)
            if count > 0:
                mcp_status.set_text(f"{count} server(s)")
                mcp_status.props("color=blue-7")
            else:
                mcp_status.set_text("Not configured")
                mcp_status.props("color=grey-6")
            with mcp_server_list:
                if not servers:
                    with ui.column().classes("w-full items-center q-pa-sm"):
                        ui.icon("dns", size="md").classes("text-grey-4")
                        ui.label("No documentation servers added yet").classes("text-xs text-grey-5")
                        ui.label(
                            "Add a GitBook MCP endpoint or other documentation server URL below."
                        ).classes("text-xs text-grey-5 text-center")
                    return
                for srv in servers:
                    srv_url = srv.get("url", "")
                    srv_name = srv.get("name", "")
                    with ui.row().classes("w-full items-center gap-2"):
                        ui.icon("link", size="14px").classes("muted")
                        ui.label(srv_name).classes("text-xs font-semibold").style("min-width: 80px;")
                        ui.label(srv_url).classes("text-xs muted flex-grow font-mono").style(
                            "overflow: hidden; text-overflow: ellipsis; white-space: nowrap;"
                        )

                        async def _test_one(url=srv_url, name=srv_name):
                            ui.notify(f"Testing {name}...", type="info", timeout=1500)
                            connected = await asyncio.to_thread(mcp_client.check_connection, url)
                            if connected:
                                ui.notify(f"{name}: Connected", type="positive")
                            else:
                                ui.notify(f"{name}: Could not connect — check URL and server status", type="negative")

                        ui.button(icon="wifi_tethering", on_click=_test_one).props(
                            "dense flat round size=xs"
                        ).tooltip(f"Test connection to {srv_name}")

                        def _remove_one(idx_url=srv_url):
                            config.mcp_servers = [s for s in config.mcp_servers if s.get("url") != idx_url]
                            config.save()
                            _refresh_mcp_list()

                        ui.button(icon="close", on_click=_remove_one).props(
                            "dense flat round size=xs color=red"
                        ).tooltip(f"Remove {srv_name}")

        _refresh_mcp_list()

        # ── Add server ──
        ui.separator().classes("q-my-xs")
        ui.label("Add Server").classes("text-xs font-semibold")
        with ui.row().classes("w-full items-end gap-2").style("flex-wrap: nowrap;"):
            mcp_name_input = ui.input(
                placeholder="Display name (optional)",
            ).props("dense outlined").style("min-width: 180px; flex: 0 0 auto;").tooltip(
                "A friendly name for the server — auto-generated from URL if left blank"
            )
            mcp_url_input = ui.input(
                placeholder="https://docs.example.com/~gitbook/mcp",
            ).props("dense outlined").classes("flex-grow").style("min-width: 200px;").tooltip(
                "The MCP endpoint URL — usually ends in /~gitbook/mcp for GitBook sites"
            )
            mcp_url_input.on("keydown.enter", lambda: _add_mcp_server())

            def _add_mcp_server():
                name = mcp_name_input.value.strip()
                url = mcp_url_input.value.strip()
                if not url:
                    ui.notify("Enter a server URL first", type="warning")
                    return
                if not name:
                    try:
                        from urllib.parse import urlparse
                        name = urlparse(url).hostname or "MCP Server"
                    except Exception:
                        name = "MCP Server"
                # Check for duplicate URL
                existing_urls = [s.get("url", "") for s in config.mcp_servers]
                if url in existing_urls:
                    ui.notify(f"This URL is already configured", type="warning")
                    return
                config.mcp_servers.append({"name": name, "url": url})
                config.save()
                mcp_name_input.set_value("")
                mcp_url_input.set_value("")
                _refresh_mcp_list()
                ui.notify(f"Added {name}", type="positive")

            ui.button("Add", on_click=_add_mcp_server, icon="add").props("dense color=primary size=sm")

    return mcp_status
