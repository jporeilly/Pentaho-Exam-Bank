import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ResultsPane } from "./ResultsPane";
import type { ResultsAnalysis } from "./api";

const ANALYSIS: ResultsAnalysis = {
  minAttempts: 20,
  totalResponses: 80,
  exams: [{
    courseId: "developer-di-practitioner",
    certificationId: "c1",
    name: "DI Practitioner",
    attempts: 40,
    meanScore: 0.62,
    firstAttempt: "2026-10-01T09:00:00Z",
    lastAttempt: "2026-10-08T09:00:00Z",
    judged: 2,
    flagged: 1,
    items: [
      {
        id: "di-m1-q1", stem: "Which step **reads** a file?", topic: "Getting Started", difficulty: "Medium",
        attempts: 40, correct: 20, p: 0.5, discrimination: 0.71, upperP: 1, lowerP: 0,
        suggestedDifficulty: "Medium", blank: 0, flags: [],
        options: [
          { text: "CSV input", correct: true, chosen: 20, share: 0.5, upperChosen: 10 },
          { text: "Sort rows", correct: false, chosen: 20, share: 0.5, upperChosen: 0 },
        ],
      },
      {
        id: "di-m1-q2", stem: "Which step writes rows?", topic: "Getting Started", difficulty: "Medium",
        attempts: 40, correct: 20, p: 0.5, discrimination: -0.6, upperP: 0, lowerP: 1,
        suggestedDifficulty: "Medium", blank: 0,
        flags: [{ level: "bad", text: "Stronger candidates get it wrong more often than weaker ones. Check the key and the wording." }],
        options: [
          { text: "Table output", correct: true, chosen: 20, share: 0.5, upperChosen: 0 },
          { text: "Trap", correct: false, chosen: 20, share: 0.5, upperChosen: 10 },
        ],
      },
    ],
  }],
};

function fakeServer(analysis: ResultsAnalysis, importReply: unknown = null, status = 200) {
  const posted: string[] = [];
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const body = String(url).includes("/api/results/import")
      ? (posted.push(JSON.parse(String(init?.body)).csv), importReply)
      : analysis;
    return Promise.resolve(new Response(JSON.stringify(body), {
      status: String(url).includes("/import") ? status : 200,
      headers: { "Content-Type": "application/json" },
    }));
  });
  return posted;
}

afterEach(() => vi.unstubAllGlobals());

describe("ResultsPane", () => {
  it("shows each question's numbers, its options and its flags", async () => {
    fakeServer(ANALYSIS);
    render(<ResultsPane />);
    expect(await screen.findByText("DI Practitioner")).toBeInTheDocument();
    expect(screen.getByText(/40 attempts · mean score 62%/)).toBeInTheDocument();
    expect(screen.getByText("reads").tagName).toBe("STRONG");
    expect(screen.getByText("0.71")).toBeInTheDocument();
    expect(screen.getByText(/Check the key and the wording/)).toBeInTheDocument();
    expect(screen.getByText("CSV input").closest("li")).toHaveClass("correct");
  });

  it("Only flagged questions hides the ones with nothing to say", async () => {
    fakeServer(ANALYSIS);
    render(<ResultsPane />);
    await screen.findByText("DI Practitioner");
    await userEvent.click(screen.getByLabelText("Only flagged questions"));
    expect(screen.queryByText("di-m1-q1")).not.toBeInTheDocument();
    expect(screen.getByText("di-m1-q2")).toBeInTheDocument();
  });

  it("imports a CSV the author picks, and says what came in", async () => {
    const posted = fakeServer({ ...ANALYSIS, exams: [] },
      { rows: 80, added: 80, attempts: 40, courses: ["developer-di-practitioner"], totalResponses: 80 });
    render(<ResultsPane />);
    await screen.findByText("No results imported yet.");
    const file = new File(["Attempt ID,Course ID\n"], "detail.csv", { type: "text/csv" });
    await userEvent.upload(screen.getByLabelText("Results CSV file"), file);
    await screen.findByText(/Imported 80 answers from 40 attempts \(80 new\)/);
    expect(posted).toEqual(["Attempt ID,Course ID\n"]);
  });

  it("says why a file was refused", async () => {
    fakeServer({ ...ANALYSIS, exams: [] }, { detail: 'This is not the results Sheet\'s Detail tab: it has no "Question Id" column.' }, 422);
    render(<ResultsPane />);
    await screen.findByText("No results imported yet.");
    await userEvent.upload(screen.getByLabelText("Results CSV file"), new File(["x"], "x.csv"));
    await waitFor(() => expect(screen.getByText(/not the results Sheet's Detail tab/)).toBeInTheDocument());
  });
});

describe("pulling from the results service", () => {
  function service(configured: boolean) {
    const calls: string[] = [];
    vi.stubGlobal("fetch", (url: string) => {
      calls.push(String(url));
      const u = String(url);
      const body = u.includes("/api/results/service")
        ? { configured, env: "PEB_RESULTS_ADMIN_SECRET" }
        : u.includes("/api/results/pull")
          ? { rows: 12, added: 12, attempts: 2, courses: ["developer-di-practitioner"], totalResponses: 12, services: 1 }
          : { ...ANALYSIS, exams: [] };
      return Promise.resolve(new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } }));
    });
    return calls;
  }

  it("is unavailable without the admin secret", async () => {
    service(false);
    render(<ResultsPane />);
    await screen.findByText("No results imported yet.");
    expect(screen.getByRole("button", { name: "Pull from results service" })).toBeDisabled();
  });

  it("pulls and says what came in", async () => {
    const calls = service(true);
    render(<ResultsPane />);
    const pull = await screen.findByRole("button", { name: "Pull from results service" });
    await waitFor(() => expect(pull).toBeEnabled());
    await userEvent.click(pull);
    expect(await screen.findByText(/Pulled 12 answers from 2 attempts \(12 new\)/)).toBeInTheDocument();
    expect(calls.some((c) => c.includes("/api/results/pull"))).toBe(true);
  });
});
