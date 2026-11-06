import unittest
from playtest.engine.types import Pose, RobotState, ComponentHealth, CollisionEvent, CombatLogEntry
from playtest.engine.field import (
    push_robot_inside_arena_if_past_wall,
    get_chassis_grid_cells,
)
from playtest.engine.movement import DRIVE_UNIT_MM, snap_pose_to_grid
from playtest.engine.combat import (
    apply_damage_to_component,
    ensure_robots_not_overlapping,
    resolve_inert_contact,
)
from playtest.engine.collision import find_components_along_contact_line
from playtest.engine.match import create_match, execute_turn, MoveChoice, read_saved_robot


def make_bot(bid: str, name: str, pose: Pose, chassis_template: str = "Square", components: dict = None, **kwargs) -> RobotState:
    comps = components or {}
    cids = list(comps.keys())
    return RobotState(
        id=bid,
        name=name,
        chassis_name="Chassis",
        chassis_template=chassis_template,
        flip_strength=3,
        pose=pose,
        components=comps,
        connections={cid: cids for cid in cids},
        supply_graph={cid: [] for cid in cids},
        reverse_supply={cid: [] for cid in cids},
        **kwargs
    )


class TestNewRulesVerification(unittest.TestCase):

    def test_wall_push_in_on_rotation(self):
        """
        Rule: when a robot would occupy any tile past a wall (say due to rotating)
        it is pushed into the arena until all of it is inside the arena.
        Arena interior is [100, 700] x [100, 700].
        """
        pose_wide = Pose(x=420.0, y=140.0, theta=90.0)
        pushed = push_robot_inside_arena_if_past_wall(pose_wide, "Wide")
        self.assertGreaterEqual(pushed.y, 180.0)

        cells = get_chassis_grid_cells("Wide", pushed)
        for cx, cy in cells:
            self.assertGreaterEqual(cx * 40, 100)
            self.assertLessEqual((cx + 1) * 40, 700)
            self.assertGreaterEqual(cy * 40, 100)
            self.assertLessEqual((cy + 1) * 40, 700)

        pose_tri = Pose(x=140.0, y=420.0, theta=90.0)
        pushed_tri = push_robot_inside_arena_if_past_wall(pose_tri, "Triangle")
        cells_tri = get_chassis_grid_cells("Triangle", pushed_tri)
        for cx, cy in cells_tri:
            self.assertGreaterEqual(cx * 40, 100)
            self.assertLessEqual((cx + 1) * 40, 700)
            self.assertGreaterEqual(cy * 40, 100)
            self.assertLessEqual((cy + 1) * 40, 700)

    def test_raised_robot_deflection_on_push(self):
        """
        Rule: while a robot is raised, any time it would push another robot instead
        it is moved back from the contact. (Stationary robot stays where it is).
        """
        moving_bot = make_bot(
            bid="r1", name="Bot 1", chassis_template="Square",
            pose=Pose(x=400.0, y=360.0, theta=0.0),
            is_raised=True,
        )
        stationary_bot = make_bot(
            bid="r2", name="Bot 2", chassis_template="Square",
            pose=Pose(x=400.0, y=320.0, theta=180.0),
            is_raised=False,
        )

        col = CollisionEvent(
            time_t=0.5,
            contact_point=(400.0, 340.0),
            robot1_octant="front",
            robot2_octant="front",
            robot1_components=[],
            robot2_components=[],
            contact_type="INERT",
            description="Front to front contact",
            step_index=0,
        )

        steps = [{"type": "forwards", "direction": 1}]
        logs = resolve_inert_contact(
            col=col,
            r1=moving_bot,
            r2=stationary_bot,
            round_num=1,
            moving_robot_id="r1",
            moving_rem_steps=steps,
        )

        # Stationary bot did not move!
        self.assertEqual(stationary_bot.pose.x, 400.0)
        self.assertEqual(stationary_bot.pose.y, 320.0)

        # Moving bot deflected back from contact (away from stationary bot, so in +y direction: 360 -> 400)
        self.assertEqual(moving_bot.pose.x, 400.0)
        self.assertEqual(moving_bot.pose.y, 400.0)

        deflect_logs = [l.message for l in logs if "instead of pushing" in l.message]
        self.assertTrue(len(deflect_logs) > 0)
        self.assertIn("Bot 1 is RAISED", deflect_logs[0])

    def test_raised_robot_deflection_in_non_overlapping(self):
        moving_bot = make_bot(
            bid="r1", name="Bot 1", chassis_template="Square",
            pose=Pose(x=400.0, y=360.0, theta=0.0),
            is_raised=True,
        )
        stationary_bot = make_bot(
            bid="r2", name="Bot 2", chassis_template="Square",
            pose=Pose(x=400.0, y=360.0, theta=180.0),
            is_raised=False,
        )
        logs = []
        ensure_robots_not_overlapping(moving_bot, stationary_bot, 1, logs)
        self.assertEqual(stationary_bot.pose.y, 360.0)
        self.assertNotEqual(moving_bot.pose.y, 360.0)
        self.assertTrue(any("instead of pushing" in l.message for l in logs))

    def test_raised_robot_retains_action_cards(self):
        csv_text = read_saved_robot("Vyper_Spinner.csv")
        match = create_match(csv_text, "Vyper_flipper", "Player Bot")
        p_bot = match.player_robot
        a_bot = match.automaton_robot

        a_bot.is_raised = True

        execute_turn(match, MoveChoice(0, 0, cards=["Wait", "Wait", "Wait"]), fixed_automaton_roll=1)

        cancelled_actions = [a for a in match.action_step_results if a.get("cancelled") and a.get("reason") == "Robot is raised"]
        self.assertEqual(len(cancelled_actions), 0)
        self.assertFalse(a_bot.is_raised)

    def test_component_damage_and_destruction_thresholds(self):
        comp = ComponentHealth(
            id="c1", name="Armor", card_type="component",
            max_durability=4, current_durability=4, absorption=1,
            requirements="", outputs="", keywords="", text="",
            x=0, y=0, rotation=0, box=(0, 0, 44, 64),
        )

        st1, abs1, ex1 = apply_damage_to_component(comp, 3.0, is_weapon_damage=True)
        self.assertEqual(st1, "UNDAMAGED")
        self.assertEqual(abs1, 1.0)
        self.assertEqual(ex1, 2.0)
        self.assertFalse(comp.is_damaged)
        self.assertFalse(comp.is_destroyed)

        st2, abs2, ex2 = apply_damage_to_component(comp, 4.0, is_weapon_damage=True)
        self.assertEqual(st2, "DAMAGED")
        self.assertEqual(abs2, 1.0)
        self.assertEqual(ex2, 3.0)
        self.assertTrue(comp.is_damaged)
        self.assertFalse(comp.is_destroyed)

        st3, abs3, ex3 = apply_damage_to_component(comp, 5.0, is_weapon_damage=True)
        self.assertEqual(st3, "DESTROYED")
        self.assertEqual(abs3, 4.0)
        self.assertEqual(ex3, 1.0)
        self.assertTrue(comp.is_destroyed)

        comp2 = ComponentHealth(
            id="c2", name="Armor 2", card_type="component",
            max_durability=4, current_durability=4, absorption=1,
            requirements="", outputs="", keywords="", text="",
            x=0, y=0, rotation=0, box=(0, 0, 44, 64),
        )
        st4, abs4, ex4 = apply_damage_to_component(comp2, 10.0, is_weapon_damage=True)
        self.assertEqual(st4, "DESTROYED")
        self.assertEqual(abs4, 4.0)
        self.assertEqual(ex4, 6.0)
        self.assertTrue(comp2.is_destroyed)

    def test_wedge_armor_side_protection(self):
        robot = make_bot(
            bid="bot", name="Test Bot", chassis_template="Square",
            pose=Pose(x=420.0, y=420.0, theta=0.0),
        )
        wedge = ComponentHealth(
            id="wedge_front", name="Titanium Wedge", card_type="component",
            max_durability=5, current_durability=5, absorption=1,
            requirements="", outputs="", keywords="wedge",
            text="attacks that hit this components side hit this instead",
            x=188.0, y=50.0, rotation=0, box=(188.0, 50.0, 232.0, 114.0),
            is_wedge=True,
        )
        motor = ComponentHealth(
            id="motor_front", name="Motor", card_type="component",
            max_durability=3, current_durability=3, absorption=1,
            requirements="", outputs="", keywords="", text="",
            x=188.0, y=100.0, rotation=0, box=(188.0, 100.0, 232.0, 164.0),
        )
        robot.components["wedge_front"] = wedge
        robot.components["motor_front"] = motor

        cids = find_components_along_contact_line(
            robot=robot,
            contact_pt=(420.0, 390.0),
            robot_x=420.0,
            robot_y=420.0,
            robot_theta=0.0,
            octant="front",
            is_weapon_contact=True,
        )
        self.assertEqual(cids, ["wedge_front"])


if __name__ == "__main__":
    unittest.main()
