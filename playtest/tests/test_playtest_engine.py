"""Unit tests for the playtest rules engine."""

import sys
import unittest
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

        # 2. Straight (3, 3) -> Forward along North (-y) by 3 * 35 = 105 mm
        traj_fwd = generate_trajectory(start, MoveChoice(3, 3), num_steps=10)
        self.assertAlmostEqual(traj_fwd[-1].x, 400.0, places=1)
        self.assertAlmostEqual(traj_fwd[-1].y, 495.0, places=1)
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

        # Vyper_flipper: 1 = Retreat, 2 = Face, 3..6 = Rush
        self.assertEqual(get_automaton_action("Vyper_flipper", robot, 1), "Retreat")
        self.assertEqual(get_automaton_action("Vyper_flipper", robot, 2), "Face")
        self.assertEqual(get_automaton_action("Vyper_flipper", robot, 5), "Rush")

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


if __name__ == "__main__":
    unittest.main()
