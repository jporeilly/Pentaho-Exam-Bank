# Changelog

All notable changes to Pentaho Exam Bank are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`dist/` holds the built installers, one per version**
  (`desktop/scripts/collect-installer.ps1`). Tauri leaves its output four
  directories deep inside `target/`, where `cargo clean` will delete it. This
  copies it to `dist/` at the repo root with its version in the name, so
  builds accumulate side by side, and writes a `.sha256` beside each — an
  installer is 38 MB of executable people are asked to run as administrator.
  It refuses to collect a build whose filename disagrees with the version in
  `tauri.conf.json`.

- **`desktop/scripts/verify-install.ps1`**, to run after installing. Read-only
  and unelevated. It checks the registry key in **both views**, that the
  launcher carries a name the Content Editor accepts, that no database or
  config was shipped inside the install, that the app starts and keeps its
  data in `%APPDATA%` rather than under Program Files, that closing it takes
  the backend with it — and finally asks the **Content Editor's own code**
  whether it can find the install, rather than reimplementing that judgement.
  `-InstallDir` mirrors the editor's `PEB_INSTALL_DIR` override.

- **The Tauri desktop shell** (`desktop/src-tauri/`). Starts the vendored
  Python on a free port, shows a startup page while it comes up, then
  navigates the window to it — so the packaged app serves the same interface
  a checkout does, which is what stops the two builds drifting.

  A **kill-on-close job object** means a crashed or Task-Managered shell
  cannot leave uvicorn holding the port and the SQLite lock. Readiness is
  asked of Rust, never fetched from the startup page: that page is on a
  `tauri://` origin, so a cross-origin fetch to `127.0.0.1` can never be read
  back and the page would spin forever in front of a working server.

  The **binary is named `pentaho-exam-bank.exe`** because that is a contract,
  not a label: the Content Editor looks for exactly that name inside an
  install. Cargo's default would have been `pentaho-exam-bank-desktop.exe`,
  which matches neither of the two shapes it accepts.

  The installer uses Tauri's NSIS **hooks** rather than overriding its
  template — twenty lines instead of owning eleven hundred. They write
  `HKLM\SOFTWARE\Pentaho\ExamBank` in **both registry views** (an NSIS
  installer is 32-bit; the Content Editor's Python is 64-bit and reads the
  64-bit view first), clear `app\` and `python\` before an upgrade so a
  removed module cannot linger and stay importable, and remove the key on
  uninstall. The user's bank in `%APPDATA%` is never touched.

  Verified by assembling the install layout by hand and running it, which
  needs no elevation: vendored Python, a free port, `GET /` 200, the database
  at `%APPDATA%\com.pentaho.exam-bank\db` rather than inside the install, a
  visible window, and no orphaned uvicorn after the shell was killed.

- **Desktop packaging, started** (`desktop/`). The vendored-Python recipe from
  the Content Editor, adapted: `fetch-python.ps1` builds a self-contained
  Python 3.12.8 with the bank's runtime dependencies (148 MB), and
  `stage-app.ps1` assembles `exam_bank/` + `frontend/dist` + `boot.py` into the
  tree the installer bundles. Both verified end to end; the Tauri shell and
  NSIS installer are still to come.

  `requirements-dev.txt` splits `pytest` out, because the installer vendors
  `requirements.txt` and a test framework cannot run inside a shipped app.

### Changed

- **The icon is a marked exam paper, not a tickbox.** A page with a rule
  and a tick punched out of it, still in violet (`#7C3AED`). The old badge
  said "done" where this app means "exam", and at 24 px in a taskbar of
  three Pentaho tiles that is the only thing distinguishing it. The badge
  itself was added to the Content Manager's `make-icons.py`, which is where
  all three suite icons are drawn.

- **The NiceGUI layer is gone, and `run.bat` starts one server.** The API
  serves the built React front end from `frontend/dist` at its own root, so
  the interface and the API are one process on **port 7788**; the 7777 the
  old interface used is retired. `exam_bank/gui/` (22 components, ~9,500
  lines), `main.py` and the `nicegui` dependency are all removed.

  The Content Editor's Questions button launches `run.bat` and never knew
  which port anything listened on, so it is unaffected — but it now gets a
  bank that *can* publish back, which its tooltip still hedges about.

  **The front end is rebuilt on every start.** A build is about five seconds,
  and building "only when missing" means a `git pull` leaves the old interface
  in place with nothing on screen saying so. A machine with no Node.js and an
  existing build starts on that build and says it did not rebuild.

- **Renamed to Pentaho Exam Bank.** The product, the Python package
  (`question_bank` -> `exam_bank`), the module that was the same name as its
  own package (`core/question_bank.py` -> `core/bank.py`), the class
  (`QuestionBankDB` -> `ExamBankDB`), the launch handover (`PQB_COURSE` ->
  `PEB_COURSE`) and every string an author reads. The Content Editor's
  Questions button opened a window titled "Question Bank Generator" - a
  third name for the same app, and the one that made this worth doing.

- **The database moved with it**, `assets/db/question_bank.db` ->
  `exam_bank.db`, by a rename at startup rather than a copy: two databases
  that both look live is the worse failure, because a later session edits one
  and reads the other. An `exam_bank.db` that already exists always wins.
  `tests/test_config_migration.py` pins the old name literally - a sweep over
  the repo silently rewrote that migration to `exam_bank.db -> exam_bank.db`
  while it was being written, which read fine and did nothing.

- **`PQB_COURSE` is still read** when `PEB_COURSE` is absent. A Content Editor
  installed before the rename sends the old name, and the alternative is a
  button that opens the bank on no course until two apps are reinstalled in
  the right order. Drop it once no shipped editor sends it.

- **The app's state directory is now separate from its code.** `config.py`
  creates `assets/db`, `assets/config` and `assets/db/backups` at IMPORT, off
  the package root. That is correct for a checkout and fatal for an install:
  the code lives under Program Files, which a normal user cannot write, so the
  import raises `PermissionError: [WinError 5]` three frames into pathlib
  before the app can say anything at all — reproduced by staging the package
  under a read-only directory.

  `PEB_STATE_DIR` moves everything the app writes; unset, it is the repo's own
  `assets/` exactly as before, so development is unchanged. `PROJECT_ROOT`
  stays where the code is, because `core/docs.py` reads the shipped guide from
  it.

### Fixed

- **An install can now find the Content Manager's courses.** The only rule
  was "look for a sibling directory", which is right in every checkout and
  can never work in an install: the code sits under Program Files, so the
  sibling searched was `C:\Program Files\Pentaho Exam Bank\Pentaho-Content-Manager`.
  The first install opened with every pane empty and nothing on screen
  saying why. The installer now runs `find-courses.ps1`, which looks one
  level down a short list of known roots and records the checkout it finds
  under `HKLM\SOFTWARE\Pentaho\ExamBank\PcmRepo` — the same value shape the
  Content Editor already writes, so one search answers for both apps. The
  app reads that hint, and still prefers an explicit `PCM_REPO`. Finding
  nothing is not a failure: the install continues and Settings asks.
- **A saved empty courses path no longer pins the app to "not configured".**
  Every config migrated from a checkout holds `""` for `pcm_courses_dir`,
  and that was passed through as a deliberate choice, overriding the
  default forever — so the discovery above would have been found and then
  ignored on exactly the machines that needed it.

- **The staging script leaked the build machine's own configuration.**
  Importing the staged tree to verify it runs `config.py`, which creates its
  directories *and* migrates `~/.question_bank/` into them — so the first run
  of `stage-app.ps1` put a `config.json` naming this machine's Ollama model and
  MCP servers, plus a database, inside the installer staging tree. The import
  check now redirects state to a scratch directory, and the "nothing private"
  assertion runs both before and after it: asserting only beforehand could
  never have caught a file the check itself created.

- **`pytest` from the repo root crashed the interpreter.** Collection walked
  into the vendored runtime, found pywin32's own test modules, and
  `win32comext	askscheduler	est	est_addtask.py` took the process down with
  an access violation before any test of this app ran. `pytest.ini` scopes
  collection to `tests/`.

- **AI & Docs, as a React pane** (`core/docs.py`,
  `exam_bank/api/routers/docs.py`). Ask the app's own guide a question, search
  it, or read it — the last of the NiceGUI panes.

  **Retrieval decides whether the model is called at all.** A model asked "how
  do I publish back to a course?" answers *something* whether or not it was
  given anything to read, and a confident invention about a tool somebody is
  about to use is worse than no answer. If nothing in the documentation
  matches, this says so and never calls the model.

  An answer comes back with **the sections it was built from**, shown beneath
  it. An answer about your own app is only worth anything if you can check
  what it read — and when retrieval matches weakly, seeing the sources is what
  reveals that.

  It asks through `core/providers`, so it honours the configured provider. The
  NiceGUI version called Ollama directly, and answered nothing at all if you
  had picked Anthropic or OpenAI in Settings.

- **Publish back into a course** (`core/publisher.py`, the Publish pane,
  `POST /api/courses/{slug}/exam/questions{,/plan}`). A **merge**, not a
  write: the course's `exam.json` is read, its `questions` array replaced, and
  every other key handed back untouched and in its original order — `intake`
  above all, which the whole-document exporter has no parameter for and would
  have dropped. The file's own line endings are preserved, because the Content
  Manager repo has `core.autocrlf=true` and imposing either turns a
  two-question edit into a whole-file diff.

  The write **requires the hash from a plan**, so it cannot be issued by a
  client that never asked what it was about to change, and it closes the race
  with the Content Editor, which writes this same file in whole. Publishing is
  refused — never quietly adjusted — when the pool would be empty, smaller
  than `questionsPerAttempt`, carry duplicate ids, or be published into a
  course the certification was not adopted from.

- **A refusal for stale `intake.contact` blocks.** Five published `exam.json`
  turned out to carry the contact relay's secret inside a block that moved to
  `course.json` months ago, which is how one credential came to be published
  in eight files instead of three. Publishing over one would re-commit it, so
  the merge refuses and names the key path. Deliberately not stripped:
  dropping an authored key silently is the same failure in the other
  direction, and silence is what let the copies sit there.

- **An app icon** (`icons/icon.ico`, plus the browser tab's
  `frontend/public/favicon.ico`): the suite's black P tile with a violet
  ticked-answer-box badge. Drawn by the Content Manager's `make-icons.py`,
  which gained the `check` badge for it, and committed here as an artifact -
  see **The icon** in the README for the regeneration recipe.

- **An HTTP API** (`exam_bank/api`) over the existing core — system,
  questions, certifications, courses, generation and export. Generation runs as
  a background job, because a course is dozens of model calls and minutes of
  work. Started by `run.bat` alongside the interface, or alone with
  `run-api.bat` / `python -m exam_bank.api`. It binds loopback only: there
  is no authentication, so anything that can reach it can read and change the
  bank.

- **One provider module** (`core/providers.py`). Sixteen call sites named
  Ollama directly; they now dispatch to Ollama, Anthropic or OpenAI, with keys
  read from the environment at call time and never stored.

- **`core/source.py`** — the generation input type, moved out of the PPTX
  reader so that reading a course no longer drags in `python-pptx`.

- **`python-multipart` was undeclared.** FastAPI needs it for the Import
  pane's file upload, and nothing here imports it directly — so it was present
  on this machine as somebody else's dependency, the feature worked, and a
  fresh venv (which `_venv.bat` builds automatically on repair) would have had
  the upload fail.

- **Documentation search finds what it is asked for.** Two problems, both
  measurable against this repo's own guide.

  Words kept whatever punctuation and markdown were attached, because the
  matcher split on whitespace: "certification" appears 88 times as text and
  only **34** times as a bare whitespace token, so two thirds of its
  occurrences were invisible. Tokenising on word characters recovers them.

  And ranking was dominated by the common words of the question. "How do I
  import a CSV?" was ranked mostly on *do*, *a* and *I*, and returned "Two
  Independent Checks" — a section containing those words and nothing about
  importing. It now returns "CSV Format", "Import Steps" and "Importing
  Existing Questions". Stop words are dropped, headings weigh more than
  bodies, and scoring counts distinct query terms rather than total hits, so a
  section repeating one word cannot outrank one covering the whole question.

- **Admin, as a React pane** (`core/admin.py`, `exam_bank/api/routers/admin.py`,
  the Admin pane). Backups and bulk deletion, deliberately in one place: this
  is the only part of the app with no undo, and somebody about to delete four
  hundred questions should be able to see the backup list while they decide.

  Deleting is **count-first**. The filters are the same ones the bank list
  uses, so it is genuinely easy to press delete against a view believed to
  show four questions and have it match four hundred. The count, a breakdown
  by status and certification, and a few of the actual stems all come back
  before anything goes — and the count is carried on the button rather than
  hidden behind "Are you sure?".

  The delete then **passes that count back**, and is refused if the bank has
  changed since. An **empty filter set matches everything**, so an unfiltered
  deletion has to be asked for explicitly rather than arrived at by clearing
  fields.

  Backups are addressed **by name, never by path** — a client that could hand
  over a path could restore the bank from, or delete, any file on the machine.
  Restoring reports the name of the backup taken of what it replaced, so the
  restore itself can be undone.

- **Settings, as a React pane** (`exam_bank/api/routers/settings.py`,
  `GET`/`PUT /api/settings`). Identity, provider and model, the courses and
  export directories, the quality thresholds, and the list defaults.

  It **never handles an API key**. Keys are read from the environment at call
  time and this app has never stored one, so the pane is told only *whether* a
  key is present, as a boolean — a form that accepted one would write it into
  `config.json`, a plain file in the project directory.

  It **writes only an allowlist**, and the allowlist and the validation are
  one table, so a field cannot be made writable without saying what a valid
  value is. `config.save()` writes the whole dataclass, and the config also
  holds state the app manages for itself — the recent-files list, the map from
  a source file to its certification — which a browser able to PUT arbitrary
  keys could quietly break with nothing reporting it.

  A setting an environment variable governs (`OLLAMA_MODEL` and friends) is
  shown but not editable, naming the variable. Left editable it would save,
  appear to work, and revert on the next start.

  One bad value changes none of the others, and a courses directory that does
  not exist is refused rather than saved — saved silently it would list no
  courses and look like an empty Content Manager rather than a typo.

- **Exam paper, as a React pane** (`core/exam_builder.plan_exam`, the Exam
  paper pane, `POST /api/exam/plan` and `/pdf`, `GET /api/exam/topics`). Draws
  a paper in the proportions an author sets, and **says when it cannot**.

  That last part is the reason it is two endpoints. The selection redistributes
  silently: a topic whose pool is too small contributes what it has and the
  difference is taken from topics with spare questions, so a 40/30/30 exam can
  come back 40/45/15 at the right length. The printed cover lists what the
  paper IS but never what was asked for, so telling the two apart meant
  remembering the weights you typed. `/plan` states the discrepancy outright,
  naming both the topic that fell short and the one covering for it.

  `select_exam_questions` is unchanged and now delegates to `plan_exam`, so
  the account and the paper cannot describe different selections.

- **Import, as a React pane** (`core/importing.py`, `core/validation.py`, the
  Import pane, `POST /api/import/preview` and `/commit`). Look-then-save, like
  publishing: a file of questions is parsed and reported on, and nothing is
  saved until the author chooses it. The preview says which questions cannot
  be graded and which the bank already has — the two things invisible in the
  file itself. A duplicate stays selectable but unticked, because "we reworded
  it" is a real answer and a pre-ticked decision is not one.

  Files are recognised by **content**, not extension: `.csv` covers both real
  CSV and the plain-text format, `.json` covers a Content Manager `exam.json`
  and this bank's own export, `.xml` covers QTI and Moodle. Guessing from the
  extension imports a plausible wrong shape rather than failing.

- **One definition of what makes a question gradeable.** The rules existed
  only in `QuestionEditor.tsx`; import needs them server-side, and neither
  copy can do the other's job — the browser answers while an author types, the
  server validates four hundred rows at once. Both are now driven from
  `tests/fixtures/question_problems.json`, and both suites assert against it
  message for message and in order. Reword a rule in one language and the
  other language's suite goes red; watched it fail from both sides.

- **Two backups in the same second were one backup.** The name carries a
  timestamp with one-second resolution and `sqlite3.connect` on an existing
  path overwrites it, so an author who took a backup, changed something and
  took another was left with a single file holding the later state.

  The restore path made that worse than wasteful: `restore_backup` writes a
  `pre_restore` copy *before* reading its source, so restoring a backup that
  was itself a `pre_restore` generated the same name in the same second — the
  safety copy landed on the very file being restored from, replacing the old
  bank with the current one. The restore then "succeeded" while changing
  nothing, and the backup it read no longer existed. Names are now made unique
  before anything is written; all three new tests fail against the old naming.

- **The import tab told authors the opposite of what the code does.** It said
  a plain-text file imports "all options as distractors". `import_from_text`
  in fact takes the **first option as the key**, positionally and silently —
  so the question is perfectly gradeable and nothing flags it. The format note
  now says the key was guessed and that every one needs checking, which is the
  only warning there is.

- **`request` forced `application/json` onto multipart uploads.** A `FormData`
  body has to carry its own boundary, and the header could not be removed by
  merging one in from `init.headers` — the upload arrived unparseable and the
  server answered with a missing-field 422 rather than naming the header.

- **A corrected answer was published alongside the typo it replaced.**
  `Question.all_choices` returned the stored `option_order` verbatim, and the
  editor never sends that field — so once an author fixed a key, the export
  saw the pre-edit option list, failed to find the corrected key in it, and
  appended it as an extra choice. The question shipped with the typo still
  selectable and two near-identical options in front of the learner, which is
  the one defect a reviewer cannot answer their way out of. The order is now
  applied rather than believed: surviving options keep their slot, an
  edited-away entry leaves a hole that the new text fills in place, and
  anything left over goes on the end — so a stale order can cost position,
  never correctness. `tests/test_pcm_roundtrip.py` covers the edit cases; five
  of the six fail against the old property.

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
