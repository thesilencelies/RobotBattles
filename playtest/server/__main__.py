"""CLI entry point for Combat Robotics Playtest App."""

import argparse
import sys
from pathlib import Path

# Add repo root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from playtest.server.httpd import DEFAULT_HOST, DEFAULT_PORT, serve


def main() -> None:
    parser = argparse.ArgumentParser(description="Combat Robotics Playtest App Server")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host address to bind to (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to listen on (default: 8002)")
    parser.add_argument("--quiet", action="store_true", help="Suppress access logging")
    args = parser.parse_args()

    serve(host=args.host, port=args.port, quiet=args.quiet)


if __name__ == "__main__":
    main()
