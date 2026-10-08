"""Tests for builder.server.data module."""

import unittest
from pathlib import Path

from builder.server.data import (
    CARD_HEIGHT_MM,
    CARD_WIDTH_MM,
    compute_card_box,
    compute_connections,
    load_all_cards,
    parse_robot_csv,
    serialize_robot_csv,
)

class TestData(unittest.TestCase):
    def test_card_dimensions(self):
        self.assertEqual(CARD_WIDTH_MM, 44.0)
        self.assertEqual(CARD_HEIGHT_MM, 64.0)

    def test_load_all_cards(self):
        catalog = load_all_cards()
        self.assertGreater(len(catalog["chassis"]), 0)
        self.assertGreater(len(catalog["components"]), 0)
        self.assertGreater(len(catalog["weapons"]), 0)

        # Verify "all" only contains playable cards, no chassis
        for card in catalog["all"]:
            self.assertNotEqual(card.get("type"), "chassis")

        # Verify Viper Wedge Chassis is present in chassis list
        viper = next((c for c in catalog["chassis"] if c["name"] == "Viper Wedge Chassis"), None)
        self.assertIsNotNone(viper)
        self.assertEqual(viper["weight"], 3)
        self.assertEqual(viper["cost"], 2)
        self.assertEqual(viper["template"], "Square")
        self.assertEqual(viper["flip_strength"], 5)
        self.assertIsNotNone(viper["image_url"])

    def test_compute_card_box(self):
        # 0 rotation
        box0 = compute_card_box(10.0, 20.0, 0, w=64.0, h=89.0)
        self.assertEqual(box0, (10.0, 20.0, 74.0, 109.0))

        # 90 rotation (w and h swapped)
        box90 = compute_card_box(10.0, 20.0, 90, w=64.0, h=89.0)
        self.assertEqual(box90, (10.0, 20.0, 99.0, 84.0))

    def test_compute_connections(self):
        # Two cards placed right next to each other (touching within 3mm)
        card1 = {
            "id": "1",
            "card": "Galaxy 120",
            "location": "chassis:100.0,100.0,0",
        }
        card2 = {
            "id": "2",
            "card": "Wires",
            "location": f"chassis:{100.0 + CARD_WIDTH_MM},100.0,0",
        }
        card3 = {
            "id": "3",
            "card": "Micro Servo",
            "location": "chassis:300.0,300.0,0",  # Far away
        }

        conns = compute_connections([card1, card2, card3])
        self.assertIn("2", conns["1"])
        self.assertIn("1", conns["2"])
        self.assertEqual(conns["3"], [])

    def test_robot_csv_roundtrip(self):
        sample_csv = (
            "id,card,location,connections\n"
            "1,Viper Wedge Chassis,chassis:0,0,0,\n"
            "2,Four-Bar Lifter,chassis:150.0,70.0,0,3\n"
            "3,Galaxy 300 3S,chassis:150.0,159.0,0,2\n"
            "4,Repeat 2207 Hubmotor,spares:0,\n"
        )

        parsed = parse_robot_csv(sample_csv)
        self.assertEqual(parsed["chassis"]["name"], "Viper Wedge Chassis")
        self.assertEqual(len(parsed["placed_cards"]), 2)
        self.assertEqual(len(parsed["spare_cards"]), 1)
        self.assertEqual(parsed["placed_cards"][0]["card"], "Four-Bar Lifter")
        self.assertEqual(parsed["spare_cards"][0]["card"], "Repeat 2207 Hubmotor")

        serialized = serialize_robot_csv(parsed)
        lines = [line.strip() for line in serialized.strip().split("\n") if line.strip()]
        self.assertEqual(lines[0], "id,card,location,connections")
        self.assertIn("Viper Wedge Chassis", lines[1])
        self.assertIn("Four-Bar Lifter", serialized)
        self.assertIn("Galaxy 300 3S", serialized)
        self.assertIn("Repeat 2207 Hubmotor", serialized)


if __name__ == "__main__":
    unittest.main()
