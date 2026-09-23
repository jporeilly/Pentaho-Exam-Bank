"""The changelog helper, which exists because the same mistake happened three
times: a `### Added` inserted at the top of Unreleased when one already
existed further down, leaving two sections of one name and bullets under the
wrong heading."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import changelog  # noqa: E402

HEAD = """\
# Changelog

## [Unreleased]

### Added

- **An existing addition.**

### Fixed

- **An existing fix.**

## [0.1.0] - 2026-09-21

### Added

- **Something released.**
"""


@pytest.fixture
def doc(tmp_path, monkeypatch):
    path = tmp_path / "CHANGELOG.md"
    path.write_text(HEAD, encoding="utf-8")
    monkeypatch.setattr(changelog, "CHANGELOG", path)
    return path


def headings(text):
    unreleased = text.split("## [Unreleased]")[1].split("\n## ")[0]
    return [l[4:] for l in unreleased.splitlines() if l.startswith("### ")]


def test_an_entry_joins_the_section_that_already_exists(doc):
    out = changelog.add("- **A new addition.**", "Added")

    assert headings(out) == ["Added", "Fixed"], "a second Added section was created"
    assert out.count("### Added") == 2, "the released block's Added was touched"


def test_it_goes_to_the_top_of_its_section(doc):
    out = changelog.add("- **Newest.**", "Added")
    added = out.split("### Added\n")[1]

    assert added.index("**Newest.**") < added.index("**An existing addition.**")


def test_a_missing_section_is_created_in_keep_a_changelog_order(doc):
    out = changelog.add("- **Gone away.**", "Removed")

    # Added, Changed, Deprecated, REMOVED, Fixed - so it lands before Fixed.
    assert headings(out) == ["Added", "Removed", "Fixed"]


def test_a_section_that_sorts_last_goes_last(doc):
    out = changelog.add("- **A vulnerability.**", "Security")

    assert headings(out) == ["Added", "Fixed", "Security"]


def test_the_released_block_is_never_touched(doc):
    out = changelog.add("- **A new addition.**", "Added")

    released = out.split("## [0.1.0]")[1]
    assert "A new addition" not in released
    assert "**Something released.**" in released


def test_an_unknown_section_is_refused(doc, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["changelog.py", "Improved", "-"])

    assert changelog.main(sys.argv) == 2
