"""Tests for reviewer editing of Etsy listing fields before publishing."""

import json

from src.storage.models import Product


def _get_product(session_factory, product_id: int) -> Product:
    session = session_factory()
    try:
        product = session.get(Product, product_id)
        session.refresh(product)
        return product
    finally:
        session.close()


class TestEditListing:
    def test_edit_updates_all_fields(self, dashboard):
        client, ids, sf = dashboard
        resp = client.post(
            f"/product/{ids['pending']}/edit",
            data={
                "title": "  2026 Ultimate Budget Planner PDF  ",
                "description": "Brand new description.",
                "tags": "a, b, c",
                "price_usd": "7.50",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "Listing details updated." in resp.get_data(as_text=True)

        p = _get_product(sf, ids["pending"])
        assert p.title == "2026 Ultimate Budget Planner PDF"
        assert p.description == "Brand new description."
        assert json.loads(p.tags) == ["a", "b", "c"]
        assert p.price_usd == 7.50

    def test_tags_dedup_and_trim(self, dashboard):
        client, ids, sf = dashboard
        client.post(
            f"/product/{ids['pending']}/edit",
            data={
                "title": "Title",
                "description": "d",
                "tags": "  cozy ,cozy, planner\nnotes ,",
                "price_usd": "5.99",
            },
        )
        p = _get_product(sf, ids["pending"])
        assert json.loads(p.tags) == ["cozy", "planner", "notes"]

    def test_too_many_tags_rejected(self, dashboard):
        client, ids, sf = dashboard
        many = ",".join(f"tag{i}" for i in range(14))
        resp = client.post(
            f"/product/{ids['pending']}/edit",
            data={"title": "Title", "description": "d", "tags": many, "price_usd": "5.99"},
            follow_redirects=True,
        )
        assert "at most 13 tags" in resp.get_data(as_text=True)
        p = _get_product(sf, ids["pending"])
        # Unchanged from the seed
        assert json.loads(p.tags) == ["budget planner", "2026 planner"]

    def test_long_tag_rejected(self, dashboard):
        client, ids, sf = dashboard
        resp = client.post(
            f"/product/{ids['pending']}/edit",
            data={
                "title": "Title",
                "description": "d",
                "tags": "ok, thisisareallylongtagover20chars",
                "price_usd": "5.99",
            },
            follow_redirects=True,
        )
        assert "20 characters or fewer" in resp.get_data(as_text=True)
        p = _get_product(sf, ids["pending"])
        assert json.loads(p.tags) == ["budget planner", "2026 planner"]

    def test_zero_price_rejected(self, dashboard):
        client, ids, sf = dashboard
        resp = client.post(
            f"/product/{ids['pending']}/edit",
            data={"title": "Title", "description": "d", "tags": "a", "price_usd": "0"},
            follow_redirects=True,
        )
        assert "greater than 0" in resp.get_data(as_text=True)
        p = _get_product(sf, ids["pending"])
        assert p.price_usd == 5.99

    def test_empty_price_rejected(self, dashboard):
        client, ids, sf = dashboard
        resp = client.post(
            f"/product/{ids['pending']}/edit",
            data={"title": "Title", "description": "d", "tags": "a", "price_usd": ""},
            follow_redirects=True,
        )
        assert "must be a number" in resp.get_data(as_text=True)

    def test_empty_title_rejected(self, dashboard):
        client, ids, sf = dashboard
        resp = client.post(
            f"/product/{ids['pending']}/edit",
            data={"title": "   ", "description": "d", "tags": "a", "price_usd": "5.99"},
            follow_redirects=True,
        )
        assert "Title is required." in resp.get_data(as_text=True)

    def test_long_title_rejected(self, dashboard):
        client, ids, sf = dashboard
        resp = client.post(
            f"/product/{ids['pending']}/edit",
            data={"title": "x" * 141, "description": "d", "tags": "a", "price_usd": "5.99"},
            follow_redirects=True,
        )
        assert "140 characters" in resp.get_data(as_text=True)

    def test_edit_approved_allowed(self, dashboard):
        client, ids, sf = dashboard
        resp = client.post(
            f"/product/{ids['approved']}/edit",
            data={"title": "Approved Edit", "description": "d", "tags": "a", "price_usd": "9.99"},
            follow_redirects=True,
        )
        assert "Listing details updated." in resp.get_data(as_text=True)
        p = _get_product(sf, ids["approved"])
        assert p.title == "Approved Edit"

    def test_edit_published_saves_locally_and_syncs(self, dashboard):
        """Published products are now editable; the save also pushes to Etsy.

        Etsy uploads are disabled in the test config, so the sync fails and is
        surfaced as a warning -- but the local edit is still saved.
        """
        client, ids, sf = dashboard
        resp = client.post(
            f"/product/{ids['published']}/edit",
            data={
                "title": "Published Edit",
                "description": "d",
                "tags": "a",
                "price_usd": "9.99",
            },
            follow_redirects=True,
        )
        body = resp.get_data(as_text=True)
        # The local change is saved even though Etsy is unreachable in tests.
        p = _get_product(sf, ids["published"])
        assert p.title == "Published Edit"
        # ...and the (failed) Etsy sync attempt is surfaced to the reviewer.
        assert "Saved locally" in body

    def test_edit_form_prefilled(self, dashboard):
        client, ids, sf = dashboard
        client.post(
            f"/product/{ids['pending']}/edit",
            data={
                "title": "Prefilled Title Check",
                "description": "Prefilled description body.",
                "tags": "alpha, beta",
                "price_usd": "6.25",
            },
        )
        html = client.get(f"/product/{ids['pending']}").get_data(as_text=True)
        assert 'value="Prefilled Title Check"' in html
        assert "Prefilled description body." in html
        assert 'value="alpha, beta"' in html
        assert 'value="6.25"' in html
