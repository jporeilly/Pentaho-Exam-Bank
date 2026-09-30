"""The installer's courses search (desktop/scripts/find-courses.ps1).

Run for real, under Windows PowerShell, against checkouts built in a temp
directory. `-ReportOnly` stops it before the registry write, which needs
elevation, and `-Roots` stops it looking at this machine's own checkouts.

The case that prompted these: the dev machine held the main Content Manager
checkout and a git worktree of it on an unmerged branch, both with 13
courses. The search recorded the worktree. The comment beside the sort said
a tie went to the first found, but Windows PowerShell 5.1's Sort-Object is
not stable, and nothing ranked a worktree below a main checkout anyway.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "desktop" / "scripts" / "find-courses.ps1"
POWERSHELL = shutil.which("powershell.exe")

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or POWERSHELL is None,
    reason="the installer runs this under Windows PowerShell",
)


def checkout(root, name, courses, git="dir"):
    """A directory holding `courses` courses.

    git="dir" is a main checkout, git="file" a worktree (its .git is a file
    naming the real repository), git=None a copy with no git at all.
    """
    repo = root / name
    for i in range(courses):
        course = repo / "courses" / f"course-{i}"
        course.mkdir(parents=True)
        (course / "course.json").write_text("{}", encoding="utf-8")
    if git == "dir":
        (repo / ".git").mkdir()
    elif git == "file":
        (repo / ".git").write_text(
            f"gitdir: C:/elsewhere/.git/worktrees/{name}\n", encoding="utf-8"
        )
    return repo


def search(root):
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(SCRIPT), "-Roots", str(root), "-ReportOnly"],
        capture_output=True, text=True, timeout=60,
    )
    return result.returncode, result.stdout


def recorded(stdout):
    """The path the search would record, from its report line."""
    for line in stdout.splitlines():
        if line.startswith("Would record "):
            return line[len("Would record "):].rsplit(" (", 1)[0]
    raise AssertionError(f"no 'Would record' line in:\n{stdout}")


def test_a_main_checkout_beats_a_worktree_it_ties_with(tmp_path):
    """The dev machine, exactly: same name pattern, same course count."""
    main = checkout(tmp_path, "Pentaho-Content-Manager", 3)
    worktree = checkout(tmp_path, "pcm-060", 3, git="file")

    code, out = search(tmp_path)

    assert code == 0, out
    assert recorded(out) == str(main)
    assert f"Passed over git worktree {worktree} (3 courses)." in out, (
        "the install log must say why the worktree was not chosen"
    )


def test_a_main_checkout_beats_a_worktree_with_more_courses(tmp_path):
    """A branch that adds a course must not pull the install onto the branch.
    The worktree is work in flight; the main checkout is what the author
    publishes from."""
    main = checkout(tmp_path, "Pentaho-Content-Manager", 1)
    checkout(tmp_path, "pcm-060", 2, git="file")

    code, out = search(tmp_path)

    assert code == 0, out
    assert recorded(out) == str(main)


def test_a_copy_without_git_is_not_taken_for_a_worktree(tmp_path):
    """A content-only copy (a zip, a clone with .git removed) is usable, and
    the existing rule is that courses/ is the whole requirement. Only a .git
    FILE marks a worktree."""
    copy = checkout(tmp_path, "courses-copy", 1, git=None)
    checkout(tmp_path, "pcm-060", 2, git="file")

    code, out = search(tmp_path)

    assert code == 0, out
    assert recorded(out) == str(copy)


def test_a_worktree_alone_is_still_recorded(tmp_path):
    """Demoted, not refused: a worktree's courses beat an app with none, and
    the author can still change it in Settings."""
    worktree = checkout(tmp_path, "pcm-060", 2, git="file")

    code, out = search(tmp_path)

    assert code == 0, out
    assert recorded(out) == str(worktree)


def test_more_courses_still_wins_between_main_checkouts(tmp_path):
    checkout(tmp_path, "Pentaho-Content-Manager", 1)
    bigger = checkout(tmp_path, "pcm-renamed", 2)

    code, out = search(tmp_path)

    assert code == 0, out
    assert recorded(out) == str(bigger)


def test_a_tie_between_main_checkouts_goes_to_the_named_one(tmp_path):
    """The named checkout is looked at first, and the comment promised the
    first found wins a tie. Sort-Object in 5.1 does not keep that promise on
    its own."""
    named = checkout(tmp_path, "Pentaho-Content-Manager", 2)
    checkout(tmp_path, "another-clone", 2)
    checkout(tmp_path, "zz-clone", 2)

    code, out = search(tmp_path)

    assert code == 0, out
    assert recorded(out) == str(named)


def test_nothing_found_exits_1_without_failing_loudly(tmp_path):
    (tmp_path / "not-a-checkout").mkdir()

    code, out = search(tmp_path)

    assert code == 1
    assert "No Content Manager courses found" in out
