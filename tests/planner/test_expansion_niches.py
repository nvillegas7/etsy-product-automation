"""Invariants for the expansion planner niches (travel, wedding, meal &
recipe, self-care, home management, small business).

Guards two things:
  * EVERY niche declared in ``config/niches.yaml`` maps every one of its
    ``niche_pages`` ids to a registered renderer (no dangling ids that would
    silently drop a page);
  * each of the six new niches builds a complete, valid planner without
    raising, with real niche pages and working back-links.
"""

from __future__ import annotations

import fitz
import pytest
import yaml

from src.planner.generator import PlannerGenerator, PlannerSpec
from src.planner.niche_pages import NICHES_PATH, RENDERERS, get_niche_pages

NEW_NICHES = [
    ("travel", "ocean_blue"),
    ("wedding", "blush_butter"),
    ("meal_recipe", "terracotta_clay"),
    ("self_care", "lavender_haze"),
    ("home_management", "patina_blue"),
    ("small_business", "charcoal_minimal"),
]


def _all_niches() -> dict:
    with open(NICHES_PATH) as fh:
        return yaml.safe_load(fh).get("niches", {})


@pytest.fixture
def out_dir(tmp_path, monkeypatch):
    import src.planner.generator as gen_mod

    monkeypatch.setattr(gen_mod, "OUTPUT_DIR", tmp_path)
    return tmp_path


class TestEveryNichePageResolves:
    def test_every_declared_id_is_registered(self):
        """No niche in niches.yaml may declare a page id without a renderer."""
        offenders = {}
        for slug, cfg in _all_niches().items():
            for entry in cfg.get("niche_pages", []) or []:
                pid = entry.get("id")
                if pid not in RENDERERS:
                    offenders.setdefault(slug, []).append(pid)
        assert not offenders, f"unregistered niche page ids: {offenders}"

    @pytest.mark.parametrize("slug,_palette", NEW_NICHES)
    def test_new_niche_declares_resolvable_pages(self, slug, _palette):
        specs = get_niche_pages(slug)
        # 5-7 differentiating pages per the dossier; all must resolve.
        assert 5 <= len(specs) <= 7, f"{slug} declared {len(specs)} pages"
        for s in specs:
            assert s.id in RENDERERS


class TestNewNichesGenerate:
    @pytest.mark.parametrize("slug,palette", NEW_NICHES)
    def test_niche_builds_valid_planner(self, out_dir, slug, palette):
        spec = PlannerSpec(
            title=f"2026 {slug}",
            display_title=f"2026 {slug}",
            year=2026,
            palette_name=palette,
            niche_slug=slug,
            include_weekly=False,
            include_daily=False,
        )
        path = PlannerGenerator().generate(spec)
        assert path.exists()
        doc = fitz.open(str(path))
        try:
            # cover + index + year glance + 12*(cal+plan+review) + niche + back
            assert len(doc) > 12
            n_pages = len(get_niche_pages(slug))
            # the niche section adds one page per declared niche_page
            assert len(doc) == 3 + 36 + n_pages + 3
            # a niche page carries a back-to-index link
            niche_page = doc[3 + 36]
            assert len(niche_page.get_links()) > 0
        finally:
            doc.close()
