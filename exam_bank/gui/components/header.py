"""Header bar with app title, theme selector, dark mode toggle, and exit button."""

import asyncio
import os

from nicegui import ui, app

from ..styles import THEME_COLORS
from ...utils.config import config


def build_header():
    """Build the app header bar matching pptx_to_video style."""
    dark = ui.dark_mode(config.dark_mode)

    # Load saved theme
    saved_theme = config.theme_color
    if saved_theme not in THEME_COLORS:
        saved_theme = "Slate"
    initial_theme = THEME_COLORS[saved_theme]

    # Apply initial theme via JS
    ui.add_head_html(f"""<script>
    document.documentElement.style.setProperty('--theme-gradient', '{initial_theme["gradient"]}');
    document.documentElement.style.setProperty('--theme-primary', '{initial_theme["primary"]}');
    document.addEventListener('DOMContentLoaded', function() {{
        if (window.Quasar) Quasar.setCssVar('primary', '{initial_theme["primary"]}');
    }});
    </script>""")

    with ui.header().classes("app-header items-center justify-between"):
        with ui.row().classes("items-center gap-2"):
            ui.icon("quiz", size="24px").classes("text-white")
            ui.label("Pentaho Exam Bank").classes("text-lg font-bold text-white tracking-wide")

        with ui.row().classes("items-center gap-3"):
            theme_select = ui.select(
                list(THEME_COLORS.keys()), value=saved_theme,
            ).props("dense dark borderless").classes("text-white").style("min-width: 90px;")

            def on_theme_change(e):
                theme = THEME_COLORS.get(e.value, THEME_COLORS["Slate"])
                ui.run_javascript(f"""
                    document.documentElement.style.setProperty('--theme-gradient', '{theme["gradient"]}');
                    document.documentElement.style.setProperty('--theme-primary', '{theme["primary"]}');
                    if (window.Quasar) Quasar.setCssVar('primary', '{theme["primary"]}');
                """)
                config.theme_color = e.value
                config.save()

            theme_select.on_value_change(on_theme_change)

            ui.label("Light").classes("text-white text-xs")
            dark_switch = ui.switch("", value=config.dark_mode).props("dark color=grey-4 dense")
            ui.label("Dark").classes("text-white text-xs")

            def on_dark_change(e):
                dark.set_value(e.value)
                config.dark_mode = e.value
                config.save()

            dark_switch.on_value_change(on_dark_change)

            async def confirm_exit():
                with ui.dialog() as dlg, ui.card().classes("q-pa-lg"):
                    ui.label("Exit Application?").classes("text-base font-semibold")
                    ui.label("All unsaved questions will be lost.").classes("muted text-xs q-mt-xs")
                    with ui.row().classes("q-mt-md gap-2 justify-end"):
                        ui.button("Cancel", on_click=dlg.close).props("flat dense")

                        async def do_exit():
                            dlg.close()
                            config.save()
                            # Replace page with goodbye screen and try to close tab
                            await ui.run_javascript("""
                                document.open();
                                document.write(`<html><head><style>
                                    body{margin:0;display:flex;justify-content:center;
                                         align-items:center;height:100vh;
                                         background:#1e1e2e;font-family:sans-serif;color:#94a3b8;}
                                    h2{color:#e2e8f0;margin-bottom:8px;}
                                </style></head><body>
                                    <div style="text-align:center">
                                        <h2>Application closed</h2>
                                        <p>You can close this tab.</p>
                                    </div>
                                </body></html>`);
                                document.close();
                                setTimeout(function(){ window.close(); }, 1000);
                            """)
                            await asyncio.sleep(1.0)
                            app.shutdown()
                            # Force-kill so the console window closes and port is released
                            os._exit(0)

                        ui.button("Exit", on_click=do_exit, icon="power_settings_new").props("color=red dense")
                dlg.open()

            def toggle_fit_to_screen():
                ui.run_javascript("""
                    document.body.classList.toggle('fit-to-screen');
                """)

            ui.button("Fit", icon="fit_screen", on_click=toggle_fit_to_screen).props(
                "dense flat dark size=sm"
            ).classes("text-white").tooltip("Toggle fit-to-screen layout")

            ui.button(icon="power_settings_new", on_click=confirm_exit).props(
                "dense flat dark size=sm"
            ).classes("text-white").tooltip("Exit application")

    return dark
