"""Move the version in every carrier at once, and cut the changelog release.

VERSION.md used to describe this as five manual steps across three files.
Phase 4 took it to NINE carriers in seven files, two of them lockfiles npm
rewrites on install - at which point "carefully edit each one" stops being
a process and becomes a list of chances to miss one. The Content Manager
learned this the expensive way: its lockfile sat six releases behind
because nothing was looking at it.

`tests/test_version.py` is the guard and stays the guard. This is the tool
that makes the guard pass on the first try.

    python scripts/bump.py 1.0.0
    python scripts/bump.py 1.0.0 --dry-run

The changelog's `## [Unreleased]` heading becomes `## [x.y.z] - <today>`
and a fresh Unreleased section opens above it, because a release that eats
the Unreleased heading leaves the next change nowhere to go.
"""

import argparse
import datetime as _dt
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (path, regex with ONE group for the version, human name)
#
# Every pattern is anchored to the line and the key it belongs to. A bare
# search for the old version string would also hit a DEPENDENCY that
# happens to be on the same number - the lockfiles are full of them.
CARRIERS = [
    ("exam_bank/__init__.py",
     r'(?m)^__version__ = "([0-9]+\.[0-9]+\.[0-9]+)"$',
     "the source of truth"),
    ("VERSION.md",
     r'(?m)^\*\*Current:\s*([0-9]+\.[0-9]+\.[0-9]+)\*\*',
     "the Current: line"),
    ("desktop/package.json",
     r'(?m)^  "version": "([0-9]+\.[0-9]+\.[0-9]+)",',
     "the desktop package"),
    ("desktop/package-lock.json",
     r'(?m)^  "version": "([0-9]+\.[0-9]+\.[0-9]+)",',
     "the desktop lockfile, top level"),
    ("desktop/package-lock.json",
     r'(?m)^      "version": "([0-9]+\.[0-9]+\.[0-9]+)",',
     'the desktop lockfile, packages[""]'),
    ("frontend/package.json",
     r'(?m)^  "version": "([0-9]+\.[0-9]+\.[0-9]+)",',
     "the frontend package"),
    ("frontend/package-lock.json",
     r'(?m)^  "version": "([0-9]+\.[0-9]+\.[0-9]+)",',
     "the frontend lockfile, top level"),
    ("frontend/package-lock.json",
     r'(?m)^      "version": "([0-9]+\.[0-9]+\.[0-9]+)",',
     'the frontend lockfile, packages[""]'),
    ("desktop/src-tauri/tauri.conf.json",
     r'(?m)^  "version": "([0-9]+\.[0-9]+\.[0-9]+)",',
     "the Tauri config"),
    ("desktop/src-tauri/Cargo.toml",
     r'(?m)^version = "([0-9]+\.[0-9]+\.[0-9]+)"$',
     "the crate"),
    # Cargo.lock holds every dependency's version too, so this one is
    # anchored to OUR package block rather than to a line shape.
    ("desktop/src-tauri/Cargo.lock",
     r'(?m)^name = "pentaho-exam-bank"\nversion = "([0-9]+\.[0-9]+\.[0-9]+)"$',
     "the Cargo lockfile"),
]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def _write(rel, text):
    # newline="\n": this tree is LF and git has core.autocrlf on. Letting
    # Python translate would rewrite every line of a lockfile as a change.
    (ROOT / rel).write_text(text, encoding="utf-8", newline="\n")


def bump_changelog(new, today, dry_run):
    text = _read("CHANGELOG.md")
    if not re.search(r"(?m)^##\s*\[Unreleased\]", text):
        sys.exit("CHANGELOG.md has no [Unreleased] heading to cut.")
    replacement = (
        "## [Unreleased]\n"
        "\n"
        f"## [{new}] - {today}"
    )
    text = re.sub(r"(?m)^##\s*\[Unreleased\]", replacement, text, count=1)
    if not dry_run:
        _write("CHANGELOG.md", text)
    print(f"  [ok]   CHANGELOG.md          -> [{new}] - {today}, fresh Unreleased")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("version", help="the new version, x.y.z")
    ap.add_argument("--dry-run", action="store_true",
                    help="say what would change and write nothing")
    args = ap.parse_args()

    new = args.version
    if not re.fullmatch(r"\d+\.\d+\.\d+", new):
        sys.exit(f"{new!r} is not a plain x.y.z")

    today = _dt.date.today().isoformat()
    current = re.search(CARRIERS[0][1], _read(CARRIERS[0][0])).group(1)
    print(f"\n  {current} -> {new}\n")

    # Group by file so a file touched twice is read and written once.
    edits = {}
    for rel, pattern, label in CARRIERS:
        text = edits.get(rel, _read(rel))
        match = re.search(pattern, text)
        if not match:
            sys.exit(f"  [FAIL] {rel}: no match for {label} - "
                     "the file's shape changed, fix the pattern")
        found = match.group(1)
        if found != current:
            # Not fatal-by-assumption: report which one drifted and stop
            # before writing anything, so a half-bumped tree is impossible.
            sys.exit(f"  [FAIL] {rel}: {label} says {found}, "
                     f"expected {current}. Fix the drift first.")
        start, end = match.span(1)
        edits[rel] = text[:start] + new + text[end:]
        print(f"  [ok]   {rel:<38} {label}")

    if not args.dry_run:
        for rel, text in edits.items():
            _write(rel, text)

    bump_changelog(new, today, args.dry_run)

    if args.dry_run:
        print("\n  (dry run - nothing written)\n")
    else:
        print("\n  Now run the tests; test_version.py checks every carrier.\n")


if __name__ == "__main__":
    main()
