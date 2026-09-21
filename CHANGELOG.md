# Changelog

All notable changes to Pentaho Question Bank are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **An HTTP API** (`question_bank/api`) over the existing core — system,
  questions, certifications, courses, generation and export. Generation runs as
  a background job, because a course is dozens of model calls and minutes of
  work. Started by `run.bat` alongside the interface, or alone with
  `run-api.bat` / `python -m question_bank.api`. It binds loopback only: there
  is no authentication, so anything that can reach it can read and change the
  bank.

- **One provider module** (`core/providers.py`). Sixteen call sites named
  Ollama directly; they now dispatch to Ollama, Anthropic or OpenAI, with keys
  read from the environment at call time and never stored.

- **`core/source.py`** — the generation input type, moved out of the PPTX
  reader so that reading a course no longer drags in `python-pptx`.

### Fixed

- **The launchers now call the venv's interpreter by explicit path.** They
  activated the venv and trusted `python`, which on a machine with the Windows
  Store Python still resolved to the Store build — so the dependency check
  passed against the wrong interpreter and the app died later on the first
  package that was only in the venv.

- **Sibling scripts are called via `%~dp0`.** A bare name fails outright where
  `NoDefaultCurrentDirectoryInExePath=1` is set, which stops `cmd` resolving an
  executable from the current directory.

- **Resolving the courses directory was written twice, and the second copy was
  wrong**: `Path(config.pcm_courses_dir or ".")` turned "not configured" into
  the *current working directory*, which is a real directory — so the guard
  never fired and the app would look for courses wherever it had been started
  from.

- **Exporting an `exam.json` across two courses is refused** rather than
  produced. Each course's `pool_order` starts at 0, so two pools interleave
  instead of concatenating, giving a plausible file in an order nobody chose.

## [0.1.0] - 2026-09-21

The first tracked version. The code predates it — what is new here is the
Pentaho name, a package that no longer depends on the folder it sits in, and an
import path that can read a live course exam without quietly damaging it.

### Added

- **`scripts/migrate_pcm_exams.py`** — adopts a PCM course's exam into the
  bank. One certification per course, ids preserved, and it verifies the ids
  survived rather than assuming it. The course slug is resolved at run time and
  must exist: a cached slug that silently stopped resolving is how the bank's
  two original certifications died when PCM renamed the courses under them.

- **`pool_order`** on a question — the position it held in its course pool,
  added through the existing schema-migration path. `-1` means it was not
  adopted from a pool.

- **`tests/test_pcm_roundtrip.py`** — nine tests guarding the round-trip, plus
  `VERSION.md`, `INSTALL.md`, this file, and a version-drift test.

### Fixed

- **Question ids are preserved when adopting a course exam.** They were
  discarded, so every question got a fresh uuid on import. The live pools use
  hand-authored ids (`m1-q1`, `q-preview`), and PCM treats an id as a durable
  external key — it goes into the results payload posted to the webhook, and an
  in-progress attempt is keyed on the ids it was dealt. Minting would have
  orphaned every recorded result. A question genuinely without an id still gets
  one; PCM's own fallback for that case is positional (`q1`, `q2`, …), which
  must never be relied on.

- **The `source` citation survives a round-trip.** It is richer than `module` —
  "Lab 1 — Your First Win" against "See It Work" — and the exporter rebuilt it
  from `topic`, downgrading it to the bare module name every time. An authored
  citation now wins; a generated question still gets one built from course plus
  section.

- **A pool keeps its authored order.** Nothing recorded it, and `search()`
  returns `updated_at DESC`, so writing a pool back reordered the entire
  `questions` array. That is an unreadable diff, and in a pool that draws N
  questions with shuffle off it silently changes which questions get asked.

  Verified against the live files: `pdi-2hr-lab` (20 questions) and
  `developer-di-practitioner` (48) both round-trip byte-identically, in order.

### Changed

- **Renamed to Pentaho Question Bank**, matching the other Pentaho repos — on
  disk and on GitHub (`jporeilly/Pentaho-Question-Bank`).

- **The Python package moved into `question_bank/`.** The repo directory *was*
  the package: a root `__init__.py`, and tests importing `question_bank.core.*`.
  That made `C:\Projects` itself a source root, and made the folder name
  load-bearing — the rename would have broken every import, because a hyphen is
  not valid in a Python identifier. The repo root is now the source root.

- **The project root is derived once.** Four modules each walked
  `parent.parent[.parent]` to find it, and all four shifted a level in the move;
  they now import `PROJECT_ROOT` / `ASSETS_DIR` from `utils.config`.

### Known limitations

- **Nothing publishes back to a course yet.** `export_pcm_exam_json` writes a
  fresh `exam.json` from a fixed parameter list and has no parameter for
  `intake`, so publishing would delete the pre-exam candidate form config that
  the Content Editor owns. The publish step must merge into the existing file —
  the mirror of the editor's `put_exam`. See `PLAN.md` §3.4.

- PPTX and vision-model generation still work but are slated to be dropped in
  0.2.0; the future of this app is course content.
