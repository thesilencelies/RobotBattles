"""
tests/test_movement_templates.py

Tests for the movement template generator and permutation mapping.
Verifies complete coverage of all 121 permutations from -5 to +5 on both tracks,
the minimality of the 6 consolidated physical templates, and SVG rendering integrity.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generate_movement_templates import (
    DEFAULT_DRIVE_UNIT_MM,
    DEFAULT_WHEELBASE_MM,
    MovementTemplate,
    build_all_movement_templates,
    compute_all_permutations,
    generate_printable_sheet_svg,
    generate_rulebook_preview_svg,
    map_permutation_to_template,
)


class TestMovementTemplates(unittest.TestCase):
    def test_permutation_coverage(self):
        """Verify that every pair in [-5, 5] x [-5, 5] is covered across the 8 templates."""
        all_perms = compute_all_permutations()
        self.assertEqual(len(all_perms), 121)

        seen_pairs = set()
        templates_used = set()

        for p in all_perms:
            l = p["left"]
            r = p["right"]
            seen_pairs.add((l, r))
            self.assertTrue(-5 <= l <= 5)
            self.assertTrue(-5 <= r <= 5)

            if l == 0 and r == 0:
                self.assertEqual(p["category"], "stop")
                self.assertEqual(p["template_id"], "stop")
            else:
                self.assertIn(p["category"], ["straight", "spin", "pivot", "curve_forward", "asymmetric_counter"])
                self.assertTrue(isinstance(p["flipped"], bool))
                self.assertTrue(isinstance(p["at_rear"], bool))
                self.assertTrue(len(p["target_line_label"]) > 0)
                templates_used.add(p["template_id"])

        # All 121 unique coordinate pairs checked
        self.assertEqual(len(seen_pairs), 121)

        # Non-zero pairs map to the 6 physical templates or asymmetric counter
        self.assertEqual(
            templates_used,
            {"straight", "spin", "pivot", "curve_gentle", "curve_medium", "curve_sharp", "spin_pivot"}
        )

    def test_symmetry_logic(self):
        """Verify flipping and rear placement for representative cases."""
        # Straight forward
        p_fwd = map_permutation_to_template(3, 3)
        self.assertEqual(p_fwd["template_id"], "straight")
        self.assertEqual(p_fwd["target_line_label"], "L3 R3")
        self.assertFalse(p_fwd["flipped"])
        self.assertFalse(p_fwd["at_rear"])

        # Straight reverse
        p_rev = map_permutation_to_template(-3, -3)
        self.assertEqual(p_rev["template_id"], "straight")
        self.assertEqual(p_rev["target_line_label"], "L3 R3")
        self.assertFalse(p_rev["flipped"])
        self.assertTrue(p_rev["at_rear"])

        # Forward gentle curve (3, 2) vs flipped (2, 3)
        p_gentle = map_permutation_to_template(3, 2)
        p_gentle_flip = map_permutation_to_template(2, 3)
        self.assertEqual(p_gentle["template_id"], "curve_gentle")
        self.assertEqual(p_gentle_flip["template_id"], "curve_gentle")
        self.assertEqual(p_gentle["target_line_label"], "L3 R2")
        self.assertEqual(p_gentle_flip["target_line_label"], "L3 R2")
        self.assertFalse(p_gentle["flipped"])
        self.assertTrue(p_gentle_flip["flipped"])

        # Forward medium curve (2, 1) and its strict multiple (4, 2) on SAME template
        p_med_21 = map_permutation_to_template(2, 1)
        p_med_42 = map_permutation_to_template(4, 2)
        p_med_flip = map_permutation_to_template(1, 2)
        self.assertEqual(p_med_21["template_id"], "curve_medium")
        self.assertEqual(p_med_42["template_id"], "curve_medium")
        self.assertEqual(p_med_flip["template_id"], "curve_medium")
        self.assertEqual(p_med_21["target_line_label"], "L2 R1")
        self.assertEqual(p_med_42["target_line_label"], "L4 R2")
        self.assertFalse(p_med_21["flipped"])
        self.assertTrue(p_med_flip["flipped"])  # Left turn is flipped!

        # Reverse medium curve (-2, -1) vs reverse left curve (-1, -2)
        p_rev_right = map_permutation_to_template(-2, -1)
        p_rev_left = map_permutation_to_template(-1, -2)
        self.assertEqual(p_rev_right["template_id"], "curve_medium")
        self.assertEqual(p_rev_left["template_id"], "curve_medium")
        self.assertTrue(p_rev_right["at_rear"])
        self.assertTrue(p_rev_left["at_rear"])
        self.assertFalse(p_rev_right["flipped"])
        self.assertTrue(p_rev_left["flipped"])

        # Forward sharp curve (3, 1), (4, 1), and (5, 1)
        p_sharp_31 = map_permutation_to_template(3, 1)
        p_sharp_41 = map_permutation_to_template(4, 1)
        self.assertEqual(p_sharp_31["template_id"], "curve_sharp")
        self.assertEqual(p_sharp_31["target_line_label"], "L3 R1")
        self.assertEqual(p_sharp_41["template_id"], "curve_sharp")
        self.assertEqual(p_sharp_41["target_line_label"], "L4 R1")

        # Asymmetric drive with negative (3, -1) and (3, -2): resolved via spin then pivot
        p_asym_31 = map_permutation_to_template(3, -1)
        self.assertEqual(p_asym_31["template_id"], "spin_pivot")
        self.assertEqual(p_asym_31["category"], "asymmetric_counter")
        self.assertIn("Spin L1 R-1", p_asym_31["target_line_label"])
        self.assertIn("Pivot L2 R0", p_asym_31["target_line_label"])

        p_asym_32 = map_permutation_to_template(3, -2)
        self.assertEqual(p_asym_32["template_id"], "spin_pivot")
        self.assertIn("Spin L2 R-2", p_asym_32["target_line_label"])
        self.assertIn("Pivot L1 R0", p_asym_32["target_line_label"])

        # Spin CW (2, -2) vs Spin CCW (-2, 2)
        p_spin_cw = map_permutation_to_template(2, -2)
        p_spin_ccw = map_permutation_to_template(-2, 2)
        self.assertEqual(p_spin_cw["template_id"], "spin")
        self.assertEqual(p_spin_ccw["template_id"], "spin")
        self.assertFalse(p_spin_cw["flipped"])
        self.assertTrue(p_spin_ccw["flipped"])

        # Pivot right (3, 0) vs Pivot left (0, 3)
        p_piv_r = map_permutation_to_template(3, 0)
        p_piv_l = map_permutation_to_template(0, 3)
        self.assertEqual(p_piv_r["template_id"], "pivot")
        self.assertEqual(p_piv_l["template_id"], "pivot")
        self.assertFalse(p_piv_r["flipped"])
        self.assertTrue(p_piv_l["flipped"])

    def test_consolidated_template_set(self):
        """Verify the 6 consolidated MovementTemplate definitions."""
        templates = build_all_movement_templates()
        self.assertEqual(len(templates), 6)

        categories = {}
        for t in templates:
            categories[t.category] = categories.get(t.category, 0) + 1
            w, h = t.get_dimensions()
            self.assertGreater(w, 0.0)
            self.assertGreater(h, 0.0)

            svg = t.to_svg()
            self.assertTrue(svg.startswith("<svg"))
            self.assertNotIn("START", svg)
            self.assertNotIn("°", svg)
            for l, r in t.pairs:
                self.assertIn(f"L{l} R{r}", svg)

        self.assertEqual(categories["straight"], 1)
        self.assertEqual(categories["spin"], 1)
        self.assertEqual(categories["pivot"], 1)
        self.assertEqual(categories["curve_forward"], 3)
        self.assertEqual(len(categories), 4)

    def test_sheet_and_preview_svg(self):
        """Verify multi-template sheet and rulebook preview generation."""
        templates = build_all_movement_templates()
        sheet_svg = generate_printable_sheet_svg(templates)
        self.assertTrue(sheet_svg.startswith("<svg"))
        self.assertTrue(sheet_svg.strip().endswith("</svg>"))
        self.assertIn("ROBOT BATTLES - MOVEMENT TEMPLATES", sheet_svg)
        self.assertIn("50 mm SCALE BAR", sheet_svg)

        preview_svg = generate_rulebook_preview_svg(templates)
        self.assertTrue(preview_svg.startswith("<svg"))
        self.assertTrue(preview_svg.strip().endswith("</svg>"))
        self.assertIn("Straight (1 to 5)", preview_svg)
        self.assertIn("Curve Template", preview_svg)

    def test_spin_and_pivot_rates_and_remainders(self):
        """Verify 90° spin increments, 45° pivot increments hitting 180° at (4,0), and remainder chaining."""
        templates = {t.template_id: t for t in build_all_movement_templates()}

        # Spin template has 4 increments (1 to 4), where 4 = 360°
        spin_t = templates["spin"]
        self.assertEqual(len(spin_t.pairs), 4)
        self.assertEqual(spin_t.pairs, [(1, -1), (2, -2), (3, -3), (4, -4)])

        # Pivot template has 4 increments (1 to 4), where 4 = 180°
        pivot_t = templates["pivot"]
        self.assertEqual(len(pivot_t.pairs), 4)
        self.assertEqual(pivot_t.pairs, [(1, 0), (2, 0), (3, 0), (4, 0)])

        # Permutation mapping for 5/0 and -5/0 triggers remainder
        p_5_0 = map_permutation_to_template(5, 0)
        self.assertEqual(p_5_0["template_id"], "pivot")
        self.assertIn("L4 R0 + L1 R0", p_5_0["target_line_label"])
        self.assertIn("remainder", p_5_0["remainder_note"].lower())

        p_neg5_0 = map_permutation_to_template(-5, 0)
        self.assertEqual(p_neg5_0["template_id"], "pivot")
        self.assertTrue(p_neg5_0["at_rear"])
        self.assertIn("remainder", p_neg5_0["remainder_note"].lower())

        # Permutation mapping for 5/-5 triggers remainder
        p_5_neg5 = map_permutation_to_template(5, -5)
        self.assertEqual(p_5_neg5["template_id"], "spin")
        self.assertIn("L4 R-4 + L1 R-1", p_5_neg5["target_line_label"])
        self.assertIn("remainder", p_5_neg5["remainder_note"].lower())


if __name__ == "__main__":
    unittest.main()
