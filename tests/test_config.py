"""Tests for utils/config.py — AppConfig load/save."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from exam_bank.utils.config import AppConfig


class TestAppConfig:
    def test_defaults(self):
        cfg = AppConfig()
        assert cfg.ollama_url == "http://localhost:11434"
        assert cfg.ollama_enabled is True
        assert cfg.theme_color == "Slate"
        assert cfg.dark_mode is True
        assert cfg.default_difficulty == "Medium"
        assert cfg.default_bloom_level == "Apply"

    def test_save_and_load(self, tmp_path):
        config_file = tmp_path / "config.json"
        with patch("exam_bank.utils.config.CONFIG_FILE", config_file):
            cfg = AppConfig(
                theme_color="Blue",
                dark_mode=False,
                ollama_model="llama3.2",
                sme_names=["Alice", "Bob"],
            )
            cfg.save()
            assert config_file.exists()

            loaded = AppConfig.load()
            assert loaded.theme_color == "Blue"
            assert loaded.dark_mode is False
            assert loaded.ollama_model == "llama3.2"
            assert loaded.sme_names == ["Alice", "Bob"]

    def test_load_ignores_unknown_fields(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "theme_color": "Purple",
            "unknown_field": "should be ignored",
            "another_unknown": 42,
        }))
        with patch("exam_bank.utils.config.CONFIG_FILE", config_file):
            loaded = AppConfig.load()
            assert loaded.theme_color == "Purple"
            assert not hasattr(loaded, "unknown_field")

    def test_load_missing_file(self, tmp_path):
        config_file = tmp_path / "nonexistent.json"
        with patch("exam_bank.utils.config.CONFIG_FILE", config_file):
            loaded = AppConfig.load()
            assert loaded.theme_color == "Slate"  # default

    def test_load_corrupt_file(self, tmp_path):
        config_file = tmp_path / "corrupt.json"
        config_file.write_text("not valid json {{{")
        with patch("exam_bank.utils.config.CONFIG_FILE", config_file):
            loaded = AppConfig.load()
            assert loaded.theme_color == "Slate"  # default

    def test_mcp_servers_default(self):
        cfg = AppConfig()
        assert cfg.mcp_servers == []
        assert cfg.mcp_enabled is False

    def test_file_certifications(self):
        cfg = AppConfig(file_certifications={"deck.pptx": "cert-123"})
        assert cfg.file_certifications["deck.pptx"] == "cert-123"

    def test_recent_files(self):
        cfg = AppConfig(recent_files=["/path/to/file.pptx"])
        assert len(cfg.recent_files) == 1
