/**
 * The rules that decide whether a question is gradeable.
 *
 * `problemsWith` is pure and tested directly, because these are claims
 * about what a valid item IS - not about a form. A rule reachable only by
 * driving the UI is a rule nobody checks when the UI changes.
 *
 * Each rule has a pair: it fires on the bad case AND stays silent on the
 * good one. Without the second half, deleting the rule still passes.
 */
import { describe, expect, it } from "vitest";
import { problemsWith } from "./QuestionEditor";
import type { Question } from "./api";

function q(over: Partial<Question> = {}): Question {
  return {
    id: "q1",
    scenario: "",
    stem: "Which step reads a CSV?",
    question_type: "single",
    key: "Text file input",
    keys: [],
    key_source_text: "",
    distractors: ["Table input", "Row generator", "Dummy"],
    option_order: [],
    explanation: "",
    topic: "Reading files",
    tags: [],
    difficulty: "Medium",
    bloom_level: "Understand",
    certification_id: "c1",
    pool_order: -1,
    status: "draft",
    assigned_sme: "",
    review_history: [],
    version_history: [],
    updated_at: "",
    ...over,
  };
}

const fields = (x: Question) => problemsWith(x).map((p) => p.field);

describe("a question that is fine", () => {
  it("has no problems", () => {
    expect(problemsWith(q())).toEqual([]);
  });

  it("is still fine as a select-all with two keys", () => {
    expect(problemsWith(q({ question_type: "multi", keys: ["A", "B"] }))).toEqual([]);
  });
});

describe("the stem", () => {
  it("cannot be empty", () => {
    expect(fields(q({ stem: "" }))).toContain("stem");
  });

  it("cannot be only whitespace", () => {
    expect(fields(q({ stem: "   " }))).toContain("stem");
  });
});

describe("what is marked correct", () => {
  it("a single-select question needs a key", () => {
    expect(fields(q({ key: "" }))).toContain("keys");
  });

  it("a select-all question needs keys", () => {
    expect(fields(q({ question_type: "multi", keys: [] }))).toContain("keys");
  });

  it("a select-all question with ONE key is flagged", () => {
    // It grades identically to single-select, so the type is a lie about
    // what the candidate is being asked to do.
    const problems = problemsWith(q({ question_type: "multi", keys: ["Only one"] }));
    expect(problems.some((p) => p.field === "keys")).toBe(true);
  });

  it("does not flag a single-select question for having one key", () => {
    expect(problemsWith(q())).toEqual([]);
  });
});

describe("the distractors", () => {
  it("cannot be empty strings", () => {
    expect(fields(q({ distractors: ["Table input", ""] }))).toContain("distractors");
  });

  it("cannot be absent entirely", () => {
    expect(fields(q({ distractors: [] }))).toContain("distractors");
  });

  it("cannot repeat the correct answer", () => {
    // The defect that survives review most often: it reads fine in a list
    // and is impossible to answer.
    const problems = problemsWith(q({ distractors: ["Table input", "Text file input"] }));
    expect(problems.some((p) => p.message.includes("both correct and a distractor"))).toBe(true);
  });

  it("matches the key case-insensitively", () => {
    const problems = problemsWith(q({ distractors: ["Table input", "TEXT FILE INPUT"] }));
    expect(problems.some((p) => p.message.includes("both correct and a distractor"))).toBe(true);
  });

  it("catches a key clash in a select-all question too", () => {
    const problems = problemsWith(
      q({ question_type: "multi", keys: ["Alpha", "Beta"], distractors: ["Gamma", "beta"] }),
    );
    expect(problems.some((p) => p.message.includes("both correct and a distractor"))).toBe(true);
  });

  it("cannot repeat each other", () => {
    const problems = problemsWith(q({ distractors: ["Table input", "table input", "Dummy"] }));
    expect(problems.some((p) => p.message.includes("appears 2 times"))).toBe(true);
  });

  it("does not flag distinct distractors", () => {
    expect(problemsWith(q({ distractors: ["One", "Two", "Three"] }))).toEqual([]);
  });
});

describe("the type switch", () => {
  it("reads keys[] for multi and ignores key", () => {
    // A question switched to multi without keys is broken even though
    // `key` still holds the old single answer.
    const problems = problemsWith(q({ question_type: "multi", key: "Left over", keys: [] }));
    expect(problems.some((p) => p.field === "keys")).toBe(true);
  });

  it("reads key for single and ignores keys[]", () => {
    expect(problemsWith(q({ question_type: "single", keys: ["stale", "values"] }))).toEqual([]);
  });
});
