#!/usr/bin/env python3
"""
generate_movement_templates.py

Generates physical movement templates for every permutation of differential drive
settings from -5 to +5 on each side (121 total permutations).

Minimizes the number of templates required:
1. Left/Right symmetry: Flipping the template horizontally turns rightward curves
   into leftward curves.
2. Forwards/Backwards: Placing the template start line at the back (rear) of the
   robot instead of the front executes reverse maneuvers along the exact same path.
3. Multi-distance & shared curvature: Multiple drive pairs sharing the identical
   radius of curvature are marked as distinct stop lines on the same physical template piece.

Outputs:
- Individual standalone SVG files for each template.
- Combined printable sheet(s) (SVG) for physical cutting/printing.
- Updated rulebook graphic (PNG / SVG).
- Complete permutation lookup catalog (Markdown / JSON).
"""

from __future__ import annotations

import argparse
from fractions import Fraction
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Set matplotlib cache directory if needed
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib_templates")

# Default Robot Dimensions in mm
DEFAULT_WHEELBASE_MM = 65.0   # Track width between wheels
DEFAULT_DRIVE_UNIT_MM = 40.0  # Linear displacement per 1 drive unit
DEFAULT_MINIATURE_RADIUS = 35.0

# ----------------------------------------------------------------------
# Geometry & Symmetry Math
# ----------------------------------------------------------------------

def map_permutation_to_template(
    left: int,
    right: int,
) -> Dict[str, Any]:
    """
    Maps an arbitrary (Left, Right) drive setting in [-5, 5] x [-5, 5]
    to its canonical template, indicating whether it requires flipping
    (for left turns) or placing at the rear (for reverse).
    """
    if left == 0 and right == 0:
        return {
            "template_id": "stop",
            "name": "Stop (0, 0)",
            "left": 0,
            "right": 0,
            "canonical_left": 0,
            "canonical_right": 0,
            "target_line_label": "N/A",
            "flipped": False,
            "at_rear": False,
            "category": "stop",
            "description": "No movement.",
        }

    # Symmetry candidates:
    # 1. (L, R)                -> as-is (flipped=False, at_rear=False)
    # 2. (R, L)                -> flipped (flipped=True, at_rear=False)
    # 3. (-L, -R)              -> at rear (flipped=False, at_rear=True)
    # 4. (-R, -L)              -> flipped + at rear (flipped=True, at_rear=True)
    candidates = [
        ((left, right), False, False),
        ((right, left), True, False),
        ((-left, -right), False, True),
        ((-right, -left), True, True),
    ]

    # Canonical selection rules:
    # We want candidate (l_c, r_c) such that:
    # - l_c >= r_c (curves right)
    # - l_c + r_c > 0 or (l_c + r_c == 0 and l_c > 0) (forward/neutral net motion)
    valid_cands = [
        c for c in candidates
        if c[0][0] >= c[0][1] and (c[0][0] + c[0][1] > 0 or (c[0][0] + c[0][1] == 0 and c[0][0] > 0))
    ]

    # Select the candidate with highest canonical L, then highest R
    best_cand = max(valid_cands, key=lambda c: (c[0][0], c[0][1]))
    (c_l, c_r), flipped, at_rear = best_cand

    # Categorize canonical pair
    remainder_note = ""
    if c_l == c_r:
        cat = "straight"
        t_id = "straight"
        name = "Straight Template"
        target_line = f"L{c_l} R{c_r}"
    elif c_l == -c_r:
        cat = "spin"
        t_id = "spin"
        name = "Spin Disc Template"
        if c_l > 4:
            rem = c_l - 4
            target_line = f"L4 R-4 + L{rem} R-{rem}"
            remainder_note = f"Move to end of Spin Disc (L4 R-4, 360°), then place template again for remainder (L{rem} R-{rem}, {rem*90}°). Total: {c_l*90}°."
        else:
            target_line = f"L{c_l} R{c_r}"
    elif c_r == 0:
        cat = "pivot"
        t_id = "pivot"
        name = "Pivot Fan Template"
        if c_l > 4:
            rem = c_l - 4
            target_line = f"L4 R0 + L{rem} R0"
            remainder_note = f"Move to end of Pivot Fan (L4 R0, 180°), then place template again for remainder (L{rem} R0, {rem*45}°). Total: {c_l*45}°."
        else:
            target_line = f"L{c_l} R{c_r}"
    elif c_r > 0:
        cat = "curve_forward"
        frac = Fraction(c_l, c_r)
        if frac == Fraction(2, 1):
            t_id = "curve_ratio_2_1"
            name = "Curve Template (2:1 Ratio)"
        else:
            t_id = f"curve_L{c_l}_R{c_r}"
            name = f"Curve Template ({c_l}, {c_r})"
        target_line = f"L{c_l} R{c_r}"
    else:  # c_r < 0
        cat = "curve_tight"
        frac = Fraction(c_l, -c_r)
        if frac == Fraction(2, 1):
            t_id = "tight_ratio_2_1"
            name = "Tight Turn Template (2:-1 Ratio)"
        else:
            t_id = f"tight_L{c_l}_Rm{-c_r}"
            name = f"Tight Turn Template ({c_l}, {c_r})"
        target_line = f"L{c_l} R{c_r}"

    return {
        "template_id": t_id,
        "name": name,
        "left": left,
        "right": right,
        "canonical_left": c_l,
        "canonical_right": c_r,
        "target_line_label": target_line,
        "remainder_note": remainder_note,
        "flipped": flipped,
        "at_rear": at_rear,
        "category": cat,
    }


def compute_all_permutations() -> List[Dict[str, Any]]:
    """Returns mapping for all 121 permutations from -5 to +5 on each side."""
    perms = []
    for l in range(-5, 6):
        for r in range(-5, 6):
            info = map_permutation_to_template(l, r)
            perms.append(info)
    return perms


# ----------------------------------------------------------------------
# Template Definitions
# ----------------------------------------------------------------------

class MovementTemplate:
    """Represents a physical movement template piece."""

    def __init__(
        self,
        template_id: str,
        name: str,
        category: str,
        pairs: List[Tuple[int, int]],
        wheelbase: float = DEFAULT_WHEELBASE_MM,
        drive_unit: float = DEFAULT_DRIVE_UNIT_MM,
    ):
        self.template_id = template_id
        self.name = name
        self.category = category
        self.pairs = pairs  # Canonical (L, R) pairs marked on this template
        self.wheelbase = wheelbase
        self.drive_unit = drive_unit

    def get_dimensions(self) -> Tuple[float, float]:
        """Returns approximate (width_mm, height_mm) bounding box."""
        if self.category == "straight":
            max_l = max(p[0] for p in self.pairs)
            return (self.wheelbase + 30.0, max_l * self.drive_unit + 40.0)
        elif self.category == "spin":
            radius = DEFAULT_MINIATURE_RADIUS
            return (radius * 2.0 + 80.0, radius * 2.0 + 70.0)
        elif self.category == "pivot":
            radius = self.wheelbase
            return (radius * 2.0 + 50.0, radius + 55.0)
        elif self.category == "curve_forward":
            max_l = max(p[0] for p in self.pairs)
            max_r = max(p[1] for p in self.pairs)
            diff = max_l - max_r
            r_out = self.wheelbase * max_l / diff
            d_theta = diff * (math.pi / 4.0)
            span_x = r_out * (1.0 - math.cos(min(d_theta, math.pi))) + self.wheelbase
            span_y = r_out * math.sin(min(d_theta, math.pi / 2.0)) + 40.0
            return (max(self.wheelbase + 40.0, span_x + 40.0), span_y + 40.0)
        else:  # curve_tight
            max_l = max(p[0] for p in self.pairs)
            min_r = min(p[1] for p in self.pairs)
            diff = max_l - min_r
            r_out = self.wheelbase * max_l / diff
            d_theta = diff * (math.pi / 4.0)
            span_x = r_out * (1.0 - math.cos(min(d_theta, math.pi))) + self.wheelbase
            span_y = r_out * math.sin(min(d_theta, math.pi / 2.0)) + 40.0
            return (max(self.wheelbase * 2.0 + 40.0, span_x + 40.0), span_y + 40.0)

    def render_svg_content(self, offset_x: float = 20.0, offset_y: float = 20.0) -> str:
        """Renders the SVG markup for this template piece."""
        w = self.wheelbase
        u = self.drive_unit

        svg_parts = []
        svg_parts.append(f'<g id="template_{self.template_id}">')

        if self.category == "straight":
            # Straight translation
            max_l = max(p[0] for p in self.pairs)
            total_height = max_l * u
            x0 = offset_x
            y_base = offset_y + total_height

            # Background contour
            svg_parts.append(
                f'<rect x="{x0}" y="{offset_y}" width="{w}" height="{total_height}" '
                f'fill="#f8fafc" stroke="#1e293b" stroke-width="2.5" rx="3" />'
            )

            # Centerline
            svg_parts.append(
                f'<line x1="{x0 + w/2}" y1="{y_base}" x2="{x0 + w/2}" y2="{offset_y}" '
                f'stroke="#94a3b8" stroke-width="1.2" stroke-dasharray="4,4" />'
            )

            # Start line (Black baseline at bottom)
            svg_parts.append(
                f'<line x1="{x0}" y1="{y_base}" x2="{x0 + w}" y2="{y_base}" '
                f'stroke="#0f172a" stroke-width="4.0" stroke-linecap="square" />'
            )
            svg_parts.append(
                f'<text x="{x0 + w/2}" y="{y_base + 12}" font-family="sans-serif" font-size="7.5" '
                f'font-weight="bold" fill="#0f172a" text-anchor="middle">START (ALIGN FRONT / REAR)</text>'
            )

            # Stop lines
            for l, r in self.pairs:
                line_y = y_base - l * u
                svg_parts.append(
                    f'<line x1="{x0}" y1="{line_y}" x2="{x0 + w}" y2="{line_y}" '
                    f'stroke="#2563eb" stroke-width="2.8" stroke-linecap="square" />'
                )
                svg_parts.append(
                    f'<text x="{x0 + w/2}" y="{line_y - 4}" font-family="sans-serif" font-size="9" '
                    f'font-weight="bold" fill="#1d4ed8" text-anchor="middle">L{l} R{r}</text>'
                )

            # Instructions label along edge
            svg_parts.append(
                f'<text x="{x0 + 4}" y="{offset_y + 12}" font-family="sans-serif" font-size="6.5" '
                f'fill="#64748b">STRAIGHT (1 to 5) | Back for -L -R</text>'
            )

        elif self.category == "spin":
            # Spin on spot disc: 90 deg increments per 1 drive unit (4 units = 360 deg)
            radius = DEFAULT_MINIATURE_RADIUS
            cx = offset_x + radius + 35.0
            cy = offset_y + radius + 25.0

            # Disc circle
            svg_parts.append(
                f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="#f8fafc" stroke="#1e293b" stroke-width="2.5" />'
            )
            # Center pin
            svg_parts.append(f'<circle cx="{cx}" cy="{cy}" r="3" fill="#0f172a" />')

            # Baseline at angle 0 (North: dx=0, dy=-radius)
            svg_parts.append(
                f'<line x1="{cx}" y1="{cy}" x2="{cx}" y2="{cy - radius}" '
                f'stroke="#0f172a" stroke-width="3.5" stroke-linecap="round" />'
            )
            svg_parts.append(
                f'<text x="{cx}" y="{cy - radius - 6}" font-family="sans-serif" font-size="7.5" '
                f'font-weight="bold" fill="#0f172a" text-anchor="middle">START (0°)</text>'
            )

            # Markings for each spin unit (L, -L)
            for l, r in self.pairs:
                d_theta = l * (math.pi / 2.0)
                px = cx + radius * math.sin(d_theta)
                py = cy - radius * math.cos(d_theta)
                if l < 4:
                    svg_parts.append(
                        f'<line x1="{cx}" y1="{cy}" x2="{px}" y2="{py}" stroke="#2563eb" stroke-width="2.4" />'
                    )
                if l == 1:
                    svg_parts.append(
                        f'<text x="{px + 6}" y="{py + 3}" font-family="sans-serif" font-size="7.5" '
                        f'font-weight="bold" fill="#1d4ed8" text-anchor="start">L1 R-1 (90°)</text>'
                    )
                elif l == 2:
                    svg_parts.append(
                        f'<text x="{px}" y="{py + 12}" font-family="sans-serif" font-size="7.5" '
                        f'font-weight="bold" fill="#1d4ed8" text-anchor="middle">L2 R-2 (180°)</text>'
                    )
                elif l == 3:
                    svg_parts.append(
                        f'<text x="{px - 6}" y="{py + 3}" font-family="sans-serif" font-size="7.5" '
                        f'font-weight="bold" fill="#1d4ed8" text-anchor="end">L3 R-3 (270°)</text>'
                    )
                elif l == 4:
                    svg_parts.append(
                        f'<text x="{cx}" y="{cy - radius - 15}" font-family="sans-serif" font-size="7.5" '
                        f'font-weight="bold" fill="#1d4ed8" text-anchor="middle">L4 R-4 (360° Full)</text>'
                    )

            # Circular clockwise guide arrow
            arc_r = radius * 0.55
            svg_parts.append(
                f'<path d="M {cx + arc_r} {cy} A {arc_r} {arc_r} 0 0 1 {cx} {cy + arc_r}" '
                f'fill="none" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="3,3" />'
            )

            svg_parts.append(
                f'<text x="{cx}" y="{cy + radius + 25}" font-family="sans-serif" font-size="6.5" '
                f'fill="#64748b" text-anchor="middle">SPIN DISC | 90° / unit | Flip for CCW</text>'
            )
            svg_parts.append(
                f'<text x="{cx}" y="{cy + radius + 34}" font-family="sans-serif" font-size="5.8" '
                f'fill="#94a3b8" text-anchor="middle">&gt;4: Move to end (L4 R-4, 360°) + Remainder</text>'
            )

        elif self.category == "pivot":
            # Pivot around right wheel: 45 deg per 1 drive unit (hits 180 deg at 4, 0)
            radius = w
            cx = offset_x + radius + 25.0
            cy = offset_y + radius + 15.0

            x_start = cx - radius
            y_start = cy
            x_end = cx + radius
            y_end = cy

            # Semicircle contour
            path_d = f"M {cx} {cy} L {x_start} {y_start} A {radius} {radius} 0 0 1 {x_end} {y_end} Z"
            svg_parts.append(
                f'<path d="{path_d}" fill="#f8fafc" stroke="#1e293b" stroke-width="2.5" />'
            )
            svg_parts.append(f'<circle cx="{cx}" cy="{cy}" r="3.5" fill="#ef4444" />')
            svg_parts.append(
                f'<text x="{cx}" y="{cy + 13}" font-family="sans-serif" font-size="6.5" '
                f'font-weight="bold" fill="#ef4444" text-anchor="middle">PIVOT WHEEL</text>'
            )

            # Start line along baseline left: (cx - radius, cy) to (cx, cy)
            svg_parts.append(
                f'<line x1="{x_start}" y1="{y_start}" x2="{cx}" y2="{cy}" '
                f'stroke="#0f172a" stroke-width="3.8" stroke-linecap="square" />'
            )
            svg_parts.append(
                f'<text x="{x_start + radius/2}" y="{cy + 12}" font-family="sans-serif" '
                f'font-size="7" font-weight="bold" fill="#0f172a" text-anchor="middle">START FRONT</text>'
            )

            for l, r in self.pairs:
                d_th = l * (math.pi / 4.0)
                px = cx - radius * math.cos(d_th)
                py = cy - radius * math.sin(d_th)
                svg_parts.append(
                    f'<line x1="{cx}" y1="{cy}" x2="{px}" y2="{py}" stroke="#2563eb" stroke-width="2.4" stroke-linecap="square" />'
                )
                label_x = cx - (radius * 0.65) * math.cos(d_th)
                label_y = cy - (radius * 0.65) * math.sin(d_th)
                if l == 4:
                    svg_parts.append(
                        f'<text x="{cx + radius/2}" y="{cy + 12}" font-family="sans-serif" font-size="7.5" '
                        f'font-weight="bold" fill="#1d4ed8" text-anchor="middle">L4 R0 (180°)</text>'
                    )
                else:
                    deg_val = l * 45
                    svg_parts.append(
                        f'<text x="{label_x}" y="{label_y - 2}" font-family="sans-serif" font-size="7.5" '
                        f'font-weight="bold" fill="#1d4ed8" text-anchor="middle">L{l} R0 ({deg_val}°)</text>'
                    )

            svg_parts.append(
                f'<text x="{cx}" y="{cy + 25}" font-family="sans-serif" font-size="6.5" '
                f'fill="#64748b" text-anchor="middle">PIVOT FAN | 45° / unit | 4 units = 180° | Flip for (0, L) | Back for Reverse</text>'
            )
            svg_parts.append(
                f'<text x="{cx}" y="{cy + 34}" font-family="sans-serif" font-size="5.8" '
                f'fill="#94a3b8" text-anchor="middle">&gt;4: Move to end (L4 R0, 180°) + Remainder</text>'
            )

        elif self.category == "curve_forward":
            # Forward curved arc: 45 deg per 1 unit differential
            max_l = max(p[0] for p in self.pairs)
            max_r = max(p[1] for p in self.pairs)
            diff = max_l - max_r
            r_in = w * max_r / diff
            r_out = w * max_l / diff
            d_theta_max = diff * (math.pi / 4.0)

            cx = offset_x + r_out
            cy = offset_y + r_out * math.sin(min(d_theta_max, math.pi / 2)) + 20.0

            p_out_start = (cx - r_out, cy)
            p_in_start = (cx - r_in, cy)

            p_out_end = (cx - r_out * math.cos(d_theta_max), cy - r_out * math.sin(d_theta_max))
            p_in_end = (cx - r_in * math.cos(d_theta_max), cy - r_in * math.sin(d_theta_max))

            large_arc = 1 if d_theta_max > math.pi else 0

            path_d = (
                f"M {p_out_start[0]} {p_out_start[1]} "
                f"A {r_out} {r_out} 0 {large_arc} 1 {p_out_end[0]} {p_out_end[1]} "
                f"L {p_in_end[0]} {p_in_end[1]} "
                f"A {r_in} {r_in} 0 {large_arc} 0 {p_in_start[0]} {p_in_start[1]} Z"
            )

            svg_parts.append(
                f'<path d="{path_d}" fill="#f8fafc" stroke="#1e293b" stroke-width="2.5" />'
            )

            # Centerline
            r_mid = (r_in + r_out) / 2.0
            p_mid_start = (cx - r_mid, cy)
            p_mid_end = (cx - r_mid * math.cos(d_theta_max), cy - r_mid * math.sin(d_theta_max))
            mid_path = (
                f"M {p_mid_start[0]} {p_mid_start[1]} "
                f"A {r_mid} {r_mid} 0 {large_arc} 1 {p_mid_end[0]} {p_mid_end[1]}"
            )
            svg_parts.append(
                f'<path d="{mid_path}" fill="none" stroke="#94a3b8" stroke-width="1.2" stroke-dasharray="4,4" />'
            )

            # Start line
            svg_parts.append(
                f'<line x1="{p_out_start[0]}" y1="{p_out_start[1]}" x2="{p_in_start[0]}" y2="{p_in_start[1]}" '
                f'stroke="#0f172a" stroke-width="3.8" stroke-linecap="square" />'
            )
            svg_parts.append(
                f'<text x="{(p_out_start[0] + p_in_start[0])/2}" y="{cy + 11}" font-family="sans-serif" '
                f'font-size="7" font-weight="bold" fill="#0f172a" text-anchor="middle">START FRONT</text>'
            )

            for l, r in self.pairs:
                d_th = (l - r) * (math.pi / 4.0)
                p_out = (cx - r_out * math.cos(d_th), cy - r_out * math.sin(d_th))
                p_in = (cx - r_in * math.cos(d_th), cy - r_in * math.sin(d_th))
                svg_parts.append(
                    f'<line x1="{p_out[0]}" y1="{p_out[1]}" x2="{p_in[0]}" y2="{p_in[1]}" '
                    f'stroke="#2563eb" stroke-width="2.8" stroke-linecap="square" />'
                )
                lbl_x = (p_out[0] + p_in[0]) / 2.0
                lbl_y = (p_out[1] + p_in[1]) / 2.0
                svg_parts.append(
                    f'<text x="{lbl_x}" y="{lbl_y - 3}" font-family="sans-serif" font-size="8" '
                    f'font-weight="bold" fill="#1d4ed8" text-anchor="middle">L{l} R{r}</text>'
                )

            svg_parts.append(
                f'<text x="{offset_x + 5}" y="{offset_y + 12}" font-family="sans-serif" font-size="6.5" '
                f'fill="#64748b">CURVE | Flip for L&lt;R | Back for -L -R</text>'
            )

        elif self.category == "curve_tight":
            # Counter-drive tight curve: 45 deg per 1 unit differential
            max_l = max(p[0] for p in self.pairs)
            min_r = min(p[1] for p in self.pairs)
            diff = max_l - min_r
            d_theta_max = diff * (math.pi / 4.0)

            r_out = w * max_l / diff
            r_in = math.fabs(w * min_r / diff)

            cx = offset_x + w + 15.0
            cy = offset_y + w + 15.0

            p_out_start = (cx - r_out, cy)
            p_in_start = (cx + r_in, cy)

            p_out_end = (cx - r_out * math.cos(d_theta_max), cy - r_out * math.sin(d_theta_max))
            p_in_end = (cx + r_in * math.cos(d_theta_max), cy + r_in * math.sin(d_theta_max))

            large_arc = 1 if d_theta_max > math.pi else 0

            path_d = (
                f"M {p_out_start[0]} {p_out_start[1]} "
                f"A {r_out} {r_out} 0 {large_arc} 1 {p_out_end[0]} {p_out_end[1]} "
                f"L {p_in_end[0]} {p_in_end[1]} "
                f"A {r_in} {r_in} 0 {large_arc} 0 {p_in_start[0]} {p_in_start[1]} Z"
            )

            svg_parts.append(
                f'<path d="{path_d}" fill="#f8fafc" stroke="#1e293b" stroke-width="2.5" />'
            )

            svg_parts.append(
                f'<line x1="{p_out_start[0]}" y1="{p_out_start[1]}" x2="{p_in_start[0]}" y2="{p_in_start[1]}" '
                f'stroke="#0f172a" stroke-width="3.8" stroke-linecap="square" />'
            )
            svg_parts.append(
                f'<text x="{(p_out_start[0] + p_in_start[0])/2}" y="{cy + 12}" font-family="sans-serif" '
                f'font-size="7" font-weight="bold" fill="#0f172a" text-anchor="middle">START</text>'
            )

            for l, r in self.pairs:
                d_th = (l - r) * (math.pi / 4.0)
                p_out = (cx - r_out * math.cos(d_th), cy - r_out * math.sin(d_th))
                p_in = (cx + r_in * math.cos(d_th), cy + r_in * math.sin(d_th))
                svg_parts.append(
                    f'<line x1="{p_out[0]}" y1="{p_out[1]}" x2="{p_in[0]}" y2="{p_in[1]}" '
                    f'stroke="#2563eb" stroke-width="2.8" stroke-linecap="square" />'
                )
                lbl_x = (p_out[0] + p_in[0]) / 2.0
                lbl_y = (p_out[1] + p_in[1]) / 2.0
                svg_parts.append(
                    f'<text x="{lbl_x}" y="{lbl_y - 3}" font-family="sans-serif" font-size="7.5" '
                    f'font-weight="bold" fill="#1d4ed8" text-anchor="middle">L{l} R{r}</text>'
                )

            svg_parts.append(
                f'<text x="{offset_x + 5}" y="{offset_y + 12}" font-family="sans-serif" font-size="6.5" '
                f'fill="#64748b">TIGHT TURN | Flip for L&lt;R</text>'
            )

        svg_parts.append("</g>")
        return "\n".join(svg_parts)

    def to_svg(self) -> str:
        """Renders complete standalone SVG document."""
        bw, bh = self.get_dimensions()
        svg_header = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {bw:.1f} {bh:.1f}" '
            f'width="{bw:.1f}mm" height="{bh:.1f}mm">\n'
            f'  <defs>\n'
            f'    <style>\n'
            f'      text {{ user-select: none; }}\n'
            f'    </style>\n'
            f'  </defs>\n'
            f'  <rect width="100%" height="100%" fill="#ffffff" />\n'
        )
        body = self.render_svg_content(offset_x=15.0, offset_y=15.0)
        svg_footer = "\n</svg>"
        return svg_header + body + svg_footer


def build_all_movement_templates(
    wheelbase: float = DEFAULT_WHEELBASE_MM,
    drive_unit: float = DEFAULT_DRIVE_UNIT_MM,
) -> List[MovementTemplate]:
    """
    Constructs the minimal set of 21 physical MovementTemplate instances
    covering every permutation from -5 to +5 on both tracks.
    """
    templates: List[MovementTemplate] = []

    # 1. Straight Template: (1, 1) to (5, 5)
    templates.append(
        MovementTemplate(
            template_id="straight",
            name="Straight Template",
            category="straight",
            pairs=[(1, 1), (2, 2), (3, 3), (4, 4), (5, 5)],
            wheelbase=wheelbase,
            drive_unit=drive_unit,
        )
    )

    # 2. Spin Disc Template: (1, -1) to (4, -4) [4 units = 360° full rotation]
    templates.append(
        MovementTemplate(
            template_id="spin",
            name="Spin Disc Template",
            category="spin",
            pairs=[(1, -1), (2, -2), (3, -3), (4, -4)],
            wheelbase=wheelbase,
            drive_unit=drive_unit,
        )
    )

    # 3. Pivot Fan Template: (1, 0) to (4, 0) [4 units = 180° semicircle]
    templates.append(
        MovementTemplate(
            template_id="pivot",
            name="Pivot Fan Template",
            category="pivot",
            pairs=[(1, 0), (2, 0), (3, 0), (4, 0)],
            wheelbase=wheelbase,
            drive_unit=drive_unit,
        )
    )

    # 4. Proportional Forward Curves
    # Ratio 2:1 shared template: (2, 1) and (4, 2)
    templates.append(
        MovementTemplate(
            template_id="curve_ratio_2_1",
            name="Curve Template (2:1 Ratio)",
            category="curve_forward",
            pairs=[(2, 1), (4, 2)],
            wheelbase=wheelbase,
            drive_unit=drive_unit,
        )
    )

    # Irreducible forward curves
    fwd_pairs = [
        ((3, 1), "curve_L3_R1", "Curve Template (3, 1)"),
        ((4, 1), "curve_L4_R1", "Curve Template (4, 1)"),
        ((5, 1), "curve_L5_R1", "Curve Template (5, 1)"),
        ((3, 2), "curve_L3_R2", "Curve Template (3, 2)"),
        ((4, 3), "curve_L4_R3", "Curve Template (4, 3)"),
        ((5, 4), "curve_L5_R4", "Curve Template (5, 4)"),
        ((5, 2), "curve_L5_R2", "Curve Template (5, 2)"),
        ((5, 3), "curve_L5_R3", "Curve Template (5, 3)"),
    ]
    for p, tid, tname in fwd_pairs:
        templates.append(
            MovementTemplate(
                template_id=tid,
                name=tname,
                category="curve_forward",
                pairs=[p],
                wheelbase=wheelbase,
                drive_unit=drive_unit,
            )
        )

    # 5. Counter-drive Tight Turns
    # Ratio -2:1 shared template: (2, -1) and (4, -2)
    templates.append(
        MovementTemplate(
            template_id="tight_ratio_2_1",
            name="Tight Turn Template (2:-1 Ratio)",
            category="curve_tight",
            pairs=[(2, -1), (4, -2)],
            wheelbase=wheelbase,
            drive_unit=drive_unit,
        )
    )

    # Irreducible counter-drive tight turns
    tight_pairs = [
        ((3, -1), "tight_L3_Rm1", "Tight Turn Template (3, -1)"),
        ((4, -1), "tight_L4_Rm1", "Tight Turn Template (4, -1)"),
        ((5, -1), "tight_L5_Rm1", "Tight Turn Template (5, -1)"),
        ((3, -2), "tight_L3_Rm2", "Tight Turn Template (3, -2)"),
        ((4, -3), "tight_L4_Rm3", "Tight Turn Template (4, -3)"),
        ((5, -4), "tight_L5_Rm4", "Tight Turn Template (5, -4)"),
        ((5, -2), "tight_L5_Rm2", "Tight Turn Template (5, -2)"),
        ((5, -3), "tight_L5_Rm3", "Tight Turn Template (5, -3)"),
    ]
    for p, tid, tname in tight_pairs:
        templates.append(
            MovementTemplate(
                template_id=tid,
                name=tname,
                category="curve_tight",
                pairs=[p],
                wheelbase=wheelbase,
                drive_unit=drive_unit,
            )
        )

    return templates


# ----------------------------------------------------------------------
# Printable Sheet & Rulebook Preview Generation
# ----------------------------------------------------------------------

def generate_printable_sheet_svg(
    templates: List[MovementTemplate],
    sheet_width_mm: float = 420.0,  # A3 Landscape
    sheet_height_mm: float = 297.0,
) -> str:
    """Arranges templates onto a printable multi-template sheet."""
    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {sheet_width_mm} {sheet_height_mm}" '
        f'width="{sheet_width_mm}mm" height="{sheet_height_mm}mm">',
        '  <rect width="100%" height="100%" fill="#ffffff" stroke="#cbd5e1" stroke-width="1" />',
        '  <text x="20" y="22" font-family="sans-serif" font-size="14" font-weight="bold" fill="#0f172a">ROBOT BATTLES - MOVEMENT TEMPLATES</text>',
        '  <text x="20" y="32" font-family="sans-serif" font-size="7.5" fill="#475569">Complete range -5 to +5. Flip face-down for left turns. Place at rear for reverse.</text>',
        '  <!-- 50mm Calibration Scale Bar -->',
        '  <line x1="320" y1="20" x2="370" y2="20" stroke="#0f172a" stroke-width="2.5" />',
        '  <text x="345" y="27" font-family="sans-serif" font-size="6" fill="#0f172a" text-anchor="middle">50 mm SCALE BAR</text>',
    ]

    # Grid packing for A3 sheet
    x_cursor = 20.0
    y_cursor = 45.0
    max_row_height = 0.0

    for t in templates:
        bw, bh = t.get_dimensions()
        if x_cursor + bw > sheet_width_mm - 15.0:
            x_cursor = 20.0
            y_cursor += max_row_height + 10.0
            max_row_height = 0.0

        if y_cursor + bh > sheet_height_mm - 15.0:
            pass

        svg_parts.append(t.render_svg_content(offset_x=x_cursor, offset_y=y_cursor))
        x_cursor += bw + 8.0
        max_row_height = max(max_row_height, bh)

    svg_parts.append("</svg>")
    return "\n".join(svg_parts)


def generate_rulebook_preview_svg(
    templates: List[MovementTemplate],
    width_px: int = 890,
    height_px: int = 890,
) -> str:
    """
    Renders an elegant rulebook preview graphic highlighting the core template
    families (Straight, Curve, Spin Disc, Pivot Fan) with annotations
    demonstrating flipping and rear placement.
    """
    t_map = {t.template_id: t for t in templates}
    t_straight = t_map.get("straight")
    t_curve = t_map.get("curve_ratio_2_1")
    t_spin = t_map.get("spin")
    t_pivot = t_map.get("pivot")

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width_px} {height_px}" width="{width_px}" height="{height_px}">
  <rect width="100%" height="100%" fill="#ffffff" />

  <!-- Straight Template (Left) -->
  <g transform="translate(60, 45) scale(2.8)">
    {t_straight.render_svg_content(offset_x=0, offset_y=0) if t_straight else ''}
  </g>

  <!-- Curve Template (Top Right) -->
  <g transform="translate(340, 50) scale(2.2)">
    {t_curve.render_svg_content(offset_x=0, offset_y=0) if t_curve else ''}
  </g>

  <!-- Spin Disc Template (Bottom Center) -->
  <g transform="translate(350, 590) scale(2.2)">
    {t_spin.render_svg_content(offset_x=0, offset_y=0) if t_spin else ''}
  </g>

  <!-- Pivot Fan Template (Bottom Right) -->
  <g transform="translate(560, 560) scale(2.2)">
    {t_pivot.render_svg_content(offset_x=0, offset_y=0) if t_pivot else ''}
  </g>

  <!-- Explanatory Rulebook Callouts -->
  <g font-family="sans-serif" fill="#1e293b">
    <!-- Straight notes -->
    <text x="60" y="820" font-size="16" font-weight="bold">Straight (1 to 5)</text>
    <text x="60" y="842" font-size="13" fill="#64748b">Place at rear for reverse (-1 to -5)</text>

    <!-- Curve notes -->
    <text x="560" y="440" font-size="16" font-weight="bold">Curve (Ratio 2:1)</text>
    <text x="560" y="462" font-size="13" fill="#64748b">Flip face-down for Left Turn</text>
    <text x="560" y="482" font-size="13" fill="#64748b">Place at rear for Reverse</text>

    <!-- Spin notes -->
    <text x="350" y="842" font-size="14" font-weight="bold" text-anchor="middle">Spin on Spot</text>
    <text x="350" y="862" font-size="12" fill="#64748b" text-anchor="middle">Rotate around center</text>

    <!-- Pivot notes -->
    <text x="730" y="842" font-size="14" font-weight="bold" text-anchor="middle">Pivot Fan</text>
    <text x="730" y="862" font-size="12" fill="#64748b" text-anchor="middle">Pivot on stationary wheel</text>
  </g>
</svg>"""
    return svg


def generate_permutation_markdown(perms: List[Dict[str, Any]]) -> str:
    """Generates a complete markdown reference table of all 121 permutations."""
    md = [
        "# Movement Permutation Catalog (-5 to +5)\n\n",
        "This table details all **121 combinations** of Left and Right drive settings, "
        "the physical template to use, and whether to **flip** the template (for left turns) "
        "or place it at the **rear** (for reverse).\n\n",
        "| Left | Right | Template Name | Target Line | Flip? | Position | Category |\n",
        "|:---:|:---:|:---|:---:|:---:|:---:|:---|\n",
    ]
    for p in sorted(perms, key=lambda x: (x["left"], x["right"])):
        if p["category"] == "stop":
            md.append(f"| {p['left']:+d} | {p['right']:+d} | Stop (No Template) | N/A | No | N/A | Stationary |\n")
        else:
            flip_str = "**YES (Face-down)**" if p["flipped"] else "No"
            pos_str = "**Back (Rear)**" if p["at_rear"] else "Front"
            md.append(
                f"| {p['left']:+d} | {p['right']:+d} | {p['name']} | `{p['target_line_label']}` | "
                f"{flip_str} | {pos_str} | {p['category']} |\n"
            )
    return "".join(md)


# ----------------------------------------------------------------------
# CLI Main
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate physical movement templates for every permutation from -5 to 5."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("movement_templates"),
        help="Directory to save individual template SVG files.",
    )
    parser.add_argument(
        "--sheet",
        type=Path,
        default=None,
        help="Output path for printable multi-template sheet SVG.",
    )
    parser.add_argument(
        "--rules-image",
        type=Path,
        default=Path("rules/images/movement_templates.png"),
        help="Path to generate/update the rulebook preview graphic.",
    )
    parser.add_argument(
        "--wheelbase",
        type=float,
        default=DEFAULT_WHEELBASE_MM,
        help=f"Robot wheelbase / track width in mm (default: {DEFAULT_WHEELBASE_MM}).",
    )
    parser.add_argument(
        "--drive-unit",
        type=float,
        default=DEFAULT_DRIVE_UNIT_MM,
        help=f"Displacement per 1 drive unit in mm (default: {DEFAULT_DRIVE_UNIT_MM}).",
    )

    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating movement templates (Wheelbase: {args.wheelbase}mm, Unit: {args.drive_unit}mm)...")
    templates = build_all_movement_templates(wheelbase=args.wheelbase, drive_unit=args.drive_unit)
    print(f"Created {len(templates)} minimal movement templates.")

    # 1. Output individual SVG templates
    for t in templates:
        file_path = args.output_dir / f"{t.template_id}.svg"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(t.to_svg())
    print(f"Saved {len(templates)} individual SVG templates to {args.output_dir}/")

    # 2. Output permutation catalog
    perms = compute_all_permutations()
    catalog_md = generate_permutation_markdown(perms)
    catalog_path = args.output_dir / "README.md"
    with open(catalog_path, "w", encoding="utf-8") as f:
        f.write(catalog_md)
    print(f"Saved complete 121-permutation catalog to {catalog_path}")

    # 3. Output printable sheet
    sheet_svg_path = args.sheet or (args.output_dir / "movement_templates_sheet.svg")
    sheet_svg = generate_printable_sheet_svg(templates)
    with open(sheet_svg_path, "w", encoding="utf-8") as f:
        f.write(sheet_svg)
    print(f"Saved printable sheet to {sheet_svg_path}")

    # 4. Generate rulebook preview
    if args.rules_image:
        args.rules_image.parent.mkdir(parents=True, exist_ok=True)
        preview_svg = generate_rulebook_preview_svg(templates)
        preview_svg_path = args.rules_image.with_suffix(".svg")
        with open(preview_svg_path, "w", encoding="utf-8") as f:
            f.write(preview_svg)

        png_rendered = False
        try:
            import cairosvg
            cairosvg.svg2png(bytestring=preview_svg.encode("utf-8"), write_to=str(args.rules_image))
            png_rendered = True
        except ImportError:
            pass

        if not png_rendered:
            try:
                import matplotlib
                matplotlib.use("Agg")
                import matplotlib.pyplot as plt
                import matplotlib.patches as patches
                import numpy as np

                fig, ax = plt.subplots(figsize=(9, 9), dpi=100)
                ax.set_xlim(0, 900)
                ax.set_ylim(900, 0)
                ax.axis("off")

                # 1. Straight template (Left)
                rect = patches.Rectangle((60, 60), 180, 560, facecolor="#f8fafc", edgecolor="#1e293b", linewidth=2.5)
                ax.add_patch(rect)
                ax.plot([60, 240], [620, 620], color="#0f172a", linewidth=4.5)
                ax.text(150, 642, "START (ALIGN FRONT / REAR)", fontsize=8.5, fontweight="bold", ha="center", color="#0f172a")

                for k in range(1, 6):
                    ly = 620 - k * 105
                    if k < 5:
                        ax.plot([60, 240], [ly, ly], color="#2563eb", linewidth=2.5)
                    ax.text(150, ly + 55, f"L{k} R{k}", fontsize=13, fontweight="bold", ha="center", va="center", color="#1e293b")

                ax.text(150, 820, "STRAIGHT (1 to 5)", fontsize=13, fontweight="bold", ha="center", color="#0f172a")
                ax.text(150, 842, "Place at rear for Reverse (-1 to -5)", fontsize=10, ha="center", color="#475569")

                # 2. Curve template (Top Right)
                arc_wedge = patches.Wedge((640, 420), 320, 180, 270, width=150, facecolor="#f8fafc", edgecolor="#1e293b", linewidth=2.5)
                ax.add_patch(arc_wedge)

                ax.plot([320, 470], [420, 420], color="#0f172a", linewidth=4.5)
                ax.text(395, 442, "START FRONT", fontsize=8.5, fontweight="bold", ha="center", color="#0f172a")

                th1 = np.radians(180 + 45.0)
                p1_out = (640 + 320 * np.cos(th1), 420 + 320 * np.sin(th1))
                p1_in = (640 + 170 * np.cos(th1), 420 + 170 * np.sin(th1))
                ax.plot([p1_out[0], p1_in[0]], [p1_out[1], p1_in[1]], color="#2563eb", linewidth=2.5)
                ax.text((p1_out[0]+p1_in[0])/2 - 20, (p1_out[1]+p1_in[1])/2 + 25, "L2 R1 (45°)", fontsize=11, fontweight="bold", color="#1e293b", ha="center")

                th2 = np.radians(180 + 90.0)
                p2_out = (640 + 320 * np.cos(th2), 420 + 320 * np.sin(th2))
                p2_in = (640 + 170 * np.cos(th2), 420 + 170 * np.sin(th2))
                ax.plot([p2_out[0], p2_in[0]], [p2_out[1], p2_in[1]], color="#2563eb", linewidth=2.5)
                ax.text((p2_out[0]+p2_in[0])/2 - 20, (p2_out[1]+p2_in[1])/2 + 25, "L4 R2 (90°)", fontsize=11, fontweight="bold", color="#1e293b", ha="center")

                ax.text(640, 460, "CURVE (Ratio 2:1)", fontsize=13, fontweight="bold", ha="center", color="#0f172a")
                ax.text(640, 482, "Flip for Left Turn | Place at rear for Reverse", fontsize=10, ha="center", color="#475569")

                # 3. Spin disc (Bottom Center)
                cx_s, cy_s = 350, 680
                r_s = 70
                spin_circ = patches.Circle((cx_s, cy_s), r_s, facecolor="#f8fafc", edgecolor="#1e293b", linewidth=2.5)
                ax.add_patch(spin_circ)
                ax.plot(cx_s, cy_s, "ko", markersize=4)

                ax.plot([cx_s, cx_s], [cy_s, cy_s - r_s], color="#0f172a", linewidth=4)
                ax.text(cx_s, cy_s - r_s - 8, "START / L4 R-4 (360°)", fontsize=7.5, fontweight="bold", ha="center", color="#0f172a")

                for k, lbl in [(1, "L1 R-1 (90°)"), (2, "L2 R-2 (180°)"), (3, "L3 R-3 (270°)")]:
                    ang = np.radians(k * 90.0 - 90.0)
                    px = cx_s + r_s * np.cos(ang)
                    py = cy_s + r_s * np.sin(ang)
                    ax.plot([cx_s, px], [cy_s, py], color="#2563eb", linewidth=2.2)
                    tx = cx_s + (r_s * 0.6) * np.cos(ang) + (10 if np.cos(ang) > 0 else (-10 if np.cos(ang) < 0 else 0))
                    ty = cy_s + (r_s * 0.6) * np.sin(ang) + (12 if np.sin(ang) > 0 else (-6 if np.sin(ang) < 0 else 0))
                    ax.text(tx, ty, lbl, fontsize=8, fontweight="bold", color="#1e293b", ha="center")

                ax.text(cx_s, 785, "SPIN DISC (90° / unit)", fontsize=12, fontweight="bold", ha="center", color="#0f172a")
                ax.text(cx_s, 807, "Rotate on center | Flip for CCW", fontsize=9.5, ha="center", color="#475569")
                ax.text(cx_s, 825, ">4: L4 R-4 (360°) + Remainder", fontsize=8.5, ha="center", color="#64748b")

                # 4. Pivot fan (Bottom Right)
                cx_p, cy_p = 720, 680
                r_p = 140
                piv_wedge = patches.Wedge((cx_p, cy_p), r_p, 180, 360, facecolor="#f8fafc", edgecolor="#1e293b", linewidth=2.5)
                ax.add_patch(piv_wedge)
                ax.plot(cx_p, cy_p, "ro", markersize=7)
                ax.text(cx_p, cy_p + 15, "PIVOT WHEEL", fontsize=8, fontweight="bold", color="#ef4444", ha="center")

                ax.plot([cx_p - r_p, cx_p], [cy_p, cy_p], color="#0f172a", linewidth=4)
                ax.text(cx_p - r_p/2, cy_p + 16, "START FRONT", fontsize=8, fontweight="bold", ha="center", color="#0f172a")

                for k in [1, 2, 3, 4]:
                    th_p = np.radians(180 + k * 45.0)
                    px = cx_p + r_p * np.cos(th_p)
                    py = cy_p + r_p * np.sin(th_p)
                    ax.plot([cx_p, px], [cy_p, py], color="#2563eb", linewidth=2.2)
                    if k == 4:
                        ax.text(cx_p + r_p/2, cy_p + 16, "L4 R0 (180°)", fontsize=8.5, fontweight="bold", color="#1d4ed8", ha="center")
                    else:
                        deg_lbl = k * 45
                        tx = cx_p + (r_p * 0.65) * np.cos(th_p)
                        ty = cy_p + (r_p * 0.65) * np.sin(th_p)
                        ax.text(tx, ty, f"L{k} R0 ({deg_lbl}°)", fontsize=8, fontweight="bold", color="#1e293b", ha="center")

                ax.text(cx_p, 815, "PIVOT FAN (45° / unit, 4 = 180°)", fontsize=12, fontweight="bold", ha="center", color="#0f172a")
                ax.text(cx_p, 835, "Flip for (0, L) | Back for Reverse", fontsize=9.5, ha="center", color="#475569")
                ax.text(cx_p, 852, ">4: L4 R0 (180°) + Remainder", fontsize=8.5, ha="center", color="#64748b")

                plt.tight_layout()
                fig.savefig(str(args.rules_image), dpi=100)
                plt.close(fig)
                png_rendered = True
            except Exception as e:
                print(f"Warning: Could not render PNG preview ({e}). SVG preview is available at {preview_svg_path}")

        if png_rendered:
            print(f"Updated rulebook graphic at {args.rules_image}")


if __name__ == "__main__":
    main()
