"""Tests for src.books.seo constraints (Etsy limits)."""

from __future__ import annotations

import pytest

from src.books.params import pick_book_params
from src.books.seo import BookListingSEO


@pytest.fixture()
def params() -> dict:
    return pick_book_params({}, existing=[], seed=42)


@pytest.fixture()
def seo() -> BookListingSEO:
    return BookListingSEO()


def test_title_length(seo, params):
    title = seo.generate_title(params, year=2026)
    assert 0 < len(title) <= 140
    assert params["display_title"] in title


def test_title_across_many_params(seo):
    for s in range(25):
        p = pick_book_params({}, existing=[], seed=s)
        assert len(seo.generate_title(p, year=2026)) <= 140


def test_tags_exactly_13_and_short(seo, params):
    tags = seo.generate_tags(params, year=2026)
    assert len(tags) == 13
    assert len(set(tags)) == 13
    for tag in tags:
        assert len(tag) <= 20, f"tag too long: {tag!r}"
        assert tag == tag.lower()


def test_tags_across_many_params(seo):
    for s in range(25):
        p = pick_book_params({}, existing=[], seed=s)
        tags = seo.generate_tags(p, year=2026)
        assert len(tags) == 13
        assert all(len(t) <= 20 and t == t.lower() for t in tags)


def test_description_sections(seo, params):
    desc = seo.generate_description(params)
    for needle in (
        "WHAT'S INSIDE", "PERFECT FOR", "HOW IT WORKS", "PLEASE NOTE",
        "coloring pages", "DIGITAL DOWNLOAD", "PERSONAL USE",
    ):
        assert needle in desc, f"missing section: {needle}"
    assert str(params["page_count"]) in desc
    assert params["age_band"] in desc
