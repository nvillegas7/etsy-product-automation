"""Dashboard surface for palette-bundle planners.

Detail page shows the bundled palettes (swatches + names) and offers a
bundle-ZIP download; the index card flags the colour count.  Everything
stays read-only and approval-gated.
"""

from __future__ import annotations

import json
import zipfile

from src.storage.models import Niche, ProductState
from src.storage.repository import ProductRepository


def _make_bundle_zip(path) -> bytes:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("2026_Budget_Planner_ocean_blue.pdf", b"%PDF-1.4 a")
        zf.writestr("2026_Budget_Planner_soft_sage.pdf", b"%PDF-1.4 b")
    return path.read_bytes()


def _create_bundle_product(session_factory, tmp_path):
    """Insert a REVIEW_PENDING planner with a real, resolvable bundle ZIP."""
    zip_path = tmp_path / "bundle.zip"
    zip_bytes = _make_bundle_zip(zip_path)

    session = session_factory()
    try:
        niche_id = session.query(Niche).first().id
        product = ProductRepository(session).create(
            niche_id=niche_id,
            product_type="planner",
            title="2026 Bundle Planner Digital Planner | iPad GoodNotes",
            display_title="2026 Bundle Planner",
            palette_name="ocean_blue",
            palettes=json.dumps(["ocean_blue", "soft_sage", "dusty_rose"]),
            bundle_path=str(zip_path),
            year=2026,
            price_usd=6.99,
            state=ProductState.REVIEW_PENDING,
        )
        return product.id, zip_bytes
    finally:
        session.close()


class TestBundleDetail:
    def test_detail_shows_palette_swatches_and_names(self, dashboard, tmp_path):
        client, _, session_factory = dashboard
        pid, _ = _create_bundle_product(session_factory, tmp_path)

        html = client.get(f"/product/{pid}").get_data(as_text=True)
        assert "Color options" in html
        assert "3 colors" in html
        # Human palette names + a hero swatch hex (Ocean Blue primary).
        assert "Ocean Blue" in html
        assert "Soft Sage" in html
        assert "Dusty Rose" in html
        assert "#4A7C8F" in html  # ocean_blue primary swatch
        # Download button for the bundle ZIP.
        assert f"/files/bundle/{pid}" in html

    def test_index_card_shows_color_count(self, dashboard, tmp_path):
        client, _, session_factory = dashboard
        _create_bundle_product(session_factory, tmp_path)
        html = client.get("/").get_data(as_text=True)
        assert "3 colors" in html


class TestBundleDownloadRoute:
    def test_bundle_route_returns_zip(self, dashboard, tmp_path):
        client, _, session_factory = dashboard
        pid, zip_bytes = _create_bundle_product(session_factory, tmp_path)

        resp = client.get(f"/files/bundle/{pid}")
        assert resp.status_code == 200
        assert resp.mimetype == "application/zip"
        assert resp.get_data() == zip_bytes

    def test_bundle_route_404_without_bundle(self, dashboard):
        """A single-palette product has no bundle to download."""
        client, ids, _ = dashboard
        assert client.get(f"/files/bundle/{ids['pending']}").status_code == 404

    def test_bundle_route_404_for_unknown_product(self, dashboard):
        client, _, _ = dashboard
        assert client.get("/files/bundle/99999").status_code == 404
