"""SQLite + SQLAlchemy engine setup."""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def get_engine(database_url: str | None = None):
    global _engine
    if _engine is None:
        if database_url is None:
            db_path = os.getenv("DATABASE_URL", "sqlite:///data/planner.db")
            if not db_path.startswith("sqlite"):
                db_path = f"sqlite:///{db_path}"
            database_url = db_path

        # Ensure directory exists
        if database_url.startswith("sqlite:///"):
            db_file = database_url.replace("sqlite:///", "")
            Path(db_file).parent.mkdir(parents=True, exist_ok=True)

        _engine = create_engine(database_url, echo=False)
    return _engine


def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        engine = get_engine(database_url)
        _SessionLocal = sessionmaker(bind=engine)
    return _SessionLocal


def init_db(database_url: str | None = None):
    """Create all tables and apply lightweight column migrations."""
    from src.storage.models import (  # noqa: F401 - import to register models
        EtsyListing,
        EtsyToken,
        Niche,
        PipelineRun,
        Product,
        TrendCache,
    )

    engine = get_engine(database_url)
    Base.metadata.create_all(engine)
    _migrate_schema(engine)
    return engine


# Columns added after the initial release. create_all() never alters existing
# tables, so pre-existing databases get them via ALTER TABLE here.
_PRODUCT_COLUMN_MIGRATIONS = {
    "product_type": "ALTER TABLE products ADD COLUMN product_type VARCHAR(30) NOT NULL DEFAULT 'planner'",
    "display_title": "ALTER TABLE products ADD COLUMN display_title VARCHAR(200)",
    "params": "ALTER TABLE products ADD COLUMN params TEXT",
    "review_note": "ALTER TABLE products ADD COLUMN review_note TEXT",
    "reviewed_at": "ALTER TABLE products ADD COLUMN reviewed_at DATETIME",
    "palettes": "ALTER TABLE products ADD COLUMN palettes TEXT",
    "bundle_path": "ALTER TABLE products ADD COLUMN bundle_path VARCHAR(500)",
}


def _migrate_schema(engine) -> None:
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "products" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("products")}
    with engine.begin() as conn:
        for column, ddl in _PRODUCT_COLUMN_MIGRATIONS.items():
            if column not in existing:
                conn.execute(text(ddl))


def reset_engine():
    """Reset the global engine (for testing)."""
    global _engine, _SessionLocal
    if _engine:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
