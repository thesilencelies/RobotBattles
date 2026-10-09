"""Automata AI logic and action table resolution for combat robotics automata."""

from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional, Tuple

from .collision import normalize_angle_deg
from .combat import parse_weapon_spin_and_damage
from .movement import generate_trajectory, list_template_options
from .types import MoveChoice, Pose, RobotState

# Archetype tables defined in automata/Action_tables.md
ARCHETYPE_TABLES: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
    "Full Rush": {
        "default": [
            {"roll_min": 1, "roll_max": 1, "action": "Retreat"},
            {"roll_min": 2, "roll_max": 2, "action": "Face"},
            {"roll_min": 3, "roll_max": 6, "action": "Rush"},
        ],
    },
    "Spin Up": {
        "charged": [  # Spin counters >= 2
            {"roll_min": 1, "roll_max": 1, "action": "Retreat"},
            {"roll_min": 2, "roll_max": 2, "action": "Face"},
            {"roll_min": 3, "roll_max": 6, "action": "Rush"},
        ],
        "uncharged": [  # Spin counters < 2
            {"roll_min": 1, "roll_max": 3, "action": "Retreat"},
            {"roll_min": 4, "roll_max": 5, "action": "Face"},
            {"roll_min": 6, "roll_max": 6, "action": "Rush"},
        ],
    },
    "Balanced": {
        "full_spin": [  # Weapon is at full spin
            {"roll_min": 1, "roll_max": 1, "action": "Retreat"},
            {"roll_min": 2, "roll_max": 3, "action": "Face"},
            {"roll_min": 4, "roll_max": 6, "action": "Rush"},
        ],
        "sub_spin": [  # Weapon is not at full spin
            {"roll_min": 1, "roll_max": 2, "action": "Retreat"},
            {"roll_min": 3, "roll_max": 4, "action": "Face"},
            {"roll_min": 5, "roll_max": 6, "action": "Rush"},
        ],
    },
}

# Per automata allocation mapping from Action_tables.md
AUTOMATA_ARCHETYPES: Dict[str, str] = {
    "vyper_flipper": "Full Rush",
    "vyper_spinner": "Spin Up",
    "beater_wide": "Balanced",
    "nightwing_wide": "Balanced",
    "chonk": "Spin Up",
}

# Backward compatibility alias
AUTOMATA_TABLES = {
    "Vyper_flipper": ARCHETYPE_TABLES["Full Rush"]["default"],
    "Vyper_Spinner_Charged": ARCHETYPE_TABLES["Spin Up"]["charged"],
    "Vyper_Spinner_Uncharged": ARCHETYPE_TABLES["Spin Up"]["uncharged"],
    "Balanced_Full": ARCHETYPE_TABLES["Balanced"]["full_spin"],
    "Balanced_Sub": ARCHETYPE_TABLES["Balanced"]["sub_spin"],
}


def roll_d6(fixed_roll: Optional[int] = None) -> int:
    if fixed_roll is not None and 1 <= fixed_roll <= 6:
        return fixed_roll
    return random.randint(1, 6)


def get_automaton_archetype(automaton_name: str) -> str:
    clean = automaton_name.strip().lower().replace(" ", "_").replace(".csv", "")
    for bot_key, arch in AUTOMATA_ARCHETYPES.items():
        if bot_key in clean:
            return arch
    # Fallback heuristics
    if "flipper" in clean or "rush" in clean:
        return "Full Rush"
    if "spinner" in clean or "chonk" in clean:
        return "Spin Up"
    if "beater" in clean or "nightwing" in clean or "balanced" in clean:
        return "Balanced"
    return "Full Rush"


def is_weapon_at_full_spin(automaton: RobotState) -> bool:
    """
    Returns True if any active spin weapon on the automaton has reached max spin.
    """
    for cid, comp in automaton.components.items():
        if comp.card_type == "weapon" and not comp.is_destroyed:
            _, max_spin, _, _ = parse_weapon_spin_and_damage(comp.outputs, comp.keywords, comp.text)
            if max_spin > 0:
                current_spin = automaton.weapon_spin_counters.get(cid, 0)
                if current_spin >= max_spin:
                    return True
    return False


def get_automaton_action(
    automaton_name: str,
    automaton: RobotState,
    roll: int,
) -> str:
    """
    Looks up action based on automaton archetype, weapon spin state, and d6 roll.
    """
    archetype = get_automaton_archetype(automaton_name)
    total_spin = sum(automaton.weapon_spin_counters.values())

    if archetype == "Full Rush":
        table = ARCHETYPE_TABLES["Full Rush"]["default"]
    elif archetype == "Spin Up":
        table = (
            ARCHETYPE_TABLES["Spin Up"]["charged"]
            if total_spin >= 2
            else ARCHETYPE_TABLES["Spin Up"]["uncharged"]
        )
    elif archetype == "Balanced":
        at_full = is_weapon_at_full_spin(automaton)
        # Fallback if dummy/test state has no components registered
        if not automaton.components and total_spin >= 3:
            at_full = True
        table = (
            ARCHETYPE_TABLES["Balanced"]["full_spin"]
            if at_full
            else ARCHETYPE_TABLES["Balanced"]["sub_spin"]
        )
    else:
        table = ARCHETYPE_TABLES["Full Rush"]["default"]

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
    Evaluates available movement template options to execute the chosen action
    (Rush, Face, Retreat) considering the opponent's current position.
    """
    d_l = automaton.left_drive_max
    d_r = automaton.right_drive_max

    if d_l <= 0 and d_r <= 0:
        return MoveChoice(0, 0)

    options = list_template_options(d_l, d_r)
    if not options:
        return MoveChoice(0, 0)

    # Opponent position and relative bearing
    dx = player.pose.x - automaton.pose.x
    dy = player.pose.y - automaton.pose.y
    target_heading_deg = math.degrees(math.atan2(dx, -dy))
    current_bearing_deg = normalize_angle_deg(target_heading_deg - automaton.pose.theta)

    if action == "Rush":
        # Maximum speed closing distance to opponent
        # Filter for forward movement options (straight, curve)
        forward_opts = [o for o in options if o["category"] in ("straight", "curve") and o["left"] > 0 and o["right"] > 0]
        if not forward_opts:
            forward_opts = [o for o in options if o["left"] > 0 or o["right"] > 0]
        if not forward_opts:
            return MoveChoice(0, 0)

        best_opt = forward_opts[0]
        min_dist = float("inf")

        for opt in forward_opts:
            choice = MoveChoice(opt["left"], opt["right"])
            traj = generate_trajectory(automaton.pose, choice, num_steps=5, clamp_to_walls=True)
            end_pose = traj[-1]
            dist_to_opp = math.hypot(player.pose.x - end_pose.x, player.pose.y - end_pose.y)
            if dist_to_opp < min_dist:
                min_dist = dist_to_opp
                best_opt = opt

        return MoveChoice(best_opt["left"], best_opt["right"])

    elif action == "Face":
        # Rotate on the spot to face opponent
        # If already facing opponent within 15 deg, stop or slight adjust
        if abs(current_bearing_deg) <= 15.0:
            return MoveChoice(0, 0)

        turn_opts = [o for o in options if o["category"] in ("spin", "pivot")]
        if not turn_opts:
            return MoveChoice(0, 0)

        best_opt = turn_opts[0]
        min_bearing_diff = float("inf")

        for opt in turn_opts:
            choice = MoveChoice(opt["left"], opt["right"])
            traj = generate_trajectory(automaton.pose, choice, num_steps=5, clamp_to_walls=True)
            end_pose = traj[-1]
            end_bearing = abs(normalize_angle_deg(target_heading_deg - end_pose.theta))
            if end_bearing < min_bearing_diff:
                min_bearing_diff = end_bearing
                best_opt = opt

        return MoveChoice(best_opt["left"], best_opt["right"])

    elif action == "Retreat":
        # Face opponent and move backwards 1 step
        if abs(current_bearing_deg) <= 35.0:
            # Already facing opponent, reverse 1 step if available
            rev_opts = [o for o in options if o["category"] == "reverse"]
            if rev_opts:
                return MoveChoice(-1, -1)
            # If no reverse, pivot away
            return MoveChoice(0, 0)
        else:
            # Turn to face them first
            turn_opts = [o for o in options if o["category"] in ("spin", "pivot")]
            if not turn_opts:
                return MoveChoice(0, 0)
            best_opt = turn_opts[0]
            min_bearing = float("inf")
            for opt in turn_opts:
                choice = MoveChoice(opt["left"], opt["right"])
                traj = generate_trajectory(automaton.pose, choice, num_steps=5, clamp_to_walls=True)
                diff = abs(normalize_angle_deg(target_heading_deg - traj[-1].theta))
                if diff < min_bearing:
                    min_bearing = diff
                    best_opt = opt
            return MoveChoice(best_opt["left"], best_opt["right"])

    return MoveChoice(0, 0)
