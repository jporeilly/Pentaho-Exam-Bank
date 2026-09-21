import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CoursesPane } from "./CoursesPane";
import type { CourseSections, Section } from "./api";

function section(over: Partial<Section> = {}): Section {
  return {
    index: 0, title: "Opening", characters: 674, exceedsContext: false,
    preview: "Prose about the topic.", ...over,
  };
}

function mockApi(contents: CourseSections) {
  vi.stubGlobal("fetch", (url: string) => {
    const path = String(url);
    const body = path.includes("/sections")
      ? contents
      : path.includes("/labs")
        ? [{ slug: "01-lab", title: "First Lab" }]
        : [{ slug: "demo", title: "Demo Course", hasExam: true, questionCount: 3 }];
    return Promise.resolve(
      new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } }),
    );
  });
}

const BUDGET = { chars: 20340, numCtx: 8192, model: "gemma4:12b" };

async function openContents() {
  await userEvent.click(await screen.findByRole("button", { name: "Contents" }));
}

afterEach(() => vi.unstubAllGlobals());

describe("sections that do not fit the model's context", () => {
  it("marks the section and says what it costs", async () => {
    // Ollama truncates silently: the questions come back thinner than the
    // material deserved with nothing anywhere to say why.
    mockApi({
      budget: BUDGET,
      sections: [
        section(),
        section({ index: 1, title: "Key Concepts Workshop", characters: 109009,
                  exceedsContext: true }),
      ],
    });
    render(<CoursesPane />);
    await openContents();

    expect(await screen.findByText("truncated")).toBeInTheDocument();
    expect(screen.getByText(/longer than gemma4:12b can read in one go/))
      .toBeInTheDocument();
  });

  it("names the window and the budget so the fix is obvious", async () => {
    mockApi({
      budget: BUDGET,
      sections: [section({ characters: 109009, exceedsContext: true })],
    });
    render(<CoursesPane />);
    await openContents();

    // A larger window, a smaller model, or split the section — the author
    // cannot choose between those without both numbers.
    expect(await screen.findByText(/8,192 tokens/)).toBeInTheDocument();
    expect(screen.getByText(/20,340 characters/)).toBeInTheDocument();
  });

  it("counts them, and reads correctly for one", async () => {
    mockApi({
      budget: BUDGET,
      sections: [section({ characters: 99999, exceedsContext: true })],
    });
    render(<CoursesPane />);
    await openContents();
    expect(await screen.findByText(/1 section is longer/)).toBeInTheDocument();
  });

  it("says nothing when everything fits", async () => {
    // The warning has to stay rare, or it stops being read.
    mockApi({
      budget: BUDGET,
      sections: [section(), section({ index: 1, title: "Second Section" })],
    });
    render(<CoursesPane />);
    await openContents();

    expect(await screen.findByText("Second Section")).toBeInTheDocument();
    expect(screen.queryByText("truncated")).not.toBeInTheDocument();
    expect(screen.queryByText(/longer than/)).not.toBeInTheDocument();
  });

  it("says nothing when no context window is configured", async () => {
    // Ollama would use the model's own default, which the app does not know.
    // Flagging against a made-up number is worse than not flagging.
    mockApi({
      budget: { chars: 0, numCtx: 0, model: "gemma4:12b" },
      sections: [section({ characters: 500000, exceedsContext: false })],
    });
    render(<CoursesPane />);
    await openContents();

    expect(await screen.findByText("Opening")).toBeInTheDocument();
    expect(screen.queryByText("truncated")).not.toBeInTheDocument();
  });
});
