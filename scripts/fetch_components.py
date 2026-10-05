#!/usr/bin/env python3
"""
Scrape combat robotics components from ITGresa.com via WooCommerce Store REST API.
Downloads primary images into categorized folders and generates catalog.json and README.md.
"""

import os
import re
import json
import urllib.request
import urllib.parse
from html import unescape
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "https://itgresa.com/wp-json/wc/store/v1/products"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPONENTS_DIR = os.path.join(BASE_DIR, "components")

CATEGORIES = {
    "kits_and_chassis": {
        "dir": "kits_and_chassis",
        "title": "Kits & Chassis",
        "card_type": "Robot Kit / Chassis",
        "desc": "Complete combat robot kits, frames, and chassis across Fairyweight (150g), Antweight (1lb), and Beetleweight (3lb) classes."
    },
    "motors": {
        "dir": "motors",
        "title": "Motors & Gearboxes",
        "card_type": "Drive / Weapon Motor",
        "desc": "Planetary/spur micro gearmotors (N10/N20/N30), Repeat Robotics brushless drive motors, and Just Cuz hubmotors."
    },
    "weapons": {
        "dir": "weapons",
        "title": "Weapon Systems",
        "card_type": "Kinetic Weapon",
        "desc": "High-RPM spinning bars, beater bars, eggbeaters, drum rotors, discs, and hardened impact teeth."
    },
    "electronics_and_escs": {
        "dir": "electronics_and_escs",
        "title": "Electronics & ESCs",
        "card_type": "Electronics & Speed Control",
        "desc": "Dual and single Electronic Speed Controllers (ESCs), BECs, power switches, and receiver modules."
    },
    "batteries_and_power": {
        "dir": "batteries_and_power",
        "title": "Batteries & Power",
        "card_type": "Power Source",
        "desc": "High-C discharge LiPo battery packs (2S, 3S, 4S) and field balance chargers."
    },
    "wheels_and_drive": {
        "dir": "wheels_and_drive",
        "title": "Wheels & Hubs",
        "card_type": "Traction & Drive",
        "desc": "High-grip foam wheels, sticky silicone tires, precision snap hubs, pulleys, and timing belts."
    },
    "mechanicals_and_armor": {
        "dir": "mechanicals_and_armor",
        "title": "Mechanicals & Armor",
        "card_type": "Armor & Structural",
        "desc": "Titanium impact plates, UHMW shock armor, aluminum standoffs, nutstrips, and hardware packs."
    },
    "connectors_and_wiring": {
        "dir": "connectors_and_wiring",
        "title": "Connectors & Wiring",
        "card_type": "Wiring & Hardware",
        "desc": "High-current connectors (XT30, XT60, MR30), JST connectors, silicone wire leads, and wiring harnesses."
    },
    "controllers_and_radio": {
        "dir": "controllers_and_radio",
        "title": "Transmitters & Radio",
        "card_type": "Radio Control",
        "desc": "Multi-channel 2.4GHz transmitters, micro receivers, and control links."
    },
    "servos_and_actuators": {
        "dir": "servos_and_actuators",
        "title": "Servos & Actuators",
        "card_type": "Actuator / Lifter",
        "desc": "High-torque digital and metal-gear servos for lifter arms, clampers, and flippers."
    },
    "tools_and_pit": {
        "dir": "tools_and_pit",
        "title": "Tools & Pit Equipment",
        "card_type": "Pit Crew / Field Repair",
        "desc": "Soldering stations, brass tip cleaners, precision hex drivers, and emergency repair bench gear."
    },
}

def clean_html(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return " ".join(text.split()).strip()

def classify_product(p):
    cat_slugs = [c.get("slug", "").lower() for c in p.get("categories", [])]
    cat_names = [c.get("name", "").lower() for c in p.get("categories", [])]
    name = p["name"].lower()
    all_text = " ".join(cat_slugs + cat_names + [name])

    # 1. Non-components to exclude
    if any(k in all_text for k in ["swag", "gift card", "classes", "shirt", "hoodie", "hat", "sticker"]):
        return None

    # 2. Tools & Pit
    if any(k in cat_slugs for k in ["soldering-tools", "bundles"]) or any(k in name for k in ["soldering", "flux", "soldering station", "tip cleaner", "desoldering", "cutter", "hex driver", "wrench", "third hand"]):
        return "tools_and_pit"

    # 3. Hardware / Screws / Nutstrips (even if name has "kit", e.g. "screw kit")
    if any(k in name for k in ["screw kit", "screw pack", "nutstrip", "threaded inserts", "washers", "locknut", "hardware kit", "standoff", "armor", "horns"]):
        return "mechanicals_and_armor"

    # 4. Electronics kits / switches
    if any(k in name for k in ["electronics kit", "power switch", "usb linker", "switch metric", "switch torx"]):
        return "electronics_and_escs"

    # 5. Full Kits & Chassis (Complete bot kits)
    if any(k in name for k in ["combat robot kit", "robot kit", "base kit", "chassis kit"]) or any(k in cat_slugs for k in ["combat-robot-kits", "fairyweight", "baby-nautiloid", "base-synthwave", "base-viper", "kerfuffle", "naked-ant", "nightwing", "outrun", "pro-synthwave", "saifu", "scalar", "ssp-kits", "weaponized_viper", "camp-witch-doctor-robot-kits"]):
        # Check if it's actually an individual component named inside a kit category
        if any(k in name for k in ["motor", "gearmotor"]) and not any(k in name for k in ["kit", "bundle"]):
            return "motors"
        if any(k in name for k in ["disc", "blade", "beater", "tooth", "teeth"]) and not any(k in name for k in ["kit", "bundle"]):
            return "weapons"
        if any(k in name for k in ["tire", "wheel", "hub"]) and not any(k in name for k in ["kit", "bundle"]):
            return "wheels_and_drive"
        return "kits_and_chassis"

    # 6. Controllers & Radio (Transmitters, standalone receivers)
    if any(k in cat_slugs for k in ["controllers"]) or any(k in name for k in ["transmitter", "fs-i6", "radio controller", "remote control", "fs-bs6", "fs-ia6b", "fs2a"]):
        return "controllers_and_radio"

    # 7. Servos & Actuators
    if any(k in cat_slugs for k in ["servo"]) or "servo" in name:
        if not any(k in name for k in ["wire", "extension lead", "cable", "retainer"]):
            return "servos_and_actuators"

    # 8. Weapons & Kinetic Systems
    if any(k in cat_slugs for k in ["weapons-systems", "hubmotor-weapons", "jc_hubmotor_weapon", "rr_hubmotor-weapon"]) or any(k in name for k in ["beater bar", "spinner blade", "weapon bar", "weapon tooth", "weapon teeth", "weapon disc", "drum weapon", "combat blade", "saw blade", "eggbeater", "rotor", "undercutter"]):
        return "weapons"

    # 9. Batteries & Power
    if any(k in cat_slugs for k in ["batteries-and-chargers", "batteries-chargers", "2s-batteries", "3s-batteries", "4s-batteries", "chargers", "dc-charger"]) or any(k in name for k in ["lipo", "battery", "charger", "power supply", "balance charger"]):
        return "batteries_and_power"

    # 10. Electronics & ESCs
    if any(k in cat_slugs for k in ["electronics", "esc", "esc-2", "esc_programmer-2", "jc_hubmotor_esc", "rr_hubmotor_esc", "arduino"]) or any(k in name for k in ["esc", "speed controller", "switch", "bec", "receiver", "arduino", "teensy", "malenki"]):
        return "electronics_and_escs"

    # 11. Wheels & Drive
    if any(k in cat_slugs for k in ["wheels-and-hubs"]) or any(k in name for k in ["wheel", "tire", "snap hub", "foam tire", "rubber tire"]):
        return "wheels_and_drive"

    # 12. Motors
    if any(k in cat_slugs for k in ["motors", "hubmotors", "beetle_hubmotor", "hubmotor-just-cuz", "n-series-micro-gearmotors", "n10-micro-gear-motor", "n20-micro-gear-motor", "n30-micro-gear-motor", "repeat", "just-cuz"]) or any(k in name for k in ["motor", "gearmotor", "hubmotor", "brushless", "brushed motor"]):
        return "motors"

    # 13. Connectors & Wiring
    if any(k in cat_slugs for k in ["connectors"]) or any(k in name for k in ["xt30", "xt60", "mr30", "jst", "wire", "cable", "harness", "lead", "connector"]):
        return "connectors_and_wiring"

    # 14. Mechanicals & Armor
    return "mechanicals_and_armor"

def fetch_all_products():
    products = []
    page = 1
    while True:
        url = f"{BASE_URL}?per_page=100&page={page}"
        print(f"Fetching page {page} from {url}...")
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if not data:
                    break
                products.extend(data)
                total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
                if page >= total_pages:
                    break
                page += 1
        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            break
    return products

def download_image(url, dest_path):
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 100:
        return True
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=25) as resp:
            content = resp.read()
            with open(dest_path, "wb") as f:
                f.write(content)
        return True
    except Exception as e:
        print(f"Failed to download {url}: {e}")
        return False

def main():
    os.makedirs(COMPONENTS_DIR, exist_ok=True)
    for cat_key, cat_info in CATEGORIES.items():
        os.makedirs(os.path.join(COMPONENTS_DIR, cat_info["dir"]), exist_ok=True)

    print("Step 1: Fetching all products from ITGresa...")
    products = fetch_all_products()
    print(f"Retrieved {len(products)} total catalog products.")

    catalog_entries = []
    download_tasks = []

    print("Step 2: Classifying products and preparing download queue...")
    for p in products:
        category_key = classify_product(p)
        if not category_key:
            # Exclude non-components
            continue

        images = p.get("images", [])
        if not images:
            continue

        primary_img = images[0]
        img_url = primary_img.get("src")
        if not img_url:
            continue

        slug = p.get("slug") or f"product-{p['id']}"
        ext = os.path.splitext(urllib.parse.urlparse(img_url).path)[1] or ".jpg"
        if "?" in ext:
            ext = ext.split("?")[0]
        if ext.lower() not in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
            ext = ".jpg"

        cat_info = CATEGORIES[category_key]
        filename = f"{slug}{ext}"
        dest_path = os.path.join(COMPONENTS_DIR, cat_info["dir"], filename)
        rel_img_path = os.path.join("components", cat_info["dir"], filename)

        # Price extraction
        price_str = ""
        prices = p.get("prices", {})
        if "price" in prices:
            raw_p = prices.get("price")
            prefix = prices.get("currency_prefix", "$")
            try:
                price_str = f"{prefix}{float(raw_p) / 100:.2f}"
            except Exception:
                price_str = f"{prefix}{raw_p}"

        desc = clean_html(p.get("short_description")) or clean_html(p.get("description"))
        if len(desc) > 280:
            desc = desc[:277] + "..."

        entry = {
            "id": p["id"],
            "name": p["name"],
            "slug": slug,
            "category_key": category_key,
            "category_title": cat_info["title"],
            "card_archetype": cat_info["card_type"],
            "price": price_str,
            "image_path": rel_img_path,
            "image_filename": filename,
            "source_image_url": img_url,
            "product_url": p.get("permalink"),
            "description": desc,
            "tags": [t.get("name") for t in p.get("tags", [])],
        }
        catalog_entries.append(entry)
        download_tasks.append((img_url, dest_path, p["name"]))

    print(f"Step 3: Downloading primary images for {len(download_tasks)} components...")
    successful = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {executor.submit(download_image, url, path): (name, url) for url, path, name in download_tasks}
        for future in as_completed(futures):
            name, url = futures[future]
            try:
                res = future.result()
                if res:
                    successful += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"Exception downloading {name}: {e}")
                failed += 1

            total_done = successful + failed
            if total_done % 50 == 0 or total_done == len(download_tasks):
                print(f"Progress: {total_done}/{len(download_tasks)} (Success: {successful}, Failed: {failed})")

    # Step 4: Save catalog.json
    catalog_json_path = os.path.join(COMPONENTS_DIR, "catalog.json")
    with open(catalog_json_path, "w", encoding="utf-8") as f:
        json.dump(catalog_entries, f, indent=2)
    print(f"Saved catalog JSON to {catalog_json_path}")

    # Step 5: Save catalog README.md
    catalog_md_path = os.path.join(COMPONENTS_DIR, "README.md")
    with open(catalog_md_path, "w", encoding="utf-8") as f:
        f.write("# Combat Robotics Component Inspiration Catalog\n\n")
        f.write("Collated from [ITGresa Robotics](https://itgresa.com/) for card design inspiration for combat robotics board game design.\n\n")
        f.write(f"- **Total Components Cataloged:** {len(catalog_entries)}\n")
        f.write(f"- **Images Downloaded:** {successful}\n\n")
        f.write("## Category Breakdown & Card Game Archetypes\n\n")

        # Group entries by category
        by_cat = {}
        for entry in catalog_entries:
            by_cat.setdefault(entry["category_key"], []).append(entry)

        for cat_key, cat_info in CATEGORIES.items():
            items = by_cat.get(cat_key, [])
            f.write(f"### {cat_info['title']} ({len(items)} items)\n\n")
            f.write(f"**Card Archetype:** `{cat_info['card_type']}`  \n")
            f.write(f"**Description:** {cat_info['desc']}  \n\n")
            f.write("| Component Name | Price | Description | Local Image | Link |\n")
            f.write("| :--- | :--- | :--- | :---: | :---: |\n")
            for item in items:
                name = item['name'].replace('|', '/')
                desc_cell = item['description'].replace('|', '/')
                rel_p = f"{cat_info['dir']}/{item['image_filename']}"
                f.write(f"| **{name}** | {item['price']} | {desc_cell} | [`{item['image_filename']}`]({rel_p}) | [Store]({item['product_url']}) |\n")
            f.write("\n---\n\n")

    print(f"Saved README/Catalog to {catalog_md_path}")
    print("Done!")

if __name__ == "__main__":
    main()
