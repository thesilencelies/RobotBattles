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
    apply_movement_step,
    generate_trajectory,
    get_action_card,
    get_action_card_steps,
    list_template_options,
    normalize_action_code,
    snap_pose_to_grid,
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


def simulate_action_plan_final_pose(
    start_pose: Pose,
    cards: List[str],
    chassis_template: str = "Square",
) -> Pose:
    """Simulates the final pose resulting from executing a 3-card Action Plan."""
    curr = start_pose.clone()
    for card in cards[:3]:
        steps = get_action_card_steps(card, chassis_template=chassis_template)
        for step in steps:
            curr = apply_movement_step(curr, step, clamp_to_walls=True, chassis_template=chassis_template)
            curr = snap_pose_to_grid(curr, chassis_template)
    return curr


def _enforce_drive_budget(cards: List[str], max_l: int, max_r: int) -> List[str]:
    """Ensures a 3-card plan does not exceed the available drive budget."""
    clean = list(cards[:3])
    while len(clean) < 3:
        clean.append("Wait")

    cur_l = sum((get_action_card(c) or {}).get("left", 0) for c in clean)
    cur_r = sum((get_action_card(c) or {}).get("right", 0) for c in clean)
    if cur_l <= max_l and cur_r <= max_r:
        return clean

    # Step-down strategy: replace higher cost forward/reverse/pivot cards
    for idx in reversed(range(len(clean))):
        c = clean[idx]
        if cur_l <= max_l and cur_r <= max_r:
            break
        if c in ("3 F", "3 B"):
            clean[idx] = "2 F" if "F" in c else "2 B"
        elif c in ("2 F", "2 B"):
            clean[idx] = "1F" if "F" in c else "1 B"
        elif c in ("1F", "1 B"):
            clean[idx] = "Wait"
        elif c in ("90 R", "-90 R"):
            clean[idx] = "45 R" if c == "90 R" else "-45 R"
        elif c in ("90 L", "-90 L"):
            clean[idx] = "45 L" if c == "90 L" else "-45 L"
        elif c in ("90 PR", "90 PL", "180 P"):
            clean[idx] = "45 R" if "R" in c or c == "180 P" else "45 L"

        cur_l = sum((get_action_card(x) or {}).get("left", 0) for x in clean)
        cur_r = sum((get_action_card(x) or {}).get("right", 0) for x in clean)

    # Final pass: if still over budget, set remaining cards to Wait
    for idx in reversed(range(len(clean))):
        if cur_l <= max_l and cur_r <= max_r:
            break
        clean[idx] = "Wait"
        cur_l = sum((get_action_card(x) or {}).get("left", 0) for x in clean)
        cur_r = sum((get_action_card(x) or {}).get("right", 0) for x in clean)

    return clean


def compute_automaton_action_plan(
    automaton: RobotState,
    player: RobotState,
    action: str,
    evade_direction: Optional[str] = None,
) -> MoveChoice:
    """
    Selects 3 movement Action Cards to execute the chosen automaton action
    (Rush, Face, Retreat, Evade) considering the opponent's current position.
    - Evade: Turns to face the clear normal (perpendicular to player) and moves away along it.
    - Face: Rotates on the spot to face the opponent.
    - Retreat: Faces the opponent and drives backwards away from them.
    - Rush: Drives at the opponent at full speed, turning towards them as needed.
    - Safeguard: None of the AI choices will end facing directly away from where the player starts.
    """
    max_l = max(1, automaton.left_drive_max)
    max_r = max(1, automaton.right_drive_max)

    # Vector from automaton to player
    dx = player.pose.x - automaton.pose.x
    dy = player.pose.y - automaton.pose.y
    target_heading_deg = math.degrees(math.atan2(dx, -dy))
    rel_bearing_deg = normalize_angle_deg(target_heading_deg - automaton.pose.theta)

    if action == "Evade":
        # Evade: move forwards and perpendicular to the line between the robots.
        # Rule (Action_tables.md): "Evade - move forwards and perpendicular to the line between the robots.
        # Roll 1-3 go to the players right, 4-6 go to the players left. If one direction is blocked, choose the unblocked direction."
        # User constraint: "evade should turn to face the normal and move away."
        p_to_a_x = automaton.pose.x - player.pose.x
        p_to_a_y = automaton.pose.y - player.pose.y
        player_to_auto_heading = math.degrees(math.atan2(p_to_a_x, -p_to_a_y))
        perp_right = (round((player_to_auto_heading + 90.0) / 45.0) * 45.0) % 360.0
        perp_left = (round((player_to_auto_heading - 90.0) / 45.0) * 45.0) % 360.0
        dist_r = _compute_direction_clearance(automaton.pose.x, automaton.pose.y, perp_right)
        dist_l = _compute_direction_clearance(automaton.pose.x, automaton.pose.y, perp_left)

        if evade_direction == "right" and dist_r >= 80.0:
            chosen_normal = perp_right
        elif evade_direction == "left" and dist_l >= 80.0:
            chosen_normal = perp_left
        elif dist_r >= 80.0 and dist_l >= 80.0:
            if evade_direction == "right":
                chosen_normal = perp_right
            elif evade_direction == "left":
                chosen_normal = perp_left
            else:
                # Rule: "if both ways are clear choose at random"
                # If equal clearance and no forced direction, pick the normal closer to current heading
                turn_r = abs(normalize_angle_deg(perp_right - automaton.pose.theta))
                turn_l = abs(normalize_angle_deg(perp_left - automaton.pose.theta))
                if turn_r < turn_l:
                    chosen_normal = perp_right
                elif turn_l < turn_r:
                    chosen_normal = perp_left
                else:
                    chosen_normal = random.choice([perp_right, perp_left])
        elif dist_r >= 80.0:
            chosen_normal = perp_right
        elif dist_l >= 80.0:
            chosen_normal = perp_left
        else:
            chosen_normal = perp_right if dist_r >= dist_l else perp_left

        turn_diff = normalize_angle_deg(chosen_normal - automaton.pose.theta)
        # Turn to face chosen_normal and move away
        if abs(turn_diff) <= 22.5:
            # Already facing normal: move forwards away along normal
            cards = ["1F", "1F", "1F"] if max_l >= 3 and max_r >= 3 else (["2 F", "Wait", "Wait"] if max_l >= 2 and max_r >= 2 else ["1F", "Wait", "Wait"])
        elif 22.5 < turn_diff <= 67.5:
            cards = ["45 R", "1F", "1F"]
        elif -67.5 <= turn_diff < -22.5:
            cards = ["45 L", "1F", "1F"]
        elif 67.5 < turn_diff <= 112.5:
            turn_card = "90 PR" if (max_l >= 1 and max_r >= 1) else "90 R"
            cards = [turn_card, "1F", "1F"]
        elif -112.5 <= turn_diff < -67.5:
            turn_card = "90 PL" if (max_l >= 1 and max_r >= 1) else "90 L"
            cards = [turn_card, "1F", "1F"]
        else:
            # Turn > 112.5 deg to face normal
            turn_card = "90 PR" if turn_diff > 0 else "90 PL"
            second_turn = "45 R" if turn_diff > 0 else "45 L"
            cards = [turn_card, second_turn, "1F"]

    elif action == "Face":
        # Face: Rotate on the spot to face their opponent
        if abs(rel_bearing_deg) <= 22.5:
            cards = ["Wait", "Wait", "Wait"]
        elif 22.5 < rel_bearing_deg <= 67.5:
            cards = ["45 R", "Wait", "Wait"]
        elif -67.5 <= rel_bearing_deg < -22.5:
            cards = ["45 L", "Wait", "Wait"]
        elif 67.5 < rel_bearing_deg <= 112.5:
            turn_card = "90 PR" if (max_l >= 1 and max_r >= 1) else "90 R"
            cards = [turn_card, "Wait", "Wait"]
        elif -112.5 <= rel_bearing_deg < -67.5:
            turn_card = "90 PL" if (max_l >= 1 and max_r >= 1) else "90 L"
            cards = [turn_card, "Wait", "Wait"]
        elif 112.5 < rel_bearing_deg <= 157.5:
            turn_card = "90 PR" if (max_l >= 1 and max_r >= 1) else "90 R"
            cards = [turn_card, "45 R", "Wait"]
        elif -157.5 <= rel_bearing_deg < -112.5:
            turn_card = "90 PL" if (max_l >= 1 and max_r >= 1) else "90 L"
            cards = [turn_card, "45 L", "Wait"]
        else:
            # Currently facing away: rotate 180 degrees to face opponent
            turn_card = "90 PR" if (max_l >= 1 and max_r >= 1) else "90 R"
            cards = [turn_card, turn_card, "Wait"]

    elif action == "Retreat":
        # Retreat: Move away from opponent while facing them
        if abs(rel_bearing_deg) <= 22.5:
            # Facing opponent: reverse away from them
            cards = ["1 B", "Wait", "Wait"]
        elif 22.5 < rel_bearing_deg <= 67.5:
            cards = ["45 R", "1 B", "Wait"]
        elif -67.5 <= rel_bearing_deg < -22.5:
            cards = ["45 L", "1 B", "Wait"]
        elif 67.5 < rel_bearing_deg <= 112.5:
            turn_card = "90 PR" if (max_l >= 1 and max_r >= 1) else "90 R"
            cards = [turn_card, "1 B", "Wait"]
        elif -112.5 <= rel_bearing_deg < -67.5:
            turn_card = "90 PL" if (max_l >= 1 and max_r >= 1) else "90 L"
            cards = [turn_card, "1 B", "Wait"]
        else:
            # Large angle: turn towards opponent, then reverse
            turn_card = "90 PR" if rel_bearing_deg > 0 else "90 PL"
            cards = [turn_card, turn_card, "1 B"]

    elif action == "Rush":
        # Rush: Drive at the opponent at full speed (turning towards opponent as required)
        if abs(rel_bearing_deg) <= 22.5:
            cards = ["2 F", "1F", "Wait"] if max_l >= 3 and max_r >= 3 else (["2 F", "Wait", "Wait"] if max_l >= 2 and max_r >= 2 else ["1F", "Wait", "Wait"])
        elif 22.5 < rel_bearing_deg <= 67.5:
            cards = ["45 R", "1F", "1F"]
        elif -67.5 <= rel_bearing_deg < -22.5:
            cards = ["45 L", "1F", "1F"]
        elif 67.5 < rel_bearing_deg <= 112.5:
            turn_card = "90 PR" if (max_l >= 1 and max_r >= 1) else "90 R"
            cards = [turn_card, "1F", "1F"]
        elif -112.5 <= rel_bearing_deg < -67.5:
            turn_card = "90 PL" if (max_l >= 1 and max_r >= 1) else "90 L"
            cards = [turn_card, "1F", "1F"]
        else:
            turn_card = "90 PR" if rel_bearing_deg > 0 else "90 PL"
            turn_card2 = "45 R" if rel_bearing_deg > 0 else "45 L"
            cards = [turn_card, turn_card2, "1F"]

    else:
        cards = ["Wait", "Wait", "Wait"]

    # Enforce active drive budget
    cards = _enforce_drive_budget(cards, max_l, max_r)

    # Post-selection safeguard: None of the AI choices should end facing directly away
    final_pose = simulate_action_plan_final_pose(automaton.pose, cards, automaton.chassis_template)
    v_end_x = player.pose.x - final_pose.x
    v_end_y = player.pose.y - final_pose.y
    if math.hypot(v_end_x, v_end_y) > 1e-3:
        to_player_start = math.degrees(math.atan2(v_end_x, -v_end_y))
        away_angle = (to_player_start + 180.0) % 360.0
        diff_from_away = abs(normalize_angle_deg(final_pose.theta - away_angle))
        if diff_from_away <= 22.5:
            # End pose is facing directly away from where player starts!
            # Adjust cards to prevent facing away: turn to face normal or player
            if action == "Evade":
                cards[0] = "90 PR" if (max_l >= 1 and max_r >= 1) else "45 R"
            elif action == "Retreat":
                cards[0] = "90 PR" if rel_bearing_deg > 0 else "90 PL"
                cards[1] = "1 B"
            else:
                cards[0] = "90 PR" if rel_bearing_deg > 0 else "90 PL"
            cards = _enforce_drive_budget(cards, max_l, max_r)

    is_reverse = (action == "Retreat" and all("B" in c or c == "Wait" for c in cards))
    sign = -1 if is_reverse else 1
    total_l = sign * sum((get_action_card(c) or {}).get("left", 0) for c in cards)
    total_r = sign * sum((get_action_card(c) or {}).get("right", 0) for c in cards)
    return MoveChoice(left=total_l, right=total_r, cards=cards)


def compute_automaton_drive(
    automaton: RobotState,
    player: RobotState,
    action: str,
    evade_direction: Optional[str] = None,
) -> MoveChoice:
    """Calculates chosen Action Cards and drive pair for automaton action."""
    return compute_automaton_action_plan(automaton, player, action, evade_direction=evade_direction)


