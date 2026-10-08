import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import cases from "./inlineFormat.cases.json";
import { Formatted, hasFormat, parseInline, plainText, toggleWrap, type InlineNode } from "./inlineFormat";

describe("the inline formatting contract", () => {
  // The same file the Python exporters and the Content Manager's quiz are
  // tested against: one meaning for "**" across the three.
  it.each(cases.cases.map((c) => [JSON.stringify(c.in), c] as const))("%s", (_, c) => {
    expect(parseInline(c.in)).toEqual(c.nodes as InlineNode[]);
  });
});

describe("rendering", () => {
  it("draws strong, em and code, and never HTML from the text", () => {
    const html = renderToStaticMarkup(<Formatted text={'**b** *i* `c` <img src=x onerror="alert(1)">'} />);
    expect(html).toBe(
      '<strong>b</strong> <em>i</em> <code class="inline-code">c</code> ' +
        "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;",
    );
  });

  it("plainText drops the markers and keeps the words", () => {
    expect(plainText("a **bold** *it* `code` \\*x\\*")).toBe("a bold it code *x*");
    expect(plainText("[Sales] * [Quantity]")).toBe("[Sales] * [Quantity]");
  });

  it("hasFormat only for real formatting", () => {
    expect(hasFormat("a **b**")).toBe(true);
    expect(hasFormat("industrial/*/sensor")).toBe(false);
    expect(hasFormat("")).toBe(false);
  });
});

describe("toggleWrap", () => {
  const sel = (v: string, word: string) => {
    const s = v.indexOf(word);
    return [s, s + word.length] as const;
  };

  it("wraps a selection and keeps the same words selected", () => {
    const r = toggleWrap("make this bold", ...sel("make this bold", "this"), "**");
    expect(r.value).toBe("make **this** bold");
    expect(r.value.slice(r.start, r.end)).toBe("this");
  });

  it("unwraps when the markers sit just outside the selection", () => {
    const r = toggleWrap("make **this** bold", ...sel("make **this** bold", "this"), "**");
    expect(r.value).toBe("make this bold");
    expect(r.value.slice(r.start, r.end)).toBe("this");
  });

  it("unwraps when the markers were selected too", () => {
    const r = toggleWrap("make **this** bold", ...sel("make **this** bold", "**this**"), "**");
    expect(r.value).toBe("make this bold");
  });

  it("italic inside bold, then out again, without touching the bold", () => {
    const v = "a **word** here";
    const on = toggleWrap(v, ...sel(v, "word"), "*");
    expect(on.value).toBe("a ***word*** here");
    expect(parseInline(on.value)).toEqual([
      ["text", "a "],
      ["strong", [["em", [["text", "word"]]]]],
      ["text", " here"],
    ]);
    const off = toggleWrap(on.value, on.start, on.end, "*");
    expect(off.value).toBe(v);
    const unbold = toggleWrap(on.value, on.start, on.end, "**");
    expect(unbold.value).toBe("a *word* here");
  });

  it("bold on an italic word nests rather than unwrapping it", () => {
    const v = "an *idea* here";
    const r = toggleWrap(v, ...sel(v, "idea"), "**");
    expect(r.value).toBe("an ***idea*** here");
  });

  it("code toggles with backticks", () => {
    const v = "the kettle.properties file";
    const on = toggleWrap(v, ...sel(v, "kettle.properties"), "`");
    expect(on.value).toBe("the `kettle.properties` file");
    expect(toggleWrap(on.value, on.start, on.end, "`").value).toBe(v);
  });

  it("a double-click's trailing space stays outside the markers", () => {
    const v = "bold this please";
    const s = v.indexOf("this");
    const r = toggleWrap(v, s, s + 5, "**");
    expect(r.value).toBe("bold **this** please");
  });

  it("an empty selection gets an empty pair with the caret inside", () => {
    const r = toggleWrap("ab", 1, 1, "**");
    expect(r.value).toBe("a****b");
    expect([r.start, r.end]).toEqual([3, 3]);
  });
});
