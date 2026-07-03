"""Tests for src.books.params: determinism, uniqueness, config constraints."""

from __future__ import annotations

import pytest

from src.books.illustrator import load_book_config
from src.books.params import pick_book_params

REQUIRED_KEYS = {
    "character_theme", "character_key", "character_name", "setting", "moral",
    "age_band", "narrative_style", "page_count", "art_palette",
    "display_title", "subtitle", "seed",
}


@pytest.fixture()
def book_params_cfg() -> dict:
    return load_book_config()["book_params"]


def test_required_keys_present():
    params = pick_book_params({}, existing=[], seed=123)
    assert REQUIRED_KEYS.issubset(params.keys())


def test_deterministic_for_same_seed():
    a = pick_book_params({}, existing=[], seed=99)
    b = pick_book_params({}, existing=[], seed=99)
    assert a == b


def test_different_seeds_vary():
    picks = {
        (p["character_key"], p["setting"], p["moral"])
        for p in (pick_book_params({}, existing=[], seed=s) for s in range(20))
    }
    assert len(picks) > 5


def test_avoids_existing_triples():
    existing: list[dict] = []
    for s in range(40):
        p = pick_book_params({}, existing=existing, seed=s)
        triple = (p["character_key"], p["setting"], p["moral"])
        assert triple not in {
            (e["character_key"], e["setting"], e["moral"]) for e in existing
        }
        existing.append(p)


def test_respects_allowed_themes(book_params_cfg):
    niche_cfg = {"allowed_themes": ["ocean"]}
    for s in range(12):
        p = pick_book_params(niche_cfg, existing=[], seed=s)
        assert p["character_theme"] == "ocean"
        assert p["character_key"] in book_params_cfg["themes"]["ocean"]["characters"]
        # ocean characters only ever appear in water-y settings
        assert p["setting"] in {"beach", "underwater", "pond"}


def test_respects_preferred_morals():
    niche_cfg = {"preferred_morals": ["kindness", "honesty"]}
    for s in range(12):
        p = pick_book_params(niche_cfg, existing=[], seed=s)
        assert p["moral"] in ("kindness", "honesty")


def test_values_within_config_space(book_params_cfg):
    p = pick_book_params({}, existing=[], seed=5)
    assert p["setting"] in book_params_cfg["settings"]
    assert p["moral"] in book_params_cfg["morals"]
    assert p["age_band"] in book_params_cfg["age_bands"]
    assert p["narrative_style"] in book_params_cfg["narrative_styles"]
    assert p["page_count"] in book_params_cfg["page_counts"]
    assert p["art_palette"] in book_params_cfg["palettes"]


def test_random_seed_when_none():
    p = pick_book_params({}, existing=[])
    assert isinstance(p["seed"], int)
    # the returned seed must reproduce the same pick
    q = pick_book_params({}, existing=[], seed=p["seed"])
    assert q == p
