/**
 * Where a link inside a documentation page goes.
 *
 * The pages link to each other the way they do on GitHub — relative `.md`
 * paths, `#anchors`, `../` — so the same file reads correctly in both places.
 * In the app those become moves within the Documentation screen, and an
 * external address goes to the system browser. Pure, so it is tested without
 * rendering anything.
 */

export type DocLink =
  /** Another page (or this one), optionally at a heading. */
  | { kind: "doc"; slug: string; anchor: string }
  /** A heading on the current page. */
  | { kind: "anchor"; anchor: string }
  /** Anything with a scheme: http(s), mailto. */
  | { kind: "external"; url: string }
  /** A repo file that is not a page here (a folder, the licence). Shown as
   *  text: there is nothing in the app to open. */
  | { kind: "none" };

/** Resolve `href`, written in the page at `currentPath` (repo-relative, e.g.
 *  "docs/guides/05-the-bank.md"), against the set of page paths the app
 *  serves. */
export function resolveDocLink(
  href: string,
  currentPath: string,
  pagePaths: ReadonlySet<string>,
): DocLink {
  const raw = (href || "").trim();
  if (/^[a-z][a-z0-9+.-]*:/i.test(raw)) return { kind: "external", url: raw };
  const hash = raw.indexOf("#");
  const path = hash >= 0 ? raw.slice(0, hash) : raw;
  const anchor = hash >= 0 ? decodeURIComponent(raw.slice(hash + 1)) : "";
  if (!path) return { kind: "anchor", anchor };

  const base = currentPath.split("/").slice(0, -1);
  const parts = path.startsWith("/") ? [] : [...base];
  for (const part of path.split("/")) {
    if (part === "..") parts.pop();
    else if (part && part !== ".") parts.push(part);
  }
  const target = parts.join("/");
  if (target.toLowerCase().endsWith(".md") && pagePaths.has(target)) {
    return { kind: "doc", slug: target.slice(0, -3), anchor };
  }
  return { kind: "none" };
}

/** A citation marker in an answer — `[A1]`, `[P2]`, `[A1, P3]` — made into
 *  links the answer's renderer turns into buttons. Code spans are left alone.
 */
export function linkCitations(markdown: string): string {
  return markdown
    .split(/(`[^`]*`)/)
    .map((chunk, i) =>
      i % 2 === 1
        ? chunk
        : chunk.replace(/\[([AP]\d+(?:\s*[,;]\s*[AP]\d+)*)\](?!\()/g, (_m, group: string) =>
            group
              .split(/\s*[,;]\s*/)
              .map((id) => `[${id}](#cite-${id})`)
              .join(" "),
          ),
    )
    .join("");
}

/** Reading time the way the Documentation screen states it. */
export function minutesToRead(words: number): number {
  return Math.max(1, Math.round(words / 200));
}
