"""Unit tests for the ProductStateMachine."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.storage.database import Base
from src.storage.models import Product, ProductState
from src.pipeline.state import ProductStateMachine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine():
    """Create an in-memory SQLite engine with all tables."""
    eng = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    """Provide a transactional session that rolls back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    sess = Session(bind=connection)
    yield sess
    sess.close()
    transaction.rollback()
    connection.close()


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


@pytest.fixture()
def sm():
    return ProductStateMachine()


# ---------------------------------------------------------------------------
# can_transition tests
# ---------------------------------------------------------------------------


class TestCanTransition:
    """Tests for ProductStateMachine.can_transition()."""

    def test_research_pending_to_research_complete(self, sm):
        assert sm.can_transition(
            ProductState.RESEARCH_PENDING, ProductState.RESEARCH_COMPLETE
        ) is True

    def test_research_complete_to_generation_pending(self, sm):
        assert sm.can_transition(
            ProductState.RESEARCH_COMPLETE, ProductState.GENERATION_PENDING
        ) is True

    def test_generation_pending_to_generation_complete(self, sm):
        assert sm.can_transition(
            ProductState.GENERATION_PENDING, ProductState.GENERATION_COMPLETE
        ) is True

    def test_generation_complete_to_review_pending(self, sm):
        assert sm.can_transition(
            ProductState.GENERATION_COMPLETE, ProductState.REVIEW_PENDING
        ) is True

    def test_generation_complete_to_upload_pending_is_invalid(self, sm):
        """Nothing skips the manual review gate."""
        assert sm.can_transition(
            ProductState.GENERATION_COMPLETE, ProductState.UPLOAD_PENDING
        ) is False

    def test_review_pending_to_approved(self, sm):
        assert sm.can_transition(
            ProductState.REVIEW_PENDING, ProductState.APPROVED
        ) is True

    def test_review_pending_to_rejected(self, sm):
        assert sm.can_transition(
            ProductState.REVIEW_PENDING, ProductState.REJECTED
        ) is True

    def test_approved_to_upload_pending(self, sm):
        assert sm.can_transition(
            ProductState.APPROVED, ProductState.UPLOAD_PENDING
        ) is True

    def test_approved_to_rejected_change_of_mind(self, sm):
        assert sm.can_transition(
            ProductState.APPROVED, ProductState.REJECTED
        ) is True

    def test_rejected_to_review_pending_re_review(self, sm):
        assert sm.can_transition(
            ProductState.REJECTED, ProductState.REVIEW_PENDING
        ) is True

    def test_review_pending_to_published_is_invalid(self, sm):
        assert sm.can_transition(
            ProductState.REVIEW_PENDING, ProductState.PUBLISHED
        ) is False

    def test_rejected_to_upload_pending_is_invalid(self, sm):
        assert sm.can_transition(
            ProductState.REJECTED, ProductState.UPLOAD_PENDING
        ) is False

    def test_upload_pending_to_published(self, sm):
        assert sm.can_transition(
            ProductState.UPLOAD_PENDING, ProductState.PUBLISHED
        ) is True

    # Any state -> FAILED should always be valid
    @pytest.mark.parametrize(
        "state",
        [
            ProductState.RESEARCH_PENDING,
            ProductState.RESEARCH_COMPLETE,
            ProductState.GENERATION_PENDING,
            ProductState.GENERATION_COMPLETE,
            ProductState.REVIEW_PENDING,
            ProductState.APPROVED,
            ProductState.REJECTED,
            ProductState.UPLOAD_PENDING,
            ProductState.PUBLISHED,
            ProductState.FAILED,
        ],
    )
    def test_any_state_to_failed(self, sm, state):
        assert sm.can_transition(state, ProductState.FAILED) is True

    # Invalid transitions
    def test_research_pending_to_published_is_invalid(self, sm):
        assert sm.can_transition(
            ProductState.RESEARCH_PENDING, ProductState.PUBLISHED
        ) is False

    def test_research_pending_to_upload_pending_is_invalid(self, sm):
        assert sm.can_transition(
            ProductState.RESEARCH_PENDING, ProductState.UPLOAD_PENDING
        ) is False

    def test_published_to_research_pending_is_invalid(self, sm):
        assert sm.can_transition(
            ProductState.PUBLISHED, ProductState.RESEARCH_PENDING
        ) is False

    def test_generation_complete_to_research_complete_is_invalid(self, sm):
        assert sm.can_transition(
            ProductState.GENERATION_COMPLETE, ProductState.RESEARCH_COMPLETE
        ) is False

    def test_failed_to_research_pending_is_invalid(self, sm):
        assert sm.can_transition(
            ProductState.FAILED, ProductState.RESEARCH_PENDING
        ) is False

    def test_research_pending_to_generation_complete_skip_is_invalid(self, sm):
        assert sm.can_transition(
            ProductState.RESEARCH_PENDING, ProductState.GENERATION_COMPLETE
        ) is False

    def test_upload_pending_to_generation_complete_backward_is_invalid(self, sm):
        assert sm.can_transition(
            ProductState.UPLOAD_PENDING, ProductState.GENERATION_COMPLETE
        ) is False


# ---------------------------------------------------------------------------
# get_state tests
# ---------------------------------------------------------------------------


class TestGetState:
    def test_returns_current_state(self, sm, session, make_product):
        product = make_product(ProductState.GENERATION_PENDING)
        assert sm.get_state(product.id, session) == ProductState.GENERATION_PENDING

    def test_raises_for_missing_product(self, sm, session):
        with pytest.raises(ValueError, match="not found"):
            sm.get_state(99999, session)


# ---------------------------------------------------------------------------
# transition tests
# ---------------------------------------------------------------------------


class TestTransition:
    def test_valid_forward_transition(self, sm, session, make_product):
        product = make_product(ProductState.RESEARCH_PENDING)
        result = sm.transition(product.id, ProductState.RESEARCH_COMPLETE, session)
        assert result == ProductState.RESEARCH_COMPLETE
        assert sm.get_state(product.id, session) == ProductState.RESEARCH_COMPLETE

    def test_full_happy_path(self, sm, session, make_product):
        """Walk a product through every valid state in order."""
        product = make_product(ProductState.RESEARCH_PENDING)

        transitions = [
            ProductState.RESEARCH_COMPLETE,
            ProductState.GENERATION_PENDING,
            ProductState.GENERATION_COMPLETE,
            ProductState.REVIEW_PENDING,
            ProductState.APPROVED,
            ProductState.UPLOAD_PENDING,
            ProductState.PUBLISHED,
        ]
        for new_state in transitions:
            sm.transition(product.id, new_state, session)

        assert sm.get_state(product.id, session) == ProductState.PUBLISHED

    def test_reject_and_re_review_path(self, sm, session, make_product):
        """A rejected product can be re-reviewed and then approved."""
        product = make_product(ProductState.REVIEW_PENDING)
        sm.transition(product.id, ProductState.REJECTED, session)
        sm.transition(product.id, ProductState.REVIEW_PENDING, session)
        sm.transition(product.id, ProductState.APPROVED, session)
        assert sm.get_state(product.id, session) == ProductState.APPROVED

    def test_transition_to_failed_from_any_state(self, sm, session, make_product):
        product = make_product(ProductState.GENERATION_PENDING)
        result = sm.transition(
            product.id, ProductState.FAILED, session, error_message="Something broke"
        )
        assert result == ProductState.FAILED
        # Verify error message was stored
        refreshed = session.get(Product, product.id)
        assert refreshed.error_message == "Something broke"

    def test_invalid_transition_raises(self, sm, session, make_product):
        product = make_product(ProductState.RESEARCH_PENDING)
        with pytest.raises(ValueError, match="Invalid state transition"):
            sm.transition(product.id, ProductState.PUBLISHED, session)

    def test_transition_nonexistent_product_raises(self, sm, session):
        with pytest.raises(ValueError, match="not found"):
            sm.transition(99999, ProductState.RESEARCH_COMPLETE, session)

    def test_transition_persists_to_db(self, sm, session, make_product):
        product = make_product(ProductState.RESEARCH_PENDING)
        sm.transition(product.id, ProductState.RESEARCH_COMPLETE, session)

        # Re-fetch from DB to confirm persistence
        refreshed = session.get(Product, product.id)
        assert refreshed.state == ProductState.RESEARCH_COMPLETE

    def test_backward_transition_raises(self, sm, session, make_product):
        product = make_product(ProductState.GENERATION_COMPLETE)
        with pytest.raises(ValueError, match="Invalid state transition"):
            sm.transition(product.id, ProductState.RESEARCH_PENDING, session)

    def test_skip_transition_raises(self, sm, session, make_product):
        """Cannot skip from RESEARCH_PENDING directly to GENERATION_COMPLETE."""
        product = make_product(ProductState.RESEARCH_PENDING)
        with pytest.raises(ValueError, match="Invalid state transition"):
            sm.transition(product.id, ProductState.GENERATION_COMPLETE, session)

    def test_same_state_transition_raises(self, sm, session, make_product):
        """Transitioning to the same state should fail (not in allowed set)."""
        product = make_product(ProductState.RESEARCH_PENDING)
        with pytest.raises(ValueError, match="Invalid state transition"):
            sm.transition(product.id, ProductState.RESEARCH_PENDING, session)

    def test_failed_to_failed_is_valid(self, sm, session, make_product):
        """FAILED -> FAILED is valid because any -> FAILED is allowed."""
        product = make_product(ProductState.FAILED)
        result = sm.transition(
            product.id, ProductState.FAILED, session, error_message="Second failure"
        )
        assert result == ProductState.FAILED

    def test_error_message_only_set_when_provided(self, sm, session, make_product):
        product = make_product(ProductState.RESEARCH_PENDING)
        sm.transition(product.id, ProductState.RESEARCH_COMPLETE, session)
        refreshed = session.get(Product, product.id)
        assert refreshed.error_message is None
