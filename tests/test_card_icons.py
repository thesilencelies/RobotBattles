from pathlib import Path
import unittest
from PIL import Image

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
ICONS_DIR = WORKSPACE_DIR / "pictures" / "icons"

EXPECTED_ICONS = [
    "weight.png",
    "weight_plain.png",
    "energy.png",
    "control.png",
    "spin.png",
    "pressure.png",
    "damage.png",
    "drive.png",
    "durability.png",
    "absorption.png",
    "template_circle.png",
    "template_large_circle.png",
    "template_line.png",
    "template_bar.png",
    "template_prongs.png",
    "template_square.png",
    "template_triangle.png",
    "template_wide.png",
]


class TestCardIcons(unittest.TestCase):
    def test_all_icons_exist_and_format(self):
        for name in EXPECTED_ICONS:
            path = ICONS_DIR / name
            self.assertTrue(path.is_file(), f"Icon missing: {name}")
            with Image.open(path) as im:
                self.assertEqual(im.size, (400, 400), f"Icon {name} has incorrect size {im.size}")
                self.assertEqual(im.mode, "RGBA", f"Icon {name} is not RGBA")

    def test_energy_icon_contrast_borders(self):
        with Image.open(ICONS_DIR / "energy.png") as im:
            pix = im.load()
            cyan_count = 0
            dark_count = 0
            for y in range(im.height):
                for x in range(im.width):
                    r, g, b, a = pix[x, y]
                    if a > 128:
                        if r < 60 and g > 180 and b > 200:
                            cyan_count += 1
                        elif r <= 30 and g <= 30 and b <= 30:
                            dark_count += 1
            self.assertGreater(cyan_count, 1000, "Energy icon missing cyan core")
            self.assertGreater(dark_count, 1000, "Energy icon missing high-contrast dark border")

    def test_spin_icon_contrast_borders(self):
        with Image.open(ICONS_DIR / "spin.png") as im:
            pix = im.load()
            orange_count = 0
            dark_count = 0
            for y in range(im.height):
                for x in range(im.width):
                    r, g, b, a = pix[x, y]
                    if a > 128:
                        if r > 200 and g > 80 and b < 50:
                            orange_count += 1
                        elif r <= 30 and g <= 30 and b <= 30:
                            dark_count += 1
            self.assertGreater(orange_count, 1000, "Spin icon missing orange spiral")
            self.assertGreater(dark_count, 1000, "Spin icon missing high-contrast dark border")

    def test_control_icon_contrast_borders(self):
        with Image.open(ICONS_DIR / "control.png") as im:
            pix = im.load()
            red_count = 0
            dark_count = 0
            for y in range(im.height):
                for x in range(im.width):
                    r, g, b, a = pix[x, y]
                    if a > 128:
                        if r > 180 and g < 50 and b < 50:
                            red_count += 1
                        elif r <= 30 and g <= 30 and b <= 30:
                            dark_count += 1
            self.assertGreater(red_count, 1000, "Control icon missing red knob")
            self.assertGreater(dark_count, 1000, "Control icon missing high-contrast dark border")

    def test_damage_icon_contrast_borders(self):
        with Image.open(ICONS_DIR / "damage.png") as im:
            pix = im.load()
            red_count = 0
            dark_count = 0
            for y in range(im.height):
                for x in range(im.width):
                    r, g, b, a = pix[x, y]
                    if a > 128:
                        if r > 180 and g < 50 and b < 50:
                            red_count += 1
                        elif r <= 30 and g <= 30 and b <= 30:
                            dark_count += 1
            self.assertGreater(red_count, 1000, "Damage icon missing red blast")
            self.assertGreater(dark_count, 1000, "Damage icon missing high-contrast dark border")

    def test_durability_icon_contrast_borders(self):
        with Image.open(ICONS_DIR / "durability.png") as im:
            pix = im.load()
            red_count = 0
            dark_count = 0
            white_count = 0
            for y in range(im.height):
                for x in range(im.width):
                    r, g, b, a = pix[x, y]
                    if a > 128:
                        if r > 140 and g < 40 and b < 40:
                            red_count += 1
                        elif r <= 30 and g <= 30 and b <= 30:
                            dark_count += 1
                        elif r > 240 and g > 240 and b > 240:
                            white_count += 1
            self.assertGreater(red_count, 1000, "Durability icon missing red body")
            self.assertGreater(dark_count, 1000, "Durability icon missing dark border")
            self.assertGreater(white_count, 200, "Durability icon missing white crack")

    def test_template_circle_contrast_borders(self):
        with Image.open(ICONS_DIR / "template_circle.png") as im:
            profile = [im.getpixel((x, 200)) for x in range(30, 85)]
            dark_pixels = [p for p in profile if p[3] > 128 and p[0] <= 30 and p[1] <= 30 and p[2] <= 30]
            red_pixels = [p for p in profile if p[3] > 128 and p[0] > 180 and p[1] < 50]
            self.assertTrue(len(dark_pixels) >= 4, "Template circle missing dark borders")
            self.assertTrue(len(red_pixels) >= 10, "Template circle missing red ring")
