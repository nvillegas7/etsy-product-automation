"""ORM models for the planner pipeline."""

import enum
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.storage.database import Base


class ProductState(enum.Enum):
    RESEARCH_PENDING = "research_pending"
    RESEARCH_COMPLETE = "research_complete"
    GENERATION_PENDING = "generation_pending"
    GENERATION_COMPLETE = "generation_complete"
    REVIEW_PENDING = "review_pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    UPLOAD_PENDING = "upload_pending"
    PUBLISHED = "published"
    FAILED = "failed"


class Niche(Base):
    __tablename__ = "niches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    seed_keywords: Mapped[str] = mapped_column(Text, nullable=False)  # JSON list
    trend_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_scored_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    niche_id: Mapped[int] = mapped_column(Integer, nullable=False)
    product_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="planner", server_default="planner"
    )
    title: Mapped[str] = mapped_column(String(140), nullable=False)
    display_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    palette_name: Mapped[str] = mapped_column(String(50), nullable=False)  # HERO palette
    # JSON list of palette names bundled in this planner product (hero first).
    # NULL for picture books, which stay single-palette.
    palettes: Mapped[str | None] = mapped_column(Text, nullable=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    params: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON dict
    pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)  # HERO palette PDF
    # Path to the multi-palette delivery ZIP (planner bundles only; NULL otherwise).
    bundle_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    mockup_path: Mapped[str | None] = mapped_column(String(500), nullable=True)  # path or JSON list
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    state: Mapped[ProductState] = mapped_column(
        Enum(ProductState), default=ProductState.RESEARCH_PENDING
    )
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_usd: Mapped[float] = mapped_column(Float, default=5.99)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class EtsyListing(Base):
    __tablename__ = "etsy_listings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, nullable=False)
    listing_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Etsy's ID
    shop_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    etsy_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class EtsyToken(Base):
    __tablename__ = "etsy_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_type: Mapped[str] = mapped_column(String(20), default="Bearer")
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TrendCache(Base):
    __tablename__ = "trend_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword: Mapped[str] = mapped_column(String(200), nullable=False)
    region: Mapped[str] = mapped_column(String(10), default="US")
    trend_data: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    phase: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ReviewEvent(Base):
    """Append-only log of every human review decision.

    Unlike ``Product.review_note`` (a single latest value that is overwritten
    each review), this keeps the full history — every approve/reject/re-review
    with its reason category, free-text comment, and a snapshot of the
    product's attributes at decision time. Rejection comments accumulate here
    so the generation workflow can later be tuned from real reviewer feedback.
    """

    __tablename__ = "review_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    product_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    decision: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # approved | rejected | re_review
    reason: Mapped[str | None] = mapped_column(String(40), nullable=True)  # category
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    params_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
