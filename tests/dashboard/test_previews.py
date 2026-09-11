"""Preview cache must follow the PDF it was rendered from.

Regression for the Sep-2026 #16 re-rejection: the product was regenerated in
place on 7/24 but the dashboard kept serving previews rendered on 7/10, so the
reviewer re-rejected fixes that had already shipped.
"""

from __future__ import annotations

import os
import time

import fitz

from src.dashboard.app import ensure_previews


def _write_pdf(path, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    page.insert_text((40, 100), text, fontsize=40)
    doc.save(str(path))
    doc.close()


def test_previews_rerender_when_pdf_is_newer(tmp_path):
    pdf = tmp_path / "planner.pdf"
    previews = tmp_path / "previews"
    _write_pdf(pdf, "OLD")
    pages = ensure_previews(7, pdf, previews)
    png = previews / "product_7" / "page_1.png"
    assert pages == [1] and png.is_file()
    stale_bytes = png.read_bytes()

    # Regenerate the PDF in place; age the cached preview so it is strictly
    # older than the new PDF (what a 7/10 cache vs a 7/24 regen looks like).
    _write_pdf(pdf, "NEW")
    older = pdf.stat().st_mtime - 5
    os.utime(png, (older, older))

    ensure_previews(7, pdf, previews)
    assert png.read_bytes() != stale_bytes
    assert png.stat().st_mtime >= pdf.stat().st_mtime


def test_previews_are_reused_when_pdf_is_unchanged(tmp_path):
    pdf = tmp_path / "planner.pdf"
    previews = tmp_path / "previews"
    _write_pdf(pdf, "SAME")
    ensure_previews(3, pdf, previews)
    png = previews / "product_3" / "page_1.png"
    first_mtime = png.stat().st_mtime
    time.sleep(0.01)
    ensure_previews(3, pdf, previews)
    assert png.stat().st_mtime == first_mtime
