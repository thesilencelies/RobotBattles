"""Integration tests for Playtest server routes."""

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from builder.server.data import read_saved_robot
from playtest.server.routes import Router


class TestPlaytestServer(unittest.TestCase):
    def setUp(self):
        self.router = Router()

    def test_get_cards(self):
        res = self.router.dispatch("GET", "/api/cards", {}, b"")
        self.assertEqual(res.status, 200)
        data = json.loads(res.body.decode("utf-8"))
        self.assertIn("chassis", data)
        self.assertIn("weapons", data)
        self.assertIn("components", data)

    def test_get_chassis(self):
        res = self.router.dispatch("GET", "/api/chassis", {}, b"")
        self.assertEqual(res.status, 200)
        data = json.loads(res.body.decode("utf-8"))
        self.assertTrue(len(data) >= 3)

    def test_get_automata(self):
        res = self.router.dispatch("GET", "/api/automata", {}, b"")
        self.assertEqual(res.status, 200)
        data = json.loads(res.body.decode("utf-8"))
        names = [r["name"] for r in data]
        self.assertTrue(any("Vyper" in n for n in names))

    def test_battle_state_auto_init(self):
        res = self.router.dispatch("GET", "/api/battle/state", {}, b"")
        self.assertEqual(res.status, 200)
        data = json.loads(res.body.decode("utf-8"))
        self.assertIn("match", data)
        self.assertIsNotNone(data["match"])
        match = data["match"]
        self.assertEqual(match["round"], 1)
        self.assertEqual(match["phase"], "planning")

    def test_battle_turn_execution(self):
        # 1. Init match
        self.router.dispatch("GET", "/api/battle/state", {}, b"")

        # 2. Execute turn
        payload = json.dumps({"left": 3, "right": 3, "fixed_roll": 4}).encode("utf-8")
        res = self.router.dispatch("POST", "/api/battle/turn", {}, payload)
        self.assertEqual(res.status, 200)
        data = json.loads(res.body.decode("utf-8"))
        match = data["match"]
        self.assertEqual(match["round"], 2)
        self.assertEqual(match["phase"], "planning")
        self.assertGreater(len(match["log"]), 1)

    def test_battle_new_with_csv(self):
        csv_text = read_saved_robot("Vyper_flipper.csv")
        payload = json.dumps({
            "player_csv": csv_text,
            "automaton": "Vyper_Spinner",
            "player_name": "Flipper Bot"
        }).encode("utf-8")

        res = self.router.dispatch("POST", "/api/battle/new", {}, payload)
        self.assertEqual(res.status, 200)
        data = json.loads(res.body.decode("utf-8"))
        match = data["match"]
        self.assertEqual(match["player_robot"]["name"], "Flipper Bot")
        self.assertEqual(match["automaton_type"], "Vyper_Spinner")

    def test_static_files(self):
        # Index HTML
        res_html = self.router.dispatch("GET", "/", {}, b"")
        self.assertEqual(res_html.status, 200)
        self.assertIn("Robot Battles - Playtest", res_html.body.decode("utf-8"))

        # App CSS
        res_css = self.router.dispatch("GET", "/app.css", {}, b"")
        self.assertEqual(res_css.status, 200)
        self.assertIn("--bg-dark", res_css.body.decode("utf-8"))

        # Builder CSS
        res_b_css = self.router.dispatch("GET", "/builder.css", {}, b"")
        self.assertEqual(res_b_css.status, 200)

        # Builder JS
        res_b_js = self.router.dispatch("GET", "/js/builder.js", {}, b"")
        self.assertEqual(res_b_js.status, 200)
        self.assertIn("BuilderController", res_b_js.body.decode("utf-8"))

        # Fallback to builder static files (canvas.js)
        res_canvas = self.router.dispatch("GET", "/js/canvas.js", {}, b"")
        self.assertEqual(res_canvas.status, 200)
        self.assertIn("MatCanvas", res_canvas.body.decode("utf-8"))

    def test_battle_new_with_custom_playcount(self):
        payload = json.dumps({
            "player_csv": read_saved_robot("Vyper_flipper.csv"),
            "automaton": "Vyper_Spinner",
            "max_rounds": 5,
        }).encode("utf-8")
        res = self.router.dispatch("POST", "/api/battle/new", {}, payload)
        self.assertEqual(res.status, 200)
        match = json.loads(res.body.decode("utf-8"))["match"]
        self.assertEqual(match["max_rounds"], 5)

        # Test 'playcount' alias
        payload2 = json.dumps({
            "player_csv": read_saved_robot("Vyper_flipper.csv"),
            "automaton": "Vyper_Spinner",
            "playcount": 3,
        }).encode("utf-8")
        res2 = self.router.dispatch("POST", "/api/battle/new", {}, payload2)
        self.assertEqual(res2.status, 200)
        match2 = json.loads(res2.body.decode("utf-8"))["match"]
        self.assertEqual(match2["max_rounds"], 3)

    def test_battle_new_default_max_rounds(self):
        payload = json.dumps({
            "player_csv": read_saved_robot("Vyper_flipper.csv"),
            "automaton": "Vyper_Spinner",
        }).encode("utf-8")
        res = self.router.dispatch("POST", "/api/battle/new", {}, payload)
        self.assertEqual(res.status, 200)
        match = json.loads(res.body.decode("utf-8"))["match"]
        self.assertEqual(match["max_rounds"], 20)

    def test_api_movement_template(self):
        # 1. Gentle curve (3, 2)
        res = self.router.dispatch("GET", "/api/movement/template", {"left": "3", "right": "2"}, b"")
        self.assertEqual(res.status, 200)
        data = json.loads(res.body.decode("utf-8"))
        tmpl = data.get("template") or data
        self.assertEqual(tmpl["template_id"], "curve_gentle")
        self.assertEqual(tmpl["nominal_rc"], 220.0)
        self.assertAlmostEqual(tmpl["target_angle_deg"], 26.0)

        # 2. Asymmetric counter (3, -1)
        res_asym = self.router.dispatch("GET", "/api/movement/template", {"left": "3", "right": "-1"}, b"")
        self.assertEqual(res_asym.status, 200)
        data_asym = json.loads(res_asym.body.decode("utf-8"))
        tmpl_asym = data_asym.get("template") or data_asym
        self.assertEqual(tmpl_asym["category"], "asymmetric_counter")
        self.assertEqual(tmpl_asym["spin_k"], 1)
        self.assertEqual(tmpl_asym["pivot_rem"], 2)

    def test_api_action_cards(self):
        res = self.router.dispatch("GET", "/api/action_cards", {}, b"")
        self.assertEqual(res.status, 200)
        data = json.loads(res.body.decode("utf-8"))
        self.assertIn("cards", data)
        self.assertEqual(len(data["cards"]), 18)
        codes = [c["code"] for c in data["cards"]]
        self.assertIn("Wait", codes)
        self.assertIn("1F", codes)
        self.assertIn("90 R", codes)
        self.assertIn("-45 L", codes)

    def test_api_battle_turn_with_cards(self):
        # Start new match
        new_payload = json.dumps({
            "player_csv": read_saved_robot("Vyper_flipper.csv"),
            "automaton": "Vyper_Spinner",
        }).encode("utf-8")
        self.router.dispatch("POST", "/api/battle/new", {}, new_payload)

        # Submit turn with 3 action cards
        turn_payload = json.dumps({
            "cards": ["1F", "45 R", "Wait"],
            "left": 2,
            "right": 1,
        }).encode("utf-8")
        res = self.router.dispatch("POST", "/api/battle/turn", {}, turn_payload)
        self.assertEqual(res.status, 200)
        match_data = json.loads(res.body.decode("utf-8"))["match"]
        self.assertEqual(match_data["player_action_cards"], ["1F", "45 R", "Wait"])
        self.assertIn("automaton_action_cards", match_data)
        self.assertEqual(len(match_data["automaton_action_cards"]), 3)
        self.assertIn("action_step_results", match_data)


if __name__ == "__main__":
    unittest.main()

