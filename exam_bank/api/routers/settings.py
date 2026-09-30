"""Read and change the app's configuration.

Two things this deliberately will not do.

It **never handles an API key.** Keys are read from ``ANTHROPIC_API_KEY`` /
``OPENAI_API_KEY`` at call time and this app has never persisted one; a
settings form that accepted a key would write it into ``config.json``, which
is a plain file in the project directory. The UI is told only *whether* a key
is present, as a boolean, so an author can see why a provider is unavailable
without the value ever crossing the wire.

It **writes only an allowlist.** ``config`` also holds state the app manages
for itself — the recent-files list, the map from a deck to its certification,
the MCP server list — and ``config.save()`` writes the whole dataclass. A
browser able to PUT arbitrary keys into that could quietly break the mapping
between a source file and its questions, which nothing would report.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...core import auto_backup, auto_export, gpu_advice
from ...core.bank import BLOOM_LEVELS, DIFFICULTIES
from ...core.exporter import FORMATS
from ...core.providers import key_status
from ...utils.config import CONFIG_FILE, DB_PATH, config

router = APIRouter(tags=["settings"])

PROVIDERS = ("ollama", "anthropic", "openai")
PAGE_SIZES = (10, 25, 50, 100)

#: Environment variables that override a config field at startup. A field
#: named here cannot be changed from the UI in any lasting way: the value is
#: written to config.json and then overridden again on the next load, so the
#: author sets it, sees it saved, restarts, and finds it reverted. Reported so
#: the field can be shown as governed elsewhere rather than silently ignored.
ENV_OVERRIDES = {
    "ollama_url": "OLLAMA_URL",
    "ollama_model": "OLLAMA_MODEL",
    "ollama_num_ctx": "OLLAMA_NUM_CTX",
    "ollama_enabled": "OLLAMA_ENABLED",
}


def _directory(value: str, label: str) -> str:
    """A path that must already exist, or a message naming it.

    Not created on the author's behalf: a typo would otherwise produce an
    empty directory that looks configured and lists no courses, which is the
    failure this app has already had once.
    """
    text = (value or "").strip()
    if not text:
        return ""
    if not Path(text).is_dir():
        raise HTTPException(400, f"{label} does not exist: {text}")
    return text


def _web_address(value: Any, label: str) -> str:
    """An http(s) URL, or a message saying it is not one. An empty value is
    refused too: the switch beside it is how the connection is turned off."""
    text = str(value or "").strip()
    if not text.lower().startswith(("http://", "https://")) or len(text) < 12:
        raise HTTPException(400, f"{label} must be an http:// or https:// address, not {text!r}.")
    return text


def _fraction(value: Any, label: str) -> float:
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise HTTPException(
            400, f"{label} is a similarity score between 0 and 1, not {number:g}."
        )
    return number


def _one_of(value: Any, allowed, label: str):
    if value not in allowed:
        raise HTTPException(
            400, f"{label} must be one of {', '.join(map(str, allowed))}, not {value!r}."
        )
    return value


def _between(value: Any, low: int, high: int, label: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise HTTPException(400, f"{label} must be a whole number, not {value!r}.")
    if not low <= number <= high:
        raise HTTPException(400, f"{label} must be between {low} and {high}, not {number}.")
    return number


#: field -> how to validate and coerce it. The allowlist and the validation
#: are one table, so a field cannot be made writable without saying what a
#: valid value is.
EDITABLE: dict[str, Callable[[Any], Any]] = {
    "sme_name": lambda v: str(v).strip(),
    "ai_provider": lambda v: _one_of(v, PROVIDERS, "The AI provider"),
    "anthropic_model": lambda v: str(v).strip(),
    "openai_model": lambda v: str(v).strip(),
    "ollama_url": lambda v: str(v).strip(),
    "ollama_model": lambda v: str(v).strip(),
    "ollama_enabled": bool,
    "ollama_num_ctx": lambda v: max(0, int(v)),
    "docs_mcp_enabled": bool,
    "docs_mcp_url": lambda v: _web_address(v, "The Pentaho docs MCP server"),
    "pcm_courses_dir": lambda v: _directory(v, "The Content Manager courses directory"),
    "output_folder": lambda v: str(v).strip(),
    "duplicate_threshold": lambda v: _fraction(v, "The duplicate threshold"),
    "validation_threshold": lambda v: _fraction(v, "The validation threshold"),
    "questions_per_page": lambda v: _one_of(int(v), PAGE_SIZES, "The page size"),
    "default_difficulty": lambda v: _one_of(v, DIFFICULTIES, "The default difficulty"),
    "default_bloom_level": lambda v: _one_of(v, BLOOM_LEVELS, "The default Bloom level"),
    "auto_export_on_save": bool,
    "default_export_format": lambda v: _one_of(v, list(FORMATS), "The default export format"),
    "auto_backup_enabled": bool,
    "auto_backup_interval_hours": lambda v: _between(v, 1, 168, "Hours between backups"),
    "auto_backup_max_count": lambda v: _between(v, 1, 100, "The number of automatic backups kept"),
}


def _current() -> dict[str, Any]:
    """Everything the settings pane needs, and nothing it must not have."""
    overridden = [
        field for field, env in ENV_OVERRIDES.items() if os.environ.get(env) is not None
    ]
    return {
        "settings": {field: getattr(config, field) for field in EDITABLE},
        # Booleans only. The values are never read here, let alone sent.
        "providerKeys": key_status(),
        "envOverridden": overridden,
        "envNames": ENV_OVERRIDES,
        "choices": {
            "providers": list(PROVIDERS),
            "difficulties": list(DIFFICULTIES),
            "bloomLevels": list(BLOOM_LEVELS),
            "pageSizes": list(PAGE_SIZES),
            "exportFormats": [{"format": k, "label": v[3]} for k, v in FORMATS.items()],
        },
        # What the two background features last did, and where auto-export
        # writes now - so the author can see them working, or why not.
        "autoExport": {"target": str(auto_export.target()), **auto_export.last},
        "autoBackup": dict(auto_backup.last),
        # Where the app is reading and writing. Shown, never set: moving the
        # database from a settings form would leave the running app holding a
        # handle to the old one.
        "paths": {
            "database": str(DB_PATH),
            "config": str(CONFIG_FILE),
        },
    }


@router.get("/api/settings")
def read_settings() -> dict[str, Any]:
    return _current()


class SettingsUpdate(BaseModel):
    """Only the fields being changed. Anything absent is left alone."""

    settings: dict[str, Any]


@router.put("/api/settings")
def update_settings(body: SettingsUpdate) -> dict[str, Any]:
    """Change the named settings, or change nothing and say why.

    Validated and applied as a set: a request naming one bad value changes
    none of the others. A half-applied settings save is the kind of thing an
    author only notices later, when the half that did not apply matters.
    """
    unknown = sorted(set(body.settings) - set(EDITABLE))
    if unknown:
        raise HTTPException(
            400,
            f"Not a setting this app will change: {', '.join(unknown)}. "
            "Some configuration is managed by the app itself.",
        )

    coerced: dict[str, Any] = {}
    for field, raw in body.settings.items():
        try:
            coerced[field] = EDITABLE[field](raw)
        except HTTPException:
            raise
        except (TypeError, ValueError) as e:
            raise HTTPException(400, f"{field}: {e}") from e

    for field, value in coerced.items():
        setattr(config, field, value)

    # Keep the active SME in the saved list, matching what the app does at
    # startup — otherwise a name typed here is forgotten on the next restart.
    name = getattr(config, "sme_name", "")
    if name and name not in config.sme_names:
        config.sme_names.append(name)

    config.save()
    return _current()


@router.get("/api/settings/gpu")
def gpu() -> dict[str, Any]:
    """What this machine's GPUs can run, for choosing an Ollama model.
    Reads nvidia-smi and Ollama; changes nothing. See core/gpu_advice."""
    return gpu_advice.advise(config.ollama_url, config.ollama_model)
