"""HTTP API and static file routing for Robot Builder."""

from __future__ import annotations

import json
import mimetypes
import posixpath
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional
from urllib.parse import unquote

from .chassis_sheets import generate_chassis_svg, get_chassis_definitions
from .data import (
    CARD_IMAGES_DIR,
    WORKSPACE_DIR,
    list_saved_robots,
    load_all_cards,
    parse_robot_csv,
    read_saved_robot,
    serialize_robot_csv,
    write_saved_robot,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".webmanifest": "application/manifest+json",
    ".svg": "image/svg+xml; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".csv": "text/csv; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}

JSON_TYPE = "application/json; charset=utf-8"


class HttpError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass
class Response:
    status: int = 200
    body: bytes = b""
    content_type: str = JSON_TYPE
    headers: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def json(cls, data: Any, status: int = 200) -> Response:
        return cls(
            status=status,
            body=json.dumps(data, indent=2).encode("utf-8"),
            content_type=JSON_TYPE,
        )

    @classmethod
    def text(cls, text: str, content_type: str = "text/plain; charset=utf-8", status: int = 200) -> Response:
        return cls(
            status=status,
            body=text.encode("utf-8"),
            content_type=content_type,
        )

    @classmethod
    def bytes_res(cls, data: bytes, content_type: str, status: int = 200) -> Response:
        return cls(status=status, body=data, content_type=content_type)


class Router:
    def __init__(self) -> None:
        self.routes_get: Dict[str, Callable[[Mapping[str, str]], Response]] = {}
        self.routes_post: Dict[str, Callable[[Mapping[str, str], bytes], Response]] = {}
        self._register_routes()

    def _register_routes(self) -> None:
        # API endpoints
        self.routes_get["/api/cards"] = self._api_cards
        self.routes_get["/api/chassis"] = self._api_chassis
        self.routes_get["/api/robots"] = self._api_list_robots

        self.routes_post["/api/robots/parse"] = self._api_parse_robot
        self.routes_post["/api/robots/serialize"] = self._api_serialize_robot

    def _api_cards(self, query: Mapping[str, str]) -> Response:
        cards = load_all_cards()
        # Return without the large by_name dict to keep payload lean
        return Response.json({
            "chassis": cards["chassis"],
            "components": cards["components"],
            "weapons": cards["weapons"],
            "all": cards["all"],
        })

    def _api_chassis(self, query: Mapping[str, str]) -> Response:
        chassis_defs = get_chassis_definitions()
        return Response.json(chassis_defs)

    def _api_list_robots(self, query: Mapping[str, str]) -> Response:
        robots = list_saved_robots()
        return Response.json(robots)

    def _api_parse_robot(self, query: Mapping[str, str], body: bytes) -> Response:
        try:
            csv_text = body.decode("utf-8")
        except UnicodeDecodeError:
            raise HttpError(400, "Invalid UTF-8 in CSV body")
        parsed = parse_robot_csv(csv_text)
        return Response.json(parsed)

    def _api_serialize_robot(self, query: Mapping[str, str], body: bytes) -> Response:
        try:
            data = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HttpError(400, "Invalid JSON body")
        csv_text = serialize_robot_csv(data)
        return Response.text(csv_text, content_type="text/csv; charset=utf-8")

    def dispatch(
        self, method: str, path: str, query: Mapping[str, str], body: bytes
    ) -> Response:
        clean_path = posixpath.normpath(unquote(path))

        try:
            # Check exact routes first
            if method in ("GET", "HEAD") and clean_path in self.routes_get:
                return self.routes_get[clean_path](query)
            if method == "POST" and clean_path in self.routes_post:
                return self.routes_post[clean_path](query, body)

            # Dynamic API routes: /api/robots/<name>
            if clean_path.startswith("/api/robots/") and len(clean_path) > len("/api/robots/"):
                robot_name = clean_path[len("/api/robots/"):]
                if method == "GET":
                    return self._handle_get_robot(robot_name)
                elif method == "POST":
                    return self._handle_post_robot(robot_name, body)

            # Chassis SVG export route
            if clean_path.startswith("/api/chassis/") and clean_path.endswith("/svg"):
                chassis_name = clean_path[len("/api/chassis/"):-4]
                return self._handle_chassis_svg(chassis_name)

            if method == "GET" or method == "HEAD":
                if clean_path in self.routes_get:
                    return self.routes_get[clean_path](query)
                # Static files
                return self._serve_static(clean_path)

            if method == "POST":
                if clean_path in self.routes_post:
                    return self.routes_post[clean_path](query, body)
                raise HttpError(404, f"POST route not found: {clean_path}")

            raise HttpError(405, f"Method not allowed: {method}")

        except HttpError as err:
            return Response.json({"error": err.detail, "status": err.status}, status=err.status)
        except Exception as exc:
            return Response.json({"error": str(exc), "status": 500}, status=500)

    def _handle_get_robot(self, name: str) -> Response:
        content = read_saved_robot(name)
        if content is None:
            raise HttpError(404, f"Robot '{name}' not found")
        return Response.text(content, content_type="text/csv; charset=utf-8")

    def _handle_post_robot(self, name: str, body: bytes) -> Response:
        try:
            # Check if JSON payload with csv_content or raw CSV
            if body.startswith(b"{"):
                data = json.loads(body.decode("utf-8"))
                if "csv_content" in data:
                    csv_text = data["csv_content"]
                else:
                    csv_text = serialize_robot_csv(data)
            else:
                csv_text = body.decode("utf-8")
        except Exception as exc:
            raise HttpError(400, f"Cannot parse robot data: {exc}")

        path = write_saved_robot(name, csv_text)
        return Response.json({
            "success": True,
            "filename": path.name,
            "size": path.stat().st_size,
        })

    def _handle_chassis_svg(self, name: str) -> Response:
        defs = get_chassis_definitions()
        for ch in defs:
            if ch["name"].lower() == name.lower() or ch["template"].lower() == name.lower():
                svg = generate_chassis_svg(ch)
                return Response.text(svg, content_type="image/svg+xml; charset=utf-8")
        raise HttpError(404, f"Chassis '{name}' not found")

    def _serve_static(self, path: str) -> Response:
        # Default index
        if path in ("", "/", "/index.html"):
            target = STATIC_DIR / "index.html"
            return self._read_file_response(target)

        # Serve CardImages
        if path.startswith("/CardImages/"):
            rel_file = path[len("/CardImages/"):]
            target = CARD_IMAGES_DIR / rel_file
            return self._read_file_response(target)

        # Serve static directory files
        rel_path = path.lstrip("/")
        target = STATIC_DIR / rel_path
        return self._read_file_response(target)

    def _read_file_response(self, target: Path) -> Response:
        # Prevent path traversal outside allowed dirs
        try:
            resolved = target.resolve()
        except Exception:
            raise HttpError(404, "Not found")

        # Must be inside STATIC_DIR or CARD_IMAGES_DIR or WORKSPACE_DIR
        valid_roots = [STATIC_DIR.resolve(), CARD_IMAGES_DIR.resolve(), WORKSPACE_DIR.resolve()]
        if not any(str(resolved).startswith(str(r)) for r in valid_roots):
            raise HttpError(403, "Access denied")

        if not resolved.exists() or resolved.is_dir():
            raise HttpError(404, f"Not found: {target.name}")

        ext = resolved.suffix.lower()
        content_type = CONTENT_TYPES.get(ext)
        if not content_type:
            content_type, _ = mimetypes.guess_type(str(resolved))
            if not content_type:
                content_type = "application/octet-stream"

        with open(resolved, "rb") as f:
            data = f.read()

        return Response.bytes_res(data, content_type=content_type)
