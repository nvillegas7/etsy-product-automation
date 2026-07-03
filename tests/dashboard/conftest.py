"""Fixtures for dashboard tests: tmp-file SQLite DB seeded with products."""

import json

import pytest

from src.storage.database import get_session_factory, init_db, reset_engine
from src.storage.models import ProductState
from src.storage.repository import NicheRepository, ProductRepository

# Paths recorded on another machine — they must not exist here so the
# dashboard's path-resilience code paths get exercised.
STALE_PDF = "/Users/neilalvinvillegas/proj/etsy-planner-bot/output/planners/gone.pdf"
STALE_MOCKUP = "/Users/neilalvinvillegas/proj/etsy-planner-bot/output/mockups/gone.png"


def _seed(session_factory) -> dict[str, int]:
    """Create one product per interesting state; return name -> id."""
    session = session_factory()
    try:
        niche = NicheRepository(session).create(
            name="Budget Planner", slug="budget-planner", seed_keywords=["budget"]
        )
        repo = ProductRepository(session)

        common = {
            "niche_id": niche.id,
            "palette_name": "ocean_blue",
            "year": 2026,
            "pdf_path": STALE_PDF,
            "mockup_path": json.dumps([STALE_MOCKUP]),
            "description": "A tidy planner.\nInstant download.",
            "tags": json.dumps(["budget planner", "2026 planner"]),
            "price_usd": 5.99,
        }

        pending = repo.create(
            product_type="planner",
            title="2026 Budget Planner Digital Planner | iPad GoodNotes",
            display_title="2026 Budget Planner",
            state=ProductState.REVIEW_PENDING,
            **common,
        )
        approved = repo.create(
            product_type="picture_book",
            title="Brave Fox Bedtime Story | Printable Picture Book",
            display_title="The Brave Little Fox",
            state=ProductState.APPROVED,
            params=json.dumps(
                {"character": "fox", "setting": "forest", "moral": "courage"}
            ),
            **{**common, "mockup_path": STALE_MOCKUP},  # single-path variant
        )
        rejected = repo.create(
            product_type="planner",
            title="2026 Fitness Planner Digital Planner | iPad GoodNotes",
            display_title="2026 Fitness Planner",
            state=ProductState.REJECTED,
            review_note="cover looks off",
            **common,
        )
        published = repo.create(
            product_type="planner",
            title="2026 Student Planner Digital Planner | iPad GoodNotes",
            display_title="2026 Student Planner",
            state=ProductState.PUBLISHED,
            **common,
        )
        return {
            "pending": pending.id,
            "approved": approved.id,
            "rejected": rejected.id,
            "published": published.id,
        }
    finally:
        session.close()


@pytest.fixture()
def dashboard(tmp_path):
    """(flask test client, seeded ids, session_factory) against a tmp DB."""
    reset_engine()
    init_db(f"sqlite:///{tmp_path}/test.db")
    session_factory = get_session_factory()
    ids = _seed(session_factory)

    from src.dashboard.app import create_app

    config = {
        "etsy": {"upload_enabled": False},
        "paths": {
            "database": str(tmp_path / "test.db"),
            "preview_dir": str(tmp_path / "previews"),
        },
    }
    app = create_app(config)
    app.config["TESTING"] = True

    with app.test_client() as client:
        yield client, ids, session_factory

    reset_engine()
