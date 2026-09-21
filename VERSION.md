# Version

**Current: 0.1.0** (development)

**Status:** 0.x, restack in progress. The app works today as a NiceGUI desktop
web app: it generates certification questions from PCM course content or the
Pentaho docs, holds them in a SQLite bank with a review lifecycle, and exports
to a PCM `exam.json`, QTI 2.1, Moodle XML, CSV, DOCX and PDF exam papers.

What 0.1.0 marks is the *first tracked* version, not a first release — the code
predates it. It is the point at which the repo took its Pentaho name, the
package stopped being the repo directory, and adopting a live course exam
became lossless. See [`CHANGELOG.md`](CHANGELOG.md).

The road to 1.0 is the restack in [`PLAN.md`](PLAN.md): the backend lifts onto
FastAPI, the NiceGUI layer is replaced by Tauri + React, and the app ships as a
Windows installer like the other Pentaho apps. Rough intent — one minor per
phase, 1.0.0 when it installs and publishes back to a course:

| Version | Phase |
| ------- | ----- |
| 0.1.0 | Rename, package restructure, lossless course adoption |
| 0.2.0 | Phase 1 — backend lifts onto FastAPI, PPTX and the duplicate clients retire |
| 0.3.0 | Phase 2 — publish back to a course (merge, never regenerate) |
| 0.4.0 | Phase 3 — Tauri + React UI |
| 1.0.0 | Phase 4 — Windows installer |

## Where the version string lives

Hand-kept, and `tests/test_version.py` fails when any carrier disagrees with
the source of truth.

| File | Form |
| ---- | ---- |
| `question_bank/__init__.py` | `__version__ = "x.y.z"` — **source of truth** |
| `VERSION.md` | the **Current:** line above |
| `CHANGELOG.md` | the most recent `## [x.y.z] - YYYY-MM-DD` heading |

Phases 3 and 4 add carriers this app does not have yet — `package.json` and its
lockfile, `desktop/src-tauri/tauri.conf.json`, `Cargo.toml` and `Cargo.lock`.
Add each to the table **and to the test** as it arrives; a carrier nobody checks
is a carrier that drifts.

## Releasing

1. Bump `__version__` in `question_bank/__init__.py`.
2. Bump the **Current:** line in this file.
3. In [`CHANGELOG.md`](CHANGELOG.md), rename `## [Unreleased]` to
   `## [x.y.z] - YYYY-MM-DD` and open a fresh `Unreleased` section.
4. Run the tests — `venv\Scripts\python.exe -m pytest -q`. `test_version.py`
   catches a carrier you missed.
5. Commit, staging by path, with `git commit -F <message-file>`.
