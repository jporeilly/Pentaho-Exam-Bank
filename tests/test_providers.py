"""Tests for core/providers.py — the LLM dispatch every call site goes through.

The existing generation tests cover prompt building and response parsing with
no model involved, so nothing exercised the dispatch itself. These do.
"""

import pytest

from exam_bank.core import ollama_client, providers
from exam_bank.utils.config import config


@pytest.fixture
def ollama(monkeypatch):
    """Active provider = ollama, with the transport captured instead of called."""
    monkeypatch.setattr(config, "ai_provider", "ollama")
    monkeypatch.setattr(config, "ollama_model", "llama3.2:3b")
    monkeypatch.setattr(config, "ollama_url", "http://localhost:11434")
    calls = []

    def fake_generate(**kwargs):
        calls.append(kwargs)
        return "generated"

    monkeypatch.setattr(ollama_client, "generate", fake_generate)
    return calls


class TestProviderSelection:
    def test_defaults_to_ollama(self, monkeypatch):
        monkeypatch.setattr(config, "ai_provider", "")
        assert providers.active_provider() == "ollama"

    def test_an_unknown_provider_falls_back_rather_than_raising(self, monkeypatch):
        """A hand-edited config must not stop the app from starting."""
        monkeypatch.setattr(config, "ai_provider", "definitely-not-a-provider")
        assert providers.active_provider() == "ollama"

    def test_model_for_each_provider(self, monkeypatch):
        monkeypatch.setattr(config, "ollama_model", "llama3.2:3b")
        monkeypatch.setattr(config, "anthropic_model", "claude-opus-4-8")
        monkeypatch.setattr(config, "openai_model", "gpt-4o")
        assert providers.model_for("ollama") == "llama3.2:3b"
        assert providers.model_for("anthropic") == "claude-opus-4-8"
        assert providers.model_for("openai") == "gpt-4o"


class TestOllamaDispatch:
    def test_generate_reaches_ollama_with_the_configured_model(self, ollama):
        assert providers.generate("Write a question.") == "generated"
        assert ollama[0]["model"] == "llama3.2:3b"
        assert ollama[0]["prompt"] == "Write a question."

    def test_an_explicit_model_overrides_the_configured_one(self, ollama):
        """This is how the model-comparison feature asks two models the same
        question — if the override stops working, Compare silently runs the
        same model twice and looks like it agrees with itself."""
        providers.generate("Prompt", model="qwen2.5:7b")
        assert ollama[0]["model"] == "qwen2.5:7b"

    def test_num_ctx_is_passed_through(self, ollama):
        """The context window must reach Ollama.

        The Content Editor's provider module sends no options at all and takes
        the model's ~4k default. Course sections are long; losing the
        configured window truncates them silently, which reads as a model that
        stopped paying attention rather than as a bug.
        """
        providers.generate("Prompt", num_ctx=65536)
        assert ollama[0]["num_ctx"] == 65536

    def test_base_url_falls_back_to_config(self, ollama):
        providers.generate("Prompt")
        assert ollama[0]["base_url"] == "http://localhost:11434"

    def test_a_missing_model_is_a_clear_error(self, monkeypatch):
        monkeypatch.setattr(config, "ai_provider", "ollama")
        monkeypatch.setattr(config, "ollama_model", "")
        with pytest.raises(providers.ProviderError, match="No Ollama model"):
            providers.generate("Prompt")

    def test_a_transport_failure_surfaces_as_a_provider_error(self, monkeypatch):
        """One error type leaves this module, so callers need one except."""
        monkeypatch.setattr(config, "ai_provider", "ollama")
        monkeypatch.setattr(config, "ollama_model", "llama3.2:3b")

        def boom(**kwargs):
            raise OSError("connection refused")

        monkeypatch.setattr(ollama_client, "generate", boom)
        with pytest.raises(providers.ProviderError, match="connection refused"):
            providers.generate("Prompt")


class TestCloudProviders:
    def test_anthropic_without_a_key_is_a_clear_error(self, monkeypatch):
        monkeypatch.setattr(config, "ai_provider", "anthropic")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(providers.ProviderError, match="ANTHROPIC_API_KEY"):
            providers.generate("Prompt")

    def test_openai_without_a_key_is_a_clear_error(self, monkeypatch):
        monkeypatch.setattr(config, "ai_provider", "openai")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(providers.ProviderError, match="OPENAI_API_KEY"):
            providers.generate("Prompt")


class TestKeysAreNeverExposed:
    def test_key_status_reports_booleans_only(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret-value")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        status = providers.key_status()
        assert status == {"anthropic": True, "openai": False}
        assert "sk-ant-secret-value" not in repr(status)

    def test_no_key_is_written_to_the_config(self, monkeypatch):
        """Keys come from the environment at call time and are never persisted.
        A key that reaches the config file gets committed by someone, eventually."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret-value")
        from dataclasses import fields

        names = {f.name for f in fields(config)}
        assert not any("key" in n.lower() or "secret" in n.lower() for n in names), (
            f"config has a credential-shaped field: {names}"
        )


class TestHealth:
    def test_reports_ollama_unreachable_rather_than_raising(self, monkeypatch):
        monkeypatch.setattr(config, "ai_provider", "ollama")
        monkeypatch.setattr(config, "ollama_model", "llama3.2:3b")
        monkeypatch.setattr(ollama_client, "list_models", lambda url, **kw: [])
        result = providers.health()
        assert result["ok"] is False
        assert "not reachable" in result["detail"]

    def test_reports_a_missing_cloud_key_without_calling_the_api(self, monkeypatch):
        monkeypatch.setattr(config, "ai_provider", "anthropic")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = providers.health()
        assert result["ok"] is False
        assert "ANTHROPIC_API_KEY" in result["detail"]
