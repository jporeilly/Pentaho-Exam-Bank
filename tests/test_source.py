"""Tests for core/source.py — the unit of source material a question comes from.

Salvaged from test_pptx_reader.py when SlideInfo moved out of the PPTX reader.
The type is shared by every generation source, so it outlives that module.
"""

from pathlib import Path

from exam_bank.core.source import SlideInfo


class TestSlideInfo:
    def test_basic_creation(self):
        section = SlideInfo(index=0, speaker_notes="Test notes")
        assert section.index == 0
        assert section.speaker_notes == "Test notes"
        assert section.title is None
        assert section.body_text is None
        assert section.thumbnail_path is None

    def test_full_creation(self):
        section = SlideInfo(
            index=5,
            speaker_notes="Notes here",
            title="My Title",
            body_text="Body content",
            thumbnail_path=Path("thumb.png"),
        )
        assert section.title == "My Title"
        assert section.body_text == "Body content"
        assert section.thumbnail_path == Path("thumb.png")


def test_importable_without_python_pptx():
    """The whole point of the move: reading course or docs content must not
    drag in python-pptx. Six modules import this type and only one of them
    has anything to do with slides."""
    import ast
    import sys
    from pathlib import Path as P

    src = P(__file__).resolve().parents[1] / "exam_bank" / "core" / "source.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    imported = {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "pptx" not in imported, f"source.py pulls in {imported}"
    # And it really does import cleanly on its own.
    assert "exam_bank.core.source" in sys.modules
