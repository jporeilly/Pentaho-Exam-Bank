"""Bulk deletion from the bank, counted before it happens.

Deleting questions in bulk is the one operation here with no undo short of a
backup, and the filters that drive it are the same ones the bank list uses —
so it is genuinely easy to press delete against a view you believe is showing
four questions and have it match four hundred.

Two things follow from that, and they are the whole module.

An **empty filter set matches everything.** ``search_count`` with no
conditions is ``WHERE 1=1``, so a request that names no filter is a truncate.
That has to be asked for explicitly rather than arrived at by leaving fields
blank — an author who cleared a filter to "start again" must not find the bank
empty.

A deletion is **counted first, then confirmed against that count.** The caller
is shown what would go and hands the number back; if the bank changed in
between, the delete is refused rather than applied to a different set. Same
shape as the publish hash, for the same reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .bank import ExamBankDB

#: Filters a bulk deletion may be narrowed by. Deliberately a small set: every
#: one of these is a field an author can see in the bank list, so what gets
#: deleted is something they can look at first.
FILTERS = ("status", "topic", "certification_id", "difficulty", "bloom_level")

#: How many stems to show back. Enough to recognise the set, few enough that
#: the count stays the thing being read.
SAMPLE_SIZE = 5


class DeletionRefused(Exception):
    """Refuse to delete, with a reason the author can act on."""


@dataclass(frozen=True)
class DeletionPlan:
    """What a bulk deletion would remove."""

    total: int
    #: True when no filter narrows the set — i.e. this is the whole bank.
    everything: bool
    by_status: dict[str, int] = field(default_factory=dict)
    by_certification: list[dict[str, Any]] = field(default_factory=list)
    #: A few stems, so the set is recognisable rather than just a number.
    sample: list[str] = field(default_factory=list)


def _active(filters: dict[str, str]) -> dict[str, str]:
    """The filters that actually narrow anything."""
    return {k: v for k, v in filters.items() if k in FILTERS and str(v or "").strip()}


def plan_deletion(db: ExamBankDB, filters: dict[str, str]) -> DeletionPlan:
    """Count what a deletion would remove, and describe the set.

    Never raises for an empty filter set: an author is allowed to *look* at
    what deleting everything would mean. It is the deletion itself that has to
    be asked for explicitly.
    """
    narrowing = _active(filters)
    total = db.search_count(**narrowing)

    # Pull the matching questions once for the breakdowns. Bounded, because a
    # breakdown of a 50,000-row bank is not what is being asked for — the
    # count above is exact regardless.
    matched = db.search(limit=5000, **narrowing)

    by_status: dict[str, int] = {}
    by_certification_counts: dict[str, int] = {}
    for question in matched:
        by_status[question.status] = by_status.get(question.status, 0) + 1
        key = question.certification_id or ""
        by_certification_counts[key] = by_certification_counts.get(key, 0) + 1

    by_certification = []
    for cert_id, count in sorted(by_certification_counts.items(), key=lambda kv: -kv[1]):
        certification = db.get_certification(cert_id) if cert_id else None
        by_certification.append({
            "id": cert_id,
            # A question with no certification is not an error, but it reads
            # as one when the name is blank.
            "name": certification.name if certification else "(no certification)",
            "count": count,
        })

    return DeletionPlan(
        total=total,
        everything=not narrowing,
        by_status=by_status,
        by_certification=by_certification,
        sample=[q.stem for q in matched[:SAMPLE_SIZE] if q.stem],
    )


def delete_questions(
    db: ExamBankDB,
    filters: dict[str, str],
    *,
    expect_count: int,
    everything: bool = False,
) -> int:
    """Delete the matching questions, having been told how many to expect.

    ``expect_count`` comes from :func:`plan_deletion`. A mismatch means the
    bank changed after the author was shown the number — generation finishing,
    an import landing, another window — and the delete is refused rather than
    applied to a set nobody looked at.

    ``everything`` must be passed explicitly to delete an unfiltered set.
    """
    narrowing = _active(filters)

    if not narrowing and not everything:
        raise DeletionRefused(
            "That would delete every question in the bank, because no filter "
            "narrows it. If that is the intention, say so explicitly — an "
            "empty filter is far more often a cleared one."
        )

    current = db.search_count(**narrowing)
    if current != expect_count:
        raise DeletionRefused(
            f"This was going to delete {expect_count} questions but now matches "
            f"{current}. The bank changed in between, so nothing has been "
            "deleted. Look again at what would go."
        )

    if current == 0:
        raise DeletionRefused("Nothing matches that selection, so there is nothing to delete.")

    # Delete by id rather than by a second WHERE clause: the ids are the ones
    # that were counted, so the delete cannot widen if a question is written
    # while it runs.
    ids = [q.id for q in db.search(limit=max(current, 1), **narrowing)]
    for question_id in ids:
        db.delete(question_id)
    return len(ids)
