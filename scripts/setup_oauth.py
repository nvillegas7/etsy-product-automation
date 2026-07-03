"""Interactive one-time OAuth 2.0 PKCE setup for Etsy.

Run with:
    python -m scripts.setup_oauth

Flow:
    1. Load ETSY_API_KEY and ETSY_SHARED_SECRET from .env.
    2. Generate a PKCE code_verifier + code_challenge.
    3. Print the authorization URL for the user to open in a browser.
    4. Start a local HTTP server on port 3003 to capture the callback.
    5. Exchange the authorization code for tokens.
    6. Save tokens to the SQLite database.
    7. Print a success message.
"""

from __future__ import annotations

import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

# Ensure project root is on the path so imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.monitoring.logger import setup_logging
from src.publisher.auth import EtsyAuth, EtsyAuthError
from src.storage.database import get_session_factory, init_db

REDIRECT_PORT = 3003
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler that captures the OAuth callback query parameters."""

    auth_code: str | None = None
    state: str | None = None
    error: str | None = None
    _event: threading.Event | None = None

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "error" in params:
            _OAuthCallbackHandler.error = params["error"][0]
            self._respond("Authorization failed. You can close this tab.")
        elif "code" in params:
            _OAuthCallbackHandler.auth_code = params["code"][0]
            _OAuthCallbackHandler.state = params.get("state", [None])[0]
            self._respond(
                "Authorization successful! You can close this tab "
                "and return to the terminal."
            )
        else:
            self._respond("Missing authorization code. Please try again.")

        # Signal the main thread
        if _OAuthCallbackHandler._event is not None:
            _OAuthCallbackHandler._event.set()

    def _respond(self, message: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        html = (
            f"<html><body style='font-family:sans-serif;text-align:center;"
            f"padding:60px;'><h2>{message}</h2></body></html>"
        )
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):  # noqa: A002
        # Silence default HTTP request logging
        pass


def main():
    load_dotenv()
    logger = setup_logging()

    api_key = os.getenv("ETSY_API_KEY", "").strip()
    shared_secret = os.getenv("ETSY_SHARED_SECRET", "").strip()

    if not api_key:
        print("ERROR: ETSY_API_KEY not found in .env file.")
        print("Create a .env file in the project root with:")
        print("  ETSY_API_KEY=your_etsy_api_keystring")
        print("  ETSY_SHARED_SECRET=your_etsy_shared_secret")
        sys.exit(1)

    # Initialise the database (creates tables if needed)
    init_db()
    session_factory = get_session_factory()
    session = session_factory()

    auth = EtsyAuth(api_key=api_key, shared_secret=shared_secret, session=session)

    # ---- Step 1: Generate PKCE pair ----
    code_verifier, code_challenge = EtsyAuth.generate_pkce_pair()

    # ---- Step 2: Build auth URL ----
    auth_url = auth.get_auth_url(
        code_challenge=code_challenge,
        redirect_uri=REDIRECT_URI,
        scopes=["listings_w", "listings_r", "listings_d"],
    )

    print()
    print("=" * 60)
    print("  Etsy OAuth 2.0 Setup (PKCE)")
    print("=" * 60)
    print()
    print("Open this URL in your browser to authorize the app:")
    print()
    print(f"  {auth_url}")
    print()
    print(f"Waiting for callback on http://localhost:{REDIRECT_PORT}/callback ...")
    print()

    # ---- Step 3: Start local callback server ----
    done_event = threading.Event()
    _OAuthCallbackHandler._event = done_event
    _OAuthCallbackHandler.auth_code = None
    _OAuthCallbackHandler.error = None

    server = HTTPServer(("0.0.0.0", REDIRECT_PORT), _OAuthCallbackHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    # Block until we receive the callback
    try:
        done_event.wait(timeout=300)  # 5-minute timeout
    except KeyboardInterrupt:
        print("\nSetup cancelled by user.")
        server.shutdown()
        sys.exit(1)

    server.shutdown()

    if _OAuthCallbackHandler.error:
        print(f"Authorization error: {_OAuthCallbackHandler.error}")
        sys.exit(1)

    auth_code = _OAuthCallbackHandler.auth_code
    if not auth_code:
        print("No authorization code received (timed out after 5 minutes).")
        sys.exit(1)

    # ---- Step 4: Exchange code for tokens ----
    print("Exchanging authorization code for tokens...")
    try:
        token_data = auth.exchange_code(
            auth_code=auth_code,
            code_verifier=code_verifier,
            redirect_uri=REDIRECT_URI,
        )
    except EtsyAuthError as exc:
        print(f"Token exchange failed: {exc}")
        sys.exit(1)

    # ---- Step 5: Save tokens to DB ----
    auth.save_tokens(token_data)

    print()
    print("=" * 60)
    print("  SUCCESS — Etsy OAuth tokens saved!")
    print("=" * 60)
    print()
    print(f"  Access token expires in {token_data.get('expires_in', '?')} seconds.")
    print("  Tokens are stored in the SQLite database and will")
    print("  auto-refresh when needed.")
    print()

    session.close()


if __name__ == "__main__":
    main()
