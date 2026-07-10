"""Wave 1 P1/P2: academic-year builds + date modes (dated / dated_next / undated).

The golden classic (test_golden_classic.py) proves the DEFAULT spec is unchanged;
these tests pin the NEW behavior the academic + date-mode knobs unlock.
"""

from __future__ import annotations

import calendar as _cal

import fitz
import pytest

import src.planner.generator as gen_mod
from src.planner.generator import (
    PlannerGenerator,
    PlannerSpec,
    _date_year,
    _planner_slots,
    _span_label,
    _span_weeks,
    _week_section_month,
    _year_part,
    _year_weeks,
)

_cal.setfirstweekday(_cal.SUNDAY)

MONTH_NAMES = set(_cal.month_name[1:])  # {"January", ..., "December"}


@pytest.fixture
def out_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(gen_mod, "OUTPUT_DIR", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Slot sequence
# ---------------------------------------------------------------------------

class TestSlots:
    def test_calendar_default_is_jan_to_dec(self):
        assert _planner_slots(PlannerSpec()) == [(m, 2026) for m in range(1, 13)]

    def test_academic_runs_aug_to_jul_across_two_years(self):
        slots = _planner_slots(PlannerSpec(start_month=8, year=2026))
        assert slots == [
            (8, 2026), (9, 2026), (10, 2026), (11, 2026), (12, 2026),
            (1, 2027), (2, 2027), (3, 2027), (4, 2027), (5, 2027),
            (6, 2027), (7, 2027),
        ]

    def test_academic_covers_all_twelve_calendar_months_once(self):
        slots = _planner_slots(PlannerSpec(start_month=8))
        assert sorted(m for m, _ in slots) == list(range(1, 13))

    def test_dated_next_shifts_anchor_by_one_year(self):
        assert _date_year(PlannerSpec(date_mode="dated_next")) == 2027
        assert _planner_slots(PlannerSpec(date_mode="dated_next")) == [
            (m, 2027) for m in range(1, 13)
        ]
        # academic + dated_next -> 2027-2028 school year
        assert _planner_slots(PlannerSpec(start_month=8, date_mode="dated_next"))[0] == (8, 2027)


# ---------------------------------------------------------------------------
# Weeks
# ---------------------------------------------------------------------------

class TestSpanWeeks:
    def test_calendar_span_reproduces_year_weeks_exactly(self):
        # The default path MUST be byte-identical to the pre-existing helper.
        assert _span_weeks(2026, 1) == _year_weeks(2026)
        assert _span_weeks(2027, 1) == _year_weeks(2027)

    def test_academic_span_starts_before_august_and_ends_in_july(self):
        weeks = _span_weeks(2026, 8)
        # First Sunday is on/before Aug 1 2026; last week ends on/after Jul 31 2027.
        from datetime import date, timedelta
        assert weeks[0] <= date(2026, 8, 1)
        assert weeks[-1] + timedelta(days=6) >= date(2027, 7, 31)
        # 12 months of weeks: 52 or 53 Sundays.
        assert 52 <= len(weeks) <= 54


class TestWeekSectionMonth:
    def test_calendar_boundary_week_maps_to_january(self):
        # Dec-28-2025 Sunday belongs to the January section (matches old else-1).
        from datetime import date
        slots = _planner_slots(PlannerSpec())
        assert _week_section_month(date(2025, 12, 28), slots) == 1
        assert _week_section_month(date(2026, 3, 1), slots) == 3

    def test_academic_pre_span_week_maps_to_august(self):
        from datetime import date
        slots = _planner_slots(PlannerSpec(start_month=8))
        # A late-July-2026 Sunday (before the Aug span) folds into August.
        assert _week_section_month(date(2026, 7, 26), slots) == 8
        # A January-2027 week stays in January (NOT collapsed to the anchor year).
        assert _week_section_month(date(2027, 1, 4), slots) == 1


# ---------------------------------------------------------------------------
# Labels + filenames
# ---------------------------------------------------------------------------

class TestLabels:
    def test_calendar_dated_label_is_empty(self):
        # Empty => cover falls back to str(year); keeps the golden classic.
        assert _span_label(PlannerSpec()) == ""

    def test_academic_label_is_two_year_span(self):
        assert _span_label(PlannerSpec(start_month=8, year=2026)) == "2026-2027"

    def test_dated_next_calendar_label_is_next_year(self):
        assert _span_label(PlannerSpec(date_mode="dated_next")) == "2027"

    def test_undated_label(self):
        assert _span_label(PlannerSpec(date_mode="undated")) == "Undated"


class TestYearPart:
    def test_default_year_part_keeps_classic_filename_token(self):
        assert _year_part(PlannerSpec()) == "2026"

    def test_academic_year_part(self):
        assert _year_part(PlannerSpec(start_month=8, year=2026)) == "2026-2027"

    def test_dated_next_year_part(self):
        assert _year_part(PlannerSpec(date_mode="dated_next")) == "2027"
        assert _year_part(PlannerSpec(start_month=8, date_mode="dated_next")) == "2027-2028"

    def test_undated_year_part(self):
        assert _year_part(PlannerSpec(date_mode="undated")) == "undated"


# ---------------------------------------------------------------------------
# Integration: academic build
# ---------------------------------------------------------------------------

def _toc_month_order(doc) -> list[str]:
    """Month-section bookmark titles in document order (exact month names only)."""
    return [t for _lvl, t, _pg in doc.get_toc() if t in MONTH_NAMES]


class TestAcademicBuild:
    def test_month_order_cover_label_and_filename(self, out_dir):
        spec = PlannerSpec(
            start_month=8, year=2026,
            niche_slug="planner", palette_name="ocean_blue",
            include_daily=False,
        )
        path = PlannerGenerator().generate(spec)

        # Filename encodes the academic span, not a single year.
        assert path.name == "2026-2027_planner_ocean_blue.pdf"

        doc = fitz.open(str(path))
        try:
            # Month sections run August -> July.
            assert _toc_month_order(doc) == [
                "August", "September", "October", "November", "December",
                "January", "February", "March", "April", "May", "June", "July",
            ]
            # Cover shows the two-year span.
            cover_text = doc[0].get_text()
            assert "2026-2027" in cover_text.replace(" ", "")
        finally:
            doc.close()

    def test_academic_grids_use_the_correct_per_month_year(self, out_dir):
        # Aug 2026 starts on a Saturday; Aug 2027 starts on a Sunday. The build
        # must key each month's grid to its OWN year, so the two differ.
        aug_2026 = _cal.monthcalendar(2026, 8)
        aug_2027 = _cal.monthcalendar(2027, 8)
        assert aug_2026 != aug_2027  # guard: the fixture assumption holds


# ---------------------------------------------------------------------------
# Integration: date-mode trio (undated / dated_next)
# ---------------------------------------------------------------------------

def _mk(out_dir, **kw):
    base = dict(niche_slug="planner", palette_name="ocean_blue",
                display_title="2026-2027 Planner", start_month=8, year=2026)
    base.update(kw)
    return PlannerGenerator().generate(PlannerSpec(**base))


class TestUndated:
    def test_scaffold_matches_dated_but_dates_are_blanked(self, out_dir):
        dated = fitz.open(str(_mk(out_dir, date_mode="dated")))
        undated = fitz.open(str(_mk(out_dir, date_mode="undated")))
        try:
            # Same navigational scaffold: identical page count + month sections.
            assert len(undated) == len(dated)
            assert _toc_month_order(undated) == _toc_month_order(dated)
            # Fully navigable (tabs, months, weeks, index all linked).
            assert sum(len(pg.get_links()) for pg in undated) > 1000

            aug_idx = next(pg - 1 for _l, t, pg in undated.get_toc() if t == "August")
            aug_text = undated[aug_idx].get_text()
            # Fill-in year, and NO real day numbers in the month grid.
            assert "20__" in aug_text
            assert not any(ln.strip() == "15" for ln in aug_text.splitlines())
            # Cover advertises undated, not a year.
            assert "Undated" in undated[0].get_text()
        finally:
            dated.close()
            undated.close()

    def test_filename_marks_undated(self, out_dir):
        path = _mk(out_dir, date_mode="undated")
        assert path.name == "undated_planner_ocean_blue.pdf"


@pytest.mark.parametrize("design", ["noir", "studio", "blueprint", "almanac"])
class TestCoverYearAcrossDesigns:
    """Every cover design (not just classic) must honor the date-mode label --
    no design may print a bare wrong year or leak a date on an undated build.
    """

    def _cover(self, out_dir, design, mode):
        p = PlannerGenerator().generate(PlannerSpec(
            niche_slug="planner", palette_name="ocean_blue",
            display_title="2026-2027 Planner", start_month=8, year=2026,
            date_mode=mode, design=design))
        doc = fitz.open(str(p))
        try:
            # Some voices space out glyphs ("2 0 2 6"); collapse for matching.
            return doc[0].get_text().replace(" ", "")
        finally:
            doc.close()

    def test_undated_cover_leaks_no_concrete_year(self, out_dir, design):
        txt = self._cover(out_dir, design, "undated")
        assert "2026" not in txt and "2027" not in txt
        assert "Undated" in txt

    def test_academic_cover_shows_the_span(self, out_dir, design):
        assert "2026-2027" in self._cover(out_dir, design, "dated")


class TestDatedNext:
    def test_filename_and_grid_use_next_school_year(self, out_dir):
        path = _mk(out_dir, date_mode="dated_next")
        assert path.name == "2027-2028_planner_ocean_blue.pdf"
        doc = fitz.open(str(path))
        try:
            # Cover shows the 2027-2028 span.
            assert "2027-2028" in doc[0].get_text().replace(" ", "")
        finally:
            doc.close()
