"""Entry point for the Pentaho Exam Bank app."""

import signal
import sys
from pathlib import Path

# Ensure the repo root is on the path, so `exam_bank` resolves as a
# package. It sits beside this file now; before the rename the package WAS
# the repo directory, which made C:\Projects itself a source root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from exam_bank.gui.web_app import run_app


def main():
    # Handle Ctrl+C and window close gracefully so the port is released
    def _shutdown(signum, frame):
        print("\n[APP] Shutting down...")
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        run_app(port=7777)
    except SystemExit:
        pass
    except KeyboardInterrupt:
        pass
    finally:
        print("[APP] Exited. Port released.")


if __name__ == "__main__":
    main()
