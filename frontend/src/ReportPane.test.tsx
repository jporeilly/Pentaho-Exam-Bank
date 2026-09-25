import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReportPane } from "./ReportPane";
import type { Report, ReportExam, ReportItem, ReportSummary } from "./api";

const LEVELS = ["Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create"];
const STATUSES = [
  { id: "draft", label: "Draft" }, { id: "sme_review", label: "SME Review" },
  { id: "revised", label: "Revised" }, { id: "approved", label: "Approved" },
  { id: "rejected", label: "Rejected" }, { id: "retired", label: "Retired" },
];

function summary(bloom: number[], over: Partial<ReportSummary> = {}): ReportSummary {
  const byBloom = Object.fromEntries(LEVELS.map((l, i) => [l, bloom[i] ?? 0]));
  const n = bloom.reduce((a, b) => a + b, 0);
  return {
    questions: n, byBloom, unknownBloom: 0,
    applyPlus: bloom.slice(2).reduce((a, b) => a + b, 0),
    analyzePlus: bloom.slice(3).reduce((a, b) => a + b, 0),
    recall: bloom[0] ?? 0, evaluate: bloom[4] ?? 0,
    scenarioLed: 0, multi: 0, thin: 0,
    byStatus: { draft: n, sme_review: 0, revised: 0, approved: 0, rejected: 0, retired: 0 },
    ...over,
  };
}

const LAB: ReportExam = {
  certificationId: "c-lab", name: "PDI in 2 Hours", sourceRef: "pdi-2hr-lab",
  level: null, exam: { pool: 30, draw: 20, passMark: 80 },
  ...summary([2, 8, 8, 12, 0], { scenarioLed: 14 }),
  bar: null,
  findings: [{ severity: "note", title: "Not scored against a certification bar",
               detail: "The course states no level.", action: "Nothing to do." }],
  topics: [
    { topic: "See It Work", ...summary([0, 4, 2, 2, 0]) },
    { topic: "Make It Yours", ...summary([1, 1, 1, 9, 0]) },
  ],
};

const DI: ReportExam = {
  certificationId: "c-di", name: "DI Practitioner", sourceRef: "developer-di-practitioner",
  level: { number: 1, name: "Practitioner" }, exam: { pool: 48, draw: 40, passMark: 80 },
  ...summary([11, 13, 15, 8, 1]),
  bar: {
    level: 1, name: "Practitioner", clears: false,
    criteria: [
      { criterion: "Apply+", kind: "floor", got: 24, percent: 50, bar: 50, ok: true, gap: 0 },
      { criterion: "Analyze+", kind: "floor", got: 5, percent: 10, bar: 15, ok: false, gap: 3 },
      { criterion: "Evaluate", kind: "floor", got: 1, percent: 2, bar: 1, ok: true, gap: 0 },
      { criterion: "Recall", kind: "ceiling", got: 11, percent: 23, bar: 30, ok: true, gap: 0 },
    ],
  },
  findings: [{ severity: "review", title: "Misses the Level 1 Practitioner bar on 1 of 4",
               detail: "Analyze+ 10% against 15%.", action: "Close the largest gap first." }],
  topics: [{ topic: "Getting Started", ...summary([11, 13, 15, 8, 1]) }],
};

function item(id: string, cert: string, bloom: string, over: Partial<ReportItem> = {}): ReportItem {
  return { id, certificationId: cert, topic: "See It Work", bloom, status: "draft",
           scenario: false, multi: false, stem: `Stem of ${id}`, poolOrder: 0, ...over };
}

function report(over: Partial<Report> = {}): Report {
  return {
    levels: LEVELS, statuses: STATUSES, coursesConfigured: true,
    ...summary([13, 21, 23, 20, 1]),
    exams: [LAB, DI], emptyCourses: 9,
    items: [
      item("q-analyze", "c-lab", "Analyze", { poolOrder: 0, scenario: true }),
      item("q-understand", "c-lab", "Understand", { poolOrder: 1 }),
      item("q-apply", "c-lab", "Apply", { poolOrder: 2, multi: true }),
      item("m1-q1", "c-di", "Remember", { poolOrder: 0, topic: "Getting Started" }),
    ],
    ...over,
  };
}

function serve(body: unknown, status = 200) {
  const calls: string[] = [];
  vi.stubGlobal("fetch", (url: string) => {
    calls.push(String(url));
    const payload = status === 200 ? body : { detail: body };
    return Promise.resolve(new Response(JSON.stringify(payload), {
      status, headers: { "Content-Type": "application/json" },
    }));
  });
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

const examButton = (name: RegExp) => screen.getByRole("button", { name });
const stems = () => Array.from(document.querySelectorAll(".stem"));

describe("choosing an exam", () => {
  it("opens on the first exam and lists every exam that holds questions", async () => {
    serve(report());
    render(<ReportPane />);
    expect(await screen.findByRole("heading", { name: "PDI in 2 Hours" })).toBeInTheDocument();
    expect(examButton(/PDI in 2 Hours/)).toHaveAttribute("aria-pressed", "true");
    expect(examButton(/DI Practitioner/)).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText(/9 more courses in the bank hold no questions/)).toBeInTheDocument();
  });

  it("opens on the course the app was launched for", async () => {
    serve(report());
    render(<ReportPane openCourse="developer-di-practitioner" />);
    expect(await screen.findByRole("heading", { name: "DI Practitioner" })).toBeInTheDocument();
  });

  it("switches exam when another is chosen", async () => {
    serve(report());
    render(<ReportPane />);
    await userEvent.click(await screen.findByRole("button", { name: /DI Practitioner/ }));
    expect(screen.getByRole("heading", { name: "DI Practitioner" })).toBeInTheDocument();
    expect(screen.getByText("Level 1 · Practitioner")).toBeInTheDocument();
  });
});

describe("the breakdown", () => {
  it("shows the headline figures for the exam", async () => {
    serve(report());
    render(<ReportPane />);
    await screen.findByRole("heading", { name: "PDI in 2 Hours" });
    // 20 of 30 at Apply or above, 14 of 30 with a scenario, 20 drawn from 30
    const applyTile = screen.getByText("Apply or above").closest(".report-tile") as HTMLElement;
    expect(within(applyTile).getByText("67%")).toBeInTheDocument();
    expect(within(applyTile).getByText("20 of 30")).toBeInTheDocument();
    expect(screen.getByText("14 set a situation")).toBeInTheDocument();
    expect(screen.getByText("20 drawn from 30")).toBeInTheDocument();
  });

  it("describes the Bloom bar to a screen reader with every level's count", async () => {
    serve(report());
    render(<ReportPane />);
    await screen.findByRole("heading", { name: "PDI in 2 Hours" });
    expect(screen.getAllByRole("img")[0]).toHaveAccessibleName(
      "Remember 2, Understand 8, Apply 8, Analyze 12, Evaluate 0, Create 0",
    );
  });

  it("lists the workshops in the order the server gives them", async () => {
    serve(report());
    render(<ReportPane />);
    await screen.findByRole("heading", { name: "PDI in 2 Hours" });
    const names = screen.getAllByText(/^(See It Work|Make It Yours)$/, { selector: ".report-topic .name" })
      .map((el) => el.textContent);
    expect(names).toEqual(["See It Work", "Make It Yours"]);
  });

  it("says an exam with no level is not scored, rather than showing an empty bar", async () => {
    serve(report());
    render(<ReportPane />);
    expect(await screen.findByText(/states no level, so it is not scored/)).toBeInTheDocument();
  });

  it("shows each bar criterion with its gap in questions", async () => {
    serve(report());
    render(<ReportPane openCourse="developer-di-practitioner" />);
    await screen.findByRole("heading", { name: "DI Practitioner" });
    expect(screen.getByText("Misses its bar")).toBeInTheDocument();
    expect(screen.getByText("3 questions short")).toBeInTheDocument();
    // 24 of 48 is exactly 50%: a pass, and worth saying it is on the line.
    expect(screen.getByText("exactly on the line")).toBeInTheDocument();
  });

  it("draws the findings the server sent, word for word", async () => {
    serve(report());
    render(<ReportPane openCourse="developer-di-practitioner" />);
    expect(await screen.findByText("Misses the Level 1 Practitioner bar on 1 of 4")).toBeInTheDocument();
    expect(screen.getByText("Close the largest gap first.")).toBeInTheDocument();
  });
});

describe("the question list", () => {
  it("shows only the chosen exam's questions, in course order", async () => {
    serve(report());
    render(<ReportPane />);
    await screen.findByRole("heading", { name: "PDI in 2 Hours" });
    expect(stems().map((el) => el.textContent)).toEqual([
      "Stem of q-analyze", "Stem of q-understand", "Stem of q-apply",
    ]);
    expect(screen.queryByText("Stem of m1-q1")).not.toBeInTheDocument();
    expect(screen.getByText("Showing all 3 questions")).toBeInTheDocument();
  });

  it("narrows to one Bloom level and back", async () => {
    serve(report());
    render(<ReportPane />);
    await screen.findByRole("heading", { name: "PDI in 2 Hours" });
    const filters = screen.getByRole("group", { name: "Filter by Bloom level" });
    await userEvent.click(within(filters).getByRole("button", { name: /Analyze 1/ }));
    expect(stems().map((el) => el.textContent)).toEqual(["Stem of q-analyze"]);
    expect(screen.getByText("Showing 1 of 3, Analyze only")).toBeInTheDocument();
    await userEvent.click(within(filters).getByRole("button", { name: /All 3/ }));
    expect(stems()).toHaveLength(3);
  });

  it("offers a filter only for levels the exam actually has", async () => {
    serve(report());
    render(<ReportPane />);
    await screen.findByRole("heading", { name: "PDI in 2 Hours" });
    const filters = screen.getByRole("group", { name: "Filter by Bloom level" });
    expect(within(filters).queryByRole("button", { name: /Remember/ })).not.toBeInTheDocument();
    expect(within(filters).queryByRole("button", { name: /Evaluate/ })).not.toBeInTheDocument();
  });

  it("clears the level filter when switching exam", async () => {
    serve(report());
    render(<ReportPane />);
    await screen.findByRole("heading", { name: "PDI in 2 Hours" });
    const filters = screen.getByRole("group", { name: "Filter by Bloom level" });
    await userEvent.click(within(filters).getByRole("button", { name: /Analyze 1/ }));
    await userEvent.click(screen.getByRole("button", { name: /DI Practitioner/ }));
    expect(screen.getByText("Showing all 1 questions")).toBeInTheDocument();
  });
});

describe("when there is nothing, or something is wrong", () => {
  it("says the bank is empty instead of drawing zeros", async () => {
    serve(report({ exams: [], items: [], ...summary([]) }));
    render(<ReportPane />);
    expect(await screen.findByText(/The bank holds no questions yet/)).toBeInTheDocument();
  });

  it("says why the level bar is missing when no courses directory is configured", async () => {
    serve(report({ coursesConfigured: false }));
    render(<ReportPane />);
    expect(await screen.findByText(/No Content Manager courses directory is configured/)).toBeInTheDocument();
  });

  it("shows the server's error and can retry", async () => {
    const calls = serve("database is locked", 500);
    render(<ReportPane />);
    expect(await screen.findByText(/database is locked/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(calls.filter((c) => c.includes("/api/report"))).toHaveLength(2);
  });
});
