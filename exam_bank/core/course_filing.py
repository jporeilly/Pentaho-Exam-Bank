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

- **id** — the one format every course exam uses, which PCM's
  verify-course enforces: `<course token>-m<module>-q<question>`, as in
  `di-m3-q7`. The token and each module's m are read from the course's
  questions (in the bank and in its exam.json); the question takes the next
  number in its module, after the highest in use anywhere. A module with no
  questions yet takes the next m; a course with no questions yet takes a
  token from its slug. Never an id used anywhere in the bank or in any
  course's exam.json: the bank keys on the bare id, across courses.
- **module** — the `##` heading of the course's SUMMARY.md the lab sits
  under, which is what the exams use (2hr 5 of 5 modules, Installation 4 of
  4). The lab's title becomes the citation, as it is for adopted questions.
- **place** — straight after the last question of the same module; into a
  free slot if there is one there (a deleted question leaves one), else the
  questions after it move up one, but only as far as the next gap.

An id that already fits the course and its module is never changed: a
course's own id is how the course and the bank recognise the same question.
Everything else gets one that fits - a UUID the bank made up, an id an import
carried from another course or file, and the id of a question whose module
was changed (see refile_id).
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .bank import Certification, ExamBankDB, Question
from .pcm_reader import list_pcm_labs, read_course_json, summary_modules

#: What `uuid.uuid4()` looks like: an id the bank made up, not one a course gave.
_MINTED = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
#: The one question-id format every course exam uses, which PCM's
#: verify-course enforces: <course token>-m<module>-q<question>, e.g. di-m3-q7.
STANDARD_ID = re.compile(r"^([a-z0-9]+)-m([1-9]\d*)-q([1-9]\d*)$")

#: Words a new course's token is not taken from: they name a role or a level
#: that several courses share.
_TOKEN_SKIP = frozenset("developer analyst architect bi practitioner specialty certified lab pdi".split())


def is_minted(question_id: str) -> bool:
    """Whether the bank made this id up (a UUID) rather than a course giving it."""
    return bool(_MINTED.match(question_id or ""))


def is_standard(question_id: str) -> bool:
    """Whether the id reads <token>-m<module>-q<question>."""
    return bool(STANDARD_ID.match(question_id or ""))


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
                data = read_course_json(exam)
            except (OSError, ValueError, UnicodeDecodeError):
                continue
            for q in data.get("questions", []) if isinstance(data, dict) else []:
                if isinstance(q, dict) and q.get("id"):
                    taken.add(str(q["id"]))
    return taken


def _exam_modules(courses_dir, slug: str) -> list[tuple[str, str]]:
    """(id, module) for every question in the course's exam.json."""
    if not courses_dir or not slug:
        return []
    try:
        data = read_course_json(Path(courses_dir) / slug / "exam.json")
    except (OSError, ValueError, UnicodeDecodeError):
        return []
    items = data.get("questions", []) if isinstance(data, dict) else []
    return [(str(i.get("id", "")), str(i.get("module", ""))) for i in items if isinstance(i, dict)]


def _new_token(slug: str, taken: set[str]) -> str:
    """A token for a course none of whose questions has one yet: the first
    word of its slug that is not a role or level, made unique."""
    in_use = {m.group(1) for i in taken if (m := STANDARD_ID.match(i))}
    words = [w for w in re.split(r"[^a-z0-9]+", slug.lower()) if w and w not in _TOKEN_SKIP]
    base = words[0] if words else (re.sub(r"[^a-z0-9]", "", slug.lower())[:3] or "c")
    token, n = base, 2
    while token in in_use:
        token, n = f"{base}{n}", n + 1
    return token


@dataclass
class IdScheme:
    """How one course numbers its questions: its token, and each module's m."""

    token: str
    modules: dict[str, int] = field(default_factory=dict)   # module -> m

    def fits(self, question_id: str, module: str) -> bool:
        """Whether the id already reads this course's way, for this module."""
        m = STANDARD_ID.match(question_id or "")
        if not m or m.group(1) != self.token:
            return False
        number = int(m.group(2))
        if module in self.modules:
            return self.modules[module] == number
        return number not in self.modules.values()

    def module_number(self, module: str) -> int:
        """The module's m. A module with no questions yet takes the next one,
        rather than its place in the reading order: renumbering the modules
        after it would rename questions that are already published."""
        if module not in self.modules:
            self.modules[module] = max(self.modules.values(), default=0) + 1
        return self.modules[module]

    def next_id(self, module: str, taken: set[str]) -> str:
        """The number after the highest this module has used anywhere."""
        m = self.module_number(module)
        own = re.compile(rf"^{re.escape(self.token)}-m{m}-q([1-9]\d*)$")
        n = max((int(x.group(1)) for i in taken if (x := own.match(i))), default=0) + 1
        return f"{self.token}-m{m}-q{n}"


def id_scheme(slug: str, course: list[Question], courses_dir, taken: set[str],
              exclude: str = "") -> IdScheme:
    """The course's scheme, read from its questions in the bank and its exam.json.

    ``exclude`` leaves one question out, so that a question whose module is
    being changed does not tell the scheme its old id's module is its new one.
    """
    pairs = [(q.id, q.topic) for q in course] + _exam_modules(courses_dir, slug)
    parsed = [(m.group(1), int(m.group(2)), module) for qid, module in pairs
              if qid != exclude and (m := STANDARD_ID.match(qid))]
    counts = Counter(t for t, _, _ in parsed)
    token = counts.most_common(1)[0][0] if counts else _new_token(slug, taken)
    modules: dict[str, int] = {}
    for t, number, module in parsed:
        if t == token and module and module not in modules and number not in modules.values():
            modules[module] = number
    return IdScheme(token, modules)


def mint_id(question: Question, course: list[Question], taken: set[str], *,
            slug: str = "", courses_dir=None) -> str:
    """The next id in the course's format that nothing else uses."""
    scheme = id_scheme(slug, course, courses_dir, taken, exclude=question.id)
    return scheme.next_id(question.topic, taken | {q.id for q in course})


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

    # The id: anything that does not already read this course's way for
    # this module gets the next number in the module (see the module
    # docstring). A course's own id fits, and stays.
    scheme = id_scheme(slug, course, courses_dir, taken, exclude=question.id)
    if not scheme.fits(question.id, question.topic):
        new_id = scheme.next_id(question.topic, taken | {q.id for q in course})
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


def refile_id(db: ExamBankDB, question: Question, cert: Certification | None, *,
              courses_dir, editor: str = "") -> str:
    """After a question's module is changed, give it the id the new module
    calls for, renaming its row and recording the change in its history.

    Returns the old id, or "" when the id already fits (or the certification
    is not a course). The caller saves the question afterwards, under its
    new id. A published question renamed this way shows in the next publish
    as its old id removed and its new id added: the id names the module, so
    moving a question to another module is a new id by design.
    """
    slug = course_slug(cert)
    if not slug:
        return ""
    course = [q for q in db.search(certification_id=cert.id, limit=100000) if q.id != question.id]
    taken = taken_ids(db, courses_dir)
    scheme = id_scheme(slug, course, courses_dir, taken, exclude=question.id)
    if scheme.fits(question.id, question.topic):
        return ""
    old = question.id
    new_id = scheme.next_id(question.topic, taken | {q.id for q in course})
    question.record_edit("id", old, new_id, editor=editor or "Exam Bank")
    db.rename_question(old, new_id)
    question.id = new_id
    return old
