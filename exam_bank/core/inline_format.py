"""Inline formatting in question text: **bold**, *italic* and `code`.

The Python twin of ``frontend/src/inlineFormat.tsx``, for the exporters that
write a format with formatting of its own (QTI, Moodle XML, Word) or none at
all (plain text, the PDF paper). Both parsers are tested against
``frontend/src/inlineFormat.cases.json``, the contract the Content Manager's
quiz renderer also follows - change one, change all three.

Strict on purpose: the bank already holds text that is NOT formatting
(``[Sales] * [Quantity]``, ``industrial/*/sensor``, ``<div id="panel_1">``,
``snake_case``). An opening marker needs a non-space after it and no letter
or digit before it, a closing one the mirror image; underscores never format;
a backslash keeps a marker literal. Nothing is ever passed through as markup.
"""
from __future__ import annotations

import html
import re
from typing import Iterator, List, Tuple, Union

Node = Union[Tuple[str, str], Tuple[str, list]]

_ESCAPABLE = {"*", "`", "\\"}


def _is_word(c: str | None) -> bool:
    return c is not None and c.isalnum()


# What may sit just INSIDE a marker (see inlineFormat.tsx): not `]`, `.` or
# `/` after an opener - that is a wildcard, JSONPath `[*]` / `.*.` or a glob.
_OPENS_WITH = set("'\"‘“([{$`")
_CLOSES_WITH = set("'\"’”)]}`.!?%:")


def _can_start(c: str | None) -> bool:
    return _is_word(c) or (c is not None and c in _OPENS_WITH)


def _can_end(c: str | None) -> bool:
    return _is_word(c) or (c is not None and c in _CLOSES_WITH)


def _at(s: str, k: int) -> str | None:
    return s[k] if 0 <= k < len(s) else None


def _run(s: str, k: int) -> int:
    r = 0
    while _at(s, k + r) == "*":
        r += 1
    return r


def _find_closer(s: str, start: int, length: int) -> int:
    k = start
    while k < len(s):
        c = s[k]
        if c == "\\" and _at(s, k + 1) in _ESCAPABLE:
            k += 2
            continue
        if c == "`":
            end = s.find("`", k + 1)
            k = end + 1 if end > k + 1 else k + 1
            continue
        if c == "*":
            r = _run(s, k)
            closes = k > start and _can_end(_at(s, k - 1)) and not _is_word(_at(s, k + r))
            if closes:
                if length == 2 and r >= 2:
                    return k + r - 2
                if length == 1 and r % 2 == 1:
                    return k + r - 1
            k += r
            continue
        k += 1
    return -1


def parse(s: str | None) -> List[list]:
    """Text to nodes: ["text", s] | ["strong", nodes] | ["em", nodes] | ["code", s]."""
    s = s or ""
    out: List[list] = []
    text: List[str] = []

    def flush() -> None:
        if text:
            out.append(["text", "".join(text)])
            text.clear()

    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\" and _at(s, i + 1) in _ESCAPABLE:
            text.append(s[i + 1])
            i += 2
            continue
        if c == "`":
            end = s.find("`", i + 1)
            if end > i + 1:
                flush()
                out.append(["code", s[i + 1:end]])
                i = end + 1
                continue
            text.append(c)
            i += 1
            continue
        if c == "*":
            r = _run(s, i)
            opens = not _is_word(_at(s, i - 1)) and _can_start(_at(s, i + r))
            if opens:
                if r >= 2:
                    close = _find_closer(s, i + 2, 2)
                    if close > i + 2:
                        flush()
                        out.append(["strong", parse(s[i + 2:close])])
                        i = close + 2
                        continue
                close = _find_closer(s, i + 1, 1)
                if close > i + 1:
                    flush()
                    out.append(["em", parse(s[i + 1:close])])
                    i = close + 1
                    continue
            text.append(s[i:i + r])
            i += r
            continue
        text.append(c)
        i += 1
    flush()
    return out


def has_format(s: str | None) -> bool:
    return any(n[0] != "text" for n in parse(s))


def to_plain(s: str | None) -> str:
    """The words without their markers."""
    def walk(nodes: list) -> str:
        return "".join(n[1] if n[0] in ("text", "code") else walk(n[1]) for n in nodes)
    return walk(parse(s))


def to_html(s: str | None) -> str:
    """Escaped HTML: <strong>, <em> and <code> only; everything else is text."""
    def walk(nodes: list) -> str:
        parts = []
        for n in nodes:
            if n[0] == "text":
                parts.append(html.escape(n[1], quote=False))
            elif n[0] == "code":
                parts.append(f"<code>{html.escape(n[1], quote=False)}</code>")
            else:
                parts.append(f"<{n[0]}>{walk(n[1])}</{n[0]}>")
        return "".join(parts)
    return walk(parse(s))


_PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n\s*")


def paragraphs(s: str | None) -> List[str]:
    """The text split into paragraphs at blank lines, each trimmed; [] when
    empty. A single newline stays inside its paragraph as a line break.

    Above the inline rules, not part of them: markers never span a paragraph
    break, because each paragraph is parsed on its own. The contract's
    ``paragraphs`` cases pin this for all three parsers.
    """
    text = (s or "").replace("\r\n", "\n").strip()
    if not text:
        return []
    return [p.strip() for p in _PARAGRAPH_BREAK.split(text) if p.strip()]


# A fence line: ``` and an optional language name (json, sql, properties).
_FENCE_OPEN = re.compile(r"^\s*```([\w+.-]*)\s*$")
_FENCE_CLOSE = re.compile(r"^\s*```\s*$")


def blocks(s: str | None) -> List[Tuple[str, str, str]]:
    """The text as blocks: ("p", paragraph, "") and ("code", code, language).

    A fenced block - a line of ``` (with an optional language), the code, a
    line of ``` - is kept whole, blank lines and all, and never parsed for
    markers: in code `*` and `` ` `` are just characters (1.16.0, for the
    explanations of questions about JSONPath, SQL or a properties file). The
    prose between blocks splits into paragraphs as ``paragraphs`` does. A
    fence that never closes is not a block; its line stays text. The
    contract's ``blocks`` cases pin this for all three parsers.
    """
    lines = (s or "").replace("\r\n", "\n").split("\n")
    out: List[Tuple[str, str, str]] = []
    prose: List[str] = []

    def flush() -> None:
        out.extend(("p", p, "") for p in paragraphs("\n".join(prose)))
        prose.clear()

    i = 0
    while i < len(lines):
        opening = _FENCE_OPEN.match(lines[i])
        if opening:
            close = next((j for j in range(i + 1, len(lines)) if _FENCE_CLOSE.match(lines[j])), -1)
            if close > i:
                flush()
                out.append(("code", "\n".join(lines[i + 1:close]), opening.group(1)))
                i = close + 1
                continue
        prose.append(lines[i])
        i += 1
    flush()
    return out


def to_html_paragraphs(s: str | None) -> str:
    """One <p> per paragraph, each as to_html; a single newline is a <br/>.
    A code block is a <pre><code>, its text escaped and never parsed."""
    parts = []
    for kind, text, lang in blocks(s):
        if kind == "code":
            cls = f' class="language-{html.escape(lang)}"' if lang else ""
            parts.append(f"<pre><code{cls}>{html.escape(text, quote=False)}</code></pre>")
        else:
            parts.append("<p>" + to_html(text).replace("\n", "<br/>") + "</p>")
    return "".join(parts)


def to_plain_blocks(s: str | None) -> str:
    """The words without their markers, paragraphs a blank line apart, and a
    code block's lines indented four spaces - for plain text and the PDF."""
    parts = []
    for kind, text, _lang in blocks(s):
        if kind == "code":
            parts.append("\n".join("    " + line for line in text.split("\n")))
        else:
            parts.append(to_plain(text))
    return "\n\n".join(parts)


def runs(s: str | None) -> Iterator[Tuple[str, bool, bool, bool]]:
    """(text, bold, italic, code) runs, for writers that style runs (Word)."""
    def walk(nodes: list, bold: bool, italic: bool) -> Iterator[Tuple[str, bool, bool, bool]]:
        for n in nodes:
            if n[0] == "text":
                yield n[1], bold, italic, False
            elif n[0] == "code":
                yield n[1], bold, italic, True
            elif n[0] == "strong":
                yield from walk(n[1], True, italic)
            else:
                yield from walk(n[1], bold, True)
    yield from walk(parse(s), False, False)


def fill_element(parent, s: str | None) -> None:
    """Write formatted text into an ElementTree element: text plus inline
    <strong>/<em>/<code> children with tails, as XHTML inside QTI expects."""
    from xml.etree.ElementTree import SubElement

    def walk(el, nodes: list) -> None:
        last = None
        for n in nodes:
            if n[0] == "text":
                if last is None:
                    el.text = (el.text or "") + n[1]
                else:
                    last.tail = (last.tail or "") + n[1]
                continue
            child = SubElement(el, n[0])
            if n[0] == "code":
                child.text = n[1]
            else:
                walk(child, n[1])
            last = child
    walk(parent, parse(s))
