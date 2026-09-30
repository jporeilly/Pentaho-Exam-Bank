# Pentaho Exam Bank

Holds the certification exam questions for the Pentaho Content Manager's
courses in a reviewable bank: adopts a course's exam, lets you generate,
review and edit questions, reports each exam against the bar for its
certification level, and publishes the approved questions back into the
course — and on to the courses repo that learners' apps sync from.

An **authoring tool for the author's machine.** It is never shipped to a
learner VM: the questions it produces are, the app is not.

It is a Windows desktop app — a Tauri shell over a FastAPI backend and a React
interface, with its own Python — installed per machine. For how to use it, see
[`HOW_TO_GUIDE.md`](HOW_TO_GUIDE.md) and the pages under [`docs/`](docs/), which
the app shows under **System → Documentation** and **AI Chat** answers from.
For installing it, see [`INSTALL.md`](INSTALL.md).

## What it is for

A course's exam lives in its `exam.json` inside the Content Manager. Before
this app nothing owned the questions in it — the Content Editor deliberately
edits only the delivery and grading settings — so a pool, once written, could
not practically be changed.

This app is the other half. It **adopts** a course's existing questions, lets
you work on them, and hands them back untouched in every respect you did not
mean to change.

| Owner | Keys in a course's `exam.json` |
| ----- | ------------------------------ |
| **Content Editor** | `title`, `description`, `passMark`, `questionsPerAttempt`, `shuffle`, `webhookUrl`, `webhookSecret`, `intake` |
| **Exam Bank** | `questions`, and the numerals inside `description` |

Two writers, one file, no overlapping keys.

## Where questions come from

| Source | How |
| ------ | --- |
| **An existing course exam** | Courses → *Check courses for questions* → *Adopt into the bank*. Ids, order and citations are kept. |
| **A Content Manager course** | Generate: a course's lab guides, a whole course or one lab, written into questions by the configured AI model. |
| **A file** | Import: CSV, Excel, QTI 2.1, Moodle XML, plain text, a course `exam.json`, or this bank's JSON export. |

A generated question is anchored to the course: the model quotes the passage
showing its topic is taught there (`key_source_text`). That checks the
question is on the syllabus, not that its answer is right — every question
needs a human read before it is approved.

## What it does

- **Adopt** a course's exam, and re-sync it later without overwriting edits
  made in the bank unless you ask.
- **Generate** scenario-based questions with control over single- and
  multi-select shapes, Bloom's levels and difficulty, and review them before
  anything is saved.
- **Edit and review** — a lifecycle of `draft → sme_review → revised →
  approved`, with `rejected` and `retired` beside it. An approved question can
  be sent back to review or to draft when it changes. Every transition is
  logged with who, when and why, and every field edit with its old and new
  value.
- **Guard the form** — the editor notes a scenario that asks a question, a
  question that opens with statements, and a stray "Choose …" count, as you
  type. AI rewrite is told the same form, and says when it broke it.
- **Report** each exam against its certification bar: Bloom depth, scenario
  coverage, draw headroom, the review pipeline, and findings to act on.
- **Publish** the approved questions into a course's `exam.json` as a merge,
  and push them to the courses repo with the course version bumped and the
  change logged.
- **Print** a topic-weighted PDF exam paper, and **export** to QTI 2.1, Moodle
  XML, DOCX, CSV, JSON and text.
- **Back up and restore** the bank, and delete in bulk with a count first.

## Screens

| Screen | Contents |
| ------ | -------- |
| **Courses** | The Content Manager's courses and their pools; adopt their exams into the bank |
| **Generate** | Write questions from a course with the AI model, then choose which to keep |
| **Import** | Bring questions in from a file, with a gradeability and duplicate check first |
| **AI Chat** | Ask about the app or about Pentaho's products; answers come from this app's docs and docs.pentaho.com, with their sources |
| **Bank** | Search and filter the questions; edit, save, AI rewrite and check, move through review |
| **Report** | One exam at a time against its certification bar |
| **Exam paper** | A printable, topic-weighted PDF exam |
| **Publish** | Write the questions into a course, and push them to the courses repo |
| **Settings** | Your name, the AI provider and model, the Pentaho docs connection, folders, defaults, thresholds |
| **Admin** | Backups and restore; bulk deletion |
| **Documentation** | This guide, page by page: sections, search, and a table of contents per page |

## Question model

- **Scenario** — one to three statements that set the scene. Never a question.
- **Stem** — only the question, ending in "?". No statements before it and no
  "(Choose …)" count: the course adds its own from the number of correct
  answers, and publishing removes any that is left in a stem.
- **Key(s)** — the correct answer or answers: true, and about the concept.
- **Distractors** — plausible wrong answers of similar length to the key; never
  "All of the above".
- **Explanation** — addresses every choice by its text rather than its letter,
  because choices are shuffled.
- **`key_source_text`** — for a generated question, the passage showing its
  topic is taught. Internal; never shown to a candidate.
- **Metadata** — topic, difficulty, Bloom's level, certification, status, tags,
  provenance, and `pool_order` when the question came from a course pool.

## Round-tripping a course

A course pool carries three things that are easy to destroy and hard to notice:

- **Question ids are durable external keys.** The Content Manager puts them in
  the results payload it posts to the webhook, and keys an in-progress attempt
  on the ids it dealt. Every course's ids read the same way,
  `<course>-m<module>-q<question>` (`di-m3-q7`, `2hr-m4-q3`), which the Content
  Manager's `verify-course` enforces; the bank files every question it adds to
  a course into that format and keeps an id that already fits. Renaming one
  orphans its recorded results, so it happens only when the id no longer
  says where the question is filed (see
  [Generating questions](docs/guides/03-generating.md#filed-like-the-courses-own-questions)).
  The one-off move to this format on 2026-09-30 is mapped old -> new in the
  Content Manager's `docs/question-id-map.csv`.
- **The `source` citation is richer than the module name** — "Lab 1 — Your
  First Win" against "See It Work".
- **Order decides what gets asked** in a pool that draws N questions with
  shuffle off.

All three survive adoption and publishing, covered by
`tests/test_pcm_roundtrip.py`. Publishing merges into the course's existing
file, so the Content Editor's keys — `intake` included — are left as they are.
The one thing a round trip changes on purpose is a "(Choose …)" count in a
prompt, which is dropped.

## Export formats

| Format | Use |
| ------ | --- |
| **PCM `exam.json`** | A Content Manager course exam, single- and multi-select |
| **QTI 2.1** | Canvas, Blackboard and other standards-compliant LMSs |
| **Moodle XML** | Moodle |
| **PDF** | Printed exam papers with cover page, topic sections and answer key |
| **DOCX** | Formatted Word document with colour-coded answers |
| **CSV / JSON** | Full round-trip — every field preserved and restorable |
| **Text** | Printable study guide with shuffled choices |

## What it connects to

| Thing | For | Without it |
| ----- | --- | ---------- |
| **Content Manager** courses folder | adopting, generating from and publishing to courses | no course sources or publishing; the bank, import and export still work |
| **An AI model** — Ollama (local, free), or a hosted provider with its API key | Generate, AI rewrite, AI check, AI Chat | no AI; everything else still works |
| **docs.pentaho.com** — its GitBook MCP server | AI Chat's answers about Pentaho's products | AI Chat answers from this app's docs only; Settings turns it off |
| **git** and the courses repo | *Publish and push* | publishing still writes the course; the push is offered only when it can succeed |

The installer finds the Content Manager's courses at install time; Settings
shows the folder and can change it. **No resolved course slug is ever cached**
— a stored slug that quietly stopped resolving is how this app's original
certifications died when the courses were renamed under them.

## Layout

```
Pentaho-Exam-Bank/
├── install.bat, run.bat, run-api.bat   # Run from a checkout (see INSTALL.md)
│
├── exam_bank/                   # The package (the repo root is the source root)
│   ├── __init__.py              #   __version__ — the source of truth
│   ├── core/                    #   Business logic, no UI
│   │   ├── bank.py              #     SQLite store, Question/Certification, the lifecycle
│   │   ├── course_sync.py       #     adopting and re-syncing course exams
│   │   ├── publisher.py, distribution.py  # publish into a course; push to the courses repo
│   │   ├── report.py            #     the Report's arithmetic and the certification bars
│   │   ├── stem_text.py         #     the question form: counts, scenarios, statements
│   │   ├── question_generation.py, generation_prompts.py, question_refinement.py
│   │   ├── question_importer.py #     CSV/JSON/Excel/QTI/Moodle/text/exam.json import
│   │   ├── exporter.py          #     every output format
│   │   ├── exam_builder.py      #     topic-weighted PDF exam papers
│   │   └── pcm_reader.py        #     reads a course's guide.md as sections
│   ├── api/                     #   FastAPI over core, and the app's only surface
│   └── utils/config.py          #   settings, and where state lives
│
├── frontend/                    # React + Vite; built into dist/, served by the API
├── desktop/                     # The Tauri shell and the Windows installer build
├── icons/                       # The app icon; see "The icon" below
├── scripts/                     # bump.py (versions), migrate_pcm_exams.py, changelog.py
└── tests/                       # pytest; the frontend's tests live beside its sources
```

The repo root is the source root, so `exam_bank` imports as a package from
there. **Do not add an `__init__.py` at the repo root** — that is what used to
make `C:\Projects` itself a source root, and it made the folder name
load-bearing.

## The icon

The suite shares one mark: a black tile with a white capital P, no red and
no swirl. What separates the taskbar pins at 24 px is the **badge** — the
Content Manager wears a mortarboard, the Content Editor a pencil, and this
app a marked exam paper in violet (`#7C3AED`) — a page with a rule and a
tick punched out of it, which says "exam" where a plain tickbox said only
"done".

`icons/icon.ico` is a **committed artifact**. Nothing here draws it: the one
drawing lives in the Content Manager's `scripts/make-icons.py`, and copying
~380 lines of it here would make a second drawing of a brand that has
already moved once. The two would diverge on the next move.

**To regenerate** — only when the brand moves, from a machine with the
Content Manager checked out:

```bat
venv\Scripts\python.exe <PCM>\scripts\make-icons.py ^
    --installer-ico icons\icon.ico --badge exam --badge-color "#7C3AED"
```

Then rescale the PNGs **down** from the .ico's largest frame — never up,
which is what a blurry taskbar icon is made of:

```bat
venv\Scripts\python.exe -c "from PIL import Image; im=Image.open(r'icons\icon.ico'); im.size=max(im.ico.sizes()); m=im.convert('RGBA'); [m.resize((s,s), Image.LANCZOS).save(p) for p,s in (('icons/icon-256.png',256),('icons/icon-128.png',128),('icons/icon-32.png',32),('frontend/public/icon.png',256))]"
```

`frontend/public/favicon.ico` is the browser tab's copy, and Vite serves
`public/` at the site root — `index.html` names both rather than leaving the
browser to guess, because the guess does not survive a non-root base path.

### The installer wizard

The NSIS wizard has its own two bitmaps, `desktop/src-tauri/icons/nsis-header.bmp`
(150x57) and `nsis-sidebar.bmp` (164x314), named from `tauri.conf.json`. They
are committed artifacts for the same reason the icon is, and come from the
same generator, so the wizard cannot drift away from the mark:

```bat
venv\Scripts\python.exe <PCM>\scripts\make-icons.py --nsis-only ^
    --out-dir desktop\src-tauri\icons ^
    --title "Exam Bank" --subtitle "Certification Questions" ^
    --badge exam --badge-color "#7C3AED" --accent "#7C3AED"
```

`--accent` colours the rule under the header wordmark; the sidebar field is
left at the suite black on purpose. A coloured field is for a COURSE
installer — this is a tool, and has no accent of its own to wear. That
distinction is why the generator has two flags rather than one.

Without these keys NSIS ships its own stock artwork, which is a blue
gradient and looks like a different product. Nothing fails; the wizard
just stops being ours.

## Development

```bat
venv\Scripts\python.exe -m pytest -q
cd frontend && npx vitest run
```

Version policy and the release steps are in [`VERSION.md`](VERSION.md); the
history is in [`CHANGELOG.md`](CHANGELOG.md). This file deliberately carries no
version number — one more place to update is one more place to drift.

## License

Internal tool — not for distribution.
