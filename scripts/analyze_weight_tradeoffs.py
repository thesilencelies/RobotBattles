#!/usr/bin/env python3
"""
scripts/analyze_weight_tradeoffs.py

Analysis and plotting tool for weight tradeoffs across Robot Battles cards.
Plots out weight vs input/output resources for each component and weapon,
rendering each conversion as a bar with distinct input and output symbols on either end.

Provides:
- Separate plots for each component type (Motors, Servos, Wheels, Weapons, Batteries, Transmission, Armor).
- Multi-panel overview plot.
- Standalone interactive HTML report with dynamic spin-up slider, SVG charts, and comparison table.
- High-resolution Matplotlib PNG plot exports with embedded icons and markers.
- CLI options to view specific component types, run a live local server, or open in browser.
"""

from __future__ import annotations

import argparse
import base64
import csv
import html
import http.server
import io
import json
import math
import os
import re
import socketserver
import sys
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
CARD_DEFS_DIR = REPO_ROOT / "cardDefinitions"
ICONS_DIR = REPO_ROOT / "pictures" / "icons"
OUTPUT_DIR = REPO_ROOT / "scripts" / "output"

CATEGORIES = [
    "Motors",
    "Servos",
    "Wheels",
    "Weapons",
    "Batteries",
    "Transmission",
    "Armor",
]

RESOURCE_INFO = {
    "E": {"name": "Energy", "color": "#f59e0b", "icon": "energy.png", "emoji": "⚡"},
    "S": {"name": "Spin", "color": "#3b82f6", "icon": "spin.png", "emoji": "🔄"},
    "P": {"name": "Pressure", "color": "#8b5cf6", "icon": "pressure.png", "emoji": "🅿️"},
    "D": {"name": "Drive", "color": "#10b981", "icon": "drive.png", "emoji": "🏎️"},
    "M": {"name": "Drive", "color": "#10b981", "icon": "drive.png", "emoji": "🏎️"},
    "W": {"name": "Damage", "color": "#ef4444", "icon": "damage.png", "emoji": "💥"},
    "None": {"name": "None", "color": "#64748b", "icon": "weight_plain.png", "emoji": "⚪"},
}


def load_icon_base64() -> Dict[str, str]:
    """Reads all icon PNGs from pictures/icons and returns a dict of base64 data URIs."""
    b64_dict = {}
    if not ICONS_DIR.exists():
        return b64_dict

    for icon_file in ICONS_DIR.glob("*.png"):
        try:
            with open(icon_file, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("ascii")
                b64_dict[icon_file.name] = f"data:image/png;base64,{encoded}"
        except Exception:
            pass
    return b64_dict


def parse_resource_string(raw: str) -> Tuple[str, float]:
    """
    Parses a simple resource string (e.g., 'EE', 'SSSS', 'DDDD', 'XE').
    Returns (resource_char, count).
    """
    raw = (raw or "").strip()
    if not raw:
        return ("None", 0.0)

    # Passthrough: XE, XS
    if raw.upper() in ("XE", "XS"):
        return (raw[-1].upper(), 1.0)

    # Mixed inputs (e.g., SSSPP -> 3 Spin, 2 Pressure)
    # Count frequency of resource characters
    counts: Dict[str, int] = {}
    for ch in raw:
        cu = ch.upper()
        if cu in ("E", "S", "P", "D", "M", "W"):
            counts[cu] = counts.get(cu, 0) + 1

    if not counts:
        return ("None", 0.0)

    # Return the dominant resource or total count if homogeneous
    if len(counts) == 1:
        res = list(counts.keys())[0]
        return (res, float(counts[res]))

    # If mixed, pick the primary and sum the total
    total = sum(counts.values())
    primary = max(counts.keys(), key=lambda k: counts[k])
    return (primary, float(total))


def parse_weapon_spinup(raw: str) -> Tuple[float, float, bool]:
    """
    Parses weapon output expressions like:
    - 'WWWW' -> (4.0, 0.0, False)
    - '2XWW' -> (2.0, 2.0, False)  (2 base damage + 2*X)
    - '3XW'  -> (1.0, 3.0, False)  (1 base damage + 3*X)
    - 'XXW'  -> (1.0, 1.0, True)   (1 base damage + 1*X^2)
    - 'XWW'  -> (2.0, 1.0, False)  (2 base damage + 1*X)
    - 'XWWW' -> (3.0, 1.0, False)  (3 base damage + 1*X)
    - 'WWW2XW' -> (4.0, 2.0, False) (4 base damage + 2*X)
    Returns (base_damage, spinup_multiplier, is_quadratic).
    """
    raw = (raw or "").strip()
    if not raw:
        return (0.0, 0.0, False)

    # Check for XXW (quadratic spinup)
    if "XX" in raw.upper():
        fixed_w = raw.upper().count("W")
        return (float(max(1, fixed_w)), 1.0, True)

    # Check for multiplier + X: e.g. 2XW, 3XW, 2XWW, XWW
    match_mult = re.search(r"(\d*)X", raw, re.IGNORECASE)
    if match_mult:
        mult_str = match_mult.group(1)
        multiplier = float(mult_str) if mult_str else 1.0
        # Count Ws that are not part of the X term
        # If formula is 2XWW: 2 Ws total
        total_w = raw.upper().count("W")
        base_w = float(max(1, total_w))
        return (base_w, multiplier, False)

    # Pure repeated letters: WWWW, WWW
    pure_w = raw.upper().count("W")
    return (float(pure_w), 0.0, False)


def extract_max_spinup(keywords: str) -> int:
    """Extracts max spinup from keywords like 'Spin up (4)' or 'Spin up (3)'."""
    m = re.search(r"Spin up\s*\(\s*(\d+)\s*\)", keywords or "", re.IGNORECASE)
    if m:
        return int(m.group(1))
    return 0


@dataclass
class CardTradeoffData:
    name: str
    card_type: str  # component or weapon
    category: str   # Motors, Servos, Wheels, Weapons, Batteries, Transmission, Armor
    weight: int
    cost: int
    durability: int
    absorption: int
    requirements_raw: str
    outputs_raw: str
    input_resource: str
    input_qty: float
    output_resource: str
    output_qty_base: float
    spinup_multiplier: float = 0.0
    spinup_quadratic: bool = False
    max_spinup: int = 0
    is_passthrough: bool = False
    keywords: str = ""
    text: str = ""
    picture: str = ""

    @property
    def output_qty_max(self) -> float:
        return self.output_at_x(self.max_spinup)

    def output_at_x(self, x: int) -> float:
        """Computes output quantity at spinup counter x."""
        if self.max_spinup == 0 or self.spinup_multiplier == 0.0:
            return self.output_qty_base
        val_x = min(x, self.max_spinup)
        if self.spinup_quadratic:
            return self.output_qty_base + (val_x ** 2) * self.spinup_multiplier
        return self.output_qty_base + val_x * self.spinup_multiplier

    def efficiency_ratio(self, x: int = 0) -> float:
        """Output / Input ratio."""
        if self.input_qty <= 0:
            return 0.0
        return round(self.output_at_x(x) / self.input_qty, 2)

    def weight_efficiency(self, x: int = 0) -> float:
        """Output / Weight ratio."""
        if self.weight <= 0:
            return 0.0
        return round(self.output_at_x(x) / self.weight, 2)

    def net_output_per_weight(self, x: int = 0) -> float:
        """(Output - Input) / Weight ratio."""
        if self.weight <= 0:
            return 0.0
        return round((self.output_at_x(x) - self.input_qty) / self.weight, 2)


def classify_card(
    name: str,
    card_type: str,
    req_raw: str,
    out_raw: str,
    in_res: str,
    in_qty: float,
    out_res: str,
    out_qty: float,
    keywords: str,
) -> str:
    """Categorizes a card into one of the designated categories."""
    if card_type == "weapon":
        return "Weapons"

    # Batteries: Outputs Energy, no input
    if in_qty == 0 and out_res == "E":
        return "Batteries"

    # Motors: Energy in -> Spin out
    if in_res == "E" and out_res == "S":
        return "Motors"

    # Servos: Energy in -> Pressure out
    if in_res == "E" and out_res == "P":
        return "Servos"

    # Wheels: Spin in -> Drive out
    if in_res == "S" and out_res in ("D", "M"):
        return "Wheels"

    # Transmission / Wiring: passthroughs, ESC, Timing Pulley
    if (
        "XE" in req_raw.upper()
        or "XS" in req_raw.upper()
        or "ESC" in name
        or "Pulley" in name
        or "Belt" in name
        or (in_res == "E" and out_res == "E")
        or (in_res == "S" and out_res == "S")
    ):
        return "Transmission"

    # Armor / Defensive / Mechanicals: no output or pure absorption/durability
    return "Armor"


def load_all_tradeoff_cards() -> List[CardTradeoffData]:
    """Loads all cards from components.csv and weapons.csv and parses tradeoff data."""
    cards: List[CardTradeoffData] = []

    # 1. Load components.csv
    comp_file = CARD_DEFS_DIR / "components.csv"
    if comp_file.exists():
        with open(comp_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = (row.get("Name") or "").strip()
                if not name:
                    continue

                try:
                    weight = int(row.get("Weight") or 0)
                except ValueError:
                    weight = 0

                try:
                    cost = int(row.get("Cost") or 0)
                except ValueError:
                    cost = 0

                try:
                    durability = int(row.get("Durability") or 0)
                except ValueError:
                    durability = 0

                try:
                    absorption = int(row.get("Absorption") or 0)
                except ValueError:
                    absorption = 0

                req_raw = (row.get("Requirements") or "").strip()
                out_raw = (row.get("Outputs") or "").strip()
                keywords = (row.get("Keywords") or "").strip()
                text = (row.get("Text") or "").strip()
                picture = (row.get("Picture") or "").strip()

                in_res, in_qty = parse_resource_string(req_raw)
                out_res, out_qty = parse_resource_string(out_raw)

                is_passthrough = ("XE" in req_raw.upper() and "XE" in out_raw.upper()) or (
                    "XS" in req_raw.upper() and "XS" in out_raw.upper()
                )

                category = classify_card(
                    name=name,
                    card_type="component",
                    req_raw=req_raw,
                    out_raw=out_raw,
                    in_res=in_res,
                    in_qty=in_qty,
                    out_res=out_res,
                    out_qty=out_qty,
                    keywords=keywords,
                )

                card = CardTradeoffData(
                    name=name,
                    card_type="component",
                    category=category,
                    weight=weight,
                    cost=cost,
                    durability=durability,
                    absorption=absorption,
                    requirements_raw=req_raw,
                    outputs_raw=out_raw,
                    input_resource=in_res,
                    input_qty=in_qty,
                    output_resource=out_res,
                    output_qty_base=out_qty,
                    spinup_multiplier=0.0,
                    spinup_quadratic=False,
                    max_spinup=0,
                    is_passthrough=is_passthrough,
                    keywords=keywords,
                    text=text,
                    picture=picture,
                )
                cards.append(card)

    # 2. Load weapons.csv
    weap_file = CARD_DEFS_DIR / "weapons.csv"
    if weap_file.exists():
        with open(weap_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = (row.get("Name") or "").strip()
                if not name:
                    continue

                try:
                    weight = int(row.get("Weight") or 0)
                except ValueError:
                    weight = 0

                try:
                    cost = int(row.get("Cost") or 0)
                except ValueError:
                    cost = 0

                try:
                    durability = int(row.get("Durability") or 0)
                except ValueError:
                    durability = 0

                try:
                    absorption = int(row.get("Absorption") or 0)
                except ValueError:
                    absorption = 0

                req_raw = (row.get("Requirements") or "").strip()
                out_raw = (row.get("Outputs") or "").strip()
                keywords = (row.get("Keywords") or "").strip()
                text = (row.get("Text") or "").strip()
                picture = (row.get("Picture") or "").strip()

                in_res, in_qty = parse_resource_string(req_raw)
                base_w, mult_w, quad_w = parse_weapon_spinup(out_raw)
                max_spinup = extract_max_spinup(keywords)

                card = CardTradeoffData(
                    name=name,
                    card_type="weapon",
                    category="Weapons",
                    weight=weight,
                    cost=cost,
                    durability=durability,
                    absorption=absorption,
                    requirements_raw=req_raw,
                    outputs_raw=out_raw,
                    input_resource=in_res,
                    input_qty=in_qty,
                    output_resource="W",
                    output_qty_base=base_w,
                    spinup_multiplier=mult_w,
                    spinup_quadratic=quad_w,
                    max_spinup=max_spinup,
                    is_passthrough=False,
                    keywords=keywords,
                    text=text,
                    picture=picture,
                )
                cards.append(card)

    return cards


# ==============================================================================
# Matplotlib High-Resolution Plot Generation
# ==============================================================================

def generate_matplotlib_plots(
    cards: List[CardTradeoffData],
    output_dir: Path,
    categories: Optional[List[str]] = None,
    spinup_x: int = 0,
) -> List[str]:
    """
    Generates standalone PNG plots for specified categories,
    plus an all-in-one overview plot.
    Returns list of generated file paths.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.offsetbox import AnnotationBbox, OffsetImage
    from PIL import Image

    output_dir.mkdir(parents=True, exist_ok=True)
    target_categories = categories or CATEGORIES
    generated_files: List[str] = []

    # Preload icon PIL images
    pil_icons: Dict[str, Image.Image] = {}
    if ICONS_DIR.exists():
        for icon_path in ICONS_DIR.glob("*.png"):
            try:
                pil_icons[icon_path.name] = Image.open(icon_path).convert("RGBA")
            except Exception:
                pass

    def add_icon(ax, icon_filename: str, x: float, y: float, zoom: float = 0.055):
        if icon_filename in pil_icons:
            img = pil_icons[icon_filename]
            im = OffsetImage(img, zoom=zoom)
            ab = AnnotationBbox(im, (x, y), frameon=False, zorder=5)
            ax.add_artist(ab)

    # Styling helper
    def style_ax(ax, title: str, xlabel: str = "Weight (T)", ylabel: str = "Resource Quantity"):
        ax.set_facecolor("#111827")
        ax.grid(True, color="#374151", linestyle="--", alpha=0.5, zorder=1)
        ax.set_title(title, fontsize=14, fontweight="bold", color="#f3f4f6", pad=12)
        ax.set_xlabel(xlabel, fontsize=11, fontweight="bold", color="#9ca3af")
        ax.set_ylabel(ylabel, fontsize=11, fontweight="bold", color="#9ca3af")
        ax.tick_params(colors="#9ca3af", labelsize=10)
        for spine in ax.spines.values():
            spine.set_color("#4b5563")

    # Generate individual plots for each category
    for cat in target_categories:
        cat_cards = [c for c in cards if c.category == cat]
        if not cat_cards:
            continue

        fig, ax = plt.subplots(figsize=(10, 6.5), dpi=160)
        fig.patch.set_facecolor("#0b0f17")

        if cat == "Armor":
            # Plot Weight vs Durability & Absorption
            style_ax(ax, f"Weight Tradeoffs: {cat} (Durability & Absorption)", ylabel="Stat Value")
            for idx, c in enumerate(cat_cards):
                # Bar from Absorption to Durability
                x = c.weight + (idx % 3 - 1) * 0.12
                y_in = c.absorption
                y_out = c.durability
                ax.plot([x, x], [y_in, y_out], color="#94a3b8", linewidth=3.5, solid_capstyle="round", zorder=3)
                add_icon(ax, "absorption.png", x, y_in, zoom=0.05)
                add_icon(ax, "durability.png", x, y_out, zoom=0.05)
                ax.text(x, y_out + 0.6, c.name, fontsize=8.5, color="#f9fafb", ha="center", weight="semibold", zorder=4)
            ax.set_xlim(-0.5, 5.5)
            ax.set_ylim(-1, 20)
        elif cat == "Batteries":
            # Plot Weight vs Energy Output
            style_ax(ax, f"Weight Tradeoffs: {cat} (Energy Output)", ylabel="Energy Output (E)")
            for idx, c in enumerate(cat_cards):
                x = c.weight + (idx % 2 - 0.5) * 0.15
                y_in = 0.0
                y_out = c.output_qty_base
                ax.plot([x, x], [y_in, y_out], color="#f59e0b", linewidth=3.5, solid_capstyle="round", zorder=3)
                add_icon(ax, "weight_plain.png", x, y_in, zoom=0.05)
                add_icon(ax, "energy.png", x, y_out, zoom=0.05)
                ax.text(x, y_out + 0.35, c.name, fontsize=8.5, color="#f9fafb", ha="center", weight="semibold", zorder=4)
            ax.set_xlim(0, 4.5)
            ax.set_ylim(-0.5, 8.5)
        else:
            # Standard converter plot: Input -> Output
            style_ax(ax, f"Weight Tradeoffs: {cat} (Input -> Output, Spin-up X={spinup_x})", ylabel="Resource Quantity")

            # Group cards by weight to compute horizontal offsets
            cards_by_w: Dict[int, List[CardTradeoffData]] = {}
            for c in cat_cards:
                cards_by_w.setdefault(c.weight, []).append(c)

            for w, w_list in cards_by_w.items():
                n_items = len(w_list)
                for i, c in enumerate(w_list):
                    offset = 0.0 if n_items == 1 else (i - (n_items - 1) / 2) * 0.22
                    x = w + offset
                    y_in = c.input_qty
                    y_out = c.output_at_x(spinup_x)

                    in_icon = RESOURCE_INFO.get(c.input_resource, {}).get("icon", "weight_plain.png")
                    out_icon = RESOURCE_INFO.get(c.output_resource, {}).get("icon", "damage.png")
                    in_color = RESOURCE_INFO.get(c.input_resource, {}).get("color", "#3b82f6")
                    out_color = RESOURCE_INFO.get(c.output_resource, {}).get("color", "#ef4444")

                    # Draw connecting bar
                    bar_color = out_color if y_out >= y_in else "#64748b"
                    ax.plot([x, x], [y_in, y_out], color=bar_color, linewidth=4, solid_capstyle="round", zorder=3)

                    # Add icons at endpoints
                    add_icon(ax, in_icon, x, y_in, zoom=0.05)
                    add_icon(ax, out_icon, x, y_out, zoom=0.05)

                    # Label card name
                    label_y = max(y_in, y_out) + 0.45
                    ax.text(
                        x, label_y, f"{c.name}\n({c.input_qty:g}{c.input_resource}→{y_out:g}{c.output_resource})",
                        fontsize=7.8, color="#e5e7eb", ha="center", weight="semibold", zorder=4
                    )

            max_y = max([c.output_at_x(spinup_x) for c in cat_cards] + [c.input_qty for c in cat_cards] + [6])
            ax.set_xlim(-0.5, 7.0)
            ax.set_ylim(-0.8, max_y + 1.8)

        fig.tight_layout()
        file_path = output_dir / f"weight_tradeoffs_{cat.lower()}.png"
        fig.savefig(file_path, facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close(fig)
        generated_files.append(str(file_path))

    # Multi-panel Overview Figure
    fig, axes = plt.subplots(2, 3, figsize=(18, 11), dpi=150)
    fig.patch.set_facecolor("#0b0f17")
    fig.suptitle(f"Robot Battles - Weight Tradeoff Comparison Grid (Spin-up X={spinup_x})", fontsize=18, fontweight="bold", color="#f9fafb", y=0.98)

    overview_cats = ["Motors", "Servos", "Wheels", "Weapons", "Batteries", "Armor"]
    for ax_idx, cat in enumerate(overview_cats):
        row = ax_idx // 3
        col = ax_idx % 3
        ax = axes[row, col]
        cat_cards = [c for c in cards if c.category == cat]
        if not cat_cards:
            ax.axis("off")
            continue

        if cat == "Armor":
            style_ax(ax, "Armor & Mechanicals", ylabel="Durability & Absorption")
            for idx, c in enumerate(cat_cards):
                x = c.weight + (idx % 3 - 1) * 0.12
                ax.plot([x, x], [c.absorption, c.durability], color="#94a3b8", linewidth=3, zorder=3)
                add_icon(ax, "absorption.png", x, c.absorption, zoom=0.04)
                add_icon(ax, "durability.png", x, c.durability, zoom=0.04)
                ax.text(x, c.durability + 0.6, c.name, fontsize=7, color="#e5e7eb", ha="center", zorder=4)
            ax.set_xlim(-0.5, 5.0)
            ax.set_ylim(-1, 20)
        elif cat == "Batteries":
            style_ax(ax, "Batteries (Energy Output)", ylabel="Energy (E)")
            for idx, c in enumerate(cat_cards):
                x = c.weight + (idx % 2 - 0.5) * 0.15
                ax.plot([x, x], [0, c.output_qty_base], color="#f59e0b", linewidth=3, zorder=3)
                add_icon(ax, "weight_plain.png", x, 0, zoom=0.04)
                add_icon(ax, "energy.png", x, c.output_qty_base, zoom=0.04)
                ax.text(x, c.output_qty_base + 0.35, c.name, fontsize=7, color="#e5e7eb", ha="center", zorder=4)
            ax.set_xlim(0, 4.0)
            ax.set_ylim(-0.5, 8.0)
        else:
            style_ax(ax, f"{cat} ({cat_cards[0].input_resource} → {cat_cards[0].output_resource})", ylabel="Resource Quantity")
            cards_by_w: Dict[int, List[CardTradeoffData]] = {}
            for c in cat_cards:
                cards_by_w.setdefault(c.weight, []).append(c)

            for w, w_list in cards_by_w.items():
                n_items = len(w_list)
                for i, c in enumerate(w_list):
                    offset = 0.0 if n_items == 1 else (i - (n_items - 1) / 2) * 0.22
                    x = w + offset
                    y_in = c.input_qty
                    y_out = c.output_at_x(spinup_x)

                    in_icon = RESOURCE_INFO.get(c.input_resource, {}).get("icon", "weight_plain.png")
                    out_icon = RESOURCE_INFO.get(c.output_resource, {}).get("icon", "damage.png")
                    out_color = RESOURCE_INFO.get(c.output_resource, {}).get("color", "#ef4444")

                    ax.plot([x, x], [y_in, y_out], color=out_color if y_out >= y_in else "#64748b", linewidth=3.2, zorder=3)
                    add_icon(ax, in_icon, x, y_in, zoom=0.04)
                    add_icon(ax, out_icon, x, y_out, zoom=0.04)
                    label_y = max(y_in, y_out) + 0.35
                    ax.text(x, label_y, c.name, fontsize=7, color="#e5e7eb", ha="center", zorder=4)

            max_y = max([c.output_at_x(spinup_x) for c in cat_cards] + [c.input_qty for c in cat_cards] + [5])
            ax.set_xlim(-0.5, 6.8)
            ax.set_ylim(-0.8, max_y + 1.5)

    fig.tight_layout(rect=[0, 0.03, 1, 0.95])
    all_path = output_dir / "weight_tradeoffs_all.png"
    fig.savefig(all_path, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    generated_files.append(str(all_path))

    return generated_files


# ==============================================================================
# Standalone Interactive HTML Dashboard
# ==============================================================================

def generate_html_dashboard(cards: List[CardTradeoffData]) -> str:
    """Generates a complete, self-contained interactive HTML dashboard."""
    icons_b64 = load_icon_base64()

    # Serialize cards to JSON for client-side interactivity
    cards_json_list = []
    for c in cards:
        cards_json_list.append({
            "name": c.name,
            "card_type": c.card_type,
            "category": c.category,
            "weight": c.weight,
            "cost": c.cost,
            "durability": c.durability,
            "absorption": c.absorption,
            "req_raw": c.requirements_raw,
            "out_raw": c.outputs_raw,
            "in_res": c.input_resource,
            "in_qty": c.input_qty,
            "out_res": c.output_resource,
            "out_base": c.output_qty_base,
            "spin_mult": c.spinup_multiplier,
            "spin_quad": c.spinup_quadratic,
            "max_spin": c.max_spinup,
            "is_passthrough": c.is_passthrough,
            "keywords": c.keywords,
            "text": c.text,
            "picture": c.picture,
        })
    cards_json_str = json.dumps(cards_json_list)
    icons_json_str = json.dumps(icons_b64)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Robot Battles - Weight Tradeoff Analysis</title>
  <style>
    :root {{
      --bg-base: #0b0f17;
      --bg-surface: #111827;
      --bg-card: #1f2937;
      --bg-hover: #374151;
      --border: #374151;
      --border-focus: #60a5fa;
      --text-main: #f9fafb;
      --text-muted: #9ca3af;
      --primary: #3b82f6;
      --energy: #f59e0b;
      --spin: #3b82f6;
      --pressure: #8b5cf6;
      --drive: #10b981;
      --damage: #ef4444;
      --durability: #ef4444;
      --absorption: #06b6d4;
      --weight: #94a3b8;
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg-base);
      color: var(--text-main);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.5;
      padding: 24px;
    }}

    .container {{
      max-width: 1400px;
      margin: 0 auto;
    }}

    header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--border);
      margin-bottom: 24px;
      flex-wrap: wrap;
      gap: 16px;
    }}

    h1 {{
      font-size: 26px;
      font-weight: 800;
      letter-spacing: -0.02em;
      display: flex;
      align-items: center;
      gap: 12px;
    }}

    .subtitle {{
      color: var(--text-muted);
      font-size: 14px;
      margin-top: 4px;
    }}

    /* Global Controls Toolbar */
    .toolbar {{
      background: var(--bg-surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px 20px;
      margin-bottom: 24px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 20px;
    }}

    .control-group {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}

    .control-group label {{
      font-size: 13px;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}

    .slider-container {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}

    input[type="range"] {{
      accent-color: var(--primary);
      width: 140px;
      cursor: pointer;
    }}

    .badge-val {{
      background: var(--bg-card);
      border: 1px solid var(--border);
      padding: 2px 10px;
      border-radius: 14px;
      font-size: 13px;
      font-weight: 700;
      color: var(--primary);
      min-width: 32px;
      text-align: center;
    }}

    .btn-group {{
      display: flex;
      background: var(--bg-card);
      border-radius: 8px;
      padding: 3px;
      border: 1px solid var(--border);
    }}

    .btn-toggle {{
      background: transparent;
      border: none;
      color: var(--text-muted);
      padding: 6px 14px;
      font-size: 13px;
      font-weight: 600;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.15s ease;
    }}

    .btn-toggle.active {{
      background: var(--primary);
      color: #fff;
    }}

    /* Category Navigation Tabs */
    .tabs-nav {{
      display: flex;
      gap: 8px;
      margin-bottom: 20px;
      overflow-x: auto;
      padding-bottom: 4px;
    }}

    .tab-btn {{
      background: var(--bg-surface);
      border: 1px solid var(--border);
      color: var(--text-muted);
      padding: 10px 18px;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      white-space: nowrap;
      transition: all 0.15s ease;
    }}

    .tab-btn:hover {{
      background: var(--bg-hover);
      color: var(--text-main);
    }}

    .tab-btn.active {{
      background: var(--primary);
      border-color: var(--primary);
      color: #fff;
    }}

    /* View Content Panels */
    .view-card {{
      background: var(--bg-surface);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 24px;
      margin-bottom: 24px;
    }}

    .view-card-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      flex-wrap: wrap;
      gap: 12px;
    }}

    .view-card-header h2 {{
      font-size: 19px;
      font-weight: 700;
    }}

    .view-description {{
      color: var(--text-muted);
      font-size: 13.5px;
      margin-top: 4px;
    }}

    /* SVG Plot Container */
    .svg-container {{
      width: 100%;
      overflow-x: auto;
      background: #0d131f;
      border-radius: 10px;
      border: 1px solid #1f293d;
      padding: 16px;
    }}

    svg text {{
      font-family: inherit;
    }}

    .chart-bar {{
      transition: opacity 0.2s, stroke-width 0.2s;
      cursor: pointer;
    }}
    .chart-bar:hover {{
      opacity: 0.85;
      stroke-width: 6 !important;
    }}

    /* Card Details Drawer / Comparison Table */
    .table-container {{
      width: 100%;
      overflow-x: auto;
      margin-top: 16px;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13.5px;
    }}

    th {{
      background: var(--bg-card);
      color: var(--text-muted);
      text-transform: uppercase;
      font-size: 11.5px;
      letter-spacing: 0.05em;
      padding: 12px 14px;
      text-align: left;
      border-bottom: 1px solid var(--border);
      cursor: pointer;
      user-select: none;
    }}
    th:hover {{
      color: var(--text-main);
    }}

    td {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--border);
      color: var(--text-main);
    }}

    tr:hover td {{
      background: var(--bg-hover);
    }}

    .res-badge {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 6px;
      font-size: 12.5px;
    }}

    .badge-e {{ background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); }}
    .badge-s {{ background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.4); }}
    .badge-p {{ background: rgba(139, 92, 246, 0.2); color: #a78bfa; border: 1px solid rgba(139, 92, 246, 0.4); }}
    .badge-d {{ background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); }}
    .badge-w {{ background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); }}
    .badge-none {{ background: rgba(148, 163, 184, 0.15); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.3); }}

    .icon-img {{
      width: 18px;
      height: 18px;
      vertical-align: middle;
      object-fit: contain;
    }}

    /* Tooltip */
    #tooltip {{
      position: absolute;
      display: none;
      background: #1e293b;
      border: 1px solid #475569;
      border-radius: 8px;
      padding: 10px 14px;
      font-size: 12.5px;
      color: #f8fafc;
      pointer-events: none;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.6);
      z-index: 1000;
      max-width: 280px;
    }}

    .tradeoff-indicator {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-weight: 600;
    }}
  </style>
</head>
<body>

<div class="container">
  <header>
    <div>
      <h1>⚖️ Robot Battles: Weight Tradeoff Analysis</h1>
      <div class="subtitle">Component & Weapon Weight Tradeoff Analysis across Energy, Spin, Pressure, Drive, and Damage</div>
    </div>
    <div style="font-size: 13px; color: var(--text-muted); text-align: right;">
      <span>Set 1 Definitive Catalog</span><br>
      <span id="active-count-label">35 Components & Weapons</span>
    </div>
  </header>

  <!-- Global Toolbar Controls -->
  <div class="toolbar">
    <!-- Category Tabs Navigation -->
    <div class="control-group">
      <label>Component Type</label>
      <div class="tabs-nav" id="categoryTabs" style="margin-bottom: 0;"></div>
    </div>

    <!-- View Mode Selector -->
    <div class="control-group">
      <label>Plot View</label>
      <div class="btn-group">
        <button class="btn-toggle active" id="btnViewCoord" onclick="setViewMode('coord')">📊 Weight vs Qty</button>
        <button class="btn-toggle" id="btnViewDumbbell" onclick="setViewMode('dumbbell')">↔️ Range Bars</button>
        <button class="btn-toggle" id="btnViewDivergent" onclick="setViewMode('divergent')">🔀 Bidirectional</button>
        <button class="btn-toggle" id="btnViewTable" onclick="setViewMode('table')">📋 Tradeoff Table</button>
      </div>
    </div>

    <!-- Dynamic Spin-Up Slider -->
    <div class="control-group" id="spinupControlGroup">
      <label>Spin-up Counters (X)</label>
      <div class="slider-container">
        <input type="range" id="spinupSlider" min="0" max="4" value="0" step="1" oninput="updateSpinup(this.value)">
        <span class="badge-val" id="spinupVal">X = 0</span>
      </div>
    </div>
  </div>

  <!-- Main View Card -->
  <div class="view-card">
    <div class="view-card-header">
      <div>
        <h2 id="currentCategoryTitle">All Components Overview</h2>
        <div class="view-description" id="currentCategoryDesc">
          Plotted weight vs input and output resources. Each conversion is displayed as a bar with distinct input and output symbols on either end.
        </div>
      </div>
      <div id="chartLegend" style="display: flex; gap: 14px; align-items: center; font-size: 12.5px;"></div>
    </div>

    <!-- Chart Render Area -->
    <div id="chartArea" class="svg-container">
      <svg id="mainSvg" width="100%" height="520"></svg>
    </div>

    <!-- Table Render Area (when table view mode is active) -->
    <div id="tableArea" class="table-container" style="display: none;">
      <table id="tradeoffTable">
        <thead>
          <tr>
            <th onclick="sortTable('name')">Name ⇕</th>
            <th onclick="sortTable('category')">Type ⇕</th>
            <th onclick="sortTable('weight')">Weight ⇕</th>
            <th onclick="sortTable('cost')">Cost ⇕</th>
            <th onclick="sortTable('input_qty')">Input ⇕</th>
            <th onclick="sortTable('output_qty')">Output ⇕</th>
            <th onclick="sortTable('eff')">Efficiency (Out/In) ⇕</th>
            <th onclick="sortTable('wt_eff')">Weight Eff (Out/Wt) ⇕</th>
            <th onclick="sortTable('net_eff')">Net / Wt ⇕</th>
            <th onclick="sortTable('durability')">Durability / Abs ⇕</th>
          </tr>
        </thead>
        <tbody id="tableBody"></tbody>
      </table>
    </div>
  </div>
</div>

<div id="tooltip"></div>

<script>
  const CARDS = {cards_json_str};
  const ICONS = {icons_json_str};

  const CATEGORIES = [
    {{ id: "All", label: "🌟 All Overview", desc: "Comparative overview of all cards and tradeoffs" }},
    {{ id: "Motors", label: "⚙️ Motors (E → S)", desc: "Motors convert Energy (E) into Spin (S) across weight tiers" }},
    {{ id: "Servos", label: "🦾 Servos (E → P)", desc: "Servos convert Energy (E) into Pressure (P) across weight tiers" }},
    {{ id: "Wheels", label: "🛞 Wheels (S → D)", desc: "Wheels convert Spin (S) into Drive (D) propulsion" }},
    {{ id: "Weapons", label: "⚔️ Weapons (S/P → W)", desc: "Weapons convert Spin or Pressure into Damage (W) and Throws" }},
    {{ id: "Batteries", label: "🔋 Batteries (0 → E)", desc: "Power sources providing Energy capacity per weight unit" }},
    {{ id: "Transmission", label: "🔌 Transmission & Wiring", desc: "Wiring harnesses, power switch, timing pulley, and ESCs" }},
    {{ id: "Armor", label: "🛡️ Armor & Defense", desc: "Armor plates, wedges, forks, horns, and self-righting mechanisms" }}
  ];

  const RESOURCE_COLORS = {{
    "E": "#f59e0b",
    "S": "#3b82f6",
    "P": "#8b5cf6",
    "D": "#10b981",
    "M": "#10b981",
    "W": "#ef4444",
    "None": "#64748b"
  }};

  const RESOURCE_ICONS = {{
    "E": "energy.png",
    "S": "spin.png",
    "P": "pressure.png",
    "D": "drive.png",
    "M": "drive.png",
    "W": "damage.png",
    "None": "weight_plain.png"
  }};

  let currentCategory = "All";
  let currentViewMode = "coord"; // 'coord', 'dumbbell', 'divergent', 'table'
  let currentSpinup = 0;
  let sortField = "weight";
  let sortAsc = true;

  function init() {{
    renderCategoryTabs();
    renderLegend();
    renderActiveView();
  }}

  function renderCategoryTabs() {{
    const nav = document.getElementById("categoryTabs");
    nav.innerHTML = "";
    CATEGORIES.forEach(cat => {{
      const btn = document.createElement("button");
      btn.className = "tab-btn" + (cat.id === currentCategory ? " active" : "");
      btn.innerText = cat.label;
      btn.onclick = () => selectCategory(cat.id);
      nav.appendChild(btn);
    }});
  }}

  function selectCategory(catId) {{
    currentCategory = catId;
    renderCategoryTabs();
    const catObj = CATEGORIES.find(c => c.id === catId);
    document.getElementById("currentCategoryTitle").innerText = catObj.label;
    document.getElementById("currentCategoryDesc").innerText = catObj.desc;
    renderActiveView();
  }}

  function setViewMode(mode) {{
    currentViewMode = mode;
    ["btnViewCoord", "btnViewDumbbell", "btnViewDivergent", "btnViewTable"].forEach(id => {{
      document.getElementById(id).classList.remove("active");
    }});
    if (mode === "coord") document.getElementById("btnViewCoord").classList.add("active");
    if (mode === "dumbbell") document.getElementById("btnViewDumbbell").classList.add("active");
    if (mode === "divergent") document.getElementById("btnViewDivergent").classList.add("active");
    if (mode === "table") document.getElementById("btnViewTable").classList.add("active");

    const chartArea = document.getElementById("chartArea");
    const tableArea = document.getElementById("tableArea");
    if (mode === "table") {{
      chartArea.style.display = "none";
      tableArea.style.display = "block";
    }} else {{
      chartArea.style.display = "block";
      tableArea.style.display = "none";
    }}
    renderActiveView();
  }}

  function updateSpinup(val) {{
    currentSpinup = parseInt(val, 10);
    document.getElementById("spinupVal").innerText = "X = " + currentSpinup;
    renderActiveView();
  }}

  function getFilteredCards() {{
    if (currentCategory === "All") return CARDS;
    return CARDS.filter(c => c.category === currentCategory);
  }}

  function getCardOutput(card, x) {{
    if (card.max_spin === 0 || card.spin_mult === 0) {{
      return card.out_base;
    }}
    const effX = Math.min(x, card.max_spin);
    if (card.spin_quad) {{
      return card.out_base + (effX * effX) * card.spin_mult;
    }}
    return card.out_base + effX * card.spin_mult;
  }}

  function renderLegend() {{
    const legend = document.getElementById("chartLegend");
    legend.innerHTML = `
      <span class="tradeoff-indicator"><img class="icon-img" src="${{ICONS['energy.png']}}"> Energy (E)</span>
      <span class="tradeoff-indicator"><img class="icon-img" src="${{ICONS['spin.png']}}"> Spin (S)</span>
      <span class="tradeoff-indicator"><img class="icon-img" src="${{ICONS['pressure.png']}}"> Pressure (P)</span>
      <span class="tradeoff-indicator"><img class="icon-img" src="${{ICONS['drive.png']}}"> Drive (D)</span>
      <span class="tradeoff-indicator"><img class="icon-img" src="${{ICONS['damage.png']}}"> Damage (W)</span>
      <span class="tradeoff-indicator"><img class="icon-img" src="${{ICONS['weight.png']}}"> Weight</span>
    `;
  }}

  function renderActiveView() {{
    const cards = getFilteredCards();
    document.getElementById("active-count-label").innerText = cards.length + " Components & Weapons";

    if (currentViewMode === "coord") {{
      renderCoordinatePlot(cards);
    }} else if (currentViewMode === "dumbbell") {{
      renderDumbbellPlot(cards);
    }} else if (currentViewMode === "divergent") {{
      renderDivergentPlot(cards);
    }} else if (currentViewMode === "table") {{
      renderTable(cards);
    }}
  }}

  // =========================================================================
  // View 1: Weight vs Quantity Coordinate Plot (Bars with symbols on each end)
  // =========================================================================
  function renderCoordinatePlot(cards) {{
    const svg = document.getElementById("mainSvg");
    svg.innerHTML = "";
    const w = svg.clientWidth || 1100;
    const h = 520;
    svg.setAttribute("viewBox", `0 0 ${{w}} ${{h}}`);

    const margin = {{ top: 40, right: 40, bottom: 60, left: 70 }};
    const plotW = w - margin.left - margin.right;
    const plotH = h - margin.top - margin.bottom;

    const maxWeight = 6;
    let maxVal = 8;
    cards.forEach(c => {{
      const outVal = getCardOutput(c, currentSpinup);
      if (outVal > maxVal) maxVal = outVal;
      if (c.in_qty > maxVal) maxVal = c.in_qty;
      if (c.category === "Armor" && c.durability > maxVal) maxVal = c.durability;
    }});
    maxVal = Math.ceil(maxVal + 1);

    const xScale = weight => margin.left + (weight / maxWeight) * plotW;
    const yScale = val => margin.top + plotH - (val / maxVal) * plotH;

    // Draw Gridlines & Axes
    let gridHtml = "";
    for (let wt = 0; wt <= maxWeight; wt++) {{
      const x = xScale(wt);
      gridHtml += `<line x1="${{x}}" y1="${{margin.top}}" x2="${{x}}" y2="${{margin.top + plotH}}" stroke="#1f293d" stroke-width="1.5" stroke-dasharray="4,4"/>`;
      gridHtml += `<text x="${{x}}" y="${{margin.top + plotH + 25}}" fill="#9ca3af" font-size="13" font-weight="700" text-anchor="middle">Weight ${{wt}}</text>`;
    }}
    for (let v = 0; v <= maxVal; v += (maxVal > 12 ? 2 : 1)) {{
      const y = yScale(v);
      gridHtml += `<line x1="${{margin.left}}" y1="${{y}}" x2="${{margin.left + plotW}}" y2="${{y}}" stroke="#1f293d" stroke-width="1"/>`;
      gridHtml += `<text x="${{margin.left - 12}}" y="${{y + 4}}" fill="#9ca3af" font-size="12" text-anchor="end">${{v}}</text>`;
    }}
    svg.innerHTML += gridHtml;

    // Axis Titles
    svg.innerHTML += `<text x="${{margin.left + plotW / 2}}" y="${{h - 15}}" fill="#9ca3af" font-size="13" font-weight="700" text-anchor="middle">Weight Budget (Points)</text>`;
    svg.innerHTML += `<text x="${{20}}" y="${{margin.top + plotH / 2}}" fill="#9ca3af" font-size="13" font-weight="700" text-anchor="middle" transform="rotate(-90 20 ${{margin.top + plotH / 2}})">Resource Quantity (Input / Output)</text>`;

    // Group cards by weight to offset them horizontally
    const byWeight = {{}};
    cards.forEach(c => {{
      if (!byWeight[c.weight]) byWeight[c.weight] = [];
      byWeight[c.weight].push(c);
    }});

    const iconSize = 22;

    Object.keys(byWeight).forEach(wtStr => {{
      const group = byWeight[wtStr];
      const n = group.length;
      group.forEach((c, idx) => {{
        const offset = n === 1 ? 0 : (idx - (n - 1) / 2) * (Math.min(36, plotW / (maxWeight * 4.5)));
        const cx = xScale(c.weight) + offset;

        let yIn, yOut, inIconName, outIconName, barColor;
        if (c.category === "Armor") {{
          yIn = c.absorption;
          yOut = c.durability;
          inIconName = "absorption.png";
          outIconName = "durability.png";
          barColor = "#06b6d4";
        }} else if (c.category === "Batteries") {{
          yIn = 0;
          yOut = c.out_base;
          inIconName = "weight_plain.png";
          outIconName = "energy.png";
          barColor = "#f59e0b";
        }} else {{
          yIn = c.in_qty;
          yOut = getCardOutput(c, currentSpinup);
          inIconName = RESOURCE_ICONS[c.in_res] || "weight_plain.png";
          outIconName = RESOURCE_ICONS[c.out_res] || "damage.png";
          barColor = RESOURCE_COLORS[c.out_res] || "#3b82f6";
        }}

        const pyIn = yScale(yIn);
        const pyOut = yScale(yOut);

        // Vertical Bar connecting Input to Output
        const barElem = document.createElementNS("http://www.w3.org/2000/svg", "line");
        barElem.setAttribute("x1", cx);
        barElem.setAttribute("y1", pyIn);
        barElem.setAttribute("x2", cx);
        barElem.setAttribute("y2", pyOut);
        barElem.setAttribute("stroke", barColor);
        barElem.setAttribute("stroke-width", "5");
        barElem.setAttribute("stroke-linecap", "round");
        barElem.setAttribute("class", "chart-bar");
        barElem.onmouseenter = e => showTooltip(e, c);
        barElem.onmouseleave = hideTooltip;
        svg.appendChild(barElem);

        // Input Symbol at yIn end
        if (ICONS[inIconName]) {{
          const imgIn = document.createElementNS("http://www.w3.org/2000/svg", "image");
          imgIn.setAttribute("href", ICONS[inIconName]);
          imgIn.setAttribute("x", cx - iconSize / 2);
          imgIn.setAttribute("y", pyIn - iconSize / 2);
          imgIn.setAttribute("width", iconSize);
          imgIn.setAttribute("height", iconSize);
          imgIn.style.cursor = "pointer";
          imgIn.onmouseenter = e => showTooltip(e, c);
          imgIn.onmouseleave = hideTooltip;
          svg.appendChild(imgIn);
        }}

        // Output Symbol at yOut end
        if (ICONS[outIconName]) {{
          const imgOut = document.createElementNS("http://www.w3.org/2000/svg", "image");
          imgOut.setAttribute("href", ICONS[outIconName]);
          imgOut.setAttribute("x", cx - iconSize / 2);
          imgOut.setAttribute("y", pyOut - iconSize / 2);
          imgOut.setAttribute("width", iconSize);
          imgOut.setAttribute("height", iconSize);
          imgOut.style.cursor = "pointer";
          imgOut.onmouseenter = e => showTooltip(e, c);
          imgOut.onmouseleave = hideTooltip;
          svg.appendChild(imgOut);
        }}

        // Label above the bar
        const topY = Math.min(pyIn, pyOut) - 16;
        const textElem = document.createElementNS("http://www.w3.org/2000/svg", "text");
        textElem.setAttribute("x", cx);
        textElem.setAttribute("y", topY);
        textElem.setAttribute("fill", "#f3f4f6");
        textElem.setAttribute("font-size", "10.5");
        textElem.setAttribute("font-weight", "600");
        textElem.setAttribute("text-anchor", "middle");
        textElem.textContent = c.name;
        svg.appendChild(textElem);
      }});
    }});
  }}

  // =========================================================================
  // View 2: Horizontal Dumbbell / Range Chart (Input symbol on left, Output on right)
  // =========================================================================
  function renderDumbbellPlot(cards) {{
    const svg = document.getElementById("mainSvg");
    svg.innerHTML = "";
    const sorted = [...cards].sort((a, b) => a.weight - b.weight || a.name.localeCompare(b.name));
    const rowH = 34;
    const margin = {{ top: 30, right: 40, bottom: 40, left: 210 }};
    const w = svg.clientWidth || 1100;
    const h = Math.max(500, margin.top + margin.bottom + sorted.length * rowH);
    svg.setAttribute("viewBox", `0 0 ${{w}} ${{h}}`);
    svg.style.height = h + "px";

    const plotW = w - margin.left - margin.right;
    let maxVal = 10;
    sorted.forEach(c => {{
      const outVal = getCardOutput(c, currentSpinup);
      if (outVal > maxVal) maxVal = outVal;
      if (c.in_qty > maxVal) maxVal = c.in_qty;
      if (c.category === "Armor" && c.durability > maxVal) maxVal = c.durability;
    }});
    maxVal = Math.ceil(maxVal + 1);

    const xScale = val => margin.left + (val / maxVal) * plotW;

    // X-axis gridlines
    for (let v = 0; v <= maxVal; v += (maxVal > 12 ? 2 : 1)) {{
      const x = xScale(v);
      svg.innerHTML += `<line x1="${{x}}" y1="${{margin.top}}" x2="${{x}}" y2="${{h - margin.bottom}}" stroke="#1f293d" stroke-width="1"/>`;
      svg.innerHTML += `<text x="${{x}}" y="${{h - margin.bottom + 20}}" fill="#9ca3af" font-size="11.5" text-anchor="middle">${{v}}</text>`;
    }}

    const iconSize = 20;

    sorted.forEach((c, idx) => {{
      const cy = margin.top + idx * rowH + rowH / 2;

      // Card Name & Weight badge
      svg.innerHTML += `<text x="${{margin.left - 15}}" y="${{cy + 4}}" fill="#f3f4f6" font-size="12" font-weight="600" text-anchor="end">${{c.name}} [Wt:${{c.weight}}]</text>`;

      let vIn, vOut, inIcon, outIcon, barColor;
      if (c.category === "Armor") {{
        vIn = c.absorption;
        vOut = c.durability;
        inIcon = "absorption.png";
        outIcon = "durability.png";
        barColor = "#06b6d4";
      }} else if (c.category === "Batteries") {{
        vIn = 0;
        vOut = c.out_base;
        inIcon = "weight_plain.png";
        outIcon = "energy.png";
        barColor = "#f59e0b";
      }} else {{
        vIn = c.in_qty;
        vOut = getCardOutput(c, currentSpinup);
        inIcon = RESOURCE_ICONS[c.in_res] || "weight_plain.png";
        outIcon = RESOURCE_ICONS[c.out_res] || "damage.png";
        barColor = RESOURCE_COLORS[c.out_res] || "#3b82f6";
      }}

      const pxIn = xScale(vIn);
      const pxOut = xScale(vOut);

      // Connecting Bar
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", pxIn);
      line.setAttribute("y1", cy);
      line.setAttribute("x2", pxOut);
      line.setAttribute("y2", cy);
      line.setAttribute("stroke", barColor);
      line.setAttribute("stroke-width", "5");
      line.setAttribute("stroke-linecap", "round");
      line.setAttribute("class", "chart-bar");
      line.onmouseenter = e => showTooltip(e, c);
      line.onmouseleave = hideTooltip;
      svg.appendChild(line);

      // Input symbol on left/origin
      if (ICONS[inIcon]) {{
        const imgIn = document.createElementNS("http://www.w3.org/2000/svg", "image");
        imgIn.setAttribute("href", ICONS[inIcon]);
        imgIn.setAttribute("x", pxIn - iconSize / 2);
        imgIn.setAttribute("y", cy - iconSize / 2);
        imgIn.setAttribute("width", iconSize);
        imgIn.setAttribute("height", iconSize);
        imgIn.onmouseenter = e => showTooltip(e, c);
        imgIn.onmouseleave = hideTooltip;
        svg.appendChild(imgIn);
      }}

      // Output symbol on right/target
      if (ICONS[outIcon]) {{
        const imgOut = document.createElementNS("http://www.w3.org/2000/svg", "image");
        imgOut.setAttribute("href", ICONS[outIcon]);
        imgOut.setAttribute("x", pxOut - iconSize / 2);
        imgOut.setAttribute("y", cy - iconSize / 2);
        imgOut.setAttribute("width", iconSize);
        imgOut.setAttribute("height", iconSize);
        imgOut.onmouseenter = e => showTooltip(e, c);
        imgOut.onmouseleave = hideTooltip;
        svg.appendChild(imgOut);
      }}
    }});
  }}

  // =========================================================================
  // View 3: Bidirectional (Divergent) Bar Chart (0 in center, In on Left, Out on Right)
  // =========================================================================
  function renderDivergentPlot(cards) {{
    const svg = document.getElementById("mainSvg");
    svg.innerHTML = "";
    const sorted = [...cards].sort((a, b) => a.weight - b.weight || a.name.localeCompare(b.name));
    const rowH = 34;
    const margin = {{ top: 40, right: 60, bottom: 40, left: 190 }};
    const w = svg.clientWidth || 1100;
    const h = Math.max(500, margin.top + margin.bottom + sorted.length * rowH);
    svg.setAttribute("viewBox", `0 0 ${{w}} ${{h}}`);
    svg.style.height = h + "px";

    const plotW = w - margin.left - margin.right;
    const centerX = margin.left + plotW / 2;
    const halfW = plotW / 2;

    let maxSpan = 6;
    sorted.forEach(c => {{
      const outVal = getCardOutput(c, currentSpinup);
      if (outVal > maxSpan) maxSpan = outVal;
      if (c.in_qty > maxSpan) maxSpan = c.in_qty;
    }});
    maxSpan = Math.ceil(maxSpan + 1);

    // Center divider
    svg.innerHTML += `<line x1="${{centerX}}" y1="${{margin.top}}" x2="${{centerX}}" y2="${{h - margin.bottom}}" stroke="#4b5563" stroke-width="2"/>`;
    svg.innerHTML += `<text x="${{centerX - 20}}" y="${{margin.top - 12}}" fill="#f59e0b" font-size="12" font-weight="700" text-anchor="end">← INPUT REQUIRED</text>`;
    svg.innerHTML += `<text x="${{centerX + 20}}" y="${{margin.top - 12}}" fill="#3b82f6" font-size="12" font-weight="700" text-anchor="start">OUTPUT PRODUCED →</text>`;

    const iconSize = 20;

    sorted.forEach((c, idx) => {{
      const cy = margin.top + idx * rowH + rowH / 2;
      const vIn = c.category === "Armor" ? c.absorption : c.in_qty;
      const vOut = c.category === "Armor" ? c.durability : getCardOutput(c, currentSpinup);

      const inIcon = c.category === "Armor" ? "absorption.png" : (RESOURCE_ICONS[c.in_res] || "weight_plain.png");
      const outIcon = c.category === "Armor" ? "durability.png" : (RESOURCE_ICONS[c.out_res] || "damage.png");

      const inLen = (vIn / maxSpan) * halfW;
      const outLen = (vOut / maxSpan) * halfW;

      // Card label on the far left
      svg.innerHTML += `<text x="${{margin.left - 15}}" y="${{cy + 4}}" fill="#f3f4f6" font-size="11.5" font-weight="600" text-anchor="end">${{c.name}} (${{c.weight}}T)</text>`;

      // Input Bar (left from center)
      if (vIn > 0) {{
        const inLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
        inLine.setAttribute("x1", centerX);
        inLine.setAttribute("y1", cy);
        inLine.setAttribute("x2", centerX - inLen);
        inLine.setAttribute("y2", cy);
        inLine.setAttribute("stroke", "#f59e0b");
        inLine.setAttribute("stroke-width", "6");
        inLine.setAttribute("stroke-linecap", "round");
        inLine.setAttribute("class", "chart-bar");
        inLine.onmouseenter = e => showTooltip(e, c);
        inLine.onmouseleave = hideTooltip;
        svg.appendChild(inLine);

        // Input Symbol at end of left bar
        if (ICONS[inIcon]) {{
          const imgIn = document.createElementNS("http://www.w3.org/2000/svg", "image");
          imgIn.setAttribute("href", ICONS[inIcon]);
          imgIn.setAttribute("x", centerX - inLen - iconSize - 2);
          imgIn.setAttribute("y", cy - iconSize / 2);
          imgIn.setAttribute("width", iconSize);
          imgIn.setAttribute("height", iconSize);
          svg.appendChild(imgIn);
        }}
      }}

      // Output Bar (right from center)
      if (vOut > 0) {{
        const outLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
        outLine.setAttribute("x1", centerX);
        outLine.setAttribute("y1", cy);
        outLine.setAttribute("x2", centerX + outLen);
        outLine.setAttribute("y2", cy);
        outLine.setAttribute("stroke", RESOURCE_COLORS[c.out_res] || "#3b82f6");
        outLine.setAttribute("stroke-width", "6");
        outLine.setAttribute("stroke-linecap", "round");
        outLine.setAttribute("class", "chart-bar");
        outLine.onmouseenter = e => showTooltip(e, c);
        outLine.onmouseleave = hideTooltip;
        svg.appendChild(outLine);

        // Output Symbol at end of right bar
        if (ICONS[outIcon]) {{
          const imgOut = document.createElementNS("http://www.w3.org/2000/svg", "image");
          imgOut.setAttribute("href", ICONS[outIcon]);
          imgOut.setAttribute("x", centerX + outLen + 4);
          imgOut.setAttribute("y", cy - iconSize / 2);
          imgOut.setAttribute("width", iconSize);
          imgOut.setAttribute("height", iconSize);
          svg.appendChild(imgOut);
        }}
      }}
    }});
  }}

  // =========================================================================
  // View 4: Tradeoff Data Table
  // =========================================================================
  function sortTable(field) {{
    if (sortField === field) {{
      sortAsc = !sortAsc;
    }} else {{
      sortField = field;
      sortAsc = true;
    }}
    renderTable(getFilteredCards());
  }}

  function renderTable(cards) {{
    const tbody = document.getElementById("tableBody");
    tbody.innerHTML = "";

    const sorted = [...cards].sort((a, b) => {{
      let valA = a[sortField];
      let valB = b[sortField];
      if (sortField === "output_qty") {{
        valA = getCardOutput(a, currentSpinup);
        valB = getCardOutput(b, currentSpinup);
      }} else if (sortField === "eff") {{
        const outA = getCardOutput(a, currentSpinup);
        const outB = getCardOutput(b, currentSpinup);
        valA = a.in_qty > 0 ? outA / a.in_qty : 0;
        valB = b.in_qty > 0 ? outB / b.in_qty : 0;
      }} else if (sortField === "wt_eff") {{
        valA = a.weight > 0 ? getCardOutput(a, currentSpinup) / a.weight : 0;
        valB = b.weight > 0 ? getCardOutput(b, currentSpinup) / b.weight : 0;
      }} else if (sortField === "net_eff") {{
        valA = a.weight > 0 ? (getCardOutput(a, currentSpinup) - a.in_qty) / a.weight : 0;
        valB = b.weight > 0 ? (getCardOutput(b, currentSpinup) - b.in_qty) / b.weight : 0;
      }}

      if (typeof valA === "string") return sortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
      return sortAsc ? valA - valB : valB - valA;
    }});

    sorted.forEach(c => {{
      const tr = document.createElement("tr");
      const outVal = getCardOutput(c, currentSpinup);
      const eff = c.in_qty > 0 ? (outVal / c.in_qty).toFixed(2) : "-";
      const wtEff = c.weight > 0 ? (outVal / c.weight).toFixed(2) : "-";
      const netEff = c.weight > 0 ? ((outVal - c.in_qty) / c.weight).toFixed(2) : "-";

      const inBadgeClass = "badge-" + (c.in_res.toLowerCase());
      const outBadgeClass = "badge-" + (c.out_res.toLowerCase());

      tr.innerHTML = `
        <td style="font-weight: 700;">${{c.name}}</td>
        <td><span style="color: var(--text-muted);">${{c.category}}</span></td>
        <td><strong>${{c.weight}}</strong></td>
        <td>$${{c.cost}}</td>
        <td>
          <span class="res-badge ${{inBadgeClass}}">
            <img class="icon-img" src="${{ICONS[RESOURCE_ICONS[c.in_res] || 'weight_plain.png']}}">
            ${{c.in_qty > 0 ? c.in_qty + ' ' + c.in_res : (c.category === 'Armor' ? '-' : 'None')}}
          </span>
        </td>
        <td>
          <span class="res-badge ${{outBadgeClass}}">
            <img class="icon-img" src="${{ICONS[RESOURCE_ICONS[c.out_res] || 'damage.png']}}">
            ${{outVal > 0 ? outVal + ' ' + c.out_res : '-'}}
          </span>
        </td>
        <td style="font-weight: 600;">${{eff}}</td>
        <td style="font-weight: 600; color: #34d399;">${{wtEff}}</td>
        <td style="font-weight: 600; color: ${{parseFloat(netEff) >= 0 ? '#60a5fa' : '#f87171'}};">${{netEff}}</td>
        <td>${{c.durability}} / ${{c.absorption}}</td>
      `;
      tbody.appendChild(tr);
    }});
  }}

  // Tooltip
  const tooltip = document.getElementById("tooltip");
  function showTooltip(e, card) {{
    const outVal = getCardOutput(card, currentSpinup);
    const eff = card.in_qty > 0 ? (outVal / card.in_qty).toFixed(2) : "N/A";
    const wtEff = card.weight > 0 ? (outVal / card.weight).toFixed(2) : "N/A";

    tooltip.innerHTML = `
      <div style="font-weight: 800; font-size: 14px; margin-bottom: 4px;">${{card.name}}</div>
      <div style="color: #94a3b8; font-size: 12px; margin-bottom: 8px;">${{card.category}} • Weight: ${{card.weight}} • Cost: $${{card.cost}}</div>
      <div style="display: flex; gap: 8px; margin-bottom: 6px;">
        <span class="res-badge badge-${{card.in_res.toLowerCase()}}">In: ${{card.in_qty}} ${{card.in_res}}</span>
        <span class="res-badge badge-${{card.out_res.toLowerCase()}}">Out: ${{outVal}} ${{card.out_res}}</span>
      </div>
      <div style="font-size: 11.5px; color: #cbd5e1; border-top: 1px solid #334155; padding-top: 6px; margin-top: 6px;">
        <div>Output / Weight: <strong>${{wtEff}}</strong></div>
        <div>Conversion Ratio: <strong>${{eff}}</strong></div>
        <div>Durability: ${{card.durability}} | Absorption: ${{card.absorption}}</div>
        ${{card.keywords ? `<div style="margin-top: 4px; color: #60a5fa;">${{card.keywords}}</div>` : ''}}
      </div>
    `;
    tooltip.style.display = "block";
    tooltip.style.left = (e.pageX + 15) + "px";
    tooltip.style.top = (e.pageY + 10) + "px";
  }}

  function hideTooltip() {{
    tooltip.style.display = "none";
  }}

  window.addEventListener("DOMContentLoaded", init);
</script>
</body>
</html>
"""


# ==============================================================================
# CLI and Server Entrypoints
# ==============================================================================

def run_server(port: int = 8002, html_path: Optional[Path] = None):
    """Runs a simple local HTTP server serving the output directory and report."""
    output_dir = OUTPUT_DIR.resolve()
    os.chdir(str(output_dir))

    class Handler(http.server.SimpleHTTPRequestHandler):
        def end_headers(self):
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            super().end_headers()

    with socketserver.TCPServer(("", port), Handler) as httpd:
        print(f"Serving Weight Tradeoff Analysis on http://127.0.0.1:{port}/weight_tradeoffs.html")
        print("Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")


def main():
    parser = argparse.ArgumentParser(
        description="Weight Tradeoff Analysis and Plotting Tool for Robot Battles"
    )
    parser.add_argument(
        "--type",
        "-t",
        choices=["all"] + [c.lower() for c in CATEGORIES],
        default="all",
        help="Component category to analyze (default: all)",
    )
    parser.add_argument(
        "--spinup-x",
        "-x",
        type=int,
        default=0,
        help="Spin-up counter X to evaluate for static plots (default: 0)",
    )
    parser.add_argument(
        "--html",
        type=str,
        default=str(OUTPUT_DIR / "weight_tradeoffs.html"),
        help="Output HTML dashboard file path",
    )
    parser.add_argument(
        "--png-dir",
        type=str,
        default=str(OUTPUT_DIR),
        help="Directory to save generated PNG plots",
    )
    parser.add_argument(
        "--no-png",
        action="store_true",
        help="Skip generating Matplotlib PNG plots",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Automatically open the HTML report in default browser",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start a local HTTP server to view the report",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8002,
        help="Port for local server (default: 8002)",
    )

    args = parser.parse_args()

    cards = load_all_tradeoff_cards()
    print(f"Loaded {len(cards)} cards from cardDefinitions.")

    # Generate HTML report
    html_path = Path(args.html)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_content = generate_html_dashboard(cards)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Generated HTML dashboard: {html_path}")

    # Generate Matplotlib plots unless --no-png
    if not args.no_png:
        png_dir = Path(args.png_dir)
        target_cats = (
            CATEGORIES
            if args.type == "all"
            else [c for c in CATEGORIES if c.lower() == args.type.lower()]
        )
        try:
            generated = generate_matplotlib_plots(
                cards, png_dir, categories=target_cats, spinup_x=args.spinup_x
            )
            print(f"Generated {len(generated)} PNG plot(s) in {png_dir}:")
            for p in generated:
                print(f"  - {Path(p).name}")
        except Exception as e:
            print(f"Warning: Failed to generate Matplotlib plots: {e}")

    if args.open:
        webbrowser.open(f"file://{html_path.resolve()}")

    if args.serve:
        run_server(port=args.port, html_path=html_path)


if __name__ == "__main__":
    main()
