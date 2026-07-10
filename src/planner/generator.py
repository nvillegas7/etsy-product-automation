"""PDF orchestrator -- assembles a complete planner from page renderers.

Landscape layout (482.0 x 361.2 mm) optimised for iPad Pro 12.9", drawn as
an open ring binder with migrating month tabs and niche-specific sections.

Page order
----------
Cover -> Index -> Year at a Glance
-> [Month: Calendar, Plan, Review, Weeks (, Days)] x 12
-> Niche pages -> Notes -> Habits -> Goals

Usage
-----
    from src.planner.generator import PlannerGenerator, PlannerSpec

    spec = PlannerSpec(title="2026 Planner", year=2026)
    path = PlannerGenerator().generate(spec)
"""

from __future__ import annotations

import calendar as _cal
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from fpdf import FPDF

from src.planner.designs import DesignTheme, get_design
from src.planner.layout import PAGE_HEIGHT, PAGE_WIDTH, build_geometry
from src.planner.motifs import MOTIFS
from src.planner.navigation import NavigationManager
from src.planner.niche_pages import (
    NichePageSpec,
    get_niche_config,
    get_niche_pages,
    render_niche_page,
)
from src.planner.pages import (
    CoverPage,
    DailyPage,
    GoalSettingPage,
    HabitTrackerPage,
    IndexPage,
    MonthlyPage,
    MonthlyPlanPage,
    MonthlyReviewPage,
    NotesPage,
    PageContext,
    WeeklyPage,
    YearGlancePage,
)
from src.planner.styles import Theme, build_theme

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output" / "planners"

_cal.setfirstweekday(_cal.SUNDAY)

MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB

# Max niche tabs shown in the top tab bar (plus INDEX/CALENDAR/WEEKLY)
_MAX_NICHE_TABS = 5


# ---------------------------------------------------------------------------
# PlannerSpec
# ---------------------------------------------------------------------------

@dataclass
class PlannerSpec:
    """Specification for a planner PDF."""

    title: str = "2026 Planner"
    display_title: str = ""   # SHORT human title rendered on the cover
    subtitle: str = ""
    year: int = 2026
    palette_name: str = "neutral_beige"
    include_weekly: bool = True
    include_daily: bool = False  # off by default to control file size
    include_notes: bool = True
    include_habits: bool = True
    include_goals: bool = True
    include_monthly_plan: bool = True
    include_monthly_review: bool = True
    include_niche_pages: bool = True
    niche_slug: str = "planner"
    # Academic-year + date-mode knobs.  Defaults reproduce today's planner
    # exactly (calendar Jan->Dec of ``year`` with real dates), so the golden
    # classic stays byte-identical.
    #   start_month : first month of the plan (8 = academic August start).
    #   date_mode   : "dated"      -> real dates for ``year``
    #                 "dated_next" -> real dates for ``year + 1``
    #                 "undated"    -> fill-in headers, no real dates (same graph)
    start_month: int = 1
    date_mode: str = "dated"
    # Design-parameter system: preset id + optional per-dimension overrides
    # (e.g. {"ink": "accent-pop"}).  The default renders today's planner.
    design: str = "classic"
    design_overrides: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Week helpers
# ---------------------------------------------------------------------------

def _year_weeks(year: int) -> list[date]:
    """Return a list of Sunday start-dates for every week that overlaps *year*."""
    jan1 = date(year, 1, 1)
    days_since_sunday = (jan1.weekday() + 1) % 7
    first_sunday = jan1 - timedelta(days=days_since_sunday)

    weeks: list[date] = []
    current = first_sunday
    while current.year <= year:
        week_end = current + timedelta(days=6)
        if week_end.year >= year and current <= date(year, 12, 31):
            weeks.append(current)
        current += timedelta(days=7)
    return weeks


def _build_week_link_maps(
    slots: list[tuple[int, int]], weeks: list[date]
) -> dict[int, dict[int, int]]:
    """Build per-month maps of {day_of_month: week_index}.

    *slots* is the ordered (calendar_month, calendar_year) sequence of this
    build.  A day links to a week only when its (month, year) is one of the
    slots -- so academic spans map Jan-2027 days to the January section
    rather than dropping them.
    """
    slot_set = set(slots)
    month_maps: dict[int, dict[int, int]] = {m: {} for m, _y in slots}
    for wi, sunday in enumerate(weeks):
        for d in range(7):
            day_date = sunday + timedelta(days=d)
            if (day_date.month, day_date.year) in slot_set:
                month_maps[day_date.month][day_date.day] = wi
    return month_maps


# ---------------------------------------------------------------------------
# Academic-year + date-mode helpers (defaults reproduce the calendar year)
# ---------------------------------------------------------------------------

def _date_year(spec: "PlannerSpec") -> int:
    """The calendar year this build's dates resolve to.

    ``dated_next`` shifts the anchor ``year`` by +1 (the "2027" half of a
    2026/2027 listing); ``dated`` and ``undated`` use ``year`` as-is.
    """
    return spec.year + (1 if spec.date_mode == "dated_next" else 0)


def _planner_slots(spec: "PlannerSpec") -> list[tuple[int, int]]:
    """The 12 ordered (calendar_month, calendar_year) slots of this build.

    ``start_month=1`` -> ``[(1,Y)..(12,Y)]`` (identical to the old
    ``range(1, 13)`` at ``spec.year``).  ``start_month=8`` -> Aug..Dec of the
    base year then Jan..Jul of the next (an academic year).
    """
    base_year = _date_year(spec)
    slots: list[tuple[int, int]] = []
    for i in range(12):
        raw = spec.start_month - 1 + i
        slots.append((raw % 12 + 1, base_year + raw // 12))
    return slots


def _span_weeks(base_year: int, start_month: int) -> list[date]:
    """Sunday start-dates for every week overlapping the 12-month span.

    ``_span_weeks(Y, 1)`` reproduces ``_year_weeks(Y)`` exactly.
    """
    start = date(base_year, start_month, 1)
    end_raw = start_month - 1 + 11
    end_month, end_year = end_raw % 12 + 1, base_year + end_raw // 12
    end = date(end_year, end_month, _cal.monthrange(end_year, end_month)[1])

    days_since_sunday = (start.weekday() + 1) % 7
    current = start - timedelta(days=days_since_sunday)
    weeks: list[date] = []
    while current <= end:
        if current + timedelta(days=6) >= start:
            weeks.append(current)
        current += timedelta(days=7)
    return weeks


def _week_section_month(sunday: date, slots: list[tuple[int, int]]) -> int:
    """Which month section a week (starting *sunday*) renders under.

    A week whose Sunday falls in one of the slots renders under that month;
    a boundary week that starts before the span folds into the first section.
    Reproduces the old ``sunday.month if sunday.year == year else 1`` for the
    calendar case while fixing the two-year cross-boundary collapse.
    """
    if (sunday.month, sunday.year) in set(slots):
        return sunday.month
    return slots[0][0]


def _span_label(spec: "PlannerSpec") -> str:
    """Readable cover / year-at-a-glance year text ("" keeps the classic year).

    Empty for the default calendar build so covers fall back to ``str(year)``
    and stay byte-identical.
    """
    if spec.date_mode == "undated":
        return "Undated"
    base = _date_year(spec)
    if spec.start_month != 1:
        return f"{base}-{base + 1}"
    if spec.date_mode == "dated_next":
        return str(base)
    return ""


def _year_part(spec: "PlannerSpec") -> str:
    """The filename year token; ``"2026"`` for the default (keeps classic name)."""
    if spec.date_mode == "undated":
        return "undated"
    base = _date_year(spec)
    if spec.start_month != 1:
        return f"{base}-{base + 1}"
    return str(base)


# ---------------------------------------------------------------------------
# Top tab construction
# ---------------------------------------------------------------------------

def _build_top_tabs(
    spec: PlannerSpec, niche_pages: list[NichePageSpec]
) -> list[tuple[str, str]]:
    """Niche-aware top category tabs: (label, link_key) pairs."""
    tabs: list[tuple[str, str]] = [
        ("INDEX", NavigationManager.index_key()),
        ("CALENDAR", NavigationManager.month_key(1)),
    ]
    if spec.include_weekly:
        tabs.append(("WEEKLY", NavigationManager.week_key(0)))

    for np_spec in niche_pages[:_MAX_NICHE_TABS]:
        tabs.append((np_spec.tab, NavigationManager.niche_page_key(np_spec.id)))

    # Pad with the generic sections when there is room
    generic = []
    if spec.include_notes:
        generic.append(("NOTES", NavigationManager.notes_key()))
    if spec.include_habits:
        generic.append(("HABITS", NavigationManager.habits_key()))
    if spec.include_goals:
        generic.append(("GOALS", NavigationManager.goals_key()))
    for tab in generic:
        if len(tabs) >= 8:
            break
        tabs.append(tab)
    return tabs


# ---------------------------------------------------------------------------
# PlannerGenerator
# ---------------------------------------------------------------------------

class PlannerGenerator:
    """Generates a complete planner PDF."""

    def generate(self, spec: PlannerSpec) -> Path:
        """Build a planner and write it to disk.  Returns the output path."""
        # ---- Create FPDF instance -----------------------------------------
        pdf = FPDF(unit="mm", format=(PAGE_WIDTH, PAGE_HEIGHT))
        pdf.set_auto_page_break(auto=False)
        pdf.set_margin(0)

        pdf.set_title(spec.title)
        pdf.set_author("Etsy Planner Bot")
        pdf.set_creator("etsy-planner-bot / fpdf2")

        design: DesignTheme = get_design(spec.design, spec.design_overrides)
        theme: Theme = build_theme(pdf, spec.palette_name, design)
        # NOTE: no section title styles are configured -- ``add_bookmark``
        # relies on that so outline entries never render text on the page.

        niche_cfg = get_niche_config(spec.niche_slug)
        niche_name = niche_cfg.get("name", "")
        niche_pages = get_niche_pages(spec.niche_slug) if spec.include_niche_pages else []

        nav = NavigationManager()
        slots = _planner_slots(spec)
        weeks = _span_weeks(_date_year(spec), spec.start_month)
        ctx = PageContext(
            theme=theme,
            nav=nav,
            tabs=_build_top_tabs(spec, niche_pages),
            year=spec.year,
            year_label=_span_label(spec),
            month_years={m: y for m, y in slots},
            undated=(spec.date_mode == "undated"),
            start_month=spec.start_month,
            design=design,
            geo=build_geometry(design.shell),
            motif=MOTIFS[design.motif],
        )

        # ---- Phase 1: Pre-allocate links ----------------------------------
        nav.register_link(pdf, NavigationManager.cover_key())
        nav.register_link(pdf, NavigationManager.index_key())
        nav.register_link(pdf, NavigationManager.year_glance_key())

        for m in range(1, 13):
            nav.register_link(pdf, NavigationManager.month_key(m))
            if spec.include_monthly_plan:
                nav.register_link(pdf, NavigationManager.monthly_plan_key(m))
            if spec.include_monthly_review:
                nav.register_link(pdf, NavigationManager.monthly_review_key(m))

        if spec.include_weekly:
            for wi in range(len(weeks)):
                nav.register_link(pdf, NavigationManager.week_key(wi))

        if spec.include_daily:
            for m, cal_year in slots:
                days_in_month = _cal.monthrange(cal_year, m)[1]
                for d in range(1, days_in_month + 1):
                    nav.register_link(pdf, NavigationManager.daily_key(m, d))

        for np_spec in niche_pages:
            nav.register_link(pdf, NavigationManager.niche_page_key(np_spec.id))

        if spec.include_notes:
            nav.register_link(pdf, NavigationManager.notes_key())
        if spec.include_habits:
            nav.register_link(pdf, NavigationManager.habits_key())
        if spec.include_goals:
            nav.register_link(pdf, NavigationManager.goals_key())

        week_link_maps = (
            _build_week_link_maps(slots, weeks) if spec.include_weekly else {}
        )

        # ---- Phase 2: Render pages ----------------------------------------

        CoverPage.render(
            pdf, ctx,
            title=spec.title,
            display_title=spec.display_title,
            subtitle=spec.subtitle,
            niche_name=niche_name,
        )

        IndexPage.render(
            pdf, ctx,
            niche_name=niche_name,
            niche_pages=[{"id": p.id, "label": p.label} for p in niche_pages],
        )

        YearGlancePage.render(pdf, ctx)

        for m, cal_year in slots:
            wlm = week_link_maps.get(m) if spec.include_weekly else None
            MonthlyPage.render(pdf, ctx, month=m, week_link_map=wlm)

            if spec.include_monthly_plan:
                MonthlyPlanPage.render(pdf, ctx, month=m)
            if spec.include_monthly_review:
                MonthlyReviewPage.render(pdf, ctx, month=m)

            if spec.include_weekly:
                for wi, sunday in enumerate(weeks):
                    if _week_section_month(sunday, slots) == m:
                        WeeklyPage.render(
                            pdf, ctx, week_index=wi, start_date=sunday, month=m
                        )

            if spec.include_daily:
                days_in_month = _cal.monthrange(cal_year, m)[1]
                for d in range(1, days_in_month + 1):
                    DailyPage.render(
                        pdf, ctx, day_date=date(cal_year, m, d), month=m
                    )

        for np_spec in niche_pages:
            render_niche_page(pdf, ctx, np_spec)

        if spec.include_notes:
            NotesPage.render(pdf, ctx)
        if spec.include_habits:
            HabitTrackerPage.render(pdf, ctx)
        if spec.include_goals:
            GoalSettingPage.render(pdf, ctx)

        # ---- Phase 3: Write & validate ------------------------------------
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        year_part = _year_part(spec)
        if design.name == "classic":
            filename = f"{year_part}_{spec.niche_slug}_{spec.palette_name}.pdf"
        else:
            filename = (f"{year_part}_{spec.niche_slug}_{spec.palette_name}"
                        f"_{design.name}.pdf")
        out_path = OUTPUT_DIR / filename

        pdf.output(str(out_path))
        file_size = out_path.stat().st_size

        logger.info(
            "Generated %s  (%d pages, %.2f MB)",
            out_path,
            pdf.pages_count,
            file_size / (1024 * 1024),
        )

        if file_size > MAX_FILE_SIZE_BYTES:
            logger.warning(
                "File size %.2f MB exceeds 20 MB limit!  "
                "Consider disabling daily pages.",
                file_size / (1024 * 1024),
            )

        return out_path
