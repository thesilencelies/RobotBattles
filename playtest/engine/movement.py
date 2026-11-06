"""Template-based movement and trajectory generation for Robot Battles."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from .field import (
    WALL_BOTTOM,
    WALL_LEFT,
    WALL_RIGHT,
    WALL_TOP,
    push_robot_inside_arena_if_past_wall,
)
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

# Canonical 18 Movement Action Cards pool from cardDefinitions/action_cards.csv
ACTION_CARDS: Dict[str, Dict[str, Any]] = {
    "Wait": {
        "code": "Wait",
        "name": "Wait",
        "motion": "stay still",
        "left": 0,
        "right": 0,
        "type": "wait",
        "category": "linear",
        "category_label": "Stationary",
        "icon": "⏹️",
        "image": "Action_Wait.png",
    },
    "1F": {
        "code": "1F",
        "name": "1 Forwards",
        "motion": "move forwards 1",
        "left": 1,
        "right": 1,
        "type": "forward_1",
        "category": "linear",
        "category_label": "Forward",
        "icon": "⬆️",
        "image": "Action_1F.png",
    },
    "2 F": {
        "code": "2 F",
        "name": "2 Forwards",
        "motion": "move forwards 2",
        "left": 2,
        "right": 2,
        "type": "forward_2",
        "category": "linear",
        "category_label": "Forward",
        "icon": "⬆️",
        "image": "Action_2_F.png",
    },
    "3 F": {
        "code": "3 F",
        "name": "3 Forwards",
        "motion": "move forward 3",
        "left": 3,
        "right": 3,
        "type": "forward_3",
        "category": "linear",
        "category_label": "Forward",
        "icon": "⬆️",
        "image": "Action_3_F.png",
    },
    "1 B": {
        "code": "1 B",
        "name": "1 Reverse",
        "motion": "move backwards 1",
        "left": 1,
        "right": 1,
        "type": "backward_1",
        "category": "reverse",
        "category_label": "Reverse",
        "icon": "⬇️",
        "image": "Action_1_B.png",
    },
    "2 B": {
        "code": "2 B",
        "name": "2 Reverse",
        "motion": "move backwards 2",
        "left": 2,
        "right": 2,
        "type": "backward_2",
        "category": "reverse",
        "category_label": "Reverse",
        "icon": "⬇️",
        "image": "Action_2_B.png",
    },
    "3 B": {
        "code": "3 B",
        "name": "3 Reverse",
        "motion": "move backwards 3",
        "left": 3,
        "right": 3,
        "type": "backward_3",
        "category": "reverse",
        "category_label": "Reverse",
        "icon": "⬇️",
        "image": "Action_3_B.png",
    },
    "45 R": {
        "code": "45 R",
        "name": "45° Right Turn",
        "motion": "right turn 45",
        "left": 1,
        "right": 0,
        "type": "turn_r_45",
        "category": "turn",
        "category_label": "Forward Turn",
        "icon": "↗️",
        "image": "Action_45_R.png",
    },
    "90 R": {
        "code": "90 R",
        "name": "90° Right Turn",
        "motion": "right turn 90",
        "left": 2,
        "right": 0,
        "type": "turn_r_90",
        "category": "turn",
        "category_label": "Forward Turn",
        "icon": "↪️",
        "image": "Action_90_R.png",
    },
    "45 L": {
        "code": "45 L",
        "name": "45° Left Turn",
        "motion": "left turn 45",
        "left": 0,
        "right": 1,
        "type": "turn_l_45",
        "category": "turn",
        "category_label": "Forward Turn",
        "icon": "↖️",
        "image": "Action_45_L.png",
    },
    "90 L": {
        "code": "90 L",
        "name": "90° Left Turn",
        "motion": "left turn 90",
        "left": 0,
        "right": 2,
        "type": "turn_l_90",
        "category": "turn",
        "category_label": "Forward Turn",
        "icon": "↩️",
        "image": "Action_90_L.png",
    },
    "-45 L": {
        "code": "-45 L",
        "name": "45° Reversing Left",
        "motion": "reversing left turn 45",
        "left": 1,
        "right": 0,
        "type": "rev_turn_l_45",
        "category": "reverse_turn",
        "category_label": "Reversing Turn",
        "icon": "↙️",
        "image": "Action_-45_L.png",
    },
    "-90 L": {
        "code": "-90 L",
        "name": "90° Reversing Left",
        "motion": "reversing left turn 90",
        "left": 2,
        "right": 0,
        "type": "rev_turn_l_90",
        "category": "reverse_turn",
        "category_label": "Reversing Turn",
        "icon": "↩️",
        "image": "Action_-90_L.png",
    },
    "-45 R": {
        "code": "-45 R",
        "name": "45° Reversing Right",
        "motion": "reversing right turn 45",
        "left": 0,
        "right": 1,
        "type": "rev_turn_r_45",
        "category": "reverse_turn",
        "category_label": "Reversing Turn",
        "icon": "↘️",
        "image": "Action_-45_R.png",
    },
    "-90 R": {
        "code": "-90 R",
        "name": "90° Reversing Right",
        "motion": "reversing right turn 90",
        "left": 0,
        "right": 2,
        "type": "rev_turn_r_90",
        "category": "reverse_turn",
        "category_label": "Reversing Turn",
        "icon": "↪️",
        "image": "Action_-90_R.png",
    },
    "90 PR": {
        "code": "90 PR",
        "name": "90° Pivot Right",
        "motion": "pivot 90 right",
        "left": 1,
        "right": 1,
        "type": "pivot_r_90",
        "category": "pivot",
        "category_label": "Center Pivot",
        "icon": "🔃",
        "image": "Action_90_PR.png",
    },
    "90 PL": {
        "code": "90 PL",
        "name": "90° Pivot Left",
        "motion": "pivot 90 left",
        "left": 1,
        "right": 1,
        "type": "pivot_l_90",
        "category": "pivot",
        "category_label": "Center Pivot",
        "icon": "🔄",
        "image": "Action_90_PL.png",
    },
    "180 P": {
        "code": "180 P",
        "name": "180° Pivot",
        "motion": "180 pivot",
        "left": 2,
        "right": 2,
        "type": "pivot_180",
        "category": "pivot",
        "category_label": "Center Pivot",
        "icon": "🔁",
        "image": "Action_180_P.png",
    },
}

ACTION_CARDS_ORDER: List[str] = [
    "Wait", "1F", "2 F", "3 F",
    "1 B", "2 B", "3 B",
    "45 R", "90 R", "45 L", "90 L",
    "-45 L", "-90 L", "-45 R", "-90 R",
    "90 PR", "90 PL", "180 P",
]


def normalize_action_code(code: str) -> str:
    """Normalizes variations in card code (spaces, casing) to standard canonical code."""
    c = str(code).strip()
    if not c or c.upper() == "WAIT":
        return "Wait"
    up = c.upper().replace(" ", "")
    mapping = {
        "1F": "1F",
        "2F": "2 F",
        "3F": "3 F",
        "1B": "1 B",
        "2B": "2 B",
        "3B": "3 B",
        "45R": "45 R",
        "90R": "90 R",
        "45L": "45 L",
        "90L": "90 L",
        "-45L": "-45 L",
        "-90L": "-90 L",
        "-45R": "-45 R",
        "-90R": "-90 R",
        "90PR": "90 PR",
        "90PL": "90 PL",
        "180P": "180 P",
    }
    return mapping.get(up, c)


def get_action_card(code: str) -> Optional[Dict[str, Any]]:
    """Returns metadata for an action card by code."""
    norm = normalize_action_code(code)
    return ACTION_CARDS.get(norm)


def list_all_action_cards() -> List[Dict[str, Any]]:
    """Returns all 18 action cards in canonical display order."""
    return [ACTION_CARDS[code] for code in ACTION_CARDS_ORDER if code in ACTION_CARDS]


def list_available_action_cards(active_left: int, active_right: int) -> List[Dict[str, Any]]:
    """
    Returns all action cards whose individual drive costs fit within
    the robot's active left and right drive limits (minimum base drive of 1).
    """
    eff_l = max(1, int(active_left))
    eff_r = max(1, int(active_right))
    return [
        c for c in list_all_action_cards()
        if c["left"] <= eff_l and c["right"] <= eff_r
    ]


def validate_action_plan(
    cards: List[str], active_left: int, active_right: int
) -> Tuple[bool, str, int, int]:
    """
    Validates a 3-card plan against active drive capacity.
    Rule: sum(Left Costs) <= max(1, active_left) and sum(Right Costs) <= max(1, active_right).
    Guaranteed Base Drive: Robots always have at least 1 drive on each side.
    Returns (is_valid, error_message, total_left_cost, total_right_cost).
    """
    if len(cards) != 3:
        return (False, f"Exactly 3 action cards required, got {len(cards)}.", 0, 0)

    total_l = 0
    total_r = 0
    norm_cards: List[str] = []

    for c in cards:
        card = get_action_card(c)
        if not card:
            return (False, f"Unknown action card code '{c}'.", 0, 0)
        norm_cards.append(card["code"])
        total_l += card["left"]
        total_r += card["right"]

    max_l = max(1, int(active_left))
    max_r = max(1, int(active_right))

    if total_l > max_l:
        return (
            False,
            f"Left drive cost ({total_l}) exceeds available active drive ({max_l}).",
            total_l,
            total_r,
        )
    if total_r > max_r:
        return (
            False,
            f"Right drive cost ({total_r}) exceeds available active drive ({max_r}).",
            total_l,
            total_r,
        )

    return (True, "", total_l, total_r)


def get_action_card_steps(code: str, chassis_template: str = "Square") -> List[Dict[str, Any]]:
    """
    Decomposes an Action Card into its discrete movement steps across the grid.
    - Wait: []
    - 1F, 2 F, 3 F: 1, 2, or 3 forwards steps
    - 1 B, 2 B, 3 B: 1, 2, or 3 reverse steps
    - 45 R: 1 turn step CW pinned right
    - 90 R: 2 turn steps CW pinned right
    - 45 L: 1 turn step CCW pinned left
    - 90 L: 2 turn steps CCW pinned left
    - -45 L: 1 reversing turn step CW pinned right (reverse=True)
    - -90 L: 2 reversing turn steps CW pinned right (reverse=True)
    - -45 R: 1 reversing turn step CCW pinned left (reverse=True)
    - -90 R: 2 reversing turn steps CCW pinned left (reverse=True)
    - 90 PR: 2 pivot steps CW
    - 90 PL: 2 pivot steps CCW
    - 180 P: 4 pivot steps CW
    """
    norm = normalize_action_code(code)
    steps: List[Dict[str, Any]] = []

    if norm == "Wait":
        pass

    elif norm == "1F":
        steps.append({"type": "forwards", "direction": 1, "card": "1F"})
    elif norm == "2 F":
        steps.append({"type": "forwards", "direction": 1, "card": "2 F"})
        steps.append({"type": "forwards", "direction": 1, "card": "2 F"})
    elif norm == "3 F":
        steps.append({"type": "forwards", "direction": 1, "card": "3 F"})
        steps.append({"type": "forwards", "direction": 1, "card": "3 F"})
        steps.append({"type": "forwards", "direction": 1, "card": "3 F"})

    elif norm == "1 B":
        steps.append({"type": "reverse", "direction": -1, "card": "1 B"})
    elif norm == "2 B":
        steps.append({"type": "reverse", "direction": -1, "card": "2 B"})
        steps.append({"type": "reverse", "direction": -1, "card": "2 B"})
    elif norm == "3 B":
        steps.append({"type": "reverse", "direction": -1, "card": "3 B"})
        steps.append({"type": "reverse", "direction": -1, "card": "3 B"})
        steps.append({"type": "reverse", "direction": -1, "card": "3 B"})

    elif norm == "45 R":
        steps.append({"type": "turn", "pinned_side": "right", "rotation_deg": 45.0, "reverse": False, "card": "45 R"})
    elif norm == "90 R":
        steps.append({"type": "turn", "pinned_side": "right", "rotation_deg": 45.0, "reverse": False, "card": "90 R"})
        steps.append({"type": "turn", "pinned_side": "right", "rotation_deg": 45.0, "reverse": False, "card": "90 R"})

    elif norm == "45 L":
        steps.append({"type": "turn", "pinned_side": "left", "rotation_deg": -45.0, "reverse": False, "card": "45 L"})
    elif norm == "90 L":
        steps.append({"type": "turn", "pinned_side": "left", "rotation_deg": -45.0, "reverse": False, "card": "90 L"})
        steps.append({"type": "turn", "pinned_side": "left", "rotation_deg": -45.0, "reverse": False, "card": "90 L"})

    elif norm == "-45 L":
        steps.append({"type": "turn", "pinned_side": "right", "rotation_deg": -45.0, "reverse": True, "card": "-45 L"})
    elif norm == "-90 L":
        steps.append({"type": "turn", "pinned_side": "right", "rotation_deg": -45.0, "reverse": True, "card": "-90 L"})
        steps.append({"type": "turn", "pinned_side": "right", "rotation_deg": -45.0, "reverse": True, "card": "-90 L"})

    elif norm == "-45 R":
        steps.append({"type": "turn", "pinned_side": "left", "rotation_deg": 45.0, "reverse": True, "card": "-45 R"})
    elif norm == "-90 R":
        steps.append({"type": "turn", "pinned_side": "left", "rotation_deg": 45.0, "reverse": True, "card": "-90 R"})
        steps.append({"type": "turn", "pinned_side": "left", "rotation_deg": 45.0, "reverse": True, "card": "-90 R"})

    elif norm == "90 PR":
        steps.append({"type": "pivot", "rotation_deg": 45.0, "card": "90 PR"})
        steps.append({"type": "pivot", "rotation_deg": 45.0, "card": "90 PR"})
    elif norm == "90 PL":
        steps.append({"type": "pivot", "rotation_deg": -45.0, "card": "90 PL"})
        steps.append({"type": "pivot", "rotation_deg": -45.0, "card": "90 PL"})
    elif norm == "180 P":
        steps.append({"type": "pivot", "rotation_deg": 45.0, "card": "180 P"})
        steps.append({"type": "pivot", "rotation_deg": 45.0, "card": "180 P"})
        steps.append({"type": "pivot", "rotation_deg": 45.0, "card": "180 P"})
        steps.append({"type": "pivot", "rotation_deg": 45.0, "card": "180 P"})

    return steps


def synthesize_cards_from_drive(left: int, right: int) -> List[str]:
    """
    Synthesizes a 3-card Action Plan from a (left, right) drive pair for backward compatibility.
    """
    l_val = int(left)
    r_val = int(right)

    if l_val == 0 and r_val == 0:
        return ["Wait", "Wait", "Wait"]

    if l_val == r_val:
        if l_val > 0:
            k = min(3, l_val)
            card1 = "1F" if k == 1 else f"{k} F"
            rem = l_val - k
            card2 = "1F" if rem == 1 else (f"{rem} F" if rem > 1 else "Wait")
            return [card1, card2, "Wait"]
        else:
            k = min(3, abs(l_val))
            card1 = f"{k} B"
            rem = abs(l_val) - k
            card2 = f"{rem} B" if rem > 0 else "Wait"
            return [card1, card2, "Wait"]

    if l_val > 0 and r_val == 0:
        if l_val == 1:
            return ["45 R", "Wait", "Wait"]
        elif l_val == 2:
            return ["90 R", "Wait", "Wait"]
        else:
            return ["90 R", "45 R", "Wait"]

    if l_val == 0 and r_val > 0:
        if r_val == 1:
            return ["45 L", "Wait", "Wait"]
        elif r_val == 2:
            return ["90 L", "Wait", "Wait"]
        else:
            return ["90 L", "45 L", "Wait"]

    if l_val > 0 and r_val < 0:
        return ["90 PR", "Wait", "Wait"] if min(l_val, abs(r_val)) == 1 else ["180 P", "Wait", "Wait"]

    if l_val < 0 and r_val > 0:
        return ["90 PL", "Wait", "Wait"] if min(abs(l_val), r_val) == 1 else ["180 P", "Wait", "Wait"]

    # Curve forward
    if l_val > r_val and r_val > 0:
        return ["45 R", "1F", "Wait"]
    if r_val > l_val and l_val > 0:
        return ["45 L", "1F", "Wait"]

    return ["Wait", "Wait", "Wait"]


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


def get_turn_grid_delta(
    heading_deg: float,
    rot_deg: float,
    pinned_side: str = "right",
    chassis_template: str = "Square",
    reverse: bool = False,
) -> Tuple[int, int]:
    """
    Returns the integer (dx, dy) grid direction for a 45-degree Turn step,
    where heading 0 is North (-y), 90 is East (+x), 180 is South (+y), 270 is West (-x).

    - Square chassis swings around its outer pinned wheel/edge into the adjacent cell.
    - Wide and Triangle chassis shift 1 grid cell forward along the turn arc.
    - If reverse is True, the displacement direction is reversed (-dx, -dy).
    """
    snapped = int(round((heading_deg % 360.0) / 45.0) * 45) % 360
    is_cw = (rot_deg > 0)
    tname = (chassis_template or "Square").capitalize()

    if tname in ("Wide", "Triangle"):
        # Shifts 1 grid square forward along the turn arc
        if is_cw:
            deltas_cw = {
                0: (0, -1),    # 0 -> 45: North
                45: (1, 0),    # 45 -> 90: East
                90: (1, 0),    # 90 -> 135: East
                135: (0, 1),   # 135 -> 180: South
                180: (0, 1),   # 180 -> 225: South
                225: (-1, 0),  # 225 -> 270: West
                270: (-1, 0),  # 270 -> 315: West
                315: (0, -1),  # 315 -> 0: North
            }
            dx, dy = deltas_cw.get(snapped, (0, -1))
        else:
            deltas_ccw = {
                0: (0, -1),    # 0 -> 315: North
                315: (-1, 0),  # 315 -> 270: West
                270: (-1, 0),  # 270 -> 225: West
                225: (0, 1),   # 225 -> 180: South
                180: (0, 1),   # 180 -> 135: South
                135: (1, 0),   # 135 -> 90: East
                90: (1, 0),    # 90 -> 45: East
                45: (0, -1),   # 45 -> 0: North
            }
            dx, dy = deltas_ccw.get(snapped, (0, -1))
    else:
        # Square: swings around outer pinned edge into adjacent cell
        if is_cw:
            deltas_cw = {
                0: (1, 0),     # 0 -> 45: East
                45: (0, -1),   # 45 -> 90: North
                90: (0, 1),    # 90 -> 135: South
                135: (1, 0),   # 135 -> 180: East
                180: (-1, 0),  # 180 -> 225: West
                225: (0, 1),   # 225 -> 270: South
                270: (0, -1),  # 270 -> 315: North
                315: (-1, 0),  # 315 -> 0: West
            }
            dx, dy = deltas_cw.get(snapped, (1, 0))
        else:
            deltas_ccw = {
                0: (-1, 0),    # 0 -> 315: West
                315: (0, -1),  # 315 -> 270: North
                270: (0, 1),   # 270 -> 225: South
                225: (-1, 0),  # 225 -> 180: West
                180: (1, 0),   # 180 -> 135: East
                135: (0, 1),   # 135 -> 90: South
                90: (0, -1),   # 90 -> 45: North
                45: (1, 0),    # 45 -> 0: East
            }
            dx, dy = deltas_ccw.get(snapped, (-1, 0))

    if reverse:
        return (-dx, -dy)
    return (dx, dy)


def snap_pose_to_grid(pose: Pose, chassis_template: str = "Square") -> Pose:
    """
    Snaps a robot Pose strictly to the discrete 40mm arena grid and 45-degree heading increments:
    - Heading theta is snapped to the nearest 45 degree multiple (0, 45, 90, 135, 180, 225, 270, 315).
    - Square chassis (2x2) is centered on a grid vertex (multiple of 40.0).
    - Wide (5x1) and Triangle chassis are centered on a tile center ((floor(coord / 40.0) + 0.5) * 40.0).
    """
    snapped_th = float(int(round((pose.theta % 360.0) / 45.0)) * 45) % 360.0
    tname = (chassis_template or "Square").capitalize()
    if tname == "Square":
        snapped_x = round(pose.x / 40.0) * 40.0
        snapped_y = round(pose.y / 40.0) * 40.0
    else:
        snapped_x = (math.floor(pose.x / 40.0) + 0.5) * 40.0
        snapped_y = (math.floor(pose.y / 40.0) + 0.5) * 40.0
    return Pose(snapped_x, snapped_y, snapped_th)


def apply_movement_step(
    pose: Pose,
    step: Dict[str, Any],
    wheelbase: float = WHEELBASE_MM,
    grid_unit_mm: float = DRIVE_UNIT_MM,
    clamp_to_walls: bool = True,
    chassis_template: str = "Square",
) -> Pose:
    """
    Applies a single discrete movement step to a robot Pose.
    - forwards / reverse: translates 1 grid cell along heading delta.
    - pivot: rotates 45 degrees in place around geometric center.
    - turn: pivots 45 degrees around outer wheel/edge, snapping to discrete grid.
    - wait: no change.
    All outputs strictly snap to discrete 40mm grid vertices and 45-degree heading increments.
    """
    stype = step["type"]
    new_pose = pose.clone()

    if stype == "wait":
        pass

    elif stype in ("forwards", "reverse"):
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
        pinned = step.get("pinned_side", "right")
        is_rev = step.get("reverse", False)
        dx_g, dy_g = get_turn_grid_delta(new_pose.theta, rot_deg, pinned, chassis_template, reverse=is_rev)
        new_pose.x += dx_g * grid_unit_mm
        new_pose.y += dy_g * grid_unit_mm
        new_pose.theta = (new_pose.theta + rot_deg) % 360.0

    if clamp_to_walls:
        new_pose.x = max(WALL_LEFT + MINIATURE_RADIUS, min(WALL_RIGHT - MINIATURE_RADIUS, new_pose.x))
        new_pose.y = max(WALL_TOP + MINIATURE_RADIUS, min(WALL_BOTTOM - MINIATURE_RADIUS, new_pose.y))
        new_pose = snap_pose_to_grid(new_pose, chassis_template)
        if stype in ("pivot", "turn"):
            new_pose = push_robot_inside_arena_if_past_wall(new_pose, chassis_template)
    else:
        new_pose = snap_pose_to_grid(new_pose, chassis_template)

    return new_pose


def apply_joint_step(
    active_pose: Pose,
    passive_pose: Pose,
    step: Dict[str, Any],
    wheelbase: float = WHEELBASE_MM,
    grid_unit_mm: float = DRIVE_UNIT_MM,
    clamp_to_walls: bool = False,
    active_chassis: str = "Square",
    passive_chassis: str = "Square",
    rotate_passive: bool = False,
) -> Tuple[Pose, Pose]:
    """
    Executes a movement step on active_pose, moving passive_pose along like it is stuck to it.
    - Forwards / Reverse: both robots translate by the same grid delta.
    - Pivot: both robots rotate about active robot's center by rotation_deg (passive robot does not rotate its orientation if rotate_passive is False).
    - Turn: both robots rotate about active robot's pinned edge/wheel by rotation_deg (passive robot does not rotate its orientation if rotate_passive is False).
    Both outputs are strictly snapped to discrete 40mm grid vertices and 45-degree heading increments.
    """
    stype = step["type"]
    new_active = active_pose.clone()
    new_passive = passive_pose.clone()

    if stype == "wait":
        pass

    elif stype in ("forwards", "reverse"):
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
        if rotate_passive:
            new_passive.theta = (passive_pose.theta + rot_deg) % 360.0
        else:
            new_passive.theta = passive_pose.theta

    elif stype == "turn":
        rot_deg = step["rotation_deg"]
        pinned_side = step.get("pinned_side", "right")
        is_rev = step.get("reverse", False)
        dx_g, dy_g = get_turn_grid_delta(active_pose.theta, rot_deg, pinned_side, active_chassis, reverse=is_rev)
        dx_mm = dx_g * grid_unit_mm
        dy_mm = dy_g * grid_unit_mm
        new_active.x += dx_mm
        new_active.y += dy_mm
        new_active.theta = (active_pose.theta + rot_deg) % 360.0

        rad = math.radians(rot_deg)
        cos_r = math.cos(rad)
        sin_r = math.sin(rad)
        rel_x = passive_pose.x - active_pose.x
        rel_y = passive_pose.y - active_pose.y
        new_passive.x = new_active.x + (rel_x * cos_r - rel_y * sin_r)
        new_passive.y = new_active.y + (rel_x * sin_r + rel_y * cos_r)
        if rotate_passive:
            new_passive.theta = (passive_pose.theta + rot_deg) % 360.0
        else:
            new_passive.theta = passive_pose.theta

    if clamp_to_walls:
        new_active.x = max(WALL_LEFT + MINIATURE_RADIUS, min(WALL_RIGHT - MINIATURE_RADIUS, new_active.x))
        new_active.y = max(WALL_TOP + MINIATURE_RADIUS, min(WALL_BOTTOM - MINIATURE_RADIUS, new_active.y))
        new_passive.x = max(WALL_LEFT + MINIATURE_RADIUS, min(WALL_RIGHT - MINIATURE_RADIUS, new_passive.x))
        new_passive.y = max(WALL_TOP + MINIATURE_RADIUS, min(WALL_BOTTOM - MINIATURE_RADIUS, new_passive.y))
        new_active = snap_pose_to_grid(new_active, active_chassis)
        new_passive = snap_pose_to_grid(new_passive, passive_chassis)
        if stype in ("pivot", "turn"):
            new_active = push_robot_inside_arena_if_past_wall(new_active, active_chassis)
            new_passive = push_robot_inside_arena_if_past_wall(new_passive, passive_chassis)
    else:
        new_active = snap_pose_to_grid(new_active, active_chassis)
        new_passive = snap_pose_to_grid(new_passive, passive_chassis)
    return (new_active, new_passive)


def generate_push_trajectory(
    start_moving_pose: Pose,
    start_stationary_pose: Pose,
    remaining_steps: List[Dict[str, Any]],
    num_substeps: int = 4,
    moving_chassis: str = "Square",
    stationary_chassis: str = "Square",
) -> Tuple[List[Pose], List[Pose], Pose, Pose]:
    """
    Computes intermediate trajectory points for both the moving pusher and the stationary pushed robot
    for the remaining steps of the moving robot's action card.
    Returns (moving_trajectory, pushed_trajectory, final_moving_pose, final_pushed_pose).
    """
    curr_m = start_moving_pose.clone()
    curr_s = start_stationary_pose.clone()
    m_points: List[Pose] = [curr_m.clone()]
    s_points: List[Pose] = [curr_s.clone()]

    for step in remaining_steps:
        prev_m = curr_m.clone()
        prev_s = curr_s.clone()
        next_m, next_s = apply_joint_step(
            curr_m, curr_s, step, clamp_to_walls=True,
            active_chassis=moving_chassis, passive_chassis=stationary_chassis,
            rotate_passive=False,
        )
        curr_m = snap_pose_to_grid(next_m, moving_chassis)
        curr_s = snap_pose_to_grid(next_s, stationary_chassis)

        sub = max(1, num_substeps)
        for s in range(1, sub + 1):
            alpha = s / float(sub)
            ix_m = prev_m.x + (curr_m.x - prev_m.x) * alpha
            iy_m = prev_m.y + (curr_m.y - prev_m.y) * alpha
            d_th_m = (curr_m.theta - prev_m.theta + 180.0) % 360.0 - 180.0
            ith_m = (prev_m.theta + d_th_m * alpha) % 360.0
            m_points.append(Pose(ix_m, iy_m, ith_m))

            ix_s = prev_s.x + (curr_s.x - prev_s.x) * alpha
            iy_s = prev_s.y + (curr_s.y - prev_s.y) * alpha
            d_th_s = (curr_s.theta - prev_s.theta + 180.0) % 360.0 - 180.0
            ith_s = (prev_s.theta + d_th_s * alpha) % 360.0
            s_points.append(Pose(ix_s, iy_s, ith_s))

    return (m_points, s_points, curr_m, curr_s)


def generate_action_plan_trajectory(
    start_pose: Pose,
    cards: List[str],
    num_substeps: int = 4,
    clamp_to_walls: bool = True,
    chassis_template: str = "Square",
) -> Tuple[List[TrajectoryPoint], List[Dict[str, Any]]]:
    """
    Computes discrete trajectories and per-action step breakdowns for 3 Action Cards.
    Returns (all_trajectory_points, action_details).
    """
    clean_cards = [normalize_action_code(c) for c in cards]
    while len(clean_cards) < 3:
        clean_cards.append("Wait")
    clean_cards = clean_cards[:3]

    curr = start_pose.clone()
    all_points: List[TrajectoryPoint] = [
        TrajectoryPoint(x=curr.x, y=curr.y, theta=curr.theta, t=0.0)
    ]
    action_details: List[Dict[str, Any]] = []

    total_actions = 3
    for act_idx, code in enumerate(clean_cards):
        act_start = curr.clone()
        steps = get_action_card_steps(code, chassis_template=chassis_template)
        step_poses = [act_start.clone()]

        for step in steps:
            curr = apply_movement_step(
                curr, step, clamp_to_walls=clamp_to_walls, chassis_template=chassis_template
            )
            step_poses.append(curr.clone())

        # Generate interpolated substeps for smooth animation within action slice
        t_base = act_idx / float(total_actions)
        t_span = 1.0 / float(total_actions)
        n_steps = len(steps)

        if n_steps == 0:
            # Stationary / Wait: hold pose for this slice
            sub = max(1, num_substeps)
            for s in range(1, sub + 1):
                t_val = t_base + (s / float(sub)) * t_span
                all_points.append(
                    TrajectoryPoint(x=curr.x, y=curr.y, theta=curr.theta, t=t_val)
                )
        else:
            sub_per_step = max(1, num_substeps // n_steps)
            for s_idx in range(n_steps):
                p_s = step_poses[s_idx]
                p_e = step_poses[s_idx + 1]
                for sub in range(1, sub_per_step + 1):
                    alpha = sub / float(sub_per_step)
                    global_t = t_base + ((s_idx + alpha) / float(n_steps)) * t_span
                    ix = p_s.x + (p_e.x - p_s.x) * alpha
                    iy = p_s.y + (p_e.y - p_s.y) * alpha
                    d_th = (p_e.theta - p_s.theta + 180.0) % 360.0 - 180.0
                    ith = (p_s.theta + d_th * alpha) % 360.0
                    all_points.append(TrajectoryPoint(x=ix, y=iy, theta=ith, t=global_t))

        card_meta = get_action_card(code) or {"name": code, "motion": code}
        action_details.append({
            "action_index": act_idx,
            "card_code": code,
            "card_name": card_meta.get("name", code),
            "start_pose": {"x": act_start.x, "y": act_start.y, "theta": act_start.theta},
            "end_pose": {"x": curr.x, "y": curr.y, "theta": curr.theta},
            "steps": steps,
            "num_steps": len(steps),
        })

    return (all_points, action_details)


def generate_trajectory(
    start_pose: Pose,
    choice: MoveChoice,
    num_steps: int = 30,
    clamp_to_walls: bool = True,
    chassis_template: str = "Square",
) -> List[TrajectoryPoint]:
    """
    Computes a discrete trajectory of TrajectoryPoints from t=0.0 to t=1.0.
    Supports either explicit Action Cards (choice.cards) or legacy (choice.left, choice.right).
    """
    if choice.cards and len(choice.cards) > 0:
        pts, _ = generate_action_plan_trajectory(
            start_pose,
            choice.cards,
            num_substeps=max(1, num_steps // 3),
            clamp_to_walls=clamp_to_walls,
            chassis_template=chassis_template,
        )
        return pts

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
        curr = apply_movement_step(curr, step, clamp_to_walls=clamp_to_walls, chassis_template=chassis_template)
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

