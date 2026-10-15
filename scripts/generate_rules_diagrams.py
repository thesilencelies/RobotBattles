#!/usr/bin/env python3
"""
generate_rules_diagrams.py

Generates high-resolution, publication-quality diagrams for the Robot Battles rulebook:
1. diagram_movement_straight_curve.png - Straight forward (3/3), Reverse (-2/-2), Curve Right (2/1), Curve Left flipped (1/2)
2. diagram_movement_pivot_spin.png     - Pivot Fan (2/0 on locked wheel), Spin Disc (2/-2 on center)
3. diagram_contact_point.png           - Contact point determination along paths & Active vs. Inert classification
4. diagram_inert_contact.png           - Pushing match 4-step sequence (replaces editor note in Section 5.2)
5. diagram_active_contact.png          - Weapon strike, throw vectors, model spin, inversion flip check & wall impact
6. diagram_forks_raised.png            - Forks engagement, lifting opponent, and Raised status penalties

Adheres strictly to the rule that no mm conversions are shown (game units only).
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
    chassis: str = "wedge",  # "wedge", "square", "wide"
    color: str = LIGHT_BLUE,
    name: str = "A",
    weapon: Optional[str] = "drum",  # "drum", "disc", "forks", None
    is_inverted: bool = False,
    is_raised: bool = False,
    ghost: bool = False,
    zorder: int = 5,
    text_offset: Tuple[float, float] = (0.0, 0.0),
) -> None:
    """Draws an authentic robot miniature with chassis shape, wheels, front bumper, and active weapon red-zone."""
    rad = math.radians(heading_deg)
    alpha = 0.35 if ghost else 1.0

    if chassis == "wedge":
        base_poly = [
            (0.0, 22.0),
            (18.0, 6.0),
            (18.0, -18.0),
            (-18.0, -18.0),
            (-18.0, 6.0),
        ]
    elif chassis == "wide":
        base_poly = [
            (-24.0, 14.0),
            (24.0, 14.0),
            (24.0, -14.0),
            (-24.0, -14.0),
        ]
    else:  # square
        base_poly = [
            (-16.0, 18.0),
            (16.0, 18.0),
            (16.0, -18.0),
            (-16.0, -18.0),
        ]

    # Wheels
    wheel_offsets = [(-20.0, -2.0), (20.0, -2.0)] if chassis != "wide" else [(-26.0, -2.0), (26.0, -2.0)]
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

    if not ghost and not is_inverted:
        f_tip = rotate_point(cx, cy + (18.0 if chassis != "wedge" else 17.0), rad, cx, cy)
        f_b1 = rotate_point(cx - 5.0, cy + 9.0, rad, cx, cy)
        f_b2 = rotate_point(cx + 5.0, cy + 9.0, rad, cx, cy)
        arrow_poly = patches.Polygon([f_tip, f_b1, f_b2], closed=True, facecolor="#FFFFFF", edgecolor="none", alpha=0.8, zorder=zorder + 1)
        ax.add_patch(arrow_poly)

    if weapon and not ghost and not is_inverted:
        if weapon == "drum":
            d_pts = [
                (-9.0, 16.0), (9.0, 16.0), (9.0, 22.0), (-9.0, 22.0)
            ] if chassis != "wedge" else [
                (-7.0, 19.0), (7.0, 19.0), (7.0, 24.0), (-7.0, 24.0)
            ]
            world_d_pts = [rotate_point(px + cx, py + cy, rad, cx, cy) for px, py in d_pts]
            d_patch = patches.Polygon(world_d_pts, closed=True, facecolor=CRIMSON, edgecolor="#7F1D1D", linewidth=1.5, zorder=zorder + 2)
            ax.add_patch(d_patch)
        elif weapon == "disc":
            disc_center = rotate_point(cx, cy + 12.0, rad, cx, cy)
            disc_circle = patches.Circle(disc_center, radius=16.0, facecolor=LIGHT_RED, edgecolor=CRIMSON, linewidth=2.0, alpha=0.9, zorder=zorder + 2)
            ax.add_patch(disc_circle)
            pin = patches.Circle(disc_center, radius=3.0, facecolor=WALL_BLACK, zorder=zorder + 3)
            ax.add_patch(pin)
        elif weapon == "forks":
            fork_l = [(-11.0, 16.0), (-8.0, 16.0), (-8.0, 28.0), (-11.0, 24.0)]
            fork_r = [(8.0, 16.0), (11.0, 16.0), (11.0, 24.0), (8.0, 28.0)]
            for f_pts in [fork_l, fork_r]:
                w_f_pts = [rotate_point(px + cx, py + cy, rad, cx, cy) for px, py in f_pts]
                f_patch = patches.Polygon(w_f_pts, closed=True, facecolor=CRIMSON, edgecolor="#991B1B", linewidth=1.5, zorder=zorder + 2)
                ax.add_patch(f_patch)

    if not ghost:
        lbl = f"Bot {name}" if len(name) == 1 else name
        ax.text(
            cx + text_offset[0], cy - 2 + text_offset[1], lbl,
            color="#FFFFFF" if not is_inverted else WALL_BLACK,
            fontsize=8.5, fontweight="bold",
            ha="center", va="center", zorder=zorder + 3
        )

    if is_inverted:
        ax.text(
            cx, cy + 24, "INVERTED",
            color="#FFFFFF", fontsize=7.5, fontweight="bold",
            ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.25", facecolor=CRIMSON, edgecolor="none"),
            zorder=zorder + 4
        )
    elif is_raised:
        ax.text(
            cx, cy + 28, "⬆ RAISED",
            color="#FFFFFF", fontsize=8, fontweight="bold",
            ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.25", facecolor=AMBER_NOTE, edgecolor="none"),
            zorder=zorder + 4
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


# ----------------------------------------------------------------------
# 1. Diagram: Straight & Curve Movement Examples
# ----------------------------------------------------------------------

def generate_movement_straight_curve(output_path: Path) -> None:
    """Generates Section 4.4 movement examples: Straight (3/3), Reverse (-2/-2), Curve Right (2/1), Curve Left (1/2)."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.0, 6.2), dpi=250)

    # PANEL 1: Straight & Reverse
    draw_arena_background(ax1, (0, 240), (0, 220))
    ax1.set_title("1. Straight Driving (3/3) & Reverse (-2/-2)", fontsize=11, fontweight="bold", color=DARK_NAVY, pad=12)

    # Robot A: Straight 3/3
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

    draw_robot(ax1, 65, 43, 0, chassis="wedge", color=LIGHT_BLUE, name="A", ghost=True)
    draw_robot(ax1, 65, 43 + 3 * 35, 0, chassis="wedge", color=LIGHT_BLUE, name="A")
    ax1.annotate(
        "", xy=(32, 43 + 3 * 35 - 5), xytext=(32, 43 + 5),
        arrowprops=dict(arrowstyle="->", color=STEEL_BLUE, lw=2.5, mutation_scale=15),
        zorder=7
    )
    ax1.text(28, 95, "Advance\n3 units", fontsize=8, fontweight="bold", color=STEEL_BLUE, ha="right")

    # Robot B: Reverse -2/-2
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

    draw_robot(ax1, 175, 168, 0, chassis="square", color=AMBER_NOTE, name="B", ghost=True)
    draw_robot(ax1, 175, 168 - 2 * 35, 0, chassis="square", color=AMBER_NOTE, name="B")
    ax1.annotate(
        "", xy=(208, 168 - 2 * 35 + 5), xytext=(208, 168 - 5),
        arrowprops=dict(arrowstyle="->", color=CRIMSON, lw=2.5, mutation_scale=15),
        zorder=7
    )
    ax1.text(212, 133, "Reverse\n2 units", fontsize=8, fontweight="bold", color=CRIMSON, ha="left")

    # PANEL 2: Curved Arcs & Flipping
    draw_arena_background(ax2, (0, 240), (0, 220))
    ax2.set_title("2. Curved Arcs (2/1 Right) & Left Flipping (1/2)", fontsize=11, fontweight="bold", color=DARK_NAVY, pad=12)

    # Right Turn 2/1 (Face-Up)
    # Robot C is at (35, 33) facing North (0 deg). Front bumper at y=55.
    # Center of curvature is at (35 + 85, 55) = (120, 55).
    # Baseline is from x=(120 - 85)=35 to x=(120 - 50)=70.
    r_center_x, r_center_y = 115, 55
    r_out, r_in = 80, 45
    ax2.text(55, 205, "Right Turn (2/1): Face-Up\nSweeps 45° Clockwise", fontsize=8.5, fontweight="bold", color=STEEL_BLUE, ha="center")
    
    # Wedge sweeps from 135 deg to 180 deg
    wedge_r = patches.Wedge((r_center_x, r_center_y), r_out, 135, 180, width=(r_out - r_in), facecolor=BOX_BG, edgecolor=BOX_BORDER, linewidth=1.5, zorder=2)
    ax2.add_patch(wedge_r)
    # Baseline at 180 deg (horizontal line at y=55 from x=35 to x=70)
    ax2.plot([r_center_x - r_out, r_center_x - r_in], [r_center_y, r_center_y], color=WALL_BLACK, linewidth=3.5, zorder=3)
    ax2.text(r_center_x - (r_out + r_in) / 2, r_center_y - 8, "START FRONT", fontsize=7, fontweight="bold", ha="center", color=WALL_BLACK)
    
    # Line L2 R1 at 135 deg
    p1 = (r_center_x - r_out * math.cos(math.radians(45)), r_center_y + r_out * math.sin(math.radians(45)))
    p2 = (r_center_x - r_in * math.cos(math.radians(45)), r_center_y + r_in * math.sin(math.radians(45)))
    ax2.plot([p1[0], p2[0]], [p1[1], p2[1]], color=LIGHT_BLUE, linewidth=2.2, zorder=3)
    ax2.text(p1[0] - 6, p1[1] + 6, "L2 R1 (45°)", fontsize=7.5, fontweight="bold", color=STEEL_BLUE)

    # Initial Robot C (Ghost) at start baseline
    draw_robot(ax2, r_center_x - (r_out + r_in) / 2, r_center_y - 22, 0, chassis="wedge", color=LIGHT_BLUE, name="C", ghost=True)
    # Final Robot C at 45 deg line (turned 45 deg CW = heading -45 deg)
    r_mid = (r_out + r_in) / 2
    fc_cx = r_center_x - r_mid * math.cos(math.radians(45)) + 12 * math.sin(math.radians(45))
    fc_cy = r_center_y + r_mid * math.sin(math.radians(45)) + 12 * math.cos(math.radians(45))
    draw_robot(ax2, fc_cx, fc_cy, -45, chassis="wedge", color=LIGHT_BLUE, name="C")
    
    # Trajectory Arc
    arc_patch_r = patches.Arc((r_center_x, r_center_y), r_mid * 2, r_mid * 2, angle=0, theta1=140, theta2=175, color=STEEL_BLUE, lw=2.2, zorder=6)
    ax2.add_patch(arc_patch_r)

    # Left Turn 1/2 (Flipped Face-Down)
    # Robot D is at (185, 33) facing North. Front bumper at y=55.
    # Center of curvature is at (185 - 85, 55) = (125, 55).
    # Baseline is from x=(125 + 45)=170 to x=(125 + 80)=205.
    l_center_x, l_center_y = 125, 55
    ax2.text(185, 205, "Left Turn (1/2): FLIP Face-Down\nSweeps 45° Counter-Clockwise", fontsize=8.5, fontweight="bold", color=CRIMSON, ha="center")
    
    wedge_l = patches.Wedge((l_center_x, l_center_y), r_out, 0, 45, width=(r_out - r_in), facecolor=BOX_BG, edgecolor=BOX_BORDER, linewidth=1.5, zorder=2)
    ax2.add_patch(wedge_l)
    ax2.plot([l_center_x + r_in, l_center_x + r_out], [l_center_y, l_center_y], color=WALL_BLACK, linewidth=3.5, zorder=3)
    ax2.text(l_center_x + (r_out + r_in) / 2, l_center_y - 8, "START FRONT", fontsize=7, fontweight="bold", ha="center", color=WALL_BLACK)
    
    pl1 = (l_center_x + r_out * math.cos(math.radians(45)), l_center_y + r_out * math.sin(math.radians(45)))
    pl2 = (l_center_x + r_in * math.cos(math.radians(45)), l_center_y + r_in * math.sin(math.radians(45)))
    ax2.plot([pl1[0], pl2[0]], [pl1[1], pl2[1]], color=LIGHT_BLUE, linewidth=2.2, zorder=3)
    ax2.text(pl1[0] - 6, pl1[1] + 6, "L2 R1 (45°)", fontsize=7.5, fontweight="bold", color=STEEL_BLUE)

    draw_robot(ax2, l_center_x + (r_out + r_in) / 2, l_center_y - 22, 0, chassis="wide", color=AMBER_NOTE, name="D", ghost=True)
    fd_cx = l_center_x + r_mid * math.cos(math.radians(45)) - 12 * math.sin(math.radians(45))
    fd_cy = l_center_y + r_mid * math.sin(math.radians(45)) + 12 * math.cos(math.radians(45))
    draw_robot(ax2, fd_cx, fd_cy, 45, chassis="wide", color=AMBER_NOTE, name="D")
    
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

    # PANEL 1: Pivot Fan (2/0)
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

    draw_robot(ax1, pivot_x - 38, pivot_y - 18, 0, chassis="wedge", color=LIGHT_BLUE, name="A", ghost=True)
    draw_robot(ax1, pivot_x + 18, pivot_y + 38, -90, chassis="wedge", color=LIGHT_BLUE, name="A")
    arc_p = patches.Arc((pivot_x, pivot_y), 90, 90, angle=0, theta1=90, theta2=180, color=CRIMSON, lw=2.5, zorder=7)
    ax1.add_patch(arc_p)
    ax1.text(
        pivot_x - 75, pivot_y + 65, "Pivots 90° CW\n(2 × 45°/unit)",
        fontsize=8.5, fontweight="bold", color=CRIMSON,
        bbox=dict(boxstyle="round,pad=0.25", facecolor="#FEF2F2", edgecolor=CRIMSON)
    )

    # PANEL 2: Spin Disc (2/-2)
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

    # Initial ghost robot facing North (0 deg)
    draw_robot(ax2, disc_x, disc_y, 0, chassis="wide", color=AMBER_NOTE, name="B", ghost=True)
    # Final robot facing South (180 deg)
    draw_robot(ax2, disc_x, disc_y, 180, chassis="wide", color=AMBER_NOTE, name="B", text_offset=(0.0, 5.5))
    
    rot_arc = patches.Arc((disc_x, disc_y), 78, 78, angle=0, theta1=270, theta2=90, color=CRIMSON, lw=2.5, zorder=8)
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
# 3. Diagram: Contact Point Determination & Active vs. Inert
# ----------------------------------------------------------------------

def generate_contact_point(output_path: Path) -> None:
    """Generates Section 5.1 diagram: Contact point determination along paths and Active vs Inert."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.0, 5.8), dpi=250)

    # PANEL 1: Contact Point Determination
    draw_arena_background(ax1, (0, 220), (0, 200))
    ax1.set_title("Determining Contact Point Along Paths", fontsize=11, fontweight="bold", color=DARK_NAVY, pad=12)

    p_a_start = (45, 60)
    p_b_start = (175, 140)
    contact_pt = (110, 100)

    ax1.plot([p_a_start[0], contact_pt[0]], [p_a_start[1], contact_pt[1]], color=LIGHT_BLUE, linestyle="--", linewidth=2.0, zorder=2)
    ax1.plot([p_b_start[0], contact_pt[0]], [p_b_start[1], contact_pt[1]], color=AMBER_NOTE, linestyle="--", linewidth=2.0, zorder=2)

    draw_robot(ax1, p_a_start[0], p_a_start[1], -45, chassis="wedge", color=LIGHT_BLUE, name="A", ghost=True)
    draw_robot(ax1, p_b_start[0], p_b_start[1], 135, chassis="square", color=AMBER_NOTE, name="B", ghost=True)

    draw_robot(ax1, contact_pt[0] - 18, contact_pt[1] - 14, -45, chassis="wedge", color=LIGHT_BLUE, name="A")
    draw_robot(ax1, contact_pt[0] + 16, contact_pt[1] + 14, 135, chassis="square", color=AMBER_NOTE, name="B")

    ax1.plot(contact_pt[0], contact_pt[1], "*", color=CRIMSON, markersize=16, markeredgecolor=WALL_BLACK, markeredgewidth=1.2, zorder=15)
    ax1.text(
        contact_pt[0], contact_pt[1] - 24, "Contact Point\n(Octant: Front vs Front-Left)",
        color=WALL_BLACK, fontsize=8, fontweight="bold", ha="center",
        bbox=dict(boxstyle="round,pad=0.25", facecolor="#FEF2F2", edgecolor=CRIMSON),
        zorder=16
    )

    ax1.text(
        10, 185,
        "1. Move robots forward along paths\n2. Stop at first point of touching\n3. Contact point determines hit octant",
        fontsize=8.5, color=DARK_NAVY,
        bbox=dict(boxstyle="round,pad=0.3", facecolor=BOX_BG, edgecolor=BOX_BORDER)
    )

    # PANEL 2: Active vs. Inert Contact
    draw_arena_background(ax2, (0, 220), (0, 200))
    ax2.set_title("Active Contact vs. Inert Contact", fontsize=11, fontweight="bold", color=DARK_NAVY, pad=12)

    # Active Contact (Bot A drum directly touching Bot B bumper)
    ax2.text(55, 185, "ACTIVE CONTACT", fontsize=9.5, fontweight="bold", color=CRIMSON, ha="center")
    draw_robot(ax2, 55, 122, 180, chassis="wedge", color=LIGHT_BLUE, name="A", weapon="drum")
    draw_robot(ax2, 55, 80, 0, chassis="square", color=AMBER_NOTE, name="B", weapon=None)
    ax2.plot(55, 99, "*", color=CRIMSON, markersize=16, markeredgecolor=WALL_BLACK, zorder=15)
    ax2.text(
        55, 26, "Weapon Red-Zone touches!\n• Deals strike damage\n• Both bots THROWN away\n• Weapon takes feedback",
        fontsize=8, ha="center", color=DARK_NAVY,
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#FEF2F2", edgecolor=CRIMSON)
    )

    # Inert Contact (Chassis wedge directly touching flat armor)
    ax2.text(165, 185, "INERT CONTACT", fontsize=9.5, fontweight="bold", color=STEEL_BLUE, ha="center")
    draw_robot(ax2, 165, 120, 180, chassis="wedge", color=LIGHT_BLUE, name="A", weapon=None)
    draw_robot(ax2, 165, 84, 0, chassis="wide", color=AMBER_NOTE, name="B", weapon=None)
    ax2.plot(165, 98, "o", color=STEEL_BLUE, markersize=8, zorder=15)
    ax2.text(
        165, 26, "Chassis / Armor touches!\n• No active weapon involved\n• PUSHING MATCH occurs\n• Displace remainder template",
        fontsize=8, ha="center", color=DARK_NAVY,
        bbox=dict(boxstyle="round,pad=0.3", facecolor=BG_BLUE, edgecolor=STEEL_BLUE)
    )

    plt.tight_layout()
    plt.savefig(output_path, dpi=250)
    plt.close()
    print(f"✔ Generated {output_path}")


# ----------------------------------------------------------------------
# 4. Diagram: Inert Contact (Pushing Match) — REPLACES EDITOR NOTE
# ----------------------------------------------------------------------

def generate_inert_contact(output_path: Path) -> None:
    """Generates Section 5.2 Inert Contact (Pushing Match) 4-step sequence."""
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(14.0, 9.8), dpi=250)

    # STEP 1: Collision & Remaining Motion
    draw_arena_background(ax1, (0, 200), (0, 165))
    draw_step_badge(ax1, 10, 150, 1, "Initial Contact & Remaining Motion")

    c_x, c_y = 95, 75
    draw_robot(ax1, c_x - 18, c_y, -90, chassis="wedge", color=LIGHT_BLUE, name="A", weapon=None)
    draw_robot(ax1, c_x + 18, c_y, 90, chassis="wide", color=AMBER_NOTE, name="B", weapon=None)
    ax1.plot(c_x, c_y, "o", color=WALL_BLACK, markersize=7, zorder=12)

    ax1.annotate(
        "", xy=(c_x + 35, c_y + 15), xytext=(c_x, c_y),
        arrowprops=dict(arrowstyle="->", color=LIGHT_BLUE, lw=2.5, mutation_scale=14),
        zorder=10
    )
    ax1.text(c_x + 40, c_y + 18, "Remainder A ($v_A$)", fontsize=8, fontweight="bold", color=LIGHT_BLUE)

    ax1.annotate(
        "", xy=(c_x - 25, c_y + 25), xytext=(c_x, c_y),
        arrowprops=dict(arrowstyle="->", color=AMBER_NOTE, lw=2.5, mutation_scale=14),
        zorder=10
    )
    ax1.text(c_x - 30, c_y + 30, "Remainder B ($v_B$)", fontsize=8, fontweight="bold", color=AMBER_NOTE, ha="right")

    ax1.text(10, 18, "• Advance along templates until contact\n• Note remaining unspent distance on each template", fontsize=8, color=DARK_NAVY)

    # STEP 2: Displace Remainder Template
    draw_arena_background(ax2, (0, 200), (0, 165))
    draw_step_badge(ax2, 10, 150, 2, "Displace Remainder Template")

    draw_robot(ax2, c_x - 18, c_y, -90, chassis="wedge", color=LIGHT_BLUE, name="A", weapon=None, ghost=True)
    draw_robot(ax2, c_x + 18, c_y, 90, chassis="wide", color=AMBER_NOTE, name="B", weapon=None, ghost=True)
    ax2.plot(c_x, c_y, "o", color=WALL_BLACK, markersize=6, zorder=12)

    vb_tip = (c_x - 25, c_y + 25)
    ax2.annotate("", xy=vb_tip, xytext=(c_x, c_y), arrowprops=dict(arrowstyle="->", color=AMBER_NOTE, lw=2.0, mutation_scale=12))

    va_disp_tip = (vb_tip[0] + 35, vb_tip[1] + 15)
    ax2.annotate("", xy=va_disp_tip, xytext=vb_tip, arrowprops=dict(arrowstyle="->", color=LIGHT_BLUE, lw=2.5, linestyle="--", mutation_scale=14))
    ax2.text(va_disp_tip[0] + 5, va_disp_tip[1], "A displaced to\nend of B", fontsize=8, fontweight="bold", color=LIGHT_BLUE)

    ax2.text(10, 18, "• Displace remainder of Robot A's template\n  to the end of Robot B's template vector", fontsize=8, color=DARK_NAVY)

    # STEP 3: Straight Push Along Net Line
    draw_arena_background(ax3, (0, 200), (0, 165))
    draw_step_badge(ax3, 10, 150, 3, "Joint Push Along Net Vector")

    draw_robot(ax3, c_x - 18, c_y, -90, chassis="wedge", color=LIGHT_BLUE, name="A", weapon=None, ghost=True)
    draw_robot(ax3, c_x + 18, c_y, 90, chassis="wide", color=AMBER_NOTE, name="B", weapon=None, ghost=True)

    net_push_end = (c_x + 10, c_y + 40)
    ax3.annotate(
        "", xy=net_push_end, xytext=(c_x, c_y),
        arrowprops=dict(arrowstyle="->", color=CRIMSON, lw=3.0, mutation_scale=15),
        zorder=9
    )
    ax3.text(
        net_push_end[0] + 32, net_push_end[1] + 8, "Pushing Vector\n(Sum of motion)",
        fontsize=8, fontweight="bold", color=CRIMSON, ha="center",
        bbox=dict(boxstyle="round,pad=0.2", facecolor="#FEF2F2", edgecolor=CRIMSON)
    )

    draw_robot(ax3, c_x - 18 + 10, c_y + 40, -90, chassis="wedge", color=LIGHT_BLUE, name="A", weapon=None)
    draw_robot(ax3, c_x + 18 + 10, c_y + 40, 90, chassis="wide", color=AMBER_NOTE, name="B", weapon=None)

    ax3.text(10, 18, "• Both robots push together along straight line\n• Raised robot motion does NOT contribute", fontsize=8, color=DARK_NAVY)

    # STEP 4: Wall Collision & Separation
    draw_arena_background(ax4, (0, 200), (0, 175), wall_sides=["top"])
    draw_step_badge(ax4, 10, 142, 4, "Wall Impact & Full Unit Separation")

    draw_robot(ax4, 135, 145, 90, chassis="wide", color=AMBER_NOTE, name="B", weapon=None)
    ax4.plot(135, 162, "*", color=CRIMSON, markersize=15, zorder=15)
    ax4.text(
        135, 118, "WALL IMPACT!\nThrow strength = Lost distance",
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
    draw_robot(ax4, 40, 75, -90, chassis="wedge", color=LIGHT_BLUE, name="A", weapon=None)
    draw_robot(ax4, 145, 75, 90, chassis="wide", color=AMBER_NOTE, name="B", weapon=None)
    ax4.text(
        92, 58, "Separate 1 Full Unit\nif still touching!",
        fontsize=8, fontweight="bold", color=SUCCESS_GREEN, ha="center",
        bbox=dict(boxstyle="round,pad=0.2", facecolor="#F0FDF4", edgecolor=SUCCESS_GREEN)
    )

    ax4.text(10, 18, "• Wall collision throws bot away with lost distance\n• Weapon contacting wall loses spin & takes feedback\n• If still touching: move back 1 full unit to separate", fontsize=7.5, color=DARK_NAVY)

    plt.tight_layout()
    plt.savefig(output_path, dpi=250)
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
    draw_robot(ax1, cx - 16, cy, -90, chassis="wedge", color=LIGHT_BLUE, name="A", weapon="drum")
    draw_robot(ax1, cx + 16, cy, 90, chassis="square", color=AMBER_NOTE, name="B", weapon=None)

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
    ax1.text(cx + 70, cy + 42, "Throw Vector B\n(2d6 up to Throw Str)", fontsize=8, fontweight="bold", color=AMBER_NOTE, ha="center")

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

    draw_robot(ax2, 70, 130, 45, chassis="square", color=AMBER_NOTE, name="B", is_inverted=True)
    swirl = patches.Arc((70, 130), 45, 45, angle=0, theta1=30, theta2=330, color=CRIMSON, lw=2.0)
    ax2.add_patch(swirl)
    ax2.text(
        70, 72,
        "FLIP CHECK:\n(Throw Str - Distance) > Flip Value\n==> Robot is INVERTED!",
        fontsize=8, fontweight="bold", color=CRIMSON, ha="center",
        bbox=dict(boxstyle="round,pad=0.25", facecolor="#FEF2F2", edgecolor=CRIMSON)
    )

    draw_robot(ax2, 185, 80, -90, chassis="wedge", color=LIGHT_BLUE, name="A")
    ax2.plot(208, 80, "*", color=CRIMSON, markersize=14, zorder=15)
    ax2.text(
        165, 45, "WALL HIT!\nFull Throw Shock\nFeedback",
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
# 6. Diagram: Forks & Raised Status
# ----------------------------------------------------------------------

def generate_forks_raised(output_path: Path) -> None:
    """Generates Section 6.4 Forks engagement and Raised status penalties."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.0, 5.5), dpi=250)

    # PANEL 1: Fork Engagement
    draw_arena_background(ax1, (0, 220), (0, 180))
    ax1.set_title("Ground Game: Forks Lifting Opponent", fontsize=11, fontweight="bold", color=DARK_NAVY, pad=12)

    draw_robot(ax1, 65, 85, -90, chassis="wedge", color=LIGHT_BLUE, name="A", weapon="forks")
    draw_robot(ax1, 125, 85, 90, chassis="wide", color=AMBER_NOTE, name="B", weapon=None, is_raised=True)

    ax1.plot([97, 97], [65, 105], color=CRIMSON, linestyle=":", linewidth=2.0)
    ax1.text(
        97, 122, "In Line With Forks\n==> Opponent RAISED!",
        fontsize=8.5, fontweight="bold", color=CRIMSON, ha="center",
        bbox=dict(boxstyle="round,pad=0.25", facecolor="#FEF2F2", edgecolor=CRIMSON)
    )

    ax1.text(
        15, 22,
        "• If any part of opponent is in line with forks during contact\n"
        "• Opposing robot becomes RAISED for that contact\n"
        "• Forks do not function while inverted (unless Invertible)",
        fontsize=8, color=DARK_NAVY,
        bbox=dict(boxstyle="round,pad=0.25", facecolor=BOX_BG, edgecolor=BOX_BORDER)
    )

    # PANEL 2: Mechanical Effects of Raised Status
    draw_arena_background(ax2, (0, 220), (0, 180))
    ax2.set_title("Mechanical Penalties of RAISED Status", fontsize=11, fontweight="bold", color=DARK_NAVY, pad=12)

    effects = [
        ("1. Flip Strength Halved", "Chassis flip value is cut by half (easier to invert)"),
        ("2. Throw Strength Reduced", "Throw strength dealt to opponent is reduced by 2"),
        ("3. Zero Pushing Contribution", "Raised robot motion does not contribute in inertial contact"),
    ]

    for i, (title, desc) in enumerate(effects):
        y_pos = 135 - i * 42
        box = patches.FancyBboxPatch(
            (15, y_pos - 15), 190, 32,
            boxstyle="round,pad=2",
            facecolor=BG_AMBER if i == 2 else BOX_BG,
            edgecolor=AMBER_NOTE if i == 2 else STEEL_BLUE,
            linewidth=1.5, zorder=2
        )
        ax2.add_patch(box)
        ax2.text(25, y_pos + 4, title, fontsize=9, fontweight="bold", color=DARK_NAVY, zorder=3)
        ax2.text(25, y_pos - 8, desc, fontsize=7.5, color=TEXT_MUTED, zorder=3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=250)
    plt.close()
    print(f"✔ Generated {output_path}")


# ----------------------------------------------------------------------
# Main Execution
# ----------------------------------------------------------------------

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Generating refined rulebook illustrated diagrams...")

    generate_movement_straight_curve(OUTPUT_DIR / "diagram_movement_straight_curve.png")
    generate_movement_pivot_spin(OUTPUT_DIR / "diagram_movement_pivot_spin.png")
    generate_contact_point(OUTPUT_DIR / "diagram_contact_point.png")
    generate_inert_contact(OUTPUT_DIR / "diagram_inert_contact.png")
    generate_active_contact(OUTPUT_DIR / "diagram_active_contact.png")
    generate_forks_raised(OUTPUT_DIR / "diagram_forks_raised.png")

    print("\nAll 6 refined rulebook diagrams successfully generated in rules/images/!")


if __name__ == "__main__":
    main()
