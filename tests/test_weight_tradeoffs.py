#!/usr/bin/env python3
"""
Unit tests for the weight tradeoff analysis tool:
tests/test_weight_tradeoffs.py
"""

from pathlib import Path
import unittest
import sys

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_DIR))

from scripts.analyze_weight_tradeoffs import (
    load_all_tradeoff_cards,
    parse_resource_string,
    parse_weapon_spinup,
    CardTradeoffData,
    CATEGORIES,
    generate_matplotlib_plots,
    generate_html_dashboard,
)


class TestWeightTradeoffAnalysis(unittest.TestCase):
    def setUp(self):
        self.cards = load_all_tradeoff_cards()

    def test_load_cards_not_empty(self):
        self.assertGreater(len(self.cards), 20, "Should load components and weapons")
        names = {c.name for c in self.cards}
        self.assertIn("Brushless Motor", names)
        self.assertIn("Micro Servo", names)
        self.assertIn("Snap Wheels", names)
        self.assertIn("Four-Bar Lifter", names)
        self.assertIn("Galaxy 300 3S", names)
        self.assertIn("Titanium Wedge", names)

    def test_parse_resource_string(self):
        res_type, count = parse_resource_string("EE")
        self.assertEqual(res_type, "E")
        self.assertEqual(count, 2.0)

        res_type, count = parse_resource_string("SSSS")
        self.assertEqual(res_type, "S")
        self.assertEqual(count, 4.0)

        res_type, count = parse_resource_string("DDDD")
        self.assertEqual(res_type, "D")
        self.assertEqual(count, 4.0)

        res_type, count = parse_resource_string("")
        self.assertEqual(res_type, "None")
        self.assertEqual(count, 0.0)

    def test_weapon_spinup_parsing(self):
        # 2XWW -> base 2 W, +2*X
        base, mult, quad = parse_weapon_spinup("2XWW")
        self.assertEqual(base, 2.0)
        self.assertEqual(mult, 2.0)
        self.assertFalse(quad)

        # 3XW -> base 1 W, +3*X
        base, mult, quad = parse_weapon_spinup("3XW")
        self.assertEqual(base, 1.0)
        self.assertEqual(mult, 3.0)
        self.assertFalse(quad)

        # XXW -> base 1 W, +1*(X^2)
        base, mult, quad = parse_weapon_spinup("XXW")
        self.assertEqual(base, 1.0)
        self.assertEqual(mult, 1.0)
        self.assertTrue(quad)

        # WWWWWW -> base 6 W, no spinup
        base, mult, quad = parse_weapon_spinup("WWWWWW")
        self.assertEqual(base, 6.0)
        self.assertEqual(mult, 0.0)
        self.assertFalse(quad)

    def test_card_categories_assignment(self):
        cards_by_name = {c.name: c for c in self.cards}

        self.assertEqual(cards_by_name["Brushless Motor"].category, "Motors")
        self.assertEqual(cards_by_name["Micro Servo"].category, "Servos")
        self.assertEqual(cards_by_name["Snap Wheels"].category, "Wheels")
        self.assertEqual(cards_by_name["Four-Bar Lifter"].category, "Weapons")
        self.assertEqual(cards_by_name["Galaxy 300 3S"].category, "Batteries")
        self.assertEqual(cards_by_name["Titanium Wedge"].category, "Armor")
        self.assertEqual(cards_by_name["Wires"].category, "Transmission")

    def test_weight_and_input_output_tradeoffs(self):
        cards_by_name = {c.name: c for c in self.cards}

        # Brushless Motor: Weight 2, In: 2E, Out: 3S
        bm = cards_by_name["Brushless Motor"]
        self.assertEqual(bm.weight, 2)
        self.assertEqual(bm.input_resource, "E")
        self.assertEqual(bm.input_qty, 2.0)
        self.assertEqual(bm.output_resource, "S")
        self.assertEqual(bm.output_qty_base, 3.0)
        self.assertEqual(bm.efficiency_ratio(0), 1.5)
        self.assertEqual(bm.weight_efficiency(0), 1.5)

        # Four-Bar Lifter: Weight 4, In: 4P, Out: 6W
        fbl = cards_by_name["Four-Bar Lifter"]
        self.assertEqual(fbl.weight, 4)
        self.assertEqual(fbl.input_resource, "P")
        self.assertEqual(fbl.input_qty, 4.0)
        self.assertEqual(fbl.output_resource, "W")
        self.assertEqual(fbl.output_qty_base, 6.0)
        self.assertEqual(fbl.efficiency_ratio(0), 1.5)
        self.assertEqual(fbl.weight_efficiency(0), 1.5)

        # Horizontal Spinner: Weight 5, In: 4S, Out: 2XWW (base 2, max spinup 4 -> 10)
        hs = cards_by_name["Horizontal Spinner"]
        self.assertEqual(hs.weight, 5)
        self.assertEqual(hs.input_resource, "S")
        self.assertEqual(hs.input_qty, 4.0)
        self.assertEqual(hs.output_at_x(0), 2.0)
        self.assertEqual(hs.output_at_x(4), 10.0)

    def test_html_dashboard_generation(self):
        output_dir = WORKSPACE_DIR / "scripts" / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        html_file = output_dir / "test_weight_tradeoffs.html"

        html_content = generate_html_dashboard(self.cards)
        self.assertIn("Robot Battles - Weight Tradeoff Analysis", html_content)
        self.assertIn("Brushless Motor", html_content)
        self.assertIn("Four-Bar Lifter", html_content)
        # Verify base64 icons are present
        self.assertIn("data:image/png;base64,", html_content)

        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        self.assertTrue(html_file.is_file())
        self.assertGreater(html_file.stat().st_size, 1000)

    def test_matplotlib_generation(self):
        output_dir = WORKSPACE_DIR / "scripts" / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate plots for Motors and Weapons
        generated = generate_matplotlib_plots(self.cards, output_dir, categories=["Motors", "Weapons"], spinup_x=0)
        self.assertTrue(len(generated) >= 2)
        for p in generated:
            self.assertTrue(Path(p).is_file())
            self.assertGreater(Path(p).stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
