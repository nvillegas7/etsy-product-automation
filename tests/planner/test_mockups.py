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
    def test_five_images_written(self, planner_pdf, tmp_path):
        paths = generate_listing_images(
            planner_pdf,
            tmp_path,
            product_id=7,
            title="2026 Budget Planner",
            product_type="planner",
            palette_name="classic_boho",
        )
        assert len(paths) == 5
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
        assert len(paths) == 5

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
