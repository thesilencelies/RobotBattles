"""Differential drive kinematics and trajectory generation for Robot Battles."""

from __future__ import annotations

import math
from typing import List, Tuple

from .field import WALL_BOTTOM, WALL_LEFT, WALL_RIGHT, WALL_TOP
from .types import MoveChoice, Pose, TrajectoryPoint

DRIVE_UNIT_MM = 35.0   # Displacement in mm per 1 drive unit
WHEELBASE_MM = 60.0    # Distance between left and right wheels
MINIATURE_RADIUS = 35.0 # Effective collision radius for wall checks


def generate_trajectory(
    start_pose: Pose,
    choice: MoveChoice,
    num_steps: int = 25,
    clamp_to_walls: bool = True,
) -> List[TrajectoryPoint]:
    """
    Computes a discrete trajectory of TrajectoryPoints from t=0.0 to t=1.0
    for a given Left/Right drive choice.
    """
    l_val = float(choice.left)
    r_val = float(choice.right)

    d_l = l_val * DRIVE_UNIT_MM
    d_r = r_val * DRIVE_UNIT_MM

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

    # Case 2: Pure Straight Translation (L == R)
    if abs(l_val - r_val) < 1e-6:
        dist = d_l
        for i in range(num_steps + 1):
            t = i / float(num_steps)
            curr_dist = dist * t
            px = x_0 + curr_dist * f_x
            py = y_0 + curr_dist * f_y

            if clamp_to_walls:
                px = max(WALL_LEFT + MINIATURE_RADIUS, min(WALL_RIGHT - MINIATURE_RADIUS, px))
                py = max(WALL_TOP + MINIATURE_RADIUS, min(WALL_BOTTOM - MINIATURE_RADIUS, py))

            points.append(TrajectoryPoint(x=px, y=py, theta=start_pose.theta, t=t))
        return points

    # Case 3: Pure Pivot On The Spot (L == -R)
    if abs(l_val + r_val) < 1e-6:
        # Rotation angle delta_theta = (d_l - d_r) / W (positive turns clockwise)
        psi_total_rad = (d_l - d_r) / WHEELBASE_MM
        psi_total_deg = math.degrees(psi_total_rad)

        for i in range(num_steps + 1):
            t = i / float(num_steps)
            curr_theta = (start_pose.theta + t * psi_total_deg) % 360.0
            points.append(TrajectoryPoint(x=x_0, y=y_0, theta=curr_theta, t=t))
        return points

    # Case 4: General Differential Drive Turning Arc (L != R)
    # Total turn angle psi (positive = clockwise, d_l > d_r)
    psi_total_rad = (d_l - d_r) / WHEELBASE_MM
    v_total = (d_l + d_r) / 2.0

    for i in range(num_steps + 1):
        t = i / float(num_steps)
        psi_t = t * psi_total_rad
        curr_theta = (start_pose.theta + math.degrees(psi_t)) % 360.0

        if abs(psi_t) < 1e-5:
            delta_f = v_total * t
            delta_r = 0.0
        else:
            r_c = (v_total * t) / psi_t
            delta_f = r_c * math.sin(psi_t)
            delta_r = r_c * (1.0 - math.cos(psi_t))

        px = x_0 + delta_f * f_x + delta_r * r_x
        py = y_0 + delta_f * f_y + delta_r * r_y

        if clamp_to_walls:
            px = max(WALL_LEFT + MINIATURE_RADIUS, min(WALL_RIGHT - MINIATURE_RADIUS, px))
            py = max(WALL_TOP + MINIATURE_RADIUS, min(WALL_BOTTOM - MINIATURE_RADIUS, py))

        points.append(TrajectoryPoint(x=px, y=py, theta=curr_theta, t=t))

    return points
