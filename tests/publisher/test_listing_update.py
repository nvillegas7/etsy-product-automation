"""Tests for updating an existing Etsy listing.

Text fields (title/description/tags) go via updateListing (PATCH); price goes
via the inventory endpoint because Etsy ignores updateListing's price once a
listing has inventory.
"""

from src.publisher.listing import EtsyListingManager


class _RecordingManager(EtsyListingManager):
    """EtsyListingManager with _api_request stubbed to record calls."""

    def __init__(self, inventory: dict | None = None):
        self.auth = None
        self.rate_limiter = None
        self._shop_id_cache = 1
        self._shop_currency_cache = "PHP"
        self._inventory = inventory or {}
        self.calls: list[tuple] = []

    def _api_request(self, method, path, *, json_body=None, data=None, files=None, timeout=30):
        self.calls.append((method, path, json_body))
        if method == "GET" and path.endswith("/inventory"):
            return self._inventory
        return {}


def test_update_listing_sends_only_text_fields():
    m = _RecordingManager()
    m.update_listing(1, 99, title="T", description="D", tags=["a", "b"])
    method, path, body = m.calls[-1]
    assert method == "PATCH"
    assert path.endswith("/shops/1/listings/99")
    assert body == {"title": "T", "description": "D", "tags": ["a", "b"]}
    assert "price" not in body  # price never goes through updateListing


def test_update_listing_is_noop_without_fields():
    m = _RecordingManager()
    assert m.update_listing(1, 99) == {}
    assert m.calls == []


def test_update_listing_price_rewrites_offerings_via_inventory():
    inv = {
        "products": [
            {
                "sku": "SKU1",
                "property_values": [],
                "offerings": [
                    {
                        "price": {"amount": 33500, "divisor": 100, "currency_code": "PHP"},
                        "quantity": 999,
                        "is_enabled": True,
                        "offering_id": 7,  # read-only -- must be dropped on PUT
                    }
                ],
            }
        ]
    }
    m = _RecordingManager(inv)
    m.update_listing_price(99, 391.44)

    assert m.calls[0][0] == "GET"  # reads current inventory first
    method, path, body = m.calls[-1]
    assert method == "PUT"
    assert path.endswith("/listings/99/inventory")
    product = body["products"][0]
    assert product["sku"] == "SKU1"
    # Offering rewritten to the new price, quantity/availability preserved,
    # read-only offering_id stripped.
    assert product["offerings"][0] == {
        "price": 391.44,
        "quantity": 999,
        "is_enabled": True,
    }


def test_update_listing_price_preserves_variation_property_values():
    inv = {
        "products": [
            {
                "sku": "",
                "property_values": [
                    {
                        "property_id": 200,
                        "value_ids": [1],
                        "values": ["A4"],
                        "scale_id": None,
                        "property_name": "Size",  # extra field, should be dropped
                    }
                ],
                "offerings": [{"price": {"amount": 500, "divisor": 100}, "quantity": 1, "is_enabled": True}],
            }
        ]
    }
    m = _RecordingManager(inv)
    m.update_listing_price(99, 10.0)
    body = m.calls[-1][2]
    pv = body["products"][0]["property_values"][0]
    assert pv == {"property_id": 200, "value_ids": [1], "values": ["A4"]}
