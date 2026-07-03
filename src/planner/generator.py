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
    year: int, weeks: list[date]
) -> dict[int, dict[int, int]]:
    """Build per-month maps of {day_of_month: week_index}."""
    month_maps: dict[int, dict[int, int]] = {m: {} for m in range(1, 13)}
    for wi, sunday in enumerate(weeks):
        for d in range(7):
            day_date = sunday + timedelta(days=d)
            if day_date.year == year:
                month_maps[day_date.month][day_date.day] = wi
    return month_maps


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
        ctx = PageContext(
            theme=theme,
            nav=nav,
            tabs=_build_top_tabs(spec, niche_pages),
            year=spec.year,
            design=design,
            geo=build_geometry(design.shell),
            motif=MOTIFS[design.motif],
        )
        weeks = _year_weeks(spec.year)

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
            for m in range(1, 13):
                days_in_month = _cal.monthrange(spec.year, m)[1]
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
            _build_week_link_maps(spec.year, weeks) if spec.include_weekly else {}
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

        for m in range(1, 13):
            wlm = week_link_maps.get(m) if spec.include_weekly else None
            MonthlyPage.render(pdf, ctx, month=m, week_link_map=wlm)

            if spec.include_monthly_plan:
                MonthlyPlanPage.render(pdf, ctx, month=m)
            if spec.include_monthly_review:
                MonthlyReviewPage.render(pdf, ctx, month=m)

            if spec.include_weekly:
                for wi, sunday in enumerate(weeks):
                    effective_month = sunday.month if sunday.year == spec.year else 1
                    if effective_month == m:
                        WeeklyPage.render(
                            pdf, ctx, week_index=wi, start_date=sunday
                        )

            if spec.include_daily:
                days_in_month = _cal.monthrange(spec.year, m)[1]
                for d in range(1, days_in_month + 1):
                    DailyPage.render(
                        pdf, ctx, day_date=date(spec.year, m, d), month=m
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
        if design.name == "classic":
            filename = f"{spec.year}_{spec.niche_slug}_{spec.palette_name}.pdf"
        else:
            filename = (f"{spec.year}_{spec.niche_slug}_{spec.palette_name}"
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
