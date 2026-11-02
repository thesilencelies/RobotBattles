#!/usr/bin/env python3
"""
generate_action_cards.py

Generates TikZ LaTeX files for Robot Battles movement action cards into
cardCreation/build/card/Action_<Name>.tex, and records their filenames in
cardCreation/build/action_cards.csv.

Follows the card dimensions (56x87mm with 2.5mm bleed -> 61x92mm) and styles
used throughout the game, implementing the refined diagrams requested by the user.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import re
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
CARD_DEFS_DIR = WORKSPACE / "cardDefinitions"
BUILD_DIR = Path(__file__).resolve().parent / "build"
CARD_OUTPUT_DIR = BUILD_DIR / "card"

# Geometry constants (56mm x 87mm + 2.5mm bleed)
CARD_SAFE_W_CM = 5.60
CARD_SAFE_H_CM = 8.70
BLEED_OFFSET_X = 0.25
BLEED_OFFSET_Y = 0.25
CARD_OUTER_W_CM = CARD_SAFE_W_CM + 2.0 * BLEED_OFFSET_X
CARD_OUTER_H_CM = CARD_SAFE_H_CM + 2.0 * BLEED_OFFSET_Y


def sanitize_filename(name: str) -> str:
    s = name.strip().replace(" ", "_")
    return re.sub(r"[^A-Za-z0-9_.-]", "", s)


def escape_latex(text: str) -> str:
    if not text:
        return ""
    text = text.strip()
    text = text.replace("&", r"\&")
    text = text.replace("%", r"\%")
    text = text.replace("$", r"\$")
    text = text.replace("#", r"\#")
    text = text.replace("_", r"\_")
    return text


def chevron_up(cx: float, cy: float, half_w: float, h: float, lw: float = 2.8) -> str:
    return (
        rf"    \draw[line width={lw:.1f}pt, draw=primaryDark, line join=round, line cap=round] "
        rf"({cx - half_w:.2f}, {cy - h:.2f}) -- ({cx:.2f}, {cy:.2f}) -- ({cx + half_w:.2f}, {cy - h:.2f});"
    )


def chevron_down(cx: float, cy: float, half_w: float, h: float, lw: float = 2.8) -> str:
    return (
        rf"    \draw[line width={lw:.1f}pt, draw=primaryDark, line join=round, line cap=round] "
        rf"({cx - half_w:.2f}, {cy + h:.2f}) -- ({cx:.2f}, {cy:.2f}) -- ({cx + half_w:.2f}, {cy + h:.2f});"
    )


def build_action_diagram(action_type: str) -> list[str]:
    """Generates TikZ code for the central motion diagram."""
    lines = []

    def robot_marker(x: float, y: float, angle: float = 0.0, ghost: bool = False, label: str = "", scale: float = 1.0) -> list[str]:
        scale_str = f", scale={scale:.2f}" if scale != 1.0 else ""
        m_lines = [rf"    \begin{{scope}}[shift={{({x:.2f}, {y:.2f})}}, rotate={angle:.1f}{scale_str}]"]
        if ghost:
            m_lines.append(r"      \fill[gray!40] (-0.30, 0) -- (0, 0.40) -- (0.30, 0) -- cycle;")
            m_lines.append(r"      \draw[draw=gray!60, dashed, line width=2.4pt, rounded corners=1pt] (-1.05, 0) -- (1.05, 0);")
            m_lines.append(r"      \fill[gray!50] (-1.00, -0.17) rectangle (-0.78, 0.17);")
            m_lines.append(r"      \fill[gray!50] ( 0.78, -0.17) rectangle ( 1.00, 0.17);")
        else:
            m_lines.append(r"      \fill[arenaRed] (-0.35, 0) -- (0, 0.46) -- (0.35, 0) -- cycle;")
            m_lines.append(r"      \draw[draw=arenaRed, line width=3.6pt, rounded corners=1.2pt] (-1.05, 0) -- (1.05, 0);")
            m_lines.append(r"      \fill[primaryDark] (-1.00, -0.19) rectangle (-0.78, 0.19);")
            m_lines.append(r"      \fill[primaryDark] ( 0.78, -0.19) rectangle ( 1.00, 0.19);")
        if label:
            m_lines.append(rf"      \node[font=\fontsize{{5}}{{6}}\selectfont\sffamily\bfseries, text=textdark!60] at (0, -0.32) {{{label}}};")
        m_lines.append(r"    \end{scope}")
        return m_lines

    # Arrowhead style
    arrow_tip = r"-{Triangle[width=4.4mm,length=5.0mm]}"
    arrow_line = r"line width=2.8pt, draw=primaryDark"

    cx = 2.80

    if action_type == "wait":
        cy = 4.35
        lines.extend(robot_marker(cx, cy, 0.0, ghost=False, scale=1.20))
        # Subtle stationary circle & pause indicator
        lines.append(rf"    \draw[draw=primaryDark!30, dashed, line width=1.1pt] ({cx:.2f}, {cy:.2f}) circle (1.65cm);")
        lines.append(rf"    \fill[primaryDark!80] ({cx - 0.28:.2f}, {cy + 1.30:.2f}) rectangle ({cx - 0.10:.2f}, {cy + 1.90:.2f});")
        lines.append(rf"    \fill[primaryDark!80] ({cx + 0.10:.2f}, {cy + 1.30:.2f}) rectangle ({cx + 0.28:.2f}, {cy + 1.90:.2f});")
        lines.append(rf"    \node[anchor=center, font=\fontsize{{9}}{{11}}\selectfont\sffamily\bfseries, text=primaryDark!75] at ({cx:.2f}, {cy - 1.10:.2f}) {{STATIONARY}};")

    elif action_type == "forward_1":
        # Base at y = 2.80, one arrow straight up with single chevron, no final position
        y_base = 2.80
        y_top = 5.60
        lines.extend(robot_marker(cx, y_base, 0.0, ghost=False))
        lines.append(rf"    \draw[{arrow_line}] ({cx:.2f}, {y_base + 0.46:.2f}) -- ({cx:.2f}, {y_top:.2f});")
        lines.append(chevron_up(cx, y_top, half_w=0.55, h=0.45, lw=3.0))

    elif action_type == "forward_2":
        # Base at y = 2.50, one arrow with 2 increasingly large chevrons, no final position
        y_base = 2.50
        y_ch1 = 4.40
        y_ch2 = 6.20
        lines.extend(robot_marker(cx, y_base, 0.0, ghost=False))
        lines.append(rf"    \draw[{arrow_line}] ({cx:.2f}, {y_base + 0.46:.2f}) -- ({cx:.2f}, {y_ch2:.2f});")
        lines.append(chevron_up(cx, y_ch1, half_w=0.42, h=0.35, lw=2.6))
        lines.append(chevron_up(cx, y_ch2, half_w=0.72, h=0.58, lw=3.4))

    elif action_type == "forward_3":
        # Base at y = 2.30, one arrow with 3 increasingly large chevrons, no final position
        y_base = 2.30
        y_ch1 = 3.80
        y_ch2 = 5.15
        y_ch3 = 6.60
        lines.extend(robot_marker(cx, y_base, 0.0, ghost=False))
        lines.append(rf"    \draw[{arrow_line}] ({cx:.2f}, {y_base + 0.46:.2f}) -- ({cx:.2f}, {y_ch3:.2f});")
        lines.append(chevron_up(cx, y_ch1, half_w=0.36, h=0.30, lw=2.4))
        lines.append(chevron_up(cx, y_ch2, half_w=0.56, h=0.46, lw=2.9))
        lines.append(chevron_up(cx, y_ch3, half_w=0.86, h=0.70, lw=3.6))

    elif action_type == "backward_1":
        # Base at y = 6.20 (facing up), one arrow straight down with single chevron, no final position
        y_base = 6.20
        y_bot = 3.40
        lines.extend(robot_marker(cx, y_base, 0.0, ghost=False))
        lines.append(rf"    \draw[{arrow_line}] ({cx:.2f}, {y_base - 0.15:.2f}) -- ({cx:.2f}, {y_bot:.2f});")
        lines.append(chevron_down(cx, y_bot, half_w=0.55, h=0.45, lw=3.0))

    elif action_type == "backward_2":
        # Base at y = 6.40 (facing up), one arrow with 2 increasingly large chevrons downwards, no final position
        y_base = 6.40
        y_ch1 = 4.60
        y_ch2 = 2.80
        lines.extend(robot_marker(cx, y_base, 0.0, ghost=False))
        lines.append(rf"    \draw[{arrow_line}] ({cx:.2f}, {y_base - 0.15:.2f}) -- ({cx:.2f}, {y_ch2:.2f});")
        lines.append(chevron_down(cx, y_ch1, half_w=0.42, h=0.35, lw=2.6))
        lines.append(chevron_down(cx, y_ch2, half_w=0.72, h=0.58, lw=3.4))

    elif action_type == "backward_3":
        # Base at y = 6.60 (facing up), one arrow with 3 increasingly large chevrons downwards, no final position
        y_base = 6.60
        y_ch1 = 5.20
        y_ch2 = 3.85
        y_ch3 = 2.40
        lines.extend(robot_marker(cx, y_base, 0.0, ghost=False))
        lines.append(rf"    \draw[{arrow_line}] ({cx:.2f}, {y_base - 0.15:.2f}) -- ({cx:.2f}, {y_ch3:.2f});")
        lines.append(chevron_down(cx, y_ch1, half_w=0.36, h=0.30, lw=2.4))
        lines.append(chevron_down(cx, y_ch2, half_w=0.56, h=0.46, lw=2.9))
        lines.append(chevron_down(cx, y_ch3, half_w=0.86, h=0.70, lw=3.6))

    elif action_type == "turn_r_45":
        # Right turn 45 deg around pinned right wheel (enlarged diagram, single arrow)
        scale_val = 1.35
        d_w = 1.20
        r_wheel = 2.40
        p_x, p_y = 3.60, 3.30
        lines.extend(robot_marker(p_x - d_w, p_y, 0.0, ghost=False, scale=scale_val))
        # Rotated 45 deg CW (-45) around (p_x, p_y)
        dest_cx = p_x - d_w * math.cos(math.radians(45))
        dest_cy = p_y + d_w * math.sin(math.radians(45))
        lines.extend(robot_marker(dest_cx, dest_cy, -45.0, ghost=True, scale=scale_val))
        # Pivot dot at right wheel
        lines.append(rf"    \fill[primaryDark] ({p_x:.2f}, {p_y:.2f}) circle (2.8pt);")
        lines.append(rf"    \draw[primaryDark, line width=0.8pt] ({p_x:.2f}, {p_y:.2f}) circle (5.0pt);")
        # Single continuous arc from 180 to 135 (CW)
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({p_x:.2f}, {p_y:.2f}) ++(180:{r_wheel:.2f}) arc (180:135:{r_wheel:.2f});")

    elif action_type == "turn_r_90":
        # Right turn 90 deg around pinned right wheel (enlarged diagram, single arrow)
        scale_val = 1.35
        d_w = 1.20
        r_wheel = 2.40
        p_x, p_y = 3.60, 3.10
        lines.extend(robot_marker(p_x - d_w, p_y, 0.0, ghost=False, scale=scale_val))
        dest_cx = p_x
        dest_cy = p_y + d_w
        lines.extend(robot_marker(dest_cx, dest_cy, -90.0, ghost=True, scale=scale_val))
        # Pivot dot
        lines.append(rf"    \fill[primaryDark] ({p_x:.2f}, {p_y:.2f}) circle (2.8pt);")
        lines.append(rf"    \draw[primaryDark, line width=0.8pt] ({p_x:.2f}, {p_y:.2f}) circle (5.0pt);")
        # Single continuous arc from 180 to 90 (CW)
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({p_x:.2f}, {p_y:.2f}) ++(180:{r_wheel:.2f}) arc (180:90:{r_wheel:.2f});")

    elif action_type == "turn_l_45":
        # Left turn 45 deg around pinned left wheel (enlarged diagram, single arrow)
        scale_val = 1.35
        d_w = 1.20
        r_wheel = 2.40
        p_x, p_y = 2.00, 3.30
        lines.extend(robot_marker(p_x + d_w, p_y, 0.0, ghost=False, scale=scale_val))
        dest_cx = p_x + d_w * math.cos(math.radians(45))
        dest_cy = p_y + d_w * math.sin(math.radians(45))
        lines.extend(robot_marker(dest_cx, dest_cy, 45.0, ghost=True, scale=scale_val))
        # Pivot dot at left wheel
        lines.append(rf"    \fill[primaryDark] ({p_x:.2f}, {p_y:.2f}) circle (2.8pt);")
        lines.append(rf"    \draw[primaryDark, line width=0.8pt] ({p_x:.2f}, {p_y:.2f}) circle (5.0pt);")
        # Single continuous arc from 0 to 45 (CCW)
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({p_x:.2f}, {p_y:.2f}) ++(0:{r_wheel:.2f}) arc (0:45:{r_wheel:.2f});")

    elif action_type == "turn_l_90":
        # Left turn 90 deg around pinned left wheel (enlarged diagram, single arrow)
        scale_val = 1.35
        d_w = 1.20
        r_wheel = 2.40
        p_x, p_y = 2.00, 3.10
        lines.extend(robot_marker(p_x + d_w, p_y, 0.0, ghost=False, scale=scale_val))
        dest_cx = p_x
        dest_cy = p_y + d_w
        lines.extend(robot_marker(dest_cx, dest_cy, 90.0, ghost=True, scale=scale_val))
        # Pivot dot
        lines.append(rf"    \fill[primaryDark] ({p_x:.2f}, {p_y:.2f}) circle (2.8pt);")
        lines.append(rf"    \draw[primaryDark, line width=0.8pt] ({p_x:.2f}, {p_y:.2f}) circle (5.0pt);")
        # Single continuous arc from 0 to 90 (CCW)
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({p_x:.2f}, {p_y:.2f}) ++(0:{r_wheel:.2f}) arc (0:90:{r_wheel:.2f});")

    elif action_type == "rev_turn_l_45":
        # Reversing left turn 45 deg (left wheel moves in reverse, pinned right wheel)
        scale_val = 1.35
        d_w = 1.20
        r_wheel = 2.40
        p_x, p_y = 3.60, 5.30
        lines.extend(robot_marker(p_x - d_w, p_y, 0.0, ghost=False, scale=scale_val))
        dest_cx = p_x - d_w * math.cos(math.radians(45))
        dest_cy = p_y - d_w * math.sin(math.radians(45))
        lines.extend(robot_marker(dest_cx, dest_cy, 45.0, ghost=True, scale=scale_val))
        # Pivot dot at right wheel
        lines.append(rf"    \fill[primaryDark] ({p_x:.2f}, {p_y:.2f}) circle (2.8pt);")
        lines.append(rf"    \draw[primaryDark, line width=0.8pt] ({p_x:.2f}, {p_y:.2f}) circle (5.0pt);")
        # Single continuous arc from 180 to 225 (CCW backward)
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({p_x:.2f}, {p_y:.2f}) ++(180:{r_wheel:.2f}) arc (180:225:{r_wheel:.2f});")

    elif action_type == "rev_turn_l_90":
        # Reversing left turn 90 deg (left wheel reverses around pinned right wheel)
        scale_val = 1.35
        d_w = 1.20
        r_wheel = 2.40
        p_x, p_y = 3.60, 5.50
        lines.extend(robot_marker(p_x - d_w, p_y, 0.0, ghost=False, scale=scale_val))
        dest_cx = p_x
        dest_cy = p_y - d_w
        lines.extend(robot_marker(dest_cx, dest_cy, 90.0, ghost=True, scale=scale_val))
        # Pivot dot
        lines.append(rf"    \fill[primaryDark] ({p_x:.2f}, {p_y:.2f}) circle (2.8pt);")
        lines.append(rf"    \draw[primaryDark, line width=0.8pt] ({p_x:.2f}, {p_y:.2f}) circle (5.0pt);")
        # Single continuous arc from 180 to 270 (CCW backward)
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({p_x:.2f}, {p_y:.2f}) ++(180:{r_wheel:.2f}) arc (180:270:{r_wheel:.2f});")

    elif action_type == "rev_turn_r_45":
        # Reversing right turn 45 deg (right wheel moves in reverse, pinned left wheel)
        scale_val = 1.35
        d_w = 1.20
        r_wheel = 2.40
        p_x, p_y = 2.00, 5.30
        lines.extend(robot_marker(p_x + d_w, p_y, 0.0, ghost=False, scale=scale_val))
        dest_cx = p_x + d_w * math.cos(math.radians(-45))
        dest_cy = p_y + d_w * math.sin(math.radians(-45))
        lines.extend(robot_marker(dest_cx, dest_cy, -45.0, ghost=True, scale=scale_val))
        # Pivot dot at left wheel
        lines.append(rf"    \fill[primaryDark] ({p_x:.2f}, {p_y:.2f}) circle (2.8pt);")
        lines.append(rf"    \draw[primaryDark, line width=0.8pt] ({p_x:.2f}, {p_y:.2f}) circle (5.0pt);")
        # Single continuous arc from 360 to 315 (CW backward)
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({p_x:.2f}, {p_y:.2f}) ++(0:{r_wheel:.2f}) arc (360:315:{r_wheel:.2f});")

    elif action_type == "rev_turn_r_90":
        # Reversing right turn 90 deg (right wheel reverses around pinned left wheel)
        scale_val = 1.35
        d_w = 1.20
        r_wheel = 2.40
        p_x, p_y = 2.00, 5.50
        lines.extend(robot_marker(p_x + d_w, p_y, 0.0, ghost=False, scale=scale_val))
        dest_cx = p_x
        dest_cy = p_y - d_w
        lines.extend(robot_marker(dest_cx, dest_cy, -90.0, ghost=True, scale=scale_val))
        # Pivot dot
        lines.append(rf"    \fill[primaryDark] ({p_x:.2f}, {p_y:.2f}) circle (2.8pt);")
        lines.append(rf"    \draw[primaryDark, line width=0.8pt] ({p_x:.2f}, {p_y:.2f}) circle (5.0pt);")
        # Single continuous arc from 360 to 270 (CW backward)
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({p_x:.2f}, {p_y:.2f}) ++(360:{r_wheel:.2f}) arc (360:270:{r_wheel:.2f});")

    elif action_type == "pivot_r_90":
        # 90 Pivot Right about geometric center (cx, 4.35)
        cy = 4.35
        scale_val = 1.35
        lines.extend(robot_marker(cx, cy, 0.0, ghost=False, scale=scale_val))
        lines.extend(robot_marker(cx, cy, -90.0, ghost=True, scale=scale_val))
        lines.append(rf"    \fill[primaryDark] ({cx:.2f}, {cy:.2f}) circle (2.8pt);")
        # Single continuous arc from 135 to 45 deg (CW)
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({cx:.2f}, {cy:.2f}) ++(135:2.00) arc (135:45:2.00);")

    elif action_type == "pivot_l_90":
        # 90 Pivot Left about geometric center (cx, 4.35)
        cy = 4.35
        scale_val = 1.35
        lines.extend(robot_marker(cx, cy, 0.0, ghost=False, scale=scale_val))
        lines.extend(robot_marker(cx, cy, 90.0, ghost=True, scale=scale_val))
        lines.append(rf"    \fill[primaryDark] ({cx:.2f}, {cy:.2f}) circle (2.8pt);")
        # Single continuous arc from 45 to 135 deg (CCW)
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({cx:.2f}, {cy:.2f}) ++(45:2.00) arc (45:135:2.00);")

    elif action_type == "pivot_180":
        # 180 Pivot about geometric center (cx, 4.35)
        cy = 4.35
        scale_val = 1.35
        lines.extend(robot_marker(cx, cy + 0.45, 0.0, ghost=False, scale=scale_val))
        lines.extend(robot_marker(cx, cy - 0.45, 180.0, ghost=True, scale=scale_val))
        lines.append(rf"    \fill[primaryDark] ({cx:.2f}, {cy:.2f}) circle (2.8pt);")
        # Single semi-circular arrow looping 180 deg CW from left over top to right/down
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({cx:.2f}, {cy:.2f}) ++(170:2.15) arc (170:-10:2.15);")

    return lines


def generate_action_card_tex(card: dict) -> str:
    """Produces the full TikZ code for a single Action Card."""
    code = card["Code"]
    left_cost = int(card["LeftCost"])
    right_cost = int(card["RightCost"])
    action_type = card["Type"]

    esc_code = escape_latex(code)

    lines = [
        r"\begin{tikzpicture}[x=1cm, y=1cm]",
        rf"  \node (cardbleed) [rectangle, minimum width={CARD_OUTER_W_CM:.2f}cm, minimum height={CARD_OUTER_H_CM:.2f}cm, fill=white] at ({CARD_OUTER_W_CM/2:.2f}, {CARD_OUTER_H_CM/2:.2f}) {{}};",
        rf"  \useasboundingbox (0,0) rectangle ({CARD_OUTER_W_CM:.2f}, {CARD_OUTER_H_CM:.2f});",
        rf"  \clip (0,0) rectangle ({CARD_OUTER_W_CM:.2f}, {CARD_OUTER_H_CM:.2f});",
        r"  \providecolor{arenaRed}{HTML}{C53030}",
        r"  \providecolor{primaryDark}{HTML}{1A202C}",
        rf"  \begin{{scope}}[shift={{({BLEED_OFFSET_X:.3f}, {BLEED_OFFSET_Y:.3f})}}]",
        rf"    \draw [draw=gray!35, line width=0.4pt, rounded corners=2.0mm] (0.00, 0.00) rectangle ({CARD_SAFE_W_CM:.2f}, {CARD_SAFE_H_CM:.2f});",
    ]

    # TOP LEFT: Code only (no motion description underneath, no action badge top-right)
    lines.append(
        rf"    \node [anchor=north west, inner sep=0pt] at (0.35, 8.35) {{\fontsize{{22pt}}{{24pt}}\selectfont\sffamily\bfseries\color{{textdark}} {esc_code}}};"
    )

    # CENTER DIAGRAM
    lines.extend(build_action_diagram(action_type))

    # BOTTOM LEFT: Left Cost (no "DRIVE")
    lines.append(
        rf"    \node [anchor=south west, align=left, inner sep=0pt] at (0.35, 0.35) {{"
        rf"      \begin{{tabular}}{{@{{}}l@{{}}}}"
        rf"        {{\fontsize{{24pt}}{{26pt}}\selectfont\sffamily\bfseries\color{{textdark}} {left_cost}}} \\[-2pt]"
        rf"        {{\fontsize{{7.5pt}}{{8.5pt}}\selectfont\sffamily\bfseries\color{{textdark!60}} LEFT}}"
        rf"      \end{{tabular}}"
        rf"    }};"
    )

    # BOTTOM RIGHT: Right Cost (no "DRIVE")
    lines.append(
        rf"    \node [anchor=south east, align=right, inner sep=0pt] at (5.25, 0.35) {{"
        rf"      \begin{{tabular}}{{@{{}}r@{{}}}}"
        rf"        {{\fontsize{{24pt}}{{26pt}}\selectfont\sffamily\bfseries\color{{textdark}} {right_cost}}} \\[-2pt]"
        rf"        {{\fontsize{{7.5pt}}{{8.5pt}}\selectfont\sffamily\bfseries\color{{textdark!60}} RIGHT}}"
        rf"      \end{{tabular}}"
        rf"    }};"
    )

    # FOOTER: Copyright & Card category
    lines.append(
        r"    \node [anchor=south, inner sep=0pt] at (2.80, 0.18) {\fontsize{4.5pt}{5.5pt}\selectfont\sffamily\color{textdark!40}Robot Battles \textbullet{} Movement Action Card};"
    )

    lines.append(r"  \end{scope}")
    lines.append(r"\end{tikzpicture}%")
    return "\n".join(lines) + "\n"


def process_action_cards(csv_path: Path) -> list[dict]:
    cards = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Code") and row["Code"].strip():
                cards.append(row)
    return cards


def main():
    parser = argparse.ArgumentParser(description="Generate Action Card TikZ .tex files.")
    parser.add_argument("--output-dir", type=Path, default=CARD_OUTPUT_DIR, help="Output directory for card .tex files")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_file = CARD_DEFS_DIR / "action_cards.csv"
    if not csv_file.is_file():
        sys.exit(f"Error: {csv_file} not found.")

    cards = process_action_cards(csv_file)
    print(f"Loaded {len(cards)} action cards from {csv_file.name}")

    manifest_entries = []
    for card in cards:
        code = card["Code"]
        safe_name = "Action_" + sanitize_filename(code)
        tex_path = args.output_dir / f"{safe_name}.tex"
        content = generate_action_card_tex(card)
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(content)
        manifest_entries.append(f"card/{safe_name}.tex")
        print(f"  Generated {tex_path.name}")

    manifest_csv = BUILD_DIR / "action_cards.csv"
    with open(manifest_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for entry in manifest_entries:
            writer.writerow([entry])
    print(f"\nWrote {len(manifest_entries)} entries to {manifest_csv}")


if __name__ == "__main__":
    main()
