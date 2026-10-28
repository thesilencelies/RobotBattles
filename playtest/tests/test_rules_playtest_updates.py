import pytest
import math
from typing import Dict

from playtest.engine.types import (
    RobotState, ComponentHealth, MoveChoice, Pose, CollisionEvent
)
from playtest.engine.collision import (
    get_component_side,
    is_uhmw_wraparound_armor,
    find_components_along_contact_line,
    get_robot_miniature_parts
)
from playtest.engine.combat import (
    get_largest_absolute_drive_strength,
    _resolve_single_weapon_attack,
    resolve_inert_contact,
    resolve_collision_combat
)

def make_comp(
    cid: str,
    name: str,
    card_type: str,
    x: float,
    y: float,
    durability: int = 10,
    absorption: int = 0,
    text: str = "",
    keywords: str = "",
    outputs: str = "",
    template: str = "Line",
    **kwargs
) -> ComponentHealth:
    return ComponentHealth(
        id=cid,
        name=name,
        card_type=card_type,
        max_durability=durability,
        current_durability=durability,
        absorption=absorption,
        requirements="",
        outputs=outputs,
        keywords=keywords,
        text=text,
        x=x,
        y=y,
        rotation=0,
        box=(x, y, x + 44.0, y + 64.0),
        template=template,
        **kwargs
    )

def make_bot(
    bid: str,
    name: str,
    pose: Pose,
    components: Dict[str, ComponentHealth],
    chassis_template: str = "Square",
    **kwargs
) -> RobotState:
    cids = list(components.keys())
    return RobotState(
        id=bid,
        name=name,
        chassis_name="Chassis",
        chassis_template=chassis_template,
        flip_strength=3,
        pose=pose,
        components=components,
        connections={cid: cids for cid in cids},
        supply_graph={cid: [] for cid in cids},
        reverse_supply={cid: [] for cid in cids},
        **kwargs
    )


# =========================================================================
# Rule 1: Weapons that have reset cannot attack while inactive due to reset
# =========================================================================

def test_rule1_get_robot_miniature_parts_inactive_reset():
    # Weapon that is reset and inactive
    w1 = make_comp("w1", "Spinner", "weapon", 210.0, 50.0, is_active=False, is_reset=True)
    # Weapon that is actively resetting
    w2 = make_comp("w2", "Flipper", "weapon", 210.0, 50.0, is_active=False, is_resetting=True)
    # Weapon that is active and normal
    w3 = make_comp("w3", "Saw", "weapon", 210.0, 50.0, is_active=True, is_reset=False)

    bot = make_bot("bot", "Bot", Pose(400.0, 400.0, 0.0), {"w1": w1, "w2": w2, "w3": w3})
    parts = get_robot_miniature_parts(bot, bot.pose.x, bot.pose.y, bot.pose.theta)

    # All 3 physical weapons are in weapon_parts (for physical presence / body collision)
    all_wp_cids = [wp["cid"] for wp in parts["weapon_parts"]]
    assert "w1" in all_wp_cids
    assert "w2" in all_wp_cids
    assert "w3" in all_wp_cids

    # Only active, non-resetting w3 should be in active_weapon_parts
    act_wp_cids = [awp["cid"] for awp in parts["active_weapon_parts"]]
    assert "w1" not in act_wp_cids
    assert "w2" not in act_wp_cids
    assert "w3" in act_wp_cids


def test_rule1_resolve_single_weapon_attack_inactive_reset():
    w_inactive = make_comp("w1", "Spinner", "weapon", 210.0, 50.0, outputs="5W", is_active=False, is_reset=True)
    w_resetting = make_comp("w2", "Flipper", "weapon", 210.0, 50.0, outputs="5W", is_active=False, is_resetting=True)

    target = make_comp("target", "Plate", "structure", 210.0, 150.0, durability=20)
    attacker = make_bot("atk", "Attacker", Pose(400.0, 400.0, 0.0), {"w1": w_inactive, "w2": w_resetting})
    defender = make_bot("def", "Defender", Pose(400.0, 360.0, 0.0), {"target": target})

    dummy_col = CollisionEvent(
        time_t=0.5,
        contact_point=(400.0, 380.0),
        robot1_octant="Front",
        robot2_octant="Back",
        robot1_components=["w1"],
        robot2_components=["target"],
        contact_type="ACTIVE",
        description="Active attack"
    )

    # Inactive due to reset weapon cannot attack
    logs = []
    res1 = _resolve_single_weapon_attack(attacker, defender, w_inactive, dummy_col, ["target"], round_num=1, logs=logs)
    assert res1 == (0, 0)
    assert not w_inactive.was_used_this_turn
    assert target.current_durability == 20

    # Resetting weapon cannot attack
    logs = []
    res2 = _resolve_single_weapon_attack(attacker, defender, w_resetting, dummy_col, ["target"], round_num=1, logs=logs)
    assert res2 == (0, 0)
    assert not w_resetting.was_used_this_turn
    assert target.current_durability == 20


def test_rule1_resolve_collision_combat_falls_back_to_inert():
    w1 = make_comp("w1", "Spinner", "weapon", 210.0, 50.0, outputs="5W", is_active=False, is_reset=True)
    body1 = make_comp("b1", "Body", "structure", 210.0, 150.0, durability=20)
    body2 = make_comp("b2", "Body2", "structure", 210.0, 150.0, durability=20)

    p_bot = make_bot("p", "Player", Pose(400.0, 435.0, 0.0), {"w1": w1, "b1": body1})
    a_bot = make_bot("a", "Auto", Pose(400.0, 365.0, 180.0), {"b2": body2})

    col = CollisionEvent(
        time_t=0.5,
        contact_point=(400.0, 400.0),
        robot1_octant="Front",
        robot2_octant="Front",
        robot1_components=["w1"],
        robot2_components=["b2"],
        contact_type="ACTIVE",
        description="Active clash",
        r1_active_hit=True,
        r2_active_hit=False,
        r1_active_weapons=["w1"],
        r2_active_weapons=[]
    )

    logs = resolve_collision_combat(col, p_bot, a_bot, 1)
    # Since w1 cannot attack, combat falls back to inert pushing contact
    attack_logs = [l for l in logs if "Attacking Weapon" in l.message or "attacks with" in l.message]
    assert len(attack_logs) == 0
    assert any("Inert contact" in l.message or "PUSHING MATCH" in l.message for l in logs)


# =========================================================================
# Rule 2: UHMW wraparound armor intercepts attacks on its side
# =========================================================================

def test_rule2_side_detection_and_uhmw_identification():
    front = make_comp("f", "Front Armor", "armor", 210.0, 50.0)
    back = make_comp("b", "Back Plate", "armor", 210.0, 240.0)
    left = make_comp("l", "Left Skirt", "armor", 100.0, 150.0)
    right = make_comp("r", "Right Skirt", "armor", 320.0, 150.0)
    uhmw = make_comp("uhmw", "UHMW Wraparound Armor", "armor", 210.0, 250.0, text="Attacks that hit this components side hit this instead.")

    assert get_component_side(front) == "front"
    assert get_component_side(back) == "back"
    assert get_component_side(left) == "left"
    assert get_component_side(right) == "right"
    assert get_component_side(uhmw) == "back"
    assert is_uhmw_wraparound_armor(uhmw)
    assert not is_uhmw_wraparound_armor(back)


def test_rule2_find_components_along_contact_line_intercepts():
    back_comp = make_comp("b1", "Back Component", "component", 210.0, 240.0)
    uhmw = make_comp("uhmw", "UHMW Wraparound Armor", "armor", 210.0, 250.0, text="Attacks that hit this components side hit this instead.")
    front_comp = make_comp("f1", "Front Component", "component", 210.0, 50.0)

    defender = make_bot("def", "Defender", Pose(400.0, 400.0, 0.0), {"b1": back_comp, "uhmw": uhmw, "f1": front_comp})

    # Contact at the back of the robot (y > 400 in world coordinates when heading is 0)
    cids = find_components_along_contact_line(
        defender, (400.0, 426.0), defender.pose.x, defender.pose.y, defender.pose.theta, "Back"
    )
    assert "uhmw" in cids
    assert "b1" not in cids


def test_rule2_weapon_attack_intercepted_by_uhmw():
    back_comp = make_comp("b1", "Battery", "component", 210.0, 240.0, durability=6, absorption=0)
    front_comp = make_comp("f1", "Front Plate", "armor", 210.0, 50.0, durability=10, absorption=2)
    uhmw = make_comp("uhmw", "UHMW Wraparound Armor", "armor", 210.0, 250.0, durability=10, absorption=2, text="Attacks that hit this components side hit this instead.")

    defender = make_bot("def", "Defender", Pose(400.0, 400.0, 0.0), {"b1": back_comp, "f1": front_comp, "uhmw": uhmw})

    weapon = make_comp("w", "Hammer", "weapon", 210.0, 50.0, outputs="6W", is_active=True)
    attacker = make_bot("atk", "Attacker", Pose(400.0, 350.0, 0.0), {"w": weapon})

    dummy_col = CollisionEvent(
        time_t=0.5,
        contact_point=(400.0, 400.0),
        robot1_octant="Front",
        robot2_octant="Back",
        robot1_components=["w"],
        robot2_components=["b1"],
        contact_type="ACTIVE",
        description="Active hit"
    )

    # 1. Attack targeting back_comp is intercepted by UHMW armor
    logs = []
    _resolve_single_weapon_attack(attacker, defender, weapon, dummy_col, ["b1"], round_num=1, logs=logs)
    assert uhmw.current_durability < 10
    assert uhmw.is_damaged
    assert back_comp.current_durability == 6, "Battery should take no damage because UHMW intercepted"

    # 2. Attack targeting front_comp is NOT intercepted by back UHMW armor
    weapon.was_used_this_turn = False
    logs = []
    _resolve_single_weapon_attack(attacker, defender, weapon, dummy_col, ["f1"], round_num=2, logs=logs)
    assert front_comp.current_durability < 10
    assert front_comp.is_damaged

    # 3. If UHMW armor is destroyed, it no longer intercepts
    uhmw.is_destroyed = True
    weapon.was_used_this_turn = False
    logs = []
    _resolve_single_weapon_attack(attacker, defender, weapon, dummy_col, ["b1"], round_num=3, logs=logs)
    assert back_comp.current_durability < 6, "Battery should now take damage since UHMW is destroyed"


# =========================================================================
# Rule 3: Wall push throw perpendicular to wall with pusher drive strength
# =========================================================================

def test_rule3_largest_absolute_drive_strength():
    drive = make_comp("d", "Drive Motor", "component", 210.0, 150.0, outputs="3D")
    bot = make_bot("bot", "Bot", Pose(400.0, 400.0, 0.0), {"d": drive}, left_drive_max=3, right_drive_max=5)

    # Provided choice with negative values
    choice1 = MoveChoice(left=2, right=-6)
    assert get_largest_absolute_drive_strength(bot, choice1) == 6

    # Robot's stored current_choice
    bot.current_choice = MoveChoice(left=-4, right=1)
    assert get_largest_absolute_drive_strength(bot) == 4

    # Fallback to drive max
    bot.current_choice = None
    assert get_largest_absolute_drive_strength(bot) == 5


@pytest.mark.parametrize("wall,def_pos,expected_normal", [
    ("left", (120.0, 400.0), (1.0, 0.0)),     # Left wall at x=100 -> thrown +x (East)
    ("right", (680.0, 400.0), (-1.0, 0.0)),   # Right wall at x=700 -> thrown -x (West)
    ("top", (400.0, 120.0), (0.0, 1.0)),      # Top wall at y=100 -> thrown +y (South)
    ("bottom", (400.0, 680.0), (0.0, -1.0)),  # Bottom wall at y=700 -> thrown -y (North)
])
def test_rule3_wall_push_and_perpendicular_throw(wall, def_pos, expected_normal):
    pusher_choice = MoveChoice(left=3, right=-5)  # largest abs strength = 5
    pushed_choice = MoveChoice(left=1, right=1)   # defender drive = 1

    pusher = make_bot("pusher", "Pusher", Pose(400.0, 400.0, 0.0), {
        "d": make_comp("d", "Drive", "component", 210.0, 150.0, outputs="5D")
    })
    pusher.current_choice = pusher_choice

    body = make_comp("body", "Body", "structure", 210.0, 150.0, durability=6, absorption=0)
    defender = make_bot("def", "Defender", Pose(def_pos[0], def_pos[1], 0.0), {"body": body})
    defender.current_choice = pushed_choice

    col = CollisionEvent(
        time_t=1.0,
        contact_point=(def_pos[0], def_pos[1]),
        robot1_octant="Front",
        robot2_octant="Back",
        robot1_components=["d"],
        robot2_components=["body"],
        contact_type="INERT",
        description="Pushed into wall",
        push_vector=(expected_normal[0] * -10.0, expected_normal[1] * -10.0),
        r1_remaining_dist=50.0,
        r2_remaining_dist=0.0
    )

    init_x, init_y = defender.pose.x, defender.pose.y
    logs = resolve_inert_contact(col, pusher, defender, round_num=1, r1_choice=pusher_choice, r2_choice=pushed_choice)

    # 1. Throw displacement along normal vector
    dx = defender.pose.x - init_x
    dy = defender.pose.y - init_y

    if expected_normal[0] != 0:
        assert math.copysign(1.0, dx) == expected_normal[0]
        assert abs(dx) > 0.0
    if expected_normal[1] != 0:
        assert math.copysign(1.0, dy) == expected_normal[1]
        assert abs(dy) > 0.0

    # 2. Throw damage equals pusher's drive strength (5)
    wall_throw_logs = [l for l in logs if "thrown" in l.message.lower() or "wall" in l.message.lower()]
    assert len(wall_throw_logs) > 0
    assert any("throw damage 5" in l.message.lower() or "strength 5" in l.message.lower() for l in wall_throw_logs)
    assert defender.components["body"].current_durability <= 6 - 5
