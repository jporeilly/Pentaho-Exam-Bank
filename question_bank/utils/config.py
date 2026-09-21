"""Settings management for the Question Bank app."""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

# The repo root, two levels above this package (question_bank/utils/config.py).
# Everything that needs a path off the repo root imports PROJECT_ROOT or
# ASSETS_DIR from here rather than re-deriving its own `parent.parent...`
# walk — four modules used to do that, and each one was a separate thing to
# get wrong the next time the tree moved.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = PROJECT_ROOT / "assets"
DB_DIR = ASSETS_DIR / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR = ASSETS_DIR / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = CONFIG_DIR / "config.json"
DB_PATH = DB_DIR / "question_bank.db"
BACKUP_DIR = DB_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# Migrate config from old locations
import shutil as _shutil

# 1. From ~/.question_bank/ (legacy)
_OLD_DIR = Path.home() / ".question_bank"
if _OLD_DIR.exists():
    _old_db = _OLD_DIR / "question_bank.db"
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


def _default_pcm_courses_dir() -> str:
    """Default to the sibling Pentaho Content Manager courses dir if present."""
    cand = PROJECT_ROOT.parent / "Pentaho-Content-Manager" / "courses"
    return str(cand) if cand.is_dir() else ""


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

    # MCP documentation servers
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
    output_folder: str = str(PROJECT_ROOT / "assets" / "questions")

    # PCM course source — folder holding Pentaho Content Manager courses
    # (each subdir a course with course.json + lab guide.md files).
    pcm_courses_dir: str = field(default_factory=_default_pcm_courses_dir)

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

