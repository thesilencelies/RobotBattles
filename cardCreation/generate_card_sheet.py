#!/usr/bin/env python3
r"""
generate_card_sheet.py

Reads a CSV file of card .tex filenames (one per line, no header) and generates
a LaTeX file that lays them out in a grid suitable for printing or Tabletop Simulator.

Each card is a TikZ image of 6.9cm x 9.4cm (6.4cm x 8.9cm with 0.25cm bleed on all sides),
included via \input{}.
"""

import argparse
import csv
import math
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Layout defaults
# ---------------------------------------------------------------------------
DEFAULT_COLS = 10
DEFAULT_ROWS = 7

CARD_WIDTH_CM  = 6.9
CARD_HEIGHT_CM = 9.4

TYPE_PREFIXES = {"card": "card/"}

# ---------------------------------------------------------------------------
# LaTeX template pieces
# ---------------------------------------------------------------------------

PREAMBLE = r"""\documentclass{{article}}
\usepackage[none]{{hyphenat}}
\hyphenpenalty=10000
\exhyphenpenalty=10000
\usepackage{{tikz}}
\usepackage[export]{{adjustbox}}
\usepackage{{geometry}}
\input{{card_macros.tex}}
\usetikzlibrary{{positioning}}
\usetikzlibrary{{patterns}}
\usetikzlibrary{{arrows.meta}}
\usetikzlibrary{{calc}}

{geometry}

\setlength{{\parindent}}{{0pt}}
\setlength{{\parskip}}{{0pt}}
\setlength{{\topskip}}{{0pt}}
\pagestyle{{empty}}

\begin{{document}}
"""

SHEET_BEGIN = r"""%% --- Sheet {sheet_num} ({first_card}–{last_card}) ---
\noindent
"""

CARD_INCLUDE = r"""\hbox to {width}cm{{\hss
  \begin{{minipage}}[t][{height}cm][t]{{{width}cm}}%
    \vspace{{0pt}}%
    \input{{{filename}}}%
  \end{{minipage}}%
  \hss}}%
"""

EMPTY_CELL = r"""\hbox to {width}cm{{\hss
  \begin{{minipage}}[t][{height}cm][t]{{{width}cm}}%
  \end{{minipage}}%
  \hss}}%
"""

ROW_BEGIN = r"""\noindent\makebox[0pt][l]{}%
"""

ROW_END = r"""\par\vspace{0pt}%
"""

SHEET_END = r"""\newpage
"""

POSTAMBLE = r"""\end{document}
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_card_list(csv_path: str, prefix: str = "") -> list[str]:
    """Read a single-column CSV (no header) and return a list of .tex filenames."""
    if not os.path.isfile(csv_path):
        sys.exit(f"Error: CSV file not found: {csv_path}")

    cards = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        for row in reader:
            if row:
                filename = row[0].strip()
                if filename:
                    if prefix and "/" not in filename:
                        filename = prefix + filename
                    if not filename.endswith(".tex"):
                        filename += ".tex"
                    cards.append(filename)

    if not cards:
        sys.exit("Error: No card filenames found in the CSV.")

    return cards


def generate_latex(cards: list[str], bleed: float, cols: int, rows: int,
                   a4: bool = False) -> str:
    """Build the full LaTeX source string."""
    cards_per_sheet = cols * rows
    num_sheets = math.ceil(len(cards) / cards_per_sheet)

    if a4:
        A4_WIDTH_CM = 29.7
        A4_HEIGHT_CM = 21.0
        grid_width  = cols * CARD_WIDTH_CM  + (cols - 1) * bleed
        grid_height = rows * CARD_HEIGHT_CM + (rows - 1) * bleed
        margin_x = max(0.0, (A4_WIDTH_CM - grid_width) / 2.0)
        margin_top = max(0.0, (A4_HEIGHT_CM - grid_height) / 2.0)
        margin_bottom = max(0.0, min(margin_top, 0.4))
        geometry = (
            f"% A4 landscape with cards centered\n"
            f"\\geometry{{\n"
            f"    a4paper,\n"
            f"    landscape,\n"
            f"    left={margin_x:.4f}cm,\n"
            f"    right={margin_x:.4f}cm,\n"
            f"    top={margin_top:.4f}cm,\n"
            f"    bottom={margin_bottom:.4f}cm\n"
            f"}}"
        )
    else:
        row_slack_cm = 0.2
        page_width  = cols * CARD_WIDTH_CM  + (cols - 1) * bleed
        page_height = rows * (CARD_HEIGHT_CM + row_slack_cm) + (rows - 1) * bleed
        geometry = (
            f"% Page size matches the exact grid: {page_width:.4f}cm x {page_height:.4f}cm\n"
            f"\\geometry{{\n"
            f"    paperwidth={page_width:.4f}cm,\n"
            f"    paperheight={page_height:.4f}cm,\n"
            f"    margin=0cm\n"
            f"}}"
        )

    w = f"{CARD_WIDTH_CM:.4f}"
    h = f"{CARD_HEIGHT_CM:.4f}"

    lines = []
    lines.append(PREAMBLE.format(geometry=geometry))

    for sheet in range(num_sheets):
        first_idx  = sheet * cards_per_sheet
        last_idx   = min(first_idx + cards_per_sheet, len(cards))
        sheet_cards = cards[first_idx:last_idx]

        lines.append(SHEET_BEGIN.format(
            sheet_num=sheet + 1,
            first_card=first_idx + 1,
            last_card=last_idx,
        ))

        for row in range(rows):
            lines.append(ROW_BEGIN)
            for col in range(cols):
                pos = row * cols + col
                if pos < len(sheet_cards):
                    lines.append(CARD_INCLUDE.format(
                        width=w, height=h,
                        filename=sheet_cards[pos],
                    ))
                else:
                    lines.append(EMPTY_CELL.format(width=w, height=h))
            lines.append(ROW_END)

        lines.append(SHEET_END)

    lines.append(POSTAMBLE)
    return "".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate a LaTeX card sheet for printout or TTS."
    )
    parser.add_argument(
        "--csv", required=True,
        help="Path to the single-column CSV listing card .tex filenames."
    )
    parser.add_argument(
        "--output", default="card_sheet.tex",
        help="Output .tex filename (default: card_sheet.tex)."
    )
    parser.add_argument(
        "--type", choices=sorted(TYPE_PREFIXES), default=None,
        help="Deck type (card); prepends build/card/ subfolder."
    )
    parser.add_argument(
        "--cols", type=int, default=DEFAULT_COLS,
        help=f"Number of card columns per sheet (default: {DEFAULT_COLS})."
    )
    parser.add_argument(
        "--rows", type=int, default=DEFAULT_ROWS,
        help=f"Number of card rows per sheet (default: {DEFAULT_ROWS})."
    )
    parser.add_argument(
        "--bleed", type=float, default=0.0,
        help="Gap between cards in cm (default: 0.0)."
    )
    parser.add_argument(
        "--a4", action="store_true",
        help="Format the sheet for A4 landscape paper (centered grid)."
    )
    args = parser.parse_args()

    cards = read_card_list(args.csv, prefix=TYPE_PREFIXES.get(args.type, ""))
    cards_per_sheet = args.cols * args.rows

    print(f"Grid: {args.cols}x{args.rows} ({cards_per_sheet} cards per sheet)")
    print(f"Found {len(cards)} card(s) -> {math.ceil(len(cards) / cards_per_sheet)} sheet(s).")

    latex_source = generate_latex(cards, bleed=args.bleed, cols=args.cols, rows=args.rows,
                                  a4=args.a4)

    with open(args.output, "w", encoding="utf-8") as fh:
        fh.write(latex_source)

    print(f"LaTeX file written to: {args.output}")


if __name__ == "__main__":
    main()
