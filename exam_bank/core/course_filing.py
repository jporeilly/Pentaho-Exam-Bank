"""Filing a question into a course: the course's id, module, citation and place.

A question adopted from a course arrives with everything the course gave it:
an id in the course's own scheme (`m3-q7`, `install-ai-q12`, `q-mi`), the
module the course files it under, a citation naming the lab, and its place in
the pool. A question the BANK writes — generated from a lab, or imported from
a file that carried no ids — arrived with none of it: a random UUID for an id,
the lab's title where the course has a module name, `pptx` as its source type,
and no place at all (`pool_order` -1).

Each of those showed. The Bank listed `03f2c063-39c…` among `q-preview` and
`q-mi` with no Order. The Report counted the lab as a topic of one question.
And a single unplaced question switched off the course order for the WHOLE
publish (the exporter sorted only when every question had a place), so the
exam would have been written back in the bank's newest-first order.

This gives a new question what an adopted one has, when it is filed under a
course:

- **id** — the course's scheme. Where the course numbers its questions
  (`m3-q1`…`m3-q13`) it takes the next number in the family its module
  uses, else the course's commonest family; where it names them (`q-mi`,
  `q-hidden-data`) it takes the same prefix and a slug of the question's key
  words. Never an id used anywhere in the bank or in any course's exam.json:
  the bank keys on the bare id, across courses.
- **module** — the `##` heading of the course's SUMMARY.md the lab sits
  under, which is what the exams use (2hr 5 of 5 modules, Installation 4 of
  4). The lab's title becomes the citation, as it is for adopted questions.
- **place** — straight after the last question of the same module; into a
  free slot if there is one there (a deleted question leaves one), else the
  questions after it move up one, but only as far as the next gap.

Only ids the bank made up are ever changed. An id a course gave is how the
course and the bank recognise the same question.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .bank import Certification, ExamBankDB, Question
from .docs import STOP_WORDS, tokens
from .pcm_reader import list_pcm_labs, summary_modules

#: What `uuid.uuid4()` looks like: an id the bank made up, not one a course gave.
_MINTED = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_NUMBERED = re.compile(r"^(.*?)(\d+)$")

#: Words that say nothing about what a question is about, on top of the
#: search's stop words. A slug id is a handle for a person reading a list.
#: Found on the first real run: "What is the key advantage of…" gave
#: `q-key-advantage`. Product terms (job, step, transformation) are kept:
#: the courses' own ids use them (`q-jobs`, `q-filter-false`).
_SLUG_SKIP = STOP_WORDS | frozenset("""
pentaho pdi data integration does most likely best primary main reason
following would should could need needs use using used this that these
those which what why how when where requirement requirements scenario
approach way option support supports key advantage advantages benefit
benefits purpose important significant effective efficient efficiently
correct correctly true false result results happen happens describe
describes difference differences
""".split())


def is_minted(question_id: str) -> bool:
    """Whether the bank made this id up (a UUID) rather than a course giving it."""
    return bool(_MINTED.match(question_id or ""))


@dataclass
class CourseMap:
    """A course's labs and the modules its SUMMARY.md files them under."""

    module_of_lab: dict[str, str] = field(default_factory=dict)   # lab dir -> module
    lab_of_title: dict[str, str] = field(default_factory=dict)    # lab title -> lab dir
    title_of_lab: dict[str, str] = field(default_factory=dict)    # lab dir -> lab title

    def lab_for(self, topic: str) -> str:
        """The lab a generated topic names: its title, or "title — section"."""
        topic = (topic or "").strip()
        if topic in self.lab_of_title:
            return self.lab_of_title[topic]
        for title, lab in sorted(self.lab_of_title.items(), key=lambda kv: -len(kv[0])):
            if topic.startswith(title + " — "):
                return lab
        return ""


def course_map(courses_dir, slug: str) -> CourseMap:
    """A course's labs, by title, and the `##` module each sits under."""
    out = CourseMap()
    if not courses_dir or not slug:
        return out
    for lab in list_pcm_labs(courses_dir, slug):
        out.lab_of_title[lab["title"]] = lab["slug"]
        out.title_of_lab[lab["slug"]] = lab["title"]
    out.module_of_lab = summary_modules(courses_dir, slug)
    return out


def taken_ids(db: ExamBankDB, courses_dir) -> set[str]:
    """Every id in the bank and in every course's exam.json.

    The courses are read too because a course not yet adopted still owns its
    ids: minting one of them now would collide the day it is adopted.
    """
    taken = set(db.all_ids())
    if courses_dir and Path(courses_dir).is_dir():
        for exam in Path(courses_dir).glob("*/exam.json"):
            try:
                data = json.loads(exam.read_text(encoding="utf-8"))
            except (OSError, ValueError, UnicodeDecodeError):
                continue
            for q in data.get("questions", []) if isinstance(data, dict) else []:
                if isinstance(q, dict) and q.get("id"):
                    taken.add(str(q["id"]))
    return taken


def _slug(question: Question, words: int = 2) -> str:
    kept = [t for t in tokens(question.stem) if t not in _SLUG_SKIP and not t.isdigit()]
    if len(kept) < words:
        kept += [t for t in tokens(question.scenario) if t not in _SLUG_SKIP and t not in kept]
    return "-".join(kept[:words]) or "question"


def mint_id(question: Question, course: list[Question], taken: set[str]) -> str:
    """An id in the course's own scheme that nothing else uses."""
    given = [q for q in course if not is_minted(q.id) and q.id != question.id]
    numbered = [(m.group(1), int(m.group(2)), q) for q in given if (m := _NUMBERED.match(q.id))]

    if numbered and len(numbered) * 2 >= len(given):
        # The family the question's own module uses, else the course's commonest.
        same = Counter(p for p, _, q in numbered if q.topic == question.topic)
        every = Counter(p for p, _, _ in numbered)
        chosen = same or every
        prefix = max(chosen.items(), key=lambda kv: (kv[1], len(kv[0])))[0]
        n = max(num for p, num, _ in numbered if p == prefix) + 1
        while f"{prefix}{n}" in taken:
            n += 1
        return f"{prefix}{n}"

    # Named ids: the course's common prefix ("q-") and the question's words.
    lead = Counter(q.id.split("-")[0] + "-" for q in given if "-" in q.id)
    prefix = lead.most_common(1)[0][0] if lead else "q-"
    base = prefix + _slug(question)
    candidate, n = base, 2
    while candidate in taken:
        candidate, n = f"{base}-{n}", n + 1
    return candidate


def placement(question: Question, course: list[Question]) -> tuple[int, dict[str, int]]:
    """Where the question goes in the course order, and who moves to make room.

    After the last question of the same module; a new module goes last. If
    that slot is taken, the questions from there up to the next free slot move
    up one — no further, so a gap a deleted question left is filled rather
    than every later question renumbered (each move shows as a change until
    the course is published).
    """
    placed = sorted((q for q in course if q.pool_order >= 0 and q.id != question.id),
                    key=lambda q: q.pool_order)
    used = {q.pool_order for q in placed}
    same = [q.pool_order for q in placed if q.topic == question.topic]
    target = max(same) + 1 if same else (max(used) + 1 if used else 0)
    if target not in used:
        return target, {}
    gap = target
    while gap in used:
        gap += 1
    return target, {q.id: q.pool_order + 1 for q in placed if target <= q.pool_order < gap}


@dataclass
class Filed:
    """What filing changed, for a report or a history."""

    id_from: str
    id_to: str
    topic_from: str
    topic_to: str
    pool_order: int
    moved: dict[str, int] = field(default_factory=dict)


def course_slug(cert: Certification | None) -> str:
    """The course a certification is, or "" for one that is not a course."""
    if cert and cert.source_type == "pcm" and (cert.source_ref or "").strip():
        return cert.source_ref.strip()
    return ""


def file_into_course(
    db: ExamBankDB,
    question: Question,
    cert: Certification,
    *,
    courses_dir,
    taken: set[str],
    editor: str = "",
    record: bool = False,
) -> Filed | None:
    """Give a question its course id, module, citation and place.

    Works on a question not yet saved (a commit) and on one already in the
    bank (a repair). The question object is updated; ``question.id`` may
    change, and the caller saves it — for a saved question, rename the row
    first with ``db.rename_question``. Questions that make room are moved in
    the database here. ``record`` writes the changes into the question's
    version history, for a repair; a new question has no history to write.

    Returns None when the certification is not a course.
    """
    slug = course_slug(cert)
    if not slug:
        return None
    course = [q for q in db.search(certification_id=cert.id, limit=100000)
              if q.id != question.id]
    cmap = course_map(courses_dir, slug)
    before_id, before_topic = question.id, question.topic

    # Module and citation. Only for a question the course never filed: an
    # adopted question's module and citation are the course's own words.
    authored = question.source_type == "pcm" and question.source_file \
        and not question.source_file.startswith("pcm:")
    if not authored:
        lab = cmap.lab_for(question.topic)
        module = cmap.module_of_lab.get(lab, "")
        if module and module != question.topic:
            if record:
                question.record_edit("topic", question.topic, module, editor=editor)
            question.topic = module
        if lab:
            question.source_file = cmap.title_of_lab.get(lab, question.source_file)
        question.source_type = "pcm"

    if is_minted(question.id):
        new_id = mint_id(question, course, taken)
        if record:
            question.record_edit("id", question.id, new_id, editor=editor)
        question.id = new_id
        taken.add(new_id)

    moved: dict[str, int] = {}
    if question.pool_order < 0:
        question.pool_order, moved = placement(question, course)
        if moved:
            db.set_pool_orders(moved)

    return Filed(before_id, question.id, before_topic, question.topic,
                 question.pool_order, moved)
