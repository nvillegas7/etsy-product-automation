"""Niche-specific page renderers -- the pages that differentiate each planner.

Every niche in ``config/niches.yaml`` declares a ``niche_pages`` list of
``{id, label, tab}`` entries.  Each ``id`` maps to a renderer here that
draws a dedicated two-page spread with full chrome (tabs, coil, links).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml
from fpdf import FPDF

from src.planner.layout import Panel
from src.planner.navigation import NavigationManager
from src.planner.pages import (
    PageContext,
    _accent_note_font,
    begin_content_page,
    page_header,
    render_back_link,
)
from src.planner.widgets import (
    WHITE,
    blend,
    checkbox_lines,
    fill_texture,
    labelled_box,
    progress_bar,
    ruled_lines,
    section_label,
    table,
    water_droplets,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
NICHES_PATH = PROJECT_ROOT / "config" / "niches.yaml"


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NichePageSpec:
    """One niche page declaration from niches.yaml."""

    id: str
    label: str
    tab: str


_NICHES_CACHE: dict | None = None


def _niches() -> dict:
    global _NICHES_CACHE
    if _NICHES_CACHE is None:
        try:
            with open(NICHES_PATH) as fh:
                _NICHES_CACHE = yaml.safe_load(fh).get("niches", {})
        except Exception:
            logger.exception("Could not load niches.yaml")
            _NICHES_CACHE = {}
    return _NICHES_CACHE


def get_niche_config(niche_slug: str) -> dict:
    """Full niche dict from niches.yaml ({} for unknown slugs)."""
    return _niches().get(niche_slug, {})


def get_niche_pages(niche_slug: str) -> list[NichePageSpec]:
    """Niche page specs for *niche_slug* (empty list when none declared)."""
    raw = get_niche_config(niche_slug).get("niche_pages", []) or []
    specs = []
    for entry in raw:
        page_id = entry.get("id")
        if page_id not in RENDERERS:
            logger.warning("No renderer for niche page id '%s' -- skipping", page_id)
            continue
        specs.append(NichePageSpec(
            id=page_id,
            label=entry.get("label", page_id.replace("_", " ").title()),
            tab=entry.get("tab", page_id[:8].upper()),
        ))
    return specs


# ---------------------------------------------------------------------------
# Shared scaffold
# ---------------------------------------------------------------------------

def render_niche_page(pdf: FPDF, ctx: PageContext, spec: NichePageSpec) -> None:
    """Chrome + header + dispatch to the specific renderer."""
    begin_content_page(
        pdf, ctx,
        bind_key=NavigationManager.niche_page_key(spec.id),
        bookmark=spec.label,
        bookmark_level=0,
        active_tab=spec.tab,
    )
    words = spec.label.split()
    light = words[0].upper() if len(words) > 1 else ""
    bold = " ".join(words[1:]).upper() if len(words) > 1 else spec.label.upper()
    page_header(pdf, ctx, light, bold)
    render_back_link(pdf, ctx, NavigationManager.index_key(), "Back to Index")
    # Motif band under the header zone (never on binder; poster's nav strip
    # occupies that zone)
    if ctx.design.shell in ("cards", "flat"):
        lb = ctx.geo.left_body()
        ctx.motif.band(pdf, ctx.theme, lb.x, ctx.geo.body_y - 6.5, lb.w, 5.0)
    RENDERERS[spec.id](pdf, ctx)
    pdf.set_text_color(0, 0, 0)


# ---------------------------------------------------------------------------
# Small shared pieces
# ---------------------------------------------------------------------------

def _numbered_lines(pdf: FPDF, ctx: PageContext, panel: Panel, n: int) -> None:
    theme = ctx.theme
    gr = theme.rule_c()
    gap = panel.h / n
    for i in range(n):
        ly = panel.y + (i + 1) * gap - 2
        pdf.set_text_color(*theme.rgb("text_light"))
        theme.set_type(pdf, "inline_label", size=7)
        pdf.set_xy(panel.x, ly - 3.5)
        pdf.cell(6, 4, f"{i + 1}.", align="L")
        pdf.set_draw_color(*gr)
        pdf.line(panel.x + 7, ly, panel.x2, ly)


def _month_cols_header(pdf: FPDF, ctx: PageContext, x: float, y: float,
                       cell_w: float, h: float) -> None:
    months = "JFMAMJJASOND"
    ctx.theme.set_type(pdf, "inline_label", size=5.2)
    pdf.set_text_color(*ctx.theme.band_text_c())
    for i, ch in enumerate(months):
        pdf.set_xy(x + i * cell_w, y)
        pdf.cell(cell_w, h, ch, align="C")


# ===================================================================
# BUDGET PLANNER
# ===================================================================

def _budget_overview(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    lb, rb = ctx.geo.left_body(), ctx.geo.right_body()

    # Left: summary boxes + income + fixed expenses
    secs = lb.split_v([0.13, 0.35, 0.52], gap=7)
    for box, label in zip(secs[0].cols(3, gap=5),
                          ("Total Income", "Total Expenses", "Total Saved")):
        labelled_box(pdf, theme, box, label, label_h=6.5, lines_spacing=None)
    y = section_label(pdf, theme, secs[1].x, secs[1].y, "Income",
                      underline_w=secs[1].w)
    table(pdf, theme, Panel(secs[1].x, y, secs[1].w, secs[1].y2 - y),
          [("Source", 0.5), ("Planned", 0.25), ("Actual", 0.25)], n_rows=6)
    y = section_label(pdf, theme, secs[2].x, secs[2].y, "Fixed Expenses",
                      underline_w=secs[2].w)
    table(pdf, theme, Panel(secs[2].x, y, secs[2].w, secs[2].y2 - y),
          [("Expense", 0.4), ("Planned", 0.2), ("Actual", 0.2), ("Diff", 0.2)],
          n_rows=9)

    # Right: variable spending + savings + notes
    rsecs = rb.split_v([0.52, 0.25, 0.23], gap=7)
    y = section_label(pdf, theme, rsecs[0].x, rsecs[0].y, "Variable Spending",
                      underline_w=rsecs[0].w)
    table(pdf, theme, Panel(rsecs[0].x, y, rsecs[0].w, rsecs[0].y2 - y),
          [("Category", 0.4), ("Budget", 0.2), ("Spent", 0.2), ("Left", 0.2)],
          n_rows=9)
    y = section_label(pdf, theme, rsecs[1].x, rsecs[1].y, "Savings & Investments",
                      underline_w=rsecs[1].w)
    table(pdf, theme, Panel(rsecs[1].x, y, rsecs[1].w, rsecs[1].y2 - y),
          [("Account", 0.5), ("Goal", 0.25), ("Added", 0.25)], n_rows=4)
    labelled_box(pdf, theme, rsecs[2], "Notes", lines_spacing=7.5)


def _expense_log(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    cols = [("Date", 0.14), ("Category", 0.22), ("Description", 0.44),
            ("Amount", 0.20)]
    for panel in (ctx.geo.left_body(), ctx.geo.right_body()):
        table(pdf, theme, panel, cols, n_rows=26, zebra=True)


def _savings_goals(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    gr = theme.rule_c()
    for panel in (ctx.geo.left_body(), ctx.geo.right_body()):
        for card in panel.rows(3, gap=8):
            border = theme.border_c()
            pdf.set_fill_color(*WHITE)
            pdf.set_draw_color(*border)
            pdf.set_line_width(0.35)
            pdf.rect(card.x, card.y, card.w, card.h, style="FD",
                     round_corners=True, corner_radius=2.2)
            inner = card.inset(6, 5)
            theme.set_type(pdf, "inline_label", size=7.5)
            pdf.set_text_color(*theme.rgb("text_light"))
            pdf.set_xy(inner.x, inner.y)
            pdf.cell(28, 5, "SAVING FOR", align="L")
            pdf.set_draw_color(*gr)
            pdf.line(inner.x + 29, inner.y + 4.4, inner.x2, inner.y + 4.4)
            row_y = inner.y + 12
            half = inner.w / 2
            for i, lbl in enumerate(("GOAL AMOUNT", "DEADLINE")):
                pdf.set_xy(inner.x + i * half, row_y)
                pdf.cell(30, 5, lbl, align="L")
                pdf.line(inner.x + i * half + 31, row_y + 4.4,
                         inner.x + (i + 1) * half - 6, row_y + 4.4)
            y = section_label(pdf, theme, inner.x, row_y + 10, "Progress",
                              size=7)
            progress_bar(pdf, theme, inner.x + 1, y + 1, inner.w - 8, h=7,
                         ticks=10)
            # Deposit log fills the rest of the card
            y = section_label(pdf, theme, inner.x, y + 14, "Deposit Log",
                              size=7)
            log = Panel(inner.x, y, inner.w, inner.y2 - y)
            if log.h > 12:
                table(pdf, theme, log,
                      [("Date", 0.25), ("Amount", 0.25), ("Date", 0.25),
                       ("Amount", 0.25)],
                      n_rows=max(2, int((log.h - 6) / 8)), header_h=5.5,
                      font_size=6.5)


def _bill_tracker(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    for panel in (ctx.geo.left_body(), ctx.geo.right_body()):
        y = section_label(pdf, theme, panel.x, panel.y,
                          "Bills · Check Off When Paid", underline_w=panel.w)
        grid = Panel(panel.x, y + 1, panel.w, panel.y2 - y - 1)
        bill_w, amount_w = grid.w * 0.28, grid.w * 0.14
        month_w = (grid.w - bill_w - amount_w) / 12
        header_h = 6.5
        n_rows = 13
        row_h = (grid.h - header_h) / n_rows

        band = theme.band_fill()
        if band is not None:
            pdf.set_fill_color(*band)
            pdf.rect(grid.x, grid.y, grid.w, header_h, style="F")
        theme.set_type(pdf, "inline_label", size=6)
        pdf.set_text_color(*theme.band_text_c())
        pdf.set_xy(grid.x, grid.y)
        pdf.cell(bill_w, header_h, "BILL", align="C")
        pdf.set_xy(grid.x + bill_w, grid.y)
        pdf.cell(amount_w, header_h, "AMT", align="C")
        _month_cols_header(pdf, ctx, grid.x + bill_w + amount_w, grid.y,
                           month_w, header_h)

        gr = theme.rule_c()
        pdf.set_draw_color(*gr)
        pdf.set_line_width(0.2)
        for r in range(n_rows + 1):
            ry = grid.y + header_h + r * row_h
            pdf.line(grid.x, ry, grid.x2, ry)
        xs = [grid.x, grid.x + bill_w, grid.x + bill_w + amount_w]
        xs += [grid.x + bill_w + amount_w + i * month_w for i in range(1, 13)]
        xs.append(grid.x2)
        for x in xs:
            pdf.line(x, grid.y, x, grid.y2)
        pdf.set_draw_color(*theme.border_c())
        pdf.set_line_width(0.3)
        pdf.rect(grid.x, grid.y, grid.w, grid.h, style="D")


def _debt_tracker(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    lb, rb = ctx.geo.left_body(), ctx.geo.right_body()
    y = section_label(pdf, theme, lb.x, lb.y, "Debts", underline_w=lb.w)
    table(pdf, theme, Panel(lb.x, y, lb.w, lb.y2 - y),
          [("Creditor", 0.3), ("Balance", 0.2), ("Rate", 0.15),
           ("Min Due", 0.175), ("Paid Off", 0.175)], n_rows=12)

    rsecs = rb.split_v([0.55, 0.45], gap=7)
    y = section_label(pdf, theme, rsecs[0].x, rsecs[0].y, "Payoff Progress",
                      underline_w=rsecs[0].w)
    prog = Panel(rsecs[0].x, y + 2, rsecs[0].w, rsecs[0].y2 - y - 2)
    gr = theme.rule_c()
    for row in prog.rows(5, gap=6):
        theme.set_type(pdf, "inline_label", size=6.5)
        pdf.set_text_color(*theme.rgb("text_light"))
        pdf.set_xy(row.x, row.y)
        pdf.cell(14, 4, "DEBT", align="L")
        pdf.set_draw_color(*gr)
        pdf.line(row.x + 15, row.y + 3.6, row.x + row.w * 0.55, row.y + 3.6)
        progress_bar(pdf, theme, row.x + 1, row.y + 7, row.w - 8,
                     h=min(6.5, row.h - 11), ticks=10)
    y = section_label(pdf, theme, rsecs[1].x, rsecs[1].y, "Payment Log",
                      underline_w=rsecs[1].w)
    table(pdf, theme, Panel(rsecs[1].x, y, rsecs[1].w, rsecs[1].y2 - y),
          [("Date", 0.2), ("Debt", 0.4), ("Payment", 0.2), ("Balance", 0.2)],
          n_rows=8)


def _subscription_tracker(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    lb, rb = ctx.geo.left_body(), ctx.geo.right_body()
    y = section_label(pdf, theme, lb.x, lb.y, "Active Subscriptions",
                      underline_w=lb.w)
    table(pdf, theme, Panel(lb.x, y, lb.w, lb.y2 - y),
          [("Service", 0.34), ("Cost", 0.16), ("Billing", 0.18),
           ("Renewal", 0.18), ("Cancel?", 0.14)], n_rows=16, zebra=True)

    rsecs = rb.split_v([0.14, 0.5, 0.36], gap=7)
    for box, label in zip(rsecs[0].cols(2, gap=6),
                          ("Monthly Total", "Yearly Total")):
        labelled_box(pdf, theme, box, label, label_h=6.5, lines_spacing=None)
    y = section_label(pdf, theme, rsecs[1].x, rsecs[1].y, "Free Trials to Watch",
                      underline_w=rsecs[1].w)
    table(pdf, theme, Panel(rsecs[1].x, y, rsecs[1].w, rsecs[1].y2 - y),
          [("Service", 0.4), ("Trial Ends", 0.3), ("Decision", 0.3)], n_rows=7)
    y = section_label(pdf, theme, rsecs[2].x, rsecs[2].y, "Cancelled This Year",
                      underline_w=rsecs[2].w)
    table(pdf, theme, Panel(rsecs[2].x, y, rsecs[2].w, rsecs[2].y2 - y),
          [("Service", 0.5), ("Date", 0.25), ("Saved / mo", 0.25)], n_rows=5)


# ===================================================================
# STUDENT PLANNER
# ===================================================================

def _class_schedule(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    lb, rb = ctx.geo.left_body(), ctx.geo.right_body()

    def timetable(panel: Panel, days: list[str]) -> None:
        time_w = 16.0
        header_h = 7.0
        day_w = (panel.w - time_w) / len(days)
        hours = list(range(8, 19))  # 8 AM - 6 PM
        row_h = (panel.h - header_h) / len(hours)
        band = theme.band_fill()
        if band is not None:
            pdf.set_fill_color(*band)
            pdf.rect(panel.x, panel.y, panel.w, header_h, style="F")
        theme.set_type(pdf, "inline_label", size=6.5)
        pdf.set_text_color(*theme.band_text_c())
        for i, d in enumerate(days):
            pdf.set_xy(panel.x + time_w + i * day_w, panel.y)
            pdf.cell(day_w, header_h, d.upper(), align="C")
        gr = theme.rule_c()
        theme.set_type(pdf, "mini_digit", size=5.6)
        pdf.set_text_color(*theme.rgb("text_light"))
        for i, hour in enumerate(hours):
            hy = panel.y + header_h + i * row_h
            h12 = hour if hour <= 12 else hour - 12
            pdf.set_xy(panel.x, hy)
            pdf.cell(time_w - 1.5, row_h, f"{h12}:00", align="R")
            pdf.set_draw_color(*gr)
            pdf.set_line_width(0.2)
            pdf.line(panel.x, hy, panel.x2, hy)
        for i in range(len(days) + 1):
            x = panel.x + time_w + i * day_w
            pdf.line(x, panel.y, x, panel.y2)
        pdf.set_draw_color(*theme.border_c())
        pdf.set_line_width(0.3)
        pdf.rect(panel.x, panel.y, panel.w, panel.h, style="D")

    timetable(lb, ["Mon", "Tue", "Wed"])
    rsecs = rb.split_v([0.72, 0.28], gap=7)
    timetable(rsecs[0], ["Thu", "Fri"])
    y = section_label(pdf, theme, rsecs[1].x, rsecs[1].y, "Class List",
                      underline_w=rsecs[1].w)
    table(pdf, theme, Panel(rsecs[1].x, y, rsecs[1].w, rsecs[1].y2 - y),
          [("Class", 0.45), ("Room", 0.2), ("Professor", 0.35)], n_rows=4)


def _assignment_tracker(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    cols = [("Due", 0.13), ("Course", 0.2), ("Assignment", 0.45),
            ("Priority", 0.12), ("Done", 0.10)]
    for panel in (ctx.geo.left_body(), ctx.geo.right_body()):
        table(pdf, theme, panel, cols, n_rows=22, zebra=True)


def _exam_tracker(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    gr = theme.rule_c()
    for panel in (ctx.geo.left_body(), ctx.geo.right_body()):
        for card in panel.rows(3, gap=7):
            border = theme.border_c()
            pdf.set_fill_color(*WHITE)
            pdf.set_draw_color(*border)
            pdf.set_line_width(0.35)
            pdf.rect(card.x, card.y, card.w, card.h, style="FD",
                     round_corners=True, corner_radius=2.2)
            inner = card.inset(6, 5)
            theme.set_type(pdf, "inline_label", size=7)
            pdf.set_text_color(*theme.rgb("text_light"))
            row1 = [("COURSE", 0.42), ("DATE", 0.30), ("TIME", 0.28)]
            x = inner.x
            for lbl, frac in row1:
                w = inner.w * frac
                pdf.set_xy(x, inner.y)
                pdf.cell(pdf.get_string_width(lbl) + 1, 5, lbl, align="L")
                pdf.set_draw_color(*gr)
                pdf.line(x + pdf.get_string_width(lbl) + 2, inner.y + 4.4,
                         x + w - 4, inner.y + 4.4)
                x += w
            y = section_label(pdf, theme, inner.x, inner.y + 9,
                              "Topics to Study", size=7)
            checkbox_lines(pdf, theme, Panel(inner.x, y, inner.w * 0.62,
                                             inner.y2 - y), spacing=7.6)
            score = Panel(inner.x + inner.w * 0.68, y + 2, inner.w * 0.3,
                          inner.y2 - y - 4)
            labelled_box(pdf, theme, score, "Score", label_h=6,
                         lines_spacing=None)


def _grade_log(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    lb, rb = ctx.geo.left_body(), ctx.geo.right_body()
    y = section_label(pdf, theme, lb.x, lb.y, "Assignments & Tests",
                      underline_w=lb.w)
    table(pdf, theme, Panel(lb.x, y, lb.w, lb.y2 - y),
          [("Date", 0.14), ("Course", 0.22), ("Assignment", 0.34),
           ("Score", 0.15), ("Weight", 0.15)], n_rows=18, zebra=True)
    rsecs = rb.split_v([0.6, 0.4], gap=7)
    y = section_label(pdf, theme, rsecs[0].x, rsecs[0].y, "Grades by Course",
                      underline_w=rsecs[0].w)
    table(pdf, theme, Panel(rsecs[0].x, y, rsecs[0].w, rsecs[0].y2 - y),
          [("Course", 0.34), ("Current", 0.22), ("Target", 0.22),
           ("Final", 0.22)], n_rows=8)
    y = section_label(pdf, theme, rsecs[1].x, rsecs[1].y, "GPA Tracker",
                      underline_w=rsecs[1].w)
    table(pdf, theme, Panel(rsecs[1].x, y, rsecs[1].w, rsecs[1].y2 - y),
          [("Term", 0.34), ("Credits", 0.33), ("GPA", 0.33)], n_rows=4)


def _semester_goals(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    lb, rb = ctx.geo.left_body(), ctx.geo.right_body()
    secs = lb.split_v([0.2, 0.8], gap=7)
    labelled_box(pdf, theme, secs[0], "This Semester I Want To...", fill=True)
    y = section_label(pdf, theme, secs[1].x, secs[1].y, "Academic Goals",
                      underline_w=secs[1].w)
    goals = Panel(secs[1].x, y + 1, secs[1].w, secs[1].y2 - y - 1)
    gr = theme.rule_c()
    for card in goals.rows(3, gap=6):
        pdf.set_draw_color(*theme.border_c())
        pdf.set_line_width(0.3)
        pdf.rect(card.x, card.y, card.w, card.h, style="D",
                 round_corners=True, corner_radius=2)
        inner = card.inset(5, 4)
        theme.set_type(pdf, "inline_label", size=7)
        pdf.set_text_color(*theme.rgb("text_light"))
        pdf.set_xy(inner.x, inner.y)
        pdf.cell(14, 5, "GOAL", align="L")
        pdf.set_draw_color(*gr)
        pdf.line(inner.x + 15, inner.y + 4.2, inner.x2, inner.y + 4.2)
        y2 = section_label(pdf, theme, inner.x, inner.y + 8, "Steps", size=6.5)
        checkbox_lines(pdf, theme, Panel(inner.x, y2 - 1, inner.w,
                                         inner.y2 - y2 + 1), spacing=7.8)
    rsecs = rb.split_v([0.45, 0.3, 0.25], gap=7)
    y = section_label(pdf, theme, rsecs[0].x, rsecs[0].y, "Personal Goals",
                      underline_w=rsecs[0].w)
    checkbox_lines(pdf, theme, Panel(rsecs[0].x, y, rsecs[0].w,
                                     rsecs[0].y2 - y), spacing=9.5)
    y = section_label(pdf, theme, rsecs[1].x, rsecs[1].y, "Habits to Build",
                      underline_w=rsecs[1].w)
    checkbox_lines(pdf, theme, Panel(rsecs[1].x, y, rsecs[1].w,
                                     rsecs[1].y2 - y), spacing=9.5)
    labelled_box(pdf, theme, rsecs[2], "Reward for Crushing It", fill=True)


def _reading_list(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    cols = [("#", 0.06), ("Title", 0.4), ("Author", 0.26),
            ("Due", 0.13), ("Read", 0.15)]
    lb, rb = ctx.geo.left_body(), ctx.geo.right_body()
    y = section_label(pdf, theme, lb.x, lb.y, "Required Reading",
                      underline_w=lb.w)
    table(pdf, theme, Panel(lb.x, y, lb.w, lb.y2 - y), cols, n_rows=16,
          zebra=True, row_labels=[str(i + 1) for i in range(16)])
    rsecs = rb.split_v([0.62, 0.38], gap=7)
    y = section_label(pdf, theme, rsecs[0].x, rsecs[0].y, "Reading for Fun",
                      underline_w=rsecs[0].w)
    table(pdf, theme, Panel(rsecs[0].x, y, rsecs[0].w, rsecs[0].y2 - y),
          [("Title", 0.45), ("Author", 0.3), ("Rating", 0.25)], n_rows=9)
    labelled_box(pdf, theme, rsecs[1], "Favorite Quotes", lines_spacing=8.5)


# ===================================================================
# FITNESS PLANNER
# ===================================================================

def _workout_log(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    lb, rb = ctx.geo.left_body(), ctx.geo.right_body()
    for panel, title in ((lb, "Workout A"), (rb, "Workout B")):
        secs = panel.split_v([0.05, 0.72, 0.23], gap=5)
        date_row = secs[0]
        theme.set_type(pdf, "inline_label", size=7.5)
        pdf.set_text_color(*theme.rgb("text_light"))
        gr = theme.rule_c()
        for i, lbl in enumerate(("DATE", "FOCUS", "DURATION")):
            x = date_row.x + i * date_row.w / 3
            pdf.set_xy(x, date_row.y + 2)
            pdf.cell(pdf.get_string_width(lbl) + 1, 5, lbl, align="L")
            pdf.set_draw_color(*gr)
            pdf.line(x + pdf.get_string_width(lbl) + 2, date_row.y + 6.4,
                     x + date_row.w / 3 - 6, date_row.y + 6.4)
        y = section_label(pdf, theme, secs[1].x, secs[1].y, "Strength",
                          underline_w=secs[1].w)
        table(pdf, theme, Panel(secs[1].x, y, secs[1].w, secs[1].y2 - y),
              [("Exercise", 0.4), ("Sets", 0.15), ("Reps", 0.15),
               ("Weight", 0.15), ("Rest", 0.15)], n_rows=12)
        y = section_label(pdf, theme, secs[2].x, secs[2].y, "Cardio",
                          underline_w=secs[2].w)
        table(pdf, theme, Panel(secs[2].x, y, secs[2].w, secs[2].y2 - y),
              [("Activity", 0.4), ("Time", 0.2), ("Distance", 0.2),
               ("Cals", 0.2)], n_rows=3)


def _measurements(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    lb, rb = ctx.geo.left_body(), ctx.geo.right_body()
    y = section_label(pdf, theme, lb.x, lb.y, "Body Measurements · Monthly",
                      underline_w=lb.w)
    table(pdf, theme, Panel(lb.x, y, lb.w, lb.y2 - y),
          [("", 0.22), ("Start", 0.13), ("M1", 0.13), ("M2", 0.13),
           ("M3", 0.13), ("M4", 0.13), ("Goal", 0.13)],
          n_rows=10,
          row_labels=["Weight", "Chest", "Waist", "Hips", "L Arm", "R Arm",
                      "L Thigh", "R Thigh", "Calves", "Body Fat %"])
    rsecs = rb.split_v([0.62, 0.38], gap=7)
    y = section_label(pdf, theme, rsecs[0].x, rsecs[0].y,
                      "Progress Chart · Plot It", underline_w=rsecs[0].w)
    chart = Panel(rsecs[0].x, y + 2, rsecs[0].w, rsecs[0].y2 - y - 2)
    gr = theme.rule_c()
    pdf.set_draw_color(*gr)
    pdf.set_line_width(0.2)
    n_cols, n_rows = 12, 10
    for i in range(n_rows + 1):
        yy = chart.y + i * chart.h / n_rows
        pdf.line(chart.x, yy, chart.x2, yy)
    for i in range(n_cols + 1):
        xx = chart.x + i * chart.w / n_cols
        pdf.line(xx, chart.y, xx, chart.y2)
    pdf.set_draw_color(*theme.border_c())
    pdf.set_line_width(0.3)
    pdf.rect(chart.x, chart.y, chart.w, chart.h, style="D")
    labelled_box(pdf, theme, rsecs[1], "How I Feel This Month",
                 lines_spacing=8.5)


def _meal_planner(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    lb, rb = ctx.geo.left_body(), ctx.geo.right_body()

    def meal_grid(panel: Panel, days: list[str]) -> None:
        label_w = 20.0
        header_h = 7.0
        col_w = (panel.w - label_w) / 4
        row_h = (panel.h - header_h) / len(days)
        band = theme.band_fill()
        if band is not None:
            pdf.set_fill_color(*band)
            pdf.rect(panel.x, panel.y, panel.w, header_h, style="F")
        theme.set_type(pdf, "inline_label", size=6.2)
        pdf.set_text_color(*theme.band_text_c())
        for i, meal in enumerate(("BREAKFAST", "LUNCH", "DINNER", "SNACKS")):
            pdf.set_xy(panel.x + label_w + i * col_w, panel.y)
            pdf.cell(col_w, header_h, meal, align="C")
        gr = theme.rule_c()
        for i, d in enumerate(days):
            ry = panel.y + header_h + i * row_h
            theme.set_type(pdf, "inline_label", size=6.5)
            pdf.set_text_color(*theme.rgb("text_light"))
            pdf.set_xy(panel.x, ry)
            pdf.cell(label_w - 2, row_h, d.upper(), align="L")
            pdf.set_draw_color(*gr)
            pdf.set_line_width(0.2)
            pdf.line(panel.x, ry, panel.x2, ry)
        for i in range(5):
            x = panel.x + label_w + i * col_w
            pdf.line(x, panel.y, x, panel.y2)
        pdf.set_draw_color(*theme.border_c())
        pdf.set_line_width(0.3)
        pdf.rect(panel.x, panel.y, panel.w, panel.h, style="D")

    meal_grid(lb, ["Mon", "Tue", "Wed", "Thu"])
    rsecs = rb.split_v([0.56, 0.44], gap=7)
    meal_grid(rsecs[0], ["Fri", "Sat", "Sun"])
    y = section_label(pdf, theme, rsecs[1].x, rsecs[1].y, "Grocery List",
                      underline_w=rsecs[1].w)
    half = Panel(rsecs[1].x, y, rsecs[1].w, rsecs[1].y2 - y)
    for colp in half.cols(2, gap=8):
        checkbox_lines(pdf, theme, colp, spacing=8.4)


def _hydration_steps(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    lb, rb = ctx.geo.left_body(), ctx.geo.right_body()
    gr = theme.rule_c()

    y = section_label(pdf, theme, lb.x, lb.y,
                      "Water Intake · 8 Cups a Day", underline_w=lb.w)
    grid = Panel(lb.x, y + 2, lb.w, lb.y2 - y - 2)
    row_h = grid.h / 16
    for i in range(16):
        ry = grid.y + i * row_h
        theme.set_type(pdf, "inline_label", size=6)
        pdf.set_text_color(*theme.rgb("text_light"))
        pdf.set_xy(grid.x, ry)
        pdf.cell(14, row_h, f"Day {i + 1}", align="L")
        water_droplets(pdf, theme, grid.x + 24, ry + row_h / 2 - 1.6, n=8,
                       gap=(grid.w - 30) / 8)
        pdf.set_draw_color(*gr)
        pdf.set_line_width(0.15)
        pdf.line(grid.x, ry + row_h, grid.x2, ry + row_h)

    rsecs = rb.split_v([0.62, 0.38], gap=7)
    y = section_label(pdf, theme, rsecs[0].x, rsecs[0].y,
                      "Daily Steps · Color the Bar", underline_w=rsecs[0].w)
    chart = Panel(rsecs[0].x + 14, y + 2, rsecs[0].w - 14, rsecs[0].y2 - y - 8)
    n_days = 14
    col_w = chart.w / n_days
    pdf.set_draw_color(*blend(gr, theme.structural(), 0.3))
    pdf.set_line_width(0.25)
    for i in range(n_days):
        x = chart.x + i * col_w
        pdf.rect(x + col_w * 0.2, chart.y, col_w * 0.6, chart.h, style="D",
                 round_corners=("TOP_LEFT", "TOP_RIGHT"), corner_radius=1.2)
        theme.set_type(pdf, "mini_digit", size=5)
        pdf.set_text_color(*theme.rgb("text_light"))
        pdf.set_xy(x, chart.y2 + 1)
        pdf.cell(col_w, 3, str(i + 1), align="C")
    for i, lbl in enumerate(("10k", "7.5k", "5k", "2.5k")):
        yy = chart.y + i * chart.h / 4
        pdf.set_xy(rsecs[0].x - 2, yy - 1.5)
        theme.set_type(pdf, "mini_digit", size=5)
        pdf.cell(14, 3, lbl, align="L")
        pdf.set_draw_color(*gr)
        pdf.line(chart.x, yy, chart.x2, yy)
    y = section_label(pdf, theme, rsecs[1].x, rsecs[1].y, "Sleep Log",
                      underline_w=rsecs[1].w)
    table(pdf, theme, Panel(rsecs[1].x, y, rsecs[1].w, rsecs[1].y2 - y),
          [("Day", 0.2), ("Bedtime", 0.27), ("Wake Up", 0.27),
           ("Hours", 0.26)], n_rows=7)


def _progress_photos(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    gr = theme.rule_c()
    for panel, title in ((ctx.geo.left_body(), "Where I Started"),
                         (ctx.geo.right_body(), "Where I Am Now")):
        y = section_label(pdf, theme, panel.x, panel.y, title,
                          underline_w=panel.w)
        theme.set_type(pdf, "inline_label", size=7)
        pdf.set_text_color(*theme.rgb("text_light"))
        pdf.set_xy(panel.x, y + 1)
        pdf.cell(12, 5, "DATE", align="L")
        pdf.set_draw_color(*gr)
        pdf.line(panel.x + 13, y + 5.2, panel.x + 70, y + 5.2)
        frames = Panel(panel.x, y + 10, panel.w, panel.y2 - y - 34)
        for frame, lbl in zip(frames.cols(3, gap=6), ("FRONT", "SIDE", "BACK")):
            pdf.set_fill_color(*(theme.box_fill() or WHITE))
            pdf.set_draw_color(*theme.border_c())
            pdf.set_line_width(0.35)
            pdf.rect(frame.x, frame.y, frame.w, frame.h, style="FD",
                     round_corners=True, corner_radius=2.5)
            # camera glyph: rounded body + lens
            ccx, ccy = frame.x + frame.w / 2, frame.y + frame.h / 2
            pdf.set_draw_color(*blend(theme.rgb("secondary"),
                                      theme.structural(), 0.3))
            pdf.set_line_width(0.5)
            pdf.rect(ccx - 6, ccy - 4, 12, 9, style="D",
                     round_corners=True, corner_radius=1.5)
            pdf.ellipse(ccx - 2.4, ccy - 1.9, 4.8, 4.8, style="D")
            pdf.rect(ccx - 2, ccy - 5.8, 4, 2, style="D")
            theme.set_type(pdf, "inline_label", size=6.5)
            pdf.set_text_color(*theme.rgb("text_light"))
            pdf.set_xy(frame.x, frame.y2 + 1.5)
            pdf.cell(frame.w, 4, lbl, align="C")
        notes = Panel(panel.x, frames.y2 + 9, panel.w, panel.y2 - frames.y2 - 9)
        ruled_lines(pdf, theme, notes, spacing=7.5)


def _personal_records(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    lb, rb = ctx.geo.left_body(), ctx.geo.right_body()
    y = section_label(pdf, theme, lb.x, lb.y, "Personal Records",
                      underline_w=lb.w)
    table(pdf, theme, Panel(lb.x, y, lb.w, lb.y2 - y),
          [("Lift / Movement", 0.34), ("Current PR", 0.22), ("Date", 0.22),
           ("Goal", 0.22)], n_rows=14, zebra=True)
    rsecs = rb.split_v([0.5, 0.5], gap=7)
    y = section_label(pdf, theme, rsecs[0].x, rsecs[0].y, "Milestones Unlocked",
                      underline_w=rsecs[0].w)
    medals = Panel(rsecs[0].x, y + 3, rsecs[0].w, rsecs[0].y2 - y - 3)
    gr = theme.rule_c()
    for i, cell in enumerate(medals.rows(2, gap=6)):
        for j, medal in enumerate(cell.cols(3, gap=6)):
            cx, cy = medal.x + medal.w / 2, medal.y + medal.h * 0.38
            r = min(medal.w, medal.h) * 0.24
            pdf.set_draw_color(*blend(theme.rgb("secondary"),
                                      theme.structural(), 0.35))
            pdf.set_line_width(0.5)
            pdf.ellipse(cx - r, cy - r, r * 2, r * 2, style="D")
            pdf.polygon([(cx - r * 0.5, cy + r * 0.8), (cx - r * 0.9, cy + r * 1.9),
                         (cx, cy + r * 1.5), (cx + r * 0.9, cy + r * 1.9),
                         (cx + r * 0.5, cy + r * 0.8)], style="D")
            pdf.set_draw_color(*gr)
            pdf.set_line_width(0.25)
            pdf.line(medal.x + 2, medal.y2 - 2, medal.x2 - 2, medal.y2 - 2)
    y = section_label(pdf, theme, rsecs[1].x, rsecs[1].y, "Next Challenges",
                      underline_w=rsecs[1].w)
    checkbox_lines(pdf, theme, Panel(rsecs[1].x, y, rsecs[1].w,
                                     rsecs[1].y2 - y), spacing=9.5)


# ===================================================================
# ADHD PLANNER
# ===================================================================

def _brain_dump(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    lb, rb = ctx.geo.left_body(), ctx.geo.right_body()
    y = section_label(pdf, theme, lb.x, lb.y,
                      "Get It All Out of Your Head", underline_w=lb.w)
    _accent_note_font(pdf, theme, 13)
    pdf.set_text_color(*blend(theme.rgb("primary"), theme.rgb("text"), 0.15))
    pdf.set_xy(lb.x, y + 1)
    pdf.cell(lb.w, 8, "no filter, no order — just write", align="C")
    fill_texture(pdf, theme, Panel(lb.x, y + 12, lb.w, lb.y2 - y - 12),
                 kind="notes")

    y = section_label(pdf, theme, rb.x, rb.y, "Now Sort It", underline_w=rb.w)
    sorted_area = Panel(rb.x, y + 1, rb.w, rb.y2 - y - 1)
    quads = [q for row in sorted_area.rows(2, gap=6) for q in row.cols(2, gap=6)]
    for q, lbl in zip(quads, ("Do It Now", "Schedule It",
                              "Hand It Off", "Let It Go")):
        labelled_box(pdf, theme, q, lbl, lines_spacing=8.2)


def _priority_matrix(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    lb, rb = ctx.geo.left_body(), ctx.geo.right_body()
    for panel, quad_top, quad_bottom in (
        (lb, ("Urgent + Important", "Do First"),
         ("Urgent · Not Important", "Delegate or Simplify")),
        (rb, ("Important · Not Urgent", "Schedule It"),
         ("Not Urgent · Not Important", "Drop or Batch")),
    ):
        halves = panel.rows(2, gap=8)
        for half, (title, hint) in zip(halves, (quad_top, quad_bottom)):
            inner = labelled_box(pdf, theme, half, title, lines_spacing=None)
            _accent_note_font(pdf, theme, 11)
            pdf.set_text_color(*blend(theme.rgb("primary"), theme.rgb("text"), 0.15))
            pdf.set_xy(inner.x, inner.y)
            pdf.cell(inner.w, 6, hint, align="C")
            checkbox_lines(pdf, theme,
                           Panel(inner.x + 2, inner.y + 8, inner.w - 4,
                                 inner.h - 10), spacing=8.8)


def _time_blocking(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    lb, rb = ctx.geo.left_body(), ctx.geo.right_body()
    gr = theme.rule_c()

    y = section_label(pdf, theme, lb.x, lb.y,
                      "Time Blocks · Plan vs. Reality", underline_w=lb.w)
    grid = Panel(lb.x, y + 5, lb.w, lb.y2 - y - 5)
    time_w = 14.0
    col_w = (grid.w - time_w) / 2
    hours = list(range(7, 22))
    row_h = grid.h / len(hours)
    theme.set_type(pdf, "inline_label", size=6)
    pdf.set_text_color(*theme.band_text_c())
    for i, lbl in enumerate(("THE PLAN", "WHAT HAPPENED")):
        pdf.set_xy(grid.x + time_w + i * col_w, y)
        pdf.cell(col_w, 5, lbl, align="C")
    for i, hour in enumerate(hours):
        hy = grid.y + i * row_h
        h12 = hour if hour <= 12 else hour - 12
        ampm = "AM" if hour < 12 else "PM"
        theme.set_type(pdf, "mini_digit", size=5.6)
        pdf.set_text_color(*theme.rgb("text_light"))
        pdf.set_xy(grid.x, hy)
        pdf.cell(time_w - 1, row_h, f"{h12}{ampm.lower()}", align="R")
        pdf.set_draw_color(*gr)
        pdf.set_line_width(0.2)
        pdf.line(grid.x, hy, grid.x2, hy)
    for x in (grid.x + time_w, grid.x + time_w + col_w):
        pdf.line(x, grid.y, x, grid.y2)
    pdf.set_draw_color(*theme.border_c())
    pdf.set_line_width(0.3)
    pdf.rect(grid.x, grid.y, grid.w, grid.h, style="D")

    rsecs = rb.split_v([0.22, 0.2, 0.2, 0.38], gap=6)
    y = section_label(pdf, theme, rsecs[0].x, rsecs[0].y,
                      "Today's Non-Negotiables")
    _numbered_lines(pdf, ctx, Panel(rsecs[0].x, y, rsecs[0].w,
                                    rsecs[0].y2 - y), 3)
    inner = labelled_box(pdf, theme, rsecs[1], "Body Doubling / Focus Buddy",
                         lines_spacing=8)
    inner = labelled_box(pdf, theme, rsecs[2], "Breaks & Rewards",
                         lines_spacing=8)
    y = section_label(pdf, theme, rsecs[3].x, rsecs[3].y,
                      "Distractions That Showed Up")
    ruled_lines(pdf, theme, Panel(rsecs[3].x, y, rsecs[3].w, rsecs[3].y2 - y),
                spacing=8.5)


def _routine_builder(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    lb, rb = ctx.geo.left_body(), ctx.geo.right_body()
    for panel, title, hint in (
        (lb, "Morning Routine", "start the day gently"),
        (rb, "Evening Routine", "wind down, tomorrow-you says thanks"),
    ):
        y = section_label(pdf, theme, panel.x, panel.y, title,
                          underline_w=panel.w)
        _accent_note_font(pdf, theme, 12)
        pdf.set_text_color(*blend(theme.rgb("primary"), theme.rgb("text"), 0.15))
        pdf.set_xy(panel.x, y)
        pdf.cell(panel.w, 7, hint, align="C")
        body = Panel(panel.x, y + 10, panel.w, panel.y2 - y - 10)
        secs = body.split_v([0.62, 0.38], gap=6)
        grid = secs[0]
        time_w = 22.0
        n = 8
        row_h = grid.h / n
        gr = theme.rule_c()
        for i in range(n):
            ry = grid.y + i * row_h
            pdf.set_fill_color(*(theme.box_fill() or WHITE))
            pdf.set_draw_color(*blend(gr, theme.structural(), 0.25))
            pdf.set_line_width(0.28)
            pdf.rect(grid.x + 1, ry + row_h * 0.2, 3.4, 3.4, style="FD",
                     round_corners=True, corner_radius=0.7)
            pdf.set_draw_color(*gr)
            pdf.line(grid.x + 7, ry + row_h * 0.66, grid.x + grid.w - time_w - 4,
                     ry + row_h * 0.66)
            theme.set_type(pdf, "mini_digit", size=5.6)
            pdf.set_text_color(*theme.rgb("text_light"))
            pdf.set_xy(grid.x + grid.w - time_w, ry + row_h * 0.15)
            pdf.cell(8, 3.5, "takes", align="L")
            pdf.line(grid.x + grid.w - time_w + 9, ry + row_h * 0.66,
                     grid.x2 - 1, ry + row_h * 0.66)
        labelled_box(pdf, theme, secs[1], "If I Only Have 10 Minutes...",
                     lines_spacing=8.2)


def _parking_lot(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    for panel, title in ((ctx.geo.left_body(), "Ideas · Park Them Here"),
                         (ctx.geo.right_body(), "Someday / Maybe")):
        y = section_label(pdf, theme, panel.x, panel.y, title,
                          underline_w=panel.w)
        area = Panel(panel.x, y + 2, panel.w, panel.y2 - y - 2)
        cells = [c for row in area.rows(3, gap=6) for c in row.cols(2, gap=6)]
        gr = theme.rule_c()
        for cell in cells:
            pdf.set_draw_color(*blend(gr, theme.structural(), 0.3))
            pdf.set_line_width(0.3)
            pdf.rect(cell.x, cell.y, cell.w, cell.h, style="D",
                     round_corners=True, corner_radius=2.2)
            # lightbulb glyph
            bx, by = cell.x + 6, cell.y + 6
            pdf.set_draw_color(*blend(theme.rgb("secondary"),
                                      theme.structural(), 0.3))
            pdf.set_line_width(0.45)
            pdf.ellipse(bx - 2.6, by - 3.4, 5.2, 5.2, style="D")
            pdf.line(bx - 1.2, by + 2.2, bx + 1.2, by + 2.2)
            pdf.line(bx - 0.9, by + 3.4, bx + 0.9, by + 3.4)
            ruled_lines(pdf, theme,
                        Panel(cell.x + 3, cell.y + 11, cell.w - 6,
                              cell.h - 14), spacing=7.5)


def _energy_tracker(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    lb, rb = ctx.geo.left_body(), ctx.geo.right_body()
    gr = theme.rule_c()

    y = section_label(pdf, theme, lb.x, lb.y,
                      "Energy Map · Shade Your Levels", underline_w=lb.w)
    grid = Panel(lb.x + 16, y + 6, lb.w - 16, lb.y2 - y - 12)
    days = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
    hours = list(range(6, 23, 2))
    col_w = grid.w / len(days)
    row_h = grid.h / len(hours)
    theme.set_type(pdf, "inline_label", size=5.4)
    pdf.set_text_color(*theme.band_text_c())
    for i, d in enumerate(days):
        pdf.set_xy(grid.x + i * col_w, y + 1)
        pdf.cell(col_w, 4, d, align="C")
    for i, hour in enumerate(hours):
        hy = grid.y + i * row_h
        h12 = hour if hour <= 12 else hour - 12
        ampm = "a" if hour < 12 else "p"
        theme.set_type(pdf, "mini_digit", size=5.4)
        pdf.set_text_color(*theme.rgb("text_light"))
        pdf.set_xy(lb.x, hy + row_h / 2 - 1.8)
        pdf.cell(14, 3.5, f"{h12}{ampm}", align="L")
    pdf.set_draw_color(*gr)
    pdf.set_line_width(0.2)
    for i in range(len(hours) + 1):
        pdf.line(grid.x, grid.y + i * row_h, grid.x2, grid.y + i * row_h)
    for i in range(len(days) + 1):
        pdf.line(grid.x + i * col_w, grid.y, grid.x + i * col_w, grid.y2)
    pdf.set_draw_color(*theme.border_c())
    pdf.set_line_width(0.3)
    pdf.rect(grid.x, grid.y, grid.w, grid.h, style="D")

    rsecs = rb.split_v([0.16, 0.28, 0.28, 0.28], gap=6)
    # Legend
    y = section_label(pdf, theme, rsecs[0].x, rsecs[0].y, "Legend")
    legend = ("High — deep work", "Medium — admin & errands",
              "Low — rest, no guilt")
    fills = (0.55, 0.3, 0.12)
    for i, (lbl, op) in enumerate(zip(legend, fills)):
        lx = rsecs[0].x + 2
        ly = y + 2 + i * 6
        with pdf.local_context(fill_opacity=op):
            pdf.set_fill_color(*theme.rgb("primary"))
            pdf.rect(lx, ly, 5, 4, style="F", round_corners=True,
                     corner_radius=0.8)
        theme.set_type(pdf, "mini_digit", size=6.5)
        pdf.set_text_color(*theme.rgb("text_light"))
        pdf.set_xy(lx + 7, ly)
        pdf.cell(60, 4, lbl, align="L")
    for panel, lbl in zip(
        rsecs[1:],
        ("When Am I Sharpest?", "What Drains Me?", "What Recharges Me?"),
    ):
        y = section_label(pdf, theme, panel.x, panel.y, lbl,
                          underline_w=panel.w)
        ruled_lines(pdf, theme, Panel(panel.x, y, panel.w, panel.y2 - y),
                    spacing=8.5)


# ===================================================================
# TEACHER PLANNER
# ===================================================================

def _lesson_plan(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    lb, rb = ctx.geo.left_body(), ctx.geo.right_body()
    gr = theme.rule_c()

    top = Panel(lb.x, lb.y, lb.w, 12)
    theme.set_type(pdf, "inline_label", size=7)
    pdf.set_text_color(*theme.rgb("text_light"))
    thirds = top.cols(3, gap=6)
    for cell, lbl in zip(thirds, ("SUBJECT", "GRADE / CLASS", "DATE")):
        pdf.set_xy(cell.x, cell.y + 2)
        pdf.cell(pdf.get_string_width(lbl) + 1, 5, lbl, align="L")
        pdf.set_draw_color(*gr)
        pdf.line(cell.x + pdf.get_string_width(lbl) + 2, cell.y + 6.4,
                 cell.x2, cell.y + 6.4)

    body = Panel(lb.x, lb.y + 16, lb.w, lb.h - 16)
    secs = body.split_v([0.24, 0.24, 0.52], gap=6)
    labelled_box(pdf, theme, secs[0], "Learning Objective", lines_spacing=8)
    labelled_box(pdf, theme, secs[1], "Materials Needed", lines_spacing=8)
    labelled_box(pdf, theme, secs[2], "Lesson Activities & Timing",
                 lines_spacing=8.6)

    rsecs = rb.split_v([0.3, 0.3, 0.22, 0.18], gap=6)
    labelled_box(pdf, theme, rsecs[0], "Assessment / Check for Understanding",
                 lines_spacing=8.2)
    labelled_box(pdf, theme, rsecs[1], "Differentiation & Accommodations",
                 lines_spacing=8.2)
    labelled_box(pdf, theme, rsecs[2], "Homework", lines_spacing=8.2)
    labelled_box(pdf, theme, rsecs[3], "Reflection · What Worked?",
                 lines_spacing=8.2)


def _grade_book(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    gr = theme.rule_c()
    for panel in (ctx.geo.left_body(), ctx.geo.right_body()):
        name_w = 42.0
        header_h = 14.0
        n_cols, n_rows = 12, 15
        col_w = (panel.w - name_w) / n_cols
        row_h = (panel.h - header_h) / n_rows

        band = theme.band_fill()
        if band is not None:
            pdf.set_fill_color(*band)
            pdf.rect(panel.x, panel.y, panel.w, header_h, style="F")
        theme.set_type(pdf, "inline_label", size=6)
        pdf.set_text_color(*theme.band_text_c())
        pdf.set_xy(panel.x, panel.y)
        pdf.cell(name_w, header_h, "STUDENT", align="C")
        # slanted assignment labels area: blank write-in slots
        pdf.set_draw_color(*gr)
        pdf.set_line_width(0.2)
        for i in range(n_cols):
            x = panel.x + name_w + i * col_w
            pdf.line(x + 1.5, panel.y + header_h - 2, x + col_w - 1.5,
                     panel.y + 2.5)
        for r in range(n_rows + 1):
            ry = panel.y + header_h + r * row_h
            pdf.line(panel.x, ry, panel.x2, ry)
        for c in range(n_cols + 1):
            x = panel.x + name_w + c * col_w
            pdf.line(x, panel.y, x, panel.y2)
        pdf.line(panel.x, panel.y, panel.x, panel.y2)
        pdf.set_draw_color(*theme.border_c())
        pdf.set_line_width(0.3)
        pdf.rect(panel.x, panel.y, panel.w, panel.h, style="D")


def _student_roster(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    half = 18
    for panel, start in ((ctx.geo.left_body(), 1), (ctx.geo.right_body(), 19)):
        table(pdf, theme, panel,
              [("#", 0.06), ("Student Name", 0.34), ("Guardian", 0.26),
               ("Contact", 0.20), ("Notes", 0.14)],
              n_rows=half, zebra=True,
              row_labels=[str(i) for i in range(start, start + half)])


def _parent_contacts(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    cols = [("Date", 0.11), ("Student", 0.2), ("Contact / Method", 0.22),
            ("Reason & Outcome", 0.36), ("Follow Up", 0.11)]
    for panel in (ctx.geo.left_body(), ctx.geo.right_body()):
        table(pdf, theme, panel, cols, n_rows=16, zebra=True)


def _meeting_notes(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    lb, rb = ctx.geo.left_body(), ctx.geo.right_body()
    gr = theme.rule_c()

    top = Panel(lb.x, lb.y, lb.w, 12)
    theme.set_type(pdf, "inline_label", size=7)
    pdf.set_text_color(*theme.rgb("text_light"))
    for cell, lbl in zip(top.cols(2, gap=6), ("MEETING / TOPIC", "DATE & TIME")):
        pdf.set_xy(cell.x, cell.y + 2)
        pdf.cell(pdf.get_string_width(lbl) + 1, 5, lbl, align="L")
        pdf.set_draw_color(*gr)
        pdf.line(cell.x + pdf.get_string_width(lbl) + 2, cell.y + 6.4,
                 cell.x2, cell.y + 6.4)
    body = Panel(lb.x, lb.y + 16, lb.w, lb.h - 16)
    secs = body.split_v([0.3, 0.7], gap=6)
    labelled_box(pdf, theme, secs[0], "Attendees", lines_spacing=8)
    labelled_box(pdf, theme, secs[1], "Discussion Notes", lines_spacing=8.4)

    rsecs = rb.split_v([0.55, 0.45], gap=6)
    y = section_label(pdf, theme, rsecs[0].x, rsecs[0].y, "Action Items",
                      underline_w=rsecs[0].w)
    checkbox_lines(pdf, theme, Panel(rsecs[0].x, y, rsecs[0].w,
                                     rsecs[0].y2 - y), spacing=9.2)
    y = section_label(pdf, theme, rsecs[1].x, rsecs[1].y,
                      "Questions to Bring Up Next Time", underline_w=rsecs[1].w)
    ruled_lines(pdf, theme, Panel(rsecs[1].x, y, rsecs[1].w, rsecs[1].y2 - y),
                spacing=9)


def _curriculum_overview(pdf: FPDF, ctx: PageContext) -> None:
    theme = ctx.theme
    gr = theme.rule_c()
    months = (("AUG", "SEP", "OCT", "NOV", "DEC"),
              ("JAN", "FEB", "MAR", "APR", "MAY"))
    for panel, term, mset in ((ctx.geo.left_body(), "Fall Term", months[0]),
                              (ctx.geo.right_body(), "Spring Term", months[1])):
        y = section_label(pdf, theme, panel.x, panel.y,
                          f"{term} · Units & Themes", underline_w=panel.w)
        grid = Panel(panel.x, y + 2, panel.w, panel.y2 - y - 2)
        label_w = 16.0
        header_h = 7.0
        n_sub = 3   # subject columns (write-in)
        col_w = (grid.w - label_w) / n_sub
        row_h = (grid.h - header_h) / len(mset)
        band = theme.band_fill()
        if band is not None:
            pdf.set_fill_color(*band)
            pdf.rect(grid.x, grid.y, grid.w, header_h, style="F")
        theme.set_type(pdf, "inline_label", size=6)
        pdf.set_text_color(*theme.band_text_c())
        pdf.set_xy(grid.x, grid.y)
        pdf.cell(label_w, header_h, "", align="C")
        for i in range(n_sub):
            x = grid.x + label_w + i * col_w
            pdf.set_xy(x + 4, grid.y + header_h - 3)
            pdf.set_draw_color(*gr)
            pdf.line(x + 4, grid.y + header_h - 2, x + col_w - 4,
                     grid.y + header_h - 2)
        for i, m in enumerate(mset):
            ry = grid.y + header_h + i * row_h
            theme.set_type(pdf, "inline_label", size=6.2)
            pdf.set_text_color(*theme.rgb("text_light"))
            pdf.set_xy(grid.x, ry)
            pdf.cell(label_w - 2, row_h, m, align="C")
            pdf.set_draw_color(*gr)
            pdf.set_line_width(0.2)
            pdf.line(grid.x, ry, grid.x2, ry)
        for i in range(n_sub + 1):
            x = grid.x + label_w + i * col_w
            pdf.line(x, grid.y, x, grid.y2)
        pdf.set_draw_color(*theme.border_c())
        pdf.set_line_width(0.3)
        pdf.rect(grid.x, grid.y, grid.w, grid.h, style="D")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

RENDERERS: dict[str, Callable[[FPDF, PageContext], None]] = {
    # budget
    "budget_overview": _budget_overview,
    "expense_log": _expense_log,
    "savings_goals": _savings_goals,
    "bill_tracker": _bill_tracker,
    "debt_tracker": _debt_tracker,
    "subscription_tracker": _subscription_tracker,
    # student
    "class_schedule": _class_schedule,
    "assignment_tracker": _assignment_tracker,
    "exam_tracker": _exam_tracker,
    "grade_log": _grade_log,
    "semester_goals": _semester_goals,
    "reading_list": _reading_list,
    # fitness
    "workout_log": _workout_log,
    "measurements": _measurements,
    "meal_planner": _meal_planner,
    "hydration_steps": _hydration_steps,
    "progress_photos": _progress_photos,
    "personal_records": _personal_records,
    # adhd
    "brain_dump": _brain_dump,
    "priority_matrix": _priority_matrix,
    "time_blocking": _time_blocking,
    "routine_builder": _routine_builder,
    "parking_lot": _parking_lot,
    "energy_tracker": _energy_tracker,
    # teacher
    "lesson_plan": _lesson_plan,
    "grade_book": _grade_book,
    "student_roster": _student_roster,
    "parent_contacts": _parent_contacts,
    "meeting_notes": _meeting_notes,
    "curriculum_overview": _curriculum_overview,
}
