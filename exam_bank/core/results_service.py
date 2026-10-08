"""The exam results service (the Content Manager's Apps Script), as an admin.

Server grading takes an exam's answer keys out of the course files published
to the PUBLIC Pentaho-Courses repo and keeps them in the results service
instead (docs/EXAM-RESULTS-SETUP.md in the Content Manager, "Server grading").
Two admin actions, both checked against an admin secret the learners never
have:

- ``set_keys``: store one exam's keys, pass mark and level;
- ``export_results``: read back the per-question Detail rows (no emails) for
  item analysis.

The admin secret is read from ``PEB_RESULTS_ADMIN_SECRET`` at call time, like
the provider API keys: the app never stores it, and the UI is told only
whether it is set.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

ENV = "PEB_RESULTS_ADMIN_SECRET"
TIMEOUT_SECS = 90


class ResultsServiceError(Exception):
    """The service could not be reached or refused; the message says why."""


def admin_secret() -> str:
    return (os.environ.get(ENV) or "").strip()


def configured() -> bool:
    return bool(admin_secret())


def _post(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    secret = admin_secret()
    if not secret:
        raise ResultsServiceError(
            f"No admin secret: set the {ENV} environment variable to the ADMIN_SECRET in the "
            "results Apps Script, then restart the Exam Bank."
        )
    if not url.startswith("https://"):
        raise ResultsServiceError(f"The results service URL is not https: {url[:60]}")
    body = json.dumps({**payload, "adminSecret": secret}).encode("utf-8")
    # Apps Script answers a POST with a redirect to script.googleusercontent.com,
    # which urllib follows as a GET - the same thing a browser does.
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECS) as r:
            text = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise ResultsServiceError(f"The results service answered HTTP {e.code}.") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ResultsServiceError(f"The results service could not be reached: {e}") from e
    try:
        answer = json.loads(text)
    except ValueError as e:
        raise ResultsServiceError(
            "The results service did not answer with JSON - is the URL a deployed Apps Script web app?"
        ) from e
    if not answer.get("ok"):
        if answer.get("error") == "unauthorized":
            raise ResultsServiceError(
                f"The results service refused the admin secret. {ENV} must equal the script's "
                "ADMIN_SECRET, and the script must have been redeployed with it (an ADMIN_SECRET "
                "still starting with REPLACE- refuses everything)."
            )
        raise ResultsServiceError(f"The results service refused: {answer.get('error') or answer}")
    return answer


def keys_from_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each question's keys as option TEXTS, from exam items as published
    (``pcm_exam_items``): the app shuffles what it shows, so an answer is the
    option, never its position."""
    keys = []
    for item in items:
        options = [str(o) for o in item.get("options", [])]
        if "correctIndices" in item:
            idx = [i for i in item["correctIndices"] if isinstance(i, int)]
        else:
            idx = [item["correct"]] if isinstance(item.get("correct"), int) else []
        keys.append({
            "id": str(item.get("id", "")),
            "module": str(item.get("module", "")),
            "options": options,
            "correct": [options[i] for i in idx if 0 <= i < len(options)],
            "explanation": str(item.get("explanation", "")),
        })
    return keys


def upload_keys(url: str, course_id: str, pass_mark: int, level: int,
                items: list[dict[str, Any]]) -> int:
    """Store one exam's keys on the results service. Returns how many it holds."""
    keys = keys_from_items(items)
    missing = [k["id"] for k in keys if not k["correct"]]
    if missing:
        raise ResultsServiceError(f"These questions have no correct answer to upload: {', '.join(missing)}")
    answer = _post(url, {"type": "set_keys", "courseId": course_id, "passMark": int(pass_mark),
                         "level": int(level), "questions": keys})
    stored = int(answer.get("stored", 0))
    if stored != len(keys):
        raise ResultsServiceError(f"The results service stored {stored} of {len(keys)} keys.")
    return stored


def export_results(url: str, course_id: str = "") -> list[dict[str, Any]]:
    """The Detail rows, as the item analysis import takes them. Rows the
    service could not mark ("-") are left out, as the CSV import does."""
    answer = _post(url, {"type": "export_results", **({"courseId": course_id} if course_id else {})})
    rows = []
    for r in answer.get("rows", []):
        mark = str(r.get("wasCorrect", "")).strip().upper()
        if mark == "-" or not r.get("attemptId") or not r.get("questionId"):
            continue
        rows.append({
            "attempt_id": str(r["attemptId"]),
            "question_id": str(r["questionId"]),
            "course_id": str(r.get("courseId", "")),
            "submitted_at": str(r.get("submittedAt", "")),
            "user_answer": str(r.get("userAnswer", "")),
            "correct_answer": str(r.get("correctAnswer", "")),
            "was_correct": 1 if mark in ("Y", "YES", "TRUE", "1") else 0,
        })
    return rows
