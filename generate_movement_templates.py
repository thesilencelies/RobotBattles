#!/usr/bin/env python3
"""
generate_movement_templates.py

Generates physical movement templates for every permutation of differential drive
settings from -5 to +5 on each side (121 total permutations).

Consolidated to 8 physical templates:
1. Core (3 Pieces): Straight, Spin Disc, Pivot Fan
2. Forward Curves (3 Pieces): Gentle Curve (45°), Medium Curve (90°), Sharp Curve (135°-180°)
3. Counter-Drive Tight Turns (2 Pieces): Tight Hook (R = -1), Tight Counter-Spin (R <= -2)

Symmetries:
1. Left/Right symmetry: Flipping the template horizontally turns rightward curves
   into leftward curves.
2. Forwards/Backwards: Placing the template start line at the back (rear) of the
   robot instead of the front executes reverse maneuvers along the exact same path.
3. Multi-setting curves with non-orthogonal stop lines: Routes with similar curvature
   share a physical template piece, with stop lines drawn at the required bumper angle.

Note: No template titles/names are printed on the physical pieces per game design.
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

    # Categorize canonical pair across the 8 consolidated templates
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
        diff = c_l - c_r
        if diff == 1:
            t_id = "curve_gentle"
            name = "Gentle Curve Template"
        elif diff == 2:
            t_id = "curve_medium"
            name = "Medium Curve Template"
        else:  # diff >= 3
            t_id = "curve_sharp"
            name = "Sharp Curve Template"
        target_line = f"L{c_l} R{c_r}"
    else:  # c_r < 0
        cat = "curve_tight"
        if c_r == -1:
            t_id = "tight_hook"
            name = "Tight Hook Template"
        else:  # c_r <= -2
            t_id = "tight_spin"
            name = "Tight Counter-Spin Template"
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
        nominal_rc: float = 100.0,
        r_out: float = 50.0,
        r_in: float = 15.0,
        wheelbase: float = DEFAULT_WHEELBASE_MM,
        drive_unit: float = DEFAULT_DRIVE_UNIT_MM,
    ):
        self.template_id = template_id
        self.name = name
        self.category = category
        self.pairs = pairs  # Canonical (L, R) pairs marked on this template
        self.nominal_rc = nominal_rc
        self.r_out = r_out
        self.r_in = r_in
        self.wheelbase = wheelbase
        self.drive_unit = drive_unit

    def get_dimensions(self) -> Tuple[float, float]:
        """Returns approximate (width_mm, height_mm) bounding box."""
        w = self.wheelbase
        u = self.drive_unit
        if self.category == "straight":
            max_l = max(p[0] for p in self.pairs)
            return (w + 30.0, max_l * u + 40.0)
        elif self.category == "spin":
            radius = DEFAULT_MINIATURE_RADIUS
            return (radius * 2.0 + 80.0, radius * 2.0 + 60.0)
        elif self.category == "pivot":
            radius = w
            return (radius * 2.0 + 50.0, radius + 55.0)
        elif self.category == "curve_forward":
            r_out = self.nominal_rc + w / 2.0
            max_phi = max((l + r) / 2.0 * u / self.nominal_rc for l, r in self.pairs) + math.radians(6.0)
            span_x = r_out * (1.0 - math.cos(min(max_phi, math.pi))) + w + 30.0
            span_y = r_out * math.sin(min(max_phi, math.pi / 2.0)) + 40.0
            return (max(span_x, w + 40.0), span_y + 30.0)
        else:  # curve_tight
            span = (self.r_out + self.r_in) * 1.5 + 40.0
            return (span, span)

    def render_svg_content(self, offset_x: float = 20.0, offset_y: float = 20.0) -> str:
        """
        Renders the SVG markup for this template piece.
        Note: Per user requirement, template names/titles are not printed on the physical pieces.
        Only start baselines, stop lines, degree/unit indicators, and drive pair labels are drawn.
        """
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
                f'<rect x="{x0:.1f}" y="{offset_y:.1f}" width="{w:.1f}" height="{total_height:.1f}" '
                f'fill="#f8fafc" stroke="#1e293b" stroke-width="2.5" rx="3" />'
            )

            # Centerline
            svg_parts.append(
                f'<line x1="{x0 + w/2:.1f}" y1="{y_base:.1f}" x2="{x0 + w/2:.1f}" y2="{offset_y:.1f}" '
                f'stroke="#94a3b8" stroke-width="1.2" stroke-dasharray="4,4" />'
            )

            # Start line (Black baseline at bottom)
            svg_parts.append(
                f'<line x1="{x0:.1f}" y1="{y_base:.1f}" x2="{x0 + w:.1f}" y2="{y_base:.1f}" '
                f'stroke="#0f172a" stroke-width="4.0" stroke-linecap="square" />'
            )
            svg_parts.append(
                f'<text x="{x0 + w/2:.1f}" y="{y_base + 12:.1f}" font-family="sans-serif" font-size="7.5" '
                f'font-weight="bold" fill="#0f172a" text-anchor="middle">START</text>'
            )

            # Stop lines
            for l, r in self.pairs:
                line_y = y_base - l * u
                svg_parts.append(
                    f'<line x1="{x0:.1f}" y1="{line_y:.1f}" x2="{x0 + w:.1f}" y2="{line_y:.1f}" '
                    f'stroke="#2563eb" stroke-width="2.8" stroke-linecap="square" />'
                )
                svg_parts.append(
                    f'<text x="{x0 + w/2:.1f}" y="{line_y - 4:.1f}" font-family="sans-serif" font-size="9" '
                    f'font-weight="bold" fill="#1d4ed8" text-anchor="middle">L{l} R{r}</text>'
                )

        elif self.category == "spin":
            # Spin on spot disc: 90 deg increments per 1 drive unit (4 units = 360 deg)
            radius = DEFAULT_MINIATURE_RADIUS
            cx = offset_x + radius + 35.0
            cy = offset_y + radius + 25.0

            # Disc circle
            svg_parts.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius:.1f}" fill="#f8fafc" stroke="#1e293b" stroke-width="2.5" />'
            )
            # Center pin
            svg_parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3" fill="#0f172a" />')

            # Baseline at angle 0 (North: dx=0, dy=-radius)
            svg_parts.append(
                f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{cx:.1f}" y2="{cy - radius:.1f}" '
                f'stroke="#0f172a" stroke-width="3.5" stroke-linecap="round" />'
            )
            svg_parts.append(
                f'<text x="{cx:.1f}" y="{cy - radius - 6:.1f}" font-family="sans-serif" font-size="7.5" '
                f'font-weight="bold" fill="#0f172a" text-anchor="middle">START</text>'
            )

            # Markings for each spin unit (L, -L)
            for l, r in self.pairs:
                d_theta = l * (math.pi / 2.0)
                px = cx + radius * math.sin(d_theta)
                py = cy - radius * math.cos(d_theta)
                if l < 4:
                    svg_parts.append(
                        f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{px:.1f}" y2="{py:.1f}" stroke="#2563eb" stroke-width="2.4" />'
                    )
                if l == 1:
                    svg_parts.append(
                        f'<text x="{px + 6:.1f}" y="{py + 3:.1f}" font-family="sans-serif" font-size="7.5" '
                        f'font-weight="bold" fill="#1d4ed8" text-anchor="start">L1 R-1 (90°)</text>'
                    )
                elif l == 2:
                    svg_parts.append(
                        f'<text x="{px:.1f}" y="{py + 12:.1f}" font-family="sans-serif" font-size="7.5" '
                        f'font-weight="bold" fill="#1d4ed8" text-anchor="middle">L2 R-2 (180°)</text>'
                    )
                elif l == 3:
                    svg_parts.append(
                        f'<text x="{px - 6:.1f}" y="{py + 3:.1f}" font-family="sans-serif" font-size="7.5" '
                        f'font-weight="bold" fill="#1d4ed8" text-anchor="end">L3 R-3 (270°)</text>'
                    )
                elif l == 4:
                    svg_parts.append(
                        f'<text x="{cx:.1f}" y="{cy - radius - 15:.1f}" font-family="sans-serif" font-size="7.5" '
                        f'font-weight="bold" fill="#1d4ed8" text-anchor="middle">L4 R-4 (360°)</text>'
                    )

            # Circular clockwise guide arrow
            arc_r = radius * 0.55
            svg_parts.append(
                f'<path d="M {cx + arc_r:.1f} {cy:.1f} A {arc_r:.1f} {arc_r:.1f} 0 0 1 {cx:.1f} {cy + arc_r:.1f}" '
                f'fill="none" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="3,3" />'
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
            path_d = f"M {cx:.1f} {cy:.1f} L {x_start:.1f} {y_start:.1f} A {radius:.1f} {radius:.1f} 0 0 1 {x_end:.1f} {y_end:.1f} Z"
            svg_parts.append(
                f'<path d="{path_d}" fill="#f8fafc" stroke="#1e293b" stroke-width="2.5" />'
            )
            svg_parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3.5" fill="#ef4444" />')
            svg_parts.append(
                f'<text x="{cx:.1f}" y="{cy + 13:.1f}" font-family="sans-serif" font-size="7" '
                f'font-weight="bold" fill="#ef4444" text-anchor="middle">PIN</text>'
            )

            # Start line along baseline
            svg_parts.append(
                f'<line x1="{x_start:.1f}" y1="{y_start:.1f}" x2="{cx:.1f}" y2="{cy:.1f}" '
                f'stroke="#0f172a" stroke-width="4.0" stroke-linecap="square" />'
            )
            svg_parts.append(
                f'<text x="{(x_start + cx)/2:.1f}" y="{cy + 12:.1f}" font-family="sans-serif" font-size="7" '
                f'font-weight="bold" fill="#0f172a" text-anchor="middle">START</text>'
            )

            # Pivot stop lines: 45, 90, 135, 180 deg
            for l, r in self.pairs:
                d_th = l * (math.pi / 4.0)
                px = cx - radius * math.cos(d_th)
                py = cy - radius * math.sin(d_th)
                if l < 4:
                    svg_parts.append(
                        f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{px:.1f}" y2="{py:.1f}" stroke="#2563eb" stroke-width="2.6" />'
                    )
                deg_label = l * 45
                lbl_x = cx - (radius * 0.68) * math.cos(d_th)
                lbl_y = cy - (radius * 0.68) * math.sin(d_th)
                if l == 4:
                    svg_parts.append(
                        f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{x_end:.1f}" y2="{y_end:.1f}" stroke="#2563eb" stroke-width="2.6" />'
                    )
                    svg_parts.append(
                        f'<text x="{cx + radius/2:.1f}" y="{cy + 12:.1f}" font-family="sans-serif" font-size="7.5" '
                        f'font-weight="bold" fill="#1d4ed8" text-anchor="middle">L4 R0 (180°)</text>'
                    )
                else:
                    svg_parts.append(
                        f'<text x="{lbl_x:.1f}" y="{lbl_y - 3:.1f}" font-family="sans-serif" font-size="7.5" '
                        f'font-weight="bold" fill="#1d4ed8" text-anchor="middle">L{l} R0 ({deg_label}°)</text>'
                    )

        elif self.category == "curve_forward":
            # Forward curved channel with non-orthogonal bumper stop lines
            r_in = self.nominal_rc - w / 2.0
            r_out = self.nominal_rc + w / 2.0
            max_phi = max((l + r) / 2.0 * u / self.nominal_rc for l, r in self.pairs)
            max_arc = max_phi + math.radians(6.0)

            cx = offset_x + r_out
            cy = offset_y + r_out * math.sin(min(max_arc, math.pi / 2.0)) + 25.0

            p_out_start = (cx - r_out, cy)
            p_in_start = (cx - r_in, cy)

            p_out_end = (cx - r_out * math.cos(max_arc), cy - r_out * math.sin(max_arc))
            p_in_end = (cx - r_in * math.cos(max_arc), cy - r_in * math.sin(max_arc))

            large_arc = 1 if max_arc > math.pi else 0

            path_d = (
                f"M {p_out_start[0]:.1f} {p_out_start[1]:.1f} "
                f"A {r_out:.1f} {r_out:.1f} 0 {large_arc} 1 {p_out_end[0]:.1f} {p_out_end[1]:.1f} "
                f"L {p_in_end[0]:.1f} {p_in_end[1]:.1f} "
                f"A {r_in:.1f} {r_in:.1f} 0 {large_arc} 0 {p_in_start[0]:.1f} {p_in_start[1]:.1f} Z"
            )

            svg_parts.append(
                f'<path d="{path_d}" fill="#f8fafc" stroke="#1e293b" stroke-width="2.5" />'
            )

            # Centerline
            p_mid_start = (cx - self.nominal_rc, cy)
            p_mid_end = (cx - self.nominal_rc * math.cos(max_arc), cy - self.nominal_rc * math.sin(max_arc))
            mid_path = (
                f"M {p_mid_start[0]:.1f} {p_mid_start[1]:.1f} "
                f"A {self.nominal_rc:.1f} {self.nominal_rc:.1f} 0 {large_arc} 1 {p_mid_end[0]:.1f} {p_mid_end[1]:.1f}"
            )
            svg_parts.append(
                f'<path d="{mid_path}" fill="none" stroke="#94a3b8" stroke-width="1.2" stroke-dasharray="4,4" />'
            )

            # Start line
            svg_parts.append(
                f'<line x1="{p_out_start[0]:.1f}" y1="{p_out_start[1]:.1f}" x2="{p_in_start[0]:.1f}" y2="{p_in_start[1]:.1f}" '
                f'stroke="#0f172a" stroke-width="4.0" stroke-linecap="square" />'
            )
            svg_parts.append(
                f'<text x="{(p_out_start[0] + p_in_start[0])/2:.1f}" y="{cy + 12:.1f}" font-family="sans-serif" '
                f'font-size="7.5" font-weight="bold" fill="#0f172a" text-anchor="middle">START</text>'
            )

            # Non-orthogonal bumper stop lines for each pair
            for l, r in self.pairs:
                dist = (l + r) / 2.0 * u
                phi = dist / self.nominal_rc
                th = math.radians((l - r) * 45.0)

                pc_x = cx - self.nominal_rc * math.cos(phi)
                pc_y = cy - self.nominal_rc * math.sin(phi)

                bx = math.cos(th)
                by = math.sin(th)

                p_left = (pc_x - (w / 2.0) * bx, pc_y - (w / 2.0) * by)
                p_right = (pc_x + (w / 2.0) * bx, pc_y + (w / 2.0) * by)

                svg_parts.append(
                    f'<line x1="{p_left[0]:.1f}" y1="{p_left[1]:.1f}" x2="{p_right[0]:.1f}" y2="{p_right[1]:.1f}" '
                    f'stroke="#2563eb" stroke-width="2.8" stroke-linecap="square" />'
                )

                txt_x = pc_x - 5.0 * math.sin(th)
                txt_y = pc_y + 5.0 * math.cos(th)
                svg_parts.append(
                    f'<text x="{txt_x:.1f}" y="{txt_y:.1f}" font-family="sans-serif" font-size="8" '
                    f'font-weight="bold" fill="#1d4ed8" text-anchor="middle">L{l} R{r}</text>'
                )

        elif self.category == "curve_tight":
            # Counter-drive tight curve channel
            cx = offset_x + self.r_out + 20.0
            cy = offset_y + self.r_out + 20.0

            max_deg = max((l - r) * 45.0 for l, r in self.pairs) + 8.0
            max_rad = math.radians(max_deg)

            p_out_start = (cx - self.r_out, cy)
            p_in_start = (cx + self.r_in, cy)

            p_out_end = (cx - self.r_out * math.cos(max_rad), cy - self.r_out * math.sin(max_rad))
            p_in_end = (cx + self.r_in * math.cos(max_rad), cy + self.r_in * math.sin(max_rad))

            large_arc = 1 if max_rad > math.pi else 0

            path_d = (
                f"M {p_out_start[0]:.1f} {p_out_start[1]:.1f} "
                f"A {self.r_out:.1f} {self.r_out:.1f} 0 {large_arc} 1 {p_out_end[0]:.1f} {p_out_end[1]:.1f} "
                f"L {p_in_end[0]:.1f} {p_in_end[1]:.1f} "
                f"A {self.r_in:.1f} {self.r_in:.1f} 0 {large_arc} 0 {p_in_start[0]:.1f} {p_in_start[1]:.1f} Z"
            )

            svg_parts.append(
                f'<path d="{path_d}" fill="#f8fafc" stroke="#1e293b" stroke-width="2.5" />'
            )

            # Center rotation pin
            svg_parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="2.5" fill="#94a3b8" />')

            # Start line
            svg_parts.append(
                f'<line x1="{p_out_start[0]:.1f}" y1="{p_out_start[1]:.1f}" x2="{p_in_start[0]:.1f}" y2="{p_in_start[1]:.1f}" '
                f'stroke="#0f172a" stroke-width="4.0" stroke-linecap="square" />'
            )
            svg_parts.append(
                f'<text x="{(p_out_start[0] + p_in_start[0])/2:.1f}" y="{cy + 12:.1f}" font-family="sans-serif" '
                f'font-size="7" font-weight="bold" fill="#0f172a" text-anchor="middle">START</text>'
            )

            # Stop lines
            for l, r in self.pairs:
                d_th = (l - r) * (math.pi / 4.0)
                p_out = (cx - self.r_out * math.cos(d_th), cy - self.r_out * math.sin(d_th))
                p_in = (cx + self.r_in * math.cos(d_th), cy + self.r_in * math.sin(d_th))

                svg_parts.append(
                    f'<line x1="{p_out[0]:.1f}" y1="{p_out[1]:.1f}" x2="{p_in[0]:.1f}" y2="{p_in[1]:.1f}" '
                    f'stroke="#2563eb" stroke-width="2.8" stroke-linecap="square" />'
                )

                lbl_x = (p_out[0] + p_in[0]) / 2.0
                lbl_y = (p_out[1] + p_in[1]) / 2.0
                svg_parts.append(
                    f'<text x="{lbl_x:.1f}" y="{lbl_y - 3:.1f}" font-family="sans-serif" font-size="7.5" '
                    f'font-weight="bold" fill="#1d4ed8" text-anchor="middle">L{l} R{r}</text>'
                )

        svg_parts.append("</g>")
        return "\n".join(svg_parts)

    def to_svg(self, transparent_bg: bool = False) -> str:
        """Renders complete standalone SVG document."""
        bw, bh = self.get_dimensions()
        bg_rect = "" if transparent_bg else '  <rect width="100%" height="100%" fill="#ffffff" />\n'
        svg_header = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {bw:.1f} {bh:.1f}" '
            f'width="{bw:.1f}mm" height="{bh:.1f}mm">\n'
            f'  <defs>\n'
            f'    <style>\n'
            f'      text {{ user-select: none; }}\n'
            f'    </style>\n'
            f'  </defs>\n'
            f'{bg_rect}'
        )
        body = self.render_svg_content(offset_x=15.0, offset_y=15.0)
        svg_footer = "\n</svg>"
        return svg_header + body + svg_footer


def build_all_movement_templates(
    wheelbase: float = DEFAULT_WHEELBASE_MM,
    drive_unit: float = DEFAULT_DRIVE_UNIT_MM,
) -> List[MovementTemplate]:
    """
    Constructs the minimal consolidated set of 8 physical MovementTemplate instances
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

    # 4. Gentle Curve Template: diff = 1 (nominal 45° turns)
    templates.append(
        MovementTemplate(
            template_id="curve_gentle",
            name="Gentle Curve Template",
            category="curve_forward",
            pairs=[(2, 1), (3, 2), (4, 3), (5, 4)],
            nominal_rc=140.0,
            wheelbase=wheelbase,
            drive_unit=drive_unit,
        )
    )

    # 5. Medium Curve Template: diff = 2 (nominal 90° turns)
    templates.append(
        MovementTemplate(
            template_id="curve_medium",
            name="Medium Curve Template",
            category="curve_forward",
            pairs=[(3, 1), (4, 2), (5, 3)],
            nominal_rc=76.4,
            wheelbase=wheelbase,
            drive_unit=drive_unit,
        )
    )

    # 6. Sharp Curve Template: diff >= 3 (nominal 135°-180° tight forward hooks)
    templates.append(
        MovementTemplate(
            template_id="curve_sharp",
            name="Sharp Curve Template",
            category="curve_forward",
            pairs=[(4, 1), (5, 2), (5, 1)],
            nominal_rc=45.0,
            wheelbase=wheelbase,
            drive_unit=drive_unit,
        )
    )

    # 7. Tight Hook Template: Counter-drive with R = -1
    templates.append(
        MovementTemplate(
            template_id="tight_hook",
            name="Tight Hook Template",
            category="curve_tight",
            pairs=[(2, -1), (3, -1), (4, -1), (5, -1)],
            r_out=50.0,
            r_in=15.0,
            wheelbase=wheelbase,
            drive_unit=drive_unit,
        )
    )

    # 8. Tight Counter-Spin Template: Counter-drive with R <= -2
    templates.append(
        MovementTemplate(
            template_id="tight_spin",
            name="Tight Counter-Spin Template",
            category="curve_tight",
            pairs=[(3, -2), (4, -2), (5, -2), (4, -3), (5, -3), (5, -4)],
            r_out=41.0,
            r_in=24.0,
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
    sheet_width_mm: float = 650.0,
    sheet_height_mm: float = 650.0,
) -> str:
    """Arranges the 8 consolidated templates onto a single printable sheet."""
    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {sheet_width_mm} {sheet_height_mm}" '
        f'width="{sheet_width_mm}mm" height="{sheet_height_mm}mm">',
        '  <rect width="100%" height="100%" fill="#ffffff" stroke="#cbd5e1" stroke-width="1" />',
        '  <text x="20" y="22" font-family="sans-serif" font-size="14" font-weight="bold" fill="#0f172a">ROBOT BATTLES - MOVEMENT TEMPLATES (8 CONSOLIDATED TEMPLATES)</text>',
        '  <text x="20" y="32" font-family="sans-serif" font-size="7.5" fill="#475569">Complete range -5 to +5. Flip face-down for left turns. Place at rear for reverse.</text>',
        '  <!-- 50mm Calibration Scale Bar -->',
        '  <line x1="550" y1="20" x2="600" y2="20" stroke="#0f172a" stroke-width="2.5" />',
        '  <text x="575" y="27" font-family="sans-serif" font-size="6" fill="#0f172a" text-anchor="middle">50 mm SCALE BAR</text>',
    ]

    # Clean multi-row grid packing
    x_cursor = 20.0
    y_cursor = 45.0
    max_row_height = 0.0

    for t in templates:
        bw, bh = t.get_dimensions()
        if x_cursor + bw > sheet_width_mm - 15.0:
            x_cursor = 20.0
            y_cursor += max_row_height + 15.0
            max_row_height = 0.0

        svg_parts.append(f'  <!-- Template: {t.name} ({t.template_id}) -->')
        svg_parts.append(f'  <g transform="translate({x_cursor:.1f}, {y_cursor:.1f})">')
        svg_parts.append(t.render_svg_content(offset_x=5.0, offset_y=5.0))
        svg_parts.append('  </g>')

        x_cursor += bw + 15.0
        if bh > max_row_height:
            max_row_height = bh

    svg_parts.append("</svg>")
    return "\n".join(svg_parts)


def generate_rulebook_preview_svg(
    templates: List[MovementTemplate],
    width_px: int = 900,
    height_px: int = 900,
) -> str:
    """Generates the preview illustration for Section 6 of the rulebook."""
    t_map = {t.template_id: t for t in templates}
    t_straight = t_map.get("straight")
    t_curve = t_map.get("curve_medium")
    t_spin = t_map.get("spin")
    t_pivot = t_map.get("pivot")

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width_px} {height_px}" width="{width_px}" height="{height_px}">
  <rect width="100%" height="100%" fill="#ffffff" />

  <!-- Straight Template (Left) -->
  <g transform="translate(60, 50) scale(2.2)">
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
    <text x="560" y="440" font-size="16" font-weight="bold">Curve Template</text>
    <text x="560" y="462" font-size="13" fill="#64748b">Align bumper to marked stop line</text>
    <text x="560" y="482" font-size="13" fill="#64748b">Flip for Left | Back for Reverse</text>

    <!-- Spin notes -->
    <text x="350" y="842" font-size="14" font-weight="bold" text-anchor="middle">Spin on Spot</text>
    <text x="350" y="862" font-size="12" fill="#64748b" text-anchor="middle">Rotate around center (90° / unit)</text>

    <!-- Pivot notes -->
    <text x="730" y="842" font-size="14" font-weight="bold" text-anchor="middle">Pivot Fan</text>
    <text x="730" y="862" font-size="12" fill="#64748b" text-anchor="middle">Pivot on locked wheel (45° / unit)</text>
  </g>
</svg>"""
    return svg


def generate_permutation_markdown(perms: List[Dict[str, Any]]) -> str:
    """Generates a complete markdown reference table of all 121 permutations."""
    md = [
        "# Movement Permutation Catalog (-5 to +5)\n\n",
        "This table details all **121 combinations** of Left and Right drive settings, "
        "the physical template to use across the **8 consolidated templates**, and whether to **flip** "
        "the template (for left turns) or place it at the **rear** (for reverse).\n\n",
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

def export_template_png(svg_str: str, png_path: Path, dpi: int = 300) -> bool:
    """Exports SVG content to high-resolution transparent PNG."""
    try:
        import shutil
        import subprocess
        convert_bin = shutil.which("magick") or shutil.which("convert")
        if convert_bin:
            cmd = [convert_bin, "-background", "none", "-density", str(dpi), "svg:-", str(png_path)]
            subprocess.run(cmd, input=svg_str.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return True
        import cairosvg
        cairosvg.svg2png(bytestring=svg_str.encode("utf-8"), write_to=str(png_path), dpi=dpi)
        return True
    except Exception as e:
        print(f"Warning: Could not export {png_path}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Generate physical movement templates for every permutation from -5 to 5 (8 consolidated templates)."
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

    print(f"Generating consolidated movement templates (Wheelbase: {args.wheelbase}mm, Unit: {args.drive_unit}mm)...")
    templates = build_all_movement_templates(wheelbase=args.wheelbase, drive_unit=args.drive_unit)
    print(f"Created {len(templates)} consolidated movement templates.")

    # Remove any old SVG/PNG files in movement_templates/ that don't belong to the 8 templates
    valid_ids = {t.template_id for t in templates} | {"movement_templates_sheet"}
    for old_f in args.output_dir.glob("*.*"):
        if old_f.stem not in valid_ids and old_f.name != "README.md":
            try:
                old_f.unlink()
            except Exception:
                pass

    # 1. Output individual SVG and transparent PNG templates
    rules_img_dir = Path("rules/images")
    rules_img_dir.mkdir(parents=True, exist_ok=True)
    for t in templates:
        svg_content = t.to_svg(transparent_bg=True)
        file_path = args.output_dir / f"{t.template_id}.svg"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(svg_content)
        png_path = args.output_dir / f"{t.template_id}.png"
        export_template_png(svg_content, png_path)

        # Also copy key templates for rulebook diagrams into rules/images/
        if t.template_id in ("straight", "spin", "pivot", "curve_medium"):
            rulebook_png = rules_img_dir / f"template_{t.template_id}.png"
            export_template_png(svg_content, rulebook_png)
    print(f"Saved {len(templates)} individual SVG and transparent PNG templates to {args.output_dir}/")

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

                ax.text(150, 820, "Straight (1 to 5)", fontsize=13, fontweight="bold", ha="center", color="#0f172a")
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
                ax.text((p1_out[0]+p1_in[0])/2 - 20, (p1_out[1]+p1_in[1])/2 + 25, "L3 R1", fontsize=11, fontweight="bold", color="#1e293b", ha="center")

                th2 = np.radians(180 + 90.0)
                p2_out = (640 + 320 * np.cos(th2), 420 + 320 * np.sin(th2))
                p2_in = (640 + 170 * np.cos(th2), 420 + 170 * np.sin(th2))
                ax.plot([p2_out[0], p2_in[0]], [p2_out[1], p2_in[1]], color="#2563eb", linewidth=2.5)
                ax.text((p2_out[0]+p2_in[0])/2 - 20, (p2_out[1]+p2_in[1])/2 + 25, "L4 R2", fontsize=11, fontweight="bold", color="#1e293b", ha="center")

                ax.text(640, 460, "Curve Template", fontsize=13, fontweight="bold", ha="center", color="#0f172a")
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

                ax.text(cx_s, 785, "Spin on Spot (90° / unit)", fontsize=12, fontweight="bold", ha="center", color="#0f172a")
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

                ax.text(cx_p, 815, "Pivot Fan (45° / unit, 4 = 180°)", fontsize=12, fontweight="bold", ha="center", color="#0f172a")
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
