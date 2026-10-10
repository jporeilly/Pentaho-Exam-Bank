"""The Python half of the inline formatting contract.

The cases are the frontend's file, so a change to what "**" means fails here
and in vitest alike."""
import json
from pathlib import Path
from xml.etree.ElementTree import Element, tostring

import pytest

from exam_bank.core import inline_format as fmt

CONTRACT = json.loads(
    (Path(__file__).resolve().parents[1] / "frontend" / "src" / "inlineFormat.cases.json")
    .read_text(encoding="utf-8")
)
CASES = CONTRACT["cases"]
PARAGRAPHS = CONTRACT["paragraphs"]


@pytest.mark.parametrize("case", CASES, ids=[json.dumps(c["in"]) for c in CASES])
def test_contract(case):
    assert fmt.parse(case["in"]) == case["nodes"]


@pytest.mark.parametrize("case", PARAGRAPHS, ids=[json.dumps(c["in"]) for c in PARAGRAPHS])
def test_paragraph_contract(case):
    assert fmt.paragraphs(case["in"]) == case["paragraphs"]


BLOCKS = CONTRACT["blocks"]


@pytest.mark.parametrize("case", BLOCKS, ids=[json.dumps(c["in"]) for c in BLOCKS])
def test_block_contract(case):
    got = [list(b) if b[0] == "code" else [b[0], b[1]] for b in fmt.blocks(case["in"])]
    assert got == case["blocks"]


def test_a_code_block_is_pre_code_escaped_and_never_formatted():
    assert fmt.to_html_paragraphs("Given:\n\n```json\n{\"a\": \"<b>**x**</b>\"}\n```") == (
        '<p>Given:</p><pre><code class="language-json">'
        '{"a": "&lt;b&gt;**x**&lt;/b&gt;"}</code></pre>'
    )


def test_plain_text_indents_a_code_block():
    assert fmt.to_plain_blocks("Read **this**:\n\n```sql\nSELECT *\nFROM t\n```\n\nDone.") == (
        "Read this:\n\n    SELECT *\n    FROM t\n\nDone."
    )


def test_paragraphs_become_p_elements_with_line_breaks():
    assert fmt.to_html_paragraphs("the **key** idea\nstill one\n\nsecond <b>") == (
        "<p>the <strong>key</strong> idea<br/>still one</p><p>second &lt;b&gt;</p>"
    )
    assert fmt.to_html_paragraphs("   ") == ""


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
