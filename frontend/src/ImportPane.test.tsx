import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ImportPane } from "./ImportPane";
import type { ImportedQuestion, ImportPreview, Question } from "./api";

const CERTS = [
  {
    id: "cert-1", name: "DI Practitioner", description: "",
    sourceType: "pcm", sourceRef: "developer-di-practitioner", questionCount: 48,
  },
];

function question(over: Partial<Question> = {}): Question {
  return {
    id: "q1", scenario: "", stem: "Which step reads a delimited file?",
    question_type: "single", key: "CSV file input", keys: [], key_source_text: "",
    distractors: ["Table output"], option_order: [], explanation: "", topic: "",
    tags: [], difficulty: "Medium", bloom_level: "Apply", certification_id: "",
    pool_order: -1, status: "draft", assigned_sme: "", review_history: [],
    version_history: [], updated_at: "",
    ...over,
  };
}

function item(over: Partial<ImportedQuestion> = {}): ImportedQuestion {
  return {
    question: question(),
    problems: [],
    duplicate_of: "",
    duplicate_stem: "",
    duplicate_score: 0,
    ...over,
  };
}

function preview(over: Partial<ImportPreview> = {}): ImportPreview {
  const questions = over.questions ?? [item()];
  return {
    filename: "questions.csv",
    format: "csv",
    formatLabel: "CSV",
    formatNote: "",
    count: questions.length,
    gradeable: questions.filter((q) => q.problems.length === 0).length,
    duplicates: questions.filter((q) => q.duplicate_of).length,
    ...over,
    questions,
  };
}

/** Records every request so a test can assert what was NOT sent. */
function mockApi(handlers: {
  preview?: ImportPreview | { status: number; detail: string };
  commit?: unknown;
  docs?: unknown;
} = {}) {
  const calls: Array<{ path: string; body: unknown }> = [];
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const path = String(url);
    const isForm = typeof FormData !== "undefined" && init?.body instanceof FormData;
    calls.push({
      path,
      body: isForm ? "<form>" : init?.body ? JSON.parse(String(init.body)) : null,
    });

    const json = (body: unknown, status = 200) =>
      Promise.resolve(
        new Response(JSON.stringify(body), {
          status,
          headers: { "Content-Type": "application/json" },
        }),
      );

    if (path.includes("/import/preview")) {
      const r = handlers.preview ?? preview();
      return "status" in r ? json({ detail: r.detail }, r.status) : json(r);
    }
    if (path.includes("/import/check-docs")) {
      return json(handlers.docs ?? { results: [], threshold: 0.7, ms: 10 });
    }
    if (path.includes("/import/commit")) {
      return json(handlers.commit ?? { saved: 1, ids: ["q1"], refused: [] });
    }
    return json(CERTS);
  });
  return calls;
}

async function upload(name = "questions.csv") {
  const input = screen.getByLabelText("Question file") as HTMLInputElement;
  await userEvent.upload(input, new File(["stem,key\n"], name, { type: "text/csv" }));
}

afterEach(() => vi.unstubAllGlobals());

describe("reading the file", () => {
  it("shows what the file turned out to be", async () => {
    mockApi({ preview: preview({ formatLabel: "Content Manager exam.json" }) });
    render(<ImportPane />);

    await upload();

    expect(await screen.findByText(/Content Manager exam\.json/)).toBeInTheDocument();
  });

  it("saves nothing while previewing", async () => {
    const calls = mockApi();
    render(<ImportPane />);

    await upload();
    await screen.findByRole("table");

    expect(calls.some((c) => c.path.includes("/import/commit"))).toBe(false);
  });

  it("shows the format's warning where the file has one", async () => {
    // The plain-text reader takes the FIRST option as the key, positionally.
    // The result is gradeable, so nothing else flags it — this is the only
    // warning there is.
    mockApi({
      preview: preview({
        formatLabel: "Plain-text questions",
        formatNote:
          "The text format has no way to mark a correct answer, so the FIRST " +
          "option of each question is taken as the key.",
      }),
    });
    render(<ImportPane />);

    await upload();

    expect(await screen.findByText(/FIRST option/)).toBeInTheDocument();
  });

  it("shows the server's refusal rather than inventing one", async () => {
    // An extension the picker allows whose CONTENT is not recognised - the
    // only refusal a user can actually reach, since `accept` filters the
    // obviously-wrong extensions before they are ever uploaded.
    mockApi({
      preview: {
        status: 415,
        detail: "That XML is neither QTI 2.1 nor Moodle XML.",
      },
    });
    render(<ImportPane />);

    await upload("export.xml");

    expect(await screen.findByText(/neither QTI 2.1 nor Moodle/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("what gets selected", () => {
  it("selects the gradeable questions that are not already in the bank", async () => {
    mockApi({
      preview: preview({
        questions: [
          item(),
          item({ question: question({ id: "q2" }), duplicate_of: "existing", duplicate_score: 92 }),
        ],
      }),
    });
    render(<ImportPane />);

    await upload();

    expect(await screen.findByRole("button", { name: "Import 1 of 2" })).toBeInTheDocument();
  });

  it("leaves a duplicate unticked but tickable", async () => {
    // "We reworded it" is a real answer, so this is a decision rather than a
    // refusal — but a pre-ticked decision is not one.
    mockApi({
      preview: preview({
        questions: [item({ duplicate_of: "existing", duplicate_score: 92 })],
      }),
    });
    render(<ImportPane />);

    await upload();
    const box = await screen.findByRole("checkbox");

    expect(box).not.toBeChecked();
    expect(box).toBeEnabled();
    await userEvent.click(box);
    expect(await screen.findByRole("button", { name: "Import 1 of 1" })).toBeInTheDocument();
  });

  it("will not let an ungradeable question be chosen at all", async () => {
    // The server refuses these. Leaving it tickable moves the refusal to
    // after the button.
    mockApi({
      preview: preview({
        questions: [
          item({
            question: question({ key: "" }),
            problems: [
              { field: "keys", message: "Nothing is marked correct, so the question cannot be graded." },
            ],
          }),
        ],
      }),
    });
    render(<ImportPane />);

    await upload();

    expect(await screen.findByRole("checkbox")).toBeDisabled();
    // The whole sentence: "cannot be graded" alone also matches the stat
    // label counting them, so the short form is ambiguous.
    expect(
      screen.getByText("Nothing is marked correct, so the question cannot be graded."),
    ).toBeInTheDocument();
  });

  it("says how a duplicate matched, not just that it did", async () => {
    mockApi({
      preview: preview({
        questions: [
          item({
            duplicate_of: "existing",
            duplicate_score: 92,
            duplicate_stem: "Which step reads a CSV?",
          }),
        ],
      }),
    });
    render(<ImportPane />);

    await upload();

    expect(await screen.findByText(/92% match/)).toBeInTheDocument();
    expect(screen.getByText(/Which step reads a CSV\?/)).toBeInTheDocument();
  });

  it("select-all takes the gradeable ones only", async () => {
    mockApi({
      preview: preview({
        questions: [
          item(),
          item({
            question: question({ id: "q2", key: "" }),
            problems: [{ field: "keys", message: "Nothing is marked correct." }],
          }),
          item({ question: question({ id: "q3" }), duplicate_of: "existing" }),
        ],
      }),
    });
    render(<ImportPane />);

    await upload();
    await userEvent.click(await screen.findByRole("button", { name: "Select all gradeable" }));

    expect(await screen.findByRole("button", { name: "Import 2 of 3" })).toBeInTheDocument();
  });
});

describe("saving", () => {
  it("sends only the chosen questions", async () => {
    const calls = mockApi({
      preview: preview({
        questions: [item(), item({ question: question({ id: "q2" }) })],
      }),
    });
    render(<ImportPane />);

    await upload();
    await userEvent.click((await screen.findAllByRole("checkbox"))[1]);
    await userEvent.click(screen.getByRole("button", { name: "Import 1 of 2" }));

    const commit = calls.find((c) => c.path.includes("/import/commit"))!;
    expect((commit.body as { questions: Question[] }).questions.map((q) => q.id)).toEqual(["q1"]);
  });

  it("sends the certification and topic that were chosen", async () => {
    const calls = mockApi();
    render(<ImportPane />);

    await upload();
    await userEvent.selectOptions(await screen.findByLabelText("Certification"), "cert-1");
    await userEvent.type(screen.getByLabelText("Topic"), "Lab 1");
    await userEvent.click(screen.getByRole("button", { name: "Import 1 of 1" }));

    const commit = calls.find((c) => c.path.includes("/import/commit"))!;
    expect(commit.body).toMatchObject({ certification_id: "cert-1", topic: "Lab 1" });
  });

  it("says how many landed, and that they are drafts", async () => {
    mockApi({ commit: { saved: 2, ids: ["a", "b"], refused: [] } });
    render(<ImportPane />);

    await upload();
    await userEvent.click(await screen.findByRole("button", { name: /^Import/ }));

    expect(await screen.findByText("Imported")).toBeInTheDocument();
    expect(screen.getByText(/added to the bank as/)).toBeInTheDocument();
  });

  it("names anything the server refused, with the reason", async () => {
    mockApi({
      commit: {
        saved: 1,
        ids: ["a"],
        refused: [{ stem: "Which step?", reason: "Nothing is marked correct." }],
      },
    });
    render(<ImportPane />);

    await upload();
    await userEvent.click(await screen.findByRole("button", { name: /^Import/ }));

    const refused = await screen.findByRole("list");
    expect(within(refused).getByText("Which step?")).toBeInTheDocument();
    expect(within(refused).getByText(/Nothing is marked correct/)).toBeInTheDocument();
  });

  it("clears the preview after saving, so nothing is imported twice", async () => {
    mockApi();
    render(<ImportPane />);

    await upload();
    await userEvent.click(await screen.findByRole("button", { name: /^Import/ }));
    await screen.findByText("Imported");

    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("checking against docs.pentaho.com", () => {
  // The docs check existed since the NiceGUI days with no button anywhere.
  it("says per question whether the docs back the answer, and imports nothing", async () => {
    const calls = mockApi({
      preview: preview({ questions: [item(), item({ question: question({ id: "q2", stem: "Which reads Access?",
                                                                          key: "Access input" }) })] }),
      docs: { threshold: 0.7, ms: 900, results: [
        { status: "supported", detail: "CSV file input: 100%", answers: [],
          sources: [{ title: "Text File Input", link: "https://docs.pentaho.com/pdi/text-file-input" }] },
        { status: "not-found", detail: "Access input: 50%", answers: [], sources: [] },
      ] },
    });
    render(<ImportPane />);
    await upload();
    await screen.findByText("Which reads Access?");

    await userEvent.click(screen.getByRole("button", { name: "Check answers against docs.pentaho.com" }));

    expect(await screen.findByText(/backs 1 of 2 answers; 1 not found there/)).toBeInTheDocument();
    expect(screen.getByText("Backed")).toBeInTheDocument();
    expect(screen.getByText("Not found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Text File Input" })).toBeInTheDocument();
    const sent = calls.find((c) => c.path.includes("/import/check-docs"))!.body as { questions: unknown[] };
    expect(sent.questions).toHaveLength(2);
    expect(calls.some((c) => c.path.includes("/import/commit"))).toBe(false);
  });

  it("shows why the check could not run", async () => {
    mockApi();
    vi.stubGlobal("fetch", ((orig) => (url: string, init?: RequestInit) =>
      String(url).includes("/import/check-docs")
        ? Promise.resolve(new Response(JSON.stringify({ detail: "The Pentaho docs connection is off in Settings." }),
                                       { status: 409, headers: { "Content-Type": "application/json" } }))
        : orig(url, init))(globalThis.fetch as (u: string, i?: RequestInit) => Promise<Response>));
    render(<ImportPane />);
    await upload();
    await screen.findByText("Which step reads a delimited file?");

    await userEvent.click(screen.getByRole("button", { name: "Check answers against docs.pentaho.com" }));

    expect(await screen.findByText(/connection is off in Settings/)).toBeInTheDocument();
  });
});
