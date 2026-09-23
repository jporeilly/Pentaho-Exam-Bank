import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DocsPane } from "./DocsPane";
import type { DocAnswer, DocDocument, DocSearchResult } from "./api";

const SECTION = {
  document: "How-To Guide",
  heading: "Importing Existing Questions",
  snippet: "Drop a CSV into the Import pane.",
  score: 6,
};

function answer(over: Partial<DocAnswer> = {}): DocAnswer {
  return {
    answered: true,
    answer: "Use the Import pane.",
    sources: [SECTION],
    provider: "ollama",
    model: "gemma4:12b",
    ...over,
  };
}

function results(over: Partial<DocSearchResult> = {}): DocSearchResult {
  return { query: "import", sectionsSearched: 158, results: [SECTION], ...over };
}

const DOCUMENTS: DocDocument[] = [
  {
    document: "How-To Guide",
    sections: [{ heading: "Importing Existing Questions", text: "Drop a CSV in." }],
  },
  { document: "README", sections: [{ heading: "Installing", text: "Run the installer." }] },
];

function mockApi(handlers: {
  ask?: DocAnswer | { status: number; detail: string };
  search?: DocSearchResult;
  documents?: DocDocument[];
} = {}) {
  const calls: Array<{ path: string; body: unknown }> = [];
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const path = String(url);
    calls.push({ path, body: init?.body ? JSON.parse(String(init.body)) : null });

    const json = (body: unknown, status = 200) =>
      Promise.resolve(
        new Response(JSON.stringify(body), {
          status,
          headers: { "Content-Type": "application/json" },
        }),
      );

    if (path.includes("/docs/ask")) {
      const r = handlers.ask ?? answer();
      return "status" in r ? json({ detail: r.detail }, r.status) : json(r);
    }
    if (path.includes("/docs/search")) return json(handlers.search ?? results());
    return json(handlers.documents ?? DOCUMENTS);
  });
  return calls;
}

async function ask(question = "How do I import a CSV?") {
  await userEvent.type(await screen.findByLabelText("Your question"), question);
  await userEvent.click(screen.getByRole("button", { name: "Ask the guide" }));
}

afterEach(() => vi.unstubAllGlobals());

describe("asking", () => {
  it("says up front that answers come only from the app's own docs", async () => {
    mockApi();
    render(<DocsPane />);

    expect(await screen.findByText(/never from outside them/)).toBeInTheDocument();
  });

  it("shows the answer with the sections it was built from", async () => {
    // An answer about your own app is only worth anything if you can check
    // what it read.
    mockApi();
    render(<DocsPane />);

    await ask();

    expect(await screen.findByText("Use the Import pane.")).toBeInTheDocument();
    expect(screen.getByText("Built from")).toBeInTheDocument();
    const sources = screen.getByRole("list");
    expect(within(sources).getByText("Importing Existing Questions")).toBeInTheDocument();
  });

  it("names the model that answered", async () => {
    mockApi();
    render(<DocsPane />);

    await ask();

    expect(await screen.findByText(/gemma4:12b/)).toBeInTheDocument();
  });

  it("says plainly when the docs do not cover the question", async () => {
    // The server never called the model in this case. Presenting it as a
    // normal answer would hide exactly the thing worth knowing.
    mockApi({
      ask: answer({
        answered: false,
        answer: "Nothing in the documentation covers that.",
        sources: [],
      }),
    });
    render(<DocsPane />);

    await ask("kubernetes helm chart");

    expect(await screen.findByText("Not covered")).toBeInTheDocument();
    expect(screen.queryByText("Built from")).not.toBeInTheDocument();
  });

  it("will not ask an empty question", async () => {
    mockApi();
    render(<DocsPane />);

    expect(await screen.findByRole("button", { name: "Ask the guide" })).toBeDisabled();
  });

  it("shows the server's refusal rather than inventing one", async () => {
    mockApi({
      ask: { status: 503, detail: "ANTHROPIC_API_KEY is not set in the environment." },
    });
    render(<DocsPane />);

    await ask();

    expect(await screen.findByText(/ANTHROPIC_API_KEY/)).toBeInTheDocument();
  });
});

describe("searching", () => {
  it("lists matching sections without calling the model", async () => {
    const calls = mockApi();
    render(<DocsPane />);

    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await userEvent.type(await screen.findByLabelText("Search the documentation"), "import");

    expect(await screen.findByText("Importing Existing Questions")).toBeInTheDocument();
    expect(calls.some((c) => c.path.includes("/docs/ask"))).toBe(false);
  });

  it("says how much was searched when nothing matches", async () => {
    // So an empty result reads as "not in the docs" rather than "docs not
    // loaded", which otherwise look identical.
    mockApi({ search: results({ query: "helm", results: [], sectionsSearched: 158 }) });
    render(<DocsPane />);

    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await userEvent.type(await screen.findByLabelText("Search the documentation"), "helm");

    expect(await screen.findByText(/158 sections/)).toBeInTheDocument();
  });

  it("does not search on every keystroke", async () => {
    const calls = mockApi();
    render(<DocsPane />);

    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await userEvent.type(await screen.findByLabelText("Search the documentation"), "import");
    await screen.findByText("Importing Existing Questions");

    const searches = calls.filter((c) => c.path.includes("/docs/search"));
    expect(searches.length).toBeLessThan(6);
  });
});

describe("reading", () => {
  it("shows a document's sections", async () => {
    mockApi();
    render(<DocsPane />);

    await userEvent.click(screen.getByRole("button", { name: "Read" }));

    expect(await screen.findByText("Drop a CSV in.")).toBeInTheDocument();
  });

  it("switches between documents", async () => {
    mockApi();
    render(<DocsPane />);

    await userEvent.click(screen.getByRole("button", { name: "Read" }));
    await userEvent.click(await screen.findByRole("button", { name: "README" }));

    expect(await screen.findByText("Run the installer.")).toBeInTheDocument();
    expect(screen.queryByText("Drop a CSV in.")).not.toBeInTheDocument();
  });

  it("says so when there is no documentation beside the app", async () => {
    mockApi({ documents: [] });
    render(<DocsPane />);

    await userEvent.click(screen.getByRole("button", { name: "Read" }));

    expect(await screen.findByText(/No documentation was found/)).toBeInTheDocument();
  });
});
