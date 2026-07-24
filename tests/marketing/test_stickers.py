"""Digital sticker assets: per-palette sheet PDF + pre-cropped alpha PNGs."""

from __future__ import annotations

import fitz
import pytest
from PIL import Image

from src.marketing.stickers import (
    STICKERS_PER_PALETTE,
    generate_sticker_assets,
    sticker_count_for,
)


class TestCounts:
    def test_per_palette_count_meets_p13_floor(self):
        # P13 spec: 40-50+ elements per palette.
        assert STICKERS_PER_PALETTE >= 40

    def test_bundle_count_math(self):
        assert sticker_count_for(4) == 4 * STICKERS_PER_PALETTE
        assert sticker_count_for(0) == 0


class TestGeneration:
    @pytest.fixture(scope="class")
    def assets(self, tmp_path_factory):
        out = tmp_path_factory.mktemp("stickers")
        return generate_sticker_assets("classic_boho", out)

    def test_sheet_pdf_written(self, assets):
        assert assets.sheet_pdf.name == "Digital_Stickers_classic_boho.pdf"
        doc = fitz.open(str(assets.sheet_pdf))
        try:
            assert len(doc) >= 1
        finally:
            doc.close()

    def test_one_png_per_element(self, assets):
        assert assets.count == STICKERS_PER_PALETTE
        assert len(assets.png_paths) == len({p.name for p in assets.png_paths})

    def test_pngs_are_precropped_with_alpha(self, assets):
        # An icon sticker: RGBA with real transparent surround + opaque strokes.
        with Image.open(assets.png_paths[0]) as img:
            assert img.mode == "RGBA"
            alphas = img.getchannel("A")
            lo, hi = alphas.getextrema()
            assert lo == 0, "no transparent pixels -- not pre-cropped"
            assert hi > 200, "no opaque pixels -- element missing"

    def test_weekday_chips_present(self, assets):
        names = {p.name.split("_", 1)[1] for p in assets.png_paths}
        assert "chip_monday.png" in names
        assert "chip_to_do.png" in names

    def test_unknown_palette_raises(self, tmp_path):
        with pytest.raises(KeyError):
            generate_sticker_assets("no_such_palette", tmp_path)
