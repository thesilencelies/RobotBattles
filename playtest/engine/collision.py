"""Composite miniature polygon intersection, active weapon red-zone detection, and contact resolution."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from .field import (
    CHASSIS_MINIATURE_SHAPES,
    MAT_CENTER_X,
    MAT_CENTER_Y,
    MAT_TO_MINI_SCALE,
    card_to_miniature_offset,
    get_chassis_polygon,
    get_weapon_template_geometry,
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

    point_dir_deg = math.degrees(math.atan2(dx, -dy))
    relative_angle = normalize_angle_deg(point_dir_deg - heading_deg)

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
            axis = (-edge[1], edge[0])

            mag = math.hypot(axis[0], axis[1])
            if mag < 1e-6:
                continue
            axis = (axis[0] / mag, axis[1] / mag)

            proj1 = [p[0] * axis[0] + p[1] * axis[1] for p in poly1]
            min1, max1 = min(proj1), max(proj1)

            proj2 = [p[0] * axis[0] + p[1] * axis[1] for p in poly2]
            min2, max2 = min(proj2), max(proj2)

            if max1 < min2 or max2 < min1:
                return False

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

    c1x = sum(p[0] for p in poly1) / len(poly1)
    c1y = sum(p[1] for p in poly1) / len(poly1)
    c2x = sum(p[0] for p in poly2) / len(poly2)
    c2y = sum(p[1] for p in poly2) / len(poly2)
    return ((c1x + c2x) / 2.0, (c1y + c2y) / 2.0)


def world_to_local_point(
    wx: float, wy: float, center_x: float, center_y: float, theta_deg: float
) -> Tuple[float, float]:
    """Transforms world coordinate (wx, wy) into local robot miniature space (where North is -y)."""
    dx = wx - center_x
    dy = wy - center_y
    rad = math.radians(-theta_deg)
    cos_t = math.cos(rad)
    sin_t = math.sin(rad)
    lx = dx * cos_t - dy * sin_t
    ly = dx * sin_t + dy * cos_t
    return (lx, ly)


def local_miniature_to_mat_point(lx: float, ly: float) -> Tuple[float, float]:
    """Converts local miniature coordinates to A3 chassis mat coordinates in mm."""
    mx = MAT_CENTER_X + lx / MAT_TO_MINI_SCALE
    my = MAT_CENTER_Y + ly / MAT_TO_MINI_SCALE
    return (mx, my)


def get_robot_miniature_parts(
    robot: RobotState, px: float, py: float, theta: float
) -> Dict[str, Any]:
    """
    Constructs the composite miniature geometry (chassis polygon + weapon polygons)
    transformed to the given world pose.
    """
    chassis_poly = get_chassis_polygon(robot.chassis_template, px, py, theta)

    weapon_parts = []
    active_weapon_parts = []

    for cid, comp in robot.components.items():
        if comp.card_type != "weapon" or comp.is_destroyed:
            continue
        # Invertible check
        if robot.is_inverted and not comp.is_invertible:
            continue

        offset = card_to_miniature_offset(comp.x, comp.y)
        geom = get_weapon_template_geometry(comp.template, offset)

        w_poly = transform_polygon(geom["polygon"], px, py, theta)
        act_poly = transform_polygon(geom["active_polygon"], px, py, theta)

        weapon_parts.append({"cid": cid, "polygon": w_poly})
        active_weapon_parts.append({"cid": cid, "polygon": act_poly})

    all_body_polygons = [chassis_poly] + [wp["polygon"] for wp in weapon_parts]

    return {
        "chassis_polygon": chassis_poly,
        "weapon_parts": weapon_parts,
        "active_weapon_parts": active_weapon_parts,
        "all_body_polygons": all_body_polygons,
    }


def find_contacted_components_on_mat(
    robot: RobotState,
    contact_pt: Tuple[float, float],
    robot_x: float,
    robot_y: float,
    robot_theta: float,
    octant: str,
    active_cid: Optional[str] = None,
) -> List[str]:
    """
    Maps world contact point onto the A3 chassis sheet to determine which
    outermost card(s) were contacted.
    """
    if active_cid and active_cid in robot.components and not robot.components[active_cid].is_destroyed:
        return [active_cid]

    lx, ly = world_to_local_point(contact_pt[0], contact_pt[1], robot_x, robot_y, robot_theta)
    mx, my = local_miniature_to_mat_point(lx, ly)

    active_comps = [c for c in robot.components.values() if not c.is_destroyed]
    if not active_comps:
        return []

    def dist_point_to_box(px: float, py: float, box: Tuple[float, float, float, float]) -> float:
        clamped_x = max(box[0], min(box[2], px))
        clamped_y = max(box[1], min(box[3], py))
        return math.hypot(px - clamped_x, py - clamped_y)

    # 1. Exact inside-box check
    inside_comps = [
        c for c in active_comps
        if c.box[0] <= mx <= c.box[2] and c.box[1] <= my <= c.box[3]
    ]
    if inside_comps:
        # If multiple overlap, pick the one with center closest to (mx, my)
        best = min(
            inside_comps,
            key=lambda c: math.hypot(
                mx - (c.box[0] + c.box[2]) / 2.0,
                my - (c.box[1] + c.box[3]) / 2.0,
            ),
        )
        return [best.id]

    # 2. Outside all boxes: find the active card whose box boundary is closest to (mx, my)
    best = min(active_comps, key=lambda c: dist_point_to_box(mx, my, c.box))
    return [best.id]


def detect_collision(
    r1: RobotState,
    traj1: List[TrajectoryPoint],
    r2: RobotState,
    traj2: List[TrajectoryPoint],
) -> Optional[CollisionEvent]:
    """
    Steps along both trajectories simultaneously from t=0.0 to t=1.0.
    Detects first collision between composite miniatures, tests active weapon red zones,
    and calculates remaining motion vectors for pushing match.
    """
    num_steps = min(len(traj1), len(traj2))

    for k in range(1, num_steps):
        p1 = traj1[k]
        p2 = traj2[k]

        parts1 = get_robot_miniature_parts(r1, p1.x, p1.y, p1.theta)
        parts2 = get_robot_miniature_parts(r2, p2.x, p2.y, p2.theta)

        # Check collision across all body polygons
        has_contact = False
        contact_pt = (0.0, 0.0)

        for polyA in parts1["all_body_polygons"]:
            for polyB in parts2["all_body_polygons"]:
                if polygons_intersect(polyA, polyB):
                    has_contact = True
                    contact_pt = find_polygon_contact_center(polyA, polyB)
                    break
            if has_contact:
                break

        if has_contact:
            # Check Active weapon contact:
            # Does R1 active weapon touch any part of R2?
            r1_active_cid = None
            for act in parts1["active_weapon_parts"]:
                for polyB in parts2["all_body_polygons"]:
                    if polygons_intersect(act["polygon"], polyB):
                        r1_active_cid = act["cid"]
                        break
                if r1_active_cid:
                    break

            # Does R2 active weapon touch any part of R1?
            r2_active_cid = None
            for act in parts2["active_weapon_parts"]:
                for polyA in parts1["all_body_polygons"]:
                    if polygons_intersect(act["polygon"], polyA):
                        r2_active_cid = act["cid"]
                        break
                if r2_active_cid:
                    break

            is_active_hit = bool(r1_active_cid or r2_active_cid)
            contact_type = "ACTIVE" if is_active_hit else "INERT"

            oct1 = get_octant(p1.x, p1.y, contact_pt[0], contact_pt[1], p1.theta)
            oct2 = get_octant(p2.x, p2.y, contact_pt[0], contact_pt[1], p2.theta)

            comps1 = find_contacted_components_on_mat(r1, contact_pt, p1.x, p1.y, p1.theta, oct1, r1_active_cid)
            comps2 = find_contacted_components_on_mat(r2, contact_pt, p2.x, p2.y, p2.theta, oct2, r2_active_cid)

            # Remaining motion vectors from contact step k to destination t=1.0
            dest1 = traj1[-1]
            dest2 = traj2[-1]
            v1_rem_x = dest1.x - p1.x
            v1_rem_y = dest1.y - p1.y
            v2_rem_x = dest2.x - p2.x
            v2_rem_y = dest2.y - p2.y

            r1_rem_dist = math.hypot(v1_rem_x, v1_rem_y)
            r2_rem_dist = math.hypot(v2_rem_x, v2_rem_y)

            # The pair of robots move in a straight line created by summing their remaining motion templates
            push_vec = (v1_rem_x + v2_rem_x, v1_rem_y + v2_rem_y)

            desc_parts = []
            if contact_type == "ACTIVE":
                if r1_active_cid and r2_active_cid:
                    desc_parts.append(f"Head-on active weapon clash! ({r1.name} and {r2.name})")
                elif r1_active_cid:
                    wname = r1.components[r1_active_cid].name
                    desc_parts.append(f"{r1.name}'s active {wname} strikes {r2.name}'s {oct2} octant!")
                else:
                    wname = r2.components[r2_active_cid].name
                    desc_parts.append(f"{r2.name}'s active {wname} strikes {r1.name}'s {oct1} octant!")
            else:
                desc_parts.append(f"Inert pushing contact: {r1.name} ({oct1}) vs {r2.name} ({oct2})")

            return CollisionEvent(
                time_t=p1.t,
                step_index=k,
                contact_point=contact_pt,
                robot1_octant=oct1,
                robot2_octant=oct2,
                robot1_components=comps1,
                robot2_components=comps2,
                contact_type=contact_type,
                description=" ".join(desc_parts),
                r1_remaining_dist=r1_rem_dist,
                r2_remaining_dist=r2_rem_dist,
                r1_rem_vector=(v1_rem_x, v1_rem_y),
                r2_rem_vector=(v2_rem_x, v2_rem_y),
                push_vector=push_vec,
                r1_active_hit=bool(r1_active_cid),
                r2_active_hit=bool(r2_active_cid),
            )

    return None


def check_robots_in_contact(r1: RobotState, r2: RobotState) -> bool:
    """
    Checks whether any body polygons (chassis or weapons) of r1 and r2
    are currently intersecting in their current poses.
    """
    parts1 = get_robot_miniature_parts(r1, r1.pose.x, r1.pose.y, r1.pose.theta)
    parts2 = get_robot_miniature_parts(r2, r2.pose.x, r2.pose.y, r2.pose.theta)

    for polyA in parts1["all_body_polygons"]:
        for polyB in parts2["all_body_polygons"]:
            if polygons_intersect(polyA, polyB):
                return True
    return False


def check_robot_forks_in_line(
    fork_robot: RobotState,
    opp_robot: RobotState,
    contact_pt: Optional[Tuple[float, float]] = None,
    fork_pose: Any = None,
    contacted_cids: Optional[List[str]] = None,
    opp_pose: Any = None,
) -> bool:
    """
    Checks if any part of the opposing robot is in line with fork_robot's forks during contact.
    Rule: 'The forks trigger if any part of the opposing robot is in line with the fork, not just the contact point'
    """
    fork_comps = [
        c for c in fork_robot.components.values()
        if (c.is_forks or "FORKS" in c.keywords.upper()) and not c.is_destroyed
    ]
    if not fork_comps:
        return False

    # 1. Direct component contact with forks
    fork_ids = {c.id for c in fork_comps}
    if contacted_cids and any(cid in fork_ids for cid in contacted_cids):
        return True

    # Resolve fork_robot pose
    if fork_pose is None:
        fx, fy, ftheta = fork_robot.pose.x, fork_robot.pose.y, fork_robot.pose.theta
    elif hasattr(fork_pose, "x"):
        fx, fy, ftheta = fork_pose.x, fork_pose.y, fork_pose.theta
    else:
        fx, fy, ftheta = fork_pose

    # Resolve opp_robot pose
    if opp_pose is None:
        ox, oy, otheta = opp_robot.pose.x, opp_robot.pose.y, opp_robot.pose.theta
    elif hasattr(opp_pose, "x"):
        ox, oy, otheta = opp_pose.x, opp_pose.y, opp_pose.theta
    else:
        ox, oy, otheta = opp_pose

    # Opposing robot geometry (all body polygons: chassis + weapons)
    opp_parts = get_robot_miniature_parts(opp_robot, ox, oy, otheta)
    opp_polys = list(opp_parts.get("all_body_polygons", []))

    # Also include 12-gon approximation of the 70mm diameter disc base
    opp_disc = [
        (ox + 35.0 * math.cos(2.0 * math.pi * i / 12.0), oy + 35.0 * math.sin(2.0 * math.pi * i / 12.0))
        for i in range(12)
    ]
    opp_polys.append(opp_disc)

    for fc in fork_comps:
        min_x, min_y, max_x, max_y = fc.box

        # Lateral span in local miniature coordinates (relative to MAT_CENTER_X)
        lx_left = (min_x - MAT_CENTER_X) * MAT_TO_MINI_SCALE
        lx_right = (max_x - MAT_CENTER_X) * MAT_TO_MINI_SCALE
        lx_min = min(lx_left, lx_right) - 2.0
        lx_max = max(lx_left, lx_right) + 2.0

        # Longitudinal span: extending forward from rear edge of the fork card
        # Heading 0 is North = -Y (forward)
        ly_rear = (max_y - MAT_CENTER_Y) * MAT_TO_MINI_SCALE + 2.0
        ly_front = ly_rear - 150.0  # extends forward across the contact zone

        corridor_local = [
            (lx_min, ly_front),
            (lx_max, ly_front),
            (lx_max, ly_rear),
            (lx_min, ly_rear),
        ]
        corridor_world = transform_polygon(corridor_local, fx, fy, ftheta)

        # Check if ANY part of opposing robot's geometry intersects the fork corridor
        for poly in opp_polys:
            if polygons_intersect(corridor_world, poly):
                return True

        # Check if contact point falls inside the corridor
        if contact_pt and point_in_polygon(contact_pt[0], contact_pt[1], corridor_world):
            return True

    return False
