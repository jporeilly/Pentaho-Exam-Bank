"""MCP (Model Context Protocol) client for GitBook documentation servers."""

import json
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SearchResult:
    title: str
    link: str
    content: str


def _parse_sse_response(body: str) -> dict:
    for line in body.split("\n"):
        if line.startswith("data: "):
            return json.loads(line[6:])
    return json.loads(body)


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


def check_connection(mcp_url: str, timeout: float = 5.0) -> bool:
    try:
        result = _post_jsonrpc(mcp_url, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "question-bank", "version": "1.0"},
        }, timeout=timeout)
        return "result" in result
    except Exception:
        return False


def search_documentation(query: str, mcp_url: str, timeout: float = 20.0) -> List[SearchResult]:
    try:
        data = _post_jsonrpc(mcp_url, "tools/call", {
            "name": "searchDocumentation",
            "arguments": {"query": query},
        }, msg_id=3, timeout=timeout)
        results = []
        for item in data.get("result", {}).get("content", []):
            text = item.get("text", "")
            if not text.strip():
                continue
            title, link, content = "", "", ""
            for line in text.split("\n"):
                if line.startswith("Title: "):
                    title = line[7:].strip()
                elif line.startswith("Link: "):
                    link = line[6:].strip()
                elif line.startswith("Content: "):
                    content = line[9:].strip()
                elif content and line.strip():
                    content += " " + line.strip()
            if title or content:
                results.append(SearchResult(title=title, link=link, content=content))
        return results
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
