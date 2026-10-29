#!/usr/bin/env python3
"""
generate_card_json.py

Writes json/cards.json: Tabletop Simulator metadata for all cards, tiles
(chassis and weapon templates), and tokens (movement templates) in one file.

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
          "back":        "<raw.githubusercontent URL of card back in pictures/backs>",
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
          "thickness":   "0.1",
          "stackable":   "true"
        }, ...
      },
      "Token": {
        "1": {
          "name":           "<Name>",
          "description":    "<description of movement template>",
          "gm_notes":       "<pairs and geometry>",
          "tags":           {"1": "Token", "2": "Template", "3": "Movement", "4": "Straight"},
          "lua_script":     "",
          "face":           "<raw.githubusercontent URL of token image in movement_templates>",
          "back":           "<raw.githubusercontent URL of token image in movement_templates>",
          "thickness":      "0.2",
          "merge_distance": "15.0",
          "stackable":      "false"
        }, ...
      },
      "Figurine": {}
    }

Sources:
    cardDefinitions/components.csv -> Card, Component
    cardDefinitions/weapons.csv    -> Card, Weapon, <Template>
    Chassis & Weapon templates     -> Tile (Template markers)
    movement_templates/*.png       -> Token (Movement templates)

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

from generate_movement_templates import build_all_movement_templates

WORKSPACE = Path(__file__).resolve().parent
CARD_DEFS_DIR = WORKSPACE / "cardDefinitions"
CARD_IMAGES_DIR = WORKSPACE / "CardImages"
TTS_ASSETS_DIR = WORKSPACE / "tts_assets"
PICTURES_DIR = WORKSPACE / "pictures"
ICONS_DIR = PICTURES_DIR / "icons"
COMPONENTS_DIR = WORKSPACE / "components"
MOVEMENT_TEMPLATES_DIR = WORKSPACE / "movement_templates"

GITHUB_REPO_RAW = (
    "https://raw.githubusercontent.com/thesilencelies/RobotBattles/"
    "refs/heads/main/"
)
CARD_IMAGES_URL = GITHUB_REPO_RAW + "CardImages/"
TTS_ASSETS_URL = GITHUB_REPO_RAW + "tts_assets/"
PICTURES_URL = GITHUB_REPO_RAW + "pictures/"
ICONS_URL = GITHUB_REPO_RAW + "pictures/icons/"
COMPONENTS_URL = GITHUB_REPO_RAW + "components/"
MOVEMENT_TEMPLATES_URL = GITHUB_REPO_RAW + "movement_templates/"

CARD_BACK_URL = PICTURES_URL + "backs/CardBack.png"

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
    "Reset": (
        ("reset",),
        "Reset: this weapon is inactive the turn after it is used. (this does not cause the robot to be considered stuck if it is also a self righter)",
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

    return cards


def enumerate_tiles() -> list[dict]:
    tiles = []

    # 1. Chassis Template Boundary Tiles (Square, Triangle, Wide)
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
            "thickness": "0.2",
            "stackable": "true",
            "_local_images": (icon_path,),
        })

    # 2. Weapon Template Tiles (Circle, Large Circle, Line, Bar, Prongs)
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
            "thickness": "0.1",
            "stackable": "true",
            "_local_images": (icon_path,),
        })

    return tiles


def enumerate_tokens() -> list[dict]:
    tokens = []
    templates = build_all_movement_templates()

    for t in templates:
        image_name = f"{t.template_id}.png"
        image_path = MOVEMENT_TEMPLATES_DIR / image_name
        image_url = MOVEMENT_TEMPLATES_URL + quote(image_name)

        pairs_str = ", ".join(f"({l}, {r})" for l, r in t.pairs)
        if t.category == "straight":
            desc = f"Straight movement template for drive pairs: {pairs_str}"
        elif t.category == "spin":
            desc = f"Spin disc movement template (360-degree rotation) for drive pairs: {pairs_str}"
        elif t.category == "pivot":
            desc = f"Pivot fan movement template (180-degree semicircle) for drive pairs: {pairs_str}"
        else:
            desc = f"{t.name} for forward curved maneuvers: {pairs_str}"

        gm_lines = [
            f"template:{t.name.replace(' Template', '')}",
            f"category:{t.category}",
            f"pairs:{pairs_str}",
        ]
        if t.category == "curve_forward":
            gm_lines.append(f"radius:{t.nominal_rc:g}mm")

        tag_name = t.name.replace(" Template", "")
        token_name = f"{tag_name} Movement Template"

        tokens.append({
            "name": token_name,
            "description": desc,
            "gm_notes": "\n".join(gm_lines),
            "tags": build_tags("Token", "Template", "Movement", tag_name),
            "lua_script": "",
            "face": image_url,
            "back": image_url,
            "thickness": "0.2",
            "merge_distance": "15.0",
            "stackable": "false",
            "_local_images": (image_path,),
        })

    return tokens


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
    tokens = enumerate_tokens()

    doc = {
        "Card": to_indexed_dict(cards),
        "Tile": to_indexed_dict(tiles),
        "Token": to_indexed_dict(tokens),
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
        print(f"\nTokens ({len(tokens)}):")
        for tok in tokens:
            print(f"  {tok['name']}  <- {tok['face']}")

    print(
        f"\nWrote {len(cards)} card(s), {len(tiles)} tile(s), "
        f"and {len(tokens)} token(s) to {output_path.relative_to(WORKSPACE)}"
    )

    # Check local image existence
    card_back_file = PICTURES_DIR / "backs" / "CardBack.png"
    if not card_back_file.is_file():
        print(f"\nWarning: Card back image not found: {card_back_file}")

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

    missing_tokens = [
        tok["name"]
        for tok in tokens
        if any(not p.is_file() for p in tok.get("_local_images", ()))
    ]
    if missing_tokens:
        print(f"\nWarning: {len(missing_tokens)} token image(s) not found locally:")
        for name in missing_tokens:
            print(f"  {name}")


if __name__ == "__main__":
    main()
