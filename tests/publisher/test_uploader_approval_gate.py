"""Regression tests for the EtsyUploader approval gate.

Manual approval in the dashboard is mandatory before anything reaches Etsy.
The uploader itself must refuse products that have not been approved, even
when it is called directly instead of via
``PipelineOrchestrator.publish_approved``.
"""

import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.publisher.uploader import EtsyUploader, PublishError
from src.storage.database import Base
from src.storage.models import EtsyListing, Product, ProductState


# ---------------------------------------------------------------------------
# Fakes / fixtures
# ---------------------------------------------------------------------------


class FakeListingManager:
    """Stands in for EtsyListingManager; records every API call made."""

    def __init__(self):
        self.calls: list[str] = []
        self.delivered_file: str | None = None

    def get_shop_id(self) -> int:
        self.calls.append("get_shop_id")
        return 111

    def create_draft_listing(
        self, shop_id, title, description, price, taxonomy_id, tags
    ) -> dict:
        self.calls.append("create_draft_listing")
        return {"listing_id": 222}

    def upload_listing_file(self, shop_id, listing_id, file_path, *, bundle_path=None) -> dict:
        self.calls.append("upload_listing_file")
        # The buyer-facing delivery file: bundle ZIP when present, else the PDF.
        self.delivered_file = bundle_path or file_path
        return {}

    def upload_listing_image(self, shop_id, listing_id, image_path, rank) -> dict:
        self.calls.append("upload_listing_image")
        return {}

    def activate_listing(self, shop_id, listing_id) -> dict:
        self.calls.append("activate_listing")
        return {"url": "https://www.etsy.com/listing/222"}


@pytest.fixture()
def session():
    """In-memory SQLite session with all tables created."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    sess = Session(engine)
    yield sess
    sess.close()
    engine.dispose()


@pytest.fixture()
def make_product(session):
    """Factory fixture: create a publish-ready Product in a given state."""

    def _make(state: ProductState) -> Product:
        product = Product(
            niche_id=1,
            title="2026 Budget Planner Digital Planner | iPad GoodNotes",
            palette_name="ocean_blue",
            year=2026,
            price_usd=5.99,
            pdf_path="/tmp/fake.pdf",
            description="A tidy planner.",
            tags=json.dumps(["budget planner", "2026 planner"]),
            state=state,
        )
        session.add(product)
        session.commit()
        return product

    return _make


@pytest.fixture()
def manager():
    return FakeListingManager()


@pytest.fixture()
def uploader(session, manager):
    return EtsyUploader(listing_manager=manager, session=session)


# ---------------------------------------------------------------------------
# Refusal: unapproved products never reach Etsy
# ---------------------------------------------------------------------------


class TestUploaderRefusesUnapprovedProducts:
    @pytest.mark.parametrize(
        "state",
        [
            ProductState.RESEARCH_PENDING,
            ProductState.RESEARCH_COMPLETE,
            ProductState.GENERATION_PENDING,
            ProductState.GENERATION_COMPLETE,
            ProductState.REVIEW_PENDING,
            ProductState.REJECTED,
            ProductState.PUBLISHED,
            ProductState.FAILED,
        ],
    )
    def test_publish_refuses_unapproved_state(
        self, session, make_product, manager, uploader, state
    ):
        product = make_product(state)

        with pytest.raises(PublishError, match="not approved"):
            uploader.publish(product, [], taxonomy_id=100)

        # No Etsy API call was made, no listing row was written, and the
        # product state was left untouched (not marked FAILED).
        assert manager.calls == []
        assert session.execute(select(EtsyListing)).scalars().all() == []
        assert session.get(Product, product.id).state == state

    def test_publish_product_refuses_review_pending(
        self, session, make_product, manager, uploader
    ):
        """The by-ID convenience wrapper goes through the same gate."""
        product = make_product(ProductState.REVIEW_PENDING)

        with pytest.raises(PublishError, match="not approved"):
            uploader.publish_product(product.id, mockup_paths=[])

        assert manager.calls == []
        assert session.get(Product, product.id).state == ProductState.REVIEW_PENDING

    def test_publish_product_refuses_generation_complete(
        self, session, make_product, manager, uploader
    ):
        product = make_product(ProductState.GENERATION_COMPLETE)

        with pytest.raises(PublishError, match="not approved"):
            uploader.publish_product(product.id, mockup_paths=[])

        assert manager.calls == []
        assert (
            session.get(Product, product.id).state
            == ProductState.GENERATION_COMPLETE
        )


# ---------------------------------------------------------------------------
# Acceptance: approved products publish normally
# ---------------------------------------------------------------------------


class TestUploaderAcceptsApprovedProducts:
    def test_publish_approved_product(self, session, make_product, manager, uploader):
        product = make_product(ProductState.APPROVED)

        listing = uploader.publish(product, [], taxonomy_id=100)

        assert listing.listing_id == 222
        assert listing.status == "active"
        assert session.get(Product, product.id).state == ProductState.PUBLISHED
        assert "activate_listing" in manager.calls

    def test_publish_upload_pending_product(
        self, session, make_product, manager, uploader
    ):
        """publish_approved hands off in UPLOAD_PENDING; that must still work."""
        product = make_product(ProductState.UPLOAD_PENDING)

        listing = uploader.publish(product, [], taxonomy_id=100)

        assert listing.status == "active"
        assert session.get(Product, product.id).state == ProductState.PUBLISHED

    def test_delivers_hero_pdf_when_no_bundle(
        self, session, make_product, manager, uploader
    ):
        """A single-palette product delivers its hero PDF (no bundle)."""
        product = make_product(ProductState.APPROVED)

        uploader.publish(product, [], taxonomy_id=100)

        assert manager.delivered_file == product.pdf_path

    def test_delivers_bundle_zip_when_present(
        self, session, make_product, manager, uploader
    ):
        """A multi-palette product delivers its bundle ZIP, not the hero PDF."""
        product = make_product(ProductState.APPROVED)
        product.bundle_path = "/tmp/product_bundle.zip"
        session.commit()

        uploader.publish(product, [], taxonomy_id=100)

        # The buyer receives every colourway (the ZIP), not just the hero PDF.
        assert manager.delivered_file == "/tmp/product_bundle.zip"
        assert manager.delivered_file != product.pdf_path
