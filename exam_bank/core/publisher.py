"""Write the bank's questions into a Content Manager course's ``exam.json``.

Ownership is the whole design, and it is not symmetrical: the Content Editor
owns the exam's delivery and grading settings, the bank owns ``questions``.
So this deliberately does **not** build an exam.json. ``export_pcm_exam_json``
does that, and what it has no parameter for it drops without saying so —
``intake`` above all, which decides whether a course collects a candidate's
name at all. This reads the course's own file, replaces one key in it, and
hands everything else back untouched and in its original order.

Nothing is written until everything is decided. :func:`plan` produces the
diff and every reason to refuse; :func:`apply` performs the write. An author
sees what a publish would do to a live course before it does it, which is the
difference between a merge and an overwrite somebody pressed by accident.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from .bank import Question
from .exporter import pcm_exam_items


class PublishRefused(Exception):
    """Refuse to write, with a reason the author can act on.

    Carries prose rather than a code because every one of these is a thing a
    person has to decide about: the message is the whole value.
    """


@dataclass(frozen=True)
class QuestionChange:
    """One question that exists on both sides but differs."""

    id: str
    fields: list[str]


@dataclass(frozen=True)
class PublishPlan:
    """What publishing would do, computed without touching the file."""

    path: Path
    source_sha: str
    document: dict[str, Any]
    # The line ending the file already uses, so publishing does not convert
    # one. The Content Manager repo has core.autocrlf=true, so a course file
    # checked out afresh is CRLF while one written by tooling is LF; imposing
    # either turns a two-question edit into a whole-file diff.
    newline: str = "\n"
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[QuestionChange] = field(default_factory=list)
    unchanged: int = 0
    reordered: bool = False
    preserved_keys: list[str] = field(default_factory=list)
    before_count: int = 0
    after_count: int = 0
    # The one piece of authored prose a publish may touch: the pool-size
    # numeral the Content Manager's build check enforces. Both empty when the
    # description already agrees, which is the usual case.
    description_before: str = ""
    description_after: str = ""

    @property
    def is_noop(self) -> bool:
        """True when the course's pool already says exactly this.

        Worth knowing before writing: a no-op publish still rewrites the file,
        and a rewritten file is a change the Content Editor may be sitting on
        top of.
        """
        return not (
            self.added
            or self.removed
            or self.changed
            or self.reordered
            or self.description_after
        )


def _walk(node: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    """Every scalar in a document, with its full dotted key path."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _walk(value, f"{path}[{i}]")
    else:
        yield path, node


def stale_blocks(document: dict[str, Any]) -> list[str]:
    """Key paths that should not be in a modern ``exam.json``.

    Two things, both found in the published courses repo in September 2026:

    * ``intake.contact`` — the contact block's original home. It moved to
      ``course.json`` because ``architect-con-specialty``, the one course with
      no exam, could not have a contact page otherwise. Nothing has read it
      here since, so a copy left behind is dead configuration that still looks
      authoritative.
    * a ``webhookSecret`` anywhere but the top level — a live credential at a
      path no code reads. Five published ``exam.json`` carried the contact
      relay's secret inside that dead ``intake.contact`` block, which is how
      one credential came to be published in eight files instead of three.

    Reported so the caller can refuse. Deliberately not stripped: a round-trip
    that quietly rewrites an authored file is how such a block gets
    re-committed with nobody deciding to, and the same silence is what let the
    original copies sit there for months.
    """
    found = []
    intake = document.get("intake")
    if isinstance(intake, dict) and "contact" in intake:
        found.append("intake.contact")
    for key_path, _ in _walk(document):
        if key_path != "webhookSecret" and key_path.split(".")[-1] == "webhookSecret":
            if key_path not in found:
                found.append(key_path)
    return found


# The two pool-size phrasings the Content Manager's verify-course.mjs
# recognises, copied from `checkExamDescriptionClaims` rather than from the
# plan that described them — the plan said "N-exam bank", the check says
# "N-question bank", and a pattern that never matches fixes nothing silently.
# `\s+` because the verifier collapses whitespace before matching, so a claim
# split across two lines counts there and has to count here.
_POOL_OF = re.compile(r"(?i)(pool\s+of\s+)(\d+)")
_QUESTION_BANK = re.compile(r"(?i)(\d+)(-question\s+bank)")


def update_pool_numerals(description: str, pool_size: int) -> str:
    """Bring a description's pool-size claim into line with the pool.

    ``verify-course.mjs`` **fails the build** when the prose misstates the pool
    size ("drawn from a pool of 48"), so a publish that changes the pool and
    leaves the sentence alone hands back a course that will not verify.

    Only the numeral is touched, and only in the two phrasings the verifier
    actually recognises. Rewriting the sentence would be taking over prose the
    author owns. Claims about ``questionsPerAttempt`` and ``passMark`` are left
    alone on purpose: publishing changes neither, so a disagreement there is a
    real one for the author to resolve rather than something to paper over.
    """
    out = _POOL_OF.sub(lambda m: f"{m.group(1)}{pool_size}", description)
    return _QUESTION_BANK.sub(lambda m: f"{pool_size}{m.group(2)}", out)


def _load(path: Path) -> tuple[dict[str, Any], str, str]:
    """The course's exam document, a hash of the exact bytes, and its newline."""
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise PublishRefused(f"{path} could not be read: {e}") from e
    try:
        document = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as e:
        raise PublishRefused(
            f"{path.parent.name}/{path.name} is not readable JSON, so there is "
            f"nothing safe to merge into: {e}"
        ) from e
    if not isinstance(document, dict):
        raise PublishRefused(
            f"{path.parent.name}/{path.name} is a {type(document).__name__}, not an "
            "exam object."
        )
    # Detect rather than assume: whichever the file already uses is the one
    # to write back. A mixed file is treated as CRLF, because converting the
    # CRLF majority to LF is the bigger diff.
    newline = "\r\n" if b"\r\n" in raw else "\n"
    return document, hashlib.sha256(raw).hexdigest(), newline


def plan(
    exam_path: Path, questions: list[Question], *, source_label: str = ""
) -> PublishPlan:
    """What publishing ``questions`` into ``exam_path`` would do.

    Refuses rather than writing something plausible when the result would be
    an exam nobody can sit, or a file carrying configuration this app cannot
    account for.
    """
    if not questions:
        raise PublishRefused(
            "Nothing is selected, and publishing an empty pool would leave the "
            "course with an exam that cannot be sat. Narrow the filters less, "
            "or check that the questions have reached the status you are "
            "publishing."
        )

    if not exam_path.is_file():
        # Creating one would mean inventing passMark, the webhook and the
        # intake behaviour — every setting this app is careful not to own.
        raise PublishRefused(
            f"{exam_path.parent.name} has no exam.json. This publishes questions "
            "into an exam the Content Editor already set up; it does not create "
            "one, because the pass mark, the webhook and the intake behaviour "
            "are not the bank's to invent."
        )

    document, source_sha, newline = _load(exam_path)

    stale = stale_blocks(document)
    if stale:
        raise PublishRefused(
            f"{exam_path.parent.name}/exam.json carries configuration that moved "
            f"out of exam.json: {', '.join(stale)}. Publishing would re-commit "
            "it. `intake.contact` belongs in course.json, and a webhookSecret "
            "below the top level is a credential nothing reads. Remove the "
            "block in the Content Editor first — this app will not strip it, "
            "because dropping an authored key silently is the same failure in "
            "the other direction."
        )

    items = pcm_exam_items(questions, source_label=source_label)

    ids = [str(item.get("id", "")) for item in items]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        # PCM keys an in-progress attempt on the ids it dealt, and posts them
        # in the results payload. Two questions sharing one id make both the
        # resume and the recorded result ambiguous.
        raise PublishRefused(
            "Two questions share an id, which PCM uses as a durable key for "
            f"in-progress attempts and recorded results: {', '.join(duplicates)}."
        )

    per_attempt = document.get("questionsPerAttempt")
    if isinstance(per_attempt, int) and per_attempt > len(items):
        raise PublishRefused(
            f"This course draws {per_attempt} questions per attempt but the "
            f"selection has {len(items)}. Publishing it would leave an exam "
            "that cannot be sat. Publish more questions, or lower "
            "questionsPerAttempt in the Content Editor first."
        )

    old_items = document.get("questions")
    old_items = old_items if isinstance(old_items, list) else []
    old_by_id: dict[str, dict] = {
        str(item.get("id", "")): item for item in old_items if isinstance(item, dict)
    }
    new_by_id = {str(item["id"]): item for item in items}

    added = [i for i in new_by_id if i not in old_by_id]
    removed = [i for i in old_by_id if i not in new_by_id]
    changed = []
    for qid, new_item in new_by_id.items():
        old_item = old_by_id.get(qid)
        if old_item is None:
            continue
        fields = sorted(
            f for f in set(old_item) | set(new_item)
            if old_item.get(f) != new_item.get(f)
        )
        if fields:
            changed.append(QuestionChange(id=qid, fields=fields))

    # Order is compared over the questions common to both sides, so that
    # adding one at the end does not read as "the whole pool moved".
    kept_before = [i for i in old_by_id if i in new_by_id]
    kept_after = [i for i in new_by_id if i in old_by_id]

    # Assigning to an existing key keeps its position in the document, so a
    # file that lists `questions` before `webhookUrl` still does afterwards.
    merged = dict(document)
    merged["questions"] = items

    # The pool size the description claims is the one thing a publish can
    # invalidate in prose, and verify-course.mjs fails the build over it.
    description = document.get("description")
    description_before = description_after = ""
    if isinstance(description, str) and description:
        candidate = update_pool_numerals(description, len(items))
        if candidate != description:
            description_before, description_after = description, candidate
            merged["description"] = candidate

    return PublishPlan(
        path=exam_path,
        source_sha=source_sha,
        document=merged,
        newline=newline,
        added=added,
        removed=removed,
        changed=changed,
        unchanged=len(new_by_id) - len(added) - len(changed),
        reordered=kept_before != kept_after,
        preserved_keys=[
            k for k in document if k != "questions" and not (k == "description" and description_after)
        ],
        before_count=len(old_items),
        after_count=len(items),
        description_before=description_before,
        description_after=description_after,
    )


def apply(plan: PublishPlan, *, expect_sha: str = "") -> Path:
    """Write the planned document, replacing the course's exam.json.

    ``expect_sha`` is the hash the caller was shown a plan for. The Content
    Editor writes this same file, and it writes its whole in-memory copy — so
    a plan reviewed a minute ago can describe a file that no longer exists in
    that form. Passing the hash back turns that race into a refusal instead of
    a silent overwrite of somebody else's save.
    """
    if expect_sha and expect_sha != plan.source_sha:
        raise PublishRefused(
            "The course's exam.json changed after this plan was made — most "
            "likely the Content Editor saved it. Nothing has been written. "
            "Look at the plan again against the current file."
        )

    current = plan.path.read_bytes() if plan.path.is_file() else b""
    if hashlib.sha256(current).hexdigest() != plan.source_sha:
        raise PublishRefused(
            "The course's exam.json changed between planning and writing. "
            "Nothing has been written."
        )

    text = json.dumps(plan.document, indent=2, ensure_ascii=False) + "\n"

    # Write beside the target and rename over it. A partially written exam.json
    # in a course directory is worse than an unwritten one: PCM would read it,
    # fail to parse, and show the course with no exam at all.
    tmp = plan.path.with_name(f"{plan.path.name}.tmp{os.getpid()}")
    try:
        tmp.write_text(text, encoding="utf-8", newline=plan.newline)
        os.replace(tmp, plan.path)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        raise PublishRefused(f"{plan.path} could not be written: {e}") from e
    return plan.path
