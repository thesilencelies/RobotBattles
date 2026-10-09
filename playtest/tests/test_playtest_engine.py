"""Unit tests for the playtest rules engine."""

import sys
import unittest
from unittest.mock import patch
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from builder.server.data import read_saved_robot
from playtest.engine.automata import (
    compute_automaton_drive,
    get_automaton_action,
    roll_d6,
)
from playtest.engine.collision import detect_collision, get_octant
from playtest.engine.combat import (
    apply_damage_to_component,
    parse_weapon_spin_and_damage,
    refresh_robot_drive_and_power,
    resolve_collision_combat,
)
from playtest.engine.match import create_match, execute_turn
from playtest.engine.movement import generate_trajectory
from playtest.engine.types import (
    CollisionEvent,
    ComponentHealth,
    MoveChoice,
    Pose,
    RobotState,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class TestPlaytestEngine(unittest.TestCase):
    def test_trajectory_generation(self):
        start = Pose(400.0, 600.0, 0.0)  # North

        # 1. Stationary
        traj_stat = generate_trajectory(start, MoveChoice(0, 0), num_steps=10)
        self.assertEqual(len(traj_stat), 11)
        self.assertAlmostEqual(traj_stat[-1].x, 400.0)
        self.assertAlmostEqual(traj_stat[-1].y, 600.0)

        # 2. Straight (3, 3) -> Forward along North (-y) by 3 * 40 = 120 mm
        traj_fwd = generate_trajectory(start, MoveChoice(3, 3), num_steps=10)
        self.assertAlmostEqual(traj_fwd[-1].x, 400.0, places=1)
        self.assertAlmostEqual(traj_fwd[-1].y, 480.0, places=1)
        self.assertAlmostEqual(traj_fwd[-1].theta, 0.0, places=1)

        # 3. Pivot on spot (-2, 2) -> Center stays same, theta rotates
        traj_piv = generate_trajectory(start, MoveChoice(-2, 2), num_steps=10)
        self.assertAlmostEqual(traj_piv[-1].x, 400.0, places=1)
        self.assertAlmostEqual(traj_piv[-1].y, 600.0, places=1)
        self.assertNotEqual(traj_piv[-1].theta, 0.0)

        # 4. Arc turn (3, 1) -> Advances and curves
        traj_arc = generate_trajectory(start, MoveChoice(3, 1), num_steps=10)
        self.assertNotEqual(traj_arc[-1].x, 400.0)
        self.assertLess(traj_arc[-1].y, 600.0)

    def test_octant_determination(self):
        # Center at (0, 0), heading 0 (North = -y)
        self.assertEqual(get_octant(0, 0, 0, -50, 0.0), "Front")
        self.assertEqual(get_octant(0, 0, 50, -50, 0.0), "Front-Right")
        self.assertEqual(get_octant(0, 0, 50, 0, 0.0), "Right")
        self.assertEqual(get_octant(0, 0, 50, 50, 0.0), "Back-Right")
        self.assertEqual(get_octant(0, 0, 0, 50, 0.0), "Back")
        self.assertEqual(get_octant(0, 0, -50, 50, 0.0), "Back-Left")
        self.assertEqual(get_octant(0, 0, -50, 0, 0.0), "Left")
        self.assertEqual(get_octant(0, 0, -50, -50, 0.0), "Front-Left")

    def test_automata_action_tables(self):
        # Create dummy robot
        robot = RobotState(
            id="a",
            name="Vyper_Spinner",
            chassis_name="Viper Wedge Chassis",
            chassis_template="Triangle",
            flip_strength=5,
            pose=Pose(400, 200, 180),
            components={},
            connections={},
            supply_graph={},
            reverse_supply={},
            weapon_spin_counters={"w": 2},  # Charged
        )

        # Charged Vyper_Spinner: 1 = Retreat, 2 = Face, 3..6 = Rush
        self.assertEqual(get_automaton_action("Vyper_Spinner", robot, 1), "Retreat")
        self.assertEqual(get_automaton_action("Vyper_Spinner", robot, 2), "Face")
        self.assertEqual(get_automaton_action("Vyper_Spinner", robot, 4), "Rush")

        # Uncharged Vyper_Spinner: spin counters < 2
        robot.weapon_spin_counters["w"] = 0
        self.assertEqual(get_automaton_action("Vyper_Spinner", robot, 1), "Retreat")
        self.assertEqual(get_automaton_action("Vyper_Spinner", robot, 3), "Retreat")
        self.assertEqual(get_automaton_action("Vyper_Spinner", robot, 4), "Face")
        self.assertEqual(get_automaton_action("Vyper_Spinner", robot, 6), "Rush")

        # Vyper_flipper (Full Rush): 1 = Retreat, 2 = Face, 3..6 = Rush
        self.assertEqual(get_automaton_action("Vyper_flipper", robot, 1), "Retreat")
        self.assertEqual(get_automaton_action("Vyper_flipper", robot, 2), "Face")
        self.assertEqual(get_automaton_action("Vyper_flipper", robot, 5), "Rush")

        # Chonk (Spin Up):
        # Charged (>= 2)
        robot.weapon_spin_counters["w"] = 2
        self.assertEqual(get_automaton_action("Chonk", robot, 1), "Retreat")
        self.assertEqual(get_automaton_action("Chonk", robot, 2), "Face")
        self.assertEqual(get_automaton_action("Chonk", robot, 5), "Rush")
        # Uncharged (< 2)
        robot.weapon_spin_counters["w"] = 1
        self.assertEqual(get_automaton_action("Chonk", robot, 2), "Retreat")
        self.assertEqual(get_automaton_action("Chonk", robot, 5), "Face")
        self.assertEqual(get_automaton_action("Chonk", robot, 6), "Rush")

        # Beater_wide / Nightwing_wide (Balanced):
        # Setup Beater Bar component with max_spin = 3
        beater_comp = ComponentHealth(
            id="16", name="Beater Bar", card_type="weapon", max_durability=9,
            current_durability=9, absorption=1, requirements="SSS", outputs="XWWW",
            keywords="Spin up (3);Self-right", text="", x=180, y=30, rotation=0,
            box=(180, 30, 224, 94), is_wedge=False,
        )
        robot.components = {"16": beater_comp}

        # Sub-spin (< 3): 1..2 = Retreat, 3..4 = Face, 5..6 = Rush
        robot.weapon_spin_counters = {"16": 1}
        self.assertEqual(get_automaton_action("Beater_wide", robot, 1), "Retreat")
        self.assertEqual(get_automaton_action("Beater_wide", robot, 2), "Retreat")
        self.assertEqual(get_automaton_action("Beater_wide", robot, 3), "Face")
        self.assertEqual(get_automaton_action("Beater_wide", robot, 4), "Face")
        self.assertEqual(get_automaton_action("Beater_wide", robot, 5), "Rush")
        self.assertEqual(get_automaton_action("Beater_wide", robot, 6), "Rush")

        # Full-spin (>= 3): 1 = Retreat, 2..3 = Face, 4..6 = Rush
        robot.weapon_spin_counters = {"16": 3}
        self.assertEqual(get_automaton_action("Beater_wide", robot, 1), "Retreat")
        self.assertEqual(get_automaton_action("Beater_wide", robot, 2), "Face")
        self.assertEqual(get_automaton_action("Beater_wide", robot, 3), "Face")
        self.assertEqual(get_automaton_action("Beater_wide", robot, 4), "Rush")
        self.assertEqual(get_automaton_action("Beater_wide", robot, 6), "Rush")

        # Nightwing_wide behaves identically under Balanced archetype
        self.assertEqual(get_automaton_action("Nightwing_wide", robot, 2), "Face")
        self.assertEqual(get_automaton_action("Nightwing_wide", robot, 4), "Rush")

    def test_automata_drive_calculation(self):
        player = RobotState(
            id="p", name="Player", chassis_name="", chassis_template="Square",
            flip_strength=5, pose=Pose(400, 500, 0), components={}, connections={},
            supply_graph={}, reverse_supply={}
        )
        # Automaton is at (400, 200), facing South (180 deg) -> Player is directly in front of it!
        automaton = RobotState(
            id="a", name="Auto", chassis_name="", chassis_template="Triangle",
            flip_strength=5, pose=Pose(400, 200, 180), components={}, connections={},
            supply_graph={}, reverse_supply={}, left_drive_max=3, right_drive_max=3
        )

        # Rush -> Straight forward towards player
        drive_rush = compute_automaton_drive(automaton, player, "Rush")
        self.assertEqual(drive_rush.left, 3)
        self.assertEqual(drive_rush.right, 3)

        # Retreat -> Back up
        drive_retreat = compute_automaton_drive(automaton, player, "Retreat")
        self.assertEqual(drive_retreat.left, -1)
        self.assertEqual(drive_retreat.right, -1)

    def test_full_match_initialization_and_turn(self):
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        self.assertIsNotNone(csv_text)

        match = create_match(
            player_csv=csv_text,
            automaton_name="Vyper_flipper",
            player_name="Test Pilot",
        )

        self.assertEqual(match.round, 1)
        self.assertEqual(match.phase, "planning")
        self.assertEqual(match.player_robot.name, "Test Pilot")
        self.assertGreater(match.player_robot.left_drive_max, 0)
        self.assertGreater(match.player_robot.right_drive_max, 0)

        # Execute turn 1 with (3, 3) forward
        updated = execute_turn(match, MoveChoice(left=3, right=3), fixed_automaton_roll=4)
        self.assertEqual(updated.round, 2)
        self.assertEqual(updated.phase, "planning")
        self.assertGreater(len(updated.log), 1)
        self.assertEqual(updated.automaton_action, "Rush")

    def test_damage_and_feedback(self):
        comp = ComponentHealth(
            id="1", name="Titanium Wedge", card_type="component", max_durability=9,
            current_durability=9, absorption=1, requirements="", outputs="", keywords="wedge",
            text="", x=100, y=20, rotation=0, box=(100, 20, 144, 84), is_wedge=True
        )
        status, abs_dmg, excess = apply_damage_to_component(comp, 10.0, is_weapon_damage=True)
        self.assertEqual(status, "DESTROYED")
        self.assertEqual(abs_dmg, 9.0)
        self.assertEqual(excess, 1.0)

    def test_match_completion_10_rounds(self):
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player")

        # Step 10 rounds of stationary / passive moves
        for r in range(1, 11):
            if match.phase == "game_over":
                break
            execute_turn(match, MoveChoice(0, 0), fixed_automaton_roll=1)

        self.assertEqual(match.phase, "game_over")
        self.assertIsNotNone(match.winner)
        self.assertIsNotNone(match.win_reason)


    def test_weapon_template_placement(self):
        from playtest.engine.field import card_to_miniature_offset, get_weapon_template_geometry
        # Mat center is 210, 150. A weapon placed near front center: x=188, y=50 (width 44, height 64)
        # Card center: cx = 188 + 22 = 210, cy = 50 + 32 = 82
        # Offset: dx = 0, dy = (82 - 150) * 0.273 = -18.564 (forward on miniature)
        lx, ly = card_to_miniature_offset(188.0, 50.0, 44.0, 64.0)
        self.assertAlmostEqual(lx, 0.0, places=2)
        self.assertLess(ly, -15.0)

        geom = get_weapon_template_geometry("Circle", (lx, ly))
        self.assertAlmostEqual(geom["center"][0], lx)
        self.assertAlmostEqual(geom["center"][1], ly)
        self.assertEqual(geom["radius"], 22.0)

    def test_start_of_turn_spin_up(self):
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player")
        # In Round 1 initialization, start_of_turn_spin_up already fired
        # Horizontal Spinner has Spin up (4), starts at 1 spin counter (0 + 1)
        player_bot = match.player_robot
        spin_weapons = [c for c in player_bot.components.values() if "spin up" in c.keywords.lower()]
        self.assertGreater(len(spin_weapons), 0)
        w = spin_weapons[0]
        self.assertGreaterEqual(w.spin_counters, 1)

    def test_pushing_match_resolution(self):
        from playtest.engine.combat import resolve_collision_combat
        from playtest.engine.types import CollisionEvent
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        # Create simulated inert collision event
        col = CollisionEvent(
            time_t=0.5,
            contact_point=(400.0, 400.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=[list(p_bot.components.keys())[0]],
            robot2_components=[list(a_bot.components.keys())[0]],
            contact_type="INERT",
            description="Pushing match",
            r1_remaining_dist=80.0,
            r2_remaining_dist=40.0,
            push_vector=(0.0, -10.0),
        )
        p_bot.pose.theta = 0.0
        a_bot.pose.theta = 180.0
        logs = resolve_collision_combat(col, p_bot, a_bot, 1)
        self.assertGreater(len(logs), 0)
        # Drive should absorb feedback equal to opponent's remaining momentum
        self.assertTrue(any("feedback" in entry.message.lower() for entry in logs))
        # Standalone inert contact does NOT rotate robots
        self.assertFalse(any("rotated a random amount" in entry.message for entry in logs))
        self.assertEqual(p_bot.pose.theta, 0.0)
        self.assertEqual(a_bot.pose.theta, 180.0)

    def test_flip_inversion_math(self):
        from playtest.engine.combat import resolve_collision_combat
        from playtest.engine.types import CollisionEvent
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        # Setup spin counters on automaton weapon
        auto_weapon = [c for c in a_bot.components.values() if c.card_type == "weapon"][0]
        a_bot.weapon_spin_counters[auto_weapon.id] = 4

        col = CollisionEvent(
            time_t=0.5,
            contact_point=(400.0, 400.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=[list(p_bot.components.keys())[0]],
            robot2_components=[auto_weapon.id],
            contact_type="ACTIVE",
            description="Active strike",
            r1_active_hit=False,
            r2_active_hit=True,
        )
        logs = resolve_collision_combat(col, p_bot, a_bot, 1)
        self.assertTrue(any("THROWN" in entry.message for entry in logs))

    def test_wedge_prevents_throw(self):
        from playtest.engine.combat import resolve_collision_combat
        from playtest.engine.types import CollisionEvent
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        # Ensure player robot has a wedge component hit
        wedge_comp = ComponentHealth(
            id="wedge_1", name="Titanium Wedge", card_type="component",
            max_durability=9, current_durability=9, absorption=1, requirements="",
            outputs="", keywords="wedge", text="", x=100, y=20, rotation=0,
            box=(100, 20, 144, 84), is_wedge=True,
        )
        p_bot.components["wedge_1"] = wedge_comp

        auto_weapon = [c for c in a_bot.components.values() if c.card_type == "weapon"][0]
        a_bot.weapon_spin_counters[auto_weapon.id] = 4

        col = CollisionEvent(
            time_t=0.5,
            contact_point=(400.0, 400.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=["wedge_1"],
            robot2_components=[auto_weapon.id],
            contact_type="ACTIVE",
            description="Active strike hitting wedge",
            r1_active_hit=False,
            r2_active_hit=True,
        )
        logs = resolve_collision_combat(col, p_bot, a_bot, 1)
        # Wedge was hit: p_bot is NOT thrown, and no throw reflection to a_bot
        self.assertTrue(any("Wedge was hit" in entry.message for entry in logs))
        self.assertFalse(any(f"{p_bot.name} is THROWN" in entry.message for entry in logs))

    def test_split_supply_distribution(self):
        """
        Verify the canonical rule:
        - If a supplier can supply all downstream components, they are all supplied.
        - If not, priority is: drive first, then weapons, unless drive side is 0 this turn.
        - Within same category: largest requirement going down.
        """
        # Battery output 2E
        battery = ComponentHealth(
            id="bat", name="Battery", card_type="component",
            max_durability=5, current_durability=5, absorption=0,
            requirements="", outputs="2E", keywords="", text="",
            x=200, y=200, rotation=0, box=(200, 200, 244, 264)
        )
        # Left drive motor requiring 2E, outputs D
        left_motor = ComponentHealth(
            id="m_left", name="Left Motor", card_type="component",
            max_durability=3, current_durability=3, absorption=0,
            requirements="2E", outputs="D", keywords="", text="",
            x=100, y=100, rotation=0, box=(100, 100, 144, 164)
        )
        # Weapon requiring 2E, outputs 4W
        weapon = ComponentHealth(
            id="wep", name="Spinner Weapon", card_type="weapon",
            max_durability=4, current_durability=4, absorption=0,
            requirements="2E", outputs="4W", keywords="Spin up (1, 3)", text="",
            x=210, y=50, rotation=0, box=(210, 50, 254, 114)
        )

        robot = RobotState(
            id="test_bot", name="Test Bot", chassis_name="Square", chassis_template="Square",
            flip_strength=3, pose=Pose(400, 400, 0),
            components={"bat": battery, "m_left": left_motor, "wep": weapon},
            connections={"bat": ["m_left", "wep"], "m_left": ["bat"], "wep": ["bat"]},
            supply_graph={"m_left": ["bat"], "wep": ["bat"], "bat": []},
            reverse_supply={"bat": ["m_left", "wep"], "m_left": [], "wep": []},
        )

        # 1. Normal state: drive is used by default (current_move=None)
        # 2E total supply: drive takes priority over weapon!
        refresh_robot_drive_and_power(robot)
        self.assertTrue(robot.components["bat"].is_active)
        self.assertTrue(robot.components["m_left"].is_active, "Drive should be supplied first")
        self.assertFalse(robot.components["wep"].is_active, "Weapon should be unpowered due to 2E supply limit")
        self.assertEqual(robot.left_drive_max, 1)

        # 2. Divert power: Robot chooses not to use left drive this turn (left = 0)
        refresh_robot_drive_and_power(robot, current_move=MoveChoice(left=0, right=0))
        self.assertTrue(robot.components["bat"].is_active)
        self.assertFalse(robot.components["m_left"].is_active, "Drive not used this turn, so power is freed")
        self.assertTrue(robot.components["wep"].is_active, "Weapon should receive freed power")

        # 3. Sufficient power: Battery upgraded to 4E -> both are supplied
        battery.outputs = "4E"
        refresh_robot_drive_and_power(robot)
        self.assertTrue(robot.components["m_left"].is_active)
        self.assertTrue(robot.components["wep"].is_active)

    def test_best_effort_split_supply_overlapping_batteries(self):
        """
        Tests the exact user scenario:
        A 4-supply battery (bat1) is connected to 2 motors (m1, m2).
        A 2-supply battery (bat2) is connected to both those motors (m1, m2) AND a 3rd motor (m3).
        Each motor requires 2E.
        Best-effort max-flow must supply bat1 -> m1 (2E), bat1 -> m2 (2E), bat2 -> m3 (2E),
        so ALL 3 motors are active, regardless of component ID ordering.
        """
        for id_swap in [False, True]:
            b1_id = "bat_alpha" if not id_swap else "bat_zeta"
            b2_id = "bat_zeta" if not id_swap else "bat_alpha"

            bat1 = ComponentHealth(
                id=b1_id, name="Battery 4E", card_type="component",
                max_durability=5, current_durability=5, absorption=0,
                requirements="", outputs="4E", keywords="", text="",
                x=100, y=100, rotation=0, box=(100, 100, 144, 164)
            )
            bat2 = ComponentHealth(
                id=b2_id, name="Battery 2E", card_type="component",
                max_durability=5, current_durability=5, absorption=0,
                requirements="", outputs="2E", keywords="", text="",
                x=300, y=100, rotation=0, box=(300, 100, 344, 164)
            )
            m1 = ComponentHealth(
                id="m1", name="Motor 1", card_type="component",
                max_durability=3, current_durability=3, absorption=0,
                requirements="2E", outputs="D", keywords="", text="",
                x=50, y=200, rotation=0, box=(50, 200, 94, 264)
            )
            m2 = ComponentHealth(
                id="m2", name="Motor 2", card_type="component",
                max_durability=3, current_durability=3, absorption=0,
                requirements="2E", outputs="D", keywords="", text="",
                x=150, y=200, rotation=0, box=(150, 200, 194, 264)
            )
            m3 = ComponentHealth(
                id="m3", name="Motor 3", card_type="component",
                max_durability=3, current_durability=3, absorption=0,
                requirements="2E", outputs="D", keywords="", text="",
                x=350, y=200, rotation=0, box=(350, 200, 394, 264)
            )

            components = {b1_id: bat1, b2_id: bat2, "m1": m1, "m2": m2, "m3": m3}
            supply_graph = {
                b1_id: [],
                b2_id: [],
                "m1": [b1_id, b2_id],
                "m2": [b1_id, b2_id],
                "m3": [b2_id],
            }
            reverse_supply = {
                b1_id: ["m1", "m2"],
                b2_id: ["m1", "m2", "m3"],
                "m1": [],
                "m2": [],
                "m3": [],
            }
            robot = RobotState(
                id="tree_bot", name="Tree Bot", chassis_name="Square", chassis_template="Square",
                flip_strength=3, pose=Pose(400, 400, 0),
                components=components,
                connections={},
                supply_graph=supply_graph,
                reverse_supply=reverse_supply,
            )

            refresh_robot_drive_and_power(robot)
            self.assertTrue(robot.components["m1"].is_active, f"m1 must be active (swap={id_swap})")
            self.assertTrue(robot.components["m2"].is_active, f"m2 must be active (swap={id_swap})")
            self.assertTrue(robot.components["m3"].is_active, f"m3 must be active (swap={id_swap})")

    def test_best_effort_split_supply_priority_preservation(self):
        """
        When supply is constrained (2E + 2E = 4E total, but 3 motors require 6E):
        - If m3 is drive and m1, m2 are weapons, m3 (drive) must stay active.
        """
        bat1 = ComponentHealth(
            id="bat1", name="Battery 2E #1", card_type="component",
            max_durability=5, current_durability=5, absorption=0,
            requirements="", outputs="2E", keywords="", text="",
            x=100, y=100, rotation=0, box=(100, 100, 144, 164)
        )
        bat2 = ComponentHealth(
            id="bat2", name="Battery 2E #2", card_type="component",
            max_durability=5, current_durability=5, absorption=0,
            requirements="", outputs="2E", keywords="", text="",
            x=300, y=100, rotation=0, box=(300, 100, 344, 164)
        )
        # m1 and m2 are weapon motors (cat_pri = 1)
        m1 = ComponentHealth(
            id="m1", name="Weapon Motor 1", card_type="component",
            max_durability=3, current_durability=3, absorption=0,
            requirements="2E", outputs="4W", keywords="", text="",
            x=50, y=200, rotation=0, box=(50, 200, 94, 264)
        )
        m2 = ComponentHealth(
            id="m2", name="Weapon Motor 2", card_type="component",
            max_durability=3, current_durability=3, absorption=0,
            requirements="2E", outputs="4W", keywords="", text="",
            x=150, y=200, rotation=0, box=(150, 200, 194, 264)
        )
        # m3 is drive motor (cat_pri = 0)
        m3 = ComponentHealth(
            id="m3", name="Drive Motor 3", card_type="component",
            max_durability=3, current_durability=3, absorption=0,
            requirements="2E", outputs="D", keywords="", text="",
            x=350, y=200, rotation=0, box=(350, 200, 394, 264)
        )

        robot = RobotState(
            id="tree_bot", name="Tree Bot", chassis_name="Square", chassis_template="Square",
            flip_strength=3, pose=Pose(400, 400, 0),
            components={"bat1": bat1, "bat2": bat2, "m1": m1, "m2": m2, "m3": m3},
            connections={},
            supply_graph={
                "bat1": [],
                "bat2": [],
                "m1": ["bat1", "bat2"],
                "m2": ["bat1", "bat2"],
                "m3": ["bat2"],
            },
            reverse_supply={},
        )

        refresh_robot_drive_and_power(robot)
        # Drive (m3) has higher priority than weapon motors (m1, m2), so m3 must be active!
        self.assertTrue(robot.components["m3"].is_active, "Drive motor m3 must be prioritized")
        # One weapon motor gets remaining 2E from bat1, the other is unpowered
        active_weapons = [cid for cid in ["m1", "m2"] if robot.components[cid].is_active]
        self.assertEqual(len(active_weapons), 1, "Exactly one of m1 or m2 should be active")

    def test_judges_decision_destroyed_and_damaged_counts(self):
        from playtest.engine.match import execute_turn
        from playtest.engine.types import MoveChoice
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        match.round = 10  # simulate final round

        # Scenario 1: Player has 0 destroyed, 2 damaged. Automaton has 1 destroyed, 0 damaged.
        # Player must win because fewer cards were destroyed (0 vs 1).
        p_comps = list(match.player_robot.components.values())
        a_comps = list(match.automaton_robot.components.values())

        p_comps[0].is_damaged = True
        p_comps[1].is_damaged = True

        a_comps[0].is_destroyed = True

        execute_turn(match, MoveChoice(left=0, right=0), fixed_automaton_roll=1)

        self.assertEqual(match.phase, "game_over")
        self.assertEqual(match.winner, "player")
        self.assertIn("Judge's Decision", match.win_reason)
        self.assertIn("0 destroyed, 2 damaged vs 1 destroyed, 0 damaged", match.win_reason)
        self.assertNotIn("durability", match.win_reason.lower())

    def test_judges_decision_damaged_tiebreaker(self):
        from playtest.engine.match import execute_turn
        from playtest.engine.types import MoveChoice
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        match.round = 10

        p_comps = list(match.player_robot.components.values())
        a_comps = list(match.automaton_robot.components.values())

        # Tied on destroyed (1 each), but automaton has more damaged (2 vs 1)
        p_comps[0].is_destroyed = True
        p_comps[1].is_damaged = True

        a_comps[0].is_destroyed = True
        a_comps[1].is_damaged = True
        a_comps[2].is_damaged = True

        execute_turn(match, MoveChoice(left=0, right=0), fixed_automaton_roll=1)

        self.assertEqual(match.phase, "game_over")
        self.assertEqual(match.winner, "player")
        self.assertIn("Judge's Decision", match.win_reason)
        self.assertIn("1 destroyed, 1 damaged vs 1 destroyed, 2 damaged", match.win_reason)

    def test_judges_decision_exact_tie(self):
        from playtest.engine.match import execute_turn
        from playtest.engine.types import MoveChoice
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        match.round = 10

        p_comps = list(match.player_robot.components.values())
        a_comps = list(match.automaton_robot.components.values())

        p_comps[0].is_destroyed = True
        p_comps[1].is_damaged = True

        a_comps[0].is_destroyed = True
        a_comps[1].is_damaged = True

        execute_turn(match, MoveChoice(left=0, right=0), fixed_automaton_roll=1)

        self.assertEqual(match.phase, "game_over")
        self.assertEqual(match.winner, "draw")
        self.assertIn("Exact tie", match.win_reason)

    def test_large_circle_template_geometry(self):
        from playtest.engine.field import get_weapon_template_geometry
        geom = get_weapon_template_geometry("Large Circle", (5.0, -10.0))
        self.assertEqual(geom["type"], "circle")
        self.assertEqual(geom["radius"], 30.0)
        self.assertEqual(geom["center"], (5.0, -10.0))

    def test_defeat_rule_invert_and_self_right(self):
        from playtest.engine.match import is_robot_defeated, can_robot_uninvert_to_regain_drive
        csv_text = read_saved_robot("Vyper_flipper.csv")
        match = create_match(csv_text, "Vyper_Spinner", "Player Bot")
        bot = match.player_robot

        # Initial state: upright, has active drive -> NOT defeated
        self.assertFalse(is_robot_defeated(bot))

        # Invert the robot
        bot.is_inverted = True

        # Destroy invertible wheels so drive is 0 while inverted
        for comp in bot.components.values():
            if "invertible" in comp.keywords.lower():
                comp.is_destroyed = True

        from playtest.engine.combat import refresh_robot_drive_and_power
        refresh_robot_drive_and_power(bot)

        # Drive is now 0 while inverted
        self.assertEqual(bot.left_drive_max, 0)
        self.assertEqual(bot.right_drive_max, 0)

        # But it has Self-right on lifter and would have drive when upright -> NOT defeated!
        self.assertTrue(can_robot_uninvert_to_regain_drive(bot))
        self.assertFalse(is_robot_defeated(bot))

        # Now destroy the self-righting weapon/component
        for comp in bot.components.values():
            if "self-right" in comp.keywords.lower():
                comp.is_destroyed = True

        # Now it has no way to uninvert itself to regain drive -> IS defeated!
        self.assertFalse(can_robot_uninvert_to_regain_drive(bot))
        self.assertTrue(is_robot_defeated(bot))

    def test_automata_rush_turns_to_face_opponent_behind(self):
        from playtest.engine.automata import compute_automaton_drive
        csv_text = read_saved_robot("Vyper_flipper.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        auto_bot = match.automaton_robot
        p_bot = match.player_robot

        # Position automaton at (400, 400) facing North (theta = 0 deg)
        auto_bot.pose = Pose(x=400.0, y=400.0, theta=0.0)
        # Position player behind automaton at (400, 600 - South, theta=0)
        p_bot.pose = Pose(x=400.0, y=600.0, theta=0.0)

        # Automaton is facing North, opponent is to the South (behind it, bearing ~ 180 degrees)
        # On "Rush", it should turn around to face the player instead of driving away!
        choice = compute_automaton_drive(auto_bot, p_bot, "Rush")
        # A turn to face them means asymmetric drive (spin or pivot, where left != right)
        self.assertNotEqual(choice.left, choice.right, "Automaton should turn (spin/pivot) to face opponent behind")

    def test_match_records_weight_and_cost(self):
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        self.assertGreater(match.player_robot.total_weight, 0)
        self.assertGreater(match.player_robot.total_cost, 0)
        self.assertGreater(match.automaton_robot.total_weight, 0)
        self.assertGreater(match.automaton_robot.total_cost, 0)
        d = match.player_robot.to_dict()
        self.assertIn("total_weight", d)
        self.assertIn("total_cost", d)

    def test_integer_damage_progression_and_feedback_rounding(self):
        from playtest.engine.combat import resolve_inward_damage_progression, resolve_feedback_propagation
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        bot = match.player_robot

        # Ensure feedback on a component supplying two consumers splits rounding down
        comp = list(bot.components.values())[0]
        # Feedback of 7 split between 2 suppliers = 7 // 2 = 3 each
        logs = resolve_feedback_propagation(bot, comp.id, 7)
        self.assertIsInstance(logs, list)

        # Test inward damage progression with integer arithmetic
        inward_logs = resolve_inward_damage_progression(bot, comp.id, 9)
        self.assertIsInstance(inward_logs, list)

    def test_throw_damage_halved_unless_wall_hit(self):
        from playtest.engine.combat import resolve_collision_combat
        from playtest.engine.types import CollisionEvent
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        # Place robots in center, far from walls (e.g. 400, 400)
        p_bot.pose = Pose(x=400.0, y=400.0, theta=0.0)
        a_bot.pose = Pose(x=400.0, y=360.0, theta=180.0)

        # Identify weapon component on p_bot and configure 5W throw weapon
        weapon_comps = [c for c in p_bot.components.values() if c.card_type == "weapon"]
        self.assertGreater(len(weapon_comps), 0)
        w_comp = weapon_comps[0]
        w_comp.outputs = "5W"
        w_comp.text = "Deals no damage."

        # Non-wedge component on opponent (battery)
        non_wedge_cid = [cid for cid, c in a_bot.components.items() if not c.is_wedge][0]

        # Contact event where p_bot weapon actively hits opponent
        col = CollisionEvent(
            time_t=0.5,
            contact_point=(400.0, 380.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=[w_comp.id],
            robot2_components=[non_wedge_cid],
            contact_type="ACTIVE",
            description="Active strike",
            r1_remaining_dist=0.0,
            r2_remaining_dist=0.0,
            push_vector=(0.0, -10.0),
            r1_active_hit=True,
            r2_active_hit=False,
        )

        # Case 1: Thrown clear of wall -> takes half throw damage (5 // 2 = 2)
        with patch("random.randint", return_value=1): # 1+1 = 2 roll
            logs = resolve_collision_combat(col, p_bot, a_bot, round_num=1)
            thrown_logs = [l.message for l in logs if "THROWN" in l.message]
            self.assertTrue(any("takes half throw damage 2" in msg for msg in thrown_logs))

        # Case 2: Thrown near wall (target lands <= 20mm from wall) -> takes full throw damage (5)
        # Position victim close to top wall (y=25) so thrown displacement hits the wall
        a_bot.pose = Pose(x=400.0, y=25.0, theta=180.0)
        p_bot.pose = Pose(x=400.0, y=50.0, theta=0.0)
        col.contact_point = (400.0, 45.0)
        with patch("random.randint", return_value=3): # 3+3 = 6 roll
            logs_wall = resolve_collision_combat(col, p_bot, a_bot, round_num=1)
            wall_logs = [l.message for l in logs_wall if "THROWN into a WALL" in l.message]
            self.assertTrue(any("takes full throw damage 5" in msg for msg in wall_logs))

    def test_active_contact_still_in_contact_proceeds_to_inertial_and_rotates(self):
        from playtest.engine.combat import resolve_collision_combat
        from playtest.engine.types import CollisionEvent
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        # Position touching at center
        p_bot.pose = Pose(x=400.0, y=410.0, theta=0.0)
        a_bot.pose = Pose(x=400.0, y=380.0, theta=180.0)

        # Configure weapon with 5 attack strength
        w_comp = [c for c in p_bot.components.values() if c.card_type == "weapon"][0]
        w_comp.outputs = "5W"
        w_comp.text = "Deals no damage."

        # Opponent component contacted is a Wedge! (Titanium Wedge)
        # The wedge keyword prevents the opponent from being thrown!
        wedge_cid = [cid for cid, c in a_bot.components.items() if c.is_wedge][0]

        col = CollisionEvent(
            time_t=0.5,
            contact_point=(400.0, 395.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=[w_comp.id],
            robot2_components=[wedge_cid],
            contact_type="ACTIVE",
            description="Active strike into wedge",
            r1_remaining_dist=20.0,
            r2_remaining_dist=20.0,
            push_vector=(0.0, -10.0),
            r1_active_hit=True,
            r2_active_hit=False,
        )

        orig_p_theta = p_bot.pose.theta
        orig_a_theta = a_bot.pose.theta

        logs = resolve_collision_combat(col, p_bot, a_bot, round_num=1)
        log_messages = [l.message for l in logs]

        # 1. Active contact occurred
        self.assertTrue(any("ACTIVE WEAPON HIT" in msg for msg in log_messages))
        # 2. Wedge prevented throw
        self.assertTrue(any("is not thrown" in msg for msg in log_messages))
        # 3. Because robots remain in contact, inertial contact proceeded
        self.assertTrue(any("proceeding with inertial contact" in msg for msg in log_messages))
        # 4. Pushing match occurred
        self.assertTrue(any("PUSHING MATCH" in msg for msg in log_messages))
        # 5. At the end of inertial contact, both robots rotated a random amount
        self.assertTrue(any("End of inertial contact: both robots are rotated a random amount" in msg for msg in log_messages))
        self.assertNotEqual(p_bot.pose.theta, orig_p_theta)
        self.assertNotEqual(a_bot.pose.theta, orig_a_theta)

    def test_active_contact_thrown_clear_does_not_proceed_to_inertial(self):
        from playtest.engine.combat import resolve_collision_combat
        from playtest.engine.types import CollisionEvent
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        p_bot.pose = Pose(x=400.0, y=410.0, theta=0.0)
        a_bot.pose = Pose(x=400.0, y=380.0, theta=180.0)

        w_comp = [c for c in p_bot.components.values() if c.card_type == "weapon"][0]
        w_comp.outputs = "8W"
        w_comp.text = "Deals no damage."

        # Opponent component is NOT a wedge (battery)
        non_wedge_cid = [cid for cid, c in a_bot.components.items() if not c.is_wedge][0]

        col = CollisionEvent(
            time_t=0.5,
            contact_point=(400.0, 395.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=[w_comp.id],
            robot2_components=[non_wedge_cid],
            contact_type="ACTIVE",
            description="Active strike into battery",
            r1_remaining_dist=20.0,
            r2_remaining_dist=20.0,
            push_vector=(0.0, -10.0),
            r1_active_hit=True,
            r2_active_hit=False,
        )

        # Throw roll is high (6+6 = 12 -> 8 units / 320mm displacement away!)
        with patch("random.randint", return_value=6):
            logs = resolve_collision_combat(col, p_bot, a_bot, round_num=1)
            log_messages = [l.message for l in logs]

            # Robot was thrown away
            self.assertTrue(any("is THROWN" in msg for msg in log_messages))
            # Did NOT proceed to inertial contact
            self.assertFalse(any("proceeding with inertial contact" in msg for msg in log_messages))


if __name__ == "__main__":
    unittest.main()


