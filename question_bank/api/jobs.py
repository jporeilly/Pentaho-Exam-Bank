"""Background jobs for work that outlives a request.

Generating a course's questions is dozens of model calls and takes minutes, so
it cannot be a plain synchronous endpoint: the client would sit on an open
connection past every sensible timeout and learn nothing about progress. A job
is started, its id returned immediately, and the client polls.

Deliberately in-process and in-memory. This is a single-user authoring tool on
one machine — a queue or a jobs table would be machinery with nothing to do.
The cost is that jobs do not survive a restart, which is the right trade for
work that is re-runnable and never the source of truth; nothing is written to
the bank until the author commits it.
"""

from __future__ import annotations

import threading
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, List

# Finished jobs are kept so a client that polls late still gets its results.
# Capped so a long session cannot grow without bound.
_MAX_RETAINED = 40

RUNNING = "running"
DONE = "done"
ERROR = "error"
CANCELLED = "cancelled"


@dataclass
class Job:
    id: str
    kind: str
    status: str = RUNNING
    current: int = 0
    total: int = 0
    message: str = ""
    result: List[Any] = field(default_factory=list)
    error: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    finished_at: str = ""
    _cancel: bool = False

    @property
    def cancelled(self) -> bool:
        return self._cancel

    def progress(self, current: int, total: int, message: str = "") -> None:
        """Progress callback handed to the worker. Raises `JobCancelled` when
        the author has asked to stop, which unwinds the worker at its next
        checkpoint rather than leaving it running to completion unseen."""
        if self._cancel:
            raise JobCancelled()
        self.current, self.total = current, total
        if message:
            self.message = message

    def as_json(self, serialise: Callable[[Any], dict] | None = None) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "progress": {
                "current": self.current,
                "total": self.total,
                "message": self.message,
            },
            "count": len(self.result),
            "result": [serialise(r) for r in self.result] if serialise else [],
            "error": self.error,
            "createdAt": self.created_at,
            "finishedAt": self.finished_at,
        }


class JobCancelled(Exception):
    """Raised inside a worker when the job has been cancelled."""


_jobs: dict[str, Job] = {}
_lock = threading.Lock()


def get(job_id: str) -> Job | None:
    with _lock:
        return _jobs.get(job_id)


def all_jobs() -> List[Job]:
    with _lock:
        return sorted(_jobs.values(), key=lambda j: j.created_at, reverse=True)


def cancel(job_id: str) -> bool:
    job = get(job_id)
    if not job or job.status != RUNNING:
        return False
    job._cancel = True
    return True


def _prune() -> None:
    """Drop the oldest finished jobs once there are too many. Running jobs are
    never pruned — losing the handle to work still in flight would leave it
    running with nobody able to see it or stop it."""
    finished = [j for j in _jobs.values() if j.status != RUNNING]
    if len(finished) <= _MAX_RETAINED:
        return
    finished.sort(key=lambda j: j.created_at)
    for job in finished[: len(finished) - _MAX_RETAINED]:
        _jobs.pop(job.id, None)


def start(kind: str, work: Callable[[Job], List[Any]]) -> Job:
    """Run `work` on its own thread and return the job immediately.

    `work` is handed the job so it can report progress and check for
    cancellation. Whatever it returns becomes the job's result.
    """
    job = Job(id=str(uuid.uuid4()), kind=kind)
    with _lock:
        _jobs[job.id] = job
        _prune()

    def run() -> None:
        try:
            job.result = work(job) or []
            job.status = DONE
            job.message = job.message or f"Done — {len(job.result)} produced"
        except JobCancelled:
            job.status = CANCELLED
            job.message = "Cancelled"
        except Exception as e:  # noqa: BLE001 — a worker crash must reach the client
            job.status = ERROR
            job.error = f"{type(e).__name__}: {e}"
            # Kept server-side only; the client gets the message, not the trace.
            print(f"[JOB {job.id}] failed\n{traceback.format_exc()}")
        finally:
            job.finished_at = datetime.now().isoformat()

    threading.Thread(target=run, name=f"job-{kind}-{job.id[:8]}", daemon=True).start()
    return job
