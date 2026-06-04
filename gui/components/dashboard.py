"""AI-powered analytics dashboard — charts and LLM-generated insights."""

import threading
from collections import Counter

from nicegui import ui

from ..state import AppState, UIRefs
from ...core.question_bank import (
    BLOOM_LEVELS, DIFFICULTIES, STATUSES, STATUS_LABELS,
)
from ...core import ollama_client
from ...utils.config import config


# ── Colour palettes ──────────────────────────────────────

STATUS_COLORS = {
    "draft": "#9ca3af", "sme_review": "#3b82f6", "revised": "#8b5cf6",
    "approved": "#10b981", "rejected": "#ef4444", "retired": "#6b7280",
}
DIFF_COLORS = {"Easy": "#10b981", "Medium": "#f59e0b", "Hard": "#ef4444"}
BLOOM_COLORS = {
    "Remember": "#60a5fa", "Understand": "#34d399", "Apply": "#fbbf24",
    "Analyze": "#f97316", "Evaluate": "#ef4444", "Create": "#8b5cf6",
}


def build_dashboard(state: AppState, refs: UIRefs):
    """Build the analytics dashboard panel."""

    dashboard_container = ui.column().classes("w-full gap-4")
    _callback_anchor = ui.column().style("display: none;")

    def refresh_dashboard():
        dashboard_container.clear()
        with dashboard_container:
            total = state.db.count()
            if total == 0:
                with ui.column().classes("w-full items-center q-pa-lg gap-2"):
                    ui.icon("analytics", size="48px").classes("text-grey-4")
                    ui.label("No data to display yet").classes("text-base text-grey-5")
                    ui.label(
                        "Generate questions from the Generate tab or import existing ones "
                        "from the Import tab to see analytics here."
                    ).classes("text-xs text-grey-5 text-center")
                return

            # ── Row 1: KPI cards ──────────────────────────
            certs = state.db.list_certifications()
            topics = state.db.get_topics()
            approved = state.db.count(status="approved")
            draft = state.db.count(status="draft")
            review = state.db.count(status="sme_review")

            with ui.row().classes("w-full gap-3 flex-wrap"):
                _kpi_card("Total Questions", total, "quiz", "primary")
                _kpi_card("Approved", approved, "check_circle", "positive")
                _kpi_card("In Review", review, "rate_review", "blue")
                _kpi_card("Drafts", draft, "edit_note", "grey")
                _kpi_card("Certifications", len(certs), "workspace_premium", "blue")
                _kpi_card("Topics", len(topics), "label", "teal")

            # ── Row 2: Charts ─────────────────────────────
            # Fetch all questions for aggregation
            all_qs = state.db.search(limit=10000)

            with ui.row().classes("w-full gap-3"):
                with ui.card().classes("flex-1 q-pa-sm").style("min-width: 300px"):
                    ui.label("Status Distribution").classes("text-sm font-bold q-mb-xs")
                    _status_chart(all_qs)

                with ui.card().classes("flex-1 q-pa-sm").style("min-width: 300px"):
                    ui.label("Difficulty Distribution").classes("text-sm font-bold q-mb-xs")
                    _difficulty_chart(all_qs)

            with ui.row().classes("w-full gap-3"):
                with ui.card().classes("flex-1 q-pa-sm").style("min-width: 300px"):
                    ui.label("Bloom's Taxonomy Levels").classes("text-sm font-bold q-mb-xs")
                    _bloom_chart(all_qs)

                with ui.card().classes("flex-1 q-pa-sm").style("min-width: 300px"):
                    ui.label("Questions per Topic").classes("text-sm font-bold q-mb-xs")
                    _topic_chart(all_qs)

            # ── Row 3: More charts ────────────────────────
            with ui.row().classes("w-full gap-3"):
                with ui.card().classes("flex-1 q-pa-sm").style("min-width: 300px"):
                    ui.label("Questions per Certification").classes("text-sm font-bold q-mb-xs")
                    _cert_chart(all_qs, certs)

                with ui.card().classes("flex-1 q-pa-sm").style("min-width: 300px"):
                    ui.label("Question Type Split").classes("text-sm font-bold q-mb-xs")
                    _type_chart(all_qs)

            # ── Row 4: Quality metrics ────────────────────
            with ui.card().classes("w-full q-pa-sm"):
                ui.label("Quality Metrics").classes("text-sm font-bold q-mb-xs")
                _quality_metrics(all_qs)

            # ── Row 5: AI insights ────────────────────────
            with ui.card().classes("w-full q-pa-sm"):
                ui.label("AI Insights").classes("text-sm font-bold q-mb-xs")
                insights_container = ui.column().classes("w-full")

                has_ai = config.ollama_enabled and config.ollama_model
                if has_ai:
                    ui.button(
                        "Generate AI Insights",
                        icon="auto_awesome",
                        on_click=lambda: _generate_insights(all_qs, insights_container),
                    ).props("color=purple size=sm")
                else:
                    ui.label("Enable Ollama in AI & Docs to get AI-powered insights.").classes(
                        "text-xs text-grey-5 italic"
                    )

    def _kpi_card(label: str, value, icon: str, color: str):
        with ui.card().classes("q-pa-sm").style("min-width: 120px"):
            with ui.row().classes("items-center gap-2"):
                ui.icon(icon, color=color, size="sm")
                ui.label(str(value)).classes(f"text-2xl font-bold text-{color}")
            ui.label(label).classes("text-xs text-grey-6")

    def _status_chart(questions):
        counts = Counter(q.status for q in questions)
        data = []
        for s in STATUSES:
            if counts.get(s, 0) > 0:
                data.append({
                    "value": counts[s],
                    "name": STATUS_LABELS.get(s, s.title()),
                    "itemStyle": {"color": STATUS_COLORS.get(s, "#9ca3af")},
                })
        ui.echart({
            "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
            "series": [{
                "type": "pie",
                "radius": ["40%", "70%"],
                "data": data,
                "label": {"show": True, "fontSize": 11},
                "emphasis": {"itemStyle": {"shadowBlur": 10}},
            }],
        }).style("height: 250px")

    def _difficulty_chart(questions):
        counts = Counter(q.difficulty for q in questions)
        categories = [d for d in DIFFICULTIES if counts.get(d, 0) > 0]
        values = [counts.get(d, 0) for d in categories]
        colors = [DIFF_COLORS.get(d, "#9ca3af") for d in categories]
        ui.echart({
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category", "data": categories},
            "yAxis": {"type": "value"},
            "series": [{
                "type": "bar",
                "data": [{"value": v, "itemStyle": {"color": c}} for v, c in zip(values, colors)],
                "barWidth": "60%",
            }],
        }).style("height: 250px")

    def _bloom_chart(questions):
        counts = Counter(q.bloom_level for q in questions)
        categories = [b for b in BLOOM_LEVELS if counts.get(b, 0) > 0]
        values = [counts.get(b, 0) for b in categories]
        colors = [BLOOM_COLORS.get(b, "#9ca3af") for b in categories]
        ui.echart({
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category", "data": categories, "axisLabel": {"rotate": 30}},
            "yAxis": {"type": "value"},
            "series": [{
                "type": "bar",
                "data": [{"value": v, "itemStyle": {"color": c}} for v, c in zip(values, colors)],
                "barWidth": "50%",
            }],
        }).style("height: 250px")

    def _topic_chart(questions):
        counts = Counter(q.topic or "Uncategorized" for q in questions)
        # Sort by count descending, cap at 15
        sorted_topics = counts.most_common(15)
        categories = [t for t, _ in sorted_topics]
        values = [c for _, c in sorted_topics]
        ui.echart({
            "tooltip": {"trigger": "axis"},
            "grid": {"left": "20%"},
            "yAxis": {"type": "category", "data": list(reversed(categories)), "axisLabel": {"width": 120, "overflow": "truncate"}},
            "xAxis": {"type": "value"},
            "series": [{
                "type": "bar",
                "data": list(reversed(values)),
                "itemStyle": {"color": "#14b8a6"},
                "barWidth": "60%",
            }],
        }).style("height: 300px")

    def _cert_chart(questions, certs):
        cert_map = {c.id: c.name for c in certs}
        counts = Counter(cert_map.get(q.certification_id, "Unassigned") for q in questions)
        sorted_certs = counts.most_common(10)
        categories = [c for c, _ in sorted_certs]
        values = [v for _, v in sorted_certs]
        ui.echart({
            "tooltip": {"trigger": "axis"},
            "grid": {"left": "25%"},
            "yAxis": {"type": "category", "data": list(reversed(categories)), "axisLabel": {"width": 150, "overflow": "truncate"}},
            "xAxis": {"type": "value"},
            "series": [{
                "type": "bar",
                "data": list(reversed(values)),
                "itemStyle": {"color": "#3b82f6"},
                "barWidth": "60%",
            }],
        }).style("height: 250px")

    def _type_chart(questions):
        single = sum(1 for q in questions if q.question_type == "single")
        multi = sum(1 for q in questions if q.question_type == "multi")
        ui.echart({
            "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
            "series": [{
                "type": "pie",
                "radius": ["40%", "70%"],
                "data": [
                    {"value": single, "name": "Single Select", "itemStyle": {"color": "#3b82f6"}},
                    {"value": multi, "name": "Multi-Select", "itemStyle": {"color": "#8b5cf6"}},
                ],
                "label": {"show": True, "fontSize": 11},
            }],
        }).style("height: 250px")

    def _quality_metrics(questions):
        total = len(questions)
        if total == 0:
            return

        has_explanation = sum(1 for q in questions if q.explanation and q.explanation.strip())
        has_source = sum(1 for q in questions if q.key_source_text and q.key_source_text.strip())
        has_scenario = sum(1 for q in questions if q.scenario and q.scenario.strip())
        has_cert = sum(1 for q in questions if q.certification_id)
        has_topic = sum(1 for q in questions if q.topic)

        # Avg choice count
        choice_counts = [q.num_choices for q in questions if q.num_choices > 0]
        avg_choices = sum(choice_counts) / len(choice_counts) if choice_counts else 0

        metrics = [
            ("Has Explanation", has_explanation, total),
            ("Has Source Text", has_source, total),
            ("Has Scenario", has_scenario, total),
            ("Assigned to Cert", has_cert, total),
            ("Has Topic", has_topic, total),
        ]

        with ui.row().classes("w-full gap-4 flex-wrap"):
            for label, count, tot in metrics:
                pct = int(count / tot * 100) if tot else 0
                color = "positive" if pct >= 80 else "warning" if pct >= 50 else "negative"
                with ui.column().classes("items-center gap-0"):
                    ui.label(f"{pct}%").classes(f"text-lg font-bold text-{color}")
                    ui.label(f"{count}/{tot}").classes("text-xs text-grey-6")
                    ui.label(label).classes("text-xs text-grey-7")

            with ui.column().classes("items-center gap-0"):
                ui.label(f"{avg_choices:.1f}").classes("text-lg font-bold text-primary")
                ui.label("avg").classes("text-xs text-grey-6")
                ui.label("Choices/Question").classes("text-xs text-grey-7")

        # Legend
        with ui.row().classes("gap-3 q-mt-xs items-center"):
            ui.label("Colour key:").classes("text-xs text-grey-5")
            ui.badge("80%+", color="positive").classes("text-xs")
            ui.label("good").classes("text-xs text-grey-5")
            ui.badge("50-79%", color="warning").classes("text-xs")
            ui.label("needs work").classes("text-xs text-grey-5")
            ui.badge("<50%", color="negative").classes("text-xs")
            ui.label("low").classes("text-xs text-grey-5")

    def _generate_insights(questions, container):
        """Use Ollama to analyze the question bank and provide insights."""
        container.clear()
        with container:
            ui.spinner("dots", size="lg", color="purple")
            ui.label("Analyzing question bank with AI…").classes("text-sm text-grey-6")

        # Build a concise summary for the LLM
        total = len(questions)
        status_counts = Counter(q.status for q in questions)
        diff_counts = Counter(q.difficulty for q in questions)
        bloom_counts = Counter(q.bloom_level for q in questions)
        topic_counts = Counter(q.topic or "Uncategorized" for q in questions)
        type_counts = Counter(q.question_type for q in questions)
        has_explanation = sum(1 for q in questions if q.explanation and q.explanation.strip())
        has_source = sum(1 for q in questions if q.key_source_text and q.key_source_text.strip())

        summary = f"""Question Bank Summary:
- Total questions: {total}
- Status breakdown: {dict(status_counts)}
- Difficulty breakdown: {dict(diff_counts)}
- Bloom's taxonomy breakdown: {dict(bloom_counts)}
- Question types: {dict(type_counts)}
- Topics ({len(topic_counts)}): {dict(topic_counts.most_common(10))}
- Questions with explanations: {has_explanation}/{total} ({int(has_explanation/total*100)}%)
- Questions with source text: {has_source}/{total} ({int(has_source/total*100)}%)

Bloom's taxonomy ideal distribution for certification exams:
- Remember/Understand: ~20% (foundational)
- Apply/Analyze: ~60% (core competency)
- Evaluate/Create: ~20% (advanced)

Difficulty ideal distribution:
- Easy: ~25%, Medium: ~50%, Hard: ~25%"""

        prompt = f"""Analyze this certification exam question bank and provide actionable insights.

{summary}

Provide your analysis in these sections:
1. **Overall Health** — Is the bank ready for exam generation? What's the approval rate?
2. **Coverage Gaps** — Are any topics under-represented? Any Bloom's levels missing?
3. **Difficulty Balance** — How does the distribution compare to the ideal?
4. **Quality Concerns** — What percentage lack explanations or source text? Impact?
5. **Recommendations** — Top 3-5 specific actions to improve the bank.

Be concise and specific. Use numbers. Focus on actionable advice."""

        def do_generate():
            try:
                return ollama_client.generate(
                    prompt=prompt,
                    model=config.ollama_model,
                    system="You are a certification exam development consultant. Provide data-driven insights about question bank quality and coverage.",
                    base_url=config.ollama_url,
                    timeout=120.0,
                )
            except Exception as e:
                return f"Error generating insights: {e}"

        def on_done(result):
            container.clear()
            with container:
                if result.startswith("Error"):
                    ui.label(result).classes("text-sm text-red")
                else:
                    ui.markdown(result).classes("text-sm")

        def run():
            result = do_generate()
            with _callback_anchor:
                ui.timer(0, lambda: (on_done(result), False), once=True)

        threading.Thread(target=run, daemon=True).start()

    # Return refresh handle so admin tab can call it
    refresh_dashboard()
    return refresh_dashboard
