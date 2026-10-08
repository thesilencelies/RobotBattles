"""Template-based movement and trajectory generation for Robot Battles."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from .field import WALL_BOTTOM, WALL_LEFT, WALL_RIGHT, WALL_TOP
from .types import MoveChoice, Pose, TrajectoryPoint

# Distance in mm per 1 drive unit on the straight template
DRIVE_UNIT_MM = 40.0
WHEELBASE_MM = 65.0
MINIATURE_RADIUS = 35.0


def list_template_options(left_max: int, right_max: int) -> List[Dict[str, Any]]:
    """
    Returns valid discrete movement template tracks available to a robot
    with the given active left and right drive counts.
    """
    options: List[Dict[str, Any]] = [
        {"name": "Stop (0, 0)", "left": 0, "right": 0, "category": "stop", "icon": "⏹️"}
    ]

    # 1. Straight tracks: (1, 1) .. (k, k)
    max_straight = min(left_max, right_max)
    for k in range(1, max_straight + 1):
        options.append({
            "name": f"Straight {k} ({k}, {k})",
            "left": k,
            "right": k,
            "category": "straight",
            "icon": "⬆️",
        })

    # Reverse: (-1, -1) if both have drive
    if left_max >= 1 and right_max >= 1:
        options.append({
            "name": "Reverse 1 (-1, -1)",
            "left": -1,
            "right": -1,
            "category": "reverse",
            "icon": "⬇️",
        })

    # 2. Curve tracks from template: (2, 1), (3, 1), (4, 2), (5, 3) and mirrored
    curve_pairs = [
        (2, 1, "Curve Right (2, 1)"),
        (3, 1, "Curve Right (3, 1)"),
        (4, 2, "Curve Right (4, 2)"),
        (5, 3, "Curve Right (5, 3)"),
        (1, 2, "Curve Left (1, 2)"),
        (1, 3, "Curve Left (1, 3)"),
        (2, 4, "Curve Left (2, 4)"),
        (3, 5, "Curve Left (3, 5)"),
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

    # 3. Pivot tracks: (1, 0) .. (4, 0) and (0, 1) .. (0, 4)
    for k in range(1, left_max + 1):
        if k <= 4:
            options.append({
                "name": f"Pivot Right ({k}, 0)",
                "left": k,
                "right": 0,
                "category": "pivot",
                "icon": "🔃",
            })
    for k in range(1, right_max + 1):
        if k <= 4:
            options.append({
                "name": f"Pivot Left (0, {k})",
                "left": 0,
                "right": k,
                "category": "pivot",
                "icon": "🔄",
            })

    # 4. Spin-on-spot tracks: (1, -1), (2, -2), (-1, 1), (-2, 2)
    max_spin = min(left_max, right_max)
    for k in range(1, min(2, max_spin) + 1):
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

    return options


def generate_trajectory(
    start_pose: Pose,
    choice: MoveChoice,
    num_steps: int = 30,
    clamp_to_walls: bool = True,
) -> List[TrajectoryPoint]:
    """
    Computes a discrete trajectory of TrajectoryPoints from t=0.0 to t=1.0
    for a chosen (Left, Right) drive pair along the corresponding template track.
    The robot starts with its front at the black line on the template and ends
    with its front at the corresponding line.
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

    points: List[TrajectoryPoint] = []

    # Case 1: Stationary (0, 0)
    if abs(l_val) < 1e-6 and abs(r_val) < 1e-6:
        for i in range(num_steps + 1):
            t = i / float(num_steps)
            points.append(TrajectoryPoint(x=x_0, y=y_0, theta=start_pose.theta, t=t))
        return points

    # Case 2: Straight translation (L == R)
    if abs(l_val - r_val) < 1e-6:
        total_dist = l_val * DRIVE_UNIT_MM
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
    # Circle template: 45 deg per 1 drive unit
    if abs(l_val + r_val) < 1e-6:
        delta_deg = l_val * 45.0  # Positive L spins clockwise
        for i in range(num_steps + 1):
            t = i / float(num_steps)
            curr_theta = (start_pose.theta + t * delta_deg) % 360.0
            points.append(TrajectoryPoint(x=x_0, y=y_0, theta=curr_theta, t=t))
        return points

    # Case 4: Pivot on one wheel (one side is 0)
    # Semicircle template: sectors are 22.5 deg per 1 unit
    if abs(r_val) < 1e-6:
        # Left wheel driving, pivoting around right wheel (turning right / clockwise)
        turn_angle_deg = l_val * 22.5
        pivot_offset = WHEELBASE_MM / 2.0
        # Pivot point is to the right of center: (x_0 + pivot_offset * r_x, y_0 + pivot_offset * r_y)
        pv_x = x_0 + pivot_offset * r_x
        pv_y = y_0 + pivot_offset * r_y
        for i in range(num_steps + 1):
            t = i / float(num_steps)
            rot_rad = math.radians(t * turn_angle_deg)
            # Center rotates around pivot point
            # Vector from pivot to center: (-pivot_offset * r_x, -pivot_offset * r_y)
            # Rotated by rot_rad (clockwise)
            cos_a = math.cos(rot_rad)
            sin_a = math.sin(rot_rad)
            vx = -pivot_offset * r_x
            vy = -pivot_offset * r_y
            rot_vx = vx * cos_a - vy * sin_a
            rot_vy = vx * sin_a + vy * cos_a
            px = pv_x + rot_vx
            py = pv_y + rot_vy
            curr_theta = (start_pose.theta + t * turn_angle_deg) % 360.0
            if clamp_to_walls:
                px = max(WALL_LEFT + MINIATURE_RADIUS, min(WALL_RIGHT - MINIATURE_RADIUS, px))
                py = max(WALL_TOP + MINIATURE_RADIUS, min(WALL_BOTTOM - MINIATURE_RADIUS, py))
            points.append(TrajectoryPoint(x=px, y=py, theta=curr_theta, t=t))
        return points

    if abs(l_val) < 1e-6:
        # Right wheel driving, pivoting around left wheel (turning left / counter-clockwise)
        turn_angle_deg = -r_val * 22.5
        pivot_offset = WHEELBASE_MM / 2.0
        pv_x = x_0 - pivot_offset * r_x
        pv_y = y_0 - pivot_offset * r_y
        for i in range(num_steps + 1):
            t = i / float(num_steps)
            rot_rad = math.radians(t * turn_angle_deg)
            cos_a = math.cos(rot_rad)
            sin_a = math.sin(rot_rad)
            vx = pivot_offset * r_x
            vy = pivot_offset * r_y
            rot_vx = vx * cos_a - vy * sin_a
            rot_vy = vx * sin_a + vy * cos_a
            px = pv_x + rot_vx
            py = pv_y + rot_vy
            curr_theta = (start_pose.theta + t * turn_angle_deg) % 360.0
            if clamp_to_walls:
                px = max(WALL_LEFT + MINIATURE_RADIUS, min(WALL_RIGHT - MINIATURE_RADIUS, px))
                py = max(WALL_TOP + MINIATURE_RADIUS, min(WALL_BOTTOM - MINIATURE_RADIUS, py))
            points.append(TrajectoryPoint(x=px, y=py, theta=curr_theta, t=t))
        return points

    # Case 5: Curved Arc Template (L != R, both non-zero)
    # Calibrated to the curve tracks: (2, 1) -> 30 deg, (3, 1), (4, 2), (5, 3) -> 55 deg
    pair_angles = {
        (2, 1): 30.0,
        (3, 1): 55.0,
        (4, 2): 55.0,
        (5, 3): 55.0,
        (1, 2): -30.0,
        (1, 3): -55.0,
        (2, 4): -55.0,
        (3, 5): -55.0,
    }
    int_pair = (int(round(l_val)), int(round(r_val)))
    if int_pair in pair_angles:
        total_angle_deg = pair_angles[int_pair]
    else:
        # Fallback proportional formula
        total_angle_deg = ((l_val - r_val) / WHEELBASE_MM) * DRIVE_UNIT_MM * (180.0 / math.pi)

    avg_dist = ((l_val + r_val) / 2.0) * DRIVE_UNIT_MM
    total_angle_rad = math.radians(total_angle_deg)

    for i in range(num_steps + 1):
        t = i / float(num_steps)
        psi_t = total_angle_rad * t
        curr_theta = (start_pose.theta + math.degrees(psi_t)) % 360.0

        if abs(psi_t) < 1e-4:
            delta_f = avg_dist * t
            delta_r = 0.0
        else:
            # Arc radius
            r_c = (avg_dist * t) / psi_t
            delta_f = r_c * math.sin(psi_t)
            delta_r = r_c * (1.0 - math.cos(psi_t))

        px = x_0 + delta_f * f_x + delta_r * r_x
        py = y_0 + delta_f * f_y + delta_r * r_y

        if clamp_to_walls:
            px = max(WALL_LEFT + MINIATURE_RADIUS, min(WALL_RIGHT - MINIATURE_RADIUS, px))
            py = max(WALL_TOP + MINIATURE_RADIUS, min(WALL_BOTTOM - MINIATURE_RADIUS, py))

        points.append(TrajectoryPoint(x=px, y=py, theta=curr_theta, t=t))

    return points
