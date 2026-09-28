/**
 * System → Documentation, rendered against a fake backend.
 *
 * What these hold: the guide opens on its hub; the sidebar is the sections
 * and their pages; a page renders as markdown with the backend's heading ids
 * (matched by line, not re-slugged); links between pages move within the
 * screen; search opens a page at the heading it matched; and AI Chat's
 * request to show a page at a heading is honoured.
 */
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DocsPane } from "./DocsPane";
import type { DocIndex, DocPage, DocSearchResult } from "./api";

const INDEX: DocIndex = {
  count: 4,
  sections: [
    {
      name: "Start here",
      items: [
        { slug: "HOW_TO_GUIDE", title: "How-To Guide", section: "Start here", summary: "The hub.", words: 400, path: "HOW_TO_GUIDE.md" },
      ],
    },
    {
      name: "Using the Exam Bank",
      items: [
        { slug: "docs/guides/05-the-bank", title: "The Bank", section: "Using the Exam Bank", summary: "Lists questions.", words: 900, path: "docs/guides/05-the-bank.md" },
        { slug: "docs/guides/06-review", title: "Review", section: "Using the Exam Bank", summary: "Statuses.", words: 300, path: "docs/guides/06-review.md" },
      ],
    },
    {
      name: "Project",
      items: [
        { slug: "CHANGELOG", title: "Changelog", section: "Project", summary: "", words: 20000, path: "CHANGELOG.md" },
      ],
    },
  ],
};

const PAGES: Record<string, DocPage> = {
  HOW_TO_GUIDE: {
    ...INDEX.sections[0].items[0],
    content: "The guide is a set of pages.\n\n- [The Bank](docs/guides/05-the-bank.md)\n- [Ollama](https://ollama.com)\n",
    headings: [],
  },
  "docs/guides/05-the-bank": {
    ...INDEX.sections[1].items[0],
    content: "The Bank lists questions.\n\n## Saving a Question\n\nPress Save.\n\n## Sending it back\n\nSee [Review](06-review.md).\n",
    headings: [
      { level: 2, text: "Saving a Question", id: "saving-a-question", line: 3 },
      { level: 2, text: "Sending it back", id: "sending-it-back", line: 7 },
    ],
  },
  "docs/guides/06-review": {
    ...INDEX.sections[1].items[1],
    content: "| Status | Meaning |\n| --- | --- |\n| Draft | New |\n",
    headings: [],
  },
};

function hits(over: Partial<DocSearchResult> = {}): DocSearchResult {
  return {
    query: "save",
    sectionsSearched: 115,
    results: [
      { slug: "docs/guides/05-the-bank", page: "The Bank", section: "Using the Exam Bank", heading: "Saving a Question", anchor: "saving-a-question", snippet: "Press **Save**.", score: 6 },
    ],
    ...over,
  };
}

function mockApi(handlers: { search?: DocSearchResult } = {}) {
  const calls: string[] = [];
  const bodies: unknown[] = [];
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const path = String(url);
    calls.push(path);
    if (init?.body) bodies.push(JSON.parse(String(init.body)));
    const json = (body: unknown, status = 200) =>
      Promise.resolve(new Response(status === 204 ? null : JSON.stringify(body), {
        status, headers: { "Content-Type": "application/json" },
      }));
    if (path.includes("/api/open-url")) return json(null, 204);
    if (path.includes("/api/docs/search")) return json(handlers.search ?? hits());
    if (path.includes("/api/docs/page")) {
      const slug = new URL(path, "http://x").searchParams.get("slug") ?? "";
      return PAGES[slug] ? json(PAGES[slug]) : json({ detail: "no page" }, 404);
    }
    return json(INDEX);
  });
  return { calls, bodies };
}

const scrolled: string[] = [];
beforeEach(() => {
  window.localStorage.clear();
  scrolled.length = 0;
  Element.prototype.scrollIntoView = function (this: Element) {
    scrolled.push(this.id);
  } as never;
  HTMLElement.prototype.scrollTo = (() => {}) as never;
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
    cb(0);
    return 0;
  });
});
afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("the sidebar and the first page", () => {
  it("opens on the guide's hub, with every section and page listed", async () => {
    mockApi();
    render(<DocsPane />);

    expect(await screen.findByRole("heading", { level: 1, name: "How-To Guide" })).toBeInTheDocument();
    const nav = screen.getByRole("complementary", { name: "Documentation" });
    for (const name of ["Start here", "Using the Exam Bank", "Project"]) {
      expect(within(nav).getByRole("button", { name: new RegExp(name) })).toBeInTheDocument();
    }
    expect(within(nav).getByRole("button", { name: "The Bank" })).toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: "How-To Guide" })).toHaveAttribute("aria-current", "page");
  });

  it("returns to the page read last", async () => {
    window.localStorage.setItem("peb-docs-page", "docs/guides/06-review");
    mockApi();
    render(<DocsPane />);

    expect(await screen.findByRole("heading", { level: 1, name: "Review" })).toBeInTheDocument();
  });

  it("shows where a page sits and how long it is", async () => {
    mockApi();
    render(<DocsPane />);
    await userEvent.click(await screen.findByRole("button", { name: "The Bank" }));

    const crumbs = await screen.findByRole("navigation", { name: "Breadcrumb" });
    expect(crumbs).toHaveTextContent("Documentation");
    expect(crumbs).toHaveTextContent("Using the Exam Bank");
    expect(screen.getByText(/900 words · about 5 min read/)).toBeInTheDocument();
  });

  it("collapses a section, but never the one holding the open page", async () => {
    mockApi();
    render(<DocsPane />);
    await screen.findByRole("heading", { level: 1, name: "How-To Guide" });

    await userEvent.click(screen.getByRole("button", { name: /Using the Exam Bank/ }));
    expect(screen.queryByRole("button", { name: "The Bank" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Start here/ }));
    expect(screen.getByRole("button", { name: "How-To Guide" })).toBeInTheDocument();
  });
});

describe("a page", () => {
  it("renders markdown, with the backend's heading ids", async () => {
    mockApi();
    render(<DocsPane />);
    await userEvent.click(await screen.findByRole("button", { name: "The Bank" }));

    const h = await screen.findByRole("heading", { level: 2, name: "Saving a Question" });
    expect(h).toHaveAttribute("id", "saving-a-question");
  });

  it("lists its headings under On this page, and scrolls to one", async () => {
    mockApi();
    render(<DocsPane />);
    await userEvent.click(await screen.findByRole("button", { name: "The Bank" }));

    const toc = await screen.findByRole("complementary", { name: "On this page" });
    await userEvent.click(within(toc).getByRole("link", { name: "Sending it back" }));
    expect(scrolled).toContain("sending-it-back");
  });

  it("renders a table", async () => {
    mockApi();
    render(<DocsPane />);
    await userEvent.click(await screen.findByRole("button", { name: "Review" }));

    expect(await screen.findByRole("columnheader", { name: "Status" })).toBeInTheDocument();
  });

  it("follows a link to another page inside the screen", async () => {
    mockApi();
    render(<DocsPane />);
    await userEvent.click(await screen.findByRole("button", { name: "The Bank" }));
    await userEvent.click(await screen.findByRole("link", { name: "Review" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Review" })).toBeInTheDocument();
  });

  it("opens an outside link through the backend, in the system browser", async () => {
    const { calls, bodies } = mockApi();
    render(<DocsPane />);
    await userEvent.click(await screen.findByRole("link", { name: "Ollama" }));

    expect(calls.some((c) => c.includes("/api/open-url"))).toBe(true);
    expect(bodies).toContainEqual({ url: "https://ollama.com" });
  });

  it("steps through the pages with Previous and Next", async () => {
    mockApi();
    render(<DocsPane />);
    await screen.findByRole("heading", { level: 1, name: "How-To Guide" });

    const pager = screen.getByRole("navigation", { name: "Previous and next page" });
    await userEvent.click(within(pager).getByRole("button", { name: /Next/ }));
    expect(await screen.findByRole("heading", { level: 1, name: "The Bank" })).toBeInTheDocument();
  });
});

describe("search", () => {
  it("opens the page at the heading that matched", async () => {
    mockApi();
    render(<DocsPane />);
    await screen.findByRole("heading", { level: 1, name: "How-To Guide" });

    await userEvent.type(screen.getByRole("searchbox", { name: "Search the documentation" }), "save");
    const hit = await screen.findByRole("button", { name: /The Bank › Saving a Question/ });
    expect(hit).toHaveTextContent("Press Save."); // markdown marks removed
    await userEvent.click(hit);

    expect(await screen.findByRole("heading", { level: 1, name: "The Bank" })).toBeInTheDocument();
    expect(scrolled).toContain("saving-a-question");
  });

  it("says how much it looked through when nothing matches", async () => {
    mockApi({ search: hits({ results: [] }) });
    render(<DocsPane />);
    await screen.findByRole("heading", { level: 1, name: "How-To Guide" });

    await userEvent.type(screen.getByRole("searchbox"), "kubernetes");
    expect(await screen.findByText(/Nothing about “kubernetes” in 115 sections/)).toBeInTheDocument();
  });
});

describe("opened from AI Chat", () => {
  it("shows the page asked for, at its heading", async () => {
    mockApi();
    const { rerender } = render(<DocsPane target={null} />);
    await screen.findByRole("heading", { level: 1, name: "How-To Guide" });

    rerender(<DocsPane target={{ slug: "docs/guides/05-the-bank", anchor: "sending-it-back", seq: 1 }} />);
    expect(await screen.findByRole("heading", { level: 1, name: "The Bank" })).toBeInTheDocument();
    await act(async () => {});
    expect(scrolled).toContain("sending-it-back");
  });

  it("hands the request back as done, so it is used once", async () => {
    // Found in the browser: left standing in App, the request reopened its
    // page every time Documentation was shown, over the page read since.
    mockApi();
    const done = vi.fn();
    render(<DocsPane target={{ slug: "docs/guides/06-review", anchor: "", seq: 3 }} onTargetDone={done} />);

    expect(await screen.findByRole("heading", { level: 1, name: "Review" })).toBeInTheDocument();
    expect(done).toHaveBeenCalledTimes(1);
  });
});
