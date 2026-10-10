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

Shown after the exam. It says why the correct answer is right, and nothing
else: it teaches the idea the question turns on, and it does not go through
the wrong options or label them "Correct" and "Incorrect". A multi-select
question explains each of its correct answers.

- One to three short paragraphs. A blank line starts a new paragraph.
- The one to three key terms in **bold**: the feature, setting or idea the
  answer turns on. Bold phrases, never whole sentences.
- An answer is named by what it says, never by a letter, because the options
  are shuffled.
- Only when the question is about the order or routing of steps, a flow line
  as a paragraph of its own: PDI's step names joined by arrows,
  Table input → Filter rows → Table output. Most explanations have none. An
  AI proposal says so when its flow names something that is not a PDI step,
  or draws more than one. The printed exam paper prints the arrow as `->`.

> A **header row** is the first line of a delimited file, and the CSV file
> input step reads it as the column names by default.
>
> Turning **Header row present?** off makes the step read that first line as
> data, which is what a file without one needs.

The editor shows the explanation under its field the way candidates will see
it. An AI proposal (rewrite or explanation) says so when its explanation
still labels options or names one by its letter. The course shows the
paragraphs and the bold as written.

## The house style

Everything on this page is the house style: the template every question is
written to. The rules the AI is given are the same rules, word for word.
**The house style** panel shows them, on the Generate screen and on the
Bank's **AI rewrite all**, read live from the prompts the model gets, so the
panel and the model can never disagree. New questions are generated to it,
and **AI rewrite** (one question or the whole Bank) brings older questions to
it.

## Quotes, names and punctuation

One rule for each job quotation marks used to do (from 1.15.0):

| What | How | Not |
|---|---|---|
| A field, column, key, file, path, variable, expression or typed value | `region_code`, `kettle.properties`, `${INPUT_DIR}`, `Y` | 'region_code' |
| A PDI step, job entry or menu item | Its PDI name, plain: Stream lookup, Filter rows | 'Stream Lookup' |
| An ordinary word or a number | Plain: sales records, a price of 49.99 | 'sales' records, `49.99` |
| Words quoted exactly as written, such as an error message | Double quotes | Single quotes |

And:

- Straight quotes and apostrophes, never curly ones; no contractions
  (does not, cannot).
- American spelling (normalize, behavior), except in a product's own names
  (Row normaliser).
- The answers to one question share one form: all sentences ending in a
  period, or all short phrases without one. Formatting never singles out an
  answer: if the correct answer has `code`, the wrong ones use it too, or
  none does.
- A serial comma (fields, rows, and steps). Numbers one to nine in words,
  10 and above in digits, and digits for any value or anything with a unit
  (5 GB).

PDI's step names are its own, read from a PDI 11 install: sentence case,
"Stream lookup" not "Stream Lookup".

The AI is given these rules, and the app applies the mechanical ones to
whatever the AI proposes, before you see it: curly quotes straightened,
contractions written out, a Title Case step name put back to PDI's, quotes
taken off a step name, a quoted name or path put in code, a bare number taken
out of code, and code taken off a correct answer when no wrong answer has any.
What needs a reader - quotes left around a word that may be a key or an
ordinary word, an ordinary word put in code, a contraction such as "it's" -
appears as a note on the proposal.

## Formatting

Three kinds, and only these: **bold**, *italic* and `code`. Use code for an
exact name or value - a file (`kettle.properties`), a variable
(`${INPUT_DIR}`), a field or a path - as set out above. Bold is for an
explanation's key terms; italic, sparingly, for the one word a question
turns on (*not*, *first*, *only*).

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
