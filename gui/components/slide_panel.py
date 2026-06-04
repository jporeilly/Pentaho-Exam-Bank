"""Slide preview panel: shows slide images, thumbnails, and speaker notes side-by-side."""

import os
import shutil

from nicegui import ui

from ..state import AppState, UIRefs, EVT_SLIDE_CHANGED, EVT_ACTION_BAR_CHANGED
from ..styles import STATIC_DIR


def build_slide_panel(state: AppState, refs: UIRefs):
    """Build the slide preview panel matching pptx_to_video two-column layout."""

    with ui.card().classes("w-full q-pa-md") as slide_card:
        with ui.row().classes("items-center gap-2 q-mb-xs"):
            ui.icon("preview", size="20px").classes("themed-icon")
            panel_title = ui.label("Slide Preview").classes("text-sm font-bold")
            ui.space()
            slide_info = ui.label("Select a file").classes("muted text-xs")

        preview_container = ui.column().classes("w-full")
        action_bar_container = ui.row().classes(
            "w-full items-center gap-2 q-pa-xs"
        ).style("border-top: 1px solid rgba(128,128,128,0.2);")

    def refresh_slide_preview():
        preview_container.clear()

        slide = state.current_slide
        f = state.selected_file

        if not f or not slide:
            # Check if a docs-based certification is active (no PPTX needed)
            docs_cert = None
            if state.active_cert_id:
                cert = state.db.get_certification(state.active_cert_id)
                if cert and cert.source_type == "docs":
                    docs_cert = cert

            if docs_cert:
                topic_display = state.active_topic or docs_cert.name
                slide_info.set_text(f"Docs: {docs_cert.name}")
                panel_title.set_text("Documentation Source")
                with preview_container:
                    with ui.column().classes("w-full items-center q-pa-lg gap-2"):
                        ui.icon("auto_stories", size="64px", color="teal")
                        ui.label(f"Certification: {docs_cert.name}").classes("text-sm font-medium")
                        ui.label(f"Search topic: {topic_display}").classes("text-sm text-teal")

                        # Show selected MCP servers
                        from ...utils.config import config as _cfg
                        if _cfg.mcp_servers:
                            selected_urls = state.active_mcp_servers
                            if selected_urls:
                                active = [s for s in _cfg.mcp_servers if s.get("url") in selected_urls]
                            else:
                                active = _cfg.mcp_servers
                            server_names = [s.get("name", s.get("url", "?")) for s in active]
                            ui.label(f"Servers: {', '.join(server_names)}").classes("text-xs text-grey-6")
                        else:
                            ui.label("No MCP servers configured — check AI & Docs tab").classes("text-xs text-orange")

                        ui.label(
                            "Type a search topic in the sidebar topic field, "
                            "then click Generate from Docs below."
                        ).classes("text-xs muted text-center").style("max-width: 450px;")
                refresh_action_bar()
                return

            slide_info.set_text("Select a file or select a Docs certification")
            panel_title.set_text("Slide Preview")
            with preview_container:
                with ui.column().classes("w-full items-center q-pa-xl"):
                    ui.icon("slideshow", size="64px").classes("muted")
                    ui.label("Load a PPTX file, or select a Docs certification to generate from documentation").classes("muted text-sm text-center")
            return

        slide_idx = state.current_slide_idx
        slide_info.set_text(f"Slide {slide_idx + 1}/{f.slide_count} — {f.path.name}")
        panel_title.set_text("Slide Preview")

        with preview_container:
            # Two-column layout: Slide Image | Speaker Notes
            with ui.row().classes("w-full gap-4").style("flex-wrap: nowrap; align-items: flex-start;"):

                # -- LEFT COLUMN: Slide image + filmstrip + nav --
                with ui.column().classes("gap-1").style("flex: 1 1 50%; min-width: 0;"):

                    # Slide image (from PowerPoint COM export)
                    img_path = f.slide_images[slide_idx] if slide_idx < len(f.slide_images) else None
                    if img_path and img_path.exists():
                        static_img = STATIC_DIR / f"qb_slide_{slide_idx}.png"
                        shutil.copy(img_path, static_img)
                        ui.image(
                            f"/static/qb_slide_{slide_idx}.png?v={state.preview_cache_bust}&t={int(os.path.getmtime(static_img) * 1000)}"
                        ).classes("slide-preview-img w-full").props("fit=contain").style(
                            "max-height: 45vh; border-radius: 6px;"
                        )
                    else:
                        # Fallback: show text content if no image available
                        with ui.column().classes("w-full q-pa-md").style(
                            "min-height: 200px; background: #1a1a2e; border-radius: 8px;"
                            " display: flex; align-items: center; justify-content: center;"
                        ):
                            if slide.title:
                                ui.label(slide.title).classes("text-lg font-bold").style("color: #e0e0e0;")
                            if slide.body_text:
                                ui.label(slide.body_text[:300]).classes("text-sm").style(
                                    "color: #b0b0b0; white-space: pre-wrap;"
                                )
                            if not slide.title and not slide.body_text:
                                ui.label(f"Slide {slide_idx + 1}").classes("text-xl muted")
                            ui.label("Exporting slide images...").classes("text-xs muted q-mt-sm")

                    # Content summary badges
                    with ui.row().classes("items-center gap-1 flex-wrap q-mt-xs"):
                        if slide.title:
                            ui.badge("Has Title").props("color=primary outline").classes("text-xs")
                        if slide.body_text:
                            ui.badge(f"{len(slide.body_text)} chars body").props("color=primary outline").classes("text-xs")
                        if slide.speaker_notes:
                            ui.badge(f"{len(slide.speaker_notes)} chars notes").props("color=green outline").classes("text-xs")
                        else:
                            ui.badge("No Notes").props("color=orange outline").classes("text-xs")

                    # Thumbnail filmstrip (with actual images when available)
                    if f.slide_count > 1:
                        with ui.row().classes("w-full gap-1 items-center q-pa-xs").style(
                            "flex-wrap: nowrap; overflow-x: auto; overflow-y: hidden;"
                        ):
                            for t_idx in range(f.slide_count):
                                is_current = t_idx == slide_idx
                                t_slide = f.reader.slides[t_idx] if f.reader else None
                                has_notes = bool(t_slide and t_slide.speaker_notes and t_slide.speaker_notes.strip())
                                t_img = f.slide_images[t_idx] if t_idx < len(f.slide_images) else None

                                def _click_thumb(idx=t_idx):
                                    _nav_to(idx)

                                border = "border: 2px solid var(--theme-primary, #1976d2);" if is_current else "border: 2px solid transparent;"
                                opacity = "opacity: 1;" if is_current else "opacity: 0.6;"

                                if t_img and t_img.exists():
                                    # Actual slide thumbnail image
                                    static_thumb = STATIC_DIR / f"qb_thumb_{t_idx}.png"
                                    shutil.copy(t_img, static_thumb)
                                    ui.image(
                                        f"/static/qb_thumb_{t_idx}.png?v={state.preview_cache_bust}&t={int(os.path.getmtime(static_thumb) * 1000)}"
                                    ).classes("cursor-pointer").style(
                                        f"height: 72px; width: 96px; object-fit: cover;"
                                        f" border-radius: 4px; {border} {opacity}"
                                    ).on("click", _click_thumb)
                                else:
                                    # Fallback: numbered placeholder
                                    bg = "background: #e8f5e9;" if has_notes else "background: #fff3e0;"
                                    ui.label(f"{t_idx + 1}").classes("cursor-pointer text-xs font-mono").style(
                                        f"height: 72px; width: 96px; display: flex; align-items: center; "
                                        f"justify-content: center; border-radius: 3px; {border} {opacity} {bg}"
                                    ).on("click", _click_thumb)

                    # Navigation below thumbnails
                    with ui.row().classes("w-full items-center justify-center gap-2 q-mt-xs"):
                        prev_btn = ui.button(
                            icon="chevron_left", on_click=lambda: _nav(-1),
                        ).props("dense flat round").tooltip("Previous slide")
                        prev_btn.classes("slide-nav-prev")
                        if slide_idx == 0:
                            prev_btn.disable()

                        ui.label(f"{slide_idx + 1} / {f.slide_count}").classes(
                            "text-sm font-mono"
                        )

                        next_btn = ui.button(
                            icon="chevron_right", on_click=lambda: _nav(1),
                        ).props("dense flat round").tooltip("Next slide")
                        next_btn.classes("slide-nav-next")
                        if slide_idx >= f.slide_count - 1:
                            next_btn.disable()

                        if f.slide_count > 2:
                            nav_slider = ui.slider(
                                min=0, max=f.slide_count - 1, step=1, value=slide_idx,
                            ).classes("w-32")
                            nav_slider.on_value_change(lambda e: _nav_to(int(e.value)))

                # -- RIGHT COLUMN: Speaker Notes --
                with ui.column().classes("gap-2").style("flex: 1 1 50%; min-width: 0;"):
                    # Notes header
                    with ui.row().classes("items-center gap-1"):
                        ui.icon("notes", size="16px").classes("themed-icon")
                        ui.label("Speaker Notes").classes("text-xs font-semibold")
                        ui.space()
                        notes_text = slide.speaker_notes or ""
                        notes_len = len(notes_text.strip())
                        ui.label(f"{notes_len} chars").classes("muted text-xs")

                    # Notes content (read-only display)
                    if notes_text.strip():
                        ui.textarea(value=notes_text).classes(
                            "w-full"
                        ).props("outlined autogrow rows=6 dense readonly")
                    else:
                        ui.label("This slide has no speaker notes.").classes("muted italic")
                        ui.label(
                            "Questions require speaker notes — the correct answer (key) must be "
                            "traceable to the notes text."
                        ).classes("text-xs muted q-mt-xs")

        refresh_action_bar()

    def refresh_action_bar():
        """Rebuild only the action bar (Generate / progress) without touching the slide preview."""
        action_bar_container.clear()
        with action_bar_container:
            if state.is_generating:
                ui.spinner(size="sm")
                msg = state.progress_message or "Generating..."
                ui.label(msg).classes("text-xs")
                ui.button("Cancel", icon="cancel", on_click=lambda: _cancel()).props(
                    "flat dense size=sm color=negative"
                )
            else:
                # Label depends on the active certification's source type.
                _src = ""
                if state.active_cert_id:
                    _cert = state.db.get_certification(state.active_cert_id)
                    _src = _cert.source_type if _cert else ""
                _docs_mode = _src == "docs"
                _pcm_mode = _src == "pcm"
                if _pcm_mode:
                    btn_label = "Generate from PCM course"
                    btn_tip = "Generate questions from the selected PCM course's content"
                elif _docs_mode:
                    btn_label = "Generate from Docs"
                    btn_tip = "Generate questions from MCP documentation"
                else:
                    btn_label = "Generate"
                    btn_tip = "Generate questions for this slide using AI"
                ui.button(
                    btn_label, icon="auto_awesome",
                    on_click=lambda: refs.on_generate() if refs.on_generate else None,
                ).props("dense flat color=primary size=sm").tooltip(btn_tip)
                if not _docs_mode and not _pcm_mode:
                    ui.button(
                        "Generate All Slides", icon="dynamic_feed",
                        on_click=lambda: refs.on_generate_batch() if refs.on_generate_batch else None,
                    ).props("dense flat color=secondary size=sm").tooltip(
                        "Generate questions from ALL slides with speaker notes"
                    )
                    if state.selected_file and state.current_slide:
                        ui.button("Compare", icon="compare", on_click=lambda: _compare_models()).props(
                            "flat dense color=purple size=sm"
                        ).tooltip("Compare two AI models")

    def _compare_models():
        from ...core import ollama_client
        from ...core.question_generation import generate_questions_batch
        from ...utils.config import config
        import threading

        # Check prerequisites
        if not config.ollama_enabled:
            ui.notify("Ollama not enabled", type="warning")
            return
        f = state.selected_file
        if not f or not f.reader:
            ui.notify("No file loaded", type="warning")
            return
        slide = state.current_slide
        if not slide:
            ui.notify("No slide selected", type="warning")
            return

        try:
            models = ollama_client.list_models(base_url=config.ollama_url)
            model_names = [m.name for m in models]
        except Exception:
            ui.notify("Could not fetch models from Ollama", type="warning")
            return

        if len(model_names) < 2:
            ui.notify("Need at least 2 Ollama models installed for comparison", type="warning")
            return

        with ui.dialog() as dlg, ui.card().classes("q-pa-md").style("min-width: 900px; max-width: 1100px; max-height: 85vh; overflow-y: auto;"):
            ui.label("Model Comparison").classes("text-base font-bold")
            ui.label(f"Slide {state.current_slide_idx + 1}: {slide.title or 'Untitled'}").classes("text-sm text-grey-6")

            with ui.row().classes("w-full gap-4 items-end"):
                model_a = ui.select(model_names, value=model_names[0], label="Model A").props("dense outlined").classes("flex-1")
                model_b = ui.select(model_names, value=model_names[1] if len(model_names) > 1 else model_names[0], label="Model B").props("dense outlined").classes("flex-1")

            results_container = ui.row().classes("w-full gap-4 q-mt-md")

            def _run_comparison():
                if model_a.value == model_b.value:
                    ui.notify("Select two different models", type="warning")
                    return

                results_container.clear()
                with results_container:
                    ui.spinner("dots", size="lg")
                    ui.label("Generating with both models...").classes("text-sm text-grey-6")

                results = {"a": None, "b": None, "done": 0}
                # Hidden anchor for safe callback scheduling
                anchor = ui.column().style("display:none;")

                def gen(model_name, key):
                    try:
                        qs = generate_questions_batch(
                            slides=[slide],
                            model=model_name,
                            base_url=config.ollama_url,
                            num_per_slide=1,
                            difficulty=config.default_difficulty,
                            bloom_level=config.default_bloom_level,
                            certification_id=state.active_cert_id or (f.certification_id if f else ""),
                            source_file=f.path.name if f else "",
                            system_prompt=config.system_prompt,
                            topic=state.active_topic or (f.topic if f else ""),
                        )
                        results[key] = qs[0] if qs else None
                    except Exception as e:
                        results[key] = str(e)
                    results["done"] += 1
                    if results["done"] == 2:
                        with anchor:
                            ui.timer(0, lambda: (_show_results(results), False), once=True)

                threading.Thread(target=gen, args=(model_a.value, "a"), daemon=True).start()
                threading.Thread(target=gen, args=(model_b.value, "b"), daemon=True).start()

            def _show_results(results):
                results_container.clear()
                with results_container:
                    for key, label_text, model_name in [("a", "Model A", model_a.value), ("b", "Model B", model_b.value)]:
                        with ui.card().classes("flex-1 q-pa-sm"):
                            ui.label(f"{label_text}: {model_name}").classes("text-sm font-bold")
                            q = results[key]
                            if isinstance(q, str):
                                ui.label(f"Error: {q}").classes("text-sm text-red")
                            elif q is None:
                                ui.label("No question generated").classes("text-sm text-grey-5")
                            else:
                                if q.scenario:
                                    ui.label(q.scenario).classes("text-xs italic text-grey-6 q-mt-xs")
                                ui.label(q.stem).classes("text-sm font-medium q-mt-xs")
                                for ans in q.correct_answers:
                                    ui.label(f"✓ {ans}").classes("text-xs text-green")
                                for d in q.distractors:
                                    ui.label(f"✗ {d}").classes("text-xs text-grey-6")
                                if q.explanation:
                                    with ui.expansion("Explanation").classes("q-mt-xs"):
                                        ui.label(q.explanation).classes("text-xs")
                                # "Keep this" button
                                def _keep(question=q):
                                    state.generated_questions.append(question)
                                    state.bus.emit("questions_changed")
                                    ui.notify(f"Added question from {model_name}", type="positive")
                                ui.button("Keep This", icon="add", on_click=_keep).props("flat dense color=positive size=sm q-mt-sm")

            ui.button("Generate & Compare", icon="compare_arrows", on_click=_run_comparison).props("color=primary")
            ui.button("Close", on_click=dlg.close).props("flat")

        dlg.open()

    def _cancel():
        """Cancel generation — sets flag checked by the background thread."""
        state._cancel_generation = True
        state.progress_message = "Cancelling..."

    def _nav(delta):
        f = state.selected_file
        if not f:
            return
        new_idx = state.current_slide_idx + delta
        if 0 <= new_idx < f.slide_count:
            state.current_slide_idx = new_idx
            refresh_slide_preview()

    def _nav_to(idx):
        f = state.selected_file
        if not f:
            return
        if 0 <= idx < f.slide_count:
            state.current_slide_idx = idx
            refresh_slide_preview()

    state.bus.on(EVT_SLIDE_CHANGED, refresh_slide_preview)
    state.bus.on(EVT_ACTION_BAR_CHANGED, refresh_action_bar)
    refs.nav_slide = _nav
    refresh_slide_preview()
