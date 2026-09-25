# What did not come across from NiceGUI

The NiceGUI layer was deleted in `9d0588f` — 22 components, about 10,600
lines. Most of it was rebuilt in React, but not all, and the gaps are quiet:
the code is still in `exam_bank/core/`, it just has nothing calling it. A
function with no caller does not fail a test or a build.

This is an audit of what is missing, done by listing the deleted components
against the React panes, and by finding every public function in `core/`
with no reference from `api/`, from elsewhere in `core/`, or from the front
end. Checked 2026-09-25.

**Not a bug list.** Some of this was dropped on purpose and should be struck
out rather than built.

## Gone on purpose — do not rebuild

| Was | Why |
| --- | --- |
| `slide_panel.py` (426 lines) | PPTX generation was dropped as a product decision. |
| `pptx_exporter*.py`, `pptx_reader.py` in core | Same. Candidates for deletion rather than porting. |

## Missing, and worth deciding about

### 1. AI operations on a question — 6 of 8 still unreachable

`core/question_refinement.py` has eight AI operations. Two are now wired
(`improve_question`, `qa_check_question`, plus the new `review_answers`).
These six have **no API route and no caller**:

| Function | What it did in the old editor |
| --- | --- |
| `regen_stem` | Reword the stem and scenario, leaving every choice locked. |
| `regen_key` | Replace the correct answer only. |
| `regen_distractor` | Replace one distractor, keeping the others. |
| `qa_fix_question` | Apply the proofreader's findings rather than only listing them. |
| `generate_explanation` | Write the explanation from the key and distractors. |
| `ai_assign_keys` | Pick the key for an imported question that has none. |

`ai_assign_keys` is the one with a real use today: the plain-text importer
takes the FIRST option as the key, positionally, and nothing else flags the
result because the question is still gradeable.

All six take `(question, model, base_url)` and return a value — none of them
mutates now, but that was true of `improve_question` too until it was wired
up and the mutation was found. **Treat each as untested until it has a test.**

### 2. A dashboard — `dashboard.py`, 356 lines

No React equivalent. The bank has counts by status, topic, difficulty and
Bloom level (`get_status_counts`, `get_topic_counts`, `get_difficulty_counts`,
`get_bloom_counts`) and only the first is surfaced, in the header.

**`get_bloom_counts` is computed and returned by `/api/health` as `byBloom`
and rendered nowhere.** If you are looking for "the Bloom report", this is
where it would live; there is no such screen today. The
`docs/bloom-review/*.json` files are hand-written review notes, not output
from a feature.

### 3. A student view — `student_view.py`, 193 lines

No React equivalent. Previewed a question as a candidate would see it —
which is now more useful than it was, because the Content Manager shuffles
options at render and the bank's stored order is no longer what a learner
sees.

### 4. Import validation against the source — `import_validation.py`, 547 lines

`core/question_importer.py` still has `validate_question_against_pptx`,
`validate_question_against_docs` and `validate_batch`, all unreachable. The
Import pane previews and reports duplicates and ungradeable questions, but
does not check an imported question against the material it claims to come
from.

### 5. Ollama settings — `ollama_settings.py`, 299 lines

`core/ollama_client.py` has `get_gpu_info`, `recommend_models` and
`recommend_num_ctx`, none of them reachable. The Settings pane lets you type
a model name and a context size; it cannot tell you what the machine will
actually run. On a two-card box this matters: a model that does not fit one
GPU spills to CPU and runs several times slower.

### 6. MCP settings — `mcp_settings.py`, 141 lines

`core/mcp_client.py` has `search_documentation` and
`search_multiple_servers_structured` with no caller. The settings API
mentions MCP once; the Settings pane does not mention it at all.

### 7. Streaming model output

`ollama_client.py` has `generate_stream`, `chat_stream` and six `async_*`
variants, all unreachable. Everything is a blocking call today — the AI
answer-check takes **171 seconds** against the local model because it makes
two sequential requests and shows nothing until both finish.

## Probably just dead code

`core/spreadsheet_converter.py` exports `match_headers`, `convert_sheet`,
`convert_workbook` and `convert_xlsx_to_csv`, none called. **xlsx import
works** — it goes through `import_from_xlsx`, which is wired. These four look
like a separate conversion path that lost its caller. Confirm, then delete.

## Suggested order

1. **`ai_assign_keys`** — fixes a known, silent import defect.
2. **The dashboard**, including the Bloom distribution that is already
   computed and thrown away.
3. **`generate_explanation`** and **`qa_fix_question`** — the two that save
   the most typing in review.
4. **Streaming**, or at least a progress indication, before more AI features
   land on top of a 171-second blocking call.
5. **Student view** — cheap, and now shows something the author cannot
   otherwise see.
6. Decide on Ollama/MCP settings; delete the PPTX and spreadsheet-converter
   remnants.
