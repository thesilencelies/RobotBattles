"""Automata AI logic and action table resolution for Vyper_flipper and Vyper_Spinner."""

from __future__ import annotations

import math
import random
from typing import Dict, Optional, Tuple

from .collision import normalize_angle_deg
from .types import MoveChoice, Pose, RobotState

AUTOMATA_TABLES = {
    "Vyper_flipper": [
        {"roll_min": 1, "roll_max": 1, "action": "Retreat"},
        {"roll_min": 2, "roll_max": 2, "action": "Face"},
        {"roll_min": 3, "roll_max": 6, "action": "Rush"},
    ],
    "Vyper_Spinner_Charged": [  # Spin counters >= 2
        {"roll_min": 1, "roll_max": 1, "action": "Retreat"},
        {"roll_min": 2, "roll_max": 2, "action": "Face"},
        {"roll_min": 3, "roll_max": 6, "action": "Rush"},
    ],
    "Vyper_Spinner_Uncharged": [  # Spin counters < 2
        {"roll_min": 1, "roll_max": 3, "action": "Retreat"},
        {"roll_min": 4, "roll_max": 5, "action": "Face"},
        {"roll_min": 6, "roll_max": 6, "action": "Rush"},
    ],
}


def roll_d6(fixed_roll: Optional[int] = None) -> int:
    if fixed_roll is not None and 1 <= fixed_roll <= 6:
        return fixed_roll
    return random.randint(1, 6)


def get_automaton_action(
    automaton_name: str,
    automaton: RobotState,
    roll: int,
) -> str:
    """
    Looks up action based on automaton type, weapon state, and d6 roll.
    """
    clean_name = automaton_name.replace(" ", "_")

    if "Spinner" in clean_name:
        # Check weapon spin counters
        spin_count = sum(automaton.weapon_spin_counters.values())
        table_key = "Vyper_Spinner_Charged" if spin_count >= 2 else "Vyper_Spinner_Uncharged"
    else:
        table_key = "Vyper_flipper"

    table = AUTOMATA_TABLES.get(table_key, AUTOMATA_TABLES["Vyper_flipper"])
    for row in table:
        if row["roll_min"] <= roll <= row["roll_max"]:
            return row["action"]
    return "Rush"


def compute_automaton_drive(
    automaton: RobotState,
    player: RobotState,
    action: str,
) -> MoveChoice:
    """
    Calculates the chosen (Left, Right) drive pair based on the selected action
    and the opponent's relative position.
    """
    d_l = automaton.left_drive_max
    d_r = automaton.right_drive_max

    # If robot has no drive, return 0, 0
    if d_l <= 0 and d_r <= 0:
        return MoveChoice(0, 0)

    # Vector from automaton to player
    dx = player.pose.x - automaton.pose.x
    dy = player.pose.y - automaton.pose.y

    # Heading of vector towards player (North is dy < 0)
    target_heading_deg = math.degrees(math.atan2(dx, -dy))
    rel_bearing_deg = normalize_angle_deg(target_heading_deg - automaton.pose.theta)

    if action == "Rush":
        # Drive at opponent at full speed
        if abs(rel_bearing_deg) <= 20.0:
            # Straight rush
            return MoveChoice(left=d_l, right=d_r)
        elif 20.0 < rel_bearing_deg <= 60.0:
            # Curve right towards opponent
            return MoveChoice(left=d_l, right=max(0, d_r - 2))
        elif -60.0 <= rel_bearing_deg < -20.0:
            # Curve left towards opponent
            return MoveChoice(left=max(0, d_l - 2), right=d_r)
        elif rel_bearing_deg > 60.0:
            # Sharp clockwise turn
            return MoveChoice(left=d_l, right=-min(d_r, 2))
        else:
            # Sharp counter-clockwise turn
            return MoveChoice(left=-min(d_l, 2), right=d_r)

    elif action == "Face":
        # Rotate on the spot to face opponent
        if abs(rel_bearing_deg) <= 10.0:
            return MoveChoice(0, 0)
        elif rel_bearing_deg > 0:
            turn_amt = min(d_l, d_r, 2)
            return MoveChoice(left=turn_amt, right=-turn_amt)
        else:
            turn_amt = min(d_l, d_r, 2)
            return MoveChoice(left=-turn_amt, right=turn_amt)

    elif action == "Retreat":
        # Face opponent and move backwards 1 step
        if abs(rel_bearing_deg) > 35.0:
            # First orient to face them
            turn_amt = min(d_l, d_r, 2)
            if rel_bearing_deg > 0:
                return MoveChoice(left=turn_amt, right=-turn_amt)
            else:
                return MoveChoice(left=-turn_amt, right=turn_amt)
        else:
            # Reverse away 1 step
            step_l = -1 if d_l > 0 else 0
            step_r = -1 if d_r > 0 else 0
            return MoveChoice(left=step_l, right=step_r)

    return MoveChoice(0, 0)
