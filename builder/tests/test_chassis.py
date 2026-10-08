"""Tests for chassis sheet generation."""

import unittest

from builder.server.chassis_sheets import (
    generate_chassis_svg,
    generate_printable_html,
    get_chassis_definitions,
)


class TestChassisSheets(unittest.TestCase):
    def test_chassis_definitions(self):
        defs = get_chassis_definitions()
        self.assertGreater(len(defs), 0)
        for ch in defs:
            self.assertIn("geometry", ch)
            self.assertIn("points", ch["geometry"])
            self.assertEqual(ch["sheet_width_mm"], 420.0)
            self.assertEqual(ch["sheet_height_mm"], 297.0)

    def test_generate_chassis_svg(self):
        defs = get_chassis_definitions()
        viper = next(c for c in defs if c["name"] == "Viper Wedge Chassis")
        svg = generate_chassis_svg(viper)
        self.assertIn('<svg xmlns="http://www.w3.org/2000/svg"', svg)
        self.assertIn('viewBox="0 0 420.0 297.0"', svg)
        self.assertIn("Viper Wedge Chassis", svg)
        self.assertIn("chassis-boundary-shape", svg)
        self.assertIn("FRONT / HEADING", svg)
        self.assertIn("WEIGHT", svg)
        self.assertIn("COST", svg)
        self.assertIn("FLIP STR", svg)
        self.assertIn("<image", svg)

    def test_generate_printable_html(self):
        defs = get_chassis_definitions()
        viper = next(c for c in defs if c["name"] == "Viper Wedge Chassis")
        html = generate_printable_html(viper)
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("size: A3 landscape;", html)
        self.assertIn("<svg", html)


if __name__ == "__main__":
    unittest.main()
