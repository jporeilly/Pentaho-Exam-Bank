import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ResultsDbAdmin } from "./ResultsDbAdmin";

const STATUS = {
  path: "C:/data/exam_results.db", defaultPath: "C:/data/exam_results.db", exists: true,
  attempts: 6, answers: 12, sizeKb: 40, backups: [{ name: "exam_results_1", sizeKb: 40, created: "2026-10-22 10:00" }],
};
const OPTIONS = {
  courses: [{ id: "c1", name: "DI Practitioner" }], candidates: ["cand_1"], maxAttemptNo: 1,
  firstDay: "2026-10-01", lastDay: "2026-10-20",
};

function server(status = STATUS, refuse = false) {
  const calls: { path: string; method: string; body: Record<string, unknown> | null }[] = [];
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const path = String(url);
    calls.push({ path, method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : null });
    const json = (body: unknown, code = 200) =>
      Promise.resolve(new Response(JSON.stringify(body), { status: code, headers: { "Content-Type": "application/json" } }));
    if (path.includes("/api/results/attempts")) return json({ attempts: [], summary: {}, options: OPTIONS });
    if (path.includes("/results-db/append"))
      return json({ addedAttempts: 2, addedAnswers: 4, skippedAttempts: 1, totalAttempts: 8, totalAnswers: 16 });
    if (path.includes("/delete/preview"))
      return json({ attempts: 2, answers: 4, sample: [{ attemptId: "a1", candidateId: "cand_1", day: "2026-10-01", courseId: "c1" }] });
    if (path.includes("/results-db/delete"))
      return refuse ? json({ detail: "now match 3" }, 409) : json({ removedAttempts: 2, removedAnswers: 4, safetyBackup: "b_before_delete.db" });
    if (path.includes("/results-db/truncate"))
      return json({ removedAttempts: 6, removedAnswers: 12, safetyBackup: "b_before_truncate.db" });
    return json(status);
  });
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

describe("ResultsDbAdmin", () => {
  it("shows what the file holds and appends under the filters", async () => {
    const calls = server();
    render(<ResultsDbAdmin />);
    expect(await screen.findByText(/6 attempts, 12 answers/)).toBeInTheDocument();
    await userEvent.selectOptions(await screen.findByLabelText("Result"), "pass");
    await userEvent.click(screen.getByRole("button", { name: "Append matching records" }));
    expect(await screen.findByText(/Added 2 attempts and 4 answers \(1 already there\)/)).toBeInTheDocument();
    const post = calls.find((c) => c.path.includes("/results-db/append"))!;
    expect(post.body).toMatchObject({ passed: "pass" });
  });

  it("truncate needs the tick, and sends the count it was shown", async () => {
    const calls = server();
    render(<ResultsDbAdmin />);
    const button = await screen.findByRole("button", { name: "Truncate results database" });
    expect(button).toBeDisabled();
    await userEvent.click(screen.getByLabelText(/remove all 6 attempts/));
    expect(button).toBeEnabled();
    await userEvent.click(button);
    expect(await screen.findByText(/Removed 6 attempts and 12 answers. Safety backup: b_before_truncate.db/)).toBeInTheDocument();
    expect(calls.find((c) => c.path.includes("/truncate"))!.body).toMatchObject({ expect_count: 6 });
  });

  it("delete is count-first, needs the tick, and shows a refusal", async () => {
    const calls = server(STATUS, true);
    render(<ResultsDbAdmin />);
    const count = await screen.findByRole("button", { name: "Count matching records" });
    expect(count).toBeDisabled();                    // no filter: use Truncate
    await userEvent.selectOptions(await screen.findByLabelText("Course"), "c1");
    await userEvent.click(count);
    const del = await screen.findByRole("button", { name: "Delete 2" });
    expect(del).toBeDisabled();
    await userEvent.click(screen.getByLabelText(/delete these 2/));
    await userEvent.click(del);
    expect(await screen.findByText("now match 3")).toBeInTheDocument();
    expect(calls.find((c) => c.path.endsWith("/results-db/delete"))!.body).toMatchObject({ expect_count: 2, course: "c1" });
  });

  it("a changed filter drops a stale count", async () => {
    server();
    render(<ResultsDbAdmin />);
    await userEvent.selectOptions(await screen.findByLabelText("Course"), "c1");
    await userEvent.click(await screen.findByRole("button", { name: "Count matching records" }));
    expect(await screen.findByRole("button", { name: "Delete 2" })).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Result"), "fail");
    expect(screen.queryByRole("button", { name: "Delete 2" })).toBeNull();
  });
});
