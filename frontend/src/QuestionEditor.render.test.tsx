/**
 * The editor as the Bank uses it, rendered: saving says so and keeps saying
 * so, and an approved question can be sent back.
 *
 * Rendered through BankPane on purpose. The "Saved" that nobody ever saw was
 * not a bug in the editor alone: the editor cleared it whenever its question
 * prop changed, and BankPane hands the saved question straight back in. Only
 * the two together show it.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BankPane } from "./BankPane";
import type { Question } from "./api";

function question(over: Partial<Question> = {}): Question {
  return {
    id: "m1-q1", scenario: "A developer is loading a file.", stem: "Which step reads a file?",
    question_type: "single", key: "CSV input", keys: [], key_source_text: "",
    distractors: ["Table output", "Sort rows"], option_order: [],
    explanation: "", topic: "Getting Started", tags: [], difficulty: "Medium",
    bloom_level: "Apply", certification_id: "c1", pool_order: 0, status: "draft",
    assigned_sme: "", review_history: [], version_history: [],
    updated_at: "2026-09-28T10:00:00", ...over,
  };
}

const TRANSITIONS = {
  draft: ["sme_review", "rejected"],
  sme_review: ["revised", "approved", "rejected"],
  revised: ["sme_review", "approved", "rejected"],
  approved: ["sme_review", "draft", "retired"],
  rejected: ["draft"],
  retired: ["draft"],
};

/** A small fake of the server: it keeps the question, applies PUTs and
 *  status moves to it, and answers the lists the pane asks for. With
 *  `renameTo`, a PUT that changes the topic renames the question, as the
 *  bank does when a course question moves to another module. */
function fakeServer(start: Question, renameTo = "") {
  let current = start;
  const puts: string[] = [];
  const bodies: Record<string, unknown>[] = [];
  const json = (body: unknown) =>
    Promise.resolve(new Response(JSON.stringify(body), {
      headers: { "Content-Type": "application/json" },
    }));
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const u = String(url);
    const method = init?.method ?? "GET";
    if (u.includes("/api/lifecycle")) {
      return json({ statuses: Object.keys(TRANSITIONS), transitions: TRANSITIONS });
    }
    if (u.includes("/api/certifications")) {
      return json([{ id: "c1", name: "DI Practitioner", description: "", sourceType: "pcm",
                     sourceRef: "developer-di-practitioner", questionCount: 1 }]);
    }
    if (method === "POST" && u.endsWith("/ai/explanation")) {
      return json({
        explanation: "CSV input reads the file. Table output writes rows. Sort rows orders them.",
        groundedOn: "Text File Input",
        unnamed: [],
      });
    }
    if (method === "POST" && u.endsWith("/ai/answer")) {
      return json({
        proposed: { ...current, key: "Table output", distractors: ["CSV input", "Sort rows"],
                    tags: current.tags.filter((t) => t !== "key-unverified") },
        changed: true,
        analysis: [
          { option: "CSV input", correct: false, quote: "" },
          { option: "Table output", correct: true, quote: "Table output writes rows." },
          { option: "Sort rows", correct: false, quote: "" },
        ],
        groundedOn: "Text File Output",
      });
    }
    if (method === "PUT") {
      puts.push(u);
      bodies.push(JSON.parse(String(init?.body)));
      const body = JSON.parse(String(init?.body));
      const moved = renameTo && body.topic !== current.topic;
      current = { ...current, ...body, ...(moved ? { id: renameTo } : {}) };
      return json(current);
    }
    if (method === "POST" && u.endsWith("/ai/rewrite")) {
      // A model that ignored the rule: its scenario asks the question.
      return json({
        proposed: { ...current, scenario: "What does a developer check first?",
                    stem: "Which step reads the file?" },
        problems: [],
        notes: [{ field: "scenario", message: "The scenario asks a question. A scenario is " +
                  "statements that set the scene; the question belongs in the Question field." }],
        unchanged: false,
      });
    }
    if (method === "POST" && u.endsWith("/status")) {
      current = { ...current, status: JSON.parse(String(init?.body)).status };
      return json(current);
    }
    return json({ items: [current], total: 1, limit: 25, offset: 0 });
  });
  return { puts, bodies };
}

afterEach(() => vi.unstubAllGlobals());

async function openEditor() {
  render(<BankPane />);
  await userEvent.click(await screen.findByText("Which step reads a file?"));
  return screen.findByText("Edit question");
}

describe("how the answers look", () => {
  it("draws the correct answer green and each distractor rose, without changing their labels", async () => {
    fakeServer(question());
    await openEditor();

    // The tick is CSS, so the label still reads exactly "Correct answer".
    const key = screen.getByLabelText("Correct answer");
    expect(key).toHaveValue("CSV input");
    expect(key.closest(".field")).toHaveClass("answer-key");

    const distractor = screen.getByDisplayValue("Table output");
    expect(distractor.closest(".option-row")).toHaveClass("wrong");
    expect(screen.getByDisplayValue("Sort rows").closest(".option-row")).toHaveClass("wrong");
  });

  it("colours the buttons by what they do", async () => {
    fakeServer(question());
    await openEditor();

    expect(screen.getByRole("button", { name: "AI answer key" })).toHaveClass("secondary", "ai");
    expect(screen.getByRole("button", { name: "Add a distractor" })).toHaveClass("secondary", "add");
    expect(screen.getAllByRole("button", { name: "Remove" })[0]).toHaveClass("secondary", "danger");
    expect(screen.getByRole("button", { name: "Reject" })).toHaveClass("danger");
    expect(screen.getByRole("button", { name: "Send for review" })).toHaveClass("info");
  });
});

describe("saving a question", () => {
  it("says it was saved, and the message survives the Bank refreshing the row", async () => {
    fakeServer(question());
    await openEditor();

    const stem = screen.getByDisplayValue("Which step reads a file?");
    await userEvent.type(stem, " today");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("status")).toHaveTextContent(/Saved at \d/);
    // Still there after BankPane has handed the saved question back in.
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.getByRole("status")).toHaveTextContent(/Saved at/);
  });

  it("clears the message at the next edit", async () => {
    fakeServer(question());
    await openEditor();

    const stem = screen.getByDisplayValue("Which step reads a file?");
    await userEvent.type(stem, "!");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("status");

    await userEvent.type(stem, "?");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("reminds the author when the question they saved is still approved", async () => {
    fakeServer(question({ status: "approved" }));
    await openEditor();

    await userEvent.type(screen.getByDisplayValue("Which step reads a file?"), " now");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      /Still approved: send it back for review/,
    );
  });
});

describe("moving a course question to another module", () => {
  // Its id names the module (<course>-m<module>-q<n>), so the bank renames
  // it. The Bank list keyed rows on the id and patched only a row with the
  // NEW id, so the renamed question's row went stale; and the editor cleared
  // its notice whenever the id changed, so the save looked unconfirmed.
  it("says the id changed, keeps the notice, and the next save uses the new id", async () => {
    const server = fakeServer(question({ id: "di-m1-q1" }), "di-m3-q15");
    await openEditor();

    const topic = screen.getByDisplayValue("Getting Started");
    await userEvent.clear(topic);
    await userEvent.type(topic, "Data Sources");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("status")).toHaveTextContent(/Saved at \d/);
    expect(screen.getByRole("status")).toHaveTextContent("Its id is now di-m3-q15");
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.getByRole("status")).toHaveTextContent("di-m3-q15");
    // The row follows the question to its new id; none is left on the old one.
    expect(screen.getByRole("cell", { name: "di-m3-q15" })).toBeInTheDocument();
    expect(screen.queryByRole("cell", { name: "di-m1-q1" })).not.toBeInTheDocument();

    await userEvent.type(screen.getByDisplayValue("Which step reads a file?"), "!");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("status");
    expect(server.puts.at(-1)).toContain("/api/questions/di-m3-q15");
  });
});

describe("the house form", () => {
  it("advises, without blocking Save, when the scenario asks a question", async () => {
    fakeServer(question());
    await openEditor();

    await userEvent.type(screen.getByDisplayValue("A developer is loading a file."), " Why?");

    expect(screen.getByText(/The scenario asks a question/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
  });

  it("shows the rewrite's scenario, and says when the model broke the form", async () => {
    fakeServer(question());
    await openEditor();

    await userEvent.click(screen.getByRole("button", { name: "AI rewrite" }));

    expect(await screen.findByText("What does a developer check first?")).toBeInTheDocument();
    expect(screen.getByText(/Scenario: The scenario asks a question/)).toBeInTheDocument();
  });
});

describe("an approved question", () => {
  it("can be sent back for review, and says where it went", async () => {
    fakeServer(question({ status: "approved" }));
    await openEditor();

    expect(screen.getByRole("button", { name: "Back to draft" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retire" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Send for review" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Moved to SME Review");
  });

  it("can be sent back to draft", async () => {
    fakeServer(question({ status: "approved" }));
    await openEditor();

    await userEvent.click(screen.getByRole("button", { name: "Back to draft" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Moved to Draft");
  });
});

describe("AI explanation and AI answer key", () => {
  // Both propose; nothing reaches the bank until the author presses Save.
  it("puts a proposed explanation into the field only when taken, and saves nothing", async () => {
    const server = fakeServer(question());
    await openEditor();

    await userEvent.click(screen.getByRole("button", { name: "AI explanation" }));
    expect(await screen.findByText(/Written from Text File Input/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Use this explanation" }));

    expect(screen.getByDisplayValue(/CSV input reads the file/)).toBeInTheDocument();
    expect(server.puts).toHaveLength(0);
  });

  it("flags a guessed answer, and taking the AI answer key clears the flag", async () => {
    const server = fakeServer(question({ tags: ["key-unverified"] }));
    await openEditor();
    expect(screen.getByRole("note")).toHaveTextContent(/guessed when this question was imported/);

    await userEvent.click(screen.getByRole("button", { name: "AI answer key" }));
    expect(await screen.findByText(/Decided from Text File Output/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Use this answer" }));

    expect(screen.queryByRole("note")).not.toBeInTheDocument();
    expect(screen.getByDisplayValue("Table output")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("status");
    expect(server.bodies.at(-1)).toMatchObject({ key: "Table output", tags: [] });
  });

  it("lets the author confirm a guessed answer is right", async () => {
    const server = fakeServer(question({ tags: ["key-unverified", "imported"] }));
    await openEditor();

    await userEvent.click(screen.getByRole("button", { name: "The answer is right" }));
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("status");

    expect(server.bodies.at(-1)).toMatchObject({ key: "CSV input", tags: ["imported"] });
  });
});

describe("formatting the text", () => {
  // Bold, italic and code are markers in the text (**, *, `), so the bank,
  // the exports and the course's exam.json all carry them as plain strings.
  // The bar and the shortcuts only ever wrap or unwrap the selection.
  const select = (el: HTMLInputElement | HTMLTextAreaElement, word: string) => {
    el.focus();
    const at = el.value.indexOf(word);
    el.setSelectionRange(at, at + word.length);
  };

  it("Ctrl+B bolds the selected words, previews them, and saves the markers", async () => {
    const server = fakeServer(question());
    // A window that is not painting never delivers a frame. The selection
    // was once put back in requestAnimationFrame and was lost exactly there.
    vi.stubGlobal("requestAnimationFrame", () => 0);
    await openEditor();
    const stem = screen.getByDisplayValue("Which step reads a file?") as HTMLTextAreaElement;

    select(stem, "reads");
    await userEvent.keyboard("{Control>}b{/Control}");

    expect(stem).toHaveValue("Which step **reads** a file?");
    // The same words stay selected, so a second press unbolds them.
    expect(stem.value.slice(stem.selectionStart, stem.selectionEnd)).toBe("reads");
    await userEvent.keyboard("{Control>}b{/Control}");
    expect(stem).toHaveValue("Which step reads a file?");
    await userEvent.keyboard("{Control>}b{/Control}");
    const preview = stem.closest(".field")!.querySelector(".format-preview")!;
    expect(preview.querySelector("strong")).toHaveTextContent("reads");

    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText(/Saved at/);
    expect(server.bodies.at(-1)!.stem).toBe("Which step **reads** a file?");
  });

  it("the bar waits for a text field, and leaves when the author moves to one it cannot format", async () => {
    fakeServer(question());
    await openEditor();
    const italic = screen.getByRole("button", { name: "Italic (Ctrl+I)" });
    expect(italic).toBeDisabled();

    const scenario = screen.getByDisplayValue("A developer is loading a file.") as HTMLTextAreaElement;
    select(scenario, "loading");
    await waitFor(() => expect(italic).toBeEnabled());
    await userEvent.click(italic);
    expect(scenario).toHaveValue("A developer is *loading* a file.");

    await userEvent.click(screen.getByDisplayValue("Getting Started")); // Topic: no formatting
    expect(italic).toBeDisabled();
  });

  it("code on one distractor touches only that distractor", async () => {
    fakeServer(question({ distractors: ["Table output", "Sort rows"] }));
    await openEditor();
    const sort = screen.getByDisplayValue("Sort rows") as HTMLInputElement;
    select(sort, "Sort rows");
    await userEvent.click(screen.getByRole("button", { name: "Code" }));

    expect(sort).toHaveValue("`Sort rows`");
    expect(screen.getByDisplayValue("Table output")).toBeInTheDocument();
    const row = sort.closest(".option-row")!;
    expect(row.querySelector(".format-preview code")).toHaveTextContent("Sort rows");
  });

  it("the Bank's list draws the formatting rather than the markers", async () => {
    fakeServer(question({ stem: "Which step **reads** a `.csv` file?" }));
    render(<BankPane />);
    const bold = await screen.findByText("reads");
    expect(bold.tagName).toBe("STRONG");
    expect(screen.getByText(".csv").tagName).toBe("CODE");
    expect(screen.queryByText(/\*\*/)).not.toBeInTheDocument();
  });
});
