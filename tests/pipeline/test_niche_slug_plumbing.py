"""The niche slug must survive the trip from niches.yaml to the generator.

Regression for the Sep-2026 travel/wedding rejections: the orchestrator handed
``PlannerSpec`` a slug DERIVED FROM THE DISPLAY NAME ("Wedding Planner" ->
"wedding_planner") while the registry key -- the thing the generator looks
niche pages and motif policy up by -- was ``wedding``.  Every niche whose key
is not name-shaped shipped as a generic planner with zero niche pages and an
off-topic motif.
"""

from __future__ import annotations

import pytest

from src.pipeline.orchestrator import (
    PipelineOrchestrator,
    _load_niches_config,
    _niche_slug,
)
from src.planner.niche_pages import get_niche_pages
from src.storage.models import Product

CONFIG = {
    "pipeline": {"max_products_per_day": 1000},
    "planner": {"year": 2026},
    "pricing": {"default_price_usd": 5.99, "book_price_usd": 4.99},
    "research": {"use_live_trends": False},
    "etsy": {"upload_enabled": False},
}


def _planner_niches() -> dict:
    return {
        slug: cfg
        for slug, cfg in _load_niches_config().items()
        if cfg.get("product_type", "planner") == "planner"
    }


class TestLoaderInjectsSlug:
    def test_every_config_carries_its_registry_key(self):
        for key, cfg in _load_niches_config().items():
            assert cfg.get("slug") == key

    def test_niche_slug_prefers_injected_key(self):
        assert _niche_slug({"slug": "wedding", "name": "Wedding Planner"}) == "wedding"

    def test_niche_slug_falls_back_to_name_for_adhoc_dicts(self):
        assert _niche_slug({"name": "Fitness Planner"}) == "fitness_planner"
        assert _niche_slug({}) == "planner"


class TestEveryPlannerNicheResolvesItsPages:
    @pytest.mark.parametrize("key", sorted(_planner_niches()))
    def test_pipeline_slug_finds_niche_pages(self, key):
        """The slug the PIPELINE derives must find the niche's own pages."""
        cfg = _planner_niches()[key]
        pages = get_niche_pages(_niche_slug(cfg))
        assert 5 <= len(pages) <= 7, (
            f"{key}: pipeline slug {_niche_slug(cfg)!r} resolves "
            f"{len(pages)} niche pages"
        )


class TestGeneratePlannerPdfSpec:
    @pytest.mark.parametrize("key", ["wedding", "travel", "fitness_planner"])
    def test_spec_uses_registry_slug(self, key, monkeypatch):
        captured = {}

        class FakeGenerator:
            def generate(self, spec):
                captured["spec"] = spec
                return "/tmp/fake.pdf"

        import src.pipeline.orchestrator as orch

        monkeypatch.setattr(orch, "_import_planner_generator", lambda: FakeGenerator)
        cfg = _load_niches_config()[key]
        product = Product(
            title=f"2026 {cfg['name']}",
            display_title=f"2026 {cfg['name']}",
            palette_name="ocean_blue",
            year=2026,
            price_usd=5.99,
            params='{"design": "classic"}',
        )
        orchestrator = PipelineOrchestrator(CONFIG, lambda: None)
        orchestrator._generate_planner_pdf(product, cfg)
        assert captured["spec"].niche_slug == key
        assert 5 <= len(get_niche_pages(captured["spec"].niche_slug)) <= 7
