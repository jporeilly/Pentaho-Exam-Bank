# Pentaho Exam Bank

Writes certification exam questions from Pentaho course content, holds them in
a reviewable bank, and publishes them where they are needed — as a Content
Manager `exam.json`, a QTI or Moodle import, or a printed exam paper.

An **authoring tool that runs on your machine only.** It is never shipped to a
learner VM: the questions it produces are, the app is not.

> **The restack is in progress.** The interface is now React over a FastAPI
> backend, served as one app on one port from a checkout. What remains is the
> Tauri packaging and a Windows installer, and PPTX and vision-model
> generation are being dropped along the way. See
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
| **Exam Bank** | `questions`, and the numerals inside `description` |

Two writers, one file, no overlapping keys.

## Getting started

See [`INSTALL.md`](INSTALL.md). In short: Python 3.10+, then `install.bat`
once and `run.bat` to start the app — the interface on
<http://localhost:7777> and the HTTP API on <http://localhost:7788>, whose
interactive documentation is at `/docs`. `run-api.bat` starts the API alone.

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
Pentaho-Exam-Bank/
├── install.bat                  # One-click install
├── run.bat                      # Launch the app (API + built front end, port 7788)
├── run-api.bat                  # Launch: API alone, without opening a browser
├── _venv.bat                    # Shared venv check/repair for both launchers
│
├── exam_bank/               # The package (the repo root is the source root)
│   ├── __init__.py              #   __version__ — the source of truth
│   ├── core/                    #   Business logic, no UI
│   │   ├── bank.py              #     SQLite store + Question/Certification models
│   │   ├── question_generation.py, generation_prompts.py, generation_parsing.py
│   │   ├── question_refinement.py   #  regenerate, improve, QA, explanations
│   │   ├── question_importer.py #     CSV/JSON/Excel/QTI/Moodle/exam.json import
│   │   ├── exporter.py          #     every output format
│   │   ├── exam_builder.py      #     topic-weighted PDF exam papers
│   │   ├── pcm_reader.py        #     reads a course's guide.md as sections
│   │   ├── ollama_client.py, mcp_client.py
│   │   └── pptx_*.py            #     slated for removal in 0.2.0
│   ├── api/                     #   FastAPI over core, and the app's only surface
│   │   ├── __main__.py          #     `python -m exam_bank.api [--open]`
│   │   ├── jobs.py              #     background jobs; generation takes minutes
│   │   └── routers/             #     system, questions, certifications, courses,
│   │                            #     generation, export, import, exam, publish,
│   │                            #     settings, admin, docs
│   └── utils/config.py          #   settings, and PROJECT_ROOT for everything else
│
├── frontend/                    # React + Vite; `npm run build` produces dist/,
│   └── src/                     #   which the API serves at its own root
│
├── icons/                       # The app icon; see "The icon" below
├── scripts/migrate_pcm_exams.py # Adopt a course's exam into the bank
├── tests/                       # 278 tests
└── assets/                      # Database, config, caches — gitignored
```

The repo root is the source root, so `exam_bank` imports as a package from
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
```

Version policy and the release steps are in [`VERSION.md`](VERSION.md); the
history is in [`CHANGELOG.md`](CHANGELOG.md). This file deliberately carries no
version number — one more place to update is one more place to drift.

## License

Internal tool — not for distribution.
