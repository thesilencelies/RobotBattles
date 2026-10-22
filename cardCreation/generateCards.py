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

# Geometry constants for US Game Card size (56mm x 87mm / 5.6cm x 8.7cm) with 2.5mm white bleed
CARD_SAFE_W_CM = 5.60
CARD_SAFE_H_CM = 8.70
BLEED_OFFSET_X = 0.25  # 0.25 cm (2.5mm) white bleed on all sides
BLEED_OFFSET_Y = 0.25  # 0.25 cm (2.5mm) white bleed on all sides
CARD_OUTER_W_CM = CARD_SAFE_W_CM + 2.0 * BLEED_OFFSET_X  # 6.10 cm
CARD_OUTER_H_CM = CARD_SAFE_H_CM + 2.0 * BLEED_OFFSET_Y  # 9.20 cm

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
    "large circle": "pictures/icons/template_large_circle.png",
    "large_circle": "pictures/icons/template_large_circle.png",
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


RESOURCE_CHARS = set("ECSMWPD")
MATH_VARS = set("XYxy")


def tokenize_resources(res_str: str) -> list[str]:
    """
    Splits a resource string into individual resource tokens.
    Single-resource strings (e.g. SSSSS, WWW2XW, 2XWW, XS) remain a single token.
    Mixed-resource strings (e.g. SSSPP, 3S 2P, 2XS 2YP) are split by delimiters or resource transitions.
    """
    s = res_str.strip().strip('"')
    if not s:
        return []

    res_in_s = [c.upper() for c in s if c.upper() in RESOURCE_CHARS]
    unique_res = set(res_in_s)

    # If at most one resource type exists in the entire string, keep as single token
    if len(unique_res) <= 1:
        if len(unique_res) == 1 and re.search(r"[XxYy]", s):
            return [re.sub(r"[\s+]+", "", s)]
        return [s]

    tokens = []
    current_token = []
    current_res = None

    i = 0
    while i < len(s):
        c = s[i]
        c_upper = c.upper()

        if c in " ,\t\r\n":
            if current_token:
                tokens.append("".join(current_token))
                current_token = []
                current_res = None
            i += 1
            continue

        if c_upper in RESOURCE_CHARS:
            if current_res is not None and current_res != c_upper:
                # Transition to a different resource type (e.g. SSS -> PP)
                tokens.append("".join(current_token))
                current_token = [c]
                current_res = c_upper
            else:
                current_token.append(c)
                current_res = c_upper
        elif c_upper in MATH_VARS or c.isdigit() or c in "+*x/-":
            if current_res is not None:
                # Transition from completed resource to a new number/math prefix
                tokens.append("".join(current_token))
                current_token = [c]
                current_res = None
            else:
                current_token.append(c)
        else:
            current_token.append(c)
        i += 1

    if current_token:
        tokens.append("".join(current_token))

    return tokens


def parse_token_info(tok: str) -> dict | None:
    """Parses a resource token into prefix, char, count, math_expr, and fixed_count."""
    tok = tok.strip()
    match = re.match(r"^(.*?)([ECSMWPD])$", tok, re.IGNORECASE)
    if not match:
        return None
    prefix, char = match.groups()
    char = char.upper()

    if not prefix:
        return {"prefix": "", "char": char, "count": 1, "is_repeat": True, "math_expr": None}
    if all(c.upper() == char for c in prefix):
        return {"prefix": prefix, "char": char, "count": len(prefix) + 1, "is_repeat": True, "math_expr": None}
    if prefix.isdigit():
        return {"prefix": prefix, "char": char, "count": int(prefix), "is_repeat": True, "math_expr": None}

    # Math prefix: math letters are strictly X and Y
    mult_after_match = re.match(r"^(\d*(?:XxX|XX|YxY|YY|XY|YX|[XY]|\d+x\d+))(" + char + r"*)$", prefix, re.IGNORECASE)
    mult_before_match = re.match(r"^(" + char + r"+)(\d*(?:XxX|XX|YxY|YY|XY|YX|[XY]|\d+x\d+))$", prefix, re.IGNORECASE)

    if mult_after_match:
        mult_expr, extra_icons = mult_after_match.groups()
        fixed_count = len(extra_icons)
        return {"prefix": prefix, "char": char, "count": fixed_count + 1, "is_repeat": False, "mult_expr": mult_expr, "fixed_count": fixed_count}
    elif mult_before_match:
        extra_icons, mult_expr = mult_before_match.groups()
        fixed_count = len(extra_icons)
        return {"prefix": prefix, "char": char, "count": fixed_count + 1, "is_repeat": False, "mult_expr": mult_expr, "fixed_count": fixed_count}

    return {"prefix": prefix, "char": char, "count": 1, "is_repeat": False, "mult_expr": prefix, "fixed_count": 0}


def format_single_resource_item(tok_info: dict, resource_math: bool = False, icon_size: str = "") -> str:
    """Formats a parsed single resource item token into TikZ/LaTeX markup."""
    char = tok_info["char"]
    prefix = tok_info["prefix"]

    if resource_math:
        if tok_info["is_repeat"]:
            count = tok_info["count"]
            return rf"$\vcenter{{\hbox{{\sffamily\bfseries\LARGE {count}}}}}\;\vcenter{{\hbox{{\resource{char}}}}}$"
        else:
            mult_expr = tok_info.get("mult_expr", prefix)
            fixed_count = tok_info.get("fixed_count", 0)
            if mult_expr.upper() == "XX":
                mult_expr = "XxX"
            elif mult_expr.upper() == "YY":
                mult_expr = "YxY"

            if fixed_count == 0:
                esc_mult = escape_latex(mult_expr)
                return rf"$\vcenter{{\hbox{{\sffamily\bfseries\LARGE {esc_mult}}}}}\;\vcenter{{\hbox{{\resource{char}}}}}$"
            else:
                math_expr = f"{mult_expr}+{fixed_count}"
                esc_math = escape_latex(math_expr)
                return rf"$\vcenter{{\hbox{{\sffamily\bfseries\LARGE {esc_math}}}}}\;\vcenter{{\hbox{{\resource{char}}}}}$"
    else:
        if tok_info["is_repeat"]:
            count = tok_info["count"]
            sz = icon_size if icon_size else ("[0.52cm]" if count >= 5 else "")
            icons = [f"\\resource{char}{sz}" for _ in range(count)]
            if count <= 2:
                return r"\hspace{1.5pt}".join(icons)
            else:
                top_count = (count + 1) // 2
                row1 = r"\hspace{1.5pt}".join(icons[:top_count])
                row2 = r"\hspace{1.5pt}".join(icons[top_count:])
                return rf"\parbox{{2.5cm}}{{\centering {row1}\par\vspace{{1.5pt}}{row2}}}"
        else:
            mult_expr = tok_info.get("mult_expr", prefix)
            fixed_count = tok_info.get("fixed_count", 0)
            if mult_expr.upper() == "XX":
                mult_expr = "XxX"
            elif mult_expr.upper() == "YY":
                mult_expr = "YxY"
            esc_mult = escape_latex(mult_expr)
            mult_element = rf"$\vcenter{{\hbox{{\sffamily\bfseries\LARGE {esc_mult}}}}}\;\vcenter{{\hbox{{\resource{char}}}}}$"

            if fixed_count == 0:
                return mult_element
            else:
                fixed_icons = [rf"\resource{char}" for _ in range(fixed_count)]
                row1 = r"\hspace{1.5pt}".join(fixed_icons)
                row2 = mult_element
                return rf"\parbox{{2.5cm}}{{\centering {row1}\par\vspace{{1.5pt}}{row2}}}"


def format_resource_item(prefix: str, char: str, resource_math: bool = False, icon_size: str = "") -> str:
    """Formats a single resource item, repeated icons, or fixed + multiplier symbols."""
    raw_tok = f"{prefix}{char}"
    info = parse_token_info(raw_tok)
    if info:
        return format_single_resource_item(info, resource_math=resource_math, icon_size=icon_size)
    esc_tok = escape_latex(raw_tok)
    return rf"{{\sffamily\bfseries {esc_tok}}}"


def parse_resources(res_str: str, resource_math: bool = False) -> str:
    """
    Parses a resource string into TikZ/LaTeX markup.
    Rules from terminology.md:
      - Repeated letter (e.g. EE, CC, SSS) -> multiple icons drawn.
        Repeat symbols are placed closer together, spilling into two rows if count >= 3.
      - Additive symbols and math (e.g. W2XW, 2XWW, XWW, XWWW) ->
        Pure symbols drawn in row 1, math plus symbol drawn in row 2 below them.
      - Multiplier alone (e.g. 2XW, XXW, XE, 6W) ->
        Prefix rendered in sans-serif text vertically center-aligned with the icon in a single row.
      - Multiplier XX is rendered as XxX, YY is rendered as YxY. Math letters are strictly X and Y.
      - Mixed requirements (e.g. SSSPP -> 3 Spin, 2 Pressure) ->
        Icons grouped by resource type across two rows.
      - If resource_math is True:
        Numbers are written out next to the resource symbol (e.g. 4S, 2X+1W) instead of counts of icons.
    """
    if not res_str:
        return ""

    tokens = tokenize_resources(res_str)
    if not tokens:
        return ""

    if len(tokens) == 1:
        info = parse_token_info(tokens[0])
        if info:
            return format_single_resource_item(info, resource_math=resource_math)
        return rf"{{\sffamily\bfseries {escape_latex(tokens[0])}}}"

    # Multiple tokens (mixed resources, e.g. ["SSS", "PP"])
    parsed_infos = []
    for t in tokens:
        info = parse_token_info(t)
        if info:
            parsed_infos.append(info)
        else:
            parsed_infos.append({"raw": t})

    total_icons = sum(info.get("count", 1) for info in parsed_infos)

    if resource_math:
        elements = []
        for info in parsed_infos:
            if "raw" in info:
                raw_text = info["raw"]
                elements.append(rf"{{\sffamily\bfseries {escape_latex(raw_text)}}}")
            else:
                elements.append(format_single_resource_item(info, resource_math=True))
        if len(elements) == 2:
            return rf"\parbox{{2.5cm}}{{\centering {elements[0]}\par\vspace{{1.5pt}}{elements[1]}}}"
        else:
            return r"\hspace{2pt}".join(elements)
    else:
        # Icon representation: scale down to [0.52cm] if 5 or more icons total
        icon_size = "[0.52cm]" if total_icons >= 5 else ""

        # If total_icons <= 2, render side-by-side on 1 row
        if total_icons <= 2:
            icons = []
            for info in parsed_infos:
                ch = info["char"]
                if info.get("is_repeat"):
                    icons.extend([f"\\resource{ch}{icon_size}" for _ in range(info["count"])])
                else:
                    icons.append(format_single_resource_item(info, resource_math=False, icon_size=icon_size))
            return r"\hspace{1.5pt}".join(icons)

        # If 2 distinct resource groups (like SSS and PP):
        if len(parsed_infos) == 2:
            row_items = []
            for info in parsed_infos:
                ch = info["char"]
                if info.get("is_repeat"):
                    c_icons = [f"\\resource{ch}{icon_size}" for _ in range(info["count"])]
                    row_items.append(r"\hspace{1.5pt}".join(c_icons))
                else:
                    row_items.append(format_single_resource_item(info, resource_math=False, icon_size=icon_size))
            return rf"\parbox{{2.5cm}}{{\centering {row_items[0]}\par\vspace{{1.5pt}}{row_items[1]}}}"

        # General fallback for > 2 resource groups
        row_items = []
        for info in parsed_infos:
            ch = info["char"]
            if info.get("is_repeat"):
                c_icons = [f"\\resource{ch}{icon_size}" for _ in range(info["count"])]
                row_items.append(r"\hspace{1.5pt}".join(c_icons))
            else:
                row_items.append(format_single_resource_item(info, resource_math=False, icon_size=icon_size))
        top = row_items[0]
        bot = r"\hspace{2pt}".join(row_items[1:])
        return rf"\parbox{{2.5cm}}{{\centering {top}\par\vspace{{1.5pt}}{bot}}}"


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
        f.write(r"""% Robot Battles Card Macros
\RequirePackage{xcolor}
\RequirePackage{graphicx}
\RequirePackage[export]{adjustbox}
\RequirePackage{tikz}
\RequirePackage[none]{hyphenat}
\RequirePackage[sfdefault]{roboto}

% Color definitions
\definecolor{chevronpurple}{RGB}{40, 0, 70}
\definecolor{costgreen}{RGB}{0, 128, 20}
\definecolor{durabilityred}{RGB}{185, 0, 0}
\definecolor{textdark}{RGB}{20, 20, 20}

% Keyword colors
""" + colors_block + r"""

% Keyword badge macro: text in front of colored box (fixed height for all keywords)
\newcommand{\keywordbadge}[2]{%
  \tikz[baseline=-0.6ex]\node[fill=#1, rounded corners=2.0pt, inner xsep=4.0pt, inner ysep=0pt, minimum height=0.46cm, text height=0.24cm, text depth=0.07cm, text=white]{\sffamily\bfseries\scriptsize #2};%
}

% Global graphicspath so images resolve from build/, permutations/, cardCreation/, or root
\graphicspath{{../../../../}{../../../}{../../}{../}{./}{../../../../pictures/icons/}{../../../pictures/icons/}{../../pictures/icons/}{../pictures/icons/}{pictures/icons/}}

% Resource icon commands
\newcommand{\resourceE}[1][0.68cm]{\includegraphics[height=#1,keepaspectratio]{pictures/icons/energy.png}}
\newcommand{\resourceC}[1][0.68cm]{\includegraphics[height=#1,keepaspectratio]{pictures/icons/control.png}}
\newcommand{\resourceS}[1][0.68cm]{\includegraphics[height=#1,keepaspectratio]{pictures/icons/spin.png}}
\newcommand{\resourceP}[1][0.68cm]{\includegraphics[height=#1,keepaspectratio]{pictures/icons/pressure.png}}
\newcommand{\resourceM}[1][0.68cm]{\includegraphics[height=#1,keepaspectratio]{pictures/icons/drive.png}}
\newcommand{\resourceD}[1][0.68cm]{\includegraphics[height=#1,keepaspectratio]{pictures/icons/drive.png}}
\newcommand{\resourceW}[1][0.68cm]{\includegraphics[height=#1,keepaspectratio]{pictures/icons/damage.png}}

% Card stat icon commands
\newcommand{\durabilityicon}{\includegraphics[height=0.76cm,keepaspectratio]{pictures/icons/durability.png}}
\newcommand{\absorptionicon}{\includegraphics[height=0.76cm,keepaspectratio]{pictures/icons/absorption.png}}
\newcommand{\weighticon}[1][0.80cm]{\includegraphics[height=#1,keepaspectratio]{pictures/icons/weight.png}}
\newcommand{\weighticonplain}[1][0.80cm]{\includegraphics[height=#1,keepaspectratio]{pictures/icons/weight_plain.png}}
""")
    print(f"Wrote {macros_file}")


def generate_card_tex(
    card: dict,
    weight_mode: str = "number",
    cost_number: bool = True,
    resource_math: bool = False,
) -> str:
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

    req_markup = parse_resources(card.get("Requirements") or "", resource_math=resource_math)
    out_markup = parse_resources(card.get("Outputs") or "", resource_math=resource_math)

    img_rel_path = find_component_image(card.get("Picture") or "")

    kw_markup, color_defs = format_keywords(keywords)

    lines = [
        r"\begin{tikzpicture}[x=1cm, y=1cm]",
        rf"  \node (cardbleed) [rectangle, minimum width={CARD_OUTER_W_CM:.2f}cm, minimum height={CARD_OUTER_H_CM:.2f}cm, fill=white] at ({CARD_OUTER_W_CM/2:.2f}, {CARD_OUTER_H_CM/2:.2f}) {{}};",
        rf"  \useasboundingbox (0,0) rectangle ({CARD_OUTER_W_CM:.2f}, {CARD_OUTER_H_CM:.2f});",
        rf"  \clip (0,0) rectangle ({CARD_OUTER_W_CM:.2f}, {CARD_OUTER_H_CM:.2f});",
    ]

    # Provide colors if compiling standalone
    for cname, (r, g, b) in color_defs:
        lines.append(rf"  \providecolor{{{cname}}}{{RGB}}{{{r}, {g}, {b}}}")

    lines.append(rf"  \begin{{scope}}[shift={{({BLEED_OFFSET_X:.3f}, {BLEED_OFFSET_Y:.3f})}}]")

    # Cut guide border (faint cut line at 56mm x 87mm boundary)
    lines.append(
        rf"    \draw [draw=gray!35, line width=0.4pt, rounded corners=2.0mm] (0.00, 0.00) rectangle ({CARD_SAFE_W_CM:.2f}, {CARD_SAFE_H_CM:.2f});"
    )

    # --- TOP ROW: Weights, Title, Cost, Template ---
    # Stacked or Numbered Weight Icons
    if weight > 0:
        if weight_mode == "number":
            lines.append(rf"    \node [anchor=center] at (0.50, 7.95) {{\weighticonplain[0.85cm]}};")
            lines.append(rf"    \node [anchor=center] at (0.50, 7.87) {{\textcolor{{white}}{{\sffamily\bfseries\large {weight}}}}};")
        elif weight_mode == "multiple_no_1t":
            if weight <= 3:
                for w_idx in range(weight):
                    wy = 7.95 - (w_idx * 0.90)
                    lines.append(rf"    \node [anchor=center] at (0.50, {wy:.2f}) {{\weighticonplain}};")
            else:
                col1_count = (weight + 1) // 2
                col2_count = weight - col1_count
                x1, x2 = 0.35, 0.88
                y_start = 7.95
                y_spacing = 0.70
                for i in range(col1_count):
                    wy = y_start - (i * y_spacing)
                    lines.append(rf"    \node [anchor=center] at ({x1:.2f}, {wy:.2f}) {{\weighticonplain[0.58cm]}};")
                for i in range(col2_count):
                    wy = y_start - (i * y_spacing)
                    lines.append(rf"    \node [anchor=center] at ({x2:.2f}, {wy:.2f}) {{\weighticonplain[0.58cm]}};")
        else:
            if weight <= 3:
                for w_idx in range(weight):
                    wy = 7.95 - (w_idx * 0.90)
                    lines.append(rf"    \node [anchor=center] at (0.50, {wy:.2f}) {{\weighticon}};")
            else:
                col1_count = (weight + 1) // 2
                col2_count = weight - col1_count
                x1, x2 = 0.35, 0.88
                y_start = 7.95
                y_spacing = 0.70
                for i in range(col1_count):
                    wy = y_start - (i * y_spacing)
                    lines.append(rf"    \node [anchor=center] at ({x1:.2f}, {wy:.2f}) {{\weighticon[0.58cm]}};")
                for i in range(col2_count):
                    wy = y_start - (i * y_spacing)
                    lines.append(rf"    \node [anchor=center] at ({x2:.2f}, {wy:.2f}) {{\weighticon[0.58cm]}};")

    # Card Title (top-center)
    esc_name = escape_latex(name)
    lines.append(
        rf"    \node [anchor=center, text width=3.2cm, align=center] at (2.80, 8.00) {{\fontsize{{13pt}}{{15pt}}\sffamily\bfseries {esc_name}}};"
    )

    # Cost (top-right, green dollar signs or number next to dollar)
    if cost > 0:
        if cost_number:
            lines.append(
                rf"    \node [anchor=center] at (5.05, 8.00) {{\textcolor{{costgreen}}{{\sffamily\textbf{{\LARGE \${cost}}}}}}};"
            )
        elif cost < 4:
            cost_str = r"\$" * cost
            lines.append(
                rf"    \node [anchor=center] at (5.05, 8.00) {{\textcolor{{costgreen}}{{\sffamily\textbf{{\LARGE {cost_str}}}}}}};"
            )
        else:
            top_count = (cost + 1) // 2
            bot_count = cost - top_count
            row1 = r"\$" * top_count
            row2 = r"\$" * bot_count
            lines.append(
                rf"    \node [anchor=center] at (5.05, 8.00) {{\textcolor{{costgreen}}{{\sffamily\bfseries\large\begin{{tabular}}{{@{{}}c@{{}}}}{row1}\\[-4pt]{row2}\end{{tabular}}}}}};"
            )

    # Template Icon (below cost, if weapon card)
    if template and template in TEMPLATE_ICONS:
        tmpl_icon = TEMPLATE_ICONS[template]
        lines.append(
            rf"    \node [anchor=center] at (4.75, 6.55) {{\includegraphics[height=0.92cm, keepaspectratio]{{{tmpl_icon}}}}};"
        )

    # --- COMPONENT ARTWORK (Center-Upper) ---
    art_cx = 2.80
    art_cy = 6.45
    if img_rel_path:
        lines.append(
            rf"    \node [anchor=center] at ({art_cx:.2f}, {art_cy:.2f}) {{\includegraphics[width=3.1cm, max height=1.9cm, keepaspectratio]{{{img_rel_path}}}}};"
        )
    else:
        lines.append(
            rf"    \node [rectangle, draw=gray!40, rounded corners=0.15cm, dashed, minimum width=3.0cm, minimum height=1.8cm, fill=gray!5] at ({art_cx:.2f}, {art_cy:.2f}) {{\small\color{{gray}}\textsf{{[ {esc_name} ]}}}};"
        )

    # --- MIDDLE BAND: Left/Right Pointy Chevrons & Resource Flow ---
    if req_markup:
        lines.append(
            r"    \fill [chevronpurple] (0.00, 5.15) -- (0.75, 4.40) -- (0.00, 3.65) -- (0.00, 3.97) -- (0.45, 4.40) -- (0.00, 4.83) -- cycle;"
        )
        lines.append(
            rf"    \node [anchor=center, text width=2.2cm, align=center] at (1.65, 4.40) {{{req_markup}}};"
        )

    if out_markup:
        lines.append(
            rf"    \fill [chevronpurple] ({CARD_SAFE_W_CM - 0.75:.2f}, 5.15) -- ({CARD_SAFE_W_CM:.2f}, 4.40) -- ({CARD_SAFE_W_CM - 0.75:.2f}, 3.65) -- ({CARD_SAFE_W_CM - 0.75:.2f}, 3.97) -- ({CARD_SAFE_W_CM - 0.45:.2f}, 4.40) -- ({CARD_SAFE_W_CM - 0.75:.2f}, 4.83) -- cycle;"
        )
        lines.append(
            rf"    \node [anchor=center, text width=2.2cm, align=center] at (3.95, 4.40) {{{out_markup}}};"
        )

    # --- TEXT & KEYWORDS AREA (Middle-Lower) ---
    text_content = []
    if kw_markup:
        text_content.append(kw_markup)
    if rules_text:
        esc_rules = escape_latex(rules_text)
        text_content.append(rf"{{\sffamily\small {esc_rules}}}")

    if text_content:
        full_text = r"\par\vspace{3pt}".join(text_content)
        lines.append(
            rf"    \node [anchor=center, text width=4.8cm, align=center] at (2.80, 2.55) {{{full_text}}};"
        )

    # --- BOTTOM ROW: Durability (Left), Absorption (Right) & Copyright Line ---
    if durability:
        lines.append(
            rf"    \node [anchor=center] at (1.60, 0.90) {{$\vcenter{{\hbox{{\durabilityicon}}}}\;\vcenter{{\hbox{{\sffamily\bfseries\huge {escape_latex(durability)}}}}}$}};"
        )

    if absorption:
        lines.append(
            rf"    \node [anchor=center] at (4.00, 0.90) {{$\vcenter{{\hbox{{\absorptionicon}}}}\;\vcenter{{\hbox{{\sffamily\bfseries\huge {escape_latex(absorption)}}}}}$}};"
        )

    artist = (card.get("Artist") or card.get("Art") or "itgresa.com").strip()
    esc_artist = escape_latex(artist)
    lines.append(
        rf"    \node [anchor=center] at (2.80, 0.20) {{\fontsize{{5pt}}{{6pt}}\selectfont\sffamily\color{{textdark!60}}\textcopyright{{}} LiLiCo \quad Art: {esc_artist}}};"
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
    parser.add_argument(
        "--weight-mode",
        choices=["number", "multiple", "multiple_no_1t"],
        default="number",
        help="Weight icon style: number (default: single icon with number), multiple (with 1T), or multiple_no_1t (without 1T)",
    )
    parser.add_argument(
        "--weight-number",
        action="store_true",
        help="Use a single weight logo with number on top (default)",
    )
    parser.add_argument(
        "--multiple-weights",
        "--stacked-weights",
        action="store_true",
        help="Use multiple stacked weight logos with 1T instead of single numbered logo",
    )
    parser.add_argument(
        "--no-weight-1t",
        action="store_true",
        help="Use multiple stacked weight logos without 1T text",
    )
    parser.add_argument(
        "--cost-number",
        action="store_true",
        default=True,
        help="Have a number next to the cost symbol (default: True)",
    )
    parser.add_argument(
        "--multiple-cost",
        "--cost-symbols",
        action="store_true",
        help="Use multiple dollar signs instead of single $ with number",
    )
    parser.add_argument(
        "--resource-math",
        action="store_true",
        default=False,
        help="Have a number next to the resources writing out the math instead of a count of resources",
    )
    parser.add_argument(
        "--manifest-csv",
        type=Path,
        default=None,
        help="Path to output all_cards.csv manifest (defaults to build/all_cards.csv or output-dir parent)",
    )
    args = parser.parse_args()

    weight_mode = args.weight_mode
    if args.multiple_weights:
        weight_mode = "multiple"
    elif args.no_weight_1t:
        weight_mode = "multiple_no_1t"
    elif args.weight_number:
        weight_mode = "number"

    cost_number = True
    if args.multiple_cost:
        cost_number = False

    args.output_dir.mkdir(parents=True, exist_ok=True)

    all_cards = []
    csv_files = [
        CARD_DEFS_DIR / "components.csv",
        CARD_DEFS_DIR / "weapons.csv",
    ]
    for extra_csv in CARD_DEFS_DIR.glob("*.csv"):
        if extra_csv not in csv_files and extra_csv.name != "chassis.csv":
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
        tex_code = generate_card_tex(
            card,
            weight_mode=weight_mode,
            cost_number=args.cost_number,
            resource_math=args.resource_math,
        )
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(tex_code)
        # Store relative to manifest
        all_tex_filenames.append(f"card/{tex_filename}")

    manifest_csv = args.manifest_csv or (args.output_dir.parent / "all_cards.csv")
    with open(manifest_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for tex in all_tex_filenames:
            writer.writerow([tex])

    print(f"Generated {len(all_cards)} card .tex file(s) in {args.output_dir}")
    print(f"Card list written to {manifest_csv}")


if __name__ == "__main__":
    main()
