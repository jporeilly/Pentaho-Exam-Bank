"""Generate tab: generation settings (difficulty, Bloom's, question specs) + question editor."""

from nicegui import ui

from ..state import AppState, UIRefs
from .question_editor import build_question_editor
from ...utils.config import config


def build_generate_tab(state: AppState, refs: UIRefs):
    """Build the Generate tab: generation settings and inline question editor."""
    from ...core.question_bank import BLOOM_LEVELS, DIFFICULTIES

    def _save(field, value):
        setattr(config, field, value)
        config.save()

    # Descriptive dropdown options
    DIFFICULTY_OPTIONS = {
        "Easy": "Easy  —  recall facts and definitions",
        "Medium": "Medium  —  apply concepts to scenarios",
        "Hard": "Hard  —  analyze, evaluate, or design",
    }
    BLOOM_OPTIONS = {
        "Remember": "Remember  —  recall facts",
        "Understand": "Understand  —  explain ideas",
        "Apply": "Apply  —  use in new situations",
        "Analyze": "Analyze  —  break down and compare",
        "Evaluate": "Evaluate  —  justify and critique",
        "Create": "Create  —  design something new",
    }

    # ── Generation Settings ──────────────────────────────
    with ui.expansion("Generation Settings", icon="tune").classes("w-full").props(
        "default-opened dense header-class=section-title"
    ):
        with ui.card().classes("w-full q-pa-md"):
            with ui.row().classes("w-full items-start gap-1 q-mb-sm"):
                ui.icon("help_outline", size="xs").classes("text-grey-5 q-mt-xs")
                ui.label(
                    "Set the difficulty and cognitive level for AI-generated questions. "
                    "These defaults apply to every question generated from the current slide."
                ).classes("text-xs text-grey-6")

            with ui.row().classes("w-full gap-2 items-end"):
                ui.select(
                    DIFFICULTY_OPTIONS, value=config.default_difficulty,
                    label="Difficulty",
                    on_change=lambda e: _save("default_difficulty", e.value),
                ).classes("flex-grow").props("dense outlined").tooltip(
                    "Controls how challenging the questions will be"
                )
                # Initialise the multi-select Bloom's state from saved default.
                if not getattr(state, "_gen_bloom_levels", None):
                    state._gen_bloom_levels = [config.default_bloom_level]

                def _on_bloom_change(e):
                    levels = e.value or []
                    if isinstance(levels, str):
                        levels = [levels]
                    if not levels:
                        levels = [config.default_bloom_level]
                    state._gen_bloom_levels = levels
                    # Keep the single saved default in sync (first selected).
                    _save("default_bloom_level", levels[0])

                ui.select(
                    BLOOM_OPTIONS, value=list(state._gen_bloom_levels),
                    label="Bloom's Taxonomy Level(s)",
                    multiple=True,
                    on_change=_on_bloom_change,
                ).classes("flex-grow").props("dense outlined use-chips").tooltip(
                    "Pick one or more levels. With several selected, they're spread across "
                    "slides/sections in turn — higher levels demand more analysis."
                )

            # ── Question specs ──
            ui.separator().classes("q-my-sm")

            if not hasattr(state, '_gen_question_specs'):
                state._gen_question_specs = [{"keys": 1, "distractors": 3}]

            specs_container = ui.column().classes("w-full gap-1")

            def _rebuild_specs():
                specs_container.clear()
                with specs_container:
                    with ui.row().classes("w-full items-center gap-2"):
                        ui.label("Questions per slide / section").classes("text-sm font-semibold")
                        ui.button(icon="add", on_click=_add_question_spec).props(
                            "flat round dense size=xs color=positive"
                        ).tooltip("Add another question per slide/section")
                        _n = len(state._gen_question_specs)
                        ui.label(f"· {_n} per slide/section").classes("text-xs text-grey-5")
                    ui.label(
                        "Each row = one question generated per slide (PPTX) or per section "
                        "(PCM course / Docs). Set 1 key for single-select, 2+ for multi-select "
                        "(\"Which two…\"). Add rows with ＋ to generate more questions each. "
                        "Total generated = (slides or sections) × rows."
                    ).classes("text-xs text-grey-5 q-mb-xs")

                    for qi, spec in enumerate(state._gen_question_specs):
                        with ui.row().classes("w-full gap-2 items-center"):
                            ui.label(f"Q{qi + 1}").classes("text-xs font-mono w-8")
                            ui.number(
                                label="Correct answers",
                                value=spec["keys"],
                                min=1, max=4, step=1,
                                on_change=lambda e, i=qi: _update_spec(i, "keys", int(e.value or 1)),
                            ).classes("w-32").props("dense outlined").tooltip(
                                "Number of correct answers — 1 = single-select, 2+ = multi-select"
                            )
                            ui.number(
                                label="Wrong answers",
                                value=spec["distractors"],
                                min=1, max=6, step=1,
                                on_change=lambda e, i=qi: _update_spec(i, "distractors", int(e.value or 3)),
                            ).classes("w-32").props("dense outlined").tooltip(
                                "Number of plausible but incorrect answers"
                            )
                            q_type = "Multi-select" if spec["keys"] > 1 else "Single-select"
                            total = spec["keys"] + spec["distractors"]
                            ui.label(f"{q_type} · {total} choices").classes("text-xs text-grey-5")
                            if len(state._gen_question_specs) > 1:
                                ui.button(icon="remove", on_click=lambda _, i=qi: _remove_question_spec(i)).props(
                                    "flat round dense size=xs color=negative"
                                ).tooltip("Remove this question row")

            def _update_spec(idx, field, value):
                state._gen_question_specs[idx][field] = value
                _rebuild_specs()

            def _add_question_spec():
                last = state._gen_question_specs[-1] if state._gen_question_specs else {"keys": 1, "distractors": 3}
                state._gen_question_specs.append({"keys": last["keys"], "distractors": last["distractors"]})
                _rebuild_specs()

            def _remove_question_spec(idx):
                if len(state._gen_question_specs) > 1:
                    state._gen_question_specs.pop(idx)
                    _rebuild_specs()

            _rebuild_specs()

            # ── Total target (PCM course / Docs) ──
            ui.separator().classes("q-my-sm")
            if not hasattr(state, "_gen_target_total"):
                state._gen_target_total = 0

            def _on_target_change(e):
                state._gen_target_total = int(e.value or 0)

            with ui.row().classes("w-full items-center gap-2"):
                ui.number(
                    label="Total questions to generate",
                    value=state._gen_target_total, min=0, max=500, step=1,
                    on_change=_on_target_change,
                ).classes("w-56").props("dense outlined").tooltip(
                    "For a PCM course or Docs: total questions to generate, spread across "
                    "all sections (overrides the per-section count above). 0 = use the "
                    "per-slide/section rows instead."
                )
                ui.label(
                    "Set a total to generate more than one per section — e.g. 20 across "
                    "a 6-section course. Leave 0 to use the rows above."
                ).classes("text-xs text-grey-5")

            # ── Options toggles ──
            ui.separator().classes("q-my-sm")
            with ui.row().classes("w-full items-center gap-4"):
                with ui.row().classes("items-center gap-1"):
                    def _on_scenario_change(e):
                        state._gen_include_scenario = e.value
                    ui.switch("Include scenario", value=True, on_change=_on_scenario_change).props("dense")
                    ui.icon("help_outline", size="xs").classes("text-grey-5 cursor-pointer").tooltip(
                        "When enabled, each question begins with a realistic workplace scenario "
                        "(1-3 sentences) that sets the context before the question stem."
                    )
                with ui.row().classes("items-center gap-1"):
                    def _on_mermaid_change(e):
                        config.mermaid_enabled = e.value
                        config.save()
                    ui.switch(
                        "Mermaid diagrams", value=config.mermaid_enabled,
                        on_change=_on_mermaid_change,
                    ).props("dense")
                    ui.icon("account_tree", size="xs").classes("text-grey-5 cursor-pointer").tooltip(
                        "When enabled, the AI may include Mermaid diagrams (flowcharts, sequence "
                        "diagrams, mind maps) in explanations to visualize processes and relationships."
                    )

    # ── Generated Questions (inline editor) ──────────────
    ui.separator().classes("q-my-sm")
    build_question_editor(state, refs)
