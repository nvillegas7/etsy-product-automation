"""Internet-exposure hardening for the dashboard (it approves + publishes to
the live Etsy shop, and publishing incurs listing fees).

Guards: constant-time Basic-Auth check, per-client brute-force throttle
(Cloudflare client IP trusted only from loopback), same-origin enforcement
on state-changing requests, security headers, unpredictable secret key.
"""

from __future__ import annotations

import base64

import pytest

from src.storage.database import get_session_factory, init_db, reset_engine
from tests.dashboard.conftest import _seed

PASSWORD = "correct-horse-battery-staple"


def _basic(user: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture()
def secured(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", PASSWORD)
    monkeypatch.setenv("DASHBOARD_AUTH_MAX_FAILURES", "3")
    monkeypatch.delenv("DASHBOARD_SECRET_KEY", raising=False)
    reset_engine()
    init_db(f"sqlite:///{tmp_path}/test.db")
    ids = _seed(get_session_factory())
    from src.dashboard.app import create_app

    app = create_app({
        "etsy": {"upload_enabled": False},
        "paths": {"database": str(tmp_path / "test.db"),
                  "preview_dir": str(tmp_path / "previews")},
    })
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield app, client, ids
    reset_engine()


class TestBasicAuth:
    def test_no_credentials_is_challenged(self, secured):
        _, client, _ = secured
        r = client.get("/")
        assert r.status_code == 401
        assert "Basic" in r.headers["WWW-Authenticate"]

    def test_wrong_password_rejected_right_password_accepted(self, secured):
        _, client, _ = secured
        assert client.get("/", headers=_basic("admin", "nope")).status_code == 401
        assert client.get("/", headers=_basic("admin", PASSWORD)).status_code == 200

    def test_secret_key_is_not_the_old_predictable_default(self, secured):
        app, _, _ = secured
        assert app.secret_key != "product-studio-local"
        assert len(app.secret_key) >= 32


class TestBruteForceThrottle:
    def test_lockout_after_repeated_failures_even_for_right_password(self, secured):
        _, client, _ = secured
        for _ in range(3):
            assert client.get("/", headers=_basic("admin", "bad")).status_code == 401
        r = client.get("/", headers=_basic("admin", PASSWORD))
        assert r.status_code == 429
        assert "Retry-After" in r.headers

    def test_unauthenticated_challenges_do_not_count(self, secured):
        _, client, _ = secured
        for _ in range(10):
            assert client.get("/").status_code == 401  # browser prompt round-trips
        assert client.get("/", headers=_basic("admin", PASSWORD)).status_code == 200

    def test_cloudflare_client_ip_separates_buckets_from_loopback(self, secured):
        _, client, _ = secured
        attacker = {"CF-Connecting-IP": "203.0.113.9", **_basic("admin", "bad")}
        for _ in range(3):
            client.get("/", headers=attacker)
        assert client.get("/", headers={"CF-Connecting-IP": "203.0.113.9",
                                        **_basic("admin", PASSWORD)}).status_code == 429
        owner = {"CF-Connecting-IP": "198.51.100.7", **_basic("admin", PASSWORD)}
        assert client.get("/", headers=owner).status_code == 200

    def test_forwarded_ip_header_is_ignored_from_non_loopback_peers(self, secured):
        _, client, _ = secured
        # A LAN client spoofing CF-Connecting-IP must not be able to pick a
        # fresh bucket: failures are keyed on its real peer address.
        lan = {"REMOTE_ADDR": "192.168.1.50"}
        for i in range(3):
            client.get("/", headers={"CF-Connecting-IP": f"10.0.0.{i}",
                                     **_basic("admin", "bad")}, environ_base=lan)
        r = client.get("/", headers={"CF-Connecting-IP": "10.0.0.99",
                                     **_basic("admin", PASSWORD)}, environ_base=lan)
        assert r.status_code == 429


class TestSameOriginWrites:
    def test_cross_site_origin_is_refused(self, secured):
        _, client, ids = secured
        r = client.post(f"/product/{ids['pending']}/approve",
                        headers={"Origin": "https://evil.example",
                                 **_basic("admin", PASSWORD)})
        assert r.status_code == 403

    def test_fetch_metadata_cross_site_is_refused(self, secured):
        _, client, ids = secured
        r = client.post(f"/product/{ids['pending']}/approve",
                        headers={"Sec-Fetch-Site": "cross-site",
                                 **_basic("admin", PASSWORD)})
        assert r.status_code == 403

    def test_null_origin_is_refused(self, secured):
        _, client, ids = secured
        r = client.post(f"/product/{ids['pending']}/approve",
                        headers={"Origin": "null", **_basic("admin", PASSWORD)})
        assert r.status_code == 403

    def test_same_origin_form_post_is_allowed(self, secured):
        _, client, ids = secured
        r = client.post(f"/product/{ids['pending']}/re-review",
                        headers={"Origin": "http://localhost",
                                 "Referer": "http://localhost/product/1",
                                 **_basic("admin", PASSWORD)})
        assert r.status_code != 403

    def test_reads_are_not_origin_checked(self, secured):
        _, client, _ = secured
        r = client.get("/", headers={"Origin": "https://evil.example",
                                     **_basic("admin", PASSWORD)})
        assert r.status_code == 200


class TestSecurityHeaders:
    def test_headers_present_on_pages(self, secured):
        _, client, _ = secured
        r = client.get("/", headers=_basic("admin", PASSWORD))
        assert r.headers["X-Frame-Options"] == "DENY"
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        assert r.headers["Referrer-Policy"] == "same-origin"
        assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
        assert r.headers["Strict-Transport-Security"].startswith("max-age=")
        assert r.headers["Cache-Control"] == "no-store"

    def test_headers_present_on_auth_challenge_too(self, secured):
        _, client, _ = secured
        r = client.get("/")
        assert r.status_code == 401 and r.headers["X-Frame-Options"] == "DENY"
