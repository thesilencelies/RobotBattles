#!/usr/bin/env python3
"""
generate_chassis_sheets.py

Reads cardDefinitions/chassis.csv and generates standalone printable A3 landscape
sheets (SVG and HTML) for each chassis template shape, complete with mm grid,
chassis stats banner, and orientation heading.
"""

import argparse
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

from builder.server.chassis_sheets import export_all_chassis_sheets


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate A3 Chassis Sheets")
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=WORKSPACE / "chassisSheets",
        help="Destination directory for generated sheets",
    )
    args = parser.parse_args()

    out_dir = args.output_dir.resolve()
    print(f"Generating A3 chassis sheets into: {out_dir}")
    files = export_all_chassis_sheets(out_dir)
    for f in files:
        print(f"  + {f.name}")
    print(f"Done. Generated {len(files)} files.")


if __name__ == "__main__":
    main()
