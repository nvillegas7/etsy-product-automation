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

    def fake_render(self, product, niche_cfg, palette_name=None):
        palette = palette_name or product.palette_name
        path = pdf_dir / f"product_{product.id}_{palette}.pdf"
        path.write_bytes(f"PDF for {palette}".encode())
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
