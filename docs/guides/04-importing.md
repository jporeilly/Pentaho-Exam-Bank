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
4. Press **Import N of M**. Questions arrive as drafts.

Imported into a course's certification, a question takes a place in the
course order. If the file gave it no id, it also gets one in the course's
scheme, as a generated question does (see
[Generating questions](03-generating.md#filed-like-the-courses-own-questions));
an id the file carried is kept.

A plain-text file carries no marked answers, so its correct answers are
guessed from their position. The preview says so; check them before relying
on them.
