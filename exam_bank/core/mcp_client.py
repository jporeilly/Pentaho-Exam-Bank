"""MCP (Model Context Protocol) client for GitBook documentation servers.

docs.pentaho.com is published with GitBook, which serves an MCP endpoint at
``/~gitbook/mcp``. AI Chat calls its ``searchDocumentation`` tool once per
question, and Settings probes the server to say whether it is answering.

**Called from the backend, never the window.** GitBook's endpoint sends no
CORS headers (checked 2026-09-28: a preflight gets 204 and no
``Access-Control-Allow-*``), so a browser fetch from the app's page is
refused before it leaves. Python has no such rule — which is also why the
Content Editor's copy of this client works and the Content Manager's webview
one does not.

**Stateless.** One JSON-RPC POST per call, no ``initialize`` handshake and no
session id: GitBook accepts a bare ``tools/call`` (checked live, and the
Content Editor relies on the same). ``probe`` does send ``initialize``, because
that is what reports the server's name and version.

Replies come as JSON or as Server-Sent Events (GitBook sends SSE: an
``event: message`` line and one ``data:`` line). Both are handled, including a
``data`` value split over several lines, which the SSE format allows.

Two layers: ``probe`` and ``search`` RAISE :class:`McpError` with a sentence a
person can act on, for callers that must say what went wrong; the older
``check_connection`` / ``search_documentation`` swallow everything and return
False / [] for the callers written against them.
"""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import List

#: The search tool GitBook's MCP server offers. Its schema is ``{query}`` only
#: (``additionalProperties: false``), so nothing else is sent.
SEARCH_TOOL = "searchDocumentation"

PROTOCOL_VERSION = "2025-03-26"


class McpError(Exception):
    """The server could not be reached, or answered with an error."""


@dataclass
class SearchResult:
    title: str
    link: str
    content: str


def _parse_sse_response(body: str) -> dict:
    """The first JSON-RPC message in an SSE stream, or the body as JSON.

    SSE events are separated by a blank line, and an event's ``data`` may span
    several ``data:`` lines that join with newlines.
    """
    if "data:" not in body:
        return json.loads(body)
    data: list[str] = []
    for line in body.splitlines() + [""]:
        if line.startswith("data:"):
            # One leading space is the separator, and only one: the spec.
            data.append(line[6:] if line[5:6] == " " else line[5:])
        elif not line.strip() and data:
            try:
                message = json.loads("\n".join(data))
            except json.JSONDecodeError:
                data = []
                continue
            if isinstance(message, dict) and ("result" in message or "error" in message):
                return message
            data = []
    raise json.JSONDecodeError("no JSON-RPC message in the event stream", body, 0)


def _post_jsonrpc(url: str, method: str, params: dict, msg_id: int = 1,
                  timeout: float = 15.0) -> dict:
    payload = json.dumps({
        "jsonrpc": "2.0", "id": msg_id, "method": method, "params": params,
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return _parse_sse_response(resp.read().decode())


def _call(url: str, method: str, params: dict, msg_id: int, timeout: float) -> dict:
    """One request, with every failure turned into an :class:`McpError`."""
    if not url.lower().startswith(("http://", "https://")):
        raise McpError(f"'{url}' is not an http(s) address.")
    try:
        message = _post_jsonrpc(url, method, params, msg_id=msg_id, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise McpError(f"The server answered HTTP {e.code} {e.reason}.") from e
    except urllib.error.URLError as e:
        reason = e.reason
        if isinstance(reason, (socket.timeout, TimeoutError)):
            raise McpError(f"No answer within {timeout:g} seconds.") from e
        raise McpError(f"Could not reach the server: {reason}.") from e
    except (socket.timeout, TimeoutError) as e:
        raise McpError(f"No answer within {timeout:g} seconds.") from e
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise McpError("The server's reply was not an MCP (JSON-RPC) message.") from e
    except OSError as e:
        raise McpError(f"Could not reach the server: {e}.") from e
    if "error" in message:
        err = message.get("error") or {}
        raise McpError(f"The server returned an error: {err.get('message', err)}.")
    return message.get("result") or {}


def probe(url: str, timeout: float = 8.0) -> dict:
    """Whether the server answers, who it is, and which tools it offers.

    ``initialize`` then ``tools/list``. Returns ``{server, version, tools,
    ms}``; raises :class:`McpError`.
    """
    started = time.monotonic()
    init = _call(url, "initialize", {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "pentaho-exam-bank", "version": "1"},
    }, 1, timeout)
    listed = _call(url, "tools/list", {}, 2, timeout)
    info = init.get("serverInfo") or {}
    return {
        "server": info.get("title") or info.get("name") or "",
        "version": info.get("version") or "",
        "tools": [t.get("name", "") for t in listed.get("tools") or [] if t.get("name")],
        "ms": round((time.monotonic() - started) * 1000),
    }


def _hits(result: dict) -> List[SearchResult]:
    """GitBook's ``Title: / Link: / Content:`` text blocks, one per hit."""
    out: List[SearchResult] = []
    for item in result.get("content", []) or []:
        text = item.get("text", "") if isinstance(item, dict) else ""
        if not text.strip():
            continue
        title, link, content = "", "", ""
        for line in text.split("\n"):
            if line.startswith("Title: ") and not content:
                title = line[7:].strip()
            elif line.startswith("Link: ") and not content:
                link = line[6:].strip()
            elif line.startswith("Content: ") and not content:
                content = line[9:].strip()
            elif content and line.strip():
                content += " " + line.strip()
        if title or content:
            out.append(SearchResult(title=title, link=link, content=content))
    return out


def search(query: str, url: str, limit: int = 5, timeout: float = 15.0) -> List[SearchResult]:
    """The server's best hits for ``query``, at most ``limit`` of them.

    Raises :class:`McpError`. The server returns ten and ignores any limit it
    is sent, so the cut is made here.
    """
    result = _call(url, "tools/call", {
        "name": SEARCH_TOOL,
        "arguments": {"query": query},
    }, 3, timeout)
    if result.get("isError"):
        raise McpError("The search tool reported an error.")
    return _hits(result)[:limit]


# --- the original, error-swallowing interface --------------------------------


def check_connection(mcp_url: str, timeout: float = 5.0) -> bool:
    try:
        result = _post_jsonrpc(mcp_url, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "exam-bank", "version": "1.0"},
        }, timeout=timeout)
        return "result" in result
    except Exception:
        return False


def search_documentation(query: str, mcp_url: str, timeout: float = 20.0) -> List[SearchResult]:
    try:
        data = _post_jsonrpc(mcp_url, "tools/call", {
            "name": SEARCH_TOOL,
            "arguments": {"query": query},
        }, msg_id=3, timeout=timeout)
        return _hits(data.get("result", {}) or {})
    except Exception:
        return []


def search_multiple_servers(query: str, servers: list, max_results: int = 4,
                            max_chars: int = 3000, timeout: float = 20.0) -> str:
    all_results: List[SearchResult] = []
    for server in servers:
        url = server.get("url", "")
        name = server.get("name", url)
        if not url:
            continue
        try:
            results = search_documentation(query, url, timeout=timeout)
            for r in results:
                r.title = f"{r.title} [{name}]"
            all_results.extend(results)
        except Exception:
            pass
    if not all_results:
        return ""
    parts, total = [], 0
    for r in all_results[:max_results]:
        snippet = r.content[:600] if len(r.content) > 600 else r.content
        entry = f"[{r.title}]({r.link})\n{snippet}"
        if total + len(entry) > max_chars:
            break
        parts.append(entry)
        total += len(entry)
    if not parts:
        return ""
    return "--- Relevant Documentation ---\n" + "\n\n".join(parts) + "\n--- End Documentation ---"


def search_multiple_servers_structured(query: str, servers: list, max_results: int = 4,
                                       max_chars: int = 3000, timeout: float = 20.0) -> list:
    """Like search_multiple_servers but returns structured results.

    Returns list of dicts: [{"title": ..., "link": ..., "content": ..., "server": ...}]
    """
    all_results = []
    for server in servers:
        url = server.get("url", "")
        name = server.get("name", url)
        if not url:
            continue
        try:
            results = search_documentation(query, url, timeout=timeout)
            for r in results:
                all_results.append({
                    "title": r.title,
                    "link": r.link,
                    "content": r.content,
                    "server": name,
                })
        except Exception:
            pass
    # Truncate to max_results and max_chars
    out, total = [], 0
    for r in all_results[:max_results]:
        snippet = r["content"][:600] if len(r["content"]) > 600 else r["content"]
        if total + len(snippet) > max_chars:
            break
        out.append({**r, "content": snippet})
        total += len(snippet)
    return out
