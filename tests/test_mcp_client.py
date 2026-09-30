"""Tests for core/mcp_client.py — MCP protocol client."""

import json
from unittest.mock import patch, MagicMock

import pytest

from exam_bank.core.mcp_client import _parse_sse_response


class TestParseSSEResponse:
    def test_sse_format(self):
        body = 'data: {"result": "ok"}\n'
        result = _parse_sse_response(body)
        assert result == {"result": "ok"}

    def test_plain_json(self):
        body = '{"result": "ok"}'
        result = _parse_sse_response(body)
        assert result == {"result": "ok"}


# --- the raising layer: probe and search ------------------------------------------

import io
import urllib.error

from exam_bank.core import mcp_client
from exam_bank.core.mcp_client import McpError


def _replies(*bodies):
    """urlopen returning each body in turn, as GitBook does: SSE."""
    it = iter(bodies)

    def fake(req, timeout=0):
        resp = MagicMock()
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        resp.read.return_value = next(it).encode()
        return resp
    return fake


def _sse(message):
    return "event: message\ndata: " + json.dumps(message) + "\n\n"


class TestSse:
    def test_data_split_over_lines_is_joined(self):
        body = 'event: message\ndata: {"jsonrpc":"2.0",\ndata: "id":1,"result":{"ok":true}}\n\n'
        assert _parse_sse_response(body)["result"] == {"ok": True}

    def test_a_non_rpc_event_is_skipped(self):
        body = 'data: {"ping": 1}\n\n' + _sse({"jsonrpc": "2.0", "id": 1, "result": {"x": 1}})
        assert _parse_sse_response(body)["result"] == {"x": 1}


class TestProbe:
    def test_names_the_server_and_its_tools(self):
        replies = _replies(
            _sse({"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {"name": "docs", "title": "Pentaho MCP Server", "version": "0.27.2"}}}),
            _sse({"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "searchDocumentation"}, {"name": "getPage"}]}}),
        )
        with patch("urllib.request.urlopen", side_effect=replies):
            info = mcp_client.probe("https://docs.example/~gitbook/mcp")
        assert info["server"] == "Pentaho MCP Server"
        assert info["version"] == "0.27.2"
        assert info["tools"] == ["searchDocumentation", "getPage"]
        assert isinstance(info["ms"], int)

    @pytest.mark.parametrize("error, says", [
        (urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO()), "HTTP 404 Not Found"),
        (urllib.error.URLError("getaddrinfo failed"), "Could not reach the server: getaddrinfo failed"),
        (urllib.error.URLError(TimeoutError("timed out")), "No answer within 8 seconds"),
        (TimeoutError("timed out"), "No answer within 8 seconds"),
    ])
    def test_says_why_it_failed(self, error, says):
        with patch("urllib.request.urlopen", side_effect=error):
            with pytest.raises(McpError, match=says):
                mcp_client.probe("https://docs.example/~gitbook/mcp")

    def test_refuses_an_address_that_is_not_http(self):
        with pytest.raises(McpError, match="not an http"):
            mcp_client.probe("ftp://docs.example")

    def test_a_json_rpc_error_is_reported(self):
        body = _sse({"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "Method not found"}})
        with patch("urllib.request.urlopen", side_effect=_replies(body)):
            with pytest.raises(McpError, match="Method not found"):
                mcp_client.probe("https://docs.example/~gitbook/mcp")

    def test_a_reply_that_is_not_json_rpc_is_reported(self):
        with patch("urllib.request.urlopen", side_effect=_replies("<html>proxy login</html>")):
            with pytest.raises(McpError, match="not an MCP"):
                mcp_client.probe("https://docs.example/~gitbook/mcp")


class TestSearch:
    def _result(self, n):
        return _sse({"jsonrpc": "2.0", "id": 3, "result": {"content": [
            {"type": "text", "text": f"Title: Page {i}\nLink: https://docs.example/p{i}\nContent: Line one\nline two"}
            for i in range(n)
        ]}})

    def test_hits_are_parsed_and_cut_to_the_limit(self):
        """The server sends ten whatever it is asked, so the cut is ours."""
        with patch("urllib.request.urlopen", side_effect=_replies(self._result(10))):
            hits = mcp_client.search("ports", "https://docs.example/~gitbook/mcp", limit=3)
        assert [h.title for h in hits] == ["Page 0", "Page 1", "Page 2"]
        assert hits[0].link == "https://docs.example/p0"
        assert hits[0].content == "Line one line two"

    def test_only_the_query_is_sent(self):
        """The tool's schema is {query} with additionalProperties false."""
        sent = {}

        def fake(req, timeout=0):
            sent["body"] = json.loads(req.data)
            return _replies(self._result(1))(req)

        with patch("urllib.request.urlopen", side_effect=fake):
            mcp_client.search("ports", "https://docs.example/~gitbook/mcp")
        assert sent["body"]["method"] == "tools/call"
        assert sent["body"]["params"] == {"name": "searchDocumentation", "arguments": {"query": "ports"}}

    def test_a_tool_error_raises(self):
        body = _sse({"jsonrpc": "2.0", "id": 3, "result": {"isError": True, "content": []}})
        with patch("urllib.request.urlopen", side_effect=_replies(body)):
            with pytest.raises(McpError, match="search tool reported an error"):
                mcp_client.search("ports", "https://docs.example/~gitbook/mcp")
