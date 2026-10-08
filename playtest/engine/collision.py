"""Polygon intersection, contact detection, and octant determination."""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from .field import (
    CHASSIS_MINIATURE_SHAPES,
    WEAPON_MINIATURE_TEMPLATES,
    get_chassis_polygon,
    point_in_polygon,
    transform_point,
    transform_polygon,
)
from .types import CollisionEvent, ComponentHealth, RobotState, TrajectoryPoint

OCTANT_NAMES = [
    "Front",
    "Front-Right",
    "Right",
    "Back-Right",
    "Back",
    "Back-Left",
    "Left",
    "Front-Left",
]


def normalize_angle_deg(deg: float) -> float:
    """Normalizes angle to [-180.0, 180.0)."""
    a = deg % 360.0
    if a >= 180.0:
        a -= 360.0
    return a


def get_octant(from_x: float, from_y: float, to_x: float, to_y: float, heading_deg: float) -> str:
    """
    Determines which of the 8 octants of a robot the target point lies in,
    relative to its heading (where heading 0 is North = -y).
    """
    dx = to_x - from_x
    dy = to_y - from_y
    if abs(dx) < 1e-4 and abs(dy) < 1e-4:
        return "Front"

    # Angle of vector: dx is right (+x), dy is down (+y)
    # North is dy < 0, dx = 0 -> angle 0
    # East is dx > 0, dy = 0 -> angle 90
    point_dir_deg = math.degrees(math.atan2(dx, -dy))
    relative_angle = normalize_angle_deg(point_dir_deg - heading_deg)

    # Octants are 45-degree wedges centered around 0, 45, 90, 135, 180, -135, -90, -45
    if -22.5 <= relative_angle < 22.5:
        return "Front"
    elif 22.5 <= relative_angle < 67.5:
        return "Front-Right"
    elif 67.5 <= relative_angle < 112.5:
        return "Right"
    elif 112.5 <= relative_angle < 157.5:
        return "Back-Right"
    elif relative_angle >= 157.5 or relative_angle < -157.5:
        return "Back"
    elif -157.5 <= relative_angle < -112.5:
        return "Back-Left"
    elif -112.5 <= relative_angle < -67.5:
        return "Left"
    else:
        return "Front-Left"


def polygons_intersect(poly1: List[Tuple[float, float]], poly2: List[Tuple[float, float]]) -> bool:
    """Separating Axis Theorem (SAT) for convex/simple polygon intersection."""
    for poly in [poly1, poly2]:
        n = len(poly)
        for i in range(n):
            p1 = poly[i]
            p2 = poly[(i + 1) % n]
            edge = (p2[0] - p1[0], p2[1] - p1[1])
            axis = (-edge[1], edge[0])  # Perpendicular normal

            mag = math.hypot(axis[0], axis[1])
            if mag < 1e-6:
                continue
            axis = (axis[0] / mag, axis[1] / mag)

            # Project poly1 onto axis
            proj1 = [p[0] * axis[0] + p[1] * axis[1] for p in poly1]
            min1, max1 = min(proj1), max(proj1)

            # Project poly2 onto axis
            proj2 = [p[0] * axis[0] + p[1] * axis[1] for p in poly2]
            min2, max2 = min(proj2), max(proj2)

            if max1 < min2 or max2 < min1:
                return False  # Separating axis found

    return True


def find_polygon_contact_center(
    poly1: List[Tuple[float, float]], poly2: List[Tuple[float, float]]
) -> Tuple[float, float]:
    """Finds an approximate midpoint of contact between two intersecting polygons."""
    pts_in_2 = [p for p in poly1 if point_in_polygon(p[0], p[1], poly2)]
    pts_in_1 = [p for p in poly2 if point_in_polygon(p[0], p[1], poly1)]
    all_pts = pts_in_2 + pts_in_1

    if all_pts:
        avg_x = sum(p[0] for p in all_pts) / len(all_pts)
        avg_y = sum(p[1] for p in all_pts) / len(all_pts)
        return (avg_x, avg_y)

    # Fallback to centroid midpoint
    c1x = sum(p[0] for p in poly1) / len(poly1)
    c1y = sum(p[1] for p in poly1) / len(poly1)
    c2x = sum(p[2] for p in poly2) / len(poly2) if len(poly2[0]) > 2 else sum(p[0] for p in poly2) / len(poly2)
    c2y = sum(p[1] for p in poly2) / len(poly2)
    return ((c1x + c2x) / 2.0, (c1y + c2y) / 2.0)


def map_octant_to_components(robot: RobotState, octant: str) -> List[str]:
    """
    Finds the outermost component(s) located in the given octant on the robot's A3 mat.
    Center of chassis is (210, 150).
    """
    chassis_cx = 210.0
    chassis_cy = 150.0

    matching_comps = []
    for cid, comp in robot.components.items():
        if comp.is_destroyed:
            continue
        # Card center
        ccx = comp.x + (comp.box[2] - comp.box[0]) / 2.0
        ccy = comp.y + (comp.box[3] - comp.box[1]) / 2.0
        # In chassis mat: top is forward (y=0 is front)
        comp_oct = get_octant(chassis_cx, chassis_cy, ccx, ccy, heading_deg=0.0)
        if comp_oct == octant:
            matching_comps.append((cid, comp))

    if not matching_comps:
        # Fallback to closest component in that direction or perimeter component
        # If Front octant, return forward-most components
        all_active = [c for c in robot.components.values() if not c.is_destroyed]
        if not all_active:
            return []
        if "Front" in octant:
            sorted_by_y = sorted(all_active, key=lambda c: c.y)
            return [sorted_by_y[0].id]
        elif "Back" in octant:
            sorted_by_y = sorted(all_active, key=lambda c: -c.y)
            return [sorted_by_y[0].id]
        elif "Left" in octant:
            sorted_by_x = sorted(all_active, key=lambda c: c.x)
            return [sorted_by_x[0].id]
        else:
            sorted_by_x = sorted(all_active, key=lambda c: -c.x)
            return [sorted_by_x[0].id]

    # Return matching components (outermost first)
    return [cid for cid, _ in matching_comps]


def is_active_weapon_contact(
    robot: RobotState,
    contact_point: Tuple[float, float],
    octant: str,
) -> bool:
    """
    Checks if the contact point touches the weapon's active area (red zone).
    Invertible check: if inverted and weapon not invertible, inactive.
    """
    weapons = [c for c in robot.components.values() if c.card_type == "weapon" and not c.is_destroyed]
    if not weapons:
        return False

    for w in weapons:
        if robot.is_inverted and not w.is_invertible:
            continue
        # Check if weapon is mounted in the contacted direction (typically Front)
        if "Front" in octant:
            return True
        # For full circular spinners: active anywhere in front and sides
        if "Circle" in w.keywords or "Spinner" in w.name:
            if octant in ("Front", "Front-Left", "Front-Right", "Left", "Right"):
                return True

    return False


def detect_collision(
    r1: RobotState,
    traj1: List[TrajectoryPoint],
    r2: RobotState,
    traj2: List[TrajectoryPoint],
) -> Optional[CollisionEvent]:
    """
    Steps along both trajectories simultaneously from t=0.0 to t=1.0.
    Returns the first collision event if the miniature polygons intersect.
    """
    num_steps = min(len(traj1), len(traj2))

    for k in range(1, num_steps):
        p1 = traj1[k]
        p2 = traj2[k]

        poly1 = get_chassis_polygon(r1.chassis_template, p1.x, p1.y, p1.theta)
        poly2 = get_chassis_polygon(r2.chassis_template, p2.x, p2.y, p2.theta)

        if polygons_intersect(poly1, poly2):
            contact_pt = find_polygon_contact_center(poly1, poly2)
            oct1 = get_octant(p1.x, p1.y, contact_pt[0], contact_pt[1], p1.theta)
            oct2 = get_octant(p2.x, p2.y, contact_pt[0], contact_pt[1], p2.theta)

            comps1 = map_octant_to_components(r1, oct1)
            comps2 = map_octant_to_components(r2, oct2)

            is_active_1 = is_active_weapon_contact(r1, contact_pt, oct1)
            is_active_2 = is_active_weapon_contact(r2, contact_pt, oct2)

            contact_type = "ACTIVE" if (is_active_1 or is_active_2) else "INERT"

            desc_parts = []
            if contact_type == "ACTIVE":
                if is_active_1 and is_active_2:
                    desc_parts.append(f"Head-on weapon clash! ({r1.name} {oct1} vs {r2.name} {oct2})")
                elif is_active_1:
                    desc_parts.append(f"{r1.name}'s weapon strikes {r2.name}'s {oct2} octant!")
                else:
                    desc_parts.append(f"{r2.name}'s weapon strikes {r1.name}'s {oct1} octant!")
            else:
                desc_parts.append(f"Inert pushing contact: {r1.name} ({oct1}) pushes {r2.name} ({oct2})")

            return CollisionEvent(
                time_t=p1.t,
                contact_point=contact_pt,
                robot1_octant=oct1,
                robot2_octant=oct2,
                robot1_components=comps1,
                robot2_components=comps2,
                contact_type=contact_type,
                description=" ".join(desc_parts),
            )

    return None
