"""Automata AI logic and action table resolution for combat robotics automata."""

from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional, Tuple

from .collision import normalize_angle_deg
from .combat import parse_weapon_spin_and_damage
from .field import WALL_BOTTOM, WALL_LEFT, WALL_RIGHT, WALL_TOP
from .movement import (
    MINIATURE_RADIUS,
    generate_trajectory,
    get_action_card,
    list_template_options,
    normalize_action_code,
    synthesize_cards_from_drive,
)
from .types import MoveChoice, Pose, RobotState

# Archetype tables defined in automata/Action_tables.md
ARCHETYPE_TABLES: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
    "Full Rush": {
        "default": [
            {"roll_min": 1, "roll_max": 1, "action": "Retreat"},
            {"roll_min": 2, "roll_max": 2, "action": "Face"},
            {"roll_min": 3, "roll_max": 3, "action": "Evade"},
            {"roll_min": 4, "roll_max": 6, "action": "Rush"},
        ],
    },
    "Spin Up": {
        "charged": [  # Spin counters >= 2
            {"roll_min": 1, "roll_max": 1, "action": "Face"},
            {"roll_min": 2, "roll_max": 2, "action": "Evade"},
            {"roll_min": 3, "roll_max": 6, "action": "Rush"},
        ],
        "uncharged": [  # Spin counters < 2
            {"roll_min": 1, "roll_max": 2, "action": "Retreat"},
            {"roll_min": 3, "roll_max": 3, "action": "Face"},
            {"roll_min": 4, "roll_max": 5, "action": "Evade"},
            {"roll_min": 6, "roll_max": 6, "action": "Rush"},
        ],
    },
    "Balanced": {
        "full_spin": [  # Weapon is at full spin
            {"roll_min": 1, "roll_max": 1, "action": "Retreat"},
            {"roll_min": 2, "roll_max": 2, "action": "Face"},
            {"roll_min": 3, "roll_max": 3, "action": "Evade"},
            {"roll_min": 4, "roll_max": 6, "action": "Rush"},
        ],
        "sub_spin": [  # Weapon is not at full spin
            {"roll_min": 1, "roll_max": 1, "action": "Retreat"},
            {"roll_min": 2, "roll_max": 3, "action": "Evade"},
            {"roll_min": 4, "roll_max": 4, "action": "Face"},
            {"roll_min": 5, "roll_max": 6, "action": "Rush"},
        ],
    },
    "Flank": {
        "target_not_facing": [  # Opposing robot is not facing toward it
            {"roll_min": 1, "roll_max": 1, "action": "Retreat"},
            {"roll_min": 2, "roll_max": 3, "action": "Evade"},
            {"roll_min": 4, "roll_max": 6, "action": "Rush"},
        ],
        "target_facing": [  # Opposing robot is facing toward it
            {"roll_min": 1, "roll_max": 1, "action": "Retreat"},
            {"roll_min": 2, "roll_max": 4, "action": "Evade"},
            {"roll_min": 5, "roll_max": 5, "action": "Face"},
            {"roll_min": 6, "roll_max": 6, "action": "Rush"},
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
    "billet_hammersaw": "Flank",
    "sparrow_crusher": "Flank",
}

# Backward compatibility alias
AUTOMATA_TABLES = {
    "Vyper_flipper": ARCHETYPE_TABLES["Full Rush"]["default"],
    "Vyper_Spinner_Charged": ARCHETYPE_TABLES["Spin Up"]["charged"],
    "Vyper_Spinner_Uncharged": ARCHETYPE_TABLES["Spin Up"]["uncharged"],
    "Balanced_Full": ARCHETYPE_TABLES["Balanced"]["full_spin"],
    "Balanced_Sub": ARCHETYPE_TABLES["Balanced"]["sub_spin"],
    "Flank_Facing": ARCHETYPE_TABLES["Flank"]["target_facing"],
    "Flank_Not_Facing": ARCHETYPE_TABLES["Flank"]["target_not_facing"],
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
    if "hammersaw" in clean or "billet" in clean or "sparrow" in clean or "crusher" in clean or "flank" in clean:
        return "Flank"
    if "flipper" in clean or "rush" in clean:
        return "Full Rush"
    if "spinner" in clean or "chonk" in clean:
        return "Spin Up"
    if "beater" in clean or "nightwing" in clean or "balanced" in clean:
        return "Balanced"
    return "Full Rush"


def is_robot_facing_target(observer_pose: Pose, target_pose: Pose, threshold_deg: float = 45.0) -> bool:
    """Returns True if target_pose lies within +/- threshold_deg of observer's heading."""
    dx = target_pose.x - observer_pose.x
    dy = target_pose.y - observer_pose.y
    target_heading = math.degrees(math.atan2(dx, -dy))
    bearing = abs(normalize_angle_deg(target_heading - observer_pose.theta))
    return bearing <= threshold_deg


def is_automaton_at_full_spin(automaton: RobotState) -> bool:
    """
    Automata consider themselves at full spin unless they have an active weapon
    with spin up that is not at max spin.
    """
    if not automaton.components:
        total_spin = sum(automaton.weapon_spin_counters.values())
        return total_spin >= 3

    for cid, comp in automaton.components.items():
        if comp.card_type == "weapon" and not comp.is_destroyed and comp.is_active:
            if automaton.is_inverted and not comp.is_invertible:
                continue
            _, max_spin, _, _ = parse_weapon_spin_and_damage(comp.outputs, comp.keywords, comp.text)
            if max_spin > 0:
                current_spin = automaton.weapon_spin_counters.get(cid, 0)
                if current_spin < max_spin:
                    return False
    return True


is_weapon_at_full_spin = is_automaton_at_full_spin


def get_automaton_action(
    automaton_name: str,
    automaton: RobotState,
    roll: int,
    opponent: Optional[RobotState] = None,
) -> str:
    """
    Looks up action based on automaton archetype, weapon spin state, and d6 roll.
    For Flank archetype, evaluates whether the opposing robot is facing toward it (+/- 45 deg).
    Automata consider themselves at full spin unless they have an active weapon
    with spin up that is not at max spin.
    """
    archetype = get_automaton_archetype(automaton_name)
    total_spin = sum(automaton.weapon_spin_counters.values())
    at_full = is_automaton_at_full_spin(automaton) if automaton.components else (total_spin >= 3)

    if archetype == "Full Rush":
        table = ARCHETYPE_TABLES["Full Rush"]["default"]
    elif archetype == "Spin Up":
        is_charged = (is_automaton_at_full_spin(automaton) if automaton.components else (total_spin >= 2)) or (total_spin >= 2)
        table = (
            ARCHETYPE_TABLES["Spin Up"]["charged"]
            if is_charged
            else ARCHETYPE_TABLES["Spin Up"]["uncharged"]
        )
    elif archetype == "Balanced":
        table = (
            ARCHETYPE_TABLES["Balanced"]["full_spin"]
            if at_full
            else ARCHETYPE_TABLES["Balanced"]["sub_spin"]
        )
    elif archetype == "Flank":
        is_facing = is_robot_facing_target(opponent.pose, automaton.pose, 45.0) if opponent is not None else True
        table = (
            ARCHETYPE_TABLES["Flank"]["target_facing"]
            if is_facing
            else ARCHETYPE_TABLES["Flank"]["target_not_facing"]
        )
    else:
        table = ARCHETYPE_TABLES["Full Rush"]["default"]

    for row in table:
        if row["roll_min"] <= roll <= row["roll_max"]:
            return row["action"]
    return "Rush"


def _compute_direction_clearance(x: float, y: float, heading_deg: float) -> float:
    """Calculates clearance distance (in mm) from (x, y) along heading_deg to the arena walls."""
    rad = math.radians(heading_deg)
    vx = math.sin(rad)
    vy = -math.cos(rad)

    min_dist = float("inf")
    left_bound = WALL_LEFT + MINIATURE_RADIUS
    if vx < -1e-6:
        d = (left_bound - x) / vx
        if d > 0:
            min_dist = min(min_dist, d)
    right_bound = WALL_RIGHT - MINIATURE_RADIUS
    if vx > 1e-6:
        d = (right_bound - x) / vx
        if d > 0:
            min_dist = min(min_dist, d)
    top_bound = WALL_TOP + MINIATURE_RADIUS
    if vy < -1e-6:
        d = (top_bound - y) / vy
        if d > 0:
            min_dist = min(min_dist, d)
    bottom_bound = WALL_BOTTOM - MINIATURE_RADIUS
    if vy > 1e-6:
        d = (bottom_bound - y) / vy
        if d > 0:
            min_dist = min(min_dist, d)

    return min_dist


def compute_automaton_drive(
    automaton: RobotState,
    player: RobotState,
    action: str,
    evade_direction: Optional[str] = None,
) -> MoveChoice:
    """
    Calculates the chosen (Left, Right) drive pair and synthesized Action Cards
    based on the selected action and the opponent's relative position.
    """
    d_l = automaton.left_drive_max
    d_r = automaton.right_drive_max

    # Guaranteed base drive of 1 if unpowered/damaged
    eff_l = max(1, d_l)
    eff_r = max(1, d_r)

    # Vector from automaton to player
    dx = player.pose.x - automaton.pose.x
    dy = player.pose.y - automaton.pose.y

    target_heading_deg = math.degrees(math.atan2(dx, -dy))
    rel_bearing_deg = normalize_angle_deg(target_heading_deg - automaton.pose.theta)

    if action == "Rush":
        if abs(rel_bearing_deg) <= 20.0:
            c = MoveChoice(left=d_l, right=d_r)
        elif 20.0 < rel_bearing_deg <= 60.0:
            c = MoveChoice(left=d_l, right=max(0, d_r - 2))
        elif -60.0 <= rel_bearing_deg < -20.0:
            c = MoveChoice(left=max(0, d_l - 2), right=d_r)
        elif rel_bearing_deg > 60.0:
            c = MoveChoice(left=d_l, right=-min(d_r, 2))
        else:
            c = MoveChoice(left=-min(d_l, 2), right=d_r)

    elif action == "Face":
        if abs(rel_bearing_deg) <= 10.0:
            c = MoveChoice(0, 0)
        elif rel_bearing_deg > 0:
            turn_amt = min(eff_l, eff_r, 2)
            c = MoveChoice(left=turn_amt, right=-turn_amt)
        else:
            turn_amt = min(eff_l, eff_r, 2)
            c = MoveChoice(left=-turn_amt, right=turn_amt)

    elif action == "Retreat":
        if abs(rel_bearing_deg) > 35.0:
            turn_amt = min(eff_l, eff_r, 2)
            if rel_bearing_deg > 0:
                c = MoveChoice(left=turn_amt, right=-turn_amt)
            else:
                c = MoveChoice(left=-turn_amt, right=turn_amt)
        else:
            step_l = -1 if eff_l > 0 else 0
            step_r = -1 if eff_r > 0 else 0
            c = MoveChoice(left=step_l, right=step_r)

    elif action == "Evade":
        perp_right = normalize_angle_deg(target_heading_deg + 90.0)
        perp_left = normalize_angle_deg(target_heading_deg - 90.0)
        dist_right = _compute_direction_clearance(automaton.pose.x, automaton.pose.y, perp_right)
        dist_left = _compute_direction_clearance(automaton.pose.x, automaton.pose.y, perp_left)
        if dist_right >= 80.0 and dist_left >= 80.0:
            chosen_hdg = perp_right if evade_direction == "right" else (perp_left if evade_direction == "left" else random.choice([perp_right, perp_left]))
        elif dist_left >= 80.0:
            chosen_hdg = perp_left
        else:
            chosen_hdg = perp_right if dist_right >= dist_left else perp_left

        evade_bearing = normalize_angle_deg(chosen_hdg - automaton.pose.theta)
        if abs(evade_bearing) <= 20.0:
            c = MoveChoice(left=d_l, right=d_r)
        elif evade_bearing > 0:
            c = MoveChoice(left=d_l, right=-min(d_r, 2))
        else:
            c = MoveChoice(left=-min(d_l, 2), right=d_r)
    else:
        c = MoveChoice(0, 0)

    c.cards = synthesize_cards_from_drive(c.left, c.right)
    return c


def compute_automaton_action_plan(
    automaton: RobotState,
    player: RobotState,
    action: str,
    evade_direction: Optional[str] = None,
) -> MoveChoice:
    """
    Selects 3 movement Action Cards to execute the chosen automaton action
    (Rush, Face, Retreat, Evade) considering the opponent's current position.
    """
    return compute_automaton_drive(automaton, player, action, evade_direction=evade_direction)

