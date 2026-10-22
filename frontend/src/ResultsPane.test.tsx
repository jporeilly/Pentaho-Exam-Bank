import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ResultsPane } from "./ResultsPane";
import type { ResultsAnalysis, ResultsAttempts, TopicAdvice, TopicReport } from "./api";

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

const ATTEMPTS: ResultsAttempts = {
  attempts: [
    { attemptId: "a2", candidateId: "cand_a", courseId: "developer-di-practitioner", course: "DI Practitioner",
      role: "developer", company: "", submittedAt: "2026-10-16T16:34:37", day: "2026-10-16", attemptNo: 2,
      ofAttempts: 2, score: 20, total: 40, percentage: 0.5, passed: false },
    { attemptId: "a1", candidateId: "cand_a", courseId: "developer-di-practitioner", course: "DI Practitioner",
      role: "developer", company: "", submittedAt: "2026-10-13T20:03:56", day: "2026-10-13", attemptNo: 1,
      ofAttempts: 2, score: 33, total: 40, percentage: 0.83, passed: true },
  ],
  summary: { attempts: 2, candidates: 1, passed: 1, failed: 1, meanPercentage: 0.665 },
  options: {
    courses: [{ id: "developer-di-practitioner", name: "DI Practitioner" }],
    candidates: ["cand_a"], maxAttemptNo: 2, firstDay: "2026-10-13", lastDay: "2026-10-16",
  },
};

const row = (label: string, wrong: number, answers: number, thin = false) => ({
  label, courseId: "developer-di-practitioner", course: "DI Practitioner", questions: 2, answers, wrong,
  wrongRate: wrong / answers, shareOfWrong: wrong / 30, thin,
  worstQuestions: [{ id: "di-m1-q2", answers: 40, wrong: 20, wrongRate: 0.5, stem: "Which step writes rows?" }],
});

const TOPICS: TopicReport = {
  minAnswers: 20, answers: 80, wrong: 30,
  courses: [{
    courseId: "developer-di-practitioner", name: "DI Practitioner", attempts: 40, answers: 80, wrong: 30,
    wrongRate: 0.375,
    topics: [row("Getting Started", 20, 40), row("Jobs", 10, 12, true)],
    modules: [row("Module 1", 20, 40)],
  }],
};

const ADVICE: TopicAdvice = {
  summary: "Getting Started is missed most.", dropped: 1, model: "m1", provider: "ollama",
  suggestions: [{ course: "DI Practitioner", topic: "Getting Started", questionIds: ["di-m1-q2"],
                  priority: "high", advice: "Check the key on di-m1-q2." }],
};

const EMPTY_ATTEMPTS: ResultsAttempts = {
  attempts: [], summary: { attempts: 0, candidates: 0, passed: 0, failed: 0, meanPercentage: null },
  options: { courses: [], candidates: [], maxAttemptNo: 0, firstDay: "", lastDay: "" },
};

/** Answers the pane's calls; `urls` records every URL fetched, the array each import body. */
function fakeServer(analysis: ResultsAnalysis, importReply: unknown = null, status = 200,
                    attempts: ResultsAttempts = EMPTY_ATTEMPTS) {
  const posted: string[] = [];
  const urls: string[] = [];
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const u = String(url);
    urls.push(u);
    let body: unknown = analysis;
    let code = 200;
    if (u.includes("/api/results/import-xlsx")) {
      posted.push(JSON.parse(String(init?.body)).xlsx);
      body = importReply;
      code = status;
    } else if (u.includes("/api/results/import")) {
      posted.push(JSON.parse(String(init?.body)).csv);
      body = importReply;
      code = status;
    } else if (u.includes("/api/results/attempts")) {
      body = attempts;
    } else if (u.includes("/api/results/topics/advice")) {
      body = ADVICE;
    } else if (u.includes("/api/results/topics")) {
      body = TOPICS;
    } else if (u.includes("/api/results/service")) {
      body = { configured: false, env: "X" };
    }
    return Promise.resolve(new Response(JSON.stringify(body), {
      status: code, headers: { "Content-Type": "application/json" },
    }));
  });
  return Object.assign(posted, { urls });
}

afterEach(() => vi.unstubAllGlobals());

describe("ResultsPane", () => {
  it("ranks topics by wrong answers, switches to modules, and dims thin rows", async () => {
    fakeServer(ANALYSIS);
    render(<ResultsPane />);
    const head = await screen.findByText("Where candidates go wrong");
    const table = head.closest("section")!.querySelector("table")!;
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("Getting Started");
    expect(rows[1]).toHaveClass("results-thin");
    expect(within(table).getByLabelText(/20 wrong, 67%/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "By module" }));
    expect(within(head.closest("section")!).getByText("Module 1")).toBeInTheDocument();
  });

  it("Analyse with AI shows the reading, and drops it when the filters change", async () => {
    const calls = fakeServer(ANALYSIS, null, 200, ATTEMPTS);
    render(<ResultsPane />);
    await userEvent.click(await screen.findByRole("button", { name: "Analyse with AI" }));
    const region = await screen.findByRole("region", { name: "AI reading" });
    expect(region).toHaveTextContent("Getting Started is missed most.");
    expect(region).toHaveTextContent("Check the key on di-m1-q2.");
    expect(region).toHaveTextContent("1 suggestion named something not in the report");
    expect(calls.urls.some((u) => u.includes("/api/results/topics/advice"))).toBe(true);
    await userEvent.selectOptions(screen.getByLabelText("Result"), "pass");
    await waitFor(() => expect(screen.queryByRole("region", { name: "AI reading" })).toBeNull());
  });

  it("shows each question's numbers, its options and its flags", async () => {
    fakeServer(ANALYSIS);
    render(<ResultsPane />);
    expect(await screen.findByRole("heading", { name: "DI Practitioner" })).toBeInTheDocument();
    expect(screen.getByText(/40 attempts · mean score 62%/)).toBeInTheDocument();
    expect(screen.getByText("reads").tagName).toBe("STRONG");
    expect(screen.getByText("0.71")).toBeInTheDocument();
    expect(screen.getByText(/Check the key and the wording/)).toBeInTheDocument();
    expect(screen.getByText("CSV input").closest("li")).toHaveClass("correct");
  });

  it("Only flagged questions hides the ones with nothing to say", async () => {
    fakeServer(ANALYSIS);
    render(<ResultsPane />);
    await screen.findByRole("heading", { name: "DI Practitioner" });
    await userEvent.click(screen.getByLabelText("Only flagged questions"));
    expect(screen.queryByText("di-m1-q1")).not.toBeInTheDocument();
    expect(screen.getAllByText("di-m1-q2").length).toBeGreaterThan(0);
  });

  it("imports a CSV the author picks, and says what came in", async () => {
    const posted = fakeServer({ ...ANALYSIS, exams: [] },
      { rows: 80, added: 80, attempts: 40, courses: ["developer-di-practitioner"], totalResponses: 80 });
    render(<ResultsPane />);
    await screen.findByText("No results imported yet.");
    const file = new File(["Attempt ID,Course ID\n"], "detail.csv", { type: "text/csv" });
    await userEvent.upload(screen.getByLabelText("Results file"), file);
    await screen.findByText(/Imported 80 answers from 40 attempts \(80 new\)/);
    expect([...posted]).toEqual(["Attempt ID,Course ID\n"]);
  });

  it("says why a file was refused", async () => {
    fakeServer({ ...ANALYSIS, exams: [] }, { detail: 'This is not the results Sheet\'s Detail tab: it has no "Question Id" column.' }, 422);
    render(<ResultsPane />);
    await screen.findByText("No results imported yet.");
    await userEvent.upload(screen.getByLabelText("Results file"), new File(["x"], "x.csv"));
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
          : u.includes("/api/results/attempts")
            ? EMPTY_ATTEMPTS
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

describe("the workbook, attempts and filters", () => {
  it("imports the workbook (.xlsx) as base64 and says what each tab gave", async () => {
    const posted = fakeServer({ ...ANALYSIS, exams: [] },
      { rows: 80, added: 80, attempts: 2, addedAttempts: 2, totalAttempts: 2, answers: 80, totalResponses: 80,
        courses: ["developer-di-practitioner"],
        sheets: [{ name: "All results", kind: "attempts", rows: 2 }, { name: "Detail", kind: "answers", rows: 80 },
                 { name: "Other", kind: "ignored", rows: 0 }] });
    render(<ResultsPane />);
    await screen.findByText("No results imported yet.");
    const file = new File([new Uint8Array([80, 75, 3, 4])], "Pentaho Exam Results.xlsx");
    await userEvent.upload(screen.getByLabelText("Results file"), file);
    await screen.findByText(/Read 2 tabs: 2 attempts \(2 new\) and 80 answers \(80 new\)/);
    expect([...posted]).toEqual([btoa("PK\u0003\u0004")]);
  });

  it("lists each attempt separately, a retake marked as 2 of 2", async () => {
    fakeServer(ANALYSIS, null, 200, ATTEMPTS);
    render(<ResultsPane />);
    await screen.findByRole("heading", { name: "Attempts" });
    expect(screen.getByText(/2 attempts · 1 candidate · 1 passed · 1 failed · mean 67%/)).toBeInTheDocument();
    const rows = screen.getAllByRole("row").filter((r) => within(r).queryByText("cand_a"));
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("Failed")).toBeInTheDocument();
    expect(rows[0]).toHaveTextContent("2 of 2");
    expect(rows[1]).toHaveTextContent("1 of 2");
  });

  it("sends the date range and the other filters to the server, and clears them", async () => {
    const sent = fakeServer(ANALYSIS, null, 200, ATTEMPTS);
    render(<ResultsPane />);
    await screen.findByRole("heading", { name: "Attempts" });
    fireEvent.change(screen.getByLabelText("From date"), { target: { value: "2026-10-14" } });
    fireEvent.change(screen.getByLabelText("To date"), { target: { value: "2026-10-16" } });
    await userEvent.selectOptions(screen.getByLabelText("Result"), "fail");
    await userEvent.selectOptions(screen.getByLabelText("Attempt number"), "2");
    await userEvent.selectOptions(screen.getByLabelText("Course"), "developer-di-practitioner");
    await waitFor(() => {
      const last = sent.urls.filter((u) => u.includes("/api/results/attempts")).pop()!;
      expect(last).toContain("date_from=2026-10-14");
      expect(last).toContain("date_to=2026-10-16");
      expect(last).toContain("passed=fail");
      expect(last).toContain("attempt_no=2");
      expect(last).toContain("course=developer-di-practitioner");
      const analysis = sent.urls.filter((u) => u.includes("/api/results/analysis")).pop()!;
      expect(analysis).toContain("date_from=2026-10-14");
    });
    await userEvent.click(screen.getByText("Clear filters"));
    await waitFor(() => {
      const last = sent.urls.filter((u) => u.includes("/api/results/attempts")).pop()!;
      expect(last).not.toContain("date_from");
      expect(last).not.toContain("passed");
    });
  });

  it("a preset fills both dates with a seven-day span", async () => {
    const sent = fakeServer(ANALYSIS, null, 200, ATTEMPTS);
    render(<ResultsPane />);
    await screen.findByRole("heading", { name: "Attempts" });
    await userEvent.click(screen.getByText("Last 7 days"));
    const fromBox = screen.getByLabelText("From date") as HTMLInputElement;
    const toBox = screen.getByLabelText("To date") as HTMLInputElement;
    await waitFor(() => expect(fromBox.value).toMatch(/^\d{4}-\d{2}-\d{2}$/));
    const days = (new Date(toBox.value).getTime() - new Date(fromBox.value).getTime()) / 86400000;
    expect(days).toBe(6);
    expect(sent.urls.some((u) => u.includes("date_from="))).toBe(true);
  });
});
