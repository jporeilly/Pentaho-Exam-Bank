# How a Question Is Written

Every question in the bank follows one form, the same one the courses use: a
scenario, a question, the options, and an explanation.

## The scenario

One to three *statements* that set the scene: a real working situation, who
is involved and what they are dealing with. A scenario is never a question and
never ends in "?". It gives the question the context it needs without giving
away the answer, and never mentions the course, a lab or a workshop.

> A developer loads a supplier's delimited file into a transformation. The
> file has no header row.

## The question

Only the question: one direct question ending in "?". No statements in front
of it — they belong in the scenario — and no "(Choose one)": the course counts
the correct answers and adds that itself, as *(Choose one)* or *(Choose two)*.
A multi-select question says how many it wants in its own words: "Which two …?".

> Which setting makes the step read the first line as data?

## The options

The correct answer (or answers) and the distractors. Distractors are plausible
and wrong: a common misconception, a neighbouring feature, a partial truth.
They are about the same length as the correct answer, so length gives nothing
away. Never "All of the above" or "None of the above".

## The explanation

Shown after the exam. It says why each correct answer is right and each
distractor is wrong, naming each option by its text, never by a letter,
because options are shuffled.

## Formatting

Three kinds, and only these: **bold**, *italic* and `code`. Use code for
things the learner types or sees on screen - a file (`kettle.properties`),
a variable (`${INPUT_DIR}`), a step or a menu path - and bold or italic
sparingly, for the one word a question turns on (*not*, *first*, *only*).

They are stored as markers in the text, the way they are typed: `**bold**`,
`*italic*`, `` `code` ``. The editor's buttons and Ctrl+B / Ctrl+I write them
for you. Because they are plain text, they travel with the question:

- **The course** draws them in the exam once its Content Manager is a release
  later than 0.7.12; an older one shows the markers as typed.
- **Word, QTI and Moodle** exports carry them as real bold, italic and code.
- **CSV and JSON** keep the markers, so a round trip loses nothing.
- **Plain text** and the **printed exam paper** show the words without them.

An asterisk that is not formatting stays an asterisk: `[Sales] * [Quantity]`,
`$.orders[*]`, `industrial/*/sensor` and `*.ktr` are left alone, and
underscores never format. To show a literal `**` pair, put a backslash in
front of each asterisk (`\*`).

## When a question breaks the form

The editor checks the scenario and the question as you type, and shows a note
in amber when either breaks the form: a scenario that asks a question, a
question that opens with statements, two questions in one, or a "Choose …"
count. The notes are advice: they never stop a save. AI rewrite is told the
same form, and says when its proposal broke it. Publishing removes a
"Choose …" count from any question that still has one, so it can never reach a
learner twice.
