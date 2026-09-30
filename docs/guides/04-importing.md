# Importing Questions from a File

The **Import** screen reads CSV, Excel, QTI 2.1, Moodle XML, plain text, a
Content Manager `exam.json`, or this bank's own JSON export.

1. Choose the file. Nothing is saved yet: you see how many questions were
   **found**, how many are **gradeable**, how many **cannot be graded**, and
   how many are **already in the bank** (by wording, with the match shown).
2. Optionally set a **Certification** and a **Topic** for all of them.
3. Tick the questions to keep. **Select all gradeable** is the usual choice; a
   question that cannot be graded cannot be ticked, and a near-duplicate needs
   a deliberate tick.
4. Optionally press **Check answers against docs.pentaho.com** (see below).
5. Press **Import N of M**. Questions arrive as drafts.

## Checking answers against docs.pentaho.com

A file from somewhere else arrives with answers nobody here has checked.
**Check answers against docs.pentaho.com** looks each question up in Pentaho's
documentation, through the same connection AI Chat uses, and adds a column to
the preview:

- **Backed** — the docs carry every correct answer: all of it word for word,
  or enough of its meaningful words (not "the", "of", "a") to reach the **Docs
  check threshold** in [Settings](../admin/01-settings.md). The pages it
  found are linked.
- **Not found** — the docs may say it differently, or not at all. A prompt to
  look, not a verdict.
- **Not checked** — the search could not be made; the reason is shown.

It changes nothing and imports nothing; you still choose what to import. It
needs the Pentaho docs connection switched on in Settings.

Imported into a course's certification, a question takes a place in the
course order and an id in the course's format, `<course>-m<module>-q<question>`,
as a generated question does (see
[Generating questions](03-generating.md#filed-like-the-courses-own-questions)).
An id that already fits the course and the question's module is kept: it is
how the course and the bank recognise the same question. Any other id the file
carried (one from another course, or in an older style such as `q-preview`)
is replaced with the next number in the module.

A plain-text file carries no marked answers, so its correct answers are
guessed from their position: the first option is taken. The preview says so,
and the editor keeps saying so at the top of each such question until the
answer is checked. **AI answer key** proposes the answer from the course's
pages; see [AI rewrite, check, explanation and answer key](../writing/02-ai-rewrite-and-check.md).
