"""Entry point for the Question Bank Generator app."""

import signal
import sys
from pathlib import Path

# Ensure the project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from question_bank.gui.web_app import run_app


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
