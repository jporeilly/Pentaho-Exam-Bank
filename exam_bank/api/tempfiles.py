"""Temporary files that are deleted once the response has been sent.

Shared by every route that builds a file and hands it back. Written twice it
was also, on the second occasion, written without the cleanup — and a leaked
export is invisible: the download works, and the file sits in the temp
directory for the life of the machine.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable


def temp_path(suffix: str, prefix: str = "peb-") -> Path:
    """An empty file that something is about to be written into."""
    handle = tempfile.NamedTemporaryFile(prefix=prefix, suffix=f".{suffix}", delete=False)
    handle.close()
    return Path(handle.name)


def cleanup(path: Path) -> Callable[[], None]:
    """A background task that deletes ``path``.

    Errors are swallowed on purpose: the response has already gone out, and a
    temp file that cannot be removed is not worth failing a download over.
    """

    def remove() -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    return remove
