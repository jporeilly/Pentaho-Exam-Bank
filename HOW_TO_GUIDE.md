# Pentaho Exam Bank — How-To Guide

How to use the Pentaho Exam Bank to hold, write, review and publish the
certification exam questions for the Pentaho Content Manager's courses.

The usual path through the app:

1. **Courses** — adopt a course's exam into the bank.
2. **Bank** — edit questions, and move them through review.
3. **Report** — check each exam against the bar for its certification level.
4. **Publish** — write the approved questions back into the course, and push
   them to the courses repo so learners get them.

**Generate** and **Import** add questions from other places; **Exam paper**
prints a PDF exam; **Settings**, **Admin** and **AI & Docs** look after the app.

## Table of Contents

- [Getting Started](#getting-started)
- [How a Question Is Written](#how-a-question-is-written)
- [Courses: Adopting a Course's Exam](#courses-adopting-a-courses-exam)
- [Generating Questions from a Course](#generating-questions-from-a-course)
- [Importing Questions from a File](#importing-questions-from-a-file)
- [The Bank: Finding and Editing Questions](#the-bank-finding-and-editing-questions)
- [Saving a Question](#saving-a-question)
- [AI Rewrite and AI Check](#ai-rewrite-and-ai-check)
- [Review: Moving a Question Through Its Statuses](#review-moving-a-question-through-its-statuses)
- [The Report](#the-report)
- [Building a Printed Exam Paper](#building-a-printed-exam-paper)
- [Publishing to a Course](#publishing-to-a-course)
- [Settings](#settings)
- [Admin: Backups and Bulk Deletion](#admin-backups-and-bulk-deletion)
- [AI & Docs](#ai--docs)
- [Troubleshooting](#troubleshooting)

---

## Getting Started

### Opening the app

The Exam Bank is a Windows desktop app. Open it from its desktop shortcut, or
from the **Questions** button in the Pentaho Content Editor, which opens it on
the course you were editing: the Generate and Bank screens start on that course.

### The window

- **The side bar** holds the screens: Courses, Generate and Import (bringing
  questions in); Bank, Report, Exam paper and Publish (working with them);
  Settings, Admin and AI & Docs (the app itself). The Bank entry shows how many
  questions the bank holds.
- **The status bar** along the bottom reads *Exam Bank v1.6.0 · Content Manager
  v0.5.0*: this app's version, and the version of the Content Manager whose
  courses it reads. If the interface and the backend ever report different
  versions, the Exam Bank part turns red — restart the app.

### Where the database, backups and courses live

- **The bank** is one SQLite database in your user profile:
  `%APPDATA%\com.pentaho.exam-bank\db\exam_bank.db`. Settings shows the exact
  path.
- **Backups** sit beside it in `db\backups\`, one file per backup, named with
  the time and a label.
- **The courses** are read from the Content Manager's `courses/` folder, found
  at install time. Settings shows it and lets you change it.

---

## How a Question Is Written

Every question in the bank follows one form, the same one the courses use: a
scenario, a question, the options, and an explanation.

### The scenario

One to three *statements* that set the scene: a real working situation, who
is involved and what they are dealing with. A scenario is never a question and
never ends in "?". It gives the question the context it needs without giving
away the answer, and never mentions the course, a lab or a workshop.

> A developer loads a supplier's delimited file into a transformation. The
> file has no header row.

### The question

Only the question: one direct question ending in "?". No statements in front
of it — they belong in the scenario — and no "(Choose one)": the course counts
the correct answers and adds that itself, as *(Choose one)* or *(Choose two)*.
A multi-select question says how many it wants in its own words: "Which two …?".

> Which setting makes the step read the first line as data?

### The options

The correct answer (or answers) and the distractors. Distractors are plausible
and wrong: a common misconception, a neighbouring feature, a partial truth.
They are about the same length as the correct answer, so length gives nothing
away. Never "All of the above" or "None of the above".

### The explanation

Shown after the exam. It says why each correct answer is right and each
distractor is wrong, naming each option by its text, never by a letter,
because options are shuffled.

### When a question breaks the form

The editor checks the scenario and the question as you type, and shows a note
in amber when either breaks the form: a scenario that asks a question, a
question that opens with statements, two questions in one, or a "Choose …"
count. The notes are advice: they never stop a save. AI rewrite is told the
same form, and says when its proposal broke it. Publishing removes a
"Choose …" count from any question that still has one, so it can never reach a
learner twice.

---

## Courses: Adopting a Course's Exam

The **Courses** screen lists the Content Manager's courses, with the size of
each course's exam pool. **Contents** on a row shows the course's labs and the
sections a question could be generated from; a section marked *truncated* is
longer than the configured model can read in one go.

To bring a course's exam questions into the bank:

1. Press **Check courses for questions**. Nothing is written yet: you get a
   table with, for each course, how many questions are **New**, **Changed**
   (edited in the bank since they came in), already **In bank**, and
   **Refused**.
2. Read the **Notes** column. A refused id is one that two courses both use —
   the bank keys questions by id, so adopting both would overwrite one with the
   other. A question the bank cannot grade (no correct answer, a distractor
   identical to the answer) is listed rather than adopted.
3. Press **Adopt into the bank**. New questions arrive as drafts.

Questions you have edited in the bank are **not** replaced by the course's
wording unless you tick *Replace the N questions edited here with the course's
version*. Their review status is kept either way.

---

## Generating Questions from a Course

The **Generate** screen writes new questions with the configured AI model,
from a course's own material.

1. Choose the **Course**, and a **Lab** or *Whole course*. Getting-started
   labs are skipped in a whole-course run but can be chosen on their own.
2. Choose where to **File under** (a certification), how many **Questions**,
   and the **Difficulty**.
3. **Formats** sets the shape of the questions. With no rows, every question
   has one correct answer out of four. **Add a format** to add shapes — for
   example *Choose 2 of 5* — and tick **Mix formats** to deal them out at
   random. Each row shows how candidates will see it, for example
   *shown as "(Choose two)"*.
4. Tick the **Bloom's** levels to spread the questions across.
5. Optionally add extra instructions for the model, and press **Generate**.
   A whole course can take the better part of an hour; the run carries on if
   you leave the screen, and **Cancel** stops it.
6. When it finishes, review the questions. Everything starts ticked; untick
   what is wrong and press **Save N to the bank**. Nothing is saved until you
   do.

A question marked *not anchored to the course material* could not be matched
to anything in the course, so it may be about something the course does not
teach. Every generated question needs a human read before it is trusted: the
app cannot check that an answer is right.

---

## Importing Questions from a File

The **Import** screen reads CSV, Excel, QTI 2.1, Moodle XML, plain text, a
Content Manager `exam.json`, or this bank's own JSON export.

1. Choose the file. Nothing is saved yet: you see how many questions were
   **found**, how many are **gradeable**, how many **cannot be graded**, and
   how many are **already in the bank** (by wording, with the match shown).
2. Optionally set a **Certification** and a **Topic** for all of them.
3. Tick the questions to keep. **Select all gradeable** is the usual choice; a
   question that cannot be graded cannot be ticked, and a near-duplicate needs
   a deliberate tick.
4. Press **Import N of M**. Questions arrive as drafts.

A plain-text file carries no marked answers, so its correct answers are
guessed from their position. The preview says so; check them before relying
on them.

---

## The Bank: Finding and Editing Questions

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
- **Notes** (amber) are the form in [How a Question Is Written](#how-a-question-is-written):
  a scenario that asks a question, a question that opens with statements, two
  questions in one, or a "Choose …" count. They never stop a save.

Every edit is recorded field by field in the question's version history, with
the old and new value.

---

## Saving a Question

Press **Save**. When it is done, a green **✓ Saved at 10:42** appears beside the
button and stays until your next edit. If the save fails, the reason is shown
at the top of the editor instead and nothing is changed.

If the question was **Approved** when you saved it, the message adds *Still
approved: send it back for review if this change needs one.* Approval is a
judgment of the wording at the time; see
[Review](#review-moving-a-question-through-its-statuses) for sending it back.

---

## AI Rewrite and AI Check

Both need an AI model set up in [Settings](#settings). Neither writes anything
to the bank.

**AI rewrite** asks the model for a better version of the question. The model
is told the house form: the scenario is statements that set the scene, the
question is only the question. The proposal shows the new scenario, question
and options. If the model broke the form anyway — say, put a question in the
scenario — the proposal says so under it. Press **Use this** to copy the
proposal into the editor (still unsaved; press Save if you agree), or
**Discard**.

**AI check answers** asks the model whether the question can be answered
correctly as written — for example, whether a distractor is also true — and
proofreads it. Beside its opinion you see the bank's own checks: whether the
question can be graded, and whether it follows the form. It is a second
opinion, not a guarantee.

---

## Review: Moving a Question Through Its Statuses

| Status | Meaning |
| --- | --- |
| **Draft** | Newly adopted, generated or imported, or sent back for rework |
| **SME Review** | Waiting for a subject-matter expert |
| **Revised** | Reworked after review, going back for another look |
| **Approved** | Cleared for use in an exam |
| **Rejected** | Not usable as it stands |
| **Retired** | No longer in use, kept for the record |

The buttons at the bottom of the editor are the moves allowed from the
question's current status:

| From | Can move to |
| --- | --- |
| Draft | SME Review, Rejected |
| SME Review | Revised, Approved, Rejected |
| Revised | SME Review, Approved, Rejected |
| Approved | SME Review, Draft, Retired |
| Rejected | Draft |
| Retired | Draft |

The buttons say what they do: **Send for review**, **Mark revised**,
**Approve**, **Reject**, **Retire**, **Back to draft**. Save any edits first —
the buttons are disabled while there are unsaved changes. After a move, a
green **✓ Moved to SME Review** (or wherever it went) confirms it.

**Sending an approved question back.** If you change an approved question, use
**Send for review** or **Back to draft** so it is reviewed again before it is
published as approved. Its approval date is cleared; its review history still
records when it was approved and who sent it back.

Every move is recorded in the question's review history with the time and the
reviewer's name. Set your name once in **Settings → Who you are**.

---

## The Report

The **Report** screen breaks down one exam at a time. Choose the exam at the
top.

- **Tiles**: how many questions, the share at Apply or above and at Analyze or
  above, the share that opens with a scenario, the draw headroom (how much
  bigger the pool is than one attempt), and how many are approved.
- **Bloom classification**: how deep the questions go, Remember to Evaluate.
- **Certification bar**: whether the exam clears the bar for its level. Each
  bar is a floor on the share at Apply or above, at Analyze or above and at
  Evaluate, and a ceiling on Remember:

  | Level | Apply+ | Analyze+ | Evaluate | Remember at most |
  | --- | --- | --- | --- | --- |
  | 1 Practitioner | 50% | 15% | 1% | 30% |
  | 2 Specialty | 60% | 30% | 5% | 20% |
  | 3 Certified | 70% | 40% | 15% | 15% |

  A figure exactly on its line passes. A course with no level (a try-it lab)
  is not scored against a bar.
- **By workshop**: the same breakdown per module, in course order.
- **Review pipeline**: how many questions are at each status.
- **Findings**: what the numbers say to do, by the same rules for every exam —
  for example questions without a scenario, or a pool too small for its draw.
- **Every question, as classified**: the full list, filterable by Bloom level.

---

## Building a Printed Exam Paper

The **Exam paper** screen builds a printable PDF exam.

1. Choose the certifications to **Draw from** (Ctrl-click for more than one)
   and which questions to use — **Approved**, **In review**, **Drafts**.
2. Set the number of **Questions**, the **Difficulty**, and the **Topic mix** —
   the share of the paper each topic gets. The shares must total 100%.
3. Press **Check the mix**. If the bank cannot fill the mix you asked for, you
   see, topic by topic, what you wanted, what is available and what the paper
   would hold, before anything is built.
4. Give it an **Exam title** and, optionally, an **Institution** for the cover.
   A **Seed** gives the same paper again; leave it blank for a new paper each
   time. Tick **Answer key** to add one.
5. Press **Build the paper**.

A question with several correct answers is printed with its count, for example
*(Choose 2)*.

---

## Publishing to a Course

The **Publish** screen writes the bank's questions into a course's
`exam.json`, and can push them on to the courses repo that learners' apps
sync from.

1. Choose the **Course** and the **certification** its questions come from.
2. Choose which questions: **Approved only** (the default), **In review**,
   **Drafts** or **Every status**. Publishing replaces the course's whole
   question pool with these, so with *Approved only* any question not yet
   approved drops out of the course. Publishing is refused if that would leave
   fewer questions than one attempt draws.
3. Press **Check what would change**. You see exactly which questions would be
   added, reworded or removed, and that the exam's own settings (pass mark,
   draw size, results webhook) are untouched.
4. Leave **Also push to the courses repo** ticked to publish to learners, and
   press **Publish and push** (or **Publish to the course** without the push).

With the push, one press writes the exam, moves the course's version on
(0.1.11 → 0.1.12), adds a line to the Content Manager's CHANGELOG naming what
changed, commits those three files and pushes, then pushes the exam to the
courses repo. Installed Content Managers pick it up at their next launch —
no installer rebuild. Only the exam is pushed; the rest of the course stays as
it was published.

What is written is the question only: any "Choose …" count left in a stem is
removed, because the Content Manager adds its own.

The push is refused, before anything is written, when it cannot succeed: no
git on the machine, the Content Manager repo behind its remote, uncommitted
changes in the files it would commit, or a course that was never published.
It stops before touching anything if the push would add a secret-like value to
the public repo.

---

## Settings

- **Who you are** — your name, stamped on every review action so the history
  says who approved what.
- **AI** — the provider and model used by Generate, AI rewrite and AI check.
  For Ollama, its URL and context window; for a hosted provider, whether its
  API key is present. Keys are read from the environment (`ANTHROPIC_API_KEY`,
  `OPENAI_API_KEY`) and never stored or shown.
- **Where things are** — the Content Manager courses folder, the export folder,
  and the database and config file paths.
- **Defaults** — questions per page, and the default difficulty and Bloom level.
- **Thresholds** — how alike two questions must be before import calls them
  duplicates, and how closely an imported answer must match its source text
  to count as validated. Both run from 0 to 1; higher is stricter.

A setting governed by an environment variable is shown but cannot be edited
here, and names the variable. Press **Save**; *Saved* confirms it.

---

## Admin: Backups and Bulk Deletion

**Backups.** Give the backup a label (what it is for) and press **Back up
now**. The list shows every backup with when it was taken and its size.
**Restore** on a row puts that backup back; the bank it replaces is saved as a
backup of its own first, and the message names it.

**Deleting in bulk.** Set the filters (certification, status, topic,
difficulty), press **Count what would go**, and read the count, the breakdown
and the sample stems before pressing delete — the button carries the count.
This cannot be undone without a backup.

---

## AI & Docs

Ask a question about the app, search its documentation, or read it. Answers
come only from this guide and the README: if they do not cover a question, you
are told so and the model is not asked. The sections an answer was built from
are shown under it, so you can check it.

---

## Troubleshooting

**"Saved" never appeared.** Fixed in 1.6.0: the message now stays until your
next edit. Check the status bar says 1.6.0 or later.

**An approved question cannot be sent back.** Fixed in 1.6.0: Approved can
move to SME Review, Draft or Retired.

**The Exam Bank version in the status bar is red.** The interface and the
backend are different builds. Close the app completely and open it again; if it
persists, reinstall.

**"Two Content Manager checkouts disagree."** The app was opened for a course
from one Content Manager folder while Settings points at another. Fix the
courses folder in Settings.

**"No AI model is configured."** Choose a provider and model in Settings.

**"The model did not return a usable question."** Try again, or a larger model.

**A sync shows questions as Changed.** They were edited in the bank after they
came from the course. They are left alone unless you tick *Replace*.

**Publish is refused.** The plan says why: too few questions for the draw with
the chosen statuses, or, for a push, one of the reasons under
[Publishing to a Course](#publishing-to-a-course).
