"""Composite miniature polygon intersection, active weapon red-zone detection, and contact resolution."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from .field import (
    CHASSIS_MINIATURE_SHAPES,
    MAT_CENTER_X,
    MAT_CENTER_Y,
    MAT_TO_MINI_SCALE,
    WALL_BOTTOM,
    WALL_LEFT,
    WALL_RIGHT,
    WALL_TOP,
    card_to_miniature_offset,
    get_chassis_polygon,
    get_weapon_template_geometry,
    point_in_polygon,
    transform_point,
    transform_polygon,
)
from .types import CollisionEvent, ComponentHealth, Pose, RobotState, TrajectoryPoint

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


def rotate_point_around(
    pt: Tuple[float, float], center: Tuple[float, float], angle_deg: float
) -> Tuple[float, float]:
    """Rotates a 2D point around center by angle_deg (clockwise in y-down coords)."""
    if abs(angle_deg) < 1e-4:
        return pt
    rad = math.radians(angle_deg)
    cos_t = math.cos(rad)
    sin_t = math.sin(rad)
    dx = pt[0] - center[0]
    dy = pt[1] - center[1]
    return (center[0] + dx * cos_t - dy * sin_t, center[1] + dx * sin_t + dy * cos_t)


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

        cw = 64.0 if comp.rotation in (90, 270) else 44.0
        ch = 44.0 if comp.rotation in (90, 270) else 64.0
        offset = card_to_miniature_offset(comp.x, comp.y, cw, ch)
        geom = get_weapon_template_geometry(comp.template, offset)

        w_poly_local = [rotate_point_around(p, offset, comp.rotation) for p in geom["polygon"]]
        act_poly_local = [rotate_point_around(p, offset, comp.rotation) for p in geom["active_polygon"]]
        act_polys_local = [
            [rotate_point_around(p, offset, comp.rotation) for p in ap]
            for ap in geom.get("active_polygons", [geom["active_polygon"]])
        ]

        w_poly = transform_polygon(w_poly_local, px, py, theta)
        act_poly = transform_polygon(act_poly_local, px, py, theta)
        act_polys = [transform_polygon(ap, px, py, theta) for ap in act_polys_local]

        weapon_parts.append({"cid": cid, "polygon": w_poly})
        active_weapon_parts.append({"cid": cid, "polygon": act_poly, "polygons": act_polys})

    all_body_polygons = [chassis_poly] + [wp["polygon"] for wp in weapon_parts]

    return {
        "chassis_polygon": chassis_poly,
        "weapon_parts": weapon_parts,
        "active_weapon_parts": active_weapon_parts,
        "all_body_polygons": all_body_polygons,
    }


def is_wedge_fork_or_drive(c: ComponentHealth) -> bool:
    kw = (c.keywords or "").upper()
    nm = (c.name or "").upper()
    out = (c.outputs or "").upper()
    has_wedge = c.is_wedge or "WEDGE" in kw or "WEDGE" in nm
    has_fork = c.is_forks or "FORK" in kw or "FORK" in nm
    has_drive = out.count("D") > 0 or out.count("M") > 0 or "DRIVE" in kw or "DRIVE" in nm or "WHEEL" in nm
    return has_wedge or has_fork or has_drive


def ray_aabb_distance(ox: float, oy: float, dx: float, dy: float, box: Tuple[float, float, float, float]) -> Optional[float]:
    """
    Computes entry distance t >= 0 along ray (ox, oy) + t * (dx, dy) to axis-aligned box (bmin_x, bmin_y, bmax_x, bmax_y).
    Returns t >= 0 if intersects, or None. If (ox, oy) is inside, returns 0.0.
    """
    bmin_x, bmin_y, bmax_x, bmax_y = box
    if bmin_x <= ox <= bmax_x and bmin_y <= oy <= bmax_y:
        return 0.0

    tmin = 0.0
    tmax = float("inf")
    for o, d, bmin, bmax in [(ox, dx, bmin_x, bmax_x), (oy, dy, bmin_y, bmax_y)]:
        if abs(d) < 1e-6:
            if o < bmin or o > bmax:
                return None
        else:
            t1 = (bmin - o) / d
            t2 = (bmax - o) / d
            if t1 > t2:
                t1, t2 = t2, t1
            tmin = max(tmin, t1)
            tmax = min(tmax, t2)
            if tmin > tmax:
                return None
    return tmin if tmin >= 0.0 else None


def ray_segment_intersection(
    ox: float, oy: float, dx: float, dy: float,
    x1: float, y1: float, x2: float, y2: float
) -> Optional[float]:
    """
    Finds intersection parameter t >= 0 along ray (ox, oy) + t * (dx, dy)
    with line segment from (x1, y1) to (x2, y2).
    """
    sx = x2 - x1
    sy = y2 - y1
    denom = dx * sy - dy * sx
    if abs(denom) < 1e-7:
        return None  # Parallel or collinear

    t = ((x1 - ox) * sy - (y1 - oy) * sx) / denom
    s = ((x1 - ox) * dy - (y1 - oy) * dx) / denom
    if t >= -1e-4 and -1e-4 <= s <= 1.0 + 1e-4:
        return max(0.0, t)
    return None


def ray_polygon_distance(
    ox: float, oy: float, dx: float, dy: float, polygon: List[Tuple[float, float]]
) -> Optional[float]:
    """
    Returns entry distance t >= 0 along ray into polygon.
    If (ox, oy) is inside the polygon (or on its boundary), returns 0.0.
    """
    if point_in_polygon(ox, oy, polygon):
        return 0.0

    n = len(polygon)
    min_t: Optional[float] = None
    for i in range(n):
        p1 = polygon[i]
        p2 = polygon[(i + 1) % n]
        t = ray_segment_intersection(ox, oy, dx, dy, p1[0], p1[1], p2[0], p2[1])
        if t is not None:
            if min_t is None or t < min_t:
                min_t = t
    return min_t


def find_components_along_contact_line(
    robot: RobotState,
    contact_pt: Tuple[float, float],
    robot_x: float,
    robot_y: float,
    robot_theta: float,
    octant: str,
    skip_without_wedge_fork_drive: bool = False,
    active_cid: Optional[str] = None,
) -> List[str]:
    """
    Maps world contact point onto the A3 chassis sheet to determine which
    component(s) along the contact line were contacted.
    Rule: 'The first remaining component on the robot along the line corresponding to the contact point is the component hit.'
    Rule: 'When working out what component is hit, if a template is crossed that weapon is the component hit in that contact.'
    Rule: 'Where ambiguous, both components make contact.'
    Rule: 'Similarly if a weapon contacts multiple components at once, each component is damaged...'
    Rule: 'unless inverted this component's attacks skip past components without wedge, fork or drive'
    """
    if active_cid and active_cid in robot.components and not robot.components[active_cid].is_destroyed:
        return [active_cid]

    active_comps = [c for c in robot.components.values() if not c.is_destroyed]
    if not active_comps:
        return []

    lx, ly = world_to_local_point(contact_pt[0], contact_pt[1], robot_x, robot_y, robot_theta)
    mx, my = local_miniature_to_mat_point(lx, ly)

    # Inward ray in local miniature coordinates from (lx, ly) towards robot center (0.0, 0.0)
    ldx = -lx
    ldy = -ly
    ldist = math.hypot(ldx, ldy)
    lux, luy = (ldx / ldist, ldy / ldist) if ldist > 1e-4 else (0.0, -1.0)

    # Rule: "When working out what component is hit, if a template is crossed that weapon is the component hit in that contact."
    active_weapons = [
        c for c in active_comps
        if c.card_type == "weapon" and (not robot.is_inverted or c.is_invertible)
    ]
    if skip_without_wedge_fork_drive:
        active_weapons = [c for c in active_weapons if is_wedge_fork_or_drive(c)]

    crossed_weapon_templates: List[Tuple[float, ComponentHealth]] = []
    for w_comp in active_weapons:
        cw = 64.0 if w_comp.rotation in (90, 270) else 44.0
        ch = 44.0 if w_comp.rotation in (90, 270) else 64.0
        offset = card_to_miniature_offset(w_comp.x, w_comp.y, cw, ch)
        geom = get_weapon_template_geometry(w_comp.template, offset)
        w_poly_local = [rotate_point_around(p, offset, w_comp.rotation) for p in geom["polygon"]]

        t_enter = ray_polygon_distance(lx, ly, lux, luy, w_poly_local)
        if t_enter is not None and t_enter <= ldist + 5.0:
            crossed_weapon_templates.append((t_enter, w_comp))

    if crossed_weapon_templates:
        crossed_weapon_templates.sort(key=lambda item: item[0])
        min_wt = crossed_weapon_templates[0][0]
        hit_wpn_cids: List[str] = []
        for t_val, w_comp in crossed_weapon_templates:
            if abs(t_val - min_wt) <= 1.5:
                if w_comp.id not in hit_wpn_cids:
                    hit_wpn_cids.append(w_comp.id)
        if hit_wpn_cids:
            return hit_wpn_cids

    # Ray pointing inward toward chassis center on A3 mat
    dx = MAT_CENTER_X - mx
    dy = MAT_CENTER_Y - my
    dist = math.hypot(dx, dy)
    ux, uy = (dx / dist, dy / dist) if dist > 1e-4 else (0.0, -1.0)

    def dist_point_to_box(px: float, py: float, box: Tuple[float, float, float, float]) -> float:
        clamped_x = max(box[0], min(box[2], px))
        clamped_y = max(box[1], min(box[3], py))
        return math.hypot(px - clamped_x, py - clamped_y)

    intersections: List[Tuple[float, ComponentHealth]] = []
    for c in active_comps:
        if c.box[0] <= mx <= c.box[2] and c.box[1] <= my <= c.box[3]:
            intersections.append((0.0, c))
        else:
            t_enter = ray_aabb_distance(mx, my, ux, uy, c.box)
            if t_enter is not None and t_enter >= 0:
                intersections.append((t_enter, c))

    intersections.sort(key=lambda item: item[0])

    if not intersections:
        closest_comps = sorted(active_comps, key=lambda c: dist_point_to_box(mx, my, c.box))
        intersections = [(dist_point_to_box(mx, my, c.box), c) for c in closest_comps]

    # NightWing skip rule
    if skip_without_wedge_fork_drive:
        filtered = [item for item in intersections if is_wedge_fork_or_drive(item[1])]
        if filtered:
            intersections = filtered

    if not intersections:
        return [active_comps[0].id]

    min_t = intersections[0][0]
    # Include components whose boundary is within 4mm of first contact (seam / multi-contact)
    hit_cids: List[str] = []
    for t_val, comp in intersections:
        if abs(t_val - min_t) <= 4.0:
            if comp.id not in hit_cids:
                hit_cids.append(comp.id)

    return hit_cids if hit_cids else [intersections[0][1].id]


def find_contacted_components_on_mat(
    robot: RobotState,
    contact_pt: Tuple[float, float],
    robot_x: float,
    robot_y: float,
    robot_theta: float,
    octant: str,
    active_cid: Optional[str] = None,
) -> List[str]:
    """Backward-compatible wrapper for mapping world contact point to contacted component."""
    return find_components_along_contact_line(
        robot, contact_pt, robot_x, robot_y, robot_theta, octant,
        skip_without_wedge_fork_drive=False, active_cid=active_cid
    )


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
            # Check Active weapon contact across ALL active weapons:
            # Does R1 active weapons touch any part of R2?
            r1_active_weapons: List[str] = []
            r1_weapon_targets: Dict[str, List[str]] = {}
            for act in parts1["active_weapon_parts"]:
                w_cid = act["cid"]
                w_comp = r1.components.get(w_cid)
                if not w_comp or w_comp.is_destroyed:
                    continue
                sub_polys = act.get("polygons", [act["polygon"]])
                w_targets: List[str] = []
                w_hit = False
                for sub_poly in sub_polys:
                    intersecting_polys = [polyB for polyB in parts2["all_body_polygons"] if polygons_intersect(sub_poly, polyB)]
                    if intersecting_polys:
                        w_hit = True
                        wpn_contact_pt = find_polygon_contact_center(sub_poly, intersecting_polys[0])
                        skip_rule = ("skip past components without wedge, fork or drive" in (w_comp.text or "").lower() and not r1.is_inverted)
                        oct_r2 = get_octant(p2.x, p2.y, wpn_contact_pt[0], wpn_contact_pt[1], p2.theta)
                        targets = find_components_along_contact_line(
                            r2, wpn_contact_pt, p2.x, p2.y, p2.theta, oct_r2,
                            skip_without_wedge_fork_drive=skip_rule
                        )
                        for t in targets:
                            w_targets.append(t)
                if w_hit:
                    r1_active_weapons.append(w_cid)
                    r1_weapon_targets[w_cid] = w_targets

            # Does R2 active weapons touch any part of R1?
            r2_active_weapons: List[str] = []
            r2_weapon_targets: Dict[str, List[str]] = {}
            for act in parts2["active_weapon_parts"]:
                w_cid = act["cid"]
                w_comp = r2.components.get(w_cid)
                if not w_comp or w_comp.is_destroyed:
                    continue
                sub_polys = act.get("polygons", [act["polygon"]])
                w_targets: List[str] = []
                w_hit = False
                for sub_poly in sub_polys:
                    intersecting_polys = [polyA for polyA in parts1["all_body_polygons"] if polygons_intersect(sub_poly, polyA)]
                    if intersecting_polys:
                        w_hit = True
                        wpn_contact_pt = find_polygon_contact_center(sub_poly, intersecting_polys[0])
                        skip_rule = ("skip past components without wedge, fork or drive" in (w_comp.text or "").lower() and not r2.is_inverted)
                        oct_r1 = get_octant(p1.x, p1.y, wpn_contact_pt[0], wpn_contact_pt[1], p1.theta)
                        targets = find_components_along_contact_line(
                            r1, wpn_contact_pt, p1.x, p1.y, p1.theta, oct_r1,
                            skip_without_wedge_fork_drive=skip_rule
                        )
                        for t in targets:
                            w_targets.append(t)
                if w_hit:
                    r2_active_weapons.append(w_cid)
                    r2_weapon_targets[w_cid] = w_targets

            is_active_hit = bool(r1_active_weapons or r2_active_weapons)
            contact_type = "ACTIVE" if is_active_hit else "INERT"

            oct1 = get_octant(p1.x, p1.y, contact_pt[0], contact_pt[1], p1.theta)
            oct2 = get_octant(p2.x, p2.y, contact_pt[0], contact_pt[1], p2.theta)

            if r1_active_weapons:
                comps1 = list(r1_active_weapons)
            else:
                comps1 = find_contacted_components_on_mat(r1, contact_pt, p1.x, p1.y, p1.theta, oct1, active_cid=None)

            if r2_active_weapons:
                comps2 = list(r2_active_weapons)
            else:
                comps2 = find_contacted_components_on_mat(r2, contact_pt, p2.x, p2.y, p2.theta, oct2, active_cid=None)

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
                if r1_active_weapons and r2_active_weapons:
                    desc_parts.append(f"Head-on active weapon clash! ({r1.name} and {r2.name})")
                elif r1_active_weapons:
                    w_names = ", ".join(r1.components[w].name for w in r1_active_weapons if w in r1.components)
                    desc_parts.append(f"{r1.name}'s active {w_names} strikes {r2.name}'s {oct2} octant!")
                else:
                    w_names = ", ".join(r2.components[w].name for w in r2_active_weapons if w in r2.components)
                    desc_parts.append(f"{r2.name}'s active {w_names} strikes {r1.name}'s {oct1} octant!")
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
                r1_active_hit=bool(r1_active_weapons),
                r2_active_hit=bool(r2_active_weapons),
                r1_active_weapons=r1_active_weapons,
                r2_active_weapons=r2_active_weapons,
                r1_weapon_targets=r1_weapon_targets,
                r2_weapon_targets=r2_weapon_targets,
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
    if fork_robot.is_inverted:
        fork_comps = [c for c in fork_comps if c.is_invertible]
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


def get_weapon_wall_contacts(
    robot: RobotState,
    pose: Pose,
    wall_tol: float = 1.0,
) -> List[str]:
    """
    Returns list of weapon component IDs whose miniature polygons contact
    or cross the arena perimeter walls.
    """
    parts = get_robot_miniature_parts(robot, pose.x, pose.y, pose.theta)
    contacting_cids: List[str] = []
    for w_part in parts["weapon_parts"]:
        cid = w_part["cid"]
        poly = w_part["polygon"]
        hits_wall = any(
            x <= WALL_LEFT + wall_tol
            or x >= WALL_RIGHT - wall_tol
            or y <= WALL_TOP + wall_tol
            or y >= WALL_BOTTOM - wall_tol
            for x, y in poly
        )
        if hits_wall and cid not in contacting_cids:
            contacting_cids.append(cid)
    return contacting_cids
