/**
 * The TypeScript half of the gradeability contract.
 *
 * Every case comes from `tests/fixtures/question_problems.json` — the same
 * file `tests/test_validation.py` reads. This asserts TypeScript produces
 * exactly those messages, in that order; the Python suite asserts the same of
 * `exam_bank/core/validation.py`. The rules exist in both languages because
 * neither copy can do the other's job — the browser gives feedback while an
 * author types, the server validates a file of four hundred rows — and this
 * fixture is what stops them drifting apart.
 *
 * There is deliberately no case here that the fixture does not contain.
 */
import { describe, expect, it } from "vitest";

import fixture from "../../tests/fixtures/question_problems.json";
import { problemsWith } from "./QuestionEditor";
import type { Problem, Question } from "./api";

interface Case {
  name: string;
  question: Partial<Question>;
  problems: Problem[];
}

// Imported rather than read off disk: no node types are configured here, and
// a path resolved at run time can silently miss and leave every case passing
// by vacuum. A bad path is a build error instead.
const cases = fixture.cases as Case[];

/** The fields the fixture sets, over a question that is otherwise empty. */
function question(over: Partial<Question>): Question {
  return {
    id: "q",
    scenario: "",
    stem: "",
    question_type: "single",
    key: "",
    keys: [],
    distractors: [],
    explanation: "",
    topic: "",
    tags: [],
    difficulty: "Medium",
    bloom_level: "Apply",
    status: "draft",
    ...over,
  } as Question;
}

describe("the shared gradeability fixture", () => {
  it("was found and is not empty", () => {
    // A path that silently resolves to nothing would make every case below
    // pass by vacuum.
    expect(cases.length).toBeGreaterThan(10);
  });

  it.each(cases.map((c) => [c.name, c] as const))("%s", (_name, c) => {
    expect(problemsWith(question(c.question))).toEqual(c.problems);
  });
});
