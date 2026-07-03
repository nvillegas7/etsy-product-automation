"""Product state machine with validated transitions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from src.storage.models import Product, ProductState
from src.storage.repository import ProductRepository

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Valid transitions map
# ---------------------------------------------------------------------------
# Every state -> FAILED is implicitly valid (handled separately).
_VALID_TRANSITIONS: dict[ProductState, set[ProductState]] = {
    ProductState.RESEARCH_PENDING: {ProductState.RESEARCH_COMPLETE},
    ProductState.RESEARCH_COMPLETE: {ProductState.GENERATION_PENDING},
    ProductState.GENERATION_PENDING: {ProductState.GENERATION_COMPLETE},
    # Every generated product waits for a human decision before anything
    # can reach Etsy.
    ProductState.GENERATION_COMPLETE: {ProductState.REVIEW_PENDING},
    ProductState.REVIEW_PENDING: {ProductState.APPROVED, ProductState.REJECTED},
    # APPROVED -> REJECTED lets the reviewer change their mind before upload.
    ProductState.APPROVED: {ProductState.UPLOAD_PENDING, ProductState.REJECTED},
    # A rejected product can be sent back for another look.
    ProductState.REJECTED: {ProductState.REVIEW_PENDING},
    ProductState.UPLOAD_PENDING: {ProductState.PUBLISHED},
    # Terminal states -- no forward transitions (only FAILED is allowed,
    # which is handled by the special-case below).
    ProductState.PUBLISHED: set(),
    ProductState.FAILED: set(),
}


class ProductStateMachine:
    """Enforce and execute legal state transitions for products.

    Usage::

        sm = ProductStateMachine()
        sm.transition(product_id=1, new_state=ProductState.RESEARCH_COMPLETE, session=session)
    """

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    @staticmethod
    def can_transition(current_state: ProductState, new_state: ProductState) -> bool:
        """Return True if moving from *current_state* to *new_state* is legal.

        Any state can transition to FAILED.  Otherwise only the explicitly
        defined forward transitions are permitted.
        """
        if new_state == ProductState.FAILED:
            return True
        allowed = _VALID_TRANSITIONS.get(current_state, set())
        return new_state in allowed

    @staticmethod
    def get_state(product_id: int, session: "Session") -> ProductState:
        """Return the current state of a product.

        Raises
        ------
        ValueError
            If no product with the given *product_id* exists.
        """
        product = session.get(Product, product_id)
        if product is None:
            raise ValueError(f"Product {product_id} not found")
        return product.state

    # ------------------------------------------------------------------
    # Transition
    # ------------------------------------------------------------------

    @staticmethod
    def transition(
        product_id: int,
        new_state: ProductState,
        session: "Session",
        error_message: str | None = None,
    ) -> ProductState:
        """Validate and execute a state transition.

        Parameters
        ----------
        product_id : int
            Primary key of the product to update.
        new_state : ProductState
            Desired target state.
        session : sqlalchemy.orm.Session
            Active database session.
        error_message : str or None
            Optional error detail (typically set when transitioning to FAILED).

        Returns
        -------
        ProductState
            The new state after a successful transition.

        Raises
        ------
        ValueError
            If the product does not exist or the transition is illegal.
        """
        product = session.get(Product, product_id)
        if product is None:
            raise ValueError(f"Product {product_id} not found")

        current_state = product.state

        if not ProductStateMachine.can_transition(current_state, new_state):
            raise ValueError(
                f"Invalid state transition for product {product_id}: "
                f"{current_state.value} -> {new_state.value}"
            )

        old_value = current_state.value
        product.state = new_state
        if error_message is not None:
            product.error_message = error_message
        session.commit()

        logger.info(
            "product_state_transition",
            product_id=product_id,
            from_state=old_value,
            to_state=new_state.value,
        )
        return new_state
