"""Full publish orchestration — draft, upload, activate, record."""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from sqlalchemy.orm import Session

from src.publisher.currency import convert_usd
from src.publisher.listing import EtsyListingManager, EtsyAPIError
from src.storage.models import EtsyListing, Product, ProductState
from src.storage.repository import EtsyListingRepository, ProductRepository
from src.utils.retry import retry_with_backoff

logger = structlog.get_logger()

# Maximum number of mockup images Etsy allows per listing
MAX_IMAGES = 10
# We limit to 5 for a clean gallery
RECOMMENDED_MAX_IMAGES = 5

# States a product may be in when it reaches the uploader. Manual approval in
# the dashboard is mandatory: PipelineOrchestrator.publish_approved verifies
# APPROVED and hands off in UPLOAD_PENDING; a direct caller may pass a product
# still in APPROVED. Anything else has not cleared human review.
PUBLISHABLE_STATES = (ProductState.APPROVED, ProductState.UPLOAD_PENDING)


class PublishError(Exception):
    """Raised when the publish workflow fails irrecoverably."""


class EtsyUploader:
    """Orchestrates the end-to-end listing publish pipeline.

    Steps:
        1. Resolve the shop ID.
        2. Create a draft listing with SEO metadata.
        3. Upload the digital PDF file.
        4. Upload mockup images (up to 5).
        5. Activate the listing.
        6. Record the listing in the etsy_listings table.

    Each network step is wrapped with retry_with_backoff.
    """

    def __init__(
        self,
        listing_manager: EtsyListingManager,
        session: Session,
        fx_rates: dict | None = None,
    ):
        """Initialize with a listing manager and database session.

        Args:
            listing_manager: EtsyListingManager for API interactions.
            session: SQLAlchemy session for DB persistence.
            fx_rates: USD->currency exchange rates (units per 1 USD), used to
                convert the product's USD price into the shop's currency at
                publish time. Empty/None is fine for USD-denominated shops.
        """
        self.listing_manager = listing_manager
        self.session = session
        self.fx_rates = fx_rates or {}
        self.product_repo = ProductRepository(session)
        self.listing_repo = EtsyListingRepository(session)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def publish(
        self,
        product: Product,
        mockup_paths: list[str],
        taxonomy_id: int | None = None,
    ) -> EtsyListing:
        """Publish a product to Etsy.

        Args:
            product: Product ORM instance (must have title, description,
                tags, price_usd, and pdf_path set).
            mockup_paths: Paths to mockup images (PNG/JPG).
            taxonomy_id: Override taxonomy ID; defaults to env ETSY_TAXONOMY_ID.

        Returns:
            The created EtsyListing record.

        Raises:
            PublishError: If the product has not been approved for upload,
                or if any step fails after retries.
        """
        import json
        import os

        # --- Approval gate: nothing reaches Etsy without manual review ---
        if product.state not in PUBLISHABLE_STATES:
            raise PublishError(
                f"Product {product.id} is '{product.state.value}', not approved "
                "for upload. Only products approved in the review dashboard "
                "(state 'approved' or 'upload_pending') can be published to Etsy."
            )

        logger.info("publish_start", product_id=product.id, title=product.title)

        taxonomy_id = taxonomy_id or int(os.getenv("ETSY_TAXONOMY_ID", "0"))
        if not taxonomy_id:
            raise PublishError(
                "taxonomy_id is required. Set ETSY_TAXONOMY_ID env var "
                "or pass it explicitly."
            )

        tags = json.loads(product.tags) if isinstance(product.tags, str) else (product.tags or [])

        # --- Step 1: Resolve shop ID + currency ---
        self.product_repo.update_state(product.id, ProductState.UPLOAD_PENDING)
        shop_id = self._step_get_shop_id()

        # Etsy prices listings in the shop's currency; our prices are USD.
        # Convert before creating the draft so a $5.99 planner doesn't list as
        # 5.99 of a weaker currency. (No-op for USD shops.)
        shop_currency = self.listing_manager.get_shop_currency()
        listing_price = convert_usd(product.price_usd, shop_currency, self.fx_rates)
        if shop_currency != "USD":
            logger.info(
                "listing_price_converted",
                product_id=product.id,
                price_usd=product.price_usd,
                shop_currency=shop_currency,
                listing_price=listing_price,
            )

        etsy_listing_id: int | None = None
        etsy_url: str | None = None

        try:
            # --- Step 2: Create draft listing ---
            draft = self._step_create_draft(
                shop_id=shop_id,
                title=product.title,
                description=product.description or "",
                price=listing_price,
                taxonomy_id=taxonomy_id,
                tags=tags,
            )
            etsy_listing_id = draft.get("listing_id")
            logger.info("publish_draft_created", etsy_listing_id=etsy_listing_id)

            # Record an initial DB entry as draft
            db_listing = self.listing_repo.create(
                product_id=product.id,
                listing_id=etsy_listing_id,
                shop_id=shop_id,
                status="draft",
            )

            # --- Step 3: Upload digital file (bundle ZIP if present, else PDF) ---
            if product.pdf_path:
                self._step_upload_file(
                    shop_id,
                    etsy_listing_id,
                    product.pdf_path,
                    bundle_path=product.bundle_path,
                )
            else:
                raise PublishError("Product has no pdf_path set.")

            # --- Step 4: Upload mockup images ---
            images_to_upload = mockup_paths[:RECOMMENDED_MAX_IMAGES]
            for rank, img_path in enumerate(images_to_upload, start=1):
                self._step_upload_image(shop_id, etsy_listing_id, img_path, rank)

            # --- Step 5: Activate listing ---
            activate_resp = self._step_activate(shop_id, etsy_listing_id)
            etsy_url = activate_resp.get("url") or (
                f"https://www.etsy.com/listing/{etsy_listing_id}"
            )

            # --- Step 6: Update DB records ---
            self.listing_repo.update(
                db_listing.id,
                status="active",
                etsy_url=etsy_url,
                published_at=datetime.now(timezone.utc),
            )
            self.product_repo.update_state(product.id, ProductState.PUBLISHED)

            logger.info(
                "publish_complete",
                product_id=product.id,
                etsy_listing_id=etsy_listing_id,
                etsy_url=etsy_url,
            )
            return db_listing

        except Exception as exc:
            logger.error(
                "publish_failed",
                product_id=product.id,
                etsy_listing_id=etsy_listing_id,
                error=str(exc),
            )
            self.product_repo.update_state(
                product.id,
                ProductState.FAILED,
                error=str(exc),
            )
            raise PublishError(f"Publish failed for product {product.id}: {exc}") from exc

    def publish_product(self, product_id: int, mockup_paths: list[str] | None = None) -> EtsyListing:
        """Convenience wrapper — loads a Product by ID and publishes it.

        If *mockup_paths* is not supplied, falls back to the product's
        ``mockup_path`` field (expected to be a single path or a JSON list).

        Args:
            product_id: Primary key in the products table.
            mockup_paths: Optional explicit list of mockup image paths.

        Returns:
            The created EtsyListing record.
        """
        import json

        product = self.product_repo.get(product_id)
        if product is None:
            raise PublishError(f"Product {product_id} not found.")

        if mockup_paths is None:
            if product.mockup_path:
                # Could be a single path or a JSON-encoded list
                try:
                    mockup_paths = json.loads(product.mockup_path)
                    if isinstance(mockup_paths, str):
                        mockup_paths = [mockup_paths]
                except (json.JSONDecodeError, TypeError):
                    mockup_paths = [product.mockup_path]
            else:
                mockup_paths = []

        return self.publish(product, mockup_paths)

    # ------------------------------------------------------------------
    # Internal steps (each wrapped with retry)
    # ------------------------------------------------------------------

    @retry_with_backoff(max_retries=3, base_delay=2.0, exceptions=(EtsyAPIError,))
    def _step_get_shop_id(self) -> int:
        return self.listing_manager.get_shop_id()

    @retry_with_backoff(max_retries=3, base_delay=2.0, exceptions=(EtsyAPIError,))
    def _step_create_draft(
        self,
        shop_id: int,
        title: str,
        description: str,
        price: float,
        taxonomy_id: int,
        tags: list[str],
    ) -> dict:
        return self.listing_manager.create_draft_listing(
            shop_id=shop_id,
            title=title,
            description=description,
            price=price,
            taxonomy_id=taxonomy_id,
            tags=tags,
        )

    @retry_with_backoff(max_retries=3, base_delay=2.0, exceptions=(EtsyAPIError, OSError))
    def _step_upload_file(
        self,
        shop_id: int,
        listing_id: int,
        file_path: str,
        bundle_path: str | None = None,
    ) -> dict:
        return self.listing_manager.upload_listing_file(
            shop_id, listing_id, file_path, bundle_path=bundle_path
        )

    @retry_with_backoff(max_retries=3, base_delay=2.0, exceptions=(EtsyAPIError, OSError))
    def _step_upload_image(
        self, shop_id: int, listing_id: int, image_path: str, rank: int
    ) -> dict:
        return self.listing_manager.upload_listing_image(shop_id, listing_id, image_path, rank)

    @retry_with_backoff(max_retries=3, base_delay=2.0, exceptions=(EtsyAPIError,))
    def _step_activate(self, shop_id: int, listing_id: int) -> dict:
        return self.listing_manager.activate_listing(shop_id, listing_id)
