"""Run the API server.

    venv\\Scripts\\python.exe -m question_bank.api             # default port
    venv\\Scripts\\python.exe -m question_bank.api --port 9000
    venv\\Scripts\\python.exe -m question_bank.api --reload    # development

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
from pathlib import Path

DEFAULT_PORT = 7788
DEFAULT_HOST = "127.0.0.1"

# Written on start, removed on exit. Mirrors run.bat's question_bank_port.txt.
PORT_FILE = Path(tempfile.gettempdir()) / "question_bank_api_port.txt"


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m question_bank.api",
        description="Serve the Pentaho Question Bank API.",
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
    args = parser.parse_args(argv)

    # This API has no authentication: anything that can reach it can read the
    # question bank, write to it, and spend the machine's model time. On one
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

    print(f"Question Bank API on http://{args.host}:{args.port}")
    print(f"Interactive docs at http://{args.host}:{args.port}/docs")
    try:
        uvicorn.run(
            "question_bank.api.app:app",
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
    # `python -m question_bank.api` from the repo root already has the root on
    # sys.path; running the file directly does not, so make both work.
    if __package__ in (None, ""):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    raise SystemExit(main())
