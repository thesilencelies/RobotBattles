"""HTTP routing for the Combat Robotics Playtest App."""

from __future__ import annotations

import json
import mimetypes
import posixpath
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional
from urllib.parse import unquote

from builder.server.chassis_sheets import generate_chassis_svg, get_chassis_definitions
from builder.server.data import (
    CARD_IMAGES_DIR,
    WORKSPACE_DIR,
    list_saved_robots,
    load_all_cards,
    parse_robot_csv,
    read_saved_robot,
    serialize_robot_csv,
    write_saved_robot,
)
from playtest.engine.match import create_match, execute_turn
from playtest.engine.types import MatchState, MoveChoice

PLAYTEST_DIR = Path(__file__).resolve().parent.parent
PLAYTEST_STATIC_DIR = Path(__file__).resolve().parent / "static"
BUILDER_STATIC_DIR = WORKSPACE_DIR / "builder" / "server" / "static"

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
        return cls(status=status, body=text.encode("utf-8"), content_type=content_type)

    @classmethod
    def bytes_res(cls, data: bytes, content_type: str, status: int = 200) -> Response:
        return cls(status=status, body=data, content_type=content_type)


class Router:
    def __init__(self) -> None:
        self.routes_get: Dict[str, Callable[[Mapping[str, str]], Response]] = {}
        self.routes_post: Dict[str, Callable[[Mapping[str, str], bytes], Response]] = {}
        self.current_match: Optional[MatchState] = None
        self._register_routes()

    def _register_routes(self) -> None:
        # Builder API routes
        self.routes_get["/api/cards"] = self._api_cards
        self.routes_get["/api/chassis"] = self._api_chassis
        self.routes_get["/api/robots"] = self._api_list_robots
        self.routes_post["/api/robots/parse"] = self._api_parse_robot
        self.routes_post["/api/robots/serialize"] = self._api_serialize_robot

        # Battle API routes
        self.routes_get["/api/battle/state"] = self._api_battle_state
        self.routes_get["/api/automata"] = self._api_automata
        self.routes_post["/api/battle/new"] = self._api_battle_new
        self.routes_post["/api/battle/turn"] = self._api_battle_turn
        self.routes_post["/api/battle/reset"] = self._api_battle_reset

    def _api_cards(self, query: Mapping[str, str]) -> Response:
        cards = load_all_cards()
        return Response.json({
            "chassis": cards["chassis"],
            "components": cards["components"],
            "weapons": cards["weapons"],
            "all": cards["all"],
        })

    def _api_chassis(self, query: Mapping[str, str]) -> Response:
        return Response.json(get_chassis_definitions())

    def _api_list_robots(self, query: Mapping[str, str]) -> Response:
        return Response.json(list_saved_robots())

    def _api_parse_robot(self, query: Mapping[str, str], body: bytes) -> Response:
        try:
            csv_text = body.decode("utf-8")
        except UnicodeDecodeError:
            raise HttpError(400, "Invalid UTF-8 in CSV body")
        return Response.json(parse_robot_csv(csv_text))

    def _api_serialize_robot(self, query: Mapping[str, str], body: bytes) -> Response:
        try:
            data = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HttpError(400, "Invalid JSON body")
        return Response.text(serialize_robot_csv(data), content_type="text/csv; charset=utf-8")

    def _api_automata(self, query: Mapping[str, str]) -> Response:
        saved = list_saved_robots()
        automata_list = [r for r in saved if "Vyper" in r["name"] or "automata" in r["path"].lower()]
        return Response.json(automata_list)

    def _api_battle_state(self, query: Mapping[str, str]) -> Response:
        if self.current_match is None:
            # Auto-initialize a default match between Vyper_Spinner and Vyper_flipper
            spinner_csv = read_saved_robot("Vyper_Spinner.csv")
            if spinner_csv:
                self.current_match = create_match(spinner_csv, "Vyper_flipper", "Player Spinner")
            else:
                return Response.json({"match": None})
        return Response.json({"match": self.current_match.to_dict()})

    def _api_battle_new(self, query: Mapping[str, str], body: bytes) -> Response:
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            raise HttpError(400, "Invalid JSON payload")

        player_csv = data.get("player_csv", "")
        if not player_csv:
            player_csv = read_saved_robot("Vyper_Spinner.csv") or ""
        if not player_csv:
            raise HttpError(400, "No player robot CSV provided")

        automaton_name = data.get("automaton", "Vyper_flipper")
        player_name = data.get("player_name", "Player 1")

        try:
            self.current_match = create_match(
                player_csv=player_csv,
                automaton_name=automaton_name,
                player_name=player_name,
            )
        except Exception as exc:
            raise HttpError(400, f"Cannot initialize match: {exc}")

        return Response.json({"match": self.current_match.to_dict()})

    def _api_battle_turn(self, query: Mapping[str, str], body: bytes) -> Response:
        if self.current_match is None:
            raise HttpError(400, "No active match. Start a new match first.")

        try:
            data = json.loads(body.decode("utf-8"))
            left = int(data.get("left", 0))
            right = int(data.get("right", 0))
            fixed_roll = int(data["fixed_roll"]) if "fixed_roll" in data else None
        except Exception:
            raise HttpError(400, "Invalid turn parameters (left, right required as integers)")

        execute_turn(self.current_match, MoveChoice(left=left, right=right), fixed_automaton_roll=fixed_roll)
        return Response.json({"match": self.current_match.to_dict()})

    def _api_battle_reset(self, query: Mapping[str, str], body: bytes) -> Response:
        self.current_match = None
        return Response.json({"success": True})

    def dispatch(
        self, method: str, path: str, query: Mapping[str, str], body: bytes
    ) -> Response:
        clean_path = posixpath.normpath(unquote(path))

        try:
            if method in ("GET", "HEAD") and clean_path in self.routes_get:
                return self.routes_get[clean_path](query)
            if method == "POST" and clean_path in self.routes_post:
                return self.routes_post[clean_path](query, body)

            # Dynamic API routes: /api/robots/<name>
            if clean_path.startswith("/api/robots/") and len(clean_path) > len("/api/robots/"):
                robot_name = clean_path[len("/api/robots/"):]
                if method == "GET":
                    content = read_saved_robot(robot_name)
                    if content is None:
                        raise HttpError(404, f"Robot '{robot_name}' not found")
                    return Response.text(content, content_type="text/csv; charset=utf-8")
                elif method == "POST":
                    if body.startswith(b"{"):
                        p_data = json.loads(body.decode("utf-8"))
                        csv_text = p_data.get("csv_content") or serialize_robot_csv(p_data)
                    else:
                        csv_text = body.decode("utf-8")
                    out_path = write_saved_robot(robot_name, csv_text)
                    return Response.json({"success": True, "filename": out_path.name})

            # Chassis SVG export route
            if clean_path.startswith("/api/chassis/") and clean_path.endswith("/svg"):
                chassis_name = clean_path[len("/api/chassis/"):-4]
                defs = get_chassis_definitions()
                for ch in defs:
                    if ch["name"].lower() == chassis_name.lower() or ch["template"].lower() == chassis_name.lower():
                        return Response.text(generate_chassis_svg(ch), content_type="image/svg+xml; charset=utf-8")
                raise HttpError(404, f"Chassis '{chassis_name}' not found")

            if method in ("GET", "HEAD"):
                return self._serve_static(clean_path)

            raise HttpError(405, f"Method not allowed: {method}")

        except HttpError as err:
            return Response.json({"error": err.detail, "status": err.status}, status=err.status)
        except Exception as exc:
            return Response.json({"error": str(exc), "status": 500}, status=500)

    def _serve_static(self, path: str) -> Response:
        if path in ("", "/", "/index.html"):
            target = PLAYTEST_STATIC_DIR / "index.html"
            return self._read_file_response(target)

        # Serve static CardImages/
        if path.startswith("/CardImages/"):
            rel_file = path[len("/CardImages/"):]
            return self._read_file_response(CARD_IMAGES_DIR / rel_file)

        # Serve components/ and pictures/
        if path.startswith("/components/") or path.startswith("/pictures/"):
            rel_file = path.lstrip("/")
            return self._read_file_response(WORKSPACE_DIR / rel_file)

        # First check playtest static dir
        rel_path = path.lstrip("/")
        p_target = PLAYTEST_STATIC_DIR / rel_path
        if p_target.exists() and not p_target.is_dir():
            return self._read_file_response(p_target)

        # Fallback check builder static dir (e.g. for reused builder JS/CSS)
        b_target = BUILDER_STATIC_DIR / rel_path
        if b_target.exists() and not b_target.is_dir():
            return self._read_file_response(b_target)

        raise HttpError(404, f"Not found: {path}")

    def _read_file_response(self, target: Path) -> Response:
        try:
            resolved = target.resolve()
        except Exception:
            raise HttpError(404, "Not found")

        valid_roots = [
            PLAYTEST_STATIC_DIR.resolve(),
            BUILDER_STATIC_DIR.resolve(),
            CARD_IMAGES_DIR.resolve(),
            WORKSPACE_DIR.resolve(),
        ]
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
