"""Arena layout, hazard zones, and miniature template geometry."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

ARENA_WIDTH = 800.0
ARENA_HEIGHT = 800.0

WALL_LEFT = 100.0
WALL_RIGHT = 700.0
WALL_TOP = 100.0
WALL_BOTTOM = 700.0

PLAYER_START_POSE = (400.0, 620.0, 0.0)      # (x, y, theta) facing North
AUTOMATON_START_POSE = (400.0, 180.0, 180.0)  # (x, y, theta) facing South

# 4 Corner hazard pit boxes: [min_x, min_y, max_x, max_y]
HAZARD_PITS = [
    (0.0, 0.0, 150.0, 150.0),        # Top-Left
    (650.0, 0.0, 800.0, 150.0),      # Top-Right
    (0.0, 650.0, 150.0, 800.0),      # Bottom-Left
    (650.0, 650.0, 800.0, 800.0),    # Bottom-Right
]

# Chassis miniature polygons in local coordinates (origin at center, facing North = -Y)
CHASSIS_MINIATURE_SHAPES: Dict[str, List[Tuple[float, float]]] = {
    "Triangle": [
        (0.0, -36.0),    # Forward tip apex
        (35.0, -5.0),    # Right shoulder
        (35.0, 35.0),    # Right rear
        (-35.0, 35.0),   # Left rear
        (-35.0, -5.0),   # Left shoulder
    ],
    "Square": [
        (-30.0, -35.0),  # Top left
        (30.0, -35.0),   # Top right
        (30.0, 35.0),    # Bottom right
        (-30.0, 35.0),   # Bottom left
    ],
    "Wide": [
        (-42.0, -25.0),  # Top left
        (42.0, -25.0),   # Top right
        (42.0, 25.0),    # Bottom right
        (-42.0, 25.0),   # Bottom left
    ],
}

# Weapon template shapes in local coordinates relative to weapon mount point
WEAPON_MINIATURE_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "Circle": {
        "type": "circle",
        "radius": 22.0,
        "offset": (0.0, -10.0),
        "active_arc": (-110.0, 110.0),  # Degrees relative to heading
    },
    "Large Circle": {
        "type": "circle",
        "radius": 30.0,
        "offset": (0.0, -10.0),
        "active_arc": (-110.0, 110.0),
    },
    "Line": {
        "type": "polygon",
        "points": [(-4.0, -42.0), (4.0, -42.0), (4.0, 10.0), (-4.0, 10.0)],
        "active_points": [(-4.0, -42.0), (4.0, -42.0), (4.0, -28.0), (-4.0, -28.0)],
    },
    "Bar": {
        "type": "polygon",
        "points": [(-32.0, -40.0), (32.0, -40.0), (32.0, -25.0), (-32.0, -25.0)],
        "active_points": [(-32.0, -40.0), (32.0, -40.0), (32.0, -33.0), (-32.0, -33.0)],
    },
    "Prongs": {
        "type": "polygon",
        "points": [
            (-28.0, -42.0), (-16.0, -42.0), (-16.0, -26.0),
            (16.0, -26.0), (16.0, -42.0), (28.0, -42.0),
            (28.0, -18.0), (-28.0, -18.0),
        ],
        "active_points": [
            (-28.0, -42.0), (-16.0, -42.0), (-16.0, -32.0), (-28.0, -32.0),
            (16.0, -42.0), (28.0, -42.0), (28.0, -32.0), (16.0, -32.0),
        ],
    },
}


def transform_point(
    local_pt: Tuple[float, float],
    center_x: float,
    center_y: float,
    theta_deg: float,
) -> Tuple[float, float]:
    """Transforms a local coordinate (where North is -y) to world coordinates with heading theta_deg."""
    lx, ly = local_pt
    rad = math.radians(theta_deg)
    cos_t = math.cos(rad)
    sin_t = math.sin(rad)
    # Local: -y is forward, +x is right
    # World: heading 0 has forward (0, -1) and right (1, 0)
    wx = center_x + lx * cos_t - ly * sin_t
    wy = center_y + lx * sin_t + ly * cos_t
    return (wx, wy)


def transform_polygon(
    polygon: List[Tuple[float, float]],
    center_x: float,
    center_y: float,
    theta_deg: float,
) -> List[Tuple[float, float]]:
    """Transforms an entire polygon from local to world space."""
    return [transform_point(pt, center_x, center_y, theta_deg) for pt in polygon]


def is_in_hazard(x: float, y: float) -> bool:
    """Checks if (x, y) falls within any hazard pit or outside the outer arena walls."""
    # Outside walls
    if x < WALL_LEFT or x > WALL_RIGHT or y < WALL_TOP or y > WALL_BOTTOM:
        return True
    # Inside hazard pit zones
    for min_x, min_y, max_x, max_y in HAZARD_PITS:
        if min_x <= x <= max_x and min_y <= y <= max_y:
            return True
    return False


def get_chassis_polygon(template_name: str, x: float, y: float, theta: float) -> List[Tuple[float, float]]:
    shape = CHASSIS_MINIATURE_SHAPES.get(template_name, CHASSIS_MINIATURE_SHAPES["Square"])
    return transform_polygon(shape, x, y, theta)


def point_in_polygon(px: float, py: float, poly: List[Tuple[float, float]]) -> bool:
    """Standard ray-casting algorithm for point-in-polygon."""
    n = len(poly)
    inside = False
    p1x, p1y = poly[0]
    for i in range(1, n + 1):
        p2x, p2y = poly[i % n]
        if py > min(p1y, p2y):
            if py <= max(p1y, p2y):
                if px <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (py - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or px <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside
