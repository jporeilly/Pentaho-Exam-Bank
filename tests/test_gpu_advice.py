"""GPU advice: what this machine can run, judged against ONE card.

nvidia-smi and Ollama are stubbed with the machine this was written on: two
12 GB RTX 3060s. The NiceGUI-era advice added the cards together, which on
that machine is exactly the wrong answer: a model that does not fit one card
ran about four times slower.
"""

import pytest
from fastapi.testclient import TestClient

from exam_bank.api.app import app
from exam_bank.core import gpu_advice, ollama_client
from exam_bank.core.ollama_client import OllamaModel

GB = 1024 ** 3
TWO_3060S = [{"name": "NVIDIA GeForce RTX 3060", "total_mb": 12288, "free_mb": 11000}] * 2


@pytest.fixture
def machine(monkeypatch):
    state = {"gpus": TWO_3060S, "up": True, "running": [],
             "models": [OllamaModel("gemma4:12b", int(7.04 * GB)),
                        OllamaModel("gemma4:e4b", int(8.95 * GB)),
                        OllamaModel("gemma3:27b", int(16.2 * GB)),
                        OllamaModel("qwen2.5:32b", int(18.5 * GB)),
                        OllamaModel("nomic-embed-text:latest", int(0.26 * GB))]}
    monkeypatch.setattr(ollama_client, "get_gpu_info", lambda: state["gpus"])
    monkeypatch.setattr(ollama_client, "check_connection", lambda url, timeout=3.0: state["up"])
    monkeypatch.setattr(ollama_client, "list_models", lambda url, timeout=5.0: state["models"])
    monkeypatch.setattr(ollama_client, "list_running", lambda url, timeout=5.0: state["running"])
    return state


def fits(advice):
    return {m["name"]: m["fit"] for m in advice["models"]}


def test_models_are_judged_against_one_card_not_the_two_together(machine):
    advice = gpu_advice.advise("http://ollama", "gemma4:12b")

    assert fits(advice) == {"nomic-embed-text:latest": "fits", "gemma4:12b": "fits",
                            "gemma4:e4b": "tight", "gemma3:27b": "split", "qwen2.5:32b": "split"}
    assert advice["largestGpuGb"] == 12.0
    assert any("fits on one 12.0 GB card" in a for a in advice["advice"])


def test_a_model_too_big_for_one_card_is_called_slow_and_a_better_one_named(machine):
    advice = gpu_advice.advise("http://ollama", "gemma3:27b")

    said = " ".join(advice["advice"])
    assert "more than one 12.0 GB card holds" in said and "several times slower" in said
    # The largest that fits comfortably - not the embedding model, not the tight one.
    assert "fits one card comfortably is gemma4:12b" in said


def test_a_loaded_model_partly_on_the_cpu_is_named(machine):
    machine["running"] = [{"name": "gemma3:27b", "size": int(18 * GB), "size_vram": int(12 * GB)}]

    said = " ".join(gpu_advice.advise("http://ollama", "gemma3:27b")["advice"])

    assert "gemma3:27b is loaded now with 33% of it on the CPU" in said


def test_a_model_that_is_not_pulled_says_how_to_pull_it(machine):
    said = " ".join(gpu_advice.advise("http://ollama", "llama9:70b")["advice"])
    assert "`ollama pull llama9:70b`" in said


def test_no_gpu_and_no_ollama_are_said_plainly(machine):
    machine["gpus"] = []
    assert "No NVIDIA GPU was found" in gpu_advice.advise("http://ollama", "gemma4:12b")["advice"][0]

    machine["up"] = False
    advice = gpu_advice.advise("http://ollama", "gemma4:12b")
    assert advice["ollama"] is False and advice["models"] == []
    assert "not answering" in advice["advice"][0]


def test_the_endpoint_reports_it(machine):
    body = TestClient(app).get("/api/settings/gpu").json()

    assert body["largestGpuGb"] == 12.0 and len(body["gpus"]) == 2
    assert {m["name"] for m in body["models"]} >= {"gemma4:12b", "gemma3:27b"}
