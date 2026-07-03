"""Etsy OAuth 2.0 PKCE authentication and token management."""

import base64
import hashlib
import os
import secrets
from datetime import datetime

import requests
import structlog

from src.storage.repository import EtsyTokenRepository

logger = structlog.get_logger()

ETSY_AUTH_URL = "https://www.etsy.com/oauth/connect"
ETSY_TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"


class EtsyAuthError(Exception):
    """Raised when Etsy authentication fails."""


class EtsyAuth:
    """Handles Etsy OAuth 2.0 PKCE flow and token lifecycle."""

    def __init__(self, api_key: str, shared_secret: str, session):
        """Initialize with Etsy API credentials and a SQLAlchemy session.

        Args:
            api_key: Etsy API key (keystring / client_id).
            shared_secret: Etsy app shared secret (not used in PKCE but
                kept for potential future needs like webhook verification).
            session: SQLAlchemy Session instance for token persistence.
        """
        self.api_key = api_key
        self.shared_secret = shared_secret
        self.session = session
        self.token_repo = EtsyTokenRepository(session)

    # ------------------------------------------------------------------
    # PKCE helpers
    # ------------------------------------------------------------------

    @staticmethod
    def generate_pkce_pair() -> tuple[str, str]:
        """Generate a PKCE code_verifier and code_challenge (S256).

        Returns:
            Tuple of (code_verifier, code_challenge).
        """
        code_verifier = secrets.token_urlsafe(64)[:128]
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = (
            base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        )
        return code_verifier, code_challenge

    # ------------------------------------------------------------------
    # Authorization URL
    # ------------------------------------------------------------------

    def get_auth_url(
        self,
        code_challenge: str,
        redirect_uri: str,
        scopes: list[str] | None = None,
    ) -> str:
        """Build the Etsy OAuth authorization URL.

        Args:
            code_challenge: PKCE S256 challenge string.
            redirect_uri: Registered callback URI.
            scopes: OAuth scopes; defaults to listings_w, listings_r, listings_d.

        Returns:
            Fully-formed authorization URL the user should open in a browser.
        """
        if scopes is None:
            scopes = ["listings_w", "listings_r", "listings_d"]

        state = secrets.token_urlsafe(24)
        scope_str = " ".join(scopes)

        params = (
            f"response_type=code"
            f"&client_id={self.api_key}"
            f"&redirect_uri={redirect_uri}"
            f"&scope={scope_str}"
            f"&code_challenge={code_challenge}"
            f"&code_challenge_method=S256"
            f"&state={state}"
        )
        url = f"{ETSY_AUTH_URL}?{params}"
        logger.info("etsy_auth_url_generated", redirect_uri=redirect_uri, scopes=scopes)
        return url

    # ------------------------------------------------------------------
    # Token exchange
    # ------------------------------------------------------------------

    def exchange_code(
        self,
        auth_code: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> dict:
        """Exchange an authorization code for access + refresh tokens.

        Args:
            auth_code: The authorization code from the callback.
            code_verifier: The original PKCE code_verifier.
            redirect_uri: Must match the redirect_uri used in the auth URL.

        Returns:
            Token response dict with access_token, refresh_token, expires_in.

        Raises:
            EtsyAuthError: If the token request fails.
        """
        payload = {
            "grant_type": "authorization_code",
            "client_id": self.api_key,
            "redirect_uri": redirect_uri,
            "code": auth_code,
            "code_verifier": code_verifier,
        }

        logger.info("etsy_token_exchange", grant_type="authorization_code")
        try:
            resp = requests.post(ETSY_TOKEN_URL, json=payload, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error(
                "etsy_token_exchange_failed",
                status=getattr(exc.response, "status_code", None),
                body=getattr(exc.response, "text", str(exc)),
            )
            raise EtsyAuthError(f"Token exchange failed: {exc}") from exc

        token_data = resp.json()
        logger.info(
            "etsy_token_exchange_success",
            expires_in=token_data.get("expires_in"),
        )
        return token_data

    # ------------------------------------------------------------------
    # Token refresh
    # ------------------------------------------------------------------

    def refresh_token(self, refresh_token_str: str) -> dict:
        """Refresh an expired access token.

        Args:
            refresh_token_str: The refresh_token from a previous token response.

        Returns:
            New token response dict.

        Raises:
            EtsyAuthError: If the refresh request fails.
        """
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.api_key,
            "refresh_token": refresh_token_str,
        }

        logger.info("etsy_token_refresh")
        try:
            resp = requests.post(ETSY_TOKEN_URL, json=payload, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error(
                "etsy_token_refresh_failed",
                status=getattr(exc.response, "status_code", None),
                body=getattr(exc.response, "text", str(exc)),
            )
            raise EtsyAuthError(f"Token refresh failed: {exc}") from exc

        token_data = resp.json()
        logger.info(
            "etsy_token_refresh_success",
            expires_in=token_data.get("expires_in"),
        )
        return token_data

    # ------------------------------------------------------------------
    # Token persistence
    # ------------------------------------------------------------------

    def save_tokens(self, token_data: dict) -> None:
        """Persist token data to the database.

        Args:
            token_data: Dict with access_token, refresh_token, expires_in,
                and optionally token_type.
        """
        self.token_repo.save_token(
            access_token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
            expires_in=token_data["expires_in"],
            token_type=token_data.get("token_type", "Bearer"),
        )
        logger.info("etsy_tokens_saved")

    # ------------------------------------------------------------------
    # Get a valid access token (auto-refresh if expired)
    # ------------------------------------------------------------------

    def get_valid_token(self) -> str:
        """Return a valid access token, refreshing if necessary.

        Loads the most recent token from the database. If the token is
        expired (or will expire within 60 seconds), refreshes it and
        saves the new token pair.

        Returns:
            A valid access_token string.

        Raises:
            EtsyAuthError: If no tokens exist or refresh fails.
        """
        token = self.token_repo.get_latest()
        if token is None:
            raise EtsyAuthError(
                "No Etsy tokens found. Run `python -m scripts.setup_oauth` first."
            )

        # Refresh if expired or expiring within 60 seconds
        if self.token_repo.is_expired(token):
            logger.info("etsy_token_expired_refreshing")
            new_token_data = self.refresh_token(token.refresh_token)
            self.save_tokens(new_token_data)
            return new_token_data["access_token"]

        return token.access_token
