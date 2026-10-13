"""Unit tests for the playtest rules engine."""

import random
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
    start_of_turn_spin_up,
)
from playtest.engine.match import build_robot_state, create_match, execute_turn
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

        # Charged Vyper_Spinner: 1 = Face, 2 = Evade, 3..6 = Rush
        self.assertEqual(get_automaton_action("Vyper_Spinner", robot, 1), "Face")
        self.assertEqual(get_automaton_action("Vyper_Spinner", robot, 2), "Evade")
        self.assertEqual(get_automaton_action("Vyper_Spinner", robot, 3), "Rush")
        self.assertEqual(get_automaton_action("Vyper_Spinner", robot, 6), "Rush")

        # Uncharged Vyper_Spinner: spin counters < 2
        robot.weapon_spin_counters["w"] = 0
        self.assertEqual(get_automaton_action("Vyper_Spinner", robot, 1), "Retreat")
        self.assertEqual(get_automaton_action("Vyper_Spinner", robot, 2), "Retreat")
        self.assertEqual(get_automaton_action("Vyper_Spinner", robot, 3), "Face")
        self.assertEqual(get_automaton_action("Vyper_Spinner", robot, 4), "Evade")
        self.assertEqual(get_automaton_action("Vyper_Spinner", robot, 5), "Evade")
        self.assertEqual(get_automaton_action("Vyper_Spinner", robot, 6), "Rush")

        # Vyper_flipper (Full Rush): 1 = Retreat, 2 = Face, 3 = Evade, 4..6 = Rush
        self.assertEqual(get_automaton_action("Vyper_flipper", robot, 1), "Retreat")
        self.assertEqual(get_automaton_action("Vyper_flipper", robot, 2), "Face")
        self.assertEqual(get_automaton_action("Vyper_flipper", robot, 3), "Evade")
        self.assertEqual(get_automaton_action("Vyper_flipper", robot, 4), "Rush")
        self.assertEqual(get_automaton_action("Vyper_flipper", robot, 6), "Rush")

        # Chonk (Spin Up):
        # Charged (>= 2)
        robot.weapon_spin_counters["w"] = 2
        self.assertEqual(get_automaton_action("Chonk", robot, 1), "Face")
        self.assertEqual(get_automaton_action("Chonk", robot, 2), "Evade")
        self.assertEqual(get_automaton_action("Chonk", robot, 3), "Rush")
        self.assertEqual(get_automaton_action("Chonk", robot, 6), "Rush")
        # Uncharged (< 2)
        robot.weapon_spin_counters["w"] = 1
        self.assertEqual(get_automaton_action("Chonk", robot, 1), "Retreat")
        self.assertEqual(get_automaton_action("Chonk", robot, 2), "Retreat")
        self.assertEqual(get_automaton_action("Chonk", robot, 3), "Face")
        self.assertEqual(get_automaton_action("Chonk", robot, 4), "Evade")
        self.assertEqual(get_automaton_action("Chonk", robot, 5), "Evade")
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

        # Sub-spin (< 3): 1 = Retreat, 2..3 = Evade, 4 = Face, 5..6 = Rush
        robot.weapon_spin_counters = {"16": 1}
        self.assertEqual(get_automaton_action("Beater_wide", robot, 1), "Retreat")
        self.assertEqual(get_automaton_action("Beater_wide", robot, 2), "Evade")
        self.assertEqual(get_automaton_action("Beater_wide", robot, 3), "Evade")
        self.assertEqual(get_automaton_action("Beater_wide", robot, 4), "Face")
        self.assertEqual(get_automaton_action("Beater_wide", robot, 5), "Rush")
        self.assertEqual(get_automaton_action("Beater_wide", robot, 6), "Rush")

        # Full-spin (>= 3): 1 = Retreat, 2 = Face, 3 = Evade, 4..6 = Rush
        robot.weapon_spin_counters = {"16": 3}
        self.assertEqual(get_automaton_action("Beater_wide", robot, 1), "Retreat")
        self.assertEqual(get_automaton_action("Beater_wide", robot, 2), "Face")
        self.assertEqual(get_automaton_action("Beater_wide", robot, 3), "Evade")
        self.assertEqual(get_automaton_action("Beater_wide", robot, 4), "Rush")
        self.assertEqual(get_automaton_action("Beater_wide", robot, 6), "Rush")

        # Nightwing_wide behaves identically under Balanced archetype
        self.assertEqual(get_automaton_action("Nightwing_wide", robot, 2), "Face")
        self.assertEqual(get_automaton_action("Nightwing_wide", robot, 3), "Evade")
        self.assertEqual(get_automaton_action("Nightwing_wide", robot, 5), "Rush")

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

        # Evade when already facing perpendicular (facing East = 90 deg)
        automaton_east = RobotState(
            id="a", name="Auto", chassis_name="", chassis_template="Triangle",
            flip_strength=5, pose=Pose(400, 200, 90), components={}, connections={},
            supply_graph={}, reverse_supply={}, left_drive_max=3, right_drive_max=3
        )
        drive_evade = compute_automaton_drive(automaton_east, player, "Evade", evade_direction="left")
        # Moving straight forward along the perpendicular heading (East)
        self.assertEqual(drive_evade.left, 3)
        self.assertEqual(drive_evade.right, 3)

        # Evade against left wall (x = 140, near WALL_LEFT=100) -> must evade right (East)
        automaton_near_left = RobotState(
            id="a", name="Auto", chassis_name="", chassis_template="Triangle",
            flip_strength=5, pose=Pose(140, 200, 90), components={}, connections={},
            supply_graph={}, reverse_supply={}, left_drive_max=3, right_drive_max=3
        )
        drive_evade_wall = compute_automaton_drive(automaton_near_left, player, "Evade")
        self.assertEqual(drive_evade_wall.left, 3)
        self.assertEqual(drive_evade_wall.right, 3)

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

        # Boundary test: incoming damage >= half durability (ignoring absorption) -> DAMAGED
        tire = ComponentHealth(
            id="2", name="High Grip Tires", card_type="component", max_durability=6,
            current_durability=6, absorption=1, requirements="", outputs="", keywords="",
            text="", x=0, y=0, rotation=0, box=(0, 0, 44, 64)
        )
        # Incoming 2: 2 < 6/2 (3.0) -> UNDAMAGED
        st2, abs2, ex2 = apply_damage_to_component(tire, 2.0, is_weapon_damage=True)
        self.assertEqual(st2, "UNDAMAGED")
        self.assertEqual(abs2, 1.0)
        self.assertEqual(ex2, 1.0)
        self.assertFalse(tire.is_damaged)

        # Incoming 3: 3 >= 6/2 (3.0) -> DAMAGED (ignores absorption)
        st3, abs3, ex3 = apply_damage_to_component(tire, 3.0, is_weapon_damage=True)
        self.assertEqual(st3, "DAMAGED")
        self.assertEqual(abs3, 1.0)
        self.assertEqual(ex3, 2.0)
        self.assertTrue(tire.is_damaged)

    def test_match_completion_20_rounds(self):
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player")

        # Step 20 rounds of stationary / passive moves
        for r in range(1, 21):
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
        # Inertial separation moves both robots 1 step away from each other
        self.assertTrue(any("Inertial separation" in entry.message for entry in logs))
        self.assertEqual(p_bot.pose.y, 660.0)
        self.assertEqual(a_bot.pose.y, 135.0)  # Clamped to WALL_TOP + MINIATURE_RADIUS (100 + 35)

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

    def test_wedge_keyword_when_raised_does_not_prevent_throw(self):
        from playtest.engine.combat import resolve_collision_combat
        from playtest.engine.types import CollisionEvent
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        # Ensure player robot has a wedge component hit, but is raised!
        wedge_comp = ComponentHealth(
            id="wedge_1", name="Titanium Wedge", card_type="component",
            max_durability=9, current_durability=9, absorption=1, requirements="",
            outputs="", keywords="wedge", text="", x=100, y=20, rotation=0,
            box=(100, 20, 144, 84), is_wedge=True,
        )
        p_bot.components["wedge_1"] = wedge_comp
        p_bot.is_raised = True

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
            description="Active strike hitting raised wedge",
            r1_active_hit=False,
            r2_active_hit=True,
        )
        logs = resolve_collision_combat(col, p_bot, a_bot, 1)
        # Wedge was hit, but p_bot is raised: Wedge effect does NOT apply, so p_bot IS thrown!
        self.assertTrue(any("Wedge effect does not apply" in entry.message for entry in logs))
        self.assertTrue(any(f"{p_bot.name} is THROWN" in entry.message for entry in logs))

    def test_split_supply_distribution(self):
        """
        Verify the rule:
        - When supply is insufficient to power all connected components:
          - The player can choose which components get supplied each turn during the planning phase.
          - Automaton chooses in order: self-righting (if inverted), then weapons, then drive.
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

        # 1. Player choice: Player chooses drive
        refresh_robot_drive_and_power(robot, chosen_components=["m_left"])
        self.assertTrue(robot.components["bat"].is_active)
        self.assertTrue(robot.components["m_left"].is_active, "Drive should be supplied when chosen by player")
        self.assertFalse(robot.components["wep"].is_active, "Weapon should be unpowered due to 2E supply limit")
        self.assertEqual(robot.left_drive_max, 1)

        # 2. Player choice: Player chooses weapon
        refresh_robot_drive_and_power(robot, chosen_components=["wep"])
        self.assertTrue(robot.components["bat"].is_active)
        self.assertFalse(robot.components["m_left"].is_active, "Drive should be unpowered")
        self.assertTrue(robot.components["wep"].is_active, "Weapon should be powered when chosen by player")
        self.assertEqual(robot.left_drive_max, 0)

        # 3. Automaton order (when upright): weapons then drive
        refresh_robot_drive_and_power(robot, is_automaton=True)
        self.assertTrue(robot.components["bat"].is_active)
        self.assertTrue(robot.components["wep"].is_active, "Automaton prioritizes weapons over drive when upright")
        self.assertFalse(robot.components["m_left"].is_active, "Drive should be unpowered for automaton")

        # 4. Automaton order (when inverted with self-righting): self-righting first
        sr_arm = ComponentHealth(
            id="sr", name="Self Righting Arm", card_type="component",
            max_durability=3, current_durability=3, absorption=0,
            requirements="2E", outputs="", keywords="Self-right", text="",
            x=200, y=300, rotation=0, box=(200, 300, 244, 364)
        )
        robot.components["sr"] = sr_arm
        robot.supply_graph["sr"] = ["bat"]
        robot.reverse_supply["bat"].append("sr")
        robot.is_inverted = True

        refresh_robot_drive_and_power(robot, is_automaton=True)
        self.assertTrue(robot.components["sr"].is_active, "Automaton prioritizes self-righting when inverted")
        self.assertFalse(robot.components["wep"].is_active, "Weapon unpowered because self-righting took the 2E")
        self.assertFalse(robot.components["m_left"].is_active, "Drive unpowered")

        # 5. Sufficient power: Battery upgraded to 6E -> all are supplied
        battery.outputs = "6E"
        refresh_robot_drive_and_power(robot)
        self.assertTrue(robot.components["m_left"].is_active)
        self.assertTrue(robot.components["wep"].is_active)
        self.assertTrue(robot.components["sr"].is_active)

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
        - Player can choose m3 (drive) and m1 (weapon) to stay active.
        - Automaton prioritizes weapons (m1, m2) over drive (m3).
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
        # m1 and m2 are weapon motors
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
        # m3 is drive motor
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

        # 1. Player explicitly chooses m3 (drive) and m1 (weapon)
        refresh_robot_drive_and_power(robot, chosen_components=["m3", "m1"])
        self.assertTrue(robot.components["m3"].is_active, "Drive motor m3 must be active when chosen")
        self.assertTrue(robot.components["m1"].is_active, "Weapon motor m1 must be active when chosen")
        self.assertFalse(robot.components["m2"].is_active, "Weapon motor m2 must be unpowered")

        # 2. Automaton prioritizes weapons (m1, m2) over drive (m3)
        refresh_robot_drive_and_power(robot, is_automaton=True)
        self.assertTrue(robot.components["m1"].is_active, "Automaton prioritizes weapons")
        self.assertTrue(robot.components["m2"].is_active, "Automaton prioritizes weapons")
        self.assertFalse(robot.components["m3"].is_active, "Drive motor m3 unpowered for automaton")

    def test_judges_decision_destroyed_and_damaged_counts(self):
        from playtest.engine.match import execute_turn
        from playtest.engine.types import MoveChoice
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        match.round = match.max_rounds  # simulate final round

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
        match.round = match.max_rounds

        # Pick non-vital components (wedges, armor, weapons, servos) so drive and power remain intact
        p_comps = [c for c in match.player_robot.components.values() if not any(k in c.name.lower() for k in ("wheel", "motor", "galaxy", "tattu", "gnb", "battery"))]
        a_comps = [c for c in match.automaton_robot.components.values() if not any(k in c.name.lower() for k in ("wheel", "motor", "galaxy", "tattu", "gnb", "battery"))]

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
        match.round = match.max_rounds

        p_comps = [c for c in match.player_robot.components.values() if not any(k in c.name.lower() for k in ("wheel", "motor", "galaxy", "tattu", "gnb", "battery"))]
        a_comps = [c for c in match.automaton_robot.components.values() if not any(k in c.name.lower() for k in ("wheel", "motor", "galaxy", "tattu", "gnb", "battery"))]

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

    def test_active_contact_still_in_contact_proceeds_to_inertial(self):
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
        # 5. Random rotation after inertial contact was removed
        self.assertFalse(any("rotated a random amount" in msg for msg in log_messages))
        self.assertEqual(p_bot.pose.theta, orig_p_theta)
        self.assertEqual(a_bot.pose.theta, orig_a_theta)
        # 6. Inertial separation occurred
        self.assertTrue(any("Inertial separation" in msg for msg in log_messages))

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

    def test_inertial_separation_wall_clamped(self):
        """Tests that inertial separation respects arena boundary walls ('if possible')."""
        from playtest.engine.combat import resolve_collision_combat
        from playtest.engine.types import CollisionEvent
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        # p_bot is close to left wall: WALL_LEFT is 100, min robot x is 135 (WALL_LEFT + MINIATURE_RADIUS 35)
        p_bot.pose = Pose(x=145.0, y=400.0, theta=0.0)
        a_bot.pose = Pose(x=175.0, y=400.0, theta=180.0)

        col = CollisionEvent(
            time_t=0.5,
            contact_point=(160.0, 400.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=[list(p_bot.components.keys())[0]],
            robot2_components=[list(a_bot.components.keys())[0]],
            contact_type="INERT",
            description="Pushing match near wall",
            r1_remaining_dist=0.0,
            r2_remaining_dist=0.0,
            push_vector=(0.0, 0.0),
        )

        logs = resolve_collision_combat(col, p_bot, a_bot, round_num=1)
        # p_bot tries to move left (-x) by 40mm: 145 - 40 = 105, clamped to 135 (only 10mm moved)
        self.assertEqual(p_bot.pose.x, 135.0)
        # a_bot moves right (+x) by 40mm: 175 + 40 = 215 (well within bounds)
        self.assertEqual(a_bot.pose.x, 215.0)
        self.assertTrue(any("Inertial separation" in entry.message for entry in logs))

    def test_configurable_playcount_in_engine(self):
        """Tests that the simulator playcount (max rounds) can be configured for dev purposes."""
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        # Initialize match with 3 rounds max
        match = create_match(csv_text, "Vyper_flipper", "Player Bot", max_rounds=3)
        self.assertEqual(match.max_rounds, 3)
        self.assertEqual(match.round, 1)
        self.assertTrue(any("3 rounds max" in e.message for e in match.log))

        # Round 1 -> Round 2
        match = execute_turn(match, MoveChoice(0, 0), fixed_automaton_roll=1)
        self.assertEqual(match.round, 2)
        self.assertEqual(match.phase, "planning")

        # Round 2 -> Round 3
        match = execute_turn(match, MoveChoice(0, 0), fixed_automaton_roll=1)
        self.assertEqual(match.round, 3)
        self.assertEqual(match.phase, "planning")

        # Round 3 -> Reaches max_rounds=3 -> game_over (Judge's Decision)
        match = execute_turn(match, MoveChoice(0, 0), fixed_automaton_roll=1)
        self.assertEqual(match.round, 3)
        self.assertEqual(match.phase, "game_over")
        self.assertIn("Judge's Decision", match.win_reason)

    def test_movement_template_metadata_in_match(self):
        """Tests that execute_turn generates template metadata for both player and automaton."""
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot", max_rounds=5)

        # Player chooses straight (2, 2)
        match = execute_turn(match, MoveChoice(2, 2), fixed_automaton_roll=2)
        self.assertIsNotNone(match.player_template)
        self.assertEqual(match.player_template["template_id"], "straight")
        self.assertEqual(match.player_template["category"], "straight")
        self.assertEqual(match.player_template["canonical_left"], 2)
        self.assertEqual(match.player_template["canonical_right"], 2)
        self.assertIn("pairs", match.player_template)
        self.assertIn((2, 2), match.player_template["pairs"])

        self.assertIsNotNone(match.automaton_template)
        self.assertIn("template_id", match.automaton_template)
        self.assertIn("category", match.automaton_template)

        # MatchState serialization includes template info
        m_dict = match.to_dict()
        self.assertIn("player_template", m_dict)
        self.assertIn("automaton_template", m_dict)
        self.assertEqual(m_dict["player_template"]["template_id"], "straight")

    def test_damage_steps_recording_in_active_combat(self):
        """Tests that damage_steps records structured steps during active weapon clash."""
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        p_bot = build_robot_state(csv_text, "player", "Player Bot", (400.0, 420.0, 0.0))
        a_bot = build_robot_state(csv_text, "automaton", "Auto Bot", (400.0, 380.0, 180.0))

        p_w = [c for c in p_bot.components.values() if c.card_type == "weapon"][0]
        p_bot.weapon_spin_counters[p_w.id] = 3
        p_w.spin_counters = 3

        a_cids = list(a_bot.components.keys())

        col = CollisionEvent(
            time_t=0.5,
            contact_point=(400.0, 400.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=[p_w.id],
            robot2_components=[a_cids[0]],
            contact_type="ACTIVE",
            description="Active strike on opponent",
            r1_active_hit=True,
            r2_active_hit=False,
        )

        steps = []
        logs = resolve_collision_combat(col, p_bot, a_bot, round_num=1, steps=steps)
        self.assertTrue(len(steps) > 0)
        # Verify first step is damage on opponent
        dmg_step = steps[0]
        self.assertEqual(dmg_step.phase, "damage")
        self.assertEqual(dmg_step.robot_id, "automaton")
        self.assertEqual(dmg_step.target_cid, a_cids[0])
        self.assertIsNone(dmg_step.from_cid)
        self.assertTrue(dmg_step.amount > 0)
        self.assertIn(dmg_step.new_status, ("UNDAMAGED", "DAMAGED", "DESTROYED"))

        # Verify recoil feedback step occurred on player weapon
        recoil_steps = [s for s in steps if s.phase == "recoil_feedback"]
        self.assertTrue(len(recoil_steps) > 0)
        self.assertEqual(recoil_steps[0].robot_id, "player")
        self.assertEqual(recoil_steps[0].target_cid, p_w.id)

    def test_default_turn_count_20_in_engine(self):
        """Rule: Match length defaults to 20 rounds."""
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        self.assertEqual(match.max_rounds, 20)
        self.assertEqual(match.round, 1)

    def test_spin_up_counters_removed_when_weapon_becomes_inactive(self):
        """Rule: If the weapon becomes inactive all counters are removed."""
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        bot = match.player_robot

        # Find spinner weapon
        spin_weapons = [c for c in bot.components.values() if "spin up" in c.keywords.lower()]
        self.assertTrue(len(spin_weapons) > 0)
        weapon = spin_weapons[0]

        # Give the weapon 3 spin counters
        bot.weapon_spin_counters[weapon.id] = 3
        weapon.spin_counters = 3

        # Case 1: Weapon is active and powered -> counters preserved
        refresh_robot_drive_and_power(bot)
        self.assertTrue(weapon.is_active)
        self.assertEqual(bot.weapon_spin_counters[weapon.id], 3)
        self.assertEqual(weapon.spin_counters, 3)

        # Case 2: Upstream power is destroyed -> weapon becomes inactive -> counters removed!
        suppliers = bot.supply_graph.get(weapon.id, [])
        for sid in suppliers:
            bot.components[sid].is_destroyed = True

        refresh_robot_drive_and_power(bot)
        self.assertFalse(weapon.is_active)
        self.assertEqual(bot.weapon_spin_counters[weapon.id], 0)
        self.assertEqual(weapon.spin_counters, 0)

        # Case 3: Start of turn spin up does not add counters to inactive weapon
        spin_logs = start_of_turn_spin_up(bot)
        self.assertEqual(len(spin_logs), 0)
        self.assertEqual(bot.weapon_spin_counters[weapon.id], 0)
        self.assertEqual(weapon.spin_counters, 0)

        # Case 4: Weapon itself destroyed -> counters removed
        weapon.is_destroyed = True
        refresh_robot_drive_and_power(bot)
        self.assertEqual(bot.weapon_spin_counters[weapon.id], 0)
        self.assertEqual(weapon.spin_counters, 0)

    def test_wedge_only_hit_if_component_being_hit(self):
        """Rule: A wedge is only hit if it is the component being hit (taking damage)."""
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        p_bot.pose = Pose(x=400.0, y=410.0, theta=0.0)
        a_bot.pose = Pose(x=400.0, y=380.0, theta=180.0)

        w_comp = [c for c in p_bot.components.values() if c.card_type == "weapon"][0]
        w_comp.outputs = "5W"
        w_comp.text = ""

        wedge_cids = [cid for cid, c in a_bot.components.items() if c.is_wedge]
        non_wedge_cids = [cid for cid, c in a_bot.components.items() if not c.is_wedge and "wheel" in c.name.lower()]
        self.assertTrue(len(wedge_cids) > 0)
        self.assertTrue(len(non_wedge_cids) > 0)

        wedge_id = wedge_cids[0]
        wheel_id = non_wedge_cids[0]

        # Case 1: Contact list on opponent includes both wheel and wedge on that side,
        # but the wheel is the component taking damage.
        # The wedge must NOT trigger: robot IS thrown!
        col1 = CollisionEvent(
            time_t=0.5,
            contact_point=(400.0, 395.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=[w_comp.id],
            robot2_components=[wheel_id, wedge_id],
            contact_type="ACTIVE",
            description="Active strike into wheel",
            r1_remaining_dist=0.0,
            r2_remaining_dist=0.0,
            push_vector=(0.0, -10.0),
            r1_active_hit=True,
            r2_active_hit=False,
        )

        orig_a_y = a_bot.pose.y
        logs1 = resolve_collision_combat(col1, p_bot, a_bot, round_num=1)
        log_msgs1 = [l.message for l in logs1]
        self.assertFalse(any("Wedge was hit —" in m for m in log_msgs1))
        self.assertTrue(any("THROWN" in m for m in log_msgs1))
        self.assertNotEqual(a_bot.pose.y, orig_a_y)

        # Reset opponent pose and player weapon spin
        a_bot.pose = Pose(x=400.0, y=380.0, theta=180.0)
        p_bot.weapon_spin_counters[w_comp.id] = 1
        w_comp.spin_counters = 1

        # Case 2: Contact is directly on the wedge itself (wedge takes the damage).
        # Wedge effect applies: robot is NOT thrown!
        col2 = CollisionEvent(
            time_t=0.5,
            contact_point=(400.0, 395.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=[w_comp.id],
            robot2_components=[wedge_id],
            contact_type="ACTIVE",
            description="Active strike into wedge",
            r1_remaining_dist=0.0,
            r2_remaining_dist=0.0,
            push_vector=(0.0, -10.0),
            r1_active_hit=True,
            r2_active_hit=False,
        )

        logs2 = resolve_collision_combat(col2, p_bot, a_bot, round_num=1)
        log_msgs2 = [l.message for l in logs2]
        self.assertTrue(any("Wedge was hit —" in m for m in log_msgs2))
        self.assertFalse(any("THROWN" in m for m in log_msgs2))
        self.assertTrue(any("Inertial separation" in m for m in log_msgs2))

    def test_weapon_damage_applies_only_to_contacted_component(self):
        """Rule: Weapon strike damage applies to just the one contacted component, while recoil feedback uses the chain."""
        from playtest.engine.types import DamageTrainStep
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        p_bot.pose = Pose(x=400.0, y=410.0, theta=0.0)
        a_bot.pose = Pose(x=400.0, y=380.0, theta=180.0)

        # Target on player: TPU Plate (connected to other components)
        plate_cids = [cid for cid, c in p_bot.components.items() if "plate" in c.name.lower() and len(p_bot.connections.get(cid, [])) > 0]
        self.assertTrue(len(plate_cids) > 0)
        target_armor_id = plate_cids[0]
        connected_to_armor = p_bot.connections.get(target_armor_id, [])
        self.assertTrue(len(connected_to_armor) > 0)

        # Configure automaton weapon with 20 attack strength
        a_w_comp = [c for c in a_bot.components.values() if c.card_type == "weapon"][0]
        a_w_comp.outputs = "20W"
        a_w_comp.keywords = "Spin up (2)"
        a_w_comp.text = ""
        a_bot.weapon_spin_counters[a_w_comp.id] = 1

        steps: list[DamageTrainStep] = []
        col = CollisionEvent(
            time_t=0.5,
            contact_point=(400.0, 395.0),
            robot1_octant="Rear",
            robot2_octant="Front",
            robot1_components=[target_armor_id],
            robot2_components=[a_w_comp.id],
            contact_type="ACTIVE",
            description="Active strike into armor",
            r1_remaining_dist=0.0,
            r2_remaining_dist=0.0,
            push_vector=(0.0, -10.0),
            r1_active_hit=False,
            r2_active_hit=True,
        )

        random.seed(42)
        logs = resolve_collision_combat(col, p_bot, a_bot, round_num=1, steps=steps)

        # 1. Target armor takes damage and is destroyed
        armor_comp = p_bot.components[target_armor_id]
        self.assertTrue(armor_comp.is_destroyed)

        # 2. Connected internal components do NOT take excess weapon damage
        for nid in connected_to_armor:
            ncomp = p_bot.components[nid]
            self.assertFalse(ncomp.is_destroyed, f"{ncomp.name} should not be destroyed by weapon damage")
            self.assertFalse(ncomp.is_damaged, f"{ncomp.name} should not be damaged by weapon damage")

        # 3. Only 1 damage step for player (no inward damage steps)
        p_damage_steps = [s for s in steps if s.robot_id == p_bot.id and s.phase == "damage"]
        self.assertEqual(len(p_damage_steps), 1)
        self.assertEqual(p_damage_steps[0].target_cid, target_armor_id)

        # 4. Attacking weapon took recoil feedback via supply chain (half of 20 = 10)
        recoil_steps = [s for s in steps if s.robot_id == a_bot.id and s.phase == "recoil_feedback"]
        self.assertGreater(len(recoil_steps), 0)

    def test_increases_throw_strength_by_2(self):
        """Rule: Weapon text 'Increases throw strength by 2' adds +2 to throw strength, not x2."""
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        p_bot.pose = Pose(x=400.0, y=410.0, theta=0.0)
        a_bot.pose = Pose(x=400.0, y=380.0, theta=180.0)

        # Configure player weapon with 4 attack strength and 'Increases throw strength by 2'
        w_comp = [c for c in p_bot.components.values() if c.card_type == "weapon"][0]
        w_comp.outputs = "4W"
        w_comp.keywords = "Spin up (2)"
        w_comp.text = "Increases throw strength by 2"
        p_bot.weapon_spin_counters[w_comp.id] = 1

        non_wedge = [cid for cid, c in a_bot.components.items() if not c.is_wedge and "wheel" in c.name.lower()][0]

        col = CollisionEvent(
            time_t=0.5,
            contact_point=(400.0, 395.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=[w_comp.id],
            robot2_components=[non_wedge],
            contact_type="ACTIVE",
            description="Active strike into wheel",
            r1_remaining_dist=0.0,
            r2_remaining_dist=0.0,
            push_vector=(0.0, -10.0),
            r1_active_hit=True,
            r2_active_hit=False,
        )

        logs = resolve_collision_combat(col, p_bot, a_bot, round_num=1)
        log_msgs = [l.message for l in logs]
        # Base 4 + 2 = 6 throw strength (not 4 * 2 = 8)
        self.assertTrue(any("THROWN! (Strength 6" in m for m in log_msgs))

    def test_reset_keyword_attack_and_supply_lifecycle(self):
        """
        Verify:
        1. Attacking triggers Reset.
        2. In the next turn, weapon is inactive while resetting.
        3. A component that is resetting needs to be supplied in order to reset.
        4. Once supplied for that turn, reset completes and weapon is active in the following turn.
        """
        from playtest.engine.match import execute_turn, create_match
        from playtest.engine.types import MoveChoice, CollisionEvent
        from playtest.engine.combat import resolve_collision_combat

        csv_text = read_saved_robot("Vyper_flipper.csv")
        match = create_match(csv_text, "Vyper_Spinner", "Player Flipper")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        # Four-Bar Lifter has Reset keyword
        lifter = next(c for c in p_bot.components.values() if "four-bar lifter" in c.name.lower())
        self.assertTrue(lifter.is_reset, "Four-Bar Lifter should have is_reset=True")
        self.assertFalse(lifter.is_resetting)
        self.assertTrue(lifter.is_active, "Lifter starts active")

        # 1. Trigger attack in collision
        col = CollisionEvent(
            time_t=0.5,
            contact_point=(200.0, 200.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=[lifter.id],
            robot2_components=[list(a_bot.components.keys())[0]],
            contact_type="ACTIVE",
            description="Lifter active strike",
            r1_active_hit=True,
            r2_active_hit=False,
        )
        resolve_collision_combat(col, p_bot, a_bot, round_num=1)
        self.assertTrue(lifter.was_used_this_turn, "Attacking triggers used")

        # Execute turn 1 cleanup to transition to turn 2
        # (simulate execute_turn's cleanup phase on turn 1)
        execute_turn(match, MoveChoice(0, 0))
        self.assertTrue(lifter.is_resetting, "Weapon transitions to is_resetting=True for turn after use")
        self.assertIn(lifter.id, p_bot.resetting_weapons)

        # In turn 2: Lifter is supplied, but is inactive (resetting)
        self.assertFalse(lifter.is_active, "Weapon is inactive during the turn after it is used")
        self.assertTrue(lifter.reset_supplied, "Lifter was supplied in turn 2 so it can reset")

        # Execute turn 2: at cleanup, because it received supply, it completes reset
        execute_turn(match, MoveChoice(0, 0))
        self.assertFalse(lifter.is_resetting, "Reset finishes after being supplied for the turn")
        self.assertNotIn(lifter.id, p_bot.resetting_weapons)
        self.assertTrue(lifter.is_active, "Lifter is now active again in subsequent round")

    def test_reset_keyword_not_supplied_remains_resetting(self):
        """
        Verify that a resetting component that is NOT supplied does not finish resetting.
        """
        from playtest.engine.match import execute_turn, create_match
        from playtest.engine.types import MoveChoice

        csv_text = read_saved_robot("Vyper_flipper.csv")
        match = create_match(csv_text, "Vyper_Spinner", "Player Flipper")
        p_bot = match.player_robot

        lifter = next(c for c in p_bot.components.values() if "four-bar lifter" in c.name.lower())
        lifter.is_resetting = True
        p_bot.resetting_weapons.append(lifter.id)

        # Destroy the servo supplying the lifter with pressure
        servo = next(c for c in p_bot.components.values() if "servo" in c.name.lower())
        servo.is_destroyed = True

        execute_turn(match, MoveChoice(0, 0))

        self.assertFalse(lifter.reset_supplied, "Lifter was not supplied because its supplier is destroyed")
        self.assertTrue(lifter.is_resetting, "Lifter remains resetting because it was not supplied")
        self.assertFalse(lifter.is_active, "Lifter remains inactive")

    def test_reset_keyword_player_choice_when_insufficient_supply(self):
        """
        When supply is insufficient to power all components, player choice determines
        whether the resetting component receives supply to reset or another component gets it.
        """
        from playtest.engine.combat import refresh_robot_drive_and_power
        from playtest.engine.types import ComponentHealth, RobotState, Pose

        battery = ComponentHealth(
            id="bat", name="Battery", card_type="component",
            max_durability=5, current_durability=5, absorption=0,
            requirements="", outputs="2E", keywords="", text="",
            x=200, y=200, rotation=0, box=(200, 200, 244, 264)
        )
        motor = ComponentHealth(
            id="m_left", name="Left Motor", card_type="component",
            max_durability=3, current_durability=3, absorption=0,
            requirements="2E", outputs="D", keywords="", text="",
            x=100, y=100, rotation=0, box=(100, 100, 144, 164)
        )
        reset_wep = ComponentHealth(
            id="wep", name="Reset Weapon", card_type="weapon",
            max_durability=4, current_durability=4, absorption=0,
            requirements="2E", outputs="4W", keywords="Reset", text="",
            x=210, y=50, rotation=0, box=(210, 50, 254, 114),
            is_reset=True, is_resetting=True,
        )
        robot = RobotState(
            id="test_bot", name="Test Bot", chassis_name="Square", chassis_template="Square",
            flip_strength=3, pose=Pose(400, 400, 0),
            components={"bat": battery, "m_left": motor, "wep": reset_wep},
            connections={"bat": ["m_left", "wep"], "m_left": ["bat"], "wep": ["bat"]},
            supply_graph={"m_left": ["bat"], "wep": ["bat"], "bat": []},
            reverse_supply={"bat": ["m_left", "wep"], "m_left": [], "wep": []},
            resetting_weapons=["wep"],
        )

        # 1. Player chooses to supply drive motor instead of resetting weapon
        refresh_robot_drive_and_power(robot, chosen_components=["m_left"])
        self.assertTrue(robot.components["m_left"].is_active, "Drive gets 2E")
        self.assertFalse(robot.components["wep"].reset_supplied, "Weapon does not get 2E, reset_supplied is False")
        self.assertFalse(robot.components["wep"].is_active, "Weapon is inactive")

        # 2. Player chooses to supply resetting weapon instead of drive
        refresh_robot_drive_and_power(robot, chosen_components=["wep"])
        self.assertFalse(robot.components["m_left"].is_active, "Drive is unpowered")
        self.assertTrue(robot.components["wep"].reset_supplied, "Weapon gets 2E to reset, reset_supplied is True")
        self.assertFalse(robot.components["wep"].is_active, "Weapon is still inactive while resetting")

    def test_reset_keyword_self_right_triggers_used_and_requires_active(self):
        """
        Verify:
        1. Self-righting requires weapon to be active.
        2. Self-righting with Reset weapon triggers used.
        """
        from playtest.engine.match import execute_turn, create_match
        from playtest.engine.types import MoveChoice

        csv_text = read_saved_robot("Vyper_flipper.csv")
        match = create_match(csv_text, "Vyper_Spinner", "Player Flipper")
        p_bot = match.player_robot

        lifter = next(c for c in p_bot.components.values() if "four-bar lifter" in c.name.lower())
        self.assertTrue(lifter.is_active)

        # Invert robot
        p_bot.is_inverted = True

        # When turn ends without contact, active lifter self-rights the robot
        execute_turn(match, MoveChoice(0, 0))
        self.assertFalse(p_bot.is_inverted, "Robot self-righted to upright")
        self.assertTrue(lifter.is_resetting, "Self-righting with weapon triggered Reset")
        self.assertFalse(lifter.is_active, "Lifter is now inactive during reset")

        # Now test: if robot is inverted while lifter is resetting (inactive), it CANNOT self-right yet
        p_bot.is_inverted = True
        self.assertTrue(lifter.is_resetting)
        # Execute turn: lifter will be supplied this turn, but cannot self-right this turn
        execute_turn(match, MoveChoice(0, 0))
        # During turn cleanup: lifter received supply so it finishes reset, but could not self-right during that turn
        self.assertFalse(lifter.is_resetting, "Reset finished at end of round")
        # In next turn, now that it has reset and is active, it can self-right!
        execute_turn(match, MoveChoice(0, 0))
        self.assertFalse(p_bot.is_inverted, "Robot self-rights once lifter has completed reset")

    def test_reset_keyword_defeat_exemption_when_inverted(self):
        """
        Verify:
        "This weapon is inactive the turn after it is used.
        (this does not cause the robot to be considered stuck if it is also a self righter)"
        """
        from playtest.engine.match import is_robot_defeated, create_match

        csv_text = read_saved_robot("Vyper_flipper.csv")
        match = create_match(csv_text, "Vyper_Spinner", "Player Flipper")
        p_bot = match.player_robot

        lifter = next(c for c in p_bot.components.values() if "four-bar lifter" in c.name.lower())

        # Invert robot and disable all invertible drive so it has 0 drive when inverted
        p_bot.is_inverted = True
        for c in p_bot.components.values():
            c.is_invertible = False
        p_bot.left_drive_max = 0
        p_bot.right_drive_max = 0

        # Lifter is resetting (inactive)
        lifter.is_resetting = True
        lifter.is_active = False

        # Exemption check: Even though lifter is inactive due to Reset, robot is NOT defeated
        self.assertFalse(is_robot_defeated(p_bot), "Robot with resetting self-righter is not defeated")

        # But if the lifter itself or its supply source is destroyed:
        lifter.is_destroyed = True
        self.assertTrue(is_robot_defeated(p_bot), "Robot IS defeated when self-righter is destroyed")


if __name__ == "__main__":
    unittest.main()



