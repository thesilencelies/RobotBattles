#!/usr/bin/env python3
"""
regenerate_all_data.py

Master data regeneration script for Robot Battles.
Executes the full data generation and export pipeline in one command:
  1. Card Pipeline (cardCreation/build_cards.py)
     - Procedural icons (pictures/icons/)
     - TikZ card definitions (cardCreation/build/card/*.tex)
     - Standalone PNG card images (CardImages/*.png)
     - Printable A4 card sheets (cardCreation/build/print_sheet_a4.pdf)
  2. Tabletop Simulator JSON (generate_card_json.py -> json/cards.json)
  3. A3 Chassis Sheets (scripts/generate_chassis_sheets.py -> chassisSheets/)
  4. Movement Templates (generate_movement_templates.py -> movement_templates/)
  5. Combat Simulation Report (scripts/simulate_combat.py -> scripts/output/)

Usage:
  python scripts/regenerate_all_data.py            # Complete regeneration
  python scripts/regenerate_all_data.py --quick    # Skip slow image rasterization
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_step(name: str, cmd: list[str], cwd: Path | None = None) -> None:
    step_cwd = cwd or REPO_ROOT
    print(f"\n[{time.strftime('%H:%M:%S')}] ▶ {name}")
    print(f"  Command: {' '.join(str(c) for c in cmd)}")
    start = time.perf_counter()
    result = subprocess.run(cmd, cwd=step_cwd)
    duration = time.perf_counter() - start
    if result.returncode != 0:
        print(f"❌ FAILED: {name} (exit code {result.returncode}) after {duration:.2f}s")
        sys.exit(result.returncode)
    print(f"✔ Completed {name} in {duration:.2f}s")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Regenerate all generated data, cards, assets, and reports for Robot Battles."
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Skip high-resolution raster image export (CardImages/ PNGs and A4 PDF sheet).",
    )
    parser.add_argument(
        "--skip-simulation",
        action="store_true",
        help="Skip running the combat simulation report.",
    )
    args = parser.parse_args()

    total_start = time.perf_counter()
    print("=" * 80)
    print(" REGENERATING ALL ROBOT BATTLES DATA & ASSETS")
    print(f" Repository: {REPO_ROOT}")
    print(f" Mode: {'Quick (no rasterization)' if args.quick else 'Full (all assets & images)'}")
    print("=" * 80)

    # 1. Card pipeline
    if args.quick:
        # Icons + TeX cards only
        run_step(
            "Card Icons",
            [sys.executable, str(REPO_ROOT / "cardCreation" / "generate_icons.py")],
            cwd=REPO_ROOT / "cardCreation",
        )
        run_step(
            "Card TikZ Definitions & Manifest",
            [sys.executable, str(REPO_ROOT / "cardCreation" / "generateCards.py")],
            cwd=REPO_ROOT / "cardCreation",
        )
    else:
        run_step(
            "Card Creation Pipeline (Icons, TeX, PNGs, A4 Sheet)",
            [sys.executable, str(REPO_ROOT / "cardCreation" / "build_cards.py")],
            cwd=REPO_ROOT / "cardCreation",
        )

    # 2. Tabletop Simulator JSON
    run_step(
        "Tabletop Simulator JSON (json/cards.json)",
        [sys.executable, str(REPO_ROOT / "generate_card_json.py")],
        cwd=REPO_ROOT,
    )

    # 3. Chassis Sheets
    run_step(
        "A3 Chassis Sheets (chassisSheets/)",
        [sys.executable, str(REPO_ROOT / "scripts" / "generate_chassis_sheets.py")],
        cwd=REPO_ROOT,
    )

    # 4. Movement Templates
    run_step(
        "Movement Templates & Rulebook Graphic",
        [sys.executable, str(REPO_ROOT / "generate_movement_templates.py")],
        cwd=REPO_ROOT,
    )

    # 5. Combat Simulation
    if not args.skip_simulation:
        run_step(
            "Combat Simulation Report (scripts/output/)",
            [sys.executable, str(REPO_ROOT / "scripts" / "simulate_combat.py")],
            cwd=REPO_ROOT,
        )

    # 6. Print and Play Packages (A4 & A3)
    run_step(
        "Print and Play PDF Packages (build/robot_battles_pnp_*.pdf)",
        [sys.executable, str(REPO_ROOT / "scripts" / "generate_print_and_play.py")],
        cwd=REPO_ROOT,
    )

    total_duration = time.perf_counter() - total_start
    print("\n" + "=" * 80)
    print(f"✔ ALL DATA REGENERATION COMPLETE in {total_duration:.2f}s")
    print("=" * 80)


if __name__ == "__main__":
    main()
