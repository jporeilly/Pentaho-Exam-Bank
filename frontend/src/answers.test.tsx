/**
 * A correct answer and a distractor never look alike, and the marks that say
 * which is which stay out of the words a screen reader or a test reads.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AnswerMark, OptionList } from "./answers";

describe("OptionList", () => {
  const options = [
    { text: "Sort rows, then Unique rows", correct: true },
    { text: "Unique rows alone", correct: false, note: "“needs sorted input”" },
  ];

  it("marks each option correct or wrong, in its class and its spoken name", () => {
    render(<OptionList options={options} label="Options" />);
    const [right, wrong] = screen.getAllByRole("listitem");
    expect(right).toHaveClass("opt", "correct");
    expect(wrong).toHaveClass("opt", "wrong");
    // The visually-hidden prefix is what a screen reader hears.
    expect(right).toHaveTextContent("Correct: Sort rows, then Unique rows");
    expect(wrong).toHaveTextContent("Wrong: Unique rows alone");
  });

  it("shows a note under an option", () => {
    render(<OptionList options={options} />);
    expect(screen.getByText("“needs sorted input”")).toHaveClass("opt-quote");
  });

  it("is labelled when a label is given", () => {
    render(<OptionList options={options} label="Proposed answer key" />);
    expect(screen.getByRole("list", { name: "Proposed answer key" })).toBeInTheDocument();
  });
});

describe("AnswerMark", () => {
  it("draws its tick or cross in CSS, so it adds no text and is hidden from readers", () => {
    const { container } = render(
      <>
        <AnswerMark kind="correct" />
        <AnswerMark kind="wrong" />
      </>,
    );
    const marks = container.querySelectorAll(".answer-mark");
    expect(marks).toHaveLength(2);
    marks.forEach((m) => {
      expect(m).toHaveTextContent("");
      expect(m).toHaveAttribute("aria-hidden");
    });
    expect(marks[0]).toHaveClass("correct");
    expect(marks[1]).toHaveClass("wrong");
  });
});
