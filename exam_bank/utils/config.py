"""Settings management for the Exam Bank app."""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

# Where the CODE is: the repo root, two levels above this package
# (exam_bank/utils/config.py). Everything that needs a path off it imports
# PROJECT_ROOT from here rather than re-deriving its own `parent.parent...`
# walk — four modules used to do that, and each one was a separate thing to
# get wrong the next time the tree moved.
#
# Read-only inside an install. Use it for things that SHIP (the guide the
# AI & Docs pane reads); never for anything the app writes.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def state_dir() -> Path:
    """Where the bank keeps its database, its config and its backups.

    Separate from PROJECT_ROOT because in an install they are not the same
    place. The code lives under Program Files, which a normal user cannot
    write to — and this module creates its directories at IMPORT, so a
    read-only root does not degrade gracefully: it raises
    ``PermissionError: [WinError 5] Access is denied`` three frames into
    pathlib before the app can say anything useful. Proved by staging the
    package under a read-only directory and importing it.

    ``PEB_STATE_DIR`` is how the installed shell points this at
    ``%APPDATA%\\com.pentaho.exam-bank`` (Tauri's ``app_data_dir``). Unset — which is every checkout — it is the repo's
    own ``assets/``, exactly as before, so development is unchanged.
    """
    override = os.environ.get("PEB_STATE_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return PROJECT_ROOT / "assets"


ASSETS_DIR = state_dir()
DB_DIR = ASSETS_DIR / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR = ASSETS_DIR / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = CONFIG_DIR / "config.json"
DB_PATH = DB_DIR / "exam_bank.db"
BACKUP_DIR = DB_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# Migrate config from old locations
import shutil as _shutil

# The names this app shipped under before the Exam Bank rename. Held as
# constants because several places need them and a find-and-replace sweep must
# not quietly rewrite them to the new name — one already did, which turned the
# migration below into a no-op that would have left the live bank behind.
# `tests/test_config_migration.py` pins both.
PRE_RENAME_DB_NAME = "question_bank.db"
PRE_RENAME_HOME_DIR = ".question_bank"


def adopt_pre_rename_db(db_dir: Path, db_path: Path) -> bool:
    """Move `question_bank.db` to `exam_bank.db`, the name before the rename.

    Rename rather than copy, and run it before anything else can create the new
    file: two databases that both look live is the worse failure, because a
    later session edits one and reads the other. An existing `exam_bank.db`
    always wins — it is the newer of the two by construction.
    """
    old = db_dir / PRE_RENAME_DB_NAME
    if old.exists() and not db_path.exists():
        old.rename(db_path)
        return True
    return False


# 0. From assets/db/<pre-rename name> (the name this app shipped under)
adopt_pre_rename_db(DB_DIR, DB_PATH)

# 1. From ~/.question_bank/ (legacy)
_OLD_DIR = Path.home() / PRE_RENAME_HOME_DIR
if _OLD_DIR.exists():
    _old_db = _OLD_DIR / PRE_RENAME_DB_NAME
    _old_cfg = _OLD_DIR / "config.json"
    if _old_db.exists() and not DB_PATH.exists():
        _shutil.copy2(_old_db, DB_PATH)
    if _old_cfg.exists() and not CONFIG_FILE.exists():
        _shutil.copy2(_old_cfg, CONFIG_FILE)

# 2. From assets/db/config.json (previous location)
_OLD_CONFIG = DB_DIR / "config.json"
if _OLD_CONFIG.exists() and not CONFIG_FILE.exists():
    _shutil.copy2(_OLD_CONFIG, CONFIG_FILE)
    _OLD_CONFIG.unlink()  # remove old copy to avoid confusion
elif _OLD_CONFIG.exists() and CONFIG_FILE.exists():
    _OLD_CONFIG.unlink()  # new location takes precedence


# Where an installer records the Content Manager checkout it found on this
# machine. Two keys because two apps do the same search and either may have
# run first: the Exam Bank's own installer writes the first, and the Content
# Editor has been writing the second for several releases. The VALUE is the
# repo ROOT, not the courses directory — that is the shape the editor
# already stores, and matching it means one search answers for both.
_PCM_HINT_KEYS = (
    r"SOFTWARE\Pentaho\ExamBank",
    r"SOFTWARE\Pentaho\ContentEditor",
)
_PCM_HINT_VALUE = "PcmRepo"


def _installer_hint() -> Optional[Path]:
    """A Content Manager checkout recorded in the registry, if one is usable.

    Both hives and BOTH REGISTRY VIEWS. An NSIS installer is a 32-bit
    process, so its writes land in WOW6432Node, while this is 64-bit Python
    reading the native view — check one and an install that definitely
    registered itself looks absent.

    A hint is only returned when it still has a ``courses`` directory. A
    checkout that has since moved or been emptied is worse than no hint at
    all: the app would report itself configured and then find nothing.
    """
    if os.name != "nt":
        return None
    try:
        import winreg
    except ImportError:  # pragma: no cover - Windows-only path
        return None

    views = (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY)
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for key_path in _PCM_HINT_KEYS:
            for view in views:
                try:
                    with winreg.OpenKey(
                        hive, key_path, 0, winreg.KEY_READ | view
                    ) as key:
                        raw, _ = winreg.QueryValueEx(key, _PCM_HINT_VALUE)
                except OSError:
                    continue
                if not raw:
                    continue
                candidate = Path(str(raw)).expanduser()
                if (candidate / "courses").is_dir():
                    return candidate
    return None


def _default_pcm_courses_dir() -> str:
    """Where to look for the Content Manager's courses, best guess first.

    The only rule used to be "look for a sibling directory", which is right
    in every checkout and can never work in an install: the code sits under
    Program Files, so the sibling searched was
    ``C:\\Program Files\\Pentaho Exam Bank\\Pentaho-Content-Manager``. The
    first install opened with every pane empty and nothing on screen saying
    why.

    Order matters. An explicit environment variable is a deliberate choice
    and outranks anything found by searching; the installer's hint is a
    machine-wide fact; the sibling is the developer convenience it always
    was. Nothing found returns "" — unconfigured, which the UI already
    reports properly. A guessed path would fail later and further from the
    cause.
    """
    from_env = os.environ.get("PCM_REPO", "").strip()
    if from_env:
        # Not trusted blindly. A stale PCM_REPO left over from a machine
        # that has been reimaged would otherwise pin the app to a directory
        # that no longer exists, with no fallback.
        candidate = Path(from_env).expanduser() / "courses"
        if candidate.is_dir():
            return str(candidate)

    hint = _installer_hint()
    if hint:
        return str(hint / "courses")

    sibling = PROJECT_ROOT.parent / "Pentaho-Content-Manager" / "courses"
    return str(sibling) if sibling.is_dir() else ""


@dataclass
class AppConfig:
    """Application configuration."""
    # Which LLM answers. Ollama is local and free; the cloud providers read
    # their key from the environment at call time and it is never stored here.
    ai_provider: str = "ollama"         # ollama | anthropic | openai
    anthropic_model: str = "claude-opus-4-8"
    openai_model: str = "gpt-4o"

    # Ollama
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = ""
    ollama_enabled: bool = True
    ollama_num_ctx: int = 8192          # context window size for Ollama (tokens)
    # How long to wait for one question before giving up on a section. A
    # 12B model on a mid-range card takes a little over two minutes for a
    # short section, so the old 180s left almost no headroom and a single
    # slow section ended the run. Generous rather than tight: the cost of
    # waiting is a slow section, the cost of cutting it short is losing one.
    generation_timeout_seconds: int = 600
    # Cap on the model's reply, in tokens. 0 = no cap, and that is the right
    # default for a REASONING model.
    #
    # Tried at 2000 to bound a runaway and it broke generation outright: every
    # section came back empty. gemma4 spends thousands of tokens reasoning
    # before it answers, and Ollama does not return those in `response` — one
    # call showed eval_count 4091 for a 330-token answer. A cap counts the
    # reasoning too, so it cuts the model off mid-thought and nothing is
    # produced at all.
    #
    # The context window already bounds the reply, and the timeout bounds the
    # wall clock. Set this only for a model you know does not reason first.
    generation_max_reply_tokens: int = 0
    system_prompt: str = ""

    # The Pentaho product documentation AI Chat searches alongside this app's
    # own: docs.pentaho.com, through the MCP server GitBook publishes for it.
    # On by default - it is what makes the chat useful for writing questions
    # about the products - and one switch in Settings turns it off, after
    # which nothing is sent to the docs site.
    docs_mcp_enabled: bool = True
    docs_mcp_url: str = "https://docs.pentaho.com/~gitbook/mcp"

    # MCP documentation servers - the older, list-shaped setting read only by
    # question_importer.validate_question_against_docs, which nothing calls.
    # Not in the settings API. AI Chat uses docs_mcp_* above.
    mcp_servers: List[dict] = field(default_factory=list)
    mcp_enabled: bool = False

    # UI
    theme_color: str = "Slate"
    dark_mode: bool = True

    # Defaults for question generation
    default_difficulty: str = "Medium"
    default_bloom_level: str = "Apply"

    # User / SME identity
    sme_name: str = ""              # Current user's name for review audit trail
    sme_names: List[str] = field(default_factory=list)  # Saved list of SME names

    # Recent files
    recent_files: List[str] = field(default_factory=list)

    # File-to-certification mapping (filename -> cert_id)
    file_certifications: dict = field(default_factory=dict)

    # Export
    # Off the STATE directory, not the code root: an install writes its
    # exports beside its database, where the user can reach them.
    output_folder: str = str(ASSETS_DIR / "questions")

    # PCM course source — folder holding Pentaho Content Manager courses
    # (each subdir a course with course.json + lab guide.md files).
    pcm_courses_dir: str = field(default_factory=_default_pcm_courses_dir)

    # Where a published exam is pushed so installed Content Managers see it:
    # the distribution repo every learner's app syncs from at launch. The
    # Content Editor's own publish pushes to the same place.
    courses_repo_url: str = "https://github.com/jporeilly/Pentaho-Courses.git"
    courses_repo_ref: str = "main"

    # Auto-backup
    auto_backup_enabled: bool = False
    auto_backup_interval_hours: int = 24
    auto_backup_max_count: int = 5

    # Duplicate detection
    duplicate_threshold: float = 0.85       # 0.0–1.0, stem similarity for duplicate detection

    # Validation
    validation_threshold: float = 0.70      # 0.0–1.0, word overlap for import validation

    # Pagination
    questions_per_page: int = 25            # 10, 25, 50, or 100

    # Default export format
    default_export_format: str = "csv"      # csv, json, qti, moodle, text, docx

    # Auto-export CSV on save
    auto_export_on_save: bool = True        # auto-export questions to assets/questions/ on save

    # Mermaid diagrams
    mermaid_enabled: bool = False            # include Mermaid diagrams in AI responses

    def save(self):
        """Save config to disk.

        UTF-8 explicitly, both here and in ``load``. Windows' default text
        encoding is cp1252, so an SME name or course title outside Latin-1
        would raise on write and mojibake on read. ``json.dumps`` escapes
        non-ASCII by default, which hides the problem today — right up until
        someone passes ``ensure_ascii=False`` to get readable names in the
        file, or the file is written by hand as UTF-8.
        """
        CONFIG_FILE.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def defaults(cls) -> "AppConfig":
        """Return a fresh AppConfig with all default values."""
        return cls()

    @classmethod
    def load(cls) -> "AppConfig":
        """Load config from disk, or return defaults."""
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                # Filter to only known fields
                known = {f.name for f in cls.__dataclass_fields__.values()}
                filtered = {k: v for k, v in data.items() if k in known}

                # An empty courses path is the ABSENCE of a choice, not a
                # choice. Configs written before the installer learned to
                # look — and every config migrated from a checkout — hold
                # "", and passing that through would override the default
                # forever: the app would keep saying "not configured" on a
                # machine where the courses were found at install time.
                # Dropping the key lets the field default run again.
                if not str(filtered.get("pcm_courses_dir", "")).strip():
                    filtered.pop("pcm_courses_dir", None)

                return cls(**filtered)
            except Exception:
                pass
        return cls()


config = AppConfig.load()

# ── .env overrides ─────────────────────────────────────
# Environment variables override config.json values.
# Supported: OLLAMA_URL, OLLAMA_MODEL, OLLAMA_NUM_CTX, OLLAMA_ENABLED
import os as _os
_env_file = PROJECT_ROOT / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file)
    except ImportError:
        pass  # python-dotenv not installed; .env loaded by run.bat instead

_env_overrides = {
    "OLLAMA_URL": ("ollama_url", str),
    "OLLAMA_MODEL": ("ollama_model", str),
    "OLLAMA_NUM_CTX": ("ollama_num_ctx", int),
    "OLLAMA_ENABLED": ("ollama_enabled", lambda v: v.lower() in ("1", "true", "yes")),
}
for env_key, (field, converter) in _env_overrides.items():
    val = _os.environ.get(env_key)
    if val is not None:
        try:
            setattr(config, field, converter(val))
        except (ValueError, TypeError):
            pass

# Migrate: ensure active sme_name is in sme_names list
if config.sme_name and config.sme_name not in config.sme_names:
    config.sme_names.append(config.sme_name)
    config.save()

