"""Push a published exam to the courses repo that installed apps sync from.

Publishing writes a course's ``exam.json`` in the Content Manager's authoring
tree, and until now it stopped there. An installed Content Manager never reads
that tree: at every launch it syncs from the distribution repo
(Pentaho-Courses), so a published exam reached nobody until somebody pushed it
by hand. This closes that gap, as one step with the publish:

1. bump the course's version in ``course.json`` (patch), so an installer or a
   synced machine says it carries new content;
2. add a line to the Content Manager's CHANGELOG under [Unreleased];
3. commit exactly those three files in the authoring repo, and push;
4. copy ``exam.json`` into the distribution repo, set the same version in the
   PUBLISHED ``course.json``, commit exactly those two files, and push.

**Only the exam.** The bank owns questions, nothing else. Pushing the whole
course folder - which is what the Content Editor's publish does - would carry
every other unpublished change with it: lab guides, certificate settings,
workshop paths that may need a newer installer. So the distribution's
``course.json`` keeps everything it had and changes one value, its version.

**Refuse before writing.** :func:`preflight` runs before the exam is written
and checks everything that can be known in advance: git is available, the
authoring tree is a repo that is up to date with its remote, and the three
files this commits have no uncommitted changes of somebody else's that a
commit would sweep in. What can only fail later (the network, a remote that
moved) is reported by :func:`release` as the stage it reached.

Three hazards learned the hard way, each guarded here:

- A full clone of Pentaho-Courses aborts part-way on Windows, where one
  course's path is too long, and staging from that partial tree records every
  missing course as deleted. So the clone is SPARSE, one course only, and the
  staged paths are asserted before anything is committed.
- The repo is PUBLIC and already holds live credentials. Nothing is pushed if
  it would put a secret-like value there that is not there already.
- ``git add -A`` sweeps up whatever else is lying in a tree. Every commit here
  names its paths.
"""

from __future__ import annotations

import os
import os
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

GIT_TIMEOUT_SECS = 180

#: Git on PATH first, then the MinGit the Content Editor and the Content
#: Manager each ship. A bare "git" is only right on a machine that happens to
#: have one; an install must be able to say it has none.
_BUNDLED_GIT = (
    Path(r"C:\Program Files\Pentaho Content Editor\mingit\cmd\git.exe"),
    Path(r"C:\Program Files\Pentaho Content Manager\mingit\cmd\git.exe"),
)

_VERSION = re.compile(r'("version"\s*:\s*")(\d+)\.(\d+)\.(\d+)(")')
_SECRET = re.compile(
    r'"(apiSecret|webhookSecret|secret|token|apiKey|password)"\s*:\s*"([^"]+)"', re.I
)
_SCRIPT_URL = re.compile(r"https://script\.google\.com/macros/s/[A-Za-z0-9_-]+/exec")


class DistributionRefused(Exception):
    """Refuse to push, with a reason the author can act on."""


@dataclass(frozen=True)
class Preflight:
    """What a push would do, established before anything is written."""

    git: str
    authoring_root: Path
    course_dir: Path
    version_from: str
    version_to: str
    repo_url: str
    repo_ref: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": True,
            "reason": "",
            "versionFrom": self.version_from,
            "versionTo": self.version_to,
            "coursesRepo": self.repo_url,
            "ref": self.repo_ref,
        }


def find_git() -> Optional[str]:
    override = os.environ.get("PEB_GIT", "").strip()
    if override and Path(override).is_file():
        return override
    found = shutil.which("git")
    if found:
        return found
    for candidate in _BUNDLED_GIT:
        if candidate.is_file():
            return str(candidate)
    return None


def _remove_tree(path: Path) -> None:
    """Delete a previous clone, read-only files and all, or refuse.

    git writes its object files read-only, and on Windows ``shutil.rmtree``
    cannot delete a read-only file. With ``ignore_errors=True`` - what this
    used - it said nothing and left the ``.git`` folder behind, so the clone
    that followed found its destination "not an empty directory" and failed:
    every publish-and-push after the machine's first one. Found 2026-09-29,
    re-publishing pdi-2hr-lab, with 76 object files left over from the first.
    """
    def writable_then_retry(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    if not path.exists():
        return
    try:
        if sys.version_info >= (3, 12):
            shutil.rmtree(path, onexc=writable_then_retry)
        else:  # pragma: no cover - the vendored runtime is 3.12
            shutil.rmtree(path, onerror=writable_then_retry)
    except OSError as e:
        raise DistributionRefused(
            f"Could not clear the previous copy of the courses repo at {path}: {e}. "
            "Nothing was pushed. Close anything that has a file open there and try again."
        ) from e


def _run(git: str, args: list[str], cwd: Path) -> str:
    """Run git without prompts; raise DistributionRefused with its message."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    try:
        proc = subprocess.run(
            [git, *args], cwd=str(cwd), env=env, capture_output=True, text=True,
            timeout=GIT_TIMEOUT_SECS, encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired as e:
        raise DistributionRefused(f"git {args[0]} took longer than {GIT_TIMEOUT_SECS}s.") from e
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()[-600:]
        raise DistributionRefused(f"git {' '.join(args[:2])} failed: {detail}")
    return proc.stdout.strip()


def _bump_patch(text: str) -> tuple[str, str, str]:
    """(text with the version's patch number raised, old, new). Exactly one
    version field, or it refuses - guessing which one to raise is how a
    version ends up somewhere it was never meant to be."""
    matches = list(_VERSION.finditer(text))
    if len(matches) != 1:
        raise DistributionRefused(
            f"course.json must hold exactly one \"version\": \"x.y.z\"; found {len(matches)}."
        )
    m = matches[0]
    old = f"{m.group(2)}.{m.group(3)}.{m.group(4)}"
    new = f"{m.group(2)}.{m.group(3)}.{int(m.group(4)) + 1}"
    return text[: m.start()] + f"{m.group(1)}{new}{m.group(5)}" + text[m.end():], old, new


def _set_version(text: str, version: str) -> str:
    matches = list(_VERSION.finditer(text))
    if len(matches) != 1:
        raise DistributionRefused(
            f"The published course.json must hold exactly one version; found {len(matches)}."
        )
    m = matches[0]
    return text[: m.start()] + f"{m.group(1)}{version}{m.group(5)}" + text[m.end():]


def _read(path: Path) -> tuple[str, str]:
    """(text with LF endings, the newline the file uses)."""
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n"), newline


def _write(path: Path, text: str, newline: str) -> None:
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))


def _secrets(text: str) -> set[tuple[str, str]]:
    found = {(m.group(1), m.group(2)) for m in _SECRET.finditer(text) if m.group(2).strip()}
    found |= {("apps-script-url", m.group(0)) for m in _SCRIPT_URL.finditer(text)}
    return found


def preflight(courses_dir: Path, slug: str, *, repo_url: str, repo_ref: str,
              git: Optional[str] = None) -> Preflight:
    """Everything a push needs, checked before the exam is written."""
    git = git or find_git()
    if not git:
        raise DistributionRefused(
            "No git was found on this machine, so the exam cannot be pushed to the "
            "courses repo. Install Git for Windows, or the Content Editor, which "
            "ships its own."
        )
    course_dir = Path(courses_dir) / slug
    root = Path(courses_dir).resolve().parent
    try:
        top = Path(_run(git, ["rev-parse", "--show-toplevel"], root)).resolve()
    except DistributionRefused as e:
        raise DistributionRefused(
            f"{root} is not a git repository, so a published exam cannot be committed "
            "from it."
        ) from e
    if top != root:
        raise DistributionRefused(
            f"The courses folder's parent ({root}) is not the root of its repository "
            f"({top}); refusing rather than committing from the wrong place."
        )

    _run(git, ["fetch", "--quiet"], root)
    try:
        behind = int(_run(git, ["rev-list", "--count", "HEAD..@{u}"], root) or "0")
    except DistributionRefused as e:
        raise DistributionRefused(
            "The Content Manager repository's branch has no upstream to push to."
        ) from e
    if behind:
        raise DistributionRefused(
            f"The Content Manager repository is {behind} commit(s) behind its remote. "
            "Pull it first, so the publish is committed on top of the latest work."
        )

    paths = [f"courses/{slug}/exam.json", f"courses/{slug}/course.json", "CHANGELOG.md"]
    dirty = _run(git, ["status", "--porcelain", "--", *paths], root)
    if dirty:
        raise DistributionRefused(
            "These have uncommitted changes in the Content Manager repository, and a "
            "push would commit them along with the exam: "
            # Split, not sliced: the output is stripped, so the first line has
            # lost its leading space and `line[3:]` cut "courses" to "ourses".
            + ", ".join(line.split(maxsplit=1)[-1] for line in dirty.splitlines())
            + ". Commit or discard them first."
        )

    text, _ = _read(course_dir / "course.json")
    _, old, new = _bump_patch(text)
    return Preflight(git=git, authoring_root=root, course_dir=course_dir,
                     version_from=old, version_to=new, repo_url=repo_url, repo_ref=repo_ref)


def _changelog_line(title: str, summary: dict[str, Any], old: str, new: str) -> str:
    parts = []
    for key, word in (("added", "added"), ("changed", "edited"), ("removed", "removed")):
        ids = summary.get(key) or []
        if ids:
            parts.append(f"{word}: {', '.join(ids)}")
    detail = "; ".join(parts) if parts else "no question changed"
    n = summary.get("afterCount", 0)
    return (f"- **{title} exam published from the Exam Bank.** "
            f"{n} question{'' if n == 1 else 's'} — {detail}. "
            f"Course version {old} → {new}.")


def _add_changelog_line(path: Path, line: str) -> None:
    """Insert a bullet at the top of [Unreleased] ### Changed, making either if
    missing. Everything else in the file is left as it was."""
    text, newline = _read(path)
    head = "## [Unreleased]"
    i = text.find(head)
    if i < 0:
        raise DistributionRefused("CHANGELOG.md has no [Unreleased] section to add the publish to.")
    start = i + len(head)
    end = text.find("\n## [", start)
    end = len(text) if end < 0 else end
    # The body runs from the end of the heading line to the newline before the
    # next release heading, so it ends with the text and the next heading keeps
    # its blank line.
    body = text[start:end].replace("\nNothing yet.\n", "\n", 1)
    marker = "\n### Changed\n"
    j = body.find(marker)
    if j >= 0:
        k = j + len(marker)
        if body[k:k + 1] == "\n":
            k += 1
        body = body[:k] + line + "\n\n" + body[k:]
    else:
        rest = body.strip("\n")
        body = f"\n\n### Changed\n\n{line}\n" + (f"\n{rest}\n" if rest else "")
    _write(path, text[:start] + body + text[end:], newline)


def release(pre: Preflight, slug: str, title: str, summary: dict[str, Any],
            cache_dir: Path) -> dict[str, Any]:
    """Bump, record, commit and push - the half that runs after the write.

    The distribution copy is prepared and checked BEFORE the authoring tree is
    touched, so a secret, a stray path or a course that was never published
    stops everything with nothing bumped, nothing committed, nothing pushed.
    Returns what happened at each stage; raises only for a refusal.
    """
    git = pre.git
    root = pre.authoring_root
    stage = "prepare"
    result: dict[str, Any] = {"versionFrom": pre.version_from, "versionTo": pre.version_to,
                              "coursesRepo": pre.repo_url}

    # ── the distribution clone: sparse, this course only ──
    clone = Path(cache_dir) / "courses-repo"
    _remove_tree(clone)
    clone.parent.mkdir(parents=True, exist_ok=True)
    _run(git, ["clone", "--quiet", "--filter=blob:none", "--no-checkout", "--branch",
               pre.repo_ref, pre.repo_url, str(clone)], clone.parent)
    _run(git, ["config", "core.longpaths", "true"], clone)
    _run(git, ["sparse-checkout", "set", "--cone", slug], clone)
    _run(git, ["checkout", "--quiet", pre.repo_ref], clone)
    published = clone / slug
    if not (published / "course.json").is_file():
        raise DistributionRefused(
            f"{slug} has never been published to the courses repo. Publish the whole "
            "course once from the Content Editor; after that the Exam Bank can keep "
            "its exam up to date."
        )

    # ── stage the distribution: the exam, and one value in course.json ──
    shutil.copyfile(pre.course_dir / "exam.json", published / "exam.json")
    pub_text, pub_nl = _read(published / "course.json")
    _write(published / "course.json", _set_version(pub_text, pre.version_to), pub_nl)
    _run(git, ["add", "--", f"{slug}/exam.json", f"{slug}/course.json"], clone)
    staged = set(_run(git, ["diff", "--cached", "--name-only"], clone).splitlines())
    allowed = {f"{slug}/exam.json", f"{slug}/course.json"}
    if not staged:
        result["courses"] = {"pushed": False, "upToDate": True}
    elif not staged <= allowed:
        raise DistributionRefused(
            f"Staging touched files outside this course's exam: {sorted(staged - allowed)}. "
            "Nothing was pushed."
        )

    # Every secret-like value about to be pushed must already be public.
    outgoing: set[tuple[str, str]] = set()
    for rel in allowed:
        outgoing |= _secrets((clone / rel).read_text(encoding="utf-8", errors="replace"))
    public: set[tuple[str, str]] = set()
    tree = _run(git, ["ls-tree", "-r", "--name-only", "HEAD"], clone).splitlines()
    for path in tree:
        if path.endswith(("/course.json", "/exam.json")):
            public |= _secrets(_run(git, ["show", f"HEAD:{path}"], clone))
    new_secrets = outgoing - public
    if new_secrets:
        kinds = sorted({k for k, _ in new_secrets})
        raise DistributionRefused(
            f"Pushing would put a {', '.join(kinds)} value into the public courses repo "
            "that is not there already. Nothing was pushed; remove it from the course "
            "files first."
        )

    # ── only now touch the authoring tree: every check above has passed ──
    course_json = pre.course_dir / "course.json"
    text, nl = _read(course_json)
    bumped, _, _ = _bump_patch(text)
    _write(course_json, bumped, nl)
    line = _changelog_line(title, summary, pre.version_from, pre.version_to)
    _add_changelog_line(root / "CHANGELOG.md", line)
    result["changelog"] = line

    # ── authoring: commit exactly the three files, push ──
    stage = "authoring"
    message = (f"Publish the {title} exam from the Exam Bank (course {pre.version_to})\n\n"
               f"{line[2:]}")
    try:
        _run(git, ["add", "--", f"courses/{slug}/exam.json", f"courses/{slug}/course.json",
                   "CHANGELOG.md"], root)
        _run(git, ["commit", "--quiet", "-m", message, "--",
                   f"courses/{slug}/exam.json", f"courses/{slug}/course.json", "CHANGELOG.md"], root)
        result["authoring"] = {"commit": _run(git, ["rev-parse", "HEAD"], root)}
        _run(git, ["push", "--quiet"], root)
        result["authoring"]["pushed"] = True

        # ── distribution: commit the two files, push ──
        stage = "courses"
        if staged:
            _run(git, ["commit", "--quiet", "-m", message], clone)
            result["courses"] = {"commit": _run(git, ["rev-parse", "HEAD"], clone)}
            _run(git, ["push", "--quiet", "origin", pre.repo_ref], clone)
            result["courses"]["pushed"] = True
    except DistributionRefused as e:
        result["failedAt"] = stage
        result["error"] = str(e)
    return result
