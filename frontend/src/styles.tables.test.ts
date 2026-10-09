// @vitest-environment node
/**
 * A bare class that changes `display` must never land on a table element.
 *
 * It has happened twice. `.row` was on every <tr> in the bank table, and a
 * `.row { display: flex }` collapsed it into a column of cells (the reason
 * `.field-row` is named as it is). Then 1.13.1's Exam paper redesign added
 * `.filter-row { display: flex }` for its pills, and the Bank's
 * `<tr className="filter-row">` became a flex box: the column filters
 * stacked in the first column. Each pane's tests passed, because jsdom
 * never applies styles.css, so the clash only showed in the built app.
 *
 * This reads the stylesheet and every component instead. A class whose
 * bare rule (`.name { ... }`, not scoped under a parent) sets `display`
 * is a layout class; no table element may carry one.
 */
import { describe, expect, it } from "vitest";

// Read from disk. Not `./styles.css?raw`: Vitest stubs CSS imports, so that
// arrived empty and this test passed blind (the first assertion below is
// what caught it). Not a static `node:fs` import either: the frontend's
// types have no Node, so the little we use is typed here.
type Fs = {
  readFileSync(path: URL, encoding: "utf8"): string;
  readdirSync(path: URL): string[];
};
const fs = (await import(/* @vite-ignore */ `node:${"fs"}`)) as Fs;
const here = new URL("./", import.meta.url);
const css = fs.readFileSync(new URL("styles.css", here), "utf8");
const COMPONENTS: Record<string, string> = Object.fromEntries(
  fs
    .readdirSync(here)
    .filter((f) => f.endsWith(".tsx") && !f.includes(".test."))
    .map((f) => [`./${f}`, fs.readFileSync(new URL(f, here), "utf8")]),
);

const TABLE_TAGS = "table|thead|tbody|tfoot|tr|td|th";

/** Classes whose own top-level rule sets `display`. */
function layoutClasses(sheet: string): Set<string> {
  const out = new Set<string>();
  const flat = sheet.replace(/\/\*[\s\S]*?\*\//g, "");
  // Innermost rules, so a rule inside @media counts too: it still sets
  // display at that width.
  for (const m of flat.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    if (!/(^|;|\s)display\s*:/.test(m[2])) continue;
    for (const selector of m[1].split(",")) {
      const bare = selector.trim().match(/^\.([a-zA-Z][\w-]*)$/);
      if (bare) out.add(bare[1]);
    }
  }
  return out;
}

/** Every class token written on a table element, with where it was. */
function tableClasses(): Array<{ cls: string; where: string }> {
  const out: Array<{ cls: string; where: string }> = [];
  const quoted = String.raw`(\{` + "`" + String.raw`[^` + "`" + String.raw`]*` + "`" +
    String.raw`\}|"[^"]*"|\{"[^"]*"\})`;
  const tag = new RegExp(String.raw`<(${TABLE_TAGS})\b[^>]*?className=` + quoted, "g");
  for (const [path, text] of Object.entries(COMPONENTS)) {
    const file = path.replace(/^\.\//, "");
    for (const m of text.matchAll(tag)) {
      // Template literals: the ${...} parts are expressions, not class names.
      const literal = m[2].replace(/\$\{[^}]*\}/g, " ");
      for (const cls of literal.match(/[a-zA-Z][\w-]*/g) ?? []) {
        out.push({ cls, where: `${file} <${m[1]}>` });
      }
    }
  }
  return out;
}

describe("styles.css and table elements", () => {
  it("finds the table classes and the layout classes it is checking", () => {
    // Guards the guard: a pattern that matched nothing would pass every time.
    expect(layoutClasses(css).has("field-row")).toBe(true);
    expect(Object.keys(COMPONENTS)).toContain("./BankPane.tsx");
    expect(tableClasses().some((t) => t.cls === "q-row")).toBe(true);
  });

  it("puts no display-changing class on a table element", () => {
    const layout = layoutClasses(css);
    const clashes = tableClasses()
      .filter((t) => layout.has(t.cls))
      .map((t) => `.${t.cls} sets display, and is on ${t.where}`);
    expect(clashes).toEqual([]);
  });
});
