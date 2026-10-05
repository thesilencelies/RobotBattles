# Card Creation Pipeline

A data-driven pipeline for generating combat robotics game cards from CSV specifications into LaTeX (`.tex`) files, standalone high-resolution card images, and printable A4 grid sheets.

Modelled after the card generation pipeline in `mobileSuitGame`.

---

## Architecture Overview

```
cardDefinitions/*.csv
        │
        ▼
generate_icons.py ──> pictures/icons/*.png (temporary icon set)
        │
        ▼
generateCards.py  ──> build/card_macros.tex (TikZ macros, colors, fonts)
                  ──> build/card/<Name>.tex  (per-card TikZ definitions)
                  ──> build/all_cards.csv
        │
        ├─────────────────────────────────────────┐
        ▼                                         ▼
generate_card_images.py                  generate_card_sheet.py
        │                                         │
        ▼                                         ▼
CardImages/<Name>.png                    build/print_sheet_a4.pdf
(standalone PNG cards)                   (printable A4 card sheets)
```

---

## Quick Start

Run the entire pipeline (generate icons, compile TeX cards, export PNG images, and generate printable A4 PDF):

```bash
python cardCreation/build_cards.py
```

Or run individual steps:

```bash
# 1. Regenerate icons only
python cardCreation/generate_icons.py

# 2. Regenerate .tex card definitions from cardDefinitions/*.csv
python cardCreation/generateCards.py

# 3. Export standalone PNG preview images into CardImages/
python cardCreation/generate_card_images.py --all

# 4. Generate A4 printable sheet
python cardCreation/generate_card_sheet.py --csv cardCreation/build/all_cards.csv --output cardCreation/build/print_sheet_a4.tex --a4 --cols 4 --rows 2
cd cardCreation/build && pdflatex print_sheet_a4.tex
```

---

## Script Reference

### `generate_icons.py`
Procedurally generates clean, transparent PNG icons into `pictures/icons/`:
- **Resources**:
  - `energy.png`: Cyan lightning bolt (Resource `E`)
  - `control.png`: Red joystick transmitter (Resource `C`)
  - `spin.png`: Orange spiral (Resource `S`)
  - `drive.png`: Drive wheel/tread (Resource `M`)
  - `damage.png`: Red/orange blast/impact burst (Resource `W`)
- **Card Stats**:
  - `weight.png`: Kettlebell with "1T" mark
  - `durability.png`: Red box with white fracture line
  - `absorption.png`: Black angled armor shield
- **Templates**:
  - `template_circle.png`: Red circle with black center dot (`Circle`)
  - `template_line.png`: Single red line (`Line`)
  - `template_bar.png`: Wide block with horizontal front line (`Bar`)
  - `template_prongs.png`: Wide bar with two forward prongs (`Prongs`)

### `generateCards.py`
Reads `cardDefinitions/components.csv` and `cardDefinitions/weapons.csv` (and any additional CSV files in `cardDefinitions/`), matches component artwork from `components/`, and writes:
- `build/card_macros.tex`: Shared colors, fonts, graphicspaths, and icon macros.
- `build/card/<Name>.tex`: Individual card TikZ document matching the `pictures/exampleCards/` layout.
- `build/all_cards.csv`: Manifest of generated `.tex` files.

### `generate_card_sheet.py`
Lays out card `.tex` files into a grid:
- Supports `--a4` mode for centered layout on standard A4 landscape paper.
- Configurable `--cols`, `--rows`, `--bleed`.

### `generate_card_images.py`
Compiles each card on its own page and rasterizes individual cards to high-resolution PNGs in `CardImages/`.

### `build_cards.py`
Master orchestration runner that executes the entire pipeline end-to-end.
