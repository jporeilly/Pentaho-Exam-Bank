"""The version string is hand-kept in several files; this test keeps them equal.

Source of truth: ``question_bank.__version__``. Every other carrier — the
**Current:** line in VERSION.md and the most recent release heading in
CHANGELOG.md — must match it exactly. See VERSION.md for the bump policy.

Phases 3 and 4 add carriers this app does not have yet (package.json and its
lockfile, tauri.conf.json, Cargo.toml, Cargo.lock). Add each one here as it
arrives: a carrier nobody checks is a carrier that drifts.
"""

import re
from pathlib import Path

from question_bank import __version__ as VERSION

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def test_version_is_plain_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", VERSION), (
        f"__version__ is {VERSION!r}; it must be a plain x.y.z"
    )


def test_version_md_current_line_agrees():
    text = _read("VERSION.md")
    match = re.search(r"^\*\*Current:\s*([0-9]+\.[0-9]+\.[0-9]+)", text, re.M)
    assert match, "VERSION.md has no '**Current: x.y.z**' line"
    assert match.group(1) == VERSION, (
        f"VERSION.md says {match.group(1)}, __version__ says {VERSION}"
    )


def test_changelog_latest_release_agrees():
    """The newest release heading must be this version.

    Read the FIRST `## [x.y.z]` heading rather than searching for the current
    version anywhere in the file: a bump that adds no changelog entry would
    otherwise pass by matching an older release that happens to mention it.
    """
    text = _read("CHANGELOG.md")
    headings = re.findall(r"^##\s*\[([^\]]+)\]", text, re.M)
    releases = [h for h in headings if h.lower() != "unreleased"]
    assert releases, "CHANGELOG.md has no release heading"
    assert releases[0] == VERSION, (
        f"CHANGELOG.md's newest release is {releases[0]}, __version__ says {VERSION}"
    )


def test_changelog_keeps_an_unreleased_section():
    """Every release opens a fresh Unreleased section; without one the next
    change has nowhere to go and lands in the shipped release's notes."""
    assert re.search(r"^##\s*\[Unreleased\]", _read("CHANGELOG.md"), re.M | re.I), (
        "CHANGELOG.md has no [Unreleased] section"
    )


def test_release_heading_carries_a_date():
    text = _read("CHANGELOG.md")
    match = re.search(r"^##\s*\[" + re.escape(VERSION) + r"\]\s*-\s*(\S+)", text, re.M)
    assert match, f"CHANGELOG.md's [{VERSION}] heading has no '- YYYY-MM-DD' date"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", match.group(1)), (
        f"date is {match.group(1)!r}; it must be YYYY-MM-DD"
    )


def test_the_docs_the_house_rules_require_all_exist():
    for name in ("VERSION.md", "CHANGELOG.md", "INSTALL.md", "README.md"):
        assert (ROOT / name).is_file(), f"{name} is missing"
