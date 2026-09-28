# Publishing to a Course

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
