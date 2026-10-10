"""Every Ollama request turns thinking off (1.14.0).

gemma4:12b, the default model, reasons at length before answering when
thinking is on: minutes per AI rewrite, hours for the bulk rewrite of an
exam. The answers are structured JSON that needs no reasoning trace.
"""

import json
import re
from pathlib import Path

from exam_bank.core import ollama_client

SOURCE = Path(ollama_client.__file__).read_text(encoding="utf-8")


def test_every_request_body_turns_thinking_off():
    # Each body names its "stream"; each must say "think": False beside it.
    streams = re.findall(r'"stream": (?:False|True),', SOURCE)
    thinks = re.findall(r'"think": False,', SOURCE)
    assert len(streams) == 8 and len(thinks) == len(streams)


def test_generate_sends_it(monkeypatch):
    sent = {}

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"response": "ok"}).encode()

    def fake_urlopen(req, timeout):
        sent.update(json.loads(req.data.decode()))
        return Reply()

    monkeypatch.setattr(ollama_client.urllib.request, "urlopen", fake_urlopen)

    assert ollama_client.generate("hi", "gemma4:12b") == "ok"
    assert sent["think"] is False
