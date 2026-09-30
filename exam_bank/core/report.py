"""The bank's Bloom balance, exam by exam, read in one pass.

The Report pane gives each exam the breakdown the exam reviews were done
with: how deep its questions go (Bloom level), how that splits across the
workshops, whether it clears the bar for its certification level, where every
question sits in review, and a short list of findings generated from those
numbers. Everything is a count over what the bank holds plus two facts only the
course files know — the course's `level` and the exam's draw size. Nothing is
written.

It is one read rather than the `get_*_counts` helpers because the pane needs
the same numbers at three grains (the bank, an exam, a workshop) and they have
to agree. Counting each grain with its own query would let them disagree the
moment a question is saved between two of them.

Two orders matter and neither is invented here:

- Questions come back in **course order** — `search(sort="course")`, the order
  the pool was authored in, which is the order the workshops teach it.
- Workshops (topics) inside an exam come from `get_topics`, which ranks them by
  the earliest pool position any of their questions holds — the same order the
  exam-paper pane uses.

A Bloom level the bank does not recognise (anything outside ``BLOOM_LEVELS``,
such as a lower-case ``apply`` written by an importer that did not validate) is
counted as ``unknownBloom`` rather than dropped. A question that silently
vanished from every bar would make the totals disagree with the bank's size.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Optional

from .bank import BLOOM_LEVELS, STATUS_LABELS, STATUSES, ExamBankDB, Question
from .pcm_reader import read_course_json

#: Apply or above: at or above it a question asks the candidate to USE what
#: they know; below it, to recall or restate it.
APPLY_PLUS = frozenset({"Apply", "Analyze", "Evaluate", "Create"})
ANALYZE_PLUS = frozenset({"Analyze", "Evaluate", "Create"})

#: The bar each certification level's exam is reviewed against — floors on
#: Apply+, Analyze+ and Evaluate, and a CEILING on recall (Remember), all as a
#: percentage of the exam's questions. The ceiling matters: a respectable
#: Apply+ can sit on top of an exam that is half recall, and only the ceiling
#: catches that.
#:
#: These are the figures the 2026-09 exam review applied (PCM 0.5.0 records
#: them in its CHANGELOG). They follow the usual shape of a certification
#: ladder but are a working standard, not an accredited one — an accredited
#: blueprint derives its numbers from a job-task analysis of the role. Change
#: them here and every exam is re-judged; they are defined nowhere else.
BARS: dict[int, dict[str, Any]] = {
    1: {"name": "Practitioner", "applyPlus": 50, "analyzePlus": 15, "evaluate": 1, "recall": 30},
    2: {"name": "Specialty", "applyPlus": 60, "analyzePlus": 30, "evaluate": 5, "recall": 20},
    3: {"name": "Certified", "applyPlus": 70, "analyzePlus": 40, "evaluate": 15, "recall": 15},
}

#: Label for questions that belong to no certification — authored in the bank
#: and never filed. They are real questions and are counted, just not under an
#: exam that does not exist.
UNFILED = "Not in a course"


def _pct(part: int, whole: int) -> int:
    return round(part * 100 / whole) if whole else 0


def _summary(questions: Iterable[Question]) -> dict[str, Any]:
    """Counts for one set of questions. Every level and status is present,
    zero or not, so a client can draw a fixed scale without guessing keys."""
    by_bloom = {level: 0 for level in BLOOM_LEVELS}
    by_status = {status: 0 for status in STATUSES}
    total = unknown = apply_plus = analyze_plus = scenario_led = multi = thin = 0

    for q in questions:
        total += 1
        if q.bloom_level in by_bloom:
            by_bloom[q.bloom_level] += 1
        else:
            unknown += 1
        if q.bloom_level in APPLY_PLUS:
            apply_plus += 1
        if q.bloom_level in ANALYZE_PLUS:
            analyze_plus += 1
        if (q.scenario or "").strip():
            scenario_led += 1
        if q.question_type == "multi":
            multi += 1
        # Fewer than two wrong answers to choose between. Almost always a
        # select-all where most of the options are correct.
        if len([d for d in (q.distractors or []) if str(d).strip()]) < 2:
            thin += 1
        # A status outside the lifecycle cannot be written through the model,
        # but a row edited by hand could carry one; count it rather than lose it.
        by_status[q.status] = by_status.get(q.status, 0) + 1

    return {
        "questions": total,
        "byBloom": by_bloom,
        "unknownBloom": unknown,
        "applyPlus": apply_plus,
        "analyzePlus": analyze_plus,
        "recall": by_bloom["Remember"],
        "evaluate": by_bloom["Evaluate"],
        "scenarioLed": scenario_led,
        "multi": multi,
        "thin": thin,
        "byStatus": by_status,
    }


def _read_json(path: Path) -> Optional[dict]:
    try:
        data = read_course_json(path)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _course_facts(courses_dir: Optional[Path], slug: str) -> tuple[Optional[dict], Optional[dict]]:
    """The course's `level` and its exam's draw, from the course files.

    Both are optional and both are genuinely absent sometimes: `pdi-2hr-lab`
    carries no level on purpose (a try-it lab is not a rung), and a bank with
    no courses directory configured cannot know either. Absent is reported as
    None, never guessed from the slug.
    """
    if not courses_dir or not slug:
        return None, None
    course_dir = courses_dir / slug

    level = None
    course = _read_json(course_dir / "course.json")
    raw = (course or {}).get("level")
    if isinstance(raw, dict) and isinstance(raw.get("number"), int):
        level = {"number": raw["number"], "name": str(raw.get("name") or "")}

    exam = None
    data = _read_json(course_dir / "exam.json")
    if data is not None:
        pool = len([q for q in data.get("questions", []) if isinstance(q, dict)])
        draw = data.get("questionsPerAttempt")
        draw = draw if isinstance(draw, int) and draw > 0 else pool
        exam = {
            "pool": pool,
            "draw": min(draw, pool) if pool else draw,
            "passMark": data.get("passMark") if isinstance(data.get("passMark"), int) else None,
        }
    return level, exam


def _bar_check(summary: dict, level: Optional[dict]) -> Optional[dict]:
    """The four criteria for the exam's level, each with its gap in QUESTIONS.

    "Four more Apply questions" is something an author can sit down and write;
    "six percentage points" is not. Integer arithmetic throughout so a result
    exactly on the line cannot flip on floating-point noise.
    """
    if not level or level["number"] not in BARS:
        return None
    bar = BARS[level["number"]]
    n = summary["questions"]

    def floor_rule(key: str, got: int, pct: int) -> dict:
        need = -(-n * pct // 100)  # ceiling of n*pct/100
        return {"criterion": key, "kind": "floor", "got": got, "percent": _pct(got, n),
                "bar": pct, "ok": got * 100 >= pct * n, "gap": max(0, need - got)}

    def ceiling_rule(key: str, got: int, pct: int) -> dict:
        allowed = n * pct // 100
        return {"criterion": key, "kind": "ceiling", "got": got, "percent": _pct(got, n),
                "bar": pct, "ok": got * 100 <= pct * n, "gap": max(0, got - allowed)}

    criteria = [
        floor_rule("Apply+", summary["applyPlus"], bar["applyPlus"]),
        floor_rule("Analyze+", summary["analyzePlus"], bar["analyzePlus"]),
        floor_rule("Evaluate", summary["evaluate"], bar["evaluate"]),
        ceiling_rule("Recall", summary["recall"], bar["recall"]),
    ]
    return {
        "level": level["number"],
        "name": bar["name"],
        "criteria": criteria,
        "clears": n > 0 and all(c["ok"] for c in criteria),
    }


def _findings(summary: dict, level: Optional[dict], exam: Optional[dict],
              bar: Optional[dict]) -> list[dict]:
    """What the numbers say to do, by the same rules for every exam.

    A finding appears only where its numbers trigger it and disappears once
    they no longer do, so the list is a to-do, not commentary. Severity:
    ``act``, ``review``, ``minor``, ``note`` (information only), ``clear``.
    """
    out: list[dict] = []
    n = summary["questions"]
    if n == 0:
        return out
    sc = _pct(summary["scenarioLed"], n)

    if exam and exam["pool"] and exam["draw"] >= exam["pool"]:
        out.append({
            "severity": "act", "title": "No draw headroom",
            "detail": f"Every candidate sits all {exam['pool']} questions, so two candidates "
                      "get an identical paper and one sitting exposes the whole pool.",
            "action": "Grow the pool, then set questionsPerAttempt below it. Drawing 20 of 30 "
                      "gives 33% headroom.",
        })

    if bar and not bar["clears"]:
        missed = [c for c in bar["criteria"] if not c["ok"]]
        parts = []
        for c in missed:
            if c["kind"] == "floor":
                parts.append(f"{c['criterion']} {c['percent']}% against {c['bar']}%, "
                             f"{c['gap']} question{'s' if c['gap'] != 1 else ''} short")
            else:
                parts.append(f"{c['criterion']} {c['percent']}% against a {c['bar']}% ceiling, "
                             f"{c['gap']} too many")
        both = {"Apply+", "Recall"} <= {c["criterion"] for c in missed}
        out.append({
            "severity": "act" if len(missed) >= 3 else "review",
            "title": f"Misses the Level {bar['level']} {bar['name']} bar on {len(missed)} of 4",
            "detail": "; ".join(parts) + ".",
            "action": ("Rewrite recall questions upward: each one moved off Remember raises "
                       "Apply+ and lowers recall in the same edit, so both gaps close together."
                       if both else "Close the largest gap first."),
        })

    # Every question sets a scenario: one to three sentences of real context
    # that the question then asks about. That is the house item-writing
    # standard, so the check is simply whether any question lacks one.
    #
    # It replaced two gap rules comparing scenario coverage with Apply+ in
    # either direction. Those were written when scenarios were optional, and
    # one of them - "scenarios that do no work", scenario share well above
    # Apply+ - fired on every exam that followed the standard, since an
    # Understand question with a scenario is correct, not decoration.
    missing = n - summary["scenarioLed"]
    if missing:
        out.append({
            "severity": "review",
            "title": f"{missing} question{'s' if missing != 1 else ''} without a scenario",
            "detail": f"{sc}% of questions set a scenario. Every question should: one to three "
                      "sentences of real working context that the question then asks about, "
                      "never a reference to the course itself.",
            "action": "Write a scenario for each and keep the prompt to the question alone. The "
                      "question list's Scen. column shows which ones.",
        })

    if summary["thin"]:
        t = summary["thin"]
        out.append({
            "severity": "minor",
            "title": f"{t} question{'s' if t != 1 else ''} with thin distractors",
            "detail": "Fewer than two wrong answers to choose between, almost always a "
                      "select-all where most options are correct.",
            "action": "Add a plausible wrong option.",
        })

    if summary["unknownBloom"]:
        u = summary["unknownBloom"]
        out.append({
            "severity": "review",
            "title": f"{u} question{'s' if u != 1 else ''} with an unrecognised Bloom level",
            "detail": "Counted in the total but in no level, so the bar check cannot see them.",
            "action": "Open them in the Bank and set a level from the list.",
        })

    if bar is None:
        out.append({
            "severity": "note", "title": "Not scored against a certification bar",
            "detail": ("The course states no level, so there is no bar to measure against."
                       if level is None else
                       f"Level {level['number']} has no bar defined."),
            "action": "Nothing to do unless the course is given a level.",
        })

    if not out:
        out.append({
            "severity": "clear", "title": f"Clears the Level {bar['level']} {bar['name']} bar",
            "detail": "All four criteria pass, and so do draw headroom, scenario coverage "
                      "and distractors.",
            "action": "Leave it alone.",
        })
    return out


def build_report(db: ExamBankDB, courses_dir: Optional[Path] = None) -> dict[str, Any]:
    """Everything the Report pane draws, from one read of the bank.

    ``courses_dir`` is the Content Manager courses directory, for the level and
    draw that only the course files hold. None when it is not configured: the
    report still works, without the bar check and draw headroom.
    """
    total = db.count()
    questions = db.search(limit=max(total, 1), sort="course") if total else []

    certs = {c.id: c for c in db.list_certifications()}
    groups: dict[str, list[Question]] = {}
    for q in questions:
        key = q.certification_id if q.certification_id in certs else ""
        groups.setdefault(key, []).append(q)

    # Exams in the order the course sort produced them; unfiled last.
    order = [k for k in groups if k] + ([""] if "" in groups else [])

    exams = []
    for cert_id in order:
        members = groups[cert_id]
        cert = certs.get(cert_id)
        slug = cert.source_ref if cert and cert.source_type == "pcm" else ""
        level, exam = _course_facts(courses_dir, slug)
        summary = _summary(members)
        bar = _bar_check(summary, level)

        topic_order = db.get_topics(cert_id) if cert_id else []
        by_topic: dict[str, list[Question]] = {}
        for q in members:
            by_topic.setdefault(q.topic or "", []).append(q)
        # Topics the ranking knows, in its order; then any it does not (an
        # empty topic, which get_topics excludes) so none is lost.
        ranked = [t for t in topic_order if t in by_topic]
        ranked += [t for t in by_topic if t not in ranked]

        exams.append({
            "certificationId": cert_id,
            "name": cert.name if cert else UNFILED,
            "sourceRef": slug,
            "level": level,
            "exam": exam,
            **summary,
            "bar": bar,
            "findings": _findings(summary, level, exam, bar),
            "topics": [{"topic": t, **_summary(by_topic[t])} for t in ranked],
        })

    ordered = [q for cert_id in order for q in groups[cert_id]]
    return {
        "levels": list(BLOOM_LEVELS),
        "statuses": [{"id": s, "label": STATUS_LABELS.get(s, s)} for s in STATUSES],
        "bars": {str(k): v for k, v in BARS.items()},
        "coursesConfigured": courses_dir is not None,
        **_summary(questions),
        "exams": exams,
        # Certifications with nothing in them. Counted rather than listed: they
        # are not wrong, but a row of zeros per course would bury the exams
        # that hold questions.
        "emptyCourses": sum(1 for cid in certs if cid not in groups),
        "items": [
            {
                "id": q.id,
                "certificationId": q.certification_id if q.certification_id in certs else "",
                "topic": q.topic,
                "bloom": q.bloom_level,
                "status": q.status,
                "scenario": bool((q.scenario or "").strip()),
                "multi": q.question_type == "multi",
                "stem": q.stem,
                "poolOrder": q.pool_order,
            }
            for q in ordered
        ],
    }
