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
        assert cfg.default_difficulty == "Medium"
        assert cfg.default_bloom_level == "Apply"

    def test_save_and_load(self, tmp_path):
        config_file = tmp_path / "config.json"
        with patch("exam_bank.utils.config.CONFIG_FILE", config_file):
            cfg = AppConfig(
                default_difficulty="Hard",
                sme_name="Ana",
                ollama_model="llama3.2",
                sme_names=["Alice", "Bob"],
            )
            cfg.save()
            assert config_file.exists()

            loaded = AppConfig.load()
            assert loaded.default_difficulty == "Hard"
            assert loaded.sme_name == "Ana"
            assert loaded.ollama_model == "llama3.2"
            assert loaded.sme_names == ["Alice", "Bob"]

    def test_load_ignores_unknown_fields(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "default_difficulty": "Easy",
            "unknown_field": "should be ignored",
            "another_unknown": 42,
            # Retired in 1.9.0 and still in every older config.json.
            "theme_color": "Purple", "dark_mode": False, "recent_files": [],
            "file_certifications": {}, "mermaid_enabled": False,
        }))
        with patch("exam_bank.utils.config.CONFIG_FILE", config_file):
            loaded = AppConfig.load()
            assert loaded.default_difficulty == "Easy"
            assert not hasattr(loaded, "unknown_field")
            assert not hasattr(loaded, "theme_color")

    def test_load_missing_file(self, tmp_path):
        config_file = tmp_path / "nonexistent.json"
        with patch("exam_bank.utils.config.CONFIG_FILE", config_file):
            loaded = AppConfig.load()
            assert loaded.default_difficulty == "Medium"  # default

    def test_load_corrupt_file(self, tmp_path):
        config_file = tmp_path / "corrupt.json"
        config_file.write_text("not valid json {{{")
        with patch("exam_bank.utils.config.CONFIG_FILE", config_file):
            loaded = AppConfig.load()
            assert loaded.default_difficulty == "Medium"  # default
