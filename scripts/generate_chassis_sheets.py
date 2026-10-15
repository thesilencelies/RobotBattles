#!/usr/bin/env python3
"""
generate_chassis_sheets.py

Reads cardDefinitions/chassis.csv and generates standalone printable A3 landscape
sheets (SVG, HTML, PDF, and TTS PNG images) for each chassis template shape, complete
with light engineering grid, front heading indicator, and card-coherent stats plate.
Also renders automata PDF sheets to PNG images in tts_assets/.
"""

import argparse
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

from builder.server.chassis_sheets import export_all_chassis_sheets, render_pdf_to_png


def render_automata_sheets_to_tts(automata_dir: Path, tts_dir: Path, dpi: int = 150) -> list[Path]:
    """Renders all individual automata sheet PDFs to PNG images in tts_assets/."""
    tts_dir.mkdir(parents=True, exist_ok=True)
    rendered = []
    for pdf_path in sorted(automata_dir.glob("*_sheet.pdf")):
        # Skip multi-page combined pdf if named *_sheet.pdf (usually automata_sheets.pdf)
        if pdf_path.name == "automata_sheets.pdf":
            continue
        out_png = tts_dir / f"{pdf_path.stem}.png"
        print(f"  * Rendering automata PDF: {pdf_path.name} -> {out_png.name}...")
        render_pdf_to_png(pdf_path, out_png, dpi=dpi)
        rendered.append(out_png)
    return rendered


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate A3 Chassis Sheets and TTS Mats")
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=WORKSPACE / "chassisSheets",
        help="Destination directory for generated sheets",
    )
    parser.add_argument(
        "--tts-dir",
        type=Path,
        default=WORKSPACE / "tts_assets",
        help="Destination directory for TTS asset images (default: tts_assets)",
    )
    parser.add_argument(
        "--automata-dir",
        type=Path,
        default=WORKSPACE / "automata",
        help="Directory containing automata sheet PDFs (default: automata)",
    )
    parser.add_argument(
        "--skip-automata",
        action="store_true",
        help="Skip rendering automata PDFs to TTS images",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=150,
        help="Render DPI for PNG images (default: 150)",
    )
    args = parser.parse_args()

    out_dir = args.output_dir.resolve()
    tts_dir = args.tts_dir.resolve()
    automata_dir = args.automata_dir.resolve()

    print(f"Generating A3 chassis sheets into: {out_dir}")
    print(f"TTS image assets target: {tts_dir}")

    files = export_all_chassis_sheets(out_dir, tts_dir=tts_dir)
    for f in files:
        print(f"  + {f.name}")

    if not args.skip_automata and automata_dir.is_dir():
        print(f"\nRendering automata sheets from {automata_dir} into {tts_dir}...")
        automata_pngs = render_automata_sheets_to_tts(automata_dir, tts_dir, dpi=args.dpi)
        files.extend(automata_pngs)

    print(f"\nDone. Generated/updated {len(files)} files.")


if __name__ == "__main__":
    main()

