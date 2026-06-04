"""Student Preview — practice mode showing questions one at a time with feedback."""

import random
from nicegui import ui
from ..state import AppState, UIRefs


def open_student_view(questions: list):
    """Open the student preview dialog with the given questions."""
    if not questions:
        ui.notify("No questions to preview", type="warning")
        return

    # Shuffle a copy
    qs = list(questions)
    random.shuffle(qs)

    state = {"idx": 0, "score": 0, "answered": 0, "submitted": False}

    with ui.dialog() as dlg, ui.card().classes("q-pa-md").style("min-width: 700px; max-width: 900px; max-height: 85vh; overflow-y: auto;"):
        # Header
        with ui.row().classes("w-full items-center gap-2"):
            ui.icon("school", size="sm", color="primary")
            ui.label("Student Preview").classes("text-base font-bold")
            ui.space()
            score_label = ui.label("0/0 correct").classes("text-sm text-grey-6")
            progress_bar = ui.linear_progress(value=0, size="8px").classes("w-32")
            ui.button(icon="close", on_click=dlg.close).props("flat round dense size=sm")

        ui.separator()
        question_container = ui.column().classes("w-full gap-2")
        nav_container = ui.row().classes("w-full justify-between q-mt-md")

        def _render_question():
            question_container.clear()
            nav_container.clear()
            state["submitted"] = False
            q = qs[state["idx"]]

            with question_container:
                # Question number and metadata
                with ui.row().classes("items-center gap-2"):
                    ui.badge(f"Q{state['idx'] + 1} of {len(qs)}").props("color=primary")
                    ui.badge(q.difficulty).props(f"color={'green' if q.difficulty == 'Easy' else 'orange' if q.difficulty == 'Medium' else 'red'} outline")
                    if q.bloom_level:
                        ui.badge(q.bloom_level).props("color=blue outline")

                # Scenario
                if q.scenario:
                    ui.label(q.scenario).classes("text-sm italic text-grey-7 q-mt-sm")

                # Stem
                ui.label(q.stem).classes("text-base font-medium q-mt-sm")

                # Multi-select hint
                if q.question_type == "multi" and q.num_correct > 1:
                    ui.label(f"(Choose {q.num_correct})").classes("text-xs text-blue q-mt-xs")

                # Choices — shuffled, as radio (single) or checkboxes (multi)
                correct_set = set(q.correct_answers)
                choices = list(q.all_choices)
                random.shuffle(choices)
                letters = "ABCDEFGHIJ"

                selected = {"values": set()}
                choice_rows = []

                for i, choice in enumerate(choices):
                    letter = letters[i] if i < len(letters) else str(i + 1)
                    is_correct = choice in correct_set

                    with ui.row().classes("w-full items-start gap-2 q-py-xs") as row:
                        if q.question_type == "multi":
                            cb = ui.checkbox(f"{letter}. {choice}").classes("text-sm")
                            def on_check(e, c=choice):
                                if e.value:
                                    selected["values"].add(c)
                                else:
                                    selected["values"].discard(c)
                            cb.on_value_change(on_check)
                            choice_rows.append((row, cb, choice, is_correct))
                        else:
                            # For single-select, use a radio-like approach with toggle buttons
                            with ui.row().classes("items-center gap-1 cursor-pointer") as choice_row:
                                badge = ui.badge(letter).props("outline color=grey").classes("text-xs")
                                lbl = ui.label(choice).classes("text-sm")

                            def on_click(c=choice, b=badge, all_rows=choice_rows):
                                selected["values"] = {c}
                                # Update visual selection
                                for _, _, bb, _ in all_rows:
                                    bb.props(remove="color=primary")
                                    bb.props(add="color=grey")
                                b.props(remove="color=grey")
                                b.props(add="color=primary")

                            choice_row.on("click", on_click)
                            choice_rows.append((choice_row, choice, badge, is_correct))

                # Feedback container (shown after submit)
                feedback_container = ui.column().classes("w-full q-mt-md")

                def _submit():
                    if not selected["values"]:
                        ui.notify("Select an answer first", type="warning")
                        return
                    if state["submitted"]:
                        return
                    state["submitted"] = True
                    state["answered"] += 1

                    is_correct = selected["values"] == correct_set
                    if is_correct:
                        state["score"] += 1

                    # Update score display
                    score_label.set_text(f"{state['score']}/{state['answered']} correct")
                    progress_bar.set_value(state["answered"] / len(qs))

                    # Show feedback
                    feedback_container.clear()
                    with feedback_container:
                        if is_correct:
                            with ui.row().classes("items-center gap-2"):
                                ui.icon("check_circle", color="green", size="sm")
                                ui.label("Correct!").classes("text-sm font-bold text-green")
                        else:
                            with ui.row().classes("items-center gap-2"):
                                ui.icon("cancel", color="red", size="sm")
                                ui.label("Incorrect").classes("text-sm font-bold text-red")
                            correct_text = ", ".join(q.correct_answers)
                            ui.label(f"Correct answer: {correct_text}").classes("text-xs text-grey-7")

                        if q.explanation:
                            ui.label("Explanation:").classes("text-xs font-bold q-mt-xs")
                            ui.label(q.explanation).classes("text-xs text-grey-7")

                    # Color the choice rows
                    for row_data in choice_rows:
                        if q.question_type == "multi":
                            row, cb, choice, is_correct_choice = row_data
                            if is_correct_choice:
                                row.style(add="background: rgba(0,200,0,0.08); border-radius: 4px;")
                            elif choice in selected["values"]:
                                row.style(add="background: rgba(200,0,0,0.08); border-radius: 4px;")
                        else:
                            row, choice, badge, is_correct_choice = row_data
                            if is_correct_choice:
                                badge.props(remove="color=grey color=primary")
                                badge.props(add="color=green")
                            elif choice in selected["values"]:
                                badge.props(remove="color=grey color=primary")
                                badge.props(add="color=red")

                    _render_nav()

                # Submit button
                ui.button("Submit Answer", icon="check", on_click=_submit).props("color=primary")

            _render_nav()

        def _render_nav():
            nav_container.clear()
            with nav_container:
                ui.button("Previous", icon="arrow_back",
                          on_click=lambda: _go(-1)).props("flat dense size=sm").set_enabled(state["idx"] > 0)
                ui.label(f"{state['idx'] + 1} / {len(qs)}").classes("text-sm text-grey-6")
                if state["idx"] < len(qs) - 1:
                    ui.button("Next", icon="arrow_forward",
                              on_click=lambda: _go(1)).props("flat dense size=sm")
                else:
                    ui.button("Finish", icon="done_all",
                              on_click=lambda: _show_summary()).props("color=primary dense size=sm")

        def _go(direction):
            state["idx"] = max(0, min(len(qs) - 1, state["idx"] + direction))
            _render_question()

        def _show_summary():
            question_container.clear()
            nav_container.clear()
            with question_container:
                ui.label("Practice Complete!").classes("text-lg font-bold q-mt-md")
                pct = int(state["score"] / max(1, state["answered"]) * 100)
                color = "positive" if pct >= 80 else "warning" if pct >= 50 else "negative"
                ui.label(f"Score: {state['score']} / {state['answered']} ({pct}%)").classes(f"text-base text-{color}")
                ui.linear_progress(value=state["score"] / max(1, state["answered"]),
                                   size="16px").props(f"color={color}").classes("w-full q-mt-sm")
                ui.button("Close", icon="close", on_click=dlg.close).props("flat color=primary q-mt-md")

        _render_question()

    dlg.open()
