"""Regression tests for the upload safety guards.

Covers two defense-in-depth fixes:

* ``_etsy_upload_enabled`` fails closed -- a missing ``etsy.upload_enabled``
  key must keep uploads disabled, and the ``ETSY_UPLOAD_ENABLED`` env var can
  only disable uploads, never enable them.
* ``ProductRepository.update_state`` enforces the same transition rules as
  ``ProductStateMachine`` instead of acting as a raw setter.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.pipeline.orchestrator import _etsy_upload_enabled
from src.storage.database import Base
from src.storage.models import Product, ProductState
from src.storage.repository import ProductRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def etsy_credentials(monkeypatch):
    """Provide valid credentials so only the config flag is under test."""
    monkeypatch.setenv("ETSY_API_KEY", "test-key")
    monkeypatch.setenv("ETSY_SHARED_SECRET", "test-secret")
    monkeypatch.delenv("ETSY_UPLOAD_ENABLED", raising=False)


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
    """Factory fixture: create a Product in a given state."""

    def _make(state: ProductState = ProductState.RESEARCH_PENDING) -> Product:
        product = Product(
            niche_id=1,
            title="Test Planner",
            palette_name="soft_sage",
            year=2026,
            price_usd=5.99,
            state=state,
        )
        session.add(product)
        session.commit()
        return product

    return _make


# ---------------------------------------------------------------------------
# _etsy_upload_enabled -- fail-closed config default
# ---------------------------------------------------------------------------


class TestEtsyUploadEnabledFailsClosed:
    def test_missing_upload_enabled_key_disables_uploads(self, etsy_credentials):
        """Deleting etsy.upload_enabled from config.yaml must not arm uploads."""
        assert _etsy_upload_enabled({"etsy": {}}) is False

    def test_missing_etsy_section_disables_uploads(self, etsy_credentials):
        assert _etsy_upload_enabled({}) is False

    def test_explicit_false_disables_uploads(self, etsy_credentials):
        assert _etsy_upload_enabled({"etsy": {"upload_enabled": False}}) is False

    def test_explicit_true_with_credentials_enables_uploads(self, etsy_credentials):
        assert _etsy_upload_enabled({"etsy": {"upload_enabled": True}}) is True

    def test_explicit_true_without_credentials_disables_uploads(self, monkeypatch):
        monkeypatch.delenv("ETSY_API_KEY", raising=False)
        monkeypatch.delenv("ETSY_SHARED_SECRET", raising=False)
        monkeypatch.delenv("ETSY_UPLOAD_ENABLED", raising=False)
        assert _etsy_upload_enabled({"etsy": {"upload_enabled": True}}) is False

    @pytest.mark.parametrize("env_value", ["false", "0", "no", "FALSE", "No"])
    def test_env_kill_switch_disables_even_when_config_enables(
        self, etsy_credentials, monkeypatch, env_value
    ):
        monkeypatch.setenv("ETSY_UPLOAD_ENABLED", env_value)
        assert _etsy_upload_enabled({"etsy": {"upload_enabled": True}}) is False

    @pytest.mark.parametrize("env_value", ["true", "1", "yes"])
    def test_env_var_cannot_enable_when_config_key_missing(
        self, etsy_credentials, monkeypatch, env_value
    ):
        """The env var is a kill switch only -- it must never enable uploads."""
        monkeypatch.setenv("ETSY_UPLOAD_ENABLED", env_value)
        assert _etsy_upload_enabled({"etsy": {}}) is False

    def test_env_var_cannot_enable_when_config_disables(
        self, etsy_credentials, monkeypatch
    ):
        monkeypatch.setenv("ETSY_UPLOAD_ENABLED", "true")
        assert _etsy_upload_enabled({"etsy": {"upload_enabled": False}}) is False


# ---------------------------------------------------------------------------
# ProductRepository.update_state -- transition validation
# ---------------------------------------------------------------------------


class TestUpdateStateValidation:
    def test_invalid_transition_raises(self, session, make_product):
        """update_state must not jump REVIEW_PENDING straight to PUBLISHED."""
        product = make_product(ProductState.REVIEW_PENDING)
        repo = ProductRepository(session)
        with pytest.raises(ValueError, match="Invalid state transition"):
            repo.update_state(product.id, ProductState.PUBLISHED)
        assert session.get(Product, product.id).state == ProductState.REVIEW_PENDING

    def test_review_gate_cannot_be_skipped(self, session, make_product):
        """GENERATION_COMPLETE -> UPLOAD_PENDING would bypass manual review."""
        product = make_product(ProductState.GENERATION_COMPLETE)
        repo = ProductRepository(session)
        with pytest.raises(ValueError, match="Invalid state transition"):
            repo.update_state(product.id, ProductState.UPLOAD_PENDING)
        assert (
            session.get(Product, product.id).state
            == ProductState.GENERATION_COMPLETE
        )

    def test_rejected_cannot_reach_upload_pending(self, session, make_product):
        product = make_product(ProductState.REJECTED)
        repo = ProductRepository(session)
        with pytest.raises(ValueError, match="Invalid state transition"):
            repo.update_state(product.id, ProductState.UPLOAD_PENDING)

    def test_valid_transition_succeeds(self, session, make_product):
        product = make_product(ProductState.APPROVED)
        repo = ProductRepository(session)
        repo.update_state(product.id, ProductState.UPLOAD_PENDING)
        assert session.get(Product, product.id).state == ProductState.UPLOAD_PENDING

    def test_same_state_is_idempotent_noop(self, session, make_product):
        """Re-asserting the current state (uploader handoff) must not raise."""
        product = make_product(ProductState.UPLOAD_PENDING)
        repo = ProductRepository(session)
        repo.update_state(product.id, ProductState.UPLOAD_PENDING)
        assert session.get(Product, product.id).state == ProductState.UPLOAD_PENDING

    def test_any_state_to_failed_allowed(self, session, make_product):
        product = make_product(ProductState.REVIEW_PENDING)
        repo = ProductRepository(session)
        repo.update_state(product.id, ProductState.FAILED, error="boom")
        refreshed = session.get(Product, product.id)
        assert refreshed.state == ProductState.FAILED
        assert refreshed.error_message == "boom"

    def test_missing_product_is_noop(self, session):
        repo = ProductRepository(session)
        # Preserves prior behavior: unknown IDs are silently ignored.
        repo.update_state(99999, ProductState.FAILED)
