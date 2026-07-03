"""Palette-bundle listing images: swatch strip + colour-options image.

A multi-palette planner must sell the colour choice (swatch strip on the
hero + a dedicated colour-options image); single-palette planners and
picture books stay byte-for-byte unchanged.
"""

from __future__ import annotations

import pytest
from fpdf import FPDF
from PIL import Image

from src.marketing.mockups import CANVAS_H, CANVAS_W, generate_listing_images


@pytest.fixture(scope="module")
def planner_pdf(tmp_path_factory):
    """A small multi-page landscape PDF standing in for a planner."""
    out = tmp_path_factory.mktemp("bundle_pdf") / "planner.pdf"
    pdf = FPDF(unit="mm", format=(297, 210))
    for i in range(14):
        pdf.add_page()
        pdf.set_fill_color(235, 225, 214)
        pdf.rect(0, 0, 297, 210, style="F")
        pdf.set_font("Helvetica", "B", 30)
        pdf.set_xy(0, 95)
        pdf.cell(297, 20, f"Page {i + 1}", align="C")
    pdf.output(str(out))
    return out


def _render(pdf, out_dir, product_id, **kwargs):
    return generate_listing_images(
        pdf,
        out_dir,
        product_id=product_id,
        title="2026 Budget Planner",
        product_type=kwargs.pop("product_type", "planner"),
        palette_name="ocean_blue",
        **kwargs,
    )


class TestBundleMockups:
    def test_bundle_adds_color_options_image(self, planner_pdf, tmp_path):
        paths = _render(
            planner_pdf,
            tmp_path,
            product_id=1,
            palettes=["ocean_blue", "soft_sage", "dusty_rose"],
        )
        assert len(paths) == 5
        for i, p in enumerate(paths):
            assert p.name == f"product_1_mockup_{i}.png"
            with Image.open(p) as img:
                assert img.size == (CANVAS_W, CANVAS_H)

    def test_bundle_hero_and_second_image_differ_from_single(
        self, planner_pdf, tmp_path
    ):
        single = _render(planner_pdf, tmp_path / "single", product_id=2)
        bundle = _render(
            planner_pdf,
            tmp_path / "bundle",
            product_id=2,
            palettes=["ocean_blue", "soft_sage", "dusty_rose", "classic_boho"],
        )
        # Hero gains a swatch strip -> the pixels change.
        assert single[0].read_bytes() != bundle[0].read_bytes()
        # Image #1 is interiors for a single palette but the colour-options
        # image for a bundle.
        assert single[1].read_bytes() != bundle[1].read_bytes()

    def test_single_palette_unchanged(self, planner_pdf, tmp_path):
        """One palette (or a duplicate list) is not a bundle: no new image."""
        none_paths = _render(planner_pdf, tmp_path / "none", product_id=3)
        one_paths = _render(
            planner_pdf, tmp_path / "one", product_id=3, palettes=["ocean_blue"]
        )
        dup_paths = _render(
            planner_pdf,
            tmp_path / "dup",
            product_id=3,
            palettes=["ocean_blue", "ocean_blue"],
        )
        assert len(none_paths) == len(one_paths) == len(dup_paths) == 5
        for a, b in zip(none_paths, one_paths):
            assert a.read_bytes() == b.read_bytes()
        for a, b in zip(none_paths, dup_paths):
            assert a.read_bytes() == b.read_bytes()

    def test_picture_book_ignores_palettes(self, tmp_path):
        """Books never pass a bundle; passing None keeps the classic set."""
        book = tmp_path / "book.pdf"
        pdf = FPDF(unit="mm", format=(210, 210))
        for i in range(6):
            pdf.add_page()
            pdf.set_fill_color(240, 220, 200)
            pdf.rect(0, 0, 210, 210, style="F")
            pdf.set_font("Helvetica", "B", 30)
            pdf.set_xy(0, 90)
            pdf.cell(210, 20, f"Page {i + 1}", align="C")
        pdf.output(str(book))

        paths = generate_listing_images(
            book,
            tmp_path / "mockups",
            product_id=4,
            title="Luna the Brave Little Fox",
            product_type="picture_book",
        )
        assert len(paths) == 5
