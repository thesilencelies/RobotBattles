import sys
from pathlib import Path
import unittest

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_DIR))

from cardCreation.generateCards import generate_card_tex, parse_resources
from cardCreation.generate_permutations import PERMUTATIONS


class TestCardPermutations(unittest.TestCase):
    def test_permutation_matrix_size(self):
        self.assertEqual(len(PERMUTATIONS), 12)
        perm_ids = [p["id"] for p in PERMUTATIONS]
        self.assertEqual(len(set(perm_ids)), 12)
        self.assertIn("p01_baseline", perm_ids)
        self.assertIn("p12_all_features", perm_ids)

    def test_p11_defaults(self):
        # Bloodsport Bar with P11 default: single weight number and $3
        card = {
            "Name": "Bloodsport Bar",
            "Weight": "6",
            "Cost": "3",
            "Template": "Large Circle",
            "Requirements": "SSSSS",
            "Outputs": "2XWW",
            "Durability": "12",
            "Absorption": "1",
        }
        tex_default = generate_card_tex(card)
        self.assertIn(r"\weighticonplain[0.85cm]", tex_default)
        self.assertIn(r"\textcolor{white}{\sffamily\bfseries\large 6}", tex_default)
        self.assertIn(r"\$3", tex_default)
        self.assertNotIn(r"\$\$\$", tex_default)

    def test_legacy_multiple_symbols_option(self):
        card = {
            "Name": "Bloodsport Bar",
            "Weight": "6",
            "Cost": "3",
            "Template": "Large Circle",
            "Requirements": "SSSSS",
            "Outputs": "2XWW",
            "Durability": "12",
            "Absorption": "1",
        }
        tex_mult = generate_card_tex(card, weight_mode="multiple", cost_number=False)
        self.assertIn(r"\weighticon", tex_mult)
        self.assertIn(r"\$\$\$", tex_mult)

    def test_resource_icon_sizing_5_or_more(self):
        # 5 icons (SSSSS) -> size [0.52cm]
        out_5s = parse_resources("SSSSS")
        self.assertIn(r"\resourceS[0.52cm]", out_5s)

        # 6 icons (WWWWWW) -> size [0.52cm]
        out_6w = parse_resources("WWWWWW")
        self.assertIn(r"\resourceW[0.52cm]", out_6w)

        # 4 icons (SSSS) -> standard size (no [0.52cm])
        out_4s = parse_resources("SSSS")
        self.assertNotIn(r"[0.52cm]", out_4s)
        self.assertIn(r"\resourceS", out_4s)

    def test_mixed_resource_requirements(self):
        # Hammer Saw: SSSPP (3 Spin, 2 Pressure) -> 5 icons total ([0.52cm]), 2 rows, no raw text SSSP
        out_ssspp = parse_resources("SSSPP")
        self.assertEqual(out_ssspp.count(r"\resourceS[0.52cm]"), 3)
        self.assertEqual(out_ssspp.count(r"\resourceP[0.52cm]"), 2)
        self.assertIn(r"\parbox{2.5cm}", out_ssspp)
        self.assertNotIn("SSSP", out_ssspp)

        # SP: 1 Spin, 1 Pressure -> single row, no parbox
        out_sp = parse_resources("SP")
        self.assertIn(r"\resourceS", out_sp)
        self.assertIn(r"\resourceP", out_sp)
        self.assertNotIn(r"\parbox", out_sp)

    def test_weight_options(self):
        card = {"Name": "Four-Bar Lifter", "Weight": "5", "Cost": "4", "Requirements": "PPPP", "Outputs": "WWWWWW"}
        
        # Mode: number
        tex_num = generate_card_tex(card, weight_mode="number")
        self.assertIn(r"\weighticonplain[0.85cm]", tex_num)
        self.assertIn(r"\textcolor{white}{\sffamily\bfseries\large 5}", tex_num)
        self.assertNotIn(r"\weighticon[0.58cm]", tex_num)

        # Mode: multiple_no_1t
        tex_no1t = generate_card_tex(card, weight_mode="multiple_no_1t")
        self.assertIn(r"\weighticonplain[0.58cm]", tex_no1t)
        self.assertNotIn(r"\weighticon[0.58cm]", tex_no1t)

    def test_cost_option(self):
        card = {"Name": "Four-Bar Lifter", "Weight": "5", "Cost": "4", "Requirements": "PPPP", "Outputs": "WWWWWW"}
        
        # Default cost: 4 signs in 2 rows
        tex_default = generate_card_tex(card, cost_number=False)
        self.assertIn(r"\begin{tabular}", tex_default)

        # Cost number: single $4
        tex_cost_num = generate_card_tex(card, cost_number=True)
        self.assertIn(r"\$4", tex_cost_num)
        self.assertNotIn(r"\begin{tabular}", tex_cost_num)

    def test_resource_math(self):
        # SSSSS -> 5 S
        res_math = parse_resources("SSSSS", resource_math=True)
        self.assertIn("5", res_math)
        self.assertIn(r"\resourceS", res_math)

        # 2XWW -> 2X+1 W
        out_2xww = parse_resources("2XWW", resource_math=True)
        self.assertIn("2X+1", out_2xww)
        self.assertIn(r"\resourceW", out_2xww)
        self.assertNotIn(r"\parbox", out_2xww)

        # XWWW -> X+2 W
        out_xwww = parse_resources("XWWW", resource_math=True)
        self.assertIn("X+2", out_xwww)
        self.assertIn(r"\resourceW", out_xwww)

        # EEEEEE -> 6 E
        out_e6 = parse_resources("EEEEEE", resource_math=True)
        self.assertIn("6", out_e6)
        self.assertIn(r"\resourceE", out_e6)

        # Pure character count: WWWWWW -> 6 W
        out_w6 = parse_resources("WWWWWW", resource_math=True)
        self.assertIn("6", out_w6)
        self.assertIn(r"\resourceW", out_w6)

        # Mixed requirements: SSSPP -> 3 S, 2 P in 2 rows
        out_ssspp_math = parse_resources("SSSPP", resource_math=True)
        self.assertIn("3", out_ssspp_math)
        self.assertIn(r"\resourceS", out_ssspp_math)
        self.assertIn("2", out_ssspp_math)
        self.assertIn(r"\resourceP", out_ssspp_math)
        self.assertIn(r"\parbox{2.5cm}", out_ssspp_math)
        self.assertNotIn("SSSP", out_ssspp_math)

        # Math variable Y
        out_2yw = parse_resources("2YW")
        self.assertIn("2Y", out_2yw)
        self.assertIn(r"\resourceW", out_2yw)
        out_yyw = parse_resources("YYW")
        self.assertIn("YxY", out_yyw)

    def test_single_ended_card_chevrons_and_positioning(self):
        left_chevron_sub = r"\fill [chevronpurple] (0.00, 5.15)"
        right_chevron_sub = r"\fill [chevronpurple] (4.85, 5.15)"

        # 1. Supply only (e.g. Battery)
        battery = {"Name": "Galaxy 120", "Outputs": "EE"}
        battery_tex = generate_card_tex(battery)
        self.assertNotIn(left_chevron_sub, battery_tex, "Supply-only card should not have left chevron")
        self.assertIn(right_chevron_sub, battery_tex, "Supply-only card should have right chevron")
        self.assertIn(r"at (3.95, 4.40)", battery_tex, "Supply icons must stay at the right side (3.95, 4.40)")
        self.assertNotIn(r"at (2.80, 4.40)", battery_tex, "Icons should not be placed in the middle (2.80, 4.40)")
        self.assertNotIn(r"at (1.65, 4.40)", battery_tex, "Supply-only card should have no node at (1.65, 4.40)")

        # 2. Requirements only (e.g. Self righting arm)
        arm = {"Name": "Self righting arm", "Requirements": "PP"}
        arm_tex = generate_card_tex(arm)
        self.assertIn(left_chevron_sub, arm_tex, "Requirements-only card should have left chevron")
        self.assertNotIn(right_chevron_sub, arm_tex, "Requirements-only card should not have right chevron")
        self.assertIn(r"at (1.65, 4.40)", arm_tex, "Requirement icons must stay at the left side (1.65, 4.40)")
        self.assertNotIn(r"at (2.80, 4.40)", arm_tex, "Icons should not be placed in the middle (2.80, 4.40)")
        self.assertNotIn(r"at (3.95, 4.40)", arm_tex, "Requirements-only card should have no node at (3.95, 4.40)")

        # 3. Both supply and requirements (e.g. Motor)
        motor = {"Name": "Brushless Motor", "Requirements": "EE", "Outputs": "SSS"}
        motor_tex = generate_card_tex(motor)
        self.assertIn(left_chevron_sub, motor_tex, "Card with both should have left chevron")
        self.assertIn(right_chevron_sub, motor_tex, "Card with both should have right chevron")
        self.assertIn(r"at (1.65, 4.40)", motor_tex)
        self.assertIn(r"at (3.95, 4.40)", motor_tex)
        self.assertNotIn(r"at (2.80, 4.40)", motor_tex)

        # 4. Neither supply nor requirements (e.g. Armor)
        armor = {"Name": "Aluminum Plate"}
        armor_tex = generate_card_tex(armor)
        self.assertNotIn(left_chevron_sub, armor_tex, "Armor card should have no left chevron")
        self.assertNotIn(right_chevron_sub, armor_tex, "Armor card should have no right chevron")
        self.assertNotIn(r"at (1.65, 4.40)", armor_tex)
        self.assertNotIn(r"at (3.95, 4.40)", armor_tex)
        self.assertNotIn(r"at (2.80, 4.40)", armor_tex)


if __name__ == "__main__":
    unittest.main()
