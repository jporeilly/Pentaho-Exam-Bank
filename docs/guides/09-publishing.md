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

## Who marks the exam: the app or the results service

The courses repository is public, so an exam whose `exam.json` carries its
answers hands them to anyone who opens it. **Marked by** on this screen
chooses where the answers live:

- **The app** (today's way): the answers and explanations are in
  `exam.json`, and the Content Manager marks the attempt on the learner's
  machine.
- **The results service**: `exam.json` is published *without* the answers
  or explanations. The results service (the exam's Apps Script) holds them,
  marks each attempt and sends back the score. Accreditation candidates
  (levels 1 and 2) still see the answers and explanations after submitting;
  certification candidates (level 3) see their score, pass or fail and
  per-module scores only.

Every server-graded publish uploads the answers to the results service
*first*; if that fails, nothing is written. **Upload keys only** stores
them without publishing anything.

To switch a course over, in this order:

1. Make sure the results Apps Script has been redeployed with an
   `ADMIN_SECRET` (the Content Manager's `docs/EXAM-RESULTS-SETUP.md`,
   "Server grading"), and set the same value in the
   `PEB_RESULTS_ADMIN_SECRET` environment variable on this machine
   (for example `setx PEB_RESULTS_ADMIN_SECRET "<value>"`), then restart
   the Exam Bank. Like the AI provider keys, the Exam Bank never stores it.
2. **Upload keys only** for the course.
3. Make sure every machine that sits the exam has a Content Manager with
   server grading. An older app cannot mark an exam that has no answers in it.
4. Choose **Marked by: The results service**, check, and publish.

Once a course is server-graded, syncing from the courses leaves it alone:
its file has no answers to bring back, and the bank is where they live.
