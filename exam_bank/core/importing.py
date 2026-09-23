"""Work out what an uploaded file is, and read the questions out of it.

The dispatch used to live inside the NiceGUI tab, interleaved with
``ui.notify`` calls — which meant the *rules* for recognising a file and the
*messages* explaining the consequences could only be reached by rendering a
page. Both matter to anything importing a file, so both are returned as data
here and the caller decides how to show them.

Recognition is by content where the extension is ambiguous, because it is:
``.csv`` covers both real CSV and the plain-text question format, ``.json``
covers both a PCM ``exam.json`` and this bank's own export, and ``.xml``
covers QTI and Moodle. Guessing from the extension alone silently imports the
wrong shape — a text file read as CSV yields one column of nonsense rather
than an error.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .bank import Question
from .question_importer import (
    _is_text_format,
    detect_xml_format,
    import_from_csv,
    import_from_json,
    import_from_moodle_xml,
    import_from_pcm_exam_json,
    import_from_qti21,
    import_from_text,
    is_pcm_exam_json,
)
from .spreadsheet_converter import HAS_OPENPYXL, import_from_xlsx


class UnsupportedFile(Exception):
    """The file is not one this app can read, with a reason that says what is."""


@dataclass(frozen=True)
class DetectedFormat:
    """What a file turned out to be, and what that costs the author."""

    format: str
    label: str
    # Something true about this format that changes what the author must do
    # next. Empty for the formats that carry everything a question needs.
    note: str = ""


#: Extensions worth telling someone about, in the order they are tried.
SUPPORTED = ("CSV", "JSON", "Excel (.xlsx)", "XML (QTI 2.1 or Moodle)", "plain text")


def detect_format(path: Path) -> DetectedFormat:
    """What the file is, decided by content wherever the extension is ambiguous."""
    suffix = path.suffix.lower()

    if suffix == ".csv":
        if _is_text_format(path):
            return DetectedFormat(
                "text", "Plain-text questions",
                "The text format has no way to mark a correct answer, so the FIRST "
                "option of each question is taken as the key. Check every one: a "
                "wrongly-keyed question is gradeable, so nothing else will flag it.",
            )
        return DetectedFormat("csv", "CSV")

    if suffix == ".json":
        if is_pcm_exam_json(path):
            return DetectedFormat(
                "pcm-exam", "Content Manager exam.json",
                "Imported as drafts with their authored ids and citations kept, so "
                "they can be published back to the same course.",
            )
        return DetectedFormat("json", "Exam Bank JSON")

    if suffix == ".xlsx":
        if not HAS_OPENPYXL:
            raise UnsupportedFile(
                "Reading Excel needs openpyxl, which is not installed. Either "
                "install it (pip install openpyxl) or save the sheet as CSV."
            )
        return DetectedFormat("xlsx", "Excel workbook")

    if suffix == ".xml":
        kind = detect_xml_format(path)
        if kind == "qti":
            return DetectedFormat("qti", "QTI 2.1")
        if kind == "moodle":
            return DetectedFormat("moodle", "Moodle XML")
        raise UnsupportedFile(
            "That XML is neither QTI 2.1 nor Moodle XML. Those are the two this "
            "app can read."
        )

    raise UnsupportedFile(
        f"There is no reader for '{suffix or path.name}'. Supported: "
        f"{', '.join(SUPPORTED)}."
    )


_READERS = {
    "csv": import_from_csv,
    "text": import_from_text,
    "json": import_from_json,
    "pcm-exam": import_from_pcm_exam_json,
    "qti": import_from_qti21,
    "moodle": import_from_moodle_xml,
}


def import_any(path: Path, *, backup_dir: Path | None = None) -> tuple[list[Question], DetectedFormat]:
    """Read the questions out of a file, whatever supported format it is in.

    Raises :class:`UnsupportedFile` rather than returning an empty list for a
    file it cannot read: nothing found and nothing readable look identical to
    a caller, and only one of them is the author's mistake to fix.
    """
    detected = detect_format(path)

    if detected.format == "xlsx":
        questions = import_from_xlsx(path, backup_dir=backup_dir)
    else:
        questions = _READERS[detected.format](path)

    return list(questions), detected
