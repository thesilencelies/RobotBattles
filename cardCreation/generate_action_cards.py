#!/usr/bin/env python3
"""
generate_action_cards.py

Generates TikZ LaTeX files for Robot Battles movement action cards into
cardCreation/build/card/Action_<Name>.tex, and records their filenames in
cardCreation/build/action_cards.csv.

Follows the card dimensions (56x87mm with 2.5mm bleed -> 61x92mm) and styles
used throughout the game, implementing the diagrams sketched by the user.
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


def build_action_diagram(action_type: str) -> list[str]:
    """Generates TikZ code for the central motion diagram."""
    lines = []
    # Style definitions
    # Red robot baseline: 2.0cm wide horizontal line with triangular nose
    # Base robot macro in TikZ scope:
    # A robot at (x, y) with angle theta:
    # \begin{scope}[shift={(x,y)}, rotate=theta] ... \end{scope}

    def robot_marker(x: float, y: float, angle: float = 0.0, ghost: bool = False, label: str = "") -> list[str]:
        m_lines = [rf"    \begin{{scope}}[shift={{({x:.2f}, {y:.2f})}}, rotate={angle:.1f}]"]
        if ghost:
            m_lines.append(r"      \fill[gray!40] (-0.28, 0) -- (0, 0.38) -- (0.28, 0) -- cycle;")
            m_lines.append(r"      \draw[draw=gray!60, dashed, line width=2.2pt, rounded corners=1pt] (-1.00, 0) -- (1.00, 0);")
            m_lines.append(r"      \fill[gray!50] (-0.95, -0.16) rectangle (-0.75, 0.16);")
            m_lines.append(r"      \fill[gray!50] ( 0.75, -0.16) rectangle ( 0.95, 0.16);")
        else:
            m_lines.append(r"      \fill[arenaRed] (-0.32, 0) -- (0, 0.44) -- (0.32, 0) -- cycle;")
            m_lines.append(r"      \draw[draw=arenaRed, line width=3.4pt, rounded corners=1.2pt] (-1.00, 0) -- (1.00, 0);")
            m_lines.append(r"      \fill[primaryDark] (-0.96, -0.18) rectangle (-0.74, 0.18);")
            m_lines.append(r"      \fill[primaryDark] ( 0.74, -0.18) rectangle ( 0.96, 0.18);")
        if label:
            m_lines.append(rf"      \node[font=\fontsize{{5}}{{6}}\selectfont\sffamily\bfseries, text=textdark!60] at (0, -0.32) {{{label}}};")
        m_lines.append(r"    \end{scope}")
        return m_lines

    # Arrowhead style
    arrow_tip = r"-{Triangle[width=3.6mm,length=4.2mm]}"
    arrow_line = r"line width=2.4pt, draw=primaryDark"

    cx = 2.80

    if action_type == "wait":
        # Robot in the center with a stationary symbol
        cy = 4.40
        lines.extend(robot_marker(cx, cy, 0.0, ghost=False))
        # Halo / pause icon
        lines.append(rf"    \draw[draw=primaryDark!30, dashed, line width=1.0pt] ({cx:.2f}, {cy:.2f}) circle (1.30cm);")
        lines.append(rf"    \fill[primaryDark!80] ({cx - 0.22:.2f}, {cy + 1.10:.2f}) rectangle ({cx - 0.08:.2f}, {cy + 1.60:.2f});")
        lines.append(rf"    \fill[primaryDark!80] ({cx + 0.08:.2f}, {cy + 1.10:.2f}) rectangle ({cx + 0.22:.2f}, {cy + 1.60:.2f});")
        lines.append(rf"    \node[anchor=center, font=\fontsize{{8}}{{9}}\selectfont\sffamily\bfseries, text=primaryDark!75] at ({cx:.2f}, {cy - 0.90:.2f}) {{STATIONARY}};")

    elif action_type == "forward_1":
        # Base at y = 3.20, moves up 1 step to y = 5.30
        y_start = 3.20
        y_end = 5.30
        lines.extend(robot_marker(cx, y_start, 0.0, ghost=False))
        lines.extend(robot_marker(cx, y_end, 0.0, ghost=True))
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({cx:.2f}, {y_start + 0.44:.2f}) -- ({cx:.2f}, {y_end - 0.08:.2f});")

    elif action_type == "forward_2":
        # Base at y = 2.60, moves up 2 steps to y = 6.00
        y_start = 2.60
        y_mid = 4.30
        y_end = 6.00
        lines.extend(robot_marker(cx, y_start, 0.0, ghost=False))
        lines.extend(robot_marker(cx, y_end, 0.0, ghost=True))
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({cx:.2f}, {y_start + 0.44:.2f}) -- ({cx:.2f}, {y_mid:.2f});")
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({cx:.2f}, {y_mid:.2f}) -- ({cx:.2f}, {y_end - 0.08:.2f});")

    elif action_type == "forward_3":
        # Base at y = 2.30, moves up 3 steps to y = 6.50
        y_start = 2.30
        y_step1 = 3.70
        y_step2 = 5.10
        y_end = 6.50
        lines.extend(robot_marker(cx, y_start, 0.0, ghost=False))
        lines.extend(robot_marker(cx, y_end, 0.0, ghost=True))
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({cx:.2f}, {y_start + 0.44:.2f}) -- ({cx:.2f}, {y_step1:.2f});")
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({cx:.2f}, {y_step1:.2f}) -- ({cx:.2f}, {y_step2:.2f});")
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({cx:.2f}, {y_step2:.2f}) -- ({cx:.2f}, {y_end - 0.08:.2f});")

    elif action_type == "backward_1":
        # Base at y = 5.50 (facing up), moves down 1 step to y = 3.40
        y_start = 5.50
        y_end = 3.40
        lines.extend(robot_marker(cx, y_start, 0.0, ghost=False))
        lines.extend(robot_marker(cx, y_end, 0.0, ghost=True))
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({cx:.2f}, {y_start - 0.15:.2f}) -- ({cx:.2f}, {y_end + 0.50:.2f});")

    elif action_type == "backward_2":
        # Base at y = 6.10, moves down 2 steps to y = 2.70
        y_start = 6.10
        y_mid = 4.40
        y_end = 2.70
        lines.extend(robot_marker(cx, y_start, 0.0, ghost=False))
        lines.extend(robot_marker(cx, y_end, 0.0, ghost=True))
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({cx:.2f}, {y_start - 0.15:.2f}) -- ({cx:.2f}, {y_mid:.2f});")
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({cx:.2f}, {y_mid:.2f}) -- ({cx:.2f}, {y_end + 0.50:.2f});")

    elif action_type == "backward_3":
        # Base at y = 6.50, moves down 3 steps to y = 2.30
        y_start = 6.50
        y_step1 = 5.10
        y_step2 = 3.70
        y_end = 2.30
        lines.extend(robot_marker(cx, y_start, 0.0, ghost=False))
        lines.extend(robot_marker(cx, y_end, 0.0, ghost=True))
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({cx:.2f}, {y_start - 0.15:.2f}) -- ({cx:.2f}, {y_step1:.2f});")
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({cx:.2f}, {y_step1:.2f}) -- ({cx:.2f}, {y_step2:.2f});")
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({cx:.2f}, {y_step2:.2f}) -- ({cx:.2f}, {y_end + 0.50:.2f});")

    elif action_type == "turn_r_45":
        # Right turn 45 deg around pinned right wheel
        # Base robot centered at (2.25, 3.20).
        # Right wheel is at (3.10, 3.20). Radius R = 1.70cm.
        # Left wheel at (1.40, 3.20) swings CW from 180 to 135 deg.
        p_x, p_y = 3.10, 3.20
        r_wheel = 1.70
        lines.extend(robot_marker(2.25, 3.20, 0.0, ghost=False))
        # Destination: rotated 45 deg CW (-45) around (p_x, p_y).
        # Destination center is shifted:
        # dx = -0.85 * cos(-45) = -0.601, dy = -0.85 * sin(-45) = +0.601
        dest_cx = p_x - 0.85 * math.cos(math.radians(-45))
        dest_cy = p_y - 0.85 * math.sin(math.radians(-45))
        lines.extend(robot_marker(dest_cx, dest_cy, -45.0, ghost=True))
        # Pivot dot at right wheel
        lines.append(rf"    \fill[primaryDark] ({p_x:.2f}, {p_y:.2f}) circle (2.2pt);")
        lines.append(rf"    \draw[primaryDark, line width=0.6pt] ({p_x:.2f}, {p_y:.2f}) circle (4.0pt);")
        # Arc from 180 to 135 (CW)
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({p_x:.2f}, {p_y:.2f}) ++(180:{r_wheel:.2f}) arc (180:135:{r_wheel:.2f});")

    elif action_type == "turn_r_90":
        # Right turn 90 deg around pinned right wheel
        p_x, p_y = 3.10, 3.00
        r_wheel = 1.70
        lines.extend(robot_marker(2.25, 3.00, 0.0, ghost=False))
        dest_cx = p_x
        dest_cy = p_y + 0.85
        lines.extend(robot_marker(dest_cx, dest_cy, -90.0, ghost=True))
        # Pivot dot
        lines.append(rf"    \fill[primaryDark] ({p_x:.2f}, {p_y:.2f}) circle (2.2pt);")
        lines.append(rf"    \draw[primaryDark, line width=0.6pt] ({p_x:.2f}, {p_y:.2f}) circle (4.0pt);")
        # Arc from 180 to 90 (CW) with midpoint chevron
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({p_x:.2f}, {p_y:.2f}) ++(180:{r_wheel:.2f}) arc (180:135:{r_wheel:.2f});")
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({p_x:.2f}, {p_y:.2f}) ++(135:{r_wheel:.2f}) arc (135:90:{r_wheel:.2f});")

    elif action_type == "turn_l_45":
        # Left turn 45 deg around pinned left wheel
        p_x, p_y = 2.50, 3.20
        r_wheel = 1.70
        lines.extend(robot_marker(3.35, 3.20, 0.0, ghost=False))
        dest_cx = p_x + 0.85 * math.cos(math.radians(45))
        dest_cy = p_y + 0.85 * math.sin(math.radians(45))
        lines.extend(robot_marker(dest_cx, dest_cy, 45.0, ghost=True))
        # Pivot dot at left wheel
        lines.append(rf"    \fill[primaryDark] ({p_x:.2f}, {p_y:.2f}) circle (2.2pt);")
        lines.append(rf"    \draw[primaryDark, line width=0.6pt] ({p_x:.2f}, {p_y:.2f}) circle (4.0pt);")
        # Arc from 0 to 45 (CCW)
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({p_x:.2f}, {p_y:.2f}) ++(0:{r_wheel:.2f}) arc (0:45:{r_wheel:.2f});")

    elif action_type == "turn_l_90":
        # Left turn 90 deg around pinned left wheel
        p_x, p_y = 2.50, 3.00
        r_wheel = 1.70
        lines.extend(robot_marker(3.35, 3.00, 0.0, ghost=False))
        dest_cx = p_x
        dest_cy = p_y + 0.85
        lines.extend(robot_marker(dest_cx, dest_cy, 90.0, ghost=True))
        # Pivot dot
        lines.append(rf"    \fill[primaryDark] ({p_x:.2f}, {p_y:.2f}) circle (2.2pt);")
        lines.append(rf"    \draw[primaryDark, line width=0.6pt] ({p_x:.2f}, {p_y:.2f}) circle (4.0pt);")
        # Arc from 0 to 90 (CCW) with midpoint chevron
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({p_x:.2f}, {p_y:.2f}) ++(0:{r_wheel:.2f}) arc (0:45:{r_wheel:.2f});")
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({p_x:.2f}, {p_y:.2f}) ++(45:{r_wheel:.2f}) arc (45:90:{r_wheel:.2f});")

    elif action_type == "rev_turn_l_45":
        # Reversing left turn 45 deg (left wheel moves in reverse, pinned right wheel)
        p_x, p_y = 3.10, 5.20
        r_wheel = 1.70
        lines.extend(robot_marker(2.25, 5.20, 0.0, ghost=False))
        dest_cx = p_x - 0.85 * math.cos(math.radians(45))
        dest_cy = p_y - 0.85 * math.sin(math.radians(45))
        lines.extend(robot_marker(dest_cx, dest_cy, 45.0, ghost=True))
        # Pivot dot at right wheel
        lines.append(rf"    \fill[primaryDark] ({p_x:.2f}, {p_y:.2f}) circle (2.2pt);")
        lines.append(rf"    \draw[primaryDark, line width=0.6pt] ({p_x:.2f}, {p_y:.2f}) circle (4.0pt);")
        # Left wheel swings backward-left from 180 to 225 deg (CCW backward)
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({p_x:.2f}, {p_y:.2f}) ++(180:{r_wheel:.2f}) arc (180:225:{r_wheel:.2f});")

    elif action_type == "rev_turn_l_90":
        # Reversing left turn 90 deg (left wheel reverses around pinned right wheel)
        p_x, p_y = 3.10, 5.40
        r_wheel = 1.70
        lines.extend(robot_marker(2.25, 5.40, 0.0, ghost=False))
        dest_cx = p_x
        dest_cy = p_y - 0.85
        lines.extend(robot_marker(dest_cx, dest_cy, 90.0, ghost=True))
        # Pivot dot
        lines.append(rf"    \fill[primaryDark] ({p_x:.2f}, {p_y:.2f}) circle (2.2pt);")
        lines.append(rf"    \draw[primaryDark, line width=0.6pt] ({p_x:.2f}, {p_y:.2f}) circle (4.0pt);")
        # Left wheel swings backward from 180 to 270 deg (CCW backward)
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({p_x:.2f}, {p_y:.2f}) ++(180:{r_wheel:.2f}) arc (180:225:{r_wheel:.2f});")
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({p_x:.2f}, {p_y:.2f}) ++(225:{r_wheel:.2f}) arc (225:270:{r_wheel:.2f});")

    elif action_type == "rev_turn_r_45":
        # Reversing right turn 45 deg (right wheel moves in reverse, pinned left wheel)
        p_x, p_y = 2.50, 5.20
        r_wheel = 1.70
        lines.extend(robot_marker(3.35, 5.20, 0.0, ghost=False))
        dest_cx = p_x + 0.85 * math.cos(math.radians(-45))
        dest_cy = p_y + 0.85 * math.sin(math.radians(-45))
        lines.extend(robot_marker(dest_cx, dest_cy, -45.0, ghost=True))
        # Pivot dot at left wheel
        lines.append(rf"    \fill[primaryDark] ({p_x:.2f}, {p_y:.2f}) circle (2.2pt);")
        lines.append(rf"    \draw[primaryDark, line width=0.6pt] ({p_x:.2f}, {p_y:.2f}) circle (4.0pt);")
        # Right wheel swings backward-right from 0 to -45 (315) deg (CW backward)
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({p_x:.2f}, {p_y:.2f}) ++(0:{r_wheel:.2f}) arc (360:315:{r_wheel:.2f});")

    elif action_type == "rev_turn_r_90":
        # Reversing right turn 90 deg (right wheel reverses around pinned left wheel)
        p_x, p_y = 2.50, 5.40
        r_wheel = 1.70
        lines.extend(robot_marker(3.35, 5.40, 0.0, ghost=False))
        dest_cx = p_x
        dest_cy = p_y - 0.85
        lines.extend(robot_marker(dest_cx, dest_cy, -90.0, ghost=True))
        # Pivot dot
        lines.append(rf"    \fill[primaryDark] ({p_x:.2f}, {p_y:.2f}) circle (2.2pt);")
        lines.append(rf"    \draw[primaryDark, line width=0.6pt] ({p_x:.2f}, {p_y:.2f}) circle (4.0pt);")
        # Right wheel swings backward from 360 to 270 deg (CW backward)
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({p_x:.2f}, {p_y:.2f}) ++(360:{r_wheel:.2f}) arc (360:315:{r_wheel:.2f});")
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({p_x:.2f}, {p_y:.2f}) ++(315:{r_wheel:.2f}) arc (315:270:{r_wheel:.2f});")

    elif action_type == "pivot_r_90":
        # 90 Pivot Right about geometric center (cx, 4.40)
        cy = 4.40
        lines.extend(robot_marker(cx, cy, 0.0, ghost=False))
        lines.extend(robot_marker(cx, cy, -90.0, ghost=True))
        lines.append(rf"    \fill[primaryDark] ({cx:.2f}, {cy:.2f}) circle (2.2pt);")
        # Arc from 130 to 40 deg (CW)
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({cx:.2f}, {cy:.2f}) ++(135:1.35) arc (135:45:1.35);")

    elif action_type == "pivot_l_90":
        # 90 Pivot Left about geometric center (cx, 4.40)
        cy = 4.40
        lines.extend(robot_marker(cx, cy, 0.0, ghost=False))
        lines.extend(robot_marker(cx, cy, 90.0, ghost=True))
        lines.append(rf"    \fill[primaryDark] ({cx:.2f}, {cy:.2f}) circle (2.2pt);")
        # Arc from 45 to 135 deg (CCW)
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({cx:.2f}, {cy:.2f}) ++(45:1.35) arc (45:135:1.35);")

    elif action_type == "pivot_180":
        # 180 Pivot about geometric center (cx, 4.40)
        # Matches media_1793618845832.png
        cy = 4.40
        lines.extend(robot_marker(cx, cy + 0.35, 0.0, ghost=False))
        lines.extend(robot_marker(cx, cy - 0.35, 180.0, ghost=True))
        lines.append(rf"    \fill[primaryDark] ({cx:.2f}, {cy:.2f}) circle (2.2pt);")
        # Semi-circular arrow looping 180 deg CW from left over top to right/down
        lines.append(rf"    \draw[{arrow_tip}, {arrow_line}] ({cx:.2f}, {cy:.2f}) ++(170:1.45) arc (170:-10:1.45);")

    return lines


def generate_action_card_tex(card: dict) -> str:
    """Produces the full TikZ code for a single Action Card."""
    code = card["Code"]
    motion = card["Motion"]
    left_cost = int(card["LeftCost"])
    right_cost = int(card["RightCost"])
    action_type = card["Type"]

    esc_code = escape_latex(code)
    esc_motion = escape_latex(motion)

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

    # TOP LEFT: Code & Motion Text
    lines.append(
        rf"    \node [anchor=north west, inner sep=0pt] at (0.35, 8.35) {{\fontsize{{18pt}}{{20pt}}\selectfont\sffamily\bfseries\color{{textdark}} {esc_code}}};"
    )
    lines.append(
        rf"    \node [anchor=north west, inner sep=0pt] at (0.35, 7.65) {{\fontsize{{7.5pt}}{{9pt}}\selectfont\sffamily\bfseries\color{{textdark!70}} {esc_motion}}};"
    )

    # TOP RIGHT: ACTION BADGE
    lines.append(
        r"    \node [anchor=north east, inner sep=0pt] at (5.25, 8.35) {\keywordbadge{chevronpurple}{ACTION}};"
    )

    # CENTER DIAGRAM
    lines.extend(build_action_diagram(action_type))

    # BOTTOM LEFT: Left Drive Cost
    lines.append(
        rf"    \node [anchor=south west, align=left, inner sep=0pt] at (0.35, 0.35) {{"
        rf"      \begin{{tabular}}{{@{{}}l@{{}}}}"
        rf"        {{\fontsize{{24pt}}{{26pt}}\selectfont\sffamily\bfseries\color{{textdark}} {left_cost}}} \\[-2pt]"
        rf"        {{\fontsize{{6.5pt}}{{7.5pt}}\selectfont\sffamily\bfseries\color{{textdark!60}} LEFT DRIVE}}"
        rf"      \end{{tabular}}"
        rf"    }};"
    )

    # BOTTOM RIGHT: Right Drive Cost
    lines.append(
        rf"    \node [anchor=south east, align=right, inner sep=0pt] at (5.25, 0.35) {{"
        rf"      \begin{{tabular}}{{@{{}}r@{{}}}}"
        rf"        {{\fontsize{{24pt}}{{26pt}}\selectfont\sffamily\bfseries\color{{textdark}} {right_cost}}} \\[-2pt]"
        rf"        {{\fontsize{{6.5pt}}{{7.5pt}}\selectfont\sffamily\bfseries\color{{textdark!60}} RIGHT DRIVE}}"
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
