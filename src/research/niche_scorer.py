"""Niche ranking and selection based on Google Trends data."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import func, select

from src.storage.models import Niche, Product
from src.storage.repository import NicheRepository

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.research.trends import TrendsClient

logger = structlog.get_logger()


def _utcnow() -> datetime:
    """Naive UTC now — matches the naive UTC timestamps SQLite stores."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

# Bonus multiplier applied when the average trend direction is positive
_RISING_BONUS_WEIGHT: float = 0.25

# Penalty multiplier applied when the niche was recently published
_RECENCY_PENALTY: float = 0.5


class NicheScorer:
    """Score and rank niches using live (or cached) Google Trends data.

    Parameters
    ----------
    trends_client : TrendsClient
        Client used to fetch / cache trend interest data.
    session : sqlalchemy.orm.Session
        Database session for niche CRUD via ``NicheRepository``.
    """

    def __init__(self, trends_client: "TrendsClient", session: "Session"):
        self._trends = trends_client
        self._session = session
        self._niche_repo = NicheRepository(session)

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def score_niche(self, niche_config: dict) -> float:
        """Compute a composite trend score for a single niche.

        Algorithm
        ---------
        1. Fetch trend interest for every seed keyword.
        2. Compute the **mean interest** (average of per-keyword mean values).
        3. Compute the **mean trend direction** across keywords.
        4. Apply a *rising bonus* if the mean direction is positive:
           ``score *= (1 + direction * RISING_BONUS_WEIGHT / 100)``
        5. Apply a *recency penalty* if the niche was published recently:
           ``score *= (1 - RECENCY_PENALTY)``
        """
        seed_keywords: list[str] = niche_config.get("seed_keywords", [])
        slug: str = _niche_slug(niche_config)

        if not seed_keywords:
            logger.warning("niche_no_keywords", niche=slug)
            return 0.0

        interests: list[float] = []
        directions: list[float] = []

        for kw in seed_keywords:
            try:
                data = self._trends.get_interest(kw)
            except Exception as exc:
                logger.warning(
                    "niche_trend_error", niche=slug, keyword=kw, error=str(exc)
                )
                continue

            values = data.get("values", [])
            if values:
                interests.append(sum(values) / len(values))
                directions.append(self._trends.calculate_trend_direction(data))

        if not interests:
            logger.warning("niche_no_interest_data", niche=slug)
            return 0.0

        avg_interest = sum(interests) / len(interests)
        avg_direction = sum(directions) / len(directions)

        score = avg_interest

        # Rising bonus
        if avg_direction > 0:
            score *= 1.0 + (avg_direction * _RISING_BONUS_WEIGHT / 100.0)

        # Recency penalty
        niche_record = self._niche_repo.get_by_slug(slug)
        if niche_record and niche_record.last_published_at:
            days_since = (_utcnow() - niche_record.last_published_at).days
            if days_since < 7:
                score *= 1.0 - _RECENCY_PENALTY
                logger.info(
                    "niche_recency_penalty",
                    niche=slug,
                    days_since_publish=days_since,
                )

        score = round(max(score, 0.0), 2)
        logger.info("niche_scored", niche=slug, score=score, direction=avg_direction)
        return score

    # ------------------------------------------------------------------
    # Ranking
    # ------------------------------------------------------------------

    def rank_niches(self, niches_config: dict) -> list[tuple[str, float]]:
        """Score every niche in *niches_config* and return a sorted ranking.

        Parameters
        ----------
        niches_config : dict
            The top-level ``niches`` mapping from ``niches.yaml``, e.g.
            ``{"adhd_planner": {...}, "budget_planner": {...}, ...}``.

        Returns
        -------
        list of (slug, score) tuples sorted **descending** by score.

        Side-effects
        ------------
        Each niche score is persisted to the database via
        ``NicheRepository.update_score()``.
        """
        rankings: list[tuple[str, float]] = []

        for slug, niche_cfg in niches_config.items():
            score = self.score_niche(niche_cfg)

            # Persist the score
            niche_record = self._niche_repo.get_by_slug(slug)
            if niche_record:
                self._niche_repo.update_score(niche_record.id, score)
            else:
                logger.debug(
                    "niche_not_in_db",
                    niche=slug,
                    hint="Run init_db and seed niches first.",
                )

            rankings.append((slug, score))

        rankings.sort(key=lambda t: t[1], reverse=True)
        logger.info("niches_ranked", rankings=rankings)
        return rankings

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def select_best(
        self,
        niches_config: dict,
        avoid_recent_days: int = 7,
    ) -> str:
        """Return the slug of the best niche to generate next.

        Candidates are ordered by trend score (descending); ties are broken
        by *generation* recency — the least-recently-generated niche wins,
        with never-generated niches first. Generation recency is
        ``max(products.created_at)`` per niche (any state), **not**
        ``niches.last_published_at``: products parked in review never update
        the publish timestamp, which used to starve every niche but the
        first one picked.

        Parameters
        ----------
        niches_config : dict
            The ``niches`` mapping from ``niches.yaml``.
        avoid_recent_days : int
            Skip niches that had a product generated within this many days
            (default 7), unless every candidate is that fresh.

        Returns
        -------
        str
            The chosen niche slug.  Falls back to the least-recently-generated
            top-scoring niche if every niche was recently generated.
        """
        rankings = self.rank_niches(niches_config)
        last_generated = self._last_generated_map()

        def _order(item: tuple[str, float]) -> tuple:
            slug, score = item
            last = last_generated.get(slug)
            # Score dominates; never-generated beats generated; older first.
            return (-score, last is not None, last or datetime.min)

        ordered = sorted(rankings, key=_order)
        cutoff = _utcnow() - timedelta(days=avoid_recent_days)

        for slug, _score in ordered:
            last = last_generated.get(slug)
            if last is None:
                logger.info("niche_selected", niche=slug, reason="never_generated")
                return slug
            if last < cutoff:
                logger.info(
                    "niche_selected",
                    niche=slug,
                    reason="not_recently_generated",
                    last_generated=last.isoformat(),
                )
                return slug

        # Fallback: every niche was recently generated -- take the
        # least-recently-generated among the top scorers.
        best_slug = ordered[0][0] if ordered else list(niches_config.keys())[0]
        logger.warning(
            "niche_fallback_selection",
            niche=best_slug,
            reason="all_recently_generated",
        )
        return best_slug

    def _last_generated_map(self) -> dict[str, datetime | None]:
        """Map niche slug -> most recent products.created_at (None = never)."""
        rows = self._session.execute(
            select(Niche.slug, func.max(Product.created_at))
            .outerjoin(Product, Product.niche_id == Niche.id)
            .group_by(Niche.id)
        ).all()
        return dict(rows)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _niche_slug(niche_config: dict) -> str:
    """Derive a slug from a niche config dict.

    Tries ``slug`` key first, then lowercases + underscores ``name``.
    """
    if "slug" in niche_config:
        return niche_config["slug"]
    name = niche_config.get("name", "unknown")
    return name.lower().replace(" ", "_")
