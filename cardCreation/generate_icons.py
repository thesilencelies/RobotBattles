#!/usr/bin/env python3
"""
generate_icons.py

Procedurally generates clean, high-resolution temporary PNG icons with alpha
transparency for the Combat Robotics card game into pictures/icons/.

Icons generated:
- weight.png: Kettlebell / 1-tonne weight with "1T" text
- energy.png: Cyan lightning bolt (Resource E)
- control.png: Single red joystick transmitter (Resource C; repeated for CC)
- spin.png: Orange spiral (Resource S)
- drive.png: Drive motor / wheel symbol (Resource M)
- damage.png: Spiky red & orange blast / explosion burst (Resource W)
- durability.png: Red block with white jagged fracture line
- absorption.png: Black angled armor shield / plate
- template_circle.png: Red circle with black center dot
- template_line.png: Single red line
- template_bar.png: Wide block with red front line
- template_prongs.png: Wide bar with two red prongs (as on ExampleWeapon)
"""

import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

WORKSPACE = Path(__file__).resolve().parent.parent
ICONS_DIR = WORKSPACE / "pictures" / "icons"
ICONS_DIR.mkdir(parents=True, exist_ok=True)

ICON_SIZE = (400, 400)


def get_font(size: int, bold: bool = True):
    font_names = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold else "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    for fn in font_names:
        if Path(fn).is_file():
            try:
                return ImageFont.truetype(fn, size)
            except Exception:
                pass
    return ImageFont.load_default()


def create_weight_icon():
    im = Image.new("RGBA", ICON_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    # Top handle (loop)
    draw.ellipse((135, 15, 265, 145), fill=(20, 20, 15, 255))
    draw.ellipse((170, 50, 230, 110), fill=(0, 0, 0, 0))

    # Weight body (trapezoid with rounded base)
    points = [
        (135, 100),
        (265, 100),
        (370, 360),
        (30, 360),
    ]
    draw.polygon(points, fill=(20, 20, 15, 255))
    draw.rounded_rectangle((28, 335, 372, 370), radius=10, fill=(20, 20, 15, 255))

    # "1T" text in white
    font = get_font(130, bold=True)
    text = "1T"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    tx = (400 - tw) / 2
    ty = 175
    draw.text((tx, ty), text, font=font, fill=(255, 255, 255, 255))

    im.save(ICONS_DIR / "weight.png", "PNG")
    print(f"Created {ICONS_DIR / 'weight.png'}")


def create_energy_icon():
    # Cyan lightning bolt (Resource E)
    im = Image.new("RGBA", ICON_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    color = (0, 225, 255, 255)
    points = [
        (220, 15),
        (105, 175),
        (185, 175),
        (80, 385),
        (295, 165),
        (210, 165),
        (295, 15),
    ]
    draw.polygon(points, fill=color)

    im.save(ICONS_DIR / "energy.png", "PNG")
    print(f"Created {ICONS_DIR / 'energy.png'}")


def create_control_icon():
    # Single red RC joystick transmitter (Resource C)
    # When CC appears, two of these are placed side-by-side matching ExampleESC
    im = Image.new("RGBA", ICON_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    lw = 24
    # Console box at bottom: x=80..320, y=230..380
    draw.rectangle((80, 230, 320, 380), fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=lw)

    # Vertical joystick stem
    draw.line([(200, 110), (200, 240)], fill=(0, 0, 0, 255), width=lw)

    # Joystick red ball knob
    red = (235, 15, 15, 255)
    r = 75
    draw.ellipse((200 - r, 110 - r, 200 + r, 110 + r), fill=red)

    im.save(ICONS_DIR / "control.png", "PNG")
    print(f"Created {ICONS_DIR / 'control.png'}")


def create_spin_icon():
    # Orange spiral (Resource S)
    im = Image.new("RGBA", ICON_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    color = (245, 120, 0, 255)
    cx, cy = 200, 200
    points = []
    turns = 2.4
    steps = 600
    for i in range(steps):
        theta = i / steps * (turns * 2 * math.pi)
        r = 15 + (theta / (turns * 2 * math.pi)) * 160
        x = cx + r * math.cos(theta)
        y = cy + r * math.sin(theta)
        points.append((x, y))

    for i in range(len(points) - 1):
        w = int(24 + (i / steps) * 16)
        draw.line([points[i], points[i + 1]], fill=color, width=w)

    im.save(ICONS_DIR / "spin.png", "PNG")
    print(f"Created {ICONS_DIR / 'spin.png'}")


def create_damage_icon():
    # Red/orange blast/explosion star (Resource W)
    im = Image.new("RGBA", ICON_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    cx, cy = 200, 200
    num_points = 16
    outer_r = 185
    inner_r = 120

    points = []
    for i in range(num_points * 2):
        angle = i * math.pi / num_points
        r = outer_r if (i % 2 == 0) else inner_r
        px = cx + r * math.cos(angle)
        py = cy + r * math.sin(angle)
        points.append((px, py))

    draw.polygon(points, fill=(230, 20, 10, 255))

    inner_points = []
    for i in range(num_points * 2):
        angle = i * math.pi / num_points
        r = (outer_r * 0.72) if (i % 2 == 0) else (inner_r * 0.72)
        px = cx + r * math.cos(angle)
        py = cy + r * math.sin(angle)
        inner_points.append((px, py))
    draw.polygon(inner_points, fill=(255, 145, 0, 255))

    im.save(ICONS_DIR / "damage.png", "PNG")
    print(f"Created {ICONS_DIR / 'damage.png'}")


def create_drive_icon():
    # Wheel / motor drive symbol (Resource M)
    im = Image.new("RGBA", ICON_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    cx, cy = 200, 200
    color = (40, 45, 55, 255)
    draw.ellipse((40, 40, 360, 360), fill=color)
    draw.ellipse((90, 90, 310, 310), fill=(255, 255, 255, 255))
    draw.ellipse((140, 140, 260, 260), fill=color)

    for i in range(8):
        angle = i * math.pi / 4
        x1 = cx + 115 * math.cos(angle)
        y1 = cy + 115 * math.sin(angle)
        x2 = cx + 180 * math.cos(angle)
        y2 = cy + 180 * math.sin(angle)
        draw.line([(x1, y1), (x2, y2)], fill=(255, 255, 255, 255), width=18)

    im.save(ICONS_DIR / "drive.png", "PNG")
    print(f"Created {ICONS_DIR / 'drive.png'}")


def create_durability_icon():
    # Red rectangle with white jagged fracture line
    im = Image.new("RGBA", ICON_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    red = (185, 0, 0, 255)
    draw.rectangle((60, 20, 340, 380), fill=red)

    crack = [
        (60, 250),
        (130, 210),
        (170, 260),
        (220, 190),
        (270, 240),
        (340, 180),
    ]
    draw.line(crack, fill=(255, 255, 255, 255), width=28, joint="miter")

    im.save(ICONS_DIR / "durability.png", "PNG")
    print(f"Created {ICONS_DIR / 'durability.png'}")


def create_absorption_icon():
    # Black armor shield / plate (trapezoid with angled bottom)
    im = Image.new("RGBA", ICON_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    black = (15, 15, 15, 255)
    points = [
        (70, 40),
        (330, 40),
        (340, 260),
        (270, 370),
        (130, 370),
        (60, 260),
    ]
    draw.polygon(points, fill=black)

    im.save(ICONS_DIR / "absorption.png", "PNG")
    print(f"Created {ICONS_DIR / 'absorption.png'}")


def create_template_circle():
    # Red circle with black center dot
    im = Image.new("RGBA", ICON_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    red = (235, 10, 10, 255)
    lw = 40
    draw.ellipse((40, 40, 360, 360), outline=red, width=lw)
    draw.ellipse((160, 160, 240, 240), fill=(10, 10, 10, 255))

    im.save(ICONS_DIR / "template_circle.png", "PNG")
    print(f"Created {ICONS_DIR / 'template_circle.png'}")


def create_template_line():
    # Single line template
    im = Image.new("RGBA", ICON_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    red = (235, 10, 10, 255)
    lw = 45
    draw.line([(200, 40), (200, 360)], fill=red, width=lw)

    im.save(ICONS_DIR / "template_line.png", "PNG")
    print(f"Created {ICONS_DIR / 'template_line.png'}")


def create_template_bar():
    # Wide block with horizontal red line at the front
    im = Image.new("RGBA", ICON_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    black = (10, 10, 10, 255)
    red = (235, 10, 10, 255)
    draw.rectangle((40, 140, 360, 320), fill=black)
    draw.rectangle((40, 80, 360, 130), fill=red)

    im.save(ICONS_DIR / "template_bar.png", "PNG")
    print(f"Created {ICONS_DIR / 'template_bar.png'}")


def create_template_prongs():
    # Wide black bar with two red lines going forwards from the bar
    im = Image.new("RGBA", ICON_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    black = (10, 10, 10, 255)
    red = (235, 10, 10, 255)

    draw.rectangle((50, 60, 140, 340), fill=black)
    draw.rectangle((120, 60, 350, 130), fill=red)
    draw.rectangle((120, 270, 350, 340), fill=red)

    im.save(ICONS_DIR / "template_prongs.png", "PNG")
    print(f"Created {ICONS_DIR / 'template_prongs.png'}")


def main():
    print(f"Generating temporary icons in {ICONS_DIR}...")
    create_weight_icon()
    create_energy_icon()
    create_control_icon()
    create_spin_icon()
    create_damage_icon()
    create_drive_icon()
    create_durability_icon()
    create_absorption_icon()
    create_template_circle()
    create_template_line()
    create_template_bar()
    create_template_prongs()
    print("Done generating all icons.")


if __name__ == "__main__":
    main()
