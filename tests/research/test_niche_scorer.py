"""Tests for NicheScorer selection: score dominance + generation rotation."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.research.niche_scorer import NicheScorer
from src.storage.database import Base
from src.storage.models import Product, ProductState
from src.storage.repository import NicheRepository


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class FakeTrendsClient:
    """Returns a fixed interest value per keyword; flat trend direction."""

    def __init__(self, interest_by_keyword: dict[str, float]):
        self.interest_by_keyword = interest_by_keyword

    def get_interest(self, keyword: str) -> dict:
        return {"values": [self.interest_by_keyword.get(keyword, 0.0)]}

    def calculate_trend_direction(self, data: dict) -> float:
        return 0.0


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    sess = Session(engine)
    yield sess
    sess.close()
    engine.dispose()


def _niches_config(slugs: list[str]) -> dict:
    return {
        slug: {"name": slug.replace("_", " ").title(), "seed_keywords": [slug]}
        for slug in slugs
    }


def _seed_niches(session, config: dict) -> dict[str, int]:
    repo = NicheRepository(session)
    return {
        slug: repo.create(name=cfg["name"], slug=slug, seed_keywords=[slug]).id
        for slug, cfg in config.items()
    }


def _add_product(session, niche_id: int, created_at: datetime) -> None:
    session.add(
        Product(
            niche_id=niche_id,
            title="t",
            palette_name="soft_sage",
            year=2026,
            state=ProductState.REVIEW_PENDING,
            created_at=created_at,
        )
    )
    session.commit()


def _scorer(session, interest: dict[str, float]) -> NicheScorer:
    return NicheScorer(trends_client=FakeTrendsClient(interest), session=session)


class TestSelectBest:
    def test_higher_score_dominates(self, session):
        config = _niches_config(["low_niche", "high_niche"])
        _seed_niches(session, config)
        scorer = _scorer(session, {"low_niche": 20.0, "high_niche": 90.0})

        assert scorer.select_best(config) == "high_niche"

    def test_tie_prefers_never_generated(self, session):
        config = _niches_config(["niche_a", "niche_b"])
        ids = _seed_niches(session, config)
        # niche_a was generated yesterday; niche_b never.
        _add_product(session, ids["niche_a"], _utcnow_naive() - timedelta(days=1))
        scorer = _scorer(session, {"niche_a": 50.0, "niche_b": 50.0})

        assert scorer.select_best(config) == "niche_b"

    def test_tie_prefers_least_recently_generated(self, session):
        config = _niches_config(["fresh_niche", "stale_niche"])
        ids = _seed_niches(session, config)
        _add_product(session, ids["fresh_niche"], _utcnow_naive() - timedelta(days=10))
        _add_product(session, ids["stale_niche"], _utcnow_naive() - timedelta(days=30))
        scorer = _scorer(session, {"fresh_niche": 50.0, "stale_niche": 50.0})

        assert scorer.select_best(config) == "stale_niche"

    def test_all_recent_falls_back_to_least_recently_generated(self, session):
        config = _niches_config(["niche_a", "niche_b"])
        ids = _seed_niches(session, config)
        _add_product(session, ids["niche_a"], _utcnow_naive() - timedelta(days=2))
        _add_product(session, ids["niche_b"], _utcnow_naive() - timedelta(days=1))
        scorer = _scorer(session, {"niche_a": 50.0, "niche_b": 50.0})

        assert scorer.select_best(config, avoid_recent_days=7) == "niche_a"

    def test_zero_scores_rotate_through_ungenerated(self, session):
        """With live trends effectively flat (all zeros), selection must not
        stick to dict order — the generated niche goes to the back."""
        config = _niches_config(["first_niche", "second_niche", "third_niche"])
        ids = _seed_niches(session, config)
        _add_product(session, ids["first_niche"], _utcnow_naive())
        scorer = _scorer(session, {})

        assert scorer.select_best(config) == "second_niche"

    def test_recently_generated_top_scorer_is_skipped(self, session):
        """avoid_recent_days keys off generation time, not publish time."""
        config = _niches_config(["hot_niche", "cool_niche"])
        ids = _seed_niches(session, config)
        _add_product(session, ids["hot_niche"], _utcnow_naive() - timedelta(days=1))
        _add_product(session, ids["cool_niche"], _utcnow_naive() - timedelta(days=30))
        scorer = _scorer(session, {"hot_niche": 90.0, "cool_niche": 20.0})

        assert scorer.select_best(config, avoid_recent_days=7) == "cool_niche"
