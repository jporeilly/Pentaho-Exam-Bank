"""Tests for core/ollama_client.py — connection check, model listing, image encoding."""

import json
import base64
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import BytesIO

import pytest

from exam_bank.core.ollama_client import (
    check_connection, list_models, _encode_image, OllamaModel,
)


class TestCheckConnection:
    def test_successful_connection(self):
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert check_connection("http://localhost:11434") is True

    def test_failed_connection(self):
        with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
            assert check_connection("http://localhost:11434") is False


class TestListModels:
    def test_successful_list(self):
        response_data = json.dumps({
            "models": [
                {"name": "llama3.2", "size": 3000000000},
                {"name": "mistral", "size": 7000000000},
            ]
        }).encode()

        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = response_data

        with patch("urllib.request.urlopen", return_value=mock_resp):
            models = list_models()
            assert len(models) == 2
            assert models[0].name == "llama3.2"
            assert models[1].name == "mistral"

    def test_empty_models(self):
        response_data = json.dumps({"models": []}).encode()
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = response_data

        with patch("urllib.request.urlopen", return_value=mock_resp):
            models = list_models()
            assert models == []

    def test_connection_error(self):
        with patch("urllib.request.urlopen", side_effect=Exception("Timeout")):
            models = list_models()
            assert models == []


class TestEncodeImage:
    def test_encode_existing_file(self, tmp_path):
        img_path = tmp_path / "test.png"
        img_path.write_bytes(b"fake png data")
        result = _encode_image(str(img_path))
        assert result is not None
        decoded = base64.b64decode(result)
        assert decoded == b"fake png data"

    def test_encode_nonexistent_file(self):
        result = _encode_image("/nonexistent/path/image.png")
        assert result is None

    def test_encode_empty_path(self):
        result = _encode_image("")
        assert result is None


class TestOllamaModel:
    def test_model_creation(self):
        model = OllamaModel(name="llama3.2", size=3000000000)
        assert model.name == "llama3.2"
        assert model.size == 3000000000

    def test_model_defaults(self):
        model = OllamaModel(name="test")
        assert model.size == 0
