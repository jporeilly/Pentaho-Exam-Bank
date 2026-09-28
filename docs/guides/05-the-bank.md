# The Bank: Finding and Editing Questions

The **Bank** screen lists the questions, 25 to a page by default.

- **Search** matches stems, scenarios and answers.
- Filter by **certification** and **status**.
- **Course order** sorts a course's questions in the order its exam was
  written, lab by lab; **Recently updated** puts the latest edits first.
- **Export CSV** downloads what the filters currently show.

Click a row to open the editor. It holds the scenario, the question, the type
(one correct answer, or several), the correct answer(s), the distractors, the
explanation, the topic, the difficulty and the Bloom level.

Two kinds of message appear under the fields:

- **Problems** (red) stop a save, because the question could not be graded:
  nothing marked correct, an empty option, a distractor that repeats the
  correct answer, a select-several question with only one correct answer.
- **Notes** (amber) are the form in [How a Question Is Written](../writing/01-how-a-question-is-written.md):
  a scenario that asks a question, a question that opens with statements, two
  questions in one, or a "Choose …" count. They never stop a save.

Every edit is recorded field by field in the question's version history, with
the old and new value.


## Saving a Question

Press **Save**. When it is done, a green **✓ Saved at 10:42** appears beside the
button and stays until your next edit. If the save fails, the reason is shown
at the top of the editor instead and nothing is changed.

If the question was **Approved** when you saved it, the message adds *Still
approved: send it back for review if this change needs one.* Approval is a
judgment of the wording at the time; see
[Review](06-review.md) for sending it back.
