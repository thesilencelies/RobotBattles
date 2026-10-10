#!/usr/bin/env python3
"""
generate_card_json.py

Writes json/cards.json: Tabletop Simulator metadata for all cards, tiles
(chassis and weapon templates), and tokens in one file.

The schema matches the TTS custom-object import format:

    {
      "Card": {
        "1": {
          "name":        "<Name>",
          "description": "<one clarifying line per keyword printed on the card>",
          "gm_notes":    "<every stat, then the card text, newline separated>",
          "tags":        {"1": "Card", "2": "Component"},
          "lua_script":  "",
          "face":        "<raw.githubusercontent URL of front image in CardImages>",
          "back":        "<raw.githubusercontent URL of card back in tts_assets>",
          "type":        "0",
          "sideways":    "false"
        }, ...
      },
      "Tile": {
        "1": {
          "name":        "<Name>",
          "description": "<description of chassis or template>",
          "gm_notes":    "<stats and template details>",
          "tags":        {"1": "Tile", "2": "Chassis", "3": "Square"},
          "lua_script":  "",
          "face":        "<raw.githubusercontent URL of token/template image>",
          "back":        "<raw.githubusercontent URL of token/template image>",
          "type":        "0",
          "thickness":   "0.5",
          "stackable":   "true"
        }, ...
      },
      "Token": {},
      "Figurine": {}
    }

Sources:
    cardDefinitions/components.csv -> Card, Component
    cardDefinitions/weapons.csv    -> Card, Weapon, <Template>
    cardDefinitions/chassis.csv    -> Card, Chassis, <Template>
    Chassis & Weapon templates     -> Tile (Chassis & Template markers)

Usage:
    python generate_card_json.py
    python generate_card_json.py --output json/cards.json --quiet
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

WORKSPACE = Path(__file__).resolve().parent
CARD_DEFS_DIR = WORKSPACE / "cardDefinitions"
CARD_IMAGES_DIR = WORKSPACE / "CardImages"
TTS_ASSETS_DIR = WORKSPACE / "tts_assets"
PICTURES_DIR = WORKSPACE / "pictures"
ICONS_DIR = PICTURES_DIR / "icons"
COMPONENTS_DIR = WORKSPACE / "components"

GITHUB_REPO_RAW = (
    "https://raw.githubusercontent.com/thesilencelies/RobotBattles/"
    "refs/heads/main/"
)
CARD_IMAGES_URL = GITHUB_REPO_RAW + "CardImages/"
TTS_ASSETS_URL = GITHUB_REPO_RAW + "tts_assets/"
PICTURES_URL = GITHUB_REPO_RAW + "pictures/"
ICONS_URL = GITHUB_REPO_RAW + "pictures/icons/"
COMPONENTS_URL = GITHUB_REPO_RAW + "components/"

CARD_BACK_URL = TTS_ASSETS_URL + "card_back.png"
CHASSIS_BACK_URL = TTS_ASSETS_URL + "chassis_back.png"

# --------------------------------------------------------------------------
# Keyword glossary (the `description` field)
# --------------------------------------------------------------------------

GLOSSARY: dict[str, tuple[tuple[str, ...], str]] = {
    "Fragile": (
        ("fragile",),
        "Fragile: if this component takes weapon damage it is destroyed as if it had a durability of 1",
    ),
    "Spin up": (
        ("spin up",),
        "Spin up (X): at the start of each turn add X spin counters and remove them all if the weapon attacks",
    ),
    "Forks": (
        ("forks",),
        "Forks: if component with forks makes contact and the opponents forks do not make contact, the opponent becomes lifted",
    ),
    "Wedge": (
        ("wedge",),
        "Wedge: if this component is hit this robot is not thrown",
    ),
    "Invertible": (
        ("invertible",),
        "Invertible: this component works inverted",
    ),
    "Self-right": (
        ("self-right", "self right"),
        "Self-right: if a turn ends without contact and this robot is inverted, invert it",
    ),
}

# Weapon template metadata
WEAPON_TEMPLATE_INFO: dict[str, dict] = {
    "Circle": {
        "icon": "template_circle.png",
        "type": "2",  # Circle
        "description": "Circle weapon active area template: 360-degree radial contact",
        "active_area": "360-degree radial contact",
    },
    "Large Circle": {
        "icon": "template_large_circle.png",
        "type": "2",  # Circle
        "description": "Large circle weapon active area template: expanded 360-degree radial reach",
        "active_area": "expanded 360-degree radial reach",
    },
    "Line": {
        "icon": "template_line.png",
        "type": "0",  # Box
        "description": "Line weapon active area template: narrow frontal line contact",
        "active_area": "narrow frontal line contact",
    },
    "Bar": {
        "icon": "template_bar.png",
        "type": "0",  # Box
        "description": "Bar weapon active area template: wide frontal bar contact",
        "active_area": "wide frontal bar contact",
    },
    "Prongs": {
        "icon": "template_prongs.png",
        "type": "0",  # Box
        "description": "Prongs weapon active area template: dual forward prongs contact",
        "active_area": "dual forward prongs contact",
    },
}

# Chassis template metadata
CHASSIS_TEMPLATE_INFO: dict[str, dict] = {
    "Square": {
        "icon": "template_square.png",
        "description": "Square chassis boundary template (220mm x 256mm)",
        "bounds": "220x256mm",
    },
    "Triangle": {
        "icon": "template_triangle.png",
        "description": "Triangle wedge chassis boundary template (340mm x 256mm)",
        "bounds": "340x256mm",
    },
    "Wide": {
        "icon": "template_wide.png",
        "description": "Wide chassis boundary template (396mm x 170mm)",
        "bounds": "396x170mm",
    },
}


def build_tags(*names: str) -> dict[str, str]:
    """TTS numbers its tags from '1'; a card/tile is tagged broadest-first."""
    return {str(number): name for number, name in enumerate(names, start=1)}


def sanitize_filename(name: str) -> str:
    s = name.strip().replace(" ", "_")
    return re.sub(r"[^A-Za-z0-9_.-]", "", s)


def _cell(row: dict, column: str) -> str:
    return (row.get(column) or "").strip()


def _int(row: dict, column: str) -> int:
    raw = _cell(row, column).replace("+", "").replace("$", "")
    try:
        return int(raw)
    except ValueError:
        return 0


def read_rows(path: Path) -> list[dict]:
    if not path.is_file():
        sys.exit(f"Error: expected CSV not found: {path}")
    with open(path, newline="", encoding="utf-8") as fh:
        return [row for row in csv.DictReader(fh) if (row.get("Name") or "").strip()]


def description_for(row: dict) -> str:
    """One clarifying line per keyword printed on the card."""
    kw_text = (_cell(row, "Keywords") + " " + _cell(row, "Text")).lower()
    found: list[tuple[int, str]] = []
    for _kw_name, (markers, clarification) in GLOSSARY.items():
        positions = [kw_text.find(m) for m in markers if kw_text.find(m) >= 0]
        if positions:
            found.append((min(positions), clarification))
    found.sort(key=lambda x: x[0])
    return "\n".join(clarification for _, clarification in found)


def component_gm_notes(row: dict) -> str:
    lines = []
    weight = _int(row, "Weight")
    if weight > 0:
        lines.append(f"weight:{weight}")
    cost = _int(row, "Cost")
    if cost > 0:
        lines.append(f"cost:${cost}")
    req = _cell(row, "Requirements")
    if req:
        lines.append(f"req:{req}")
    out = _cell(row, "Outputs")
    if out:
        lines.append(f"out:{out}")
    dur = _cell(row, "Durability")
    if dur and dur != "0":
        lines.append(f"durability:{dur}")
    abs_val = _cell(row, "Absorption")
    if abs_val and abs_val != "0":
        lines.append(f"absorption:{abs_val}")
    text = _cell(row, "Text")
    if text:
        lines.append(text)
    return "\n".join(lines)


def weapon_gm_notes(row: dict) -> str:
    lines = []
    weight = _int(row, "Weight")
    if weight > 0:
        lines.append(f"weight:{weight}")
    cost = _int(row, "Cost")
    if cost > 0:
        lines.append(f"cost:${cost}")
    tpl = _cell(row, "Template")
    if tpl:
        lines.append(f"template:{tpl}")
    req = _cell(row, "Requirements")
    if req:
        lines.append(f"req:{req}")
    out = _cell(row, "Outputs")
    if out:
        lines.append(f"out:{out}")
    dur = _cell(row, "Durability")
    if dur and dur != "0":
        lines.append(f"durability:{dur}")
    abs_val = _cell(row, "Absorption")
    if abs_val and abs_val != "0":
        lines.append(f"absorption:{abs_val}")
    text = _cell(row, "Text")
    if text:
        lines.append(text)
    return "\n".join(lines)


def chassis_gm_notes(row: dict) -> str:
    lines = []
    weight = _int(row, "Weight")
    if weight > 0:
        lines.append(f"weight:{weight}")
    cost = _int(row, "Cost")
    if cost > 0:
        lines.append(f"cost:${cost}")
    flip = _cell(row, "Flip strength")
    if flip:
        lines.append(f"flip:{flip}")
    tpl = _cell(row, "Template")
    if tpl:
        lines.append(f"template:{tpl}")
    text = _cell(row, "Text")
    if text:
        lines.append(text)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Enumerations
# --------------------------------------------------------------------------

def enumerate_cards() -> list[dict]:
    cards = []

    # 1. Components
    for row in read_rows(CARD_DEFS_DIR / "components.csv"):
        name = _cell(row, "Name")
        gm = component_gm_notes(row)
        desc = description_for(row)
        image_name = f"{sanitize_filename(name)}.png"
        cards.append({
            "name": name,
            "description": desc,
            "gm_notes": gm,
            "tags": build_tags("Card", "Component"),
            "lua_script": "",
            "face": CARD_IMAGES_URL + quote(image_name),
            "back": CARD_BACK_URL,
            "type": "0",
            "sideways": "false",
            "_local_image": CARD_IMAGES_DIR / image_name,
        })

    # 2. Weapons
    for row in read_rows(CARD_DEFS_DIR / "weapons.csv"):
        name = _cell(row, "Name")
        gm = weapon_gm_notes(row)
        desc = description_for(row)
        tpl = _cell(row, "Template")
        image_name = f"{sanitize_filename(name)}.png"
        tags = build_tags("Card", "Weapon", tpl) if tpl else build_tags("Card", "Weapon")
        cards.append({
            "name": name,
            "description": desc,
            "gm_notes": gm,
            "tags": tags,
            "lua_script": "",
            "face": CARD_IMAGES_URL + quote(image_name),
            "back": CARD_BACK_URL,
            "type": "0",
            "sideways": "false",
            "_local_image": CARD_IMAGES_DIR / image_name,
        })

    # 3. Chassis
    for row in read_rows(CARD_DEFS_DIR / "chassis.csv"):
        name = _cell(row, "Name")
        gm = chassis_gm_notes(row)
        desc = description_for(row)
        tpl = _cell(row, "Template")
        image_name = f"{sanitize_filename(name)}.png"
        tags = build_tags("Card", "Chassis", tpl) if tpl else build_tags("Card", "Chassis")
        cards.append({
            "name": name,
            "description": desc,
            "gm_notes": gm,
            "tags": tags,
            "lua_script": "",
            "face": CARD_IMAGES_URL + quote(image_name),
            "back": CHASSIS_BACK_URL,
            "type": "0",
            "sideways": "false",
            "_local_image": CARD_IMAGES_DIR / image_name,
        })

    return cards


def enumerate_tiles() -> list[dict]:
    tiles = []

    # 1. Chassis Tiles (one for each robot chassis)
    chassis_rows = read_rows(CARD_DEFS_DIR / "chassis.csv")
    for row in chassis_rows:
        name = _cell(row, "Name")
        tpl = _cell(row, "Template")
        pic = _cell(row, "Picture")
        gm = chassis_gm_notes(row)
        desc = f"{tpl} template chassis (flip strength {_cell(row, 'Flip strength') or 'N/A'})"

        pic_path = WORKSPACE / pic
        tpl_icon_name = CHASSIS_TEMPLATE_INFO.get(tpl, {}).get("icon", "template_square.png")
        tpl_icon_path = ICONS_DIR / tpl_icon_name

        face_url = GITHUB_REPO_RAW + quote(pic)
        back_url = ICONS_URL + quote(tpl_icon_name)

        tiles.append({
            "name": name,
            "description": desc,
            "gm_notes": gm,
            "tags": build_tags("Tile", "Chassis", tpl),
            "lua_script": "",
            "face": face_url,
            "back": back_url,
            "type": "0",
            "thickness": "0.5",
            "stackable": "true",
            "_local_images": (pic_path, tpl_icon_path),
        })

    # 2. Chassis Template Boundary Tiles (Square, Triangle, Wide)
    for tpl_name, tpl_data in CHASSIS_TEMPLATE_INFO.items():
        icon_name = tpl_data["icon"]
        icon_path = ICONS_DIR / icon_name
        icon_url = ICONS_URL + quote(icon_name)
        tiles.append({
            "name": f"{tpl_name} Chassis Template",
            "description": tpl_data["description"],
            "gm_notes": f"template:{tpl_name}\nbounds:{tpl_data['bounds']}",
            "tags": build_tags("Tile", "Template", "Chassis", tpl_name),
            "lua_script": "",
            "face": icon_url,
            "back": icon_url,
            "type": "0",
            "thickness": "0.5",
            "stackable": "true",
            "_local_images": (icon_path,),
        })

    # 3. Weapon Template Tiles (Circle, Large Circle, Line, Bar, Prongs)
    weapon_rows = read_rows(CARD_DEFS_DIR / "weapons.csv")
    weapons_by_template: dict[str, list[str]] = {}
    for w in weapon_rows:
        tpl = _cell(w, "Template")
        if tpl:
            weapons_by_template.setdefault(tpl, []).append(_cell(w, "Name"))

    for tpl_name, tpl_data in WEAPON_TEMPLATE_INFO.items():
        icon_name = tpl_data["icon"]
        icon_path = ICONS_DIR / icon_name
        icon_url = ICONS_URL + quote(icon_name)
        w_list = ", ".join(weapons_by_template.get(tpl_name, []))
        gm_notes = f"template:{tpl_name}\nactive_area:{tpl_data['active_area']}"
        if w_list:
            gm_notes += f"\nweapons:{w_list}"

        tiles.append({
            "name": f"{tpl_name} Weapon Template",
            "description": tpl_data["description"],
            "gm_notes": gm_notes,
            "tags": build_tags("Tile", "Template", "Weapon", tpl_name),
            "lua_script": "",
            "face": icon_url,
            "back": icon_url,
            "type": tpl_data["type"],
            "thickness": "0.5",
            "stackable": "true",
            "_local_images": (icon_path,),
        })

    # 4. Individual Weapon Marker Tiles (front = component photo, back = template icon)
    for w in weapon_rows:
        name = _cell(w, "Name")
        tpl = _cell(w, "Template")
        pic = _cell(w, "Picture")
        pic_path = WORKSPACE / pic
        tpl_info = WEAPON_TEMPLATE_INFO.get(tpl, WEAPON_TEMPLATE_INFO["Line"])
        icon_name = tpl_info["icon"]
        icon_path = ICONS_DIR / icon_name

        face_url = GITHUB_REPO_RAW + quote(pic)
        back_url = ICONS_URL + quote(icon_name)

        tiles.append({
            "name": f"{name} ({tpl})",
            "description": f"{tpl} active area weapon marker",
            "gm_notes": weapon_gm_notes(w),
            "tags": build_tags("Tile", "Weapon", tpl),
            "lua_script": "",
            "face": face_url,
            "back": back_url,
            "type": tpl_info["type"],
            "thickness": "0.5",
            "stackable": "true",
            "_local_images": (pic_path, icon_path),
        })

    return tiles


def to_indexed_dict(entries: list[dict]) -> dict[str, dict]:
    """Convert a list of items to a stringified 1-based indexed dict (1, 2, 3...).
    Strips internal helper keys (like `_local_image`)."""
    out: dict[str, dict] = {}
    for idx, entry in enumerate(entries, start=1):
        clean = {k: v for k, v in entry.items() if not k.startswith("_")}
        out[str(idx)] = clean
    return out


def main():
    parser = argparse.ArgumentParser(
        description="Write Tabletop Simulator metadata to json/cards.json."
    )
    parser.add_argument(
        "--output",
        default="json/cards.json",
        help="File to write (default: json/cards.json).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print the summary and any warnings.",
    )
    args = parser.parse_args()

    output_path = WORKSPACE / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cards = enumerate_cards()
    tiles = enumerate_tiles()

    doc = {
        "Card": to_indexed_dict(cards),
        "Tile": to_indexed_dict(tiles),
        "Token": {},
        "Figurine": {},
    }

    json_text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    output_path.write_text(json_text, encoding="utf-8")

    if not args.quiet:
        print(f"Cards ({len(cards)}):")
        for c in cards:
            print(f"  {c['name']}  <- {c['face']}")
        print(f"\nTiles ({len(tiles)}):")
        for t in tiles:
            print(f"  {t['name']}  <- {t['face']}")

    print(
        f"\nWrote {len(cards)} card(s) and {len(tiles)} tile(s) "
        f"to {output_path.relative_to(WORKSPACE)}"
    )

    # Check local image existence
    missing_cards = [
        c["name"]
        for c in cards
        if not c.get("_local_image") or not c["_local_image"].is_file()
    ]
    if missing_cards:
        print(f"\nWarning: {len(missing_cards)} card image(s) not found in {CARD_IMAGES_DIR.name}/:")
        for name in missing_cards:
            print(f"  {name}")

    missing_tiles = [
        t["name"]
        for t in tiles
        if any(not p.is_file() for p in t.get("_local_images", ()))
    ]
    if missing_tiles:
        print(f"\nWarning: {len(missing_tiles)} tile image(s) not found locally:")
        for name in missing_tiles:
            print(f"  {name}")


if __name__ == "__main__":
    main()
