"""Smoke tests for the marketing mockup composer."""

from __future__ import annotations

import fitz
import pytest
from PIL import Image

from src.marketing.mockups import CANVAS_H, CANVAS_W, generate_listing_images
from src.planner.generator import PlannerGenerator, PlannerSpec


@pytest.fixture(scope="module")
def planner_pdf(tmp_path_factory):
    """Generate one small planner PDF shared by the mockup tests."""
    import src.planner.generator as gen_mod

    out_dir = tmp_path_factory.mktemp("planner_out")
    original = gen_mod.OUTPUT_DIR
    gen_mod.OUTPUT_DIR = out_dir
    try:
        spec = PlannerSpec(
            title="2026 Budget Planner",
            display_title="2026 Budget Planner",
            palette_name="classic_boho",
            include_weekly=False,
            include_daily=False,
            niche_slug="budget_planner",
        )
        path = PlannerGenerator().generate(spec)
    finally:
        gen_mod.OUTPUT_DIR = original
    return path


class TestGenerateListingImages:
    def test_planner_has_seven_images_incl_navmap_filmstrip(self, planner_pdf, tmp_path):
        # Single-palette planner: hero + navmap + filmstrip + 4 = 7 (P3).
        paths = generate_listing_images(
            planner_pdf,
            tmp_path,
            product_id=7,
            title="2026 Budget Planner",
            product_type="planner",
            palette_name="classic_boho",
        )
        assert len(paths) == 7
        for i, p in enumerate(paths):
            assert p.name == f"product_7_mockup_{i}.png"
            assert p.exists()
            with Image.open(p) as img:
                assert img.size == (CANVAS_W, CANVAS_H)

    def test_max_images_respected(self, planner_pdf, tmp_path):
        paths = generate_listing_images(
            planner_pdf,
            tmp_path,
            product_id=8,
            title="2026 Budget Planner",
            max_images=2,
        )
        assert len(paths) == 2

    def test_unknown_palette_falls_back(self, planner_pdf, tmp_path):
        paths = generate_listing_images(
            planner_pdf,
            tmp_path,
            product_id=9,
            title="2026 Budget Planner",
            palette_name="not_a_real_palette",
        )
        assert len(paths) == 7

    def test_picture_book_square_pages(self, tmp_path):
        """Works with square pages and mentions coloring pages."""
        from fpdf import FPDF

        pdf = FPDF(unit="mm", format=(210, 210))
        for i in range(6):
            pdf.add_page()
            pdf.set_fill_color(240, 220, 200)
            pdf.rect(0, 0, 210, 210, style="F")
            pdf.set_font("Helvetica", "B", 30)
            pdf.set_xy(0, 90)
            pdf.cell(210, 20, f"Page {i + 1}", align="C")
        book_path = tmp_path / "book.pdf"
        pdf.output(str(book_path))

        paths = generate_listing_images(
            book_path,
            tmp_path / "mockups",
            product_id=10,
            title="Luna the Brave Little Fox",
            product_type="picture_book",
        )
        assert len(paths) == 5
        for p in paths:
            with Image.open(p) as img:
                assert img.size == (CANVAS_W, CANVAS_H)


class TestHyperlinkMockups:
    def test_count_hyperlinks_is_real_and_nonzero(self, planner_pdf):
        from src.marketing.mockups import _count_hyperlinks

        doc = fitz.open(str(planner_pdf))
        try:
            # A generated planner embeds hundreds of GOTO links (tabs, index...).
            assert _count_hyperlinks(doc) > 100
        finally:
            doc.close()

    def test_count_hyperlinks_zero_on_plain_pdf(self, tmp_path):
        from fpdf import FPDF

        from src.marketing.mockups import _count_hyperlinks

        pdf = FPDF()
        pdf.add_page()
        plain = tmp_path / "plain.pdf"
        pdf.output(str(plain))
        doc = fitz.open(str(plain))
        try:
            assert _count_hyperlinks(doc) == 0
        finally:
            doc.close()

    def test_navmap_and_filmstrip_render(self, planner_pdf):
        from src.marketing.mockups import (
            _compose_filmstrip,
            _compose_navmap,
            _palette_colors,
        )

        doc = fitz.open(str(planner_pdf))
        try:
            pal = _palette_colors("classic_boho")
            navmap = _compose_navmap(doc, pal, 2400)
            filmstrip = _compose_filmstrip(doc, pal)
        finally:
            doc.close()
        assert navmap.size == (CANVAS_W, CANVAS_H)
        assert filmstrip.size == (CANVAS_W, CANVAS_H)
        assert navmap.mode == "RGB"

    def test_picture_book_skips_hyperlink_mockups(self, tmp_path):
        # Books have no link graph -> no navmap/filmstrip, stays at 5.
        from fpdf import FPDF

        pdf = FPDF(unit="mm", format=(210, 210))
        for _ in range(6):
            pdf.add_page()
        book = tmp_path / "b.pdf"
        pdf.output(str(book))
        paths = generate_listing_images(
            book, tmp_path / "mk", product_id=11, title="Book",
            product_type="picture_book",
        )
        assert len(paths) == 5
