#!/usr/bin/env python3
"""
scripts/automata_weight_breakdown.py

Weight breakdown tool for Combat Robotics Game automata.
Calculates the weight allocation for each robot across four core categories:
  - Electronics (Batteries, ESCs, Wiring, Switches)
  - Weapons (Weapon cards + weapon drive motors/servos)
  - Armor (Chassis structure, Armor plates, Wedges, Horns, Forks, Self-righting)
  - Drivetrain (Wheels, Tires + drive gearmotors/hubmotors)

Motors/servos are attributed to whichever subsystem they supply based on
physical connectivity and circuit links:
  - Motors supplying weapons -> Weapons
  - Motors supplying wheels/tires -> Drivetrain
  - Servos supplying self-righting mechanisms -> Armor / Structure

Usage:
  python3 scripts/automata_weight_breakdown.py
  python3 scripts/automata_weight_breakdown.py --detailed
  python3 scripts/automata_weight_breakdown.py --json
  python3 scripts/automata_weight_breakdown.py --csv
  python3 scripts/automata_weight_breakdown.py --markdown
  python3 scripts/automata_weight_breakdown.py automata/Chonk.csv
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Path resolution
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    from builder.server.data import (
        CARD_HEIGHT_MM,
        CARD_WIDTH_MM,
        boxes_touch,
        load_all_cards,
        parse_robot_csv,
    )
except ImportError:
    # Fallback constants if builder package cannot be imported directly
    CARD_WIDTH_MM = 44.0
    CARD_HEIGHT_MM = 64.0

    def boxes_touch(
        b1: Tuple[float, float, float, float],
        b2: Tuple[float, float, float, float],
        tolerance: float = 3.0,
    ) -> bool:
        x1_min, y1_min, x1_max, y1_max = b1
        x2_min, y2_min, x2_max, y2_max = b2
        if x1_max < x2_min - tolerance or x2_max < x1_min - tolerance:
            return False
        if y1_max < y2_min - tolerance or y2_max < y1_min - tolerance:
            return False
        return True

    def load_all_cards() -> Dict[str, Any]:
        cards_by_name = {}
        for fname, ctype in [
            ("chassis.csv", "chassis"),
            ("components.csv", "component"),
            ("weapons.csv", "weapon"),
        ]:
            fpath = REPO_ROOT / "cardDefinitions" / fname
            if not fpath.exists():
                continue
            with open(fpath, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = (row.get("Name") or "").strip()
                    if not name:
                        continue
                    try:
                        weight = int(row.get("Weight") or 0)
                    except ValueError:
                        weight = 0
                    cards_by_name[name] = {
                        "name": name,
                        "type": ctype,
                        "weight": weight,
                        "requirements": (row.get("Requirements") or "").strip(),
                        "outputs": (row.get("Outputs") or "").strip(),
                        "keywords": (row.get("Keywords") or "").strip(),
                        "picture": (row.get("Picture") or "").strip(),
                    }
        return {"by_name": cards_by_name}

    def parse_robot_csv(csv_text: str) -> Dict[str, Any]:
        reader = csv.DictReader(io.StringIO(csv_text))
        catalog = load_all_cards()["by_name"]
        placed = []
        chassis = None
        for row in reader:
            cname = (row.get("card") or "").strip()
            loc = (row.get("location") or "").strip()
            conn = (row.get("connections") or "").strip()
            cid = (row.get("id") or "").strip()
            cdata = catalog.get(cname, {"name": cname, "weight": 0, "type": "component"})
            if cdata.get("type") == "chassis":
                if not chassis:
                    chassis = cdata
                continue
            x, y, rot = 100.0, 100.0, 0
            if loc.startswith("chassis:"):
                parts = loc[len("chassis:") :].split(",")
                try:
                    x = float(parts[0]) if len(parts) >= 1 else 100.0
                    y = float(parts[1]) if len(parts) >= 2 else 100.0
                    rot = int(float(parts[2])) if len(parts) >= 3 else 0
                except (ValueError, TypeError):
                    pass
            conn_list = [c.strip() for c in conn.split(";") if c.strip()]
            placed.append(
                {
                    "id": cid,
                    "card": cname,
                    "card_data": cdata,
                    "location": loc,
                    "x": x,
                    "y": y,
                    "rotation": rot,
                    "connections": conn_list,
                }
            )
        return {
            "chassis": chassis or {"name": "Default Chassis", "weight": 0, "type": "chassis"},
            "placed_cards": placed,
        }


CATEGORIES = ["electronics", "weapons", "armor", "drivetrain"]


@dataclass
class ComponentContribution:
    id: str
    name: str
    weight: int
    category: str
    role_description: str
    supplied_components: List[str] = field(default_factory=list)


@dataclass
class AutomatonWeightBreakdown:
    bot_name: str
    csv_file: str
    chassis_name: str
    chassis_weight: int
    electronics_weight: int
    weapons_weight: int
    armor_weight: int
    drivetrain_weight: int
    total_weight: int
    electronics_pct: float
    weapons_pct: float
    armor_pct: float
    drivetrain_pct: float
    contributions: List[ComponentContribution] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bot_name": self.bot_name,
            "csv_file": self.csv_file,
            "chassis_name": self.chassis_name,
            "chassis_weight": self.chassis_weight,
            "breakdown": {
                "electronics": self.electronics_weight,
                "weapons": self.weapons_weight,
                "armor": self.armor_weight,
                "drivetrain": self.drivetrain_weight,
                "total": self.total_weight,
            },
            "percentages": {
                "electronics": self.electronics_pct,
                "weapons": self.weapons_pct,
                "armor": self.armor_pct,
                "drivetrain": self.drivetrain_pct,
            },
            "contributions": [asdict(c) for c in self.contributions],
        }


def get_card_box(card: Dict[str, Any]) -> Tuple[float, float, float, float]:
    """Returns the axis-aligned bounding box (min_x, min_y, max_x, max_y) in mm."""
    rot = int(card.get("rotation", 0)) % 360
    if rot in (90, 270):
        cw, ch = CARD_HEIGHT_MM, CARD_WIDTH_MM
    else:
        cw, ch = CARD_WIDTH_MM, CARD_HEIGHT_MM
    x = float(card.get("x", 100.0))
    y = float(card.get("y", 100.0))
    return (x, y, x + cw, y + ch)


def is_wheel_card(card_name: str, card_data: Dict[str, Any]) -> bool:
    """Checks if component is a wheel / tire for drivetrain."""
    outs = card_data.get("outputs", "").upper()
    pic = card_data.get("picture", "").lower()
    name_lower = card_name.lower()
    return (
        any(d in outs for d in ("D", "M"))
        or "wheel" in name_lower
        or "tires" in name_lower
        or "tire" in name_lower
        or "wheels" in pic
    )


def is_weapon_card(card_name: str, card_data: Dict[str, Any]) -> bool:
    """Checks if card is a weapon."""
    ctype = card_data.get("type", "")
    outs = card_data.get("outputs", "").upper()
    return ctype == "weapon" or "W" in outs


def is_electronic_card(card_name: str, card_data: Dict[str, Any]) -> bool:
    """Checks if card is a battery, ESC, wiring, or power switch."""
    outs = card_data.get("outputs", "").upper()
    pic = card_data.get("picture", "").lower()
    name_lower = card_name.lower()
    is_battery = (
        ("E" in outs and not card_data.get("requirements"))
        or "battery" in pic
        or "galaxy" in name_lower
        or "tattu" in name_lower
    )
    is_wiring_esc = (
        "esc" in name_lower
        or "wire" in name_lower
        or "switch" in name_lower
        or "connectors" in pic
    )
    return is_battery or is_wiring_esc


def is_motor_or_servo(card_name: str, card_data: Dict[str, Any]) -> bool:
    """Checks if component is an electric motor, gearmotor, hubmotor, or servo."""
    name_lower = card_name.lower()
    req = card_data.get("requirements", "").upper()
    out = card_data.get("outputs", "").upper()
    has_motor_name = any(k in name_lower for k in ("motor", "gearmotor", "hubmotor", "servo"))
    converts_power = "E" in req and any(r in out for r in ("S", "P"))
    return has_motor_name or converts_power


def is_self_righting(card_name: str, card_data: Dict[str, Any]) -> bool:
    """Checks if component is a self-righting mechanism."""
    name_lower = card_name.lower()
    kw = card_data.get("keywords", "").lower()
    return "self right" in name_lower or "self-right" in kw


def resolve_motor_target_category(
    motor_card: Dict[str, Any],
    all_placed: List[Dict[str, Any]],
    catalog: Dict[str, Any],
    tolerance: float = 3.0,
) -> Tuple[str, List[str]]:
    """
    Determines which category a motor/servo supplies:
      - 'weapons' if supplying a weapon
      - 'drivetrain' if supplying wheels
      - 'armor' if supplying a self-righting arm
    Returns (target_category, list_of_supplied_card_descriptions).
    """
    motor_name = motor_card["card"]
    motor_data = motor_card["data"]
    motor_out = set(motor_data.get("outputs", "").upper())
    motor_box = motor_card["box"]

    supplied_names: List[str] = []
    supplied_types: Set[str] = set()

    for other in all_placed:
        if other["id"] == motor_card["id"]:
            continue
        other_name = other["card"]
        other_data = other["data"]
        other_req = set(other_data.get("requirements", "").upper())

        # If other component accepts motor output (e.g. Spin 'S' or Pressure 'P')
        if motor_out & other_req:
            # Check physical touching
            if boxes_touch(motor_box, other["box"], tolerance=tolerance):
                supplied_names.append(f"{other_name} (#{other['id']})")
                if is_weapon_card(other_name, other_data):
                    supplied_types.add("weapons")
                elif is_wheel_card(other_name, other_data):
                    supplied_types.add("drivetrain")
                elif is_self_righting(other_name, other_data):
                    supplied_types.add("armor")

    # If touching did not find matches, check explicit connection strings
    if not supplied_types:
        conns = motor_card.get("connections", [])
        conn_set = set(conns)
        for other in all_placed:
            if other["id"] == motor_card["id"]:
                continue
            other_name = other["card"]
            other_data = other["data"]
            other_req = set(other_data.get("requirements", "").upper())
            if motor_out & other_req:
                other_conns = set(other.get("connections", []))
                # Explicit link either by ID or shared hyperedge token
                shared = (conn_set & other_conns) or (other["id"] in conn_set) or (motor_card["id"] in other_conns)
                if shared:
                    supplied_names.append(f"{other_name} (#{other['id']})")
                    if is_weapon_card(other_name, other_data):
                        supplied_types.add("weapons")
                    elif is_wheel_card(other_name, other_data):
                        supplied_types.add("drivetrain")
                    elif is_self_righting(other_name, other_data):
                        supplied_types.add("armor")

    # Determine winning category
    if "weapons" in supplied_types:
        return "weapons", supplied_names
    if "drivetrain" in supplied_types:
        return "drivetrain", supplied_names
    if "armor" in supplied_types:
        return "armor", supplied_names

    # Fallback heuristic based on naming if isolated
    name_lower = motor_name.lower()
    if "weapon" in name_lower:
        return "weapons", ["Weapon motor (isolated heuristic)"]
    return "drivetrain", ["Drive motor (isolated heuristic)"]


def analyze_automaton(
    csv_path: Path | str,
    catalog: Optional[Dict[str, Any]] = None,
    include_chassis: bool = True,
) -> AutomatonWeightBreakdown:
    """Computes the 4-category weight breakdown for a single automaton CSV file."""
    path = Path(csv_path)
    if catalog is None:
        catalog = load_all_cards()["by_name"]

    with open(path, "r", encoding="utf-8") as f:
        csv_text = f.read()

    parsed = parse_robot_csv(csv_text)
    placed = parsed.get("placed_cards", [])
    chassis = parsed.get("chassis") or {"name": "Default Chassis", "weight": 0}

    # Pre-populate bounding boxes and catalog data
    for c in placed:
        c["box"] = get_card_box(c)
        c["data"] = catalog.get(c["card"], {"name": c["card"], "weight": 0, "type": "component"})

    weights = {"electronics": 0, "weapons": 0, "armor": 0, "drivetrain": 0}
    contributions: List[ComponentContribution] = []

    # 1. Chassis (Structural base armor)
    ch_name = chassis.get("name", "Unknown Chassis")
    ch_wt = int(chassis.get("weight", 0))
    if include_chassis:
        weights["armor"] += ch_wt
        contributions.append(
            ComponentContribution(
                id="chassis",
                name=ch_name,
                weight=ch_wt,
                category="armor",
                role_description="Chassis structure & base frame",
                supplied_components=[],
            )
        )

    # 2. Placed cards
    for c in placed:
        cid = str(c.get("id", ""))
        cname = c["card"]
        cdata = c["data"]
        wt = int(cdata.get("weight", 0))

        # 2A. Weapons
        if is_weapon_card(cname, cdata):
            weights["weapons"] += wt
            contributions.append(
                ComponentContribution(
                    id=cid,
                    name=cname,
                    weight=wt,
                    category="weapons",
                    role_description="Active Weapon Assembly",
                )
            )
            continue

        # 2B. Wheels / Tires (Drivetrain)
        if is_wheel_card(cname, cdata):
            weights["drivetrain"] += wt
            contributions.append(
                ComponentContribution(
                    id=cid,
                    name=cname,
                    weight=wt,
                    category="drivetrain",
                    role_description="Drive Wheel / Tire",
                )
            )
            continue

        # 2C. Electronics (Batteries, ESCs, Wiring, Power switches)
        if is_electronic_card(cname, cdata):
            weights["electronics"] += wt
            role = "Battery Pack" if "battery" in cdata.get("picture", "").lower() or "galaxy" in cname.lower() or "tattu" in cname.lower() else "Wiring / ESC"
            contributions.append(
                ComponentContribution(
                    id=cid,
                    name=cname,
                    weight=wt,
                    category="electronics",
                    role_description=role,
                )
            )
            continue

        # 2D. Motors & Servos (Supply attribution rule)
        if is_motor_or_servo(cname, cdata):
            target_cat, supplied = resolve_motor_target_category(c, placed, catalog)
            weights[target_cat] += wt
            desc = f"Supplies {', '.join(supplied)}" if supplied else "Motor actuator"
            contributions.append(
                ComponentContribution(
                    id=cid,
                    name=cname,
                    weight=wt,
                    category=target_cat,
                    role_description=f"Motor ({desc})",
                    supplied_components=supplied,
                )
            )
            continue

        # 2E. Self-righting arm
        if is_self_righting(cname, cdata):
            weights["armor"] += wt
            contributions.append(
                ComponentContribution(
                    id=cid,
                    name=cname,
                    weight=wt,
                    category="armor",
                    role_description="Self-righting mechanism",
                )
            )
            continue

        # 2F. Armor plates, Wedges, Forks, Horns, Structural components
        weights["armor"] += wt
        contributions.append(
            ComponentContribution(
                id=cid,
                name=cname,
                weight=wt,
                category="armor",
                role_description="Armor / Defensive / Structural Plate",
            )
        )

    total_wt = sum(weights.values())
    elec_pct = round((weights["electronics"] / total_wt * 100) if total_wt else 0.0, 1)
    weap_pct = round((weights["weapons"] / total_wt * 100) if total_wt else 0.0, 1)
    arm_pct = round((weights["armor"] / total_wt * 100) if total_wt else 0.0, 1)
    drive_pct = round((weights["drivetrain"] / total_wt * 100) if total_wt else 0.0, 1)

    return AutomatonWeightBreakdown(
        bot_name=path.stem,
        csv_file=str(path),
        chassis_name=ch_name,
        chassis_weight=ch_wt,
        electronics_weight=weights["electronics"],
        weapons_weight=weights["weapons"],
        armor_weight=weights["armor"],
        drivetrain_weight=weights["drivetrain"],
        total_weight=total_wt,
        electronics_pct=elec_pct,
        weapons_pct=weap_pct,
        armor_pct=arm_pct,
        drivetrain_pct=drive_pct,
        contributions=contributions,
    )


def analyze_all_automata(
    automata_dir: Path | str = REPO_ROOT / "automata",
    include_chassis: bool = True,
) -> List[AutomatonWeightBreakdown]:
    """Analyzes all automata CSV files in the designated directory."""
    target_dir = Path(automata_dir)
    catalog = load_all_cards()["by_name"]
    results = []
    for csv_file in sorted(target_dir.glob("*.csv")):
        results.append(analyze_automaton(csv_file, catalog=catalog, include_chassis=include_chassis))
    return results


def format_table(
    breakdowns: List[AutomatonWeightBreakdown],
    markdown: bool = False,
    include_chassis: bool = True,
) -> str:
    """Formats the breakdown results as an aligned ASCII or Markdown table."""
    if not breakdowns:
        return "No automata found."

    lines = []
    if markdown:
        lines.append("| Automaton | Electronics | Weapons | Armor | Drivetrain | Total Weight |")
        lines.append("|:---|---:|---:|---:|---:|---:|")
        for b in breakdowns:
            e_str = f"{b.electronics_weight} ({b.electronics_pct:.1f}%)"
            w_str = f"{b.weapons_weight} ({b.weapons_pct:.1f}%)"
            a_str = f"{b.armor_weight} ({b.armor_pct:.1f}%)"
            d_str = f"{b.drivetrain_weight} ({b.drivetrain_pct:.1f}%)"
            lines.append(f"| **{b.bot_name}** | {e_str} | {w_str} | {a_str} | {d_str} | **{b.total_weight}** |")

        # Average row
        n = len(breakdowns)
        avg_e = sum(b.electronics_weight for b in breakdowns) / n
        avg_w = sum(b.weapons_weight for b in breakdowns) / n
        avg_a = sum(b.armor_weight for b in breakdowns) / n
        avg_d = sum(b.drivetrain_weight for b in breakdowns) / n
        avg_tot = sum(b.total_weight for b in breakdowns) / n
        lines.append(
            f"| **AVERAGE** | {avg_e:.1f} ({(avg_e/avg_tot*100):.1f}%) | "
            f"{avg_w:.1f} ({(avg_w/avg_tot*100):.1f}%) | "
            f"{avg_a:.1f} ({(avg_a/avg_tot*100):.1f}%) | "
            f"{avg_d:.1f} ({(avg_d/avg_tot*100):.1f}%) | **{avg_tot:.1f}** |"
        )
    else:
        header = f"{'Automaton':<20} | {'Electronics':<16} | {'Weapons':<16} | {'Armor':<16} | {'Drivetrain':<16} | {'Total':<6}"
        sep = "-" * len(header)
        lines.append(sep)
        lines.append(header)
        lines.append(sep)
        for b in breakdowns:
            e_str = f"{b.electronics_weight:>2} ({b.electronics_pct:>4.1f}%)"
            w_str = f"{b.weapons_weight:>2} ({b.weapons_pct:>4.1f}%)"
            a_str = f"{b.armor_weight:>2} ({b.armor_pct:>4.1f}%)"
            d_str = f"{b.drivetrain_weight:>2} ({b.drivetrain_pct:>4.1f}%)"
            lines.append(f"{b.bot_name:<20} | {e_str:<16} | {w_str:<16} | {a_str:<16} | {d_str:<16} | {b.total_weight:>5}")
        lines.append(sep)
        n = len(breakdowns)
        avg_e = sum(b.electronics_weight for b in breakdowns) / n
        avg_w = sum(b.weapons_weight for b in breakdowns) / n
        avg_a = sum(b.armor_weight for b in breakdowns) / n
        avg_d = sum(b.drivetrain_weight for b in breakdowns) / n
        avg_tot = sum(b.total_weight for b in breakdowns) / n
        avg_e_str = f"{avg_e:>4.1f} ({(avg_e/avg_tot*100):>4.1f}%)"
        avg_w_str = f"{avg_w:>4.1f} ({(avg_w/avg_tot*100):>4.1f}%)"
        avg_a_str = f"{avg_a:>4.1f} ({(avg_a/avg_tot*100):>4.1f}%)"
        avg_d_str = f"{avg_d:>4.1f} ({(avg_d/avg_tot*100):>4.1f}%)"
        lines.append(f"{'AVERAGE':<20} | {avg_e_str:<16} | {avg_w_str:<16} | {avg_a_str:<16} | {avg_d_str:<16} | {avg_tot:>5.1f}")
        lines.append(sep)

    return "\n".join(lines)


def format_detailed(breakdowns: List[AutomatonWeightBreakdown]) -> str:
    """Formats an itemized component-by-component report for each automaton."""
    lines = []
    for b in breakdowns:
        lines.append("=" * 80)
        lines.append(f"🤖 {b.bot_name.upper()}  [Chassis: {b.chassis_name} (wt: {b.chassis_weight})]")
        lines.append(
            f"   Total Weight: {b.total_weight} pts | "
            f"Elec: {b.electronics_weight} ({b.electronics_pct:.1f}%) | "
            f"Weapons: {b.weapons_weight} ({b.weapons_pct:.1f}%) | "
            f"Armor: {b.armor_weight} ({b.armor_pct:.1f}%) | "
            f"Drive: {b.drivetrain_weight} ({b.drivetrain_pct:.1f}%)"
        )
        lines.append("-" * 80)

        for cat in CATEGORIES:
            cat_items = [c for c in b.contributions if c.category == cat]
            subtotal = sum(c.weight for c in cat_items)
            pct = (subtotal / b.total_weight * 100) if b.total_weight else 0.0
            lines.append(f"  ▶ {cat.upper():<12} Subtotal: {subtotal:>2} pts ({pct:>4.1f}%)")
            for item in cat_items:
                supp_note = f" -> supplies [{', '.join(item.supplied_components)}]" if item.supplied_components else ""
                lines.append(f"      • [{item.id:>7}] {item.name:<26} wt={item.weight:>2}  ({item.role_description}{supp_note})")
            lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute weight usage breakdown for Robot Battles automata across Electronics, Weapons, Armor, and Drivetrain."
    )
    parser.add_argument(
        "automata",
        nargs="*",
        help="Optional paths or names of specific automata CSV files to analyze.",
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Show itemized component breakdown per category for each robot.",
    )
    parser.add_argument(
        "--exclude-chassis",
        action="store_true",
        help="Exclude chassis mat weight from armor (only count placed component cards).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format.",
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        help="Output summary table in CSV format.",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Format output table as GitHub Flavored Markdown.",
    )
    args = parser.parse_args()

    include_chassis = not args.exclude_chassis

    # Resolve target files
    if args.automata:
        files = []
        for a in args.automata:
            p = Path(a)
            if not p.exists() and not p.suffix:
                p = REPO_ROOT / "automata" / f"{a}.csv"
            elif not p.exists():
                p = REPO_ROOT / "automata" / p.name
            if p.exists():
                files.append(p)
            else:
                print(f"Warning: Automaton file not found: {a}", file=sys.stderr)
        catalog = load_all_cards()["by_name"]
        breakdowns = [analyze_automaton(f, catalog=catalog, include_chassis=include_chassis) for f in files]
    else:
        breakdowns = analyze_all_automata(include_chassis=include_chassis)

    if args.json:
        data = {
            "include_chassis": include_chassis,
            "automata": [b.to_dict() for b in breakdowns],
        }
        print(json.dumps(data, indent=2))
        return

    if args.csv:
        writer = csv.writer(sys.stdout, lineterminator="\n")
        writer.writerow([
            "bot_name",
            "chassis",
            "electronics_weight",
            "electronics_pct",
            "weapons_weight",
            "weapons_pct",
            "armor_weight",
            "armor_pct",
            "drivetrain_weight",
            "drivetrain_pct",
            "total_weight",
        ])
        for b in breakdowns:
            writer.writerow([
                b.bot_name,
                b.chassis_name,
                b.electronics_weight,
                b.electronics_pct,
                b.weapons_weight,
                b.weapons_pct,
                b.armor_weight,
                b.armor_pct,
                b.drivetrain_weight,
                b.drivetrain_pct,
                b.total_weight,
            ])
        return

    # Print summary table
    print(format_table(breakdowns, markdown=args.markdown, include_chassis=include_chassis))

    if args.detailed:
        print("\n" + format_detailed(breakdowns))


if __name__ == "__main__":
    main()
