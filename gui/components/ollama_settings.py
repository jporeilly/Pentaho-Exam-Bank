"""Ollama AI settings component for the AI & Docs tab."""

import asyncio

from nicegui import ui

from ..state import UIRefs
from ...utils.config import config
from ...core import ollama_client


def build_ollama_settings(refs: UIRefs):
    """Build Ollama AI config card. Returns _refresh_models coroutine for external use."""

    with ui.card().classes("w-full q-pa-md"):
        with ui.row().classes("w-full items-center gap-2"):
            ui.icon("smart_toy", size="16px").classes("themed-icon")
            ui.label("Ollama AI").classes("text-sm font-semibold")
            ui.space()

            def _toggle_ollama(e):
                config.ollama_enabled = e.value
                config.save()
                ollama_content.set_visibility(e.value)
                if e.value:
                    ollama_status.set_text("Checking...")
                    ollama_status.props("color=grey-6")
                else:
                    ollama_status.set_text("Disabled")
                    ollama_status.props("color=grey-6")

            ui.switch("Enable", value=config.ollama_enabled, on_change=_toggle_ollama).props(
                "dense"
            ).classes("text-xs")
            ollama_status = ui.badge(
                "Disabled" if not config.ollama_enabled else "Checking...",
                color="grey-6",
            ).props("outline").classes("text-xs")

        # ── Help text ──
        with ui.row().classes("w-full items-start gap-1 q-mb-xs"):
            ui.icon("help_outline", size="xs").classes("text-grey-5 q-mt-xs")
            ui.label(
                "Ollama runs AI models locally on your machine. It powers question generation, "
                "AI improvement, QA checks, and the Docs Chat. Install from ollama.com, then "
                "pull a model (e.g. ollama pull llama3.2)."
            ).classes("text-xs text-grey-6")

        ollama_content = ui.column().classes("w-full gap-2")
        ollama_content.set_visibility(config.ollama_enabled)

        with ollama_content:
            # ── Server URL ──
            ui.label("Server URL").classes("text-xs font-semibold")
            ollama_url_input = ui.input(
                value=config.ollama_url,
                placeholder="http://localhost:11434",
            ).props("dense outlined").classes("w-full").tooltip(
                "The address where Ollama is running — usually localhost:11434"
            )

            def _save_url():
                config.ollama_url = ollama_url_input.value.strip()
                config.save()
            ollama_url_input.on("blur", lambda _: _save_url())

            # ── Model selection ──
            ui.label("Model").classes("text-xs font-semibold q-mt-xs")
            with ui.row().classes("w-full items-center gap-1"):
                ollama_model_select = ui.select(
                    [], value=None,
                ).props("dense outlined clearable").classes("flex-grow").style(
                    "min-width: 220px;"
                ).tooltip("Select the Ollama model used for question generation and AI features")
                refs.ollama_model_select = ollama_model_select

                def _save_model(e):
                    config.ollama_model = e.value or ""
                    config.save()
                ollama_model_select.on_value_change(_save_model)

                async def _refresh_models():
                    if not config.ollama_enabled:
                        ollama_status.set_text("Disabled")
                        ollama_status.props("color=grey-6")
                        return
                    url = ollama_url_input.value.strip() or ollama_client.DEFAULT_URL
                    ollama_status.set_text("Connecting...")
                    ollama_status.props("color=grey-6")
                    try:
                        models = await asyncio.to_thread(ollama_client.list_models, url)
                    except Exception:
                        models = None
                    if models:
                        names = [m.name for m in models]
                        ollama_model_select.options = names
                        ollama_model_select.update()
                        if config.ollama_model and config.ollama_model in names:
                            ollama_model_select.set_value(config.ollama_model)
                        elif names:
                            ollama_model_select.set_value(names[0])
                            config.ollama_model = names[0]
                        ollama_status.set_text(f"Connected ({len(names)} models)")
                        ollama_status.props("color=green-7")
                    else:
                        ollama_model_select.options = []
                        ollama_model_select.update()
                        ollama_status.set_text("Not connected")
                        ollama_status.props("color=red-7")

                ui.button(icon="refresh", on_click=_refresh_models).props(
                    "dense flat round size=sm"
                ).tooltip("Refresh model list from Ollama")

            ui.label(
                "No models listed? Run 'ollama pull llama3.2' in a terminal to download one."
            ).classes("text-xs text-grey-5")

            # ── Context Window ──
            ui.separator().classes("q-my-xs")
            ui.label("Context Window").classes("text-xs font-semibold")
            with ui.row().classes("w-full items-center gap-2"):
                num_ctx_input = ui.number(
                    label="num_ctx (tokens)",
                    value=config.ollama_num_ctx,
                    min=1024, max=131072, step=1024,
                ).style("min-width: 160px;").props("dense outlined").tooltip(
                    "How many tokens the model can process at once. "
                    "Higher = more context but more memory. "
                    "Can also be set via OLLAMA_NUM_CTX in .env"
                )

                def _save_num_ctx(e):
                    config.ollama_num_ctx = int(e.value or 8192)
                    config.save()
                num_ctx_input.on("blur", lambda _: _save_num_ctx(num_ctx_input))

                async def _auto_detect_ctx():
                    model = config.ollama_model
                    if not model:
                        ui.notify("Select a model first", type="warning")
                        return
                    url = ollama_url_input.value.strip() or ollama_client.DEFAULT_URL
                    ui.notify("Detecting GPU and model capabilities...", type="info", timeout=2000)
                    rec = await asyncio.to_thread(ollama_client.recommend_num_ctx, model, url)
                    if not rec.get("recommended"):
                        ui.notify("Could not auto-detect — using default 8192", type="warning")
                        return
                    num_ctx_input.value = rec["recommended"]
                    config.ollama_num_ctx = rec["recommended"]
                    config.save()
                    # Update the info display
                    _update_hw_info(rec)
                    ui.notify(
                        f"Set to {rec['recommended']:,} tokens based on your hardware",
                        type="positive",
                    )

                ui.button("Auto-detect", icon="memory", on_click=_auto_detect_ctx).props(
                    "flat dense size=sm"
                ).tooltip("Detect GPU and model context limit, then recommend optimal num_ctx")

            hw_info_container = ui.column().classes("w-full gap-0")

            def _update_hw_info(rec: dict):
                hw_info_container.clear()
                with hw_info_container:
                    with ui.row().classes("gap-4 flex-wrap"):
                        if rec.get("gpu_names") and rec["gpu_names"] != "No GPU detected":
                            with ui.row().classes("items-center gap-1"):
                                ui.icon("memory", size="xs").classes("text-positive")
                                ui.label(
                                    f"GPU: {rec['gpu_names']} "
                                    f"({rec.get('gpu_free_mb', 0):,} MB free / {rec.get('gpu_total_mb', 0):,} MB)"
                                ).classes("text-xs text-grey-6")
                        else:
                            with ui.row().classes("items-center gap-1"):
                                ui.icon("warning", size="xs").classes("text-orange")
                                ui.label("No GPU detected — running on CPU").classes("text-xs text-orange")
                        if rec.get("max_model"):
                            ui.label(
                                f"Model max: {rec['max_model']:,} tokens"
                            ).classes("text-xs text-grey-5")
                        if rec.get("param_size"):
                            ui.label(
                                f"Parameters: {rec['param_size']}"
                            ).classes("text-xs text-grey-5")

            ui.label(
                "Click Auto-detect to configure based on your GPU and model. "
                "Or set manually. OLLAMA_NUM_CTX in .env overrides on startup."
            ).classes("text-xs text-grey-5")

            # ── Model Recommendations ──
            ui.separator().classes("q-my-xs")
            with ui.expansion("Model Recommendations", icon="recommend").classes("w-full").props("dense"):
                with ui.row().classes("w-full items-start gap-1 q-mb-sm"):
                    ui.icon("help_outline", size="xs").classes("text-grey-5 q-mt-xs")
                    ui.label(
                        "Models recommended for your GPU. Shows installed models and suggestions "
                        "to pull. Click Scan to detect your hardware and see what fits."
                    ).classes("text-xs text-grey-6")

                model_rec_container = ui.column().classes("w-full gap-1")

                async def _scan_models():
                    url = ollama_url_input.value.strip() or ollama_client.DEFAULT_URL
                    ui.notify("Scanning GPU and model catalog...", type="info", timeout=2000)
                    # Get installed models
                    installed = await asyncio.to_thread(ollama_client.list_models, url)
                    installed_names = {m.name for m in installed} if installed else set()
                    # Get GPU info and recommendations
                    gpus = await asyncio.to_thread(ollama_client.get_gpu_info)
                    total_mb = sum(g["total_mb"] for g in gpus) if gpus else 0
                    recs = await asyncio.to_thread(ollama_client.recommend_models, total_mb)

                    model_rec_container.clear()
                    with model_rec_container:
                        if gpus:
                            total_gb = total_mb / 1024
                            gpu_names = ", ".join(g["name"] for g in gpus)
                            with ui.row().classes("items-center gap-1 q-mb-sm"):
                                ui.icon("memory", size="xs").classes("text-positive")
                                ui.label(f"GPU: {gpu_names} ({total_gb:.0f} GB total)").classes("text-xs text-grey-6")
                        else:
                            with ui.row().classes("items-center gap-1 q-mb-sm"):
                                ui.icon("warning", size="xs").classes("text-orange")
                                ui.label("No GPU detected — CPU-only recommendations").classes("text-xs text-orange")

                        # Category colors
                        cat_colors = {
                            "All-Rounder": "primary", "Chat": "blue", "Code": "teal",
                            "Vision": "purple", "Exam Writing": "positive",
                            "Embedding": "grey",
                        }

                        for cat, models in recs.items():
                            color = cat_colors.get(cat, "grey")
                            with ui.expansion(
                                f"{cat} ({sum(1 for m in models if m['fits'])} fit your GPU)",
                                icon="category",
                            ).classes("w-full").props("dense"):
                                for m in models:
                                    with ui.row().classes("w-full items-center gap-2 q-py-xs").style(
                                        "border-bottom: 1px solid rgba(128,128,128,0.1);"
                                    ):
                                        # Installed indicator
                                        if m["name"] in installed_names:
                                            ui.icon("check_circle", size="xs", color="positive").tooltip("Installed")
                                        else:
                                            ui.icon("download", size="xs").classes("text-grey-4").tooltip("Not installed")

                                        # Model name
                                        ui.label(m["name"]).classes("text-xs font-medium").style("min-width: 140px;")

                                        # Params
                                        ui.badge(m["params"], color="grey").props("outline").classes("text-xs")

                                        # VRAM
                                        ui.label(f"{m['vram_gb']} GB").classes("text-xs text-grey-5").style("min-width: 45px;")

                                        # Quality stars
                                        stars = "★" * m["quality"] + "☆" * (5 - m["quality"])
                                        ui.label(stars).classes("text-xs").style("min-width: 60px; letter-spacing: 1px;")

                                        # Fit badge
                                        ui.badge(m["fit_label"], color=m["fit_color"]).props("outline").classes("text-xs")

                                        # Notes
                                        ui.label(m["notes"]).classes("text-xs text-grey-5 flex-grow")

                                        # Pull button if not installed and fits
                                        if m["name"] not in installed_names and m["fits"]:
                                            ui.label(f"ollama pull {m['name']}").classes(
                                                "text-xs font-mono text-grey-5"
                                            ).tooltip("Run this command in your terminal to install")

                ui.button("Scan Hardware & Show Recommendations", icon="memory",
                          on_click=_scan_models).props("flat dense size=sm color=primary q-mt-xs")

            # ── System Prompt ──
            ui.separator().classes("q-my-xs")
            ui.label("System Prompt").classes("text-xs font-semibold")
            ui.label(
                "Override the default AI persona used for question generation. "
                "Leave blank to use the built-in certification exam writer prompt."
            ).classes("text-xs text-grey-5 q-mb-xs")
            ollama_prompt_input = ui.textarea(
                value=config.system_prompt,
                placeholder=ollama_client.DEFAULT_SYSTEM_PROMPT[:200] + "...",
            ).props("dense outlined rows=4").classes("w-full")
            refs.ollama_prompt_input = ollama_prompt_input

            def _save_prompt():
                config.system_prompt = ollama_prompt_input.value.strip()
                config.save()
            ollama_prompt_input.on("blur", lambda _: _save_prompt())

    return _refresh_models
