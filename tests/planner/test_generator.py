"""Tests for the planner generator: spec, smoke build, links, niche pages."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from src.planner.generator import PlannerGenerator, PlannerSpec
from src.planner.niche_pages import RENDERERS, get_niche_pages
from src.planner.styles import get_palette, get_palettes


# ---------------------------------------------------------------------------
# Spec construction
# ---------------------------------------------------------------------------

class TestPlannerSpec:
    def test_defaults(self):
        spec = PlannerSpec()
        assert spec.title == "2026 Planner"
        assert spec.display_title == ""
        assert spec.year == 2026
        assert spec.include_daily is False
        assert spec.include_niche_pages is True

    def test_display_title_field(self):
        spec = PlannerSpec(
            title="2026 Budget Planner Digital Download GoodNotes iPad PDF",
            display_title="2026 Budget Planner",
            niche_slug="budget_planner",
        )
        assert spec.display_title == "2026 Budget Planner"

    def test_palette_helpers_still_work(self):
        palettes = get_palettes()
        assert "classic_boho" in palettes
        pal = get_palette("classic_boho")
        assert pal.rgb("primary") == (196, 149, 106)
        with pytest.raises(KeyError):
            get_palette("no_such_palette")


# ---------------------------------------------------------------------------
# Generation smoke tests
# ---------------------------------------------------------------------------

def _small_spec(**kwargs) -> PlannerSpec:
    base = dict(
        title="2026 Planner",
        display_title="2026 Planner",
        year=2026,
        palette_name="classic_boho",
        include_weekly=False,
        include_daily=False,
    )
    base.update(kwargs)
    return PlannerSpec(**base)


@pytest.fixture
def out_dir(tmp_path, monkeypatch):
    import src.planner.generator as gen_mod

    monkeypatch.setattr(gen_mod, "OUTPUT_DIR", tmp_path)
    return tmp_path


class TestGenerateSmoke:
    def test_generate_small_planner(self, out_dir):
        spec = _small_spec(niche_slug="budget_planner")
        path = PlannerGenerator().generate(spec)
        assert path.exists()
        assert path.parent == out_dir
        assert path.stat().st_size < 20 * 1024 * 1024

        doc = fitz.open(str(path))
        # cover + index + year glance + 12*(cal+plan+review) + 6 niche + 3
        assert len(doc) == 3 + 36 + 6 + 3
        doc.close()

    def test_links_present_and_targets_valid(self, out_dir):
        spec = _small_spec(niche_slug="budget_planner")
        path = PlannerGenerator().generate(spec)
        doc = fitz.open(str(path))

        # Every chrome page must carry internal links
        for idx in (1, 2, 3, len(doc) - 1):
            links = doc[idx].get_links()
            assert len(links) > 0, f"page {idx} has no links"
            for link in links:
                if link["kind"] == fitz.LINK_GOTO:
                    assert 0 <= link["page"] < len(doc)

        # Index page must link to at least 12 distinct pages (months etc.)
        index_targets = {
            l["page"] for l in doc[1].get_links() if l["kind"] == fitz.LINK_GOTO
        }
        assert len(index_targets) >= 12

        # Year-at-a-glance mini calendars must link to month pages
        yg_targets = {
            l["page"] for l in doc[2].get_links() if l["kind"] == fitz.LINK_GOTO
        }
        assert len(yg_targets) >= 12
        doc.close()

    def test_month_tabs_migrate(self, out_dir):
        """On the September page, earlier months' tabs sit on the LEFT edge."""
        spec = _small_spec(niche_slug="budget_planner")
        path = PlannerGenerator().generate(spec)
        doc = fitz.open(str(path))

        # September monthly calendar: page index 3 + (9-1)*3 = 27
        sep_page = doc[3 + 8 * 3]
        page_w = sep_page.rect.width
        left_links = [
            l for l in sep_page.get_links()
            if l["kind"] == fitz.LINK_GOTO and l["from"].x1 < page_w * 0.05
        ]
        right_links = [
            l for l in sep_page.get_links()
            if l["kind"] == fitz.LINK_GOTO and l["from"].x0 > page_w * 0.95
        ]
        assert len(left_links) >= 8, "expected JAN-AUG tabs on the left edge"
        assert len(right_links) >= 4, "expected SEP-DEC + YEAR tabs on the right"
        doc.close()


# ---------------------------------------------------------------------------
# Text extraction / outline / weekly layout
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def weekly_planner_pdf(tmp_path_factory):
    """One planner WITH weekly pages, shared by extraction/outline tests."""
    import src.planner.generator as gen_mod

    out_dir = tmp_path_factory.mktemp("planner_weekly")
    original = gen_mod.OUTPUT_DIR
    gen_mod.OUTPUT_DIR = out_dir
    try:
        spec = _small_spec(niche_slug="budget_planner", include_weekly=True)
        path = PlannerGenerator().generate(spec)
    finally:
        gen_mod.OUTPUT_DIR = original
    return path


class TestTextExtraction:
    """Buyers search planners in GoodNotes -- extraction must be intact."""

    def test_month_name_extracts_intact(self, weekly_planner_pdf):
        doc = fitz.open(str(weekly_planner_pdf))
        # cover, index, year glance, then the January monthly calendar
        text = doc[3].get_text()
        assert "January" in text
        assert "Ja ua y" not in text  # garbled invisible bookmark titles
        doc.close()

    def test_weekly_date_labels_extract_intact(self, weekly_planner_pdf):
        doc = fitz.open(str(weekly_planner_pdf))
        # first weekly page of January follows monthly cal + plan + review
        text = doc[6].get_text()
        assert "Dec 28 - Jan 03" in text
        doc.close()

    def test_no_invisible_micro_text(self, weekly_planner_pdf):
        """No near-zero-size spans: they garble extraction and search."""
        doc = fitz.open(str(weekly_planner_pdf))
        for idx in (0, 1, 3, 6):
            for block in doc[idx].get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        assert span["size"] > 1.0, (
                            f"page {idx} has invisible text {span['text']!r}"
                        )
        doc.close()


class TestOutline:
    def test_toc_has_cover_months_and_niche_sections(self, weekly_planner_pdf):
        import calendar as _cal

        doc = fitz.open(str(weekly_planner_pdf))
        toc = doc.get_toc()
        assert len(toc) > 0, "PDF outline must not be empty"
        titles = [t[1] for t in toc]
        assert "Cover" in titles
        assert "Year at a Glance" in titles
        for m in range(1, 13):
            assert _cal.month_name[m] in titles
        assert "Monthly Budget" in titles  # niche section
        # every outline destination must resolve to a page in range
        for _level, _title, page in toc:
            assert 1 <= page <= len(doc)
        doc.close()


class TestWeeklyLayout:
    def test_days_chronological_across_spread(self, weekly_planner_pdf):
        """Top row Sun-Wed, bottom row Thu-Sat, left-to-right in each."""
        doc = fitz.open(str(weekly_planner_pdf))
        page = doc[6]  # Dec 28 - Jan 03 weekly spread
        names = ("SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY",
                 "THURSDAY", "FRIDAY", "SATURDAY")
        pos = {}
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    for name in names:
                        if span["text"].startswith(name):
                            pos[name] = fitz.Rect(span["bbox"])
        assert set(pos) == set(names)
        top = [pos[n] for n in names[:4]]
        bottom = [pos[n] for n in names[4:]]
        assert max(r.y0 for r in top) < min(r.y0 for r in bottom)
        assert [r.x0 for r in top] == sorted(r.x0 for r in top)
        assert [r.x0 for r in bottom] == sorted(r.x0 for r in bottom)
        doc.close()


# ---------------------------------------------------------------------------
# Niche pages
# ---------------------------------------------------------------------------

class TestNichePages:
    def test_all_declared_ids_have_renderers(self):
        for slug in ("budget_planner", "student_planner", "fitness_planner",
                     "adhd_planner", "teacher_planner"):
            specs = get_niche_pages(slug)
            assert len(specs) == 6, f"{slug} should declare 6 niche pages"
            for s in specs:
                assert s.id in RENDERERS

    def test_unknown_niche_has_no_pages(self):
        assert get_niche_pages("nonexistent_niche") == []

    def test_page_count_differs_per_niche(self, out_dir):
        counts = {}
        for slug in ("planner", "budget_planner"):
            spec = _small_spec(niche_slug=slug)
            path = PlannerGenerator().generate(spec)
            doc = fitz.open(str(path))
            counts[slug] = len(doc)
            doc.close()
        # 'planner' has no niche pages; budget adds 6 dedicated pages
        assert counts["budget_planner"] == counts["planner"] + 6

    @pytest.mark.parametrize(
        "slug,palette",
        [
            ("student_planner", "dusty_rose"),
            ("fitness_planner", "ocean_blue"),
            ("adhd_planner", "soft_sage"),
            ("teacher_planner", "neutral_beige"),
        ],
    )
    def test_every_niche_generates(self, out_dir, slug, palette):
        spec = _small_spec(niche_slug=slug, palette_name=palette)
        path = PlannerGenerator().generate(spec)
        doc = fitz.open(str(path))
        assert len(doc) == 3 + 36 + 6 + 3
        # niche pages carry links back to the index
        niche_page = doc[len(doc) - 5]
        assert len(niche_page.get_links()) > 0
        doc.close()
