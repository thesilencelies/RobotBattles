"""Arena layout, hazard zones, and miniature template geometry."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

# Arena world dimensions in mm (display viewBox 0 0 800 800)
ARENA_WIDTH = 800.0
ARENA_HEIGHT = 800.0

WALL_LEFT = 100.0
WALL_RIGHT = 700.0
WALL_TOP = 100.0
WALL_BOTTOM = 700.0

# Starting zones
PLAYER_START_ZONE = (300.0, 580.0, 500.0, 680.0)       # [min_x, min_y, max_x, max_y]
AUTOMATON_START_ZONE = (300.0, 120.0, 500.0, 220.0)

PLAYER_START_POSE = (400.0, 630.0, 0.0)      # (x, y, theta) facing North (0 deg)
AUTOMATON_START_POSE = (400.0, 170.0, 180.0)  # (x, y, theta) facing South (180 deg)

# 4 Corner hazard pit zones: [min_x, min_y, max_x, max_y]
HAZARD_PITS = [
    (0.0, 0.0, 150.0, 150.0),        # Top-Left
    (650.0, 0.0, 800.0, 150.0),      # Top-Right
    (0.0, 650.0, 150.0, 800.0),      # Bottom-Left
    (650.0, 650.0, 800.0, 800.0),    # Bottom-Right
]

# Scale factor from A3 chassis mat (420 x 297 mm, center at 210, 150) to arena miniature
MAT_CENTER_X = 210.0
MAT_CENTER_Y = 150.0
MAT_TO_MINI_SCALE = 0.273

# Base Chassis miniature polygons in local coordinates (origin at center, facing North = -Y)
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


def card_to_miniature_offset(card_x: float, card_y: float, card_w: float = 44.0, card_h: float = 64.0) -> Tuple[float, float]:
    """
    Computes local miniature offset (lx, ly) in mm relative to chassis center
    from a card placed on the A3 chassis sheet (420 x 297 mm, center at 210, 150).
    On the sheet: -y is forward (towards front arrow).
    On the miniature: -y is forward (heading North = 0 deg).
    """
    card_cx = card_x + card_w / 2.0
    card_cy = card_y + card_h / 2.0
    dx_mat = card_cx - MAT_CENTER_X
    dy_mat = card_cy - MAT_CENTER_Y
    return (dx_mat * MAT_TO_MINI_SCALE, dy_mat * MAT_TO_MINI_SCALE)


def get_weapon_template_geometry(
    template_name: str,
    offset: Tuple[float, float],
) -> Dict[str, Any]:
    """
    Returns the local geometry of a weapon template centered at the equivalent
    location to the card on the chassis.
    """
    ox, oy = offset
    tname = (template_name or "Line").strip()

    if "Large Circle" in tname:
        radius = 30.0
        # Polygon approximation of circle for SAT collision checks
        pts = []
        for i in range(16):
            ang = math.radians(i * (360.0 / 16.0))
            pts.append((ox + radius * math.sin(ang), oy - radius * math.cos(ang)))
        # Active area is forward perimeter arc (from -90 deg to +90 deg relative to heading)
        active_pts = []
        for i in range(9):
            ang = math.radians(-90.0 + i * 22.5)
            active_pts.append((ox + radius * math.sin(ang), oy - radius * math.cos(ang)))
        active_pts.append((ox, oy))
        return {
            "type": "circle",
            "center": (ox, oy),
            "radius": radius,
            "polygon": pts,
            "active_polygon": active_pts,
        }

    elif "Circle" in tname:
        radius = 22.0
        pts = []
        for i in range(16):
            ang = math.radians(i * (360.0 / 16.0))
            pts.append((ox + radius * math.sin(ang), oy - radius * math.cos(ang)))
        active_pts = []
        for i in range(9):
            ang = math.radians(-90.0 + i * 22.5)
            active_pts.append((ox + radius * math.sin(ang), oy - radius * math.cos(ang)))
        active_pts.append((ox, oy))
        return {
            "type": "circle",
            "center": (ox, oy),
            "radius": radius,
            "polygon": pts,
            "active_polygon": active_pts,
        }

    elif "Bar" in tname:
        # Horizontal beater bar across width
        w = 48.0
        h = 12.0
        half_w = w / 2.0
        half_h = h / 2.0
        poly = [
            (ox - half_w, oy - half_h),
            (ox + half_w, oy - half_h),
            (ox + half_w, oy + half_h),
            (ox - half_w, oy + half_h),
        ]
        # Active zone is front half of the bar
        active_poly = [
            (ox - half_w, oy - half_h),
            (ox + half_w, oy - half_h),
            (ox + half_w, oy),
            (ox - half_w, oy),
        ]
        return {
            "type": "polygon",
            "center": (ox, oy),
            "polygon": poly,
            "active_polygon": active_poly,
        }

    elif "Prongs" in tname:
        # Forks or claw prongs
        poly = [
            (ox - 24.0, oy - 28.0),
            (ox - 12.0, oy - 28.0),
            (ox - 12.0, oy - 10.0),
            (ox + 12.0, oy - 10.0),
            (ox + 12.0, oy - 28.0),
            (ox + 24.0, oy - 28.0),
            (ox + 24.0, oy + 6.0),
            (ox - 24.0, oy + 6.0),
        ]
        active_poly = [
            (ox - 24.0, oy - 28.0),
            (ox - 12.0, oy - 28.0),
            (ox - 12.0, oy - 16.0),
            (ox - 24.0, oy - 16.0),
            (ox + 12.0, oy - 28.0),
            (ox + 24.0, oy - 28.0),
            (ox + 24.0, oy - 16.0),
            (ox + 12.0, oy - 16.0),
        ]
        return {
            "type": "polygon",
            "center": (ox, oy),
            "polygon": poly,
            "active_polygon": active_poly,
        }

    else:
        # Default: Line (Vertical Spinner / Lifter)
        w = 8.0
        h = 32.0
        half_w = w / 2.0
        poly = [
            (ox - half_w, oy - 24.0),
            (ox + half_w, oy - 24.0),
            (ox + half_w, oy + 8.0),
            (ox - half_w, oy + 8.0),
        ]
        active_poly = [
            (ox - half_w, oy - 24.0),
            (ox + half_w, oy - 24.0),
            (ox + half_w, oy - 10.0),
            (ox - half_w, oy - 10.0),
        ]
        return {
            "type": "polygon",
            "center": (ox, oy),
            "polygon": poly,
            "active_polygon": active_poly,
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
