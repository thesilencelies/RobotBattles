"""Tests for Router and API routes."""

import json
import unittest

from builder.server.routes import Router


class TestServerRoutes(unittest.TestCase):
    def setUp(self):
        self.router = Router()

    def test_get_cards(self):
        res = self.router.dispatch("GET", "/api/cards", {}, b"")
        self.assertEqual(res.status, 200)
        data = json.loads(res.body.decode("utf-8"))
        self.assertIn("chassis", data)
        self.assertIn("components", data)
        self.assertIn("weapons", data)
        self.assertIn("all", data)

    def test_get_chassis(self):
        res = self.router.dispatch("GET", "/api/chassis", {}, b"")
        self.assertEqual(res.status, 200)
        data = json.loads(res.body.decode("utf-8"))
        self.assertGreater(len(data), 0)
        self.assertIn("geometry", data[0])
        self.assertEqual(data[0]["sheet_width_mm"], 420.0)
        self.assertEqual(data[0]["sheet_height_mm"], 297.0)

    def test_robot_parse_and_serialize_api(self):
        csv_text = (
            'id,card,location,connections\n'
            '1,Viper Wedge Chassis,"chassis:0,0,0",\n'
            '2,Four-Bar Lifter,"chassis:120.0,80.0,90",\n'
        )
        res_parse = self.router.dispatch("POST", "/api/robots/parse", {}, csv_text.encode("utf-8"))
        self.assertEqual(res_parse.status, 200)
        parsed = json.loads(res_parse.body.decode("utf-8"))
        self.assertEqual(parsed["chassis"]["name"], "Viper Wedge Chassis")
        self.assertEqual(len(parsed["placed_cards"]), 1)
        self.assertEqual(parsed["placed_cards"][0]["rotation"], 90)

        # Now serialize it back
        res_ser = self.router.dispatch(
            "POST", "/api/robots/serialize", {}, json.dumps(parsed).encode("utf-8")
        )
        self.assertEqual(res_ser.status, 200)
        self.assertIn("Four-Bar Lifter", res_ser.body.decode("utf-8"))

    def test_serve_static_index(self):
        res = self.router.dispatch("GET", "/", {}, b"")
        self.assertEqual(res.status, 200)
        self.assertIn("text/html", res.content_type)
        self.assertIn(b"Combat Robotics - Robot Builder", res.body)

    def test_serve_static_assets(self):
        res_css = self.router.dispatch("GET", "/app.css", {}, b"")
        self.assertEqual(res_css.status, 200)
        self.assertIn("text/css", res_css.content_type)

        res_js = self.router.dispatch("GET", "/js/app.js", {}, b"")
        self.assertEqual(res_js.status, 200)
        self.assertIn("javascript", res_js.content_type)

        res_manifest = self.router.dispatch("GET", "/manifest.webmanifest", {}, b"")
        self.assertEqual(res_manifest.status, 200)

    def test_serve_card_image(self):
        res = self.router.dispatch("GET", "/CardImages/Viper_Wedge_Chassis.png", {}, b"")
        self.assertEqual(res.status, 200)
        self.assertEqual(res.content_type, "image/png")

    def test_chassis_svg_endpoint(self):
        res = self.router.dispatch("GET", "/api/chassis/Viper%20Wedge%20Chassis/svg", {}, b"")
        self.assertEqual(res.status, 200)
        self.assertIn("image/svg+xml", res.content_type)
        self.assertIn(b"<svg", res.body)


if __name__ == "__main__":
    unittest.main()
