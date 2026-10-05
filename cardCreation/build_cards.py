#!/usr/bin/env python3
"""
build_cards.py

Master pipeline script for the Combat Robotics card generation system.
Automates the full flow:
  1. Generate temporary icons (generate_icons.py)
  2. Parse CSVs and generate card TikZ .tex files (generateCards.py)
  3. Render standalone card PNGs (generate_card_images.py)
  4. Generate printable A4 PDF sheets (generate_card_sheet.py + pdflatex)

Usage:
    python build_cards.py             # Full build: icons -> tex -> images -> A4 printout
    python build_cards.py --cards     # Only regenerate .tex files
    python build_cards.py --images    # Regenerate standalone PNG images
    python build_cards.py --print     # Only regenerate printable A4 PDF
"""

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent
BUILD_DIR = SCRIPT_DIR / "build"


def run(cmd, cwd=None, label=""):
    display = label or " ".join(str(c) for c in cmd)
    print(f"\n>> {display}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout[-3000:])
        if result.stderr:
            print(result.stderr[-3000:])
        sys.exit(f"FAILED: {display}")
    elif result.stdout:
        print(result.stdout.strip())


def main():
    parser = argparse.ArgumentParser(description="Master build pipeline for combatRoboticsGame cards.")
    parser.add_argument("--icons", action="store_true", help="Generate icons in pictures/icons/")
    parser.add_argument("--cards", action="store_true", help="Generate card .tex files in build/card/")
    parser.add_argument("--images", action="store_true", help="Generate individual card PNG images")
    parser.add_argument("--print", action="store_true", help="Generate printable A4 PDF sheet")
    parser.add_argument("--all", action="store_true", help="Run the complete pipeline (default)")
    parser.add_argument("--density", type=int, default=300, help="Render DPI for image conversion")
    args = parser.parse_args()

    # Default to all if no specific step requested
    run_all = args.all or not (args.icons or args.cards or args.images or args.print)

    print("=== Combat Robotics Card Pipeline ===")

    # Step 1: Icons
    if run_all or args.icons:
        run([sys.executable, str(SCRIPT_DIR / "generate_icons.py")],
            cwd=SCRIPT_DIR, label="Step 1: Generating icons")

    # Step 2: TeX Cards
    if run_all or args.cards:
        run([sys.executable, str(SCRIPT_DIR / "generateCards.py")],
            cwd=SCRIPT_DIR, label="Step 2: Generating card TikZ .tex files")

    # Step 3: Card Images
    if run_all or args.images:
        run([sys.executable, str(SCRIPT_DIR / "generate_card_images.py"),
             "--all", f"--density={args.density}"],
            cwd=SCRIPT_DIR, label="Step 3: Rendering individual card PNG images")

    # Step 4: Printable A4 Sheet
    if run_all or args.print:
        print_tex = BUILD_DIR / "print_sheet_a4.tex"
        cards_csv = BUILD_DIR / "all_cards.csv"
        run([sys.executable, str(SCRIPT_DIR / "generate_card_sheet.py"),
             f"--csv={cards_csv}", f"--output={print_tex}",
             "--a4", "--cols=4", "--rows=2"],
            cwd=SCRIPT_DIR, label="Step 4a: Generating A4 print sheet LaTeX")

        run(["pdflatex", "-interaction=nonstopmode", "print_sheet_a4.tex"],
            cwd=BUILD_DIR, label="Step 4b: Compiling A4 print sheet PDF")
        print(f"\nPrintable PDF generated: {BUILD_DIR / 'print_sheet_a4.pdf'}")

    print("\n=== Pipeline Complete ===")


if __name__ == "__main__":
    main()
