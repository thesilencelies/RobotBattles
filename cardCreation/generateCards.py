#!/usr/bin/env python3
"""
generateCards.py

Reads card definition CSVs from cardDefinitions/ and generates TikZ LaTeX files
for each card in build/card/<Name>.tex, along with build/card_macros.tex and
build/all_cards.csv.

Follows the layout demonstrated in pictures/exampleCards/ (ExampleESC, ExampleWeapon).
"""

import argparse
import csv
import os
import re
import sys
from pathlib import Path

# Paths
WORKSPACE = Path(__file__).resolve().parent.parent
CARD_DEFS_DIR = WORKSPACE / "cardDefinitions"
PICTURES_DIR = WORKSPACE / "pictures"
ICONS_DIR = PICTURES_DIR / "icons"
COMPONENTS_DIR = WORKSPACE / "components"
BUILD_DIR = Path(__file__).resolve().parent / "build"
CARD_OUTPUT_DIR = BUILD_DIR / "card"

import colorsys
import hashlib

# Geometry constants (in cm)
CARD_OUTER_W_CM = 6.9
CARD_OUTER_H_CM = 9.4
CARD_SAFE_W_CM = 6.4
CARD_SAFE_H_CM = 8.9
BLEED_OFFSET_X = (CARD_OUTER_W_CM - CARD_SAFE_W_CM) / 2.0  # 0.25 cm
BLEED_OFFSET_Y = (CARD_OUTER_H_CM - CARD_SAFE_H_CM) / 2.0  # 0.25 cm

KEYWORD_PALETTE = {
    "fragile": (208, 48, 48),       # Crimson Red
    "forks": (46, 125, 50),         # Forest Green
    "spin up": (230, 81, 0),        # Amber Orange
    "invertible": (21, 101, 192),   # Cobalt Blue
    "armor": (84, 110, 122),        # Slate Gray
    "lifter": (123, 31, 162),       # Deep Purple
    "clamp": (0, 131, 143),         # Teal / Cyan
    "hammer": (78, 52, 46),         # Deep Brown
    "melty": (180, 30, 120),        # Magenta
    "flame": (220, 50, 20),         # Flame Red
}

TEMPLATE_ICONS = {
    "circle": "pictures/icons/template_circle.png",
    "line": "pictures/icons/template_line.png",
    "bar": "pictures/icons/template_bar.png",
    "prongs": "pictures/icons/template_prongs.png",
}


def sanitize_filename(name: str) -> str:
    s = name.strip().replace(" ", "_")
    return re.sub(r"[^A-Za-z0-9_.-]", "", s)


def escape_latex(text: str) -> str:
    """Escapes special LaTeX characters while preserving intentional linebreaks."""
    if not text:
        return ""
    text = text.strip().strip('"').strip("'")

    lines = text.split(r"\\")
    escaped_lines = []
    for line in lines:
        sublines = line.split("\n")
        escaped_sublines = []
        for s in sublines:
            s = s.replace("\\", "")
            s = s.replace("&", r"\&")
            s = s.replace("%", r"\%")
            s = s.replace("$", r"\$")
            s = s.replace("#", r"\#")
            s = s.replace("_", r"\_")
            s = s.replace("~", r"\textasciitilde{}")
            s = s.replace("^", r"\textasciicircum{}")
            escaped_sublines.append(s.strip())
        escaped_lines.append(r" \par ".join(escaped_sublines))
    return r" \\ ".join(escaped_lines)


def get_keyword_color(keyword: str) -> tuple[str, tuple[int, int, int]]:
    """
    Returns (color_name, (r, g, b)) for a keyword.
    The base keyword (ignoring parentheses/numbers) determines the unique color.
    """
    base_kw = re.sub(r"\(.*?\)", "", keyword).strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", base_kw).strip("_")
    if not slug:
        slug = "default"
    color_name = f"kw_{slug}"

    if base_kw in KEYWORD_PALETTE:
        rgb = KEYWORD_PALETTE[base_kw]
    else:
        # Deterministic rich, readable color from keyword hash
        h_val = int(hashlib.md5(base_kw.encode("utf-8")).hexdigest()[:8], 16)
        hue = (h_val % 360) / 360.0
        r_f, g_f, b_f = colorsys.hls_to_rgb(hue, 0.35, 0.70)
        rgb = (int(r_f * 255), int(g_f * 255), int(b_f * 255))

    return color_name, rgb


def format_keywords(keywords_str: str) -> tuple[str, list[tuple[str, tuple[int, int, int]]]]:
    """
    Parses a semicolon-separated keywords string into colored badges.
    Returns (latex_badge_string, list_of_color_defs).
    """
    if not keywords_str:
        return "", []

    raw_list = [k.strip() for k in keywords_str.split(";") if k.strip()]
    if not raw_list:
        return "", []

    badges = []
    color_defs = []
    for kw in raw_list:
        color_name, rgb = get_keyword_color(kw)
        color_defs.append((color_name, rgb))
        esc_kw = escape_latex(kw)
        badges.append(rf"\keywordbadge{{{color_name}}}{{{esc_kw}}}")

    return r"\enspace ".join(badges), color_defs


def find_component_image(picture_field: str = "") -> str:
    """Finds image file path from the CSV picture field."""
    if picture_field and picture_field.strip():
        pf = picture_field.strip()
        if (WORKSPACE / pf).is_file():
            return pf
        for candidate in [COMPONENTS_DIR / pf, PICTURES_DIR / pf]:
            if candidate.is_file():
                return str(candidate.relative_to(WORKSPACE))
    return ""


def format_resource_item(prefix: str, char: str) -> str:
    """Formats a single resource item, repeated icons, or fixed + multiplier symbols."""
    if prefix and all(c == char for c in prefix):
        count = len(prefix) + 1
        icons = [f"\\resource{char}" for _ in range(count)]
        if count <= 2:
            return r"\hspace{1.5pt}".join(icons)
        else:
            # Spill into two rows if there are too many (>= 3)
            # e.g. 3 -> 2 top, 1 bottom; 4 -> 2 top, 2 bottom; 5 -> 3 top, 2 bottom
            top_count = (count + 1) // 2
            row1 = r"\hspace{1.5pt}".join(icons[:top_count])
            row2 = r"\hspace{1.5pt}".join(icons[top_count:])
            return rf"\parbox{{2.5cm}}{{\centering {row1}\par\vspace{{1.5pt}}{row2}}}"
    elif prefix:
        # Check if prefix contains an algebraic multiplier with fixed symbols (e.g. "2XW", "XWW", "XW")
        # In notations like "2XWW", regex captures prefix="2XW", char="W".
        # Fixed symbols should be visualized first, followed by multiplier symbols.
        mult_match = re.match(r"^(\d*(?:XxX|XX|X|\d+x\d+))([ECSMWPD]*)$", prefix, re.IGNORECASE)
        if mult_match:
            mult_expr, extra_icons = mult_match.groups()
            if mult_expr.upper() == "XX":
                mult_expr = "XxX"
            esc_mult = escape_latex(mult_expr)
            mult_element = rf"$\vcenter{{\hbox{{\sffamily\bfseries\LARGE {esc_mult}}}}}\;\vcenter{{\hbox{{\resource{char}}}}}$"

            fixed_count = len(extra_icons) if all(c == char for c in extra_icons) else 0
            if fixed_count == 0:
                return mult_element
            elif fixed_count == 1:
                return rf"$\vcenter{{\hbox{{\resource{char}}}}}\;\vcenter{{\hbox{{\sffamily\bfseries\LARGE {esc_mult}}}}}\;\vcenter{{\hbox{{\resource{char}}}}}$"
            else:
                fixed_icons = [rf"\resource{char}" for _ in range(fixed_count)]
                row1 = r"\hspace{1.5pt}".join(fixed_icons)
                row2 = mult_element
                return rf"\parbox{{2.5cm}}{{\centering {row1}\par\vspace{{1.5pt}}{row2}}}"

        # Standard number or algebraic expression followed by letter -> vertical center aligned
        esc_prefix = escape_latex(prefix)
        if esc_prefix.upper() == "XX":
            esc_prefix = "XxX"
        return rf"$\vcenter{{\hbox{{\sffamily\bfseries\LARGE {esc_prefix}}}}}\;\vcenter{{\hbox{{\resource{char}}}}}$"
    else:
        return rf"\resource{char}"


def parse_resources(res_str: str) -> str:
    """
    Parses a resource string into TikZ/LaTeX markup.
    Rules from terminology.md:
      - Repeated letter (e.g. EE, CC, SSS) -> multiple icons drawn.
        Repeat symbols are placed closer together, spilling into two rows if count >= 3.
      - Number or algebraic expression followed by letter (e.g. 4XW, 2XW, XE, 6W)
        -> prefix rendered in sans-serif text vertically center-aligned with the icon.
      - Fixed symbols followed by multiplier symbols (e.g. 2XWW -> 1 fixed W + 2X W, XWWW -> 2 fixed W + X W).
      - Multiplier XX is rendered as XxX (X times X).
    """
    if not res_str:
        return ""

    res_str = res_str.strip().strip('"')
    if not res_str:
        return ""

    # Check for single token like "EE", "CC", "SSS", "4XW", "XE", "E", "PP", "DD", "2XWW", "XWWW"
    match_expr = re.match(r"^([0-9]*[A-Za-z]*)([ECSMWPD])$", res_str)
    if match_expr:
        prefix, char = match_expr.groups()
        return format_resource_item(prefix, char)

    # Multi-token strings
    tokens = re.findall(r"([0-9]*[A-Za-z]*[ECSMWPD]|[A-Za-z0-9+]+)", res_str)
    out_elements = []
    for tok in tokens:
        submatch = re.match(r"^([0-9]*[A-Za-z]*)([ECSMWPD])$", tok)
        if submatch:
            prefix, char = submatch.groups()
            out_elements.append(format_resource_item(prefix, char))
        else:
            esc_tok = escape_latex(tok)
            out_elements.append(rf"{{\sffamily\bfseries {esc_tok}}}")

    return r"\hspace{2pt}".join(out_elements)


def create_macros(extra_colors: dict = None):
    """Generates build/card_macros.tex defining colors, fonts, icon macros, and keyword badge macro."""
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    macros_file = BUILD_DIR / "card_macros.tex"

    color_lines = []
    for kw, (r, g, b) in KEYWORD_PALETTE.items():
        slug = re.sub(r"[^a-z0-9]+", "_", kw).strip("_")
        color_lines.append(f"\\definecolor{{kw_{slug}}}{{RGB}}{{{r}, {g}, {b}}}")
    if extra_colors:
        for cname, (r, g, b) in extra_colors.items():
            color_lines.append(f"\\definecolor{{{cname}}}{{RGB}}{{{r}, {g}, {b}}}")
    colors_block = "\n".join(color_lines)

    with open(macros_file, "w", encoding="utf-8") as f:
        f.write(r"""% Combat Robotics Card Macros
\RequirePackage{xcolor}
\RequirePackage{graphicx}
\RequirePackage[export]{adjustbox}
\RequirePackage{tikz}
\RequirePackage[none]{hyphenat}

% Color definitions
\definecolor{chevronpurple}{RGB}{40, 0, 70}
\definecolor{costgreen}{RGB}{0, 128, 20}
\definecolor{durabilityred}{RGB}{185, 0, 0}
\definecolor{textdark}{RGB}{20, 20, 20}

% Keyword colors
""" + colors_block + r"""

% Keyword badge macro: text in front of colored box (fixed height for all keywords)
\newcommand{\keywordbadge}[2]{%
  \tikz[baseline=-0.6ex]\node[fill=#1, rounded corners=2.5pt, inner xsep=4.5pt, inner ysep=0pt, minimum height=0.52cm, text height=0.26cm, text depth=0.08cm, text=white]{\sffamily\bfseries\footnotesize #2};%
}

% Global graphicspath so images resolve from build/, cardCreation/, or root
\graphicspath{{../../}{../}{./}{../../pictures/icons/}{../pictures/icons/}{pictures/icons/}}

% Resource icon commands
\newcommand{\resourceE}{\includegraphics[height=0.76cm,keepaspectratio]{pictures/icons/energy.png}}
\newcommand{\resourceC}{\includegraphics[height=0.76cm,keepaspectratio]{pictures/icons/control.png}}
\newcommand{\resourceS}{\includegraphics[height=0.76cm,keepaspectratio]{pictures/icons/spin.png}}
\newcommand{\resourceP}{\includegraphics[height=0.76cm,keepaspectratio]{pictures/icons/pressure.png}}
\newcommand{\resourceM}{\includegraphics[height=0.76cm,keepaspectratio]{pictures/icons/drive.png}}
\newcommand{\resourceD}{\includegraphics[height=0.76cm,keepaspectratio]{pictures/icons/drive.png}}
\newcommand{\resourceW}{\includegraphics[height=0.76cm,keepaspectratio]{pictures/icons/damage.png}}

% Card stat icon commands
\newcommand{\durabilityicon}{\includegraphics[height=0.85cm,keepaspectratio]{pictures/icons/durability.png}}
\newcommand{\absorptionicon}{\includegraphics[height=0.85cm,keepaspectratio]{pictures/icons/absorption.png}}
\newcommand{\weighticon}{\includegraphics[height=0.92cm,keepaspectratio]{pictures/icons/weight.png}}
""")
    print(f"Wrote {macros_file}")


def generate_card_tex(card: dict) -> str:
    """Generates the full TikZ code for a single card."""
    name = (card.get("Name") or "Unnamed Card").strip()
    try:
        weight = int(card.get("Weight", 0) or 0)
    except ValueError:
        weight = 0

    try:
        cost = int(card.get("Cost", 0) or 0)
    except ValueError:
        cost = 0

    durability = str(card.get("Durability") or "").strip()
    absorption = str(card.get("Absorption") or "").strip()
    template = (card.get("Template") or "").strip().lower()
    keywords = (card.get("Keywords") or "").strip()
    rules_text = (card.get("Text") or "").strip()

    req_markup = parse_resources(card.get("Requirements") or "")
    out_markup = parse_resources(card.get("Outputs") or "")

    img_rel_path = find_component_image(card.get("Picture") or "")

    kw_markup, color_defs = format_keywords(keywords)

    lines = [
        r"\begin{tikzpicture}[x=1cm, y=1cm]",
        rf"  \node (cardbleed) [rectangle, minimum width={CARD_OUTER_W_CM}cm, minimum height={CARD_OUTER_H_CM}cm, fill=white] at ({CARD_OUTER_W_CM/2:.2f}, {CARD_OUTER_H_CM/2:.2f}) {{}};",
        rf"  \useasboundingbox (0,0) rectangle ({CARD_OUTER_W_CM:.2f}, {CARD_OUTER_H_CM:.2f});",
        rf"  \clip (0,0) rectangle ({CARD_OUTER_W_CM:.2f}, {CARD_OUTER_H_CM:.2f});",
    ]

    # Provide colors if compiling standalone
    for cname, (r, g, b) in color_defs:
        lines.append(rf"  \providecolor{{{cname}}}{{RGB}}{{{r}, {g}, {b}}}")

    lines.append(rf"  \begin{{scope}}[shift={{({BLEED_OFFSET_X:.3f}, {BLEED_OFFSET_Y:.3f})}}]")

    # --- TOP ROW: Weights, Title, Cost, Template ---
    # Stacked Weight Icons (top-left)
    if weight > 0:
        for w_idx in range(min(weight, 3)):
            wy = 8.15 - (w_idx * 0.95)
            lines.append(rf"    \node [anchor=center] at (0.65, {wy:.2f}) {{\weighticon}};")

    # Card Title (top-center)
    esc_name = escape_latex(name)
    lines.append(
        rf"    \node [anchor=center, text width=3.8cm, align=center] at (3.20, 8.20) {{\fontsize{{15pt}}{{17pt}}\sffamily\bfseries {esc_name}}};"
    )

    # Cost (top-right, green dollar signs)
    if cost > 0:
        if cost < 4:
            cost_str = r"\$" * cost
            lines.append(
                rf"    \node [anchor=center] at (5.70, 8.20) {{\textcolor{{costgreen}}{{\sffamily\textbf{{\Huge {cost_str}}}}}}};"
            )
        else:
            top_count = (cost + 1) // 2
            bot_count = cost - top_count
            row1 = r"\$" * top_count
            row2 = r"\$" * bot_count
            lines.append(
                rf"    \node [anchor=center] at (5.70, 8.20) {{\textcolor{{costgreen}}{{\sffamily\bfseries\Large\begin{{tabular}}{{@{{}}c@{{}}}}{row1}\\[-5pt]{row2}\end{{tabular}}}}}};"
            )

    # Template Icon (below cost, if weapon card)
    if template and template in TEMPLATE_ICONS:
        tmpl_icon = TEMPLATE_ICONS[template]
        lines.append(
            rf"    \node [anchor=center] at (5.40, 6.70) {{\includegraphics[height=1.05cm, keepaspectratio]{{{tmpl_icon}}}}};"
        )

    # --- COMPONENT ARTWORK (Center-Upper) ---
    art_cx = 3.20
    art_cy = 6.65
    if img_rel_path:
        lines.append(
            rf"    \node [anchor=center] at ({art_cx:.2f}, {art_cy:.2f}) {{\includegraphics[width=3.6cm, max height=2.1cm, keepaspectratio]{{{img_rel_path}}}}};"
        )
    else:
        lines.append(
            rf"    \node [rectangle, draw=gray!40, rounded corners=0.15cm, dashed, minimum width=3.4cm, minimum height=2.0cm, fill=gray!5] at ({art_cx:.2f}, {art_cy:.2f}) {{\small\color{{gray}}\textsf{{[ {esc_name} ]}}}};"
        )

    # --- MIDDLE BAND: Left/Right Pointy Chevrons & Resource Flow ---
    lines.append(
        r"    \fill [chevronpurple] (0.00, 5.50) -- (0.85, 4.60) -- (0.00, 3.70) -- cycle;"
    )
    lines.append(
        r"    \fill [chevronpurple] (5.55, 5.50) -- (6.40, 4.60) -- (5.55, 3.70) -- cycle;"
    )

    if req_markup:
        lines.append(
            rf"    \node [anchor=center, text width=2.6cm, align=center] at (1.95, 4.60) {{{req_markup}}};"
        )

    if out_markup:
        lines.append(
            rf"    \node [anchor=center, text width=2.6cm, align=center] at (4.50, 4.60) {{{out_markup}}};"
        )

    # --- TEXT & KEYWORDS AREA (Middle-Lower) ---
    text_content = []
    if kw_markup:
        text_content.append(kw_markup)
    if rules_text:
        esc_rules = escape_latex(rules_text)
        text_content.append(rf"{{\sffamily\normalsize {esc_rules}}}")

    if text_content:
        full_text = r"\par\vspace{4pt}".join(text_content)
        lines.append(
            rf"    \node [anchor=center, text width=5.4cm, align=center] at (3.20, 2.75) {{{full_text}}};"
        )

    # --- BOTTOM ROW: Durability (Left), Absorption (Right) & Copyright Line ---
    if durability:
        lines.append(
            rf"    \node [anchor=center] at (1.95, 0.95) {{$\vcenter{{\hbox{{\durabilityicon}}}}\;\vcenter{{\hbox{{\sffamily\bfseries\Huge {escape_latex(durability)}}}}}$}};"
        )

    if absorption:
        lines.append(
            rf"    \node [anchor=center] at (4.55, 0.95) {{$\vcenter{{\hbox{{\absorptionicon}}}}\;\vcenter{{\hbox{{\sffamily\bfseries\Huge {escape_latex(absorption)}}}}}$}};"
        )

    artist = (card.get("Artist") or card.get("Art") or "itgresa.com").strip()
    esc_artist = escape_latex(artist)
    lines.append(
        rf"    \node [anchor=center] at (3.20, 0.22) {{\fontsize{{5pt}}{{6pt}}\selectfont\sffamily\color{{textdark!60}}\textcopyright{{}} LiLiCo \quad Art: {esc_artist}}};"
    )

    lines.append(r"  \end{scope}")
    lines.append(r"\end{tikzpicture}%")
    return "\n".join(lines) + "\n"


def process_csv(csv_path: Path) -> list[dict]:
    cards = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Name") and row["Name"].strip():
                cards.append(row)
    return cards


def main():
    parser = argparse.ArgumentParser(description="Generate card TikZ .tex files from CSV definitions.")
    parser.add_argument("--output-dir", type=Path, default=CARD_OUTPUT_DIR, help="Directory to output card .tex files")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    all_cards = []
    csv_files = [
        CARD_DEFS_DIR / "components.csv",
        CARD_DEFS_DIR / "weapons.csv",
    ]
    for extra_csv in CARD_DEFS_DIR.glob("*.csv"):
        if extra_csv not in csv_files:
            csv_files.append(extra_csv)

    for csv_file in csv_files:
        if not csv_file.is_file():
            continue
        cards = process_csv(csv_file)
        all_cards.extend(cards)

    # Collect any extra keyword colors
    extra_colors = {}
    for card in all_cards:
        kw_str = (card.get("Keywords") or "").strip()
        if kw_str:
            for kw in kw_str.split(";"):
                kw = kw.strip()
                if kw:
                    cname, rgb = get_keyword_color(kw)
                    extra_colors[cname] = rgb

    create_macros(extra_colors)

    all_tex_filenames = []
    for card in all_cards:
        card_name = card["Name"].strip()
        tex_filename = f"{sanitize_filename(card_name)}.tex"
        tex_path = args.output_dir / tex_filename
        tex_code = generate_card_tex(card)
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(tex_code)
        all_tex_filenames.append(f"card/{tex_filename}")

    all_cards_csv = BUILD_DIR / "all_cards.csv"
    with open(all_cards_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for tex in all_tex_filenames:
            writer.writerow([tex])

    print(f"Generated {len(all_cards)} card .tex file(s) in {args.output_dir}")
    print(f"Card list written to {all_cards_csv}")


if __name__ == "__main__":
    main()
