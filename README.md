# Pentaho Question Bank

Writes certification exam questions from Pentaho course content, holds them in
a reviewable bank, and publishes them where they are needed — as a Content
Manager `exam.json`, a QTI or Moodle import, or a printed exam paper.

An **authoring tool that runs on your machine only.** It is never shipped to a
learner VM: the questions it produces are, the app is not.

> **The restack is in progress.** Today this is a NiceGUI web app started from
> a checkout. It is moving to the same stack as the other Pentaho apps —
> FastAPI backend, Tauri + React front end, Windows installer — and PPTX and
> vision-model generation are being dropped along the way. See
> [`PLAN.md`](PLAN.md) for the phases and [`VERSION.md`](VERSION.md) for where
> it is on the road to 1.0.

## What it is for

A course's exam lives in its `exam.json` inside the Content Manager. Until now
nothing owned the questions in it — the Content Editor deliberately edits only
the delivery and grading settings, and this bank never kept what it exported.
So a pool, once written, could not practically be changed.

This app is the other half. It **adopts** a course's existing questions, lets
you generate, review and edit them, and hands them back untouched in every
respect you did not mean to change.

| Owner | Keys in a course's `exam.json` |
| ----- | ------------------------------ |
| **Content Editor** | `title`, `description`, `passMark`, `questionsPerAttempt`, `shuffle`, `webhookUrl`, `webhookSecret`, `intake` |
| **Question Bank** | `questions`, and the numerals inside `description` |

Two writers, one file, no overlapping keys.

## Getting started

See [`INSTALL.md`](INSTALL.md). In short: Python 3.10+, then `install.bat`
once and `run.bat` to start the app on <http://localhost:7777>.

To bring a course's existing questions into the bank:

```bat
venv\Scripts\python.exe scripts\migrate_pcm_exams.py pdi-2hr-lab
```

Ids, authored order and citations are preserved — see
[Round-tripping a course](#round-tripping-a-course) for why that matters.

For a walkthrough of the app itself, [`HOW_TO_GUIDE.md`](HOW_TO_GUIDE.md) covers
each tab in detail. The Admin tab reads it in place, so it is available without
leaving the app.

## Where questions come from

| Source | What it reads |
| ------ | ------------- |
| **Content Manager course** | A course's lab `guide.md` files, split into sections. Pick a whole course or a single lab. |
| **Pentaho docs (MCP)** | The published documentation, over the GitBook MCP endpoint. |
| **An existing course exam** | A course's `exam.json`, adopted into the bank for editing. |
| **PowerPoint** | Speaker notes, with slide images for vision-capable models. *Slated for removal in 0.2.0.* |
| **Import** | CSV, JSON, Excel, QTI 2.1, Moodle XML. |

Generation is grounded: the correct answer must be traceable to the source
text, and the model is made to quote the passage that supports it
(`key_source_text`) so the claim can be checked rather than trusted.

## What it does

- **Generate** — scenario-based questions with per-question control over
  single/multi-select, key and distractor counts, Bloom's level and difficulty;
  batch generation across a whole course with balanced format distribution.
- **Refine** — regenerate just a stem, one key or one distractor; AI grammar
  and syntax checks per field; auto-generated explanations that address every
  choice.
- **Review** — a lifecycle of `draft → sme_review → revised → approved →
  retired`, every transition logged with who, when and why. Field-level version
  history with colour-coded diffs.
- **Guard quality** — fuzzy duplicate detection on stems, validation of the key
  against its source, and warnings for weak distractors.
- **Publish** — see [Export formats](#export-formats).
- **Administer** — analytics on status, difficulty, Bloom's and topic coverage;
  database browse, backup and restore.

## Round-tripping a course

A course pool carries three things that are easy to destroy and hard to notice:

- **Question ids are durable external keys.** The Content Manager puts them in
  the results payload it posts to the webhook, and keys an in-progress attempt
  on the ids it dealt. The live pools use hand-authored ids (`m1-q1`,
  `q-preview`). Minting new ones would orphan every recorded result.
- **The `source` citation is richer than the module name** — "Lab 1 — Your
  First Win" against "See It Work".
- **Order decides what gets asked** in a pool that draws N questions with
  shuffle off.

All three survive adoption and export, covered by `tests/test_pcm_roundtrip.py`.

> **Nothing publishes back to a course yet.** The export writes a fresh
> `exam.json` from a fixed parameter list, so it would drop `intake` — the
> pre-exam candidate form config the Content Editor owns. Publishing must merge
> into the existing file instead. See [`PLAN.md`](PLAN.md) §3.4.

## Layout

```
Pentaho-Question-Bank/
├── main.py                      # Entry point (NiceGUI, port 7777)
├── install.bat / run.bat        # One-click install and launch
│
├── question_bank/               # The package (the repo root is the source root)
│   ├── __init__.py              #   __version__ — the source of truth
│   ├── core/                    #   Business logic, no UI
│   │   ├── question_bank.py     #     SQLite store + Question/Certification models
│   │   ├── question_generation.py, generation_prompts.py, generation_parsing.py
│   │   ├── question_refinement.py   #  regenerate, improve, QA, explanations
│   │   ├── question_importer.py #     CSV/JSON/Excel/QTI/Moodle/exam.json import
│   │   ├── exporter.py          #     every output format
│   │   ├── exam_builder.py      #     topic-weighted PDF exam papers
│   │   ├── pcm_reader.py        #     reads a course's guide.md as sections
│   │   ├── ollama_client.py, mcp_client.py
│   │   └── pptx_*.py            #     slated for removal in 0.2.0
│   ├── gui/                     #   NiceGUI layer — replaced by React in 0.4.0
│   │   └── components/          #     one module per tab
│   └── utils/config.py          #   settings, and PROJECT_ROOT for everything else
│
├── scripts/migrate_pcm_exams.py # Adopt a course's exam into the bank
├── tests/                       # 278 tests
└── assets/                      # Database, config, caches — gitignored
```

The repo root is the source root, so `question_bank` imports as a package from
there. **Do not add an `__init__.py` at the repo root** — that is what used to
make `C:\Projects` itself a source root, and it made the folder name
load-bearing.

## Tabs

| Tab | Contents |
| --- | -------- |
| **Settings** | SME identity, bulk reassignment, export defaults, display, quality thresholds, maintenance |
| **Generate** | Source and generation settings, then the generated questions editor |
| **Import** | File import with validation, per-question reassignment, AI actions before committing |
| **Bank** | Dashboard, search and filters, bulk actions, export, backup/restore, student preview |
| **AI & Docs** | Ollama and MCP server configuration, plus a documentation chat |
| **Exam** | Exam paper builder — topic weighting, PDF options, preview |
| **Admin** | Analytics dashboard, database browser, bulk operations, in-app documentation |

## Question model

- **Scenario** — realistic context, one to three sentences.
- **Stem** — a direct question ending in "?" with an explicit "(Choose one/two.)".
- **Key(s)** — the correct answer, which must come from the source material.
- **Distractors** — two to four plausible wrong answers; no "All of the above".
- **Explanation** — addresses every choice, by its text rather than its letter,
  because choices get shuffled.
- **`key_source_text`** — the exact quote backing the key. Internal, for
  validation; never shown to a candidate.
- **Metadata** — topic, difficulty, Bloom's level, certification, status, tags,
  provenance, and `pool_order` when the question came from a course pool.

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
| **Content Manager** checkout | course content and course exams | course sources unavailable; everything else works |
| **Ollama** (local, free) | generation and refinement | no AI; the bank, import and export still work |
| **Pentaho docs MCP** | grounding in the published docs | no docs-sourced generation |

The Content Manager is found as the sibling `..\Pentaho-Content-Manager`, or at
the path set in the config. **No resolved course slug is ever cached** — a
stored slug that quietly stopped resolving is how this app's original
certifications died when the courses were renamed under them.

## Development

```bat
venv\Scripts\python.exe -m pytest -q
```

Version policy and the release steps are in [`VERSION.md`](VERSION.md); the
history is in [`CHANGELOG.md`](CHANGELOG.md). This file deliberately carries no
version number — one more place to update is one more place to drift.

## License

Internal tool — not for distribution.
