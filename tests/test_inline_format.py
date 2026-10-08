"""The Python half of the inline formatting contract.

The cases are the frontend's file, so a change to what "**" means fails here
and in vitest alike."""
import json
from pathlib import Path
from xml.etree.ElementTree import Element, tostring

import pytest

from exam_bank.core import inline_format as fmt

CASES = json.loads(
    (Path(__file__).resolve().parents[1] / "frontend" / "src" / "inlineFormat.cases.json")
    .read_text(encoding="utf-8")
)["cases"]


@pytest.mark.parametrize("case", CASES, ids=[json.dumps(c["in"]) for c in CASES])
def test_contract(case):
    assert fmt.parse(case["in"]) == case["nodes"]


def test_html_escapes_everything_but_the_three():
    assert fmt.to_html('**b** *i* `c` <img src=x onerror="alert(1)"> & more') == (
        '<strong>b</strong> <em>i</em> <code>c</code> &lt;img src=x onerror="alert(1)"&gt; &amp; more'
    )
    assert fmt.to_html("`<div>`") == "<code>&lt;div&gt;</code>"


def test_plain_and_has_format():
    assert fmt.to_plain("a **bold** *it* `code` \\*x\\*") == "a bold it code *x*"
    assert fmt.to_plain("[Sales] * [Quantity]") == "[Sales] * [Quantity]"
    assert fmt.has_format("a `b`") and not fmt.has_format("industrial/*/sensor")


def test_runs_carry_nesting():
    assert list(fmt.runs("a **b *c*** `d`")) == [
        ("a ", False, False, False),
        ("b ", True, False, False),
        ("c", True, True, False),
        (" ", False, False, False),
        ("d", False, False, True),
    ]


def test_fill_element_builds_inline_children():
    p = Element("p")
    fmt.fill_element(p, "use **the** `kettle.properties` file")
    assert tostring(p, encoding="unicode") == (
        "<p>use <strong>the</strong> <code>kettle.properties</code> file</p>"
    )
    plain = Element("p")
    fmt.fill_element(plain, "a <b> c")
    assert tostring(plain, encoding="unicode") == "<p>a &lt;b&gt; c</p>"
