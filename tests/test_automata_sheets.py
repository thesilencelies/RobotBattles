"""
test_automata_sheets.py

Tests for scripts.generate_automata_sheets module:
- Name normalization and capitalization
- Action table archetype mapping and table format
- Zero overlap layout guarantee on all automata
- Connection line generation
- Standalone PDF compilation
"""

import sys
import tempfile
import unittest
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_DIR))

from scripts.generate_automata_sheets import (
    AUTOMATA_DIR,
    compile_latex_to_pdf,
    components_supply_each_other,
    compute_connection_segment,
    extract_connected_pairs,
    generate_action_table_tex,
    generate_latex_document,
    generate_robot_page_tikz,
    get_action_table_for_bot,
    normalize_robot_name,
    process_robot_csv,
    resolve_layout,
    tex_escape,
)


class TestAutomataSheets(unittest.TestCase):
    def test_normalize_robot_name(self):
        self.assertEqual(normalize_robot_name("Beater_wide"), "Beater Wide")
        self.assertEqual(normalize_robot_name("Nightwing_wide"), "Nightwing Wide")
        self.assertEqual(normalize_robot_name("Vyper_Spinner"), "Vyper Spinner")
        self.assertEqual(normalize_robot_name("Vyper_flipper"), "Vyper Flipper")
        self.assertEqual(normalize_robot_name("Chonk"), "Chonk")

    def test_tex_escape(self):
        self.assertEqual(tex_escape("Viper & Wedge"), r"Viper \& Wedge")
        self.assertEqual(tex_escape("100% Power"), r"100\% Power")
        self.assertEqual(tex_escape("$25 Budget"), r"\$25 Budget")
        self.assertEqual(tex_escape("< 2 Spin"), r"$<$ 2 Spin")

    def test_action_table_mapping(self):
        vf = get_action_table_for_bot("Vyper_flipper")
        self.assertEqual(vf["archetype_name"], "Full Rush")
        self.assertIn("Full Rush", vf["title"])

        vs = get_action_table_for_bot("Vyper_Spinner")
        self.assertEqual(vs["archetype_name"], "Spin Up")

        bw = get_action_table_for_bot("Beater_wide")
        self.assertEqual(bw["archetype_name"], "Balanced")

        nw = get_action_table_for_bot("Nightwing_wide")
        self.assertEqual(nw["archetype_name"], "Balanced")

        ck = get_action_table_for_bot("Chonk")
        self.assertEqual(ck["archetype_name"], "Spin Up")

    def test_generate_action_table_tex(self):
        vf = get_action_table_for_bot("Vyper_flipper")
        tex = generate_action_table_tex(vf)
        self.assertIn("Full Rush Action Table", tex)
        self.assertIn("Retreat", tex)
        self.assertIn("Face", tex)
        self.assertIn("Evade", tex)
        self.assertIn("Rush", tex)

    def test_zero_overlap_all_automata(self):
        """Verifies that resolve_layout produces strictly 0 overlapping card pairs for all 5 bots."""
        csv_files = sorted(AUTOMATA_DIR.glob("*.csv"))
        self.assertGreaterEqual(len(csv_files), 5)

        for csv_file in csv_files:
            b_info = process_robot_csv(csv_file, scale=0.80, min_gap=3.0)
            boxes = b_info["resolved_boxes"]
            self.assertGreater(len(boxes), 0)

            # Check for overlaps
            overlaps = 0
            for i in range(len(boxes)):
                b1 = boxes[i]
                for j in range(i + 1, len(boxes)):
                    b2 = boxes[j]
                    dx = abs(b2["cx"] - b1["cx"])
                    dy = abs(b2["cy"] - b1["cy"])
                    if dx < (b1["w"] + b2["w"]) / 2.0 - 0.01 and dy < (b1["h"] + b2["h"]) / 2.0 - 0.01:
                        overlaps += 1

            self.assertEqual(
                overlaps,
                0,
                f"Bot {csv_file.stem} had {overlaps} overlapping card pairs after layout resolution!",
            )

            # Verify bounds fit on A3 landscape (420mm x 297mm)
            for b in boxes:
                self.assertGreaterEqual(b["cx"] - b["w"] / 2.0, 0.0)
                self.assertLessEqual(b["cx"] + b["w"] / 2.0, 420.0)
                self.assertGreaterEqual(b["cy"] - b["h"] / 2.0, 0.0)
                self.assertLessEqual(b["cy"] + b["h"] / 2.0, 297.0)

    def test_connection_lines_generated(self):
        """Verifies connected pairs are strictly supply links and styled as continuous thick lines."""
        # 1. Component supply logic unit checks
        batt = {"card": "Galaxy 120", "card_data": {"outputs": "EE", "requirements": ""}}
        motor = {"card": "Brushless Motor", "card_data": {"outputs": "SSS", "requirements": "EE"}}
        wheel = {"card": "Snap Wheels", "card_data": {"outputs": "D", "requirements": "SS"}}
        armor = {"card": "TPU Plate", "card_data": {"outputs": "", "requirements": ""}}
        servo = {"card": "20kg Metal Gear Servo", "card_data": {"outputs": "PPPP", "requirements": "EEE"}}
        lifter = {"card": "Four-Bar Lifter", "card_data": {"outputs": "WWWWWW", "requirements": "PPPP"}}

        self.assertTrue(components_supply_each_other(batt, motor))
        self.assertTrue(components_supply_each_other(motor, wheel))
        self.assertTrue(components_supply_each_other(servo, lifter))
        self.assertFalse(components_supply_each_other(armor, wheel))
        self.assertFalse(components_supply_each_other(armor, batt))
        self.assertFalse(components_supply_each_other(batt, batt))

        # 2. Extract pairs for Vyper Flipper
        b_info = process_robot_csv(AUTOMATA_DIR / "Vyper_flipper.csv")
        conns = b_info["connected_pairs"]
        self.assertGreater(len(conns), 0)

        box_map = {b["id"]: b for b in b_info["resolved_boxes"]}
        card_names = {b["id"]: b["card"] for b in b_info["resolved_boxes"]}

        # Armor and wedges should never be connected
        for id_a, id_b in conns:
            name_a = card_names.get(id_a, "")
            name_b = card_names.get(id_b, "")
            self.assertNotIn("Wedge", name_a)
            self.assertNotIn("Wedge", name_b)
            self.assertNotIn("Plate", name_a)
            self.assertNotIn("Plate", name_b)
            self.assertNotIn("Armor", name_a)
            self.assertNotIn("Armor", name_b)

        # 3. TikZ styling check
        page_tikz = generate_robot_page_tikz(b_info)
        conn_section = page_tikz.split("% Component Edge Connections")[1].split(r"\end{tikzpicture}")[0]
        self.assertIn(r"\draw[line width=5.5pt, teal!80!black, line cap=round]", conn_section)
        self.assertNotIn("Circle", conn_section)
        self.assertNotIn("dashed", conn_section)

    def test_single_bot_pdf_compilation(self):
        """Verifies end-to-end PDF generation for one bot."""
        b_info = process_robot_csv(AUTOMATA_DIR / "Vyper_flipper.csv")
        page_tikz = generate_robot_page_tikz(b_info)
        doc_tex = generate_latex_document([page_tikz])

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_pdf = Path(tmp_dir) / "Vyper_flipper_sheet.pdf"
            compile_latex_to_pdf(doc_tex, out_pdf)
            self.assertTrue(out_pdf.exists())
            self.assertGreater(out_pdf.stat().st_size, 10000)


if __name__ == "__main__":
    unittest.main()
