"""The FastAPI application.

Run it from the repo root:

    venv\\Scripts\\python.exe -m uvicorn exam_bank.api.app:app --port 7788

Routes are grouped by the thing they act on and each router stays a thin
translation of ``core``. Nothing here holds state between requests.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..core.providers import ProviderError
from .routers import (
    admin, certifications, courses, docs, exam, export, generation, importing,
    questions, settings, system,
)

log = logging.getLogger(__name__)


def _adopt_courses_on_first_run() -> None:
    """Fill a brand-new bank from the courses on disk.

    A fresh install opened on an empty bank while several hundred questions
    sat in the courses the installer had just found. Both halves were behaving
    correctly - the installer ships no database, because it is the author's
    data and not ours - but nobody had introduced them.

    Guarded by `bank_is_empty`, which requires no questions AND no
    certifications. That is the whole safety argument: there is nothing in an
    empty bank to overwrite, lose or reorder, so this needs no confirmation.
    The moment a bank has anything in it, syncing becomes a decision and goes
    through plan-then-apply like everything else that writes.

    Failure is logged and swallowed. An authoring tool that will not start
    because it could not read somebody else's courses directory is worse than
    one that starts empty and says so in the Courses pane.
    """
    try:
        from ..core import course_sync
        from ..core.bank import ExamBankDB
        from ..utils.config import DB_PATH, config

        root = (config.pcm_courses_dir or "").strip()
        if not root or not Path(root).is_dir():
            return

        db = ExamBankDB(DB_PATH, same_thread_only=False)
        try:
            if not course_sync.bank_is_empty(db):
                return
            plan = course_sync.plan(root, db)
            if not plan.total_new:
                return
            result = course_sync.apply(root, db, expect_token=plan.token)
            log.info(
                "First run: adopted %d questions from %d course(s) in %s",
                result["added"], len(result["courses"]), root,
            )
        finally:
            db.close()
    except Exception as e:  # never let this stop the app starting
        log.warning("First-run course adoption did not run: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _adopt_courses_on_first_run()
    yield


app = FastAPI(
    title="Pentaho Exam Bank",
    version=__version__,
    description="Authoring API for Pentaho certification questions.",
    lifespan=lifespan,
)

# The React front end arrives in 0.4.0 and will be served by Vite on its own
# port in development, so it is a cross-origin caller until it is bundled.
# Localhost only: this API is an authoring tool on one machine and has no
# authentication, so it must not be reachable from anywhere else.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ProviderError)
def provider_error(request: Request, exc: ProviderError) -> JSONResponse:
    """A model that is misconfigured or unreachable is an upstream failure,
    not a bad request — 502, with the provider's own message, which already
    says which key is missing or what could not be reached."""
    return JSONResponse(status_code=502, content={"detail": str(exc)})


app.include_router(system.router)
app.include_router(questions.router)
app.include_router(certifications.router)
app.include_router(courses.router)
app.include_router(generation.router)
app.include_router(export.router)
app.include_router(importing.router)
app.include_router(exam.router)
app.include_router(settings.router)
app.include_router(admin.router)
app.include_router(docs.router)


# ── the built front end ─────────────────────────────────────────
#
# Mounted only when `frontend/dist` exists, so the dev flow is
# unchanged: Vite serves 7789 and proxies /api here. A build makes
# the API one process on one port, which is what the installer will
# ship.
#
# AFTER the routers, deliberately. Starlette matches in registration
# order and a catch-all registered first swallows every /api route -
# the Content Editor's mount_ui carries the same warning, learned the
# same way: the page renders blank with a 200 and no error anywhere.
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def mount_ui() -> bool:
    """Serve `frontend/dist` at the site root. False when unbuilt."""
    index = _DIST / "index.html"
    if not index.is_file():
        return False

    # Hashed assets first, then a catch-all that hands every other
    # path to index.html so a reload deep in the app still works.
    app.mount(
        "/assets",
        StaticFiles(directory=str(_DIST / "assets")),
        name="assets",
    )

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        # NEVER answer for /api. Registering after the routers stops
        # the catch-all shadowing routes that EXIST; it does nothing
        # for a route that exists and REFUSES. A rejected path
        # traversal came back 200 with index.html, which reads as the
        # traversal having worked.
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="No such endpoint")
        candidate = _DIST / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)

    return True


UI_MOUNTED = mount_ui()
