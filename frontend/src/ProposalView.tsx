/**
 * A proposed question as the author reviews it before taking it: the AI
 * rewrite in the editor, and every row of the bulk rewrite's review list.
 * One view for both, so a question rewritten on its own and one rewritten
 * with its exam are judged on the same screen.
 *
 * Until 1.14.0 the editor's proposal showed the scenario, question and
 * options but not the explanation - so an explanation rewritten into the
 * old "Correct: ... Incorrect: ..." form was only seen after "Use this".
 */
import type { Question } from "./api";
import { OptionList } from "./answers";
import { Formatted } from "./inlineFormat";

type Note = { field: string; message: string };

const FIELD_LABEL: Record<string, string> = {
  scenario: "Scenario",
  stem: "Question",
  options: "Answers",
  explanation: "Explanation",
};

/**
 * An explanation as a candidate reads it after the exam: paragraphs, bold,
 * on a card of its own. Shown whenever there is any text, not only when it
 * carries formatting, because paragraph breaks are invisible in a textarea's
 * wrapping and the card is where they show.
 */
export function ExplanationCard({ text, label }: { text: string; label?: string }) {
  if (!text.trim()) return null;
  return (
    <div className="explanation-card">
      {label && <div className="explanation-card__label">{label}</div>}
      <div className="explanation-card__body">
        <Formatted text={text} />
      </div>
    </div>
  );
}

export function ProposedQuestion({
  proposed,
  notes = [],
  problems = [],
}: {
  proposed: Question;
  notes?: Note[];
  problems?: Note[];
}) {
  const keys = proposed.question_type === "multi" ? proposed.keys : [proposed.key];
  return (
    <div className="proposal">
      {proposed.scenario && (
        <p className="muted proposal__scenario">
          <Formatted text={proposed.scenario} />
        </p>
      )}
      <p className="proposal__stem">
        <Formatted text={proposed.stem} />
      </p>
      <OptionList
        label="Proposed options"
        options={[
          ...keys.map((k) => ({ text: k, correct: true })),
          ...proposed.distractors.map((d) => ({ text: d, correct: false })),
        ]}
      />
      <ExplanationCard text={proposed.explanation} label="Explanation" />
      {notes.map((n) => (
        <div key={`${n.field}:${n.message}`} className="advice">
          {FIELD_LABEL[n.field] ? `${FIELD_LABEL[n.field]}: ` : ""}
          <Formatted text={n.message} />
        </div>
      ))}
      {problems.length > 0 && (
        <div className="banner proposal__problems">
          This rewrite could not be graded: {problems.map((p) => p.message).join("; ")}
        </div>
      )}
    </div>
  );
}
