"""Docs Chat component — Ollama-powered chat with MCP documentation context.

Supports Mermaid diagram rendering in AI responses when the toggle is enabled.
"""

import asyncio
import re
import threading

from nicegui import ui

from ..state import AppState, UIRefs
from ...utils.config import config
from ...core import ollama_client
from ...core import mcp_client

# Regex to find ```mermaid ... ``` blocks in AI responses
_MERMAID_BLOCK_RE = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)

def _clean_citations(text: str) -> str:
    """Clean up raw MCP citation artifacts from AI responses."""
    import re
    # Remove [Object object] artifacts
    text = re.sub(r'\[Object\s+object\]', '', text)
    # Clean markdown links to just show the title: [Title](url) → Title
    text = re.sub(r'\[([^\]]+)\]\(https?://[^\)]+\)', r'\1', text)
    # Remove bare URLs
    text = re.sub(r'https?://\S+', '', text)
    return text.strip()


_MERMAID_INSTRUCTION = (
    "\n\nWhen explaining processes, workflows, architectures, or relationships, "
    "include a Mermaid diagram in your response using a ```mermaid code fence. "
    "Use flowchart (graph TD), sequence, state, or mindmap syntax as appropriate. "
    "Keep diagrams concise and readable."
)


def _render_rich_content(text: str):
    """Render text with inline Mermaid diagrams.

    Splits the response into text segments and ```mermaid blocks,
    rendering each appropriately. Mermaid diagrams are shown in
    styled containers with copy and view-source options.
    """
    parts = _MERMAID_BLOCK_RE.split(text)
    diagram_num = 0
    for i, part in enumerate(parts):
        if not part.strip():
            continue
        if i % 2 == 1:
            diagram_num += 1
            mermaid_src = part.strip()
            with ui.expansion(
                f"Diagram {diagram_num}", icon="account_tree"
            ).classes("w-full q-my-xs").props("default-opened dense"):
                # Styled container — bigger, themed background
                with ui.element("div").classes("mermaid-container"):
                    try:
                        ui.mermaid(mermaid_src).classes("w-full")
                    except Exception:
                        ui.code(mermaid_src, language="mermaid").classes("text-xs")
                # Actions: copy + view source
                with ui.row().classes("w-full items-center gap-2 q-mt-xs"):
                    ui.button(
                        "Copy source", icon="content_copy",
                        on_click=lambda _, src=mermaid_src: _copy_mermaid(src),
                    ).props("flat dense size=xs").tooltip("Copy Mermaid source to clipboard")
                    ui.button(
                        "Open in Mermaid Live", icon="open_in_new",
                        on_click=lambda _, src=mermaid_src: _open_mermaid_live(src),
                    ).props("flat dense size=xs").tooltip("Edit in Mermaid Live Editor (external)")
                with ui.expansion("View source", icon="code").classes("w-full").props("dense"):
                    ui.code(mermaid_src, language="mermaid").classes("text-xs")
        else:
            ui.label(part.strip()).classes("text-xs").style("white-space: pre-wrap;")


def _copy_mermaid(src: str):
    """Copy Mermaid source code to clipboard."""
    ui.run_javascript(f"navigator.clipboard.writeText({repr(src)})")
    ui.notify("Mermaid source copied to clipboard", type="positive", timeout=1500)


def _open_mermaid_live(src: str):
    """Open the Mermaid Live Editor with the diagram source pre-loaded."""
    import base64
    import json
    payload = json.dumps({"code": src, "mermaid": {"theme": "default"}, "autoSync": True})
    encoded = base64.urlsafe_b64encode(payload.encode()).decode()
    url = f"https://mermaid.live/edit#pako:{encoded}"
    ui.run_javascript(f"window.open({repr(url)}, '_blank')")


def build_docs_chat(state: AppState, refs: UIRefs):
    """Build an Ollama-powered docs chat panel.

    Queries MCP documentation servers for context, then sends the question
    + doc context to Ollama. Supports selecting which MCP server to query.
    When Mermaid is enabled, the AI is instructed to include diagrams.
    """

    chat_history = {"messages": []}
    mcp_source = {"server": "all"}

    with ui.card().classes("w-full q-pa-md").style("display: flex; flex-direction: column;"):
        with ui.row().classes("w-full items-center gap-2"):
            ui.icon("auto_stories", size="16px").classes("themed-icon")
            ui.label("Docs Chat").classes("text-sm font-semibold")
            ui.space()
            chat_status = ui.label("").classes("muted text-xs")

        # ── Help text ──
        with ui.row().classes("w-full items-start gap-1 q-mb-xs"):
            ui.icon("help_outline", size="xs").classes("text-grey-5 q-mt-xs")
            ui.label(
                "Ask questions about your documentation. The AI searches MCP servers for "
                "relevant content, then answers using that context. Enable Mermaid to get "
                "visual diagrams in responses."
            ).classes("text-xs text-grey-6")

        # ── Controls row: server selector + mermaid toggle ──
        with ui.row().classes("w-full items-center gap-4"):
            # Server selector
            with ui.row().classes("items-center gap-2"):
                ui.label("Search in:").classes("text-xs text-grey-6")
                servers = config.mcp_servers
                server_options = {"all": "All servers"}
                for s in servers:
                    server_options[s.get("url", "")] = s.get("name", s.get("url", ""))

                server_select = ui.select(
                    server_options, value="all",
                ).props("dense outlined").classes("w-48").tooltip(
                    "Choose which documentation server to search, or search all"
                )


                def _on_server_change(e):
                    mcp_source["server"] = e.value
                    _render_messages()  # Update empty state to reflect selection
                server_select.on_value_change(_on_server_change)

            # Mermaid toggle
            with ui.row().classes("items-center gap-1"):
                ui.switch(
                    "Mermaid diagrams",
                    value=config.mermaid_enabled,
                    on_change=lambda e: _toggle_mermaid(e.value),
                ).props("dense").tooltip(
                    "When enabled, the AI will include visual Mermaid diagrams "
                    "(flowcharts, sequence diagrams, mind maps) in its responses"
                )
                ui.icon("account_tree", size="xs").classes("text-grey-5")

        def _toggle_mermaid(val):
            config.mermaid_enabled = val
            config.save()
            _render_messages()

        # ── Chat messages area ──
        chat_container = ui.column().classes("w-full gap-1 docs-chat-scroll").style(
            "flex: 1; overflow-y: auto; padding: 4px; min-height: 200px; max-height: 500px;"
        )

        def _render_messages():
            chat_container.clear()
            with chat_container:
                if not chat_history["messages"]:
                    with ui.column().classes("w-full items-center q-pa-md gap-1"):
                        ui.icon("chat", size="36px").classes("text-grey-4")
                        ui.label("Start a conversation").classes("text-sm text-grey-5")
                        if servers:
                            selected = mcp_source.get("server", "all")
                            if selected == "all":
                                names = ", ".join(s.get("name", "?") for s in servers)
                                ui.label(f"Searching all servers: {names}").classes("text-xs text-teal")
                            else:
                                name = server_options.get(selected, selected)
                                with ui.row().classes("items-center gap-1"):
                                    ui.icon("dns", size="xs").classes("text-blue")
                                    ui.label(f"Searching: {name} only").classes("text-xs text-blue font-medium")
                        else:
                            ui.label(
                                "No MCP servers configured — add one in the settings above"
                            ).classes("text-xs text-orange")
                        ui.label(
                            "Type a question below. The AI will search your documentation for "
                            "relevant context before answering."
                        ).classes("text-xs text-grey-5 text-center")
                        if config.mermaid_enabled:
                            with ui.row().classes("items-center gap-1"):
                                ui.icon("account_tree", size="xs").classes("text-purple")
                                ui.label("Mermaid diagrams enabled — responses may include visual diagrams").classes("text-xs text-purple")
                else:
                    msgs = chat_history["messages"]
                    for idx, msg in enumerate(msgs):
                        is_user = msg["role"] == "user"
                        display_text = msg.get("display", msg["content"])
                        has_mermaid = not is_user and _MERMAID_BLOCK_RE.search(display_text)
                        with ui.row().classes(
                            "w-full " + ("justify-end" if is_user else "justify-start")
                        ):
                            with ui.card().classes(
                                "q-pa-sm " + ("chat-bubble-user" if is_user else "chat-bubble-assistant")
                            ).style("max-width: 90%;"):
                                if has_mermaid:
                                    _render_rich_content(display_text)
                                else:
                                    ui.label(display_text).classes("text-xs").style(
                                        "white-space: pre-wrap;"
                                    )
                                # Context indicator for user messages
                                if is_user and msg.get("context_found"):
                                    src_count = len(msg.get("sources", []))
                                    with ui.row().classes("items-center gap-1 q-mt-xs"):
                                        ui.icon("menu_book", size="xs").classes("text-teal")
                                        ui.label(f"{src_count} source(s) found").classes("text-xs text-teal")

                                # Source cards below AI response
                                if not is_user and msg.get("content") and idx > 0:
                                    prev = msgs[idx - 1]
                                    src_list = prev.get("sources", []) if prev.get("role") == "user" else []
                                    if src_list:
                                        with ui.expansion(
                                            f"Sources ({len(src_list)})", icon="source"
                                        ).classes("w-full q-mt-xs").props("dense"):
                                            for i, src in enumerate(src_list, 1):
                                                with ui.row().classes("w-full items-start gap-2 q-py-xs").style(
                                                    "border-bottom: 1px solid rgba(128,128,128,0.1);"
                                                ):
                                                    ui.badge(f"{i}", color="primary").classes("text-xs")
                                                    with ui.column().classes("gap-0 flex-grow"):
                                                        ui.label(src["title"]).classes("text-xs font-medium")
                                                        ui.label(src["server"]).classes("text-xs text-grey-5")
                                                        if src.get("link"):
                                                            ui.link(
                                                                src["link"], src["link"], new_tab=True
                                                            ).classes("text-xs")

        _render_messages()

        # ── Input row ──
        with ui.row().classes("w-full gap-1 items-end").style("flex-wrap: nowrap;"):
            chat_input = ui.textarea(
                placeholder="Ask about documentation... (Enter to send)",
            ).props("dense outlined autogrow rows=1").classes("flex-grow")

            async def _send_message():
                if not config.ollama_enabled:
                    ui.notify("Enable Ollama AI in the settings above first", type="warning")
                    return
                model = config.ollama_model
                if not model:
                    ui.notify("Select an Ollama model in the settings above first", type="warning")
                    return

                user_text = chat_input.value.strip()
                if not user_text:
                    return

                # Determine which servers to query
                selected = mcp_source["server"]
                if selected == "all":
                    query_servers = config.mcp_servers
                else:
                    query_servers = [s for s in config.mcp_servers if s.get("url") == selected]

                # Search MCP docs for context
                chat_status.set_text("Searching docs...")
                full_prompt = user_text
                context_found = False
                sources = []

                if query_servers and config.mcp_enabled:
                    try:
                        sources = await asyncio.to_thread(
                            mcp_client.search_multiple_servers_structured,
                            query=user_text[:200],
                            servers=query_servers,
                        )
                        if sources:
                            context_parts = ["--- Documentation Sources ---"]
                            for i, src in enumerate(sources, 1):
                                context_parts.append(
                                    f"[Source {i}] {src['title']} ({src['server']})\n{src['content']}"
                                )
                            context_parts.append("--- End Sources ---")
                            full_prompt = "\n\n".join(context_parts)
                            full_prompt += f"\n\nUser question: {user_text}"
                            full_prompt += (
                                "\n\nAnswer using the documentation sources above. "
                                "Cite sources by number in square brackets, e.g. [Source 1]. "
                                "Do NOT include URLs, markdown links, or [Object] references. "
                                "If the sources don't cover the topic, say so."
                            )
                            context_found = True
                    except Exception:
                        pass

                # Include current slide context if available
                f = state.selected_file
                if f and f.reader:
                    slide = state.current_slide
                    if slide and slide.speaker_notes:
                        full_prompt += f"\n\nCurrent slide speaker notes for reference:\n{slide.speaker_notes}"

                # Mermaid instruction
                if config.mermaid_enabled:
                    full_prompt += _MERMAID_INSTRUCTION

                chat_history["messages"].append({
                    "role": "user",
                    "content": full_prompt,
                    "display": user_text,
                    "context_found": context_found,
                    "sources": sources,
                })
                chat_input.set_value("")
                _render_messages()
                ui.run_javascript(
                    "document.querySelector('.docs-chat-scroll')?.scrollTo(0, 99999)"
                )

                chat_status.set_text(f"Streaming... ({model})")

                system = config.system_prompt or (
                    "You are a documentation expert. Answer questions accurately based on "
                    "the documentation context provided. If the documentation doesn't cover the "
                    "topic, say so clearly."
                )
                if config.mermaid_enabled:
                    system += (
                        " When helpful, include Mermaid diagrams using ```mermaid code fences "
                        "to visualize processes, workflows, or relationships."
                    )
                url = config.ollama_url or ollama_client.DEFAULT_URL

                # Add placeholder assistant message
                chat_history["messages"].append({"role": "assistant", "content": ""})
                _render_messages()

                # Stream in background thread
                stream_buffer = {"text": "", "done": False}

                def _run_stream():
                    try:
                        for chunk in ollama_client.chat_stream(
                            messages=[
                                {"role": m["role"], "content": m["content"]}
                                for m in chat_history["messages"][:-1]
                            ],
                            model=model, system=system, base_url=url,
                        ):
                            stream_buffer["text"] += chunk
                    except Exception as exc:
                        stream_buffer["text"] = f"Could not get a response: {exc}"
                    stream_buffer["done"] = True

                threading.Thread(target=_run_stream, daemon=True).start()

                def _poll_stream():
                    chat_history["messages"][-1]["content"] = stream_buffer["text"] or "(waiting for response...)"
                    _render_messages()
                    ui.run_javascript(
                        "document.querySelector('.docs-chat-scroll')?.scrollTo(0, 99999)"
                    )
                    if stream_buffer["done"]:
                        stream_timer.deactivate()
                        if not stream_buffer["text"]:
                            chat_history["messages"][-1]["content"] = "(No response from model — try a different question or check Ollama)"
                        else:
                            # Clean up citation artifacts from MCP context
                            chat_history["messages"][-1]["content"] = _clean_citations(stream_buffer["text"])
                        _render_messages()
                        chat_status.set_text(model)

                stream_timer = ui.timer(0.3, _poll_stream)

            ui.button(icon="send", on_click=_send_message).props(
                "dense round color=primary size=sm"
            ).tooltip("Send message (Enter)")

            chat_input.on("keydown.enter.prevent", lambda _: _send_message())

        # ── Action buttons ──
        with ui.row().classes("w-full gap-2 q-mt-xs"):
            def _clear_chat():
                if not chat_history["messages"]:
                    return
                with ui.dialog() as dlg, ui.card().classes("q-pa-md").style("min-width: 350px"):
                    ui.label("Clear Chat").classes("text-base font-semibold")
                    ui.label(
                        f"Remove all {len(chat_history['messages'])} messages from this conversation?"
                    ).classes("text-sm q-mt-xs")
                    with ui.row().classes("gap-2 justify-end q-mt-md"):
                        ui.button("Keep", on_click=dlg.close).props("flat dense")
                        def do_clear():
                            dlg.close()
                            chat_history["messages"].clear()
                            chat_status.set_text("")
                            _render_messages()
                        ui.button("Clear", icon="delete_sweep", on_click=do_clear).props("dense color=negative")
                dlg.open()

            ui.button("Clear Chat", on_click=_clear_chat, icon="delete_sweep").props(
                "dense flat size=sm"
            ).tooltip("Clear conversation history")
