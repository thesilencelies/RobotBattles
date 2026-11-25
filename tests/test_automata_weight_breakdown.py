"""
test_automata_weight_breakdown.py

Tests for scripts.automata_weight_breakdown module:
- Verification of total weight = 40 for all official automata
- Correct categorization of components across electronics, weapons, armor, drivetrain
- Correct attribution of motors/servos to their supplied subsystem
- CLI table, markdown, CSV, and JSON formatting
"""

import json
import sys
import unittest
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_DIR))

from scripts.automata_weight_breakdown import (
    analyze_all_automata,
    analyze_automaton,
    format_detailed,
    format_table,
)


class TestAutomataWeightBreakdown(unittest.TestCase):
    def setUp(self):
        self.automata = analyze_all_automata()
        self.by_name = {b.bot_name: b for b in self.automata}

    def test_all_automata_present(self):
        expected_bots = {
            "Beater_wide",
            "Billet_HammerSaw",
            "Chonk",
            "Nightwing_wide",
            "Sparrow_crusher",
            "Vyper_Spinner",
            "Vyper_flipper",
        }
        self.assertTrue(expected_bots.issubset(set(self.by_name.keys())))

    def test_all_automata_sum_to_forty(self):
        """Every official automaton must strictly satisfy the 40 weight limit with chassis included."""
        for b in self.automata:
            self.assertEqual(
                b.total_weight,
                40,
                f"{b.bot_name} total weight {b.total_weight} != 40",
            )
            # Verify sum of categories equals total
            cat_sum = (
                b.electronics_weight
                + b.weapons_weight
                + b.armor_weight
                + b.drivetrain_weight
            )
            self.assertEqual(cat_sum, b.total_weight)

    def test_motor_supply_attribution(self):
        """Motors must be attributed to the subsystem they supply."""
        # 1. Beater_wide: Motor 14 supplies Beater Bar (Weapons), Motors 5 & 6 supply Wheels (Drivetrain)
        bw = self.by_name["Beater_wide"]
        self.assertEqual(bw.electronics_weight, 8)  # 2x Tattu 450 (4+4)
        self.assertEqual(bw.weapons_weight, 7)      # Beater Bar (4) + Hubmotor (3)
        self.assertEqual(bw.drivetrain_weight, 12)  # 4 wheels (6) + 2 Hubmotors (6)
        self.assertEqual(bw.armor_weight, 13)       # Horns (6) + Top plate (3) + 2 TPU (2) + Chassis (2)

        # 2. Sparrow_crusher: D2830 Weapon Motors used for drive must count as Drivetrain!
        sc = self.by_name["Sparrow_crusher"]
        self.assertEqual(sc.drivetrain_weight, 16)  # 4 wheels (8) + 2 D2830 Motors (8)
        self.assertEqual(sc.weapons_weight, 7)      # Crushing Claw (3) + 25kg Servo (4)
        self.assertEqual(sc.electronics_weight, 8)  # Galaxy 1000 (5) + Galaxy 300 (3)
        self.assertEqual(sc.armor_weight, 9)        # Chassis (3) + 4 TPU (4) + Self-righting arm (1) + Micro servo (1)

        # 3. Chonk: D2830 Weapon Motor supplies Chonk Key Blade
        ck = self.by_name["Chonk"]
        self.assertEqual(ck.weapons_weight, 10)     # Chonk Key Blade (6) + D2830 Motor (4)
        self.assertEqual(ck.drivetrain_weight, 12)  # 4 wheels (6) + 2 Hubmotors (6)
        self.assertEqual(ck.electronics_weight, 8)  # 2x Tattu 450 (8)
        self.assertEqual(ck.armor_weight, 10)       # Chassis (3) + UHMW (3) + 2 TPU (2) + Self-righting (2)

        # 4. Billet_HammerSaw: 15kg Servo and 22mm Motor both supply Hammer Saw
        bhs = self.by_name["Billet_HammerSaw"]
        self.assertEqual(bhs.weapons_weight, 8)     # Hammer Saw (3) + 15kg Servo (2) + 22mm Motor (3)
        self.assertEqual(bhs.drivetrain_weight, 12) # 4 wheels (6) + 2 Hubmotors (6)
        self.assertEqual(bhs.electronics_weight, 7) # Galaxy 1000 (5) + Galaxy 120 (2)
        self.assertEqual(bhs.armor_weight, 13)      # Chassis (3) + 2 Wedges (6) + 4 TPU (4)

    def test_exclude_chassis_flag(self):
        """When chassis is excluded, total weight should reflect placed components only."""
        no_chassis = analyze_all_automata(include_chassis=False)
        by_name_nc = {b.bot_name: b for b in no_chassis}
        bw = by_name_nc["Beater_wide"]
        self.assertEqual(bw.total_weight, 38)
        self.assertEqual(bw.armor_weight, 11)

        sc = by_name_nc["Sparrow_crusher"]
        self.assertEqual(sc.total_weight, 37)
        self.assertEqual(sc.armor_weight, 6)

    def test_formatting_outputs(self):
        """Table, Markdown, and detailed formatting must not crash and produce expected content."""
        table = format_table(self.automata, markdown=False)
        self.assertIn("Beater_wide", table)
        self.assertIn("AVERAGE", table)

        md_table = format_table(self.automata, markdown=True)
        self.assertIn("| **Beater_wide** |", md_table)
        self.assertIn("| **AVERAGE** |", md_table)

        detailed = format_detailed(self.automata)
        self.assertIn("ELECTRONICS", detailed)
        self.assertIn("DRIVETRAIN", detailed)

    def test_json_serialization(self):
        """JSON output dictionary must contain all required breakdown fields."""
        bw = self.by_name["Beater_wide"]
        d = bw.to_dict()
        self.assertEqual(d["bot_name"], "Beater_wide")
        self.assertIn("breakdown", d)
        self.assertEqual(d["breakdown"]["total"], 40)
        self.assertEqual(d["breakdown"]["electronics"], 8)
        self.assertEqual(d["breakdown"]["weapons"], 7)
        self.assertEqual(d["breakdown"]["armor"], 13)
        self.assertEqual(d["breakdown"]["drivetrain"], 12)


if __name__ == "__main__":
    unittest.main()
