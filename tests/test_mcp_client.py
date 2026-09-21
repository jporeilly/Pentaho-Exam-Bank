"""Tests for core/mcp_client.py — MCP protocol client."""

import json
from unittest.mock import patch, MagicMock

import pytest

from exam_bank.core.mcp_client import (
    check_connection, search_documentation, search_multiple_servers,
    _parse_sse_response, SearchResult,
)


class TestParseSSEResponse:
    def test_sse_format(self):
        body = 'data: {"result": "ok"}\n'
        result = _parse_sse_response(body)
        assert result == {"result": "ok"}

    def test_plain_json(self):
        body = '{"result": "ok"}'
        result = _parse_sse_response(body)
        assert result == {"result": "ok"}


class TestCheckConnection:
    def test_successful(self):
        response_data = json.dumps({"result": {"serverInfo": {}}}).encode()
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = response_data

        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert check_connection("http://localhost:3000") is True

    def test_failed(self):
        with patch("urllib.request.urlopen", side_effect=Exception("refused")):
            assert check_connection("http://localhost:3000") is False


class TestSearchDocumentation:
    def test_successful_search(self):
        response_data = json.dumps({
            "result": {
                "content": [
                    {"text": "Title: Test Doc\nLink: http://example.com\nContent: Documentation content here."},
                ]
            }
        }).encode()
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = response_data

        with patch("urllib.request.urlopen", return_value=mock_resp):
            results = search_documentation("test query", "http://localhost:3000")
            assert len(results) == 1
            assert results[0].title == "Test Doc"
            assert results[0].link == "http://example.com"
            assert "Documentation content" in results[0].content

    def test_empty_results(self):
        response_data = json.dumps({"result": {"content": []}}).encode()
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = response_data

        with patch("urllib.request.urlopen", return_value=mock_resp):
            results = search_documentation("test", "http://localhost:3000")
            assert results == []

    def test_connection_error(self):
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            results = search_documentation("test", "http://localhost:3000")
            assert results == []


class TestSearchMultipleServers:
    def test_combines_results(self):
        def mock_search(query, url, timeout=20.0):
            return [
                SearchResult(title=f"Doc from {url}", link=url, content="Content here"),
            ]

        with patch("exam_bank.core.mcp_client.search_documentation", side_effect=mock_search):
            servers = [
                {"name": "Server 1", "url": "http://srv1"},
                {"name": "Server 2", "url": "http://srv2"},
            ]
            result = search_multiple_servers("test", servers)
            assert "Server 1" in result
            assert "Server 2" in result

    def test_empty_servers(self):
        result = search_multiple_servers("test", [])
        assert result == ""

    def test_all_servers_fail(self):
        with patch("exam_bank.core.mcp_client.search_documentation",
                    side_effect=Exception("fail")):
            result = search_multiple_servers("test", [{"url": "http://bad"}])
            assert result == ""

    def test_respects_max_chars(self):
        def mock_search(query, url, timeout=20.0):
            return [
                SearchResult(title="Doc", link=url, content="A" * 1000),
            ]

        with patch("exam_bank.core.mcp_client.search_documentation", side_effect=mock_search):
            servers = [{"name": f"S{i}", "url": f"http://s{i}"} for i in range(10)]
            result = search_multiple_servers("test", servers, max_chars=500)
            assert len(result) <= 600  # some overhead for formatting
