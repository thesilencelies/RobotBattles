"""Unit tests for combat simulation engine."""

import unittest
from pathlib import Path

from builder.server.data import load_all_cards
from scripts.simulate_combat import (
    PlacedComponent,
    build_robot_model,
    compute_card_box,
    parse_weapon_spin_and_damage,
    resolve_single_component_hit,
    simulate_drive_pushing_feedback,
    simulate_inward_damage_progression,
    simulate_throw_shock,
    simulate_weapon_feedback,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class TestCombatSimulation(unittest.TestCase):
    def setUp(self):
        self.catalog = load_all_cards()

    def test_weapon_damage_parsing(self):
        by_name = {w["name"]: w for w in self.catalog["weapons"]}

        # Horizontal Spinner: 2XW, max spin 4
        h_spin = by_name["Horizontal Spinner"]
        max_s, d_map, _ = parse_weapon_spin_and_damage(h_spin)
        self.assertEqual(max_s, 4)
        self.assertEqual(d_map[1], 2)
        self.assertEqual(d_map[2], 4)
        self.assertEqual(d_map[3], 6)
        self.assertEqual(d_map[4], 8)

        # Bloodsport Bar: 2XW, max spin 4
        bb = by_name["Bloodsport Bar"]
        max_s, d_map, _ = parse_weapon_spin_and_damage(bb)
        self.assertEqual(max_s, 4)
        self.assertEqual(d_map[4], 8)

        # Beater Bar: XWWW -> X*W + 2W = X + 2
        beater = by_name["Beater Bar"]
        max_s, d_map, desc = parse_weapon_spin_and_damage(beater)
        self.assertEqual(max_s, 3)
        self.assertEqual(d_map[1], 3)
        self.assertEqual(d_map[2], 4)
        self.assertEqual(d_map[3], 5)

        # Cronos Scythe: XWW -> X*W + W = X + 1
        scythe = by_name["Cronos Scythe"]
        max_s, d_map, desc = parse_weapon_spin_and_damage(scythe)
        self.assertEqual(max_s, 2)
        self.assertEqual(d_map[1], 2)
        self.assertEqual(d_map[2], 3)

        # Chonk Key Blade: XXW -> X^2 * W = X^2
        chonk = by_name["Chonk Key Blade"]
        max_s, d_map, _ = parse_weapon_spin_and_damage(chonk)
        self.assertEqual(max_s, 3)
        self.assertEqual(d_map[1], 1)
        self.assertEqual(d_map[2], 4)
        self.assertEqual(d_map[3], 9)

        # Four-Bar Lifter: 10W, deals 0 direct damage
        lifter = by_name["Four-Bar Lifter"]
        max_s, d_map, _ = parse_weapon_spin_and_damage(lifter)
        self.assertEqual(d_map[0], 0)

    def test_damage_resolution_rules(self):
        # Component: Durability 10, Absorption 4
        comp = PlacedComponent(
            id="1",
            name="Test Armor",
            card_type="component",
            durability=10,
            absorption=4,
            requirements="",
            outputs="",
            keywords="",
            text="",
            x=0,
            y=0,
            rotation=0,
            box=(0, 0, 44, 64),
        )

        # Hit with 3 damage: 3 <= 4 absorption -> absorbed cleanly, 0 excess
        res3 = resolve_single_component_hit(comp, 3.0)
        self.assertEqual(res3.status, "UNDAMAGED")
        self.assertEqual(res3.excess_damage, 0.0)

        # Hit with 8 damage: net = 4. 4 <= 10/2 (5) -> UNDAMAGED, excess = 4
        res8 = resolve_single_component_hit(comp, 8.0)
        self.assertEqual(res8.status, "UNDAMAGED")
        self.assertEqual(res8.excess_damage, 4.0)

        # Hit with 10 damage: net = 6 > 5 -> DAMAGED, excess = 6
        res10 = resolve_single_component_hit(comp, 10.0)
        self.assertEqual(res10.status, "DAMAGED")
        self.assertEqual(res10.excess_damage, 6.0)

        # Hit with 12 damage: 12 > 10 durability -> DESTROYED, absorbs 10, excess = 2
        res12 = resolve_single_component_hit(comp, 12.0)
        self.assertEqual(res12.status, "DESTROYED")
        self.assertEqual(res12.absorbed_damage, 10.0)
        self.assertEqual(res12.excess_damage, 2.0)

    def test_fragile_keyword_destruction(self):
        comp = PlacedComponent(
            id="1",
            name="Simple ESC",
            card_type="component",
            durability=5,
            absorption=3,
            requirements="EE",
            outputs="EE",
            keywords="fragile",
            text="",
            x=0,
            y=0,
            rotation=0,
            box=(0, 0, 44, 64),
            is_fragile=True,
        )

        # Taking 2 weapon damage -> effective dur is 1 -> DESTROYED
        res = resolve_single_component_hit(comp, 2.0, is_weapon_damage=True)
        self.assertEqual(res.status, "DESTROYED")
        self.assertEqual(res.effective_durability, 1)

    def test_load_and_simulate_automata(self):
        csv_path = REPO_ROOT / "automata" / "Vyper_Spinner.csv"
        robot = build_robot_model(csv_path, self.catalog)

        self.assertEqual(robot.name, "Vyper_Spinner")
        self.assertGreater(len(robot.components), 10)
        self.assertIn("19", robot.components)  # Horizontal Spinner

        # Test weapon recoil feedback
        h_spin = robot.components["19"]
        # Spin 4 with high damage -> 20 attack damage -> 10 feedback -> destroys Horizontal Spinner (dur 9)
        fb_steps = simulate_weapon_feedback(robot, h_spin, 20)
        self.assertTrue(any(s.status == "DESTROYED" for s in fb_steps))

        # Test drive pushing feedback (opponent remaining distance 3)
        push_steps = simulate_drive_pushing_feedback(robot, 3)
        self.assertTrue(all(s.status == "UNDAMAGED" for s in push_steps))

        # Test throw shock
        shock_outcomes = simulate_throw_shock(robot, 10, hit_on_wedge=False)
        self.assertEqual(len(shock_outcomes), len(robot.components))

    def test_generate_html_report(self):
        from scripts.simulate_combat import generate_html_report

        csv_path = REPO_ROOT / "automata" / "Vyper_Spinner.csv"
        robot = build_robot_model(csv_path, self.catalog)
        html_out = generate_html_report([robot], self.catalog)

        self.assertIn("<!DOCTYPE html>", html_out)
        self.assertIn("Vyper_Spinner", html_out)
        self.assertIn("Direct Hit Lethality Matrix (Perimeter Components)", html_out)
        self.assertIn("Feedback Chain Escalation & Failure Analysis", html_out)
        self.assertIn("Effective Throw Shock Damage Chart", html_out)

        # Verify that direct hit matrix includes exposed perimeter components
        self.assertIn("Horizontal Spinner", html_out)
        self.assertIn("Titanium Wedge", html_out)
        self.assertIn("TPU Plate", html_out)
        self.assertIn("UHMW Wraparound Armor", html_out)

        # Verify that internal components (battery #2, internal motors) are NOT in the matrix th columns
        import re
        matrix_header = re.search(r"<table class=\"matrix-table\">.*?<thead>\s*<tr>(.*?)</tr>\s*</thead>", html_out, re.DOTALL)
        self.assertIsNotNone(matrix_header)
        th_cells = re.findall(r"<th>(.*?)</th>", matrix_header.group(1), re.DOTALL)
        self.assertEqual(len(th_cells), len(robot.outer_components))
        # Ensure battery is not a column in direct hit matrix
        self.assertFalse(any("Galaxy 300 3S" in th for th in th_cells))

    def test_card_resource_rendering(self):
        from cardCreation.generateCards import parse_resources

        # 2XWW -> 1 fixed W + 2X multiplier W
        out_2xww = parse_resources("2XWW")
        self.assertIn(r"\resourceW", out_2xww)
        self.assertIn("2X", out_2xww)

        # XWW -> 1 fixed W + X multiplier W
        out_xww = parse_resources("XWW")
        self.assertIn(r"\resourceW", out_xww)
        self.assertIn("X", out_xww)

        # XWWW -> 2 fixed W + X multiplier W
        out_xwww = parse_resources("XWWW")
        self.assertIn(r"\resourceW\hspace{1.5pt}\resourceW", out_xwww)
        self.assertIn("X", out_xwww)

        # XXW -> XxX multiplier W
        out_xxw = parse_resources("XXW")
        self.assertIn("XxX", out_xxw)
        self.assertNotIn("XXW", out_xxw)

        # Pure repeated letters: WWWW
        out_wwww = parse_resources("WWWW")
        self.assertIn(r"\parbox", out_wwww)
        self.assertEqual(out_wwww.count(r"\resourceW"), 4)


if __name__ == "__main__":
    unittest.main()


