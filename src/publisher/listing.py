"""Etsy API v3 listing operations — create, upload files/images, activate."""

from __future__ import annotations

import os
from pathlib import Path

import requests
import structlog

from src.publisher.auth import EtsyAuth, EtsyAuthError
from src.utils.rate_limiter import TokenBucketRateLimiter

logger = structlog.get_logger()

ETSY_API_BASE = "https://openapi.etsy.com"


class EtsyAPIError(Exception):
    """Raised when an Etsy API call returns an error."""

    def __init__(self, message: str, status_code: int | None = None, body: str = ""):
        self.status_code = status_code
        self.body = body
        super().__init__(message)


class EtsyListingManager:
    """Manages Etsy listing lifecycle via the v3 REST API."""

    def __init__(self, auth: EtsyAuth, rate_limiter: TokenBucketRateLimiter):
        """Initialize with an EtsyAuth instance and a rate limiter.

        Args:
            auth: Handles OAuth tokens.
            rate_limiter: TokenBucketRateLimiter for request throttling.
        """
        self.auth = auth
        self.rate_limiter = rate_limiter
        self._shop_id_cache: int | None = None
        self._shop_currency_cache: str | None = None

    # ------------------------------------------------------------------
    # Low-level request helper
    # ------------------------------------------------------------------

    def _api_request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        data: dict | None = None,
        files: dict | None = None,
        timeout: int = 30,
    ) -> dict:
        """Send an authenticated request to the Etsy API.

        Acquires a rate-limiter token, attaches the OAuth Bearer header,
        and handles common error patterns.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: API path, e.g. "/v3/application/shops/{shop_id}/listings".
            json_body: JSON-serialisable body for POST/PUT.
            data: Form-encoded body (used with multipart uploads).
            files: Dict of files for multipart uploads.
            timeout: Request timeout in seconds.

        Returns:
            Parsed JSON response dict.

        Raises:
            EtsyAPIError: On non-2xx responses.
            EtsyAuthError: If token retrieval fails.
        """
        if not self.rate_limiter.acquire():
            raise EtsyAPIError("Rate limit exceeded — could not acquire token.", status_code=429)

        access_token = self.auth.get_valid_token()
        # Etsy requires the x-api-key header to be "<keystring>:<shared_secret>"
        # (colon-joined); sending the keystring alone returns 403
        # "Shared secret is required in x-api-key header."
        x_api_key = self.auth.api_key
        if self.auth.shared_secret:
            x_api_key = f"{self.auth.api_key}:{self.auth.shared_secret}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "x-api-key": x_api_key,
        }

        url = f"{ETSY_API_BASE}{path}"

        logger.info(
            "etsy_api_request",
            method=method,
            path=path,
            remaining_daily=self.rate_limiter.remaining_daily,
        )

        try:
            resp = requests.request(
                method=method.upper(),
                url=url,
                headers=headers,
                json=json_body,
                data=data,
                files=files,
                timeout=timeout,
            )
        except requests.ConnectionError as exc:
            logger.error("etsy_api_connection_error", path=path, error=str(exc))
            raise EtsyAPIError(f"Connection error: {exc}") from exc
        except requests.Timeout as exc:
            logger.error("etsy_api_timeout", path=path, timeout=timeout)
            raise EtsyAPIError(f"Request timed out after {timeout}s") from exc

        if resp.status_code == 429:
            logger.warning("etsy_api_rate_limited", path=path)
            raise EtsyAPIError("Etsy rate limit hit (429).", status_code=429, body=resp.text)

        if not resp.ok:
            logger.error(
                "etsy_api_error",
                path=path,
                status=resp.status_code,
                body=resp.text[:500],
            )
            raise EtsyAPIError(
                f"Etsy API error {resp.status_code}: {resp.text[:300]}",
                status_code=resp.status_code,
                body=resp.text,
            )

        # Some endpoints return 204 No Content
        if resp.status_code == 204 or not resp.content:
            return {}

        result = resp.json()
        logger.debug("etsy_api_response", path=path, status=resp.status_code)
        return result

    # ------------------------------------------------------------------
    # Shop discovery
    # ------------------------------------------------------------------

    def get_shop_id(self) -> int:
        """Retrieve the shop ID for the authenticated user.

        Caches the result after the first successful call.

        Returns:
            Etsy shop ID (integer).

        Raises:
            EtsyAPIError: If the user has no shop.
        """
        if self._shop_id_cache is not None:
            return self._shop_id_cache

        # Step 1: /users/me returns the user_id and, for shop owners, the
        # shop_id directly.
        user_resp = self._api_request("GET", "/v3/application/users/me")
        user_id = user_resp.get("user_id")
        if not user_id:
            raise EtsyAPIError("Could not determine user_id from /users/me response.")

        # Fast path: /users/me already carries shop_id for shop owners.
        shop_id = user_resp.get("shop_id")

        # Step 2: fall back to /users/{user_id}/shops. Etsy returns the shop
        # object *directly* for a single-shop user (not wrapped in a "results"
        # envelope); some responses use {"results": [...]} or a bare list.
        # Handle all three shapes -- the previous code assumed only "results"
        # and so raised a false "No shops found" for single-shop accounts.
        if not shop_id:
            shop_resp = self._api_request(
                "GET", f"/v3/application/users/{user_id}/shops"
            )
            if isinstance(shop_resp, dict) and shop_resp.get("results"):
                shop_id = shop_resp["results"][0].get("shop_id")
            elif isinstance(shop_resp, list) and shop_resp:
                shop_id = shop_resp[0].get("shop_id")
            elif isinstance(shop_resp, dict):
                shop_id = shop_resp.get("shop_id")

        if not shop_id:
            raise EtsyAPIError(
                f"No shop found for user {user_id}. Open your Etsy shop first."
            )

        self._shop_id_cache = shop_id
        logger.info("etsy_shop_id_resolved", shop_id=shop_id, user_id=user_id)
        return shop_id

    def get_shop_currency(self) -> str:
        """Return the shop's ISO currency code (e.g. 'USD', 'PHP'), cached.

        Etsy lists prices in the shop's own currency, so callers convert their
        USD-authored prices with this before creating a listing. Defaults to
        'USD' if Etsy omits the field.
        """
        if self._shop_currency_cache is not None:
            return self._shop_currency_cache

        shop_id = self.get_shop_id()
        resp = self._api_request("GET", f"/v3/application/shops/{shop_id}")
        currency = (resp.get("currency_code") or "USD").upper()
        self._shop_currency_cache = currency
        logger.info("etsy_shop_currency_resolved", shop_id=shop_id, currency=currency)
        return currency

    # ------------------------------------------------------------------
    # Create draft listing
    # ------------------------------------------------------------------

    def create_draft_listing(
        self,
        shop_id: int,
        title: str,
        description: str,
        price: float,
        taxonomy_id: int,
        tags: list[str],
    ) -> dict:
        """Create a new draft listing in the given shop.

        The listing is created as a digital download (type=download).

        Args:
            shop_id: Etsy shop ID.
            title: Listing title (<= 140 chars).
            description: Full listing description.
            price: Price in USD.
            taxonomy_id: Etsy taxonomy node ID for the "Planners" category.
            tags: List of up to 13 tags.

        Returns:
            Etsy listing response dict (includes listing_id).
        """
        body = {
            "title": title,
            "description": description,
            "price": price,
            "quantity": 999,
            "taxonomy_id": taxonomy_id,
            "tags": tags,
            "type": "download",
            "who_made": "i_did",
            "when_made": "2020_2025",
            "is_supply": False,
            "should_auto_renew": True,
        }

        result = self._api_request(
            "POST",
            f"/v3/application/shops/{shop_id}/listings",
            json_body=body,
        )
        listing_id = result.get("listing_id")
        logger.info(
            "etsy_draft_listing_created",
            listing_id=listing_id,
            shop_id=shop_id,
            title=title[:60],
        )
        return result

    # ------------------------------------------------------------------
    # Upload digital file (PDF)
    # ------------------------------------------------------------------

    def upload_listing_file(
        self,
        shop_id: int,
        listing_id: int,
        file_path: str,
        *,
        bundle_path: str | None = None,
    ) -> dict:
        """Upload the digital delivery file to an existing listing.

        For a multi-palette colour bundle the buyer must receive the ZIP of
        every palette's PDF, not just the hero PDF.  When *bundle_path* is
        supplied it is uploaded instead of *file_path*; the MIME type is
        derived from the chosen file's extension (``.zip`` uploads as
        ``application/zip``, everything else as ``application/pdf``).  This
        keeps single-PDF planners and picture books (no ``bundle_path``)
        behaving exactly as before.

        Args:
            shop_id: Etsy shop ID.
            listing_id: The listing to attach the file to.
            file_path: Path to the hero PDF (``product.pdf_path``).
            bundle_path: Optional path to the palette-bundle ZIP
                (``product.bundle_path``); takes precedence when set.

        Returns:
            Etsy file upload response dict.
        """
        chosen = bundle_path or file_path
        path_obj = Path(chosen)
        if not path_obj.exists():
            raise FileNotFoundError(f"File not found: {chosen}")

        mime_type = (
            "application/zip"
            if path_obj.suffix.lower() == ".zip"
            else "application/pdf"
        )

        file_name = path_obj.name
        with open(path_obj, "rb") as fh:
            files = {"file": (file_name, fh, mime_type)}
            # Etsy's uploadListingFile requires the file name as a separate
            # "name" form field when uploading a NEW file; without it the API
            # returns 400 "A valid name must be provided with a new file."
            data = {"name": file_name}
            result = self._api_request(
                "POST",
                f"/v3/application/shops/{shop_id}/listings/{listing_id}/files",
                data=data,
                files=files,
            )

        logger.info(
            "etsy_file_uploaded",
            listing_id=listing_id,
            file=file_name,
            mime_type=mime_type,
            size_bytes=path_obj.stat().st_size,
        )
        return result

    # ------------------------------------------------------------------
    # Upload listing image (mockup)
    # ------------------------------------------------------------------

    def upload_listing_image(
        self,
        shop_id: int,
        listing_id: int,
        image_path: str,
        rank: int = 1,
    ) -> dict:
        """Upload a mockup / listing image.

        Args:
            shop_id: Etsy shop ID.
            listing_id: Listing to attach image to.
            image_path: Path to an image file (PNG/JPG).
            rank: Image display order (1 = primary thumbnail).

        Returns:
            Etsy image upload response dict.
        """
        path_obj = Path(image_path)
        if not path_obj.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        # Determine MIME type from extension
        ext = path_obj.suffix.lower()
        mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
        mime_type = mime_map.get(ext, "image/png")

        with open(path_obj, "rb") as fh:
            files = {"image": (path_obj.name, fh, mime_type)}
            data = {"rank": str(rank)}
            result = self._api_request(
                "POST",
                f"/v3/application/shops/{shop_id}/listings/{listing_id}/images",
                data=data,
                files=files,
            )

        logger.info(
            "etsy_image_uploaded",
            listing_id=listing_id,
            image=path_obj.name,
            rank=rank,
        )
        return result

    # ------------------------------------------------------------------
    # Activate listing
    # ------------------------------------------------------------------

    def activate_listing(self, shop_id: int, listing_id: int) -> dict:
        """Activate a draft listing (makes it publicly visible).

        Etsy charges a $0.20 listing fee when activating.

        Args:
            shop_id: Etsy shop ID.
            listing_id: Draft listing to activate.

        Returns:
            Updated listing response dict.
        """
        # Etsy v3 updateListing is a PATCH; a PUT on this path returns 404
        # "Resource not found" (the method+path combo isn't routed).
        result = self._api_request(
            "PATCH",
            f"/v3/application/shops/{shop_id}/listings/{listing_id}",
            json_body={"state": "active"},
        )
        logger.info("etsy_listing_activated", listing_id=listing_id, shop_id=shop_id)
        return result
