"""Tests for design-theme sampling: per-product rotation and persistence.

The heavy pipeline steps (SEO, PDF, mockups) are stubbed so run_once() only
exercises research/selection, design sampling, and product creation.
"""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.pipeline.orchestrator import PipelineOrchestrator
from src.planner import DIMENSIONS, PRESET_PALETTES, PRESETS
from src.storage.database import Base
from src.storage.models import Product, ProductState
from src.storage.repository import NicheRepository

CONFIG = {
    "pipeline": {"max_products_per_day": 1000},
    "planner": {"year": 2026},
    "pricing": {"default_price_usd": 5.99, "book_price_usd": 4.99},
    "research": {"use_live_trends": False},
    "etsy": {"upload_enabled": False},
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def session_factory(tmp_path):
    """File-backed SQLite so every session sees the same data."""
    engine = create_engine(f"sqlite:///{tmp_path}/pipeline.db", echo=False)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


@pytest.fixture()
def orchestrator(session_factory, monkeypatch):
    """Orchestrator with the generation-heavy steps stubbed out."""
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
        "_step_generate_pdf",
        lambda self, product, niche_cfg, session: None,
    )
    monkeypatch.setattr(
        PipelineOrchestrator,
        "_step_generate_mockups",
        lambda self, product, session: [],
    )
    return PipelineOrchestrator(CONFIG, session_factory)


def _params(session_factory, product_id: int) -> dict:
    """Reload a product's params JSON through a fresh session."""
    session = session_factory()
    try:
        raw = session.get(Product, product_id).params
    finally:
        session.close()
    return json.loads(raw) if raw else {}


def _seed_planner_with_design(session, niche_id: int, design: str) -> None:
    session.add(
        Product(
            niche_id=niche_id,
            product_type="planner",
            title="t",
            palette_name="soft_sage",
            year=2026,
            params=json.dumps({"design": design}),
            state=ProductState.REVIEW_PENDING,
        )
    )


# ---------------------------------------------------------------------------
# Rotation: consecutive planner products get different themes
# ---------------------------------------------------------------------------


class TestDesignRotation:
    def test_two_consecutive_planner_products_get_different_themes(
        self, orchestrator, session_factory
    ):
        first = orchestrator.run_once(product_type="planner")
        second = orchestrator.run_once(product_type="planner")
        assert first is not None and second is not None

        design_a = _params(session_factory, first.id).get("design")
        design_b = _params(session_factory, second.id).get("design")
        assert design_a in PRESETS
        assert design_b in PRESETS
        assert design_a != design_b

    def test_no_theme_repeats_until_all_presets_are_used(
        self, orchestrator, session_factory
    ):
        seen = []
        for _ in range(len(PRESETS)):
            product = orchestrator.run_once(product_type="planner")
            assert product is not None
            seen.append(_params(session_factory, product.id).get("design"))
        assert len(seen) == len(set(seen)), f"theme repeated: {seen}"
        assert set(seen) == set(PRESETS)

    def test_exhausted_rotation_still_avoids_immediate_repeat(
        self, orchestrator, session_factory
    ):
        """When every preset was used recently, only the newest is excluded."""
        session = session_factory()
        try:
            niche = NicheRepository(session).create(
                name="Budget Planner", slug="budget_planner", seed_keywords=["b"]
            )
            for design in PRESETS:  # newest ends up being the last insert
                _seed_planner_with_design(session, niche.id, design)
            session.commit()
            newest = list(PRESETS)[-1]

            for _ in range(10):
                assert orchestrator._select_design(session) != newest
        finally:
            session.close()


# ---------------------------------------------------------------------------
# Persistence: reviewers can see the sampled theme
# ---------------------------------------------------------------------------


class TestDesignPersistence:
    def test_planner_params_persist_theme_and_dimensions(
        self, orchestrator, session_factory
    ):
        product = orchestrator.run_once(product_type="planner")
        assert product is not None

        params = _params(session_factory, product.id)
        assert params.get("design") in PRESETS
        for dim, allowed in DIMENSIONS.items():
            assert params.get(dim) in allowed, f"bad {dim}: {params.get(dim)}"

    def test_planner_palette_is_recommended_for_the_sampled_design(
        self, orchestrator, session_factory
    ):
        product = orchestrator.run_once(product_type="planner")
        assert product is not None

        design = _params(session_factory, product.id).get("design")
        session = session_factory()
        try:
            palette = session.get(Product, product.id).palette_name
        finally:
            session.close()
        assert palette in PRESET_PALETTES[design]

    def test_picture_book_params_carry_no_design(
        self, orchestrator, session_factory
    ):
        product = orchestrator.run_once(product_type="picture_book")
        assert product is not None
        assert "design" not in _params(session_factory, product.id)
