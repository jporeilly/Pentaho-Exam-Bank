"""Add an entry to the Unreleased block of CHANGELOG.md, in the right section.

Written after making the same mistake three times in three days: inserting
"### Added" (or Changed, or Fixed) at the top of the Unreleased block when one
already existed further down, leaving two sections of the same name in one
release and bullets stranded under the wrong heading.

Hand-editing is fine for prose. This is for the mechanical part - finding the
section, or creating it in Keep a Changelog's order, and putting the bullet at
the top of it.

    python scripts/changelog.py Fixed entry.md
    python scripts/changelog.py Added - "**A one-line entry.**"

`-` reads the entry from stdin. The entry is inserted verbatim, so it carries
its own bullet and wrapping.
"""

from __future__ import annotations

import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parents[1] / "CHANGELOG.md"

#: Keep a Changelog's order. A section that does not exist yet is created in
#: this position rather than at the top, so the block stays in the order
#: everything else in the file uses.
ORDER = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security")

UNRELEASED = "## [Unreleased]"


def sections(block: str) -> dict[str, int]:
    """Where each `### Name` heading starts within the block."""
    found = {}
    for name in ORDER:
        marker = f"### {name}\n"
        at = block.find(marker)
        if at >= 0:
            found[name] = at
    return found


def add(text: str, section: str) -> str:
    """CHANGELOG.md with `text` added to the named section of Unreleased."""
    doc = CHANGELOG.read_text(encoding="utf-8")

    start = doc.index(UNRELEASED) + len(UNRELEASED)
    end = doc.index("\n## ", start)          # the next released version
    block, rest = doc[start:end], doc[end:]

    entry = text.strip() + "\n\n"
    present = sections(block)

    if section in present:
        at = present[section] + len(f"### {section}\n")
        # Past the blank line the heading is followed by, so the entry lands
        # as the first bullet rather than glued to the heading.
        while at < len(block) and block[at] == "\n":
            at += 1
        block = block[:at] + entry + block[at:]
    else:
        # Insert before the first section that sorts after this one, so the
        # block keeps Keep a Changelog's order.
        later = [ORDER.index(n) for n in present if ORDER.index(n) > ORDER.index(section)]
        if later:
            after = ORDER[min(later)]
            at = present[after]
        else:
            at = len(block)
        block = block[:at] + f"### {section}\n\n" + entry + block[at:]

    return doc[:start] + block + rest


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    section, source = argv[1], argv[2]
    if section not in ORDER:
        print(f"Section must be one of {', '.join(ORDER)}, not {section!r}", file=sys.stderr)
        return 2

    text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    if not text.strip():
        print("Nothing to add.", file=sys.stderr)
        return 2

    CHANGELOG.write_text(add(text, section), encoding="utf-8", newline="\n")
    print(f"Added to {section}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
