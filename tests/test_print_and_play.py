"""Unit tests for Print and Play (PnP) PDF generation and upload tooling."""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def get_pdf_page_count(pdf_path: Path) -> int:
    out = subprocess.check_output(["pdfinfo", str(pdf_path)], text=True)
    for line in out.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise ValueError(f"Could not find page count in pdfinfo for {pdf_path}")


def test_pnp_generation_and_page_sizes():
    """Verify that generate_print_and_play.py creates valid A4 (10 pages) and A3 (8 pages) PDFs."""
    gen_script = REPO_ROOT / "scripts" / "generate_print_and_play.py"
    res = subprocess.run([sys.executable, str(gen_script)], cwd=REPO_ROOT, capture_output=True, text=True)
    assert res.returncode == 0, f"Generator failed with: {res.stderr}"

    a4_pdf = REPO_ROOT / "build" / "robot_battles_pnp_a4.pdf"
    a3_pdf = REPO_ROOT / "build" / "robot_battles_pnp_a3.pdf"
    assert a4_pdf.is_file(), "A4 PnP PDF not found"
    assert a3_pdf.is_file(), "A3 PnP PDF not found"

    # Check A4 PDF: 10 pages, 841.89 x 595.276 pts
    assert get_pdf_page_count(a4_pdf) == 10
    out_a4 = subprocess.check_output(["pdfinfo", "-f", "1", "-l", "10", str(a4_pdf)], text=True)
    for line in out_a4.splitlines():
        if line.strip().startswith("Page") and "size:" in line:
            assert "841.89" in line and "595.276" in line, f"Unexpected page size: {line}"

    # Check A3 PDF: 8 pages, 1190.55 x 841.89 pts
    assert get_pdf_page_count(a3_pdf) == 8
    out_a3 = subprocess.check_output(["pdfinfo", "-f", "1", "-l", "8", str(a3_pdf)], text=True)
    for line in out_a3.splitlines():
        if line.strip().startswith("Page") and "size:" in line:
            assert "1190.55" in line and "841.89" in line, f"Unexpected page size: {line}"


def test_upload_pnp_dry_run():
    """Verify that upload_pnp.py executes cleanly in dry-run mode."""
    upload_script = REPO_ROOT / "upload_pnp.py"
    res = subprocess.run([sys.executable, str(upload_script), "--dry-run", "--force"], cwd=REPO_ROOT, capture_output=True, text=True)
    assert res.returncode == 0, f"Dry run failed: {res.stderr}"
    assert "[dry run] Would upload" in res.stdout
    assert "robot_battles_pnp_a4.pdf" in res.stdout
    assert "robot_battles_pnp_a3.pdf" in res.stdout
