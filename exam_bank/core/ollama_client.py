"""Ollama local LLM client for AI-powered question generation."""

import base64
import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncGenerator, List, Optional, Generator

try:
    import httpx  # optional; needed only for async_ functions
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False


@dataclass
class OllamaModel:
    name: str
    size: int = 0


DEFAULT_URL = "http://localhost:11434"


def _resolve_num_ctx(num_ctx: int) -> int:
    """Resolve num_ctx: if 0, read from config; if still 0, return 0 (Ollama default)."""
    if num_ctx > 0:
        return num_ctx
    try:
        from ..utils.config import config
        return config.ollama_num_ctx or 0
    except Exception:
        return 0

DEFAULT_SYSTEM_PROMPT = (
    "You are an expert certification exam item writer. "
    "You create high-quality multiple-choice questions following best practices: "
    "scenario-based stems, one unambiguous correct answer (key), and plausible distractors. "
    "Each distractor should represent a common misconception or partial understanding."
)


def check_connection(base_url: str = DEFAULT_URL, timeout: float = 3.0) -> bool:
    try:
        req = urllib.request.Request(f"{base_url}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except Exception:
        return False


def list_models(base_url: str = DEFAULT_URL, timeout: float = 5.0) -> List[OllamaModel]:
    try:
        req = urllib.request.Request(f"{base_url}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            return [
                OllamaModel(name=m["name"], size=m.get("size", 0))
                for m in data.get("models", [])
            ]
    except Exception:
        return []


def get_model_info(model: str, base_url: str = DEFAULT_URL, timeout: float = 5.0) -> dict:
    """Get model details from Ollama /api/show. Returns dict with context_length, parameter_size, etc."""
    try:
        payload = json.dumps({"name": model}).encode()
        req = urllib.request.Request(
            f"{base_url}/api/show",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            details = data.get("details", {})
            model_info = data.get("model_info", {})
            # Find context_length from model_info (key varies by architecture)
            context_length = 0
            for key, val in model_info.items():
                if key.endswith(".context_length") and isinstance(val, int):
                    context_length = val
                    break
            return {
                "context_length": context_length,
                "parameter_size": details.get("parameter_size", ""),
                "quantization": details.get("quantization_level", ""),
                "family": details.get("family", ""),
                "format": details.get("format", ""),
            }
    except Exception:
        return {}


def get_gpu_info() -> list:
    """Detect GPU(s) via nvidia-smi. Returns list of dicts with name, total_mb, free_mb."""
    import subprocess
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        gpus = []
        for line in result.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                gpus.append({
                    "name": parts[0],
                    "total_mb": int(parts[1]),
                    "free_mb": int(parts[2]),
                })
        return gpus
    except Exception:
        return []


def list_running(base_url: str = DEFAULT_URL, timeout: float = 5.0) -> List[dict]:
    """The models loaded now (``/api/ps``): name, size, and ``size_vram`` - how
    much of it is on the GPU. [] when Ollama does not answer."""
    try:
        req = urllib.request.Request(f"{base_url}/api/ps", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            return [
                {"name": m.get("name", ""), "size": int(m.get("size", 0) or 0),
                 "size_vram": int(m.get("size_vram", 0) or 0)}
                for m in data.get("models", [])
            ]
    except Exception:
        return []


def _encode_image(image_path: str) -> Optional[str]:
    try:
        p = Path(image_path)
        if p.exists():
            return base64.b64encode(p.read_bytes()).decode("ascii")
    except Exception:
        pass
    return None


def generate(
    prompt: str,
    model: str,
    system: str = DEFAULT_SYSTEM_PROMPT,
    base_url: str = DEFAULT_URL,
    timeout: float = 120.0,
    images: Optional[List[str]] = None,
    num_ctx: int = 0,
    num_predict: int = 0,
) -> str:
    resolved_ctx = _resolve_num_ctx(num_ctx)
    body = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
    }
    options = {}
    if resolved_ctx > 0:
        options["num_ctx"] = resolved_ctx
    if num_predict > 0:
        # Cap the reply. Without one, a model that starts rambling generates
        # until it fills the whole context and Ollama returns done_reason
        # "length" with an EMPTY response — 5,807 tokens and nearly three
        # minutes spent producing nothing. A bound turns that into a fast
        # failure the caller can report instead of a long silent one.
        options["num_predict"] = num_predict
    if options:
        body["options"] = options
    if images:
        encoded = [b64 for path in images if (b64 := _encode_image(path))]
        if encoded:
            body["images"] = encoded
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{base_url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
        reply = (data.get("response") or "").strip()
        if not reply:
            # An empty reply has more than one cause and they need different
            # fixes, so say which. "length" means the model filled the context
            # before answering — on a reasoning model that is thousands of
            # tokens of thinking Ollama never returns, and the fix is a shorter
            # prompt or a bigger window, NOT a num_predict cap, which counts
            # the thinking too and cuts it off even earlier.
            print(
                f"[OLLAMA] empty reply from {model}: done_reason="
                f"{data.get('done_reason')!r} generated={data.get('eval_count')} "
                f"prompt={data.get('prompt_eval_count')} ctx={resolved_ctx}"
            )
        return reply


def generate_stream(
    prompt: str,
    model: str,
    system: str = DEFAULT_SYSTEM_PROMPT,
    base_url: str = DEFAULT_URL,
    timeout: float = 120.0,
    num_ctx: int = 0,
) -> Generator[str, None, None]:
    resolved_ctx = _resolve_num_ctx(num_ctx)
    body = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": True,
    }
    if resolved_ctx > 0:
        body["options"] = {"num_ctx": resolved_ctx}
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{base_url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for line in resp:
            if line.strip():
                chunk = json.loads(line.decode())
                text = chunk.get("response", "")
                if text:
                    yield text
                if chunk.get("done"):
                    break


def chat(
    messages: list,
    model: str,
    system: str = DEFAULT_SYSTEM_PROMPT,
    base_url: str = DEFAULT_URL,
    timeout: float = 120.0,
    num_ctx: int = 0,
) -> str:
    resolved_ctx = _resolve_num_ctx(num_ctx)
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}] + messages,
        "stream": False,
    }
    if resolved_ctx > 0:
        body["options"] = {"num_ctx": resolved_ctx}
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
        return data.get("message", {}).get("content", "").strip()


def chat_stream(
    messages: list,
    model: str,
    system: str = DEFAULT_SYSTEM_PROMPT,
    base_url: str = DEFAULT_URL,
    timeout: float = 120.0,
    num_ctx: int = 0,
) -> Generator[str, None, None]:
    resolved_ctx = _resolve_num_ctx(num_ctx)
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}] + messages,
        "stream": True,
    }
    if resolved_ctx > 0:
        body["options"] = {"num_ctx": resolved_ctx}
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for line in resp:
            if line.strip():
                chunk = json.loads(line.decode())
                text = chunk.get("message", {}).get("content", "")
                if text:
                    yield text
                if chunk.get("done"):
                    break


# ---------------------------------------------------------------------------
# Async variants (require httpx)
# ---------------------------------------------------------------------------

def _require_httpx() -> None:
    if not _HAS_HTTPX:
        raise ImportError(
            "httpx is required for async functions. Install it with: pip install httpx"
        )


async def async_check_connection(
    base_url: str = DEFAULT_URL,
    timeout: float = 5.0,
) -> bool:
    """Async version of check_connection() using httpx."""
    _require_httpx()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{base_url}/api/tags")
            return resp.status_code == 200
    except Exception:
        return False


async def async_list_models(
    base_url: str = DEFAULT_URL,
    timeout: float = 10.0,
) -> List[OllamaModel]:
    """Async version of list_models() using httpx."""
    _require_httpx()
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(f"{base_url}/api/tags")
        resp.raise_for_status()
        data = resp.json()
        return [
            OllamaModel(name=m["name"], size=m.get("size", 0))
            for m in data.get("models", [])
        ]


async def async_generate(
    prompt: str,
    model: str,
    system: str = DEFAULT_SYSTEM_PROMPT,
    base_url: str = DEFAULT_URL,
    timeout: float = 120.0,
    images: Optional[List[str]] = None,
) -> str:
    """Async version of generate() using httpx."""
    _require_httpx()
    payload: dict = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
    }
    if images:
        encoded = [b64 for path in images if (b64 := _encode_image(path))]
        if encoded:
            payload["images"] = encoded
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{base_url}/api/generate", json=payload)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()


async def async_generate_stream(
    prompt: str,
    model: str,
    system: str = DEFAULT_SYSTEM_PROMPT,
    base_url: str = DEFAULT_URL,
    timeout: float = 120.0,
) -> AsyncGenerator[str, None]:
    """Async streaming version of generate_stream() using httpx."""
    _require_httpx()
    payload = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", f"{base_url}/api/generate", json=payload) as resp:
            async for line in resp.aiter_lines():
                if line.strip():
                    data = json.loads(line)
                    chunk = data.get("response", "")
                    if chunk:
                        yield chunk
                    if data.get("done"):
                        break


async def async_chat(
    messages: list,
    model: str,
    system: str = DEFAULT_SYSTEM_PROMPT,
    base_url: str = DEFAULT_URL,
    timeout: float = 120.0,
) -> str:
    """Async version of chat() using httpx."""
    _require_httpx()
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}] + messages,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{base_url}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "").strip()


async def async_chat_stream(
    messages: list,
    model: str,
    system: str = DEFAULT_SYSTEM_PROMPT,
    base_url: str = DEFAULT_URL,
    timeout: float = 120.0,
) -> AsyncGenerator[str, None]:
    """Async streaming version of chat_stream() using httpx."""
    _require_httpx()
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}] + messages,
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", f"{base_url}/api/chat", json=payload) as resp:
            async for line in resp.aiter_lines():
                if line.strip():
                    data = json.loads(line)
                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        yield chunk
                    if data.get("done"):
                        break
