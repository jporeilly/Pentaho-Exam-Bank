"""Convert Excel spreadsheets (.xlsx) with tabbed sheets into Exam Bank CSV format.

Supports two common spreadsheet layouts:
  - **Direct mapping**: columns named Stem/Question, Key/Answer, Distractor 1-4, etc.
  - **Option columns**: columns named Option A/B/C/D (or Choice 1-4) with a
    separate "Correct" indicator column containing "A", "B", "C", "D" (or 1-4).

Each sheet can represent a different topic — sheet names are used as the default
topic when no explicit Topic column exists.
"""

import csv
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

try:
    from openpyxl import load_workbook
    from openpyxl.worksheet.worksheet import Worksheet
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

# ---------------------------------------------------------------------------
# Canonical CSV columns (must match exporter.py header row exactly)
# ---------------------------------------------------------------------------
CSV_COLUMNS = [
    "ID", "Scenario", "Stem", "Question Type", "Key", "Keys",
    "Key Source Text",
    "Distractor 1", "Distractor 2", "Distractor 3", "Distractor 4",
    "Explanation", "Topic", "Difficulty", "Bloom Level",
    "Certification ID", "Status", "Reject Reason",
    "Created By", "Assigned SME",
    "Source File", "Source Slides", "Key Source Slide",
    "Created At", "Reviewed At", "Approved At", "Tags",
]

# ---------------------------------------------------------------------------
# Header alias table — maps canonical field names to known column headings
# ---------------------------------------------------------------------------
HEADER_ALIASES: Dict[str, List[str]] = {
    # Core question fields
    "stem": ["stem", "question", "question_text", "item", "prompt", "q"],
    "key": ["key", "answer", "correct_answer", "key_answer", "right_answer"],
    "keys": ["keys", "correct_answers"],
    "question_type": ["question_type", "type", "format", "q_type"],
    "scenario": ["scenario", "context", "passage", "background", "case_study"],
    "explanation": ["explanation", "rationale", "feedback", "justification", "reason"],
    "topic": ["topic", "subject", "category", "domain", "section", "area"],
    "difficulty": ["difficulty", "level", "diff"],
    "bloom": ["bloom", "bloom_level", "taxonomy", "blooms", "bloom's_level"],
    "tags": ["tags", "keywords", "labels"],
    "status": ["status", "state"],

    # Direct distractor columns
    "distractor_1": ["distractor_1", "distractor1", "d1", "wrong_1", "wrong1",
                     "incorrect_1", "incorrect1"],
    "distractor_2": ["distractor_2", "distractor2", "d2", "wrong_2", "wrong2",
                     "incorrect_2", "incorrect2"],
    "distractor_3": ["distractor_3", "distractor3", "d3", "wrong_3", "wrong3",
                     "incorrect_3", "incorrect3"],
    "distractor_4": ["distractor_4", "distractor4", "d4", "wrong_4", "wrong4",
                     "incorrect_4", "incorrect4"],

    # Option-style columns (Pattern B)
    "option_a": ["option_a", "choice_1", "choice_a", "option1", "opt_a", "a)"],
    "option_b": ["option_b", "choice_2", "choice_b", "option2", "opt_b", "b)"],
    "option_c": ["option_c", "choice_3", "choice_c", "option3", "opt_c", "c)"],
    "option_d": ["option_d", "choice_4", "choice_d", "option4", "opt_d", "d)"],
    "option_e": ["option_e", "choice_5", "choice_e", "option5", "opt_e", "e)"],
    "correct_indicator": ["correct", "correct_option", "answer_key", "right",
                          "correct_answer_letter", "ans"],
}

# Sheets to skip (case-insensitive)
SKIP_SHEETS = {"instructions", "readme", "notes", "template", "info", "about"}


# ---------------------------------------------------------------------------
# Header matching
# ---------------------------------------------------------------------------

def _normalize_header(h: str) -> str:
    """Normalize a header string for matching."""
    h = h.strip().lower()
    h = re.sub(r"[''`]", "", h)           # remove apostrophes
    h = re.sub(r"[^a-z0-9]+", "_", h)     # non-alphanum → underscore
    h = h.strip("_")
    return h


def match_headers(raw_headers: List[str]) -> Dict[str, int]:
    """Map canonical field names to column indices using fuzzy header matching.

    Returns ``{canonical_name: column_index}``.
    """
    normalized = [_normalize_header(h) for h in raw_headers]
    mapping: Dict[str, int] = {}
    used_indices: set = set()

    # Pass 1: exact match
    for canonical, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            for i, norm in enumerate(normalized):
                if i in used_indices:
                    continue
                if norm == alias:
                    mapping[canonical] = i
                    used_indices.add(i)
                    break
            if canonical in mapping:
                break

    # Pass 2: word-boundary substring match for unmatched fields
    for canonical, aliases in HEADER_ALIASES.items():
        if canonical in mapping:
            continue
        for alias in aliases:
            for i, norm in enumerate(normalized):
                if i in used_indices:
                    continue
                if alias in norm and alias != norm:
                    if re.search(rf'\b{re.escape(alias)}\b', norm):
                        mapping[canonical] = i
                        used_indices.add(i)
                        break
            if canonical in mapping:
                break

    return mapping


def _detect_layout(mapping: Dict[str, int]) -> str:
    """Detect the spreadsheet layout pattern.

    Returns ``"options"`` if Option A/B/C/D columns with a correct indicator
    are found, otherwise ``"direct"``.
    """
    has_options = "option_a" in mapping and "option_b" in mapping
    has_indicator = "correct_indicator" in mapping
    if has_options and has_indicator:
        return "options"
    return "direct"


# ---------------------------------------------------------------------------
# Cell value helpers
# ---------------------------------------------------------------------------

def _cell_str(value) -> str:
    """Convert a cell value to a stripped string."""
    if value is None:
        return ""
    return str(value).strip()


def _resolve_correct_indicator(indicator: str, options: Dict[str, str]) -> Tuple[str, List[str]]:
    """Given a correct-answer indicator and option values, return (key, distractors).

    The indicator can be a letter (A-E), a number (1-5), or the actual answer text.
    """
    indicator = indicator.strip()
    ind_upper = indicator.upper()

    # Letter mapping
    letter_map = {"A": "option_a", "B": "option_b", "C": "option_c",
                  "D": "option_d", "E": "option_e"}
    # Number mapping
    number_map = {"1": "option_a", "2": "option_b", "3": "option_c",
                  "4": "option_d", "5": "option_e"}

    correct_field = None
    # Try letter
    if ind_upper in letter_map:
        correct_field = letter_map[ind_upper]
    # Try number
    elif ind_upper in number_map:
        correct_field = number_map[ind_upper]
    # Try "Option A" / "Choice 2" style
    else:
        m = re.match(r'(?:option|choice)\s*([a-eA-E1-5])', indicator, re.IGNORECASE)
        if m:
            val = m.group(1).upper()
            if val in letter_map:
                correct_field = letter_map[val]
            elif val in number_map:
                correct_field = number_map[val]

    # If still not resolved, try matching against option text
    if correct_field is None:
        norm_ind = indicator.lower()
        for field, text in options.items():
            if text.lower() == norm_ind:
                correct_field = field
                break

    if correct_field is None or correct_field not in options or not options[correct_field]:
        # Fallback: use first non-empty option as key
        all_opts = [v for v in options.values() if v]
        key = all_opts[0] if all_opts else ""
        distractors = all_opts[1:] if len(all_opts) > 1 else []
        return key, distractors

    key = options[correct_field]
    distractors = [v for f, v in options.items() if f != correct_field and v]
    return key, distractors


# ---------------------------------------------------------------------------
# Merged cell handling
# ---------------------------------------------------------------------------

def _unmerge_and_fill(ws: "Worksheet") -> None:
    """Unmerge all merged cells and fill the value from the top-left cell into
    every cell of the merge range.  Modifies the worksheet in-place."""
    for merge_range in list(ws.merged_cells.ranges):
        top_left = ws.cell(merge_range.min_row, merge_range.min_col).value
        ws.unmerge_cells(str(merge_range))
        for row in range(merge_range.min_row, merge_range.max_row + 1):
            for col in range(merge_range.min_col, merge_range.max_col + 1):
                ws.cell(row, col, top_left)


# ---------------------------------------------------------------------------
# Sheet → row dicts
# ---------------------------------------------------------------------------

def convert_sheet(
    ws: "Worksheet",
    sheet_name: str = "",
    default_topic: str = "",
) -> List[dict]:
    """Convert a single worksheet into a list of canonical CSV row dicts."""
    _unmerge_and_fill(ws)

    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        return []

    # Find header row — first row with ≥ 2 non-empty cells
    header_idx = 0
    for i, row in enumerate(rows):
        non_empty = sum(1 for c in row if c is not None and str(c).strip())
        if non_empty >= 2:
            header_idx = i
            break

    raw_headers = [_cell_str(c) for c in rows[header_idx]]
    if not any(raw_headers):
        return []

    mapping = match_headers(raw_headers)
    layout = _detect_layout(mapping)

    # Must have at least a stem column
    if "stem" not in mapping:
        return []

    results: List[dict] = []

    for row in rows[header_idx + 1:]:
        cells = [_cell_str(c) for c in row]

        # Skip blank rows
        if not any(cells):
            continue

        stem = cells[mapping["stem"]] if "stem" in mapping else ""
        if not stem:
            continue

        # Build the row dict
        out: dict = {col: "" for col in CSV_COLUMNS}
        out["Stem"] = stem
        out["Status"] = "draft"
        out["Created By"] = "Import (Excel)"
        out["Created At"] = datetime.now().isoformat()

        # Scenario
        if "scenario" in mapping:
            out["Scenario"] = cells[mapping["scenario"]]

        # Explanation
        if "explanation" in mapping:
            out["Explanation"] = cells[mapping["explanation"]]

        # Topic — column or sheet name fallback
        if "topic" in mapping and cells[mapping["topic"]]:
            out["Topic"] = cells[mapping["topic"]]
        elif default_topic:
            out["Topic"] = default_topic

        # Difficulty
        if "difficulty" in mapping and cells[mapping["difficulty"]]:
            out["Difficulty"] = cells[mapping["difficulty"]]
        else:
            out["Difficulty"] = "Medium"

        # Bloom
        if "bloom" in mapping and cells[mapping["bloom"]]:
            out["Bloom Level"] = cells[mapping["bloom"]]
        else:
            out["Bloom Level"] = "Apply"

        # Tags
        if "tags" in mapping:
            out["Tags"] = cells[mapping["tags"]]

        # Status
        if "status" in mapping and cells[mapping["status"]]:
            from .bank import STATUSES
            s = cells[mapping["status"]].lower()
            if s in STATUSES:
                out["Status"] = s

        # Question type
        q_type = "single"
        if "question_type" in mapping and cells[mapping["question_type"]]:
            q_type = cells[mapping["question_type"]].lower()
        out["Question Type"] = q_type

        # --- Key and distractors based on layout ---
        if layout == "options":
            # Gather option values
            option_fields = ["option_a", "option_b", "option_c", "option_d", "option_e"]
            options = {}
            for f in option_fields:
                if f in mapping:
                    options[f] = cells[mapping[f]]

            indicator = cells[mapping["correct_indicator"]] if "correct_indicator" in mapping else ""

            if indicator:
                key, distractors = _resolve_correct_indicator(indicator, options)
            else:
                # No indicator — treat first option as key, rest as distractors
                all_opts = [v for v in options.values() if v]
                key = all_opts[0] if all_opts else ""
                distractors = all_opts[1:] if len(all_opts) > 1 else []

            out["Key"] = key
            for i, d in enumerate(distractors[:4]):
                out[f"Distractor {i + 1}"] = d

        else:
            # Direct mapping
            if "key" in mapping:
                key_val = cells[mapping["key"]]
                # Check for pipe-separated multi-select
                if "|" in key_val:
                    keys_list = [k.strip() for k in key_val.split("|") if k.strip()]
                    out["Key"] = keys_list[0] if keys_list else ""
                    out["Keys"] = key_val
                    out["Question Type"] = "multi"
                else:
                    out["Key"] = key_val

            if "keys" in mapping and cells[mapping["keys"]]:
                out["Keys"] = cells[mapping["keys"]]
                keys_parts = [k.strip() for k in cells[mapping["keys"]].split("|") if k.strip()]
                if len(keys_parts) > 1:
                    out["Question Type"] = "multi"
                    if not out["Key"]:
                        out["Key"] = keys_parts[0]

            for i in range(1, 5):
                field = f"distractor_{i}"
                if field in mapping:
                    out[f"Distractor {i}"] = cells[mapping[field]]

        # Detect multi-select from stem hints
        if out["Question Type"] == "single":
            stem_lower = stem.lower()
            multi_patterns = [
                r"which\s+(two|three|four|2|3|4)\b",
                r"select\s+(two|three|four|2|3|4)\b",
                r"\(select\s+\d+\)",
                r"\(choose\s+\d+\)",
            ]
            for pat in multi_patterns:
                if re.search(pat, stem_lower):
                    out["Question Type"] = "multi"
                    break

        results.append(out)

    return results


# ---------------------------------------------------------------------------
# Workbook → combined rows
# ---------------------------------------------------------------------------

def convert_workbook(
    path: Path,
    combine: bool = True,
    use_sheet_as_topic: bool = True,
) -> Union[List[dict], Dict[str, List[dict]]]:
    """Convert all sheets in a workbook.

    Args:
        path: Path to the .xlsx file.
        combine: If True, return a single flat list. If False, return
            ``{sheet_name: [rows]}``.
        use_sheet_as_topic: Use the sheet tab name as the default topic
            when no Topic column exists.

    Returns:
        Combined list of row dicts, or dict keyed by sheet name.
    """
    if not HAS_OPENPYXL:
        raise ImportError(
            "openpyxl is required for Excel import. "
            "Install it with: pip install openpyxl"
        )

    wb = load_workbook(str(path), data_only=True)

    if combine:
        all_rows: List[dict] = []
    else:
        all_rows_by_sheet: Dict[str, List[dict]] = {}

    for sheet_name in wb.sheetnames:
        if sheet_name.lower().strip() in SKIP_SHEETS:
            continue

        ws = wb[sheet_name]
        # Skip sheets with fewer than 2 rows
        if ws.max_row is None or ws.max_row < 2:
            continue

        default_topic = sheet_name if use_sheet_as_topic else ""
        rows = convert_sheet(ws, sheet_name=sheet_name, default_topic=default_topic)

        if combine:
            all_rows.extend(rows)
        else:
            if rows:
                all_rows_by_sheet[sheet_name] = rows

    wb.close()
    return all_rows if combine else all_rows_by_sheet


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------

def _write_csv(rows: List[dict], output_path: Path) -> None:
    """Write row dicts to a CSV file with the canonical column header."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def convert_xlsx_to_csv(
    xlsx_path: Path,
    output_path: Optional[Path] = None,
    backup_dir: Optional[Path] = None,
    combine: bool = True,
) -> List[Path]:
    """Convert an .xlsx file to CSV(s) ready for Exam Bank import.

    Args:
        xlsx_path: Path to the Excel file.
        output_path: Where to write the CSV. Defaults to same directory as xlsx,
            with .csv extension.
        backup_dir: If provided, a copy of the CSV is saved here (e.g. assets/questions/).
        combine: If True, one CSV with all sheets. If False, one CSV per sheet.

    Returns:
        List of output CSV file paths.
    """
    xlsx_path = Path(xlsx_path)
    result_paths: List[Path] = []

    if combine:
        rows = convert_workbook(xlsx_path, combine=True)
        if not rows:
            return []
        out = output_path or xlsx_path.with_suffix(".csv")
        _write_csv(rows, out)
        result_paths.append(out)

        # Backup copy
        if backup_dir:
            backup_path = Path(backup_dir) / out.name
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(out, backup_path)
    else:
        sheets = convert_workbook(xlsx_path, combine=False)
        for sheet_name, rows in sheets.items():
            safe_name = re.sub(r'[^\w\-]', '_', sheet_name)
            out = output_path.parent / f"{output_path.stem}_{safe_name}.csv" if output_path else \
                  xlsx_path.parent / f"{xlsx_path.stem}_{safe_name}.csv"
            _write_csv(rows, out)
            result_paths.append(out)

            if backup_dir:
                backup_path = Path(backup_dir) / out.name
                backup_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(out, backup_path)

    return result_paths


# ---------------------------------------------------------------------------
# Direct-to-Question conversion (for GUI integration)
# ---------------------------------------------------------------------------

def import_from_xlsx(path: Path, backup_dir: Optional[Path] = None) -> "List":
    """Import questions from an .xlsx file by converting to CSV first.

    The converted CSV is also saved to ``backup_dir`` (typically ``assets/questions/``)
    as a backup of the converted data.

    Returns a list of Question objects via the existing CSV importer.
    """
    from .question_importer import import_from_csv

    rows = convert_workbook(Path(path), combine=True)
    if not rows:
        return []

    # Write temporary CSV
    tmp_csv = Path(tempfile.gettempdir()) / f"qb_converted_{Path(path).stem}.csv"
    _write_csv(rows, tmp_csv)

    # Save backup copy
    if backup_dir:
        backup_path = Path(backup_dir) / f"{Path(path).stem}_converted.csv"
        Path(backup_dir).mkdir(parents=True, exist_ok=True)
        shutil.copy2(tmp_csv, backup_path)

    # Import via existing pipeline
    questions = import_from_csv(tmp_csv)

    # Clean up temp file
    try:
        tmp_csv.unlink()
    except OSError:
        pass

    return questions


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Convert Excel spreadsheets to Exam Bank CSV format."
    )
    parser.add_argument("xlsx", type=Path, help="Path to the .xlsx file")
    parser.add_argument("-o", "--output", type=Path, default=None,
                        help="Output CSV path (default: same name with .csv)")
    parser.add_argument("--per-sheet", action="store_true",
                        help="Create one CSV per sheet instead of combining")
    parser.add_argument("--backup-dir", type=Path, default=None,
                        help="Directory to save a backup copy of the CSV")

    args = parser.parse_args()

    if not args.xlsx.exists():
        print(f"Error: File not found: {args.xlsx}", file=sys.stderr)
        sys.exit(1)

    paths = convert_xlsx_to_csv(
        args.xlsx,
        output_path=args.output,
        backup_dir=args.backup_dir,
        combine=not args.per_sheet,
    )

    for p in paths:
        print(f"Created: {p}")
    print(f"Total questions converted: {sum(1 for _ in paths)}")
