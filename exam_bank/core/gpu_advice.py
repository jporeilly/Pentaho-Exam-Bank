"""What this machine's GPUs can run: advice for choosing an Ollama model.

The answer that matters is whether a model fits on ONE card. On a machine
with two 12 GB cards a model that does not fit one is spread over both, or
spilled onto the CPU, and runs several times slower - proven on the machine
this was written on, where a model one card could not hold answered about
four times slower. So everything here is measured against the largest single
card, not the cards added together (which the NiceGUI-era advice did).

What it reads, all local and none of it written:

- the GPUs, from ``nvidia-smi`` (name, memory, free memory);
- the models pulled into Ollama, with their size on disk (``/api/tags``);
- the models loaded now, and how much of each is on the GPU (``/api/ps``) -
  the direct evidence of a spill.

A model's need is estimated from its file: the weights plus about a tenth,
plus a gigabyte for the context and the runtime. It is an estimate; what
``/api/ps`` reports for a loaded model is the measurement.
"""

from __future__ import annotations

from . import ollama_client

GB = 1024 ** 3

#: Share of a card a model may take and still be comfortable: the rest is the
#: context growing with a long prompt, and whatever else is using the card.
COMFORTABLE = 0.85


def need_gb(size_bytes: int) -> float:
    return round(size_bytes / GB * 1.1 + 1.0, 1)


def fit(need: float, largest_gb: float, total_gb: float) -> str:
    """``fits``, ``tight``, ``split`` (more than one card) or ``too-big``."""
    if largest_gb <= 0:
        return "no-gpu"
    if need <= largest_gb * COMFORTABLE:
        return "fits"
    if need <= largest_gb:
        return "tight"
    if need <= total_gb:
        return "split"
    return "too-big"


def advise(base_url: str, model: str) -> dict:
    gpus = [{"name": g["name"], "totalGb": round(g["total_mb"] / 1024, 1),
             "freeGb": round(g["free_mb"] / 1024, 1)} for g in ollama_client.get_gpu_info()]
    largest = max((g["totalGb"] for g in gpus), default=0.0)
    total = round(sum(g["totalGb"] for g in gpus), 1)
    reachable = ollama_client.check_connection(base_url)

    models = []
    for m in (ollama_client.list_models(base_url) if reachable else []):
        need = need_gb(m.size)
        models.append({"name": m.name, "sizeGb": round(m.size / GB, 1), "needGb": need,
                       "fit": fit(need, largest, total), "selected": m.name == model})
    models.sort(key=lambda m: m["sizeGb"])

    loaded = []
    for r in (ollama_client.list_running(base_url) if reachable else []):
        size, on_gpu = r.get("size", 0), r.get("size_vram", 0)
        loaded.append({"name": r.get("name", ""), "sizeGb": round(size / GB, 1),
                       "gpuPercent": round(100 * on_gpu / size) if size else 0})

    return {"ollama": reachable, "model": model, "gpus": gpus, "largestGpuGb": largest,
            "models": models, "loaded": loaded,
            "advice": _advice(reachable, model, gpus, largest, models, loaded)}


def _advice(reachable, model, gpus, largest, models, loaded) -> list[str]:
    out = []
    if not reachable:
        return ["Ollama is not answering at its address in Settings, so nothing about its "
                "models can be said. Start it, then check again."]
    if not gpus:
        out.append("No NVIDIA GPU was found (nvidia-smi is not available), so Ollama runs on "
                   "the CPU. Expect answers to be slow; the smaller the model, the less so.")
    else:
        names = {g["name"] for g in gpus}
        if len(gpus) > 1 and len(names) == 1:
            out.append(f"{len(gpus)} × {gpus[0]['name']}, {gpus[0]['totalGb']} GB each. A model "
                       "has to fit on ONE card to run at full speed.")
        else:
            out.append("GPUs: " + "; ".join(f"{g['name']} ({g['totalGb']} GB)" for g in gpus) + ".")

    chosen = next((m for m in models if m["selected"]), None)
    if model and chosen is None:
        out.append(f"{model} is not pulled into Ollama. Run `ollama pull {model}`, or pick "
                   "one that is.")
    elif chosen and gpus:
        need, name = chosen["needGb"], chosen["name"]
        if chosen["fit"] == "fits":
            out.append(f"{name} needs about {need} GB and fits on one {largest} GB card, so it "
                       "runs on the GPU at full speed.")
        elif chosen["fit"] == "tight":
            out.append(f"{name} needs about {need} GB: it fits one {largest} GB card, just. A "
                       "long prompt or another program on the card can push part of it onto "
                       "the CPU.")
        else:
            where = ("is spread over the cards or spilled onto the CPU"
                     if chosen["fit"] == "split" else "has to run largely on the CPU")
            out.append(f"{name} needs about {need} GB, more than one {largest} GB card holds, so "
                       f"it {where} - several times slower.")
            better = [m for m in models if m["fit"] == "fits" and not m["name"].startswith(
                ("nomic-embed", "mxbai-embed"))]
            if better:
                pick = max(better, key=lambda m: m["sizeGb"])
                out.append(f"The largest model you have that fits one card comfortably is "
                           f"{pick['name']} ({pick['sizeGb']} GB).")

    for r in loaded:
        if r["gpuPercent"] < 100:
            out.append(f"{r['name']} is loaded now with {100 - r['gpuPercent']}% of it on the "
                       "CPU: it will answer slowly until it is unloaded or a smaller model is "
                       "used.")
        else:
            out.append(f"{r['name']} is loaded now, entirely on the GPU.")
    return out
