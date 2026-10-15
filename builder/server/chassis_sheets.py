"""A3 Chassis Sheet Generator (SVG, printable HTML, TikZ/PDF, and PNG)."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from .data import (
    A3_HEIGHT_MM,
    A3_WIDTH_MM,
    CARD_HEIGHT_MM,
    CARD_WIDTH_MM,
    CHASSIS_TEMPLATES,
    WORKSPACE_DIR,
    get_chassis_definitions,
    sanitize_filename,
)

ICONS_DIR = WORKSPACE_DIR / "pictures" / "icons"


def tex_escape(s: Any) -> str:
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
    return s


def generate_chassis_svg(chassis: Dict[str, Any]) -> str:
    """Generates an SVG string for an A3 landscape sheet (420mm x 297mm).

    Uses a clean engineering grid background and card-design-coherent styling
    matching the automata sheets.
    """
    name = chassis.get("name", "Chassis")
    weight = chassis.get("weight", 0)
    cost = chassis.get("cost", 0)
    flip = chassis.get("flip_strength", 0)
    tpl_name = chassis.get("template", "Square")
    keywords = (chassis.get("keywords") or "").strip()
    text = (chassis.get("text") or "").strip()
    pic_url = chassis.get("picture_url") or (f"/{chassis.get('picture')}" if chassis.get("picture") else "")

    geom = CHASSIS_TEMPLATES.get(tpl_name, CHASSIS_TEMPLATES["Square"])
    points = geom.get("points", [])
    pts_str = " ".join(f"{p[0]},{p[1]}" for p in points)
    p0 = points[0] if points else [100.0, 24.0]

    # Keyword badges for SVG
    kw_svg = ""
    if keywords:
        badges = []
        kw_list = [k.strip() for k in keywords.split(";") if k.strip()]
        for idx, kw in enumerate(kw_list):
            kw_x = 4 + (idx * 22)
            badges.append(
                f'<rect x="{kw_x}" y="0" width="20" height="5.5" rx="1.5" fill="#1565c0"/>'
                f'<text x="{kw_x + 10}" y="4" fill="#ffffff" font-family="sans-serif" font-size="2.6" font-weight="bold" text-anchor="middle">{kw}</text>'
            )
        kw_svg = f'<g transform="translate(0, 52)">{"".join(badges)}</g>'

    text_svg = ""
    if text:
        text_svg = f'<text x="4" y="61" fill="#334155" font-family="sans-serif" font-size="2.8">{text}</text>'

    plate_h = 66 if (keywords or text) else 54

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {A3_WIDTH_MM} {A3_HEIGHT_MM}" width="{A3_WIDTH_MM}mm" height="{A3_HEIGHT_MM}mm" class="a3-sheet-svg">
  <defs>
    <pattern id="grid-10" width="10" height="10" patternUnits="userSpaceOnUse">
      <path d="M 10 0 L 0 0 0 10" fill="none" stroke="#f1f5f9" stroke-width="0.3"/>
    </pattern>
    <pattern id="grid-50" width="50" height="50" patternUnits="userSpaceOnUse">
      <rect width="50" height="50" fill="url(#grid-10)"/>
      <path d="M 50 0 L 0 0 0 50" fill="none" stroke="#cbd5e1" stroke-width="0.6"/>
    </pattern>
    <marker id="arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#15803d"/>
    </marker>
  </defs>

  <!-- Sheet Background (Clean Light Engineering Grid) -->
  <rect x="0" y="0" width="{A3_WIDTH_MM}" height="{A3_HEIGHT_MM}" fill="#ffffff" stroke="#cbd5e1" stroke-width="1"/>

  <!-- Grid Layer -->
  <rect x="0" y="0" width="{A3_WIDTH_MM}" height="{A3_HEIGHT_MM}" fill="url(#grid-50)"/>

  <!-- Centerlines -->
  <line x1="{A3_WIDTH_MM/2}" y1="35" x2="{A3_WIDTH_MM/2}" y2="{A3_HEIGHT_MM-25}" stroke="#93c5fd" stroke-width="0.4" stroke-dasharray="4,4" opacity="0.5"/>
  <line x1="30" y1="{A3_HEIGHT_MM/2}" x2="{A3_WIDTH_MM-30}" y2="{A3_HEIGHT_MM/2}" stroke="#93c5fd" stroke-width="0.4" stroke-dasharray="4,4" opacity="0.5"/>

  <!-- Chassis Boundary Shape -->
  <polygon points="{pts_str}" fill="rgba(2, 132, 199, 0.03)" stroke="#0284c7" stroke-width="2.0" stroke-dasharray="6,4" stroke-linejoin="round" class="chassis-boundary-shape"/>
  <text x="{316.0 if tpl_name == 'Square' else (376.0 if tpl_name == 'Triangle' else (404.0 if tpl_name == 'Wide' else p0[0] + 3))}" y="{28.5 if tpl_name == 'Square' else (139.5 if tpl_name == 'Triangle' else (69.5 if tpl_name == 'Wide' else p0[1] + 6))}" fill="#0284c7" font-family="sans-serif" font-size="3.8" font-weight="bold" text-anchor="{'end' if tpl_name in ('Square', 'Triangle', 'Wide') else 'start'}">Chassis Boundary ({tpl_name})</text>

  <!-- Forward / Facing Indicator -->
  <g class="facing-indicator" transform="translate({A3_WIDTH_MM/2}, 20)">
    <line x1="0" y1="8" x2="0" y2="0" stroke="#15803d" stroke-width="1.8" marker-end="url(#arrow)"/>
    <text x="0" y="-2" fill="#15803d" font-family="sans-serif" font-size="5" font-weight="bold" text-anchor="middle" letter-spacing="1">FRONT / HEADING</text>
  </g>

  <!-- Chassis Corner Information Plate (Card-Coherent Styling) -->
  <g class="chassis-corner-plate" transform="translate(12, 12)">
    <rect x="0" y="0" width="88" height="{plate_h}" rx="3" fill="#ffffff" stroke="#cbd5e1" stroke-width="0.8"/>
    <text x="44" y="7.5" fill="#0f172a" font-family="system-ui, -apple-system, sans-serif" font-size="5.2" font-weight="bold" text-anchor="middle">{name}</text>
    <text x="44" y="12.5" fill="#64748b" font-family="system-ui, -apple-system, sans-serif" font-size="3.5" text-anchor="middle">Template: {tpl_name}</text>
    {f'<image href="{pic_url}" x="4" y="15" width="80" height="23" preserveAspectRatio="xMidYMid meet"/>' if pic_url else ''}
    <g transform="translate(4, 39.5)">
      <rect x="0" y="0" width="80" height="11" rx="2" fill="#f8fafc" stroke="#e2e8f0" stroke-width="0.5"/>
      <text x="13" y="4" fill="#64748b" font-family="sans-serif" font-size="2.6" font-weight="bold" text-anchor="middle">WEIGHT</text>
      <text x="13" y="9" fill="#0f172a" font-family="sans-serif" font-size="4.2" font-weight="bold" text-anchor="middle">{weight}</text>
      <line x1="27" y1="1.5" x2="27" y2="9.5" stroke="#e2e8f0" stroke-width="0.5"/>
      <text x="40" y="4" fill="#64748b" font-family="sans-serif" font-size="2.6" font-weight="bold" text-anchor="middle">COST</text>
      <text x="40" y="9" fill="#008014" font-family="sans-serif" font-size="4.2" font-weight="bold" text-anchor="middle">${cost}</text>
      <line x1="53" y1="1.5" x2="53" y2="9.5" stroke="#e2e8f0" stroke-width="0.5"/>
      <text x="66" y="4" fill="#64748b" font-family="sans-serif" font-size="2.6" font-weight="bold" text-anchor="middle">FLIP STR</text>
      <text x="66" y="9" fill="#b91c1c" font-family="sans-serif" font-size="4.2" font-weight="bold" text-anchor="middle">{flip}</text>
    </g>
    {kw_svg}
    {text_svg}
  </g>

  <!-- Rules Note on Sheet -->
  <g class="sheet-rules-note" transform="translate({A3_WIDTH_MM - 150}, 10)">
    <text x="0" y="6" fill="#64748b" font-family="sans-serif" font-size="3.6">A3 Mat (420mm x 297mm) - Cards: 44mm x 64mm (Half-Poker)</text>
    <text x="0" y="11" fill="#64748b" font-family="sans-serif" font-size="3.6">All installed robot cards must sit on the chassis boundary</text>
  </g>

  <!-- Scale Bar (Bottom Right) -->
  <g class="scale-bar" transform="translate({A3_WIDTH_MM - 65}, {A3_HEIGHT_MM - 10})">
    <line x1="0" y1="0" x2="44" y2="0" stroke="#64748b" stroke-width="0.8"/>
    <line x1="0" y1="-2" x2="0" y2="2" stroke="#64748b" stroke-width="0.8"/>
    <line x1="44" y1="-2" x2="44" y2="2" stroke="#64748b" stroke-width="0.8"/>
    <text x="22" y="5" fill="#64748b" font-family="sans-serif" font-size="3.5" text-anchor="middle">Card Width (44mm)</text>
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
      background: #f1f5f9;
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
      box-shadow: 0 10px 30px rgba(0,0,0,0.15);
      background: #ffffff;
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


def generate_chassis_tikz(chassis: Dict[str, Any]) -> str:
    """Generates TikZ code for a standalone A3 landscape chassis sheet page."""
    name = chassis.get("name", "Chassis")
    weight = int(chassis.get("weight", 0) or 0)
    cost = int(chassis.get("cost", 0) or 0)
    flip = chassis.get("flip_strength", 0)
    tpl_name = chassis.get("template", "Square")
    keywords = (chassis.get("keywords") or "").strip()
    text = (chassis.get("text") or "").strip()
    pic_rel = chassis.get("picture", "").strip()

    geom = CHASSIS_TEMPLATES.get(tpl_name, CHASSIS_TEMPLATES["Square"])
    points = geom.get("points", [])
    pts_str = " -- ".join(f"({p[0]:.1f}, {p[1]:.1f})" for p in points)
    p0 = points[0] if points else [100.0, 24.0]

    # Coherent weight icons (0.45cm matches standard text line height)
    if weight > 0:
        weight_icons = r"\;".join([r"\raisebox{-0.15ex}{\weighticon[0.45cm]}"] * weight)
        weight_markup = rf"{weight_icons} \enspace ({weight})"
    else:
        weight_markup = "0"

    # Coherent cost (green dollar signs)
    if cost > 0:
        cost_signs = r"\$" * cost
        cost_markup = rf"\textcolor{{costgreen}}{{\textbf{{{cost_signs}}}}} \enspace (\${cost})"
    else:
        cost_markup = r"\$0"

    # Keywords badges
    kw_badges = []
    if keywords:
        for kw in keywords.split(";"):
            kw = kw.strip()
            if kw:
                kw_badges.append(rf"\keywordbadge{{kw_blue}}{{{tex_escape(kw)}}}")
    kw_markup = r"\enspace ".join(kw_badges)

    lines = []
    lines.append(r"\noindent\begin{tikzpicture}[remember picture, overlay, shift={(current page.north west)}, x=1mm, y=-1mm]")
    lines.append(r"  \path (0,0) rectangle (420, 297);")

    # 1. Background Grid (10mm minor, 50mm major)
    lines.append(r"  % Background Engineering Grid")
    lines.append(r"  \draw[black!5, step=10] (0,0) grid (420, 297);")
    lines.append(r"  \draw[black!12, step=50] (0,0) grid (420, 297);")

    # 2. Centerlines
    lines.append(r"  % Centerlines")
    lines.append(r"  \draw[cyan!40!black, line width=0.4pt, dash pattern=on 4mm off 4mm, opacity=0.3] (210, 30) -- (210, 280);")
    lines.append(r"  \draw[cyan!40!black, line width=0.4pt, dash pattern=on 4mm off 4mm, opacity=0.3] (20, 148.5) -- (400, 148.5);")

    # 3. Chassis Boundary Outline
    lines.append(r"  % Chassis Boundary Outline")
    lines.append(rf"  \draw[cyan!60!blue, line width=1.4pt, line join=round, dashed] {pts_str} -- cycle;")
    if tpl_name == "Square":
        label_pos = "at (316.0, 26.0) "
        label_anchor = "anchor=north east"
    elif tpl_name == "Triangle":
        label_pos = "at (376.0, 137.0) "
        label_anchor = "anchor=north east"
    elif tpl_name == "Wide":
        label_pos = "at (404.0, 67.0) "
        label_anchor = "anchor=north east"
    else:
        label_pos = f"at ({p0[0] + 2:.1f}, {p0[1] + 2:.1f}) "
        label_anchor = "anchor=north west"

    lines.append(
        rf"  \node[{label_anchor}, font=\sffamily\scriptsize\bfseries, text=cyan!60!blue] "
        rf"{label_pos}{{Chassis Boundary ({tex_escape(tpl_name)})}};"
    )

    # 4. Forward Heading Indicator
    lines.append(r"  % Forward Heading Indicator")
    lines.append(r"  \draw[line width=1.6pt, -{Triangle[length=2.8mm]}, green!60!black] (210, 24) -- (210, 14);")
    lines.append(r"  \node[anchor=south, font=\sffamily\bfseries\footnotesize, text=green!60!black] at (210, 13) {FRONT / HEADING};")

    # 5. Chassis Info Plate (Top-Left)
    lines.append(r"  % Chassis Information Plate")
    lines.append(r"  \node[anchor=north west, fill=white, draw=black!30, rounded corners=2.5mm, inner sep=3.0mm, line width=0.8pt] at (12, 10) {")
    lines.append(r"    \begin{minipage}{82mm}")
    lines.append(rf"      {{\LARGE\bfseries\sffamily {tex_escape(name)}}} \par\vspace{{1.2mm}}")
    lines.append(rf"      {{\small\sffamily\textbf{{Template:}} {tex_escape(tpl_name)}}} \par\vspace{{2.0mm}}")
    lines.append(r"      {\sffamily\small")
    lines.append(rf"        \textbf{{WEIGHT:}}\enspace {weight_markup} \hfill \textbf{{COST:}}\enspace {cost_markup} \par\vspace{{1.2mm}}")
    lines.append(rf"        \textbf{{FLIP STRENGTH:}}\enspace \textcolor{{durabilityred}}{{\textbf{{{flip}}}}}")
    lines.append(r"      } \par\vspace{1.5mm}")

    if kw_markup:
        lines.append(rf"      {kw_markup} \par\vspace{{1.5mm}}")
    if text:
        lines.append(rf"      {{\sffamily\small {tex_escape(text)}}} \par\vspace{{1.5mm}}")

    if pic_rel and (WORKSPACE_DIR / pic_rel).is_file():
        lines.append(r"      \vspace{0.5mm}")
        lines.append(rf"      {{\centering\includegraphics[width=72mm, max height=22mm, keepaspectratio]{{{pic_rel}}}\par}}")

    lines.append(r"    \end{minipage}")
    lines.append(r"  };")

    # 6. Rules Note & Scale Bar (Bottom-Right)
    lines.append(r"  % Rules Note & Scale Bar")
    lines.append(r"  \node[anchor=south east, font=\sffamily\footnotesize, text=black!60] at (408, 290) {")
    lines.append(r"    \begin{tabular}{r}")
    lines.append(r"      A3 Mat (420mm $\times$ 297mm) --- Cards: 44mm $\times$ 64mm (Half-Poker) \\")
    lines.append(r"      All installed robot cards must sit on or within the chassis boundary")
    lines.append(r"    \end{tabular}")
    lines.append(r"  };")

    lines.append(r"\end{tikzpicture}")
    return "\n".join(lines)


def generate_chassis_latex_document(pages_tikz: List[str]) -> str:
    """Wraps TikZ chassis pages in a complete standalone LaTeX document."""
    preamble = r"""\documentclass{article}
\usepackage[a3paper,landscape,margin=0mm]{geometry}
\usepackage{tikz}
\usepackage{graphicx}
\usepackage{xcolor}
\usepackage[export]{adjustbox}
\usetikzlibrary{arrows.meta,calc}
\graphicspath{{""" + str(WORKSPACE_DIR) + r"""/}{./}}
\pagestyle{empty}

\definecolor{chevronpurple}{RGB}{40, 0, 70}
\definecolor{costgreen}{RGB}{0, 128, 20}
\definecolor{durabilityred}{RGB}{185, 0, 0}
\definecolor{textdark}{RGB}{20, 20, 20}
\definecolor{kw_blue}{RGB}{21, 101, 192}

\newcommand{\weighticon}[1][0.62cm]{\includegraphics[height=#1,keepaspectratio]{pictures/icons/weight.png}}
\newcommand{\keywordbadge}[2]{%
  \tikz[baseline=-0.6ex]\node[fill=#1, rounded corners=2.5pt, inner xsep=4.5pt, inner ysep=0pt, minimum height=0.48cm, text height=0.24cm, text depth=0.08cm, text=white]{\sffamily\bfseries\footnotesize #2};%
}

\begin{document}
"""
    body = "\n\\null\\newpage\n".join(pages_tikz)
    postamble = "\n\\null\n\\end{document}\n"
    return preamble + body + postamble


def compile_latex_to_pdf(doc_tex: str, output_pdf_path: Path) -> Path:
    """Compiles LaTeX string via pdflatex (2 passes) to an output PDF file."""
    output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        tex_file = tmp_path / "document.tex"
        tex_file.write_text(doc_tex, encoding="utf-8")

        cmd = [
            "pdflatex",
            "-interaction=nonstopmode",
            "-halt-on-error",
            f"-output-directory={tmp_path}",
            str(tex_file),
        ]
        # Pass 1
        res1 = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=WORKSPACE_DIR, text=True)
        if res1.returncode != 0:
            print("LaTeX compilation pass 1 failed:")
            print(res1.stdout[-1500:])
            raise RuntimeError(f"pdflatex pass 1 failed for {output_pdf_path.name}")

        # Pass 2 to resolve TikZ remember picture overlay coordinates
        res2 = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=WORKSPACE_DIR, text=True)
        compiled_pdf = tmp_path / "document.pdf"
        if res2.returncode != 0 or not compiled_pdf.is_file():
            print("LaTeX compilation pass 2 failed:")
            print(res2.stdout[-1500:])
            raise RuntimeError(f"pdflatex pass 2 failed for {output_pdf_path.name}")

        shutil.copyfile(compiled_pdf, output_pdf_path)
    return output_pdf_path


def render_pdf_to_png(pdf_path: Path, output_png_path: Path, dpi: int = 150) -> Path:
    """Renders single-page PDF to PNG using pdftoppm."""
    output_png_path.parent.mkdir(parents=True, exist_ok=True)
    out_stem = output_png_path.with_suffix("")
    cmd = [
        "pdftoppm",
        "-png",
        "-r",
        str(dpi),
        "-singlefile",
        str(pdf_path),
        str(out_stem),
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=WORKSPACE_DIR, text=True)
    if res.returncode != 0 or not output_png_path.is_file():
        raise RuntimeError(f"pdftoppm failed to render {pdf_path.name} to {output_png_path.name}: {res.stderr}")
    return output_png_path


def export_all_chassis_sheets(output_dir: Path, tts_dir: Optional[Path] = None) -> List[Path]:
    """Generates SVGs, HTMLs, PDFs, and PNG images for all chassis in chassis.csv."""
    output_dir.mkdir(parents=True, exist_ok=True)
    chassis_list = get_chassis_definitions()
    generated = []

    for ch in chassis_list:
        name = ch["name"]
        slug = ch["name"].lower().replace(" ", "_").replace(".", "")
        safe_name = sanitize_filename(name)

        svg_file = output_dir / f"{slug}_sheet.svg"
        html_file = output_dir / f"{slug}_sheet.html"
        pdf_file = output_dir / f"{slug}_sheet.pdf"

        # 1. SVG
        with open(svg_file, "w", encoding="utf-8") as f:
            f.write(generate_chassis_svg(ch))
        # 2. HTML
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(generate_printable_html(ch))

        generated.extend([svg_file, html_file])

        # 3. TikZ -> PDF
        tikz_page = generate_chassis_tikz(ch)
        doc_tex = generate_chassis_latex_document([tikz_page])
        compile_latex_to_pdf(doc_tex, pdf_file)
        generated.append(pdf_file)

        # 4. Render to PNG in tts_dir if provided
        if tts_dir:
            tts_dir.mkdir(parents=True, exist_ok=True)
            tts_png = tts_dir / f"{safe_name}_sheet.png"
            render_pdf_to_png(pdf_file, tts_png, dpi=150)
            generated.append(tts_png)

    return generated

