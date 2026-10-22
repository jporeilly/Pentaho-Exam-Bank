import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import cases from "./inlineFormat.cases.json";
import {
  blocks, Formatted, hasFormat, paragraphs, parseInline, plainText, toggleWrap, wrapFence,
  type InlineNode,
} from "./inlineFormat";

describe("the inline formatting contract", () => {
  // The same file the Python exporters and the Content Manager's quiz are
  // tested against: one meaning for "**" across the three.
  it.each(cases.cases.map((c) => [JSON.stringify(c.in), c] as const))("%s", (_, c) => {
    expect(parseInline(c.in)).toEqual(c.nodes as InlineNode[]);
  });
});

describe("the paragraph contract", () => {
  it.each(cases.paragraphs.map((c) => [JSON.stringify(c.in), c] as const))("%s", (_, c) => {
    expect(paragraphs(c.in)).toEqual(c.paragraphs);
  });
});

describe("the block contract", () => {
  it.each(cases.blocks.map((c) => [JSON.stringify(c.in), c] as const))("%s", (_, c) => {
    expect(blocks(c.in)).toEqual(c.blocks);
  });
});

describe("code blocks on screen", () => {
  it("draws a code block as typed, between its paragraphs", () => {
    const html = renderToStaticMarkup(
      <Formatted text={"Given:\n\n```json\n{\"a\": \"**x**\"}\n```\n\nthen `$.a` reads it."} />,
    );
    expect(html).toBe(
      '<span class="fmt-p">Given:</span>' +
        '<pre class="fmt-code" data-lang="json"><code>{&quot;a&quot;: &quot;**x**&quot;}</code></pre>' +
        '<span class="fmt-p">then <code class="inline-code">$.a</code> reads it.</span>',
    );
  });

  it("draws a text that is only a code block as a block", () => {
    expect(renderToStaticMarkup(<Formatted text={"```\nx = 1\n```"} />)).toBe(
      '<pre class="fmt-code"><code>x = 1</code></pre>',
    );
  });
});

describe("paragraphs on screen", () => {
  it("draws each paragraph as its own block, formatted on its own", () => {
    const html = renderToStaticMarkup(<Formatted text={"the **key** idea\n\nwhy it *matters*"} />);
    expect(html).toBe(
      '<span class="fmt-p">the <strong>key</strong> idea</span>' +
        '<span class="fmt-p">why it <em>matters</em></span>',
    );
  });

  it("leaves text with no blank line exactly as it was", () => {
    expect(renderToStaticMarkup(<Formatted text={"line one\n**line two**"} />)).toBe(
      "line one\n<strong>line two</strong>",
    );
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

describe("wrapping a selection as a code block", () => {
  it("puts fences on lines of their own, a blank line from the prose", () => {
    const v = "Given this:{\"a\": 1}then more.";
    const r = wrapFence(v, 11, 19);
    expect(r.value).toBe("Given this:\n\n```\n{\"a\": 1}\n```\n\nthen more.");
    expect(r.value.slice(r.start, r.end)).toBe("{\"a\": 1}");
  });

  it("adds no blank lines the text already has", () => {
    const r = wrapFence("Prose.\n\nx = 1\n\nMore.", 8, 13);
    expect(r.value).toBe("Prose.\n\n```\nx = 1\n```\n\nMore.");
  });

  it("leaves the caret inside empty fences when nothing is selected", () => {
    const r = wrapFence("", 0, 0);
    expect(r.value).toBe("```\n\n```");
    expect(r).toMatchObject({ start: 4, end: 4 });
    expect(blocks(r.value)).toEqual([["code", "", ""]]);
  });
});
