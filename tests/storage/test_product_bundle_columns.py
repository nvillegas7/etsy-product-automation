"""Tests for the palette-bundle Product columns, migration, and setter."""

import json

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from src.storage.database import Base, _migrate_schema
from src.storage.models import Niche, Product, ProductState
from src.storage.repository import ProductRepository


def _factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/db.sqlite", echo=False)
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine)


class TestSchema:
    def test_new_columns_present(self, tmp_path):
        engine, _ = _factory(tmp_path)
        cols = {c["name"] for c in inspect(engine).get_columns("products")}
        assert "palettes" in cols
        assert "bundle_path" in cols
        engine.dispose()

    def test_migration_adds_columns_to_legacy_table(self, tmp_path):
        """A pre-bundle products table gains the columns via _migrate_schema."""
        engine = create_engine(f"sqlite:///{tmp_path}/legacy.db", echo=False)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE products ("
                    "id INTEGER PRIMARY KEY, niche_id INTEGER, title TEXT, "
                    "palette_name TEXT, year INTEGER)"
                )
            )
        _migrate_schema(engine)
        cols = {c["name"] for c in inspect(engine).get_columns("products")}
        assert "palettes" in cols
        assert "bundle_path" in cols
        engine.dispose()


class TestSetBundle:
    def test_set_bundle_persists_list_and_path(self, tmp_path):
        engine, factory = _factory(tmp_path)
        session = factory()
        try:
            niche = Niche(name="n", slug="n", seed_keywords="[]")
            session.add(niche)
            session.commit()
            product = Product(
                niche_id=niche.id,
                title="t",
                palette_name="ocean_blue",
                year=2026,
                state=ProductState.RESEARCH_PENDING,
            )
            session.add(product)
            session.commit()

            repo = ProductRepository(session)
            repo.set_bundle(
                product.id,
                ["ocean_blue", "charcoal_minimal", "neutral_beige"],
                bundle_path="/tmp/bundle.zip",
            )
            session.refresh(product)
            assert json.loads(product.palettes) == [
                "ocean_blue",
                "charcoal_minimal",
                "neutral_beige",
            ]
            assert product.bundle_path == "/tmp/bundle.zip"
        finally:
            session.close()
            engine.dispose()

    def test_set_bundle_without_path_leaves_path_untouched(self, tmp_path):
        engine, factory = _factory(tmp_path)
        session = factory()
        try:
            niche = Niche(name="n", slug="n", seed_keywords="[]")
            session.add(niche)
            session.commit()
            product = Product(
                niche_id=niche.id,
                title="t",
                palette_name="ocean_blue",
                year=2026,
                state=ProductState.RESEARCH_PENDING,
            )
            session.add(product)
            session.commit()

            repo = ProductRepository(session)
            repo.set_bundle(product.id, ["ocean_blue"])
            session.refresh(product)
            assert json.loads(product.palettes) == ["ocean_blue"]
            assert product.bundle_path is None
        finally:
            session.close()
            engine.dispose()
