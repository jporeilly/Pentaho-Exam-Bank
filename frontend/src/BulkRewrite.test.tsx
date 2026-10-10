import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BulkRewrite } from "./BulkRewrite";
import type { Question, RewriteEntry } from "./api";

function question(id: string, over: Partial<Question> = {}): Question {
  return {
    id, scenario: "", stem: `Question ${id}?`, question_type: "single", key: "Right",
    keys: [], key_source_text: "", distractors: ["Wrong one", "Wrong two"], option_order: [],
    explanation: "Right - Correct. Wrong one - Incorrect.", topic: "Basics", tags: [],
    difficulty: "Medium", bloom_level: "Apply", certification_id: "c1", pool_order: 0,
    status: "approved", assigned_sme: "", review_history: [], version_history: [],
    updated_at: "2026-10-10T09:00:00", ...over,
  };
}

function entry(id: string, over: Partial<RewriteEntry> = {}): RewriteEntry {
  return {
    id, original: question(id),
    proposed: question(id, { explanation: `**Right** is right for ${id}.\n\nA second paragraph.` }),
    problems: [], notes: [], unchanged: false, error: "", accepted: false, ...over,
  };
}

/** A server whose job reports `entries`, finishing on the poll after `runningPolls`. */
function fakeServer(entries: RewriteEntry[], runningPolls = 1) {
  const accepted = new Set<string>();
  const calls: Array<{ path: string; body: unknown }> = [];
  let polls = 0;
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const path = String(url);
    const body = init?.body ? JSON.parse(String(init.body)) : null;
    calls.push({ path, body });
    const json = (b: unknown, status = 200) =>
      Promise.resolve(new Response(JSON.stringify(b), {
        status, headers: { "Content-Type": "application/json" },
      }));
    if (path.endsWith("/api/questions/ai/rewrite-all")) {
      return json({ jobId: "j1", total: entries.length, status: "running" }, 202);
    }
    if (path.includes("/accept")) {
      const ids = (body as { question_ids: string[] }).question_ids;
      ids.forEach((id) => accepted.add(id));
      return json({ saved: ids, skipped: [] });
    }
    if (path.endsWith("/api/jobs/j1")) {
      polls += 1;
      const running = polls <= runningPolls;
      const shown = running ? entries.slice(0, 1) : entries;
      return json({
        id: "j1", kind: "rewrite", status: running ? "running" : "done",
        progress: { current: shown.length, total: entries.length, message: "" },
        count: shown.length, requested: entries.length, error: "",
        result: shown.map((e) => ({ ...e, accepted: accepted.has(e.id) })),
      });
    }
    if (path.includes("/cancel")) return json({ ok: true, id: "j1" });
    return json({}, 404);
  });
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

function mount(total: number, onSaved = vi.fn()) {
  render(
    <BulkRewrite
      scope={{ certification_id: "c1" }} total={total} onClose={vi.fn()} onSaved={onSaved} pollMs={5}
    />,
  );
  return onSaved;
}

describe("the bulk AI rewrite", () => {
  it("asks first, and says nothing is saved until accepted", async () => {
    const calls = fakeServer([entry("q1")]);
    mount(1);

    expect(screen.getByText(/Nothing is saved until you accept/)).toBeInTheDocument();
    // Only the house style is read before the author says yes.
    const started = () => calls.filter((c) => c.path.includes("/rewrite-all"));
    expect(started()).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Rewrite 1 question" }));

    await screen.findByText("q1");
    expect(started()[0]).toEqual({
      path: expect.stringContaining("/api/questions/ai/rewrite-all"),
      body: { certification_id: "c1" },
    });
  });

  it("grows the review list as the job runs, each with its explanation in paragraphs", async () => {
    fakeServer([entry("q1"), entry("q2")]);
    mount(2);
    await userEvent.click(screen.getByRole("button", { name: "Rewrite 2 questions" }));

    await screen.findByText("q2");
    await screen.findByText(/Rewrote 2 of 2/);
    const row = screen.getByText("q1").closest("li")!;
    const card = row.querySelector(".explanation-card")!;
    expect(card.querySelectorAll(".fmt-p")).toHaveLength(2);
    expect(card.querySelector("strong")).toHaveTextContent("Right");
  });

  it("accepts one, then all the clean ones - never one with notes", async () => {
    const calls = fakeServer([
      entry("q1"),
      entry("q2"),
      entry("q3", { notes: [{ field: "explanation", message: "It still labels options Correct/Incorrect." }] }),
      entry("q4", { unchanged: true }),
      entry("q5", { proposed: null, error: "The model did not return a usable question." }),
    ], 0);
    const onSaved = mount(5);
    await userEvent.click(screen.getByRole("button", { name: "Rewrite 5 questions" }));
    await screen.findByText("q5");

    const q1 = screen.getByText("q1").closest("li")!;
    await userEvent.click(within(q1).getByRole("button", { name: "Accept" }));
    await waitFor(() => expect(within(q1).getByText("Accepted")).toBeInTheDocument());
    expect(onSaved).toHaveBeenCalledTimes(1);

    // q2 is the only clean one left: q3 has notes, q4 changed nothing, q5 failed.
    const all = screen.getByRole("button", { name: "Accept all ready (1)" });
    await userEvent.click(all);
    const accepts = calls.filter((c) => c.path.includes("/accept")).map((c) => c.body);
    expect(accepts).toEqual([{ question_ids: ["q1"] }, { question_ids: ["q2"] }]);
    expect(screen.getByText(/1 with notes is left for you to look at/)).toBeInTheDocument();
    expect(within(screen.getByText("q4").closest("li")!).getByText("Unchanged")).toBeInTheDocument();
    expect(within(screen.getByText("q5").closest("li")!).getByText("Failed")).toBeInTheDocument();
  });

  it("shows the original beside the proposal on request", async () => {
    fakeServer([entry("q1")], 0);
    mount(1);
    await userEvent.click(screen.getByRole("button", { name: "Rewrite 1 question" }));
    const row = (await screen.findByText("q1")).closest("li")!;

    await userEvent.click(within(row).getByRole("button", { name: "Show original" }));

    expect(within(row).getByText("Original")).toBeInTheDocument();
    expect(within(row).getByText("Right - Correct. Wrong one - Incorrect.")).toBeInTheDocument();
  });
});

describe("the writing standard's notes", () => {
  it("names the answers and draws the advice's code as code", async () => {
    fakeServer([entry("q1", {
      notes: [{ field: "options", message: "Single quotes around 'sales'. Use `code` for a name." }],
    })], 0);
    mount(1);
    await userEvent.click(screen.getByRole("button", { name: "Rewrite 1 question" }));
    const row = (await screen.findByText("q1")).closest("li")!;

    const note = row.querySelector(".advice")!;
    expect(note).toHaveTextContent(/^Answers: Single quotes around 'sales'/);
    expect(note.querySelector("code")).toHaveTextContent("code");
  });
});

describe("what a rewrite changed", () => {
  it("names the parts, so a changed question stands out from a polished explanation", async () => {
    const { changedParts } = await import("./BulkRewrite");
    expect(changedParts(entry("q1"))).toEqual(["Explanation"]);
    const reworded = entry("q2", {
      proposed: question("q2", { stem: "A different question?", distractors: ["Wrong one", "Wrong 2"] }),
    });
    // Same explanation as the original: only the question and an answer moved.
    expect(changedParts(reworded)).toEqual(["Question", "Answers"]);
  });
});
