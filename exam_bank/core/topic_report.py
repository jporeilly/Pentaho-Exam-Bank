"""Where candidates go wrong: wrong answers by topic and by module.

Built from the same `responses` rows as the item analysis, so it honours the
same filters (the caller passes the attempt ids they let through). A response
belongs to the topic the BANK holds for its question (`responses.question_id`
joined to the question), because the results Sheet carries no topic of its
own. A module is read from the question id's `-m<N>-` part (`ba-m4-q9` is
module 4), the convention every course pool uses.

Privacy: only counts and question ids are produced; there are no names or
emails in `responses`, and the AI prompt built from this report carries only
what is in it.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Optional

from .item_analysis import MIN_ATTEMPTS, ensure_schema

NO_TOPIC = "(no topic)"
NOT_IN_BANK = "(not in the bank)"
NO_MODULE = "(no module)"
#: Questions named per row, worst first.
WORST_QUESTIONS = 3

_MODULE = re.compile(r"-m(\d+)-", re.IGNORECASE)


def module_of(question_id: str) -> str:
    m = _MODULE.search(question_id or "")
    return f"Module {int(m.group(1))}" if m else NO_MODULE


def _module_sort(label: str) -> int:
    m = re.search(r"\d+", label)
    return int(m.group()) if m else 10 ** 6


def _row(label: str, course_id: str, course: str, stats: dict[str, Any], total_wrong: int) -> dict[str, Any]:
    answers, wrong = stats["answers"], stats["wrong"]
    worst = sorted(stats["by_question"].items(), key=lambda kv: (-kv[1][1], -kv[1][0], kv[0]))
    worst = [{"id": qid, "answers": a, "wrong": w, "wrongRate": round(w / a, 3) if a else None,
              "stem": stats["stems"].get(qid, "")}
             for qid, (a, w) in worst if w > 0][:WORST_QUESTIONS]
    return {
        "label": label,
        "courseId": course_id,
        "course": course,
        "questions": len(stats["by_question"]),
        "answers": answers,
        "wrong": wrong,
        "wrongRate": round(wrong / answers, 3) if answers else None,
        "shareOfWrong": round(wrong / total_wrong, 3) if total_wrong else 0,
        "thin": answers < MIN_ATTEMPTS,
        "worstQuestions": worst,
    }


def _blank() -> dict[str, Any]:
    return {"answers": 0, "wrong": 0, "by_question": defaultdict(lambda: [0, 0]), "stems": {}}


def build(db, attempt_ids: Optional[set[str]] = None, course_names: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """Topics and modules ranked by wrong answers, within each course.

    A topic is per course: two courses can use the same topic name, and their
    cohorts are not the same people answering the same questions.
    """
    conn = db.conn
    ensure_schema(conn)
    names = course_names or {}
    certs = {c.source_ref: c for c in db.list_certifications() if getattr(c, "source_ref", "")}
    questions: dict[tuple[str, str], Any] = {}
    for course_id, cert in certs.items():
        for q in db.search(certification_id=cert.id, limit=100000):
            questions[(course_id, q.id)] = q

    rows = conn.execute("SELECT attempt_id, question_id, course_id, was_correct FROM responses").fetchall()
    if attempt_ids is not None:
        rows = [r for r in rows if r[0] in attempt_ids]

    topics: dict[tuple[str, str], dict[str, Any]] = defaultdict(_blank)
    modules: dict[tuple[str, str], dict[str, Any]] = defaultdict(_blank)
    for attempt_id, qid, course_id, correct in rows:
        q = questions.get((course_id, qid))
        topic = (q.topic.strip() or NO_TOPIC) if q else NOT_IN_BANK
        wrong = 0 if correct else 1
        for table, key in ((topics, (course_id, topic)), (modules, (course_id, module_of(qid)))):
            s = table[key]
            s["answers"] += 1
            s["wrong"] += wrong
            cell = s["by_question"][qid]
            cell[0] += 1
            cell[1] += wrong
            if q and qid not in s["stems"]:
                s["stems"][qid] = q.stem[:160]

    total_wrong = sum(1 for r in rows if not r[3])
    wrong_in: dict[str, int] = defaultdict(int)
    for r in rows:
        wrong_in[r[2]] += 0 if r[3] else 1
    courses: dict[str, dict[str, Any]] = {}
    for kind, table in (("topics", topics), ("modules", modules)):
        for (course_id, label), stats in table.items():
            entry = courses.setdefault(course_id, {
                "courseId": course_id,
                "name": (certs[course_id].name if course_id in certs else None) or names.get(course_id) or course_id,
                "answers": 0, "wrong": 0, "topics": [], "modules": [],
            })
            entry[kind].append(_row(label, course_id, entry["name"], stats, wrong_in[course_id]))
    for course_id, entry in courses.items():
        in_course = [r for r in rows if r[2] == course_id]
        entry["answers"] = len(in_course)
        entry["wrong"] = sum(1 for r in in_course if not r[3])
        entry["wrongRate"] = round(entry["wrong"] / entry["answers"], 3) if entry["answers"] else None
        entry["attempts"] = len({r[0] for r in in_course})
        entry["topics"].sort(key=lambda t: (-t["wrong"], -(t["wrongRate"] or 0), t["label"]))
        entry["modules"].sort(key=lambda m: (-m["wrong"], _module_sort(m["label"]), m["label"]))
    return {
        "minAnswers": MIN_ATTEMPTS,
        "answers": len(rows),
        "wrong": total_wrong,
        "courses": sorted(courses.values(), key=lambda c: c["name"].lower()),
    }
