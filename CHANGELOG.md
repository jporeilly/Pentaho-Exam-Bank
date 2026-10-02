# Changelog

All notable changes to Pentaho Exam Bank are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.11.0] - 2026-10-02

### Added

- **How alike each exam's questions are.** The report now gives every
  question its nearest neighbour in the same exam, with a similarity from
  0 to 100%, and lists each exam's closest pairs with the words they share.
  Two questions asking the same thing waste a pool slot and, drawn into one
  paper, can give each other away. 55% and above is a likely duplicate and
  raises a finding naming the pair; 40-54% is an overlap, listed but not
  flagged, since related questions within a course are expected. The
  measure is TF-IDF over the scenario, the question and the correct
  answer(s), compared by cosine, with IDF taken within the exam so a
  course's own vocabulary does not make all of its questions look alike.
  It needs no model and can say why two questions match. Calibrated on the
  eleven course exams: the median nearest neighbour scored 18%, the 99th
  percentile 45%, and the one real duplicate found (pdi-2hr-lab's
  2hr-m4-q1 and 2hr-m4-q5, the same scenario reworded with the same key)
  62%. `core/similarity.py`; `similarity` on each exam and `nearest` on
  each item in `GET /api/report`. The Report screen shows it as a section
  after Findings (the median and highest score, a chart of
  nearest-neighbour scores in 10% buckets, the closest pairs with their
  shared words) and a **Nearest** column in the question list.

### Changed

- **Colour that means something.** Every action was the one teal or a
  grey, and in the editor a correct answer looked exactly like a
  distractor. Colour now says what a thing is, the same on every screen
  (Getting Started has the key):

  - **Correct answers are green with a tick, distractors rose with a
    cross**, in the editor, in Generate's review, in the AI's proposed
    answer key and rewrite (both now listed as marked options instead of
    plain bullets), and as a green chip in Import's preview. One component,
    `answers.tsx`; the marks are drawn by CSS so they never join a label's
    text or an option's spoken name.
  - **Buttons by role**: teal for a screen's main action, violet for
    anything the AI does, green for adding or keeping, blue for looking
    without changing, red for removing or rejecting. Filled for the main
    action, a tint with coloured text for secondary ones. Status moves take
    the colour of where they lead (Approve green, Reject red). A Delete in a
    table row stays red text on nothing until the row is hovered, so a list
    is not a column of red.
  - **The side bar's three groups each have a colour** (blue for bringing
    questions in, teal for working with them, violet for the app itself):
    icons, headings and the current screen's bar, with a thin band in the
    three colours under the header.
  - The row being edited in the Bank was tinted red, a leftover from the
    old branding; it is teal now that red means a wrong answer.
  - "select all" on multi-select questions in the Report reads
    "multi-select", matching the house form ("Which two …?").

## [1.10.0] - 2026-09-30

### Added

Five features that had settings or code but nothing working behind them.

- **AI Chat answers as it writes.** The sources appear as soon as the
  searches are done, then the answer word by word, instead of all at once
  after a minute on a local model. **Stop** keeps what was written, marked
  *Stopped before it finished*, and leaves it out of the follow-up; with
  Ollama it also stops the model. Streams from Ollama, Anthropic and OpenAI
  (`providers.chat_stream`, `POST /api/chat/stream`, newline-delimited JSON).
- **GPU advice** under Settings > The model (Ollama): the cards from
  `nvidia-smi`; whether the saved model fits on ONE card - on a two-card
  machine a model that does not is spread over the cards or onto the CPU and
  runs several times slower; every pulled model's fit; the largest one that
  fits comfortably when the chosen one does not; and how much of a loaded
  model sits on the CPU (Ollama's `/api/ps`). `GET /api/settings/gpu`.
- **Check imported questions against docs.pentaho.com.** A button in
  Import's preview looks each question up through the docs connection AI
  Chat uses and marks it Backed (every correct answer found, word for word or
  by enough of its meaningful words), Not found, or Not checked, with the
  pages it found. Changes nothing. The **Docs check threshold** is back in
  Settings > Quality, now read. `POST /api/import/check-docs`.
- **Automatic backups.** Settings > Export and backups: every N hours,
  checked at start and every ten minutes, keeping the newest M. Only
  automatic backups are ever pruned; yours and a restore's safety copy are
  kept.
- **Auto-export on save, and a default export format.** After any change to
  the questions, the whole bank is written to the export folder in the
  default format (`exam-bank.csv`, `exam-bank-qti.xml` ...), a couple of
  seconds after the last change, replacing the previous copy. The Bank's
  Export now offers every format, starting on the default. A new install
  starts with auto-export off; **a saved config keeps its own value** - one
  carried over from the Question Bank may have it on.

### Fixed

- **The installer's courses search no longer records a git worktree over
  the main checkout.** On the dev machine it recorded `C:\Projects\pcm-060`,
  a worktree of the Content Manager on an unmerged branch whose courses
  predate the question-id rename, instead of `C:\Projects\Pentaho-Content-Manager`.
  Both held 13 courses. The comment said a tie went to the first found, but
  Sort-Object in Windows PowerShell 5.1 is not stable, and nothing ranked a
  worktree lower anyway. It did no harm there only because the saved config
  names the courses directory; a fresh machine or a reset config would have
  read the worktree. `find-courses.ps1` now ranks a main checkout (`.git`
  directory) above a worktree (`.git` file) whatever the counts, breaks ties
  by the order found, and logs the worktrees it passed over. A worktree on
  its own is still recorded, and a copy with no `.git` at all counts as a
  main checkout. New `-Roots` parameter so tests can search a directory of
  their own (`tests/test_find_courses_script.py`, run under Windows
  PowerShell).

### Removed

- The implementations these replaced: `validate_question_against_docs` and
  the MCP client's error-swallowing layer it used (`check_connection`,
  `search_documentation`, two multi-server searches) with the `mcp_servers`
  and `mcp_enabled` settings nothing set; and `recommend_num_ctx`,
  `MODEL_CATALOG` and `recommend_models`, which added the cards' memory
  together and named models this machine did not have.

## [1.9.0] - 2026-09-30

### Added

- **AI explanation.** A button in the question editor that proposes the
  explanation: why each correct answer is right and each distractor wrong,
  naming every option by its text. It is written from the course page the
  question cites, or else its module's pages (new `core/grounding.py`, which
  reads adopted citations such as "Course: Module — Page (Tab)" as well as lab
  titles), and says which; without a page it says so. An option the text
  never names is listed under the proposal. **Use this explanation** fills the
  field; Save saves it.
- **AI answer key.** A button that proposes which options are correct, from
  the same pages, with the sentence it relied on for each option. It picks
  exactly as many answers as the question asks for ("Which two …?" is two)
  and an answer of another size is refused. **Use this answer** takes the key
  into the editor.
- **A question whose answer was guessed at import says so.** A plain-text
  file marks no answers, so the importer took the first option and tagged the
  question `key-unverified` - and no screen showed the tag. The editor now
  says so at the top of such a question, with **The answer is right** for a
  guess that was correct; taking the AI answer key clears it too. The editor's
  Save now sends the question's tags and key source text, so both stick.

These are the two NiceGUI-era operations kept when the other four were
deleted (`generate_explanation` and `ai_assign_keys`). Both were unreachable;
`ai_assign_keys` also wrote its answer straight onto the question it was
given and read the answer count from a "(Choose two)" note that stems no
longer carry. Both now propose and write nothing, like the AI rewrite and
check, and both follow the house item-writing rules.

### Changed

- **One set of rules decides whether a question can be graded.** The editor
  and import already shared `core/validation.py` (pinned to one fixture for
  Python and TypeScript); generation's auto-fix read a third, older set
  (`Question.validate_detailed`) that disagreed with them - it wanted two
  distractors and passed a stem ending in ".". The auto-fix now reads the
  shared rules, and the old set is gone.
- **Every new question comes in one way** (`core/intake.py`): generation's
  commit and import's commit shared the loop - check, stamp the
  certification, file into the course, save - in two copies that disagreed
  on the check. Import refused a question that could not be graded;
  generation saved it. Now both refuse it and say why, and the Generate
  screen names what was not saved. The editor's Save is refused on the same
  rules server-side, as it already was in the browser.
- **Statuses, difficulties and Bloom levels come from the server**
  (`GET /api/vocabulary`, `frontend/src/vocabulary.ts`). Five screens typed
  seven copies of these lists, and the Admin bulk delete's had drifted. The
  Bank and Admin filters now show the statuses' names ("SME Review").
- `QB_API_PORT` is now `PEB_API_PORT` in `run.bat` and `run-api.bat`; the
  old name still works.

### Fixed

- **Generation's auto-fix no longer asks for explanations "by letter".** Its
  prompt told the model to address each option "(A, B, C, D) individually by
  letter" - in exams whose options are shuffled, so a letter names a
  different option for every candidate. It now asks for every option by its
  text.

### Removed

- **Code a decision had already retired** - about 1,200 lines. PowerPoint
  (dropped as a product decision): `pptx_exporter.py`,
  `pptx_exporter_fallback.py`, `pptx_reader.py`, the PowerPoint answer
  validation in `question_importer`, and the `python-pptx` dependency, which
  the installer no longer ships. `core/question_generator.py`, a re-export
  shim only the tests imported. `spreadsheet_converter.convert_xlsx_to_csv`
  and its command line (xlsx import goes through `import_from_xlsx`). Five
  config fields only the NiceGUI screens used (`theme_color`, `dark_mode`,
  `recent_files`, `file_certifications`, `mermaid_enabled`); an older
  `config.json` still loads. Unbuilt features were left in place: Ollama
  streaming and GPU advice, validating an import against the docs site,
  auto-backup, auto-export and a default export format.
- `regen_stem`, `regen_key`, `regen_distractor` (the AI rewrite covers them)
  and `qa_fix_question`: four AI operations that came across from the NiceGUI
  app and were never reachable from any screen.

## [1.8.1] - 2026-09-30

### Fixed

- **The bulk delete can be narrowed to revised or retired questions.** Its
  status filter was a list typed into the Admin screen, and it had drifted
  from the bank's: `revised` and `retired` were missing. It now comes from the
  lifecycle the server checks statuses against.
- **"Questions per page" is used.** Settings saved it and the Bank always asked
  for 25; the Bank now pages by what Settings says.
- **Switching Course order / Recently updated reloads the Bank on the first
  page.** The sort was left out of what reloads the list, so the change showed
  only after paging or filtering.
- **A course file saved with a byte-order mark is read, not skipped.** A
  Windows editor can add one, and `json.loads` refuses it. Only publishing
  accepted it; everywhere else the error was caught and the file passed over
  in silence - the sync reported the course as unparseable and adopted
  nothing, and the ids already taken left that course's ids out, so a new
  question could be given one of them. Every reader of `exam.json`,
  `course.json` and `manifest.json` now goes through one function
  (`pcm_reader.read_course_json`), and the importer's own `.json` reads accept
  a byte-order mark too.

Each fix has a test that fails with it taken out.

### Removed

- **Three Settings controls that saved a value nothing read:** *Export folder*,
  *Export questions to that folder whenever one is saved*, and *Validation
  threshold* (read only by import-validation functions nothing calls).

## [1.8.0] - 2026-09-30

### Changed

- **Every question the bank files into a course gets an id in the one course
  format, `<course>-m<module>-q<question>`.** On 2026-09-30 every course exam
  moved to that format (`m1-q1` became `di-m1-q1`, `q-preview` `2hr-m2-q1`,
  `kc-q1` `sw-m1-q1`; the map is the Content Manager's
  `docs/question-id-map.csv`), and the Content Manager's `verify-course` now
  fails any other shape. The bank's filing followed each course's old habit
  instead: the next number in a module's family (`m3-q14`, `install-ai-q20`),
  or the course's prefix plus two key words (`q-metadata-injection`). It now
  reads the course's token and each module's number from the course's
  questions, in the bank and in its `exam.json`, and takes the next number in
  the module after the highest used anywhere, so a number a published exam
  still carries is never handed out again. A module with no questions yet
  takes the next module number; a course with no questions yet takes a token
  from its name (`architect-con-specialty` would be `con`).
- **An import renumbers any id that does not fit the course.** Only an id the
  bank had made up (a UUID) used to be replaced, so a file carrying ids from
  another course, or in an older style, put them into the course as they were.
  An id that already fits the course and the question's module is still kept:
  that is how the course and the bank recognise the same question.
- **Moving a course question to another module renumbers it.** Its id names
  its module, so changing its topic gives it the new module's next number. The
  row is renamed and the change recorded in its version history; the editor
  says "Its id is now …" and keeps its Saved message, and the Bank row follows
  the question to its new id. Before this, a save that changed the id left the
  row on the old id (a click then asked for a question that no longer
  existed) and the editor cleared its message, as it does when a different
  question opens. A render test covers both, and fails with either fix taken
  out.

The live bank was renamed in step with the courses (311 questions, one
column, each rename recorded in the question's history, `updated_at` left
alone so the Bank's order does not move): backup
`exam_bank_20260930_085653_pre-standard-ids.db`. A comparison with the course
files afterwards found exactly what it found before: nothing, bar the review
edits not yet published.

### Removed

- The named-id minting (`q-` prefix plus the question's key words) and the
  numbered-family guesswork it sat beside. `scripts/file_into_courses.py`,
  the repair script, now also refiles a question whose id is not in the
  format, unless a published exam carries that id.

## [1.7.3] - 2026-09-29
### Fixed

- **A second Publish and push from the same machine pushes too.** Each push
  clones the courses repo into the app's cache, clearing the previous clone
  first. git writes its object files read-only, and on Windows the clearing
  (`shutil.rmtree(..., ignore_errors=True)`) could not delete them and said
  nothing, so the next clone found a non-empty folder and failed: every push
  after a machine's first. Found re-publishing PDI in 2 Hours, with 76 object
  files left from the morning's push; the exam was written, nothing was
  committed or pushed. The clearing now makes read-only files writable and
  retries, and refuses in words if it still cannot. A test publishes twice from
  one machine; with the old clearing put back it fails with the same message.
- **A refusal over uncommitted files names them whole.** The list lost its
  first character ("ourses/pdi-2hr-lab/exam.json").

With this fix, PDI in 2 Hours was re-published from the bank: course 0.1.13,
its 30 Bloom levels back in the course file and in Pentaho-Courses, each as it
was before the 0.1.12 publish, and every question's keys back in the course's
own order.

## [1.7.2] - 2026-09-29
### Fixed

- **Publishing writes each question's Bloom level.** It never had, and the
  first publish from the bank (PDI in 2 Hours, course 0.1.12, 2026-09-29)
  stripped all 30 levels from the course file and from Pentaho-Courses. The
  Content Manager does not read them, so no learner saw a difference; but the
  course file is where a question's level is recorded, the bank adopts from
  it, and the sync compares it — so all 30 then showed as Changed. The next
  publish of that course puts them back, and changes nothing else.
- **A publish that changes nothing now rewrites nothing.** Questions are
  written with their keys in the order every course's exam.json uses (id,
  module, bloom, scenario, prompt, options, the answer, explanation,
  source). The exporter wrote prompt and options second, so every publish
  reordered every question in the file: the 2hr publish changed 433 lines for
  a handful of real edits. Checked on this machine's bank: publishing BA
  Practitioner, RD Practitioner or Installation, whose questions match their
  course, now leaves each file byte for byte as it was.

## [1.7.1] - 2026-09-29
### Fixed

- **A question generated for a course is filed the way the course files its
  own.** Found in use: a question generated for PDI in 2 Hours and saved into
  the course came in as `03f2c063-39c7-…` among `q-preview` and `q-mi`, with
  no place in the course order, and the lab's title (*One Pipeline, Many
  Files*) where the course files questions under the module (*See It
  Scale*). Saved under a course's certification, a question now gets:

  - **an id in the course's scheme** — the next number in its module's family
    where the course numbers them (`m3-q14`), or the course's prefix and the
    question's key words where it names them (`q-metadata-injection`); never
    an id used in the bank or in any course's `exam.json`;
  - **the course's module as its topic** — the `##` heading of SUMMARY.md its
    lab sits under, which is what the exams use — with the lab as its
    citation and `pcm` as its source type (it was `pptx`);
  - **a place in the course order**, after the last question of its module:
    into a free slot if there is one (a deleted question leaves one),
    otherwise the questions after it move up one, only as far as the next
    free slot. Moving a question to make room is not recorded as an edit.

  The same applies to questions imported into a course from a file that gave
  them no id. An id a file carried, or a course gave, is never changed.
  (`core/course_filing.py`.)

- **One unplaced question no longer scrambles a published exam.** The
  exporter wrote the course order only when EVERY question had a place, so a
  single generated question switched it off for the whole pool and the exam
  would have been written back newest-first. Placed questions now go in
  course order, and any without a place follow.

### Added

- **`scripts/file_into_courses.py`** files the questions an earlier version
  saved with a random id or no place. A dry run by default (on a copy of the
  bank); `--apply` takes a backup first and records each id and module change
  in the question's history. A question already published under its id is left
  alone. Run on this machine's bank, it filed the one such question
  (`q-metadata-injection`, See It Scale, position 27 — the slot `q-hidden-data`
  left), still approved.

## [1.7.0] - 2026-09-28
### Added

- **AI Chat (Content → AI Chat): ask about the app, or about Pentaho's
  products.** A conversation grounded in two sources at once: this app's
  documentation, and Pentaho's product documentation at docs.pentaho.com,
  searched through the MCP server GitBook publishes for the docs site. Each
  retrieved section is numbered — A1, A2 for this app, P1, P2 for Pentaho —
  and the model is told to answer only from them and cite them. Under every
  answer the sources are listed by where they came from; one the answer did
  not cite is shown fainter. An A source opens that page in Documentation at
  its heading; a P source opens the Pentaho page in the browser.

  The rule the old AI & Docs pane had is kept: if neither search finds
  anything, the model is not asked, and the reply says what was searched.
  If docs.pentaho.com cannot be reached, the answer goes ahead from this
  app's documentation and says so under it. Follow-up questions carry the
  conversation, and a short follow-up is searched together with the question
  before it. Two switches choose the sources; at least one stays on. The
  conversation is kept in the window's storage until **New conversation**;
  it is not in the bank or its backups.

  Checked live against docs.pentaho.com and gemma4:12b: "Which ports does
  Pentaho Server use?" was answered from the *Change Ports and URLs* page
  (8080, 9092, 10000) and cited it; a question about sending an approved
  question back was answered from the Review page.

- **Documentation (System → Documentation), laid out like OpenSight's.** A
  sidebar of sections (Start here, Using the Exam Bank, Writing questions,
  AI, Administration, Reference, Project) that doubles as search; each page
  with a breadcrumb, word count and reading time; an **On this page** list
  that follows the scroll; and Previous / Next through the whole set. Links
  between pages move within the screen, and search opens a page at the
  heading it matched. The last page read is remembered.

- **The Pentaho docs connection in Settings.** A new **Pentaho
  documentation** section: a switch (on by default) for whether AI Chat
  searches docs.pentaho.com, the MCP server's address, and its state —
  *Connected*, with the server's name and version, its tools and how long it
  took, or the reason it is not. **Test connection** checks the address in
  the box before it is saved. Off, nothing is sent to the docs site, and the
  screen does not contact it on opening either.

- **Three new pages**: *AI Chat*, *The Pentaho docs connection* and a
  *Glossary* (pool, draw, headroom, Apply+, the certification bars and the
  rest of the screens' vocabulary).

### Changed

- **The How-To Guide is now seventeen pages under `docs/`.** Its sections
  were moved verbatim into `docs/guides`, `docs/writing` and `docs/admin` —
  a script reassembled them and compared line by line — and
  `HOW_TO_GUIDE.md` is now the hub that links every page, so the guide still
  reads on GitHub. The *Settings* page was corrected on the way: it named two
  sections the screen does not have ("AI", "Thresholds"; they are *The
  model* and *Quality*) and listed them out of order.
- **The docs are called from the backend, never the window.** GitBook's MCP
  endpoint sends no CORS headers, so a call from the page is refused before
  it leaves; the backend is not subject to that. `core/mcp_client.py` gains
  `probe` and `search`, which raise with a sentence a person can act on
  rather than returning an empty list, and parses a Server-Sent Events reply
  whose data spans several lines.
- **Search understands forms of a word.** "publish push courses repo"
  ranked a Changelog list above *Publishing to a Course*, which matched none
  of the four words exactly. A small stemmer now lets publish / publishing /
  published, course / courses and status / statuses meet.
- **Heading ids follow GitHub's rule** and are decided once, in the backend;
  the page matches each heading to its id by source line. A link written as
  `INSTALL.md#what-it-connects-to` works on GitHub and in the app alike.
- **Links open in the system browser.** The window is a webview without
  Tauri's APIs, where a `target="_blank"` link goes nowhere, so the backend
  opens `https://` pages (`POST /api/open-url`); any other scheme is refused.
- **The installer ships the whole guide**: the five root documents and the
  `docs/` folders, and the build fails if the guide's pages are missing.

### Removed

- **The AI & Docs screen and `POST /api/docs/ask`**, replaced by AI Chat and
  Documentation.

### Fixed

- **Importing a CSV or JSON file reads the Bloom level the way a course
  import does.** CSV import wrote whatever the file said straight into the
  column, so `apply` was stored as `apply` — a level the bank's own editor
  would refuse. JSON import read only `bloom_level`, so a file using `bloom`
  (the spelling CSV accepts and a course's `exam.json` writes) silently took
  the default. All three importers now share one reader: `bloom`,
  `bloom_level` or `taxonomy`, any case, and anything that is not a Bloom
  level falls back to the default rather than being stored. From the
  `claude/csv-json-bloom` branch, with tests that fail without it.

## [1.6.0] - 2026-09-28
### Added

- **An approved question can be sent back.** Approved used to lead only to
  Retired, so a question reworded after approval kept a status it no longer
  earned. It can now go to **SME Review** or **Draft** as well. Its approval
  date is cleared; the review history still says when it was approved and who
  sent it back. Retiring keeps the date.
- **The scenario and the question are kept apart — by the AI and by the
  editor.** The house form is that a scenario is one to three statements that
  set the scene, never a question, and the question is only the question. It is
  now written down once (`SCENARIO_AND_STEM_RULES`) and given to every prompt
  that writes a question: generation, AI rewrite, the AI fix and stem
  regeneration. AI rewrite is also told to move statements out of the question
  and into the scenario. Generation no longer asks for a "(Choose one.)" at the
  end of each stem, which contradicted 1.5.1.

  A model can ignore what it is told, so the form is also checked in code
  (`stem_text.form_notes`, mirrored in the editor as `formNotes`): a scenario
  that asks a question, a question that opens with statements, two questions in
  one, a stem that is not a question, and a "Choose …" count. The editor shows
  these in amber under the field as you type — advice, never blocking a save —
  the AI rewrite's proposal lists any its model broke, and AI check answers
  reports them beside its own findings. The proposal now shows its scenario
  too; before, you saw the new scenario only after pressing *Use this*.

### Fixed

- **Saving a question now says so, and keeps saying so.** The editor had a
  "Saved" label that never appeared: a save hands the updated question to the
  Bank, the Bank hands it back, and the editor took that as a different
  question and cleared the label in the same moment. It now shows a green
  **✓ Saved at 10:42** that stays until your next edit, and a status move
  shows **✓ Moved to SME Review**. Saving a question that is still approved
  adds a reminder to send it back for review if the change needs one.
- **Status buttons say what they do** — *Send for review*, *Mark revised*,
  *Approve*, *Reject*, *Retire*, *Back to draft* — rather than the name of the
  status they lead to.
- **The Generate screen previewed a count that is no longer written.** Each
  format row said stems would end "Choose two."; since 1.5.1 they hold only the
  question. It now shows how candidates see it: *shown as "(Choose two)"*.

### Documentation

- **The How-To Guide is rewritten for the app as it is.** It still described
  the NiceGUI interface retired before 1.0.0 — PPTX loading, a slide
  filmstrip, Student Preview — and the AI & Docs screen answers from it, so
  questions about the current app were being answered from one that no longer
  exists. It now walks each screen, sets out the question form, the review
  statuses and their moves, the Report's bars, publishing and pushing, and
  what to do when something is refused; its sections are split so the docs
  search finds them.
- **README and INSTALL** no longer say there is no installer and nothing
  publishes back to a course, list the current screens, describe the installed
  app's per-user state, and say what a stem holds. PLAN.md is marked done.

The editor's save message and status moves are tested by rendering the Bank
with a fake server, and both the save test and the form check were watched
failing with the fix removed.

## [1.5.1] - 2026-09-28
### Fixed

- **A "Choose one" typed into a question no longer reaches the learner
  twice.** The Content Manager counts each question's correct answers and
  adds its own "(Choose one)" / "(Choose two)", stripping any bracketed
  count the author wrote. An unbracketed one got through: three questions
  edited in review on 28 Sep 2026 ended "…(PDI)? ↵ Choose One.", and
  published as they stood a learner would have read
  "…(PDI)? Choose One. (Choose one)".

  The stem is now the question only, and the count is presentation, one
  rule in `core/stem_text.py` applied wherever a stem crosses a boundary:

  - **Publish** writes the question only, whatever the stem ends with —
    bracketed or not, "Choose", "Select" or "Pick", "Select all that
    apply". A course file written before the rule is cleaned on its next
    publish, and the plan lists those prompts as changed.
  - **Course sync** compares stems as the question only, so a bank stem
    ending "(Choose one.)" and the prompt it was published as are the same
    question, not an edit to offer back.
  - **The printed exam** adds its own count to a multi-select and no longer
    prints the stem's as well.
  - **Generation and AI assist** store the question only. The model is
    still asked to state its count, so it says what it meant; the count is
    dropped on the way in.
  - **The checker** warned that a multi-select stem "should indicate how
    many to choose", which is what pulled counts into stems in the first
    place. It now warns the other way: a stem ending in a count is flagged,
    because the course adds its own and Publish removes it.

  A sentence that carries the question is never mistaken for a count:
  "Choose two steps that run in parallel." stays whole, and a stem that is
  nothing but a count is left alone rather than published empty.

  Publish, sync, generation, AI assist and the checker were each watched
  failing with their wiring removed. The printed exam has no test that
  reads its text; it uses the same function.

## [1.5.0] - 2026-09-25
### Added

- **Publish can push the exam to the courses repo, so learners get it.**
  Publishing used to stop at the Content Manager's authoring copy of
  `exam.json`, and an installed Content Manager never reads that: it syncs
  from the distribution repo, Pentaho-Courses, at every launch. So a
  published exam reached nobody until someone pushed it by hand. The Publish
  screen now offers **Also push to the courses repo**, ticked whenever a push
  is possible, and the button becomes *Publish and push*. One press:

  1. writes the exam, as before;
  2. bumps the course's version in `course.json` (0.1.11 → 0.1.12), so an
     installer or a synced machine says it carries new content;
  3. adds a line to the Content Manager's CHANGELOG under [Unreleased] naming
     the questions added, edited and removed;
  4. commits exactly those three files in the Content Manager and pushes;
  5. pushes the exam to Pentaho-Courses, where the published `course.json`
     changes one value, its version.

  Installed apps pick it up at their next launch — no installer rebuild,
  which is only ever needed for changes to the app itself.

  **Only the exam is pushed.** The bank owns questions and nothing else, so
  the rest of the course stays exactly as it was published: lab guides,
  certificate settings and workshop paths can depend on a newer installer,
  and pushing them with an exam would be a release nobody decided on.

  **It refuses before writing** when a push cannot succeed, and says why in
  the plan, with the box disabled: no git on the machine; the Content
  Manager repo behind its remote; uncommitted changes in `exam.json`,
  `course.json` or `CHANGELOG.md` that a commit would sweep in; a course that
  was never published whole. And it stops before touching anything — nothing
  bumped, committed or pushed — when the push would put a secret-like value
  into the public repo that is not already there, or when staging reaches
  outside the course's exam. The clone is sparse, one course only: a full
  clone of Pentaho-Courses aborts part-way on Windows over one course's long
  path, and staging from that partial tree would record every other course
  as deleted.

  Git is found on PATH, else the MinGit the Content Editor or the Content
  Manager ships; it uses the machine's own git credentials, as the Content
  Editor's publish does. The repo is `courses_repo_url` in the settings file,
  Pentaho-Courses by default.

  Tested against real git repositories: what lands on each remote is
  asserted path by path, and the secrets and staged-path guards were each
  watched failing with the guard removed.


## [1.4.1] - 2026-09-25
### Added

- **A status bar showing which build is running, and on what.** Along the
  bottom of the window, the way the Content Editor does it: *Exam Bank
  v1.4.1 · Content Manager v0.5.0* — this app's version and the version of
  the Content Manager whose courses it reads, so a screenshot identifies
  itself. The version used to sit faintly in the header; it lives here now.

  The interface's version is baked in at build time and the backend's comes
  over the API. They normally agree and only one is shown. When they differ,
  both are, the second in red, because that is a stale install — part one
  release, part another — and it explains behaviour nothing else would. The
  Content Manager version is read from the `package.json` beside the
  configured courses folder, and simply left out when there is none.

### Fixed

- **The Report no longer calls a scenario on every question a problem.**
  One finding flagged exams whose scenario coverage ran well above their
  Apply+ as "scenarios that do no work", on the theory that framing on a
  recall question was decoration. That was written when scenarios were
  optional. The house standard is now that **every** question sets a
  scenario — an Understand question with one is correct — so the rule fired
  on precisely the exams that had just been brought up to standard: PDI in
  2 Hours and DI Practitioner, both at 100% scenarios, both flagged.

  It and its mirror image ("reaches Apply without scenarios") are replaced
  by the check the standard actually implies: how many questions have **no**
  scenario. A test pins that an exam with a scenario on every question and a
  low Apply+ raises nothing about scenarios.


## [1.4.0] - 2026-09-25
### Added

- **A Report screen: each exam's Bloom breakdown, in the app.** A new
  destination in the rail, between Bank and Exam paper, because you read an
  exam's balance once its questions are in and before you draw a paper from
  it. Pick an exam and it shows:

  - the headline figures: questions, Apply or above, Analyze or above,
    scenario-led, draw headroom, approved;
  - the Bloom classification as one bar from Remember to Create, with a count
    and share per level;
  - the **bar for the exam's certification level**, criterion by criterion,
    with each gap counted in questions rather than percentage points — "3
    questions short" is something an author can sit down and write. A figure
    exactly on its line passes and says so;
  - the same split by workshop, in the order the course teaches them;
  - where every question sits in the review lifecycle;
  - findings, generated from those numbers by the same rules for every exam,
    so one appears only where its numbers trigger it;
  - every question at its level, filterable by level.

  The numbers had been in the bank all along — `get_bloom_counts` was
  computed and served by `/api/stats` and drawn by nothing, a gap
  `docs/PORT-AUDIT.md` recorded when the NiceGUI dashboard did not come
  across. The breakdown was first built as a standalone page for the
  exam review; it lives here now so it reads the live bank instead of a
  snapshot.

  **All the arithmetic is the server's** (`core/report.py`, served at
  `/api/report`). The pane only draws: the bar check and the findings are
  not recomputed in TypeScript, because two copies of the rules would
  disagree the first time one changed. The level and the draw come from the
  course files (`course.json`'s `level`, `exam.json`'s
  `questionsPerAttempt`), since only they know them; with no courses
  directory configured the report still works and says why the bar is
  missing.

  **The bars are defined once, in `core/report.py`** — Level 1 Practitioner
  50 / 15 / 1 / 30, Level 2 Specialty 60 / 30 / 5 / 20, Level 3 Certified
  70 / 40 / 15 / 15 (Apply+, Analyze+ and Evaluate floors, recall ceiling, as
  percentages). They are the figures the 2026-09 exam review applied across
  the Content Manager's courses, and until now they were written down in
  nothing that ran. They follow the usual shape of a certification ladder
  but are a working standard, not an accredited one. A course with no
  `level` — `pdi-2hr-lab`, a try-it lab — is not scored, and the report says
  so rather than drawing an empty bar.

  A Bloom level the bank does not recognise, such as a lower-case `apply`
  from an importer that did not validate, is counted and flagged rather than
  dropped; otherwise an exam's bars would add up to less than its size with
  nothing to say why.

  Tested at both ends: the bar arithmetic is pinned exactly on the line and
  one question either side of it, and the tests were watched failing with a
  strict comparison in place of `>=`, with workshops sorted alphabetically,
  and with the level filter ignored.

- **The navigation rail has tests.** It shipped in 1.3.0 with none: rendered
  and walked by hand, which proves it worked once and nothing about
  tomorrow. A peer session counted the frontend test files at v1.2.0 and at
  HEAD — 13 and 13 — and pointed out that the rail's own changelog entry
  makes four falsifiable claims that nothing checked.

  Thirteen tests. The one that mattered is that the group **headings stay in
  the DOM when the rail is collapsed**: an accessibility claim written into
  a public changelog, a one-line regression for a sighted developer to make,
  and nothing on screen would look wrong afterwards. Watched failing with
  the headings dropped.

  Also pinned: the count beside Bank must not join the button's accessible
  name (it announced itself as "Bank 413" and renamed itself whenever the
  bank grew), and the rail still renders when `localStorage` throws, as it
  does in a private window.

  **The 860px auto-collapse is not covered and the entry should not have
  implied otherwise** — it is a CSS media query with no JavaScript behind
  it, so jsdom cannot exercise it. It was verified by resizing a real
  browser to 768px and reading the computed width back, and the test file
  says so rather than leaving a gap that looks like coverage.


### Changed

- **Parchment, with colour.** The theme was taken whole from the Content
  Editor's parchment, and every part of it was a shade of brown: the paper,
  the lines, the text, the buttons, the current page in the rail. It read as
  "all very brown", and a chart drawn in it made every Bloom level look
  alike. The paper stays warm; what sits on it is not brown any more.

  - Text is a dark slate instead of a dark brown, and the lines and fills
    are near-neutral.
  - The accent is a teal (5.4:1 as text on the paper, and white on it for
    buttons), so buttons, the current page and the charts speak one colour.
  - A **data ramp** joins the theme as tokens (`--data-1` … `--data-6`):
    pale gold through green and teal to deep blue and indigo. Sequential,
    so it still reads as order — light is shallow, dark is deep — while
    each step is its own colour. No red in it; red stays reserved for what
    is wrong.
  - Status pills are coloured by state: draft blue-grey, in review amber,
    revised violet, approved green, rejected red.

  This parts company with the Content Editor, which still opens on the
  brown parchment the two apps used to share.

### Fixed

- **A course edit that only re-levels a question now reaches the bank.**
  Course sync decides whether a question changed by fingerprinting the
  fields in `_CONTENT_FIELDS`, and two of the ten names in that list were the
  database *column* names — `key_answer`, `keys_json` — where the
  attributes are `key` and `keys`. Both read as `None` on every question
  ever fingerprinted. And `bloom_level` was not in the list at all, so a
  course that changed a question's stated Bloom level without touching its
  wording fingerprinted as unchanged and was skipped.

  That is exactly the edit the Content Manager's exam review made across
  eleven exams. It had not bitten only because every level change so far
  arrived with a rewrite. The answer key was never lost either, and that was
  luck: for a course question the key and the distractors partition the
  options, so moving the key moved the distractors and they caught it.

  Fingerprints are computed afresh on both sides at every sync and never
  stored, so upgrading changes nothing about questions already in the bank —
  the next sync simply sees what it should have seen. A test now fails if any
  name in the list is not a real attribute of a question.

- **The frontend build passes its typecheck again.** The navigation-rail
  tests typed their helper's `tab` parameter as the literal `"courses"`, so
  calling it with `"bank"` was a type error, and `npm run build` runs `tsc`
  before `vite` — the build was broken on `main` from the moment those tests
  landed, while vitest, which does not typecheck, stayed green. The
  parameter is a `Tab` now.


## [1.3.0] - 2026-09-25
### Added

- **AI rewrite and AI answer-check, on a question in the editor.** Two
  buttons: *AI rewrite* proposes a better wording, *AI check answers* asks
  whether the question can be answered correctly as written.

  **Both endpoints write nothing.** They return a proposal or a list of
  findings; accepting a rewrite fills the form and the author saves it with
  the same button as any other edit. That is the look-then-act shape
  publishing and importing already use, and here it is not a nicety — a
  model that edited the bank directly would be the only contributor whose
  work nobody reviewed.

  `question_refinement.improve_question` **assigned the model's output
  straight onto the Question it was handed**, so the caller's object came
  back already rewritten and anything that saved afterwards persisted an AI
  edit nobody had accepted. It works on a copy now. That module has carried
  eight AI operations since the NiceGUI layer was deleted, with no caller
  and no test; this is the first of them wired up, and the first test it has
  ever had.

  The answer check is new. `qa_check_question` is a proofreader and says so
  in its own prompt — "Do NOT flag ... answer quality" — so nothing judged
  whether a question was answerable. That is the failure that reached
  production in `analyst-ba-practitioner/ir-q9`: four options, all four
  marked correct, impossible to get wrong, and no automated check noticed
  for as long as it shipped. `review_answers` looks for a wrong key, a
  distractor that is also correct, options that are all correct, a giveaway,
  and overlapping choices.

  Findings are grouped rather than listed flat: an answer fault, a
  proofreading note, and the bank's own deterministic validator are three
  different kinds of news, and one list buries the first under the second.
  An empty result means the reviewer found nothing — **not** that the
  question is certified correct.

- **Topics list in course order, not alphabetically.** A topic's place is the
  earliest pool position any of its questions holds — authors write a pool
  lab by lab, so `MIN(pool_order)` recovers the sequence the workshops teach
  in. `analyst-ba-practitioner` now reads Overview → User Console →
  Interactive Reports → Analyzer Reports → Dashboard Designer, where
  alphabetical opened on Analyzer Reports and left User Console last.

  Both listings were fixed, because they are separately wrong in the same
  way: the bank's own `get_topics` / `get_topic_counts`, and
  `exam_builder.get_available_topics`, which is the one the **exam-paper
  pane** reads and therefore the one an author actually sets weights
  against. It had "Concepts & Terminology" above "Getting Started" in the DI
  mix — the reverse of how the course runs. They now share one
  `_TOPIC_ORDER` clause so they cannot drift apart.

  Topics made only of questions authored in the bank (`pool_order -1`) fall
  to the end rather than jumping the queue, which is what ranking them
  naively by the smallest number would do.

### Changed

- **A navigation rail down the side, in place of the tab row.** Nine
  destinations had outgrown a top bar: they wrapped at narrow widths, and in
  one row they read as nine equal siblings when they are really three stages
  of one job. Grouped **Content** (Courses, Generate, Import), **Questions**
  (Bank, Exam paper, Publish) and **System** (Settings, Admin, AI & Docs),
  with the order inside each group being the order the work happens in.

  The current item is marked with a bar down its left edge rather than the
  underline the tabs used — in a vertical list an underline reads as a
  separator between rows, not as "you are here". Bank carries the bank's
  size, which is the one count worth knowing before clicking.

  Collapses to icons and remembers it, and does so on its own below 860px.
  The group headings stay in the DOM when collapsed: the grouping is the
  point of the rail and should not disappear for a screen reader along with
  the labels. Every `localStorage` access is wrapped — it throws in a
  private window, and a nav that will not render is worse than one that
  forgot it was collapsed.

### Fixed

- **A question authored in the bank no longer publishes with its key at
  option A.** `all_choices` is correct answers followed by distractors, so
  every question the bank created went out key-first — which is how the live
  courses reached 94% "A" in `pdi-2hr-lab`. The options are now permuted
  before they are written.

  **Deterministically**, seeded from the question id. A fresh random order on
  every publish would rewrite every option of every question each time: an
  unreadable diff, and a plan claiming the whole pool had changed when
  nothing had. Seeding from the id means publishing twice writes identical
  bytes while different questions scatter their keys evenly — measured at
  24–26% per position over 4,000 ids.

  A question **adopted from a course keeps its authored order**. That order
  is the author's decision, and rewriting it would churn the file to no
  purpose.

  The Word export got the same treatment and for the same reason: the PDF
  paper and the text export both already shuffled, but `export_docx` wrote
  `[key] + distractors` straight out, so the document read "the answer is A"
  all the way down. It shares the one permutation, so a question sits the
  same way wherever it is written.

  This is belt and braces. The Content Manager now shuffles options per
  attempt at render time, so no learner sees the stored order — what this
  fixes is the file, the printed document, and anything else that reads them.

- **A packaged install no longer falls back to `python` on PATH.** The shell
  resolved its interpreter with
  `vendored_python(...).unwrap_or_else(|| PathBuf::from("python"))`. On a
  machine with the Microsoft Store Python that fallback is actively harmful:
  after an interrupted upgrade removed `python\` from under an install, the
  backend started under a foreign interpreter, got far enough to import the
  app, and died with

      ModuleNotFoundError: No module named 'fpdf'

  naming a dependency, pointing at site-packages belonging to another Python
  entirely, and saying nothing about the real fault — the bundled runtime
  being gone. A bare binary name is only ever right on a machine that happens
  to have the right thing on PATH.

  A packaged build now fails loudly and says the runtime is missing and to
  run the installer again. The fallback survives only for `tauri dev`, where
  there is no vendored runtime and PATH is the correct answer; the two are
  told apart by `<resources>/app/boot.py`, which only a packaged build has.

- **`verify-install.ps1` no longer dies on the failure it just found.** With
  `Set-StrictMode -Version Latest`, reading an unset variable throws — so
  when the backend failed to start, the bank-contents check referenced a
  counter that had never been assigned and the script terminated with a
  PowerShell error instead of printing its verdict. The counters are
  initialised up front. A verifier has to survive the thing it is verifying.


## [1.2.0] - 2026-09-25
### Added

- **The bank browses in course order — the order the workshops teach it.**
  `pool_order` is the position a question held in its course's `exam.json`
  when it was adopted, and the authors write each pool lab by lab, so that
  column already *was* workshop order. Nothing used it: the list query
  hardcoded `updated_at DESC`.

  Topics therefore come out as contiguous blocks for free —
  `analyst-ba-practitioner` reads Overview (0–7), User Console (8–13),
  Interactive Reports (14–23), Analyzer Reports (24–33), Dashboard Designer
  (34–43) — without the bank parsing `SUMMARY.md` or knowing that labs
  exist. The grouping is a consequence of the data, not a feature to
  maintain.

  A **Course order / Recently updated** control sits in the Bank toolbar,
  and `?sort=` on `/api/questions` takes the same two values. Course order
  is the default: 395 of the bank's 405 questions came from a course pool,
  and the old default was already known friction — `BankPane` patches an
  edited row in place specifically so it doesn't jump position on save.

  Questions with no pool position (`-1`: authored in the bank, never in a
  course) sort **last**. Ascending would otherwise open every pool on the
  handful of unfiled drafts. An unrecognised `sort` falls back rather than
  raising — it arrives from a URL, and a typo should not 500 a browse.

### Fixed

- **The Delete button was invisible — red text on a red background.**
  `#a32b1c` on `#a32b1c`, a contrast ratio of **1.00:1**, on every Delete
  in the Bank list and in the question editor.

  Three separate rules had accumulated for `button.danger`. The oldest
  painted `background: var(--bad)` on *every* danger button including the
  `secondary` (outline) variant; a later pair modelled it correctly with
  `:not(.secondary)` but never removed the first, and a third set the text
  colour again with a hardcoded hex instead of the token. The outline
  button ended up taking its background from one rule and its text colour
  from another — both resolving to the same value.

  The same decision written in three places, which is why it could drift
  into contradicting itself. Now written once: `.danger` is red-on-paper at
  5.41:1, `.danger:not(.secondary)` is white-on-red at 7.19:1, both clear
  of WCAG AA.


## [1.1.0] - 2026-09-24
### Added

- **The bank adopts the Content Manager's courses, and keeps them current**
  (`exam_bank/core/course_sync.py`, `POST /api/courses/sync/plan` and
  `/api/courses/sync`, the panel at the top of the Courses pane). A fresh
  install opened on an empty bank while several hundred questions sat in the
  courses the installer had just found. Both halves were behaving correctly
  — the installer ships no database, because that is the author's data and
  not ours — but nobody had introduced them.

  Look-then-act, like publishing: the plan reads and reports and writes
  nothing, and the apply carries the plan's token, so a sync cannot run
  against courses that moved while the summary sat on screen.

  **Idempotent**, which `scripts/migrate_pcm_exams.py` is not — that script
  mints a fresh certification on every run, right for a one-off migration
  and wrong for anything run twice. Certifications are matched on
  `source_ref`, the course slug, never on the title: a title is authored
  prose, and matching on it would split a course in two the first time
  somebody reworded one.

  **A sync never reverts an edit.** A question the bank has since changed is
  reported and skipped unless the author explicitly opts in, and even then
  the review state is kept — the course file has no opinion about it, and
  resetting an approved question to draft would undo work nobody asked to
  undo. These questions were adopted precisely because they had nowhere else
  to be edited; a refresh that quietly overwrote that would make the tool
  unsafe to use.

  **A brand-new bank fills itself on first launch.** Guarded by
  `bank_is_empty`, which requires no questions *and* no certifications:
  that is the whole safety argument for writing unasked, and it stops being
  true the moment the bank holds anything. Failure is logged and swallowed —
  an authoring tool that will not start because it could not read somebody
  else's courses directory is worse than one that starts empty.

- **A question id claimed by two courses is refused, not silently
  overwritten.** Found with real data while verifying the pane, not
  imagined: **30 ids in the live courses are used by two courses each** —
  `m1-q1` belongs to both `architect-install-certified` and
  `developer-di-practitioner`, and `bi-developer-ct`/`bi-developer-me` share
  eleven, `developer-ai`/`developer-sd` seven. The ids are hand-authored per
  course and nothing ever made them unique across courses.

  The questions table is keyed on that id and `save()` is INSERT OR REPLACE,
  so adopting both courses would have written one course's question over the
  other's, moved it to the wrong certification, and reported a completely
  successful sync: 398 questions in git arriving as 365 in the bank, with no
  error and nothing to compare against. The plan now names the other course
  and refuses the id on both sides. `architect-install-certified` is
  currently unadoptable in full because all twelve of its ids collide.

  Refusing is the only honest option a sync has. Making them unique means
  either rewriting ids the Content Manager keys exam results and resume state
  on, or changing the table's primary key — real changes that somebody has to
  choose.

- **The sync reports questions the importer silently dropped.** An entry with
  no prompt or no options never comes back from `import_from_pcm_exam_json`
  and nothing said so, which meant a course holding N questions adopted N-1
  with the only evidence being two numbers nobody was comparing.
  `analyst-ba-practitioner` has one, and now says so.


## [1.0.0] - 2026-09-24

### Added

- **`scripts/bump.py` moves every version carrier at once.** There are now
  **eleven** of them across seven files — Phase 4 brought both
  `package.json`s, both npm lockfiles (which carry the version *twice*
  each, at the top level and in `packages[""]`), `tauri.conf.json`,
  `Cargo.toml` and `Cargo.lock`. VERSION.md described the bump as five
  manual steps across three files, which stopped being a process and
  became a list of chances to miss one.

  It refuses to write anything if a carrier has already drifted, so a
  half-bumped tree is not a state it can reach, and it cuts
  `## [Unreleased]` into a dated release heading with a fresh Unreleased
  above it.

  `tests/test_version.py` now checks all eleven, reading the carrier table
  **from `bump.py`** rather than restating it: two copies of "where the
  version lives" is the same decision in two places, and the first change
  to either would make one of them wrong — which is the exact failure the
  test exists to catch. Watched failing with a hand-drifted `Cargo.lock`
  before being committed.

  The npm lockfiles are the ones to watch: npm rewrites both keys on
  install, silently. The Content Manager's sat six releases behind.

- **Pentaho branding on the installer wizard.** It was shipping NSIS's
  stock blue sidebar and default artwork. `nsis-header.bmp` and
  `nsis-sidebar.bmp` come from the Content Manager's `make-icons.py`, the
  same generator that draws the app icon, so the wizard cannot drift from
  the mark: a black field with the P tile wearing the violet exam badge,
  the Pentaho wordmark, and a violet accent rule under the header wordmark.
  Black sidebar rather than a coloured one because this is a tool, not a
  course — the distinction the Content Editor drew when it split
  `--accent` from `--sidebar-field`.

  ```bat
  python <PCM>\scripts\make-icons.py --nsis-only ^
      --out-dir desktop\src-tauri\icons ^
      --title "Exam Bank" --subtitle "Certification Questions" ^
      --badge exam --badge-color "#7C3AED" --accent "#7C3AED"
  ```

- **`verify-install.ps1` now checks which build it is looking at, and
  whether the courses search ran.** It reported "Everything checked out"
  about an install that was a day old and did not contain the feature
  being verified — every check was true, and all of them were about the
  wrong subject. It now fails when the installed launcher is not the
  latest local build (silent away from a build tree, where there is
  nothing to compare against), and reports separately that
  `provisioning\find-courses.ps1` shipped and that a checkout was
  recorded. Finding no courses is a **warning**, not a failure: a machine
  with no Content Manager is a valid install. Never having searched is a
  failure. Telling those two apart was the entire point.

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
