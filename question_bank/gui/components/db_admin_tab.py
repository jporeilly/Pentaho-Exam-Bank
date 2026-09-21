"""Database Administration tab — view, edit, truncate, and manage questions & certifications."""

import json
import string
from pathlib import Path
from typing import Optional

from nicegui import ui

from ..state import AppState, UIRefs, EVT_BANK_CHANGED, EVT_CERTIFICATIONS_CHANGED, EVT_ADMIN_CHANGED
from ...core.question_bank import (
    Question, Certification, BLOOM_LEVELS, DIFFICULTIES, STATUSES, STATUS_LABELS,
)
from ...utils.config import config
from .dashboard import build_dashboard


def build_db_admin_tab(state: AppState, refs: UIRefs):
    """Build the database admin panel."""

    def _section_help(text: str):
        with ui.row().classes("w-full items-start gap-1 q-mb-sm"):
            ui.icon("help_outline", size="xs").classes("text-grey-5 q-mt-xs")
            ui.label(text).classes("text-xs text-grey-6")

    # ── View toggle: Dashboard / Database / Docs ──────────
    with ui.row().classes("items-center gap-2"):
        view_toggle = ui.toggle(
            {"dashboard": "Dashboard", "database": "Database", "docs": "Documentation"},
            value="dashboard",
        ).props("dense size=sm no-caps")

        # Colour indicator for active view
        view_indicator = ui.icon("dashboard", color="green", size="sm")

        def _update_view_indicator(val):
            icons = {"dashboard": ("dashboard", "green"), "database": ("storage", "blue"), "docs": ("menu_book", "purple")}
            icon_name, color = icons.get(val, ("dashboard", "green"))
            view_indicator._props["name"] = icon_name
            view_indicator._props["color"] = color
            view_indicator.update()

    dashboard_section = ui.column().classes("w-full gap-2")
    database_section = ui.column().classes("w-full gap-2")
    docs_section = ui.column().classes("w-full gap-2")

    # Build dashboard
    with dashboard_section:
        refresh_dashboard = build_dashboard(state, refs)

    def _on_view_toggle(e):
        val = e.value or "dashboard"
        dashboard_section.set_visibility(val == "dashboard")
        database_section.set_visibility(val == "database")
        docs_section.set_visibility(val == "docs")
        _update_view_indicator(val)

    view_toggle.on_value_change(_on_view_toggle)
    database_section.set_visibility(False)
    docs_section.set_visibility(False)

    # ── Documentation section ──────────────────────────────
    with docs_section:
        _build_docs_section()

    # ── Database management section ────────────────────────
    with database_section:
        _build_database_section(state, refs, _section_help)


def _build_docs_section():
    """Build the documentation viewer section with search and AI Q&A."""
    import threading
    from ...core import ollama_client

    from ...utils.config import PROJECT_ROOT

    guide_path = PROJECT_ROOT / "HOW_TO_GUIDE.md"
    readme_path = PROJECT_ROOT / "README.md"

    # Load content once
    guide_content = ""
    readme_content = ""
    if guide_path.exists():
        try:
            guide_content = guide_path.read_text(encoding="utf-8")
        except Exception:
            pass
    if readme_path.exists():
        try:
            readme_content = readme_path.read_text(encoding="utf-8")
        except Exception:
            pass

    all_doc_content = f"# HOW-TO GUIDE\n\n{guide_content}\n\n# README\n\n{readme_content}"

    # ══════════════════════════════════════════════════════
    # ── Ask AI about Docs ─────────────────────────────────
    # ══════════════════════════════════════════════════════
    with ui.expansion("Ask AI about this app", icon="auto_awesome").classes("w-full").props(
        "default-opened dense header-class=section-title"
    ):
        with ui.card().classes("w-full q-pa-md"):
            with ui.row().classes("w-full items-start gap-1 q-mb-sm"):
                ui.icon("help_outline", size="xs").classes("text-grey-5 q-mt-xs")
                ui.label(
                    "Ask questions about how to use the app. The AI reads the documentation "
                    "and answers based on what it finds. Requires Ollama to be enabled."
                ).classes("text-xs text-grey-6")

            ai_chat_history = {"messages": []}
            _ai_callback = ui.column().style("display: none;")

            # Chat messages
            ai_chat_container = ui.column().classes("w-full gap-1").style(
                "overflow-y: auto; padding: 4px; min-height: 100px; max-height: 350px;"
            )

            def _render_ai_chat():
                ai_chat_container.clear()
                with ai_chat_container:
                    if not ai_chat_history["messages"]:
                        with ui.column().classes("w-full items-center q-pa-sm gap-1"):
                            ui.icon("smart_toy", size="md").classes("text-grey-4")
                            ui.label("Ask anything about the app").classes("text-xs text-grey-5")
                            ui.label(
                                'Try: "How do I import questions?" or "What export formats are available?"'
                            ).classes("text-xs text-grey-5 text-center")
                    else:
                        for msg in ai_chat_history["messages"]:
                            is_user = msg["role"] == "user"
                            with ui.row().classes(
                                "w-full " + ("justify-end" if is_user else "justify-start")
                            ):
                                with ui.card().classes(
                                    "q-pa-sm " + ("chat-bubble-user" if is_user else "chat-bubble-assistant")
                                ).style("max-width: 90%;"):
                                    ui.label(msg.get("display", msg["content"])).classes("text-xs").style(
                                        "white-space: pre-wrap;"
                                    )

            _render_ai_chat()

            # Input
            with ui.row().classes("w-full gap-1 items-end").style("flex-wrap: nowrap;"):
                ai_input = ui.textarea(
                    placeholder="Ask about the app... (Enter to send)",
                ).props("dense outlined autogrow rows=1").classes("flex-grow")

                async def _ask_ai():
                    if not config.ollama_enabled or not config.ollama_model:
                        ui.notify("Enable Ollama and select a model in the AI & Docs tab", type="warning")
                        return
                    user_text = ai_input.value.strip()
                    if not user_text:
                        return

                    # Find relevant sections from docs
                    context_sections = _find_relevant_sections(user_text, guide_content, readme_content)

                    full_prompt = ""
                    if context_sections:
                        full_prompt = "--- Application Documentation ---\n"
                        full_prompt += "\n\n".join(context_sections[:8])
                        full_prompt += "\n--- End Documentation ---\n\n"
                    full_prompt += f"User question: {user_text}"
                    full_prompt += (
                        "\n\nAnswer the question using the documentation above. "
                        "Be concise and specific. If the documentation doesn't cover this topic, say so."
                    )

                    ai_chat_history["messages"].append({
                        "role": "user",
                        "content": full_prompt,
                        "display": user_text,
                    })
                    ai_input.set_value("")
                    _render_ai_chat()

                    # Add placeholder
                    ai_chat_history["messages"].append({"role": "assistant", "content": ""})
                    _render_ai_chat()

                    model = config.ollama_model
                    url = config.ollama_url or ollama_client.DEFAULT_URL
                    system = (
                        "You are a helpful assistant that answers questions about the Question Bank Generator app. "
                        "Base your answers on the documentation provided. Be concise and practical."
                    )

                    stream_buf = {"text": "", "done": False}

                    def _run():
                        try:
                            for chunk in ollama_client.chat_stream(
                                messages=[
                                    {"role": m["role"], "content": m["content"]}
                                    for m in ai_chat_history["messages"][:-1]
                                ],
                                model=model, system=system, base_url=url,
                            ):
                                stream_buf["text"] += chunk
                        except Exception as exc:
                            stream_buf["text"] = f"Could not get a response: {exc}"
                        stream_buf["done"] = True

                    threading.Thread(target=_run, daemon=True).start()

                    def _poll():
                        ai_chat_history["messages"][-1]["content"] = stream_buf["text"] or "(thinking...)"
                        _render_ai_chat()
                        if stream_buf["done"]:
                            poll_timer.deactivate()
                            if not stream_buf["text"]:
                                ai_chat_history["messages"][-1]["content"] = "(No response — check Ollama)"
                            _render_ai_chat()

                    poll_timer = ui.timer(0.3, _poll)

                ui.button(icon="send", on_click=_ask_ai).props(
                    "dense round color=primary size=sm"
                ).tooltip("Ask AI (Enter)")
                ai_input.on("keydown.enter.prevent", lambda _: _ask_ai())

            # Clear
            with ui.row().classes("w-full gap-2 q-mt-xs"):
                def _clear_ai():
                    ai_chat_history["messages"].clear()
                    _render_ai_chat()
                ui.button("Clear", on_click=_clear_ai, icon="delete_sweep").props("dense flat size=xs")

    # ══════════════════════════════════════════════════════
    # ── Text Search ───────────────────────────────────────
    # ══════════════════════════════════════════════════════
    with ui.expansion("Search Documentation", icon="search").classes("w-full").props(
        "dense header-class=section-title"
    ):
        with ui.card().classes("w-full q-pa-md"):
            with ui.row().classes("w-full items-start gap-1 q-mb-sm"):
                ui.icon("help_outline", size="xs").classes("text-grey-5 q-mt-xs")
                ui.label(
                    "Search for specific keywords across both guides. "
                    "Results show matching lines with context."
                ).classes("text-xs text-grey-6")

            doc_search = ui.input(
                placeholder="Search documentation...",
            ).classes("w-full q-mb-sm").props("dense outlined clearable")
            doc_search.on("keydown.enter", lambda: _filter_docs())

            search_results_container = ui.column().classes("w-full gap-1")

            def _filter_docs():
                query = (doc_search.value or "").strip().lower()
                search_results_container.clear()

                if not query:
                    return

                results = []
                for doc_name, content in [("How-To Guide", guide_content), ("README", readme_content)]:
                    if not content:
                        continue
                    lines = content.splitlines()
                    for i, line in enumerate(lines):
                        if query in line.lower():
                            start = max(0, i - 1)
                            end = min(len(lines), i + 2)
                            context = "\n".join(lines[start:end])
                            results.append((doc_name, i + 1, context))

                with search_results_container:
                    if not results:
                        ui.label(f'No results for "{doc_search.value}"').classes("text-xs text-grey-5")
                        return

                    ui.label(f'{len(results)} result(s) for "{doc_search.value}"').classes("text-xs text-grey-6 q-mb-xs")
                    for doc_name, line_num, context in results[:30]:
                        with ui.card().classes("w-full q-pa-xs").style("border-left: 3px solid var(--theme-primary, #475569);"):
                            with ui.row().classes("items-center gap-1"):
                                ui.badge(doc_name, color="primary").props("outline").classes("text-xs")
                                ui.label(f"line {line_num}").classes("text-xs text-grey-5")
                            ui.markdown(context).classes("text-xs")

            doc_search.on("update:model-value", lambda e: _filter_docs())

    # ══════════════════════════════════════════════════════
    # ── Browse Full Docs ──────────────────────────────────
    # ══════════════════════════════════════════════════════
    with ui.expansion("Browse Full Documentation", icon="menu_book").classes("w-full").props(
        "dense header-class=section-title"
    ):
        if guide_content:
            with ui.expansion("How-To Guide", icon="auto_stories").classes("w-full").props(
                "default-opened dense"
            ):
                with ui.scroll_area().classes("w-full").style("max-height: 600px;"):
                    ui.markdown(guide_content).classes("text-sm")
        else:
            ui.label("HOW_TO_GUIDE.md not found.").classes("text-xs text-grey-5")

        if readme_content:
            with ui.expansion("README", icon="description").classes("w-full").props("dense"):
                with ui.scroll_area().classes("w-full").style("max-height: 500px;"):
                    ui.markdown(readme_content).classes("text-sm")


def _find_relevant_sections(query: str, guide: str, readme: str, max_sections: int = 8) -> list:
    """Find documentation sections relevant to a query using keyword matching.

    Splits docs into sections (by ## headings), scores each by keyword overlap,
    and returns the top matches.
    """
    import re

    query_words = set(query.lower().split())
    if not query_words:
        return []

    sections = []
    for doc_name, content in [("How-To Guide", guide), ("README", readme)]:
        if not content:
            continue
        # Split by ## headings
        parts = re.split(r'^(#{1,3}\s+.+)$', content, flags=re.MULTILINE)
        current_heading = doc_name
        current_text = ""
        for part in parts:
            if re.match(r'^#{1,3}\s+', part):
                if current_text.strip():
                    sections.append((current_heading, current_text.strip()))
                current_heading = part.strip()
                current_text = ""
            else:
                current_text += part

        if current_text.strip():
            sections.append((current_heading, current_text.strip()))

    # Score sections by keyword overlap
    scored = []
    for heading, text in sections:
        combined = f"{heading} {text}".lower()
        combined_words = set(combined.split())
        overlap = len(query_words & combined_words)
        if overlap > 0:
            scored.append((overlap, heading, text))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    total_chars = 0
    for score, heading, text in scored[:max_sections]:
        snippet = text[:800] if len(text) > 800 else text
        if total_chars + len(snippet) > 4000:
            break
        results.append(f"{heading}\n{snippet}")
        total_chars += len(snippet)

    return results


def _build_database_section(state: AppState, refs: UIRefs, _section_help):
    """Build the database management UI."""

    # ══════════════════════════════════════════════════════
    # ── 1. Stats Overview ─────────────────────────────────
    # ══════════════════════════════════════════════════════
    with ui.expansion("Stats Overview", icon="analytics").classes("w-full").props(
        "default-opened dense header-class=section-title"
    ):
        with ui.card().classes("w-full q-pa-md"):
            _section_help(
                "Live counts of questions, certifications, and topics in the database. "
                "Updates automatically when data changes."
            )
            stats_container = ui.column().classes("w-full gap-1")

    def _refresh_stats():
        stats_container.clear()
        with stats_container:
            q_count = state.db.count()
            cert_count = len(state.db.list_certifications())
            topics = state.db.get_topics()

            with ui.row().classes("gap-4 items-center"):
                with ui.card().classes("q-pa-sm"):
                    ui.label(str(q_count)).classes("text-2xl font-bold text-primary")
                    ui.label("Questions").classes("text-xs text-grey-6")
                with ui.card().classes("q-pa-sm"):
                    ui.label(str(cert_count)).classes("text-2xl font-bold text-blue")
                    ui.label("Certifications").classes("text-xs text-grey-6")
                with ui.card().classes("q-pa-sm"):
                    ui.label(str(len(topics))).classes("text-2xl font-bold text-teal")
                    ui.label("Topics").classes("text-xs text-grey-6")

            with ui.row().classes("gap-2 q-mt-sm"):
                for status in STATUSES:
                    count = state.db.count(status=status)
                    if count:
                        label = STATUS_LABELS.get(status, status.title())
                        ui.badge(f"{label}: {count}", color="grey").props("outline").classes("text-xs")

    _refresh_stats()

    # ══════════════════════════════════════════════════════
    # ── 2. Questions / Certifications Browser ─────────────
    # ══════════════════════════════════════════════════════
    ui.separator().classes("q-my-sm")
    with ui.row().classes("items-center gap-2"):
        table_select = ui.toggle(
            {"questions": "Questions", "certifications": "Certifications"},
            value="questions",
        ).props("dense size=sm no-caps")
        table_indicator = ui.icon("quiz", color="blue", size="sm")

        def _update_table_indicator(val):
            if val == "questions":
                table_indicator._props["name"] = "quiz"
                table_indicator._props["color"] = "blue"
            else:
                table_indicator._props["name"] = "workspace_premium"
                table_indicator._props["color"] = "teal"
            table_indicator.update()

    questions_container = ui.column().classes("w-full gap-2")
    certs_container = ui.column().classes("w-full gap-2")

    # Search/filter state
    search_text = {"value": ""}
    filter_topic = {"value": ""}
    filter_status = {"value": ""}
    filter_cert = {"value": ""}
    from ...utils.config import config as _cfg
    page_state = {"offset": 0, "limit": _cfg.questions_per_page}

    def _reset_and_refresh():
        page_state["offset"] = 0
        _refresh_questions()

    def _refresh_questions():
        questions_container.clear()
        with questions_container:
            _section_help(
                "Browse, search, and manage individual questions. Use filters to narrow results. "
                "Click View for details, Edit to modify, or Delete to remove."
            )

            # Filters
            with ui.element("div").classes("w-full").style(
                "display: flex; flex-wrap: wrap; gap: 8px; align-items: flex-end;"
            ):
                certs = state.db.list_certifications()
                cert_opts = {"": "All"} | {c.id: c.name for c in certs}
                ui.select(
                    options=cert_opts,
                    label="Certification",
                    value=filter_cert["value"],
                    on_change=lambda e: (filter_cert.update({"value": e.value or ""}), _reset_and_refresh()),
                ).props("dense outlined clearable").style("min-width: 170px;")

                topics = state.db.get_topics(
                    certification_id=filter_cert["value"]
                ) if filter_cert["value"] else state.db.get_topics()
                ui.select(
                    options=[""] + topics,
                    label="Topic",
                    value=filter_topic["value"],
                    on_change=lambda e: (filter_topic.update({"value": e.value or ""}), _reset_and_refresh()),
                ).props("dense outlined clearable").style("min-width: 170px;")

                ui.select(
                    options={s: STATUS_LABELS.get(s, s.title()) for s in [""] + list(STATUSES)},
                    label="Status",
                    value=filter_status["value"],
                    on_change=lambda e: (filter_status.update({"value": e.value or ""}), _reset_and_refresh()),
                ).props("dense outlined clearable").style("min-width: 150px;")

                ui.input(
                    label="Search questions...",
                    value=search_text["value"],
                    on_change=lambda e: (search_text.update({"value": e.value}), _reset_and_refresh()),
                ).classes("flex-grow").props("dense outlined clearable").tooltip(
                    "Searches stems, scenarios, answers, explanations, and source text"
                )

            # Fetch results
            questions = state.db.search(
                text=search_text["value"],
                topic=filter_topic["value"],
                status=filter_status["value"],
                certification_id=filter_cert["value"],
                limit=page_state["limit"],
                offset=page_state["offset"],
            )

            total = state.db.count(
                topic=filter_topic["value"],
                status=filter_status["value"],
                certification_id=filter_cert["value"],
            )

            if not questions:
                with ui.column().classes("w-full items-center q-pa-lg gap-2"):
                    ui.icon("search_off", size="48px").classes("text-grey-4")
                    ui.label("No questions found").classes("text-base text-grey-5")
                    ui.label(
                        "Try adjusting your search terms or filters."
                    ).classes("text-xs text-grey-5")
                return

            # Pagination
            page_num = (page_state["offset"] // page_state["limit"]) + 1
            total_pages = max(1, (total + page_state["limit"] - 1) // page_state["limit"])
            start_num = page_state["offset"] + 1
            end_num = min(page_state["offset"] + page_state["limit"], total)

            with ui.row().classes("w-full items-center justify-between q-mt-sm"):
                ui.label(f"Showing {start_num}–{end_num} of {total} questions").classes("text-sm text-grey-6")
                with ui.row().classes("gap-1"):
                    ui.button(
                        icon="chevron_left",
                        on_click=lambda: (_page(-1), _refresh_questions()),
                    ).props("flat dense size=sm").set_enabled(page_state["offset"] > 0)
                    ui.label(f"Page {page_num} of {total_pages}").classes("text-xs text-grey-6 self-center")
                    ui.button(
                        icon="chevron_right",
                        on_click=lambda: (_page(1), _refresh_questions()),
                    ).props("flat dense size=sm").set_enabled(
                        page_state["offset"] + page_state["limit"] < total
                    )

            for q in questions:
                _render_question_row(q)

    def _page(direction: int):
        new_offset = page_state["offset"] + direction * page_state["limit"]
        page_state["offset"] = max(0, new_offset)

    def _render_question_row(q: Question):
        cert_name = ""
        if q.certification_id:
            cert_obj = state.db.get_certification(q.certification_id)
            cert_name = cert_obj.name if cert_obj else q.certification_id[:8]

        status_colors = {
            "draft": "grey", "sme_review": "blue", "revised": "purple",
            "approved": "positive", "rejected": "negative", "retired": "grey-8",
        }
        s_color = status_colors.get(q.status, "grey")

        with ui.card().classes("w-full q-pa-sm"):
            with ui.row().classes("w-full items-center justify-between"):
                with ui.column().classes("flex-grow gap-0"):
                    ui.label(q.stem[:100] + ("..." if len(q.stem) > 100 else "")).classes("text-sm font-medium")
                    with ui.row().classes("gap-1 q-mt-xs"):
                        ui.badge(STATUS_LABELS.get(q.status, q.status.title()), color=s_color).classes("text-xs")
                        if cert_name:
                            ui.badge(cert_name, color="blue").props("outline").classes("text-xs")
                        if q.topic:
                            ui.badge(q.topic, color="teal").props("outline").classes("text-xs")
                        ui.badge(q.difficulty, color="grey").props("outline").classes("text-xs")
                        ui.badge(q.bloom_level, color="grey").props("outline").classes("text-xs")
                        ui.badge(q.format_label, color="grey").props("outline").classes("text-xs")

                with ui.row().classes("gap-1"):
                    ui.button("View", icon="visibility", on_click=lambda _, qid=q.id: _view_question(qid)).props(
                        "flat dense size=sm"
                    ).tooltip("View full details")
                    ui.button("Edit", icon="edit", on_click=lambda _, qid=q.id: _edit_question(qid)).props(
                        "flat dense size=sm color=primary"
                    ).tooltip("Edit question")
                    ui.button("Delete", icon="delete", on_click=lambda _, qid=q.id: _delete_question(qid)).props(
                        "flat dense size=sm color=negative"
                    ).tooltip("Delete question")

    def _view_question(qid: str):
        q = state.db.get(qid)
        if not q:
            ui.notify("Question not found", type="warning")
            return

        with ui.dialog() as dlg, ui.card().classes("q-pa-md").style("min-width: 650px; max-width: 850px;"):
            ui.label("Question Details").classes("text-base font-bold")

            fields = [
                ("ID", q.id),
                ("Status", STATUS_LABELS.get(q.status, q.status)),
                ("Type", "Multi-Select" if q.question_type == "multi" else "Single Select"),
                ("Difficulty", q.difficulty),
                ("Bloom Level", q.bloom_level),
                ("Topic", q.topic),
                ("Source File", q.source_file),
                ("Created By", q.created_by),
                ("Created At", q.created_at),
                ("Updated At", q.updated_at),
            ]

            with ui.column().classes("w-full gap-1"):
                if q.scenario:
                    ui.label("Scenario").classes("text-xs font-bold text-grey-6")
                    ui.label(q.scenario).classes("text-sm q-mb-sm")

                ui.label("Stem").classes("text-xs font-bold text-grey-6")
                ui.label(q.stem).classes("text-sm font-medium q-mb-sm")

                ui.label("Options").classes("text-xs font-bold text-grey-6")
                correct_set = set(q.correct_answers)
                all_choices = q.all_choices
                for j, choice in enumerate(all_choices):
                    letter = string.ascii_uppercase[j] if j < 26 else str(j + 1)
                    is_correct = choice in correct_set
                    if is_correct:
                        ui.label(f"{letter}: {choice}").classes("text-sm text-positive font-medium")
                    else:
                        ui.label(f"{letter}: {choice}").classes("text-sm text-grey-7")

                answer_letters = [
                    string.ascii_uppercase[j] for j, c in enumerate(all_choices)
                    if c in correct_set and j < 26
                ]
                if answer_letters:
                    ui.label(f"Answer: {', '.join(answer_letters)}").classes("text-sm font-bold text-positive q-mt-xs")

                if q.explanation:
                    ui.label("Explanation").classes("text-xs font-bold text-grey-6 q-mt-sm")
                    ui.label(q.explanation).classes("text-sm")

                if q.key_source_text:
                    ui.label("Key Source Text").classes("text-xs font-bold text-grey-6 q-mt-sm")
                    ui.label(q.key_source_text).classes("text-sm italic text-grey-7")

                # Metadata in collapsible
                with ui.expansion("Metadata", icon="info").classes("w-full q-mt-sm").props("dense"):
                    for label, value in fields:
                        if value:
                            with ui.row().classes("gap-2"):
                                ui.label(f"{label}:").classes("text-xs font-bold text-grey-6").style("min-width: 100px")
                                ui.label(str(value)).classes("text-xs")

                if q.tags:
                    ui.label("Tags").classes("text-xs font-bold text-grey-6 q-mt-sm")
                    with ui.row().classes("gap-1"):
                        for tag in q.tags:
                            ui.badge(tag, color="grey").props("outline").classes("text-xs")

            with ui.row().classes("gap-2 justify-end q-mt-sm"):
                ui.button("Close", icon="close", on_click=dlg.close).props("flat")
        dlg.open()

    def _edit_question(qid: str):
        q = state.db.get(qid)
        if not q:
            ui.notify("Question not found", type="warning")
            return

        with ui.dialog() as dlg, ui.card().classes("q-pa-md").style("min-width: 650px; max-width: 850px;"):
            ui.label("Edit Question").classes("text-base font-bold")
            ui.label(f"ID: {q.id}").classes("text-xs text-grey-5")

            scenario_input = ui.textarea(
                label="Scenario (real-world context)", value=q.scenario
            ).classes("w-full").props("dense outlined autogrow")
            stem_input = ui.textarea(
                label="Stem (the question itself)", value=q.stem
            ).classes("w-full").props("dense outlined autogrow")

            # Unified answer options with toggle
            correct_set = set(q.correct_answers)
            all_options_data: list = []
            if q.option_order:
                for opt in q.option_order:
                    all_options_data.append({"text": opt, "is_key": opt in correct_set})
            else:
                key_vals = q.keys if (q.keys and len(q.keys) > 1) else ([q.key] if q.key else [])
                for k in key_vals:
                    all_options_data.append({"text": k, "is_key": True})
                for d in (q.distractors or []):
                    all_options_data.append({"text": d, "is_key": False})
            if not all_options_data:
                all_options_data.append({"text": "", "is_key": False})

            option_rows: list = []
            options_container = ui.column().classes("w-full gap-1")

            def _rebuild_options():
                options_container.clear()
                option_rows.clear()
                with options_container:
                    with ui.row().classes("w-full items-center justify-between"):
                        key_count = sum(1 for o in all_options_data if o["is_key"])
                        dist_count = sum(1 for o in all_options_data if not o["is_key"])
                        ui.label("Answer Options").classes("text-sm font-bold")
                        ui.label(f"{key_count} correct, {dist_count} wrong").classes("text-xs text-grey-6")
                    ui.label("Click Key/Dist to toggle. Use arrows to reorder.").classes("text-xs text-grey-5 q-mb-xs")
                    for j, opt in enumerate(all_options_data):
                        with ui.row().classes("w-full gap-1 items-center"):
                            letter = chr(65 + j) if j < 26 else str(j + 1)
                            ui.label(f"{letter}:").classes("text-sm font-bold").style("min-width: 24px")
                            inp = ui.input(value=opt["text"], placeholder=f"Option {letter}").classes("flex-grow").props("dense outlined")
                            is_key = opt["is_key"]
                            ui.button(
                                "Key" if is_key else "Dist",
                                icon="check_circle" if is_key else "cancel",
                                on_click=lambda _, jj=j: _toggle_option(jj),
                            ).props(f"{'color=positive' if is_key else 'color=grey'} dense size=sm flat"
                            ).tooltip("Click to toggle between correct answer and distractor")
                            if j > 0:
                                ui.button(icon="arrow_upward", on_click=lambda _, jj=j: _move_option(jj, -1)).props("flat round dense size=xs color=grey")
                            else:
                                ui.label("").style("width: 28px")
                            if j < len(all_options_data) - 1:
                                ui.button(icon="arrow_downward", on_click=lambda _, jj=j: _move_option(jj, 1)).props("flat round dense size=xs color=grey")
                            else:
                                ui.label("").style("width: 28px")
                            option_rows.append(inp)

            def _sync_options_text():
                for j, inp in enumerate(option_rows):
                    if j < len(all_options_data):
                        all_options_data[j]["text"] = inp.value

            def _toggle_option(j):
                _sync_options_text()
                all_options_data[j]["is_key"] = not all_options_data[j]["is_key"]
                _rebuild_options()

            def _move_option(j, direction):
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
                label="Key Source Text (exact quote from speaker notes)", value=q.key_source_text
            ).classes("w-full").props("dense outlined autogrow")

            with ui.row().classes("gap-2"):
                diff_sel = ui.select(DIFFICULTIES, value=q.difficulty, label="Difficulty").props("dense outlined")
                bloom_sel = ui.select(BLOOM_LEVELS, value=q.bloom_level, label="Bloom Level").props("dense outlined")
                status_sel = ui.select(
                    {s: STATUS_LABELS.get(s, s.title()) for s in STATUSES},
                    value=q.status, label="Status",
                ).props("dense outlined")
                topic_input = ui.input(label="Topic", value=q.topic).props("dense outlined")

            with ui.row().classes("gap-2 justify-end q-mt-sm"):
                ui.button("Cancel", icon="close", on_click=dlg.close).props("flat")

                def _save():
                    _sync_options_text()
                    editor = config.sme_name or ""
                    new_keys = [o["text"] for o in all_options_data if o["is_key"] and o["text"].strip()]
                    new_dists = [o["text"] for o in all_options_data if not o["is_key"] and o["text"].strip()]
                    q.record_edit("scenario", q.scenario, scenario_input.value, editor)
                    q.record_edit("stem", q.stem, stem_input.value, editor)
                    q.record_edit("key", q.key, new_keys[0] if new_keys else "", editor)
                    q.record_edit("distractors", "|".join(q.distractors), "|".join(new_dists), editor)
                    q.record_edit("explanation", q.explanation, explanation_input.value, editor)
                    q.record_edit("key_source_text", q.key_source_text, key_source_input.value, editor)
                    q.record_edit("difficulty", q.difficulty, diff_sel.value, editor)
                    q.record_edit("bloom_level", q.bloom_level, bloom_sel.value, editor)
                    q.record_edit("status", q.status, status_sel.value, editor)
                    q.record_edit("topic", q.topic, topic_input.value, editor)
                    q.scenario = scenario_input.value
                    q.stem = stem_input.value
                    if len(new_keys) > 1:
                        q.keys = new_keys
                        q.key = new_keys[0]
                        q.question_type = "multi"
                    elif new_keys:
                        q.key = new_keys[0]
                        q.keys = []
                        q.question_type = "single"
                    else:
                        q.key = ""
                        q.keys = []
                    q.distractors = new_dists
                    q.option_order = [o["text"] for o in all_options_data if o["text"].strip()]
                    q.explanation = explanation_input.value
                    q.key_source_text = key_source_input.value
                    q.difficulty = diff_sel.value
                    q.bloom_level = bloom_sel.value
                    q.status = status_sel.value
                    q.topic = topic_input.value
                    state.db.save(q)
                    ui.notify("Question saved", type="positive")
                    dlg.close()
                    _refresh_questions()
                    _refresh_stats()
                    state.bus.emit(EVT_BANK_CHANGED)

                ui.button("Save", icon="save", on_click=_save).props("color=positive")
        dlg.open()

    def _delete_question(qid: str):
        q = state.db.get(qid)
        if not q:
            ui.notify("Question not found", type="warning")
            return
        with ui.dialog() as dlg, ui.card().classes("q-pa-md").style("min-width: 400px;"):
            ui.label("Delete Question?").classes("text-base font-bold")
            ui.label(q.stem[:100] + ("..." if len(q.stem) > 100 else "")).classes("text-sm text-grey-7")
            ui.label(f"ID: {q.id}").classes("text-xs text-grey-5")
            with ui.row().classes("items-center gap-1 q-mt-sm"):
                ui.icon("warning", color="red", size="xs")
                ui.label("This action cannot be undone.").classes("text-xs text-red")
            with ui.row().classes("gap-2 justify-end q-mt-sm"):
                ui.button("Keep", icon="close", on_click=dlg.close).props("flat")
                def _confirm():
                    state.db.delete(qid)
                    ui.notify("Question deleted", type="positive")
                    dlg.close()
                    _refresh_questions()
                    _refresh_stats()
                    state.bus.emit_many(EVT_BANK_CHANGED, EVT_CERTIFICATIONS_CHANGED)
                ui.button("Delete", icon="delete", on_click=_confirm).props("color=negative")
        dlg.open()

    # ══════════════════════════════════════════════════════
    # ── 3. Bulk Operations ────────────────────────────────
    # ══════════════════════════════════════════════════════
    bulk_container = ui.column().classes("w-full gap-2 q-mt-md")

    def _refresh_bulk():
        bulk_container.clear()
        with bulk_container:
            with ui.expansion("Bulk Operations", icon="warning").classes("w-full").props(
                "dense header-class=section-title"
            ):
                with ui.card().classes("w-full q-pa-md"):
                    _section_help(
                        "Destructive operations that affect many records at once. "
                        "Truncate deletes ALL records. Delete by status/topic targets a specific subset. "
                        "All require confirmation."
                    )

                    with ui.row().classes("gap-2 flex-wrap"):
                        ui.button(
                            "Truncate Questions", icon="delete_forever",
                            on_click=_truncate_questions,
                        ).props("color=negative outline size=sm")
                        ui.button(
                            "Truncate Certifications", icon="delete_forever",
                            on_click=_truncate_certifications,
                        ).props("color=negative outline size=sm")
                        ui.button(
                            "Delete by Status", icon="filter_alt_off",
                            on_click=_delete_by_status,
                        ).props("color=warning outline size=sm")
                        ui.button(
                            "Delete by Topic", icon="label_off",
                            on_click=_delete_by_topic,
                        ).props("color=warning outline size=sm")

    def _truncate_questions():
        with ui.dialog() as dlg, ui.card().classes("q-pa-md").style("min-width: 400px;"):
            count = state.db.count()
            ui.label("Truncate All Questions?").classes("text-base font-bold text-red")
            ui.label(f"This will permanently delete all {count} question(s) from the database.").classes("text-sm")
            with ui.row().classes("items-center gap-1 q-mt-sm"):
                ui.icon("warning", color="red", size="xs")
                ui.label("This action cannot be undone.").classes("text-xs text-red")
            confirm_input = ui.input(label='Type "DELETE" to confirm').props("dense outlined").classes("w-full q-mt-sm")
            with ui.row().classes("gap-2 justify-end q-mt-sm"):
                ui.button("Cancel", on_click=dlg.close).props("flat")
                def _confirm():
                    if confirm_input.value != "DELETE":
                        ui.notify('Type "DELETE" to confirm', type="warning")
                        return
                    state.db.conn.execute("DELETE FROM questions")
                    state.db.conn.commit()
                    ui.notify(f"Deleted {count} question(s)", type="positive")
                    dlg.close()
                    _refresh_questions()
                    _refresh_stats()
                    state.bus.emit_many(EVT_BANK_CHANGED, EVT_CERTIFICATIONS_CHANGED)
                ui.button("Truncate", icon="delete_forever", on_click=_confirm).props("color=negative")
        dlg.open()

    def _truncate_certifications():
        with ui.dialog() as dlg, ui.card().classes("q-pa-md").style("min-width: 400px;"):
            certs = state.db.list_certifications()
            ui.label("Truncate All Certifications?").classes("text-base font-bold text-red")
            ui.label(f"This will permanently delete all {len(certs)} certification(s).").classes("text-sm")
            ui.label("Questions referencing these certifications will NOT be deleted but will lose their cert link.").classes("text-xs text-orange q-mt-sm")
            with ui.row().classes("items-center gap-1"):
                ui.icon("warning", color="red", size="xs")
                ui.label("This action cannot be undone.").classes("text-xs text-red")
            confirm_input = ui.input(label='Type "DELETE" to confirm').props("dense outlined").classes("w-full q-mt-sm")
            with ui.row().classes("gap-2 justify-end q-mt-sm"):
                ui.button("Cancel", on_click=dlg.close).props("flat")
                def _confirm():
                    if confirm_input.value != "DELETE":
                        ui.notify('Type "DELETE" to confirm', type="warning")
                        return
                    state.db.conn.execute("DELETE FROM certifications")
                    state.db.conn.commit()
                    ui.notify(f"Deleted {len(certs)} certification(s)", type="positive")
                    dlg.close()
                    _refresh_questions()
                    _refresh_stats()
                    _refresh_certs()
                    state.bus.emit_many(EVT_BANK_CHANGED, EVT_CERTIFICATIONS_CHANGED)
                ui.button("Truncate", icon="delete_forever", on_click=_confirm).props("color=negative")
        dlg.open()

    def _delete_by_status():
        with ui.dialog() as dlg, ui.card().classes("q-pa-md").style("min-width: 400px;"):
            ui.label("Delete Questions by Status").classes("text-base font-bold")
            ui.label("All questions with the selected status will be permanently deleted.").classes("text-xs text-grey-6 q-mb-xs")
            status_sel = ui.select(
                {s: f"{STATUS_LABELS.get(s, s.title())} ({state.db.count(status=s)})" for s in STATUSES},
                label="Select status to delete",
            ).props("dense outlined").classes("w-full")
            with ui.row().classes("gap-2 justify-end q-mt-sm"):
                ui.button("Cancel", on_click=dlg.close).props("flat")
                def _confirm():
                    if not status_sel.value:
                        ui.notify("Select a status first", type="warning")
                        return
                    count = state.db.count(status=status_sel.value)
                    state.db.conn.execute("DELETE FROM questions WHERE status = ?", (status_sel.value,))
                    state.db.conn.commit()
                    ui.notify(f"Deleted {count} {STATUS_LABELS.get(status_sel.value, '')} question(s)", type="positive")
                    dlg.close()
                    _refresh_questions()
                    _refresh_stats()
                    state.bus.emit_many(EVT_BANK_CHANGED, EVT_CERTIFICATIONS_CHANGED)
                ui.button("Delete", icon="delete", on_click=_confirm).props("color=negative")
        dlg.open()

    def _delete_by_topic():
        with ui.dialog() as dlg, ui.card().classes("q-pa-md").style("min-width: 400px;"):
            ui.label("Delete Questions by Topic").classes("text-base font-bold")
            ui.label("All questions with the selected topic will be permanently deleted.").classes("text-xs text-grey-6 q-mb-xs")
            topics = state.db.get_topics()
            topic_sel = ui.select(
                options=topics,
                label="Select topic to delete",
                with_input=True,
            ).props("dense outlined").classes("w-full")
            with ui.row().classes("gap-2 justify-end q-mt-sm"):
                ui.button("Cancel", on_click=dlg.close).props("flat")
                def _confirm():
                    if not topic_sel.value:
                        ui.notify("Select a topic first", type="warning")
                        return
                    count = state.db.count(topic=topic_sel.value)
                    state.db.conn.execute("DELETE FROM questions WHERE topic = ?", (topic_sel.value,))
                    state.db.conn.commit()
                    ui.notify(f"Deleted {count} question(s) with topic '{topic_sel.value}'", type="positive")
                    dlg.close()
                    _refresh_questions()
                    _refresh_stats()
                    state.bus.emit_many(EVT_BANK_CHANGED, EVT_CERTIFICATIONS_CHANGED)
                ui.button("Delete", icon="delete", on_click=_confirm).props("color=negative")
        dlg.open()

    # ── Certifications browser ─────────────────────────────

    def _refresh_certs():
        certs_container.clear()
        with certs_container:
            _section_help(
                "Manage certifications — each groups questions by exam track. "
                "Edit to change name, description, or source type."
            )
            certs = state.db.list_certifications()
            if not certs:
                with ui.column().classes("w-full items-center q-pa-lg gap-2"):
                    ui.icon("workspace_premium", size="48px").classes("text-grey-4")
                    ui.label("No certifications yet").classes("text-base text-grey-5")
                    ui.label("Create one in the sidebar to start organising questions.").classes("text-xs text-grey-5")
                return

            for cert in certs:
                q_count = state.db.count(certification_id=cert.id)
                with ui.card().classes("w-full q-pa-sm"):
                    with ui.row().classes("w-full items-center justify-between"):
                        with ui.column().classes("gap-0"):
                            ui.label(cert.name).classes("text-sm font-medium")
                            if cert.description:
                                ui.label(cert.description[:100]).classes("text-xs text-grey-6")
                            with ui.row().classes("gap-1 q-mt-xs"):
                                ui.badge(f"{q_count} questions", color="blue").props("outline").classes("text-xs")
                                ui.badge(cert.source_type or "pptx", color="grey").props("outline").classes("text-xs")
                                ui.label(f"ID: {cert.id[:12]}...").classes("text-xs text-grey-5")
                        with ui.row().classes("gap-1"):
                            ui.button("Edit", icon="edit", on_click=lambda _, cid=cert.id: _edit_cert(cid)).props(
                                "flat dense size=sm color=primary"
                            ).tooltip("Edit certification")
                            ui.button("Delete", icon="delete", on_click=lambda _, cid=cert.id: _delete_cert(cid)).props(
                                "flat dense size=sm color=negative"
                            ).tooltip("Delete certification")

    def _edit_cert(cid: str):
        cert = state.db.get_certification(cid)
        if not cert:
            ui.notify("Certification not found", type="warning")
            return
        with ui.dialog() as dlg, ui.card().classes("q-pa-md").style("min-width: 400px;"):
            ui.label("Edit Certification").classes("text-base font-bold")
            name_input = ui.input(label="Name", value=cert.name).classes("w-full").props("dense outlined")
            desc_input = ui.textarea(label="Description", value=cert.description).classes("w-full").props("dense outlined autogrow")
            type_sel = ui.select(
                {"pptx": "PPTX  —  slide-based", "docs": "Documentation  —  MCP servers"},
                value=cert.source_type or "pptx",
                label="Source Type",
            ).props("dense outlined")
            with ui.row().classes("gap-2 justify-end q-mt-sm"):
                ui.button("Cancel", on_click=dlg.close).props("flat")
                def _save():
                    cert.name = name_input.value
                    cert.description = desc_input.value
                    cert.source_type = type_sel.value
                    state.db.save_certification(cert)
                    ui.notify("Certification saved", type="positive")
                    dlg.close()
                    _refresh_certs()
                    _refresh_stats()
                ui.button("Save", icon="save", on_click=_save).props("color=positive")
        dlg.open()

    def _delete_cert(cid: str):
        cert = state.db.get_certification(cid)
        if not cert:
            return
        q_count = state.db.count(certification_id=cid)
        with ui.dialog() as dlg, ui.card().classes("q-pa-md").style("min-width: 400px;"):
            ui.label("Delete Certification?").classes("text-base font-bold")
            ui.label(f"Name: {cert.name}").classes("text-sm")
            if q_count:
                with ui.row().classes("items-center gap-1 q-mt-xs"):
                    ui.icon("warning", color="orange", size="xs")
                    ui.label(f"{q_count} question(s) reference this certification and will lose their link.").classes("text-xs text-orange")
            with ui.row().classes("gap-2 justify-end q-mt-sm"):
                ui.button("Keep", on_click=dlg.close).props("flat")
                def _confirm():
                    state.db.conn.execute("DELETE FROM certifications WHERE id = ?", (cid,))
                    state.db.conn.commit()
                    ui.notify(f"Deleted certification '{cert.name}'", type="positive")
                    dlg.close()
                    _refresh_certs()
                    _refresh_stats()
                ui.button("Delete", icon="delete", on_click=_confirm).props("color=negative")
        dlg.open()

    # ── Toggle visibility ──────────────────────────────────

    def _on_table_toggle(e):
        val = e.value or "questions"
        questions_container.set_visibility(val == "questions")
        certs_container.set_visibility(val == "certifications")
        bulk_container.set_visibility(val == "questions")
        _update_table_indicator(val)

    table_select.on_value_change(_on_table_toggle)

    # Register admin refresh callback
    def _refresh_admin():
        _refresh_questions()
        _refresh_stats()

    state.bus.on(EVT_ADMIN_CHANGED, _refresh_admin)

    # ══════════════════════════════════════════════════════
    # ── 4. Auto-Backup Settings ───────────────────────────
    # ══════════════════════════════════════════════════════
    with ui.expansion("Auto-Backup", icon="backup").classes("w-full q-mt-sm").props(
        "dense header-class=section-title"
    ):
        with ui.card().classes("w-full q-pa-md"):
            _section_help(
                "Automatically back up the database at a regular interval. "
                "Changes take effect on next app restart."
            )

            # Show last backup time
            from ...core.db_backup import list_backups
            backups = list_backups()
            if backups:
                latest = backups[0]
                with ui.row().classes("items-center gap-1 q-mb-sm"):
                    ui.icon("backup", size="xs").classes("text-positive")
                    ui.label(f"Last backup: {latest['created']} ({latest['size_kb']:.0f} KB)").classes("text-xs text-grey-6")
            else:
                with ui.row().classes("items-center gap-1 q-mb-sm"):
                    ui.icon("warning", size="xs").classes("text-orange")
                    ui.label("No backups yet — create one from the Bank tab").classes("text-xs text-orange")

            def _save_backup_field(field, value):
                setattr(config, field, value)
                config.save()

            with ui.row().classes("w-full gap-4 items-center"):
                ui.switch(
                    "Enable Auto-Backup",
                    value=config.auto_backup_enabled,
                    on_change=lambda e: _save_backup_field("auto_backup_enabled", e.value),
                ).tooltip("Turn on automatic scheduled backups")
                ui.number(
                    label="Interval (hours)",
                    value=config.auto_backup_interval_hours,
                    min=1, max=168, step=1,
                    on_change=lambda e: _save_backup_field("auto_backup_interval_hours", int(e.value or 24)),
                ).classes("w-32").props("dense outlined").tooltip(
                    "How often to create a backup (1-168 hours)"
                )
                ui.number(
                    label="Max backups to keep",
                    value=config.auto_backup_max_count,
                    min=1, max=50, step=1,
                    on_change=lambda e: _save_backup_field("auto_backup_max_count", int(e.value or 5)),
                ).classes("w-32").props("dense outlined").tooltip(
                    "When this limit is reached, the oldest backup is deleted"
                )

    # Initial render
    _refresh_questions()
    _refresh_certs()
    _refresh_bulk()
    certs_container.set_visibility(False)
