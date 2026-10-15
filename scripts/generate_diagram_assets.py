#!/usr/bin/env python3
"""
generate_diagram_assets.py

Generates transparent high-resolution PNG sprites for robot miniatures and assets
to be included in native LaTeX / TikZ diagrams in rules/combat_robotics_game.tex.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import List, Optional, Tuple

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib_diagrams")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches

OUTPUT_DIR = Path("rules/images")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Palette
DARK_NAVY = "#1A365D"
STEEL_BLUE = "#2B6CB0"
LIGHT_BLUE = "#3B82F6"
CRIMSON = "#C53030"
LIGHT_RED = "#FEE2E2"
AMBER_NOTE = "#DD6B20"
WALL_BLACK = "#0F172A"
NIGHTWING_INDIGO = "#312E81"
WHEEL_COLOR = "#334155"


def create_miniature(
    filename: str,
    chassis: str = "Triangle",
    color: str = LIGHT_BLUE,
    name: str = "A",
    weapon: Optional[str] = "Line",
    forks: bool = False,
    ghost: bool = False,
    size: int = 500,
    heading_deg: float = 0.0,
) -> None:
    """Renders a single robot miniature onto a transparent PNG canvas."""
    fig, ax = plt.subplots(figsize=(3.5, 3.5), dpi=size / 3.5)
    fig.patch.set_alpha(0.0)
    ax.patch.set_alpha(0.0)

    # Frame bounds: centered at (0, 0), span -55 to 55
    span = 55.0
    ax.set_xlim(-span, span)
    ax.set_ylim(-span, span)
    ax.set_aspect("equal")
    ax.axis("off")

    rad = math.radians(heading_deg)
    alpha = 0.38 if ghost else 1.0

    def rot(x: float, y: float) -> Tuple[float, float]:
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        return (cos_a * x - sin_a * y, sin_a * x + cos_a * y)

    chassis_lower = chassis.lower()
    if chassis_lower in ("triangle", "wedge"):
        base_poly = [
            (0.0, 22.0),
            (18.0, 6.0),
            (18.0, -18.0),
            (-18.0, -18.0),
            (-18.0, 6.0),
        ]
        wheel_offsets = [(-20.0, -2.0), (20.0, -2.0)]
    elif chassis_lower == "wide":
        base_poly = [
            (-24.0, 14.0),
            (24.0, 14.0),
            (24.0, -14.0),
            (-24.0, -14.0),
        ]
        wheel_offsets = [(-26.5, -2.0), (26.5, -2.0)]
    else:  # 'square'
        base_poly = [
            (-16.0, 18.0),
            (16.0, 18.0),
            (16.0, -18.0),
            (-16.0, -18.0),
        ]
        wheel_offsets = [(-19.0, -2.0), (19.0, -2.0)]

    # 1. Wheels
    for wx_l, wy_l in wheel_offsets:
        w_pts = [
            (wx_l - 2.8, wy_l - 7.5),
            (wx_l + 2.8, wy_l - 7.5),
            (wx_l + 2.8, wy_l + 7.5),
            (wx_l - 2.8, wy_l + 7.5),
        ]
        w_rot = [rot(px, py) for px, py in w_pts]
        ax.add_patch(
            patches.Polygon(
                w_rot,
                closed=True,
                facecolor=WHEEL_COLOR if not ghost else "#94A3B8",
                edgecolor=WALL_BLACK if not ghost else "#64748B",
                linewidth=1.2,
                alpha=alpha,
                zorder=2,
            )
        )

    # 2. Chassis body
    c_rot = [rot(px, py) for px, py in base_poly]
    ax.add_patch(
        patches.Polygon(
            c_rot,
            closed=True,
            facecolor=color if not ghost else "#E2E8F0",
            edgecolor=WALL_BLACK if not ghost else "#64748B",
            linewidth=2.2 if not ghost else 1.5,
            linestyle="--" if ghost else "-",
            alpha=alpha,
            zorder=3,
        )
    )

    # 3. Direction Indicator Arrow on chassis
    if not ghost:
        tip_y = 17.0 if chassis_lower == "triangle" else (13.0 if chassis_lower == "wide" else 15.0)
        arrow_pts = [
            rot(0.0, tip_y),
            rot(-4.5, tip_y - 7.0),
            rot(4.5, tip_y - 7.0),
        ]
        ax.add_patch(
            patches.Polygon(
                arrow_pts,
                closed=True,
                facecolor="#FFFFFF",
                edgecolor="none",
                alpha=0.85,
                zorder=4,
            )
        )

    # 4. Forks (if enabled, e.g. Nightwing)
    if forks and not ghost:
        # Narrow prongs matching the updated template_prongs icon
        py = 14.0 if chassis_lower == "wide" else 12.0
        span_f = 17.0
        pw = 3.6  # Narrow prongs
        ph = 18.0
        for fx in [-span_f, span_f]:
            pr_pts = [
                (fx - pw / 2, py),
                (fx + pw / 2, py),
                (fx + pw / 2, py + ph),
                (fx - pw / 2, py + ph),
            ]
            ax.add_patch(
                patches.Polygon(
                    [rot(px, py_c) for px, py_c in pr_pts],
                    closed=True,
                    facecolor="#475569",
                    edgecolor=WALL_BLACK,
                    linewidth=1.2,
                    zorder=4,
                )
            )
            # Wedge tip
            tip_pts = [
                (fx - pw / 2, py + ph - 6.0),
                (fx + pw / 2, py + ph - 6.0),
                (fx + pw / 2, py + ph),
                (fx - pw / 2, py + ph),
            ]
            ax.add_patch(
                patches.Polygon(
                    [rot(px, py_c) for px, py_c in tip_pts],
                    closed=True,
                    facecolor=AMBER_NOTE,
                    edgecolor="#9A3412",
                    linewidth=1.0,
                    zorder=5,
                )
            )

    # 5. Weapon Templates
    if weapon and not ghost:
        w_name = weapon.strip()
        if w_name == "Circle":
            disc_y = 14.0 if chassis_lower == "triangle" else (12.0 if chassis_lower == "wide" else 13.0)
            dc = rot(0.0, disc_y)
            disc = patches.Circle(
                dc,
                radius=14.0 if not forks else 11.0,
                facecolor=LIGHT_RED,
                edgecolor=CRIMSON,
                linewidth=2.5,
                alpha=0.95,
                zorder=6,
            )
            ax.add_patch(disc)
            pin = patches.Circle(dc, radius=3.2, facecolor=WALL_BLACK, zorder=7)
            ax.add_patch(pin)

        elif w_name == "Large Circle":
            disc_y = 12.0
            dc = rot(0.0, disc_y)
            disc = patches.Circle(
                dc,
                radius=21.0,
                facecolor="#FEF2F2",
                edgecolor=CRIMSON,
                linewidth=2.8,
                alpha=0.92,
                zorder=6,
            )
            ax.add_patch(disc)
            inner_ring = patches.Circle(
                dc,
                radius=15.5,
                facecolor="none",
                edgecolor=CRIMSON,
                linewidth=1.5,
                linestyle="--",
                zorder=7,
            )
            ax.add_patch(inner_ring)
            pin = patches.Circle(dc, radius=4.0, facecolor=WALL_BLACK, zorder=8)
            ax.add_patch(pin)

        elif w_name == "Line":
            line_y = 14.0 if chassis_lower == "triangle" else 13.0
            lw = 6.5
            lh = 22.0
            # Base black bar
            l_pts = [
                (-lw / 2, line_y - 4.0),
                (lw / 2, line_y - 4.0),
                (lw / 2, line_y + lh - 4.0),
                (-lw / 2, line_y + lh - 4.0),
            ]
            ax.add_patch(
                patches.Polygon(
                    [rot(px, py) for px, py in l_pts],
                    closed=True,
                    facecolor=WALL_BLACK,
                    edgecolor=WALL_BLACK,
                    linewidth=1.0,
                    zorder=6,
                )
            )
            # Active red front half
            act_pts = [
                (-lw / 2, line_y + 7.0),
                (lw / 2, line_y + 7.0),
                (lw / 2, line_y + lh - 4.0),
                (-lw / 2, line_y + lh - 4.0),
            ]
            ax.add_patch(
                patches.Polygon(
                    [rot(px, py) for px, py in act_pts],
                    closed=True,
                    facecolor=CRIMSON,
                    edgecolor="#7F1D1D",
                    linewidth=1.2,
                    zorder=7,
                )
            )

        elif w_name == "Prongs":
            py = 13.0
            span_p = 15.0
            pw = 4.0  # Narrow prongs
            ph = 20.0
            # Base bar
            base_pts = [
                (-span_p - pw, py - 2.0),
                (span_p + pw, py - 2.0),
                (span_p + pw, py + 4.0),
                (-span_p - pw, py + 4.0),
            ]
            ax.add_patch(
                patches.Polygon(
                    [rot(px, py_c) for px, py_c in base_pts],
                    closed=True,
                    facecolor=WALL_BLACK,
                    edgecolor=WALL_BLACK,
                    linewidth=1.0,
                    zorder=6,
                )
            )
            for px_c in [-span_p, span_p]:
                pr_pts = [
                    (px_c - pw / 2, py + 4.0),
                    (px_c + pw / 2, py + 4.0),
                    (px_c + pw / 2, py + ph),
                    (px_c - pw / 2, py + ph),
                ]
                ax.add_patch(
                    patches.Polygon(
                        [rot(px, py_c) for px, py_c in pr_pts],
                        closed=True,
                        facecolor=WALL_BLACK,
                        edgecolor=WALL_BLACK,
                        linewidth=1.0,
                        zorder=6,
                    )
                )
                tip_pts = [
                    (px_c - pw / 2, py + ph - 8.0),
                    (px_c + pw / 2, py + ph - 8.0),
                    (px_c + pw / 2, py + ph),
                    (px_c - pw / 2, py + ph),
                ]
                ax.add_patch(
                    patches.Polygon(
                        [rot(px, py_c) for px, py_c in tip_pts],
                        closed=True,
                        facecolor=CRIMSON,
                        edgecolor="#7F1D1D",
                        linewidth=1.2,
                        zorder=7,
                    )
                )

    # 6. Bot Label
    if not ghost:
        lbl = f"Bot {name}" if len(name) == 1 else name
        ax.text(
            0.0,
            -3.0 if chassis_lower != "wide" else 0.0,
            lbl,
            color="#FFFFFF",
            fontsize=13.0,
            fontweight="bold",
            ha="center",
            va="center",
            zorder=9,
        )

    out_file = OUTPUT_DIR / filename
    plt.savefig(out_file, transparent=True, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    print(f"Generated sprite: {out_file}")


def main():
    print("Generating miniature robot sprites for TikZ diagrams...")

    # Triangle robots (Bot A)
    create_miniature("mini_bot_triangle_line.png", chassis="Triangle", color=LIGHT_BLUE, name="A", weapon="Line")
    create_miniature("mini_bot_triangle_circle.png", chassis="Triangle", color=LIGHT_BLUE, name="A", weapon="Circle")
    create_miniature("mini_bot_ghost_triangle_line.png", chassis="Triangle", color=LIGHT_BLUE, name="A", weapon="Line", ghost=True)

    # Square robots (Bot B)
    create_miniature("mini_bot_square_circle.png", chassis="Square", color=CRIMSON, name="B", weapon="Circle")
    create_miniature("mini_bot_square_large_circle.png", chassis="Square", color=CRIMSON, name="B", weapon="Large Circle")
    create_miniature("mini_bot_square_line.png", chassis="Square", color=AMBER_NOTE, name="B", weapon="Line")
    create_miniature("mini_bot_ghost_square_circle.png", chassis="Square", color=CRIMSON, name="B", weapon="Circle", ghost=True)
    create_miniature("mini_bot_ghost_square_line.png", chassis="Square", color=AMBER_NOTE, name="B", weapon="Line", ghost=True)

    # Wide robots (Bot B & Nightwing)
    create_miniature("mini_bot_wide_line.png", chassis="Wide", color=AMBER_NOTE, name="B", weapon="Line")
    create_miniature("mini_bot_ghost_wide_line.png", chassis="Wide", color=AMBER_NOTE, name="B", weapon="Line", ghost=True)
    create_miniature("mini_bot_nightwing.png", chassis="Wide", color=NIGHTWING_INDIGO, name="A", weapon="Circle", forks=False)
    create_miniature("mini_bot_opponent_square.png", chassis="Square", color=CRIMSON, name="B", weapon="Circle")

    print("All miniature sprites generated successfully!")


if __name__ == "__main__":
    main()
