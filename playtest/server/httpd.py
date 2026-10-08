"""Pure standard library HTTP server for Combat Robotics Playtest App."""

from __future__ import annotations

import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .routes import Router

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8002
MAX_BODY = 10 * 1024 * 1024  # 10MB limit


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "CombatRoboticsPlaytest/1.0"
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        self._run("GET")

    def do_HEAD(self) -> None:
        self._run("HEAD", body_out=False)

    def do_POST(self) -> None:
        self._run("POST")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _run(self, method: str, body_out: bool = True) -> None:
        parts = urlsplit(self.path)
        query = {k: v[0] for k, v in parse_qs(parts.query).items()}

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0

        if length > MAX_BODY:
            self.send_error(413, "Request body too large")
            return

        body = self.rfile.read(length) if length > 0 else b""

        router: Router = self.server.router  # type: ignore[attr-defined]
        try:
            response = router.dispatch(method, parts.path, query, body)
        except Exception as exc:
            self.log_error("Unhandled error on %s %s: %r", method, self.path, exc)
            self.send_error(500, "Internal error")
            return

        payload = response.body if body_out else b""
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(response.body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        for name, value in response.headers.items():
            self.send_header(name, value)
        self.end_headers()

        if payload:
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def log_message(self, fmt: str, *args: object) -> None:
        if getattr(self.server, "quiet", False):
            return
        code = args[1] if len(args) > 1 else ""
        sys.stderr.write(f"  {self.command} {self.path} -> {code}\n")


class PlaytestServer(ThreadingHTTPServer):
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, quiet: bool = False):
        self.quiet = quiet
        self.router = Router()
        super().__init__((host, port), RequestHandler)


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, quiet: bool = False) -> None:
    server = PlaytestServer(host=host, port=port, quiet=quiet)
    print(f"Combat Robotics Game - Playtest & Arena App")
    print(f"Serving at http://{host}:{port}/ (Press Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()
