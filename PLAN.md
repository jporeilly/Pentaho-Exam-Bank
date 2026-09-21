# Pentaho Question Bank — restack and course integration

**Status:** proposed, not started
**Date:** 2026-09-19
**Applies to:** `C:\Projects\question_bank` (→ `Pentaho-Question-Bank`)

---

## 1. Decisions taken

| Decision | Choice |
|---|---|
| Absorb into PCE, or keep separate? | **Keep separate.** It is a publisher with several outputs; `exam.json` is one of them. |
| Repo | **Rename on GitHub** (`Question-Bank` → `Pentaho-Question-Bank`) — keeps history and redirects existing remotes. |
| PPTX / vision generation | **Dropped.** The future is course content, not slide decks. |
| PCE integration | **PCE gets a "Questions" button** that launches PQB for the current course. |
| Stack | Match PCE: Tauri + React + TypeScript frontend, Python/FastAPI backend, vendored Python, NSIS installer. |

### Why separate, restated

The bank generates pools in bulk and stops; PCE edits prose continuously. Different job, different
cadence, different hat. Absorbing ~19.5k lines into PCE would put a rarely-used surface in front of
authors who never touch questions, and would kill QTI/Moodle/PDF export, which only make sense in a
standalone bank.

---

## 2. Architecture

### 2.1 PCM is the bottom of the stack

```
Pentaho-Content-Manager        <- install first; owns courses/, the Engine,
  courses/<slug>/exam.json        scripts/*.mjs, and brings Node + git
        |
        +-- Pentaho-Content-Editor    edits guide.md, course.json, exam SETTINGS
        +-- Pentaho-Question-Bank     owns exam.json `questions`
```

**PCE is not the source of truth — `courses/` in git is.** PCE is one editor over it; PQB is another.
PQB therefore depends on **PCM only**, and is installable and usable with PCE absent.

### 2.2 The disjoint-key contract

This already exists in code on both sides and needs no change to establish:

| Owner | Keys in `exam.json` |
|---|---|
| **PCE** | `title`, `description`, `passMark`, `questionsPerAttempt`, `shuffle`, `webhookUrl`, `webhookSecret`, `intake` — the `_EXAM_SETTINGS` tuple in `api/routers/courses.py`, which deliberately excludes `questions` |
| **PQB** | `questions` — and the numerals inside `description` (see §3.3) |

Two writers, one file, no overlapping keys. Git reconciles if they ever collide. This is the same
guarantee an API round-trip would give, without the runtime chain.

**PCM owns the schema.** `scripts/verify-course.mjs` and `src/content/localFolderSource.ts` define
the question shape; both editors conform to it.

### 2.3 Why PQB does *not* call PCE's API

Considered and rejected:

- PCE's port is assigned at launch — `desktop/boot.py` declares `--port` as `required=True` with no
  default. PQB would have to *discover* a running PCE, not call a known port.
- It would make PCE a **runtime** dependency: three apps alive to move one question into a course,
  with a silent failure mode when PCE is closed.
- It removes no conflict, because the key contract already prevents one.

The "Questions" button is a **launch**, not a dependency: PCE spawns PQB with a course slug and gets
out of the way. If PQB is not installed, the button says so.

---

## 3. Blockers — fix before any write-back

### 3.0 Status — 3.1 is FIXED (2026-09-21), and it uncovered two more

3.1 is done, along with two further losses found while proving it. All three are
covered by `tests/test_pcm_roundtrip.py`, and the import direction now round-trips
`pdi-2hr-lab` and `developer-di-practitioner` byte-identically:

* **Ids preserved on import.** The live pools use *hand-authored* ids (`m1-q1`,
  `q-preview`), not uuids — minting would have destroyed meaningful keys.
* **The `source` citation preserved.** It is richer than `module` ("Lab 1 — Your
  First Win" vs "See It Work"), and the exporter rebuilt it from `topic`,
  downgrading it on every round-trip. An authored citation now wins.
* **Pool order preserved** via a new `pool_order` column. `search()` returns
  `updated_at DESC`, so a publish-back reordered the entire array — an unreadable
  diff, and in a pool that draws N with shuffle off it changes which questions get
  asked.

**Still open: 3.4 below.**

### 3.1 Question ids churn on import — FIXED

`core/question_importer.py:import_from_pcm_exam_json` never passes `item["id"]` to the `Question`
constructor, so `Question.__post_init__` mints a fresh uuid.

Ids are load-bearing in PCM:

- `src/components/Quiz.tsx:1198` — `id: q.id` goes into the per-question `breakdown` of the results
  payload sent to the webhook and the results Sheet.
- `src/components/Quiz.tsx:397` — `saveInProgress` keys exam resume on `questionIds`.
- `src/content/localFolderSource.ts:452` — falls back to a **positional** `q${i + 1}` when an id is
  missing. Identity by position; do not let a question reach PCM without an id.

A round-trip today rewrites all 395 live ids, orphaning Sheet history and breaking in-flight attempts.

**Fix:** carry `id` through on import; mint only when genuinely absent. Guard with a round-trip test
(§7).

### 3.2 The stale-slug bug is structural

`Certification.source_ref` stores a *copy* of a PCM course slug that nothing revalidates. When PCM
renamed `developer-practitioner` → `developer-di-practitioner` (one day after the bank's last
session) and `developer-ml-speciality` → `developer-ml-specialty`, both certifications silently
stopped resolving: `load_pcm_course` returns `[]` with no error.

**Fix:** resolve live against `PCM_REPO` and validate the slug at use time. Never cache it. If a
stored slug no longer resolves, say so in the UI and offer the current course list — do not fail
silently and do not guess.

### 3.3 `verify-course.mjs` enforces description ↔ numbers

`checkExamDescriptionClaims` fails the build when the prose misstates the pool size, questions per
attempt, or pass mark — e.g. "40 questions … drawn from a pool of 48. Pass mark is 80%."

**Fix:** publishing must regenerate those numerals. It recognises several phrasings
(`pool of (\d+)`, `(\d+)-question bank`, `(\d+) questions per attempt`, …), so match the existing
sentence shape rather than rewriting the author's prose.

### 3.4 Publishing must MERGE into the existing file, never regenerate it

`export_pcm_exam_json` writes a *fresh* `exam.json` from a fixed parameter list.
It is the right tool for a brand-new pool and the wrong one for publishing back
to a live course, because it can only carry the keys it has parameters for.

Proved against `pdi-2hr-lab`: the export drops **`intake`** — the pre-exam
candidate form config (`optional`, `consent`, `startLabel`, `trackResults`,
`collectCandidate`) — because the exporter has no `intake` parameter. That is a
key the Content Editor owns, and silently deleting it is exactly what the
disjoint-key contract (§2.2) exists to prevent. `webhookSecret: ""` is likewise
omitted rather than written back as an empty string.

**Fix:** Phase 2's publish step reads the existing `exam.json`, replaces only
`questions` (plus the description numerals, §3.3), and writes the rest back
untouched — including keys the bank has never heard of. This is the exact mirror
of the Content Editor's `put_exam`, which preserves `questions` "and any key this
editor doesn't know about".

**Until that exists, nothing publishes back to a course.**

---

## 4. What moves, what dies

### 4.1 Dies

| Path | Lines | Reason |
|---|---:|---|
| `gui/` (22 components) | 10,367 | NiceGUI layer replaced by React |
| `core/ollama_client.py` | 547 | Replaced by PCE's `providers.py` (multi-provider) |
| `core/mcp_client.py` | 138 | Replaced by PCE's `api/mcp.py` |
| `core/pptx_exporter_fallback.py` | 299 | PPTX dropped |
| `core/pptx_exporter.py` | 128 | PPTX dropped (used only by `gui/components/sidebar.py:343`) |
| `core/pptx_reader.py` | 86 | PPTX dropped — **but extract `SlideInfo` first**, see §4.3 |
| `core/question_importer.py` PPTX validation | 267 | Lines 629–895: `_match_option_to_notes`, `_get_slide_reference`, `validate_question_against_pptx`, `validate_batch`. `validate_question_against_docs` (896–970) is MCP-based and **survives**. |
| `tests/test_pptx_reader.py` | 123 | — |
| `tests/test_ollama_client.py` | 93 | Superseded by PCE's provider tests |
| `tests/test_mcp_client.py` | 115 | Superseded |

**12,163 lines retired**, of which 10,367 is the GUI.

### 4.2 Moves largely unchanged

`core/` is already the right stack. **4,761 lines** lift under FastAPI:

`question_bank.py` (865, the SQLite store + model) · `question_importer.py` (703 after the PPTX
cut) · `question_refinement.py` (618) · `exam_builder.py` (610, PDF papers — uses fpdf, no PPTX
dependency) · `spreadsheet_converter.py` (588) · `exporter.py` (408) · `question_generation.py`
(384) · `generation_prompts.py` (187) · `pcm_reader.py` (166) · `db_backup.py` (105) ·
`generation_parsing.py` (80) · `question_generator.py` (47)

Tests: ≈ **2,450 of 2,784 lines survive**. They cover `core/`, not the GUI.

### 4.3 `SlideInfo` must be extracted before `pptx_reader.py` can go

`SlideInfo` is the **universal generation input type** but is defined in `core/pptx_reader.py`,
which does `from pptx import Presentation` at module top level. It is imported by six core modules
(`generation_parsing`, `generation_prompts`, `pcm_reader`, `question_generation`,
`question_importer`, plus `gui/state.py`) and five test files.

**Action:** move the dataclass to a neutral `core/source.py` and rename it — "slide" is a misnomer
once slides are gone, and `pcm_reader` already calls them *sections*. Suggested: `ContentSection`,
with `speaker_notes` → `text`. Mechanical, fully test-covered, and a prerequisite for the PPTX cut.

### 4.4 What is lost with `ollama_client.py`, and whether it matters

`providers.py` is not a superset. Dropping `ollama_client.py` loses:

| Capability | Verdict |
|---|---|
| Vision / image input (`images=`, base64) | **Accepted loss** — only used for PPTX slide images |
| `num_ctx` override | Config-driven, **default off** — never active. Accepted. |
| Streaming (`generate_stream`, `chat_stream`) | Not needed for batch generation |
| VRAM-based model catalogue (~30 models) | `providers.suggest_model()` covers the same ground |

Gained: Anthropic and OpenAI providers, plus persisted settings.

> **Watch:** long `guide.md` sections with no `num_ctx` set fall back to Ollama's default context
> window. If generation quality drops on long sections, this is the first thing to check.

---

## 5. Phases

### Phase 0 — rename and repo hygiene

- Rename the GitHub repo to `Pentaho-Question-Bank`; update the local remote.
- Rename the working directory `C:\Projects\question_bank` → `C:\Projects\Pentaho-Question-Bank`.
- Add `VERSION.md`, `CHANGELOG.md`, `INSTALL.md`; rewrite `README.md` for the new stack.
- Fold `HOW_TO_GUIDE.md` (68 KB) into the docs set — it documents the NiceGUI UI that is about to go.

**Exit:** repo renamed, remote working, four docs present, 263 tests still green.

### Phase 1 — backend lift

- Adopt PCE's `api/` layout: `app.py`, `paths.py`, `providers.py`, `mcp.py`, `routers/`, `boot.py`.
- Copy `providers.py`, `mcp.py`, `paths.py` from PCE **verbatim**, so the two apps share one settings
  shape and one state-dir convention.
- Extract `SlideInfo` → `core/source.py` (§4.3), then delete the PPTX modules.
- Repoint `question_generation.py` at `providers.generate()`.
- Port `core/` under `routers/` as HTTP endpoints; keep the module boundaries as they are.
- Carry the tests over; drop the three superseded files.

**Exit:** FastAPI serves the bank's logic; ≈ 250 tests green; no NiceGUI import anywhere in `api/`.

### Phase 2 — the integration slice (**where the value is**)

This is deliberately *before* the UI rewrite, so the integration works against the lifted backend.

1. **Fix id preservation** on import (§3.1) + round-trip test.
2. **Adopt the live pools.** Read `PCM_REPO`, import the real courses' `exam.json` — **395 questions
   across 11 courses** — ids intact. These currently have no editing tool anywhere: the bank never
   kept them, and PCE deliberately refuses to touch them. This is the unlock.

   > **Skip `courses/_template/`.** It has an `exam.json` with 3 placeholder questions; adopting
   > them would seed the bank with fixtures. `courses/architect-con-specialty/` has no `exam.json`
   > at all — 13 course dirs, 12 exam files, 11 real pools.
3. **Publish back.** Write `questions` only; preserve every key PCE owns; regenerate the description
   numerals (§3.3).
4. **Live slug resolution** (§3.2) — reuse PCE's `_resolve_repo_root` ladder verbatim: env `PCM_REPO`
   → saved setting → installer hint → sibling dir, **never raising** on a bad answer, offering a
   folder picker instead. That behaviour exists because an installed app has no shell in which to fix
   a typo.
5. Optionally shell out to `verify-course.mjs` after publishing, degrading gracefully when Node is
   absent — exactly as PCE does.

**Exit:** a course's pool round-trips byte-identically; `verify-course.mjs` passes on all 11 courses;
the bank's DB holds the real 395.

### Phase 3 — Tauri + React UI, sequenced by value

Not a 22-component big bang. The existing app has seven tabs; port them in value order:

| Order | Tab | Notes |
|---|---|---|
| 1 | **Course / Generate** | The integration path — pick course + lab, generate |
| 2 | **Bank** (browser) | List, filter, search the adopted 395 |
| 3 | **Review / Edit** | Fix a key, reword a stem, drop a question |
| 4 | **Publish** | Write back to the course |
| 5 | Settings | Provider, model, `PCM_REPO` |
| 6 | Import | QTI / Moodle / CSV / spreadsheet |
| 7 | Exam Builder | PDF papers (fpdf) |
| 8 | Admin | DB backup/restore |
| 9 | AI & Docs | MCP docs grounding |

**Exit after 4:** the app is usable end to end for course questions without the long tail.

### Phase 4 — installer

- Reuse PCE's `desktop/` recipe: `fetch-python.ps1`, `stage-app.ps1`, `collect-installer.ps1`,
  `sign.ps1`, and the NSIS hooks that clear `app\` and `python\` on PREINSTALL/POSTUNINSTALL.
- Write the discovery hint to **`HKLM\SOFTWARE\Pentaho\QuestionBank`**, in **both registry views** —
  an NSIS installer is a 32-bit process, so its PowerShell writes the WOW6432Node mirror.
- PCE reads that key to decide whether to show the **Questions** button.
- Icons: per-app badge, white P on black tile, no red, no swirl.

**Exit:** installer builds, installs, launches, finds PCM, publishes to a course.

> **UAC:** installer builds and installs need an elevation prompt this tool shell cannot raise.
> Those commands get handed over to run manually.

---

## 6. Install and dependency order

| App | Needs | Order |
|---|---|---|
| **PCM** | — (brings Node + git) | **First** |
| **PCE** | PCM: `courses/`, Engine, `scripts/*.mjs` | Second |
| **PQB** | PCM: `courses/` only | Second — **independent of PCE** |

PQB needs Node only for the optional post-publish `verify-course.mjs` run, and degrades the same way
PCE does when it is missing.

---

## 7. Verification

Run in both repos, every phase:

```bash
npm test
```

```bash
cd api && .venv\Scripts\python -m pytest -q
```

**Baselines (2026-09-19, all green):** PQB 263 pytest · PCE 93 pytest + 293 vitest at v1.22.0.

**The Phase 2 safety net — a round-trip test that must be in the suite:**

1. Read a course's `exam.json` → import → export → compare **bytes**.
2. Assert every id is unchanged.
3. Assert every key PCE owns is untouched.
4. Assert `verify-course.mjs` still passes.

Nothing writes to a real course until this passes on all 11.

---

## 8. Risks and open items

| Item | Note |
|---|---|
| **A third vendored Python** | PCE's `desktop/README.md` records it shipped "17 MB of a second Python for four releases" before anyone noticed. A third app repeats that, and `providers.py` / `mcp.py` / `paths.py` then live in three places — the same fix in three spots. Not a blocker; a shared Python package is the structural answer when it starts to hurt. |
| **Two writers on one file** | Mitigated by the disjoint-key contract (§2.2), not eliminated. Git is the backstop. |
| **The 46 orphaned drafts** | Created 2026-06-04, zero overlap with the live 395, under two certifications that no longer resolve. Decide during Phase 2: adopt, or discard with the old DB. |
| **Review lifecycle** | `draft → sme_review → approved → retired` has never advanced past `draft` in any row. Not ported unless SME review becomes real. |
| **Publishing to Pentaho-Courses** | On hold pending the exam-results Google Sheet moving accounts. Nothing here publishes. |

---

## 9. House rules for this work

- `encoding="utf-8"` on **every** `open()` — Windows Python defaults to cp1252 and manufactures
  mojibake from clean UTF-8. Check bytes, not decoded text; a console can lie about what is in a file.
- Stage by path. Never `git add -A`.
- `git commit -F <file>` — PowerShell 5.1 splits native args at embedded quotes.
- `.ps1` files ASCII-only; em-dashes break PowerShell 5.1.
- Render the React UI after hook/state edits. A bundle grep is not verification.
