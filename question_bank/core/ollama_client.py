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


def recommend_num_ctx(model: str, base_url: str = DEFAULT_URL) -> dict:
    """Auto-recommend num_ctx based on model context limit and available GPU memory.

    Returns dict with recommended, max_model, gpu_free_mb, reasoning.
    """
    info = get_model_info(model, base_url)
    gpus = get_gpu_info()

    max_model = info.get("context_length", 0)
    param_size = info.get("parameter_size", "")
    total_gpu_free_mb = sum(g["free_mb"] for g in gpus) if gpus else 0
    total_gpu_mb = sum(g["total_mb"] for g in gpus) if gpus else 0
    gpu_names = ", ".join(g["name"] for g in gpus) if gpus else "No GPU detected"

    # Estimate: each token in context needs ~0.5-2 KB of KV cache depending on model size
    # For a 27B Q4 model: ~1 KB per token. For 7B: ~0.5 KB per token.
    # Conservative: allocate ~50% of free GPU memory for KV cache
    if total_gpu_free_mb > 0:
        # Parse param size to get rough scale
        param_billions = 0
        if param_size:
            import re
            m = re.search(r'([\d.]+)', param_size)
            if m:
                param_billions = float(m.group(1))

        kb_per_token = 0.5 if param_billions < 10 else 1.0 if param_billions < 30 else 1.5
        available_for_ctx_mb = total_gpu_free_mb * 0.4  # 40% of free VRAM for KV cache
        max_from_gpu = int((available_for_ctx_mb * 1024) / kb_per_token)
        # Round to nearest 1024
        max_from_gpu = (max_from_gpu // 1024) * 1024
        max_from_gpu = max(2048, min(max_from_gpu, max_model or 131072))
    else:
        # CPU only — be conservative
        max_from_gpu = 8192

    # Pick a sensible default: min of model max and GPU-derived max, capped reasonably
    recommended = min(max_from_gpu, max_model) if max_model else max_from_gpu
    recommended = max(4096, min(recommended, 65536))  # floor 4096, cap 65536

    reasoning = f"GPU: {gpu_names} ({total_gpu_free_mb:,} MB free of {total_gpu_mb:,} MB)"
    if max_model:
        reasoning += f" | Model max: {max_model:,} tokens"
    reasoning += f" | Recommended: {recommended:,} tokens"

    return {
        "recommended": recommended,
        "max_model": max_model,
        "gpu_free_mb": total_gpu_free_mb,
        "gpu_total_mb": total_gpu_mb,
        "gpu_names": gpu_names,
        "param_size": param_size,
        "reasoning": reasoning,
    }


# ── Model recommendation catalog ──────────────────────────

MODEL_CATALOG = [
    # Chat / General
    {"name": "gemma3:27b", "category": "All-Rounder", "vram_gb": 18, "params": "27B", "quality": 5, "speed": 3, "notes": "Excellent all-round, vision capable"},
    {"name": "gemma3:12b", "category": "All-Rounder", "vram_gb": 8, "params": "12B", "quality": 4, "speed": 4, "notes": "Great balance of quality and speed"},
    {"name": "gemma3:4b", "category": "All-Rounder", "vram_gb": 3, "params": "4B", "quality": 3, "speed": 5, "notes": "Fast, good for low-end hardware"},
    {"name": "llama3.1:70b", "category": "All-Rounder", "vram_gb": 40, "params": "70B", "quality": 5, "speed": 1, "notes": "Top quality, needs high-end GPU"},
    {"name": "llama3.1:8b", "category": "All-Rounder", "vram_gb": 5, "params": "8B", "quality": 4, "speed": 4, "notes": "Solid general-purpose model"},
    {"name": "llama3.2:3b", "category": "All-Rounder", "vram_gb": 2, "params": "3B", "quality": 3, "speed": 5, "notes": "Lightweight, very fast"},
    {"name": "mistral", "category": "All-Rounder", "vram_gb": 5, "params": "7B", "quality": 4, "speed": 4, "notes": "Fast and efficient general model"},
    {"name": "mixtral", "category": "All-Rounder", "vram_gb": 28, "params": "47B", "quality": 5, "speed": 2, "notes": "MoE architecture, high quality"},
    {"name": "qwen3:32b", "category": "All-Rounder", "vram_gb": 20, "params": "32B", "quality": 5, "speed": 3, "notes": "Strong reasoning and multilingual"},
    {"name": "qwen3:8b", "category": "All-Rounder", "vram_gb": 5, "params": "8B", "quality": 4, "speed": 4, "notes": "Good quality, efficient"},
    {"name": "phi4:14b", "category": "All-Rounder", "vram_gb": 9, "params": "14B", "quality": 4, "speed": 4, "notes": "Microsoft, strong reasoning"},

    # Chat / Conversational
    {"name": "llama3.1:8b", "category": "Chat", "vram_gb": 5, "params": "8B", "quality": 4, "speed": 4, "notes": "Natural conversational style"},
    {"name": "gemma3:12b", "category": "Chat", "vram_gb": 8, "params": "12B", "quality": 4, "speed": 4, "notes": "Excellent chat with vision"},
    {"name": "command-r:35b", "category": "Chat", "vram_gb": 22, "params": "35B", "quality": 5, "speed": 3, "notes": "Cohere, built for RAG and chat"},

    # Code
    {"name": "qwen2.5-coder:32b", "category": "Code", "vram_gb": 20, "params": "32B", "quality": 5, "speed": 3, "notes": "Top code model, many languages"},
    {"name": "qwen2.5-coder:7b", "category": "Code", "vram_gb": 5, "params": "7B", "quality": 4, "speed": 4, "notes": "Good code assistant, fast"},
    {"name": "codellama:13b", "category": "Code", "vram_gb": 8, "params": "13B", "quality": 4, "speed": 4, "notes": "Meta, solid code completion"},
    {"name": "codellama:7b", "category": "Code", "vram_gb": 5, "params": "7B", "quality": 3, "speed": 5, "notes": "Lightweight code model"},
    {"name": "deepseek-coder-v2:16b", "category": "Code", "vram_gb": 10, "params": "16B", "quality": 5, "speed": 3, "notes": "Strong code generation"},
    {"name": "starcoder2:15b", "category": "Code", "vram_gb": 10, "params": "15B", "quality": 4, "speed": 3, "notes": "BigCode, 600+ languages"},

    # Vision (multimodal)
    {"name": "gemma3:27b", "category": "Vision", "vram_gb": 18, "params": "27B", "quality": 5, "speed": 3, "notes": "Image understanding + text"},
    {"name": "gemma3:12b", "category": "Vision", "vram_gb": 8, "params": "12B", "quality": 4, "speed": 4, "notes": "Vision capable, good balance"},
    {"name": "gemma3:4b", "category": "Vision", "vram_gb": 3, "params": "4B", "quality": 3, "speed": 5, "notes": "Lightweight vision model"},
    {"name": "llava:13b", "category": "Vision", "vram_gb": 8, "params": "13B", "quality": 4, "speed": 3, "notes": "Image captioning and Q&A"},
    {"name": "llava:7b", "category": "Vision", "vram_gb": 5, "params": "7B", "quality": 3, "speed": 4, "notes": "Fast image understanding"},
    {"name": "moondream:1.8b", "category": "Vision", "vram_gb": 2, "params": "1.8B", "quality": 3, "speed": 5, "notes": "Tiny vision model, very fast"},

    # Exam / Education (best for this app)
    {"name": "gemma3:27b", "category": "Exam Writing", "vram_gb": 18, "params": "27B", "quality": 5, "speed": 3, "notes": "Best for certification exam questions"},
    {"name": "qwen3:32b", "category": "Exam Writing", "vram_gb": 20, "params": "32B", "quality": 5, "speed": 3, "notes": "Strong structured output, reasoning"},
    {"name": "llama3.1:8b", "category": "Exam Writing", "vram_gb": 5, "params": "8B", "quality": 4, "speed": 4, "notes": "Good quality at lower VRAM"},
    {"name": "phi4:14b", "category": "Exam Writing", "vram_gb": 9, "params": "14B", "quality": 4, "speed": 4, "notes": "Strong at structured tasks"},
    {"name": "mistral", "category": "Exam Writing", "vram_gb": 5, "params": "7B", "quality": 4, "speed": 4, "notes": "Fast, decent question quality"},

    # Embedding / Analysis
    {"name": "nomic-embed-text", "category": "Embedding", "vram_gb": 1, "params": "137M", "quality": 4, "speed": 5, "notes": "Text embeddings for search"},
    {"name": "mxbai-embed-large", "category": "Embedding", "vram_gb": 1, "params": "335M", "quality": 5, "speed": 5, "notes": "High-quality embeddings"},
]


def recommend_models(gpu_total_mb: int = 0) -> dict:
    """Recommend models by category based on available GPU VRAM.

    Returns dict of {category: [models]} where models fit in the GPU.
    Each model dict includes a 'fits' bool and 'fit_label' string.
    """
    if gpu_total_mb <= 0:
        gpus = get_gpu_info()
        gpu_total_mb = sum(g["total_mb"] for g in gpus) if gpus else 0

    gpu_total_gb = gpu_total_mb / 1024 if gpu_total_mb else 0

    categories = {}
    seen = set()  # dedupe by (name, category)
    for m in MODEL_CATALOG:
        key = (m["name"], m["category"])
        if key in seen:
            continue
        seen.add(key)
        cat = m["category"]
        fits = m["vram_gb"] <= gpu_total_gb if gpu_total_gb > 0 else m["vram_gb"] <= 8
        tight = m["vram_gb"] > gpu_total_gb * 0.7 if gpu_total_gb > 0 else False
        if fits and not tight:
            fit_label = "Fits well"
            fit_color = "positive"
        elif fits:
            fit_label = "Tight fit"
            fit_color = "warning"
        else:
            fit_label = "Too large"
            fit_color = "negative"

        entry = {**m, "fits": fits, "fit_label": fit_label, "fit_color": fit_color}
        categories.setdefault(cat, []).append(entry)

    # Sort each category: fits first, then by quality desc, then speed desc
    for cat in categories:
        categories[cat].sort(key=lambda x: (not x["fits"], -x["quality"], -x["speed"]))

    return categories


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
) -> str:
    resolved_ctx = _resolve_num_ctx(num_ctx)
    body = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
    }
    if resolved_ctx > 0:
        body["options"] = {"num_ctx": resolved_ctx}
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
        return data.get("response", "").strip()


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
