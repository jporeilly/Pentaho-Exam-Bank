"""An AI-written reading of the wrong-answers-by-topic report.

The model is given the report's numbers and nothing else: topic and module
labels, answer and wrong counts, and the worst few questions' ids and stems.
No candidate data of any kind is in it (none is stored). It is told to cite
only what it was given, and the reply is checked against the report: a
suggestion about a topic or question the report does not contain is dropped,
because a plausible-sounding recommendation about the wrong thing is worse
than none.
"""
from __future__ import annotations

import json
from typing import Any

from . import providers
from .generation_parsing import _extract_json_object

#: Topics sent per course, worst first; the rest add tokens and no insight.
MAX_TOPICS = 12
SYSTEM = (
    "You are an assessment analyst reviewing certification exam results for an "
    "exam author. You use only the numbers you are given."
)


def compact(report: dict[str, Any]) -> dict[str, Any]:
    """The report cut down to what the model needs."""
    courses = []
    for c in report["courses"]:
        def rows(items, n):
            return [{
                "label": r["label"], "answers": r["answers"], "wrong": r["wrong"],
                "wrongRate": r["wrongRate"], "enoughAnswers": not r["thin"],
                "worstQuestions": [{"id": q["id"], "answers": q["answers"], "wrong": q["wrong"],
                                    "stem": q["stem"]} for q in r["worstQuestions"]],
            } for r in items[:n]]
        courses.append({
            "course": c["name"], "attempts": c["attempts"], "answers": c["answers"], "wrong": c["wrong"],
            "wrongRate": c["wrongRate"],
            "topics": rows(c["topics"], MAX_TOPICS), "modules": rows(c["modules"], MAX_TOPICS),
        })
    return {"minAnswersToJudge": report["minAnswers"], "courses": courses}


def build_prompt(report: dict[str, Any]) -> str:
    return f"""Below is a report of wrong answers on certification exams, by topic and by module,
for one or more courses. "wrong" counts wrong answers given; "wrongRate" is wrong / answers.
A row with enoughAnswers=false has too few answers to judge: say so rather than draw conclusions.

REPORT (JSON):
{json.dumps(compact(report), indent=1)}

Write for the exam author. Identify which topics and questions most need attention and
what to do about each (for example: the lesson may under-teach it, the question may be
ambiguous or mis-keyed, the topic may be genuinely hard and need more practice material).
Use ONLY the numbers and names above. Do not invent figures, topics or question ids. If the
report shows nothing unusual, say so plainly. Do not mention candidates individually.

Return ONLY a JSON object:
{{"summary": "2-4 sentences on the overall picture",
  "suggestions": [{{"course": "<course name as given>", "topic": "<topic or module label as given>",
                   "questionIds": ["<ids from the report>"],
                   "priority": "high" | "medium" | "low",
                   "advice": "what to check or change, and why, citing the numbers"}}]}}
At most 8 suggestions, most important first."""


def _known(report: dict[str, Any]) -> tuple[set[tuple[str, str]], set[str]]:
    labels, qids = set(), set()
    for c in report["courses"]:
        for r in [*c["topics"], *c["modules"]]:
            labels.add((c["name"], r["label"]))
            qids.update(q["id"] for q in r["worstQuestions"])
    return labels, qids


def parse_reply(reply: str, report: dict[str, Any]) -> dict[str, Any]:
    obj = _extract_json_object(reply)
    if not obj:
        # Not JSON: keep what was written, unstructured, rather than discard it.
        return {"summary": reply.strip(), "suggestions": [], "dropped": 0}
    labels, qids = _known(report)
    kept, dropped = [], 0
    for raw in obj.get("suggestions") or []:
        if not isinstance(raw, dict):
            continue
        course, topic = str(raw.get("course", "")).strip(), str(raw.get("topic", "")).strip()
        advice = str(raw.get("advice", "")).strip()
        if not advice or (course, topic) not in labels:
            dropped += 1
            continue
        priority = str(raw.get("priority", "")).strip().lower()
        kept.append({
            "course": course, "topic": topic,
            "questionIds": [q for q in (raw.get("questionIds") or []) if isinstance(q, str) and q in qids],
            "priority": priority if priority in ("high", "medium", "low") else "medium",
            "advice": advice,
        })
    return {"summary": str(obj.get("summary", "")).strip(), "suggestions": kept[:8], "dropped": dropped}


def advise(report: dict[str, Any], model: str = "") -> dict[str, Any]:
    """The reading, or ProviderError. Never calls a model with nothing to read."""
    if report["wrong"] == 0:
        return {"summary": "There are no wrong answers in these results, so there is nothing to analyse.",
                "suggestions": [], "dropped": 0, "model": "", "provider": ""}
    provider = providers.active_provider()
    chosen = (model or "").strip() or providers.model_for(provider)
    reply = providers.generate(prompt=build_prompt(report), model=chosen, system=SYSTEM, timeout=180.0)
    return {**parse_reply(reply, report), "model": chosen, "provider": provider}
