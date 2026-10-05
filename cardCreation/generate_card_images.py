#!/usr/bin/env python3
"""
generate_card_images.py

Renders individual cards to standalone PNG images (e.g. for previews, a
rulebook, website, or TTS).

Reads a single-column CSV listing card .tex filenames (e.g. build/all_cards.csv
or a custom list). Each card is placed on its own page via generate_card_sheet.py
--cols 1 --rows 1. The resulting multi-page PDF is compiled with pdflatex, then
rasterized to individual PNGs named after each card.

Usage:
    python generate_card_images.py --all
    python generate_card_images.py --csv build/all_cards.csv --output-dir ../CardImages
"""

import argparse
import csv
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent
BUILD_DIR = SCRIPT_DIR / "build"
CARD_OUTPUT_DIR = BUILD_DIR / "card"
DEFAULT_IMAGES_DIR = WORKSPACE / "CardImages"


def run(cmd, cwd=None, label=""):
    display = label or " ".join(str(c) for c in cmd)
    print(f"  $ {display}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout[-3000:])
        if result.stderr:
            print(result.stderr[-3000:])
        sys.exit(f"FAILED: {display}")


def read_card_list(csv_path: Path) -> list[str]:
    """Read a single-column CSV and return list of .tex filenames."""
    if not csv_path.is_file():
        sys.exit(f"Error: CSV file not found: {csv_path}")

    cards = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        for row in reader:
            if row and row[0].strip():
                fn = row[0].strip()
                if not fn.endswith(".tex"):
                    fn += ".tex"
                cards.append(fn)

    if not cards:
        sys.exit("Error: No card filenames found in the CSV.")

    return cards


def card_image_name(card_tex: str) -> str:
    """card/Example_ESC.tex -> Example_ESC.png"""
    stem = Path(card_tex).stem
    if stem.startswith("card_"):
        stem = stem[5:]
    stem = re.sub(r"\s+", "_", stem)
    stem = re.sub(r"[^A-Za-z0-9_.-]", "", stem)
    return stem + ".png"


def _compile_and_rasterize(sheet_name: str, output_names: list[str], output_dir: Path, density: int):
    sheet_tex = f"{sheet_name}.tex"
    sheet_pdf = f"{sheet_name}.pdf"

    run(["pdflatex", "-interaction=nonstopmode", sheet_tex], cwd=BUILD_DIR,
        label=f"pdflatex {sheet_tex}")

    output_dir.mkdir(parents=True, exist_ok=True)

    for i, out_name in enumerate(output_names):
        out_path = output_dir / out_name
        run(
            ["convert", "-density", str(density), f"{sheet_pdf}[{i}]",
             "-compress", "lzw", str(out_path)],
            cwd=BUILD_DIR,
            label=f"convert {sheet_pdf} page {i} -> {output_dir.name}/{out_name}",
        )

    print(f"\nWrote {len(output_names)} card image(s) to {output_dir}/")


def generate_card_images(csv_path: Path, output_dir: Path, density: int, sheet_name: str = "single_cards_sheet"):
    cards = read_card_list(csv_path)
    print(f"Found {len(cards)} card(s) in {csv_path}")

    # Ensure all tex files exist
    for c in cards:
        tex_file = BUILD_DIR / c
        if not tex_file.is_file():
            sys.exit(f"Error: {tex_file} not found. Please run generateCards.py first.")

    sheet_tex = f"{sheet_name}.tex"

    run(
        [sys.executable, str(SCRIPT_DIR / "generate_card_sheet.py"),
         f"--csv={csv_path}", f"--output={BUILD_DIR / sheet_tex}",
         "--cols=1", "--rows=1"],
        cwd=SCRIPT_DIR,
        label=f"generate_card_sheet {csv_path.name} -> {sheet_tex} (1 card per page)",
    )

    output_names = [card_image_name(card) for card in cards]
    _compile_and_rasterize(sheet_name, output_names, output_dir, density)


def main():
    parser = argparse.ArgumentParser(
        description="Render individual cards to standalone PNG images."
    )
    parser.add_argument(
        "--csv", type=Path, default=None,
        help="Path to single-column CSV listing card .tex filenames (default: build/all_cards.csv)"
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Render all generated cards from build/all_cards.csv"
    )
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_IMAGES_DIR,
        help=f"Directory to write PNG files (default: {DEFAULT_IMAGES_DIR})"
    )
    parser.add_argument(
        "--density", type=int, default=300,
        help="Render DPI for ImageMagick convert (default: 300)"
    )
    args = parser.parse_args()

    csv_path = args.csv
    if args.all or csv_path is None:
        csv_path = BUILD_DIR / "all_cards.csv"

    if not csv_path.is_file():
        # Run generateCards.py first if build/all_cards.csv doesn't exist
        print(f"{csv_path} not found. Running generateCards.py...")
        run([sys.executable, str(SCRIPT_DIR / "generateCards.py")], cwd=SCRIPT_DIR)

    generate_card_images(csv_path, args.output_dir, args.density)


if __name__ == "__main__":
    main()
