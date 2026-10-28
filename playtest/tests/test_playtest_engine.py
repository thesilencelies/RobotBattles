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
        csv_text = read_saved_robot("Beater_wide.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player")
        # In Round 1 initialization, start_of_turn_spin_up already fired
        # Beater Bar has Spin up (3), starts at 1 spin counter (0 + 1)
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
        # Set poses touching at (400, 400)
        p_bot.pose = Pose(x=400.0, y=435.0, theta=0.0)
        a_bot.pose = Pose(x=400.0, y=365.0, theta=180.0)
        logs = resolve_collision_combat(col, p_bot, a_bot, 1)
        self.assertGreater(len(logs), 0)
        # Drive feedback has been removed from inert contact rules
        self.assertFalse(any("feedback" in entry.message.lower() for entry in logs))
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

        # Ensure player robot has a wedge component hit with absorption=4 (double absorption = 8)
        wedge_comp = ComponentHealth(
            id="wedge_1", name="Titanium Wedge", card_type="component",
            max_durability=9, current_durability=9, absorption=4, requirements="",
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
        # Wedge was hit: double absorption (4 * 2 = 8 >= attack 6) reduces throw strength to 0!
        # Opponent also becomes raised from wedge contact!
        self.assertTrue(any("Wedge was hit" in entry.message for entry in logs))
        self.assertFalse(any(f"{p_bot.name} is THROWN" in entry.message for entry in logs))
        self.assertTrue(any("is RAISED" in entry.message for entry in logs))

    def test_wedge_keyword_when_raised_prevents_throw(self):
        from playtest.engine.combat import resolve_collision_combat
        from playtest.engine.types import CollisionEvent
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        # Ensure player robot has a wedge component hit with absorption 4, and is raised!
        wedge_comp = ComponentHealth(
            id="wedge_1", name="Titanium Wedge", card_type="component",
            max_durability=9, current_durability=9, absorption=4, requirements="",
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
        # Wedge was hit: Wedge loses double absorption while RAISED, and raised robot receives +2 throw strength!
        self.assertTrue(any("does not double absorption while RAISED" in entry.message for entry in logs))
        self.assertTrue(any(f"{p_bot.name} is THROWN" in entry.message for entry in logs))

    def test_wedge_does_not_work_when_inverted(self):
        """Tests that wedges do not prevent throws while inverted unless the component is invertible."""
        from playtest.engine.combat import resolve_collision_combat
        from playtest.engine.types import CollisionEvent
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        # Ensure player robot has a non-invertible wedge component hit, and is inverted!
        wedge_comp = ComponentHealth(
            id="wedge_1", name="Steel Wedge", card_type="component",
            max_durability=11, current_durability=11, absorption=3, requirements="",
            outputs="", keywords="wedge", text="", x=100, y=20, rotation=0,
            box=(100, 20, 144, 84), is_wedge=True, is_invertible=False,
        )
        p_bot.components["wedge_1"] = wedge_comp
        p_bot.is_inverted = True

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
            description="Active strike hitting inverted wedge",
            r1_active_hit=False,
            r2_active_hit=True,
        )
        logs = resolve_collision_combat(col, p_bot, a_bot, 1)
        # Because p_bot is inverted and wedge is not invertible, wedge does NOT prevent throw!
        self.assertTrue(any("does not function while INVERTED" in entry.message for entry in logs))
        self.assertTrue(any(f"{p_bot.name} is THROWN" in entry.message for entry in logs))

        # Now test invertible wedge:
        wedge_comp.is_invertible = True
        wedge_comp.keywords = "wedge;invertible"
        p_bot.is_inverted = True
        logs2 = resolve_collision_combat(col, p_bot, a_bot, 1)
        self.assertTrue(any("Wedge was hit" in entry.message for entry in logs2))
        self.assertFalse(any(f"{p_bot.name} is THROWN" in entry.message for entry in logs2))

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

        # Make wheels non-invertible so drive is 0 while inverted
        for comp in bot.components.values():
            if comp.is_invertible:
                comp.is_invertible = False
                comp.keywords = ""

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
        w_comp.is_active = True

        # Non-wedge component on opponent (battery)
        non_wedge_cid = [cid for cid, c in a_bot.components.items() if not c.is_wedge][0]
        a_bot.components[non_wedge_cid].absorption = 0

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

        # Case 1: Thrown clear of wall -> takes throw damage equal to full throw strength (5)
        with patch("random.randint", return_value=2): # d6 roll = 2
            logs = resolve_collision_combat(col, p_bot, a_bot, round_num=1)
            thrown_logs = [l.message for l in logs if "THROWN" in l.message]
            self.assertTrue(any("takes throw damage 5" in msg for msg in thrown_logs))
            self.assertTrue(any("rolled 2 -> rotated 120° clockwise" in l.message for l in logs))

        # Case 2: Thrown near wall (target lands <= 20mm from wall) -> takes throw damage equal to full throw strength (5)
        # Position victim close to top wall (y=25) so thrown displacement hits the wall
        a_bot.pose = Pose(x=400.0, y=25.0, theta=180.0)
        p_bot.pose = Pose(x=400.0, y=50.0, theta=0.0)
        col.contact_point = (400.0, 45.0)
        w_comp.is_active = True
        with patch("random.randint", return_value=3): # d6 roll = 3
            logs_wall = resolve_collision_combat(col, p_bot, a_bot, round_num=1)
            wall_logs = [l.message for l in logs_wall if "THROWN into a WALL" in l.message]
            self.assertTrue(any("takes throw damage 5" in msg for msg in wall_logs))
            self.assertTrue(any("rolled 3 -> rotated 180° clockwise" in l.message for l in logs_wall))

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
        w_comp.is_active = True

        # Opponent component contacted has absorption >= attack strength (prevents throw without raising attacker)
        target_cid = [cid for cid, c in a_bot.components.items() if not c.is_wedge][0]
        a_bot.components[target_cid].absorption = 10  # 10 >= 5 attack

        col = CollisionEvent(
            time_t=0.5,
            contact_point=(400.0, 395.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=[w_comp.id],
            robot2_components=[target_cid],
            contact_type="ACTIVE",
            description="Active strike absorbed by armor",
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
        # 2. Absorption prevented throw
        self.assertFalse(any(f"{a_bot.name} is THROWN" in msg for msg in log_messages))
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
        w_comp.is_active = True

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

    def test_active_contact_still_touching_separates_full_unit(self):
        """Tests that if robots remain touching after active contact, they separate a full unit."""
        from playtest.engine.combat import resolve_collision_combat, check_robots_in_contact
        from playtest.engine.types import CollisionEvent
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        # Position touching/overlapping along Y axis: dy = 50mm < 70mm (overlap = 20mm)
        p_bot.pose = Pose(x=400.0, y=420.0, theta=0.0)
        a_bot.pose = Pose(x=400.0, y=370.0, theta=180.0)

        # Attacking weapon
        w_comp = [c for c in p_bot.components.values() if c.card_type == "weapon"][0]
        w_comp.outputs = "8W"
        w_comp.text = "Deals no damage."
        w_comp.is_active = True

        # Opponent component contacted has absorption >= attack strength (prevents throw without raising attacker)
        target_cid = [cid for cid, c in a_bot.components.items() if not c.is_wedge][0]
        a_bot.components[target_cid].absorption = 10  # 10 >= 8 attack

        col = CollisionEvent(
            time_t=0.5,
            contact_point=(400.0, 395.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=[w_comp.id],
            robot2_components=[target_cid],
            contact_type="ACTIVE",
            description="Active strike into armor with zero remaining distance",
            r1_remaining_dist=0.0,
            r2_remaining_dist=0.0,
            push_vector=(0.0, 0.0),
            r1_active_hit=True,
            r2_active_hit=False,
        )

        logs = resolve_collision_combat(col, p_bot, a_bot, round_num=1)
        log_messages = [l.message for l in logs]

        # Active clash occurred
        self.assertTrue(any("ACTIVE WEAPON HIT" in msg for msg in log_messages))
        # Proceeded to inertial contact
        self.assertTrue(any("proceeding with inertial contact" in msg for msg in log_messages))
        # Separated back a full unit
        self.assertTrue(any("moved back a full unit to separate" in msg for msg in log_messages))
        # Robots are no longer touching
        self.assertFalse(check_robots_in_contact(p_bot, a_bot))
        self.assertAlmostEqual(p_bot.pose.y, 470.0, delta=0.5)
        self.assertAlmostEqual(a_bot.pose.y, 320.0, delta=0.5)

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
        # Overlap between p_bot (x=145) and a_bot (x=175) is 70 - 30 = 40mm.
        # Both robots move back a full unit (overlap/2 + DRIVE_UNIT_MM 40mm) = 20 + 40 = 60mm away from contact.
        # p_bot tries to move left (-x) by 60mm: 145 - 60 = 85, clamped to 135 (left boundary)
        self.assertEqual(p_bot.pose.x, 135.0)
        # a_bot moves right (+x) by 60mm: 175 + 60 = 235 (well within bounds)
        self.assertEqual(a_bot.pose.x, 235.0)
        self.assertTrue(any("moved back a full unit" in entry.message.lower() for entry in logs))

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
        p_w.is_active = True
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
        csv_text = read_saved_robot("Beater_wide.csv")
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
        from playtest.engine.collision import check_robots_in_contact
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        p_bot.pose = Pose(x=400.0, y=410.0, theta=0.0)
        a_bot.pose = Pose(x=400.0, y=380.0, theta=180.0)

        w_comp = [c for c in p_bot.components.values() if c.card_type == "weapon"][0]
        w_comp.outputs = "5W"
        w_comp.text = ""
        w_comp.is_active = True
        p_bot.weapon_spin_counters[w_comp.id] = 1
        w_comp.spin_counters = 1

        wedge_cids = [cid for cid, c in a_bot.components.items() if c.is_wedge]
        non_wedge_cids = [cid for cid, c in a_bot.components.items() if not c.is_wedge and ("wheel" in c.name.lower() or "tire" in c.name.lower())]
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
        w_comp.is_active = True
        p_bot.weapon_spin_counters[w_comp.id] = 1
        w_comp.spin_counters = 1

        # Case 2: Contact is directly on the wedge itself (wedge takes the damage).
        # Wedge effect applies (double absorption 3 * 2 = 6 >= 5 attack): robot is NOT thrown!
        a_bot.components[wedge_id].absorption = 3
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
        self.assertTrue(any(f"{a_bot.name} is not thrown" in m for m in log_msgs2))
        self.assertFalse(any(f"{a_bot.name} is THROWN" in m for m in log_msgs2))
        # Player Bot was raised and thrown, so robots are separated
        self.assertFalse(check_robots_in_contact(p_bot, a_bot))

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
        weapon_damage_cids = {s.target_cid for s in steps if s.phase == "damage"}
        for nid in connected_to_armor:
            self.assertNotIn(nid, weapon_damage_cids, f"Component #{nid} should not take excess weapon damage")

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
        w_comp.is_active = True
        p_bot.weapon_spin_counters[w_comp.id] = 1

        non_wedge = [cid for cid, c in a_bot.components.items() if not c.is_wedge and ("wheel" in c.name.lower() or "tire" in c.name.lower())][0]
        a_bot.components[non_wedge].absorption = 0

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

    def test_inertial_collision_motion_vector_sum(self):
        """
        Rule: 'The pair of robots move in a straight line created by summing their remaining motion templates.'
        Verify detect_collision computes push_vector as vector sum of remaining motions.
        """
        from playtest.engine.collision import detect_collision
        from playtest.engine.match import create_match
        from playtest.engine.types import TrajectoryPoint

        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player")
        r1 = match.player_robot
        r2 = match.automaton_robot

        r1.pose.x, r1.pose.y, r1.pose.theta = 400.0, 400.0, 0.0
        r2.pose.x, r2.pose.y, r2.pose.theta = 400.0, 360.0, 180.0

        r1_traj = [
            TrajectoryPoint(x=400.0, y=400.0 - 80.0 * (i / 10.0), theta=0.0, t=i / 10.0)
            for i in range(11)
        ]
        r2_traj = [
            TrajectoryPoint(x=400.0, y=360.0 + 20.0 * (i / 10.0), theta=180.0, t=i / 10.0)
            for i in range(11)
        ]

        col = detect_collision(r1, r1_traj, r2, r2_traj)
        self.assertIsNotNone(col)
        self.assertEqual(len(col.push_vector), 2)
        # Vector sum along Y is negative (-54.0) because r1 moved much faster in -Y than r2 in +Y
        self.assertAlmostEqual(col.push_vector[0], 0.0, delta=1.0)
        self.assertLess(col.push_vector[1], -20.0)

    def test_inertial_push_no_feedback_at_active_drive(self):
        """
        Rule: Inertial feedback removed. Pushing matches no longer damage active drive components.
        """
        from playtest.engine.combat import resolve_collision_combat
        from playtest.engine.types import CollisionEvent
        from playtest.engine.match import create_match

        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        col = CollisionEvent(
            time_t=0.5,
            contact_point=(400.0, 400.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=[list(p_bot.components.keys())[0]],
            robot2_components=[list(a_bot.components.keys())[0]],
            contact_type="INERT",
            description="Pushing match",
            r1_remaining_dist=80.0,  # 2 drive units
            r2_remaining_dist=40.0,  # 1 drive unit
            push_vector=(0.0, 0.0),
        )

        logs = resolve_collision_combat(col, p_bot, a_bot, round_num=1)

        # Drive feedback is NOT applied
        self.assertFalse(any("feedback from opponent's remaining momentum" in entry.message for entry in logs))

    def test_forks_in_line_detection_and_lifting(self):
        """
        Rule: 'If the opposing robot is in line with the forks during contact, they become lifted for this contact.'
        """
        from playtest.engine.collision import check_robot_forks_in_line
        from playtest.engine.combat import resolve_collision_combat
        from playtest.engine.match import create_match
        from playtest.engine.types import CollisionEvent, ComponentHealth

        csv_text = read_saved_robot("Vyper_flipper.csv")
        match = create_match(csv_text, "Vyper_Spinner", "Player")
        fork_bot = match.player_robot
        opp_bot = match.automaton_robot

        # Add a fork component to fork_bot with mat-centered box
        fork_comp = ComponentHealth(
            id="f1", name="Heavy Forks", card_type="armour", max_durability=6, current_durability=6,
            absorption=0, requirements="", outputs="", keywords="Forks", text="",
            x=180, y=70, rotation=0, box=(180, 50, 240, 110), is_forks=True,
        )
        fork_bot.components["f1"] = fork_comp

        # When opp_bot contacts in front and within x-span of the fork:
        fork_bot.pose = Pose(x=400.0, y=400.0, theta=0.0)
        opp_bot.pose = Pose(x=400.0, y=330.0, theta=180.0)
        in_line = check_robot_forks_in_line(fork_bot, opp_bot, (400.0, 365.0), fork_bot.pose, ["f1"], opp_pose=opp_bot.pose)
        self.assertTrue(in_line)

        # Off-center contact: Contact point is OUTSIDE the fork corridor (e.g. at x=425),
        # but part of opp_bot's chassis extends across and is in line with the fork!
        opp_bot.pose = Pose(x=415.0, y=330.0, theta=180.0)
        in_line_offcenter = check_robot_forks_in_line(
            fork_robot=fork_bot,
            opp_robot=opp_bot,
            contact_pt=(425.0, 365.0),
            fork_pose=fork_bot.pose,
            contacted_cids=["armour_right"],
            opp_pose=opp_bot.pose,
        )
        self.assertTrue(in_line_offcenter, "Forks trigger when any part of opp robot is in line with fork, even if contact point is outside")

        # Completely offset robot: NO part of opp_bot is in line with the fork
        opp_bot.pose = Pose(x=470.0, y=330.0, theta=180.0)
        in_line_far = check_robot_forks_in_line(
            fork_robot=fork_bot,
            opp_robot=opp_bot,
            contact_pt=(470.0, 365.0),
            fork_pose=fork_bot.pose,
            contacted_cids=["armour_far_right"],
            opp_pose=opp_bot.pose,
        )
        self.assertFalse(in_line_far, "Forks do not trigger when no part of opp robot is in line with fork")

        # In combat resolution with off-center contact point, opp_bot should still be lifted!
        opp_bot.pose = Pose(x=415.0, y=330.0, theta=180.0)
        opp_bot.is_raised = False
        col = CollisionEvent(
            time_t=0.5,
            contact_point=(425.0, 365.0),
            robot1_octant="Front-Right",
            robot2_octant="Front-Left",
            robot1_components=["armour_right"],
            robot2_components=[list(opp_bot.components.keys())[0]],
            contact_type="INERT",
            description="Contact with off-center contact point",
            push_vector=(0.0, -10.0),
        )
        resolve_logs = resolve_collision_combat(col, fork_bot, opp_bot, round_num=1)
        self.assertTrue(any("Forks lift" in entry.message for entry in resolve_logs), "Opponent in line with forks is lifted even with off-center contact point")

    def test_forks_do_not_work_when_inverted(self):
        """Tests that forks do not lift an opponent when inverted unless the component is invertible."""
        from playtest.engine.collision import check_robot_forks_in_line
        from playtest.engine.combat import resolve_collision_combat
        from playtest.engine.match import create_match
        from playtest.engine.types import CollisionEvent, ComponentHealth

        csv_text = read_saved_robot("Vyper_flipper.csv")
        match = create_match(csv_text, "Vyper_Spinner", "Player")
        fork_bot = match.player_robot
        opp_bot = match.automaton_robot

        # Add a non-invertible fork component to fork_bot
        fork_comp = ComponentHealth(
            id="f1", name="Heavy Forks", card_type="armour", max_durability=6, current_durability=6,
            absorption=0, requirements="", outputs="", keywords="Forks", text="",
            x=180, y=70, rotation=0, box=(180, 50, 240, 110), is_forks=True, is_invertible=False,
        )
        fork_bot.components["f1"] = fork_comp
        fork_bot.pose = Pose(x=400.0, y=400.0, theta=0.0)
        opp_bot.pose = Pose(x=400.0, y=330.0, theta=180.0)

        # When fork_bot is upright, forks work
        self.assertTrue(check_robot_forks_in_line(fork_bot, opp_bot, (400.0, 365.0), fork_bot.pose, ["f1"], opp_pose=opp_bot.pose))

        # When fork_bot is INVERTED, non-invertible forks do NOT work!
        fork_bot.is_inverted = True
        self.assertFalse(check_robot_forks_in_line(fork_bot, opp_bot, (400.0, 365.0), fork_bot.pose, ["f1"], opp_pose=opp_bot.pose))

        col = CollisionEvent(
            time_t=0.5,
            contact_point=(400.0, 365.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=["f1"],
            robot2_components=[list(opp_bot.components.keys())[0]],
            contact_type="INERT",
            description="Contact with inverted forks",
            push_vector=(0.0, -10.0),
        )
        resolve_logs = resolve_collision_combat(col, fork_bot, opp_bot, round_num=1)
        self.assertFalse(any("Forks lift" in entry.message for entry in resolve_logs))
        self.assertFalse(opp_bot.is_raised)

        # When fork component IS invertible:
        fork_comp.is_invertible = True
        fork_comp.keywords = "Forks;Invertible"
        fork_bot.is_inverted = True
        self.assertTrue(check_robot_forks_in_line(fork_bot, opp_bot, (400.0, 365.0), fork_bot.pose, ["f1"], opp_pose=opp_bot.pose))
        resolve_logs2 = resolve_collision_combat(col, fork_bot, opp_bot, round_num=1)
        self.assertTrue(any("Forks lift" in entry.message for entry in resolve_logs2))

    def test_raised_robot_inertial_motion_excluded(self):
        """
        Rule: 'A robot that is raised has its motion not contribute in inertial contact.'
        """
        from playtest.engine.combat import resolve_inert_contact
        from playtest.engine.match import create_match
        from playtest.engine.types import CollisionEvent

        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player")
        r1 = match.player_robot
        r2 = match.automaton_robot

        r1.pose = Pose(x=400.0, y=400.0, theta=0.0)
        r2.pose = Pose(x=400.0, y=340.0, theta=180.0)

        # r2 is raised; r1 has remaining vector (0, -30), r2 has (0, 50)
        # Normally net would be (0, 20), but because r2 is raised, r2's motion does not contribute!
        r2.is_raised = True
        col = CollisionEvent(
            time_t=0.5,
            contact_point=(400.0, 370.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=[list(r1.components.keys())[0]],
            robot2_components=[list(r2.components.keys())[0]],
            contact_type="INERT",
            description="Push with raised robot",
            r1_rem_vector=(0.0, -30.0),
            r2_rem_vector=(0.0, 50.0),
            push_vector=(0.0, 20.0),
        )
        resolve_inert_contact(col, r1, r2, round_num=1)
        # Both robots move in r1's direction (-Y) by -30.0, then both move back a full unit to separate:
        # r1: 400 - 30 + 45 = 415; r2: 340 - 30 - 45 = 265
        self.assertAlmostEqual(r1.pose.y, 415.0, delta=2.0)
        self.assertAlmostEqual(r2.pose.y, 265.0, delta=2.0)

    def test_match_export_log_structure(self):
        """
        Verifies that match export contains full telemetry including round_history, poses, choices, and components.
        """
        from playtest.engine.match import create_match, execute_turn
        from playtest.engine.types import MoveChoice
        from playtest.server.routes import Router

        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player", max_rounds=5)
        execute_turn(match, MoveChoice(left=1, right=1))

        router = Router()
        router.current_match = match

        resp = router.dispatch("GET", "/api/battle/export", {}, b"")
        self.assertEqual(resp.status, 200)
        self.assertIn("application/json", resp.content_type)
        import json
        data = json.loads(resp.body.decode("utf-8"))
        self.assertIn("round_history", data)
        self.assertEqual(len(data["round_history"]), 1)
        rd1 = data["round_history"][0]
        self.assertIn("player_start_pose", rd1)
        self.assertIn("automaton_start_pose", rd1)
        self.assertIn("player_end_pose", rd1)
        self.assertIn("automaton_end_pose", rd1)
        self.assertIn("player_components", rd1)
        self.assertIn("automaton_components", rd1)
        self.assertIn("full_log", data)

    def test_raised_status_effects(self):
        """
        Rule: Raised status reduces the throw strength of their attacks by 2 instead of
        negating throwing altogether. Flip strength is NOT changed when raised.
        Wedges lose double absorption when raised. Motion does not contribute to inertial contact.
        """
        from playtest.engine.combat import resolve_collision_combat, refresh_robot_drive_and_power
        from playtest.engine.types import CollisionEvent
        from playtest.engine.match import create_match

        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        # 1. Drive check when raised
        refresh_robot_drive_and_power(p_bot)
        normal_left = p_bot.left_drive_max
        normal_right = p_bot.right_drive_max

        p_bot.is_raised = True
        refresh_robot_drive_and_power(p_bot)
        self.assertEqual(p_bot.left_drive_max, normal_left, "Drive is not halved when raised")
        self.assertEqual(p_bot.right_drive_max, normal_right, "Drive is not halved when raised")

        # 2. Weapon deals full damage when raised, and throw strength is reduced by 2 (not 0)
        wpn = next(c for c in p_bot.components.values() if c.card_type == "weapon")
        wpn.is_active = True
        p_bot.weapon_spin_counters[wpn.id] = 3  # attack strength 6

        p_bot.is_raised = False
        target_cid = list(a_bot.components.keys())[0]
        col = CollisionEvent(
            time_t=0.5,
            contact_point=(400.0, 400.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=[wpn.id],
            robot2_components=[target_cid],
            contact_type="ACTIVE",
            description="Active strike",
            r1_active_hit=True,
            r2_active_hit=False,
        )
        # Ensure hit component has 0 absorption to isolate raised throw reduction
        a_bot.components[target_cid].absorption = 0
        logs = resolve_collision_combat(col, p_bot, a_bot, round_num=1)
        self.assertTrue(any("dealing 6 dmg" in entry.message for entry in logs))

        # Now raised: damage is still 6, but attacks have throw strength reduced by 2 (was 6, now 4)
        a_bot.components[target_cid].is_damaged = False
        a_bot.components[target_cid].is_destroyed = False
        a_bot.components[target_cid].current_durability = a_bot.components[target_cid].max_durability
        a_bot.components[target_cid].absorption = 0
        p_bot.is_raised = True
        wpn.is_active = True
        p_bot.weapon_spin_counters[wpn.id] = 3
        wpn.was_used_this_turn = False
        logs_raised = resolve_collision_combat(col, p_bot, a_bot, round_num=2)
        self.assertTrue(any("dealing 6 dmg" in entry.message for entry in logs_raised))
        self.assertTrue(any("reduced by 2 (was 6, now 4)" in entry.message for entry in logs_raised))

    def test_feedback_propagation_rounding_up(self):
        """
        Rule: 'shared equally if there are multiple components (rounding up), down the tree until the damage is all absorbed.'
        """
        from playtest.engine.combat import resolve_feedback_propagation
        from playtest.engine.types import ComponentHealth
        from playtest.engine.match import create_match

        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player")
        bot = match.player_robot

        # Setup component with 2 suppliers
        c_child = ComponentHealth(
            id="child", name="Child Device", card_type="weapon", max_durability=4, current_durability=4,
            absorption=0, requirements="", outputs="", keywords="", text="", x=0, y=0, rotation=0, box=(0, 0, 44, 64)
        )
        c_sup1 = ComponentHealth(
            id="sup1", name="Supplier 1", card_type="motor", max_durability=6, current_durability=6,
            absorption=0, requirements="", outputs="", keywords="", text="", x=0, y=0, rotation=0, box=(0, 0, 44, 64)
        )
        c_sup2 = ComponentHealth(
            id="sup2", name="Supplier 2", card_type="motor", max_durability=6, current_durability=6,
            absorption=0, requirements="", outputs="", keywords="", text="", x=0, y=0, rotation=0, box=(0, 0, 44, 64)
        )

        bot.components["child"] = c_child
        bot.components["sup1"] = c_sup1
        bot.components["sup2"] = c_sup2
        bot.supply_graph["child"] = ["sup1", "sup2"]

        # If child takes 3 feedback, excess is 3.
        # Shared equally between 2 suppliers rounding up: ceil(3 / 2) = 2 to each supplier!
        logs = resolve_feedback_propagation(bot, "child", 3, phase="feedback")
        self.assertTrue(any("Feedback passed to supplier Supplier 1 (#sup1): 2" in msg for msg in logs))
        self.assertTrue(any("Feedback passed to supplier Supplier 2 (#sup2): 2" in msg for msg in logs))

    def test_dropping_dice_shock_selection(self):
        """
        Rule: 'The component is chosen randomly by dropping a dice onto the robot and seeing which component it lands on.'
        """
        from playtest.engine.combat import simulate_dropping_card, simulate_dropping_dice
        from playtest.engine.match import create_match

        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player")
        bot = match.player_robot

        hit_cid = simulate_dropping_dice(bot)
        self.assertIsNotNone(hit_cid)
        self.assertIn(hit_cid, bot.components)

    def test_automata_weapons_down_consider_max_spin(self):
        """
        Rule: 'Automata are at full spin unless they have an active weapon with spin up that is not at max spin.'
        If their weapons are down (destroyed/inactive), they consider themselves at full spin
        and roll on the charged / full-spin action tables.
        """
        from playtest.engine.automata import get_automaton_action, is_automaton_at_full_spin
        from playtest.engine.match import create_match

        # Test 1: Spin Up archetype (Vyper_Spinner)
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player")
        bot = match.player_robot  # Vyper_Spinner loaded as robot

        # Find the weapon (Horizontal Spinner, id 13)
        w_comp = next(c for c in bot.components.values() if c.card_type == "weapon")
        self.assertEqual(w_comp.name, "Horizontal Spinner")

        # Case A: Active weapon with 0 spin counters -> NOT at full spin, uses uncharged table
        bot.weapon_spin_counters[w_comp.id] = 0
        w_comp.spin_counters = 0
        w_comp.is_active = True
        w_comp.is_destroyed = False
        self.assertFalse(is_automaton_at_full_spin(bot))
        self.assertEqual(get_automaton_action("Vyper_Spinner", bot, 1), "Retreat")
        self.assertEqual(get_automaton_action("Vyper_Spinner", bot, 3), "Face")
        self.assertEqual(get_automaton_action("Vyper_Spinner", bot, 4), "Evade")
        self.assertEqual(get_automaton_action("Vyper_Spinner", bot, 6), "Rush")

        # Case B: Weapon is destroyed -> Weapons are down, considered at full spin -> uses charged table!
        w_comp.is_destroyed = True
        self.assertTrue(is_automaton_at_full_spin(bot))
        self.assertEqual(get_automaton_action("Vyper_Spinner", bot, 1), "Face")
        self.assertEqual(get_automaton_action("Vyper_Spinner", bot, 2), "Evade")
        self.assertEqual(get_automaton_action("Vyper_Spinner", bot, 3), "Rush")
        self.assertEqual(get_automaton_action("Vyper_Spinner", bot, 6), "Rush")

        # Case C: Weapon is inactive (unpowered) -> considered at full spin -> uses charged table!
        w_comp.is_destroyed = False
        w_comp.is_active = False
        self.assertTrue(is_automaton_at_full_spin(bot))
        self.assertEqual(get_automaton_action("Vyper_Spinner", bot, 1), "Face")
        self.assertEqual(get_automaton_action("Vyper_Spinner", bot, 3), "Rush")

        # Test 2: Balanced archetype (Beater_wide)
        bw_text = read_saved_robot("Beater_wide.csv")
        bw_match = create_match(bw_text, "Vyper_flipper", "Player")
        bw_bot = bw_match.player_robot
        bw_weapon = next(c for c in bw_bot.components.values() if c.card_type == "weapon")
        self.assertEqual(bw_weapon.name, "Beater Bar")

        # Sub-spin (active, 1 counter out of 3 max) -> sub_spin table
        bw_weapon.is_active = True
        bw_weapon.is_destroyed = False
        bw_bot.weapon_spin_counters[bw_weapon.id] = 1
        bw_weapon.spin_counters = 1
        self.assertFalse(is_automaton_at_full_spin(bw_bot))
        self.assertEqual(get_automaton_action("Beater_wide", bw_bot, 1), "Retreat")
        self.assertEqual(get_automaton_action("Beater_wide", bw_bot, 2), "Evade")
        self.assertEqual(get_automaton_action("Beater_wide", bw_bot, 4), "Face")
        self.assertEqual(get_automaton_action("Beater_wide", bw_bot, 5), "Rush")

        # Destroyed weapon -> considered at full spin -> full_spin table!
        bw_weapon.is_destroyed = True
        self.assertTrue(is_automaton_at_full_spin(bw_bot))
        self.assertEqual(get_automaton_action("Beater_wide", bw_bot, 1), "Retreat")
        self.assertEqual(get_automaton_action("Beater_wide", bw_bot, 2), "Face")
        self.assertEqual(get_automaton_action("Beater_wide", bw_bot, 3), "Evade")
        self.assertEqual(get_automaton_action("Beater_wide", bw_bot, 4), "Rush")

    def test_weapon_wall_contact_when_pushed_into_wall(self):
        """
        Rule: 'When a weapon contacts a wall it should also lose all its spin counters
        and suffer feedback: (weapon strength + throw strength) // 2.'
        """
        from playtest.engine.combat import resolve_inert_contact
        from playtest.engine.match import create_match

        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player")
        spinner = match.player_robot
        opp = match.automaton_robot

        w_comp = next(c for c in spinner.components.values() if c.card_type == "weapon")
        w_id = w_comp.id

        # Set 4 spin counters on Horizontal Spinner (attack strength = 2*4 + 1 = 9)
        spinner.weapon_spin_counters[w_id] = 4
        w_comp.spin_counters = 4

        # Face West (heading 270) towards WALL_LEFT (x=100)
        spinner.pose = Pose(x=150.0, y=400.0, theta=270.0)
        opp.pose = Pose(x=190.0, y=400.0, theta=270.0)

        # Displace towards left wall (push_vector = (-50, 0), pushes spinner into wall)
        col = CollisionEvent(
            time_t=0.5,
            contact_point=(170.0, 400.0),
            robot1_octant="Back",
            robot2_octant="Front",
            robot1_components=[w_id],
            robot2_components=[list(opp.components.keys())[0]],
            contact_type="INERT",
            description="Pushing spinner into left wall",
            r1_rem_vector=(-50.0, 0.0),
            r2_rem_vector=(-50.0, 0.0),
            push_vector=(-50.0, 0.0),
        )
        logs = resolve_inert_contact(col, spinner, opp, round_num=1)

        # Horizontal Spinner touches wall:
        # 1. Lost all spin counters
        self.assertEqual(spinner.weapon_spin_counters[w_id], 0)
        self.assertEqual(w_comp.spin_counters, 0)

        # 2. Suffered feedback = (weapon_strength + wall_throw_str) // 2
        wall_fb_logs = [e.message for e in logs if "contacted the wall" in e.message]
        self.assertTrue(len(wall_fb_logs) > 0, "Should log weapon contacting the wall")
        self.assertTrue(any("Lost all spin counters" in msg for msg in wall_fb_logs))
        self.assertTrue(any("suffered" in msg for msg in wall_fb_logs))

    def test_weapon_wall_contact_when_driving_into_wall(self):
        """
        Rule: 'when a weapon contacts a wall it should also lose all its spin counters and suffer feedback.
        (This happens both if they drive into a wall and if they are pushed into it)'
        Also: driving into wall stops at the wall (stuck at wall).
        """
        from playtest.engine.match import create_match, execute_turn

        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        w_comp = next(c for c in p_bot.components.values() if c.card_type == "weapon")
        w_id = w_comp.id

        # Position player robot near left wall (x=150, y=400) facing West (270)
        p_bot.pose = Pose(x=150.0, y=400.0, theta=270.0)
        # Position automaton far away on opposite side so no robot-robot collision occurs
        a_bot.pose = Pose(x=550.0, y=400.0, theta=90.0)

        # Give player 4 spin counters
        p_bot.weapon_spin_counters[w_id] = 4
        w_comp.spin_counters = 4

        # Drive forward into left wall (L=3, R=3 forward along heading 270 = West)
        # Straight forward 3 units = 75mm west -> from 150 to 75, hitting WALL_LEFT (100)
        execute_turn(match, MoveChoice(3, 3), fixed_automaton_roll=1)

        # Verify robot stopped at the wall (clamped to WALL_LEFT + MINIATURE_RADIUS = 135)
        self.assertAlmostEqual(p_bot.pose.x, 135.0, places=1)

        # Verify weapon contacted wall: lost all spin counters and suffered feedback
        wall_logs = [e.message for e in match.log if "contacted the wall" in e.message]
        self.assertTrue(len(wall_logs) > 0, "Driving weapon into wall should log contact and feedback")
        self.assertTrue(any("Lost all spin counters (was 4)" in msg for msg in wall_logs))
        # At start of round 2, undamaged active weapon spins up 1 counter
        self.assertEqual(p_bot.weapon_spin_counters[w_id], 1)
        self.assertEqual(w_comp.spin_counters, 1)

    def test_physical_curve_templates_trajectory(self):
        """Tests that consolidated physical curve templates generate trajectories matching exact angles."""
        from playtest.engine.match import get_template_metadata
        from playtest.engine.movement import generate_trajectory

        start = Pose(x=400.0, y=400.0, theta=0.0)

        # 1. Gentle curve: (3, 2) -> 26.0 deg right
        meta_gentle = get_template_metadata(3, 2)
        self.assertEqual(meta_gentle["template_id"], "curve_gentle")
        self.assertEqual(meta_gentle["nominal_rc"], 220.0)
        self.assertAlmostEqual(meta_gentle["target_angle_deg"], 26.0)
        self.assertFalse(meta_gentle["flipped"])
        traj_g = generate_trajectory(start, MoveChoice(3, 2), num_steps=20)
        self.assertAlmostEqual(traj_g[-1].theta, 26.0, places=1)
        self.assertGreater(traj_g[-1].x, 400.0)  # moved right
        self.assertLess(traj_g[-1].y, 400.0)     # moved forward (decreased y)

        # Flipped gentle curve: (2, 3) -> 26.0 deg left (334 deg)
        meta_gentle_flip = get_template_metadata(2, 3)
        self.assertTrue(meta_gentle_flip["flipped"])
        traj_gf = generate_trajectory(start, MoveChoice(2, 3), num_steps=20)
        self.assertAlmostEqual(traj_gf[-1].theta, 334.0, places=1)
        self.assertLess(traj_gf[-1].x, 400.0)    # moved left

        # 2. Medium curve: (2, 1) -> 35.0 deg
        meta_med = get_template_metadata(2, 1)
        self.assertEqual(meta_med["template_id"], "curve_medium")
        self.assertEqual(meta_med["nominal_rc"], 97.5)
        self.assertAlmostEqual(meta_med["target_angle_deg"], 35.0)
        traj_m = generate_trajectory(start, MoveChoice(2, 1), num_steps=20)
        self.assertAlmostEqual(traj_m[-1].theta, 35.0, places=1)

        # 3. Sharp curve: (3, 1) -> 70.0 deg, and (5, 1) -> 180.0 deg
        meta_sharp = get_template_metadata(3, 1)
        self.assertEqual(meta_sharp["template_id"], "curve_sharp")
        self.assertEqual(meta_sharp["nominal_rc"], 55.0)
        self.assertAlmostEqual(meta_sharp["target_angle_deg"], 70.0)
        traj_s = generate_trajectory(start, MoveChoice(3, 1), num_steps=20)
        self.assertAlmostEqual(traj_s[-1].theta, 70.0, places=1)

        meta_sharp_max = get_template_metadata(5, 1)
        self.assertAlmostEqual(meta_sharp_max["target_angle_deg"], 180.0)
        traj_smax = generate_trajectory(start, MoveChoice(5, 1), num_steps=20)
        self.assertAlmostEqual(traj_smax[-1].theta, 180.0, places=1)

    def test_asymmetric_counter_drives_trajectory(self):
        """Tests Rule 6.1 g: Spin Disc for min(|L|, |R|) then Pivot Fan for remainder."""
        from playtest.engine.match import get_template_metadata
        from playtest.engine.movement import generate_trajectory

        start = Pose(x=400.0, y=400.0, theta=0.0)

        # Choice (3, -1): k=1 (spin 90°), rem=2 (pivot 90°) -> total rotation 180°
        meta = get_template_metadata(3, -1)
        self.assertEqual(meta["category"], "asymmetric_counter")
        self.assertEqual(meta["spin_k"], 1)
        self.assertEqual(meta["spin_deg"], 90.0)
        self.assertEqual(meta["pivot_rem"], 2)
        self.assertEqual(meta["pivot_deg"], 90.0)
        self.assertFalse(meta["flipped"])

        traj = generate_trajectory(start, MoveChoice(3, -1), num_steps=20)
        # End theta should be 180 deg
        self.assertAlmostEqual(traj[-1].theta, 180.0, places=1)

        # Choice (-1, 3): left turn counter-drive -> flipped = True
        meta_flip = get_template_metadata(-1, 3)
        self.assertEqual(meta_flip["category"], "asymmetric_counter")
        self.assertTrue(meta_flip["flipped"])
        traj_flip = generate_trajectory(start, MoveChoice(-1, 3), num_steps=20)
        self.assertAlmostEqual(traj_flip[-1].theta, 180.0, places=1)

    def test_hazard_wall_knockout_on_throw(self):
        """Rule: A marked hazard wall collision causes immediate knockout."""
        from playtest.engine.combat import resolve_collision_combat
        from playtest.engine.types import CollisionEvent
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        # Position opponent near corner hazard wall (e.g., top-left near x=25, y=25)
        a_bot.pose = Pose(x=35.0, y=25.0, theta=180.0)
        p_bot.pose = Pose(x=50.0, y=50.0, theta=0.0)

        weapon_comps = [c for c in p_bot.components.values() if c.card_type == "weapon"]
        w_comp = weapon_comps[0]
        w_comp.outputs = "6W"
        w_comp.text = "Deals no damage."
        w_comp.is_active = True

        non_wedge_cid = [cid for cid, c in a_bot.components.items() if not c.is_wedge][0]
        a_bot.components[non_wedge_cid].absorption = 0

        col = CollisionEvent(
            time_t=0.5,
            contact_point=(45.0, 40.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=[w_comp.id],
            robot2_components=[non_wedge_cid],
            contact_type="ACTIVE",
            description="Active strike near hazard wall",
            r1_remaining_dist=0.0,
            r2_remaining_dist=0.0,
            push_vector=(-10.0, -10.0),
            r1_active_hit=True,
            r2_active_hit=False,
        )

        with patch("random.randint", return_value=3):
            logs = resolve_collision_combat(col, p_bot, a_bot, round_num=1)

        self.assertTrue(a_bot.is_knocked_out)
        self.assertTrue(a_bot.is_eliminated)
        self.assertTrue(any("marked HAZARD WALL! KNOCKED OUT!" in entry.message for entry in logs))

    def test_hazard_wall_knockout_on_push(self):
        """Rule: Being pushed into a marked hazard wall causes immediate knockout."""
        from playtest.engine.combat import resolve_inert_contact
        from playtest.engine.types import CollisionEvent
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        # Position opponent close to left hazard wall at y=100
        a_bot.pose = Pose(x=25.0, y=100.0, theta=0.0)
        p_bot.pose = Pose(x=45.0, y=100.0, theta=180.0)

        col = CollisionEvent(
            time_t=0.5,
            contact_point=(35.0, 100.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=[list(p_bot.components.keys())[0]],
            robot2_components=[list(a_bot.components.keys())[0]],
            contact_type="INERTIAL",
            description="Push into hazard wall",
            r1_remaining_dist=20.0,
            r2_remaining_dist=0.0,
            push_vector=(-20.0, 0.0),
            r1_active_hit=False,
            r2_active_hit=False,
        )

        logs = resolve_inert_contact(col, p_bot, a_bot, round_num=1)
        self.assertTrue(a_bot.is_knocked_out)
        self.assertTrue(a_bot.is_eliminated)
        self.assertTrue(any("marked HAZARD WALL! KNOCKED OUT!" in entry.message for entry in logs))


    def test_ground_game_mutual_raised_tie_breaker(self):
        """
        Rule: 'When both robots would be raised in the same contact,
        randomly choose one by rolling a dice: that one is raised and the other isn't.'
        Roll <= 3 -> robot 1 is raised, robot 2 is not.
        Roll >= 4 -> robot 2 is raised, robot 1 is not.
        """
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        # Give both robots wedges in contact
        p_wedge = ComponentHealth(
            id="p_w", name="Player Wedge", card_type="armour", max_durability=10, current_durability=10,
            absorption=2, requirements="", outputs="", keywords="Wedge", text="", x=100, y=20, rotation=0,
            box=(100, 20, 140, 60), is_wedge=True,
        )
        a_wedge = ComponentHealth(
            id="a_w", name="Auto Wedge", card_type="armour", max_durability=10, current_durability=10,
            absorption=2, requirements="", outputs="", keywords="Wedge", text="", x=100, y=20, rotation=0,
            box=(100, 20, 140, 60), is_wedge=True,
        )
        p_bot.components["p_w"] = p_wedge
        a_bot.components["a_w"] = a_wedge

        col = CollisionEvent(
            time_t=0.5,
            contact_point=(400.0, 400.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=["p_w"],
            robot2_components=["a_w"],
            contact_type="INERT",
            description="Wedge vs Wedge clash",
            push_vector=(0.0, 0.0),
        )

        with patch("random.randint", return_value=2):
            logs = resolve_collision_combat(col, p_bot, a_bot, round_num=1)
            self.assertTrue(any("Ground Game Clash" in e.message for e in logs))
            self.assertTrue(any(f"{p_bot.name} to be RAISED ({a_bot.name} stays grounded)" in e.message for e in logs))

        with patch("random.randint", return_value=5):
            logs = resolve_collision_combat(col, p_bot, a_bot, round_num=1)
            self.assertTrue(any("Ground Game Clash" in e.message for e in logs))
            self.assertTrue(any(f"{a_bot.name} to be RAISED ({p_bot.name} stays grounded)" in e.message for e in logs))

    def test_trigger_weapon_suppression_and_recoil_feedback(self):
        """
        Rule: 'Trigger: If an opposing weapon makes contact this weapon does not attack.'
        'Trigger weapons don't get feedback if they don't attack.'
        """
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        # p_bot has a Trigger weapon
        p_trig = ComponentHealth(
            id="trig_wpn", name="Trigger Lifter", card_type="weapon", max_durability=8, current_durability=8,
            absorption=0, requirements="", outputs="6W", keywords="Trigger", text="Deals no damage only throws",
            x=100, y=20, rotation=0, box=(100, 20, 140, 60), is_trigger=True, is_active=True,
        )
        p_bot.components["trig_wpn"] = p_trig
        p_bot.weapon_spin_counters["trig_wpn"] = 1

        # a_bot has active spinner without trigger
        a_spin = next(c for c in a_bot.components.values() if c.card_type == "weapon")
        a_spin.is_trigger = False
        a_spin.is_active = True
        a_bot.weapon_spin_counters[a_spin.id] = 2

        col = CollisionEvent(
            time_t=0.5,
            contact_point=(400.0, 400.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=["trig_wpn"],
            robot2_components=[a_spin.id],
            contact_type="ACTIVE",
            description="Active clash",
            r1_active_hit=True,
            r2_active_hit=True,
        )

        logs = resolve_collision_combat(col, p_bot, a_bot, round_num=1)
        # Trigger weapon should be suppressed
        self.assertTrue(any("has TRIGGER: does not attack" in e.message for e in logs))
        # Trigger weapon was NOT used and took no recoil feedback
        self.assertFalse(p_trig.was_used_this_turn)
        self.assertFalse(any(f"[Recoil Feedback] Feedback on {p_trig.name}" in e.message for e in logs))
        # Opposing weapon did attack
        self.assertTrue(any(f"{a_bot.name} attacks with {a_spin.name}" in e.message for e in logs))

    def test_trigger_vs_trigger_both_attack(self):
        """
        Rule: 'If they both have Trigger they both will attack.'
        """
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        p_trig = ComponentHealth(
            id="t1", name="Lifter 1", card_type="weapon", max_durability=8, current_durability=8,
            absorption=0, requirements="", outputs="4W", keywords="Trigger", text="Deals no damage only throws",
            x=100, y=20, rotation=0, box=(100, 20, 140, 60), is_trigger=True, is_active=True,
        )
        a_trig = ComponentHealth(
            id="t2", name="Lifter 2", card_type="weapon", max_durability=8, current_durability=8,
            absorption=0, requirements="", outputs="4W", keywords="Trigger", text="Deals no damage only throws",
            x=100, y=20, rotation=0, box=(100, 20, 140, 60), is_trigger=True, is_active=True,
        )
        p_bot.components["t1"] = p_trig
        a_bot.components["t2"] = a_trig
        p_bot.weapon_spin_counters["t1"] = 1
        a_bot.weapon_spin_counters["t2"] = 1

        col = CollisionEvent(
            time_t=0.5,
            contact_point=(400.0, 400.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=["t1"],
            robot2_components=["t2"],
            contact_type="ACTIVE",
            description="Trigger vs Trigger clash",
            r1_active_hit=True,
            r2_active_hit=True,
        )

        logs = resolve_collision_combat(col, p_bot, a_bot, round_num=1)
        self.assertFalse(any("has TRIGGER: does not attack" in e.message for e in logs))
        self.assertTrue(any(f"attacks with {p_trig.name}" in e.message for e in logs))
        self.assertTrue(any(f"attacks with {a_trig.name}" in e.message for e in logs))

    def test_overhead_weapon_causes_no_throw_and_receives_recoil(self):
        """
        Rule: 'Overhead: This weapon hits a random component along the contact line instead of the outermost.
        Does not cause a throw.'
        'Overhead weapons still receive feedback.'
        """
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        oh_wpn = ComponentHealth(
            id="oh1", name="Hammer Saw", card_type="weapon", max_durability=8, current_durability=8,
            absorption=0, requirements="", outputs="6W", keywords="Overhead", text="",
            x=100, y=20, rotation=0, box=(100, 20, 140, 60), is_overhead=True, is_active=True,
        )
        p_bot.components["oh1"] = oh_wpn
        p_bot.weapon_spin_counters["oh1"] = 2

        target_cid = list(a_bot.components.keys())[0]

        col = CollisionEvent(
            time_t=0.5,
            contact_point=(400.0, 400.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=["oh1"],
            robot2_components=[target_cid],
            contact_type="ACTIVE",
            description="Overhead weapon strike",
            r1_active_hit=True,
            r2_active_hit=False,
        )

        logs = resolve_collision_combat(col, p_bot, a_bot, round_num=1)
        # Overhead causes no throw on opponent
        self.assertTrue(any("causes no throw" in e.message for e in logs))
        self.assertFalse(any(f"{a_bot.name} is THROWN" in e.message for e in logs))
        # Attacking Overhead weapon DOES receive recoil feedback
        self.assertTrue(any(f"Feedback on {oh_wpn.name}" in e.message for e in logs))

    def test_overhead_intercepted_by_titanium_top_plate(self):
        """
        Rule: 'If the defending robot has an active upright Titanium Top Plate,
        it intercepts the attack even if not on the ray.'
        """
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        oh_wpn = ComponentHealth(
            id="oh1", name="Hammer Saw", card_type="weapon", max_durability=8, current_durability=8,
            absorption=0, requirements="", outputs="4W", keywords="Overhead", text="",
            x=100, y=20, rotation=0, box=(100, 20, 140, 60), is_overhead=True, is_active=True,
        )
        p_bot.components["oh1"] = oh_wpn
        p_bot.weapon_spin_counters["oh1"] = 1

        top_plate = ComponentHealth(
            id="tp", name="Titanium Top Plate", card_type="armour", max_durability=10, current_durability=10,
            absorption=2, requirements="", outputs="", keywords="", text="overhead attacks hit this component instead unless inverted",
            x=200, y=150, rotation=0, box=(180, 130, 220, 170),
        )
        a_bot.components["tp"] = top_plate

        other_cid = [cid for cid in a_bot.components if cid != "tp"][0]

        # Attack ray targets other_cid, but Top Plate should intercept!
        col = CollisionEvent(
            time_t=0.5,
            contact_point=(400.0, 400.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=["oh1"],
            robot2_components=[other_cid],
            contact_type="ACTIVE",
            description="Overhead strike aiming at bumper",
            r1_active_hit=True,
            r2_active_hit=False,
        )

        logs = resolve_collision_combat(col, p_bot, a_bot, round_num=1)
        self.assertTrue(any("Titanium Top Plate intercepts the Overhead attack" in e.message for e in logs))
        self.assertTrue(any("Titanium Top Plate (#tp) takes 4 dmg" in e.message for e in logs))

        # When defending robot is inverted, Top Plate does NOT intercept
        a_bot.is_inverted = True
        p_bot.weapon_spin_counters["oh1"] = 1
        logs_inv = resolve_collision_combat(col, p_bot, a_bot, round_num=2)
        self.assertFalse(any("Titanium Top Plate intercepts" in e.message for e in logs_inv))

    def test_crushing_claw_pins_and_moves_opponent_on_next_turn(self):
        """
        Rule: 'For crushing claw, the next turn they move like inertial contact as if they were raised.
        Then the turn after [the claw is disabled due to Reset].'
        """
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        claw = ComponentHealth(
            id="claw1", name="Crushing Claw", card_type="weapon", max_durability=10, current_durability=10,
            absorption=1, requirements="", outputs="4W", keywords="Trigger;Overhead",
            text="next turn target moves with this robot instead", x=100, y=20, rotation=0, box=(100, 20, 140, 60),
            is_overhead=True, is_trigger=True, is_reset=True, is_active=True,
        )
        p_bot.components["claw1"] = claw
        p_bot.weapon_spin_counters["claw1"] = 1

        col = CollisionEvent(
            time_t=0.5,
            contact_point=(400.0, 400.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=["claw1"],
            robot2_components=[list(a_bot.components.keys())[0]],
            contact_type="ACTIVE",
            description="Claw strike",
            r1_active_hit=True,
            r2_active_hit=False,
        )

        # 1. Active contact grabs automaton
        logs = resolve_collision_combat(col, p_bot, a_bot, round_num=1)
        self.assertEqual(a_bot.grabbed_by, p_bot.id)
        self.assertTrue(any("Crushing Claw grabs" in e.message for e in logs))

        # 2. Next turn (turn 2): automaton moves with player
        p_bot.pose = Pose(x=400.0, y=400.0, theta=0.0)
        a_bot.pose = Pose(x=400.0, y=360.0, theta=180.0)
        # Execute turn 2: player moves forward 2 units (80mm)
        match = execute_turn(match, MoveChoice(2, 2), fixed_automaton_roll=1)
        self.assertIsNone(a_bot.grabbed_by)
        self.assertTrue(any("is grabbed by Player Bot's Crushing Claw" in e.message for e in match.log))

        # 3. Turn 3: Claw is resetting (inactive due to Reset)
        self.assertTrue(claw.is_resetting)
        self.assertFalse(claw.is_active)


    def test_multi_weapon_contact_independent_targets_max_throw_full_feedback(self):
        """
        Rule: 'If a robot has multiple weapons that make contact, determine which component
        each hits independently, the throw strength is the maximum throw transferred,
        and each receives the full feedback.'
        """
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        # Give Player Bot two active weapons
        w1 = ComponentHealth(
            id="w1", name="NightWing Disc", card_type="weapon", max_durability=8, current_durability=8,
            absorption=0, requirements="", outputs="5W", keywords="", text="",
            x=100, y=20, rotation=0, box=(100, 20, 140, 60), is_active=True,
        )
        w2 = ComponentHealth(
            id="w2", name="Single Tooth Disc", card_type="weapon", max_durability=8, current_durability=8,
            absorption=0, requirements="", outputs="3W", keywords="", text="",
            x=150, y=20, rotation=0, box=(150, 20, 190, 60), is_active=True,
        )
        p_bot.components["w1"] = w1
        p_bot.components["w2"] = w2
        p_bot.weapon_spin_counters["w1"] = 1
        p_bot.weapon_spin_counters["w2"] = 1

        # Automaton target components
        target1 = ComponentHealth(
            id="t1", name="Front Armor", card_type="component", max_durability=10, current_durability=10,
            absorption=1, requirements="", outputs="", keywords="", text="",
            x=100, y=20, rotation=0, box=(100, 20, 140, 60), is_active=True,
        )
        target2 = ComponentHealth(
            id="t2", name="Front Wheel", card_type="component", max_durability=6, current_durability=6,
            absorption=0, requirements="", outputs="D", keywords="", text="",
            x=150, y=20, rotation=0, box=(150, 20, 190, 60), is_active=True,
        )
        a_bot.components["t1"] = target1
        a_bot.components["t2"] = target2

        col = CollisionEvent(
            time_t=0.5,
            contact_point=(400.0, 400.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=["w1", "w2"],
            robot2_components=["t1", "t2"],
            contact_type="ACTIVE",
            description="Multi-weapon strike",
            r1_active_hit=True,
            r2_active_hit=False,
            r1_active_weapons=["w1", "w2"],
            r2_active_weapons=[],
            r1_weapon_targets={"w1": ["t1"], "w2": ["t2"]},
            r2_weapon_targets={},
        )

        logs = resolve_collision_combat(col, p_bot, a_bot, round_num=1)

        # 1. Target 1 took 5 dmg (from w1): 10 - (5 - 1) = 6 dur remaining
        self.assertEqual(target1.current_durability, 6)
        # 2. Target 2 took 3 dmg (from w2): 6 - 3 = 3 dur remaining
        self.assertEqual(target2.current_durability, 3)

        # 3. Throw: w1 throw = 5 - 1 = 4; w2 throw = 3 - 0 = 3; max throw transferred is 4
        self.assertTrue(any(f"{a_bot.name} is THROWN" in e.message and "Strength 4" in e.message for e in logs))

        # 4. Feedback: total attack = 5 + 3 = 8; recoil feedback = 8 // 2 = 4
        # Each weapon receives full feedback: w1 dur 8 -> 4, w2 dur 8 -> 4
        self.assertEqual(w1.current_durability, 4)
        self.assertEqual(w2.current_durability, 4)

    def test_multi_component_contact_each_damaged_max_throw(self):
        """
        Rule: 'Similarly if a weapon contacts multiple components at once, each component
        is damaged, and the throw strength received is the maximum that would be transferred.'
        """
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        w1 = ComponentHealth(
            id="w1", name="Heavy Spinner", card_type="weapon", max_durability=10, current_durability=10,
            absorption=0, requirements="", outputs="6W", keywords="", text="",
            x=100, y=20, rotation=0, box=(100, 20, 140, 60), is_active=True,
        )
        p_bot.components["w1"] = w1
        p_bot.weapon_spin_counters["w1"] = 1

        target1 = ComponentHealth(
            id="t1", name="Front Armor Plate", card_type="component", max_durability=10, current_durability=10,
            absorption=1, requirements="", outputs="", keywords="", text="",
            x=100, y=20, rotation=0, box=(100, 20, 140, 60), is_active=True,
        )
        target2 = ComponentHealth(
            id="t2", name="Heavy Bumper", card_type="component", max_durability=10, current_durability=10,
            absorption=4, requirements="", outputs="", keywords="", text="",
            x=140, y=20, rotation=0, box=(140, 20, 180, 60), is_active=True,
        )
        a_bot.components["t1"] = target1
        a_bot.components["t2"] = target2

        # Weapon contacts both components at once
        col = CollisionEvent(
            time_t=0.5,
            contact_point=(400.0, 400.0),
            robot1_octant="Front",
            robot2_octant="Front",
            robot1_components=["w1"],
            robot2_components=["t1", "t2"],
            contact_type="ACTIVE",
            description="Multi-component seam hit",
            r1_active_hit=True,
            r2_active_hit=False,
            r1_active_weapons=["w1"],
            r2_active_weapons=[],
            r1_weapon_targets={"w1": ["t1", "t2"]},
            r2_weapon_targets={},
        )

        logs = resolve_collision_combat(col, p_bot, a_bot, round_num=1)

        # Both components take damage 6
        # t1: 6 dmg - 1 abs = 5 net dmg -> 10 - 5 = 5 dur
        self.assertEqual(target1.current_durability, 5)
        # t2: 6 dmg - 4 abs = 2 net dmg -> 10 - 2 = 8 dur
        self.assertEqual(target2.current_durability, 8)

        # Max throw transferred: max(6 - 1, 6 - 4) = max(5, 2) = 5
        self.assertTrue(any(f"{a_bot.name} is THROWN" in e.message and "Strength 5" in e.message for e in logs))

    def test_nightwing_skip_components_without_wedge_fork_drive(self):
        """
        Rule: 'unless inverted this component's attacks skip past components without wedge, fork or drive'
        """
        from playtest.engine.collision import find_components_along_contact_line
        from playtest.engine.field import MAT_CENTER_X, MAT_CENTER_Y, MAT_TO_MINI_SCALE

        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        bot = match.player_robot
        bot.components.clear()

        # Place armor plate in front along North axis (y = 50, center x = MAT_CENTER_X)
        armor = ComponentHealth(
            id="c_armor", name="Armor Plate", card_type="armor", max_durability=10, current_durability=10,
            absorption=2, requirements="", outputs="", keywords="", text="",
            x=MAT_CENTER_X - 20, y=50, rotation=0, box=(MAT_CENTER_X - 20, 50, MAT_CENTER_X + 20, 90), is_active=True,
        )
        # Place wheel behind armor (y = 95)
        wheel = ComponentHealth(
            id="c_wheel", name="Snap Wheels", card_type="drive", max_durability=8, current_durability=8,
            absorption=0, requirements="", outputs="2D", keywords="", text="",
            x=MAT_CENTER_X - 20, y=95, rotation=0, box=(MAT_CENTER_X - 20, 95, MAT_CENTER_X + 20, 135), is_active=True,
        )
        bot.components["c_armor"] = armor
        bot.components["c_wheel"] = wheel

        # World pose: center (400, 400), heading 0 (facing North).
        # Contact point right on North front of bot inside armor plate (y = 70 on mat)
        contact_pt = (400.0, 400.0 - 80.0 * MAT_TO_MINI_SCALE)

        # 1. Upright NightWing: skip_without_wedge_fork_drive=True -> skips armor, targets wheel!
        hit_upright = find_components_along_contact_line(
            bot, contact_pt, 400.0, 400.0, 0.0, "Front", skip_without_wedge_fork_drive=True
        )
        self.assertEqual(hit_upright, ["c_wheel"])

        # 2. Inverted NightWing (or normal weapon): skip_without_wedge_fork_drive=False -> hits outermost armor!
        hit_inverted = find_components_along_contact_line(
            bot, contact_pt, 400.0, 400.0, 0.0, "Front", skip_without_wedge_fork_drive=False
        )
        self.assertEqual(hit_inverted, ["c_armor"])

    def test_weapon_wall_contact_feedback_rounded_up(self):
        """
        Rule: 'If its weapon hits a wall it takes feedback to the weapon equal to half the sum
        of its weapon strength and the throw strength, rounded up, and then any spin counters
        it has are removed.'
        """
        from playtest.engine.combat import resolve_weapon_wall_contact
        from playtest.engine.field import WALL_LEFT
        from playtest.engine.movement import MINIATURE_RADIUS
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        bot = match.player_robot

        w = ComponentHealth(
            id="w1", name="Wall Striker", card_type="weapon", template="disc_standard", max_durability=6, current_durability=6,
            absorption=0, requirements="", outputs="3W", keywords="", text="",
            x=100, y=20, rotation=0, box=(100, 20, 140, 60), is_active=True,
        )
        bot.components["w1"] = w
        bot.weapon_spin_counters["w1"] = 1

        # Position robot facing left wall so weapon crosses wall
        bot.pose = Pose(x=WALL_LEFT + 10.0, y=400.0, theta=270.0)

        # Attack strength = 3, throw_strength = 2 -> sum = 5 -> feedback = (5 + 1) // 2 = 3
        logs = resolve_weapon_wall_contact(bot, throw_strength=2, round_num=1)
        self.assertTrue(any("suffered 3 feedback ((weapon strength 3 + throw strength 2) / 2, rounded up)" in e.message for e in logs))
        self.assertEqual(w.current_durability, 3)
        self.assertEqual(bot.weapon_spin_counters["w1"], 0)

    def test_post_throw_separation_by_one_unit(self):
        """
        Rule: 'If a thrown robot would end up in contact with another robot, separate them by 1 unit.'
        """
        from playtest.engine.collision import check_robots_in_contact
        from playtest.engine.combat import separate_robots_full_unit
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        r1 = match.player_robot
        r2 = match.automaton_robot

        # Place robots overlapping / in contact
        r1.pose = Pose(x=400.0, y=400.0, theta=0.0)
        r2.pose = Pose(x=400.0, y=410.0, theta=180.0)
        self.assertTrue(check_robots_in_contact(r1, r2))

        sep_logs = separate_robots_full_unit(r1, r2, round_num=1, log_prefix="Post-throw separation")
        self.assertTrue(any("Post-throw separation" in e.message for e in sep_logs))
        self.assertFalse(check_robots_in_contact(r1, r2))

    def test_multi_weapon_miniature_geometry(self):
        from playtest.engine.collision import get_robot_miniature_parts
        csv_text = read_saved_robot("Beater_wide.csv")
        match = create_match(csv_text, "Nightwing_wide", "Player Bot")
        auto = match.automaton_robot

        # Nightwing has 2 weapons: NightWing AR500 Disc (id '7') and Single Tooth Disc (id '8')
        weapons = [c for c in auto.components.values() if c.card_type == "weapon"]
        self.assertEqual(len(weapons), 2)

        parts = get_robot_miniature_parts(auto, px=400.0, py=200.0, theta=180.0)
        self.assertEqual(len(parts["weapon_parts"]), 2)
        self.assertEqual(len(parts["active_weapon_parts"]), 2)

        weapon_cids = {wp["cid"] for wp in parts["weapon_parts"]}
        self.assertEqual(len(weapon_cids), 2)

    def test_template_crossed_determines_component_hit(self):
        """
        Rule: 'When working out what component is hit, if a template is crossed that weapon is the component hit in that contact.'
        """
        from playtest.engine.collision import find_components_along_contact_line
        from playtest.engine.field import MAT_CENTER_X, MAT_CENTER_Y, MAT_TO_MINI_SCALE

        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        bot = match.player_robot
        bot.components.clear()

        # Place armor plate at front bumper
        armor = ComponentHealth(
            id="c_armor", name="Front Armor", card_type="armor", max_durability=10, current_durability=10,
            absorption=2, requirements="", outputs="", keywords="", text="",
            x=MAT_CENTER_X - 20, y=50, rotation=0, box=(MAT_CENTER_X - 20, 50, MAT_CENTER_X + 20, 90), is_active=True,
        )
        # Place weapon with Circle template (radius 22mm on mini) centered at chassis center
        wpn = ComponentHealth(
            id="c_spinner", name="Spinner Disc", card_type="weapon", max_durability=12, current_durability=12,
            absorption=1, requirements="", outputs="2XW", keywords="", text="",
            template="Circle",
            x=MAT_CENTER_X - 20, y=MAT_CENTER_Y - 20, rotation=0,
            box=(MAT_CENTER_X - 20, MAT_CENTER_Y - 20, MAT_CENTER_X + 20, MAT_CENTER_Y + 20), is_active=True,
        )
        bot.components["c_armor"] = armor
        bot.components["c_spinner"] = wpn

        # Strike from front (North): contact point at y = -20mm on mini (within Circle template radius 22mm)
        # World pose: center (400, 400), facing North (theta = 0)
        contact_pt = (400.0, 400.0 - 20.0)

        # The contact line crosses the weapon's Circle template, so the weapon is the component hit!
        hit_cids = find_components_along_contact_line(
            bot, contact_pt, 400.0, 400.0, 0.0, "Front"
        )
        self.assertEqual(hit_cids, ["c_spinner"])

    def test_multi_point_contact_same_component_damage_once(self):
        """
        Rule: 'For weapons with multiple points of contact they can both hit the same thing, but they only deal damage once.'
        """
        from playtest.engine.combat import _resolve_single_weapon_attack
        from playtest.engine.types import CollisionEvent

        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        # Attacking weapon
        prongs_wpn = ComponentHealth(
            id="w_prongs", name="Lifter Claw", card_type="weapon", max_durability=10, current_durability=10,
            absorption=2, requirements="", outputs="6W", keywords="Forks", text="",
            template="Prongs", x=100, y=20, rotation=0, box=(100, 20, 140, 60), is_active=True,
        )
        p_bot.components["w_prongs"] = prongs_wpn

        # Defender target component with durability 10 (half is 5)
        target = ComponentHealth(
            id="c_target", name="Heavy Armor", card_type="armor", max_durability=10, current_durability=10,
            absorption=0, requirements="", outputs="", keywords="", text="",
            x=100, y=20, rotation=0, box=(100, 20, 140, 60), is_active=True,
        )
        a_bot.components = {"c_target": target}

        col = CollisionEvent(
            time_t=0.5, contact_point=(400.0, 400.0),
            robot1_octant="Front", robot2_octant="Front",
            robot1_components=["w_prongs"], robot2_components=["c_target"],
            contact_type="ACTIVE", description="Claw attack",
            r1_active_hit=True, r2_active_hit=False,
        )

        logs = []
        # Multi-point contact: both prongs hit "c_target"
        atk_str, throw_str = _resolve_single_weapon_attack(
            attacker=p_bot, defender=a_bot, weapon=prongs_wpn, col=col,
            defender_ray_cids=["c_target", "c_target"], round_num=1, logs=logs
        )

        # Damage dealt is 6 once, NOT 6 + 6 = 12
        self.assertTrue(target.is_damaged)
        self.assertFalse(target.is_destroyed, "Should only take damage once, not be destroyed by double damage")
        damage_entries = [e for e in logs if "[Damage]" in e.message]
        self.assertEqual(len(damage_entries), 1, "Damage should only be applied once")

    def test_multi_point_contact_different_components_damage_each(self):
        """
        Rule: When a weapon contacts multiple components at once, each component is damaged.
        """
        from playtest.engine.combat import _resolve_single_weapon_attack
        from playtest.engine.types import CollisionEvent

        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        prongs_wpn = ComponentHealth(
            id="w_prongs", name="Lifter Claw", card_type="weapon", max_durability=10, current_durability=10,
            absorption=2, requirements="", outputs="6W", keywords="Forks", text="",
            template="Prongs", x=100, y=20, rotation=0, box=(100, 20, 140, 60), is_active=True,
        )
        p_bot.components["w_prongs"] = prongs_wpn

        t1 = ComponentHealth(
            id="c_left", name="Left Armor", card_type="armor", max_durability=10, current_durability=10,
            absorption=0, requirements="", outputs="", keywords="", text="",
            x=80, y=20, rotation=0, box=(80, 20, 100, 60), is_active=True,
        )
        t2 = ComponentHealth(
            id="c_right", name="Right Armor", card_type="armor", max_durability=10, current_durability=10,
            absorption=0, requirements="", outputs="", keywords="", text="",
            x=120, y=20, rotation=0, box=(120, 20, 140, 60), is_active=True,
        )
        a_bot.components = {"c_left": t1, "c_right": t2}

        col = CollisionEvent(
            time_t=0.5, contact_point=(400.0, 400.0),
            robot1_octant="Front", robot2_octant="Front",
            robot1_components=["w_prongs"], robot2_components=["c_left", "c_right"],
            contact_type="ACTIVE", description="Claw dual strike",
            r1_active_hit=True, r2_active_hit=False,
        )

        logs = []
        atk_str, throw_str = _resolve_single_weapon_attack(
            attacker=p_bot, defender=a_bot, weapon=prongs_wpn, col=col,
            defender_ray_cids=["c_left", "c_right"], round_num=1, logs=logs
        )

        self.assertTrue(t1.is_damaged)
        self.assertTrue(t2.is_damaged)
        damage_entries = [e for e in logs if "[Damage]" in e.message]
        self.assertEqual(len(damage_entries), 2, "Both distinct components should be damaged")

    def test_raised_flip_strength_not_halved(self):
        """
        Rule: Remove any references to changing flip strength. Raised robot does NOT halve flip strength.
        """
        from playtest.engine.combat import _execute_throw

        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        bot = match.player_robot
        bot.flip_strength = 6
        bot.is_raised = True
        bot.is_inverted = False

        # If throw_str = 5 and roll is fixed or low:
        # excess_throw can be at most 5 - 1 = 4.
        # If flip_strength were halved (6 // 2 = 3), excess_throw 4 > 3 would cause inversion!
        # With unhalved flip_strength 6, excess_throw 4 <= 6, so robot is NOT inverted!
        logs = []
        import random
        orig_randint = random.randint
        try:
            random.randint = lambda a, b: 1  # Force roll_d6 = 1 -> thrown_units = 1
            _execute_throw(bot, throw_str=5, contact_point=(400.0, 400.0), round_num=1, logs=logs)
            self.assertFalse(bot.is_inverted, "Raised robot must NOT invert when excess throw (4) <= full flip strength (6)")
        finally:
            random.randint = orig_randint


if __name__ == "__main__":
    unittest.main()



