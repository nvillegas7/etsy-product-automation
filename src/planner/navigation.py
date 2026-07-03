"""Hyperlink / bookmark builder and chrome renderers for planner PDFs.

Uses fpdf2's two-phase link system:
  1. ``add_link()``  -- pre-allocates an integer link ID (before any pages exist)
  2. ``set_link(id, page=N)`` -- binds that ID to a concrete page number
     (called when the target page is rendered)

The chrome draws the "open ring binder" illusion:
  desk background -> top category tabs -> migrating month tabs ->
  paper sheets w/ shadow -> active month tab (merged with paper) ->
  spiral coil -> footer -> home button
"""

from __future__ import annotations

import calendar as _cal
import logging
from dataclasses import dataclass, field

from fpdf import FPDF

from src.planner.layout import (
    PAGE_WIDTH,
    PAGE_HEIGHT,
    PAPER_X,
    PAPER_X2,
    PAPER_Y,
    PAPER_Y2,
    TOP_TAB_HEIGHT,
    TOP_TAB_Y,
    TOP_TAB_X_START,
    TOP_TAB_X_END,
    TOP_TAB_CORNER_RADIUS,
    TOP_TAB_GAP,
    HOME_CX,
    HOME_CY,
    HOME_R,
    MONTH_TAB_WIDTH,
    MONTH_TAB_ACTIVE_EXTRA,
    MONTH_TAB_TOP,
    MONTH_TAB_SLOT_H,
    MONTH_TAB_GAP,
    MONTH_TAB_CORNER_RADIUS,
    MONTH_TAB_LABELS,
    SPIRAL_X,
    SPIRAL_WIDTH,
    SPIRAL_LOOPS,
    FOOTER_Y,
    LEFT_CONTENT_X,
    RIGHT_CONTENT_RIGHT,
)
from src.planner.styles import Theme, searchable_tracking
from src.planner.widgets import blend, desk_color, paper_color, WHITE, fit_text

logger = logging.getLogger(__name__)

MONTH_ABBREVS = [_cal.month_abbr[m].upper() for m in range(1, 13)]


# ---------------------------------------------------------------------------
# NavigationManager
# ---------------------------------------------------------------------------

@dataclass
class NavigationManager:
    """Pre-allocate, bind, and retrieve fpdf2 link IDs by name."""

    _links: dict[str, int] = field(default_factory=dict)
    _bound: dict[str, int] = field(default_factory=dict)  # name -> page

    # -- Phase 1: register / pre-allocate -----------------------------------

    def register_link(self, pdf: FPDF, name: str) -> int:
        """Pre-allocate a link ID and store it under *name*.

        Must be called **before** the target page exists.
        Binds to page 1 as placeholder so the link can be used immediately
        in tab strips (fpdf2 2.8+ requires a page number before use).
        The real page is set later via ``bind_link()``.
        """
        if name in self._links:
            return self._links[name]
        link_id = pdf.add_link()
        pdf.set_link(link_id, page=1)
        self._links[name] = link_id
        return link_id

    # -- Phase 2: bind to page ---------------------------------------------

    def bind_link(self, pdf: FPDF, name: str, page_num: int | None = None) -> None:
        """Bind the pre-allocated link *name* to *page_num* (or current page)."""
        if name not in self._links:
            logger.warning("bind_link: '%s' was never registered -- skipping", name)
            return
        page = page_num if page_num is not None else pdf.page
        pdf.set_link(self._links[name], page=page)
        self._bound[name] = page

    # -- Retrieval ---------------------------------------------------------

    def get_link(self, name: str) -> int | None:
        """Return the link ID for *name*, or ``None`` if not registered."""
        return self._links.get(name)

    def has_link(self, name: str) -> bool:
        return name in self._links

    def bound_page(self, name: str) -> int | None:
        return self._bound.get(name)

    # -- Convenience names -------------------------------------------------

    @staticmethod
    def cover_key() -> str:
        return "cover"

    @staticmethod
    def index_key() -> str:
        return "index"

    @staticmethod
    def year_glance_key() -> str:
        return "year_glance"

    @staticmethod
    def month_key(month: int) -> str:
        """month is 1-based (1=Jan)."""
        return f"month_{month:02d}"

    @staticmethod
    def monthly_plan_key(month: int) -> str:
        return f"monthly_plan_{month:02d}"

    @staticmethod
    def monthly_review_key(month: int) -> str:
        return f"monthly_review_{month:02d}"

    @staticmethod
    def week_key(week_index: int) -> str:
        """week_index is 0-based across the year."""
        return f"week_{week_index:03d}"

    @staticmethod
    def daily_key(month: int, day: int) -> str:
        return f"daily_{month:02d}_{day:02d}"

    @staticmethod
    def notes_key() -> str:
        return "notes"

    @staticmethod
    def habits_key() -> str:
        return "habits"

    @staticmethod
    def goals_key() -> str:
        return "goals"

    @staticmethod
    def niche_page_key(page_id: str) -> str:
        return f"niche_{page_id}"


# ---------------------------------------------------------------------------
# Desk + paper (the open binder illusion)
# ---------------------------------------------------------------------------

def render_desk(pdf: FPDF, theme: Theme) -> None:
    """Fill the whole page with the darker desk tone."""
    pdf.set_fill_color(*theme.desk_c())
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, style="F")


def render_paper(pdf: FPDF, theme: Theme) -> None:
    """Two paper sheets with drop shadow and page-edge shading at the coil."""
    paper = theme.paper_c()
    left_edge = SPIRAL_X + 4.6           # left sheet tucks under the coil
    right_edge = SPIRAL_X + SPIRAL_WIDTH - 4.6

    # Drop shadow (two translucent offsets)
    with pdf.local_context(fill_opacity=0.10):
        pdf.set_fill_color(30, 24, 18)
        pdf.rect(PAPER_X + 1.2, PAPER_Y + 1.8, PAPER_X2 - PAPER_X, PAPER_Y2 - PAPER_Y,
                 style="F", round_corners=True, corner_radius=2.0)
    with pdf.local_context(fill_opacity=0.08):
        pdf.set_fill_color(30, 24, 18)
        pdf.rect(PAPER_X + 2.4, PAPER_Y + 3.4, PAPER_X2 - PAPER_X, PAPER_Y2 - PAPER_Y,
                 style="F", round_corners=True, corner_radius=2.0)

    # Sheets
    pdf.set_fill_color(*paper)
    pdf.rect(PAPER_X, PAPER_Y, left_edge - PAPER_X, PAPER_Y2 - PAPER_Y,
             style="F", round_corners=("TOP_LEFT", "BOTTOM_LEFT"), corner_radius=2.0)
    pdf.rect(right_edge, PAPER_Y, PAPER_X2 - right_edge, PAPER_Y2 - PAPER_Y,
             style="F", round_corners=("TOP_RIGHT", "BOTTOM_RIGHT"), corner_radius=2.0)

    # Page-edge shading: page curvature next to the coil (stacked translucency)
    shade = blend(theme.rgb("text"), theme.desk_c(), 0.5)
    pdf.set_fill_color(*shade)
    for i, (w, op) in enumerate([(5.0, 0.045), (3.2, 0.05), (1.6, 0.06)]):
        with pdf.local_context(fill_opacity=op):
            pdf.rect(left_edge - w, PAPER_Y, w, PAPER_Y2 - PAPER_Y, style="F")
            pdf.rect(right_edge, PAPER_Y, w, PAPER_Y2 - PAPER_Y, style="F")
    # Crisp page-edge lines near the coil (stacked sheets look)
    pdf.set_line_width(0.25)
    for i, off in enumerate((0.0, 0.9, 1.8)):
        with pdf.local_context(stroke_opacity=0.35 - i * 0.09):
            pdf.set_draw_color(*shade)
            pdf.line(left_edge - off, PAPER_Y + 0.5, left_edge - off, PAPER_Y2 - 0.5)
            pdf.line(right_edge + off, PAPER_Y + 0.5, right_edge + off, PAPER_Y2 - 0.5)


# ---------------------------------------------------------------------------
# Spiral coil
# ---------------------------------------------------------------------------

def render_spiral_binding(pdf: FPDF, theme: Theme) -> None:
    """Realistic wire coil: punch holes + wire loops down the page centre."""
    top = PAPER_Y - 2.0
    bottom = PAPER_Y2 + 2.0
    spacing = (bottom - top) / SPIRAL_LOOPS

    hole_col = blend(theme.rgb("text"), (0, 0, 0), 0.35)
    wire_dark = blend(theme.rgb("secondary"), theme.rgb("text"), 0.3)
    wire_mid = blend(theme.rgb("secondary"), theme.rgb("accent"), 0.4)
    wire_light = blend(theme.rgb("secondary"), WHITE, 0.7)

    hole_w, hole_h = 2.1, 3.6
    # Punch holes sit ON the paper, just inside each sheet edge
    x_hole_l = SPIRAL_X + 0.9
    x_hole_r = SPIRAL_X + SPIRAL_WIDTH - 0.9 - hole_w

    for i in range(SPIRAL_LOOPS):
        cy = top + spacing * (i + 0.5)

        # Punch holes (small dark rounded rects on each sheet edge)
        pdf.set_fill_color(*hole_col)
        with pdf.local_context(fill_opacity=0.65):
            pdf.rect(x_hole_l, cy - hole_h / 2, hole_w, hole_h,
                     style="F", round_corners=True, corner_radius=0.9)
            pdf.rect(x_hole_r, cy - hole_h / 2, hole_w, hole_h,
                     style="F", round_corners=True, corner_radius=0.9)

        # Wire loop: extends past the holes onto both sheets
        ring_x = SPIRAL_X - 1.8
        ring_w = SPIRAL_WIDTH + 3.6
        ring_h = 4.2
        # soft shadow under the wire
        with pdf.local_context(stroke_opacity=0.18):
            pdf.set_line_width(1.5)
            pdf.set_draw_color(*hole_col)
            pdf.ellipse(ring_x, cy - ring_h / 2 + 0.7, ring_w, ring_h, style="D")
        pdf.set_line_width(1.0)
        pdf.set_draw_color(*wire_dark)
        pdf.ellipse(ring_x, cy - ring_h / 2 + 0.25, ring_w, ring_h, style="D")
        pdf.set_line_width(0.85)
        pdf.set_draw_color(*wire_mid)
        pdf.ellipse(ring_x + 0.15, cy - ring_h / 2, ring_w - 0.3, ring_h - 0.4,
                    style="D")
        pdf.set_line_width(0.4)
        pdf.set_draw_color(*wire_light)
        pdf.ellipse(ring_x + 0.35, cy - ring_h / 2 - 0.15, ring_w - 0.7,
                    ring_h - 0.7, style="D")

    pdf.set_line_width(0.2)
    pdf.set_draw_color(0, 0, 0)


# ---------------------------------------------------------------------------
# Top category tabs
# ---------------------------------------------------------------------------

def render_top_tabs(
    pdf: FPDF,
    nav: NavigationManager,
    theme: Theme,
    tabs: list[tuple[str, str]],
    active_tab: str | None = None,
) -> None:
    """Rounded-top category tabs tucked behind the paper top edge.

    *tabs* is ``[(label, link_key), ...]`` -- labels reflect the niche.
    Must be drawn BEFORE ``render_paper`` (inactive) -- the active tab is
    re-drawn merged with the paper via ``render_active_top_tab``.
    """
    if not tabs:
        return
    total_w = TOP_TAB_X_END - TOP_TAB_X_START
    tab_w = (total_w - TOP_TAB_GAP * (len(tabs) - 1)) / len(tabs)
    tab_h = TOP_TAB_HEIGHT + 4.0   # extends under the paper edge

    for i, (label, key) in enumerate(tabs):
        x = TOP_TAB_X_START + i * (tab_w + TOP_TAB_GAP)
        is_active = label == active_tab

        if is_active:
            fill = theme.active_tab_c()
            txt = WHITE
        else:
            fill = blend(theme.rgb("tab_inactive"),
                         theme.rgb("secondary"), 0.25 + 0.05 * (i % 3))
            txt = blend(theme.rgb("text"), theme.rgb("primary"), 0.25)

        pdf.set_fill_color(*fill)
        pdf.rect(x, TOP_TAB_Y, tab_w, tab_h, style="F",
                 round_corners=("TOP_LEFT", "TOP_RIGHT"),
                 corner_radius=TOP_TAB_CORNER_RADIUS)

        pdf.set_text_color(*txt)
        size = fit_text(pdf, label, theme.body, "B", 6.6, tab_w - 2.5, min_size=4.6)
        pdf.set_font(theme.body, "B", size)
        pdf.set_xy(x, TOP_TAB_Y)
        pdf.cell(tab_w, TOP_TAB_HEIGHT - 1.0, label, align="C")

        link_id = nav.get_link(key)
        if link_id is not None:
            pdf.link(x, TOP_TAB_Y, tab_w, TOP_TAB_HEIGHT, link_id)

    pdf.set_text_color(0, 0, 0)


# ---------------------------------------------------------------------------
# Month tab strips (migrating)
# ---------------------------------------------------------------------------

def _month_tab_fill(theme: Theme, m: int) -> tuple[int, int, int]:
    """Month tabs get progressively deeper tones down the strip."""
    return blend(theme.rgb("tab_inactive"), theme.rgb("secondary"),
                 0.15 + 0.55 * (m / 12.0))


def _draw_side_tab(
    pdf: FPDF,
    theme: Theme,
    side: str,                 # "L" or "R"
    slot: int,                 # 0 = YEAR slot, 1..12 = months
    label: str,
    fill: tuple[int, int, int],
    text_color: tuple[int, int, int],
    link_id: int | None,
    active: bool = False,
) -> None:
    y = MONTH_TAB_TOP + slot * MONTH_TAB_SLOT_H + MONTH_TAB_GAP / 2
    h = MONTH_TAB_SLOT_H - MONTH_TAB_GAP
    w = MONTH_TAB_WIDTH + (MONTH_TAB_ACTIVE_EXTRA if active else 0.0)
    tuck = 2.0   # how far the tab slides under the paper edge

    if side == "R":
        x = PAPER_X2 - tuck
        corners = ("TOP_RIGHT", "BOTTOM_RIGHT")
    else:
        x = PAPER_X + tuck - w
        corners = ("TOP_LEFT", "BOTTOM_LEFT")

    # subtle shadow under the tab
    with pdf.local_context(fill_opacity=0.12):
        pdf.set_fill_color(30, 24, 18)
        pdf.rect(x + (0.5 if side == "R" else -0.5), y + 0.8, w, h,
                 style="F", round_corners=corners,
                 corner_radius=MONTH_TAB_CORNER_RADIUS)

    pdf.set_fill_color(*fill)
    pdf.rect(x, y, w, h, style="F", round_corners=corners,
             corner_radius=MONTH_TAB_CORNER_RADIUS)

    # Rotated label (reads top-to-bottom like the reference)
    pdf.set_text_color(*text_color)
    pdf.set_font(theme.body, "B", 6.4 if not active else 7.0)
    cx = x + w / 2 + (1.2 if side == "R" else -0.2)
    cy = y + h / 2
    text_w = pdf.get_string_width(label)
    with pdf.rotation(angle=-90 if side == "R" else 90, x=cx, y=cy):
        pdf.set_xy(cx - text_w / 2, cy - 2.2)
        pdf.cell(text_w + 0.5, 4.4, label, align="C")

    if link_id is not None:
        pdf.link(x, y, w, h, link_id)
    pdf.set_text_color(0, 0, 0)


def render_month_tabs(
    pdf: FPDF,
    nav: NavigationManager,
    theme: Theme,
    current_month: int | None = None,
    skip_active: bool = False,
) -> None:
    """Migrating month tabs + YEAR tab.

    Months before *current_month* render on the LEFT paper edge (looking
    'used'); *current_month*..12 stay on the RIGHT edge at their absolute
    slot positions.  When *skip_active* is True the active month tab is not
    drawn (it is drawn after the paper by ``render_active_month_tab``).
    """
    inactive_text = blend(theme.rgb("text"), theme.rgb("primary"), 0.3)

    # YEAR tab (slot 0, always top-right)
    _draw_side_tab(
        pdf, theme, "R", 0, "YEAR",
        fill=blend(theme.rgb("tab_inactive"), theme.rgb("primary"), 0.28),
        text_color=inactive_text,
        link_id=nav.get_link(NavigationManager.year_glance_key()),
    )

    for m in range(1, 13):
        link_id = nav.get_link(NavigationManager.month_key(m))
        is_active = current_month == m
        if is_active and skip_active:
            continue
        if current_month is not None and m < current_month:
            side = "L"
        else:
            side = "R"
        _draw_side_tab(
            pdf, theme, side, m, MONTH_ABBREVS[m - 1],
            fill=theme.active_tab_c() if is_active else _month_tab_fill(theme, m),
            text_color=WHITE if is_active else inactive_text,
            link_id=link_id,
            active=is_active,
        )


def render_active_month_tab(
    pdf: FPDF,
    nav: NavigationManager,
    theme: Theme,
    current_month: int,
) -> None:
    """Active month tab drawn AFTER the paper so it merges with the page."""
    _draw_side_tab(
        pdf, theme, "R", current_month, MONTH_ABBREVS[current_month - 1],
        fill=theme.active_tab_c(),
        text_color=WHITE,
        link_id=nav.get_link(NavigationManager.month_key(current_month)),
        active=True,
    )


# ---------------------------------------------------------------------------
# Footer + home button + back button
# ---------------------------------------------------------------------------

def render_footer(pdf: FPDF, theme: Theme, brand: str = "Made with love",
                  x: float = LEFT_CONTENT_X, y: float = FOOTER_Y) -> None:
    """Small quiet footer text inside the paper bottom edge."""
    pdf.set_text_color(*blend(theme.rgb("text_light"), theme.paper_c(), 0.35))
    pdf.set_font(theme.body, "", 5.8)
    pdf.set_xy(x, y)
    pdf.cell(120, 4, f"© {brand} · Digital Planner", align="L")
    pdf.set_text_color(0, 0, 0)


def render_home_button(pdf: FPDF, nav: NavigationManager, theme: Theme) -> None:
    """Circular HOME button on the desk, top-right, with a house glyph."""
    link_id = nav.get_link(NavigationManager.index_key())

    pdf.set_fill_color(*theme.rgb("primary"))
    with pdf.local_context(fill_opacity=0.15):
        pdf.set_fill_color(30, 24, 18)
        pdf.ellipse(HOME_CX - HOME_R + 0.4, HOME_CY - HOME_R + 0.7,
                    HOME_R * 2, HOME_R * 2, style="F")
    pdf.set_fill_color(*theme.rgb("primary"))
    pdf.ellipse(HOME_CX - HOME_R, HOME_CY - HOME_R, HOME_R * 2, HOME_R * 2, style="F")
    pdf.set_draw_color(*WHITE)
    pdf.set_line_width(0.5)
    pdf.ellipse(HOME_CX - HOME_R + 0.9, HOME_CY - HOME_R + 0.9,
                (HOME_R - 0.9) * 2, (HOME_R - 0.9) * 2, style="D")

    # House glyph
    pdf.set_fill_color(*WHITE)
    roof = [
        (HOME_CX - 2.6, HOME_CY + 0.2),
        (HOME_CX, HOME_CY - 2.4),
        (HOME_CX + 2.6, HOME_CY + 0.2),
    ]
    pdf.polygon(roof, style="F")
    pdf.rect(HOME_CX - 1.8, HOME_CY + 0.2, 3.6, 2.6, style="F")
    pdf.set_fill_color(*theme.rgb("primary"))
    pdf.rect(HOME_CX - 0.5, HOME_CY + 1.2, 1.0, 1.6, style="F")

    if link_id is not None:
        pdf.link(HOME_CX - HOME_R, HOME_CY - HOME_R, HOME_R * 2, HOME_R * 2, link_id)


def render_back_button(
    pdf: FPDF,
    nav: NavigationManager,
    theme: Theme,
    target_key: str,
    label: str,
) -> None:
    """'BACK TO ...' outline button at the top-right of the right page."""
    from src.planner.widgets import outline_button  # local import, avoids cycle

    link_id = nav.get_link(target_key)
    pdf.set_font(theme.body, "B", 7)
    w = max(40.0, pdf.get_string_width(label.upper()) + 14)
    outline_button(pdf, theme, RIGHT_CONTENT_RIGHT - w, PAPER_Y + 4.5, w, 8.5,
                   label, link=link_id)


# ---------------------------------------------------------------------------
# Pennant month badge
# ---------------------------------------------------------------------------

def render_pennant(
    pdf: FPDF,
    theme: Theme,
    month: int,
    year: int,
    x: float | None = None,
    y: float | None = None,
) -> None:
    """Pennant flag with the month name + year, hanging off the top.

    The text styling is voice-aware; the classic/serif voices keep the
    script month + Inter Bold year exactly as before.
    """
    from src.planner.layout import PENNANT_X, PENNANT_Y, PENNANT_W, PENNANT_H, PENNANT_NOTCH

    px = PENNANT_X if x is None else x
    py = PENNANT_Y if y is None else y
    w, h, notch = PENNANT_W, PENNANT_H, PENNANT_NOTCH

    # Shadow
    with pdf.local_context(fill_opacity=0.12):
        pdf.set_fill_color(30, 24, 18)
        pdf.polygon(
            [(px + 0.7, py + 1.0), (px + w + 0.7, py + 1.0),
             (px + w + 0.7, py + h + 1.0), (px + w / 2 + 0.7, py + h - notch + 1.0),
             (px + 0.7, py + h + 1.0)],
            style="F",
        )
    # Ink: the pennant keeps primary under ink-on-paper; accent-pop remaps
    # structural color to text.
    fill = (theme.rgb("primary") if theme.ink.name == "ink-on-paper"
            else theme.structural())
    pdf.set_fill_color(*fill)
    pdf.polygon(
        [(px, py), (px + w, py), (px + w, py + h),
         (px + w / 2, py + h - notch), (px, py + h)],
        style="F",
    )

    month_name = _cal.month_name[month]
    voice = theme.design.voice
    pdf.set_text_color(*WHITE)
    if voice == "grotesk":
        size = fit_text(pdf, month_name.upper(), theme.body, "B", 9,
                        w - 4, min_size=6.5)
        pdf.set_font(theme.body, "B", size)
        try:
            # Month names are searchable: clamp to the extraction budget.
            pdf.set_char_spacing(searchable_tracking(size, 1.0))
        except Exception:
            pass
        pdf.set_xy(px, py + 4)
        pdf.cell(w, 8, month_name.upper(), align="C")
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass
        pdf.set_font(theme.body, "", 8)
        pdf.set_xy(px, py + 11)
        pdf.cell(w, 8, str(year), align="C")
    elif voice == "typewriter":
        size = fit_text(pdf, month_name.upper(), "Courier", "B", 9,
                        w - 4, min_size=6.5)
        pdf.set_font("Courier", "B", size)
        pdf.set_xy(px, py + 4)
        pdf.cell(w, 8, month_name.upper(), align="C")
        pdf.set_font("Courier", "", 8)
        pdf.set_xy(px, py + 11)
        pdf.cell(w, 8, str(year), align="C")
    elif voice == "script":
        size = fit_text(pdf, month_name, theme.script, "", 18, w - 4,
                        min_size=9)
        pdf.set_font(theme.script, "", size)
        pdf.set_xy(px, py + 2.5)
        pdf.cell(w, 8, month_name, align="C")
        pdf.set_font(theme.body, "I", 10)
        pdf.set_xy(px, py + 10.5)
        pdf.cell(w, 8, str(year), align="C")
    else:   # classic / serif -- exact pre-design rendering
        size = fit_text(pdf, month_name, theme.script, "",
                        theme.fonts.size_pennant, w - 4, min_size=9)
        pdf.set_font(theme.script, "", size)
        pdf.set_xy(px, py + 2.5)
        pdf.cell(w, 8, month_name, align="C")
        pdf.set_font(theme.body, "B", 11)
        pdf.set_xy(px, py + 10.5)
        pdf.cell(w, 8, str(year), align="C")
    pdf.set_text_color(0, 0, 0)


# ---------------------------------------------------------------------------
# Shell renderers (design-parameter system, D1)
# ---------------------------------------------------------------------------
#
# A shell fully specifies chrome: background, surface, header zone, month
# nav, category nav, footer, home affordance, back-button placement, and
# z-order.  ``NavigationManager`` and all link keys are shared and
# untouched -- shells only change where the link rectangles sit.


class BinderShell:
    """S1: the current open-ring-binder look, verbatim."""

    header_style = "pennant"

    def render_chrome(self, pdf: FPDF, ctx, active_tab: str | None,
                      current_month: int | None) -> None:
        theme = ctx.theme
        render_desk(pdf, theme)
        render_top_tabs(pdf, ctx.nav, theme, ctx.tabs, active_tab=active_tab)
        render_month_tabs(pdf, ctx.nav, theme, current_month=current_month,
                          skip_active=current_month is not None)
        render_paper(pdf, theme)
        if current_month is not None:
            render_active_month_tab(pdf, ctx.nav, theme, current_month)
        render_spiral_binding(pdf, theme)
        render_footer(pdf, theme, ctx.brand)
        render_home_button(pdf, ctx.nav, theme)

    def back_button(self, pdf: FPDF, ctx, target_key: str, label: str) -> None:
        render_back_button(pdf, ctx.nav, ctx.theme, target_key, label)


class CardsShell:
    """S2: two floating cards on the desk; coin month tabs; left rail."""

    header_style = "pennant"

    CARD_Y, CARD_H, CARD_W = 16.0, 329.0, 219.0
    L_CARD_X, R_CARD_X = 16.0, 247.0
    COIN_X = 466.0
    COIN_TOP, COIN_BOTTOM = 36.0, 336.0

    def render_chrome(self, pdf: FPDF, ctx, active_tab: str | None,
                      current_month: int | None) -> None:
        theme = ctx.theme
        pdf.set_fill_color(*theme.desk_c())
        pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, style="F")

        self._rail_tabs(pdf, ctx, active_tab)

        # Card shadows, then cards
        for cx in (self.L_CARD_X, self.R_CARD_X):
            with pdf.local_context(fill_opacity=0.12):
                pdf.set_fill_color(30, 24, 18)
                pdf.rect(cx + 1.5, self.CARD_Y + 2.5, self.CARD_W, self.CARD_H,
                         style="F", round_corners=True, corner_radius=5)
        pdf.set_fill_color(*theme.paper_c())
        for cx in (self.L_CARD_X, self.R_CARD_X):
            pdf.rect(cx, self.CARD_Y, self.CARD_W, self.CARD_H,
                     style="F", round_corners=True, corner_radius=5)

        self._coins(pdf, ctx, current_month)
        render_footer(pdf, theme, ctx.brand, x=25.0, y=349.0)
        render_home_button(pdf, ctx.nav, theme)

    def _rail_tabs(self, pdf: FPDF, ctx, active_tab: str | None) -> None:
        """Category tabs protruding from the left card edge."""
        theme = ctx.theme
        tab_h, gap = 26.0, 2.0
        x, w = 6.0, 12.0        # drawn to x=18 -- 2 mm tucks under the card
        for i, (label, key) in enumerate(ctx.tabs[:10]):
            y = 40.0 + i * (tab_h + gap)
            is_active = label == active_tab
            if is_active:
                fill = theme.active_tab_c()
                txt = WHITE
            else:
                fill = blend(theme.rgb("tab_inactive"),
                             theme.rgb("secondary"), 0.25 + 0.05 * (i % 3))
                txt = blend(theme.rgb("text"), theme.rgb("primary"), 0.25)
            with pdf.local_context(fill_opacity=0.12):
                pdf.set_fill_color(30, 24, 18)
                pdf.rect(x - 0.5, y + 0.8, w, tab_h, style="F",
                         round_corners=("TOP_LEFT", "BOTTOM_LEFT"),
                         corner_radius=2.2)
            pdf.set_fill_color(*fill)
            pdf.rect(x, y, w, tab_h, style="F",
                     round_corners=("TOP_LEFT", "BOTTOM_LEFT"),
                     corner_radius=2.2)
            pdf.set_text_color(*txt)
            size = fit_text(pdf, label, theme.body, "B", 6.0, tab_h - 4,
                            min_size=4.4)
            pdf.set_font(theme.body, "B", size)
            cx = x + (w - 2.0) / 2 - 0.2
            cy = y + tab_h / 2
            text_w = pdf.get_string_width(label)
            with pdf.rotation(angle=90, x=cx, y=cy):
                pdf.set_xy(cx - text_w / 2, cy - 2.2)
                pdf.cell(text_w + 0.5, 4.4, label, align="C")
            link_id = ctx.nav.get_link(key)
            if link_id is not None:
                pdf.link(x, y, 10.0, tab_h, link_id)
        pdf.set_text_color(0, 0, 0)

    def _coins(self, pdf: FPDF, ctx, current_month: int | None) -> None:
        """13 coin tabs centered on the right card edge (slot 0 = YEAR)."""
        theme = ctx.theme
        slot_h = (self.COIN_BOTTOM - self.COIN_TOP) / 13.0
        inactive_text = blend(theme.rgb("text"), theme.rgb("primary"), 0.3)
        active_slot = current_month if current_month is not None else -1

        def coin(slot: int, label: str, fill, txt, r: float, key: str,
                 bold_size: float) -> None:
            cy = self.COIN_TOP + slot_h * (slot + 0.5)
            with pdf.local_context(fill_opacity=0.12):
                pdf.set_fill_color(30, 24, 18)
                pdf.ellipse(self.COIN_X - r + 0.6, cy - r + 0.9, r * 2, r * 2,
                            style="F")
            pdf.set_fill_color(*fill)
            pdf.ellipse(self.COIN_X - r, cy - r, r * 2, r * 2, style="F")
            pdf.set_text_color(*txt)
            pdf.set_font(theme.body, "B", bold_size)
            pdf.set_xy(self.COIN_X - r, cy - 2.2)
            pdf.cell(r * 2, 4.4, label, align="C")
            link_id = ctx.nav.get_link(key)
            if link_id is not None:
                pdf.link(self.COIN_X - r, cy - r, r * 2, r * 2, link_id)

        coin(0, "YR",
             blend(theme.rgb("tab_inactive"), theme.rgb("primary"), 0.28),
             inactive_text, 7.5, NavigationManager.year_glance_key(), 5.2)
        for m in range(1, 13):
            if m == active_slot:
                continue
            coin(m, MONTH_ABBREVS[m - 1], _month_tab_fill(theme, m),
                 inactive_text, 7.5, NavigationManager.month_key(m), 5.2)
        if active_slot >= 1:
            coin(active_slot, MONTH_ABBREVS[active_slot - 1],
                 theme.active_tab_c(), WHITE, 9.0,
                 NavigationManager.month_key(active_slot), 5.6)
        pdf.set_text_color(0, 0, 0)

    def back_button(self, pdf: FPDF, ctx, target_key: str, label: str) -> None:
        from src.planner.widgets import outline_button

        theme = ctx.theme
        link_id = ctx.nav.get_link(target_key)
        pdf.set_font(theme.body, "B", 7)
        w = max(40.0, pdf.get_string_width(label.upper()) + 14)
        outline_button(pdf, theme, 457.0 - w, 20.0, w, 8.5, label, link=link_id)


class FlatShell:
    """S3: the page is the paper; file-folder month tabs; footer categories."""

    header_style = "script-month"

    FOLDER_X0, FOLDER_X1 = 40.0, 442.0

    def render_chrome(self, pdf: FPDF, ctx, active_tab: str | None,
                      current_month: int | None) -> None:
        theme = ctx.theme
        pdf.set_fill_color(*theme.paper_c())
        pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, style="F")

        self._folders(pdf, ctx, current_month)

        # Gutter hairline between the panels
        pdf.set_draw_color(*theme.rgb("grid_line"))
        pdf.set_line_width(0.3)
        pdf.line(241.0, 48.0, 241.0, 340.0)

        self._footer_categories(pdf, ctx, active_tab)

    def _folders(self, pdf: FPDF, ctx, current_month: int | None) -> None:
        theme = ctx.theme
        gap = 1.2
        w = (self.FOLDER_X1 - self.FOLDER_X0 - 12 * gap) / 13.0
        inactive_text = blend(theme.rgb("text"), theme.rgb("primary"), 0.3)

        def folder(slot: int, label: str, key: str, active: bool) -> None:
            x = self.FOLDER_X0 + slot * (w + gap)
            link_id = ctx.nav.get_link(key)
            if active:
                top = 0.5
                pdf.set_fill_color(*theme.paper_c())
                pdf.polygon([(x + 2.5, top), (x + w - 2.5, top),
                             (x + w, 13.0), (x, 13.0)], style="F")
                pdf.set_draw_color(*blend(theme.rgb("grid_line"),
                                          theme.structural(), 0.35))
                pdf.set_line_width(0.3)
                pdf.line(x, 13.0, x + 2.5, top)
                pdf.line(x + 2.5, top, x + w - 2.5, top)
                pdf.line(x + w - 2.5, top, x + w, 13.0)
                txt = blend(theme.rgb("text"), theme.rgb("primary"), 0.3)
            else:
                fill = (blend(theme.rgb("tab_inactive"), theme.rgb("primary"), 0.28)
                        if slot == 0 else _month_tab_fill(theme, slot))
                pdf.set_fill_color(*fill)
                pdf.polygon([(x + 2.5, 2.0), (x + w - 2.5, 2.0),
                             (x + w, 13.0), (x, 13.0)], style="F")
                txt = inactive_text
            pdf.set_text_color(*txt)
            size = fit_text(pdf, label, theme.body, "B", 6.4, w - 5,
                            min_size=4.8)
            pdf.set_font(theme.body, "B", size)
            pdf.set_xy(x, 2.0)
            pdf.cell(w, 11.0, label, align="C")
            if link_id is not None:
                pdf.link(x, 0.5, w, 12.5, link_id)

        folder(0, "YEAR", NavigationManager.year_glance_key(), False)
        for m in range(1, 13):
            folder(m, MONTH_ABBREVS[m - 1], NavigationManager.month_key(m),
                   current_month == m)
        pdf.set_text_color(0, 0, 0)

    def _footer_categories(self, pdf: FPDF, ctx, active_tab: str | None) -> None:
        """Centered small-caps category link row (INDEX first = home)."""
        theme = ctx.theme
        y, h = 346.8, 4.5
        pdf.set_font(theme.body, "B", 6.5)
        try:
            pdf.set_char_spacing(0.6)
        except Exception:
            pass
        sep = "   ·   "
        sep_w = pdf.get_string_width(sep)
        widths = [pdf.get_string_width(label) for label, _ in ctx.tabs]
        total = sum(widths) + sep_w * (len(ctx.tabs) - 1)
        x = (PAGE_WIDTH - total) / 2
        muted = blend(theme.rgb("text"), theme.rgb("primary"), 0.3)
        for (label, key), lw in zip(ctx.tabs, widths):
            is_active = label == active_tab
            pdf.set_text_color(*(theme.rgb("text") if is_active else muted))
            pdf.set_xy(x, y)
            link_id = ctx.nav.get_link(key)
            if link_id is not None:
                pdf.cell(lw + 0.5, h, label, link=link_id)
            else:
                pdf.cell(lw + 0.5, h, label)
            if is_active:
                pdf.set_draw_color(*(theme.rgb("accent")
                                     if theme.ink.accent_active
                                     else theme.structural()))
                pdf.set_line_width(0.3)
                pdf.line(x, y + h + 0.8, x + lw, y + h + 0.8)
            x += lw
            if label != ctx.tabs[-1][0]:
                pdf.set_text_color(*blend(theme.rgb("text_light"),
                                          theme.paper_c(), 0.35))
                pdf.set_xy(x, y)
                pdf.cell(sep_w, h, sep)
                x += sep_w
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass
        # Brand line only when it fits left of the centered row
        start_x = (PAGE_WIDTH - total) / 2
        pdf.set_font(theme.body, "", 5.8)
        brand_text = f"© {ctx.brand} · Digital Planner"
        if 22.0 + pdf.get_string_width(brand_text) + 8 < start_x:
            render_footer(pdf, theme, ctx.brand, x=22.0, y=347.2)
        pdf.set_text_color(0, 0, 0)

    def back_button(self, pdf: FPDF, ctx, target_key: str, label: str) -> None:
        from src.planner.widgets import outline_button

        theme = ctx.theme
        link_id = ctx.nav.get_link(target_key)
        pdf.set_font(theme.body, "B", 7)
        w = max(40.0, pdf.get_string_width(label.upper()) + 14)
        outline_button(pdf, theme, 460.0 - w, 20.0, w, 8.5, label, link=link_id)


class PosterShell:
    """S4: full-bleed raw background; inline month strip; header categories."""

    header_style = "plain"

    X0, X1 = 30.0, 452.0
    STRIP_Y, STRIP_H = 46.0, 6.5

    def render_chrome(self, pdf: FPDF, ctx, active_tab: str | None,
                      current_month: int | None) -> None:
        theme = ctx.theme
        pdf.set_fill_color(*theme.rgb("background"))
        pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, style="F")

        self._header_categories(pdf, ctx, active_tab)

        # Title rule
        pdf.set_draw_color(*theme.structural())
        pdf.set_line_width(0.4)
        pdf.line(self.X0, 44.0, self.X1, 44.0)

        self._month_strip(pdf, ctx, current_month)

        # Footer: centered small caps
        pdf.set_text_color(*blend(theme.rgb("text_light"),
                                  theme.rgb("background"), 0.35))
        pdf.set_font(theme.body, "B", 6)
        try:
            pdf.set_char_spacing(1.2)
        except Exception:
            pass
        pdf.set_xy(0, 348.0)
        pdf.cell(PAGE_WIDTH, 4, f"© {ctx.brand} · DIGITAL PLANNER".upper(),
                 align="C")
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass
        pdf.set_text_color(0, 0, 0)

    def _header_categories(self, pdf: FPDF, ctx, active_tab: str | None) -> None:
        theme = ctx.theme
        y, h = 18.0, 8.0
        pdf.set_font(theme.body, "B", 6.5)
        try:
            pdf.set_char_spacing(0.6)
        except Exception:
            pass
        gap = 6.0
        widths = [pdf.get_string_width(label) for label, _ in ctx.tabs]
        total = sum(widths) + gap * (len(ctx.tabs) - 1)
        x = self.X1 - total
        muted = blend(theme.rgb("text"), theme.rgb("background"), 0.35)
        for (label, key), lw in zip(ctx.tabs, widths):
            is_active = label == active_tab
            pdf.set_text_color(*(theme.rgb("text") if is_active else muted))
            pdf.set_xy(x, y)
            link_id = ctx.nav.get_link(key)
            if link_id is not None:
                pdf.cell(lw + 0.5, h, label, link=link_id)
            else:
                pdf.cell(lw + 0.5, h, label)
            if is_active:
                pdf.set_draw_color(*(theme.rgb("accent")
                                     if theme.ink.accent_active
                                     else theme.structural()))
                pdf.set_line_width(0.3)
                pdf.line(x, y + h - 0.6, x + lw, y + h - 0.6)
            x += lw + gap
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass
        pdf.set_text_color(0, 0, 0)

    def _month_strip(self, pdf: FPDF, ctx, current_month: int | None) -> None:
        theme = ctx.theme
        y, h = self.STRIP_Y, self.STRIP_H
        cell_w = (self.X1 - self.X0) / 13.0
        pdf.set_draw_color(*theme.rgb("grid_line"))
        pdf.set_line_width(0.25)
        for i in range(1, 13):
            tx = self.X0 + i * cell_w
            pdf.line(tx, y + 1.0, tx, y + h - 1.0)

        def strip_cell(slot: int, label: str, key: str, active: bool) -> None:
            x = self.X0 + slot * cell_w
            link_id = ctx.nav.get_link(key)
            if active:
                pdf.set_fill_color(*theme.active_tab_c())
                pdf.rect(x + 1.5, y, cell_w - 3, h, style="F",
                         round_corners=True, corner_radius=h / 2)
                pdf.set_text_color(*WHITE)
                pdf.set_font(theme.body, "B", 6.5)
            else:
                pdf.set_text_color(*theme.rgb("text_light"))
                pdf.set_font(theme.body, "", 6.5)
            pdf.set_xy(x, y)
            pdf.cell(cell_w, h, label, align="C")
            if link_id is not None:
                pdf.link(x, y, cell_w, h, link_id)

        strip_cell(0, "YEAR", NavigationManager.year_glance_key(), False)
        for m in range(1, 13):
            strip_cell(m, MONTH_ABBREVS[m - 1], NavigationManager.month_key(m),
                       current_month == m)
        pdf.set_text_color(0, 0, 0)

    def back_button(self, pdf: FPDF, ctx, target_key: str, label: str) -> None:
        """Small-caps text link at the title baseline (merges the deferred
        subtitle when the page has one: ``subtitle · BACK LABEL``)."""
        theme = ctx.theme
        link_id = ctx.nav.get_link(target_key)
        sub = getattr(ctx, "deferred_subtitle", "") or ""
        if hasattr(ctx, "deferred_subtitle"):
            ctx.deferred_subtitle = ""
        y, h = 29.0, 10.0

        pdf.set_font(theme.body, "B", 7)
        try:
            pdf.set_char_spacing(0.6)
        except Exception:
            pass
        lbl = label.upper()
        lbl_w = pdf.get_string_width(lbl) + 1
        sub_w = 0.0
        if sub:
            pdf.set_font(theme.body, "", 7)
            sub_w = pdf.get_string_width(sub) + pdf.get_string_width("  ·  ")
        x = self.X1 - lbl_w - sub_w
        if sub:
            pdf.set_text_color(*theme.rgb("text_light"))
            pdf.set_xy(x, y)
            pdf.cell(sub_w, h, f"{sub}  ·  ")
        pdf.set_font(theme.body, "B", 7)
        pdf.set_text_color(*blend(theme.rgb("text"), theme.structural(), 0.3))
        pdf.set_xy(self.X1 - lbl_w, y)
        if link_id is not None:
            pdf.cell(lbl_w, h, lbl, link=link_id)
        else:
            pdf.cell(lbl_w, h, lbl)
        pdf.set_draw_color(*theme.structural())
        pdf.set_line_width(0.25)
        pdf.line(self.X1 - lbl_w, y + h - 1.4, self.X1 - 1, y + h - 1.4)
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass
        pdf.set_text_color(0, 0, 0)


SHELLS: dict[str, object] = {
    "binder": BinderShell(),
    "cards": CardsShell(),
    "flat": FlatShell(),
    "poster": PosterShell(),
}


# ---------------------------------------------------------------------------
# Bookmark helpers
# ---------------------------------------------------------------------------

def add_bookmark(pdf: FPDF, title: str, level: int = 0) -> None:
    """Add a PDF outline/bookmark entry for the current page.

    No ``section_title_styles`` must ever be configured on *pdf*: with no
    styles set, ``start_section`` records the outline entry without
    rendering anything.  (The previous "invisible 0.01pt title" hack
    rendered overlapping micro-glyphs that garbled text extraction, and
    silently dropped outline entries whenever rendering raised -- e.g. on
    the cover, before any font was selected.)
    """
    try:
        pdf.start_section(title, level=level)
    except Exception:
        logger.warning("Could not add bookmark %r (level %d)", title, level)
