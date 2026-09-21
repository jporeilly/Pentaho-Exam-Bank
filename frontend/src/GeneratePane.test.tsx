import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GeneratePane } from "./GeneratePane";
import type { Job, Question } from "./api";

function question(over: Partial<Question> = {}): Question {
  return {
    id: "gen-1", scenario: "A developer is building a transformation.",
    stem: "Which step reads a delimited file?", question_type: "single",
    key: "CSV file input", keys: [], key_source_text: "",
    distractors: ["Table output"], option_order: ["CSV file input", "Table output"],
    explanation: "CSV file input reads delimited text.", topic: "See It Work",
    tags: [], difficulty: "Medium", bloom_level: "Apply", certification_id: "",
    pool_order: -1, status: "draft", assigned_sme: "", review_history: [],
    version_history: [], updated_at: "", ...over,
  };
}

function job(over: Partial<Job> = {}): Job {
  return {
    id: "job-1", kind: "generate", status: "done",
    progress: { current: 2, total: 2, message: "Done" },
    count: 1, result: [question()], error: "", ...over,
  };
}

function ok(body: unknown) {
  return Promise.resolve(
    new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } }),
  );
}

/**
 * Route by path and method. `jobs` is a queue: each poll takes the next, and
 * the last one repeats — which is how a running job is made to finish.
 */
function mockApi(opts: {
  jobs?: Job[];
  generateError?: { status: number; detail: string };
  /** Jobs already running when the pane mounts. */
  existing?: Job[];
} = {}) {
  const calls: Array<{ url: string; method: string; body?: unknown }> = [];
  const queue = [...(opts.jobs ?? [job()])];

  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const path = String(url);
    const method = init?.method ?? "GET";
    calls.push({
      url: path,
      method,
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    });

    if (path.includes("/api/courses") && path.includes("/labs"))
      return ok([{ slug: "01-lab", title: "First Lab" }]);
    if (path.includes("/api/courses"))
      return ok([{ slug: "demo", title: "Demo Course", hasExam: true, questionCount: 3 }]);
    if (path.includes("/api/certifications"))
      return ok([{ id: "c1", name: "DI Practitioner", description: "",
                   sourceType: "pcm", sourceRef: "di", questionCount: 5 }]);
    if (path.includes("/api/generate")) {
      if (opts.generateError)
        return Promise.resolve(
          new Response(JSON.stringify({ detail: opts.generateError.detail }), {
            status: opts.generateError.status,
            headers: { "Content-Type": "application/json" },
          }),
        );
      return ok({ jobId: "job-1", sections: 2 });
    }
    if (path.includes("/commit")) return ok({ saved: 1 });
    if (path.includes("/cancel")) return ok({ ok: true });
    if (path.includes("/api/jobs/")) return ok(queue.length > 1 ? queue.shift() : queue[0]);
    // The bare list, asked for on mount to find a run already in flight.
    if (path.endsWith("/api/jobs")) return ok(opts.existing ?? []);
    return ok({});
  });
  return calls;
}

async function chooseCourse() {
  const select = await screen.findByLabelText("Course");
  await userEvent.selectOptions(select, "demo");
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("the form", () => {
  it("cannot generate until a course is chosen", async () => {
    mockApi();
    render(<GeneratePane />);
    const button = await screen.findByRole("button", { name: "Generate" });
    expect(button).toBeDisabled();

    await chooseCourse();
    await waitFor(() => expect(button).toBeEnabled());
  });

  it("loads the labs of the chosen course", async () => {
    mockApi();
    render(<GeneratePane />);
    await chooseCourse();
    expect(await screen.findByRole("option", { name: "First Lab" })).toBeInTheDocument();
  });

  it("clears the selected lab when the course changes", async () => {
    // A lab slug belongs to one course. Carrying it over would send the
    // backend a lab the new course has never heard of.
    mockApi();
    render(<GeneratePane />);
    await chooseCourse();

    const lab = await screen.findByLabelText("Lab");
    await userEvent.selectOptions(lab, "01-lab");
    expect((lab as HTMLSelectElement).value).toBe("01-lab");

    await userEvent.selectOptions(screen.getByLabelText("Course"), "");
    expect((lab as HTMLSelectElement).value).toBe("");
  });

  it("keeps at least one Bloom level", async () => {
    // An empty list gives the backend nothing to spread across the sections.
    mockApi();
    render(<GeneratePane />);
    const apply = await screen.findByRole("checkbox", { name: /Apply/ });
    expect(apply).toBeChecked();

    await userEvent.click(apply);
    expect(apply).toBeChecked();
  });

  it("sends what the form says", async () => {
    const calls = mockApi();
    render(<GeneratePane />);
    await chooseCourse();

    await userEvent.clear(screen.getByLabelText("Questions"));
    await userEvent.type(screen.getByLabelText("Questions"), "7");
    await userEvent.selectOptions(screen.getByLabelText("Difficulty"), "Hard");
    await userEvent.selectOptions(screen.getByLabelText("File under"), "c1");
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));

    await waitFor(() => {
      const post = calls.find((c) => c.url.includes("/api/generate") && c.method === "POST");
      expect(post?.body).toMatchObject({
        course_slug: "demo", total: 7, difficulty: "Hard", certification_id: "c1",
      });
    });
  });

  it("shows the server's refusal rather than starting", async () => {
    mockApi({
      generateError: { status: 422, detail: "demo has no sections with enough prose" },
    });
    render(<GeneratePane />);
    await chooseCourse();
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));

    expect(await screen.findByText(/no sections with enough prose/)).toBeInTheDocument();
  });
});

describe("the job", () => {
  it("polls until it finishes, then shows the results", async () => {
    mockApi({
      jobs: [
        job({ status: "running", progress: { current: 1, total: 2, message: "Generating…" }, result: [], count: 0 }),
        job(),
      ],
    });
    render(<GeneratePane />);
    await chooseCourse();
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));

    expect(await screen.findByText("Generating")).toBeInTheDocument();
    expect(await screen.findByText("Generated 1")).toBeInTheDocument();
    expect(screen.getByText("Which step reads a delimited file?")).toBeInTheDocument();
  });

  it("stops polling once the job is done", async () => {
    // A timer left running keeps calling the API for a job nobody is watching,
    // and keeps setting state on a component that may be gone.
    const calls = mockApi();
    render(<GeneratePane />);
    await chooseCourse();
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));
    await screen.findByText("Generated 1");

    const after = calls.filter((c) => c.url.includes("/api/jobs/")).length;
    await new Promise((r) => setTimeout(r, 1200)); // longer than the poll interval
    expect(calls.filter((c) => c.url.includes("/api/jobs/")).length).toBe(after);
  });

  it("stops polling when the component goes away", async () => {
    const calls = mockApi({
      jobs: [job({ status: "running", progress: { current: 0, total: 2, message: "…" }, result: [], count: 0 })],
    });
    const view = render(<GeneratePane />);
    await chooseCourse();
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));
    await screen.findByText("Generating");

    view.unmount();
    const after = calls.filter((c) => c.url.includes("/api/jobs/")).length;
    await new Promise((r) => setTimeout(r, 1200));
    expect(calls.filter((c) => c.url.includes("/api/jobs/")).length).toBe(after);
  });

  it("picks up a run that was already going", async () => {
    // A course takes the better part of an hour and the job lives in the
    // backend. Reloading the page, or opening a second tab, must not show an
    // idle form with no sign that anything is happening.
    const running = job({
      id: "job-1", status: "running", result: [], count: 0,
      progress: { current: 7, total: 63, message: "Generating from section 7/63…" },
    });
    mockApi({ existing: [running], jobs: [running] });
    render(<GeneratePane />);

    expect(await screen.findByText("Generating")).toBeInTheDocument();
    expect(await screen.findByText(/section 7\/63/)).toBeInTheDocument();
    expect(await screen.findByText("7/63")).toBeInTheDocument();
  });

  it("does not adopt a job that has already finished", async () => {
    // Only a RUNNING job is worth attaching to. Showing a stale result on
    // every page load would be noise, and would read as a run just ending.
    mockApi({ existing: [job({ id: "old", status: "done" })] });
    render(<GeneratePane />);
    await screen.findByLabelText("Course");

    expect(screen.queryByText("Generated 1")).not.toBeInTheDocument();
    expect(screen.queryByText("Review")).not.toBeInTheDocument();
  });

  it("reports a failed job with the backend's reason", async () => {
    mockApi({ jobs: [job({ status: "error", error: "Ollama request failed: refused", result: [], count: 0 })] });
    render(<GeneratePane />);
    await chooseCourse();
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));

    expect(await screen.findByText(/Ollama request failed: refused/)).toBeInTheDocument();
  });
});

describe("review and commit", () => {
  it("starts with everything selected", async () => {
    // The author is reviewing a proposal; unticking what is wrong is less
    // work than ticking everything that is right.
    mockApi();
    render(<GeneratePane />);
    await chooseCourse();
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));

    expect(await screen.findByText("1 of 1 selected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Save 1 to the bank/ })).toBeEnabled();
  });

  it("saves only what is ticked", async () => {
    const calls = mockApi({
      jobs: [job({ count: 2, result: [question(), question({ id: "gen-2", stem: "Second?" })] })],
    });
    render(<GeneratePane />);
    await chooseCourse();
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));
    await screen.findByText("2 of 2 selected");

    await userEvent.click(screen.getByRole("checkbox", { name: "Keep: Second?" }));
    await userEvent.click(screen.getByRole("button", { name: /Save 1 to the bank/ }));

    await waitFor(() => {
      const commit = calls.find((c) => c.url.includes("/commit"));
      expect(commit?.body).toMatchObject({ question_ids: ["gen-1"] });
    });
  });

  it("cannot save nothing", async () => {
    mockApi();
    render(<GeneratePane />);
    await chooseCourse();
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));
    await screen.findByText("1 of 1 selected");

    await userEvent.click(screen.getByRole("button", { name: "Select none" }));
    expect(screen.getByRole("button", { name: /Save 0 to the bank/ })).toBeDisabled();
  });

  it("flags a question whose answer was not traced to the source", async () => {
    // The generator tags these. It is the one thing a reviewer most needs to
    // see before keeping a question.
    mockApi({ jobs: [job({ result: [question({ tags: ["key-not-validated"] })] })] });
    render(<GeneratePane />);
    await chooseCourse();
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));

    expect(await screen.findByText(/answer not traced to the source/)).toBeInTheDocument();
  });

  it("confirms the save and clears the review", async () => {
    mockApi();
    render(<GeneratePane />);
    await chooseCourse();
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));
    await screen.findByText("1 of 1 selected");

    await userEvent.click(screen.getByRole("button", { name: /Save 1 to the bank/ }));

    expect(await screen.findByText(/Saved 1 question to the bank/)).toBeInTheDocument();
    expect(screen.queryByText("Review")).not.toBeInTheDocument();
  });
});

describe("question formats", () => {
  it("sends no formats by default, so every question is the same shape", async () => {
    const calls = mockApi();
    render(<GeneratePane />);
    await chooseCourse();
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));

    await waitFor(() => {
      const post = calls.find((c) => c.url.includes("/api/generate") && c.method === "POST");
      expect((post?.body as { formats: unknown[] }).formats).toEqual([]);
    });
  });

  it("Mix formats is disabled until there are two to mix", async () => {
    // Shuffling one repeated shape changes nothing. A control that silently
    // does nothing is worse than one that is greyed out — which is what this
    // checkbox was before formats existed.
    mockApi();
    render(<GeneratePane />);
    const mix = await screen.findByRole("checkbox", { name: /Mix formats/ });
    expect(mix).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Add a format" }));
    expect(mix).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Add a format" }));
    await waitFor(() => expect(mix).toBeEnabled());
  });

  it("a second row defaults to a multi-select, because that is the point", async () => {
    mockApi();
    render(<GeneratePane />);
    await userEvent.click(await screen.findByRole("button", { name: "Add a format" }));
    expect(screen.getByText("“Choose one.”")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Add a format" }));
    expect(screen.getByText("“Choose two.”")).toBeInTheDocument();
  });

  it("the author sets TOTAL options, not distractors", async () => {
    // "How many distractors is a five-option question" is arithmetic nobody
    // should have to do; the conversion happens in the UI.
    const calls = mockApi();
    render(<GeneratePane />);
    await chooseCourse();
    await userEvent.click(screen.getByRole("button", { name: "Add a format" }));

    const total = screen.getByLabelText("of");
    await userEvent.clear(total);
    await userEvent.type(total, "5");
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));

    await waitFor(() => {
      const post = calls.find((c) => c.url.includes("/api/generate") && c.method === "POST");
      expect((post?.body as { formats: unknown[] }).formats).toEqual([
        { keys: 1, distractors: 4 },
      ]);
    });
  });

  it("a row can be removed", async () => {
    mockApi();
    render(<GeneratePane />);
    await userEvent.click(await screen.findByRole("button", { name: "Add a format" }));
    await userEvent.click(screen.getByRole("button", { name: "Remove format 1" }));

    expect(screen.getByText(/Add a format to mix shapes/)).toBeInTheDocument();
  });

  it("mixes shapes in one run", async () => {
    const calls = mockApi();
    render(<GeneratePane />);
    await chooseCourse();
    await userEvent.click(screen.getByRole("button", { name: "Add a format" }));
    await userEvent.click(screen.getByRole("button", { name: "Add a format" }));
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));

    await waitFor(() => {
      const post = calls.find((c) => c.url.includes("/api/generate") && c.method === "POST");
      expect((post?.body as { formats: unknown[] }).formats).toEqual([
        { keys: 1, distractors: 3 },
        { keys: 2, distractors: 3 },
      ]);
    });
  });
});
