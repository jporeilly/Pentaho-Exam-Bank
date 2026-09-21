"""CSS styles, theme colors, and UI constants for the Exam Bank app."""

import html as _html
import re as _re

# -- Directory constants -----------------------------------------------------
from ..utils.config import ASSETS_DIR
PPTX_CACHE_DIR = ASSETS_DIR / "pptx"
PPTX_CACHE_DIR.mkdir(parents=True, exist_ok=True)

STATIC_DIR = ASSETS_DIR / "temp"
STATIC_DIR.mkdir(parents=True, exist_ok=True)


THEME_COLORS = {
    "Slate": {"gradient": "linear-gradient(135deg, #334155 0%, #475569 100%)", "primary": "#475569", "quasar": "blue-grey-7"},
    "Blue": {"gradient": "linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%)", "primary": "#2563eb", "quasar": "blue-7"},
    "Indigo": {"gradient": "linear-gradient(135deg, #312e81 0%, #4f46e5 100%)", "primary": "#4f46e5", "quasar": "indigo-7"},
    "Purple": {"gradient": "linear-gradient(135deg, #581c87 0%, #7c3aed 100%)", "primary": "#7c3aed", "quasar": "purple-7"},
    "Teal": {"gradient": "linear-gradient(135deg, #134e4a 0%, #0d9488 100%)", "primary": "#0d9488", "quasar": "teal-7"},
    "Green": {"gradient": "linear-gradient(135deg, #14532d 0%, #16a34a 100%)", "primary": "#16a34a", "quasar": "green-7"},
    "Orange": {"gradient": "linear-gradient(135deg, #7c2d12 0%, #ea580c 100%)", "primary": "#ea580c", "quasar": "orange-7"},
    "Rose": {"gradient": "linear-gradient(135deg, #881337 0%, #e11d48 100%)", "primary": "#e11d48", "quasar": "pink-7"},
}

CUSTOM_CSS = """
<style>
:root {
    --sidebar-width: clamp(260px, 22vw, 380px);
    --base-font: clamp(12px, 0.85vw + 6px, 15px);
}

/* Clean, thin scrollbars */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.15); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: rgba(0,0,0,0.25); }
body.body--dark ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); }
body.body--dark ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.25); }
* { scrollbar-width: thin; scrollbar-color: rgba(0,0,0,0.15) transparent; }
body.body--dark * { scrollbar-color: rgba(255,255,255,0.15) transparent; }

/* Cards — rounded, subtle shadow, hover lift */
.nicegui-card {
    border-radius: 10px !important;
    border: 1px solid rgba(0,0,0,0.06) !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
    transition: box-shadow 0.2s ease !important;
}
.nicegui-card:hover {
    box-shadow: 0 3px 10px rgba(0,0,0,0.07) !important;
}
body.body--dark .nicegui-card {
    border-color: rgba(255,255,255,0.08) !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.3) !important;
}
body.body--dark .nicegui-card:hover {
    box-shadow: 0 3px 10px rgba(0,0,0,0.4) !important;
}

/* Header — gradient background */
.app-header {
    background: var(--theme-gradient, linear-gradient(135deg, #334155 0%, #475569 100%)) !important;
    min-height: 52px !important;
    padding: 0 16px !important;
}

/* Sidebar */
.sidebar {
    width: var(--sidebar-width);
    min-width: 220px;
    max-width: 400px;
    flex-shrink: 0;
    height: calc(100dvh - 52px);
    overflow-y: auto;
    overflow-x: hidden;
    border-right: 1px solid rgba(0,0,0,0.08);
    background: #fafbfc;
}
body.body--dark .sidebar {
    background: #1a1a2e;
    border-right-color: rgba(255,255,255,0.06);
}

/* Main content panel */
.main-content {
    flex: 1;
    min-width: 0;
    height: calc(100dvh - 52px);
    overflow-y: auto;
    overflow-x: hidden;
    background: #f5f6f8;
}
body.body--dark .main-content {
    background: #121220;
}

/* Two-panel layout (sidebar + main) */
.two-panel {
    display: flex;
    flex-wrap: nowrap;
}

/* Section labels */
.section-title {
    font-size: 0.85rem !important;
    font-weight: 700 !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #64748b;
}
body.body--dark .section-title { color: #94a3b8 !important; }

/* Theme-aware accents */
.q-tab--active { color: var(--theme-primary, #475569) !important; }
.q-tab__indicator { background: var(--theme-primary, #475569) !important; }
.q-linear-progress__track { background: color-mix(in srgb, var(--theme-primary, #475569) 15%, transparent) !important; }
.q-linear-progress__model { background: var(--theme-primary, #475569) !important; }
.q-badge--outline { color: var(--theme-primary, #475569) !important; border-color: var(--theme-primary, #475569) !important; }
.themed-icon { color: var(--theme-primary, #475569) !important; }
.q-linear-progress { border-radius: 6px !important; overflow: hidden !important; }

/* File rows */
.file-row {
    border-radius: 6px;
    padding: 6px 10px;
    transition: background 0.15s ease;
    border: 1px solid transparent;
    cursor: pointer;
    width: 100%;
    box-sizing: border-box;
}
.file-row:hover { background: #e8edf2; border-color: #d1d9e0; }
body.body--dark .file-row:hover { background: #1e293b; border-color: #334155; }
.file-row-selected {
    background: color-mix(in srgb, var(--theme-primary, #475569) 12%, white) !important;
    border-color: color-mix(in srgb, var(--theme-primary, #475569) 50%, white) !important;
}
body.body--dark .file-row-selected {
    background: color-mix(in srgb, var(--theme-primary, #475569) 25%, black) !important;
    border-color: var(--theme-primary, #475569) !important;
}

/* Drop area for file upload */
.drop-area {
    border: 2px dashed color-mix(in srgb, var(--theme-primary, #475569) 40%, transparent) !important;
    border-radius: 8px !important;
    background: color-mix(in srgb, var(--theme-primary, #475569) 4%, transparent) !important;
    min-height: 48px !important;
    transition: border-color 0.2s, background 0.2s;
}
.drop-area .q-uploader__header {
    background: transparent !important;
    color: var(--theme-primary, #475569) !important;
    border-bottom: none !important;
    min-height: 36px !important;
    padding: 4px 8px !important;
    font-size: 13px;
}
.drop-area .q-uploader__header .q-btn { display: none !important; }
.drop-area .q-uploader__list { display: none !important; }
.drop-area:hover, .drop-area.q-uploader--drag-over {
    border-color: var(--theme-primary, #475569) !important;
    background: color-mix(in srgb, var(--theme-primary, #475569) 10%, transparent) !important;
}
body.body--dark .drop-area {
    border-color: color-mix(in srgb, var(--theme-primary, #475569) 30%, transparent) !important;
    background: color-mix(in srgb, var(--theme-primary, #475569) 6%, transparent) !important;
}

/* Slide preview image */
.slide-preview-img {
    max-height: min(420px, 45dvh);
    width: 100%;
    object-fit: contain;
    border-radius: 8px;
    border: 1px solid rgba(0,0,0,0.1);
    background: #000;
}
body.body--dark .slide-preview-img { border-color: rgba(255,255,255,0.1); }

/* Question card styling */
.question-card {
    border-left: 4px solid var(--theme-primary, #4f46e5);
    transition: border-color 0.2s;
}
.question-card:hover { border-left-color: color-mix(in srgb, var(--theme-primary, #4f46e5) 70%, white); }
.question-card.status-draft { border-left-color: #f59e0b; }
.question-card.status-sme_review { border-left-color: #3b82f6; }
.question-card.status-revised { border-left-color: #06b6d4; }
.question-card.status-approved { border-left-color: #10b981; }
.question-card.status-rejected { border-left-color: #ef4444; }
.question-card.status-retired { border-left-color: #6b7280; }

/* Compact table rows */
.bank-table .q-td { padding: 4px 8px !important; }

/* Badge colors */
.badge-easy { background: #10b981 !important; }
.badge-medium { background: #f59e0b !important; }
.badge-hard { background: #ef4444 !important; }
.badge-draft { background: #f59e0b !important; }
.badge-sme_review { background: #3b82f6 !important; }
.badge-revised { background: #06b6d4 !important; }
.badge-approved { background: #10b981 !important; }
.badge-rejected { background: #ef4444 !important; }
.badge-retired { background: #6b7280 !important; }

/* Validation warning */
.validation-warning { color: #d97706; font-size: 0.85em; }

/* Muted text */
.muted { color: #64748b !important; }
body.body--dark .muted { color: #94a3b8 !important; }

/* Responsive typography */
.section-title { font-size: clamp(0.7rem, 0.8vw + 0.3rem, 0.85rem) !important; }
.text-xs, .muted { font-size: clamp(10px, 0.7vw + 5px, 13px) !important; }
.text-sm { font-size: clamp(12px, 0.75vw + 6px, 14px) !important; }

/* Medium screens */
@media (max-width: 1400px) {
    :root { --sidebar-width: clamp(240px, 20vw, 340px); }
}
/* Smaller screens */
@media (max-width: 1100px) {
    :root { --sidebar-width: clamp(220px, 18vw, 300px); }
    .nicegui-card { padding: 10px !important; }
}
/* Responsive flex helpers — rows that auto-wrap on narrow viewports */
.q-row, .nicegui-row { flex-wrap: wrap !important; }
.q-select { min-width: 0 !important; }
/* Prevent cards and inputs from overflowing their container */
.q-card, .q-input, .q-select, .q-field { max-width: 100%; box-sizing: border-box; }
/* Badges wrap gracefully */
.q-badge { white-space: nowrap; }
/* Chat bubbles for Docs Chat */
.chat-bubble-user {
    background: color-mix(in srgb, var(--theme-primary, #475569) 15%, white) !important;
    border-radius: 12px 12px 4px 12px !important;
}
body.body--dark .chat-bubble-user {
    background: color-mix(in srgb, var(--theme-primary, #475569) 30%, black) !important;
}
.chat-bubble-assistant {
    background: #f1f5f9 !important;
    border-radius: 12px 12px 12px 4px !important;
}
body.body--dark .chat-bubble-assistant {
    background: #1e293b !important;
}

/* Stack on narrow screens */
@media (max-width: 900px) {
    .sidebar {
        width: 100% !important; min-width: 100% !important; max-width: 100% !important;
        height: auto !important; max-height: 40vh;
        border-right: none !important;
        border-bottom: 1px solid rgba(0,0,0,0.08);
    }
    .main-content { height: auto !important; min-height: 40vh; }
    .two-panel { flex-direction: column !important; }
}

/* ── Explanation formatting ──────────────────────────── */
.expl-container { display: flex; flex-direction: column; gap: 4px; }
.expl-row {
    padding: 8px 14px; border-radius: 8px; font-size: 0.85rem;
    line-height: 1.6; transition: background 0.15s;
}
.expl-correct {
    background: #ecfdf5; border-left: 4px solid #10b981;
}
.expl-incorrect {
    background: #fef2f2; border-left: 4px solid #ef4444;
}
.expl-neutral {
    padding: 6px 14px; color: #4b5563;
}
.expl-choice-correct { font-weight: 600; color: #059669; }
.expl-reason-correct { color: #065f46; }
.expl-choice-incorrect { font-weight: 600; color: #dc2626; }
.expl-reason-incorrect { color: #7f1d1d; }
body.body--dark .expl-correct { background: #064e3b; }
body.body--dark .expl-incorrect { background: #450a0a; }
body.body--dark .expl-neutral { color: #9ca3af; }
body.body--dark .expl-choice-correct { color: #34d399; }
body.body--dark .expl-reason-correct { color: #a7f3d0; }
body.body--dark .expl-choice-incorrect { color: #fca5a5; }
body.body--dark .expl-reason-incorrect { color: #fecaca; }

/* ── Fit-to-screen mode ──────────────────────────────── */
body.fit-to-screen .sidebar {
    width: clamp(180px, 14vw, 280px) !important;
    min-width: 160px !important;
}
body.fit-to-screen .main-content {
    flex: 1 1 0% !important;
    min-width: 0;
}
body.fit-to-screen .slide-preview-img {
    max-height: 78dvh !important;
}
body.fit-to-screen .nicegui-card {
    padding: 8px !important;
}
body.fit-to-screen .section-title {
    font-size: clamp(0.6rem, 0.7vw + 0.2rem, 0.8rem) !important;
}
body.fit-to-screen .q-tab-panels {
    max-height: calc(100dvh - 52px) !important;
    overflow-y: auto;
}
body.fit-to-screen .q-pa-md {
    padding: 8px !important;
}
body.fit-to-screen .q-gutter-sm > * {
    margin: 4px !important;
}

/* ── Mermaid diagram styling ──────────────────────── */
.mermaid-container {
    width: 100%;
    min-height: 200px;
    padding: 16px;
    border-radius: 10px;
    background: #f8fafc;
    border: 1px solid rgba(0,0,0,0.06);
    overflow-x: auto;
}
body.body--dark .mermaid-container {
    background: #1e293b;
    border-color: rgba(255,255,255,0.08);
}
.mermaid-container .nicegui-mermaid {
    width: 100%;
    min-height: 180px;
}
.mermaid-container .nicegui-mermaid svg {
    width: 100% !important;
    max-width: 100%;
    height: auto !important;
    min-height: 180px;
    font-family: 'Segoe UI', system-ui, sans-serif !important;
}
/* Mermaid node styling overrides for a cleaner look */
.mermaid-container .node rect,
.mermaid-container .node circle,
.mermaid-container .node polygon {
    rx: 8px;
    ry: 8px;
    stroke-width: 2px;
}
.mermaid-container .edgeLabel {
    font-size: 12px !important;
}
</style>
"""

def _split_explanation_line(safe: str, keyword: str) -> tuple:
    """Split an explanation line into (choice_text, rest) around the Correct/Incorrect separator.

    Handles both quoted ('choice' — Correct:) and unquoted (choice text — Correct:) patterns.
    Returns ("", "") if no split point found.
    """
    # Try quoted first: 'choice text' — Correct: ...
    m = _re.match(r"^['\u2018\u201c\"](.+?)['\u2019\u201d\"](.*)$", safe)
    if m:
        return m.group(1), m.group(2)
    # Try unquoted: split on the separator before Correct/Incorrect
    # Matches: " — Correct", " -- Correct", " - Correct"
    pat = _re.compile(
        r"^(.+?)\s*(?:\u2014|—|--)\s*(?=" + keyword + r")",
        _re.IGNORECASE,
    )
    m = pat.match(safe)
    if m:
        choice = m.group(1).strip()
        rest = safe[m.end():]
        return choice, f" \u2014 {rest}"
    return "", ""


def format_explanation_html(text: str) -> str:
    """Convert explanation text into styled HTML with colour-coded correct/incorrect answers.

    Supports both light and dark mode via CSS classes.
    Used by import_tab and question_editor for consistent explanation display.
    """
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    parts: list[str] = []
    for line in lines:
        safe = _html.escape(line)
        # Check Incorrect FIRST — "- Correct" is a substring of "- Incorrect"
        is_incorrect = any(k in safe for k in (
            "\u2014 Incorrect", "\u2014 incorrect",
            "— Incorrect", "— incorrect",
            "-- Incorrect", "-- incorrect",
            "- Incorrect", "- incorrect",
            "Incorrect:", "incorrect:",
        ))
        is_correct = not is_incorrect and any(k in safe for k in (
            "\u2014 Correct", "\u2014 correct",
            "— Correct", "— correct",
            "-- Correct", "-- correct",
            "- Correct", "- correct",
            "Correct:", "correct:",
        ))
        if is_correct:
            choice, reason = _split_explanation_line(safe, "correct")
            if choice:
                reason = _re.sub(r"([Cc]orrect:?)", r"<b>\1</b>", reason, count=1)
                inner = (f"<span class='expl-choice-correct'>\u2713 {choice}</span>"
                         f"<span class='expl-reason-correct'>{reason}</span>")
            else:
                inner = _re.sub(r"([Cc]orrect:?)", r"<b>\1</b>", safe, count=1)
            parts.append(f"<div class='expl-row expl-correct'>{inner}</div>")
        elif is_incorrect:
            choice, reason = _split_explanation_line(safe, "incorrect")
            if choice:
                reason = _re.sub(r"([Ii]ncorrect:?)", r"<b>\1</b>", reason, count=1)
                inner = (f"<span class='expl-choice-incorrect'>\u2717 {choice}</span>"
                         f"<span class='expl-reason-incorrect'>{reason}</span>")
            else:
                inner = _re.sub(r"([Ii]ncorrect:?)", r"<b>\1</b>", safe, count=1)
            parts.append(f"<div class='expl-row expl-incorrect'>{inner}</div>")
        else:
            parts.append(f"<div class='expl-row expl-neutral'>{safe}</div>")
    return f"<div class='expl-container'>{''.join(parts)}</div>"


THEME_APPLY_JS = """
<script>
function applyTheme(gradient, primary) {
    document.documentElement.style.setProperty('--theme-gradient', gradient);
    document.documentElement.style.setProperty('--theme-primary', primary);
    if (window.Quasar) Quasar.setCssVar('primary', primary);
}
</script>
"""

MERMAID_INIT_JS = """
<script>
// Auto-configure Mermaid theme based on dark/light mode
document.addEventListener('DOMContentLoaded', function() {
    if (window.mermaid) {
        var isDark = document.body.classList.contains('body--dark');
        window.mermaid.initialize({
            startOnLoad: false,
            theme: isDark ? 'dark' : 'default',
            themeVariables: isDark ? {
                primaryColor: '#475569',
                primaryBorderColor: '#64748b',
                primaryTextColor: '#e2e8f0',
                lineColor: '#64748b',
                secondaryColor: '#334155',
                tertiaryColor: '#1e293b',
                fontSize: '14px',
            } : {
                primaryColor: '#e2e8f0',
                primaryBorderColor: '#94a3b8',
                primaryTextColor: '#1e293b',
                lineColor: '#475569',
                secondaryColor: '#f1f5f9',
                tertiaryColor: '#f8fafc',
                fontSize: '14px',
            },
            flowchart: { curve: 'basis', padding: 16 },
            sequence: { mirrorActors: false },
        });
    }
});
// Re-init mermaid when dark mode toggles
var _mermaidObserver = new MutationObserver(function(mutations) {
    mutations.forEach(function(m) {
        if (m.attributeName === 'class' && window.mermaid) {
            var isDark = document.body.classList.contains('body--dark');
            window.mermaid.initialize({
                startOnLoad: false,
                theme: isDark ? 'dark' : 'default',
            });
        }
    });
});
_mermaidObserver.observe(document.body, { attributes: true, attributeFilter: ['class'] });
</script>
"""
