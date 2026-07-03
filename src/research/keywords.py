"""Keyword expansion and scoring for Etsy listing optimisation."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from src.research.trends import TrendsClient

logger = structlog.get_logger()

# Hard-coded platforms that Etsy planner buyers commonly search for
_PLATFORM_MODIFIERS: list[str] = ["goodnotes", "ipad", "notability", "kindle scribe"]

# Current year used in year-specific keyword expansion
_CURRENT_YEAR: int = datetime.now().year


class KeywordExpander:
    """Expand a niche's seed keywords into a rich list of search-ready phrases.

    Parameters
    ----------
    niche_config : dict
        A single niche entry from ``niches.yaml``, e.g.::

            {
                "name": "ADHD Planner",
                "seed_keywords": ["adhd planner", ...],
                "modifiers": ["digital", "printable", ...],
                ...
            }
    """

    def __init__(self, niche_config: dict):
        self._config = niche_config

    # ------------------------------------------------------------------
    # Expansion
    # ------------------------------------------------------------------

    def expand(
        self,
        seed_keywords: list[str] | None = None,
        modifiers: list[str] | None = None,
    ) -> list[str]:
        """Return a de-duplicated list of expanded keyword phrases.

        Expansion rules
        ---------------
        1. **Modifier combos** -- each seed keyword paired with each modifier,
           with the modifier prepended: ``"digital adhd planner"``.
        2. **Year-specific** -- the current year prepended: ``"2026 adhd planner"``.
        3. **Platform-specific** -- common app names prepended:
           ``"goodnotes adhd planner"``, ``"ipad adhd planner"``.
        4. **Bare seed keywords** are always included as-is.
        """
        seeds = seed_keywords if seed_keywords is not None else self._config.get("seed_keywords", [])
        mods = modifiers if modifiers is not None else self._config.get("modifiers", [])

        expanded: list[str] = []
        seen: set[str] = set()

        def _add(phrase: str) -> None:
            normalised = _normalise(phrase)
            if normalised and normalised not in seen:
                seen.add(normalised)
                expanded.append(normalised)

        for seed in seeds:
            # Bare seed
            _add(seed)

            # Modifier combos
            for mod in mods:
                # Skip platform modifiers here -- they get their own pass below
                _add(f"{mod} {seed}")

            # Year-specific
            _add(f"{_CURRENT_YEAR} {seed}")

            # Platform-specific (avoid duplicates with modifiers)
            for platform in _PLATFORM_MODIFIERS:
                _add(f"{platform} {seed}")

        return expanded

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def score_keywords(
        self,
        keywords: list[str],
        trends_client: "TrendsClient",
    ) -> list[tuple[str, float]]:
        """Score each keyword using Google Trends data.

        Score formula::

            score = mean_interest * (1 + direction_bonus)

        where ``direction_bonus`` is ``trend_direction / 100`` (so a keyword
        trending up by 50% gets a 1.5x multiplier, and one trending down by
        50% gets a 0.5x multiplier).

        Returns a list of ``(keyword, score)`` tuples sorted descending by
        score.
        """
        scored: list[tuple[str, float]] = []

        for kw in keywords:
            try:
                data = trends_client.get_interest(kw)
            except Exception as exc:
                logger.warning("keyword_score_error", keyword=kw, error=str(exc))
                scored.append((kw, 0.0))
                continue

            values = data.get("values", [])
            if not values:
                scored.append((kw, 0.0))
                continue

            mean_interest = sum(values) / len(values)
            direction = trends_client.calculate_trend_direction(data)
            direction_bonus = direction / 100.0  # -1.0 .. 1.0

            score = mean_interest * (1.0 + direction_bonus)
            score = max(score, 0.0)  # floor at zero
            scored.append((kw, round(score, 2)))

        scored.sort(key=lambda t: t[1], reverse=True)
        return scored

    # ------------------------------------------------------------------
    # Tag generation
    # ------------------------------------------------------------------

    @staticmethod
    def generate_tags(
        scored_keywords: list[tuple[str, float]],
        max_tags: int = 13,
        max_chars: int = 20,
    ) -> list[str]:
        """Select the best tags for an Etsy listing.

        Rules
        -----
        * Tags are lowercase, alphanumeric + spaces only.
        * Each tag is at most *max_chars* characters.
        * No two tags may be too similar (>0.8 sequence-match ratio).
        * Returns exactly *max_tags* tags (Etsy maximum is 13).  If there
          are not enough unique candidates, the list is padded with
          truncated variants.
        """
        candidates: list[str] = []

        for kw, _score in scored_keywords:
            tag = _to_tag(kw, max_chars)
            if not tag:
                continue
            if _is_too_similar(tag, candidates, threshold=0.8):
                continue
            candidates.append(tag)
            if len(candidates) >= max_tags:
                break

        # Pad if we don't have enough unique tags
        if len(candidates) < max_tags:
            for kw, _score in scored_keywords:
                tag = _to_tag(kw, max_chars)
                if tag and tag not in candidates:
                    candidates.append(tag)
                if len(candidates) >= max_tags:
                    break

        return candidates[:max_tags]


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _normalise(text: str) -> str:
    """Lowercase, strip, collapse whitespace."""
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _to_tag(text: str, max_chars: int = 20) -> str:
    """Convert a keyword phrase into an Etsy-safe tag string.

    * Lowercase
    * Only ASCII letters, digits, and spaces
    * Truncated to *max_chars* at a word boundary when possible
    """
    # Normalise unicode (e.g. accented chars -> ASCII when possible)
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = _normalise(text)
    text = re.sub(r"[^a-z0-9 ]", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) <= max_chars:
        return text

    # Try to truncate at a word boundary
    truncated = text[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated.strip()


def _is_too_similar(tag: str, existing: list[str], threshold: float = 0.8) -> bool:
    """Return True if *tag* is too similar to any tag in *existing*."""
    for other in existing:
        ratio = SequenceMatcher(None, tag, other).ratio()
        if ratio > threshold:
            return True
    return False
