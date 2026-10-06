#!/usr/bin/env python3
"""
gather_set1_images.py

Gathers copies of all component, weapon, and chassis images used in Set 1
into `set1_component_images/` with categorized subfolders (`components/`,
`weapons/`, `chassis/`) and a flat aggregated folder (`all/`).

Also generates:
- `set1_component_images/image_sources.txt`: Detailed text reference with store links,
  direct image URLs, card names, and manufacturer groupings for seeking permissions.
- `set1_component_images/image_sources.md`: Formatted Markdown table with clickable links.
"""

import csv
import html
import json
import os
import shutil
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
CATALOG_PATH = WORKSPACE / "components" / "catalog.json"
CARD_DEFS_DIR = WORKSPACE / "cardDefinitions"
OUTPUT_DIR = WORKSPACE / "set1_component_images"

CATEGORY_SOURCES = [
    ("components", "Component Cards", CARD_DEFS_DIR / "components.csv"),
    ("weapons", "Weapon Cards", CARD_DEFS_DIR / "weapons.csv"),
    ("chassis", "Chassis Mats", CARD_DEFS_DIR / "chassis.csv"),
]


def detect_brand(name: str, tags: list[str], prod_url: str) -> str:
    combined = (name + " " + " ".join(tags) + " " + prod_url).lower()
    if "fingertech" in combined or "viper" in combined or "nightwing" in combined:
        return "FingerTech Robotics"
    elif "just cuz" in combined or "ssp" in combined or "chonk" in combined:
        return "Just Cuz Robotics"
    elif "repeat robotics" in combined or "scalar" in combined:
        return "Repeat Robotics"
    elif any(
        k in combined
        for k in ("turnabot", "startabot", "overthrow", "squeezy", "slammer")
    ):
        return "Turnabot"
    elif "nautiloid" in combined or "rad robotics" in combined:
        return "RAD Robotics"
    elif "banebots" in combined:
        return "BaneBots"
    elif "saifu" in combined:
        return "Kitbots"
    elif "bloodsport" in combined:
        return "Team Bloodsport"
    elif "black frost" in combined:
        return "Team Bad Idea (Black Frost)"
    elif "gens ace" in combined or "tattu" in combined:
        return "Gens Ace / Tattu"
    elif "pololu" in combined or "zumo" in combined:
        return "Pololu"
    elif "flycolor" in combined:
        return "Flycolor"
    elif "scorpion" in combined:
        return "Robot Power (Scorpion)"
    elif "malenki" in combined:
        return "Malenki (Martin)"
    elif "cronos" in combined:
        return "Team Cronos"
    else:
        return "ITGresa / General"


def load_catalog():
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    by_path = {item["image_path"]: item for item in catalog if "image_path" in item}
    by_filename = {
        item["image_filename"]: item for item in catalog if "image_filename" in item
    }
    return by_path, by_filename


def main():
    by_path, by_filename = load_catalog()

    # Create directories
    components_dir = OUTPUT_DIR / "components"
    weapons_dir = OUTPUT_DIR / "weapons"
    chassis_dir = OUTPUT_DIR / "chassis"
    all_dir = OUTPUT_DIR / "all"

    for d in (components_dir, weapons_dir, chassis_dir, all_dir):
        d.mkdir(parents=True, exist_ok=True)

    gathered_data = {}
    total_images = 0

    for cat_key, cat_title, csv_path in CATEGORY_SOURCES:
        if not csv_path.exists():
            continue

        cat_items = []
        target_subfolder = OUTPUT_DIR / cat_key

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))

        for idx, row in enumerate(reader, 1):
            card_name = row["Name"].strip()
            pic_rel = row["Picture"].strip()
            source_file = WORKSPACE / pic_rel

            if not source_file.is_file():
                raise FileNotFoundError(f"Missing source file: {source_file}")

            # Lookup catalog info
            item = by_path.get(pic_rel) or by_filename.get(source_file.name)
            if not item:
                raise ValueError(f"Catalog item not found for {pic_rel}")

            prod_name = html.unescape(item.get("name", card_name))
            prod_url = item.get("product_url", "")
            img_url = item.get("source_image_url", "")
            tags = item.get("tags", [])
            brand = detect_brand(prod_name, tags, prod_url)
            price = item.get("price", "")

            # Copy to category subfolder
            target_file = target_subfolder / source_file.name
            shutil.copy2(source_file, target_file)

            # Copy to flat 'all' folder
            target_all = all_dir / source_file.name
            shutil.copy2(source_file, target_all)

            cat_items.append(
                {
                    "index": idx,
                    "card_name": card_name,
                    "file_name": source_file.name,
                    "rel_path": f"{cat_key}/{source_file.name}",
                    "source_path": pic_rel,
                    "product_name": prod_name,
                    "brand": brand,
                    "price": price,
                    "product_url": prod_url,
                    "image_url": img_url,
                    "tags": tags,
                }
            )
            total_images += 1

        gathered_data[cat_key] = {"title": cat_title, "items": cat_items}

    # Generate image_sources.txt
    txt_lines = []
    txt_lines.append("=" * 80)
    txt_lines.append("SET 1 COMPONENT & CARD IMAGES - SOURCE LINKS & PERMISSION REFERENCE")
    txt_lines.append("=" * 80)
    txt_lines.append("")
    txt_lines.append(f"Total Unique Images Gathered: {total_images}")
    for cat_key, cat_title, _ in CATEGORY_SOURCES:
        count = len(gathered_data[cat_key]["items"])
        txt_lines.append(f"  - {cat_title:<18}: {count} images")
    txt_lines.append("")
    txt_lines.append("PRIMARY SOURCE STORE:")
    txt_lines.append("All images were originally cataloged from ITGresa Robotics (https://itgresa.com/),")
    txt_lines.append("the primary online distributor for US/North American combat robotics builders.")
    txt_lines.append("Specific components are designed and manufactured by individual robot builders")
    txt_lines.append("and combat robotics teams (e.g., FingerTech Robotics, Just Cuz Robotics, Repeat")
    txt_lines.append("Robotics, Turnabot, RAD Robotics, Kitbots, BaneBots, etc.).")
    txt_lines.append("")
    txt_lines.append("FOLDER ORGANIZATION:")
    txt_lines.append("  - components/ : 36 images for component cards (cardDefinitions/components.csv)")
    txt_lines.append("  - weapons/    : 14 images for weapon cards (cardDefinitions/weapons.csv)")
    txt_lines.append("  - chassis/    :  5 images for chassis mats (cardDefinitions/chassis.csv)")
    txt_lines.append("  - all/        : All 55 images gathered into a single flat directory")
    txt_lines.append("")
    txt_lines.append("=" * 80)

    for cat_key, cat_title, _ in CATEGORY_SOURCES:
        items = gathered_data[cat_key]["items"]
        txt_lines.append("")
        txt_lines.append("-" * 80)
        txt_lines.append(f"{cat_title.upper()} ({len(items)} items)")
        txt_lines.append("-" * 80)
        txt_lines.append("")

        for it in items:
            txt_lines.append(f"[{it['index']}] Card Name:       {it['card_name']}")
            txt_lines.append(f"    Image Filename:  {it['file_name']}")
            txt_lines.append(f"    Folder Location: {it['rel_path']}")
            txt_lines.append(f"    Store Product:   {it['product_name']}")
            txt_lines.append(f"    Manufacturer:    {it['brand']}")
            if it["price"]:
                txt_lines.append(f"    Store Price:     {it['price']}")
            txt_lines.append(f"    Product Page:    {it['product_url']}")
            txt_lines.append(f"    Original Image:  {it['image_url']}")
            txt_lines.append("")

    # Group by Brand / Manufacturer
    txt_lines.append("=" * 80)
    txt_lines.append("BREAKDOWN BY MANUFACTURER / BRAND (FOR SEEKING PERMISSION)")
    txt_lines.append("=" * 80)
    txt_lines.append("")

    brand_groups = {}
    for cat_key, _, _ in CATEGORY_SOURCES:
        for it in gathered_data[cat_key]["items"]:
            b = it["brand"]
            brand_groups.setdefault(b, []).append((cat_key, it))

    for b in sorted(brand_groups.keys()):
        b_items = brand_groups[b]
        txt_lines.append(f"=== {b} ({len(b_items)} item{'s' if len(b_items) != 1 else ''}) ===")
        for cat_key, it in b_items:
            txt_lines.append(
                f"  - [{it['card_name']}] ({it['product_name']})"
            )
            txt_lines.append(f"      Product: {it['product_url']}")
            txt_lines.append(f"      Image:   {it['image_url']}")
        txt_lines.append("")

    txt_lines.append("=" * 80)
    txt_lines.append("PLAIN LIST OF ALL PRODUCT & IMAGE URLS")
    txt_lines.append("=" * 80)
    txt_lines.append("")
    for cat_key, _, _ in CATEGORY_SOURCES:
        for it in gathered_data[cat_key]["items"]:
            txt_lines.append(f"{it['card_name']}:")
            txt_lines.append(f"  Page:  {it['product_url']}")
            txt_lines.append(f"  Image: {it['image_url']}")
    txt_lines.append("")

    txt_file = OUTPUT_DIR / "image_sources.txt"
    with open(txt_file, "w", encoding="utf-8") as f:
        f.write("\n".join(txt_lines))

    # Also generate image_sources.md (Markdown format)
    md_lines = []
    md_lines.append("# Set 1 Component & Card Images — Source Links & Permissions")
    md_lines.append("")
    md_lines.append(
        "This directory contains copies of all images used for Set 1 of the combat robotics card game, "
        "along with complete origin URLs to assist in seeking permission from photographers and manufacturers."
    )
    md_lines.append("")
    md_lines.append("## Summary")
    md_lines.append("")
    md_lines.append(f"- **Total Images:** {total_images}")
    for cat_key, cat_title, _ in CATEGORY_SOURCES:
        count = len(gathered_data[cat_key]["items"])
        md_lines.append(f"- **{cat_title}:** {count} (`{cat_key}/`)")
    md_lines.append(f"- **All Combined:** {total_images} (`all/`)")
    md_lines.append("- **Primary Retailer:** [ITGresa Robotics](https://itgresa.com/)")
    md_lines.append("")

    for cat_key, cat_title, _ in CATEGORY_SOURCES:
        items = gathered_data[cat_key]["items"]
        md_lines.append(f"## {cat_title} ({len(items)})")
        md_lines.append("")
        md_lines.append(
            "| # | Card Name | Image File | Manufacturer / Brand | Store Product Page | Direct Image Link |"
        )
        md_lines.append(
            "|---|---|---|---|---|---|"
        )
        for it in items:
            esc_name = it["card_name"].replace("|", "\\|")
            esc_pname = it["product_name"].replace("|", "\\|")
            p_link = f"[{esc_pname}]({it['product_url']})" if it["product_url"] else "N/A"
            i_link = f"[Image Link]({it['image_url']})" if it["image_url"] else "N/A"
            md_lines.append(
                f"| {it['index']} | **{esc_name}** | `{it['file_name']}` | {it['brand']} | {p_link} | {i_link} |"
            )
        md_lines.append("")

    md_lines.append("## Outreach Grouping by Manufacturer / Creator")
    md_lines.append("")
    for b in sorted(brand_groups.keys()):
        b_items = brand_groups[b]
        md_lines.append(f"### {b} ({len(b_items)} items)")
        md_lines.append("")
        for cat_key, it in b_items:
            md_lines.append(
                f"- **{it['card_name']}** ([Product Page]({it['product_url']}) | [Image]({it['image_url']})) — *{it['product_name']}*"
            )
        md_lines.append("")

    md_file = OUTPUT_DIR / "image_sources.md"
    with open(md_file, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"Successfully gathered {total_images} images into {OUTPUT_DIR}")
    print(f"Generated text reference: {txt_file}")
    print(f"Generated markdown reference: {md_file}")


if __name__ == "__main__":
    main()
