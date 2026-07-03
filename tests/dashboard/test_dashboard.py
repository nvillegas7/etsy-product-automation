"""Tests for the manual-approval dashboard."""

from src.storage.models import Product, ProductState


def _get_product(session_factory, product_id: int) -> Product:
    session = session_factory()
    try:
        product = session.get(Product, product_id)
        session.refresh(product)
        return product
    finally:
        session.close()


# ---------------------------------------------------------------------------
# List page
# ---------------------------------------------------------------------------


class TestListPage:
    def test_index_renders_all_products(self, dashboard):
        client, ids, _ = dashboard
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "Product Studio" in html
        assert "2026 Budget Planner" in html
        assert "The Brave Little Fox" in html
        # State chips with counts
        assert "Review pending" in html
        assert "Approved" in html
        assert "Published" in html

    def test_index_shows_book_params_summary(self, dashboard):
        client, _, _ = dashboard
        html = client.get("/").get_data(as_text=True)
        assert "fox • forest • courage" in html

    def test_state_filter(self, dashboard):
        client, _, _ = dashboard
        html = client.get("/?state=review_pending").get_data(as_text=True)
        assert "2026 Budget Planner" in html
        assert "The Brave Little Fox" not in html
        assert "2026 Student Planner" not in html

    def test_type_filter(self, dashboard):
        client, _, _ = dashboard
        html = client.get("/?ptype=picture_book").get_data(as_text=True)
        assert "The Brave Little Fox" in html
        assert "2026 Budget Planner" not in html

    def test_unknown_filters_fall_back_to_all(self, dashboard):
        client, _, _ = dashboard
        resp = client.get("/?state=bogus&ptype=bogus")
        assert resp.status_code == 200
        assert "2026 Budget Planner" in resp.get_data(as_text=True)

    def test_missing_files_show_placeholder(self, dashboard):
        client, _, _ = dashboard
        html = client.get("/").get_data(as_text=True)
        assert "File missing" in html


# ---------------------------------------------------------------------------
# Detail page
# ---------------------------------------------------------------------------


class TestDetailPage:
    def test_detail_renders(self, dashboard):
        client, ids, _ = dashboard
        resp = client.get(f"/product/{ids['pending']}")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "2026 Budget Planner" in html
        assert "budget planner" in html  # tag chip
        assert "Review decision" in html  # approve/reject form
        # PDF is missing on this machine -> disabled state, no crash
        assert "PDF missing" in html

    def test_detail_404_for_unknown_product(self, dashboard):
        client, _, _ = dashboard
        assert client.get("/product/99999").status_code == 404


# ---------------------------------------------------------------------------
# Review actions
# ---------------------------------------------------------------------------


class TestReviewActions:
    def test_approve_flips_state_and_stores_note(self, dashboard):
        client, ids, session_factory = dashboard
        resp = client.post(
            f"/product/{ids['pending']}/approve",
            data={"note": "looks great"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "approved" in resp.get_data(as_text=True)
        product = _get_product(session_factory, ids["pending"])
        assert product.state == ProductState.APPROVED
        assert product.review_note == "looks great"
        assert product.reviewed_at is not None

    def test_reject_stores_note(self, dashboard):
        client, ids, session_factory = dashboard
        resp = client.post(
            f"/product/{ids['pending']}/reject",
            data={"note": "typo on cover"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        product = _get_product(session_factory, ids["pending"])
        assert product.state == ProductState.REJECTED
        assert product.review_note == "typo on cover"

    def test_re_review_returns_rejected_to_pending(self, dashboard):
        client, ids, session_factory = dashboard
        resp = client.post(
            f"/product/{ids['rejected']}/re-review", follow_redirects=True
        )
        assert resp.status_code == 200
        product = _get_product(session_factory, ids["rejected"])
        assert product.state == ProductState.REVIEW_PENDING

    def test_illegal_transition_flashes_error(self, dashboard):
        client, ids, session_factory = dashboard
        # published -> approved is not a legal transition
        resp = client.post(
            f"/product/{ids['published']}/approve", follow_redirects=True
        )
        assert resp.status_code == 200
        assert "Invalid state transition" in resp.get_data(as_text=True)
        product = _get_product(session_factory, ids["published"])
        assert product.state == ProductState.PUBLISHED


# ---------------------------------------------------------------------------
# Publishing
# ---------------------------------------------------------------------------


class TestPublish:
    def test_publish_with_upload_disabled_flashes_error(self, dashboard):
        client, ids, session_factory = dashboard
        resp = client.post(
            f"/product/{ids['approved']}/publish", follow_redirects=True
        )
        assert resp.status_code == 200
        assert "Etsy upload is disabled" in resp.get_data(as_text=True)
        product = _get_product(session_factory, ids["approved"])
        assert product.state in (ProductState.APPROVED, ProductState.UPLOAD_PENDING)

    def test_publish_non_approved_product_is_refused(self, dashboard):
        client, ids, session_factory = dashboard
        resp = client.post(
            f"/product/{ids['pending']}/publish", follow_redirects=True
        )
        assert resp.status_code == 200
        assert "Only approved products can be published" in resp.get_data(as_text=True)
        product = _get_product(session_factory, ids["pending"])
        assert product.state == ProductState.REVIEW_PENDING


# ---------------------------------------------------------------------------
# File serving
# ---------------------------------------------------------------------------


class TestFileRoutes:
    def test_pdf_404_for_unknown_product(self, dashboard):
        client, _, _ = dashboard
        assert client.get("/files/pdf/99999").status_code == 404

    def test_pdf_404_when_file_missing_on_disk(self, dashboard):
        client, ids, _ = dashboard
        assert client.get(f"/files/pdf/{ids['pending']}").status_code == 404

    def test_mockup_404_when_missing(self, dashboard):
        client, ids, _ = dashboard
        assert client.get(f"/files/mockup/{ids['pending']}/0").status_code == 404
        assert client.get(f"/files/mockup/{ids['pending']}/99").status_code == 404
        assert client.get("/files/mockup/99999/0").status_code == 404

    def test_preview_404_when_missing(self, dashboard):
        client, ids, _ = dashboard
        assert client.get(f"/files/preview/{ids['pending']}/1").status_code == 404
        assert client.get("/files/preview/99999/1").status_code == 404

    def test_no_raw_paths_accepted(self, dashboard):
        client, _, _ = dashboard
        # Non-integer ids must not match the routes at all.
        assert client.get("/files/pdf/../etc/passwd").status_code == 404
        assert client.get("/files/preview/1/../../secret").status_code == 404
