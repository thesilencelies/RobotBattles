#!/usr/bin/env python3
"""
generate_automata_sheets.py

Lays out automata for printing onto A3 paper (outputting a PDF via LaTeX and TikZ).
- Normalizes names (replaces underbars with spaces, normalizes capitalization).
- Includes the action tables (Rush, Face, Retreat) based on automata archetypes.
- Straightens layout with layout relaxation and card scaling to eliminate all overlaps.
- Renders component connection lines bridging the edges of adjacent connected cards.
- Compiles via pdflatex into high-resolution A3 landscape PDF sheets.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Workspace root
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_DIR))

from builder.server.chassis_sheets import render_pdf_to_png
from builder.server.data import (
    A3_HEIGHT_MM,
    A3_WIDTH_MM,
    CARD_HEIGHT_MM,
    CARD_WIDTH_MM,
    CHASSIS_TEMPLATES,
    compute_card_box,
    compute_connections,
    get_card_image_url,
    load_all_cards,
    parse_robot_csv,
    sanitize_filename,
)

AUTOMATA_DIR = WORKSPACE_DIR / "automata"
ACTION_TABLES_MD = AUTOMATA_DIR / "Action_tables.md"
CARD_IMAGES_DIR = WORKSPACE_DIR / "CardImages"
TTS_ASSETS_DIR = WORKSPACE_DIR / "tts_assets"


# ---------------------------------------------------------------------------
# Name Normalization & Formatting
# ---------------------------------------------------------------------------

def normalize_robot_name(name: str) -> str:
    """Replaces underscores with spaces and normalizes capitalization (Title Case)."""
    clean = name.replace("_", " ").strip()
    return clean.title()


def tex_escape(s: str) -> str:
    """Escapes special LaTeX characters in plain text strings."""
    s = str(s)
    s = s.replace("\\", r"\textbackslash{}")
    s = s.replace("&", r"\&")
    s = s.replace("%", r"\%")
    s = s.replace("$", r"\$")
    s = s.replace("#", r"\#")
    s = s.replace("_", r"\_")
    s = s.replace("{", r"\{")
    s = s.replace("}", r"\}")
    s = s.replace("~", r"\textasciitilde{}")
    s = s.replace("^", r"\textasciicircum{}")
    s = s.replace("<", r"$<$")
    s = s.replace(">", r"$>$")
    return s


# ---------------------------------------------------------------------------
# Action Tables Parsing & Lookup
# ---------------------------------------------------------------------------

# Canonical archetype tables
ARCHETYPE_TABLES: Dict[str, Dict[str, Any]] = {
    "Full Rush": {
        "title": "Full Rush Action Table",
        "description": "Always same table",
        "sections": [
            {
                "condition": "",
                "rows": [
                    ("1", "Retreat"),
                    ("2", "Face"),
                    ("3", "Evade"),
                    ("4--6", "Rush"),
                ],
            }
        ],
    },
    "Spin Up": {
        "title": "Spin Up Action Table",
        "sections": [
            {
                "condition": "If 2+ spin counters on weapon (or weapons down):",
                "rows": [
                    ("1", "Face"),
                    ("2", "Evade"),
                    ("3--6", "Rush"),
                ],
            },
            {
                "condition": "Otherwise (< 2 spin counters):",
                "rows": [
                    ("1--2", "Retreat"),
                    ("3", "Face"),
                    ("4--5", "Evade"),
                    ("6", "Rush"),
                ],
            },
        ],
    },
    "Balanced": {
        "title": "Balanced Action Table",
        "sections": [
            {
                "condition": "If weapon is at full spin (or weapons down):",
                "rows": [
                    ("1", "Retreat"),
                    ("2", "Face"),
                    ("3", "Evade"),
                    ("4--6", "Rush"),
                ],
            },
            {
                "condition": "Otherwise (spinning up):",
                "rows": [
                    ("1", "Retreat"),
                    ("2--3", "Evade"),
                    ("4", "Face"),
                    ("5--6", "Rush"),
                ],
            },
        ],
    },
}

# Fallback bot to archetype mapping matching Action_tables.md
DEFAULT_BOT_ARCHETYPES: Dict[str, str] = {
    "vyper_flipper": "Full Rush",
    "vyper_spinner": "Spin Up",
    "beater_wide": "Balanced",
    "nightwing_wide": "Balanced",
    "chonk": "Spin Up",
}


def load_bot_archetype_mapping() -> Dict[str, str]:
    """Reads automata/Action_tables.md to map robot file stems to their archetypes."""
    mapping = dict(DEFAULT_BOT_ARCHETYPES)
    if not ACTION_TABLES_MD.exists():
        return mapping

    with open(ACTION_TABLES_MD, "r", encoding="utf-8") as f:
        lines = f.readlines()

    in_allocation_table = False
    for line in lines:
        line_s = line.strip()
        if "Per automata allocation" in line_s:
            in_allocation_table = True
            continue
        if in_allocation_table:
            if line_s.startswith("|") and not line_s.startswith("|-") and "Bot" not in line_s:
                parts = [p.strip() for p in line_s.split("|") if p.strip()]
                if len(parts) >= 2:
                    bot_key = parts[0].strip().lower()
                    archetype_val = parts[1].strip()
                    mapping[bot_key] = archetype_val
    return mapping


def get_action_table_for_bot(bot_stem: str) -> Dict[str, Any]:
    """Returns the action table definition dictionary for a given bot stem."""
    mapping = load_bot_archetype_mapping()
    archetype_name = mapping.get(bot_stem.lower(), "Balanced")
    # Lookup canonical archetype
    for key, val in ARCHETYPE_TABLES.items():
        if key.lower() == archetype_name.lower():
            res = dict(val)
            res["archetype_name"] = key
            return res
    # Fallback to Balanced
    res = dict(ARCHETYPE_TABLES["Balanced"])
    res["archetype_name"] = archetype_name
    return res


# ---------------------------------------------------------------------------
# Layout Relaxation & Overlap Elimination
# ---------------------------------------------------------------------------

def resolve_layout(
    placed: List[Dict[str, Any]],
    scale: float = 0.80,
    min_gap: float = 3.5,
    sheet_w: float = A3_WIDTH_MM,
    sheet_h: float = A3_HEIGHT_MM,
    iterations: int = 150,
) -> List[Dict[str, Any]]:
    """
    Scales and straightens placed cards to ensure strictly zero overlap
    with a minimum gap between all adjacent cards.
    """
    if not placed:
        return []

    # 1. Compute original bounding boxes and centers
    orig_cards = []
    for c in placed:
        rot = int(c.get("rotation", 0)) % 360
        is_rotated = rot in (90, 270)
        w0 = CARD_HEIGHT_MM if is_rotated else CARD_WIDTH_MM
        h0 = CARD_WIDTH_MM if is_rotated else CARD_HEIGHT_MM
        x0 = float(c.get("x", 100.0))
        y0 = float(c.get("y", 100.0))
        cx = x0 + w0 / 2.0
        cy = y0 + h0 / 2.0
        orig_cards.append({
            "id": str(c.get("id")),
            "card": c.get("card", "Card"),
            "card_data": c.get("card_data", {}),
            "rotation": rot,
            "orig_w": w0,
            "orig_h": h0,
            "orig_cx": cx,
            "orig_cy": cy,
        })

    # Robot bounding box center in original coordinates
    min_x = min(c["orig_cx"] - c["orig_w"] / 2.0 for c in orig_cards)
    max_x = max(c["orig_cx"] + c["orig_w"] / 2.0 for c in orig_cards)
    min_y = min(c["orig_cy"] - c["orig_h"] / 2.0 for c in orig_cards)
    max_y = max(c["orig_cy"] + c["orig_h"] / 2.0 for c in orig_cards)
    robot_cx = (min_x + max_x) / 2.0
    robot_cy = (min_y + max_y) / 2.0

    # Target center on A3 landscape sheet (center horizontally, y=155 leaving header clearance)
    target_cx = sheet_w / 2.0
    target_cy = 155.0

    # 2. Scale positions and dimensions
    boxes: List[Dict[str, Any]] = []
    for c in orig_cards:
        w = c["orig_w"] * scale
        h = c["orig_h"] * scale
        cx = target_cx + (c["orig_cx"] - robot_cx) * scale
        cy = target_cy + (c["orig_cy"] - robot_cy) * scale
        boxes.append({
            "id": c["id"],
            "card": c["card"],
            "card_data": c["card_data"],
            "rotation": c["rotation"],
            "w": w,
            "h": h,
            "cx": cx,
            "cy": cy,
            "target_cx": cx,
            "target_cy": cy,
        })

    # 3. Iterative relaxation to separate overlapping and tightly packed boxes
    for _ in range(iterations):
        for i in range(len(boxes)):
            b1 = boxes[i]
            for j in range(i + 1, len(boxes)):
                b2 = boxes[j]
                req_dx = (b1["w"] + b2["w"]) / 2.0 + min_gap
                req_dy = (b1["h"] + b2["h"]) / 2.0 + min_gap
                dx = b2["cx"] - b1["cx"]
                dy = b2["cy"] - b1["cy"]
                ox = req_dx - abs(dx)
                oy = req_dy - abs(dy)
                if ox > 0 and oy > 0:
                    if ox < oy:
                        push = (ox / 2.0) + 0.05
                        sign = 1.0 if dx >= 0 else -1.0
                        b1["cx"] -= push * sign
                        b2["cx"] += push * sign
                    else:
                        push = (oy / 2.0) + 0.05
                        sign = 1.0 if dy >= 0 else -1.0
                        b1["cy"] -= push * sign
                        b2["cy"] += push * sign

            # Gentle restoring force toward initial scaled position
            b1["cx"] += 0.05 * (b1["target_cx"] - b1["cx"])
            b1["cy"] += 0.05 * (b1["target_cy"] - b1["cy"])

    # 4. Final strict pass to guarantee strictly 0 overlaps with min_gap
    for _ in range(60):
        moved = 0
        for i in range(len(boxes)):
            b1 = boxes[i]
            for j in range(i + 1, len(boxes)):
                b2 = boxes[j]
                req_dx = (b1["w"] + b2["w"]) / 2.0 + min_gap
                req_dy = (b1["h"] + b2["h"]) / 2.0 + min_gap
                dx = b2["cx"] - b1["cx"]
                dy = b2["cy"] - b1["cy"]
                ox = req_dx - abs(dx)
                oy = req_dy - abs(dy)
                if ox > 0 and oy > 0:
                    if ox < oy:
                        push = (ox / 2.0) + 0.1
                        sign = 1.0 if dx >= 0 else -1.0
                        b1["cx"] -= push * sign
                        b2["cx"] += push * sign
                    else:
                        push = (oy / 2.0) + 0.1
                        sign = 1.0 if dy >= 0 else -1.0
                        b1["cy"] -= push * sign
                        b2["cy"] += push * sign
                    moved += 1
        if moved == 0:
            break

    return boxes


# ---------------------------------------------------------------------------
# Component Connection Line Computation
# ---------------------------------------------------------------------------

SUPPLY_RESOURCES: Set[str] = {"E", "S", "P", "D", "M"}


def components_supply_each_other(
    card_a: Dict[str, Any],
    card_b: Dict[str, Any],
    by_name: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Returns True if component A can supply component B or component B can supply component A.
    Checks whether outputs of one component provide supply resources ('E', 'S', 'P', 'D', 'M')
    required by the other.
    """
    name_a = card_a.get("card") or card_a.get("name", "")
    name_b = card_b.get("card") or card_b.get("name", "")
    data_a = card_a.get("card_data") or (by_name.get(name_a) if by_name else {}) or {}
    data_b = card_b.get("card_data") or (by_name.get(name_b) if by_name else {}) or {}

    outs_a = set(str(data_a.get("outputs", "")).upper()) & SUPPLY_RESOURCES
    reqs_a = set(str(data_a.get("requirements", "")).upper()) & SUPPLY_RESOURCES
    outs_b = set(str(data_b.get("outputs", "")).upper()) & SUPPLY_RESOURCES
    reqs_b = set(str(data_b.get("requirements", "")).upper()) & SUPPLY_RESOURCES

    return bool((outs_a & reqs_b) or (outs_b & reqs_a))


def extract_connected_pairs(
    placed: List[Dict[str, Any]],
    raw_rows: List[Dict[str, Any]],
    supply_only: bool = True,
) -> Set[Tuple[str, str]]:
    """
    Identifies all pairs of placed cards that are physically adjacent or
    connected in the robot definition, filtered to components that supply
    one another if supply_only is True.
    """
    pairs: Set[Tuple[str, str]] = set()

    # 1. Physical adjacency in original configuration
    auto_conns = compute_connections(placed)
    for cid, neighbors in auto_conns.items():
        for n in neighbors:
            if str(cid) != "1" and str(n) != "1":
                pair = tuple(sorted([str(cid), str(n)]))
                pairs.add(pair)

    # 2. Connection column parsing (handling explicit IDs and shared c_ IDs)
    c_groups: Dict[str, Set[str]] = {}
    valid_ids = {str(c.get("id")) for c in placed}

    for row in raw_rows:
        cid = str(row.get("id", "")).strip()
        if cid not in valid_ids:
            continue
        conns_str = (row.get("connections") or "").strip()
        if not conns_str:
            continue
        for token in conns_str.split(";"):
            token = token.strip()
            if not token:
                continue
            if token.startswith("c_"):
                c_groups.setdefault(token, set()).add(cid)
            elif token in valid_ids and token != cid:
                pairs.add(tuple(sorted([cid, token])))

    # Any cards sharing a temporary c_ ID group are connected
    for _, members in c_groups.items():
        m_list = list(members)
        for i in range(len(m_list)):
            for j in range(i + 1, len(m_list)):
                pairs.add(tuple(sorted([m_list[i], m_list[j]])))

    if supply_only:
        card_map = {str(c.get("id")): c for c in placed}
        pairs = {
            p for p in pairs
            if p[0] in card_map and p[1] in card_map and components_supply_each_other(card_map[p[0]], card_map[p[1]])
        }

    return pairs


def compute_connection_segment(
    b1: Dict[str, Any], b2: Dict[str, Any]
) -> Tuple[float, float, float, float]:
    """
    Calculates a straight line segment bridging the facing edges of two cards.
    Returns (x1, y1, x2, y2).
    """
    x1_min = b1["cx"] - b1["w"] / 2.0
    x1_max = b1["cx"] + b1["w"] / 2.0
    y1_min = b1["cy"] - b1["h"] / 2.0
    y1_max = b1["cy"] + b1["h"] / 2.0

    x2_min = b2["cx"] - b2["w"] / 2.0
    x2_max = b2["cx"] + b2["w"] / 2.0
    y2_min = b2["cy"] - b2["h"] / 2.0
    y2_max = b2["cy"] + b2["h"] / 2.0

    # 1. Horizontal separation with overlapping vertical span
    if x1_max <= x2_min + 0.1:
        y_start = max(y1_min, y2_min)
        y_end = min(y1_max, y2_max)
        if y_end > y_start:
            ymid = (y_start + y_end) / 2.0
            return (x1_max, ymid, x2_min, ymid)
    elif x2_max <= x1_min + 0.1:
        y_start = max(y1_min, y2_min)
        y_end = min(y1_max, y2_max)
        if y_end > y_start:
            ymid = (y_start + y_end) / 2.0
            return (x2_max, ymid, x1_min, ymid)

    # 2. Vertical separation with overlapping horizontal span
    if y1_max <= y2_min + 0.1:
        x_start = max(x1_min, x2_min)
        x_end = min(x1_max, x2_max)
        if x_end > x_start:
            xmid = (x_start + x_end) / 2.0
            return (xmid, y1_max, xmid, y2_min)
    elif y2_max <= y1_min + 0.1:
        x_start = max(x1_min, x2_min)
        x_end = min(x1_max, x2_max)
        if x_end > x_start:
            xmid = (x_start + x_end) / 2.0
            return (xmid, y2_max, xmid, y1_min)

    # 3. Diagonal separation: clamp to boundaries
    def clamp(v: float, vmin: float, vmax: float) -> float:
        return max(vmin, min(v, vmax))

    px1 = clamp(b2["cx"], x1_min, x1_max)
    py1 = clamp(b2["cy"], y1_min, y1_max)
    px2 = clamp(b1["cx"], x2_min, x2_max)
    py2 = clamp(b1["cy"], y2_min, y2_max)
    return (px1, py1, px2, py2)


# ---------------------------------------------------------------------------
# LaTeX / TikZ Document Generation
# ---------------------------------------------------------------------------

def generate_action_table_tex(action_data: Dict[str, Any]) -> str:
    """Formats an Action Table tabular LaTeX string."""
    title = action_data.get("title", "Action Table")
    sections = action_data.get("sections", [])

    lines = []
    lines.append(r"\sffamily")
    lines.append(r"\begin{tabular}{@{}c l@{}}")
    lines.append(rf"\multicolumn{{2}}{{c}}{{\textbf{{\large {title}}}}} \\")
    lines.append(r"\midrule")

    for s_idx, sec in enumerate(sections):
        cond = sec.get("condition", "").strip()
        if cond:
            lines.append(rf"\multicolumn{{2}}{{@{{}}l@{{}}}}{{\textbf{{\footnotesize {tex_escape(cond)}}}}} \\")
            lines.append(r"\textbf{d6 Roll} & \textbf{Action} \\")
            lines.append(r"\midrule")
        else:
            lines.append(r"\textbf{d6 Roll} & \textbf{Action} \\")
            lines.append(r"\midrule")

        for roll_str, act_str in sec.get("rows", []):
            lines.append(rf"{roll_str} & {act_str} \\")

        if s_idx < len(sections) - 1:
            lines.append(r"\midrule")

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    return "\n".join(lines)


def generate_robot_page_tikz(bot_info: Dict[str, Any], scale: float = 0.80, min_gap: float = 3.5) -> str:
    """Generates the TikZ environment for a single robot's A3 landscape page."""
    bot_name = bot_info["bot_name"]
    display_name = normalize_robot_name(bot_name)
    chassis = bot_info["chassis"]
    chassis_name = chassis.get("name", "Chassis")
    template_name = chassis.get("template", "Square")
    total_weight = bot_info["total_weight"]
    total_cost = bot_info["total_cost"]
    flip_str = chassis.get("flip_strength", 0)

    action_table = bot_info["action_table"]
    archetype_name = action_table.get("archetype_name", "Balanced")

    boxes = bot_info["resolved_boxes"]
    box_map = {b["id"]: b for b in boxes}
    connected_pairs = bot_info["connected_pairs"]

    lines = []
    lines.append(r"\noindent\begin{tikzpicture}[remember picture, overlay, shift={(current page.north west)}, x=1mm, y=-1mm]")
    lines.append(r"  \path (0,0) rectangle (420, 297);")

    # 1. Background Grid (10mm minor, 50mm major)
    lines.append(r"  % Background Engineering Grid")
    lines.append(r"  \draw[black!5, step=10] (0,0) grid (420, 297);")
    lines.append(r"  \draw[black!12, step=50] (0,0) grid (420, 297);")

    # 2. Chassis Outline
    geom = CHASSIS_TEMPLATES.get(template_name, CHASSIS_TEMPLATES.get("Square", {}))
    points = geom.get("points", [])
    if points:
        pts_str = " -- ".join(f"({p[0]:.1f}, {p[1]:.1f})" for p in points)
        lines.append(r"  % Chassis Boundary Outline")
        lines.append(rf"  \draw[cyan!60!blue, line width=1.4pt, line join=round, dashed] {pts_str} -- cycle;")
        p0 = points[0]
        lines.append(
            rf"  \node[anchor=north west, font=\sffamily\scriptsize\bfseries, text=cyan!60!blue] "
            rf"at ({p0[0] + 2:.1f}, {p0[1] + 2:.1f}) {{Chassis Boundary ({tex_escape(template_name)})}};"
        )

    # 3. Heading / Front Indicator
    lines.append(r"  % Forward Heading Indicator")
    lines.append(r"  \draw[line width=1.6pt, -{Triangle[length=2.8mm]}, green!60!black] (210, 24) -- (210, 14);")
    lines.append(r"  \node[anchor=south, font=\sffamily\bfseries\footnotesize, text=green!60!black] at (210, 13) {FRONT / HEADING};")

    # 4. Title & Robot Specs Plate (Top-Left)
    flip_note = f" \\quad \\textbf{{FLIP:}} {flip_str}" if flip_str else ""
    lines.append(r"  % Title & Specs Information Plate")
    lines.append(r"  \node[anchor=north west, fill=white, draw=black!40, rounded corners=2mm, inner sep=3mm, line width=0.7pt] at (12, 12) {")
    lines.append(r"    \begin{minipage}{85mm}")
    lines.append(rf"      {{\LARGE\bfseries\sffamily {tex_escape(display_name)}}} \par\vspace{{1.5mm}}")
    lines.append(rf"      {{\small\sffamily\textbf{{Chassis:}} {tex_escape(chassis_name)} ({tex_escape(template_name)})}} \par\vspace{{0.5mm}}")
    lines.append(rf"      {{\small\sffamily\textbf{{Archetype:}} {tex_escape(archetype_name)}}} \par\vspace{{2mm}}")
    lines.append(rf"      {{\sffamily\bfseries WEIGHT:}} {total_weight} \quad {{\sffamily\bfseries COST:}} \${total_cost}{flip_note}")
    lines.append(r"    \end{minipage}")
    lines.append(r"  };")

    # 5. Action Table Plate (Top-Right)
    action_table_tex = generate_action_table_tex(action_table)
    lines.append(r"  % Automata Action Table")
    lines.append(r"  \node[anchor=north east, fill=white, draw=black!40, rounded corners=2mm, inner sep=2.5mm, line width=0.7pt] at (408, 12) {")
    lines.append(f"    {action_table_tex}")
    lines.append(r"  };")

    # 6. Card Nodes
    lines.append(r"  % Robot Component Cards")
    unrot_w = CARD_WIDTH_MM * scale
    unrot_h = CARD_HEIGHT_MM * scale

    for b in boxes:
        card_name = b["card"]
        cx = b["cx"]
        cy = b["cy"]
        w = b["w"]
        h = b["h"]
        rot = b["rotation"]

        # Check image availability
        url = get_card_image_url(card_name)
        if url:
            img_filename = Path(url).name
            if rot == 0:
                angle_opt = ""
            else:
                angle_opt = f", angle=-{rot}"

            lines.append(
                rf"  \node[inner sep=0, anchor=center] at ({cx:.2f}, {cy:.2f}) "
                rf"{{\includegraphics[width={unrot_w:.2f}mm, height={unrot_h:.2f}mm{angle_opt}]{{{img_filename}}}}};"
            )
            # Subtle card boundary frame
            lines.append(
                rf"  \draw[rounded corners=1mm, line width=0.5pt, black!40] "
                rf"({cx - w / 2.0:.2f}, {cy - h / 2.0:.2f}) rectangle ({cx + w / 2.0:.2f}, {cy + h / 2.0:.2f});"
            )
        else:
            # Fallback vector card block
            lines.append(
                rf"  \filldraw[fill=blue!5!white, draw=blue!40!black, rounded corners=1mm, line width=0.6pt] "
                rf"({cx - w / 2.0:.2f}, {cy - h / 2.0:.2f}) rectangle ({cx + w / 2.0:.2f}, {cy + h / 2.0:.2f});"
            )
            lines.append(
                rf"  \node[align=center, font=\footnotesize\sffamily\bfseries, text width={w - 4:.2f}mm] "
                rf"at ({cx:.2f}, {cy:.2f}) {{{tex_escape(card_name)}}};"
            )

    # 7. Component Connection Lines (drawn after cards so they sit clearly on top of card borders)
    lines.append(r"  % Component Edge Connections")
    drawn_pairs: Set[Tuple[str, str]] = set()
    for id_a, id_b in connected_pairs:
        pair_key = tuple(sorted([id_a, id_b]))
        if pair_key in drawn_pairs:
            continue
        drawn_pairs.add(pair_key)

        b1 = box_map.get(id_a)
        b2 = box_map.get(id_b)
        if not b1 or not b2:
            continue

        x1, y1, x2, y2 = compute_connection_segment(b1, b2)
        # Avoid drawing trivial or negative segments
        seg_len = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        if seg_len < 0.2:
            continue
        # Only draw clean edge-to-edge jumper lines between facing adjacent cards
        is_ortho = (abs(x1 - x2) < 0.05) or (abs(y1 - y2) < 0.05)
        if not (is_ortho and seg_len <= 8.5 or (not is_ortho and seg_len <= 4.0)):
            continue

        # Extend line segment by 1.0mm onto adjacent card borders so there is no gap
        dx = (x2 - x1) / seg_len
        dy = (y2 - y1) / seg_len
        ex1, ey1 = x1 - dx * 1.0, y1 - dy * 1.0
        ex2, ey2 = x2 + dx * 1.0, y2 + dy * 1.0

        lines.append(
            rf"  \draw[line width=5.5pt, teal!80!black, line cap=round] "
            rf"({ex1:.2f}, {ey1:.2f}) -- ({ex2:.2f}, {ey2:.2f});"
        )

    lines.append(r"\end{tikzpicture}")
    return "\n".join(lines)


def generate_latex_document(robot_pages_tikz: List[str]) -> str:
    """Wraps pages in a complete standalone LaTeX document."""
    preamble = r"""\documentclass{article}
\usepackage[a3paper,landscape,margin=0mm]{geometry}
\usepackage{tikz}
\usepackage{graphicx}
\usepackage{xcolor}
\usepackage{booktabs}
\usetikzlibrary{arrows.meta,calc}
\graphicspath{{""" + str(CARD_IMAGES_DIR) + r"""/}{./CardImages/}}
\pagestyle{empty}

\begin{document}
"""
    body = "\n\\null\\newpage\n".join(robot_pages_tikz)
    postamble = "\n\\null\n\\end{document}\n"
    return preamble + body + postamble


# ---------------------------------------------------------------------------
# Data Loading & Processing
# ---------------------------------------------------------------------------

def process_robot_csv(
    csv_file: Path | str, scale: float = 0.80, min_gap: float = 3.5
) -> Dict[str, Any]:
    """Loads an automaton CSV and calculates layout and connections."""
    csv_path = Path(csv_file)
    bot_stem = csv_path.stem
    with open(csv_path, "r", encoding="utf-8") as f:
        csv_text = f.read()

    parsed = parse_robot_csv(csv_text)
    placed = parsed.get("placed_cards", [])
    chassis = parsed.get("chassis") or {"name": "Default Chassis", "template": "Square", "weight": 0, "cost": 0}

    # Raw rows to catch c_ hyperedges
    with open(csv_file, "r", encoding="utf-8") as f:
        raw_rows = list(csv.DictReader(f))

    # Weight and cost
    total_weight = int(chassis.get("weight", 0))
    total_cost = int(chassis.get("cost", 0))
    for c in placed:
        cdata = c.get("card_data", {})
        total_weight += int(cdata.get("weight", 0))
        total_cost += int(cdata.get("cost", 0))

    # Overlap resolution
    resolved_boxes = resolve_layout(placed, scale=scale, min_gap=min_gap)

    # Connections
    connected_pairs = extract_connected_pairs(placed, raw_rows)

    # Action table
    action_table = get_action_table_for_bot(bot_stem)

    return {
        "bot_name": bot_stem,
        "csv_file": csv_file,
        "chassis": chassis,
        "total_weight": total_weight,
        "total_cost": total_cost,
        "action_table": action_table,
        "resolved_boxes": resolved_boxes,
        "connected_pairs": connected_pairs,
    }


# ---------------------------------------------------------------------------
# PDF Compilation
# ---------------------------------------------------------------------------

def compile_latex_to_pdf(tex_code: str, output_pdf: Path) -> Path:
    """Compiles LaTeX code via pdflatex into the target PDF path."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        tex_path = tmp_path / "document.tex"
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(tex_code)

        # Run pdflatex twice from project root to resolve TikZ remember picture coordinates
        cmd = [
            "pdflatex",
            "-interaction=nonstopmode",
            "-halt-on-error",
            f"-output-directory={tmp_dir}",
            str(tex_path),
        ]
        # Pass 1
        proc1 = subprocess.run(cmd, cwd=WORKSPACE_DIR, capture_output=True, text=True)
        if proc1.returncode != 0:
            sys.stderr.write(proc1.stdout)
            sys.stderr.write(proc1.stderr)
            raise RuntimeError(f"pdflatex pass 1 failed with code {proc1.returncode}")

        # Pass 2
        proc2 = subprocess.run(cmd, cwd=WORKSPACE_DIR, capture_output=True, text=True)
        if proc2.returncode != 0:
            sys.stderr.write(proc2.stdout)
            sys.stderr.write(proc2.stderr)
            raise RuntimeError(f"pdflatex pass 2 failed with code {proc2.returncode}")

        generated_pdf = tmp_path / "document.pdf"
        if not generated_pdf.exists():
            raise FileNotFoundError("pdflatex did not produce document.pdf")

        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(generated_pdf, output_pdf)

    return output_pdf


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lay out automata for printing onto A3 paper (outputting a PDF via LaTeX and TikZ)."
    )
    parser.add_argument(
        "--bot",
        "-b",
        type=str,
        default=None,
        help="Specific bot to build (e.g. 'Vyper_flipper', 'Beater_wide'). Defaults to all.",
    )
    parser.add_argument(
        "--scale",
        "-s",
        type=float,
        default=0.80,
        help="Card scale factor (default: 0.80).",
    )
    parser.add_argument(
        "--gap",
        "-g",
        type=float,
        default=3.0,
        help="Minimum gap between cards in mm (default: 3.0).",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=AUTOMATA_DIR,
        help="Destination directory for generated PDFs (default: automata/).",
    )
    parser.add_argument(
        "--individual",
        action="store_true",
        default=True,
        help="Generate separate individual PDFs for each bot in addition to combined (default: True).",
    )
    parser.add_argument(
        "--combined-only",
        action="store_true",
        help="Generate only the combined multi-page PDF (skip individual PDFs and TTS PNGs).",
    )
    parser.add_argument(
        "--tts-dir",
        type=Path,
        default=TTS_ASSETS_DIR,
        help="Destination directory for TTS asset images (default: tts_assets/).",
    )
    parser.add_argument(
        "--skip-tts",
        action="store_true",
        help="Skip rendering individual sheets to TTS PNG images in tts_assets/.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=150,
        help="Render DPI for PNG images (default: 150).",
    )
    args = parser.parse_args()

    out_dir = args.output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    tts_dir = args.tts_dir.resolve() if args.tts_dir else None

    # Discover target CSV files
    all_csvs = sorted(AUTOMATA_DIR.glob("*.csv"))
    if args.bot:
        target_name = args.bot.lower().replace(".csv", "")
        csv_files = [f for f in all_csvs if f.stem.lower() == target_name]
        if not csv_files:
            sys.exit(f"Error: Bot '{args.bot}' not found in {AUTOMATA_DIR}")
    else:
        csv_files = all_csvs

    if not csv_files:
        sys.exit(f"No CSV files found in {AUTOMATA_DIR}")

    print(f"Processing {len(csv_files)} automata CSVs (scale={args.scale}, gap={args.gap}mm)...")
    processed_bots = []
    for f in csv_files:
        print(f"  * Loading: {f.name} -> {normalize_robot_name(f.stem)}")
        b_info = process_robot_csv(f, scale=args.scale, min_gap=args.gap)
        processed_bots.append(b_info)

    if args.bot:
        generate_individual = True
        generate_combined = False
    elif args.combined_only:
        generate_individual = False
        generate_combined = True
    else:
        generate_individual = True
        generate_combined = True

    # 1. Individual PDFs and TTS PNGs
    if generate_individual:
        for b_info in processed_bots:
            pdf_path = out_dir / f"{b_info['bot_name']}_sheet.pdf"
            print(f"Generating individual PDF: {pdf_path.name}...")
            page_tikz = generate_robot_page_tikz(b_info, scale=args.scale, min_gap=args.gap)
            doc_tex = generate_latex_document([page_tikz])
            compile_latex_to_pdf(doc_tex, pdf_path)
            print(f"  + Created: {pdf_path}")

            if not args.skip_tts and tts_dir:
                tts_dir.mkdir(parents=True, exist_ok=True)
                out_png = tts_dir / f"{b_info['bot_name']}_sheet.png"
                print(f"  * Rendering TTS PNG: {pdf_path.name} -> {out_png.name}...")
                render_pdf_to_png(pdf_path, out_png, dpi=args.dpi)
                print(f"  + Created: {out_png}")

    # 2. Combined PDF
    if generate_combined:
        combined_pdf_path = out_dir / "automata_sheets.pdf"
        print(f"Generating combined multi-page PDF: {combined_pdf_path.name}...")
        all_pages_tikz = [
            generate_robot_page_tikz(b_info, scale=args.scale, min_gap=args.gap)
            for b_info in processed_bots
        ]
        doc_tex = generate_latex_document(all_pages_tikz)
        compile_latex_to_pdf(doc_tex, combined_pdf_path)
        print(f"  + Created: {combined_pdf_path} ({len(all_pages_tikz)} pages)")

    print("Finished successfully.")


if __name__ == "__main__":
    main()
