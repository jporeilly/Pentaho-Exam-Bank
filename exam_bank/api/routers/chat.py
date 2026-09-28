"""AI Chat, and the Pentaho docs connection it depends on.

``POST /api/chat`` answers one turn of a conversation from two sources: this
app's documentation and docs.pentaho.com (through GitBook's MCP server). The
grounding rules are in ``core/chat.py``; this is the I/O around them.

``GET /api/docs-mcp/status`` is what Settings shows: whether the docs server is
answering, who it is and which tools it offers.

``POST /api/open-url`` opens a web page in the system browser: a Pentaho docs
source under an answer, or a link in the documentation (GitHub, ollama.com).
The page is served into a webview that has no Tauri APIs and no new-window
handler, where a link with ``target="_blank"`` goes nowhere, so the backend
opens it. ``https://`` only: a ``file:`` URL or another scheme would run
whatever Windows associates with it, which is not something to leave on a
port, even a loopback one. (A browser page on another origin cannot reach
this anyway: a JSON POST needs a CORS preflight, which only localhost passes.)
"""

from __future__ import annotations

import time
import webbrowser
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...core import chat as chat_core
from ...core import docs as docs_core
from ...core import mcp_client
from ...core.providers import ProviderError, active_provider, chat, model_for
from ...utils.config import config

router = APIRouter(tags=["chat"])

#: How long a docs search may take before the answer goes ahead without it.
#: GitBook answers in under a second; this is for the network that doesn't.
MCP_TIMEOUT = 15.0


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[Turn] = Field(..., min_length=1)
    appDocs: bool = True
    pentahoDocs: bool = True


def _docs_host() -> str:
    return (urlparse(config.docs_mcp_url).hostname or "docs.pentaho.com").lower()


@router.post("/api/chat")
def answer(body: ChatRequest) -> dict[str, Any]:
    """One turn: search both sources, then answer from what they found."""
    *earlier, last = [m.model_dump() for m in body.messages]
    question = last["content"].strip()
    if last["role"] != "user" or not question:
        raise HTTPException(400, "The last message must be a question.")
    if not body.appDocs and not body.pentahoDocs:
        raise HTTPException(400, "Choose at least one source to answer from.")

    query = chat_core.retrieval_query(earlier, question)
    host = _docs_host()
    grounding: dict[str, Any] = {
        "app": {"searched": body.appDocs, "found": 0},
        "pentaho": {"searched": False, "found": 0, "host": host},
    }
    sources: list[chat_core.Source] = []

    if body.appDocs:
        found = docs_core.context_for(
            query, docs_core.load_sections(),
            budget=chat_core.APP_BUDGET, limit=chat_core.APP_SECTIONS,
        )
        sources += chat_core.app_sources(found)
        grounding["app"]["found"] = len(found)

    if body.pentahoDocs:
        if not config.docs_mcp_enabled:
            grounding["pentaho"]["reason"] = "The Pentaho docs connection is off in Settings."
        else:
            grounding["pentaho"]["searched"] = True
            started = time.monotonic()
            try:
                hits = mcp_client.search(
                    query, config.docs_mcp_url,
                    limit=chat_core.PENTAHO_HITS, timeout=MCP_TIMEOUT,
                )
            except mcp_client.McpError as e:
                grounding["pentaho"]["error"] = str(e)
            else:
                sources += chat_core.pentaho_sources(hits)
                grounding["pentaho"]["found"] = len(hits)
            grounding["pentaho"]["ms"] = round((time.monotonic() - started) * 1000)

    if not sources:
        # Deliberately not a model call. Asked with nothing to read, the model
        # answers from what it knows about tools in general, which reads
        # exactly like an answer about this one.
        return {
            "answered": False,
            "answer": _not_covered(body, grounding, host),
            "sources": [],
            "grounding": grounding,
        }

    try:
        reply = chat(
            chat_core.build_messages(earlier, question, sources),
            system=chat_core.SYSTEM,
            base_url=config.ollama_url,
            timeout=float(config.generation_timeout_seconds or 600),
            num_ctx=int(getattr(config, "ollama_num_ctx", 0) or 0),
        )
    except ProviderError as e:
        # The provider's own message names the thing to fix — an absent key, a
        # model that was never pulled — so it is passed through.
        raise HTTPException(503, str(e)) from e

    cited = chat_core.cited_ids(reply)
    return {
        "answered": True,
        "answer": reply.strip(),
        "sources": [s.to_json(cited) for s in sources],
        "grounding": grounding,
        "provider": active_provider(),
        "model": model_for(active_provider()),
    }


def _not_covered(body: ChatRequest, grounding: dict[str, Any], host: str) -> str:
    """Why there is no answer, naming each source and what happened to it."""
    pentaho = grounding["pentaho"]
    if not body.pentahoDocs:
        why = "Nothing in this app's documentation covers that."
    elif pentaho.get("error"):
        why = f"{host} could not be searched: {pentaho['error']}"
        if body.appDocs:
            why = "Nothing in this app's documentation covers that, and " + why
    elif pentaho.get("reason"):
        why = f"The {host} connection is off in Settings."
        if body.appDocs:
            why = "Nothing in this app's documentation covers that. " + why
    elif body.appDocs:
        why = f"Neither this app's documentation nor {host} has anything on that."
    else:
        why = f"{host} has nothing on that."
    return why + " Try different words: nothing is guessed from outside the documentation."


@router.get("/api/docs-mcp/status")
def docs_mcp_status(url: str = "") -> dict[str, Any]:
    """Whether the docs server answers. ``url`` tests an address before it is
    saved; without it, the saved one is tested."""
    target = (url or config.docs_mcp_url).strip()
    base = {"enabled": config.docs_mcp_enabled, "url": target}
    try:
        info = mcp_client.probe(target)
    except mcp_client.McpError as e:
        return {**base, "ok": False, "server": "", "version": "", "tools": [],
                "ms": None, "searchTool": False, "error": str(e)}
    return {**base, "ok": True, **info,
            "searchTool": mcp_client.SEARCH_TOOL in info["tools"], "error": ""}


class OpenUrl(BaseModel):
    url: str


@router.post("/api/open-url", status_code=204)
def open_url(body: OpenUrl) -> None:
    """Open an https page in the system browser."""
    parsed = urlparse(body.url.strip())
    if parsed.scheme != "https" or not parsed.hostname:
        raise HTTPException(400, "Only https:// pages are opened from here.")
    webbrowser.open(parsed.geturl())
