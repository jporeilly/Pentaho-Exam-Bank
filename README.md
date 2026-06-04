# Question Bank Generator

Generate high-quality certification exam questions from PowerPoint presentations, MCP documentation, and Pentaho Content Manager (PCM) courses using local AI (Ollama).

## Features

- **AI-Powered Generation** -- Ollama local LLM generates certification exam questions from PPTX speaker notes, MCP documentation, or PCM course content
- **Triple Source Types** -- Generate from PPTX slides (speaker notes), MCP documentation servers (Docs), or **PCM course content** (a Pentaho Content Manager course's lab `guide.md` files)
- **PCM Course Source** -- Point at a PCM `courses/` directory, pick a course (and optionally a single lab/module), and generate questions grounded in that course's content; export back as a PCM `exam.json` to close the loop
- **PCM Exam Export** -- One-click export to a PCM-renderer `exam.json` (single- and multi-select), ready to drop straight into a course
- **Targeted Regeneration** -- Regenerate just the stem, a single key, or a single distractor without affecting other parts
- **Per-Question Specs** -- Independent key/distractor count per question (single or multi-select mix)
- **Slide Image Preview** -- PowerPoint COM automation exports slides as PNG images for pixel-perfect preview
- **Key Traceability** -- Correct answers (keys) must come from slide speaker notes, with automated validation
- **Varying MCQ Format** -- Mix of single-select and multi-select ("Which two...") questions with 3-5 choices
- **Exam Builder** -- Generate formatted PDF exam papers with topic weighting, difficulty filtering, randomization, cover page, and answer key
- **Enforced Workflow** -- Draft -> SME Review -> Approved/Revised/Rejected with per-row status dropdowns showing only valid transitions
- **SME Audit Trail** -- Every status change logged with SME name, timestamp, and comments
- **SME Management** -- Add/rename/remove SMEs with confirmation dialogs, reassign questions between SMEs, auto-syncing dropdowns across all tabs, Enter-key support, friendly empty states
- **Certification Management** -- PPTX or Docs source types, reassign questions between certifications, track counts per cert
- **Import & Validate** -- Upload existing questions (CSV/JSON/Excel/QTI 2.1/Moodle XML), dual-mode validation (PPTX speaker notes or MCP documentation) with auto-detection from certification type, PPTX/Docs toggle, AI key assignment from speaker notes + slide images, auto-generated explanations, AI actions on imported questions
- **Excel Spreadsheet Converter** -- Import .xlsx files with auto-detected column layouts (direct or Option A/B/C/D pattern), multi-sheet support with sheet-name topics, merged cell handling
- **Round-Trip CSV** -- Export preserves all 27 fields; re-import restores questions with full metadata
- **Version History** -- Every question edit is tracked with field-level diffs (color-coded: red strikethrough for old, green for new), timestamps, and editor names; `record_edit()` called for every field edit in Bank and Admin
- **Duplicate Detection** -- Fuzzy stem matching (configurable threshold, default 85%) prevents duplicate questions at import and save time, independent of source validation
- **Multi-Format Export** -- CSV, JSON, QTI 2.1 (Canvas/Blackboard), Moodle XML, DOCX, plain text, PDF exam papers
- **Docs Chat** -- Ollama-powered documentation chat with MCP server context for AI-assisted authoring, optional Mermaid diagram generation
- **Mermaid Diagrams** -- Toggle to include visual diagrams (flowcharts, sequence, state, mind maps) in AI responses across Docs Chat and question explanations; expandable panels with copy-to-clipboard source
- **MCP Documentation** -- Model Context Protocol integration for GitBook documentation context
- **AI Key Assignment** -- For imported questions without marked answers, AI analyzes speaker notes + slide image to determine which options are correct keys vs distractors
- **AI QA Check** -- Focused grammar, spelling, and syntax checking per field (scenario, stem, keys, distractors) with auto-fix and field-level issue display
- **AI Improvement** -- One-click AI enhancement of individual questions (also available for imported questions)
- **Explanation Generation** -- Auto-generates source-backed explanations from speaker notes during PPTX validation, citing why each answer is correct or incorrect
- **Option Order Preservation** -- Imported questions retain original A: B: C: D: E: ordering through validation, editing, and bank storage
- **Admin Dashboard** -- ECharts analytics (status, difficulty, Bloom's, topic/cert distribution, quality metrics) with AI-powered insights from Ollama
- **Database Admin** -- View, search, edit, delete questions/certifications; bulk truncate, delete by status/topic
- **Event Bus** -- Pub/sub EventBus on AppState replaces callback chains for decoupled cross-tab communication (questions_changed, bank_changed, stats_changed, certifications_changed, files_changed, slide_changed, action_bar_changed, admin_changed)
- **Cross-Tab Sync** -- Deleting/editing questions in Bank auto-refreshes Admin, and vice versa; sidebar topics, certifications, and file list stay in sync across all tabs
- **Bank Pagination** -- Bank tab shows configurable questions per page (10, 25, 50, or 100; default 25) with prev/next navigation; page resets on filter or search change
- **Tags in Bank UI** -- Tags displayed as purple badges on question cards with a Tag dropdown filter in the search bar; internal tags (qa:*, key-*) are hidden
- **Keyboard Shortcuts** -- Ctrl+G (generate), Ctrl+S (save all), ArrowLeft/Right (slide navigation); arrow keys only fire when no modifier is held
- **Batch Generation** -- "Generate All Slides" button generates questions from all slides with speaker notes in one batch
- **Mini Dashboard on Bank** -- Enhanced stats section with approval progress bar, difficulty distribution badges, and low-coverage topic alerts
- **Undo for Deletes** -- Single and bulk deletes stage questions for 10 seconds with an undo bar; undo re-inserts the question
- **Student Preview View** -- Dialog-based practice mode from the Bank tab with shuffled choices, submit-for-feedback, score tracking, and final summary
- **QTI/Moodle Import** -- Import questions from QTI 2.1 and Moodle XML files with auto-detected format by root element
- **Ollama Model Comparison** -- "Compare" button in the action bar generates the same question with two different models side-by-side; user keeps the preferred result
- **Auto-Backup Schedule** -- Configurable in Admin tab (Database view); automatic backups at a specified interval (default 24h) keeping up to N backups (default 5)
- **Async Ollama Client** -- Async versions of all Ollama functions using httpx (async_generate, async_chat, async_generate_stream, async_chat_stream, async_check_connection, async_list_models); sync versions unchanged
- **Configurable Context Window** -- `num_ctx` setting (default 8192) controls Ollama token limit; Auto-detect button queries GPU (nvidia-smi) and model capabilities (/api/show) to recommend optimal value; configurable via UI, config.json, or `OLLAMA_NUM_CTX` in `.env`
- **Responsive UI** -- 2-panel layout with 8 color themes, dark/light mode, gradient header; slide preview only shows on the Generate tab to maximize canvas space on all other tabs

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com/) running locally (default: `http://localhost:11434`)
- An Ollama model installed (e.g. `ollama pull llama3.2`)
- Microsoft PowerPoint (for slide image export; Pillow-based fallback on non-Windows or when PowerPoint is not installed)

## Quick Start

### Install

```batch
install.bat
```

Or manually:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Run

```batch
run.bat
```

Or manually:

```bash
venv\Scripts\activate
python main.py
```

Opens in your browser at **http://localhost:7777**

## Usage

### From PPTX Slides

1. **Load a PPTX** -- Drag-and-drop into the sidebar (file is cached in `assets/pptx/`, slide images auto-exported)
2. **Preview Slides** -- Slide images display at the top of the main area with thumbnail filmstrip navigation
3. **Assign Certification** -- Create/select a PPTX certification in the sidebar to link the deck
4. **Configure** -- Set difficulty, Bloom's level, and questions per slide in the Generate tab
5. **Generate** -- Click "Generate" in the action bar below the slide preview
6. **Review** -- Edit questions in the Generate tab, use AI Improve for refinement
7. **Save** -- Save individual or all questions to the bank

### From MCP Documentation

1. **Create a Docs Certification** -- In the sidebar, create a certification with Source = "Docs"
2. **Set a Topic** -- Type a specific search topic (e.g. "Archive Installation") in the sidebar topic field
3. **Generate** -- Click "Generate from Docs" in the action bar; MCP servers are searched for documentation
4. **Review & Save** -- Same workflow as PPTX-generated questions

### From a PCM Course

Generate questions grounded in a Pentaho Content Manager course's own content, then export back into that course.

1. **Set the courses directory** -- In **Settings -> Output**, set the *PCM courses directory* (defaults to a sibling `Pentaho-Content-Manager/courses` if present).
2. **Pick a course** -- In the sidebar **PCM Course** section, choose a course from the dropdown. This find-or-creates a `pcm` certification bound to that course and makes it active.
3. **(Optional) Scope to a lab/module** -- Use the **Lab / module** dropdown to generate from a single lab instead of the whole course.
4. **Generate** -- Click **"Generate from PCM course"** in the action bar. Each lab `guide.md` is split into sections (HTML/widget markup stripped) and used as grounding; keys are traced to the course text.
5. **Review & Save** -- Same workflow as other sources. The section heading becomes the question's topic (the PCM `module` label).
6. **Export back to PCM** -- In the Bank tab, filter to approved questions and click **PCM Exam** to write an `exam.json`; drop it into the course's directory in PCM and reseed.

### Common Workflow

1. **Lifecycle** -- Move questions through Draft -> SME Review -> Approved/Rejected
2. **Export** -- Use the Bank tab to filter, search, and export in your preferred format
3. **Import** -- Upload existing questions via the Import tab, select certification (auto-detects PPTX/Docs mode), validate and apply AI actions
4. **Exam Builder** -- Use the Exam tab to build weighted, randomized PDF exam papers
5. **Docs Chat** -- Use the AI & Docs tab to query documentation servers and get AI-powered answers

## Layout

The app uses a **2-panel layout** matching the PPTX to Video project:

- **Left Sidebar** -- File management, certifications, generation settings
- **Right Main Area**:
  - **Slide Preview** (top) -- Full slide image with thumbnail filmstrip and speaker notes (only visible on the Generate tab; hidden on all other tabs to maximize canvas space)
  - **Tab Bar** (below preview) -- SETTINGS | GENERATE | IMPORT | BANK | AI & DOCS | EXAM | ADMIN

### Tab Descriptions

| Tab | Contents |
|-----|----------|
| **Settings** | Six collapsible sections: SME Identity (add/rename/remove with confirmation and reassign), Reassignment Tools (bulk-move questions by SME or certification), Questions Export Settings (output folder with folder picker, default format, auto-export CSV toggle), Display (questions per page), Quality & Detection (duplicate and validation thresholds with clamping), App Info & Maintenance (stats, last backup, file paths, Vacuum, Integrity Check). Per-section Reset to Defaults buttons. |
| **Generate** | Generation settings (difficulty, Bloom's, per-question specs), generated questions editor |
| **Import** | CSV/JSON/Excel/QTI 2.1/Moodle XML import, collapsible Import Settings and Upload panels, per-question certification/topic reassignment, colour-coded PPTX/Docs validation toggle (blue/teal), labeled action buttons, confirmation dialogs for Save All and Clear All, auto-explanation from notes, AI actions (improve, regen, QA check), auto-export indicator |
| **Bank** | Four collapsible sections: Dashboard (status counts, approval progress, difficulty distribution, low-coverage alerts), Search & Filters (7 auto-refreshing filters, keyword search), Bulk Actions & Export (status transitions, SME assignment, bulk delete with confirmation, 6 export formats with filter summary, workflow reference, Student View), Database Backup & Restore. Per-card labeled Edit/Delete buttons, question numbers, expanded explanations, better empty states, pagination showing range. |
| **AI & Docs** | Two-column layout: Left has Ollama AI settings (enable toggle, server URL, model selector with pull hint, system prompt with explanation) and MCP Documentation Servers (enable toggle, server list with test/remove, add with URL validation and Enter key, friendly empty state). Right has Docs Chat (server selector, streaming responses, context indicator, clear confirmation). All cards have help descriptions. |
| **Exam** | Three collapsible sections: Exam Configuration (3-column layout with Exam Details, Question Source with status filters, Topic Weighting with distribute-evenly and validation), PDF Options (5 toggles with tooltips, answer key/explanation dependency), PDF Preview (friendly empty state with step guide, inline iframe, download/open links). Help text on every section. |
| **Admin** | Three views via toggle: Dashboard (ECharts analytics with better empty state, quality metrics with colour legend, AI insights), Database (collapsible Stats Overview, Questions/Certifications browser with labeled buttons, search with pagination reset, friendly empty states, collapsible Bulk Operations with help text, Auto-Backup with last backup time and tooltips), Documentation (AI Q&A chat powered by Ollama with automatic context retrieval from docs, keyword search with line numbers, inline HOW_TO_GUIDE.md and README.md viewer) |

## Architecture

```
question_bank/
├── main.py                          # Entry point (port 7777)
├── run.bat                          # Batch launcher
├── install.bat                      # One-click installer
├── requirements.txt                 # Dependencies
│
├── core/                            # Business logic
│   ├── pptx_reader.py              # PowerPoint file parser (titles, body, speaker notes)
│   ├── pptx_exporter.py            # Slide image export via PowerPoint COM automation
│   ├── pptx_exporter_fallback.py   # Cross-platform slide export fallback (Pillow)
│   ├── ollama_client.py            # Ollama REST API client (sync + async via httpx: generate, chat, stream, list_models)
│   ├── mcp_client.py               # MCP documentation server client (GitBook search)
│   ├── question_bank.py            # SQLite models + database (Question, Certification, ReviewEntry)
│   ├── question_generator.py       # Re-export facade (backward compat) for the 4 modules below
│   ├── generation_prompts.py       # System prompt, build_prompt(), question specs
│   ├── generation_parsing.py       # JSON extraction, key-against-notes validation
│   ├── question_generation.py      # Core generation pipeline (generate, batch, auto-fix)
│   ├── question_refinement.py      # Regen, improve, QA check, explanation, AI key assignment
│   ├── question_importer.py        # CSV/JSON/text import + PPTX and MCP docs validation
│   ├── spreadsheet_converter.py    # Excel (.xlsx) to CSV converter with auto column detection
│   ├── exporter.py                 # Multi-format export (CSV, JSON, QTI 2.1, Moodle XML, DOCX, text)
│   ├── exam_builder.py             # Exam Builder: topic-weighted selection + PDF generation (fpdf2)
│   └── db_backup.py               # Database backup, restore, and info utilities
│
├── gui/                             # NiceGUI web interface
│   ├── web_app.py                  # 2-panel layout, tab wiring, keyboard shortcuts (slim orchestrator)
│   ├── state.py                    # Shared state (AppState with EventBus, UIRefs)
│   ├── styles.py                   # Directory constants, 8 themes, responsive CSS, dark mode, explanation formatter
│   └── components/
│       ├── header.py               # Gradient header bar, theme selector, dark/light toggle, exit
│       ├── sidebar.py              # File upload/cache, certs, topics, recent files (full sidebar refresh)
│       ├── slide_panel.py          # Slide image preview with thumbnail filmstrip + speaker notes
│       ├── generate_tab.py         # Generation Settings UI (difficulty, Bloom's, question specs, scenario toggle)
│       ├── generation_handler.py  # Generation orchestration (on_generate, batch, auto-QA, dupe replacement)
│       ├── question_editor.py     # Generated questions list with edit/save/improve/delete
│       ├── bank_browser.py         # Metrics, DB backup/restore, search, filter, lifecycle, export
│       ├── settings_tab.py         # SME identity, reassignment tools, export, display, quality, app info & maintenance
│       ├── import_tab.py           # Import orchestrator — file upload, UI layout, card rendering
│       ├── import_context.py       # Shared mutable context for import sub-modules (ImportContext)
│       ├── import_validation.py    # Validation, QA check, AI key assignment, explanation generation
│       ├── import_edit_dialog.py   # Edit dialog with Key/Distractor toggle + AI regen actions
│       ├── import_save.py          # Save/commit to bank, CSV auto-export, duplicate detection
│       ├── db_admin_tab.py         # Database admin — CRUD, bulk truncate, delete by status/topic
│       ├── dashboard.py            # ECharts analytics dashboard + AI-powered insights (Ollama)
│       ├── exam_tab.py             # Exam Builder UI (cert selection, topic weighting, PDF generation)
│       ├── docs_search_tab.py      # AI & Docs tab orchestrator (Ollama + MCP + Docs Chat)
│       ├── ollama_settings.py      # Ollama AI config card (enable, URL, model, pull, prompt)
│       ├── mcp_settings.py         # MCP Documentation Servers card (enable, list, add/remove)
│       ├── docs_chat.py            # Docs Chat with MCP context search + Ollama streaming
│       └── student_view.py         # Student Preview dialog (practice mode with score tracking)
│
├── assets/
│   ├── pptx/                        # Cached PPTX files + exported slide images per deck
│   ├── questions/                   # Sample CSV + auto-exported CSVs per certification/topic
│   ├── config/                      # App configuration
│   │   └── config.json              # App settings (migrated from assets/db/ on startup)
│   └── db/                          # SQLite database and backups
│       ├── question_bank.db         # Main question bank database
│       └── backups/                 # Timestamped database backups
│
├── tests/                           # Test suite (pytest)
│   ├── conftest.py                 # Shared fixtures
│   ├── test_question_bank.py       # Question model, validation, lifecycle, DB CRUD
│   ├── test_exporter.py            # Multi-format export tests
│   ├── test_exam_builder.py        # Exam builder and PDF generation tests
│   ├── test_question_importer.py   # CSV/JSON import tests
│   ├── test_question_generator.py  # AI generation pipeline tests
│   ├── test_pptx_reader.py         # PPTX reader tests
│   ├── test_db_backup.py           # Backup/restore tests
│   ├── test_config.py              # AppConfig tests
│   ├── test_ollama_client.py       # Ollama client tests
│   ├── test_mcp_client.py          # MCP client tests
│   ├── test_spreadsheet_converter.py # Excel converter tests
│   ├── test_event_bus.py            # EventBus pub/sub tests (8 tests)
│   └── test_qti_moodle_import.py    # QTI 2.1 and Moodle XML import tests (6 tests)
│
└── utils/
    └── config.py                    # AppConfig dataclass (persisted to assets/config/config.json)
```

## Data Storage

| File | Location | Purpose |
|------|----------|---------|
| `config.json` | `assets/config/` | App settings (Ollama, theme, recent files, SME name, thresholds) |
| `question_bank.db` | `assets/db/` | SQLite database (questions, certifications, audit trail) |
| Backups | `assets/db/backups/` | Timestamped database backups (created manually or before restore) |
| PPTX cache | `assets/pptx/` | Uploaded PPTX files + exported slide PNG images |
| Question CSVs | `assets/questions/{Cert}/{Topic}.csv` | Auto-exported CSVs on commit to bank (per certification and topic) |
| Static files | `%TEMP%/question_bank_static/` | Temporary slide images served to browser |
| Exports | `assets/questions/` | Exported question files (configurable in Settings; default changed from `~/Documents/QuestionBank/`) |

> **Migration**: On first run, if data exists in the old location (`~/.question_bank/`), the database and config are automatically copied to their new locations. The config file is also automatically migrated from `assets/db/config.json` to `assets/config/config.json` on startup.

### Database Backup & Restore

The **Bank** tab includes a collapsible "Database Backup & Restore" section:

- **Create Backup** -- Timestamped copy with optional label (uses SQLite online backup API for consistency)
- **Restore** -- Overwrite current DB from a backup (safety backup created automatically before restore)
- **Delete** -- Remove old backups
- **DB Info** -- Shows database location, size, and last modified date

## PPTX Slide Image Export

When a PPTX file is uploaded:

1. The file is copied to `assets/pptx/` for permanent caching
2. A background thread uses PowerPoint COM automation (`win32com.client`) to export each slide as PNG
3. Images are stored in `assets/pptx/{filename}/slide_001.png`, etc.
4. PNGs are served to the browser via NiceGUI's static file route with cache-busting params
5. Previously exported images are loaded from cache on subsequent sessions
6. If PowerPoint is not installed, a text-based fallback is shown

## Question Lifecycle

```
draft --> sme_review --> revised --> approved --> retired
                    \-> rejected --> draft (rework)
```

Every transition is recorded with SME name, timestamp, and optional comment.

## Question Model

Each question follows certification exam best practices:

- **Scenario** -- Realistic context (1-3 sentences)
- **Stem** -- Clear, direct question ending with "?" (e.g. "Which two options describe...?")
- **Key** -- Correct answer(s) sourced from slide speaker notes
- **Distractors** -- 2-4 plausible but incorrect answers (no "All/None of the above")
- **Explanation** -- Why the key is correct and why distractors are wrong
- **key_source_text** -- Exact quote from speaker notes that supports the key
- **Metadata** -- Difficulty, Bloom's level, topic, certification, status, source slide(s)

## Export Formats

| Format | Use Case |
|--------|----------|
| **CSV** | Spreadsheets, custom processing, full round-trip backup/restore |
| **JSON** | Programmatic access, APIs, full round-trip backup/restore |
| **QTI 2.1** | Industry-standard LMS import (Canvas, Blackboard, etc.) |
| **Moodle XML** | Moodle LMS import |
| **Text** | Printable study guides with shuffled choices |
| **DOCX** | Formatted Word document with metadata, colour-coded answers |
| **PDF Exam** | Formatted exam papers with cover page, topic sections, and answer key (via Exam tab) |
| **PCM Exam** | `exam.json` for the Pentaho Content Manager renderer (single- and multi-select; scenario/source carried through), to drop into a course |

## Dependencies

| Package | Purpose |
|---------|---------|
| `nicegui >= 2.0.0` | Web UI framework (Quasar + Vue.js) |
| `python-pptx >= 1.0.0` | PowerPoint file reading |
| `python-dotenv >= 1.0.0` | Environment variable support |
| `pywin32` | PowerPoint COM automation for slide image export (Windows) |
| `fpdf2 >= 2.7.0` | PDF exam paper generation |
| `python-docx >= 1.1.0` | Word document (.docx) export |
| `Pillow >= 10.0.0` | Cross-platform slide image fallback rendering |
| `openpyxl >= 3.1.0` | Excel spreadsheet (.xlsx) import and conversion |
| `httpx >= 0.27.0` | Async HTTP client for async Ollama functions |
| `pytest >= 8.0.0` | Test suite (development) |

## UI Themes

8 color themes available from the header dropdown: Slate, Blue, Indigo, Purple, Teal, Green, Orange, Rose. Dark and light modes supported.

## License

Internal tool -- not for distribution.
