import type { ReactNode } from "react";

/**
 * Inline formatting in question text: **bold**, *italic* and `code`.
 *
 * Stored as those markers in the plain text the bank already keeps, so a
 * question stays a string everywhere it travels - the database, CSV/JSON,
 * the course's exam.json - and the Content Manager's quiz renders the same
 * three things with a twin of this parser. `inlineFormat.cases.json` is the
 * contract both are tested against (and the Python exporters too).
 *
 * Strict on purpose, because the bank already holds text that is NOT
 * formatting: `[Sales] * [Quantity]`, `industrial/*\/sensor`,
 * `$.customer.email[*]`, `<div id="panel_1">`, `snake_case`. So:
 *  - an opening marker needs a non-space after it and no letter or digit
 *    before it; a closing one the mirror image. A lone or spaced `*` is
 *    just an asterisk;
 *  - underscores never format (identifiers are full of them);
 *  - nothing is ever HTML: every node renders as React text.
 * A backslash keeps a marker literal: `\*`, `` \` ``, `\\`.
 */

export type InlineNode =
  | ["text", string]
  | ["strong", InlineNode[]]
  | ["em", InlineNode[]]
  | ["code", string];

const ESCAPABLE = new Set(["*", "`", "\\"]);
const WORD = /[\p{L}\p{N}]/u;

const isWord = (c: string | undefined) => c !== undefined && WORD.test(c);

// What may sit just INSIDE a marker. Words start with a letter, a digit, a
// quote or an opening bracket, and end with a letter, a digit, a closing
// quote or bracket, or sentence punctuation ("**Note:**"). Not `]`, `.` or `/` after an
// opener: that is a wildcard - JSONPath `[*]` and `.*.`, a glob `/*/` -
// and two of them in one explanation once italicised everything between.
const OPENS_WITH = new Set(["'", '"', "‘", "“", "(", "[", "{", "$", "`"]);
const CLOSES_WITH = new Set(["'", '"', "’", "”", ")", "]", "}", "`", ".", "!", "?", "%", ":"]);
const canStart = (c: string | undefined) => isWord(c) || (c !== undefined && OPENS_WITH.has(c));
const canEnd = (c: string | undefined) => isWord(c) || (c !== undefined && CLOSES_WITH.has(c));

function runLength(s: string, k: number): number {
  let r = 0;
  while (s[k + r] === "*") r++;
  return r;
}

/** Where the closing `**` (len 2) or `*` (len 1) for an opener ends, or -1.
 *  Returns the index of the closer's first character. Code spans and
 *  escapes are stepped over, so a marker inside them never closes. */
function findCloser(s: string, from: number, len: 1 | 2): number {
  let k = from;
  while (k < s.length) {
    const c = s[k];
    if (c === "\\" && ESCAPABLE.has(s[k + 1])) {
      k += 2;
      continue;
    }
    if (c === "`") {
      const end = s.indexOf("`", k + 1);
      if (end > k + 1) {
        k = end + 1;
        continue;
      }
      k += 1;
      continue;
    }
    if (c === "*") {
      const r = runLength(s, k);
      const after = s[k + r];
      const before = s[k - 1];
      const closes = k > from && canEnd(before) && !isWord(after);
      if (closes) {
        // A run of 3 closes both: `**` takes its last two, `*` its last one.
        if (len === 2 && r >= 2) return k + r - 2;
        if (len === 1 && r % 2 === 1) return k + r - 1;
      }
      k += r;
      continue;
    }
    k += 1;
  }
  return -1;
}

export function parseInline(s: string): InlineNode[] {
  const out: InlineNode[] = [];
  let text = "";
  const flush = () => {
    if (text) out.push(["text", text]);
    text = "";
  };
  let i = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === "\\" && ESCAPABLE.has(s[i + 1])) {
      text += s[i + 1];
      i += 2;
      continue;
    }
    if (c === "`") {
      const end = s.indexOf("`", i + 1);
      if (end > i + 1) {
        flush();
        out.push(["code", s.slice(i + 1, end)]);
        i = end + 1;
        continue;
      }
      text += c;
      i += 1;
      continue;
    }
    if (c === "*") {
      const r = runLength(s, i);
      const opens = !isWord(s[i - 1]) && canStart(s[i + r]);
      if (opens) {
        if (r >= 2) {
          const close = findCloser(s, i + 2, 2);
          if (close > i + 2) {
            flush();
            out.push(["strong", parseInline(s.slice(i + 2, close))]);
            i = close + 2;
            continue;
          }
        }
        const close = findCloser(s, i + 1, 1);
        if (close > i + 1) {
          flush();
          out.push(["em", parseInline(s.slice(i + 1, close))]);
          i = close + 1;
          continue;
        }
      }
      text += s.slice(i, i + r);
      i += r;
      continue;
    }
    text += c;
    i += 1;
  }
  flush();
  return out;
}

function render(nodes: InlineNode[], key = ""): ReactNode[] {
  return nodes.map((n, i) => {
    const k = `${key}${i}`;
    switch (n[0]) {
      case "text":
        return n[1];
      case "code":
        return (
          <code key={k} className="inline-code">
            {n[1]}
          </code>
        );
      case "strong":
        return <strong key={k}>{render(n[1], `${k}.`)}</strong>;
      case "em":
        return <em key={k}>{render(n[1], `${k}.`)}</em>;
    }
  });
}

/** Question text with its formatting drawn. Text only - never HTML. */
export function Formatted({ text }: { text: string | null | undefined }) {
  return <>{render(parseInline(text ?? ""))}</>;
}

/** The words without their markers: for titles, dialogs and lengths. */
export function plainText(s: string | null | undefined): string {
  const walk = (nodes: InlineNode[]): string =>
    nodes.map((n) => (n[0] === "text" || n[0] === "code" ? n[1] : walk(n[1]))).join("");
  return walk(parseInline(s ?? ""));
}

/** Whether the text carries any formatting worth previewing. */
export function hasFormat(s: string | null | undefined): boolean {
  return parseInline(s ?? "").some((n) => n[0] !== "text");
}

export type Marker = "**" | "*" | "`";

/**
 * Bold/italic/code on a selection, as a toolbar button or Ctrl+B does it:
 * wraps the selection, or unwraps it when it is already wrapped (markers
 * just outside it, or selected along with it). An empty selection gets an
 * empty pair with the caret between. Returns the new value and the new
 * selection, which covers the same words.
 */
export function toggleWrap(
  value: string,
  start: number,
  end: number,
  marker: Marker,
): { value: string; start: number; end: number } {
  // A double-click selects the trailing space too; markers hug the words.
  while (start < end && /\s/.test(value[start])) start++;
  while (end > start && /\s/.test(value[end - 1])) end--;
  const m = marker.length;

  // Asterisks immediately outside the selection: bold is 2 or more on both
  // sides, italic an odd count (1, or 3 = bold+italic).
  const starsBefore = (() => {
    let n = 0;
    while (value[start - 1 - n] === "*") n++;
    return n;
  })();
  const starsAfter = runLength(value, end);
  const wrappedOutside =
    marker === "`"
      ? value[start - 1] === "`" && value[end] === "`"
      : marker === "**"
        ? starsBefore >= 2 && starsAfter >= 2
        : starsBefore % 2 === 1 && starsAfter % 2 === 1;
  if (start < end && wrappedOutside) {
    // Bold sits OUTSIDE italic in "***x***", so it is the outermost pair
    // of the run; italic the innermost.
    const cutBefore = marker === "**" ? start - starsBefore : start - m;
    const cutAfter = marker === "**" ? end + starsAfter - m : end;
    const v =
      value.slice(0, cutBefore) +
      value.slice(cutBefore + m, cutAfter) +
      value.slice(cutAfter + m);
    const ns = start - m;
    return { value: v, start: ns, end: ns + (end - start) };
  }

  const sel = value.slice(start, end);
  const selectedWithMarkers =
    sel.length > 2 * m &&
    sel.startsWith(marker) &&
    sel.endsWith(marker) &&
    (marker !== "*" || (!sel.startsWith("**") || sel.startsWith("***")));
  if (selectedWithMarkers) {
    const inner = sel.slice(m, sel.length - m);
    return { value: value.slice(0, start) + inner + value.slice(end), start, end: start + inner.length };
  }

  const v = value.slice(0, start) + marker + sel + marker + value.slice(end);
  return { value: v, start: start + m, end: end + m };
}
