"""Template-based movement and trajectory generation for Robot Battles."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from .field import WALL_BOTTOM, WALL_LEFT, WALL_RIGHT, WALL_TOP
from .types import MoveChoice, Pose, TrajectoryPoint

# Distance in mm per 1 drive unit on the straight template
from generate_movement_templates import (
    DEFAULT_DRIVE_UNIT_MM,
    DEFAULT_MINIATURE_RADIUS,
    DEFAULT_WHEELBASE_MM,
    map_permutation_to_template,
)

DRIVE_UNIT_MM: float = DEFAULT_DRIVE_UNIT_MM
WHEELBASE_MM: float = DEFAULT_WHEELBASE_MM
MINIATURE_RADIUS: float = DEFAULT_MINIATURE_RADIUS

# Physical curve template parameters matching generate_movement_templates.py
CURVE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "curve_gentle": {
        "nominal_rc": 220.0,
        "pair_angles": {
            (3, 2): 26.0,
            (4, 3): 36.5,
            (5, 4): 47.0,
        },
    },
    "curve_medium": {
        "nominal_rc": 97.5,
        "pair_angles": {
            (2, 1): 35.0,
            (4, 2): 70.0,
            (5, 3): 94.0,
        },
    },
    "curve_sharp": {
        "nominal_rc": 55.0,
        "pair_angles": {
            (3, 1): 70.0,
            (4, 1): 105.0,
            (5, 2): 145.0,
            (5, 1): 180.0,
        },
    },
}


def list_template_options(left_max: int, right_max: int) -> List[Dict[str, Any]]:
    """
    Returns valid discrete movement template tracks available to a robot
    with the given active left and right drive counts.
    """
    options: List[Dict[str, Any]] = [
        {"name": "Stop (0, 0)", "left": 0, "right": 0, "category": "stop", "icon": "⏹️"}
    ]

    # 1. Straight tracks forward: (1, 1) .. (k, k)
    max_straight = min(left_max, right_max)
    for k in range(1, max_straight + 1):
        options.append({
            "name": f"Straight {k} ({k}, {k})",
            "left": k,
            "right": k,
            "category": "straight",
            "icon": "⬆️",
        })

    # Reverse straight tracks: (-1, -1) .. (-k, -k)
    for k in range(1, max_straight + 1):
        options.append({
            "name": f"Reverse {k} (-{k}, -{k})",
            "left": -k,
            "right": -k,
            "category": "reverse",
            "icon": "⬇️",
        })

    # 2. Forward Curve tracks across the 3 physical curve templates
    curve_pairs = [
        # Gentle curve: (3, 2), (4, 3), (5, 4)
        (3, 2, "Gentle Curve Right (3, 2)"),
        (4, 3, "Gentle Curve Right (4, 3)"),
        (5, 4, "Gentle Curve Right (5, 4)"),
        (2, 3, "Gentle Curve Left (2, 3)"),
        (3, 4, "Gentle Curve Left (3, 4)"),
        (4, 5, "Gentle Curve Left (4, 5)"),
        # Medium curve: (2, 1), (4, 2), (5, 3)
        (2, 1, "Medium Curve Right (2, 1)"),
        (4, 2, "Medium Curve Right (4, 2)"),
        (5, 3, "Medium Curve Right (5, 3)"),
        (1, 2, "Medium Curve Left (1, 2)"),
        (2, 4, "Medium Curve Left (2, 4)"),
        (3, 5, "Medium Curve Left (3, 5)"),
        # Sharp curve: (3, 1), (4, 1), (5, 2), (5, 1)
        (3, 1, "Sharp Curve Right (3, 1)"),
        (4, 1, "Sharp Curve Right (4, 1)"),
        (5, 2, "Sharp Curve Right (5, 2)"),
        (5, 1, "Sharp Curve Right (5, 1)"),
        (1, 3, "Sharp Curve Left (1, 3)"),
        (1, 4, "Sharp Curve Left (1, 4)"),
        (2, 5, "Sharp Curve Left (2, 5)"),
        (1, 5, "Sharp Curve Left (1, 5)"),
    ]
    for l_val, r_val, lbl in curve_pairs:
        if l_val <= left_max and r_val <= right_max:
            options.append({
                "name": lbl,
                "left": l_val,
                "right": r_val,
                "category": "curve",
                "icon": "↗️" if l_val > r_val else "↖️",
            })

    # 3. Pivot tracks: (1, 0) .. (5, 0) and (0, 1) .. (0, 5)
    for k in range(1, left_max + 1):
        if k <= 5:
            options.append({
                "name": f"Pivot Right ({k}, 0)",
                "left": k,
                "right": 0,
                "category": "pivot",
                "icon": "🔃",
            })
    for k in range(1, right_max + 1):
        if k <= 5:
            options.append({
                "name": f"Pivot Left (0, {k})",
                "left": 0,
                "right": k,
                "category": "pivot",
                "icon": "🔄",
            })

    # 4. Spin-on-spot tracks: (1, -1) .. (4, -4) and (-1, 1) .. (-4, 4)
    max_spin = min(left_max, right_max)
    for k in range(1, min(4, max_spin) + 1):
        options.append({
            "name": f"Spin CW ({k}, -{k})",
            "left": k,
            "right": -k,
            "category": "spin",
            "icon": "↻",
        })
        options.append({
            "name": f"Spin CCW (-{k}, {k})",
            "left": -k,
            "right": k,
            "category": "spin",
            "icon": "↺",
        })

    # 5. Asymmetric counter drives: e.g. (3, -1), (3, -2), (4, -1), (4, -2)
    for l_cand in range(1, left_max + 1):
        for r_cand in range(1, right_max + 1):
            if l_cand != r_cand:
                options.append({
                    "name": f"Counter CW ({l_cand}, -{r_cand})",
                    "left": l_cand,
                    "right": -r_cand,
                    "category": "asymmetric_counter",
                    "icon": "🔀",
                })
                options.append({
                    "name": f"Counter CCW (-{l_cand}, {r_cand})",
                    "left": -l_cand,
                    "right": r_cand,
                    "category": "asymmetric_counter",
                    "icon": "🔀",
                })

    return options


def generate_trajectory(
    start_pose: Pose,
    choice: MoveChoice,
    num_steps: int = 30,
    clamp_to_walls: bool = True,
) -> List[TrajectoryPoint]:
    """
    Computes a discrete trajectory of TrajectoryPoints from t=0.0 to t=1.0
    for a chosen (Left, Right) drive pair along the corresponding physical movement template.
    The robot starts with its front (or rear for reverse) bumper flush at the template baseline
    and follows the exact template channel to the marked stop line.
    """
    l_val = float(choice.left)
    r_val = float(choice.right)

    theta_0_rad = start_pose.heading_rad()
    x_0 = start_pose.x
    y_0 = start_pose.y

    # Forward vector f (heading 0 is North: dx = 0, dy = -1)
    f_x = math.sin(theta_0_rad)
    f_y = -math.cos(theta_0_rad)

    # Right vector r (heading 0 is North: dx = 1, dy = 0)
    r_x = math.cos(theta_0_rad)
    r_y = math.sin(theta_0_rad)

    # Map choice directly to physical movement template
    info = map_permutation_to_template(int(choice.left), int(choice.right))
    cat = info["category"]

    # Case 1: Stationary (0, 0)
    if cat == "stop":
        points = [
            TrajectoryPoint(x=x_0, y=y_0, theta=start_pose.theta, t=i / float(num_steps))
            for i in range(num_steps + 1)
        ]
        return points

    # Case 2: Straight translation (L == R)
    if cat == "straight":
        total_dist = l_val * DRIVE_UNIT_MM
        points = []
        for i in range(num_steps + 1):
            t = i / float(num_steps)
            dist_t = total_dist * t
            px = x_0 + dist_t * f_x
            py = y_0 + dist_t * f_y
            if clamp_to_walls:
                px = max(WALL_LEFT + MINIATURE_RADIUS, min(WALL_RIGHT - MINIATURE_RADIUS, px))
                py = max(WALL_TOP + MINIATURE_RADIUS, min(WALL_BOTTOM - MINIATURE_RADIUS, py))
            points.append(TrajectoryPoint(x=px, y=py, theta=start_pose.theta, t=t))
        return points

    # Case 3: Pure Spin-on-the-spot (L == -R)
    # Spin Disc template: 90 deg per 1 drive unit (4 units = 360 deg)
    if cat == "spin":
        delta_deg = l_val * 90.0  # Positive L spins clockwise
        points = []
        for i in range(num_steps + 1):
            t = i / float(num_steps)
            curr_theta = (start_pose.theta + t * delta_deg) % 360.0
            points.append(TrajectoryPoint(x=x_0, y=y_0, theta=curr_theta, t=t))
        return points

    # Case 4: Pivot on locked wheel (one side is 0)
    # Pivot Fan template: 45 deg per 1 unit (4 units = 180 deg)
    if cat == "pivot":
        points = []
        pivot_offset = WHEELBASE_MM / 2.0

        if abs(r_val) < 1e-6 and l_val > 0:
            # Forward pivot around right wheel (turning right / CW)
            pv_x = x_0 + pivot_offset * r_x
            pv_y = y_0 + pivot_offset * r_y
            total_deg = l_val * 45.0
            for i in range(num_steps + 1):
                t = i / float(num_steps)
                phi = math.radians(t * total_deg)
                px = pv_x - pivot_offset * (math.cos(phi) * r_x - math.sin(phi) * f_x)
                py = pv_y - pivot_offset * (math.cos(phi) * r_y - math.sin(phi) * f_y)
                curr_theta = (start_pose.theta + t * total_deg) % 360.0
                if clamp_to_walls:
                    px = max(WALL_LEFT + MINIATURE_RADIUS, min(WALL_RIGHT - MINIATURE_RADIUS, px))
                    py = max(WALL_TOP + MINIATURE_RADIUS, min(WALL_BOTTOM - MINIATURE_RADIUS, py))
                points.append(TrajectoryPoint(x=px, y=py, theta=curr_theta, t=t))

        elif abs(l_val) < 1e-6 and r_val > 0:
            # Forward pivot around left wheel (turning left / CCW)
            pv_x = x_0 - pivot_offset * r_x
            pv_y = y_0 - pivot_offset * r_y
            total_deg = r_val * 45.0
            for i in range(num_steps + 1):
                t = i / float(num_steps)
                phi = math.radians(t * total_deg)
                px = pv_x + pivot_offset * (math.cos(phi) * r_x + math.sin(phi) * f_x)
                py = pv_y + pivot_offset * (math.cos(phi) * r_y + math.sin(phi) * f_y)
                curr_theta = (start_pose.theta - t * total_deg) % 360.0
                if clamp_to_walls:
                    px = max(WALL_LEFT + MINIATURE_RADIUS, min(WALL_RIGHT - MINIATURE_RADIUS, px))
                    py = max(WALL_TOP + MINIATURE_RADIUS, min(WALL_BOTTOM - MINIATURE_RADIUS, py))
                points.append(TrajectoryPoint(x=px, y=py, theta=curr_theta, t=t))

        elif abs(r_val) < 1e-6 and l_val < 0:
            # Reverse pivot on right wheel (template at rear)
            pv_x = x_0 + pivot_offset * r_x
            pv_y = y_0 + pivot_offset * r_y
            total_deg = abs(l_val) * 45.0
            for i in range(num_steps + 1):
                t = i / float(num_steps)
                phi = math.radians(t * total_deg)
                px = pv_x - pivot_offset * (math.cos(phi) * r_x - math.sin(phi) * f_x)
                py = pv_y - pivot_offset * (math.cos(phi) * r_y - math.sin(phi) * f_y)
                curr_theta = (start_pose.theta - t * total_deg) % 360.0
                if clamp_to_walls:
                    px = max(WALL_LEFT + MINIATURE_RADIUS, min(WALL_RIGHT - MINIATURE_RADIUS, px))
                    py = max(WALL_TOP + MINIATURE_RADIUS, min(WALL_BOTTOM - MINIATURE_RADIUS, py))
                points.append(TrajectoryPoint(x=px, y=py, theta=curr_theta, t=t))

        elif abs(l_val) < 1e-6 and r_val < 0:
            # Reverse pivot on left wheel (template at rear)
            pv_x = x_0 - pivot_offset * r_x
            pv_y = y_0 - pivot_offset * r_y
            total_deg = abs(r_val) * 45.0
            for i in range(num_steps + 1):
                t = i / float(num_steps)
                phi = math.radians(t * total_deg)
                px = pv_x + pivot_offset * (math.cos(phi) * r_x - math.sin(phi) * f_x)
                py = pv_y + pivot_offset * (math.cos(phi) * r_y - math.sin(phi) * f_y)
                curr_theta = (start_pose.theta + t * total_deg) % 360.0
                if clamp_to_walls:
                    px = max(WALL_LEFT + MINIATURE_RADIUS, min(WALL_RIGHT - MINIATURE_RADIUS, px))
                    py = max(WALL_TOP + MINIATURE_RADIUS, min(WALL_BOTTOM - MINIATURE_RADIUS, py))
                points.append(TrajectoryPoint(x=px, y=py, theta=curr_theta, t=t))

        return points

    # Case 5: Forward / Reverse Curves using consolidated physical Curve Templates
    # (curve_gentle, curve_medium, curve_sharp)
    if cat == "curve_forward":
        t_id = info["template_id"]
        c_l = info["canonical_left"]
        c_r = info["canonical_right"]
        cfg = CURVE_CONFIGS.get(t_id, CURVE_CONFIGS["curve_medium"])
        r_c = cfg["nominal_rc"]
        phi_deg = cfg["pair_angles"].get((c_l, c_r), (c_l - c_r) * 35.0)
        flipped = info["flipped"]
        at_rear = info["at_rear"]

        points = []
        for i in range(num_steps + 1):
            t = i / float(num_steps)
            phi = math.radians(t * phi_deg)
            cos_p = math.cos(phi)
            sin_p = math.sin(phi)

            if not at_rear:
                # Forward motion along the curved channel
                delta_f = r_c * sin_p + MINIATURE_RADIUS * (1.0 - cos_p)
                delta_r = r_c * (1.0 - cos_p) - MINIATURE_RADIUS * sin_p
                if flipped:
                    delta_r = -delta_r
                    delta_th = -t * phi_deg
                else:
                    delta_th = t * phi_deg
            else:
                # Reverse motion along the curved channel (template at rear bumper)
                delta_f = -(r_c * sin_p + MINIATURE_RADIUS * (1.0 - cos_p))
                delta_r = r_c * (1.0 - cos_p) - MINIATURE_RADIUS * sin_p
                if flipped:
                    delta_r = -delta_r
                    delta_th = t * phi_deg
                else:
                    delta_th = -t * phi_deg

            px = x_0 + delta_f * f_x + delta_r * r_x
            py = y_0 + delta_f * f_y + delta_r * r_y
            curr_theta = (start_pose.theta + delta_th) % 360.0

            if clamp_to_walls:
                px = max(WALL_LEFT + MINIATURE_RADIUS, min(WALL_RIGHT - MINIATURE_RADIUS, px))
                py = max(WALL_TOP + MINIATURE_RADIUS, min(WALL_BOTTOM - MINIATURE_RADIUS, py))

            points.append(TrajectoryPoint(x=px, y=py, theta=curr_theta, t=t))

        return points

    # Case 6: Asymmetric Counter-drives (opposite signs with unequal magnitudes)
    # Rule 6.1 g: Spin on spot using Spin Disc for shared magnitude, then Pivot Fan for remainder.
    if cat == "asymmetric_counter":
        c_l = info["canonical_left"]
        c_r = info["canonical_right"]
        k = -c_r  # common magnitude for spin disc
        rem = c_l - k  # remainder magnitude for pivot fan

        # Phase 1 Spin direction & Phase 2 Pivot wheel
        if choice.left > 0 and choice.right < 0:
            spin_l, spin_r = k, -k
            piv_l, piv_r = (rem, 0) if choice.left > abs(choice.right) else (0, -rem)
        elif choice.left < 0 and choice.right > 0:
            spin_l, spin_r = -k, k
            piv_l, piv_r = (0, rem) if choice.right > abs(choice.left) else (-rem, 0)
        else:
            spin_l, spin_r = k, -k
            piv_l, piv_r = (rem, 0)

        n1 = max(1, int(round(num_steps * (k / float(k + rem)))))
        n2 = max(1, num_steps - n1)

        # Generate Phase 1 (spin on the spot)
        traj_spin = generate_trajectory(
            start_pose,
            MoveChoice(spin_l, spin_r),
            num_steps=n1,
            clamp_to_walls=clamp_to_walls,
        )
        mid_pose = Pose(x=traj_spin[-1].x, y=traj_spin[-1].y, theta=traj_spin[-1].theta)

        # Generate Phase 2 (pivot from intermediate pose)
        traj_pivot = generate_trajectory(
            mid_pose,
            MoveChoice(piv_l, piv_r),
            num_steps=n2,
            clamp_to_walls=clamp_to_walls,
        )

        combined: List[TrajectoryPoint] = []
        t_spin_end = k / float(k + rem)
        for i, pt in enumerate(traj_spin[:-1]):
            t = (i / float(n1)) * t_spin_end
            combined.append(TrajectoryPoint(x=pt.x, y=pt.y, theta=pt.theta, t=t))

        for i, pt in enumerate(traj_pivot):
            t = t_spin_end + (i / float(n2)) * (1.0 - t_spin_end)
            combined.append(TrajectoryPoint(x=pt.x, y=pt.y, theta=pt.theta, t=t))

        return combined

    # Fallback to straight
    total_dist = l_val * DRIVE_UNIT_MM
    return [
        TrajectoryPoint(
            x=x_0 + total_dist * (i / float(num_steps)) * f_x,
            y=y_0 + total_dist * (i / float(num_steps)) * f_y,
            theta=start_pose.theta,
            t=i / float(num_steps),
        )
        for i in range(num_steps + 1)
    ]
