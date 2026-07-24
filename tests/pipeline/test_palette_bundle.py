"""Integration tests for the curated palette bundle in the planner branch.

The low-level per-palette PDF render (_generate_planner_pdf) is stubbed to
write a tiny dummy file so _step_generate_pdf runs for real and exercises the
bundling/zip logic without the slow PDF pipeline. SEO, mockups, and keyword
research are stubbed as the other pipeline tests do.
"""

import json
import zipfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.pipeline.orchestrator import PipelineOrchestrator
from src.planner import PRESET_PALETTES
from src.storage.database import Base
from src.storage.models import Product, ProductState


def _make_config(tmp_path, palette_bundle=True):
    return {
        "pipeline": {"max_products_per_day": 1000},
        "planner": {"year": 2026, "palette_bundle": palette_bundle},
        "pricing": {"default_price_usd": 5.99, "book_price_usd": 4.99},
        "research": {"use_live_trends": False},
        "etsy": {"upload_enabled": False},
        "paths": {"bundle_dir": str(tmp_path / "bundles")},
    }


@pytest.fixture()
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/pipeline.db", echo=False)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


def _stub_heavy_steps(monkeypatch, tmp_path):
    """Stub research/SEO/mockups and make PDF render write a real dummy file."""
    monkeypatch.setattr(
        PipelineOrchestrator,
        "_do_keyword_research",
        lambda self, niche_cfg, session: (["kw"], [("kw", 0.0)]),
    )
    monkeypatch.setattr(
        PipelineOrchestrator,
        "_step_seo",
        lambda self, product, niche_cfg, scored_keywords, session: None,
    )
    monkeypatch.setattr(
        PipelineOrchestrator,
        "_step_generate_mockups",
        lambda self, product, session: [],
    )

    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir(exist_ok=True)

    def fake_render(self, product, niche_cfg, palette_name=None, date_mode="dated"):
        palette = palette_name or product.palette_name
        suffix = "" if date_mode == "dated" else f"_{date_mode}"
        path = pdf_dir / f"product_{product.id}_{palette}{suffix}.pdf"
        path.write_bytes(f"PDF for {palette} {date_mode}".encode())
        return path

    monkeypatch.setattr(
        PipelineOrchestrator, "_generate_planner_pdf", fake_render
    )


def _reload(session_factory, product_id):
    session = session_factory()
    try:
        p = session.get(Product, product_id)
        session.expunge(p)
        return p
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Bundle mode (default)
# ---------------------------------------------------------------------------


class TestPaletteBundle:
    def test_planner_run_produces_bundle_of_3_to_4_palettes(
        self, session_factory, tmp_path, monkeypatch
    ):
        _stub_heavy_steps(monkeypatch, tmp_path)
        orch = PipelineOrchestrator(_make_config(tmp_path), session_factory)
        product = orch.run_once(product_type="planner")
        assert product is not None
        assert product.state == ProductState.REVIEW_PENDING

        p = _reload(session_factory, product.id)
        palettes = json.loads(p.palettes)
        assert 3 <= len(palettes) <= 4
        assert len(palettes) == len(set(palettes))  # de-duped

    def test_hero_pdf_is_first_palette(
        self, session_factory, tmp_path, monkeypatch
    ):
        _stub_heavy_steps(monkeypatch, tmp_path)
        orch = PipelineOrchestrator(_make_config(tmp_path), session_factory)
        product = orch.run_once(product_type="planner")

        p = _reload(session_factory, product.id)
        palettes = json.loads(p.palettes)
        hero = palettes[0]
        assert p.palette_name == hero
        assert p.pdf_path.endswith(f"_{hero}.pdf")
        assert p.file_size_bytes and p.file_size_bytes > 0

    def test_bundle_zip_exists_and_contains_all_palette_pdfs(
        self, session_factory, tmp_path, monkeypatch
    ):
        _stub_heavy_steps(monkeypatch, tmp_path)
        orch = PipelineOrchestrator(_make_config(tmp_path), session_factory)
        product = orch.run_once(product_type="planner")

        p = _reload(session_factory, product.id)
        palettes = json.loads(p.palettes)
        assert p.bundle_path is not None

        from pathlib import Path

        zpath = Path(p.bundle_path)
        assert zpath.exists()
        with zipfile.ZipFile(zpath) as zf:
            names = zf.namelist()
        assert len(names) == len(palettes)
        for palette in palettes:
            assert any(name.endswith(f"_{palette}.pdf") for name in names)
        # arcnames are clean (no absolute paths)
        assert all(not n.startswith("/") for n in names)

    def test_params_carry_palette_list(
        self, session_factory, tmp_path, monkeypatch
    ):
        _stub_heavy_steps(monkeypatch, tmp_path)
        orch = PipelineOrchestrator(_make_config(tmp_path), session_factory)
        product = orch.run_once(product_type="planner")

        p = _reload(session_factory, product.id)
        params = json.loads(p.params)
        assert params["palettes"] == json.loads(p.palettes)

    def test_hero_is_recommended_for_the_design(
        self, session_factory, tmp_path, monkeypatch
    ):
        _stub_heavy_steps(monkeypatch, tmp_path)
        orch = PipelineOrchestrator(_make_config(tmp_path), session_factory)
        product = orch.run_once(product_type="planner")

        p = _reload(session_factory, product.id)
        design = json.loads(p.params)["design"]
        assert p.palette_name in PRESET_PALETTES[design]


# ---------------------------------------------------------------------------
# Single-palette fallback
# ---------------------------------------------------------------------------


class TestSinglePaletteFallback:
    def test_no_bundle_when_disabled(
        self, session_factory, tmp_path, monkeypatch
    ):
        _stub_heavy_steps(monkeypatch, tmp_path)
        config = _make_config(tmp_path, palette_bundle=False)
        orch = PipelineOrchestrator(config, session_factory)
        product = orch.run_once(product_type="planner")
        assert product is not None

        p = _reload(session_factory, product.id)
        palettes = json.loads(p.palettes)
        assert len(palettes) == 1
        assert palettes[0] == p.palette_name
        assert p.bundle_path is None
        assert p.pdf_path.endswith(f"_{p.palette_name}.pdf")


# ---------------------------------------------------------------------------
# P2: date-mode trio (academic teacher/student)
# ---------------------------------------------------------------------------


class TestDateTrio:
    def test_builds_matrix_is_hero_x3_plus_others_x2(self, session_factory, tmp_path):
        orch = PipelineOrchestrator(_make_config(tmp_path), session_factory)
        palettes = ["hero", "b", "c"]
        assert orch._planner_builds({"date_trio": True}, palettes) == [
            ("hero", "dated"), ("hero", "dated_next"), ("hero", "undated"),
            ("b", "dated_next"), ("b", "undated"),
            ("c", "dated_next"), ("c", "undated"),
        ]

    def test_non_trio_is_one_dated_pdf_per_palette(self, session_factory, tmp_path):
        orch = PipelineOrchestrator(_make_config(tmp_path), session_factory)
        assert orch._planner_builds({}, ["hero", "b"]) == [
            ("hero", "dated"), ("b", "dated")
        ]

    def test_trio_niche_zips_all_date_versions(
        self, session_factory, tmp_path, monkeypatch
    ):
        from pathlib import Path

        _stub_heavy_steps(monkeypatch, tmp_path)
        config = _make_config(tmp_path)
        config["planner"]["priority_niches"] = ["teacher_planner"]  # force trio niche
        orch = PipelineOrchestrator(config, session_factory)
        product = orch.run_once(product_type="planner")

        p = _reload(session_factory, product.id)
        palettes = json.loads(p.palettes)
        with zipfile.ZipFile(Path(p.bundle_path)) as zf:
            names = zf.namelist()

        # hero x3 date modes + each other colorway x2.
        assert len(names) == 3 + 2 * (len(palettes) - 1)
        assert any("2026-2027" in n for n in names)   # this school year
        assert any("2027-2028" in n for n in names)   # next school year
        assert any("undated" in n for n in names)
        # Hero preview PDF is the dated (2026-2027) build.
        assert p.pdf_path is not None

    def test_trio_delivered_even_when_palette_bundle_disabled(
        self, session_factory, tmp_path, monkeypatch
    ):
        from pathlib import Path

        _stub_heavy_steps(monkeypatch, tmp_path)
        config = _make_config(tmp_path, palette_bundle=False)
        config["planner"]["priority_niches"] = ["teacher_planner"]
        orch = PipelineOrchestrator(config, session_factory)
        product = orch.run_once(product_type="planner")

        p = _reload(session_factory, product.id)
        # Single palette, but 3 date modes -> the trio must still be zipped,
        # not silently dropped to just the hero PDF.
        assert p.bundle_path is not None
        with zipfile.ZipFile(Path(p.bundle_path)) as zf:
            names = zf.namelist()
        assert len(names) == 3
        assert any("2026-2027" in n for n in names)
        assert any("undated" in n for n in names)


# ---------------------------------------------------------------------------
# P13 (in-zip half): digital stickers ride in the planner zip
# ---------------------------------------------------------------------------


class TestDigitalStickers:
    def _stub_sticker_generator(self, monkeypatch, tmp_path):
        """Fake generate_sticker_assets: tiny files, real return shape."""
        from src.marketing.stickers import StickerAssets

        def fake_assets(palette, out_dir, **kwargs):
            from pathlib import Path

            out = Path(out_dir)
            out.mkdir(parents=True, exist_ok=True)
            sheet = out / f"Digital_Stickers_{palette}.pdf"
            sheet.write_bytes(b"sheet")
            pngs = []
            for i in range(2):
                p = out / palette
                p.mkdir(exist_ok=True)
                png = p / f"{i:02d}_icon.png"
                png.write_bytes(b"png")
                pngs.append(png)
            return StickerAssets(palette=palette, sheet_pdf=sheet,
                                 png_paths=pngs)

        import src.pipeline.orchestrator as orch_mod
        monkeypatch.setattr(orch_mod, "_import_stickers", lambda: fake_assets)

    def test_stickers_added_to_bundle_zip_when_enabled(
        self, session_factory, tmp_path, monkeypatch
    ):
        from pathlib import Path

        _stub_heavy_steps(monkeypatch, tmp_path)
        self._stub_sticker_generator(monkeypatch, tmp_path)
        config = _make_config(tmp_path)
        config["planner"]["digital_stickers"] = True
        config["paths"]["sticker_dir"] = str(tmp_path / "stickers")
        orch = PipelineOrchestrator(config, session_factory)
        product = orch.run_once(product_type="planner")

        p = _reload(session_factory, product.id)
        palettes = json.loads(p.palettes)
        with zipfile.ZipFile(Path(p.bundle_path)) as zf:
            names = zf.namelist()

        # One sheet PDF + 2 stubbed PNGs per palette, PNGs foldered.
        sheets = [n for n in names if n.startswith("Digital_Stickers_")]
        pngs = [n for n in names if n.startswith("Stickers_")]
        assert len(sheets) == len(palettes)
        assert len(pngs) == 2 * len(palettes)
        assert all("/" in n for n in pngs)  # foldered per colorway

    def test_stickers_off_by_default(self, session_factory, tmp_path, monkeypatch):
        from pathlib import Path

        _stub_heavy_steps(monkeypatch, tmp_path)
        orch = PipelineOrchestrator(_make_config(tmp_path), session_factory)
        product = orch.run_once(product_type="planner")
        p = _reload(session_factory, product.id)
        with zipfile.ZipFile(Path(p.bundle_path)) as zf:
            assert not any("Sticker" in n for n in zf.namelist())
