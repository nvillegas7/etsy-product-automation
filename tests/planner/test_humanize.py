"""Tests for the ``humanize`` slug helper and the guarantee that no raw
underscore-slug ever leaks into rendered planner/book text.

The owner once saw a cover reading ``fitness_planner`` instead of
``Fitness Planner`` -- an unmistakable "auto-generated" tell.  These tests
lock that door shut: ``humanize`` cleans any slug fallback, and a broad
extraction guard scans every page of a generated planner AND a generated
book for snake_case tokens.
"""

from __future__ import annotations

import re

import fitz
import pytest

from src.books.generator import BookGenerator, BookSpec
from src.books.params import pick_book_params
from src.planner.generator import PlannerGenerator, PlannerSpec
from src.planner.styles import humanize

# A token that looks machine-made: lowercase words joined by underscores.
SNAKE_CASE = re.compile(r"[a-z]+_[a-z]+")


# ---------------------------------------------------------------------------
# Unit: humanize
# ---------------------------------------------------------------------------

class TestHumanize:
    def test_underscores(self):
        assert humanize("fitness_planner") == "Fitness Planner"

    def test_hyphens(self):
        assert humanize("self-care") == "Self Care"

    def test_mixed_separators_and_whitespace(self):
        assert humanize("  budget__planner-2026  ") == "Budget Planner 2026"

    def test_already_clean_input(self):
        assert humanize("Fitness Planner") == "Fitness Planner"

    def test_single_word(self):
        assert humanize("planner") == "Planner"

    def test_digits_pass_through(self):
        assert humanize("2026_daily_planner") == "2026 Daily Planner"

    def test_empty_string(self):
        assert humanize("") == ""

    def test_none(self):
        assert humanize(None) == ""

    def test_output_has_no_snake_case(self):
        for slug in ("fitness_planner", "adhd_planner", "self-care_kit"):
            assert not SNAKE_CASE.search(humanize(slug))


# ---------------------------------------------------------------------------
# Planner: a niche with NO "name" still renders a clean title
# ---------------------------------------------------------------------------

@pytest.fixture
def out_dir(tmp_path, monkeypatch):
    import src.planner.generator as gen_mod

    monkeypatch.setattr(gen_mod, "OUTPUT_DIR", tmp_path)
    return tmp_path


def _cover_text(path) -> str:
    doc = fitz.open(str(path))
    try:
        return doc[0].get_text()
    finally:
        doc.close()


class TestPlannerTitleFallback:
    def test_unknown_niche_renders_humanized_cover_title(self, out_dir):
        """A slug with no niche config / no 'name' must still render a clean,
        human title -- never the raw underscore-slug."""
        slug = "custom_focus_planner"  # not in niches.yaml -> config {}, no name
        # Mirror the orchestrator / generate_sample fallback exactly.
        title = humanize(slug)
        spec = PlannerSpec(
            title=title,
            display_title=title,
            year=2026,
            palette_name="classic_boho",
            include_weekly=False,
            include_daily=False,
            niche_slug=slug,
        )
        path = PlannerGenerator().generate(spec)
        cover = _cover_text(path)
        assert "Custom Focus Planner" in cover
        assert "custom_focus_planner" not in cover
        assert "_" not in cover


# ---------------------------------------------------------------------------
# Broad guard: NO snake_case token anywhere in a planner OR a book
# ---------------------------------------------------------------------------

def _all_text(path) -> str:
    doc = fitz.open(str(path))
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def _snake_tokens(text: str) -> list[str]:
    return sorted(set(SNAKE_CASE.findall(text)))


class TestNoSnakeCaseInRenderedText:
    def test_planner_has_no_snake_case(self, out_dir):
        # fitness_planner exercises the very slug from the bug report.
        spec = PlannerSpec(
            title=humanize("fitness_planner"),
            display_title=humanize("fitness_planner"),
            year=2026,
            palette_name="ocean_blue",
            include_weekly=True,
            include_daily=False,
            niche_slug="fitness_planner",
        )
        path = PlannerGenerator().generate(spec)
        text = _all_text(path)
        assert "Fitness Planner" in text
        offenders = _snake_tokens(text)
        assert not offenders, f"snake_case leaked into planner: {offenders}"

    def test_book_has_no_snake_case(self, tmp_path):
        params = pick_book_params({}, existing=[], seed=42)
        params["page_count"] = 12
        spec = BookSpec(
            title=params["display_title"],
            subtitle=params["subtitle"],
            year=2026,
            palette_name=params["art_palette"],
            params=params,
            output_dir=tmp_path,
        )
        path = BookGenerator().generate(spec)
        text = _all_text(path)
        offenders = _snake_tokens(text)
        assert not offenders, f"snake_case leaked into book: {offenders}"

    def test_book_with_underscore_character_key_stays_clean(self, tmp_path):
        """Even a character_key / setting that carries an underscore must be
        humanized before it reaches any drawn label."""
        params = pick_book_params({}, existing=[], seed=7)
        params["page_count"] = 12
        params["character_key"] = "pea_pod"   # underscore key -> "Pea Pod"
        params["character_name"] = "Penny"
        spec = BookSpec(
            title="Penny Learns to Share",
            palette_name=params["art_palette"],
            params=params,
            output_dir=tmp_path,
        )
        path = BookGenerator().generate(spec)
        text = _all_text(path)
        # the species label must reach the page humanized, never "pea_pod"
        assert "Pea Pod" in text
        assert "pea_pod" not in text
        offenders = _snake_tokens(text)
        assert not offenders, f"snake_case leaked into book: {offenders}"
