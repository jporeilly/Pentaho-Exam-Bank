"""The version string is hand-kept in several files; this test keeps them equal.

Source of truth: ``exam_bank.__version__``. Every other carrier — the
**Current:** line in VERSION.md and the most recent release heading in
CHANGELOG.md — must match it exactly. See VERSION.md for the bump policy.

Phase 4 brought the rest: package.json and its lockfile for both the desktop
shell and the frontend, tauri.conf.json, Cargo.toml and Cargo.lock. They are
checked from `scripts/bump.py`'s carrier table, so the tool that writes them
and the test that checks them cannot disagree about where they are.
"""

import re
import sys
from pathlib import Path

from exam_bank import __version__ as VERSION

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from bump import CARRIERS  # noqa: E402  (needs the path above)

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


def test_every_carrier_bump_py_knows_about_agrees():
    """The Phase 3 and 4 carriers: package.json and its lockfile (twice
    each, top level and packages[""]), tauri.conf.json, Cargo.toml and
    Cargo.lock.

    The table is imported from `scripts/bump.py` rather than written out
    again here. Two copies of "where the version lives" is the same
    decision in two places, and the first change to either would make one
    of them wrong - which is exactly the failure this test exists to
    catch. A pattern that stops matching its file fails here loudly rather
    than silently checking nothing.
    """
    assert CARRIERS, "bump.py's carrier table is empty"
    seen = set()
    for rel, pattern, label in CARRIERS:
        text = _read(rel)
        match = re.search(pattern, text)
        assert match, (
            f"{rel}: nothing matches the pattern for {label}. The file's "
            "shape changed; fix scripts/bump.py and this passes again."
        )
        assert match.group(1) == VERSION, (
            f"{rel} ({label}) says {match.group(1)}, __version__ says {VERSION}"
        )
        seen.add(rel)

    # The carriers that existed before Phase 4 are checked individually
    # above; these are the ones the installer brought in. Named explicitly
    # so DELETING a row from bump.py's table cannot quietly shrink what is
    # verified - the test would still pass over whatever was left.
    for required in ("desktop/package.json", "desktop/package-lock.json",
                     "frontend/package.json", "frontend/package-lock.json",
                     "desktop/src-tauri/tauri.conf.json",
                     "desktop/src-tauri/Cargo.toml",
                     "desktop/src-tauri/Cargo.lock"):
        assert required in seen, f"{required} is not in bump.py's carrier table"
