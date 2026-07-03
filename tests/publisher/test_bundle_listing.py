"""Bundle-aware digital delivery: upload the ZIP, describe the colours.

- ``EtsyListingManager.upload_listing_file`` uploads the palette-bundle ZIP
  (as ``application/zip``) when ``bundle_path`` is given, else the hero PDF.
- ``ListingSEO.generate_description`` names every colourway in the bundle.
"""

from __future__ import annotations

import zipfile

import pytest

from src.publisher.listing import EtsyListingManager
from src.publisher.seo import ListingSEO


class _StubAuth:
    api_key = "test-key"

    def get_valid_token(self) -> str:  # pragma: no cover - never hit
        return "token"


class _StubRateLimiter:
    remaining_daily = 100

    def acquire(self) -> bool:  # pragma: no cover - never hit
        return True


@pytest.fixture()
def manager():
    mgr = EtsyListingManager(auth=_StubAuth(), rate_limiter=_StubRateLimiter())
    calls: list[dict] = []

    def _fake_api_request(method, path, *, files=None, **kwargs):
        # The file handle is captured while still open inside the method.
        name, fh, mime = files["file"]
        calls.append({"method": method, "path": path, "name": name, "mime": mime})
        return {}

    mgr._api_request = _fake_api_request  # type: ignore[assignment]
    return mgr, calls


@pytest.fixture()
def pdf_file(tmp_path):
    p = tmp_path / "2026_Budget_Planner_ocean_blue.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    return p


@pytest.fixture()
def zip_file(tmp_path, pdf_file):
    z = tmp_path / "2026_Budget_Planner_bundle.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.write(pdf_file, arcname=pdf_file.name)
    return z


class TestUploadDeliveryFile:
    def test_uploads_pdf_when_no_bundle(self, manager, pdf_file):
        mgr, calls = manager
        mgr.upload_listing_file(111, 222, str(pdf_file))
        assert calls[0]["name"] == pdf_file.name
        assert calls[0]["mime"] == "application/pdf"

    def test_uploads_zip_when_bundle_present(self, manager, pdf_file, zip_file):
        mgr, calls = manager
        mgr.upload_listing_file(111, 222, str(pdf_file), bundle_path=str(zip_file))
        # The ZIP is delivered instead of the hero PDF.
        assert calls[0]["name"] == zip_file.name
        assert calls[0]["mime"] == "application/zip"

    def test_missing_bundle_raises(self, manager, pdf_file, tmp_path):
        mgr, _ = manager
        with pytest.raises(FileNotFoundError):
            mgr.upload_listing_file(
                111, 222, str(pdf_file), bundle_path=str(tmp_path / "nope.zip")
            )


class TestDescriptionColorOptions:
    def test_names_every_bundled_palette(self):
        desc = ListingSEO().generate_description(
            niche_config={"name": "Budget Planner"},
            year=2026,
            palettes=["ocean_blue", "soft_sage", "dusty_rose"],
        )
        assert (
            "3 color options included: Ocean Blue, Soft Sage, Dusty Rose" in desc
        )

    def test_single_palette_has_no_color_section(self):
        desc = ListingSEO().generate_description(
            niche_config={"name": "Budget Planner"},
            year=2026,
            palettes=["ocean_blue"],
        )
        assert "color options included" not in desc

    def test_no_palettes_arg_is_unchanged(self):
        desc = ListingSEO().generate_description(
            niche_config={"name": "Budget Planner"}, year=2026
        )
        assert "color options included" not in desc
