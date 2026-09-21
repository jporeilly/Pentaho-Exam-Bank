"""LLM provider dispatch — Ollama (local), Anthropic, or OpenAI.

Everything that asks a model for text goes through ``generate`` / ``chat``
here, so the choice of provider is made in one place instead of at each of the
sixteen call sites that used to name Ollama directly.

**API keys are never stored.** They are read from ``ANTHROPIC_API_KEY`` /
``OPENAI_API_KEY`` at call time, so this app never persists a credential. The
non-secret preferences — which provider is active, and each provider's model —
live in the app's existing config.

Two deliberate differences from the Content Editor's version of this module,
which this one otherwise mirrors:

* **Settings come from ``utils.config``, not a second settings file.** The
  editor keeps its own ``settings.json`` because it has nothing else; this app
  already has a config with the Ollama URL, model and context size in it. A
  verbatim copy would have meant two files disagreeing about the same thing.

* **``num_ctx`` is preserved.** The editor sends Ollama no ``options`` at all
  and takes whatever default the model ships with, which is around 4k. This
  app sends a configured window (8192 by default, and higher on machines that
  can afford it). Course sections are long; dropping this would truncate them
  silently, which looks like a model that has stopped paying attention rather
  than like a bug.
"""

from __future__ import annotations

import os
from typing import List, Optional

from . import ollama_client
from ..utils.config import config

PROVIDERS = ("ollama", "anthropic", "openai")

# Shown when a caller gives no system prompt of its own.
DEFAULT_SYSTEM_PROMPT = ollama_client.DEFAULT_SYSTEM_PROMPT


class ProviderError(Exception):
    """Any provider misconfiguration or call failure."""


def active_provider() -> str:
    name = (getattr(config, "ai_provider", "") or "ollama").strip().lower()
    return name if name in PROVIDERS else "ollama"


def key_status() -> dict:
    """Which provider keys are present in the environment — booleans only.
    The values are never returned, logged or written anywhere."""
    return {
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
    }


def model_for(provider: str) -> str:
    if provider == "ollama":
        return (config.ollama_model or "").strip()
    if provider == "anthropic":
        return (getattr(config, "anthropic_model", "") or "claude-opus-4-8").strip()
    if provider == "openai":
        return (getattr(config, "openai_model", "") or "gpt-4o").strip()
    return ""


# ── Cloud providers ─────────────────────────────────────────────────


def _anthropic_chat(model: str, messages: List[dict], system: str, timeout: float) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ProviderError("ANTHROPIC_API_KEY is not set in the environment.")
    try:
        from anthropic import Anthropic
    except ImportError:
        raise ProviderError("The `anthropic` package isn't installed: pip install anthropic")
    try:
        client = Anthropic(api_key=key, timeout=timeout)
        # No temperature — removed on Opus 4.7/4.8 and Sonnet 5 (returns 400).
        resp = client.messages.create(
            model=model, max_tokens=8000, system=system, messages=messages,
        )
        return "".join(
            getattr(b, "text", "") for b in resp.content
            if getattr(b, "type", None) == "text"
        )
    except ProviderError:
        raise
    except Exception as e:  # noqa: BLE001 — surface any SDK/API error to the UI
        raise ProviderError(f"Anthropic request failed: {e}")


def _openai_chat(model: str, messages: List[dict], system: str, timeout: float) -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ProviderError("OPENAI_API_KEY is not set in the environment.")
    try:
        from openai import OpenAI
    except ImportError:
        raise ProviderError("The `openai` package isn't installed: pip install openai")
    try:
        client = OpenAI(api_key=key, timeout=timeout)
        full = ([{"role": "system", "content": system}] if system else []) + messages
        try:
            resp = client.chat.completions.create(model=model, messages=full, max_tokens=4000)
        except Exception:
            # Newer models reject `max_tokens` for `max_completion_tokens`;
            # retry once with the default cap rather than guessing which.
            resp = client.chat.completions.create(model=model, messages=full)
        return resp.choices[0].message.content or ""
    except ProviderError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ProviderError(f"OpenAI request failed: {e}")


# ── Dispatch ────────────────────────────────────────────────────────


def generate(
    prompt: str,
    model: str = "",
    system: str = "",
    base_url: str = "",
    timeout: float = 120.0,
    num_ctx: int = 0,
    num_predict: int = 0,
    images: Optional[List[str]] = None,
) -> str:
    """One completion from the active provider.

    ``model`` overrides the active provider's configured model — that is how
    the model-comparison feature asks two models the same question. ``base_url``
    and ``num_ctx`` apply to Ollama only; the cloud providers ignore them.

    ``images`` is Ollama-only and goes away with PPTX generation in 0.2.0.
    """
    provider = active_provider()
    system = system or DEFAULT_SYSTEM_PROMPT
    chosen = (model or "").strip() or model_for(provider)

    if provider == "ollama":
        if not chosen:
            raise ProviderError(
                "No Ollama model is configured. Pick one in Settings, or pull "
                "one with `ollama pull llama3.2:3b`."
            )
        try:
            return ollama_client.generate(
                prompt=prompt,
                model=chosen,
                system=system,
                base_url=base_url or config.ollama_url,
                timeout=timeout,
                num_ctx=num_ctx,
                num_predict=num_predict,
                images=images,
            )
        except Exception as e:  # noqa: BLE001 — one error type out of this module
            raise ProviderError(f"Ollama request failed: {e}")

    messages = [{"role": "user", "content": prompt}]
    if provider == "anthropic":
        return _anthropic_chat(chosen, messages, system, timeout)
    if provider == "openai":
        return _openai_chat(chosen, messages, system, timeout)
    raise ProviderError(f"Unknown provider '{provider}'")


def chat(
    messages: List[dict],
    system: str = "",
    model: str = "",
    base_url: str = "",
    timeout: float = 120.0,
) -> str:
    """Multi-turn chat from the active provider. ``messages`` is a list of
    ``{role, content}`` with roles 'user' / 'assistant'."""
    provider = active_provider()
    system = system or DEFAULT_SYSTEM_PROMPT
    chosen = (model or "").strip() or model_for(provider)

    if provider == "ollama":
        if not chosen:
            raise ProviderError("No Ollama model is configured.")
        try:
            return ollama_client.chat(
                messages=messages,
                model=chosen,
                system=system,
                base_url=base_url or config.ollama_url,
                timeout=timeout,
            )
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"Ollama request failed: {e}")
    if provider == "anthropic":
        return _anthropic_chat(chosen, messages, system, timeout)
    if provider == "openai":
        return _openai_chat(chosen, messages, system, timeout)
    raise ProviderError(f"Unknown provider '{provider}'")


def health() -> dict:
    """Connection status for the ACTIVE provider. No paid API call is made for
    the cloud providers — key presence and SDK import only."""
    provider = active_provider()
    model = model_for(provider)
    if provider == "ollama":
        url = config.ollama_url
        models = [m.name for m in ollama_client.list_models(url)]
        ok = bool(models)
        return {
            "provider": "ollama", "ok": ok, "model": model, "models": models,
            "detail": "connected" if ok else f"not reachable at {url}",
        }
    if not key_status().get(provider):
        env = "ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"
        return {"provider": provider, "ok": False, "model": model, "detail": f"{env} not set"}
    package = "anthropic" if provider == "anthropic" else "openai"
    try:
        __import__(package)
    except ImportError:
        return {"provider": provider, "ok": False, "model": model,
                "detail": f"`{package}` package not installed"}
    return {"provider": provider, "ok": True, "model": model, "detail": "key detected"}
