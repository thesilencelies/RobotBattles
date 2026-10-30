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


def compute_movement_steps(left: int, right: int) -> List[Dict[str, Any]]:
    """
    Computes discrete movement steps on the 45-degree snapped grid.
    Rules:
    - If the absolute value of the remaining drive differs and the previous step was not a turn or one value is 0:
      Do a turn step. The side with less drive is kept still, and the robot rotates 45 degrees towards that side,
      keeping that edge where it is. Increment or decrement the side that has more drive towards 0.
    - Else:
      - If both have the same sign: take a forwards (or reverse) step.
        Move the robot one square in the direction it is facing (or opposite if negative).
        Increment or decrement both drive values towards 0.
      - If the signs of both are different: do a pivot step.
        Rotate the robot 45 degrees around its centre, in the direction determined by the signs
        (positive is forwards, negative is reverse). Increment or decrement both drive values towards 0.
    """
    steps: List[Dict[str, Any]] = []
    rem_l = int(left)
    rem_r = int(right)
    prev_was_turn = False

    while rem_l != 0 or rem_r != 0:
        if abs(rem_l) != abs(rem_r) and (not prev_was_turn or rem_l == 0 or rem_r == 0):
            prev_was_turn = True
            if abs(rem_l) > abs(rem_r):
                pinned = "right"
                rot_deg = 45.0 if rem_l > 0 else -45.0
                new_l = rem_l - 1 if rem_l > 0 else rem_l + 1
                new_r = rem_r
            else:
                pinned = "left"
                rot_deg = -45.0 if rem_r > 0 else 45.0
                new_r = rem_r - 1 if rem_r > 0 else rem_r + 1
                new_l = rem_l

            steps.append({
                "type": "turn",
                "pinned_side": pinned,
                "rotation_deg": rot_deg,
                "left_before": rem_l,
                "right_before": rem_r,
                "left_after": new_l,
                "right_after": new_r,
            })
            rem_l, rem_r = new_l, new_r
        else:
            prev_was_turn = False
            if (rem_l > 0 and rem_r > 0) or (rem_l < 0 and rem_r < 0):
                is_reverse = (rem_l < 0)
                new_l = rem_l + 1 if is_reverse else rem_l - 1
                new_r = rem_r + 1 if is_reverse else rem_r - 1
                steps.append({
                    "type": "reverse" if is_reverse else "forwards",
                    "direction": -1 if is_reverse else 1,
                    "left_before": rem_l,
                    "right_before": rem_r,
                    "left_after": new_l,
                    "right_after": new_r,
                })
                rem_l, rem_r = new_l, new_r
            else:
                rot_deg = 45.0 if rem_l > 0 else -45.0
                new_l = rem_l - 1 if rem_l > 0 else rem_l + 1
                new_r = rem_r + 1 if rem_r < 0 else rem_r - 1
                steps.append({
                    "type": "pivot",
                    "rotation_deg": rot_deg,
                    "left_before": rem_l,
                    "right_before": rem_r,
                    "left_after": new_l,
                    "right_after": new_r,
                })
                rem_l, rem_r = new_l, new_r

    return steps


def get_heading_grid_delta(theta_deg: float) -> Tuple[int, int]:
    """
    Returns the integer (dx, dy) grid direction for a heading in degrees,
    snapped to the nearest 45 degree increment.
    Heading 0 is North (-y), 90 is East (+x), 180 is South (+y), 270 is West (-x).
    """
    snapped = int(round((theta_deg % 360.0) / 45.0) * 45) % 360
    deltas = {
        0: (0, -1),
        45: (1, -1),
        90: (1, 0),
        135: (1, 1),
        180: (0, 1),
        225: (-1, 1),
        270: (-1, 0),
        315: (-1, -1),
    }
    return deltas.get(snapped, (0, -1))


def apply_movement_step(
    pose: Pose,
    step: Dict[str, Any],
    wheelbase: float = WHEELBASE_MM,
    grid_unit_mm: float = DRIVE_UNIT_MM,
    clamp_to_walls: bool = True,
) -> Pose:
    """
    Applies a single discrete movement step to a robot Pose.
    """
    stype = step["type"]
    new_pose = pose.clone()

    if stype in ("forwards", "reverse"):
        dx_g, dy_g = get_heading_grid_delta(new_pose.theta)
        direction = step.get("direction", 1 if stype == "forwards" else -1)
        dx_mm = dx_g * direction * grid_unit_mm
        dy_mm = dy_g * direction * grid_unit_mm
        new_pose.x += dx_mm
        new_pose.y += dy_mm

    elif stype == "pivot":
        rot_deg = step["rotation_deg"]
        new_pose.theta = (new_pose.theta + rot_deg) % 360.0

    elif stype == "turn":
        rot_deg = step["rotation_deg"]
        pinned = step["pinned_side"]
        rad = math.radians(rot_deg)
        r_rad = math.radians(new_pose.theta)
        rx = math.cos(r_rad)
        ry = math.sin(r_rad)
        pv_offset = (wheelbase / 2.0) if pinned == "right" else -(wheelbase / 2.0)
        pv_x = new_pose.x + pv_offset * rx
        pv_y = new_pose.y + pv_offset * ry
        v_x = new_pose.x - pv_x
        v_y = new_pose.y - pv_y
        cos_r = math.cos(rad)
        sin_r = math.sin(rad)
        new_pose.x = pv_x + (v_x * cos_r - v_y * sin_r)
        new_pose.y = pv_y + (v_x * sin_r + v_y * cos_r)
        new_pose.theta = (new_pose.theta + rot_deg) % 360.0

    if clamp_to_walls:
        new_pose.x = max(WALL_LEFT + MINIATURE_RADIUS, min(WALL_RIGHT - MINIATURE_RADIUS, new_pose.x))
        new_pose.y = max(WALL_TOP + MINIATURE_RADIUS, min(WALL_BOTTOM - MINIATURE_RADIUS, new_pose.y))

    return new_pose


def apply_joint_step(
    active_pose: Pose,
    passive_pose: Pose,
    step: Dict[str, Any],
    wheelbase: float = WHEELBASE_MM,
    grid_unit_mm: float = DRIVE_UNIT_MM,
    clamp_to_walls: bool = False,
) -> Tuple[Pose, Pose]:
    """
    Executes a movement step on active_pose, moving passive_pose along like it is stuck to it.
    - Forwards / Reverse: both robots translate by the same grid delta.
    - Pivot: both robots rotate about active robot's center by rotation_deg.
    - Turn: both robots rotate about active robot's pinned edge/wheel by rotation_deg.
    """
    stype = step["type"]
    new_active = active_pose.clone()
    new_passive = passive_pose.clone()

    if stype in ("forwards", "reverse"):
        dx_g, dy_g = get_heading_grid_delta(active_pose.theta)
        direction = step.get("direction", 1 if stype == "forwards" else -1)
        dx_mm = dx_g * direction * grid_unit_mm
        dy_mm = dy_g * direction * grid_unit_mm
        new_active.x += dx_mm
        new_active.y += dy_mm
        new_passive.x += dx_mm
        new_passive.y += dy_mm

    elif stype == "pivot":
        rot_deg = step["rotation_deg"]
        rad = math.radians(rot_deg)
        cos_r = math.cos(rad)
        sin_r = math.sin(rad)
        new_active.theta = (new_active.theta + rot_deg) % 360.0
        rel_x = passive_pose.x - active_pose.x
        rel_y = passive_pose.y - active_pose.y
        new_passive.x = active_pose.x + (rel_x * cos_r - rel_y * sin_r)
        new_passive.y = active_pose.y + (rel_x * sin_r + rel_y * cos_r)
        new_passive.theta = (new_passive.theta + rot_deg) % 360.0

    elif stype == "turn":
        rot_deg = step["rotation_deg"]
        pinned_side = step["pinned_side"]
        rad = math.radians(rot_deg)
        cos_r = math.cos(rad)
        sin_r = math.sin(rad)

        r_heading = math.radians(active_pose.theta)
        rx = math.cos(r_heading)
        ry = math.sin(r_heading)
        pivot_offset = (wheelbase / 2.0) if pinned_side == "right" else -(wheelbase / 2.0)
        pv_x = active_pose.x + pivot_offset * rx
        pv_y = active_pose.y + pivot_offset * ry

        v_ax = active_pose.x - pv_x
        v_ay = active_pose.y - pv_y
        new_active.x = pv_x + (v_ax * cos_r - v_ay * sin_r)
        new_active.y = pv_y + (v_ax * sin_r + v_ay * cos_r)
        new_active.theta = (new_active.theta + rot_deg) % 360.0

        v_px = passive_pose.x - pv_x
        v_py = passive_pose.y - pv_y
        new_passive.x = pv_x + (v_px * cos_r - v_py * sin_r)
        new_passive.y = pv_y + (v_px * sin_r + v_py * cos_r)
        new_passive.theta = (new_passive.theta + rot_deg) % 360.0

    if clamp_to_walls:
        new_active.x = max(WALL_LEFT + MINIATURE_RADIUS, min(WALL_RIGHT - MINIATURE_RADIUS, new_active.x))
        new_active.y = max(WALL_TOP + MINIATURE_RADIUS, min(WALL_BOTTOM - MINIATURE_RADIUS, new_active.y))
        new_passive.x = max(WALL_LEFT + MINIATURE_RADIUS, min(WALL_RIGHT - MINIATURE_RADIUS, new_passive.x))
        new_passive.y = max(WALL_TOP + MINIATURE_RADIUS, min(WALL_BOTTOM - MINIATURE_RADIUS, new_passive.y))

    return (new_active, new_passive)


def generate_trajectory(
    start_pose: Pose,
    choice: MoveChoice,
    num_steps: int = 30,
    clamp_to_walls: bool = True,
) -> List[TrajectoryPoint]:
    """
    Computes a discrete trajectory of TrajectoryPoints from t=0.0 to t=1.0
    for a chosen (Left, Right) drive pair along discrete grid steps.
    """
    l_val = int(choice.left)
    r_val = int(choice.right)

    steps = compute_movement_steps(l_val, r_val)
    if not steps:
        count = max(1, num_steps)
        return [
            TrajectoryPoint(x=start_pose.x, y=start_pose.y, theta=start_pose.theta, t=i / float(count))
            for i in range(count + 1)
        ]

    step_poses: List[Pose] = [start_pose.clone()]
    curr = start_pose.clone()
    for step in steps:
        curr = apply_movement_step(curr, step, clamp_to_walls=clamp_to_walls)
        step_poses.append(curr.clone())

    total_steps = len(steps)
    if num_steps <= 0 or num_steps == total_steps:
        points: List[TrajectoryPoint] = []
        for i, p in enumerate(step_poses):
            points.append(TrajectoryPoint(x=p.x, y=p.y, theta=p.theta, t=i / float(total_steps)))
        return points

    # Interpolate for smooth animation if num_steps > total_steps
    points: List[TrajectoryPoint] = []
    sub = max(1, num_steps // total_steps)
    for step_idx in range(total_steps):
        p_start = step_poses[step_idx]
        p_end = step_poses[step_idx + 1]
        for s in range(sub):
            alpha = s / float(sub)
            t_val = (step_idx + alpha) / float(total_steps)
            interp_x = p_start.x + (p_end.x - p_start.x) * alpha
            interp_y = p_start.y + (p_end.y - p_start.y) * alpha
            d_th = (p_end.theta - p_start.theta + 180.0) % 360.0 - 180.0
            interp_th = (p_start.theta + d_th * alpha) % 360.0
            points.append(TrajectoryPoint(x=interp_x, y=interp_y, theta=interp_th, t=t_val))

    final = step_poses[-1]
    points.append(TrajectoryPoint(x=final.x, y=final.y, theta=final.theta, t=1.0))
    return points
