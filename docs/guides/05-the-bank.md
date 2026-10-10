# The Bank: Finding and Editing Questions

The **Bank** screen lists the questions, 25 to a page by default.

- Pick a **certification** above the table to see one course's questions.
- The row under the column headings **filters each column**: type part of an
  **ID** (`m4`, `ba-m4-q9`), **search** the text (the scenario, the question,
  every answer and the explanation), or pick a **topic**, **difficulty**,
  **Bloom level** or **status**. Filters combine. A topic is matched exactly,
  so *Concepts* does not also bring in *Key Concepts*. **Clear filters**
  appears while any is set, and the filter row stays when nothing matches, so
  you can always undo what emptied the table.
- **Course order** sorts a course's questions in the order its exam was
  written, lab by lab; **Recently updated** puts the latest edits first.
- **Export** downloads what the filters currently show, in the format chosen
  beside it: CSV, JSON, QTI 2.1, Moodle XML, plain text or Word. It starts on
  the default export format set in [Settings](../admin/01-settings.md).

The list draws each question's formatting (**bold**, *italic*, `code`), as
the course will.

Click a row to open the editor. It holds the scenario, the question, the type
(one correct answer, or several), the correct answer(s), the distractors, the
explanation, the topic, the difficulty and the Bloom level.

The correct answer is a **green** field marked ✓ and each distractor a **rose**
field marked ✗, so the two never look alike. The same colours mark the options
wherever they are shown: Generate's review, the AI's proposed answer key and
rewrite, and Import's preview.

**Formatting.** The **B**, *I* and **`</>`** buttons above the fields make the
selected words bold, italic or code, in whichever text field you are in (the
scenario, the question, an answer or the explanation); **Ctrl+B** and
**Ctrl+I** do the same. Pressing one again on the same words takes it off. A
field that carries formatting shows a preview under it. See
[Formatting](../writing/01-how-a-question-is-written.md#formatting) for what
the markers are and where they show.

Two kinds of message appear under the fields:

- **Problems** (red) stop a save, because the question could not be graded:
  nothing marked correct, an empty option, a distractor that repeats the
  correct answer, a select-several question with only one correct answer.
- **Notes** (amber) are the form in [How a Question Is Written](../writing/01-how-a-question-is-written.md):
  a scenario that asks a question, a question that opens with statements, two
  questions in one, or a "Choose …" count. They never stop a save.

Every edit is recorded field by field in the question's version history, with
the old and new value.

## Rewriting every question at once

**AI rewrite all (N)**, above the table, runs the editor's
[AI rewrite](../writing/02-ai-rewrite-and-check.md) on every question the
filters show - pick a certification, a topic or an ID first to rewrite fewer.
Each question is proofread, and its explanation rewritten to the
[house style](../writing/01-how-a-question-is-written.md#the-house-style):
why the correct answer is right, in paragraphs, with the key terms in bold.

1. Press **AI rewrite all**. A card says how many questions it will rewrite
   and shows the house style; press **Rewrite N questions** to start, or
   **Cancel**. Up to 1,000 at a time.
2. The questions are rewritten one model call at a time (about 15 seconds
   each with gemma4:12b), and each appears in a review list as it finishes.
   You can review while it runs; **Stop** ends the run, keeping what is done.
3. Each proposal shows the new question and its explanation, and **Changed:**
   names what moved - mostly *Explanation*. A *Scenario*, *Question* or
   *Answers* there is where to look first, because a reworded question can
   ask something different. **Show original** puts the old one beside it.
4. Press **Accept** on one, **Skip** to pass it over, or **Accept all ready**
   to take every proposal with no notes. A proposal with notes - an
   explanation that still labels options "Incorrect", say - is left for you.

**Nothing is saved until you accept.** Accepting is the editor's own save:
each changed field goes into the question's version history, under the editor
*AI rewrite (bulk)*. A question edited since the rewrite started is not
overwritten - it is skipped, and the list says why. Questions the model
could not rewrite are marked *Failed*; those it left as they were,
*Unchanged*.

The model can drop a caveat or reword a scenario more than it should, so read
each proposal before accepting it.

## Changing a question's module

A course question's id names its module (`di-m3-q7` is module 3), so changing
its **topic** to another module gives it that module's next number
(`di-m5-q13`). The saved message says so, the Bank row follows it, and the
history records the old and new id. When the course is next published, its
exam shows the old id removed and the new one added.


## Saving a Question

Press **Save**. When it is done, a green **✓ Saved at 10:42** appears beside the
button and stays until your next edit. If the save fails, the reason is shown
at the top of the editor instead and nothing is changed.

If the question was **Approved** when you saved it, the message adds *Still
approved: send it back for review if this change needs one.* Approval is a
judgment of the wording at the time; see
[Review](06-review.md) for sending it back.
