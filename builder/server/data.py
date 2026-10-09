"""Data parsing, card catalog, and robot CSV serialization."""

from __future__ import annotations

import csv
import io
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

WORKSPACE_DIR = Path(__file__).resolve().parent.parent.parent
CARD_DEFS_DIR = WORKSPACE_DIR / "cardDefinitions"
CARD_IMAGES_DIR = WORKSPACE_DIR / "CardImages"
AUTOMATA_DIR = WORKSPACE_DIR / "automata"


def sanitize_filename(name: str) -> str:
    """Matches the sanitize_filename logic used in generateCards.py."""
    s = name.strip().replace(" ", "_")
    return re.sub(r"[^A-Za-z0-9_.-]", "", s)


def safe_int(value: Any, default: int = 0) -> int:
    try:
        val_str = str(value).strip()
        if not val_str:
            return default
        return int(val_str)
    except (ValueError, TypeError):
        return default


def get_card_image_url(card_name: str) -> Optional[str]:
    """Finds if an image exists in CardImages for this card."""
    sanitized = sanitize_filename(card_name)
    # Check exact sanitized name with .png
    candidates = [
        f"{sanitized}.png",
        f"{card_name}.png",
        f"{card_name.replace(' ', '_')}.png",
    ]
    for c in candidates:
        if (CARD_IMAGES_DIR / c).exists():
            return f"/CardImages/{c}"
    return None


def load_card_csv(
    file_path: Path,
    card_type: str,
) -> List[Dict[str, Any]]:
    cards: List[Dict[str, Any]] = []
    if not file_path.exists():
        return cards

    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("Name") or "").strip()
            if not name:
                continue

            card: Dict[str, Any] = {
                "name": name,
                "type": card_type,
                "weight": safe_int(row.get("Weight")),
                "cost": safe_int(row.get("Cost")),
                "keywords": (row.get("Keywords") or "").strip(),
                "text": (row.get("Text") or "").strip(),
                "picture": (row.get("Picture") or "").strip(),
                "image_url": get_card_image_url(name),
            }

            if card_type == "chassis":
                card["template"] = (row.get("Template") or "Square").strip()
                card["flip_strength"] = safe_int(row.get("Flip strength"))
                pic = (row.get("Picture") or "").strip()
                card["picture_url"] = f"/{pic}" if pic else ""
            elif card_type == "component":
                card["requirements"] = (row.get("Requirements") or "").strip()
                card["outputs"] = (row.get("Outputs") or "").strip()
                card["durability"] = safe_int(row.get("Durability"))
                card["absorption"] = safe_int(row.get("Absorption"))
            elif card_type == "weapon":
                card["template"] = (row.get("Template") or "").strip()
                card["requirements"] = (row.get("Requirements") or "").strip()
                card["outputs"] = (row.get("Outputs") or "").strip()
                card["durability"] = safe_int(row.get("Durability"))
                card["absorption"] = safe_int(row.get("Absorption"))

            cards.append(card)
    return cards


def load_all_cards() -> Dict[str, Any]:
    """Loads all cards grouped by category, and creates a flat lookup dict."""
    chassis = load_card_csv(CARD_DEFS_DIR / "chassis.csv", "chassis")
    components = load_card_csv(CARD_DEFS_DIR / "components.csv", "component")
    weapons = load_card_csv(CARD_DEFS_DIR / "weapons.csv", "weapon")

    # Playable cards that can be added to the robot/spares (chassis is a Mat, not a card)
    playable_cards = components + weapons
    all_by_name = {c["name"]: c for c in (chassis + components + weapons)}

    return {
        "chassis": chassis,
        "components": components,
        "weapons": weapons,
        "all": playable_cards,
        "by_name": all_by_name,
    }


# Template geometry on A3 sheet (420mm x 297mm)
# Origin (0,0) is top-left, coordinates in millimeters (mm).
# Standard card size in mm: 64mm width x 89mm height.
# Half-poker card size in mm: 44mm width x 64mm height
A3_WIDTH_MM = 420.0
A3_HEIGHT_MM = 297.0
CARD_WIDTH_MM = 44.0
CARD_HEIGHT_MM = 64.0

# Chassis boundary templates on A3 landscape sheet (420mm x 297mm)
CHASSIS_TEMPLATES = {
    "Square": {
        "name": "Square",
        "description": "Full height and slightly narrower than a true square",
        "type": "polygon",
        # Full height (256mm) and slightly narrower than true square (220mm wide)
        "points": [
            [100.0, 24.0],
            [320.0, 24.0],
            [320.0, 280.0],
            [100.0, 280.0],
        ],
        "bounds": {"x": 100.0, "y": 24.0, "width": 220.0, "height": 256.0},
        "facing": "north",
    },
    "Triangle": {
        "name": "Triangle",
        "description": "Wedge chassis with forward triangular front and rectangular base",
        "type": "polygon",
        # Wedge profile: width 340mm, height 256mm: rear y=280, shoulders y=135, apex at (210, 24)
        "points": [
            [210.0, 24.0],   # Front apex tip
            [380.0, 135.0],  # Right front shoulder
            [380.0, 280.0],  # Right rear corner
            [40.0, 280.0],   # Left rear corner
            [40.0, 135.0],   # Left front shoulder
        ],
        "bounds": {"x": 40.0, "y": 24.0, "width": 340.0, "height": 256.0},
        "facing": "north",
    },
    "Wide": {
        "name": "Wide",
        "description": "Full width but just a bit over half of the vertical space",
        "type": "polygon",
        # Full width (396mm) and just over half vertical space (170mm high)
        "points": [
            [12.0, 65.0],
            [408.0, 65.0],
            [408.0, 235.0],
            [12.0, 235.0],
        ],
        "bounds": {"x": 12.0, "y": 65.0, "width": 396.0, "height": 170.0},
        "facing": "north",
    },
}


def get_chassis_definitions() -> List[Dict[str, Any]]:
    cards_data = load_all_cards()
    chassis_list = cards_data["chassis"]
    result = []
    for ch in chassis_list:
        tpl_key = ch.get("template", "Square")
        geom = CHASSIS_TEMPLATES.get(tpl_key, CHASSIS_TEMPLATES["Square"])
        result.append({
            **ch,
            "geometry": geom,
            "sheet_width_mm": A3_WIDTH_MM,
            "sheet_height_mm": A3_HEIGHT_MM,
            "card_width_mm": CARD_WIDTH_MM,
            "card_height_mm": CARD_HEIGHT_MM,
        })
    return result


def compute_card_box(
    x: float, y: float, rotation: int, w: float = CARD_WIDTH_MM, h: float = CARD_HEIGHT_MM
) -> Tuple[float, float, float, float]:
    """Returns (min_x, min_y, max_x, max_y) for a card at x,y with given rotation."""
    rot = (rotation % 360)
    if rot in (90, 270):
        cw, ch = h, w
    else:
        cw, ch = w, h
    return (x, y, x + cw, y + ch)


def boxes_touch(
    b1: Tuple[float, float, float, float],
    b2: Tuple[float, float, float, float],
    tolerance: float = 3.0,
) -> bool:
    """Checks if two axis-aligned bounding boxes overlap or touch within tolerance (mm)."""
    x1_min, y1_min, x1_max, y1_max = b1
    x2_min, y2_min, x2_max, y2_max = b2

    # Check non-overlap with tolerance
    if x1_max < x2_min - tolerance or x2_max < x1_min - tolerance:
        return False
    if y1_max < y2_min - tolerance or y2_max < y1_min - tolerance:
        return False
    return True


def compute_connections(cards: List[Dict[str, Any]]) -> Dict[Any, List[Any]]:
    """Calculates adjacency connections between placed cards."""
    boxes: Dict[Any, Tuple[float, float, float, float]] = {}
    for c in cards:
        cid = c.get("id")
        loc = c.get("location", "")
        # Only compute for cards placed on chassis
        if str(loc).startswith("chassis:"):
            parts = loc[len("chassis:"):].split(",")
            if len(parts) >= 2:
                try:
                    x = float(parts[0])
                    y = float(parts[1])
                    rot = int(parts[2]) if len(parts) >= 3 else 0
                    boxes[cid] = compute_card_box(x, y, rot)
                except (ValueError, TypeError):
                    pass

    connections: Dict[Any, List[Any]] = {c.get("id"): [] for c in cards}
    card_ids = list(boxes.keys())
    for i in range(len(card_ids)):
        id_a = card_ids[i]
        box_a = boxes[id_a]
        for j in range(i + 1, len(card_ids)):
            id_b = card_ids[j]
            box_b = boxes[id_b]
            if boxes_touch(box_a, box_b):
                connections[id_a].append(str(id_b))
                connections[id_b].append(str(id_a))

    return connections


def parse_robot_csv(csv_text: str) -> Dict[str, Any]:
    """
    Parses robot definition in the schema:
    id,card,location,connections
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    cards_data = load_all_cards()
    by_name = cards_data["by_name"]

    placed_cards: List[Dict[str, Any]] = []
    spare_cards: List[Dict[str, Any]] = []
    selected_chassis: Optional[Dict[str, Any]] = None

    for row in reader:
        cid = (row.get("id") or "").strip()
        card_name = (row.get("card") or "").strip()
        location = (row.get("location") or "").strip()
        conn_str = (row.get("connections") or "").strip()

        # Handle unquoted chassis coordinates that might have been split across columns
        if location.startswith("chassis:") and "," not in location and ";" not in location:
            extras = []
            conn_val = ""
            if conn_str and re.match(r"^-?\d+(\.\d+)?$", conn_str):
                extras.append(conn_str)
                rest = row.get(None, [])
                for r_val in rest:
                    r_str = str(r_val).strip()
                    if re.match(r"^-?\d+(\.\d+)?$", r_str):
                        extras.append(r_str)
                    else:
                        conn_val = r_str
                        break
                location = location + "," + ",".join(extras)
                conn_str = conn_val

        if not card_name:
            continue

        raw_card = by_name.get(card_name, {
            "name": card_name,
            "type": "component",
            "weight": 0,
            "cost": 0,
        })
        card_obj = dict(raw_card)

        # Check if it's the chassis
        if card_obj.get("type") == "chassis":
            if not selected_chassis:
                selected_chassis = card_obj
            # The chassis is the mat itself, not an placed card on the mat
            continue

        conn_list = [c.strip() for c in conn_str.split(";") if c.strip()]

        if location.startswith("spares"):
            spare_cards.append({
                "id": cid,
                "card": card_name,
                "card_data": card_obj,
                "location": location,
                "connections": conn_list,
            })
        elif location.startswith("chassis"):
            # Format: chassis:x,y,rot or chassis:x;y;rot
            loc_body = location[len("chassis:"):].strip() if ":" in location else ""
            if ";" in loc_body:
                coords = [p.strip() for p in loc_body.split(";") if p.strip()]
            else:
                coords = [p.strip() for p in loc_body.split(",") if p.strip()]

            try:
                x = float(coords[0]) if len(coords) >= 1 and coords[0] != "" else 100.0
            except (ValueError, TypeError):
                x = 100.0
            try:
                y = float(coords[1]) if len(coords) >= 2 and coords[1] != "" else 100.0
            except (ValueError, TypeError):
                y = 100.0
            try:
                rot = int(float(coords[2])) if len(coords) >= 3 and coords[2] != "" else 0
            except (ValueError, TypeError):
                rot = 0

            placed_cards.append({
                "id": cid,
                "card": card_name,
                "card_data": card_obj,
                "location": location,
                "x": x,
                "y": y,
                "rotation": rot,
                "connections": conn_list,
            })
        else:
            # Default fallback to chassis
            placed_cards.append({
                "id": cid,
                "card": card_name,
                "card_data": card_obj,
                "location": f"chassis:100,100,0",
                "x": 100.0,
                "y": 100.0,
                "rotation": 0,
                "connections": conn_list,
            })

    # If chassis wasn't explicitly found, default to first chassis
    if not selected_chassis and cards_data["chassis"]:
        selected_chassis = cards_data["chassis"][0]

    return {
        "chassis": selected_chassis,
        "placed_cards": placed_cards,
        "spare_cards": spare_cards,
    }


def serialize_robot_csv(robot_data: Dict[str, Any]) -> str:
    """
    Serializes a robot into CSV format with header:
    id,card,location,connections
    """
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["id", "card", "location", "connections"])

    placed = robot_data.get("placed_cards", [])
    spares = robot_data.get("spare_cards", [])
    chassis = robot_data.get("chassis")

    # If connections not provided, auto-compute for placed cards
    auto_conns = compute_connections(placed)

    row_id = 1

    # First row: Chassis
    if chassis and isinstance(chassis, dict) and chassis.get("name"):
        chassis_name = chassis["name"]
        writer.writerow([str(row_id), chassis_name, "chassis:0,0,0", ""])
        row_id += 1

    # Placed cards
    for card in placed:
        c_id = card.get("id") or str(row_id)
        name = card.get("card") or (card.get("card_data") or {}).get("name") or "Card"
        x = card.get("x", 100.0)
        y = card.get("y", 100.0)
        rot = card.get("rotation", 0)
        loc = f"chassis:{x:.1f},{y:.1f},{rot}"

        conns = card.get("connections")
        if conns is None:
            conns = auto_conns.get(card.get("id", ""), [])
        if isinstance(conns, list):
            conn_str = ";".join(str(c) for c in conns)
        else:
            conn_str = str(conns)

        writer.writerow([str(c_id), name, loc, conn_str])
        row_id += 1

    # Spare cards
    spare_idx = 0
    for card in spares:
        c_id = card.get("id") or str(row_id)
        name = card.get("card") or (card.get("card_data") or {}).get("name") or "Card"
        loc = f"spares:{spare_idx}"
        spare_idx += 1
        writer.writerow([str(c_id), name, loc, ""])
        row_id += 1

    return out.getvalue()


def list_saved_robots() -> List[Dict[str, Any]]:
    """Lists saved CSV robot files in automata/ directory."""
    AUTOMATA_DIR.mkdir(parents=True, exist_ok=True)
    robots = []
    for p in sorted(AUTOMATA_DIR.glob("*.csv")):
        robots.append({
            "name": p.stem,
            "filename": p.name,
            "path": str(p),
            "size": p.stat().st_size,
        })
    return robots


def read_saved_robot(filename: str) -> Optional[str]:
    clean_name = Path(filename).name
    if not clean_name.endswith(".csv"):
        clean_name += ".csv"
    target = AUTOMATA_DIR / clean_name
    if not target.exists():
        return None
    with open(target, "r", encoding="utf-8") as f:
        return f.read()


def write_saved_robot(filename: str, csv_content: str) -> Path:
    AUTOMATA_DIR.mkdir(parents=True, exist_ok=True)
    clean_name = Path(filename).name
    if not clean_name.endswith(".csv"):
        clean_name += ".csv"
    target = AUTOMATA_DIR / clean_name
    with open(target, "w", encoding="utf-8") as f:
        f.write(csv_content)
    return target
