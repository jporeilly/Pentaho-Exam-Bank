"""The writing standard's mechanical half: quotes, names and punctuation.

generation_prompts.WRITING_RULES tells the model the standard (1.15.0). A
model follows most of it and misses some, and the bank was written before it
existed: in 2026-10 its 489 questions put 143 spans in single quotes for six
different reasons (field names, values, paths, step names, ordinary words,
an option's text), wrote "Stream Lookup" 15 times against PDI's "Stream
lookup", and held 26 curly quotes and 5 contractions.

Two layers, both deterministic - whether text follows a rule is not a
question to ask another model:

- ``tidy`` makes the changes that cannot alter what a sentence says: curly
  quotes made straight, "n't" written out, runs of spaces closed up, a Title
  Case step name put back to PDI's own ("Stream Lookup" -> "Stream lookup"),
  quotes taken off a step name, and a quoted identifier or path put in code
  ('region_code' -> `region_code`). Code spans are never touched.
- ``style_notes`` reports what needs a reader: quotes left around a word,
  which may be a key (code) or an ordinary word (no quotes); a value in
  double quotes; a contraction tidy does not expand; answers that mix full
  sentences with fragments; bold outside the explanation. Advice, never a
  block, and a proposal with notes waits for the author in the bulk review.

Both run over every proposal the AI makes (rewrite, explanation, generation)
before the author sees it, so what is proposed is already tidy.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Callable, List, Tuple

from .inline_format import blocks
from .pdi_names import JOB_ENTRIES, STEPS

# --- Code is left alone ------------------------------------------------------

# A fenced code block (1.16.0), as inline_format.blocks reads one: a line of
# ``` with an optional language, the code, a line of ```. Kept verbatim -
# SQL has its quotes, a sample its own spacing.
_FENCED = re.compile(r"^[ \t]*```[\w+.-]*[ \t]*\r?\n(?:.*\n)*?[ \t]*```[ \t]*\r?$", re.M)

_CODE = re.compile(r"`[^`\n]+`")


def _outside_fences(text: str, fix: Callable[[str], str]) -> str:
    out, last = [], 0
    for m in _FENCED.finditer(text):
        out.append(fix(text[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(fix(text[last:]))
    return "".join(out)


def _outside_code(text: str, fix: Callable[[str], str]) -> str:
    """Apply ``fix`` to the text between code spans only."""
    out, last = [], 0
    for m in _CODE.finditer(text):
        out.append(fix(text[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(fix(text[last:]))
    return "".join(out)


def _without_code(text: str) -> str:
    return _CODE.sub(" ", _FENCED.sub(" ", text))


# --- PDI's names -----------------------------------------------------------

# Several words only: a one-word name ("Calculator") has no case to get wrong.
_NAMES = sorted({n for n in (*STEPS, *JOB_ENTRIES) if " " in n.strip()}, key=len, reverse=True)
_BY_LOWER = {n.lower(): n for n in _NAMES}
_NAME = re.compile(
    r"(?<![\w/])(" + "|".join(re.escape(n) for n in _NAMES) + r")(s?)(?![\w/])",
    re.IGNORECASE,
)


def _title_case(s: str) -> bool:
    """Every word starts with a capital, and it is not all capitals ("GROUP BY")."""
    words = [w for w in re.split(r"[\s/]+", s) if w]
    return all(w[0].isupper() for w in words if w[0].isalpha()) and not s.isupper()


def _pdi_case(m: re.Match) -> str:
    found, plural = m.group(1), m.group(2)
    canonical = _BY_LOWER[found.lower()]
    # Only the Title Case slip: "a merge join" in lower case is the idea, not
    # the step, and is left as written. "Stream Lookups" -> "Stream lookups".
    if found != canonical and _title_case(found):
        return canonical + plural.lower()
    return m.group(0)


# --- Quotes -----------------------------------------------------------------

# A quoted span: the opening quote after a non-word character, the closing one
# before a non-word character, no quote inside. An apostrophe ("customer's",
# "the customers' rows") opens nothing, so it is never taken for one.
_SINGLE = re.compile(r"(?<![\w'])'([^'\s](?:[^'\n]*[^'\s])?)'(?![\w'])")
_DOUBLE = re.compile(r'(?<![\w"])"([^"\s](?:[^"\n]*[^"\s])?)"(?![\w"])')

# What only code can be: no spaces, and a character prose does not use inside
# a word, or camelCase. 'region_code', '${INPUT_DIR}', '%APPDATA%\x', '*'.
_IDENTIFIER = re.compile(r"^(?=\S+$)(?:.*[_$/\\%{}\[\]:=*<>|]|.*[a-z][A-Z]|.*\.\w).*$")


def _unquote(m: re.Match) -> str:
    inner = m.group(1)
    if inner.lower() in _BY_LOWER:
        return _BY_LOWER[inner.lower()]
    if inner in STEPS or inner in JOB_ENTRIES:
        return inner
    if _IDENTIFIER.match(inner) and "`" not in inner:
        return f"`{inner}`"
    return m.group(0)


# --- Contractions -------------------------------------------------------------

_NOT = {
    "can't": "cannot", "won't": "will not", "shan't": "shall not",
    "doesn't": "does not", "don't": "do not", "didn't": "did not",
    "isn't": "is not", "aren't": "are not", "wasn't": "was not",
    "weren't": "were not", "hasn't": "has not", "haven't": "have not",
    "hadn't": "had not", "shouldn't": "should not", "wouldn't": "would not",
    "couldn't": "could not", "mustn't": "must not", "needn't": "need not",
}
_NOT_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in _NOT) + r")\b", re.IGNORECASE)
# The ones that cannot be written out blind: "it's" is "it is" or "it has".
_OTHER_CONTRACTION = re.compile(r"\b\w+'(?:s|re|ll|ve|d|m)\b", re.IGNORECASE)
# A possessive is fine; these few are only ever contractions. Case matters:
# "IT's budget" is the IT department's.
_POSSESSIVE_OK = re.compile(
    r"^(?!(?:[Ii]t|[Tt]hat|[Tt]here|[Hh]ere|[Ww]hat|[Ww]ho|[Ww]here|[Hh]e|[Ss]he|[Ll]et)'s$)\w+'s$"
)


def _expand(m: re.Match) -> str:
    word = m.group(1)
    full = _NOT[word.lower()]
    return full[0].upper() + full[1:] if word[0].isupper() else full


# --- tidy -------------------------------------------------------------------

_CURLY = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


def _outside_double_quotes(s: str, fix: Callable[[str], str]) -> str:
    """Double quotes hold words as written - a message, a user's ticket - so
    they are quoted exactly, contractions and all."""
    out, last = [], 0
    for m in _DOUBLE.finditer(s):
        out.append(fix(s[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(fix(s[last:]))
    return "".join(out)


def _tidy_prose(s: str) -> str:
    s = re.sub(r"(?<=\S) {2,}(?=\S)", " ", s)
    # A flow of steps (EXPLANATION_RULES) is drawn with a real arrow; a
    # model typing ASCII writes "->". Spaced only, so an expression such as
    # x->y is left alone (and code never reaches here).
    s = s.replace(" -> ", " → ")
    s = _outside_double_quotes(s, lambda part: _NOT_RE.sub(_expand, part))
    s = _SINGLE.sub(_unquote, s)
    s = _NAME.sub(_pdi_case, s)
    return s


# A bare number in code: "a quantity of `2`". A number in a sentence is
# plain (WRITING_RULES), and taking the backticks off changes no word.
_CODE_NUMBER = re.compile(r"`(-?\d[\d,]*(?:\.\d+)?)`")


def _tidy_text(text: str) -> str:
    text = text.translate(_CURLY)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = _CODE_NUMBER.sub(r"\1", text)
    return _outside_code(text, _tidy_prose)


def tidy(text: str | None) -> str:
    """The text with the standard's mechanical rules applied; code untouched."""
    if not text:
        return text or ""
    return _outside_fences(text, _tidy_text).strip()


def tidy_question(question):
    """A copy of the question with every text field tidied.

    An answer is tidied wherever it appears - key, keys, distractors and the
    shuffled order - by the same function, so the copies still match.
    """
    q = copy.deepcopy(question)
    q.scenario = tidy(q.scenario)
    q.stem = tidy(q.stem)
    q.key = tidy(q.key)
    q.keys = [tidy(k) for k in (q.keys or [])]
    q.distractors = [tidy(d) for d in (q.distractors or [])]
    q.option_order = [tidy(o) for o in (q.option_order or [])]
    q.explanation = tidy(q.explanation)
    # Code in the correct answer(s) and in no wrong one marks the answer:
    # the standard's first live trial put `region_code` in the key alone.
    # Taking the backticks off changes no word, so it is done here, in
    # every copy of the answer alike.
    keys = set(q.keys if q.question_type == "multi" and q.keys else [q.key])
    options = _options(q)
    coded = {o for o in options if _CODE.search(o)}
    if coded and coded <= keys and len(options) > len(keys):
        plain = {o: _CODE.sub(lambda m: m.group(0)[1:-1], o) for o in coded}
        q.key = plain.get(q.key, q.key)
        q.keys = [plain.get(k, k) for k in q.keys]
        q.option_order = [plain.get(o, o) for o in q.option_order]
    return q


# --- style_notes ------------------------------------------------------------


def _options(question) -> List[str]:
    keys = question.keys if question.question_type == "multi" and question.keys else [question.key]
    return [o for o in dict.fromkeys([*keys, *(question.distractors or [])]) if o and o.strip()]


def text_notes(text: str) -> List[str]:
    """The standard's notes on one piece of text."""
    notes: List[str] = []
    prose = _without_code(text or "")
    singles = list(dict.fromkeys(m.group(1) for m in _SINGLE.finditer(prose)))
    if singles:
        shown = ", ".join(f"'{s}'" for s in singles[:3]) + (" ..." if len(singles) > 3 else "")
        notes.append(
            f"Single quotes around {shown}. Use `code` for a name or value the "
            "reader types or sees, and no quotes for an ordinary word."
        )
    doubles = list(dict.fromkeys(m.group(1) for m in _DOUBLE.finditer(prose) if " " not in m.group(1)))
    if doubles:
        shown = ", ".join(f'"{s}"' for s in doubles[:3])
        notes.append(
            f"Quotes around {shown}. A value goes in `code`; a label or step "
            "name takes no quotes."
        )
    contractions = [w for w in _OTHER_CONTRACTION.findall(prose) if not _POSSESSIVE_OK.match(w)]
    if contractions:
        notes.append(f"Contraction \"{contractions[0]}\": write it out.")
    # The first live trial of the standard (2026-10-10) had the model put
    # ordinary nouns in code - `customer` data, `order` data. A name it may
    # be (a table called sales), so a note rather than a change.
    word = _CODE_WORD.search(text or "")
    if word:
        notes.append(
            f"`{word.group(1)}` {word.group(2)}: an ordinary word takes no code. "
            "Keep code for exact names and values."
        )
    return notes


_CODE_WORD = re.compile(
    r"`([a-z]+)`\s+(data|records?|files?|tables?|systems?|details|information|streams?|rows?)\b"
)


# Every name a flow line may hold, any case: PDI's own.
_ANY_NAME = {n.lower() for n in (*STEPS, *JOB_ENTRIES)}


def flow_notes(text: str) -> List[str]:
    """Notes on an explanation's flow lines (Table input → Filter rows).

    The first live trial (2026-10-10) drew a flow in six of seven
    explanations, and named "Preview" and "Input step" in them - neither is
    a step. A flow that names what PDI has no step for teaches the wrong
    thing, so each name is checked against PDI's own.
    """
    lines = [line for line in _FENCED.sub("", text or "").split("\n") if "→" in line]
    notes: List[str] = []
    if len(lines) > 1:
        notes.append("More than one flow line. Keep the one the answer is about, or none.")
    unknown = []
    for line in lines:
        for part in line.split("→"):
            written = part.strip().strip("`*").strip()
            name = re.sub(r"^(?:the|a|an)\s+|\s+step$", "", written, flags=re.I)
            if name and name.lower() not in _ANY_NAME and written not in unknown:
                unknown.append(written)
    if unknown:
        shown = ", ".join(f'"{u}"' for u in unknown[:3])
        notes.append(
            f"The flow line names {shown}, which PDI has no step called. Use "
            "PDI's step names, or drop the line."
        )
    return notes


# Past this a block stops illustrating and starts being a listing to study.
_LONG_BLOCK = 12


def code_notes(question) -> List[Tuple[str, str]]:
    """Notes on code blocks (1.16.0): explanation only, one at most, short,
    and a JSON block that parses - a model asked for a sample can invent a
    broken one, and a broken sample teaches the wrong syntax."""
    notes: List[Tuple[str, str]] = []
    for field, texts in (("scenario", [question.scenario]), ("stem", [question.stem]),
                         ("options", _options(question))):
        if any(_FENCED.search(t or "") for t in texts):
            notes.append((field, "A code block belongs in the explanation only."))
    found = [b for b in blocks(question.explanation) if b[0] == "code"]
    if len(found) > 1:
        notes.append(("explanation", "More than one code block. Keep the one the answer turns on."))
    for _kind, code, lang in found:
        lines = code.count("\n") + 1
        if lines > _LONG_BLOCK:
            notes.append(("explanation", f"The code block runs to {lines} lines. Show only the part the answer turns on."))
        if lang.lower() == "json":
            try:
                json.loads(code)
            except ValueError as e:
                notes.append(("explanation", f"The JSON block does not parse ({e.msg}, line {e.lineno}). Fix it or drop it."))
    return notes


def style_notes(question) -> List[Tuple[str, str]]:
    """(field, message) for what the writing standard leaves to the author."""
    notes: List[Tuple[str, str]] = code_notes(question)
    for field in ("scenario", "stem", "explanation"):
        notes += [(field, m) for m in text_notes(getattr(question, field, "") or "")]
    notes += [("explanation", m) for m in flow_notes(question.explanation)]
    options = _options(question)
    seen = set()
    for o in options:
        for m in text_notes(o):
            if m not in seen:
                seen.add(m)
                notes.append(("options", m))
    # The same trial put `region_code` in the correct answer and in no other:
    # formatting that marks the right one gives it away.
    keys = set(question.keys if question.question_type == "multi" and question.keys else [question.key])
    coded = [o for o in options if _CODE.search(o)]
    if coded and all(o in keys for o in coded) and len(options) > len(keys):
        notes.append((
            "options",
            "Only the correct answer has `code` in it, which gives it away. Use "
            "code in the wrong answers too, or in none.",
        ))
    endings = {o.rstrip().endswith(".") for o in options}
    if len(endings) > 1:
        notes.append((
            "options",
            "Some answers end with a full stop and some do not. Make them all "
            "sentences with one, or all short phrases without.",
        ))
    bold = re.compile(r"\*\*[^*\n]+\*\*")
    for field, texts in (("scenario", [question.scenario]), ("stem", [question.stem]),
                         ("options", options)):
        if any(bold.search(_without_code(t or "")) for t in texts):
            notes.append((
                field,
                "Bold is for the explanation's key terms only. Anywhere else it "
                "makes words stand out, and in an answer it can give it away.",
            ))
    return notes
