"""Tests for typed generation buttons and publish-on-approve behavior."""

import time

import pytest

import src.dashboard.app as dashboard_app
from src.publisher.uploader import PublishError
from src.storage.database import get_session_factory, init_db, reset_engine
from src.storage.models import Product, ProductState

from tests.dashboard.conftest import _seed


def _wait_for_generation_thread(timeout: float = 5.0) -> None:
    """Block until the background generation thread releases the lock."""
    deadline = time.time() + timeout
    while dashboard_app._generation_lock.locked() and time.time() < deadline:
        time.sleep(0.01)
    assert not dashboard_app._generation_lock.locked(), "generation lock stuck"


def _get_product(session_factory, product_id: int) -> Product:
    session = session_factory()
    try:
        product = session.get(Product, product_id)
        session.refresh(product)
        return product
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Uploads-enabled app fixture (conftest's `dashboard` keeps uploads disabled)
# ---------------------------------------------------------------------------


def _make_client(tmp_path, etsy_config: dict):
    reset_engine()
    init_db(f"sqlite:///{tmp_path}/test.db")
    session_factory = get_session_factory()
    ids = _seed(session_factory)

    config = {
        "etsy": etsy_config,
        "paths": {
            "database": str(tmp_path / "test.db"),
            "preview_dir": str(tmp_path / "previews"),
        },
    }
    app = dashboard_app.create_app(config)
    app.config["TESTING"] = True
    return app.test_client(), ids, session_factory


@pytest.fixture()
def uploads_enabled(tmp_path, monkeypatch):
    """Client whose config arms uploads (credentials via env)."""
    monkeypatch.setenv("ETSY_API_KEY", "test-key")
    monkeypatch.setenv("ETSY_SHARED_SECRET", "test-secret")
    monkeypatch.delenv("ETSY_UPLOAD_ENABLED", raising=False)
    client, ids, session_factory = _make_client(
        tmp_path, {"upload_enabled": True, "publish_on_approve": True}
    )
    yield client, ids, session_factory
    reset_engine()


@pytest.fixture()
def uploads_enabled_no_autopublish(tmp_path, monkeypatch):
    monkeypatch.setenv("ETSY_API_KEY", "test-key")
    monkeypatch.setenv("ETSY_SHARED_SECRET", "test-secret")
    monkeypatch.delenv("ETSY_UPLOAD_ENABLED", raising=False)
    client, ids, session_factory = _make_client(
        tmp_path, {"upload_enabled": True, "publish_on_approve": False}
    )
    yield client, ids, session_factory
    reset_engine()


# ---------------------------------------------------------------------------
# /generate type wiring
# ---------------------------------------------------------------------------


class TestGenerateTypes:
    def test_generate_picture_book_passes_type_to_run_once(
        self, dashboard, monkeypatch
    ):
        client, _, _ = dashboard
        recorded = {}

        def fake_run_once(self, product_type=None):
            recorded["product_type"] = product_type
            return None

        monkeypatch.setattr(
            "src.pipeline.orchestrator.PipelineOrchestrator.run_once", fake_run_once
        )

        resp = client.post(
            "/generate", data={"type": "picture_book"}, follow_redirects=True
        )
        assert resp.status_code == 200
        assert "Picture book generation started" in resp.get_data(as_text=True)
        _wait_for_generation_thread()
        assert recorded["product_type"] == "picture_book"

    def test_generate_planner_passes_type_to_run_once(self, dashboard, monkeypatch):
        client, _, _ = dashboard
        recorded = {}

        def fake_run_once(self, product_type=None):
            recorded["product_type"] = product_type
            return None

        monkeypatch.setattr(
            "src.pipeline.orchestrator.PipelineOrchestrator.run_once", fake_run_once
        )

        resp = client.post("/generate", data={"type": "planner"}, follow_redirects=True)
        assert "Planner generation started" in resp.get_data(as_text=True)
        _wait_for_generation_thread()
        assert recorded["product_type"] == "planner"

    def test_generate_without_type_runs_auto_rotation(self, dashboard, monkeypatch):
        client, _, _ = dashboard
        recorded = {}

        def fake_run_generation(config, session_factory, product_type=None):
            recorded["product_type"] = product_type
            dashboard_app._generation_lock.release()

        monkeypatch.setattr(dashboard_app, "_run_generation", fake_run_generation)

        client.post("/generate", follow_redirects=True)
        _wait_for_generation_thread()
        assert recorded["product_type"] is None

    def test_index_has_both_generate_buttons(self, dashboard):
        client, _, _ = dashboard
        html = client.get("/").get_data(as_text=True)
        assert "Generate planner" in html
        assert "Generate picture book" in html
        assert 'value="picture_book"' in html

    def test_picture_book_filter_makes_book_button_primary(self, dashboard):
        client, _, _ = dashboard
        html = client.get("/?ptype=picture_book").get_data(as_text=True)
        # The dark (primary) button must be the picture-book one.
        planner_form, _, book_form = html.partition('value="picture_book"')
        assert "btn-dark" in book_form.split("</form>")[0]
        assert "btn-outline" in planner_form.split('value="planner"')[1].split("</form>")[0]


# ---------------------------------------------------------------------------
# Publish on approve
# ---------------------------------------------------------------------------


class TestPublishOnApprove:
    def test_approve_with_uploads_disabled_stays_approved(self, dashboard):
        """Current situation: approve parks the product, message explains."""
        client, ids, session_factory = dashboard
        resp = client.post(
            f"/product/{ids['pending']}/approve", follow_redirects=True
        )
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "uploads are currently disabled" in html
        assert "will need publishing once Etsy access is enabled" in html
        product = _get_product(session_factory, ids["pending"])
        assert product.state == ProductState.APPROVED

    def test_approve_publishes_when_uploads_enabled(
        self, uploads_enabled, monkeypatch
    ):
        client, ids, session_factory = uploads_enabled
        published = []

        def fake_publish_approved(self, product_id):
            published.append(product_id)
            session = session_factory()
            try:
                product = session.get(Product, product_id)
                product.state = ProductState.PUBLISHED
                session.commit()
                return product
            finally:
                session.close()

        monkeypatch.setattr(
            "src.pipeline.orchestrator.PipelineOrchestrator.publish_approved",
            fake_publish_approved,
        )

        resp = client.post(
            f"/product/{ids['pending']}/approve", follow_redirects=True
        )
        assert resp.status_code == 200
        assert "approved and published to Etsy" in resp.get_data(as_text=True)
        assert published == [ids["pending"]]
        product = _get_product(session_factory, ids["pending"])
        assert product.state == ProductState.PUBLISHED

    def test_publish_failure_leaves_product_approved(
        self, uploads_enabled, monkeypatch
    ):
        """A failed upload must keep the product retryable via Publish."""
        client, ids, session_factory = uploads_enabled

        def failing_publish_approved(self, product_id):
            # Mimic the real uploader's failure handling: mark FAILED, raise.
            session = session_factory()
            try:
                product = session.get(Product, product_id)
                product.state = ProductState.FAILED
                session.commit()
            finally:
                session.close()
            raise PublishError("etsy exploded")

        monkeypatch.setattr(
            "src.pipeline.orchestrator.PipelineOrchestrator.publish_approved",
            failing_publish_approved,
        )

        resp = client.post(
            f"/product/{ids['pending']}/approve", follow_redirects=True
        )
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "publishing failed" in html
        assert "etsy exploded" in html
        product = _get_product(session_factory, ids["pending"])
        assert product.state == ProductState.APPROVED

    def test_publish_on_approve_false_skips_publish(
        self, uploads_enabled_no_autopublish, monkeypatch
    ):
        client, ids, session_factory = uploads_enabled_no_autopublish
        published = []
        monkeypatch.setattr(
            "src.pipeline.orchestrator.PipelineOrchestrator.publish_approved",
            lambda self, product_id: published.append(product_id),
        )

        resp = client.post(
            f"/product/{ids['pending']}/approve", follow_redirects=True
        )
        assert resp.status_code == 200
        assert published == []
        product = _get_product(session_factory, ids["pending"])
        assert product.state == ProductState.APPROVED
