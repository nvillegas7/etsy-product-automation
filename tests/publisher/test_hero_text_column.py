"""Hero listing image: the left text block stays inside its column.

The fixed-size subtitle ("Hyperlinked · iPad & Tablet Ready", 898 px; the
book line 949 px) ran past the 780 px column into the tilted cover.
"""

from __future__ import annotations

import fitz
import pytest
from fpdf import FPDF
from PIL import ImageDraw

from src.marketing import mockups

TX, MAX_W = 170, 780


@pytest.fixture(scope="module")
def doc(tmp_path_factory):
    out = tmp_path_factory.mktemp("hero") / "cover.pdf"
    pdf = FPDF(unit="mm", format=(297, 210))
    pdf.add_page()
    pdf.output(str(out))
    opened = fitz.open(str(out))
    yield opened
    opened.close()


@pytest.mark.parametrize("product_type,title", [
    ("planner", "2026-2027 Teacher Planner"),
    ("planner", "2026 ADHD Planner"),
    ("picture_book", "Octavia the Octopus Learns to Be Kind"),
])
def test_left_text_fits_its_column(doc, monkeypatch, product_type, title):
    drawn = []
    original = ImageDraw.ImageDraw.text

    def record(self, xy, text, *args, **kwargs):
        if xy[0] == TX:
            drawn.append((text, self.textbbox(xy, text, font=kwargs.get("font"))))
        return original(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", record)
    mockups._compose_hero(doc, dict(mockups._FALLBACK_PALETTE), title,
                          product_type, design_label="Noir")
    assert len(drawn) >= 3      # kicker, title line(s), subtitle
    for text, box in drawn:
        assert box[2] <= TX + MAX_W, f"{text!r} ends at {box[2]} px"
