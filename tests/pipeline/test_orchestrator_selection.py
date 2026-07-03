"""Tests for niche selection: product_type filtering, seeding, fair rotation.

The heavy pipeline steps (SEO, PDF, mockups) are stubbed so run_once() only
exercises research/selection, product creation, and the state machine.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.pipeline.orchestrator import PipelineOrchestrator, _load_niches_config
from src.storage.database import Base
from src.storage.models import Niche, Product, ProductState
from src.storage.repository import NicheRepository

BOOK_SLUGS = {"kids_book_animals", "kids_book_fruits_veggies", "kids_book_bedtime"}

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


def _niche_slug(session_factory, niche_id: int) -> str:
    session = session_factory()
    try:
        return session.get(Niche, niche_id).slug
    finally:
        session.close()


# ---------------------------------------------------------------------------
# product_type restriction
# ---------------------------------------------------------------------------


class TestProductTypeRestriction:
    def test_picture_book_run_selects_a_book_niche(
        self, orchestrator, session_factory
    ):
        product = orchestrator.run_once(product_type="picture_book")
        assert product is not None
        assert product.product_type == "picture_book"
        assert product.state == ProductState.REVIEW_PENDING
        assert _niche_slug(session_factory, product.niche_id) in BOOK_SLUGS

    def test_planner_run_selects_a_planner_niche(self, orchestrator, session_factory):
        product = orchestrator.run_once(product_type="planner")
        assert product is not None
        assert product.product_type == "planner"
        assert _niche_slug(session_factory, product.niche_id) not in BOOK_SLUGS

    def test_invalid_product_type_raises(self, orchestrator):
        with pytest.raises(ValueError, match="Invalid product_type"):
            orchestrator.run_once(product_type="ebook")


# ---------------------------------------------------------------------------
# Niche seeding
# ---------------------------------------------------------------------------


class TestNicheSeeding:
    def test_every_configured_niche_is_seeded_by_a_run(
        self, orchestrator, session_factory
    ):
        """teacher_planner and all book niches must exist in the DB even
        when a run is restricted to one product type."""
        product = orchestrator.run_once(product_type="planner")
        assert product is not None

        session = session_factory()
        try:
            db_slugs = {niche.slug for niche in session.query(Niche).all()}
        finally:
            session.close()
        assert set(_load_niches_config().keys()) <= db_slugs


# ---------------------------------------------------------------------------
# Fair rotation
# ---------------------------------------------------------------------------


class TestRotation:
    def test_no_niche_repeats_while_ungenerated_niches_exist(
        self, orchestrator, session_factory
    ):
        all_slugs = set(_load_niches_config().keys())
        seen = []
        for _ in range(len(all_slugs)):
            product = orchestrator.run_once()
            assert product is not None
            seen.append(_niche_slug(session_factory, product.niche_id))
        assert len(seen) == len(set(seen)), f"niche repeated: {seen}"
        assert set(seen) == all_slugs

    def test_least_recently_generated_wins_when_all_have_products(
        self, orchestrator, session_factory
    ):
        niches_config = _load_niches_config()
        session = session_factory()
        try:
            orchestrator._seed_niches(niches_config, session)
            repo = NicheRepository(session)
            now = datetime(2026, 7, 1, 12, 0, 0)
            for slug in niches_config:
                created = now - (
                    timedelta(days=30) if slug == "teacher_planner" else timedelta(days=1)
                )
                niche = repo.get_by_slug(slug)
                session.add(
                    Product(
                        niche_id=niche.id,
                        title="t",
                        palette_name="soft_sage",
                        year=2026,
                        state=ProductState.REVIEW_PENDING,
                        created_at=created,
                    )
                )
            session.commit()

            assert (
                orchestrator._least_recently_generated(niches_config, session)
                == "teacher_planner"
            )
        finally:
            session.close()

    def test_never_generated_niche_beats_generated_ones(
        self, orchestrator, session_factory
    ):
        niches_config = _load_niches_config()
        session = session_factory()
        try:
            orchestrator._seed_niches(niches_config, session)
            repo = NicheRepository(session)
            for slug in niches_config:
                if slug == "kids_book_bedtime":
                    continue  # the only never-generated niche
                niche = repo.get_by_slug(slug)
                session.add(
                    Product(
                        niche_id=niche.id,
                        title="t",
                        palette_name="soft_sage",
                        year=2026,
                        state=ProductState.REVIEW_PENDING,
                        created_at=datetime(2020, 1, 1),
                    )
                )
            session.commit()

            assert (
                orchestrator._least_recently_generated(niches_config, session)
                == "kids_book_bedtime"
            )
        finally:
            session.close()
