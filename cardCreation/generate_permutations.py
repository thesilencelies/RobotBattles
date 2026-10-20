#!/usr/bin/env python3
"""
generate_permutations.py

Generates card layouts for all 12 permutations of the 4 layout alterations:
  1. Weight: multiple with 1T (default) vs multiple without 1T vs single number on top
  2. Cost: multiple $ signs (default) vs single $ with number
  3. Resources: count of icons (default) vs number writing out math

Outputs:
  cardCreation/build/permutations/<perm_id>/
    card/*.tex
    all_cards.csv
    Four-Bar_Lifter.png
    Brushless_Motor.png
    Wires.png
  cardCreation/build/permutations/
    Four-Bar_Lifter_comparison.png
    Brushless_Motor_comparison.png
    Wires_comparison.png
    comparison.html
"""

import argparse
import csv
import os
import shutil
import subprocess
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent
BUILD_DIR = SCRIPT_DIR / "build"
PERMUTATIONS_DIR = BUILD_DIR / "permutations"

PERMUTATIONS = [
    {
        "id": "p01_baseline",
        "name": "Baseline (Default)",
        "weight_mode": "multiple",
        "cost_number": False,
        "resource_math": False,
        "weight_desc": "Multiple with 1T",
        "cost_desc": "Multiple $$",
        "res_desc": "Icon count",
    },
    {
        "id": "p02_res_math",
        "name": "Resource Math",
        "weight_mode": "multiple",
        "cost_number": False,
        "resource_math": True,
        "weight_desc": "Multiple with 1T",
        "cost_desc": "Multiple $$",
        "res_desc": "Number & math",
    },
    {
        "id": "p03_cost_num",
        "name": "Cost Number",
        "weight_mode": "multiple",
        "cost_number": True,
        "resource_math": False,
        "weight_desc": "Multiple with 1T",
        "cost_desc": "Number ($X)",
        "res_desc": "Icon count",
    },
    {
        "id": "p04_cost_num_res_math",
        "name": "Cost Number + Resource Math",
        "weight_mode": "multiple",
        "cost_number": True,
        "resource_math": True,
        "weight_desc": "Multiple with 1T",
        "cost_desc": "Number ($X)",
        "res_desc": "Number & math",
    },
    {
        "id": "p05_no_1t",
        "name": "No 1T on Weight",
        "weight_mode": "multiple_no_1t",
        "cost_number": False,
        "resource_math": False,
        "weight_desc": "Multiple no 1T",
        "cost_desc": "Multiple $$",
        "res_desc": "Icon count",
    },
    {
        "id": "p06_no_1t_res_math",
        "name": "No 1T + Resource Math",
        "weight_mode": "multiple_no_1t",
        "cost_number": False,
        "resource_math": True,
        "weight_desc": "Multiple no 1T",
        "cost_desc": "Multiple $$",
        "res_desc": "Number & math",
    },
    {
        "id": "p07_no_1t_cost_num",
        "name": "No 1T + Cost Number",
        "weight_mode": "multiple_no_1t",
        "cost_number": True,
        "resource_math": False,
        "weight_desc": "Multiple no 1T",
        "cost_desc": "Number ($X)",
        "res_desc": "Icon count",
    },
    {
        "id": "p08_no_1t_cost_num_res_math",
        "name": "No 1T + Cost Number + Resource Math",
        "weight_mode": "multiple_no_1t",
        "cost_number": True,
        "resource_math": True,
        "weight_desc": "Multiple no 1T",
        "cost_desc": "Number ($X)",
        "res_desc": "Number & math",
    },
    {
        "id": "p09_weight_num",
        "name": "Weight Number",
        "weight_mode": "number",
        "cost_number": False,
        "resource_math": False,
        "weight_desc": "Single # on logo",
        "cost_desc": "Multiple $$",
        "res_desc": "Icon count",
    },
    {
        "id": "p10_weight_num_res_math",
        "name": "Weight Number + Resource Math",
        "weight_mode": "number",
        "cost_number": False,
        "resource_math": True,
        "weight_desc": "Single # on logo",
        "cost_desc": "Multiple $$",
        "res_desc": "Number & math",
    },
    {
        "id": "p11_weight_num_cost_num",
        "name": "Weight Number + Cost Number",
        "weight_mode": "number",
        "cost_number": True,
        "resource_math": False,
        "weight_desc": "Single # on logo",
        "cost_desc": "Number ($X)",
        "res_desc": "Icon count",
    },
    {
        "id": "p12_all_features",
        "name": "All Features Combined",
        "weight_mode": "number",
        "cost_number": True,
        "resource_math": True,
        "weight_desc": "Single # on logo",
        "cost_desc": "Number ($X)",
        "res_desc": "Number & math",
    },
]

TARGET_CARDS = ["Four-Bar_Lifter", "Brushless_Motor", "Wires"]


def run(cmd, cwd=None, label=""):
    display = label or " ".join(str(c) for c in cmd)
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout[-2000:])
        if result.stderr:
            print(result.stderr[-2000:])
        sys.exit(f"FAILED: {display}")
    return result.stdout


def generate_single_permutation(perm: dict, target_cards: list[str], density: int = 200):
    perm_id = perm["id"]
    perm_dir = PERMUTATIONS_DIR / perm_id
    card_dir = perm_dir / "card"
    card_dir.mkdir(parents=True, exist_ok=True)

    # 1. Generate card TikZ files
    gen_cmd = [
        sys.executable,
        str(SCRIPT_DIR / "generateCards.py"),
        f"--output-dir={card_dir}",
        f"--weight-mode={perm['weight_mode']}",
        f"--manifest-csv={perm_dir / 'all_cards.csv'}",
    ]
    if perm["cost_number"]:
        gen_cmd.append("--cost-number")
    if perm["resource_math"]:
        gen_cmd.append("--resource-math")

    run(gen_cmd, cwd=SCRIPT_DIR, label=f"generateCards for {perm_id}")

    # Copy card_macros.tex into perm_dir so pdflatex finds it
    shutil.copy2(BUILD_DIR / "card_macros.tex", perm_dir / "card_macros.tex")

    # 2. Compile targeted sample cards
    target_csv = perm_dir / "sample_cards.csv"
    with open(target_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for card_stem in target_cards:
            writer.writerow([f"card/{card_stem}.tex"])

    sample_sheet_tex = perm_dir / "sample_cards_sheet.tex"
    run(
        [
            sys.executable,
            str(SCRIPT_DIR / "generate_card_sheet.py"),
            f"--csv={target_csv}",
            f"--output={sample_sheet_tex}",
            "--cols=1",
            "--rows=1",
        ],
        cwd=SCRIPT_DIR,
        label=f"generate_card_sheet for {perm_id}",
    )

    run(
        ["pdflatex", "-interaction=nonstopmode", "sample_cards_sheet.tex"],
        cwd=perm_dir,
        label=f"pdflatex sample_cards_sheet for {perm_id}",
    )

    # 3. Rasterize cards
    sample_pdf = perm_dir / "sample_cards_sheet.pdf"
    img_prefix = perm_dir / "card_page"
    run(
        ["pdftoppm", "-png", "-r", str(density), str(sample_pdf), str(img_prefix)],
        cwd=perm_dir,
        label=f"pdftoppm for {perm_id}",
    )

    for i, card_stem in enumerate(target_cards, start=1):
        src_png = perm_dir / f"card_page-{i}.png"
        dst_png = perm_dir / f"{card_stem}.png"
        if src_png.exists():
            shutil.move(src_png, dst_png)


def create_comparison_grid(card_stem: str, permutations: list[dict], output_path: Path):
    """Stitches all 12 permutation card images into a 4x3 comparison grid image."""
    cols = 4
    rows = 3
    card_images = []
    for p in permutations:
        img_path = PERMUTATIONS_DIR / p["id"] / f"{card_stem}.png"
        if img_path.exists():
            card_images.append((p, Image.open(img_path)))
        else:
            print(f"Warning: {img_path} not found.")

    if not card_images:
        return

    first_im = card_images[0][1]
    cw, ch = first_im.size

    # Scale down card for manageable grid size
    scale = 0.5
    thumb_w = int(cw * scale)
    thumb_h = int(ch * scale)

    banner_h = 75
    cell_w = thumb_w + 30
    cell_h = thumb_h + banner_h + 30

    grid_w = cols * cell_w + 40
    grid_h = rows * cell_h + 90

    grid_im = Image.new("RGBA", (grid_w, grid_h), (245, 247, 250, 255))
    draw = ImageDraw.Draw(grid_im)

    # Header
    bold_font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    reg_font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if Path(bold_font_path).exists():
        font_title = ImageFont.truetype(bold_font_path, 28)
        font_badge = ImageFont.truetype(bold_font_path, 15)
        font_desc = ImageFont.truetype(reg_font_path, 13)
    else:
        font_title = font_badge = font_desc = ImageFont.load_default()

    display_name = card_stem.replace("_", " ")
    draw.text((30, 25), f"Layout Permutations Comparison: {display_name}", fill=(20, 25, 40, 255), font=font_title)

    for idx, (p, im) in enumerate(card_images):
        r = idx // cols
        c = idx % cols

        x = 30 + c * cell_w
        y = 80 + r * cell_h

        # Cell background card
        draw.rounded_rectangle((x, y, x + cell_w - 15, y + cell_h - 15), radius=8, fill=(255, 255, 255, 255), outline=(215, 220, 230, 255), width=2)

        # Permutation title
        draw.text((x + 12, y + 10), f"{p['id'].split('_')[0].upper()}: {p['name']}", fill=(30, 40, 80, 255), font=font_badge)
        desc_line = f"W: {p['weight_desc']}  |  $: {p['cost_desc']}  |  Res: {p['res_desc']}"
        draw.text((x + 12, y + 32), desc_line, fill=(100, 110, 130, 255), font=font_desc)

        # Card image
        thumb = im.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        img_x = x + (cell_w - 15 - thumb_w) // 2
        img_y = y + banner_h
        grid_im.paste(thumb, (img_x, img_y), thumb if thumb.mode == "RGBA" else None)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    grid_im.save(output_path, "PNG")
    print(f"Generated comparison grid: {output_path}")


def create_html_viewer(permutations: list[dict], target_cards: list[str], output_path: Path):
    card_tabs = "".join(
        f'<button class="tab-btn {"active" if i == 0 else ""}" onclick="showCard(\'{c}\')">{c.replace("_", " ")}</button>'
        for i, c in enumerate(target_cards)
    )

    card_sections = []
    for i, c in enumerate(target_cards):
        style = "display: block;" if i == 0 else "display: none;"
        cards_html = []
        for p in permutations:
            rel_img = f"{p['id']}/{c}.png"
            badge_class = "badge-baseline" if p["id"] == "p01_baseline" else ("badge-all" if p["id"] == "p12_all_features" else "badge-perm")
            cards_html.append(f"""
            <div class="card-item">
              <div class="card-header">
                <span class="badge {badge_class}">{p['id'].split('_')[0].upper()}</span>
                <strong>{p['name']}</strong>
              </div>
              <div class="card-meta">
                <div><span>Weight:</span> {p['weight_desc']}</div>
                <div><span>Cost:</span> {p['cost_desc']}</div>
                <div><span>Resources:</span> {p['res_desc']}</div>
              </div>
              <div class="card-image-box">
                <img src="{rel_img}" alt="{c} ({p['name']})" loading="lazy">
              </div>
            </div>
            """)
        cards_grid = "\n".join(cards_html)
        card_sections.append(f"""
        <div id="section-{c}" class="card-section" style="{style}">
          <h2>{c.replace('_', ' ')}</h2>
          <div class="grid">{cards_grid}</div>
        </div>
        """)

    full_sections = "\n".join(card_sections)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Robot Battles Card Layout Permutations</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: #0f172a;
    color: #e2e8f0;
    margin: 0;
    padding: 24px;
  }}
  h1 {{ margin: 0 0 8px 0; font-size: 26px; color: #f8fafc; }}
  p.subtitle {{ color: #94a3b8; margin-top: 0; margin-bottom: 20px; }}
  .tabs {{ display: flex; gap: 8px; margin-bottom: 24px; border-bottom: 1px solid #334155; padding-bottom: 12px; }}
  .tab-btn {{
    background: #1e293b;
    color: #94a3b8;
    border: 1px solid #334155;
    padding: 10px 20px;
    border-radius: 8px;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
  }}
  .tab-btn.active {{
    background: #3b82f6;
    color: white;
    border-color: #3b82f6;
  }}
  .tab-btn:hover:not(.active) {{
    background: #334155;
    color: #f8fafc;
  }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 20px;
  }}
  .card-item {{
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 16px;
    display: flex;
    flex-direction: column;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
  }}
  .card-header {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
    font-size: 15px;
    color: #f1f5f9;
  }}
  .badge {{
    font-size: 11px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 4px;
  }}
  .badge-baseline {{ background: #059669; color: white; }}
  .badge-all {{ background: #8b5cf6; color: white; }}
  .badge-perm {{ background: #475569; color: white; }}
  .card-meta {{
    font-size: 12px;
    color: #94a3b8;
    margin-bottom: 12px;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }}
  .card-meta span {{ color: #cbd5e1; font-weight: 600; }}
  .card-image-box {{
    background: #0b1120;
    border-radius: 8px;
    padding: 10px;
    display: flex;
    justify-content: center;
    align-items: center;
  }}
  .card-image-box img {{
    max-width: 100%;
    height: auto;
    border-radius: 6px;
    box-shadow: 0 4px 8px rgba(0,0,0,0.5);
  }}
</style>
<script>
function showCard(cardName) {{
  document.querySelectorAll('.card-section').forEach(el => el.style.display = 'none');
  document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
  document.getElementById('section-' + cardName).style.display = 'block';
  event.target.classList.add('active');
}}
</script>
</head>
<body>
  <h1>Robot Battles - Alternative Card Layout Permutations</h1>
  <p class="subtitle">Comparing 12 permutations of weight, cost, and resource alterations across representative cards.</p>
  <div class="tabs">
    {card_tabs}
  </div>
  {full_sections}
</body>
</html>
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Generated HTML comparison: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate and compare all 12 card layout permutations.")
    parser.add_argument("--density", type=int, default=200, help="Render DPI (default: 200)")
    parser.add_argument("--cards", nargs="+", default=TARGET_CARDS, help="Card stem names to render")
    args = parser.parse_args()

    PERMUTATIONS_DIR.mkdir(parents=True, exist_ok=True)

    print("=== Generating 12 Card Layout Permutations ===")
    for perm in PERMUTATIONS:
        print(f"\n--- Permutation: {perm['id']} ({perm['name']}) ---")
        generate_single_permutation(perm, args.cards, density=args.density)

    print("\n=== Generating Comparison Grids ===")
    for card_stem in args.cards:
        grid_out = PERMUTATIONS_DIR / f"{card_stem}_comparison.png"
        create_comparison_grid(card_stem, PERMUTATIONS, grid_out)

    html_out = PERMUTATIONS_DIR / "comparison.html"
    create_html_viewer(PERMUTATIONS, args.cards, html_out)

    print("\n=== All Permutations Generated Successfully ===")


if __name__ == "__main__":
    main()
