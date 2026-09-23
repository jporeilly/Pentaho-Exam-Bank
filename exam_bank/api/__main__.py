"""Run the API server.

    venv\\Scripts\\python.exe -m exam_bank.api             # default port
    venv\\Scripts\\python.exe -m exam_bank.api --port 9000
    venv\\Scripts\\python.exe -m exam_bank.api --reload    # development

The chosen port is written to a file in the temp directory so a launcher can
find and stop the server it started, the same way ``run.bat`` already tracks
the UI's port.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import socket
import sys
import tempfile
import threading
import time
import webbrowser
from pathlib import Path

DEFAULT_PORT = 7788
DEFAULT_HOST = "127.0.0.1"

# Written on start, removed on exit. Mirrors run.bat's exam_bank_port.txt.
PORT_FILE = Path(tempfile.gettempdir()) / "exam_bank_api_port.txt"


def _is_loopback(host: str) -> bool:
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host if host != "localhost" else "127.0.0.1", port))
            return True
        except OSError:
            return False


def _wait_until_serving(host: str, port: int, timeout: float = 20.0) -> bool:
    """Block until something accepts a connection on ``port``.

    Opening the browser at the same moment the server is told to start shows
    the person a connection error and makes them reload — uvicorn takes a
    second or two to bind. Polling is crude but it is the only thing that is
    true from outside the server: the port either accepts or it does not.
    """
    target = "127.0.0.1" if host in ("localhost", "") else host
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.5)
            if probe.connect_ex((target, port)) == 0:
                return True
        time.sleep(0.25)
    return False


def _open_browser_when_ready(host: str, port: int, timeout: float = 20.0) -> None:
    """Open the app in a browser once it is actually answering.

    Gives up silently on a machine with no browser to open — the server is
    running either way, and the console has already printed the URL.
    """
    if not _wait_until_serving(host, port, timeout):
        return
    try:
        webbrowser.open(f"http://{host}:{port}/")
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m exam_bank.api",
        description="Serve the Pentaho Exam Bank API.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--reload", action="store_true",
                        help="restart on code changes (development)")
    parser.add_argument("--log-level", default="info")
    parser.add_argument(
        "--allow-remote", action="store_true",
        help="permit binding a non-loopback address (see the warning below)",
    )
    parser.add_argument(
        "--open", action="store_true", dest="open_browser",
        help="open the app in a browser once the server is answering",
    )
    args = parser.parse_args(argv)

    # This API has no authentication: anything that can reach it can read the
    # exam bank, write to it, and spend the machine's model time. On one
    # machine that is fine, on a network it is not, so binding anything but
    # loopback has to be asked for explicitly rather than reached by passing
    # --host 0.0.0.0 to see what happens.
    if not _is_loopback(args.host) and not args.allow_remote:
        print(
            f"Refusing to bind {args.host}: the API is unauthenticated, so "
            f"anyone who can reach it can read and change the bank.\n"
            f"Pass --allow-remote if you really mean to expose it.",
            file=sys.stderr,
        )
        return 2

    if not args.reload and not _port_is_free(args.host, args.port):
        # uvicorn's own failure here is a bare OSError from deep in asyncio,
        # and the usual cause is simply the server already running.
        print(
            # ASCII only: this is printed to a Windows console, which encodes
            # to the active codepage. An em-dash here becomes a single byte
            # that renders correctly under cp1252 and as garbage under the
            # cp437/850 a console actually defaults to.
            f"Port {args.port} is already in use. Another copy of the API is "
            f"probably running - stop it, or pass --port to use a different one.",
            file=sys.stderr,
        )
        return 1

    try:
        import uvicorn
    except ImportError:
        print("uvicorn is not installed. Run: pip install -r requirements.txt",
              file=sys.stderr)
        return 1

    try:
        PORT_FILE.write_text(str(args.port), encoding="utf-8")
    except OSError:
        pass  # Only a convenience for launchers; never worth failing to start.

    print(f"Exam Bank on http://{args.host}:{args.port}")
    print(f"Interactive API docs at http://{args.host}:{args.port}/docs")

    if args.open_browser:
        # A daemon thread: uvicorn.run() blocks below and owns the process,
        # and a browser that never opened must not keep it alive.
        threading.Thread(
            target=_open_browser_when_ready,
            args=(args.host, args.port),
            daemon=True,
        ).start()
    try:
        uvicorn.run(
            "exam_bank.api.app:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level=args.log_level,
        )
    except KeyboardInterrupt:
        pass
    finally:
        try:
            # Only remove it if it is still ours — a second server that
            # started later owns the file now.
            if PORT_FILE.exists() and PORT_FILE.read_text(encoding="utf-8").strip() == str(args.port):
                PORT_FILE.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    # `python -m exam_bank.api` from the repo root already has the root on
    # sys.path; running the file directly does not, so make both work.
    if __package__ in (None, ""):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    raise SystemExit(main())
