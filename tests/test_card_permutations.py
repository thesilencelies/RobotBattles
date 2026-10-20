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

    def test_baseline_defaults(self):
        # Bloodsport Bar
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
        self.assertIn(r"\weighticon", tex_default)
        self.assertNotIn(r"\weighticonplain", tex_default)
        self.assertIn(r"\$\$\$", tex_default)
        self.assertNotIn(r"\$3", tex_default)

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


if __name__ == "__main__":
    unittest.main()
