# Generating Questions from a Course

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

## Filed like the course's own questions

Saved under a course's certification, each question is filed the way the
course files its own:

- **Its id follows the course's scheme** — the next number in its module's
  family where the course numbers them (`m3-q14`, `install-ai-q20`), or the
  course's prefix and the question's key words where it names them
  (`q-metadata-injection`). Never an id another question, or another course's
  exam, already uses.
- **Its topic is the course's module** — the heading in the course's contents
  its lab sits under (*See It Scale*), and the lab (*One Pipeline, Many
  Files*) becomes its citation, which the course shows with the results.
- **It takes a place in the course order**, straight after the last question
  of its module, so the Bank's **Order** column, *Course order* and the
  published exam all have it where it belongs. A slot a deleted question left
  is filled; otherwise the questions after it move up one, as far as the next
  free slot.

A question marked *not anchored to the course material* could not be matched
to anything in the course, so it may be about something the course does not
teach. Every generated question needs a human read before it is trusted: the
app cannot check that an answer is right.
