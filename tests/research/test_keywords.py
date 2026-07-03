"""Unit tests for keyword expansion, scoring, and tag generation.

These tests do NOT require network access -- the TrendsClient is mocked where
needed.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.research.keywords import (
    KeywordExpander,
    _is_too_similar,
    _normalise,
    _to_tag,
)


# ------------------------------------------------------------------
# Sample fixtures
# ------------------------------------------------------------------

@pytest.fixture()
def adhd_config() -> dict:
    return {
        "name": "ADHD Planner",
        "seed_keywords": [
            "adhd planner",
            "adhd daily planner",
        ],
        "modifiers": [
            "digital",
            "printable",
            "pdf",
        ],
        "preferred_palettes": ["soft_sage", "neutral_beige"],
    }


@pytest.fixture()
def expander(adhd_config) -> KeywordExpander:
    return KeywordExpander(adhd_config)


# ------------------------------------------------------------------
# Tests: _normalise helper
# ------------------------------------------------------------------

class TestNormalise:
    def test_lowercase(self):
        assert _normalise("ADHD Planner") == "adhd planner"

    def test_strips_whitespace(self):
        assert _normalise("  hello  world  ") == "hello world"

    def test_collapses_inner_spaces(self):
        assert _normalise("a   b") == "a b"


# ------------------------------------------------------------------
# Tests: _to_tag helper
# ------------------------------------------------------------------

class TestToTag:
    def test_basic(self):
        assert _to_tag("Digital Planner") == "digital planner"

    def test_removes_special_chars(self):
        assert _to_tag("budget!@ planner#") == "budget planner"

    def test_truncates_long_tag_at_word_boundary(self):
        tag = _to_tag("very long keyword phrase here", max_chars=20)
        assert len(tag) <= 20
        # Should truncate at a word boundary, not mid-word
        assert not tag.endswith(" ")

    def test_truncates_single_long_word(self):
        tag = _to_tag("superlongwordwithnobreaks", max_chars=10)
        assert len(tag) <= 10

    def test_empty_input(self):
        assert _to_tag("") == ""

    def test_unicode_normalised(self):
        # Accented characters should be stripped to ASCII equivalents
        assert _to_tag("cafe\u0301") == "cafe"


# ------------------------------------------------------------------
# Tests: _is_too_similar helper
# ------------------------------------------------------------------

class TestIsTooSimilar:
    def test_identical_strings(self):
        assert _is_too_similar("budget planner", ["budget planner"]) is True

    def test_very_different_strings(self):
        assert _is_too_similar("fitness tracker", ["budget planner"]) is False

    def test_threshold_boundary(self):
        # "adhd planner" vs "budget tracker" are different enough even at low threshold
        assert _is_too_similar("adhd planner", ["budget tracker"], threshold=0.5) is False
        # "adhd planner" vs "adhd planners" are very similar (ratio ~0.96)
        assert _is_too_similar("adhd planner", ["adhd planners"], threshold=0.95) is True

    def test_empty_existing(self):
        assert _is_too_similar("anything", []) is False


# ------------------------------------------------------------------
# Tests: KeywordExpander.expand
# ------------------------------------------------------------------

class TestExpand:
    def test_returns_list_of_strings(self, expander):
        result = expander.expand()
        assert isinstance(result, list)
        assert all(isinstance(kw, str) for kw in result)

    def test_includes_bare_seeds(self, expander):
        result = expander.expand()
        assert "adhd planner" in result
        assert "adhd daily planner" in result

    def test_includes_modifier_combos(self, expander):
        result = expander.expand()
        assert "digital adhd planner" in result
        assert "printable adhd planner" in result
        assert "pdf adhd daily planner" in result

    def test_includes_year_specific(self, expander):
        result = expander.expand()
        year = datetime.now().year
        assert f"{year} adhd planner" in result

    def test_includes_platform_specific(self, expander):
        result = expander.expand()
        assert "goodnotes adhd planner" in result
        assert "ipad adhd planner" in result

    def test_no_duplicates(self, expander):
        result = expander.expand()
        assert len(result) == len(set(result))

    def test_all_lowercase(self, expander):
        result = expander.expand()
        for kw in result:
            assert kw == kw.lower()

    def test_custom_seeds_and_modifiers(self, adhd_config):
        exp = KeywordExpander(adhd_config)
        result = exp.expand(
            seed_keywords=["test planner"],
            modifiers=["custom"],
        )
        assert "test planner" in result
        assert "custom test planner" in result

    def test_empty_seeds(self, adhd_config):
        exp = KeywordExpander(adhd_config)
        result = exp.expand(seed_keywords=[], modifiers=["digital"])
        assert result == []

    def test_empty_modifiers_still_has_seeds_and_platforms(self, adhd_config):
        exp = KeywordExpander(adhd_config)
        result = exp.expand(
            seed_keywords=["budget planner"],
            modifiers=[],
        )
        assert "budget planner" in result
        assert "goodnotes budget planner" in result
        year = datetime.now().year
        assert f"{year} budget planner" in result

    def test_modifier_already_in_platforms_still_works(self):
        """If 'goodnotes' appears in both modifiers and _PLATFORM_MODIFIERS,
        the keyword should appear only once."""
        config = {
            "name": "Test",
            "seed_keywords": ["planner"],
            "modifiers": ["goodnotes"],
        }
        exp = KeywordExpander(config)
        result = exp.expand()
        # "goodnotes planner" should appear exactly once
        assert result.count("goodnotes planner") == 1


# ------------------------------------------------------------------
# Tests: KeywordExpander.score_keywords
# ------------------------------------------------------------------

class TestScoreKeywords:
    def _mock_trends_client(self, data_map: dict | None = None):
        """Return a mock TrendsClient.

        ``data_map`` maps keyword -> {"dates": [...], "values": [...]}.
        """
        client = MagicMock()
        data_map = data_map or {}

        def mock_get_interest(kw, **kwargs):
            return data_map.get(kw, {"dates": [], "values": []})

        client.get_interest = MagicMock(side_effect=mock_get_interest)
        client.calculate_trend_direction = MagicMock(return_value=0.0)
        return client

    def test_returns_sorted_descending(self, expander):
        data = {
            "adhd planner": {"dates": ["2025-01"], "values": [80]},
            "adhd daily planner": {"dates": ["2025-01"], "values": [50]},
        }
        client = self._mock_trends_client(data)
        result = expander.score_keywords(["adhd planner", "adhd daily planner"], client)

        assert result[0][0] == "adhd planner"
        assert result[0][1] >= result[1][1]

    def test_empty_values_scores_zero(self, expander):
        client = self._mock_trends_client()
        result = expander.score_keywords(["unknown keyword"], client)
        assert result[0][1] == 0.0

    def test_positive_direction_boosts_score(self, expander):
        data = {
            "adhd planner": {"dates": ["2025-01"], "values": [60]},
        }
        client = self._mock_trends_client(data)
        # Positive direction = 50%
        client.calculate_trend_direction = MagicMock(return_value=50.0)

        result = expander.score_keywords(["adhd planner"], client)
        # score = 60 * (1 + 0.5) = 90
        assert result[0][1] == 90.0

    def test_negative_direction_reduces_score(self, expander):
        data = {
            "adhd planner": {"dates": ["2025-01"], "values": [60]},
        }
        client = self._mock_trends_client(data)
        client.calculate_trend_direction = MagicMock(return_value=-50.0)

        result = expander.score_keywords(["adhd planner"], client)
        # score = 60 * (1 + (-0.5)) = 30
        assert result[0][1] == 30.0

    def test_error_keyword_scores_zero(self, expander):
        client = MagicMock()
        client.get_interest = MagicMock(side_effect=RuntimeError("API down"))
        result = expander.score_keywords(["failing keyword"], client)
        assert result[0][1] == 0.0


# ------------------------------------------------------------------
# Tests: KeywordExpander.generate_tags
# ------------------------------------------------------------------

class TestGenerateTags:
    def test_returns_max_tags(self):
        scored = [(f"keyword {i}", float(100 - i)) for i in range(30)]
        tags = KeywordExpander.generate_tags(scored, max_tags=13)
        assert len(tags) == 13

    def test_all_tags_lowercase(self):
        scored = [("Digital Planner", 90.0), ("Budget Tracker", 80.0)]
        tags = KeywordExpander.generate_tags(scored, max_tags=2)
        for tag in tags:
            assert tag == tag.lower()

    def test_no_special_characters(self):
        scored = [("planner!! @2026", 90.0)]
        tags = KeywordExpander.generate_tags(scored, max_tags=1)
        assert tags[0].replace(" ", "").isalnum()

    def test_tags_within_max_chars(self):
        scored = [("this is a very very long keyword phrase", 90.0)]
        tags = KeywordExpander.generate_tags(scored, max_tags=1, max_chars=20)
        for tag in tags:
            assert len(tag) <= 20

    def test_no_overly_similar_tags(self):
        scored = [
            ("budget planner", 90.0),
            ("budget planners", 89.0),
            ("fitness planner", 70.0),
        ]
        tags = KeywordExpander.generate_tags(scored, max_tags=3)
        # "budget planner" and "budget planners" are very similar;
        # one of them should be replaced
        assert len(set(tags)) == len(tags)  # all unique

    def test_empty_input(self):
        tags = KeywordExpander.generate_tags([], max_tags=13)
        assert tags == []

    def test_fewer_candidates_than_max(self):
        scored = [("only one keyword", 50.0)]
        tags = KeywordExpander.generate_tags(scored, max_tags=13)
        # Should not crash; just returns what we have
        assert len(tags) <= 13
        assert len(tags) >= 1

    def test_tags_are_strings(self):
        scored = [("adhd planner", 80.0), ("budget planner", 70.0)]
        tags = KeywordExpander.generate_tags(scored, max_tags=2)
        assert all(isinstance(t, str) for t in tags)

    def test_deduplication_in_padding(self):
        """When padding with extra candidates, duplicates should not appear."""
        scored = [
            ("adhd planner", 90.0),
            ("adhd planner", 80.0),  # duplicate
        ]
        tags = KeywordExpander.generate_tags(scored, max_tags=5)
        assert len(tags) == len(set(tags))
