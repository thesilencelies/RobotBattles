#!/usr/bin/env python3
"""
generate_rules_diagrams.py

Generates high-resolution, publication-quality diagrams for the Robot Battles rulebook:
1. diagram_movement_straight_curve.png - Straight forward (3/3), Reverse (-2/-2), Curve Right (2/1), Curve Left flipped (1/2) with official weapon templates
2. diagram_movement_pivot_spin.png     - Pivot Fan (2/0 on locked wheel), Spin Disc (2/-2 on center) with official weapon templates
3. diagram_contact_point.png           - Contact point determination: 3 collision scenarios (weapon-weapon, one-sided, inert) + Automata Card Mapping (Vyper Spinner)
4. diagram_inert_contact.png           - Pushing match 4-step sequence with armed robots colliding shoulder-to-flank
5. diagram_active_contact.png          - Weapon strike, throw vectors, model spin, inversion flip check & wall impact
6. diagram_forks_raised.png            - Automata card layout showing forks (Nightwing Wide), positive & negative angled fork engagement, and Raised penalties

Adheres strictly to the rule that no mm conversions are shown (game units only).
Uses strictly existing chassis templates (Square, Triangle, Wide) and existing weapon templates (Circle, Large Circle, Line, Bar, Prongs).
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import List, Optional, Tuple, Union

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib_diagrams")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np

OUTPUT_DIR = Path("rules/images")

# Color Palette matching rules document
DARK_NAVY = "#1A365D"
STEEL_BLUE = "#2B6CB0"
LIGHT_BLUE = "#3B82F6"
BG_BLUE = "#EFF6FF"
CRIMSON = "#C53030"
LIGHT_RED = "#FEE2E2"
AMBER_NOTE = "#DD6B20"
BG_AMBER = "#FFFAF0"
HAZARD_YELLOW = "#EAB308"
WALL_BLACK = "#0F172A"
ARENA_FLOOR = "#FFFFFF"
GRID_COLOR = "#E2E8F0"
TEXT_DARK = "#1E293B"
TEXT_MUTED = "#64748B"
BOX_BG = "#F8FAFC"
BOX_BORDER = "#CBD5E1"
SUCCESS_GREEN = "#16A34A"


# ----------------------------------------------------------------------
# Drawing Primitives
# ----------------------------------------------------------------------

def draw_arena_background(
    ax: plt.Axes,
    xlim: Tuple[float, float],
    ylim: Tuple[float, float],
    wall_sides: Optional[List[str]] = None,
    hazard_corner: Optional[str] = None,
    show_grid: bool = True,
    start_box: Optional[Tuple[float, float, float, float]] = None,
) -> None:
    """Draws an arena subsection background with floor, grid, boundary walls, and hazard pits."""
    ax.set_facecolor(ARENA_FLOOR)
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    ax.set_aspect("equal")
    ax.axis("off")

    if show_grid:
        gx = np.arange(math.floor(xlim[0] / 20) * 20, xlim[1] + 20, 20)
        gy = np.arange(math.floor(ylim[0] / 20) * 20, ylim[1] + 20, 20)
        for x in gx:
            ax.plot([x, x], ylim, color=GRID_COLOR, linewidth=0.8, zorder=0)
        for y in gy:
            ax.plot(xlim, [y, y], color=GRID_COLOR, linewidth=0.8, zorder=0)

    if start_box:
        bx, by, bw, bh = start_box
        s_rect = patches.Rectangle(
            (bx, by), bw, bh,
            facecolor="#FEF2F2", edgecolor=CRIMSON, linewidth=2.2, zorder=1
        )
        ax.add_patch(s_rect)
        ax.text(
            bx + bw / 2, by + bh / 2, "STARTING ZONE",
            color=CRIMSON, fontsize=8, fontweight="bold",
            ha="center", va="center", alpha=0.85, zorder=1
        )

    if wall_sides:
        for side in wall_sides:
            if side == "top":
                ax.fill_between(xlim, ylim[1] - 12, ylim[1], facecolor=WALL_BLACK, zorder=10)
                ax.plot(xlim, [ylim[1] - 12, ylim[1] - 12], color=DARK_NAVY, linewidth=2.5, zorder=11)
            elif side == "bottom":
                ax.fill_between(xlim, ylim[0], ylim[0] + 12, facecolor=WALL_BLACK, zorder=10)
                ax.plot(xlim, [ylim[0] + 12, ylim[0] + 12], color=DARK_NAVY, linewidth=2.5, zorder=11)
            elif side == "left":
                ax.axvspan(xlim[0], xlim[0] + 12, facecolor=WALL_BLACK, zorder=10)
                ax.plot([xlim[0] + 12, xlim[0] + 12], ylim, color=DARK_NAVY, linewidth=2.5, zorder=11)
            elif side == "right":
                ax.axvspan(xlim[1] - 12, xlim[1], facecolor=WALL_BLACK, zorder=10)
                ax.plot([xlim[1] - 12, xlim[1] - 12], ylim, color=DARK_NAVY, linewidth=2.5, zorder=11)

    if hazard_corner:
        pw = 55
        ph = 55
        if hazard_corner == "top_left":
            px, py = xlim[0], ylim[1] - ph
        elif hazard_corner == "top_right":
            px, py = xlim[1] - pw, ylim[1] - ph
        elif hazard_corner == "bottom_left":
            px, py = xlim[0], ylim[0]
        else:
            px, py = xlim[1] - pw, ylim[0]

        hazard_rect = patches.Rectangle(
            (px, py), pw, ph,
            facecolor=HAZARD_YELLOW, edgecolor=WALL_BLACK, linewidth=2.5,
            hatch="//", zorder=9
        )
        ax.add_patch(hazard_rect)
        ax.text(
            px + pw / 2, py + ph / 2, "HAZARD PIT",
            color=WALL_BLACK, fontsize=7.5, fontweight="bold",
            ha="center", va="center", rotation=45,
            bbox=dict(boxstyle="round,pad=0.2", facecolor="#FEF08A", edgecolor="none", alpha=0.9),
            zorder=12
        )


def rotate_point(x: float, y: float, angle_rad: float, cx: float = 0.0, cy: float = 0.0) -> Tuple[float, float]:
    """Rotates point (x, y) around (cx, cy) by angle_rad."""
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    nx = cx + cos_a * (x - cx) - sin_a * (y - cy)
    ny = cy + sin_a * (x - cx) + cos_a * (y - cy)
    return (nx, ny)


def draw_robot(
    ax: plt.Axes,
    cx: float,
    cy: float,
    heading_deg: float,  # 0 deg = North (towards positive Y)
    chassis: str = "Triangle",  # "Triangle" (wedge), "Square", "Wide"
    color: str = LIGHT_BLUE,
    name: str = "A",
    weapon: Optional[str] = "Line",  # Official templates: 'Circle', 'Large Circle', 'Line', 'Bar', 'Prongs', or None
    is_inverted: bool = False,
    is_raised: bool = False,
    ghost: bool = False,
    zorder: int = 5,
    text_offset: Tuple[float, float] = (0.0, 0.0),
) -> None:
    """
    Draws a robot miniature using official chassis templates (Square, Triangle, Wide)
    and official weapon active area templates (Circle, Large Circle, Line, Bar, Prongs).
    """
    rad = math.radians(heading_deg)
    alpha = 0.35 if ghost else 1.0

    # 1. Chassis Templates (from chassis_templates.png)
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
        wheel_offsets = [(-26.0, -2.0), (26.0, -2.0)]
    else:  # 'square'
        base_poly = [
            (-16.0, 18.0),
            (16.0, 18.0),
            (16.0, -18.0),
            (-16.0, -18.0),
        ]
        wheel_offsets = [(-19.0, -2.0), (19.0, -2.0)]

    # Wheels
    for wx_l, wy_l in wheel_offsets:
        w_rect_pts = [
            (wx_l - 2.5, wy_l - 7.0),
            (wx_l + 2.5, wy_l - 7.0),
            (wx_l + 2.5, wy_l + 7.0),
            (wx_l - 2.5, wy_l + 7.0),
        ]
        world_w_pts = [rotate_point(px + cx, py + cy, rad, cx, cy) for px, py in w_rect_pts]
        w_poly = patches.Polygon(
            world_w_pts, closed=True,
            facecolor="#334155" if not ghost else "#94A3B8",
            edgecolor=WALL_BLACK, linewidth=1.0, alpha=alpha, zorder=zorder - 1
        )
        ax.add_patch(w_poly)

    world_poly = [rotate_point(px + cx, py + cy, rad, cx, cy) for px, py in base_poly]
    c_poly = patches.Polygon(
        world_poly, closed=True,
        facecolor=color if not is_inverted else "#94A3B8",
        edgecolor=WALL_BLACK if not ghost else "#64748B",
        linewidth=2.0 if not ghost else 1.2,
        linestyle="--" if ghost else "-",
        alpha=alpha, zorder=zorder
    )
    ax.add_patch(c_poly)

    # Forward direction indicator arrow on chassis
    if not ghost and not is_inverted:
        f_tip = rotate_point(cx, cy + (18.0 if chassis_lower != "triangle" else 17.0), rad, cx, cy)
        f_b1 = rotate_point(cx - 5.0, cy + 9.0, rad, cx, cy)
        f_b2 = rotate_point(cx + 5.0, cy + 9.0, rad, cx, cy)
        arrow_poly = patches.Polygon([f_tip, f_b1, f_b2], closed=True, facecolor="#FFFFFF", edgecolor="none", alpha=0.8, zorder=zorder + 1)
        ax.add_patch(arrow_poly)

    # 2. Official Weapon Templates (Circle, Large Circle, Line, Bar, Prongs)
    if weapon and not ghost and not is_inverted:
        w_name = weapon.strip()

        if w_name == "Circle":
            # Circle Template: radial active ring with center mounting pin (matches template_circle.png)
            disc_center = rotate_point(cx, cy + (12.0 if chassis_lower != "triangle" else 14.0), rad, cx, cy)
            disc_circle = patches.Circle(disc_center, radius=14.0, facecolor=LIGHT_RED, edgecolor=CRIMSON, linewidth=2.4, alpha=0.9, zorder=zorder + 2)
            ax.add_patch(disc_circle)
            pin = patches.Circle(disc_center, radius=3.2, facecolor=WALL_BLACK, zorder=zorder + 3)
            ax.add_patch(pin)

        elif w_name == "Large Circle":
            # Large Circle Template: expanded radial reach with center cutout (matches template_large_circle.png)
            disc_center = rotate_point(cx, cy + (12.0 if chassis_lower != "triangle" else 14.0), rad, cx, cy)
            disc_circle = patches.Circle(disc_center, radius=20.0, facecolor="#FEF2F2", edgecolor=CRIMSON, linewidth=2.8, alpha=0.9, zorder=zorder + 2)
            ax.add_patch(disc_circle)
            inner_ring = patches.Circle(disc_center, radius=15.0, facecolor="none", edgecolor=CRIMSON, linewidth=1.5, linestyle="--", zorder=zorder + 3)
            ax.add_patch(inner_ring)
            pin = patches.Circle(disc_center, radius=4.0, facecolor=WALL_BLACK, zorder=zorder + 4)
            ax.add_patch(pin)

        elif w_name == "Bar":
            # Bar Template: wide frontal bar with active red front zone (matches template_bar.png)
            bar_y = 14.0 if chassis_lower != "triangle" else 16.0
            bar_w = 40.0 if chassis_lower == "wide" else 32.0
            # Base black bar
            b_pts = [(-bar_w / 2, bar_y - 2.0), (bar_w / 2, bar_y - 2.0), (bar_w / 2, bar_y + 6.0), (-bar_w / 2, bar_y + 6.0)]
            w_b_pts = [rotate_point(px + cx, py + cy, rad, cx, cy) for px, py in b_pts]
            ax.add_patch(patches.Polygon(w_b_pts, closed=True, facecolor=WALL_BLACK, edgecolor=WALL_BLACK, linewidth=1.0, zorder=zorder + 2))
            # Active red front strip
            act_pts = [(-bar_w / 2, bar_y + 2.5), (bar_w / 2, bar_y + 2.5), (bar_w / 2, bar_y + 6.0), (-bar_w / 2, bar_y + 6.0)]
            w_act_pts = [rotate_point(px + cx, py + cy, rad, cx, cy) for px, py in act_pts]
            ax.add_patch(patches.Polygon(w_act_pts, closed=True, facecolor=CRIMSON, edgecolor="#7F1D1D", linewidth=1.2, zorder=zorder + 3))

        elif w_name == "Line":
            # Line Template: narrow frontal line contact with active red zone (matches template_line.png)
            line_y = 12.0 if chassis_lower != "triangle" else 14.0
            lw = 7.0
            lh = 22.0
            # Base line body
            l_pts = [(-lw / 2, line_y - 4.0), (lw / 2, line_y - 4.0), (lw / 2, line_y + lh - 4.0), (-lw / 2, line_y + lh - 4.0)]
            w_l_pts = [rotate_point(px + cx, py + cy, rad, cx, cy) for px, py in l_pts]
            ax.add_patch(patches.Polygon(w_l_pts, closed=True, facecolor=WALL_BLACK, edgecolor=WALL_BLACK, linewidth=1.0, zorder=zorder + 2))
            # Active red forward half
            act_l_pts = [(-lw / 2, line_y + 7.0), (lw / 2, line_y + 7.0), (lw / 2, line_y + lh - 4.0), (-lw / 2, line_y + lh - 4.0)]
            w_act_l_pts = [rotate_point(px + cx, py + cy, rad, cx, cy) for px, py in act_l_pts]
            ax.add_patch(patches.Polygon(w_act_l_pts, closed=True, facecolor=CRIMSON, edgecolor="#7F1D1D", linewidth=1.2, zorder=zorder + 3))

        elif w_name == "Prongs":
            # Prongs Template: dual forward forks with active red prongs (matches template_prongs.png)
            py = 12.0 if chassis_lower != "triangle" else 13.0
            span = 14.0 if chassis_lower != "wide" else 18.0
            pw = 5.5
            ph = 20.0
            # Black base bar
            base_pts = [(-span - pw, py - 2.0), (span + pw, py - 2.0), (span + pw, py + 4.0), (-span - pw, py + 4.0)]
            w_base = [rotate_point(px + cx, py + cy, rad, cx, cy) for px, py in base_pts]
            ax.add_patch(patches.Polygon(w_base, closed=True, facecolor=WALL_BLACK, edgecolor=WALL_BLACK, linewidth=1.0, zorder=zorder + 2))
            # Left & Right prongs
            for px_c in [-span, span]:
                pr_pts = [(px_c - pw / 2, py + 4.0), (px_c + pw / 2, py + 4.0), (px_c + pw / 2, py + ph), (px_c - pw / 2, py + ph)]
                w_pr = [rotate_point(px + cx, py + cy, rad, cx, cy) for px, py in pr_pts]
                ax.add_patch(patches.Polygon(w_pr, closed=True, facecolor=WALL_BLACK, edgecolor=WALL_BLACK, linewidth=1.0, zorder=zorder + 2))
                # Active red tips
                tip_pts = [(px_c - pw / 2, py + ph - 10.0), (px_c + pw / 2, py + ph - 10.0), (px_c + pw / 2, py + ph), (px_c - pw / 2, py + ph)]
                w_tip = [rotate_point(px + cx, py + cy, rad, cx, cy) for px, py in tip_pts]
                ax.add_patch(patches.Polygon(w_tip, closed=True, facecolor=CRIMSON, edgecolor="#7F1D1D", linewidth=1.2, zorder=zorder + 3))

    # Robot label
    if not ghost:
        lbl = f"Bot {name}" if len(name) == 1 else name
        ax.text(
            cx + text_offset[0], cy - 2 + text_offset[1], lbl,
            color="#FFFFFF" if not is_inverted else WALL_BLACK,
            fontsize=8.5, fontweight="bold",
            ha="center", va="center", zorder=zorder + 6
        )

    if is_inverted:
        ax.text(
            cx, cy + 24, "INVERTED",
            color="#FFFFFF", fontsize=7.5, fontweight="bold",
            ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.25", facecolor=CRIMSON, edgecolor="none"),
            zorder=zorder + 7
        )
    elif is_raised:
        ax.text(
            cx, cy + 28, "^ RAISED",
            color="#FFFFFF", fontsize=8, fontweight="bold",
            ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.25", facecolor=AMBER_NOTE, edgecolor="none"),
            zorder=zorder + 7
        )


def draw_step_badge(ax: plt.Axes, x: float, y: float, step: int, title: str, zorder: int = 20) -> None:
    """Draws a numbered step header badge."""
    text = f"Step {step}: {title}"
    ax.text(
        x, y, text,
        color="#FFFFFF", fontsize=9, fontweight="bold",
        ha="left", va="center",
        bbox=dict(boxstyle="round,pad=0.35", facecolor=DARK_NAVY, edgecolor="none"),
        zorder=zorder
    )


def draw_card(
    ax: plt.Axes,
    cx: float,
    cy: float,
    w: float,
    h: float,
    name: str,
    category: str = "armor",  # 'weapon', 'armor', 'motor', 'battery', 'forks', 'wheel', 'esc'
    stats: str = "",
    is_hit: bool = False,
    is_shielded: bool = False,
    zorder: int = 5,
) -> None:
    """Draws an individual component card on an automaton sheet layout with title, category color, and stats."""
    x = cx - w / 2
    y = cy - h / 2

    if is_hit:
        fc = "#FEF2F2"
        ec = CRIMSON
        lw = 2.4
    elif is_shielded:
        fc = "#F8FAFC"
        ec = STEEL_BLUE
        lw = 1.2
    else:
        fc = "#FFFFFF"
        ec = BOX_BORDER
        lw = 1.0

    card_box = patches.FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.2,rounding_size=2.0",
        facecolor=fc, edgecolor=ec, linewidth=lw,
        zorder=zorder
    )
    ax.add_patch(card_box)

    bar_h = 3.6
    bar_color = {
        "weapon": CRIMSON,
        "forks": AMBER_NOTE,
        "armor": "#475569",
        "motor": SUCCESS_GREEN,
        "esc": "#7C3AED",
        "battery": LIGHT_BLUE,
        "wheel": WALL_BLACK,
    }.get(category, STEEL_BLUE)

    header_bar = patches.FancyBboxPatch(
        (x + 0.8, y + h - bar_h - 0.8), w - 1.6, bar_h,
        boxstyle="round,pad=0.1,rounding_size=1.0",
        facecolor=bar_color, edgecolor="none",
        zorder=zorder + 1
    )
    ax.add_patch(header_bar)

    ax.text(
        cx, y + h - bar_h - 3.2, name,
        fontsize=6.2, fontweight="bold",
        color=DARK_NAVY if not is_hit else CRIMSON,
        ha="center", va="top", zorder=zorder + 2
    )

    if stats:
        ax.text(
            cx, y + 2.5, stats,
            fontsize=5.2, color=TEXT_MUTED if not is_hit else CRIMSON,
            fontweight="bold" if is_hit else "normal",
            ha="center", va="bottom", zorder=zorder + 2
        )

    if is_hit:
        ax.text(
            cx, cy - 1.0, "* HIT! *",
            fontsize=7.5, fontweight="bold", color=CRIMSON,
            ha="center", va="center", zorder=zorder + 3
        )
    elif is_shielded:
        ax.text(
            cx, cy - 1.0, "[ SHIELDED ]",
            fontsize=5.6, fontweight="bold", color=STEEL_BLUE,
            ha="center", va="center", zorder=zorder + 3
        )


# ----------------------------------------------------------------------
# 1. Diagram: Straight & Curve Movement Examples
# ----------------------------------------------------------------------

def generate_movement_straight_curve(output_path: Path) -> None:
    """Generates Section 4.4 movement examples: Straight (3/3), Reverse (-2/-2), Curve Right (2/1), Curve Left (1/2)."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.0, 6.2), dpi=250)

    # PANEL 1: Straight & Reverse
    draw_arena_background(ax1, (0, 240), (0, 220))
    ax1.set_title("1. Straight Driving (3/3) & Reverse (-2/-2)", fontsize=11, fontweight="bold", color=DARK_NAVY, pad=12)

    # Robot A: Straight 3/3 (Line Template / Vertical Spinner)
    ax1.text(65, 205, "Straight (3/3): Front Alignment", fontsize=9, fontweight="bold", color=STEEL_BLUE, ha="center")
    t_w, t_h = 36, 105
    t_x = 47
    t_y = 65
    rect_a = patches.Rectangle((t_x, t_y), t_w, t_h, facecolor=BOX_BG, edgecolor=BOX_BORDER, linewidth=1.5, zorder=2)
    ax1.add_patch(rect_a)
    ax1.plot([t_x, t_x + t_w], [t_y, t_y], color=WALL_BLACK, linewidth=3.5, zorder=3)
    ax1.text(t_x + t_w / 2, t_y - 7, "START (Front Bumper)", fontsize=7, fontweight="bold", ha="center", color=WALL_BLACK)
    for i in range(1, 4):
        ly = t_y + i * 35
        ax1.plot([t_x, t_x + t_w], [ly, ly], color=LIGHT_BLUE, linewidth=2.0, zorder=3)
        ax1.text(t_x + t_w / 2, ly - 5, f"L{i} R{i}", fontsize=7.5, fontweight="bold", ha="center", color=STEEL_BLUE)

    draw_robot(ax1, 65, 43, 0, chassis="Triangle", color=LIGHT_BLUE, name="A", weapon="Line", ghost=True)
    draw_robot(ax1, 65, 43 + 3 * 35, 0, chassis="Triangle", color=LIGHT_BLUE, name="A", weapon="Line")
    ax1.annotate(
        "", xy=(32, 43 + 3 * 35 - 5), xytext=(32, 43 + 5),
        arrowprops=dict(arrowstyle="->", color=STEEL_BLUE, lw=2.5, mutation_scale=15),
        zorder=7
    )
    ax1.text(28, 95, "Advance\n3 units", fontsize=8, fontweight="bold", color=STEEL_BLUE, ha="right")

    # Robot B: Reverse -2/-2 (Circle Template / Horizontal Spinner)
    ax1.text(175, 205, "Reverse (-2/-2): Rear Alignment", fontsize=9, fontweight="bold", color=CRIMSON, ha="center")
    t_xb = 157
    t_yb = 150
    t_hb = 70
    rect_b = patches.Rectangle((t_xb, t_yb - t_hb), t_w, t_hb, facecolor=BOX_BG, edgecolor=BOX_BORDER, linewidth=1.5, zorder=2)
    ax1.add_patch(rect_b)
    ax1.plot([t_xb, t_xb + t_w], [t_yb, t_yb], color=WALL_BLACK, linewidth=3.5, zorder=3)
    ax1.text(t_xb + t_w / 2, t_yb + 7, "START (Rear Bumper)", fontsize=7, fontweight="bold", ha="center", color=WALL_BLACK)
    for i in range(1, 3):
        ly = t_yb - i * 35
        ax1.plot([t_xb, t_xb + t_w], [ly, ly], color=LIGHT_BLUE, linewidth=2.0, zorder=3)
        ax1.text(t_xb + t_w / 2, ly + 5, f"L{i} R{i}", fontsize=7.5, fontweight="bold", ha="center", color=STEEL_BLUE)

    draw_robot(ax1, 175, 168, 0, chassis="Square", color=AMBER_NOTE, name="B", weapon="Circle", ghost=True)
    draw_robot(ax1, 175, 168 - 2 * 35, 0, chassis="Square", color=AMBER_NOTE, name="B", weapon="Circle")
    ax1.annotate(
        "", xy=(208, 168 - 2 * 35 + 5), xytext=(208, 168 - 5),
        arrowprops=dict(arrowstyle="->", color=CRIMSON, lw=2.5, mutation_scale=15),
        zorder=7
    )
    ax1.text(212, 133, "Reverse\n2 units", fontsize=8, fontweight="bold", color=CRIMSON, ha="left")

    # PANEL 2: Curved Arcs & Flipping
    draw_arena_background(ax2, (0, 240), (0, 220))
    ax2.set_title("2. Curved Arcs (2/1 Right) & Left Flipping (1/2)", fontsize=11, fontweight="bold", color=DARK_NAVY, pad=12)

    # Right Turn 2/1 (Face-Up) - Robot C (Bar Template / Beater Bar)
    r_center_x, r_center_y = 115, 55
    r_out, r_in = 80, 45
    ax2.text(55, 205, "Right Turn (2/1): Face-Up\nSweeps 45° Clockwise", fontsize=8.5, fontweight="bold", color=STEEL_BLUE, ha="center")
    
    wedge_r = patches.Wedge((r_center_x, r_center_y), r_out, 135, 180, width=(r_out - r_in), facecolor=BOX_BG, edgecolor=BOX_BORDER, linewidth=1.5, zorder=2)
    ax2.add_patch(wedge_r)
    ax2.plot([r_center_x - r_out, r_center_x - r_in], [r_center_y, r_center_y], color=WALL_BLACK, linewidth=3.5, zorder=3)
    ax2.text(r_center_x - (r_out + r_in) / 2, r_center_y - 8, "START FRONT", fontsize=7, fontweight="bold", ha="center", color=WALL_BLACK)
    
    p1 = (r_center_x - r_out * math.cos(math.radians(45)), r_center_y + r_out * math.sin(math.radians(45)))
    p2 = (r_center_x - r_in * math.cos(math.radians(45)), r_center_y + r_in * math.sin(math.radians(45)))
    ax2.plot([p1[0], p2[0]], [p1[1], p2[1]], color=LIGHT_BLUE, linewidth=2.2, zorder=3)
    ax2.text(p1[0] - 6, p1[1] + 6, "L2 R1 (45°)", fontsize=7.5, fontweight="bold", color=STEEL_BLUE)

    draw_robot(ax2, r_center_x - (r_out + r_in) / 2, r_center_y - 22, 0, chassis="Triangle", color=LIGHT_BLUE, name="C", weapon="Bar", ghost=True)
    r_mid = (r_out + r_in) / 2
    fc_cx = r_center_x - r_mid * math.cos(math.radians(45)) + 12 * math.sin(math.radians(45))
    fc_cy = r_center_y + r_mid * math.sin(math.radians(45)) + 12 * math.cos(math.radians(45))
    draw_robot(ax2, fc_cx, fc_cy, -45, chassis="Triangle", color=LIGHT_BLUE, name="C", weapon="Bar")
    
    arc_patch_r = patches.Arc((r_center_x, r_center_y), r_mid * 2, r_mid * 2, angle=0, theta1=140, theta2=175, color=STEEL_BLUE, lw=2.2, zorder=6)
    ax2.add_patch(arc_patch_r)

    # Left Turn 1/2 (Flipped Face-Down) - Robot D (Prongs Template / Forks)
    l_center_x, l_center_y = 125, 55
    ax2.text(185, 205, "Left Turn (1/2): FLIP Face-Down\nSweeps 45° Counter-Clockwise", fontsize=8.5, fontweight="bold", color=CRIMSON, ha="center")
    
    wedge_l = patches.Wedge((l_center_x, l_center_y), r_out, 0, 45, width=(r_out - r_in), facecolor=BOX_BG, edgecolor=BOX_BORDER, linewidth=1.5, zorder=2)
    ax2.add_patch(wedge_l)
    ax2.plot([l_center_x + r_in, l_center_x + r_out], [l_center_y, l_center_y], color=WALL_BLACK, linewidth=3.5, zorder=3)
    ax2.text(l_center_x + (r_out + r_in) / 2, l_center_y - 8, "START FRONT", fontsize=7, fontweight="bold", ha="center", color=WALL_BLACK)
    
    pl1 = (l_center_x + r_out * math.cos(math.radians(45)), l_center_y + r_out * math.sin(math.radians(45)))
    pl2 = (l_center_x + r_in * math.cos(math.radians(45)), l_center_y + r_in * math.sin(math.radians(45)))
    ax2.plot([pl1[0], pl2[0]], [pl1[1], pl2[1]], color=LIGHT_BLUE, linewidth=2.2, zorder=3)
    ax2.text(pl1[0] + 4, pl1[1] + 6, "L1 R2 (45°)", fontsize=7.5, fontweight="bold", color=STEEL_BLUE)

    draw_robot(ax2, l_center_x + (r_out + r_in) / 2, l_center_y - 22, 0, chassis="Wide", color=AMBER_NOTE, name="D", weapon="Prongs", ghost=True)
    fd_cx = l_center_x + r_mid * math.cos(math.radians(45)) - 12 * math.sin(math.radians(45))
    fd_cy = l_center_y + r_mid * math.sin(math.radians(45)) + 12 * math.cos(math.radians(45))
    draw_robot(ax2, fd_cx, fd_cy, 45, chassis="Wide", color=AMBER_NOTE, name="D", weapon="Prongs")
    
    arc_patch_l = patches.Arc((l_center_x, l_center_y), r_mid * 2, r_mid * 2, angle=0, theta1=5, theta2=40, color=CRIMSON, lw=2.2, zorder=6)
    ax2.add_patch(arc_patch_l)

    plt.tight_layout()
    plt.savefig(output_path, dpi=250)
    plt.close()
    print(f"✔ Generated {output_path}")


# ----------------------------------------------------------------------
# 2. Diagram: Pivot Fan vs. Spin Disc Rotations
# ----------------------------------------------------------------------

def generate_movement_pivot_spin(output_path: Path) -> None:
    """Generates Section 4.4 movement examples: Pivot Fan (2/0) vs. Spin Disc (2/-2)."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.0, 5.8), dpi=250)

    # PANEL 1: Pivot Fan (2/0) - Robot A (Line Template)
    draw_arena_background(ax1, (0, 220), (0, 200))
    ax1.set_title("3. Pivot Fan: Locked Wheel Turn (2/0)", fontsize=11, fontweight="bold", color=DARK_NAVY, pad=12)

    pivot_x, pivot_y = 110, 55
    fan = patches.Wedge((pivot_x, pivot_y), 75, 0, 180, facecolor=BOX_BG, edgecolor=BOX_BORDER, linewidth=1.5, zorder=2)
    ax1.add_patch(fan)
    ax1.plot([pivot_x - 75, pivot_x], [pivot_y, pivot_y], color=WALL_BLACK, linewidth=3.5, zorder=3)
    ax1.text(pivot_x - 38, pivot_y - 10, "START FRONT", fontsize=7.5, fontweight="bold", ha="center", color=WALL_BLACK)
    
    ax1.plot(pivot_x, pivot_y, "o", color=CRIMSON, markersize=8, zorder=10)
    ax1.text(
        pivot_x + 5, pivot_y - 12, "LOCKED WHEEL (PIN)",
        fontsize=7.5, fontweight="bold", color=CRIMSON,
        bbox=dict(boxstyle="round,pad=0.2", facecolor="#FEF2F2", edgecolor=CRIMSON)
    )

    angles = [45, 90, 135, 180]
    labels = ["L1 R0 (45°)", "L2 R0 (90°)", "L3 R0 (135°)", "L4 R0 (180°)"]
    for ang, lbl in zip(angles, labels):
        rx = pivot_x - 75 * math.cos(math.radians(ang))
        ry = pivot_y + 75 * math.sin(math.radians(ang))
        ax1.plot([pivot_x, rx], [pivot_y, ry], color=LIGHT_BLUE, linewidth=1.8, zorder=3)
        if ang == 45:
            ax1.text(rx - 2, ry + 4, lbl, fontsize=7.5, fontweight="bold", color=STEEL_BLUE, ha="right")
        elif ang == 90:
            ax1.text(rx, ry + 4, lbl, fontsize=7.5, fontweight="bold", color=STEEL_BLUE, ha="center")
        else:
            ax1.text(rx + 2, ry + 3, lbl, fontsize=7.5, fontweight="bold", color=STEEL_BLUE)

    draw_robot(ax1, pivot_x - 38, pivot_y - 18, 0, chassis="Triangle", color=LIGHT_BLUE, name="A", weapon="Line", ghost=True)
    draw_robot(ax1, pivot_x + 18, pivot_y + 38, -90, chassis="Triangle", color=LIGHT_BLUE, name="A", weapon="Line")
    
    arc_p = patches.Arc((pivot_x, pivot_y), 90, 90, angle=0, theta1=90, theta2=180, color=CRIMSON, lw=2.5, zorder=7)
    ax1.add_patch(arc_p)
    ax1.text(
        pivot_x - 75, pivot_y + 65, "Pivots 90° CW\n(2 × 45°/unit)",
        fontsize=8.5, fontweight="bold", color=CRIMSON,
        bbox=dict(boxstyle="round,pad=0.25", facecolor="#FEF2F2", edgecolor=CRIMSON)
    )

    # PANEL 2: Spin Disc (2/-2) - Robot B (Large Circle Template)
    draw_arena_background(ax2, (0, 220), (0, 200))
    ax2.set_title("Spin Disc: In-Place Center Rotation (2/-2)", fontsize=11, fontweight="bold", color=DARK_NAVY, pad=12)

    disc_x, disc_y = 110, 100
    disc = patches.Circle((disc_x, disc_y), radius=60, facecolor=BOX_BG, edgecolor=BOX_BORDER, linewidth=1.5, zorder=2)
    ax2.add_patch(disc)
    ax2.plot([disc_x, disc_x], [disc_y, disc_y + 60], color=WALL_BLACK, linewidth=3.5, zorder=3)
    ax2.text(disc_x, disc_y + 68, "START (0°)", fontsize=7.5, fontweight="bold", color=WALL_BLACK, ha="center")
    
    ax2.plot([disc_x, disc_x + 60], [disc_y, disc_y], color=LIGHT_BLUE, linewidth=1.8, zorder=3)
    ax2.text(disc_x + 64, disc_y, "L1 R-1\n(90°)", fontsize=7.5, fontweight="bold", color=STEEL_BLUE, va="center")
    ax2.plot([disc_x, disc_x], [disc_y, disc_y - 60], color=LIGHT_BLUE, linewidth=1.8, zorder=3)
    ax2.text(disc_x, disc_y - 72, "L2 R-2 (180°)", fontsize=7.5, fontweight="bold", color=STEEL_BLUE, ha="center")
    ax2.plot([disc_x, disc_x - 60], [disc_y, disc_y], color=LIGHT_BLUE, linewidth=1.8, zorder=3)
    ax2.text(disc_x - 64, disc_y, "L3 R-3\n(270°)", fontsize=7.5, fontweight="bold", color=STEEL_BLUE, ha="right", va="center")

    ax2.plot(disc_x, disc_y, "o", color=WALL_BLACK, markersize=5.5, zorder=10)
    ax2.plot(disc_x, disc_y, "o", color="#FFFFFF", markersize=2.2, zorder=11)

    draw_robot(ax2, disc_x, disc_y, 0, chassis="Wide", color=AMBER_NOTE, name="B", weapon="Large Circle", ghost=True)
    draw_robot(ax2, disc_x, disc_y, 180, chassis="Wide", color=AMBER_NOTE, name="B", weapon="Large Circle", text_offset=(0.0, 6.0), zorder=8)
    
    rot_arc = patches.Arc((disc_x, disc_y), 78, 78, angle=0, theta1=270, theta2=90, color=CRIMSON, lw=2.5, zorder=12)
    ax2.add_patch(rot_arc)
    ax2.text(
        disc_x + 22, disc_y + 40, "Rotates 180° CW\n(Zero displacement!)",
        fontsize=8.5, fontweight="bold", color=CRIMSON,
        bbox=dict(boxstyle="round,pad=0.25", facecolor="#FEF2F2", edgecolor=CRIMSON)
    )

    plt.tight_layout()
    plt.savefig(output_path, dpi=250)
    plt.close()
    print(f"✔ Generated {output_path}")


# ----------------------------------------------------------------------
# 3. Diagram: Contact Point Determination & Automata Card Mapping
# ----------------------------------------------------------------------

def generate_contact_point(output_path: Path) -> None:
    """Generates Section 5.1 diagram: 3 Contact Scenarios + Octant Mapping to Automaton Sheet (Vyper Spinner)."""
    fig = plt.figure(figsize=(15.0, 10.0), dpi=250)
    gs = fig.add_gridspec(2, 3, height_ratios=[1.0, 1.25], hspace=0.28, wspace=0.22)

    # ------------------------------------------------------------------
    # TOP ROW: 3 Collision Scenarios
    # ------------------------------------------------------------------

    # Panel 1: Weapon vs. Weapon
    ax1 = fig.add_subplot(gs[0, 0])
    draw_arena_background(ax1, (0, 160), (0, 140))
    ax1.set_title("Scenario 1: Weapon vs. Weapon", fontsize=10, fontweight="bold", color=CRIMSON, pad=8)
    draw_robot(ax1, 52, 70, -90, chassis="Triangle", color=LIGHT_BLUE, name="A", weapon="Line")
    draw_robot(ax1, 108, 70, 90, chassis="Square", color=AMBER_NOTE, name="B", weapon="Circle")
    ax1.plot(80, 70, "*", color=CRIMSON, markersize=18, markeredgecolor=WALL_BLACK, zorder=15)
    ax1.text(
        80, 15,
        "BOTH WEAPON RED-ZONES TOUCH\n• Mutual attack damage\n• Mutual feedback (1/2 str)\n• Both bots THROWN apart",
        fontsize=7.5, color=DARK_NAVY, ha="center",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#FEF2F2", edgecolor=CRIMSON)
    )

    # Panel 2: Weapon Only From One Side
    ax2 = fig.add_subplot(gs[0, 1])
    draw_arena_background(ax2, (0, 160), (0, 140))
    ax2.set_title("Scenario 2: Weapon From One Side", fontsize=10, fontweight="bold", color=DARK_NAVY, pad=8)
    draw_robot(ax2, 50, 70, -90, chassis="Triangle", color=LIGHT_BLUE, name="A", weapon="Line")
    draw_robot(ax2, 108, 70, 0, chassis="Square", color=AMBER_NOTE, name="B", weapon="Bar")  # Bar facing North away from contact!
    ax2.plot(78, 70, "*", color=CRIMSON, markersize=18, markeredgecolor=WALL_BLACK, zorder=15)
    ax2.text(
        80, 15,
        "ONE-SIDED ACTIVE HIT\n• Bot A weapon strikes Bot B flank\n• Bot B takes strike damage\n• Bot A takes 1/2 str feedback",
        fontsize=7.5, color=DARK_NAVY, ha="center",
        bbox=dict(boxstyle="round,pad=0.3", facecolor=BOX_BG, edgecolor=BOX_BORDER)
    )

    # Panel 3: Inertial Chassis Contact (Armed bots, shoulder to flank)
    ax3 = fig.add_subplot(gs[0, 2])
    draw_arena_background(ax3, (0, 160), (0, 140))
    ax3.set_title("Scenario 3: Inertial Chassis Contact", fontsize=10, fontweight="bold", color=STEEL_BLUE, pad=8)
    # Bot A (Line weapon) facing 45 deg away, Bot B (Bar weapon) facing 180 deg away
    draw_robot(ax3, 50, 68, 45, chassis="Triangle", color=LIGHT_BLUE, name="A", weapon="Line")
    draw_robot(ax3, 105, 75, 180, chassis="Wide", color=AMBER_NOTE, name="B", weapon="Bar")
    ax3.plot(76, 70, "o", color=STEEL_BLUE, markersize=9, zorder=15)
    ax3.text(
        80, 15,
        "INERT CONTACT (ARMED BOTS)\n• Shoulder-to-flank collision\n• Neither weapon red-zone touches\n• Resolves as PUSHING MATCH",
        fontsize=7.5, color=DARK_NAVY, ha="center",
        bbox=dict(boxstyle="round,pad=0.3", facecolor=BG_BLUE, edgecolor=STEEL_BLUE)
    )

    # ------------------------------------------------------------------
    # BOTTOM ROW: Octant System & Mapping to Automata Card Layout
    # ------------------------------------------------------------------

    # Left Bottom: Octant System on Miniature
    ax_oct = fig.add_subplot(gs[1, 0])
    draw_arena_background(ax_oct, (0, 160), (0, 160), show_grid=False)
    ax_oct.set_title("Octant System on Miniature", fontsize=10.5, fontweight="bold", color=DARK_NAVY, pad=8)

    mcx, mcy = 80, 80
    draw_robot(ax_oct, mcx, mcy, 0, chassis="Triangle", color=LIGHT_BLUE, name="Vyper", weapon="Circle")

    # Draw 8 octant radiating lines & labels
    octants = [
        (1, "1: Front", 90),
        (2, "2: Front-R", 45),
        (3, "3: Right", 0),
        (4, "4: Rear-R", -45),
        (5, "5: Rear", -90),
        (6, "6: Rear-L", -135),
        (7, "7: Left", 180),
        (8, "8: Front-L", 135),
    ]
    for o_num, o_name, deg in octants:
        rad = math.radians(deg)
        lx = mcx + 45 * math.cos(rad)
        ly = mcy + 45 * math.sin(rad)
        ax_oct.plot([mcx, lx], [mcy, ly], color=GRID_COLOR, linestyle="--", linewidth=1.0, zorder=1)
        tx = mcx + 58 * math.cos(rad)
        ty = mcy + 58 * math.sin(rad)
        c = CRIMSON if o_num == 8 else TEXT_MUTED
        fw = "bold" if o_num == 8 else "normal"
        if o_num == 8:
            # Offset Oct 8 slightly perpendicular to avoid crossing the strike arrow
            ax_oct.text(tx - 10, ty - 8, f"Oct {o_num}", fontsize=6.8, color=c, fontweight=fw, ha="center", va="center")
        else:
            ax_oct.text(tx, ty, f"Oct {o_num}", fontsize=6.8, color=c, fontweight=fw, ha="center", va="center")

    # Incoming Strike Arrow at Octant 8 (Front-Left) - shifted outward to not overlap "Oct 8" text
    strk_start = (mcx + 68 * math.cos(math.radians(135)), mcy + 68 * math.sin(math.radians(135)))
    strk_end = (mcx + 22 * math.cos(math.radians(135)), mcy + 22 * math.sin(math.radians(135)))
    ax_oct.annotate(
        "", xy=strk_end, xytext=strk_start,
        arrowprops=dict(arrowstyle="->", color=CRIMSON, lw=3.0, mutation_scale=16),
        zorder=20
    )
    ax_oct.plot(strk_end[0], strk_end[1], "*", color=CRIMSON, markersize=14, markeredgecolor=WALL_BLACK, zorder=21)
    ax_oct.text(
        strk_start[0] - 6, strk_start[1] + 12, "INCOMING STRIKE\nAT OCTANT 8 (Front-L)",
        fontsize=7.2, fontweight="bold", color=CRIMSON, ha="center",
        bbox=dict(boxstyle="round,pad=0.2", facecolor="#FEF2F2", edgecolor=CRIMSON),
        zorder=22
    )

    # Right Bottom: Automata Card Layout (Vyper Spinner)
    ax_map = fig.add_subplot(gs[1, 1:])
    ax_map.set_facecolor(ARENA_FLOOR)
    ax_map.set_xlim(0, 310)
    ax_map.set_ylim(0, 160)
    ax_map.set_aspect("equal")
    ax_map.axis("off")
    ax_map.set_title("Automata Card Sheet Mapping: Vyper Spinner Layout", fontsize=11, fontweight="bold", color=DARK_NAVY, pad=8)

    # Sheet background box
    s_bg = patches.FancyBboxPatch(
        (10, 8), 290, 144,
        boxstyle="round,pad=1.5,rounding_size=3.0",
        facecolor=BOX_BG, edgecolor=BOX_BORDER, linewidth=1.5, zorder=1
    )
    ax_map.add_patch(s_bg)

    # Robot Heading Indicator on sheet
    ax_map.annotate(
        "", xy=(155, 142), xytext=(155, 126),
        arrowprops=dict(arrowstyle="->", color=STEEL_BLUE, lw=2.2, mutation_scale=12),
        zorder=3
    )
    ax_map.text(155, 146, "FRONT (HEADING)", fontsize=7.2, fontweight="bold", color=STEEL_BLUE, ha="center", zorder=3)

    # Cards grid: Vyper Spinner layout (from automata/Vyper_Spinner.csv)
    # Row 1 (Front): Titanium Wedge (x=65), Horizontal Spinner (x=155), Titanium Wedge (x=245)
    # Row 2 (Middle): Galaxy 120 ESC (x=65), Repeat 2207 Hubmotor (x=155), Tattu 450 4S (x=245)
    # Row 3 (Rear): Left Wheel (x=65), TPU Plate (x=155), Right Wheel (x=245)
    card_w, card_h = 72, 32
    cy_front = 108
    cy_mid = 68
    cy_rear = 28

    # Front Row
    draw_card(ax_map, 65, cy_front, card_w, card_h, "Titanium Wedge", category="armor", stats="Front-L Armor • 4 pts", is_hit=True)
    draw_card(ax_map, 155, cy_front, card_w, card_h, "Horizontal Spinner", category="weapon", stats="Front Weapon • Circle Tpl")
    draw_card(ax_map, 245, cy_front, card_w, card_h, "Titanium Wedge", category="armor", stats="Front-R Armor • 4 pts")

    # Middle Row (Shielded internal components)
    draw_card(ax_map, 65, cy_mid, card_w, card_h, "Galaxy 120 ESC", category="esc", stats="Drive ESC • 2 pts", is_shielded=True)
    draw_card(ax_map, 155, cy_mid, card_w, card_h, "Repeat 2207 Hub", category="motor", stats="Weapon Motor • 3 pts", is_shielded=True)
    draw_card(ax_map, 245, cy_mid, card_w, card_h, "Tattu 450 4S", category="battery", stats="Battery Pack • 2 pts", is_shielded=True)

    # Rear Row
    draw_card(ax_map, 65, cy_rear, card_w, card_h, "Left Wheel", category="wheel", stats="Drive Wheel • 2 pts")
    draw_card(ax_map, 155, cy_rear, card_w, card_h, "TPU Plate", category="armor", stats="Rear Bumper • 3 pts")
    draw_card(ax_map, 245, cy_rear, card_w, card_h, "Right Wheel", category="wheel", stats="Drive Wheel • 2 pts")

    # Highlight arrow from Octant 8 directly to Front-L Titanium Wedge
    ax_map.annotate(
        "Direct hit at Octant 8!\nOutermost card absorbs strike",
        xy=(65, cy_front + 16), xytext=(25, cy_front + 32),
        arrowprops=dict(arrowstyle="->", color=CRIMSON, lw=2.2, mutation_scale=12),
        fontsize=7.2, fontweight="bold", color=CRIMSON, ha="center",
        bbox=dict(boxstyle="round,pad=0.2", facecolor="#FEF2F2", edgecolor=CRIMSON),
        zorder=10
    )

    # Shielding callout
    ax_map.text(
        205, 14,
        "Internal components (ESC, Motor, Battery) are SHIELDED\n"
        "Damage does NOT penetrate inwards until outer armor is breached!",
        fontsize=7.2, fontweight="bold", color=STEEL_BLUE, ha="center",
        bbox=dict(boxstyle="round,pad=0.25", facecolor=BG_BLUE, edgecolor=STEEL_BLUE),
        zorder=10
    )

    plt.savefig(output_path, dpi=250, bbox_inches="tight")
    plt.close()
    print(f"✔ Generated {output_path}")


# ----------------------------------------------------------------------
# 4. Diagram: Inert Contact (Pushing Match) — ARMED ROBOTS SHOULDER-TO-FLANK
# ----------------------------------------------------------------------

def generate_inert_contact(output_path: Path) -> None:
    """Generates Section 5.2 Inert Contact (Pushing Match) 4-step sequence with armed robots colliding shoulder-to-flank."""
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(14.0, 9.8), dpi=250)

    # STEP 1: Collision & Remaining Motion
    draw_arena_background(ax1, (0, 200), (0, 165))
    draw_step_badge(ax1, 10, 150, 1, "Initial Contact & Remaining Motion")

    c_x, c_y = 95, 75
    # Bot A (Line Template) facing 45 deg (North-East, weapon points away from Bot B)
    # Bot B (Bar Template) facing 180 deg (South, bar points away down)
    # They collide at Bot A's flank/shoulder and Bot B's flank!
    draw_robot(ax1, c_x - 18, c_y - 10, 45, chassis="Triangle", color=LIGHT_BLUE, name="A", weapon="Line")
    draw_robot(ax1, c_x + 16, c_y + 12, 180, chassis="Wide", color=AMBER_NOTE, name="B", weapon="Bar")
    ax1.plot(c_x, c_y, "o", color=STEEL_BLUE, markersize=8, zorder=12)

    ax1.annotate(
        "", xy=(c_x + 35, c_y + 15), xytext=(c_x, c_y),
        arrowprops=dict(arrowstyle="->", color=LIGHT_BLUE, lw=2.5, mutation_scale=14),
        zorder=10
    )
    ax1.annotate(
        "", xy=(c_x + 28, c_y + 14), xytext=(142, 110),
        arrowprops=dict(arrowstyle="->", color=LIGHT_BLUE, lw=1.2),
        zorder=15
    )
    ax1.text(142, 112, "Remainder A ($v_A$)", fontsize=8, fontweight="bold", color=LIGHT_BLUE, ha="left", zorder=16)

    ax1.annotate(
        "", xy=(c_x - 25, c_y + 25), xytext=(c_x, c_y),
        arrowprops=dict(arrowstyle="->", color=AMBER_NOTE, lw=2.5, mutation_scale=14),
        zorder=10
    )
    ax1.text(c_x - 30, c_y + 30, "Remainder B ($v_B$)", fontsize=8, fontweight="bold", color=AMBER_NOTE, ha="right")

    ax1.text(
        10, 18,
        "• Advance along templates until chassis contact\n"
        "• Both bots armed, but weapon red-zones do NOT touch (shoulder-to-flank)\n"
        "• Note remaining unspent distance on each template",
        fontsize=7.8, color=DARK_NAVY
    )

    # STEP 2: Displace Remainder Template
    draw_arena_background(ax2, (0, 200), (0, 165))
    draw_step_badge(ax2, 10, 150, 2, "Displace Remainder Template")

    draw_robot(ax2, c_x - 18, c_y - 10, 45, chassis="Triangle", color=LIGHT_BLUE, name="A", weapon="Line", ghost=True)
    draw_robot(ax2, c_x + 16, c_y + 12, 180, chassis="Wide", color=AMBER_NOTE, name="B", weapon="Bar", ghost=True)
    ax2.plot(c_x, c_y, "o", color=STEEL_BLUE, markersize=6, zorder=12)

    vb_tip = (c_x - 25, c_y + 25)
    ax2.annotate("", xy=vb_tip, xytext=(c_x, c_y), arrowprops=dict(arrowstyle="->", color=AMBER_NOTE, lw=2.0, mutation_scale=12))

    va_disp_tip = (vb_tip[0] + 35, vb_tip[1] + 15)
    ax2.annotate("", xy=va_disp_tip, xytext=vb_tip, arrowprops=dict(arrowstyle="->", color=LIGHT_BLUE, lw=2.5, linestyle="--", mutation_scale=14))
    ax2.text(va_disp_tip[0] + 5, va_disp_tip[1], "A displaced to\nend of B", fontsize=8, fontweight="bold", color=LIGHT_BLUE)

    ax2.text(
        10, 18,
        "• Displace remainder of Robot A's template\n"
        "  to the end of Robot B's template vector\n"
        "• Net line forms the shared pushing vector",
        fontsize=7.8, color=DARK_NAVY
    )

    # STEP 3: Straight Push Along Net Line
    draw_arena_background(ax3, (0, 200), (0, 165))
    draw_step_badge(ax3, 10, 150, 3, "Joint Push Along Net Vector")

    draw_robot(ax3, c_x - 18, c_y - 10, 45, chassis="Triangle", color=LIGHT_BLUE, name="A", weapon="Line", ghost=True)
    draw_robot(ax3, c_x + 16, c_y + 12, 180, chassis="Wide", color=AMBER_NOTE, name="B", weapon="Bar", ghost=True)

    net_push_end = (c_x + 10, c_y + 40)
    ax3.annotate(
        "", xy=net_push_end, xytext=(c_x, c_y),
        arrowprops=dict(arrowstyle="->", color=CRIMSON, lw=3.0, mutation_scale=15),
        zorder=9
    )
    ax3.annotate(
        "Pushing Vector\n(Sum of motion)",
        xy=(net_push_end[0] - 2, net_push_end[1]),
        xytext=(45, 128),
        arrowprops=dict(arrowstyle="->", color=CRIMSON, lw=1.5),
        fontsize=8, fontweight="bold", color=CRIMSON, ha="center",
        bbox=dict(boxstyle="round,pad=0.25", facecolor="#FEF2F2", edgecolor=CRIMSON),
        zorder=20
    )

    draw_robot(ax3, c_x - 18 + 10, c_y - 10 + 40, 45, chassis="Triangle", color=LIGHT_BLUE, name="A", weapon="Line")
    draw_robot(ax3, c_x + 16 + 10, c_y + 12 + 40, 180, chassis="Wide", color=AMBER_NOTE, name="B", weapon="Bar")

    ax3.text(
        10, 18,
        "• Both robots push together along the straight net line\n"
        "• Raised robot motion does NOT contribute to pushing power",
        fontsize=7.8, color=DARK_NAVY
    )

    # STEP 4: Wall Collision & Separation
    draw_arena_background(ax4, (0, 200), (0, 175), wall_sides=["top"])
    draw_step_badge(ax4, 10, 142, 4, "Wall Impact & Full Unit Separation")

    draw_robot(ax4, 135, 145, 180, chassis="Wide", color=AMBER_NOTE, name="B", weapon="Bar")
    ax4.plot(135, 162, "*", color=CRIMSON, markersize=15, zorder=15)
    ax4.text(
        135, 114, "WALL IMPACT!\nThrow strength = Lost distance",
        fontsize=7.5, fontweight="bold", color=CRIMSON, ha="center",
        bbox=dict(boxstyle="round,pad=0.2", facecolor="#FEF2F2", edgecolor=CRIMSON),
        zorder=16
    )

    ax4.annotate(
        "", xy=(50, 75), xytext=(72, 75),
        arrowprops=dict(arrowstyle="->", color=SUCCESS_GREEN, lw=2.5, mutation_scale=14)
    )
    ax4.annotate(
        "", xy=(135, 75), xytext=(113, 75),
        arrowprops=dict(arrowstyle="->", color=SUCCESS_GREEN, lw=2.5, mutation_scale=14)
    )
    draw_robot(ax4, 40, 75, 45, chassis="Triangle", color=LIGHT_BLUE, name="A", weapon="Line")
    draw_robot(ax4, 145, 75, 180, chassis="Wide", color=AMBER_NOTE, name="B", weapon="Bar")
    ax4.text(
        92, 58, "Separate 1 Full Unit\nif still touching!",
        fontsize=8, fontweight="bold", color=SUCCESS_GREEN, ha="center",
        bbox=dict(boxstyle="round,pad=0.2", facecolor="#F0FDF4", edgecolor=SUCCESS_GREEN)
    )

    ax4.text(
        10, 18,
        "• Wall collision throws bot away with lost distance\n"
        "• Weapon contacting wall loses spin & takes feedback\n"
        "• If still touching at end: move back 1 full unit to separate",
        fontsize=7.5, color=DARK_NAVY
    )

    plt.savefig(output_path, dpi=250, bbox_inches="tight")
    plt.close()
    print(f"✔ Generated {output_path}")


# ----------------------------------------------------------------------
# 5. Diagram: Active Contact, Throws, Inversion & Wall Hit
# ----------------------------------------------------------------------

def generate_active_contact(output_path: Path) -> None:
    """Generates Section 5.3 & 6.1 Active Contact, Throws, Inversion & Hazard elimination."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.0, 6.2), dpi=250)

    # PANEL 1: Weapon Strike & Radiating Throw Vectors
    draw_arena_background(ax1, (0, 220), (0, 200))
    ax1.set_title("Active Weapon Strike & Throw Vectors", fontsize=11, fontweight="bold", color=DARK_NAVY, pad=12)

    cx, cy = 110, 105
    draw_robot(ax1, cx - 16, cy, -90, chassis="Triangle", color=LIGHT_BLUE, name="A", weapon="Bar")
    draw_robot(ax1, cx + 16, cy, 90, chassis="Square", color=AMBER_NOTE, name="B", weapon="Circle")

    ax1.plot(cx, cy, "*", color=CRIMSON, markersize=20, markeredgecolor=WALL_BLACK, markeredgewidth=1.2, zorder=15)
    ax1.text(
        cx, cy + 22, "STRIKE CONTACT\nDamage hits outermost component!",
        fontsize=8, fontweight="bold", color=CRIMSON, ha="center",
        bbox=dict(boxstyle="round,pad=0.25", facecolor="#FEF2F2", edgecolor=CRIMSON),
        zorder=16
    )

    ax1.annotate(
        "", xy=(cx - 65, cy - 25), xytext=(cx - 20, cy - 8),
        arrowprops=dict(arrowstyle="->", color=LIGHT_BLUE, lw=3.0, mutation_scale=15),
        zorder=12
    )
    ax1.text(cx - 70, cy - 38, "Throw Vector A\n(Base = Attack Received)", fontsize=8, fontweight="bold", color=STEEL_BLUE, ha="center")

    ax1.annotate(
        "", xy=(cx + 65, cy + 30), xytext=(cx + 20, cy + 8),
        arrowprops=dict(arrowstyle="->", color=AMBER_NOTE, lw=3.0, mutation_scale=15),
        zorder=12
    )
    ax1.text(cx + 70, cy + 42, "Throw Vector B\n(min(d6, Throw Str))", fontsize=8, fontweight="bold", color=AMBER_NOTE, ha="center")

    ax1.text(
        10, 22,
        "• Weapons hit outermost contacted component\n"
        "• Weapons take feedback = 1/2 attack strength\n"
        "• Both robots thrown away along radiating vectors",
        fontsize=8, color=DARK_NAVY,
        bbox=dict(boxstyle="round,pad=0.25", facecolor=BOX_BG, edgecolor=BOX_BORDER)
    )

    # PANEL 2: Inversion, Wall Impact & Hazard Pit
    draw_arena_background(ax2, (0, 220), (0, 200), wall_sides=["right"], hazard_corner="top_right")
    ax2.set_title("Throw Flight, Inversion & Wall / Pit Hazards", fontsize=11, fontweight="bold", color=DARK_NAVY, pad=12)

    draw_robot(ax2, 70, 130, 45, chassis="Square", color=AMBER_NOTE, name="B", weapon="Circle", is_inverted=True)
    swirl = patches.Arc((70, 130), 45, 45, angle=0, theta1=30, theta2=330, color=CRIMSON, lw=2.0)
    ax2.add_patch(swirl)
    ax2.text(
        70, 72,
        "FLIP CHECK:\n(Throw Str - Distance) > Flip Value\n==> Robot is INVERTED!",
        fontsize=8, fontweight="bold", color=CRIMSON, ha="center",
        bbox=dict(boxstyle="round,pad=0.25", facecolor="#FEF2F2", edgecolor=CRIMSON)
    )

    draw_robot(ax2, 185, 80, -90, chassis="Triangle", color=LIGHT_BLUE, name="A", weapon="Bar")
    ax2.plot(208, 80, "*", color=CRIMSON, markersize=14, zorder=15)
    ax2.text(
        165, 45, "WALL HIT!\nThrow Shock\nFeedback",
        fontsize=7.5, fontweight="bold", color=CRIMSON, ha="center",
        bbox=dict(boxstyle="round,pad=0.2", facecolor="#FEF2F2", edgecolor=CRIMSON)
    )

    ax2.text(
        10, 22,
        "• Inverted robots cannot use standard drive/weapons\n"
        "• Wall shock: Inflicts full throw strength feedback\n"
        "• Pushed/Thrown into hazard pit = ELIMINATED!",
        fontsize=8, color=DARK_NAVY,
        bbox=dict(boxstyle="round,pad=0.25", facecolor=BOX_BG, edgecolor=BOX_BORDER)
    )

    plt.tight_layout()
    plt.savefig(output_path, dpi=250)
    plt.close()
    print(f"✔ Generated {output_path}")


# ----------------------------------------------------------------------
# 6. Diagram: Forks & Raised Status (Layout, Positive & Negative Angled Contact)
# ----------------------------------------------------------------------

def generate_forks_raised(output_path: Path) -> None:
    """Generates Section 6.4 Forks diagram: Automata Card Layout (Nightwing Wide), Positive & Negative Angled Contact."""
    fig = plt.figure(figsize=(15.0, 6.4), dpi=250)
    gs = fig.add_gridspec(1, 3, width_ratios=[1.15, 1.0, 1.0], wspace=0.24)

    # ------------------------------------------------------------------
    # PANEL 1: Automata Card Layout (Nightwing Wide with Forks)
    # ------------------------------------------------------------------
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.set_facecolor(ARENA_FLOOR)
    ax1.set_xlim(0, 240)
    ax1.set_ylim(0, 185)
    ax1.set_aspect("equal")
    ax1.axis("off")
    ax1.set_title("1. Automata Layout: Forks Mounted", fontsize=10.5, fontweight="bold", color=DARK_NAVY, pad=10)

    # Background card panel
    s_bg = patches.FancyBboxPatch(
        (8, 8), 224, 168,
        boxstyle="round,pad=1.5,rounding_size=3.0",
        facecolor=BOX_BG, edgecolor=BOX_BORDER, linewidth=1.5, zorder=1
    )
    ax1.add_patch(s_bg)

    ax1.annotate(
        "", xy=(120, 168), xytext=(120, 152),
        arrowprops=dict(arrowstyle="->", color=STEEL_BLUE, lw=2.2, mutation_scale=12),
        zorder=3
    )
    ax1.text(120, 172, "FRONT (HEADING)", fontsize=7.2, fontweight="bold", color=STEEL_BLUE, ha="center", zorder=3)

    # Nightwing Wide 3x3 layout (from automata/Nightwing_wide.csv)
    cw, ch = 65, 33
    cy_f, cy_m, cy_r = 130, 88, 46
    cx_l, cx_c, cx_r = 46, 120, 194

    # Front Row: Forks on Left & Right bumpers, Beater Bar in center
    draw_card(ax1, cx_l, cy_f, cw, ch, "Forks", category="forks", stats="Ground Wedge • Prongs Tpl")
    draw_card(ax1, cx_c, cy_f, cw, ch, "Beater Bar", category="weapon", stats="Front Weapon • Bar Tpl")
    draw_card(ax1, cx_r, cy_f, cw, ch, "Forks", category="forks", stats="Ground Wedge • Prongs Tpl")

    # Middle Row: Drive components
    draw_card(ax1, cx_l, cy_m, cw, ch, "Left Wheel", category="wheel", stats="Drive Wheel • 2 pts")
    draw_card(ax1, cx_c, cy_m, cw, ch, "Repeat 2207", category="motor", stats="Weapon Motor • 3 pts", is_shielded=True)
    draw_card(ax1, cx_r, cy_m, cw, ch, "Right Wheel", category="wheel", stats="Drive Wheel • 2 pts")

    # Rear Row
    draw_card(ax1, cx_l, cy_r, cw, ch, "Galaxy 120", category="esc", stats="ESC • 2 pts", is_shielded=True)
    draw_card(ax1, cx_c, cy_r, cw, ch, "Tattu 450", category="battery", stats="Battery • 2 pts", is_shielded=True)
    draw_card(ax1, cx_r, cy_r, cw, ch, "TPU Plate", category="armor", stats="Rear Bumper • 2 pts")

    ax1.text(
        120, 16,
        "Forks mounted on front perimeter cards extend forward,\nusing the Prongs template to establish ground-game zones.",
        fontsize=6.8, color=DARK_NAVY, ha="center", zorder=5
    )

    # ------------------------------------------------------------------
    # PANEL 2: Positive Example - Angled Engagement in Line With Forks
    # ------------------------------------------------------------------
    ax2 = fig.add_subplot(gs[0, 1])
    draw_arena_background(ax2, (0, 200), (0, 215))
    ax2.set_title("2. Positive: In Line With Forks", fontsize=10.5, fontweight="bold", color=SUCCESS_GREEN, pad=10)

    # Bot A (Wide chassis with Prongs template) shifted up to y=98
    # Bot B (Triangle chassis with Line template) shifted up to y=140
    draw_robot(ax2, 70, 98, 45, chassis="Wide", color=LIGHT_BLUE, name="A", weapon="Prongs")
    draw_robot(ax2, 116, 138, -110, chassis="Triangle", color=AMBER_NOTE, name="B", weapon="Line", is_raised=True)

    # Fork projection lines showing contact in-line
    ax2.plot([70, 110], [98, 138], color=CRIMSON, linestyle="--", lw=2.0, zorder=12)
    ax2.plot(100, 128, "*", color=CRIMSON, markersize=16, markeredgecolor=WALL_BLACK, zorder=15)

    ax2.text(
        100, 28,
        "POSITIVE ENGAGEMENT\n"
        "• Opponent contacts in line with forks\n"
        "• Bot B is lifted ==> RAISED!\n"
        "• Attacks throw strength -2\n"
        "  and 0 pushing contribution",
        fontsize=7.5, color=DARK_NAVY, ha="center",
        bbox=dict(boxstyle="round,pad=0.25", facecolor="#F0FDF4", edgecolor=SUCCESS_GREEN)
    )

    # ------------------------------------------------------------------
    # PANEL 3: Negative Example - Angled Contact Outside Fork Line
    # ------------------------------------------------------------------
    ax3 = fig.add_subplot(gs[0, 2])
    draw_arena_background(ax3, (0, 200), (0, 215))
    ax3.set_title("3. Negative: Outside Fork Line", fontsize=10.5, fontweight="bold", color=CRIMSON, pad=10)

    # Bot A (Wide chassis with Prongs template) shifted up to y=105
    # Bot B strikes Bot A on the side flank (outside prongs)
    draw_robot(ax3, 75, 105, 0, chassis="Wide", color=LIGHT_BLUE, name="A", weapon="Prongs")
    draw_robot(ax3, 126, 95, -90, chassis="Triangle", color=AMBER_NOTE, name="B", weapon="Line")

    # Flank contact point (outside fork prongs)
    ax3.plot(101, 100, "o", color=CRIMSON, markersize=10, markeredgecolor=WALL_BLACK, zorder=15)
    ax3.annotate(
        "Contact on flank\n(Outside fork line)",
        xy=(101, 100), xytext=(145, 145),
        arrowprops=dict(arrowstyle="->", color=CRIMSON, lw=2.0, mutation_scale=12),
        fontsize=7.5, fontweight="bold", color=CRIMSON, ha="center",
        bbox=dict(boxstyle="round,pad=0.2", facecolor="#FEF2F2", edgecolor=CRIMSON),
        zorder=20
    )

    ax3.text(
        100, 28,
        "NEGATIVE ENGAGEMENT\n"
        "• Opponent strikes side / flank\n"
        "• Contact is OUTSIDE the fork line\n"
        "• Bot B is NOT RAISED\n"
        "• Normal collision / strike resolves",
        fontsize=7.5, color=DARK_NAVY, ha="center",
        bbox=dict(boxstyle="round,pad=0.25", facecolor="#FEF2F2", edgecolor=CRIMSON)
    )

    plt.savefig(output_path, dpi=250, bbox_inches="tight")
    plt.close()
    print(f"✔ Generated {output_path}")


# ----------------------------------------------------------------------
# Main Execution
# ----------------------------------------------------------------------

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Generating refined rulebook illustrated diagrams with official templates...")

    generate_movement_straight_curve(OUTPUT_DIR / "diagram_movement_straight_curve.png")
    generate_movement_pivot_spin(OUTPUT_DIR / "diagram_movement_pivot_spin.png")
    generate_contact_point(OUTPUT_DIR / "diagram_contact_point.png")
    generate_inert_contact(OUTPUT_DIR / "diagram_inert_contact.png")
    generate_active_contact(OUTPUT_DIR / "diagram_active_contact.png")
    generate_forks_raised(OUTPUT_DIR / "diagram_forks_raised.png")

    print("\nAll 6 refined rulebook diagrams successfully generated in rules/images/!")


if __name__ == "__main__":
    main()
