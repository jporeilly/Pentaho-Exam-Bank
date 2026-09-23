"""Entry point for the desktop shell's backend.

Why this exists rather than `python -m exam_bank.api`, which is what
`run.bat` runs from a checkout:

The vendored runtime is Python's Windows "embeddable package", whose
`._pth` file REPLACES sys.path outright. The current directory is not on
it and PYTHONPATH is ignored while a `._pth` is present, so `exam_bank`
is simply not importable no matter what working directory the process is
given. The failure is a bare ModuleNotFoundError with nothing pointing at
the cause.

Putting the app root on sys.path explicitly fixes that, and gives the
packaged and development launches ONE code path rather than two that can
drift.

    python boot.py --port 7788 [--app-dir <dir>]

--app-dir defaults to the directory beside this file, which is the shape
stage-app.ps1 produces:

    app/boot.py
    app/exam_bank/api/app.py
    app/frontend/dist/index.html

The ROOT goes on sys.path, not `exam_bank/` - unlike the Content Editor,
whose api modules import each other flatly, this is a real package and
everything inside it imports as `exam_bank.something`.

That layout is not cosmetic either. `api/app.py` resolves the built UI as
`parents[2]/frontend/dist`, which is two levels above itself; flattening
the tree would leave the server running with no interface to serve, which
looks exactly like a crash and is not one.
"""
import argparse
import os
import sys


def _plain(path):
    r"""Drop Windows' verbatim \\?\ prefix from a drive path.

    os.chdir() cannot use one: SetCurrentDirectory rejects the verbatim
    form, so an install under C:\Program Files fails here with every path
    check passing. The shell strips it too - this is the second line of
    defence, because the cost of getting it wrong is a server that dies
    before it can say why.

    Genuine UNC paths (\\?\UNC\...) and paths over the legacy limit still
    need the prefix, so only ordinary drive paths are unwrapped.
    """
    p = str(path)
    if p.startswith("\\\\?\\"):
        rest = p[4:]
        if len(rest) > 2 and rest[1] == ":" and rest[0].isalpha() and len(rest) < 250:
            return rest
    return p


def main():
    ap = argparse.ArgumentParser(description="Start the Pentaho Exam Bank backend.")
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--app-dir", default=None)
    args = ap.parse_args()

    here = _plain(os.path.dirname(os.path.abspath(__file__)))
    app_root = _plain(os.path.abspath(args.app_dir or here))

    app_py = os.path.join(app_root, "exam_bank", "api", "app.py")
    if not os.path.isfile(app_py):
        # Explicit beats a ModuleNotFoundError three frames deep: this is
        # the message that says the INSTALL is wrong, not the app.
        sys.exit(
            "boot: exam_bank/api/app.py not found at {} - "
            "the install is incomplete".format(app_py)
        )

    ui = os.path.join(app_root, "frontend", "dist", "index.html")
    if not os.path.isfile(ui):
        # The server would start and serve a 404 at its own root, which
        # reads as a broken app rather than a broken install.
        sys.exit(
            "boot: frontend/dist/index.html not found at {} - "
            "the interface was not staged".format(ui)
        )

    sys.path.insert(0, app_root)
    os.chdir(app_root)

    # Belt and braces with the shell's PYTHONDONTWRITEBYTECODE: never
    # compile bytecode into a read-only install tree - a .pyc the
    # installer never shipped is a file the uninstaller leaves behind.
    sys.dont_write_bytecode = True

    import uvicorn
    uvicorn.run("exam_bank.api.app:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
