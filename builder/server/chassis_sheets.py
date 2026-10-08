"""A3 Chassis Sheet Generator (SVG and printable HTML)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .data import (
    A3_HEIGHT_MM,
    A3_WIDTH_MM,
    CARD_HEIGHT_MM,
    CARD_WIDTH_MM,
    CHASSIS_TEMPLATES,
    get_chassis_definitions,
)


def generate_chassis_svg(chassis: Dict[str, Any]) -> str:
    """Generates an SVG string for an A3 landscape sheet (420mm x 297mm)."""
    name = chassis.get("name", "Chassis")
    weight = chassis.get("weight", 0)
    cost = chassis.get("cost", 0)
    flip = chassis.get("flip_strength", 0)
    tpl_name = chassis.get("template", "Square")
    pic_url = chassis.get("picture_url") or (f"/{chassis.get('picture')}" if chassis.get("picture") else "")

    geom = CHASSIS_TEMPLATES.get(tpl_name, CHASSIS_TEMPLATES["Square"])
    points = geom.get("points", [])
    pts_str = " ".join(f"{p[0]},{p[1]}" for p in points)

    # Grid pattern: 10mm minor, 50mm major
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {A3_WIDTH_MM} {A3_HEIGHT_MM}" width="{A3_WIDTH_MM}mm" height="{A3_HEIGHT_MM}mm" class="a3-sheet-svg">
  <defs>
    <pattern id="grid-10" width="10" height="10" patternUnits="userSpaceOnUse">
      <path d="M 10 0 L 0 0 0 10" fill="none" stroke="#2a3342" stroke-width="0.3" opacity="0.6"/>
    </pattern>
    <pattern id="grid-50" width="50" height="50" patternUnits="userSpaceOnUse">
      <rect width="50" height="50" fill="url(#grid-10)"/>
      <path d="M 50 0 L 0 0 0 50" fill="none" stroke="#3b485d" stroke-width="0.7" opacity="0.8"/>
    </pattern>
    <marker id="arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#00d26a"/>
    </marker>
  </defs>

  <!-- Sheet Background -->
  <rect x="0" y="0" width="{A3_WIDTH_MM}" height="{A3_HEIGHT_MM}" fill="#0f141c" stroke="#1f2937" stroke-width="1"/>

  <!-- Grid Layer -->
  <rect x="0" y="0" width="{A3_WIDTH_MM}" height="{A3_HEIGHT_MM}" fill="url(#grid-50)"/>

  <!-- Centerlines -->
  <line x1="{A3_WIDTH_MM/2}" y1="35" x2="{A3_WIDTH_MM/2}" y2="{A3_HEIGHT_MM-25}" stroke="#00e5ff" stroke-width="0.4" stroke-dasharray="4,4" opacity="0.4"/>
  <line x1="30" y1="{A3_HEIGHT_MM/2}" x2="{A3_WIDTH_MM-30}" y2="{A3_HEIGHT_MM/2}" stroke="#00e5ff" stroke-width="0.4" stroke-dasharray="4,4" opacity="0.4"/>

  <!-- Chassis Boundary Shape -->
  <polygon points="{pts_str}" fill="rgba(0, 229, 255, 0.04)" stroke="#00e5ff" stroke-width="2.5" stroke-linejoin="round" class="chassis-boundary-shape"/>

  <!-- Forward / Facing Indicator -->
  <g class="facing-indicator" transform="translate({A3_WIDTH_MM/2}, 20)">
    <line x1="0" y1="8" x2="0" y2="0" stroke="#00d26a" stroke-width="1.8" marker-end="url(#arrow)"/>
    <text x="0" y="-2" fill="#00d26a" font-family="sans-serif" font-size="5" font-weight="bold" text-anchor="middle" letter-spacing="1">FRONT / HEADING</text>
  </g>

  <!-- Chassis Corner Information Plate with Picture & Printed Stats on Mat -->
  <g class="chassis-corner-plate" transform="translate(12, 6)">
    <rect x="0" y="0" width="82" height="52" rx="4" fill="#131c2a" stroke="#253549" stroke-width="0.8"/>
    <text x="41" y="8" fill="#ffffff" font-family="sans-serif" font-size="5.2" font-weight="bold" text-anchor="middle">{name}</text>
    <text x="41" y="13" fill="#38bdf8" font-family="sans-serif" font-size="3.5" text-anchor="middle">Template: {tpl_name}</text>
    {f'<image href="{pic_url}" x="4" y="15" width="74" height="23" preserveAspectRatio="xMidYMid meet"/>' if pic_url else ''}
    <g transform="translate(4, 39)">
      <rect x="0" y="0" width="74" height="10.5" rx="2" fill="#0c121c" stroke="#1e293b" stroke-width="0.5"/>
      <text x="12" y="4" fill="#94a3b8" font-family="sans-serif" font-size="2.6" text-anchor="middle">WEIGHT</text>
      <text x="12" y="8.8" fill="#f59e0b" font-family="sans-serif" font-size="4" font-weight="bold" text-anchor="middle">{weight}</text>
      <line x1="25" y1="1.5" x2="25" y2="9" stroke="#1e293b" stroke-width="0.5"/>
      <text x="37" y="4" fill="#94a3b8" font-family="sans-serif" font-size="2.6" text-anchor="middle">COST</text>
      <text x="37" y="8.8" fill="#10b981" font-family="sans-serif" font-size="4" font-weight="bold" text-anchor="middle">${cost}</text>
      <line x1="49" y1="1.5" x2="49" y2="9" stroke="#1e293b" stroke-width="0.5"/>
      <text x="61" y="4" fill="#94a3b8" font-family="sans-serif" font-size="2.6" text-anchor="middle">FLIP STR</text>
      <text x="61" y="8.8" fill="#f43f5e" font-family="sans-serif" font-size="4" font-weight="bold" text-anchor="middle">{flip}</text>
    </g>
  </g>

  <!-- Rules Note on Sheet -->
  <g class="sheet-rules-note" transform="translate({A3_WIDTH_MM - 145}, 7)">
    <text x="0" y="6" fill="#64748b" font-family="sans-serif" font-size="3.8">A3 Mat (420mm x 297mm) - Cards: 44mm x 64mm (Half-Poker)</text>
    <text x="0" y="12" fill="#64748b" font-family="sans-serif" font-size="3.8">All installed robot cards must sit on the chassis boundary</text>
  </g>

  <!-- Scale Bar (Bottom Right) -->
  <g class="scale-bar" transform="translate({A3_WIDTH_MM - 65}, {A3_HEIGHT_MM - 7})">
    <line x1="0" y1="0" x2="44" y2="0" stroke="#ffffff" stroke-width="0.8"/>
    <line x1="0" y1="-2" x2="0" y2="2" stroke="#ffffff" stroke-width="0.8"/>
    <line x1="44" y1="-2" x2="44" y2="2" stroke="#ffffff" stroke-width="0.8"/>
    <text x="22" y="5" fill="#94a3b8" font-family="sans-serif" font-size="3.5" text-anchor="middle">Card Width (44mm)</text>
  </g>
</svg>
"""
    return svg


def generate_printable_html(chassis: Dict[str, Any]) -> str:
    """Generates a standalone printable HTML page for an A3 sheet."""
    svg_content = generate_chassis_svg(chassis)
    name = chassis.get("name", "Chassis")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{name} - A3 Chassis Mat</title>
  <style>
    @page {{
      size: A3 landscape;
      margin: 0;
    }}
    body {{
      margin: 0;
      padding: 0;
      background: #0f141c;
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
      font-family: system-ui, -apple-system, sans-serif;
    }}
    .sheet-wrapper {{
      width: 420mm;
      height: 297mm;
      box-sizing: border-box;
      box-shadow: 0 10px 30px rgba(0,0,0,0.5);
    }}
    svg {{
      width: 100%;
      height: 100%;
      display: block;
    }}
    @media print {{
      body {{
        background: none;
      }}
      .sheet-wrapper {{
        box-shadow: none;
      }}
    }}
  </style>
</head>
<body>
  <div class="sheet-wrapper">
    {svg_content}
  </div>
</body>
</html>
"""
    return html


def export_all_chassis_sheets(output_dir: Path) -> List[Path]:
    """Generates SVGs and printable HTMLs for all chassis in chassis.csv."""
    output_dir.mkdir(parents=True, exist_ok=True)
    chassis_list = get_chassis_definitions()
    generated = []

    for ch in chassis_list:
        slug = ch["name"].lower().replace(" ", "_").replace(".", "")
        svg_file = output_dir / f"{slug}_sheet.svg"
        html_file = output_dir / f"{slug}_sheet.html"

        with open(svg_file, "w", encoding="utf-8") as f:
            f.write(generate_chassis_svg(ch))
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(generate_printable_html(ch))

        generated.extend([svg_file, html_file])

    return generated
