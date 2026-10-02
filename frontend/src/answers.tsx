/**
 * How a correct answer and a distractor look, everywhere an option is shown.
 *
 * A correct answer is green with a tick; a distractor is rose with a cross.
 * Until 1.11.0 the two were drawn identically in the editor, and only
 * Generate's review coloured the key, with an inline style. One component
 * means one look.
 *
 * The tick and the cross are drawn by CSS (::before), not written into the
 * markup, so they never join a label's text or an option's accessible name:
 * "Correct answer" still reads as "Correct answer", and the option's words
 * are its name.
 */

export function AnswerMark({ kind }: { kind: "correct" | "wrong" }) {
  return <span className={`answer-mark ${kind}`} aria-hidden />;
}

export interface ShownOption {
  text: string;
  correct: boolean;
  /** A line under the option, such as the course text a decision rests on. */
  note?: string;
}

/** A read-only list of options, each marked correct or wrong. */
export function OptionList({ options, label }: { options: ShownOption[]; label?: string }) {
  return (
    <ul className="opt-list" aria-label={label}>
      {options.map((o, i) => (
        <li key={i} className={`opt ${o.correct ? "correct" : "wrong"}`}>
          <AnswerMark kind={o.correct ? "correct" : "wrong"} />
          <span>
            <span className="visually-hidden">{o.correct ? "Correct: " : "Wrong: "}</span>
            {o.text}
            {o.note && <span className="opt-quote">{o.note}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}
