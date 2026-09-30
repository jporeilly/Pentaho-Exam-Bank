import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BankPane } from "./BankPane";
import type { Question } from "./api";

function question(over: Partial<Question> = {}): Question {
  return {
    id: "m1-q1", scenario: "", stem: "Which step reads a file?",
    question_type: "single", key: "CSV input", keys: [], key_source_text: "",
    distractors: ["Table output"], option_order: ["CSV input", "Table output"],
    explanation: "", topic: "Getting Started", tags: [], difficulty: "Medium",
    bloom_level: "Apply", certification_id: "c1", pool_order: 0, status: "draft",
    assigned_sme: "", review_history: [], version_history: [],
    updated_at: "2026-09-21T10:00:00", ...over,
  };
}

/** Route each call by path so the component gets what it actually asks for. */
function mockApi(questions: Question[], total = questions.length) {
  const calls: string[] = [];
  vi.stubGlobal("fetch", (url: string) => {
    calls.push(String(url));
    const body = String(url).includes("/api/certifications")
      ? [{ id: "c1", name: "DI Practitioner", description: "", sourceType: "pcm",
           sourceRef: "developer-di-practitioner", questionCount: total }]
      : { items: questions, total, limit: 25, offset: 0 };
    return Promise.resolve(
      new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } }),
    );
  });
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

describe("BankPane", () => {
  it("lists what the bank holds", async () => {
    mockApi([question(), question({ id: "m1-q2", stem: "Which step writes rows?" })]);
    render(<BankPane />);

    expect(await screen.findByText("Which step reads a file?")).toBeInTheDocument();
    expect(screen.getByText("Which step writes rows?")).toBeInTheDocument();
  });

  it("shows the range and the unpaged total", async () => {
    mockApi([question()], 395);
    render(<BankPane />);
    expect(await screen.findByText("1–1 of 395")).toBeInTheDocument();
  });

  it("shows an adopted question's pool position, and a dash when it has none", async () => {
    // pool_order is what puts a published pool back in the author's order, so
    // whether a question carries one is worth being able to see.
    mockApi([question({ pool_order: 7 }), question({ id: "gen-1", pool_order: -1 })]);
    render(<BankPane />);

    await screen.findByText("7");
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("says so plainly when nothing matches", async () => {
    mockApi([], 0);
    render(<BankPane />);
    expect(await screen.findByText("No questions match those filters.")).toBeInTheDocument();
  });

  it("shows the server's message when a request fails", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: "database is locked" }), {
          status: 500, headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    render(<BankPane />);
    expect(await screen.findByText(/database is locked/)).toBeInTheDocument();
  });

  it("returns to the first page when a filter changes", async () => {
    // Staying on page 4 of a result set that now has one page shows an empty
    // table and reads as a bug rather than as a filter.
    const calls = mockApi([question()], 395);
    render(<BankPane />);
    await screen.findByText("Which step reads a file?");

    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(calls.at(-1)).toContain("offset=25"));

    await userEvent.selectOptions(
      screen.getByDisplayValue("Any status"),
      "approved",
    );
    await waitFor(() => {
      const last = calls.at(-1)!;
      expect(last).toContain("status=approved");
      expect(last).toContain("offset=0");
    });
  });

  it("ignores a slow response that a newer one has already overtaken", async () => {
    // Typing fires a request per keystroke and they do not have to come back
    // in order. Without a guard, a slow "cluster" landing after a fast
    // "clustered" leaves the wrong rows sitting under the right search box.
    const pending: Array<(value: Response) => void> = [];
    vi.stubGlobal("fetch", (url: string) => {
      // Only the question list is held back; the pane's other lookups (the
      // certifications, Settings for the page size, the vocabulary) answer at
      // once, with nothing, and the pane falls back where it needs to.
      if (!String(url).includes("/api/questions")) {
        return Promise.resolve(
          new Response("[]", { headers: { "Content-Type": "application/json" } }),
        );
      }
      return new Promise<Response>((resolve) => pending.push(resolve));
    });

    render(<BankPane />);
    await waitFor(() => expect(pending.length).toBe(1));

    await userEvent.type(screen.getByPlaceholderText(/Search stems/), "a");
    await waitFor(() => expect(pending.length).toBe(2));

    const reply = (stem: string) =>
      new Response(
        JSON.stringify({ items: [question({ stem })], total: 1, limit: 25, offset: 0 }),
        { headers: { "Content-Type": "application/json" } },
      );

    // The NEWEST request answers first, then the stale one arrives late.
    pending[1](reply("NEWEST result"));
    await screen.findByText("NEWEST result");

    // Resolve the stale one inside act() and let every queued microtask and
    // re-render settle BEFORE asserting. A plain waitFor passes on its first
    // check — before the late update has had a chance to land — so it reports
    // success whether the guard is there or not. This assertion has to be
    // made after the damage would have been done, not instead of it.
    await act(async () => {
      pending[0](reply("STALE result"));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByText("NEWEST result")).toBeInTheDocument();
    expect(screen.queryByText("STALE result")).not.toBeInTheDocument();
  });

  it("carries the active filters into the export link", async () => {
    // Exporting "what I am looking at" is the whole point; an export that
    // ignored the filters would quietly hand over the entire bank.
    mockApi([question()], 1);
    render(<BankPane />);
    await screen.findByText("Which step reads a file?");

    await userEvent.selectOptions(screen.getByDisplayValue("Any status"), "draft");

    await waitFor(() => {
      const link = screen.getByRole("button", { name: "Export" })
        .closest("a") as HTMLAnchorElement;
      expect(link.getAttribute("href")).toContain("status=draft");
    });
  });
});

describe("paging and sorting", () => {
  // "Questions per page" was saved in Settings and never read: the Bank asked
  // for 25 whatever it said.
  it("asks for the page size Settings holds", async () => {
    const calls: string[] = [];
    vi.stubGlobal("fetch", (url: string) => {
      calls.push(String(url));
      const u = String(url);
      const body = u.includes("/api/settings")
        ? { settings: { questions_per_page: 10 } }
        : u.includes("/api/certifications")
          ? []
          : { items: [question()], total: 1, limit: 10, offset: 0 };
      return Promise.resolve(
        new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } }),
      );
    });
    render(<BankPane />);

    await waitFor(() => expect(calls.some((c) => c.includes("limit=10"))).toBe(true));
  });

  // `sort` was missing from what reloads the list, so on the first page
  // switching Course order / Recently updated changed nothing on screen.
  it("reloads when the sort order changes on the first page", async () => {
    const calls = mockApi([question()]);
    render(<BankPane />);
    await screen.findByText("Which step reads a file?");

    await userEvent.selectOptions(screen.getByDisplayValue("Course order"), "updated");

    await waitFor(() => expect(calls.some((c) => c.includes("sort=updated"))).toBe(true));
  });
});

describe("export", () => {
  // Settings saved a default export format and nothing read it; the Bank only
  // ever exported CSV.
  it("starts on the default format from Settings, and exports in any other", async () => {
    vi.stubGlobal("fetch", (url: string) => {
      const u = String(url);
      const body = u.includes("/api/settings")
        ? { settings: { questions_per_page: 25, default_export_format: "docx" },
            choices: { exportFormats: [{ format: "csv", label: "CSV" },
                                       { format: "docx", label: "Word (.docx)" }] } }
        : u.includes("/api/certifications") ? [] : { items: [question()], total: 1, limit: 25, offset: 0 };
      return Promise.resolve(
        new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } }),
      );
    });
    render(<BankPane />);
    const href = () => (screen.getByRole("button", { name: "Export" }).closest("a") as HTMLAnchorElement)
      .getAttribute("href") ?? "";

    await waitFor(() => expect(href()).toContain("/api/export/docx"));
    await userEvent.selectOptions(screen.getByLabelText("Export format"), "csv");
    expect(href()).toContain("/api/export/csv");
  });
});
