"""CRUD operations for all models."""

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.storage.models import (
    EtsyListing,
    EtsyToken,
    Niche,
    PipelineRun,
    Product,
    ProductState,
    TrendCache,
)


class NicheRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, name: str, slug: str, seed_keywords: list[str]) -> Niche:
        niche = Niche(
            name=name, slug=slug, seed_keywords=json.dumps(seed_keywords)
        )
        self.session.add(niche)
        self.session.commit()
        return niche

    def get_by_slug(self, slug: str) -> Niche | None:
        return self.session.execute(
            select(Niche).where(Niche.slug == slug)
        ).scalar_one_or_none()

    def get_all(self) -> list[Niche]:
        return list(self.session.execute(select(Niche)).scalars().all())

    def get_best_unpublished(self, days: int = 7) -> Niche | None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return self.session.execute(
            select(Niche)
            .where(
                (Niche.last_published_at.is_(None))
                | (Niche.last_published_at < cutoff)
            )
            .order_by(Niche.trend_score.desc().nullslast())
        ).scalars().first()

    def update_score(self, niche_id: int, score: float):
        niche = self.session.get(Niche, niche_id)
        if niche:
            niche.trend_score = score
            niche.last_scored_at = datetime.now(timezone.utc)
            self.session.commit()

    def mark_published(self, niche_id: int):
        niche = self.session.get(Niche, niche_id)
        if niche:
            niche.last_published_at = datetime.now(timezone.utc)
            self.session.commit()


class ProductRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, **kwargs) -> Product:
        product = Product(**kwargs)
        self.session.add(product)
        self.session.commit()
        return product

    def get(self, product_id: int) -> Product | None:
        return self.session.get(Product, product_id)

    def update_state(self, product_id: int, state: ProductState, error: str | None = None):
        """Set a product's state, enforcing state-machine transition rules.

        Re-asserting the current state is an idempotent no-op (still updates
        ``error_message``); any other change must be a legal transition per
        ``ProductStateMachine`` or a ValueError is raised.
        """
        # Imported lazily: src.pipeline.state imports this module at import
        # time, so a top-level import here would be circular.
        from src.pipeline.state import ProductStateMachine

        product = self.session.get(Product, product_id)
        if product:
            if product.state != state and not ProductStateMachine.can_transition(
                product.state, state
            ):
                raise ValueError(
                    f"Invalid state transition for product {product_id}: "
                    f"{product.state.value} -> {state.value}"
                )
            product.state = state
            product.error_message = error
            self.session.commit()

    def update(self, product_id: int, **kwargs):
        product = self.session.get(Product, product_id)
        if product:
            for key, value in kwargs.items():
                setattr(product, key, value)
            self.session.commit()

    def set_bundle(
        self,
        product_id: int,
        palettes: list[str] | str | None,
        bundle_path: str | None = None,
    ):
        """Persist the palette bundle metadata on a planner product.

        ``palettes`` may be a list (JSON-encoded here) or a pre-serialized
        string. ``bundle_path`` is only written when provided so callers can
        set the palette list before the zip exists.
        """
        product = self.session.get(Product, product_id)
        if product:
            if isinstance(palettes, list):
                product.palettes = json.dumps(palettes)
            elif palettes is not None:
                product.palettes = palettes
            if bundle_path is not None:
                product.bundle_path = str(bundle_path)
            self.session.commit()

    def get_by_state(self, state: ProductState) -> list[Product]:
        return list(
            self.session.execute(
                select(Product).where(Product.state == state)
            ).scalars().all()
        )

    def list_products(
        self,
        state: ProductState | None = None,
        product_type: str | None = None,
        limit: int | None = None,
    ) -> list[Product]:
        """Newest-first product listing with optional state/type filters."""
        query = select(Product).order_by(Product.created_at.desc(), Product.id.desc())
        if state is not None:
            query = query.where(Product.state == state)
        if product_type is not None:
            query = query.where(Product.product_type == product_type)
        if limit is not None:
            query = query.limit(limit)
        return list(self.session.execute(query).scalars().all())


class EtsyListingRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, product_id: int, **kwargs) -> EtsyListing:
        listing = EtsyListing(product_id=product_id, **kwargs)
        self.session.add(listing)
        self.session.commit()
        return listing

    def update(self, listing_id: int, **kwargs):
        listing = self.session.get(EtsyListing, listing_id)
        if listing:
            for key, value in kwargs.items():
                setattr(listing, key, value)
            self.session.commit()

    def get_by_product(self, product_id: int) -> EtsyListing | None:
        return self.session.execute(
            select(EtsyListing).where(EtsyListing.product_id == product_id)
        ).scalar_one_or_none()


class EtsyTokenRepository:
    def __init__(self, session: Session):
        self.session = session

    def save_token(
        self,
        access_token: str,
        refresh_token: str,
        expires_in: int,
        token_type: str = "Bearer",
    ) -> EtsyToken:
        token = EtsyToken(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type=token_type,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        )
        self.session.add(token)
        self.session.commit()
        return token

    def get_latest(self) -> EtsyToken | None:
        return self.session.execute(
            select(EtsyToken).order_by(EtsyToken.created_at.desc())
        ).scalars().first()

    def is_expired(self, token: EtsyToken) -> bool:
        expires_at = token.expires_at
        if expires_at.tzinfo is None:
            # SQLite stores naive datetimes; stored values are UTC.
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= expires_at


class TrendCacheRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_cached(self, keyword: str, ttl_hours: int = 24) -> dict | None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)
        entry = self.session.execute(
            select(TrendCache)
            .where(TrendCache.keyword == keyword, TrendCache.fetched_at > cutoff)
            .order_by(TrendCache.fetched_at.desc())
        ).scalars().first()
        if entry:
            return json.loads(entry.trend_data)
        return None

    def save(self, keyword: str, trend_data: dict, score: float | None = None):
        entry = TrendCache(
            keyword=keyword,
            trend_data=json.dumps(trend_data),
            score=score,
        )
        self.session.add(entry)
        self.session.commit()
        return entry


class PipelineRunRepository:
    def __init__(self, session: Session):
        self.session = session

    def start_run(self, product_id: int | None = None) -> PipelineRun:
        run = PipelineRun(product_id=product_id)
        self.session.add(run)
        self.session.commit()
        return run

    def complete_run(self, run_id: int, status: str = "completed", error: str | None = None):
        run = self.session.get(PipelineRun, run_id)
        if run:
            run.completed_at = datetime.now(timezone.utc)
            run.status = status
            run.error_message = error
            self.session.commit()

    def update_phase(self, run_id: int, phase: str):
        run = self.session.get(PipelineRun, run_id)
        if run:
            run.phase = phase
            self.session.commit()

    def get_recent(self, limit: int = 10) -> list[PipelineRun]:
        return list(
            self.session.execute(
                select(PipelineRun)
                .order_by(PipelineRun.started_at.desc())
                .limit(limit)
            ).scalars().all()
        )
