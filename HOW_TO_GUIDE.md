# Pentaho Exam Bank -- How-To Guide

A step-by-step guide for using the Pentaho Exam Bank to create, manage, and export certification exam questions.

## Table of Contents

- [Getting Started](#getting-started)
- [Loading PPTX Files](#loading-pptx-files)
- [Slide Image Preview](#slide-image-preview)
- [Managing Certifications](#managing-certifications)
- [Generating from PPTX](#generating-questions-from-pptx)
- [Generating from Documentation](#generating-questions-from-documentation)
- [Generating from a PCM Course](#generating-questions-from-a-pcm-course)
- [Reviewing and Editing Questions](#reviewing-and-editing-questions)
- [Question Lifecycle and SME Review](#question-lifecycle-and-sme-review)
- [Importing Existing Questions](#importing-existing-questions)
  - [Two Independent Checks](#two-independent-checks)
  - [AI Key Assignment](#ai-key-assignment)
  - [Import Action Bar](#import-action-bar)
  - [Full Import-to-Bank Pipeline](#full-import-to-bank-pipeline)
  - [Explanation Generation](#explanation-generation)
  - [QA Check](#qa-check)
- [Searching and Filtering the Bank](#searching-and-filtering-the-bank)
- [Student Preview](#student-preview)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Exporting Questions](#exporting-questions)
- [Building PDF Exams](#building-pdf-exams)
- [Settings Tab](#settings-tab)
- [Auto-Backup Schedule](#auto-backup-schedule)
- [Configuring Ollama AI](#configuring-ollama-ai)
- [Using MCP Documentation Servers](#using-mcp-documentation-servers)
- [Using Docs Chat](#using-docs-chat)
- [Admin Tab](#admin-tab)
  - [Dashboard](#dashboard)
  - [Database Management](#database-management)
- [Customizing the UI](#customizing-the-ui)
- [Troubleshooting](#troubleshooting)

---

## Getting Started

### First-Time Setup

1. Run `install.bat` to create a virtual environment and install dependencies.
2. Make sure [Ollama](https://ollama.com/) is installed and running (`ollama serve`).
3. Pull a model: `ollama pull llama3.2` (or any model you prefer).
4. Run `run.bat` to start the app. It opens at `http://localhost:7777`.

### The Interface

The app uses a **2-panel layout** matching the PPTX to Video project:

- **Left Sidebar** -- File management, certifications, generation settings
- **Right Main Area**:
  - **Slide Preview** (top) -- Full slide image with thumbnail filmstrip and speaker notes (only visible on the Generate tab; hidden on all other tabs to maximize canvas space)
  - **Tab Bar** (below preview) -- SETTINGS, GENERATE, BANK, IMPORT, AI & DOCS, EXAM, ADMIN

### Tab Overview

| Tab | Purpose |
| --- | ------- |
| **Settings** | SME management (add/rename/remove/reassign), certification reassignment, quality & detection thresholds (duplicate, validation, questions per page), export settings, app info |
| **Generate** | Generation settings (difficulty, Bloom's, per-question specs), generated questions editor, batch generation (all slides) |
| **Bank** | Search, filter, tag filter, pagination (25/page), mini dashboard, per-row status transitions, bulk actions, undo for deletes, SME assignment, student preview, multi-format export, database backup/restore |
| **Import** | CSV/JSON/Excel/QTI 2.1/Moodle XML import, PPTX/Docs dual-mode validation toggle (auto-detected), AI actions (improve, regen, QA check) |
| **AI & Docs** | Ollama AI config + MCP Documentation Servers (left), Docs Chat (right), model comparison |
| **Exam** | Exam Builder -- generate formatted PDF exam papers with topic weighting, difficulty filtering, randomization |
| **Admin** | Analytics dashboard (ECharts charts, quality metrics, AI insights) + Database management (CRUD, bulk truncate, delete by status/topic, auto-backup schedule) |

---

## Loading PPTX Files

### Drag and Drop

Drag a `.pptx` file directly onto the upload area in the left sidebar. The file is automatically:

1. Copied to `assets/pptx/` for permanent caching
2. Loaded and parsed for titles, body text, and speaker notes
3. Slide images exported in a background thread via PowerPoint COM automation

### Paste a File Path

1. Click the **Add** button in the sidebar.
2. Type or paste the full file path into the dialog.
3. Click **Add** to load.

### Recent Files

Previously loaded files appear in the "Recent" dropdown for quick re-loading. Cached files in `assets/pptx/` persist between sessions.

### PPTX Caching

When you upload a PPTX file:

- The file is copied to `assets/pptx/{filename}.pptx`
- Slide images are exported to `assets/pptx/{filename}/slide_001.png`, etc.
- On subsequent loads, cached images are used instantly (no re-export needed)
- Re-uploading the same filename replaces the cached version and re-exports images

> **Important**: Questions require **speaker notes** on the slides. The correct answer (key) must be traceable to the speaker notes text. Slides without notes will be skipped during generation.

---

## Slide Image Preview

The slide preview sits at the top of the main area and shows:

### Slide Image

- Full slide rendered as a PNG image via PowerPoint COM automation
- Pixel-perfect rendering of all shapes, charts, SmartArt, and formatting
- Falls back to a Pillow-based renderer if PowerPoint is not installed (cross-platform)

### Thumbnail Filmstrip

- Horizontal scrollable strip of slide thumbnails below the main image
- Click any thumbnail to jump to that slide
- Current slide has a highlighted border
- If images are still exporting, numbered placeholders are shown (green = has notes, orange = no notes)

### Speaker Notes

- Displayed in the right column next to the slide image
- Character count shown in the header
- Read-only view -- edit notes in PowerPoint and re-upload

### Navigation

- Previous/Next buttons with keyboard-friendly layout
- Slide counter (e.g. "3 / 10")
- Slider for quick navigation on large decks

### Content Badges

Below the slide image, badges show:

- "Has Title" -- if the slide has a title shape
- "X chars body" -- character count of body text
- "X chars notes" -- character count of speaker notes
- "No Notes" -- warning badge if notes are missing

---

## Managing Certifications

Certifications let you organize questions by exam. Each certification has a **source type**: PPTX (questions generated from slides), Docs (from MCP documentation), or PCM (from a Pentaho Content Manager course's content).

### Create a Certification

1. In the sidebar, find the **Certifications** section.
2. Type a name (e.g. "SE Certification 2026") in the text input.
3. Select the **Source** type: "PPTX" for slide-based, "Docs" for documentation-based, or "PCM" for a PCM course. (For PCM, it's easier to use the **PCM Course** picker below, which creates the certification for you -- see [Generating from a PCM Course](#generating-questions-from-a-pcm-course).)
4. Click the **+** button.

### Assign a Certification to a Deck

1. Select the certification from the "Active Certification" dropdown.
2. Any files you load will automatically be assigned to the active certification.
3. You can also select a different certification while a file is selected to reassign it.

### Reassign Questions Between Certifications

1. Go to the **Settings** tab > **Reassign Questions by Certification**.
2. Select the "From" and "To" certifications.
3. Click **Reassign** to move all questions from one certification to another.

### Delete a Certification

Click the trash icon next to a certification name. You cannot delete a certification that has questions assigned to it -- reassign or delete those questions first. Deleting a certification automatically refreshes the sidebar (certifications list, topic dropdown, file list, and recent files).

---

## Generating Questions from PPTX

### Configure Generation Settings

In the **Generate** tab under **Generation Settings**:

- **Difficulty** -- Easy, Medium, or Hard
- **Bloom's Level** -- Remember, Understand, Apply, Analyze, Evaluate, or Create
- **Per-question specs** -- Add rows with independent Keys and Distractors counts per question. Each row shows "Single" or "Multi" and total choice count. Use +/- buttons to add or remove question specs.

### Generate from Slides

1. Make sure a PPTX file is loaded and a PPTX certification is assigned.
2. Make sure Ollama is enabled and a model is selected (AI & Docs tab).
3. Navigate to the slide you want to generate from.
4. Click **Generate** in the action bar below the slide preview (or press **Ctrl+G**).
5. The app auto-switches to the **Generate** tab where results appear.

### Batch Generation (All Slides)

To generate questions from every slide at once:

1. Click the **Generate All Slides** button in the action bar.
2. The app processes all slides that have speaker notes in a single batch.
3. Slides without speaker notes are automatically skipped.
4. Results appear in the Generate tab as they are produced.

### What Happens During Generation

For each slide with speaker notes:

1. The AI receives the slide title, body text, and speaker notes.
2. It generates the requested number of questions following certification exam best practices.
3. Each question's key (correct answer) is validated against the speaker notes.
4. Questions that fail validation are tagged for manual review; text-format imports (A:/B:/C: style) are tagged as "key-unverified" since the correct answer is unknown.
5. Duplicate questions (similar stem to existing bank questions) are automatically skipped.

### Question Types

The generator creates a mix of:

- **Single-select** (70%) -- One correct answer, 2-4 distractors
- **Multi-select** (30%) -- "Which two..." or "Which three..." with multiple correct answers

---

## Generating Questions from Documentation

For certifications based on MCP documentation (not PPTX slides):

### Docs Generation Setup

1. Create a certification with **Source = "Docs"** in the sidebar.
2. Configure MCP documentation servers in the **AI & Docs** tab.

### Generate from Docs

1. Select your Docs certification from the sidebar dropdown.
2. The slide preview panel changes to show **"Documentation Source"** with a teal book icon.
3. Type a specific search topic in the sidebar **Topic** field (e.g. "Archive Installation").
4. The preview panel shows your topic and configured MCP servers.
5. Click **Generate from Docs** in the action bar.
6. The app searches MCP documentation servers for your topic, then generates questions from the results.

### Tips for Docs-Based Generation

- Be specific with your topic -- "Archive Installation" produces more focused questions than just "Archive"
- You can generate multiple batches by changing the topic and clicking Generate again
- Questions are marked with a "Docs" badge in the Bank tab
- The same review, save, and lifecycle workflow applies as for PPTX-generated questions

---

## Generating Questions from a PCM Course

Generate questions grounded in a **Pentaho Content Manager (PCM)** course's own content -- the lab `guide.md` files -- then export them back into that course as an `exam.json`. This closes the loop: PCM course content -> Exam Bank -> `exam.json` -> PCM.

### One-Time Setup

1. Open **Settings -> Output** and set the **PCM courses directory** -- the folder that holds the PCM courses (each subdirectory is a course with a `course.json` and lab folders). If a sibling `Pentaho-Content-Manager/courses` exists next to this app, it is pre-filled.

### Pick a Course (and optionally a Lab)

1. In the sidebar **PCM Course** section, choose a course from the dropdown. This **find-or-creates** a certification with **Source = "PCM"** bound to that course (`source_ref` = course slug) and makes it the active certification.
2. (Optional) Use the **Lab / module** dropdown to scope generation to a single lab instead of the whole course. Leave it on **"(Whole course)"** to use everything.
3. Use the **refresh** button beside the course dropdown to rescan the courses directory after adding/removing courses.

### Generate from the Course

1. Configure difficulty, Bloom's level, and per-question key/distractor specs in the **Generate** tab (same as other sources).
2. Click **"Generate from PCM course"** in the action bar.
3. Each lab `guide.md` is split into sections on `##` headings; PCM rendering markup (tab widgets, HTML buttons, `<dfn>` tags, image/link syntax) is stripped so the model grounds on plain prose. Each section produces questions whose **key is traced to the course text** (`key_source_text`).
4. The section heading becomes the question's **topic** -- which maps to the PCM `module` label on export.

### Export Back to PCM

1. In the **Bank** tab, filter to the course's certification (and ideally **Approved** status).
2. Click **PCM Exam** to write an `exam.json` (single- and multi-select supported).
3. Drop the `exam.json` into that course's directory in PCM and run `npm run reseed-content`. The exam renders in the PCM dock.

### Tips for PCM-Based Generation

- Questions carry a **"PCM"** badge in the Bank tab.
- Whole-course generation produces a lot of questions (one batch per section); scope to a single lab, or lower the per-question count, to keep runs fast.
- Review and approve as usual before exporting -- only export what you trust.

---

## Reviewing and Editing Questions

### The Generated Tab

Each generated question appears as a card showing:

- Difficulty and Bloom's level badges
- Format label (e.g. "Single (4 choices)" or "Select 2 (5 choices)")
- The question stem
- Correct answers (green check) and distractors (grey X)
- Source slide reference and key source text
- Explanation (expandable)
- Validation warnings (if any)

### Editing a Question

1. Click the **edit** (pencil) icon on a question card.
2. The edit form appears with fields for:
   - Scenario, question type, stem
   - **Answer Options** -- A unified list showing all options (keys + distractors) with:
     - **Letter prefix** (A:, B:, C:, etc.) for reference
     - **Text input** for editing the option text
     - **Key/Dist toggle** -- Click the green "Key" or grey "Dist" button to reclassify any option as correct or incorrect
     - **Reorder arrows** -- Move options up or down in the list
     - A summary shows the current count (e.g. "3 key(s), 2 distractor(s)")
   - Key source text, explanation, difficulty, Bloom's level, topic
3. Click **Apply** to save changes or **Cancel** to discard.

### Targeted Regeneration

Each question card has small refresh buttons for surgical AI regeneration:

- **Stem refresh** -- Regenerate only the question stem (all choices stay locked)
- **Key refresh** (green, per correct answer) -- Regenerate a single correct answer (stem and distractors stay locked)
- **Distractor refresh** (grey, per distractor) -- Regenerate a single distractor (stem and keys stay locked)

### AI Improve

Click the **magic wand** icon to have the AI improve a question. This refines the wording, distractors, and explanation while keeping the key grounded in the original source.

### Version History

Every edit to a saved question is tracked with field-level diffs. The `record_edit()` function is called for every field edit in both the Bank and Admin tabs.

- **Automatic tracking** -- When you edit a question in the Bank or Admin tab, changes to each field (stem, key, distractors, explanation, etc.) are recorded with a timestamp and version number.
- **Color-coded diffs** -- The version history panel shows changes with red strikethrough text for old values and green text for new values, making it easy to see exactly what changed.
- **View history** -- In the Bank tab edit dialog, expand the "Version History" panel to see all past edits in reverse chronological order.
- **Audit trail** -- Each entry shows the timestamp, version number, which field changed, and who made the edit (if an SME name is set).

### Saving Questions

- **Save one** -- Click the save icon on an individual card
- **Save All to Bank** -- Saves all generated questions at once
- **Clear All** -- Discards all generated questions

---

## Question Lifecycle and SME Review

### Status States

| Status | Meaning |
| ------ | ------- |
| **Draft** | Newly created, not yet reviewed |
| **SME Review** | Submitted for Subject Matter Expert review |
| **Revised** | Sent back for revision after review |
| **Approved** | Accepted for use in exams |
| **Rejected** | Not acceptable (with reason recorded) |
| **Retired** | No longer in active use |

### Allowed Transitions

```text
draft       -> sme_review, rejected
sme_review  -> revised, approved, rejected
revised     -> sme_review, approved, rejected
approved    -> retired
rejected    -> draft (rework)
retired     -> draft (reopen)
```

### Moving Questions Through the Lifecycle

1. Open the **Bank** tab.
2. Find the question you want to transition.
3. Use the **per-row status dropdown** on the right side of each question card. It only shows valid transitions for that question's current status (enforced workflow).
4. For rejections, a dialog will ask for a reason/comment.
5. All transitions are recorded in the question's review history with your SME name and timestamp.

### Bulk Transitions

1. Select multiple questions using the checkboxes.
2. Choose a target status from the **"Transition to"** dropdown.
3. Optionally select an SME from the **"Assign SME"** dropdown (type to add new names).
4. Click **Apply to Selected**. Questions with invalid transitions are skipped with a count.

### Workflow Reference

The Bank tab displays the workflow: Draft -> SME Review -> Approved / Revised / Rejected. Rejected -> Draft. Approved -> Retired.

### Setting Your SME Identity

Go to **Settings** tab > **Your Identity (SME)** and enter your name. This name appears in all audit trail entries.

---

## Importing Existing Questions

If you already have questions in CSV, JSON, Excel, QTI 2.1, or Moodle XML format, you can import and validate them.

### Import Steps

1. Go to the **Import** tab.
2. Expand the **Import Settings** panel and optionally select a **Default certification** — this auto-detects the validation mode (PPTX or Docs) and auto-loads the linked PPTX file if applicable. The selected certification and topic are applied to all imported questions as defaults.
3. Optionally select or create a **Default topic** — the dropdown filters by the selected certification.
4. Expand the **Upload Questions** panel and upload a CSV, JSON, Excel (.xlsx), QTI 2.1 (.xml), or Moodle XML (.xml) file using drag-and-drop or the file browser. You can also reload from a **Recent Bank CSV**.
5. Imported questions appear as cards with "Not validated yet" status. Each card shows a question number (e.g. "Q1 of 15") and has labeled action buttons.
6. **Reassign per question** — Each card has its own Certification and Topic dropdowns. You can assign different questions to different certifications or topics without opening the edit dialog. This means a single import can feed questions into multiple certification tracks.

### QTI 2.1 and Moodle XML Import

You can import questions from other LMS platforms:

- **QTI 2.1** -- Standard format exported from Canvas, Blackboard, and other LMS platforms. Upload the XML file (or a .zip package containing QTI XML).
- **Moodle XML** -- Exported from Moodle's exam bank export feature.

The importer **auto-detects the format** by inspecting the root XML element -- no manual format selection is needed. Imported questions feed into the same validation and review pipeline as CSV/JSON/Excel imports.

### Two Independent Checks

Imported questions go through **two independent checks** that serve different purposes:

| Check | What it compares | Compared against | Threshold | Display |
| ----- | ---------------- | ---------------- | --------- | ------- |
| **Validation** | Correct answer text (key) | Slide speaker notes (PPTX) or MCP documentation (Docs) | Configurable (default 70%) word overlap or AI analysis | Green/red pass/fail badge with slide number and match quality |
| **Duplicate detection** | Question stem | All existing stems in the exam bank | Configurable (default 85%) word overlap | Orange badge: "Possible duplicate (92% match): existing stem..." |

**Validation** confirms that the correct answer is supported by the source material (speaker notes or documentation). For questions with known keys, the percentage shown (e.g. "Fuzzy match 75% overlap in slide 3") measures how much of the answer text appears in the notes. For text-format imports where the correct answer is unknown, AI analyzes the speaker notes and slide image to determine which options are keys vs distractors (see [AI Key Assignment](#ai-key-assignment) below).

**Duplicate detection** checks whether a similar question already exists in the bank. This runs automatically at import time and again at save time as a final gate. The percentage shown (e.g. "92% match") measures stem-to-stem word overlap against bank questions — it has nothing to do with speaker notes.

> **Note**: Duplicate detection checks imported questions against the bank only, not against each other within the same import batch.

### AI Key Assignment

When importing questions from text format (A:/B:/C: style options), the app does **not** guess which options are correct. Instead, multi-select questions are imported with all options as distractors and tagged `key-unverified`. When you click **Validate** (single or batch), the app uses AI to determine the correct answers:

1. **Speaker notes + slide image** are sent to Ollama along with all the question's options.
2. The AI identifies which options are supported by the source material and returns the correct letter(s).
3. Options are split into **keys** (correct) and **distractors** (incorrect) based on the AI's response.
4. The `key_source_text` field is populated with the exact quote from the notes that supports the key.
5. The `key-unverified` tag is removed and the question is marked as validated.

**Requirements for AI key assignment:**
- Ollama must be enabled with a model selected (AI & Docs tab)
- The question must have a `key-unverified` tag (set automatically for text-format imports)
- A PPTX file must be loaded with speaker notes on the referenced slide

If Ollama is unavailable, text-match validation is used as a fallback — but this requires the question to already have keys assigned.

### Validation Modes

The Import tab supports two validation modes, shown as a colour-coded **PPTX / Docs toggle** in the Import Settings (PPTX = blue, Docs = teal):

**PPTX mode** (blue — for slide-based certifications):

1. Selecting a PPTX certification auto-loads its linked PPTX file for validation.
2. Click **Validate All** to check all imported questions against the speaker notes.
3. **AI path** (text-format imports with no keys): Ollama analyzes speaker notes + slide image to determine which options are correct. Runs in a background thread with progress notifications every 3 questions.
4. **Text-match path** (questions with existing keys): Checks key text against speaker notes with configurable word overlap threshold (default 70%, adjustable in Settings). The referenced slide is checked first, then all other slides as fallback.
5. Passing questions are automatically assigned the matched slide number and source file.

**Docs mode** (teal — for documentation-based certifications):

1. Selecting a Docs certification auto-switches to Docs mode.
2. Requires MCP documentation servers to be configured and enabled in the **AI & Docs** tab.
3. Click **Validate All** to search MCP servers for each question's correct answer.
4. Validation checks for exact text matches or word overlap above the configured validation threshold (default 70%) in the documentation.

The mode is auto-detected from the certification's source type, but you can manually override it with the toggle (e.g., to validate PPTX-sourced questions against docs, or vice versa).

Each question shows pass (green), fail (red), or pending (grey) status. A status badge below the toggle shows what source is loaded (e.g., "PPTX: intro.pptx" or "Docs: 3 MCP server(s) available").

### Import Action Bar

The action bar above imported questions provides labeled buttons:

| Button | Ollama? | Threading | Description |
| ------ | ------- | --------- | ----------- |
| **Validate All** | Sometimes | Auto-detected | Check all answers against speaker notes or MCP docs; uses AI for key-unverified questions |
| **Explain** | Yes | Background | Generate source-backed explanations for validated questions lacking one |
| **QA All** | Yes | Background | Run grammar/spelling/syntax check on all questions |
| **Save Passed** | No | Synchronous | Save only validated (passed) questions to the bank |
| **Save All** | No | Dialog | Shows confirmation with count of unvalidated questions, then saves |
| **Clear All** | No | Dialog | Shows confirmation before removing all imported questions |

Ollama-dependent batch operations (Explain, QA All, and AI-powered Validate All) run in a **background thread** to avoid overwhelming the Ollama connection. Progress notifications appear every 3-5 questions (e.g. "AI validating: 3/12", "Explanations: 5/12", "QA progress: 10/20"). Validate All auto-detects whether AI is needed: if any questions have `key-unverified` tags, it runs in a background thread with AI; otherwise it runs synchronously with fast text matching.

Each question card has labeled per-card action buttons: **Edit**, **Validate**, **QA**, **Save**, and **Delete**.

### Full Import-to-Bank Pipeline

The recommended workflow for importing questions from text format into the bank:

1. **Import** -- Upload a CSV, JSON, or Excel file. Questions appear as cards with "Not validated yet" status. Text-format multi-select questions have all options as distractors (no guessing) and are tagged `key-unverified`.

2. **Validate All** -- Click the validate button. For `key-unverified` questions, AI analyzes speaker notes + slide image to assign correct keys. For questions with existing keys, text matching validates them against notes. Imported question text (stem, scenario, keys, distractors) is never modified — only the classification of which options are keys vs distractors changes.

3. **Review & Edit** -- Click Edit on any question card to open the edit dialog. The dialog includes:
   - **Certification & Topic dropdowns** -- Reassign the question to a different certification or topic directly in the dialog
   - **Toggle Key/Distractor** -- Click the "Key" or "Dist" button next to any option to reclassify it
   - **Reorder options** -- Use arrow up/down buttons to change the display order
   - **Edit text** -- Modify any option's text directly in the input field
   - **AI actions** -- Use AI Improve, Regen Stem, or QA Check buttons within the dialog

4. **Generate Explanations** -- Click the explanations button. AI generates source-backed explanations for all validated questions, citing why each answer is correct or incorrect. Displayed with colour-coded formatting (green for correct, red for incorrect).

5. **QA All** -- Click the QA button. AI checks grammar, spelling, and syntax across all fields (scenario, stem, keys, distractors). Issues are displayed with severity badges.

6. **Save to Bank** -- Click Save Passed (validated only) or Save All. Before writing to SQLite:
   - All required fields are verified via `validate_detailed()`
   - Internal tags (`qa:*`, `key-unverified`, `key-not-validated`) are stripped
   - Duplicate stems (configurable threshold, default 85% overlap) are detected and skipped
   - Questions are saved with full metadata (certification, topic, source slide, explanation, etc.)
   - A CSV is auto-exported to `assets/questions/{Certification}/{Topic}.csv`

### Import Settings

The collapsible Import Settings panel provides:

- **Default certification** -- Dropdown to select which certification imported questions are assigned to. You can change this per question after import using the per-card certification dropdown.
- **Default topic** -- Dropdown filtered by certification, with option to create new topics. Also changeable per question after import.
- **Validation mode (PPTX / Docs toggle)** -- Colour-coded toggle (PPTX = blue, Docs = teal). Auto-detected from certification source type, with manual override. A status badge shows the loaded source (e.g. "PPTX: intro.pptx" or "Docs: 3 MCP server(s) available").
- **Auto-fix warnings** -- Checkbox (off by default). When enabled, AI may rewrite keys/distractors to fix quality warnings after validation. Off by default to preserve imported text exactly as-is.

### Per-Question Reassignment

Each imported question card includes its own **Certification** and **Topic** dropdowns. This allows you to:

- Assign different questions from the same import to different certifications
- Spread questions across multiple topics in one import session
- Reassign questions without opening the full edit dialog

These per-card dropdowns update the question immediately — no need to click Apply.

### Explanation Generation

The **Generate Explanations** button (auto-fix icon) creates source-backed explanations from speaker notes:

- **When to use** -- After running Validate All so that questions have matched slides. Click the Generate Explanations button to process all validated questions in the background.
- **Single-question** -- Validating a single question (per-card validate button) auto-generates its explanation immediately if Ollama is enabled.
- **What it produces** -- A concise 2-4 sentence explanation citing specific facts from the speaker notes. Each choice (correct and incorrect) is addressed with a reason.
- **Format** -- "'choice text' -- Correct/Incorrect: reason citing notes." for each key and distractor.
- **Storage** -- Stored in the question's `explanation` field (~200-500 bytes per question). Persists when saved to the bank and is included in all exports.
- **Skipped when** -- The question already has an explanation, Ollama is disabled, or no speaker notes are available on the matched slide.

### QA Check

The **QA All** button (spellcheck icon) runs an AI proofreading pass on imported questions:

- **What it checks** -- Spelling errors, grammar mistakes (subject-verb agreement, tense, articles, punctuation), and syntax issues (missing punctuation, broken sentences) across four fields: scenario, stem, key(s), and distractor(s).
- **What it does NOT check** -- Style preferences, question design, answer quality, or exam best practices. It focuses purely on language correctness.
- **Results display** -- Each issue shows an error/warning icon, a field badge (e.g. "stem", "distractor"), and the specific issue with a suggested correction. The expansion header shows counts: "QA: 2 error(s), 1 warning(s)".
- **Auto-fix** -- When running QA on a single question, issues are automatically fixed (up to 3 attempts) and re-checked until the question passes or the maximum attempts are reached.
- **QA All** -- Runs the check on all imported questions in the background. Progress shown every 5 questions. Issues are stored as tags and displayed in expandable panels on each question card.

### Save to Bank

- **Save Passed to Bank** -- Only saves questions that passed validation
- **Save All to Bank** -- Saves everything (including unvalidated)
- Duplicate questions (stem overlap above the configured duplicate threshold, default 85%) are automatically detected and skipped at save time
- Questions are also checked for duplicates at import time with an orange warning badge
- **CSV auto-export** -- On save, a CSV is automatically exported to `assets/questions/{Certification Name}/{Topic}.csv`. If the file already exists, new questions are merged without duplicating existing entries. This provides a file-based backup organized by certification and topic.

### CSV Format

The CSV importer supports two modes:

**Simple import** -- Minimal columns for new questions:

| Column | Required | Aliases |
| ------ | -------- | ------- |
| Stem | Yes | stem, question |
| Key | Yes | key, answer, correct |
| Distractor 1-4 | No | distractor_1, distractor1, d1, wrong_1 |
| Scenario | No | scenario, context |
| Explanation | No | explanation, rationale, feedback |
| Topic | No | topic, subject, category |
| Difficulty | No | difficulty, level (defaults to "Medium") |
| Bloom Level | No | bloom, bloom_level, taxonomy (defaults to "Apply") |

**Full round-trip** -- All 27 columns from a CSV export are preserved on re-import, including ID, status, question type, keys, certification, SME, timestamps, source slides, tags, and reject reason. Missing columns default to sensible values.

For multi-select questions, separate multiple keys with `|` in the Key or Keys column (e.g. `Answer A|Answer B`).

A sample CSV is provided at `assets/questions/sample_import.csv`.

### Excel (.xlsx) Format

The Excel importer auto-detects two common column layouts:

**Direct mapping** -- Columns named Question/Stem, Answer/Key, Distractor 1-4:

| Column | Maps to |
| ------ | ------- |
| Question / Stem | Stem |
| Answer / Key / Correct Answer | Key (correct answer) |
| Distractor 1-4 / Wrong 1-4 | Distractors |
| Scenario / Context | Scenario |
| Explanation / Rationale | Explanation |
| Topic / Subject / Category | Topic |
| Difficulty / Level | Difficulty |

**Option columns with indicator** -- Columns named Option A/B/C/D (or Choice 1-4) with a separate "Correct" column:

| Column | Purpose |
| ------ | ------- |
| Question | The question stem |
| Option A / Choice 1 | First answer choice |
| Option B / Choice 2 | Second answer choice |
| Option C / Choice 3 | Third answer choice |
| Option D / Choice 4 | Fourth answer choice |
| Correct | Which option is correct: "A", "B", "C", "D" (or 1-4) |

**Multi-sheet support:**
- Each sheet tab in the workbook is processed independently
- Sheet names are used as the default **Topic** when no Topic column exists
- Sheets named "Instructions", "README", "Notes", or "Template" are automatically skipped
- Merged cells are handled — the merged value is filled into all rows

**Backup:** When importing from Excel, the converted CSV is automatically saved to `assets/questions/` as a backup.

### JSON Format

```json
[
  {
    "stem": "Which option describes...?",
    "key": "The correct answer",
    "distractors": ["Wrong 1", "Wrong 2", "Wrong 3"],
    "scenario": "A company is...",
    "explanation": "Because...",
    "topic": "Security",
    "difficulty": "Medium"
  }
]
```

---

## Searching and Filtering the Bank

The **Bank** tab is organized into four collapsible sections, each with help text explaining what it does.

### 1. Dashboard

The collapsible **Dashboard** section shows an at-a-glance overview:

- **Status counts** -- Total, draft, SME review, revised, approved, rejected, retired
- **Approval progress** -- Visual bar showing "X of Y approved (Z%)" with colour coding (green ≥80%, warning ≥50%, red <50%)
- **Difficulty distribution** -- Easy / Medium / Hard breakdown badges
- **Low-coverage alerts** -- Topics with fewer than 5 questions, shown with a warning icon

When the bank is empty, the dashboard shows a friendly empty state with guidance on how to add questions.

### 2. Search & Filters

The collapsible **Search & Filters** section provides:

- **Text search** -- Searches across stems, scenarios, keys, and explanations (press Enter or click Search)
- **7 filter dropdowns** -- Certification, Topic, Difficulty, Bloom, Status, SME, Tag
- **Auto-refresh** -- Changing any filter automatically refreshes results (no need to click Search after changing a dropdown)
- All filters are AND-combined

### 3. Bulk Actions & Export

The collapsible **Bulk Actions & Export** section contains:

**Bulk Actions:**
- Select questions with checkboxes, then choose a status transition or SME assignment
- **Apply to Selected** -- Transitions selected questions and assigns SME
- **Delete Selected** -- Shows a confirmation dialog before deleting (with 10-second undo window)

**Workflow Reference** -- A collapsible sub-panel showing all valid status transitions:
- Draft → SME Review (submit for review)
- SME Review → Approved / Revised / Rejected (reviewer decision)
- Revised → SME Review (resubmit after changes)
- Rejected → Draft (send back for rework)
- Approved → Retired (end of life)

**Export:**
- 6 format buttons with descriptive tooltips: CSV, JSON, QTI 2.1, Moodle XML, Text, DOCX
- Exports respect all active filters -- a notification shows the count and active filters before downloading
- **Student View** -- Opens practice mode with score tracking

### Pagination

Results show "Showing X–Y of Z questions" with prev/next navigation. The page resets to 1 whenever you change a filter. Change the page size in the **Settings** tab under **Display**.

### Question Cards

Each question card shows:

- **Question number** (e.g. "Q1", "Q12") for easy reference
- Status badge, difficulty, Bloom's level, format, topic, assigned SME, tags
- Full stem with scenario, all choices with correct/incorrect colour coding
- **Explanation expanded by default** for review workflow
- Rejection reason (if rejected) with block icon
- Timestamps (created by, reviewed, approved)
- Per-row **status transition dropdown** for quick workflow changes
- Labeled **Edit** and **Delete** buttons (not just icons)

### Undo for Deletes

When you delete a single question or use bulk delete, the questions are **staged for 10 seconds** with an undo bar at the top of the Bank tab. Click **Undo All** to re-insert the deleted questions. After 10 seconds, the deletion is finalized and cannot be undone.

### 4. Database Backup & Restore

The collapsible **Database Backup & Restore** section at the bottom provides:

- Database info (location, size, last modified)
- Create timestamped backups with optional labels
- Restore from any backup (with confirmation dialog and automatic safety backup)
- Delete old backups

---

## Student Preview

The **Student Preview** is a dialog-based practice mode opened from the Bank tab. It lets you experience questions as a student would during an exam.

### Opening the Preview

1. Go to the **Bank** tab.
2. Click the **Student Preview** button (mortarboard icon) in the action bar.
3. A full-screen dialog opens with the practice session.

### How It Works

- Questions are presented **one at a time** with shuffled answer choices.
- Select your answer(s) and click **Submit** to receive immediate feedback.
- Correct answers are highlighted in green; incorrect selections are highlighted in red.
- The explanation is shown after each submission so you can learn from mistakes.
- Navigate through questions using the Next button.

### Score Tracking

- A running score is displayed during the session (e.g. "3 / 5 correct").
- At the end of the session, a **final summary** shows your total score, percentage, and a breakdown of which questions you got right or wrong.

### Tips

- Use the Bank filters before opening Student Preview to practice a specific topic, difficulty, or certification.
- Student Preview uses the currently filtered question set from the Bank tab.

---

## Keyboard Shortcuts

The following keyboard shortcuts are available throughout the app:

| Shortcut | Action |
| -------- | ------ |
| **Ctrl+G** | Generate questions from the current slide |
| **Ctrl+S** | Save all generated questions to the bank |
| **ArrowLeft** | Navigate to the previous slide |
| **ArrowRight** | Navigate to the next slide |

> **Note**: Arrow key shortcuts only fire when no modifier key (Ctrl, Alt, Shift) is held, so they do not interfere with text editing or other shortcuts.

---

## Database Backup & Restore

The **Bank** tab includes a collapsible "Database Backup & Restore" section below the question list.

### Database Location

The SQLite database is stored in the project at `assets/db/exam_bank.db`. App settings are in `assets/config/config.json` (automatically migrated from `assets/db/config.json` on startup). On first run, data is automatically migrated from the old location (`~/.exam_bank/`) if present.

### Creating a Backup

1. Open the **Bank** tab.
2. Expand "Database Backup & Restore".
3. Optionally enter a label (e.g. "before-import").
4. Click **Create Backup**.
5. The backup is saved to `assets/db/backups/` with a timestamped filename.

Backups use SQLite's online backup API for a consistent snapshot, even while the app is running.

### Restoring a Backup

1. Find the backup you want to restore in the list.
2. Click the **restore** (arrow) icon.
3. A confirmation dialog explains what will happen.
4. Click **Restore** to proceed.

A safety backup of the current database is automatically created before any restore, so you can always undo a restore.

### Deleting a Backup

Click the **delete** (trash) icon next to a backup to remove it.

### Database Info

The panel shows the current database location, file size, and last modified date

---

## Exporting Questions

### From the Bank Tab

1. Filter the questions you want to export (or leave unfiltered for all).
2. Click one of the export format buttons:
   - **CSV** -- Full round-trip format (all 27 fields preserved for backup/restore)
   - **JSON** -- Full round-trip format for programmatic access
   - **QTI 2.1** -- Industry-standard XML for Canvas, Blackboard, and other LMS platforms
   - **Moodle XML** -- For Moodle LMS import
   - **DOCX** -- Formatted Word document with metadata, colour-coded correct answers
   - **Text** -- Human-readable with shuffled choices for study guides
3. The file is saved to disk **and** a browser download is triggered.

### Export Location

Exports are saved to `~/Documents/QuestionBank/` by default. Change this in **Settings** tab > **Export Settings**.

### Round-Trip CSV Backup

The CSV export includes all question fields (ID, status, SME, timestamps, certification, source slides, tags, etc.). You can re-import this CSV via the Import tab to fully restore your exam bank. A sample CSV is provided at `assets/questions/sample_import.csv`.

---

## Building PDF Exams

The **Exam** tab lets you create formatted PDF exam papers from your exam bank. It is organized into three collapsible sections, each with help text.

### 1. Exam Configuration

The collapsible **Exam Configuration** section contains a 3-column layout:

**Exam Details** (left column):
- **Exam Title** -- Appears on the PDF cover page (default: "Practice Exam")
- **Institution / Course** -- Optional, shown below the title on the cover page
- **Time Limit (minutes)** -- Set to 0 for no time limit. Shown in the exam instructions

**Question Source** (middle column):
- Select one or more **Certifications** (dropdown shows question count per cert)
- Set the **Total Questions** count and select which **Difficulties** to include (defaults to all)
- Choose which **statuses** to include: Draft, SME Review, Approved (defaults to Approved only)
- If no status is checked, a warning appears: "Defaults to Approved when nothing is selected"
- An info line shows the total available questions, statuses, and topic count

**Topic Weighting** (right column):
- Once certifications are selected, topics appear with question counts
- Set a **percentage weight** for each topic (e.g. 30% / 70%)
- The total must sum to ~100% (colour-coded: green when valid, red when off)
- **Distribute Evenly** button splits weights equally across all topics
- Topics with 0% weight are excluded from the exam
- If no certifications are selected, a friendly empty state guides you

### 2. PDF Options

The collapsible **PDF Options** section provides 5 toggles, each with a tooltip explaining what it does:

- **Randomize question order** -- Shuffle questions within each topic section
- **Randomize answer choices** -- Shuffle A/B/C/D order for each question
- **Include answer key** -- Add an answer key page at the end of the PDF
- **Include scenarios** -- Show the scenario context before each question
- **Include explanations in answer key** -- Add detailed explanations (automatically disabled when answer key is off)

### Generate the PDF

1. Click **Generate Exam PDF** (tooltip: "Build a formatted PDF exam paper from your exam bank").
2. The PDF is saved to the export folder and auto-downloaded in your browser.
3. If fewer questions are available than requested, an info notification shows the actual count.

### 3. PDF Preview

The collapsible **PDF Preview** section shows:
- Before generation: a friendly empty state with 3 numbered steps
- After generation: the PDF in an inline iframe (700px height) with "Open in new tab" and "Download PDF" links

### PDF Layout

- **Cover page** -- Title, institution, question count, difficulty breakdown, topic summary, candidate info fields (name, company, business unit, date), and instructions
- **Questions** -- Grouped by topic with section headers, numbered sequentially, A/B/C/D choices
- **Multi-select** -- Marked with "(Choose N)" after the stem
- **Answer key** -- Compact 3-column grid, or expanded format with explanations

---

## Settings Tab

The **Settings** tab provides app-wide configuration organized into six collapsible sections. Each section includes a brief description explaining what it does, and sections that accept configuration have a **Reset to Defaults** button.

### 1. SME Identity

Manage Subject Matter Experts who create, review, and approve questions. The active SME name is stamped on every question action (create, review, approve, reject) so the team can see who did what.

- **Who is working right now?** -- Select the active SME from the dropdown. Their name appears in the audit trail.
- **Add a new SME** -- Type a name and press **Enter** or click the **+** button. The new SME is automatically set as active.
- **SME list** -- Shows all SMEs with their question count. Each entry has **Rename** and **Remove** buttons.
  - **Rename** opens a dialog where you can also update all existing questions to the new name (keeps the audit trail consistent).
  - **Remove** shows a confirmation dialog. If the SME has questions assigned, you can optionally reassign them to another SME before removing.

### 2. Reassignment Tools

Bulk-move questions between SMEs or certifications. Useful when someone leaves the team or when you restructure certification tracks.

- **By SME** -- Select a source ("Move from...") and destination ("Move to...") SME, then click **Move**.
- **By Certification** -- Same flow for certifications. Each dropdown shows the question count per certification.

### 3. Questions Export Settings

Configure where exported question files are saved and the default file format.

- **Output folder** -- Directory where exported files are saved. Default `assets/questions/`. Use the folder icon to browse or the open-folder icon to view it in Explorer.
- **Default format** -- Preferred format for one-click export. Options: CSV, JSON, QTI 2.1, Moodle XML, Text, DOCX. Each option includes a short description (e.g. "CSV -- spreadsheet-friendly"). Default CSV.
- **Auto-export CSV on save** -- When enabled, every question saved to the bank is also written to `assets/questions/{Certification}/{Topic}.csv`. Useful for maintaining a file-based backup alongside the database. Enabled by default.

### 4. Display

Control how questions are displayed in the Bank and Admin tabs.

- **Questions per page** -- Choose from 10 (fast loading), 25 (balanced, default), 50 (less paging), or 100 (show all). Takes effect on the next page refresh.

### 5. Quality & Detection

Tune thresholds for duplicate detection and import validation. Higher percentages are stricter -- raise them to reduce false positives, lower them to catch more potential matches.

- **Duplicate detection -- Similarity threshold (%)** -- Two questions are flagged as duplicates when their stems are this similar. Default 85%. Range 50-100%. Values are clamped to the valid range.
- **Import validation -- Word overlap threshold (%)** -- Imported questions must overlap this much with the source speaker notes (PPTX mode) or MCP documentation (Docs mode). Default 70%. Range 50-100%.

### 6. App Info & Maintenance

View application paths, database statistics, last backup status, and run maintenance tools.

- **Stats at a glance** -- Total questions, certifications, and database size displayed prominently.
- **Last backup** -- Shows the date, time, and size of the most recent backup. If no backups exist, a warning suggests creating one from the Admin tab.
- **File paths** -- Collapsible sub-section showing the database, config, and backups directory paths.
- **Database Maintenance** -- Two tools to keep the database healthy:
  - **Vacuum Database** -- Reclaims unused space after bulk deletes. Shows how much space was freed.
  - **Check Integrity** -- Runs SQLite's integrity check to verify the database is not corrupted.

> **Tip**: Run Vacuum after deleting many questions, or if the database file seems larger than expected. Use Check Integrity if you suspect data corruption after a crash.

---

## Auto-Backup Schedule

You can configure automatic database backups in the **Admin** tab (Database view).

### Setup

1. Go to the **Admin** tab and switch to the **Database** view.
2. Find the **Auto-Backup** section.
3. **Enable** the auto-backup toggle.
4. Set the **Interval** -- How often backups are created (default: 24 hours).
5. Set **Max Backups** -- Maximum number of automatic backups to keep (default: 5). When the limit is reached, the oldest backup is deleted to make room.

### How It Works

- When enabled, the app uses a background timer (`ui.timer`) to create backups at the configured interval.
- Backups are saved to `assets/db/backups/` with timestamped filenames, just like manual backups.
- The auto-backup schedule persists across sessions (saved in config).
- Auto-backups and manual backups share the same backup directory and are visible in the Bank tab's backup list.

> **Tip**: Enable auto-backup if you are actively building a large exam bank. The default settings (every 24 hours, keep 5) provide a rolling week of backups with minimal disk usage.

---

## Configuring Ollama AI

Ollama is configured in the **AI & Docs** tab (left column). Each card includes help text explaining what it does.

### Ollama Setup

1. Go to the **AI & Docs** tab.
2. Under **Ollama AI** (includes help text explaining that Ollama runs AI locally):
   - **Enable/Disable** -- Toggle with connection status badge (Connected/Not connected/Disabled)
   - **Server URL** -- Default `http://localhost:11434`, with tooltip explaining the address
   - **Model** -- Click Refresh to load available models, then select one. A hint below says "No models listed? Run 'ollama pull llama3.2' in a terminal to download one."
   - **Context Window (num_ctx)** -- Controls how many tokens the model can process at once. Default 8192. Increase for long speaker notes or documentation. Range: 1024–131072, step 1024. Can also be set via `OLLAMA_NUM_CTX` in `.env`.
   - **System Prompt** -- Override the default AI persona. Help text explains: "Leave blank to use the built-in certification exam writer prompt."

### Context Window (num_ctx)

The `num_ctx` setting controls the maximum number of tokens Ollama processes per request. This affects all AI features — question generation, improvement, QA checks, Docs Chat, and AI Insights.

- **Default: 8192** -- Good for most use cases with typical speaker notes
- **Increase to 16384+** if you have very long speaker notes, large documentation context, or complex multi-turn chat conversations
- **Lower values** use less memory but may truncate long prompts
- The setting is applied automatically to all Ollama API calls via the `options.num_ctx` parameter

#### Auto-Detect

Click the **Auto-detect** button next to the num_ctx input to automatically configure based on your hardware:

1. Detects your GPU(s) via `nvidia-smi` (name, total VRAM, free VRAM)
2. Queries the selected Ollama model's maximum context length and parameter size via `/api/show`
3. Calculates an optimal `num_ctx` based on:
   - Available GPU free memory (allocates ~40% for KV cache)
   - Model parameter count (larger models need more memory per token)
   - Model's maximum supported context length (ceiling)
4. Displays GPU info, model capabilities, and the recommended value
5. Saves the recommended value to config

**Adapts to any hardware:**

| Setup | Typical Recommendation |
| ----- | --------------------- |
| No GPU (CPU only) | 8,192 tokens |
| 8 GB GPU + 7B model | ~16,384 tokens |
| 2x 12 GB GPU + 27B model | ~65,536 tokens |
| 48 GB GPU + 70B model | ~32,768 tokens |

You can always override the auto-detected value manually or via the `.env` file.

**Environment variable override:** Set `OLLAMA_NUM_CTX=16384` in your `.env` file to override the UI setting. Environment variables take precedence over `config.json` on startup.

### Recommended Models

The app includes a **Model Recommendations** panel (collapsible, inside Ollama AI settings) that suggests models based on your GPU hardware. Click **Scan Hardware & Show Recommendations** to detect your GPU and see what fits.

Models are organised by use case:

| Category | Best for | Example models |
| -------- | -------- | -------------- |
| **Exam Writing** | Question generation, QA checks | gemma3:27b, qwen3:32b, phi4:14b, llama3.1:8b |
| **All-Rounder** | General tasks, balanced | gemma3:12b, llama3.1:8b, mistral, mixtral |
| **Chat** | Docs Chat, conversational | llama3.1:8b, gemma3:12b, command-r:35b |
| **Code** | Code-related questions | qwen2.5-coder:32b, deepseek-coder-v2, codellama |
| **Vision** | Slide image analysis | gemma3:27b, gemma3:12b, llava:13b, moondream |
| **Embedding** | Text search and similarity | nomic-embed-text, mxbai-embed-large |

Each model shows:
- **Installed indicator** -- green check if already pulled, download icon if not
- **Parameter count** and **VRAM requirement**
- **Quality rating** (1-5 stars) and **fit assessment** (Fits well / Tight fit / Too large)
- **Pull command** -- shown for models that fit but aren't installed yet

Larger models produce higher-quality questions but need more VRAM and run slower.

### Environment Variables (.env)

The following environment variables can be set in the `.env` file in the project root to override config values on startup:

| Variable | Description | Example |
| -------- | ----------- | ------- |
| `OLLAMA_URL` | Ollama server address | `http://localhost:11434` |
| `OLLAMA_MODEL` | Default model name | `gemma3:27b` |
| `OLLAMA_NUM_CTX` | Context window size (tokens) | `8192` |
| `OLLAMA_ENABLED` | Enable/disable Ollama | `true` or `false` |

Environment variables override values in `config.json`. The `.env` file is loaded by `run.bat` (shell) and by `python-dotenv` (Python) on startup.

---

## Using MCP Documentation Servers

MCP (Model Context Protocol) servers provide documentation context for smarter question generation. The card includes help text explaining what MCP is.

### Add a Server

1. Go to the **AI & Docs** tab > **MCP Documentation Servers** (left column, below Ollama AI).
2. Enable the toggle: **"Use documentation servers for generation and validation"**.
3. Enter a server name (optional — auto-generated from URL hostname if blank) and URL.
4. Press **Enter** or click **Add**. Duplicate URLs are rejected with a warning.

When no servers are configured, a friendly empty state guides you to add your first server.

### Test a Connection

Each server has a test button (wifi icon) that shows "Testing..." then reports success or a helpful error message. The badge at the top shows the connection status (e.g. "2/2 connected" or "0/2 connected").

### How It Works

When MCP is enabled, the generator:

1. Sends the slide title (or first 100 chars of notes) as a search query.
2. Retrieves relevant documentation snippets from MCP servers.
3. Includes this context in the AI prompt alongside the slide content.
4. This helps the AI generate more accurate, domain-specific questions.

---

## Using Docs Chat

The **AI & Docs** tab includes a Docs Chat panel on the right side for interactive documentation queries. The chat includes help text explaining its purpose: "Ask questions about your documentation. The AI searches MCP servers for relevant content, then answers using that context."

### How to Use

1. Go to the **AI & Docs** tab.
2. Make sure Ollama is enabled and a model is selected (left column).
3. Select which MCP server to search (or "All servers") using the "Search in" dropdown.
4. Type your question in the chat input and press **Enter** or click the send button.

### What Happens

1. Your question is sent to the configured MCP servers for documentation search.
2. Relevant documentation snippets are retrieved and included as context.
3. The current slide's speaker notes are also included for reference.
4. A **"Doc context included"** indicator appears on your message bubble when documentation was found.
5. Ollama streams an AI response based on the documentation context.

### Clear Chat

The **Clear Chat** button shows a confirmation dialog before removing the conversation history.

### Features

- **Server selector** -- Choose "All servers" or a specific MCP server to search
- **Streaming responses** -- AI responses stream in real-time as they're generated
- **Slide context** -- Automatically includes the current slide's speaker notes
- **Mermaid diagrams** -- Toggle to request visual diagrams in AI responses (see below)
- **Clear Chat** -- Reset the conversation history (with confirmation dialog)

### Mermaid Diagrams

A **Mermaid diagrams** toggle is available in both the Docs Chat and the Generate tab (Generation Settings). When enabled:

1. The AI is instructed to include Mermaid diagrams (flowcharts, sequence diagrams, state diagrams, mind maps) when explaining processes, workflows, or relationships.
2. Diagrams are rendered visually inline using NiceGUI's built-in Mermaid support.
3. Each diagram appears in an **expandable panel** with:
   - The rendered visual diagram (default-opened)
   - A **"Copy source"** button to copy the raw Mermaid code to your clipboard
   - A **"View source"** collapsible showing the raw Mermaid syntax
4. Mermaid rendering works across all tabs — Docs Chat, Generated Questions, Bank, and Import.

**Supported diagram types:**
- `graph TD` / `flowchart` -- Process flows and decision trees
- `sequenceDiagram` -- Interaction sequences between components
- `stateDiagram-v2` -- State transitions (e.g. question lifecycle)
- `mindmap` -- Topic hierarchies and concept maps
- `pie` -- Distribution charts

**Example use cases:**
- Ask Docs Chat: "Explain the archive installation process" — AI responds with a flowchart
- Generate questions with Mermaid enabled — explanations may include diagrams showing why answers are correct
- Ask Docs Chat: "Show the relationship between these components" — AI responds with a sequence or class diagram

The Mermaid toggle state is saved in your config and persists across sessions.

---

## Admin Tab

The Admin tab has three views, toggled at the top: **Dashboard**, **Database**, and **Documentation**. The Slide Preview panel is hidden on the Admin tab (as it is on all tabs except Generate) to give the full canvas width.

### Dashboard

The dashboard provides visual analytics of your exam bank. When the bank is empty, a friendly empty state guides you to generate or import questions.

- **KPI Cards** -- Total questions, approved, in review, drafts, certifications, and topics at a glance
- **Status Distribution** -- Donut chart showing questions by lifecycle status
- **Difficulty Distribution** -- Bar chart comparing Easy / Medium / Hard counts
- **Bloom's Taxonomy Levels** -- Bar chart showing Remember through Create distribution
- **Questions per Topic** -- Horizontal bar chart (top 15 topics by count)
- **Questions per Certification** -- Horizontal bar chart
- **Question Type Split** -- Pie chart of single-select vs multi-select
- **Quality Metrics** -- Percentage of questions with explanations, source text, scenarios, cert/topic assignment, and average choices per question. Includes a colour legend: green (80%+), orange (50-79%), red (<50%)

#### AI Insights

Click **Generate AI Insights** to send a summary of your bank to Ollama. The AI returns analysis covering:

1. **Overall Health** -- Approval rate and exam readiness
2. **Coverage Gaps** -- Under-represented topics or Bloom's levels
3. **Difficulty Balance** -- Comparison to ideal distribution (25% Easy, 50% Medium, 25% Hard)
4. **Quality Concerns** -- Missing explanations, source text gaps
5. **Recommendations** -- Top actionable improvements

> Requires Ollama to be enabled and a model selected in the AI & Docs tab.

### Database Management

Switch to the **Database** view for full CRUD operations. The view is organized into collapsible sections, each with help text:

#### Stats Overview

Live counts of questions, certifications, and topics with status breakdown badges. Updates automatically when data changes.

#### Questions Browser

- **Search & Filter** -- Filter by Certification, Topic, Status, and free-text search. All filters auto-refresh results and reset pagination to page 1. Search tooltip explains which fields are searched.
- **Pagination** -- Shows "Showing X-Y of Z questions" with page navigation
- **Labeled buttons** -- Each question card has **View**, **Edit**, and **Delete** buttons with text labels (not just icons)
- **View** -- Opens full question details with metadata in a collapsible sub-section
- **Edit** -- Opens editor with descriptive field labels, Key/Distractor toggle with help text, and version tracking
- **Delete** -- Confirmation dialog with warning icon and "Keep" / "Delete" buttons
- **Empty state** -- Centered icon + guidance when no questions match filters

#### Certifications Browser

- View all certifications with question counts and source type (descriptive labels: "PPTX -- slide-based", "Documentation -- MCP servers")
- Labeled **Edit** and **Delete** buttons
- Friendly empty state when no certifications exist
- Delete warns about affected question count

#### Bulk Operations

Collapsible section with help text explaining each operation:

- **Truncate Questions** -- Delete ALL questions (requires typing "DELETE" to confirm)
- **Truncate Certifications** -- Delete ALL certifications (questions keep data but lose cert links)
- **Delete by Status** -- Delete all questions with a specific status, with count shown
- **Delete by Topic** -- Delete all questions under a specific topic, with count shown

> All destructive operations require confirmation and cannot be undone.

#### Auto-Backup

Collapsible section showing last backup time and settings:

- **Enable/disable** toggle with tooltip
- **Interval** (hours) with tooltip explaining range
- **Max backups** with tooltip explaining rotation behaviour
- Shows last backup date/time or a warning if no backups exist

#### Cross-Tab Sync

All changes made in the Admin tab automatically refresh the **Bank** tab, **sidebar**, and stats. Likewise, changes in the Bank tab refresh Admin. This ensures all views stay consistent.

### Documentation

Switch to the **Documentation** view to access three collapsible sections:

#### Ask AI about this app

A built-in AI chat that answers questions about the application using the documentation as context. Requires Ollama to be enabled.

- Type a question (e.g. "How do I import questions?" or "What export formats are available?")
- The AI automatically finds the most relevant sections from both guides using keyword matching
- Streams the response inline with chat bubbles
- No MCP servers needed — uses local documentation only

#### Search Documentation

Keyword search across both HOW_TO_GUIDE.md and README.md:

- Type a keyword and matching lines appear as cards with document name, line number, and surrounding context
- Results update as you type
- Up to 30 results shown

#### Browse Full Documentation

Scrollable rendered views of both guides:

- **How-To Guide** -- The full HOW_TO_GUIDE.md (default-opened)
- **README** -- Collapsible section with the project README.md

Both are loaded from the project root and rendered as markdown in scrollable areas.

### Ollama Model Comparison

The **Compare** button in the action bar opens a dialog for side-by-side model comparison:

1. Click the **Compare** button in the action bar (available when Ollama is enabled).
2. A dialog opens with two model selectors pre-filled with different models.
3. Both models generate a question from the same slide and prompt simultaneously.
4. The results appear side-by-side so you can compare quality, style, and accuracy.
5. Click **Keep** on the preferred result to use it as the generated question.

This is useful for evaluating which Ollama model works best for your content before committing to a full batch generation run.

---

## Customizing the UI

### Color Themes

Click the theme dropdown in the header bar to choose from 8 themes: Slate, Blue, Indigo, Purple, Teal, Green, Orange, Rose.

### Dark / Light Mode

Use the Light/Dark toggle switch in the header bar. Your preference is saved across sessions.

### Exit

Click the power button in the header to exit. A confirmation dialog prevents accidental shutdown. The app auto-exits when all browser tabs are closed (2-second grace period for refreshes).

---

## Troubleshooting

### "Ollama not configured"

Make sure Ollama is running (`ollama serve`) and a model is pulled. Go to the AI & Docs tab, check the URL, and click Refresh to load models.

### Slide images not showing

Make sure Microsoft PowerPoint is installed for best quality slide rendering. The app uses PowerPoint COM automation (`win32com.client`) to export slides as PNG images. If PowerPoint is not available, a cross-platform fallback uses Pillow to render simplified text-based slide previews with titles, bullet points, and notes indicators.

### "No speaker notes" warnings

The AI generates questions primarily from speaker notes. Add notes to your slides in PowerPoint (View > Notes) for best results.

### "Key not validated" warnings

The AI-generated correct answer could not be found in the speaker notes. This can happen when the AI paraphrases too much. Edit the question to align the key with the actual notes text.

### Questions are too similar

The duplicate detection uses a configurable word overlap threshold on stems (default 85%). Adjust it in the **Settings** tab under **Quality & Detection** > **Duplicate Threshold (%)**. Range is 50-100%; lower values catch more potential duplicates, higher values are stricter.

### Import validation fails

**PPTX mode:** Make sure the correct certification is selected — the linked PPTX is auto-loaded for validation. If no PPTX is linked, load one in the sidebar first. Validation checks the key against all slides' speaker notes with a configurable word overlap threshold (default 70%, adjustable in Settings under **Quality & Detection** > **Validation Threshold (%)**).

**Docs mode:** Make sure MCP documentation servers are configured and enabled in the AI & Docs tab. Validation searches the MCP servers for the question's correct answer text with the configured validation threshold (default 70%).

### QA check not finding issues / finding too many

The QA check focuses specifically on spelling, grammar, and syntax errors. It does not flag style, question design, or best-practice concerns. If the AI returns no issues, the question's language is correct. If it returns many false positives, try a larger Ollama model (e.g. `llama3.1:8b` or `mixtral`) for better accuracy.

### Explanation not generated

For batch: click the **Generate Explanations** button (auto-fix icon) after Validate All — it runs in the background. For single questions, the per-card validate button auto-generates an explanation. Requirements: (1) Ollama enabled with a model selected, (2) the question passes PPTX validation, (3) the matched slide has speaker notes, and (4) the question doesn't already have an explanation.

### Port already in use

If port 7777 is busy, the app automatically finds the next available port. You can also change the default in `main.py` (`run_app(port=7777)`).

### Slide images re-exporting every time

Slide images are cached in `assets/pptx/{filename}/`. If they keep re-exporting, check that the `assets/pptx/` directory is writable and not being cleared by an external process.
