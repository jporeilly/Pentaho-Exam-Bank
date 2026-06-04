"""SQLite-backed question bank with full CRUD, search, and tagging."""

import json
import sqlite3
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional


BLOOM_LEVELS = [
    "Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create",
]

DIFFICULTIES = ["Easy", "Medium", "Hard"]

# Full question lifecycle:
#   draft → sme_review → revised → approved → retired
#                      ↘ rejected
STATUSES = ["draft", "sme_review", "revised", "approved", "rejected", "retired"]

# Valid transitions between states
STATUS_TRANSITIONS = {
    "draft":      ["sme_review", "rejected"],
    "sme_review": ["revised", "approved", "rejected"],
    "revised":    ["sme_review", "approved", "rejected"],
    "approved":   ["retired"],
    "rejected":   ["draft"],       # can be reworked
    "retired":    ["draft"],       # can be brought back
}

STATUS_LABELS = {
    "draft":      "Draft",
    "sme_review": "SME Review",
    "revised":    "Revised",
    "approved":   "Approved",
    "rejected":   "Rejected",
    "retired":    "Retired",
}

# Varying multiple choice: questions can have 3, 4, or 5 total choices
CHOICE_COUNTS = [3, 4, 5]


SOURCE_TYPES = ["pptx", "docs", "pcm"]


@dataclass
class Certification:
    """A certification exam that PPTX decks or documentation sources are assigned to."""
    id: str = ""
    name: str = ""              # e.g. "SE Certification 2026"
    description: str = ""
    source_type: str = "pptx"   # "pptx" = slide-based, "docs" = MCP docs, "pcm" = PCM course
    source_ref: str = ""        # for "pcm": the PCM course slug to read content from
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at


@dataclass
class ReviewEntry:
    """A single review action in the question's audit trail."""
    timestamp: str = ""
    sme_name: str = ""
    action: str = ""            # e.g. "submitted", "approved", "rejected", "revised"
    from_status: str = ""
    to_status: str = ""
    comment: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class Question:
    """A single certification exam question following best practices.

    Key rule: the correct answer (key) MUST be sourced from slide content.
    The source slide(s) that contain the key are tracked in source_slides / key_source_slide.

    Lifecycle: draft → sme_review → revised/approved/rejected → retired
    Each transition is logged in review_history with SME name and timestamp.
    """
    id: str = ""
    scenario: str = ""              # Background context / setup
    stem: str = ""                  # The actual question (e.g. "Which two..." for multi-select)
    question_type: str = "single"   # "single" = 1 correct, "multi" = N correct ("Which two...")
    key: str = ""                   # Correct answer (for single-select) — MUST come from slides
    keys: List[str] = field(default_factory=list)  # Multiple correct answers (for multi-select)
    key_source_text: str = ""       # The exact text from the slide that supports the key(s)
    distractors: List[str] = field(default_factory=list)  # Wrong answers (2-4)
    option_order: List[str] = field(default_factory=list)  # Original display order of all options (keys + distractors interleaved)
    explanation: str = ""           # Why the key(s) are correct
    source_file: str = ""           # Which PPTX it came from
    source_slides: List[int] = field(default_factory=list)  # All slides referenced (0-based)
    key_source_slide: int = -1      # Primary slide containing the key answer (0-based)
    topic: str = ""                 # Subject area / tag
    tags: List[str] = field(default_factory=list)
    difficulty: str = "Medium"      # Easy / Medium / Hard
    bloom_level: str = "Apply"      # Bloom's taxonomy level
    certification_id: str = ""      # FK to certifications table
    source_type: str = "pptx"       # "pptx" = slide-based, "docs" = documentation-based
    source_links: List[str] = field(default_factory=list)  # Documentation URLs (for docs-sourced questions)
    status: str = "draft"           # Lifecycle state

    # SME / review tracking
    created_by: str = ""            # Who generated/created the question (SME name or "AI")
    assigned_sme: str = ""          # SME currently responsible for review
    review_history: List[dict] = field(default_factory=list)  # Audit trail of ReviewEntry dicts
    reject_reason: str = ""         # Why it was rejected (if status == rejected)
    version_history: List[dict] = field(default_factory=list)  # Edit history [{timestamp, field, old, new, editor}]
    version: int = 1                # Current version number

    # Timestamps
    created_at: str = ""
    updated_at: str = ""
    submitted_at: str = ""          # When first sent for review
    reviewed_at: str = ""           # When last reviewed by SME
    approved_at: str = ""           # When approved

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    @property
    def correct_answers(self) -> List[str]:
        """Return all correct answers (1 for single, N for multi-select)."""
        if self.question_type == "multi" and self.keys:
            return self.keys
        return [self.key] if self.key else []

    @property
    def num_correct(self) -> int:
        """How many correct answers this question has."""
        return len(self.correct_answers)

    @property
    def num_choices(self) -> int:
        """Total number of answer choices (correct + distractors)."""
        return len(self.correct_answers) + len(self.distractors)

    @property
    def all_choices(self) -> List[str]:
        """Return all options in original display order (or keys+distractors if no order stored)."""
        if self.option_order:
            return list(self.option_order)
        return self.correct_answers + self.distractors

    @property
    def format_label(self) -> str:
        """Human-readable format label like 'Single (4 choices)' or 'Multi-2 (5 choices)'."""
        if self.question_type == "multi":
            return f"Select {self.num_correct} ({self.num_choices} choices)"
        return f"Single ({self.num_choices} choices)"

    def transition(self, new_status: str, sme_name: str = "", comment: str = ""):
        """Move the question to a new lifecycle state with audit trail.

        Raises ValueError if the transition is not allowed.
        """
        allowed = STATUS_TRANSITIONS.get(self.status, [])
        if new_status not in allowed:
            raise ValueError(
                f"Cannot transition from '{self.status}' to '{new_status}'. "
                f"Allowed: {allowed}"
            )
        entry = ReviewEntry(
            sme_name=sme_name,
            action=new_status,
            from_status=self.status,
            to_status=new_status,
            comment=comment,
        )
        self.review_history.append({
            "timestamp": entry.timestamp,
            "sme_name": entry.sme_name,
            "action": entry.action,
            "from_status": entry.from_status,
            "to_status": entry.to_status,
            "comment": entry.comment,
        })

        now = datetime.now().isoformat()
        if new_status == "sme_review" and not self.submitted_at:
            self.submitted_at = now
        if new_status in ("approved", "revised", "rejected"):
            self.reviewed_at = now
        if new_status == "approved":
            self.approved_at = now
        if new_status == "rejected":
            self.reject_reason = comment

        self.status = new_status
        self.updated_at = now

    def allowed_transitions(self) -> List[str]:
        """Return the list of states this question can move to."""
        return STATUS_TRANSITIONS.get(self.status, [])

    def record_edit(self, field: str, old_value: str, new_value: str, editor: str = ""):
        """Record a field edit in the version history."""
        if old_value == new_value:
            return
        self.version_history.append({
            "timestamp": datetime.now().isoformat(),
            "field": field,
            "old": str(old_value)[:500],
            "new": str(new_value)[:500],
            "editor": editor,
            "version": self.version,
        })
        self.version += 1
        self.updated_at = datetime.now().isoformat()

    def validate(self) -> List[str]:
        """Return a list of all quality issues (errors + warnings)."""
        errors, warnings = self.validate_detailed()
        return errors + warnings

    def validate_detailed(self) -> tuple:
        """Return (errors, warnings) — errors block save, warnings are advisory.

        Returns:
            (errors: List[str], warnings: List[str])
        """
        errors = []
        warnings = []

        # ── Errors (block save) ──────────────────────────────
        if not self.stem.strip():
            errors.append("Stem is empty")

        if self.question_type == "multi":
            if len(self.keys) < 2:
                errors.append("Multi-select needs at least 2 correct answers")
        else:
            if not self.key.strip():
                errors.append("Key (correct answer) is empty")

        if len(self.distractors) < 2:
            errors.append(f"Only {len(self.distractors)} distractor(s) — need at least 2")

        # Check for duplicate between correct answers and distractors
        correct_lower = {a.strip().lower() for a in self.correct_answers}
        for d in self.distractors:
            if d.strip().lower() in correct_lower:
                errors.append("A distractor is identical to a correct answer")
                break

        # ── Warnings (advisory) ──────────────────────────────
        if self.question_type == "multi":
            if self.keys and not any(w in self.stem.lower() for w in [
                "choose two", "choose three", "choose four",
                "which two", "which three", "select two", "select three",
            ]):
                warnings.append("Multi-select stem should indicate how many to choose")

        if self.source_type == "pptx":
            if not self.key_source_text:
                warnings.append("Key is not linked to source slide text")
            if self.key_source_slide < 0:
                warnings.append("No source slide recorded for the key answer")
        if not self.certification_id:
            warnings.append("Not assigned to a certification")

        # Check for common item-writing flaws
        all_answer_lengths = [len(a) for a in self.correct_answers] + [len(d) for d in self.distractors]
        if all_answer_lengths and max(all_answer_lengths) > 2 * min(all_answer_lengths):
            warnings.append("Answer lengths are unbalanced — correct answer may stand out")

        lower_distractors = [d.lower().strip() for d in self.distractors]
        if "all of the above" in lower_distractors or "none of the above" in lower_distractors:
            warnings.append("'All/None of the above' is a weak distractor")

        if self.stem.strip() and self.stem.strip()[-1:] not in "?.:)":
            warnings.append("Stem should end with a question mark, period, or colon")

        if "key-unverified" in self.tags:
            if self.question_type == "multi" and not self.keys:
                warnings.append("Correct answers not assigned — edit to mark which options are correct")
            else:
                warnings.append("Correct answer not yet verified — first answer was assumed as key")
        elif "key-not-validated" in self.tags:
            warnings.append("Key failed validation against source material — review the correct answer")

        return errors, warnings


class QuestionBankDB:
    """SQLite database for storing and querying questions and certifications."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        self._migrate()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS certifications (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                description TEXT DEFAULT '',
                source_type TEXT DEFAULT 'pptx',
                source_ref TEXT DEFAULT '',
                created_at TEXT DEFAULT '',
                updated_at TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS questions (
                id TEXT PRIMARY KEY,
                scenario TEXT DEFAULT '',
                stem TEXT DEFAULT '',
                question_type TEXT DEFAULT 'single',
                key_answer TEXT DEFAULT '',
                keys_json TEXT DEFAULT '[]',
                key_source_text TEXT DEFAULT '',
                distractors TEXT DEFAULT '[]',
                explanation TEXT DEFAULT '',
                source_file TEXT DEFAULT '',
                source_slides TEXT DEFAULT '[]',
                key_source_slide INTEGER DEFAULT -1,
                topic TEXT DEFAULT '',
                tags TEXT DEFAULT '[]',
                difficulty TEXT DEFAULT 'Medium',
                bloom_level TEXT DEFAULT 'Apply',
                certification_id TEXT DEFAULT '',
                source_type TEXT DEFAULT 'pptx',
                status TEXT DEFAULT 'draft',
                created_by TEXT DEFAULT '',
                assigned_sme TEXT DEFAULT '',
                review_history TEXT DEFAULT '[]',
                reject_reason TEXT DEFAULT '',
                version_history TEXT DEFAULT '[]',
                version INTEGER DEFAULT 1,
                created_at TEXT DEFAULT '',
                updated_at TEXT DEFAULT '',
                submitted_at TEXT DEFAULT '',
                reviewed_at TEXT DEFAULT '',
                approved_at TEXT DEFAULT '',
                FOREIGN KEY (certification_id) REFERENCES certifications(id)
            );

            CREATE INDEX IF NOT EXISTS idx_questions_topic ON questions(topic);
            CREATE INDEX IF NOT EXISTS idx_questions_status ON questions(status);
            CREATE INDEX IF NOT EXISTS idx_questions_difficulty ON questions(difficulty);
            CREATE INDEX IF NOT EXISTS idx_questions_source ON questions(source_file);
            CREATE INDEX IF NOT EXISTS idx_questions_cert ON questions(certification_id);
            CREATE INDEX IF NOT EXISTS idx_questions_sme ON questions(assigned_sme);
        """)
        self.conn.commit()

    def _migrate(self):
        """Add columns that may be missing from older databases."""
        # Migrate certifications table
        cert_cols = {row[1] for row in self.conn.execute("PRAGMA table_info(certifications)").fetchall()}
        if "source_type" not in cert_cols:
            self.conn.execute("ALTER TABLE certifications ADD COLUMN source_type TEXT DEFAULT 'pptx'")
            self.conn.commit()
        if "source_ref" not in cert_cols:
            self.conn.execute("ALTER TABLE certifications ADD COLUMN source_ref TEXT DEFAULT ''")
            self.conn.commit()

        existing = {row[1] for row in self.conn.execute("PRAGMA table_info(questions)").fetchall()}
        migrations = {
            "question_type": "ALTER TABLE questions ADD COLUMN question_type TEXT DEFAULT 'single'",
            "keys_json": "ALTER TABLE questions ADD COLUMN keys_json TEXT DEFAULT '[]'",
            "key_source_text": "ALTER TABLE questions ADD COLUMN key_source_text TEXT DEFAULT ''",
            "source_slides": "ALTER TABLE questions ADD COLUMN source_slides TEXT DEFAULT '[]'",
            "key_source_slide": "ALTER TABLE questions ADD COLUMN key_source_slide INTEGER DEFAULT -1",
            "certification_id": "ALTER TABLE questions ADD COLUMN certification_id TEXT DEFAULT ''",
            "created_by": "ALTER TABLE questions ADD COLUMN created_by TEXT DEFAULT ''",
            "assigned_sme": "ALTER TABLE questions ADD COLUMN assigned_sme TEXT DEFAULT ''",
            "review_history": "ALTER TABLE questions ADD COLUMN review_history TEXT DEFAULT '[]'",
            "reject_reason": "ALTER TABLE questions ADD COLUMN reject_reason TEXT DEFAULT ''",
            "source_type": "ALTER TABLE questions ADD COLUMN source_type TEXT DEFAULT 'pptx'",
            "submitted_at": "ALTER TABLE questions ADD COLUMN submitted_at TEXT DEFAULT ''",
            "reviewed_at": "ALTER TABLE questions ADD COLUMN reviewed_at TEXT DEFAULT ''",
            "approved_at": "ALTER TABLE questions ADD COLUMN approved_at TEXT DEFAULT ''",
            "source_links": "ALTER TABLE questions ADD COLUMN source_links TEXT DEFAULT '[]'",
            "version_history": "ALTER TABLE questions ADD COLUMN version_history TEXT DEFAULT '[]'",
            "version": "ALTER TABLE questions ADD COLUMN version INTEGER DEFAULT 1",
            "option_order": "ALTER TABLE questions ADD COLUMN option_order TEXT DEFAULT '[]'",
        }
        for col, sql in migrations.items():
            if col not in existing:
                self.conn.execute(sql)
        self.conn.commit()

    # ── Certification CRUD ────────────────────────────────

    def save_certification(self, cert: Certification) -> Certification:
        cert.updated_at = datetime.now().isoformat()
        self.conn.execute("""
            INSERT OR REPLACE INTO certifications (id, name, description, source_type, source_ref, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (cert.id, cert.name, cert.description, cert.source_type, cert.source_ref, cert.created_at, cert.updated_at))
        self.conn.commit()
        return cert

    def get_certification(self, cert_id: str) -> Optional[Certification]:
        row = self.conn.execute("SELECT * FROM certifications WHERE id = ?", (cert_id,)).fetchone()
        if not row:
            return None
        cols = set(row.keys())
        return Certification(
            id=row["id"], name=row["name"], description=row["description"],
            source_type=row["source_type"] if "source_type" in cols else "pptx",
            source_ref=row["source_ref"] if "source_ref" in cols else "",
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def list_certifications(self) -> List[Certification]:
        rows = self.conn.execute("SELECT * FROM certifications ORDER BY name").fetchall()
        results = []
        for r in rows:
            cols = set(r.keys())
            results.append(Certification(
                id=r["id"], name=r["name"], description=r["description"],
                source_type=r["source_type"] if "source_type" in cols else "pptx",
                source_ref=r["source_ref"] if "source_ref" in cols else "",
                created_at=r["created_at"], updated_at=r["updated_at"],
            ))
        return results

    def delete_certification(self, cert_id: str):
        self.conn.execute("DELETE FROM certifications WHERE id = ?", (cert_id,))
        self.conn.commit()

    def count_by_certification(self, cert_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM questions WHERE certification_id = ?", (cert_id,)
        ).fetchone()
        return row[0] if row else 0

    # ── Question CRUD ─────────────────────────────────────

    def save(self, q: Question) -> Question:
        q.updated_at = datetime.now().isoformat()
        self.conn.execute("""
            INSERT OR REPLACE INTO questions
            (id, scenario, stem, question_type, key_answer, keys_json, key_source_text,
             distractors, option_order, explanation, source_file, source_slides, key_source_slide,
             topic, tags, difficulty, bloom_level, certification_id, source_type, source_links,
             status, created_by, assigned_sme, review_history, reject_reason,
             version_history, version,
             created_at, updated_at, submitted_at, reviewed_at, approved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            q.id, q.scenario, q.stem, q.question_type, q.key, json.dumps(q.keys),
            q.key_source_text, json.dumps(q.distractors), json.dumps(q.option_order),
            q.explanation,
            q.source_file, json.dumps(q.source_slides), q.key_source_slide,
            q.topic, json.dumps(q.tags), q.difficulty, q.bloom_level,
            q.certification_id, q.source_type, json.dumps(q.source_links),
            q.status, q.created_by, q.assigned_sme,
            json.dumps(q.review_history), q.reject_reason,
            json.dumps(q.version_history), q.version,
            q.created_at, q.updated_at, q.submitted_at, q.reviewed_at, q.approved_at,
        ))
        self.conn.commit()
        return q

    def get(self, question_id: str) -> Optional[Question]:
        row = self.conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        return self._row_to_question(row) if row else None

    def delete(self, question_id: str):
        self.conn.execute("DELETE FROM questions WHERE id = ?", (question_id,))
        self.conn.commit()

    def search(
        self,
        text: str = "",
        topic: str = "",
        difficulty: str = "",
        bloom_level: str = "",
        status: str = "",
        certification_id: str = "",
        source_file: str = "",
        assigned_sme: str = "",
        tags: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> List[Question]:
        conditions = []
        params = []

        if text:
            conditions.append(
                "(stem LIKE ? OR scenario LIKE ? OR key_answer LIKE ? OR explanation LIKE ?)"
            )
            params.extend([f"%{text}%"] * 4)
        if topic:
            conditions.append("topic LIKE ?")
            params.append(f"%{topic}%")
        if difficulty:
            conditions.append("difficulty = ?")
            params.append(difficulty)
        if bloom_level:
            conditions.append("bloom_level = ?")
            params.append(bloom_level)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if certification_id:
            conditions.append("certification_id = ?")
            params.append(certification_id)
        if source_file:
            conditions.append("source_file LIKE ?")
            params.append(f"%{source_file}%")
        if assigned_sme:
            conditions.append("assigned_sme = ?")
            params.append(assigned_sme)
        if tags:
            conditions.append("tags LIKE ?")
            params.append(f'%"{tags}"%')

        where = " AND ".join(conditions) if conditions else "1=1"
        query = f"SELECT * FROM questions WHERE {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_question(r) for r in rows]

    def search_count(
        self,
        text: str = "",
        topic: str = "",
        difficulty: str = "",
        bloom_level: str = "",
        status: str = "",
        certification_id: str = "",
        source_file: str = "",
        assigned_sme: str = "",
        tags: str = "",
    ) -> int:
        """Return total matching question count for pagination."""
        conditions = []
        params = []
        if text:
            conditions.append(
                "(stem LIKE ? OR scenario LIKE ? OR key_answer LIKE ? OR explanation LIKE ?)"
            )
            params.extend([f"%{text}%"] * 4)
        if topic:
            conditions.append("topic LIKE ?")
            params.append(f"%{topic}%")
        if difficulty:
            conditions.append("difficulty = ?")
            params.append(difficulty)
        if bloom_level:
            conditions.append("bloom_level = ?")
            params.append(bloom_level)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if certification_id:
            conditions.append("certification_id = ?")
            params.append(certification_id)
        if source_file:
            conditions.append("source_file LIKE ?")
            params.append(f"%{source_file}%")
        if assigned_sme:
            conditions.append("assigned_sme = ?")
            params.append(assigned_sme)
        if tags:
            conditions.append("tags LIKE ?")
            params.append(f'%"{tags}"%')
        where = " AND ".join(conditions) if conditions else "1=1"
        row = self.conn.execute(f"SELECT COUNT(*) FROM questions WHERE {where}", params).fetchone()
        return row[0] if row else 0

    def get_status_counts(self) -> dict:
        """Return question counts per status for dashboard metrics."""
        rows = self.conn.execute(
            "SELECT status, COUNT(*) FROM questions GROUP BY status"
        ).fetchall()
        counts = {s: 0 for s in STATUSES}
        for row in rows:
            counts[row[0]] = row[1]
        counts["total"] = sum(counts.values())
        return counts

    def get_topic_counts(self, certification_id: str = "") -> dict:
        """Return question counts per topic."""
        if certification_id:
            rows = self.conn.execute(
                "SELECT topic, COUNT(*) FROM questions WHERE certification_id = ? AND topic != '' GROUP BY topic ORDER BY topic",
                (certification_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT topic, COUNT(*) FROM questions WHERE topic != '' GROUP BY topic ORDER BY topic"
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def get_difficulty_counts(self, certification_id: str = "") -> dict:
        """Return question counts per difficulty level."""
        if certification_id:
            rows = self.conn.execute(
                "SELECT difficulty, COUNT(*) FROM questions WHERE certification_id = ? GROUP BY difficulty",
                (certification_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT difficulty, COUNT(*) FROM questions GROUP BY difficulty"
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def get_bloom_counts(self, certification_id: str = "") -> dict:
        """Return question counts per Bloom's taxonomy level."""
        if certification_id:
            rows = self.conn.execute(
                "SELECT bloom_level, COUNT(*) FROM questions WHERE certification_id = ? GROUP BY bloom_level",
                (certification_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT bloom_level, COUNT(*) FROM questions GROUP BY bloom_level"
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def count(self, status: str = "", topic: str = "", certification_id: str = "") -> int:
        conditions = []
        params = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if topic:
            conditions.append("topic = ?")
            params.append(topic)
        if certification_id:
            conditions.append("certification_id = ?")
            params.append(certification_id)
        where = " AND ".join(conditions)
        sql = f"SELECT COUNT(*) FROM questions WHERE {where}" if where else "SELECT COUNT(*) FROM questions"
        row = self.conn.execute(sql, params).fetchone()
        return row[0] if row else 0

    def get_topics(self, certification_id: str = "") -> List[str]:
        if certification_id:
            rows = self.conn.execute(
                "SELECT DISTINCT topic FROM questions WHERE topic != '' AND certification_id = ? ORDER BY topic",
                (certification_id,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT DISTINCT topic FROM questions WHERE topic != '' ORDER BY topic"
            ).fetchall()
        return [r[0] for r in rows]

    def get_smes(self) -> List[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT assigned_sme FROM questions WHERE assigned_sme != '' ORDER BY assigned_sme"
        ).fetchall()
        return [r[0] for r in rows]

    def get_all_tags(self) -> List[str]:
        """Return sorted list of unique user-facing tags (excluding internal qa: tags)."""
        rows = self.conn.execute(
            "SELECT DISTINCT tags FROM questions WHERE tags != '[]' AND tags != ''"
        ).fetchall()
        all_tags = set()
        for row in rows:
            try:
                tag_list = json.loads(row[0])
                for tag in tag_list:
                    if not tag.startswith("qa:"):
                        all_tags.add(tag)
            except (json.JSONDecodeError, TypeError):
                pass
        return sorted(all_tags)

    def has_similar_stem(self, stem: str, threshold: float = None) -> bool:
        """Check if a question with a very similar stem already exists.

        Uses normalized word overlap to detect duplicates. Returns True if
        any existing question has >= threshold overlap with the given stem.
        """
        if threshold is None:
            from ..utils.config import config
            threshold = config.duplicate_threshold
        if not stem or not stem.strip():
            return False
        norm_stem = " ".join(stem.lower().split())
        stem_words = set(norm_stem.split())
        if not stem_words:
            return False

        # Check against all stems in the DB
        rows = self.conn.execute("SELECT stem FROM questions").fetchall()
        for row in rows:
            existing = " ".join((row[0] or "").lower().split())
            if not existing:
                continue
            # Exact match
            if norm_stem == existing:
                return True
            # Word overlap
            existing_words = set(existing.split())
            overlap = len(stem_words & existing_words) / max(len(stem_words), len(existing_words))
            if overlap >= threshold:
                return True
        return False

    def find_similar_stems(self, stem: str, threshold: float = None) -> List["Question"]:
        """Return existing questions with stems similar to the given one."""
        return [q for q, _ in self.find_similar_stems_scored(stem, threshold)]

    def find_similar_stems_scored(self, stem: str, threshold: float = None) -> List[tuple]:
        """Return list of (Question, similarity_score) for stems above threshold."""
        if threshold is None:
            from ..utils.config import config
            threshold = config.duplicate_threshold
        if not stem or not stem.strip():
            return []
        norm_stem = " ".join(stem.lower().split())
        stem_words = set(norm_stem.split())
        if not stem_words:
            return []

        matches = []
        rows = self.conn.execute("SELECT id, stem FROM questions").fetchall()
        for row in rows:
            existing = " ".join((row[1] or "").lower().split())
            if not existing:
                continue
            existing_words = set(existing.split())
            if norm_stem == existing:
                overlap = 1.0
            else:
                overlap = len(stem_words & existing_words) / max(len(stem_words), len(existing_words))
            if overlap >= threshold:
                q = self.get(row[0])
                if q:
                    matches.append((q, overlap))
        return matches

    def bulk_update_status(self, ids: List[str], status: str):
        now = datetime.now().isoformat()
        self.conn.executemany(
            "UPDATE questions SET status = ?, updated_at = ? WHERE id = ?",
            [(status, now, qid) for qid in ids],
        )
        self.conn.commit()

    def _row_to_question(self, row: sqlite3.Row) -> Question:
        """Convert a database row to a Question, handling old/new schema gracefully."""
        keys = set(row.keys())

        # Handle old source_slide (int) vs new source_slides (JSON list)
        source_slides = []
        if "source_slides" in keys:
            try:
                source_slides = json.loads(row["source_slides"])
            except (json.JSONDecodeError, TypeError):
                pass
        if not source_slides and "source_slide" in keys:
            old = row["source_slide"]
            if old is not None and old >= 0:
                source_slides = [old]

        def _safe(col, default=""):
            return row[col] if col in keys and row[col] is not None else default

        review_history = []
        if "review_history" in keys:
            try:
                review_history = json.loads(row["review_history"])
            except (json.JSONDecodeError, TypeError):
                pass

        question_type = _safe("question_type", "single")
        keys_list = []
        if "keys_json" in keys:
            try:
                keys_list = json.loads(row["keys_json"])
            except (json.JSONDecodeError, TypeError):
                pass

        return Question(
            id=row["id"],
            scenario=row["scenario"],
            stem=row["stem"],
            question_type=question_type,
            key=row["key_answer"],
            keys=keys_list,
            key_source_text=_safe("key_source_text"),
            distractors=json.loads(row["distractors"]),
            option_order=json.loads(_safe("option_order", "[]")) if "option_order" in keys else [],
            explanation=row["explanation"],
            source_file=row["source_file"],
            source_slides=source_slides,
            key_source_slide=_safe("key_source_slide", -1),
            topic=row["topic"],
            tags=json.loads(row["tags"]),
            difficulty=row["difficulty"],
            bloom_level=row["bloom_level"],
            certification_id=_safe("certification_id"),
            source_type=_safe("source_type", "pptx"),
            source_links=json.loads(_safe("source_links", "[]")) if "source_links" in keys else [],
            status=row["status"],
            created_by=_safe("created_by"),
            assigned_sme=_safe("assigned_sme"),
            review_history=review_history,
            reject_reason=_safe("reject_reason"),
            version_history=json.loads(_safe("version_history", "[]")) if "version_history" in keys else [],
            version=_safe("version", 1) if "version" in keys else 1,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            submitted_at=_safe("submitted_at"),
            reviewed_at=_safe("reviewed_at"),
            approved_at=_safe("approved_at"),
        )

    # ── SME helpers ──────────────────────────────────────

    def count_by_sme(self, sme_name: str) -> int:
        """Count questions assigned to a given SME."""
        row = self.conn.execute(
            "SELECT COUNT(*) FROM questions WHERE assigned_sme = ?", (sme_name,)
        ).fetchone()
        return row[0] if row else 0

    def reassign_sme(self, old_name: str, new_name: str) -> int:
        """Reassign all questions from one SME to another. Returns count updated."""
        cur = self.conn.execute(
            "UPDATE questions SET assigned_sme = ?, updated_at = ? WHERE assigned_sme = ?",
            (new_name, datetime.now().isoformat(), old_name),
        )
        self.conn.commit()
        return cur.rowcount

    def reassign_certification(self, from_cert_id: str, to_cert_id: str) -> int:
        """Move all questions from one certification to another. Returns count updated."""
        now = datetime.now().isoformat()
        # Also update source_type to match the target certification
        to_cert = self.get_certification(to_cert_id)
        new_source_type = to_cert.source_type if to_cert else "pptx"
        cur = self.conn.execute(
            "UPDATE questions SET certification_id = ?, source_type = ?, updated_at = ? "
            "WHERE certification_id = ?",
            (to_cert_id, new_source_type, now, from_cert_id),
        )
        self.conn.commit()
        return cur.rowcount

    def close(self):
        self.conn.close()
