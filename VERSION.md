# Version

**Current: 1.3.0**

**Status:** released. The app is a Tauri desktop shell over a FastAPI backend
and a React UI, shipping as a per-machine Windows installer with its own
vendored Python. It generates certification questions from PCM course content
or the Pentaho docs, holds them in a SQLite bank with a review lifecycle,
publishes back into a live course's `exam.json` as a merge, and exports to QTI
2.1, Moodle XML, CSV, DOCX and PDF exam papers.

1.0.0 is the condition this file set out in advance and did not move: *one
minor per phase, 1.0.0 when it installs and publishes back to a course*.
Publish-back landed in Phase 2 and the installer in Phase 4. The intervening
minors were never cut — the repo stayed on 0.1.0 through three phases — so this
is 0.1.0 to 1.0.0 in one step rather than a run of releases. The phases were
done; the tags were not.

What 0.1.0 marked was the *first tracked* version, not a first release: the
point at which the repo took its Pentaho name, the package stopped being the
repo directory, and adopting a live course exam became lossless.

| Version | Phase |
| ------- | ----- |
| 0.1.0 | Rename, package restructure, lossless course adoption |
| 0.2.0 | Phase 1 — backend lifts onto FastAPI, PPTX and the duplicate clients retire |
| 0.3.0 | Phase 2 — publish back to a course (merge, never regenerate) |
| 0.4.0 | Phase 3 — Tauri + React UI |
| 1.0.0 | Phase 4 — Windows installer |

The phase ladder ends there. Past 1.0.0 this is ordinary semver against the
installed app: a minor for a feature an installed copy did not have, a patch
for a fix. 1.1.0 is the first of those — the bank adopts the Content
Manager's courses instead of opening empty, which 1.0.0 shipped without.

## Where the version string lives

Eleven sites across seven files. The table below is the human-readable copy;
the machine-readable one is `CARRIERS` in
[`scripts/bump.py`](scripts/bump.py), which both the bump tool and
`tests/test_version.py` read — so the thing that writes them and the thing
that checks them cannot disagree about where they are.

| File | Form |
| ---- | ---- |
| `exam_bank/__init__.py` | `__version__ = "x.y.z"` — **source of truth** |
| `VERSION.md` | the **Current:** line above |
| `CHANGELOG.md` | the most recent `## [x.y.z] - YYYY-MM-DD` heading |
| `desktop/package.json` | `"version"` |
| `desktop/package-lock.json` | `"version"` **twice** — top level and `packages[""]` |
| `frontend/package.json` | `"version"` |
| `frontend/package-lock.json` | `"version"` **twice** |
| `desktop/src-tauri/tauri.conf.json` | `"version"` — what the installer filename carries |
| `desktop/src-tauri/Cargo.toml` | `version = "x.y.z"` |
| `desktop/src-tauri/Cargo.lock` | the `pentaho-exam-bank` package entry |

A carrier nobody checks is a carrier that drifts. The two npm lockfiles are the
ones to watch: npm rewrites both of their version keys on install, silently,
and the Content Manager's sat six releases behind before anyone looked.

## Releasing

1. `venv\Scripts\python.exe scripts/bump.py x.y.z` — moves every carrier and
   cuts `## [Unreleased]` into `## [x.y.z] - <today>` with a fresh Unreleased
   above it. It refuses to write anything if a carrier has already drifted,
   so a half-bumped tree is not a state this can reach. `--dry-run` first if
   you want to see the list.
2. Run the tests — `venv\Scripts\python.exe -m pytest -q`. `test_version.py`
   checks all eleven sites.
3. Build and collect the installer — `cd desktop && npm run dist`.
4. Install it, then `desktop\scripts\verify-install.ps1`. It fails if the
   installed launcher is not the build you just made, so "verified" cannot
   accidentally mean the previous release.
5. Commit, staging by path, with `git commit -F <message-file>`.
