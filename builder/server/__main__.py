"""Entry point for python -m builder.server"""

import argparse
import sys

from .httpd import DEFAULT_HOST, DEFAULT_PORT, serve


def main() -> None:
    parser = argparse.ArgumentParser(description="Robot Builder Web Server")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Host to bind (default: {DEFAULT_HOST})")
    parser.add_argument("--port", "-p", type=int, default=DEFAULT_PORT, help=f"Port (default: {DEFAULT_PORT})")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress access logging")
    args = parser.parse_args()

    serve(host=args.host, port=args.port, quiet=args.quiet)


if __name__ == "__main__":
    main()
