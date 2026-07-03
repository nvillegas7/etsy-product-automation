"""Page renderers for every planner page type.

Each class exposes a ``render(pdf, ctx, ...)`` method that adds one page to
the given FPDF instance.  ``ctx`` is a :class:`PageContext` bundling the
theme (palette + fonts + design), navigation manager, shell geometry,
motif family, and the niche-aware top tabs.

Weekly / monthly bodies and cover compositions dispatch through the
``WEEKLY_VARIANTS`` / ``MONTHLY_VARIANTS`` / ``COVER_VARIANTS`` registries
(design dimensions D2 and D6); the ``boxed`` / ``arch`` entries are the
pre-design renderings, verbatim.

All coordinates are in millimetres on a 482.0 x 361.2 mm landscape page.
"""

from __future__ import annotations

import calendar as _cal
import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from fpdf import FPDF

from src.planner.designs import DesignTheme
from src.planner.layout import (
    PAGE_HEIGHT,
    PAGE_WIDTH,
    PENNANT_W,
    Geometry,
    Panel,
    build_geometry,
)
from src.planner.motifs import MOTIFS, MotifFamily
from src.planner.navigation import (
    NavigationManager,
    SHELLS,
    add_bookmark,
    render_pennant,
)
from src.planner.styles import Theme, searchable_tracking
from src.planner.widgets import (
    WHITE,
    blend,
    checkbox_lines,
    fill_texture,
    fit_role_text,
    fit_text,
    labelled_box,
    mood_faces,
    outline_button,
    page_title,
    priority_rows,
    progress_bar,
    ruled_lines,
    section_label,
    table,
    water_droplets,
    wrap_text,
)

_cal.setfirstweekday(_cal.SUNDAY)
WEEKDAY_LABELS = ["S", "M", "T", "W", "T", "F", "S"]
WEEKDAY_NAMES = ["SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY",
                 "THURSDAY", "FRIDAY", "SATURDAY"]


# ===================================================================
# Page context + chrome scaffolding
# ===================================================================

@dataclass
class PageContext:
    """Everything shared by page renderers for one planner build."""

    theme: Theme
    nav: NavigationManager
    tabs: list[tuple[str, str]] = field(default_factory=list)  # (label, key)
    year: int = 2026
    brand: str = "Made with love"
    design: DesignTheme = field(default_factory=DesignTheme)
    geo: Geometry = field(default_factory=lambda: build_geometry("binder"))
    motif: MotifFamily = field(default_factory=lambda: MOTIFS["botanical"])
    deferred_subtitle: str = ""    # poster shell: subtitle merges into back link
    corner_action_key: str = ""    # target of the shell's corner button, if any


def begin_content_page(
    pdf: FPDF,
    ctx: PageContext,
    *,
    bind_key: str | None = None,
    bookmark: str | None = None,
    bookmark_level: int = 0,
    active_tab: str | None = None,
    current_month: int | None = None,
) -> None:
    """Add a page and draw the shell chrome in its z-order."""
    pdf.add_page()
    if bind_key:
        ctx.nav.bind_link(pdf, bind_key)
    if bookmark:
        add_bookmark(pdf, bookmark, level=bookmark_level)
    ctx.deferred_subtitle = ""
    ctx.corner_action_key = ""
    SHELLS[ctx.design.shell].render_chrome(pdf, ctx, active_tab, current_month)


def render_back_link(pdf: FPDF, ctx: PageContext, target_key: str,
                     label: str) -> None:
    """Shell-owned back button (placement varies per shell).

    Records the target on the context so body renderers (e.g. the columns
    monthly sidebar) can skip quick links that would duplicate the corner
    button's target on the same page edge.
    """
    ctx.corner_action_key = target_key
    SHELLS[ctx.design.shell].back_button(pdf, ctx, target_key, label)


def page_header(
    pdf: FPDF,
    ctx: PageContext,
    light: str,
    bold: str,
    *,
    month: int | None = None,
    subtitle: str | None = None,
) -> None:
    """Header zone, dispatching on the shell's header style."""
    theme = ctx.theme
    geo = ctx.geo
    style = geo.header_style

    if style == "pennant":
        if month is not None:
            render_pennant(pdf, theme, month, ctx.year,
                           x=geo.pennant_x, y=geo.pennant_y)
            tx = geo.pennant_x + PENNANT_W + 9
        else:
            tx = geo.left_x
        # Cards has a shorter header zone: tighten the title/subtitle stack
        title_dy = 7.0 if ctx.design.shell == "binder" else 4.0
        sub_dy = 15.5 if ctx.design.shell == "binder" else 16.0
        end_x = page_title(pdf, theme, tx, geo.header_y + title_dy, light, bold)
        if subtitle:
            theme.text(pdf, "page_subtitle", tx, geo.header_y + sub_dy, 120, 5,
                       subtitle, color=theme.rgb("text_light"))
            pdf.set_text_color(*theme.rgb("text"))
        elif ctx.design.shell == "cards":
            ctx.motif.divider(pdf, theme, (tx + end_x) / 2,
                              geo.header_y + 17.5, 40)

    elif style == "script-month":
        tx = geo.left_x
        if month is not None:
            name = _cal.month_name[month]
            pdf.set_font(theme.script, "", 20)
            pdf.set_text_color(*blend(theme.rgb("primary"),
                                      theme.rgb("text"), 0.1))
            mw = pdf.get_string_width(name)
            pdf.set_xy(tx, geo.header_y + 2)
            pdf.cell(mw + 2, 12, name)
            tx += mw + 8
        end_x = page_title(pdf, theme, tx, geo.header_y + 4.5, light, bold)
        if subtitle:
            theme.text(pdf, "page_subtitle", tx, geo.header_y + 15, 120, 5,
                       subtitle, color=theme.rgb("text_light"))
            pdf.set_text_color(*theme.rgb("text"))
        else:
            ctx.motif.divider(pdf, theme, (tx + end_x) / 2,
                              geo.header_y + 17.5, 40)

    else:   # "plain" (poster)
        if month is not None:
            month_line = f"{_cal.month_name[month].upper()} · {ctx.year}"
            pdf.set_font(theme.body, "B", 7)
            try:
                # Month names are searchable content: clamp the small-caps
                # tracking to the extraction-safe budget (1.2 pt at 7 pt
                # split 'JANUARY' into per-letter words).
                pdf.set_char_spacing(searchable_tracking(7, 1.2))
            except Exception:
                pass
            pdf.set_text_color(*blend(theme.rgb("text"),
                                      theme.rgb("background"), 0.3))
            pdf.set_xy(geo.left_x, geo.header_y)
            pdf.cell(120, 5, month_line)
            try:
                pdf.set_char_spacing(0)
            except Exception:
                pass
        spec = theme.role("page_title")
        page_title(pdf, theme, geo.left_x, geo.header_y + 9, light, bold,
                   size=spec.size * 1.25)
        # Subtitle merges into the back link (drawn right-aligned later)
        ctx.deferred_subtitle = subtitle or ""

    pdf.set_text_color(*theme.rgb("text"))


# ===================================================================
# Shared small pieces
# ===================================================================

def _habit_mini_grid(pdf: FPDF, ctx: PageContext, panel: Panel,
                     rows_n: int = 4, cols_n: int = 8) -> None:
    """The weekly extras habit grid: habit rows x 7 day cols + label col."""
    theme = ctx.theme
    gr = theme.rule_c()
    ch, cw = panel.h / rows_n, panel.w / cols_n
    pdf.set_draw_color(*gr)
    pdf.set_line_width(0.22)
    pdf.set_font(theme.body, "B", 5.4)
    pdf.set_text_color(*theme.rgb("text_light"))
    for c in range(1, cols_n):
        pdf.set_xy(panel.x + c * cw, panel.y - 3.4)
        pdf.cell(cw, 3, WEEKDAY_LABELS[c - 1], align="C")
    for r in range(rows_n + 1):
        pdf.line(panel.x, panel.y + r * ch, panel.x2, panel.y + r * ch)
    for c in range(cols_n + 1):
        pdf.line(panel.x + c * cw, panel.y, panel.x + c * cw, panel.y2)


def _numbered_priority_lines(pdf: FPDF, theme: Theme, panel: Panel,
                             n: int = 3, size: float = 7.5) -> None:
    """'1.' text-numbered priority lines (the lighter treatment)."""
    gr = theme.rule_c()
    for i in range(n):
        ly = panel.y + 3.5 + i * ((panel.y2 - panel.y - 3) / n)
        pdf.set_text_color(*theme.rgb("text_light"))
        theme.set_type(pdf, "inline_label", size=size)
        pdf.set_xy(panel.x + 1, ly - 3)
        pdf.cell(6, 4, f"{i + 1}.", align="L")
        pdf.set_draw_color(*gr)
        pdf.line(panel.x + 8, ly + 1, panel.x2, ly + 1)


# ===================================================================
# 1. CoverPage (D6 -- cover compositions)
# ===================================================================

def _shown_title(ctx: PageContext, title: str, display_title: str) -> str:
    """Strip a leading year from the title (the year accent shows it)."""
    shown = (display_title or title).strip()
    if shown.startswith(str(ctx.year)):
        stripped = shown[len(str(ctx.year)):].strip(" -·")
        if stripped:
            shown = stripped
    return shown


def _cover_year_text(theme: Theme, year: int) -> str:
    if theme.design.voice == "typewriter":
        return "- " + " ".join(str(year)) + " -"
    return str(year)


def _niche_pill(pdf: FPDF, theme: Theme, label: str, y: float,
                cx: float | None = None, right: float | None = None,
                outline: bool = False) -> None:
    """Niche badge.  ``outline=True`` renders a white-stroked pill for
    covers whose background is the solid primary plate (a filled primary
    pill would vanish there)."""
    pdf.set_font(theme.body, "B", 8.5)
    label = label.upper()
    try:
        pdf.set_char_spacing(1.2)
    except Exception:
        pass
    pw = pdf.get_string_width(label) + 10
    px = (right - pw) if right is not None else (cx - pw / 2)
    if outline:
        pdf.set_draw_color(*WHITE)
        pdf.set_line_width(0.5)
        pdf.rect(px, y, pw, 9, style="D", round_corners=True,
                 corner_radius=4.5)
    else:
        pdf.set_fill_color(*theme.rgb("primary"))
        pdf.rect(px, y, pw, 9, style="F", round_corners=True,
                 corner_radius=4.5)
    pdf.set_text_color(*WHITE)
    pdf.set_xy(px, y)
    pdf.cell(pw, 9, label, align="C")
    try:
        pdf.set_char_spacing(0)
    except Exception:
        pass


def _fit_title_lines(pdf: FPDF, theme: Theme, text: str, max_w: float,
                     max_lines: int = 2, min_size: float = 14,
                     max_size: float | None = None) -> tuple[list[str], float]:
    """Role-aware display-title fitting: shrink, then wrap, never clip."""
    spec = theme.role("display_title")
    fam = theme._family(spec.family)
    cased, size = fit_role_text(pdf, theme, "display_title", text, max_w,
                                min_size=20 if max_size is None else min_size,
                                max_size=max_size)
    lines = [cased]
    if pdf.get_string_width(cased) > max_w:
        lines = wrap_text(pdf, cased, fam, spec.style, size, max_w)
        while len(lines) > max_lines and size > min_size:
            size -= 2
            pdf.set_font(fam, spec.style, size)
            lines = wrap_text(pdf, cased, fam, spec.style, size, max_w)
        lines = lines[:max_lines]
    return lines, size


def _cover_arch(pdf: FPDF, ctx: PageContext, title: str, display_title: str,
                subtitle: str, niche_name: str) -> None:
    """C1: arch-family cover.

    STRUCTURE VARIES BY VOICE (designs.py "Cover-composition variance"):
    the classic voice keeps the golden double-frame + rounded title card +
    hero artwork verbatim; every other voice renders the 'meadow horizon'
    composition instead -- a staggered motif field growing from a rolling
    ground band, open sky, high centered title -- so classic and meadow
    read as different products at thumbnail size.
    """
    if ctx.design.voice == "classic":
        _arch_classic(pdf, ctx, title, display_title, subtitle, niche_name)
    else:
        _arch_meadow(pdf, ctx, title, display_title, subtitle, niche_name)


def _arch_classic(pdf: FPDF, ctx: PageContext, title: str, display_title: str,
                  subtitle: str, niche_name: str) -> None:
    """C1a: double frame + rounded title card (classic-exact, golden)."""
    theme = ctx.theme
    bg = theme.paper_c()
    pr = theme.rgb("primary")
    cx = PAGE_WIDTH / 2

    pdf.set_fill_color(*bg)
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, style="F")

    ctx.motif.cover_hero(pdf, theme,
                         seed=f"{ctx.year}-{ctx.design.motif}-cover")

    # Double border frame
    pdf.set_draw_color(*pr)
    pdf.set_line_width(0.6)
    pdf.rect(9, 9, PAGE_WIDTH - 18, PAGE_HEIGHT - 18, style="D")
    pdf.set_line_width(0.25)
    pdf.rect(12, 12, PAGE_WIDTH - 24, PAGE_HEIGHT - 24, style="D")

    # Corner ornaments at the inner frame (botanical's hero has branches)
    if ctx.design.motif != "botanical":
        inset = 12
        ctx.motif.corner(pdf, theme, inset, inset, 22, "TL")
        ctx.motif.corner(pdf, theme, PAGE_WIDTH - inset, inset, 22, "TR")
        ctx.motif.corner(pdf, theme, inset, PAGE_HEIGHT - inset, 22, "BL")
        ctx.motif.corner(pdf, theme, PAGE_WIDTH - inset, PAGE_HEIGHT - inset,
                         22, "BR")

    # Title card
    shown = _shown_title(ctx, title, display_title)
    card = Panel(PAGE_WIDTH * 0.185, PAGE_HEIGHT * 0.315,
                 PAGE_WIDTH * 0.63, PAGE_HEIGHT * 0.29)
    with pdf.local_context(fill_opacity=0.82):
        pdf.set_fill_color(*bg)
        pdf.rect(card.x, card.y, card.w, card.h, style="F",
                 round_corners=True, corner_radius=6)
    pdf.set_draw_color(*pr)
    pdf.set_line_width(0.4)
    pdf.rect(card.x + 3, card.y + 3, card.w - 6, card.h - 6, style="D",
             round_corners=True, corner_radius=4.5)

    max_w = card.w - 24
    text_color = blend(theme.rgb("text"), pr, 0.25)

    # Year accent
    pdf.set_text_color(*blend(pr, theme.rgb("text"), 0.1))
    theme.set_type(pdf, "cover_year")
    pdf.set_xy(card.x, card.y + 10)
    pdf.cell(card.w, 12, _cover_year_text(theme, ctx.year), align="C")

    # Display title -- shrink then wrap to max 2 lines; never clip.
    lines, size = _fit_title_lines(pdf, theme, shown, max_w, max_lines=2,
                                   min_size=14)
    pdf.set_text_color(*text_color)
    line_h = size * 0.42
    ty = card.y + 30
    for ln in lines:
        pdf.set_xy(card.x, ty)
        pdf.cell(card.w, line_h, ln, align="C")
        ty += line_h + 2

    ctx.motif.divider(pdf, theme, cx, ty + 6, 84)

    if subtitle:
        sub, _ = fit_role_text(pdf, theme, "cover_subtitle",
                               subtitle, max_w, min_size=8)
        pdf.set_text_color(*blend(theme.rgb("text"), pr, 0.4))
        pdf.set_xy(card.x, ty + 10)
        pdf.cell(card.w, 10, sub, align="C")

    if niche_name:
        _niche_pill(pdf, theme, niche_name, PAGE_HEIGHT - 40, cx=cx)


def _arch_meadow(pdf: FPDF, ctx: PageContext, title: str, display_title: str,
                 subtitle: str, niche_name: str) -> None:
    """C1b: 'meadow horizon' (every non-classic voice).

    A staggered motif field grows from a rolling ground band along the
    bottom; the sky above stays open with the title block centered high
    and the niche pill folded into that stack.  Deliberately shares no
    structure with the classic arch: no border frame, no corner
    quarter-circles, no concentric mounds, no mirrored sprigs, no
    bottom-center badge.
    """
    theme = ctx.theme
    bg = theme.paper_c()
    pr = theme.rgb("primary")
    sec = theme.rgb("secondary")
    cx = PAGE_WIDTH / 2

    pdf.set_fill_color(*bg)
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, style="F")

    # Rolling ground: two overlapping sine-edged bands anchor the bottom
    ground_y = 294.0
    for base_y, color, op, phase, amp, wl in (
            (ground_y, sec, 0.35, 0.0, 5.0, 230.0),
            (ground_y + 20.0, pr, 0.28, 88.0, 6.0, 300.0)):
        step = PAGE_WIDTH / 48.0
        pts = [(i * step,
                base_y + amp * math.sin(2 * math.pi * (i * step + phase) / wl))
               for i in range(49)]
        pts += [(PAGE_WIDTH, PAGE_HEIGHT), (0, PAGE_HEIGHT)]
        with pdf.local_context(fill_opacity=op):
            pdf.set_fill_color(*color)
            pdf.polygon(pts, style="F")

    # Staggered motif field growing from the ground line
    ctx.motif.ground_field(pdf, theme, 26.0, ground_y - 130.0,
                           PAGE_WIDTH - 52.0, 136.0,
                           seed=f"{ctx.year}-{ctx.design.motif}-meadow")

    # Title stack, centered high in the open sky
    max_w = 340.0
    pdf.set_text_color(*blend(pr, theme.rgb("text"), 0.1))
    theme.set_type(pdf, "cover_year")
    pdf.set_xy(cx - max_w / 2, 34.0)
    pdf.cell(max_w, 12, _cover_year_text(theme, ctx.year), align="C")

    shown = _shown_title(ctx, title, display_title)
    lines, size = _fit_title_lines(pdf, theme, shown, max_w, max_lines=2,
                                   min_size=14)
    pdf.set_text_color(*blend(theme.rgb("text"), pr, 0.25))
    line_h = size * 0.42
    ty = 54.0
    for ln in lines:
        pdf.set_xy(cx - max_w / 2, ty)
        pdf.cell(max_w, line_h, ln, align="C")
        ty += line_h + 2

    ctx.motif.divider(pdf, theme, cx, ty + 7, 60)

    if subtitle:
        sub, _ = fit_role_text(pdf, theme, "cover_subtitle",
                               subtitle, max_w, min_size=8)
        pdf.set_text_color(*blend(theme.rgb("text"), pr, 0.4))
        pdf.set_xy(cx - max_w / 2, ty + 12)
        pdf.cell(max_w, 10, sub, align="C")
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass

    if niche_name:
        _niche_pill(pdf, theme, niche_name, ty + 27, cx=cx)
    pdf.set_text_color(*theme.rgb("text"))


# -- C2: band cover -- four ink-keyed structures -------------------------


def _fit_band_title(pdf: FPDF, theme: Theme, shown: str, max_w: float,
                    max_lines: int = 3,
                    min_size: float = 15) -> tuple[list[str], float]:
    """Title lines for text sitting ON a solid band.

    Script faces are never reversed in solid bands (same rationale as the
    validator rule): swap to the display face in title case.
    """
    if theme.role("display_title").family == "script":
        cased = " ".join(w if w.isdigit() else w.capitalize()
                         for w in shown.split())
        size = fit_text(pdf, cased, theme.display, "B", 40, max_w,
                        min_size=16)
        lines = wrap_text(pdf, cased, theme.display, "B", size, max_w)
        while len(lines) > max_lines and size > 16:
            size -= 2
            lines = wrap_text(pdf, cased, theme.display, "B", size, max_w)
        return lines[:max_lines], size
    return _fit_title_lines(pdf, theme, shown, max_w, max_lines=max_lines,
                            min_size=min_size)


def _band_subtitle_font(pdf: FPDF, theme: Theme, subtitle: str) -> str:
    """Select the cover-subtitle face (script swaps to display) and return
    the cased text."""
    if theme.role("cover_subtitle").family == "script":
        pdf.set_font(theme.display, "", 13)
        return subtitle
    theme.set_type(pdf, "cover_subtitle")
    return theme.case("cover_subtitle", subtitle)


def _cover_band(pdf: FPDF, ctx: PageContext, title: str, display_title: str,
                subtitle: str, niche_name: str) -> None:
    """C2: solid-band cover.

    STRUCTURE IS KEYED ON THE INK DIMENSION (designs.py
    "Cover-composition variance") -- palette architecture decides how the
    solid band is deployed, and every structure renders motif artwork so
    the motif family is visible on the storefront hero image:

    soft-wash     wide left band + motif pattern field   (riviera)
    ink-on-paper  slim top band + motif strips on paper  (ledger)
    accent-pop    thin accent spine + ghost numeral      (blueprint)
    filled-blocks full-bleed solid plate                 (noir)
    """
    variant = {
        "soft-wash": _band_left,
        "ink-on-paper": _band_top,
        "accent-pop": _band_spine,
        "filled-blocks": _band_solid,
    }[ctx.design.ink]
    variant(pdf, ctx, title, display_title, subtitle, niche_name)


def _band_left(pdf: FPDF, ctx: PageContext, title: str, display_title: str,
               subtitle: str, niche_name: str) -> None:
    """C2a (soft-wash): wide left band; motif pattern fills the open field."""
    theme = ctx.theme
    pr = theme.rgb("primary")
    band_w = 170.0

    pdf.set_fill_color(*theme.paper_c())
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, style="F")

    # Motif pattern field on the open panel (no ghost numeral here)
    ctx.motif.pattern_fill(pdf, theme, band_w, 0, PAGE_WIDTH - band_w,
                           PAGE_HEIGHT,
                           seed=f"{ctx.year}-{ctx.design.motif}-band")

    pdf.set_fill_color(*pr)
    pdf.rect(0, 0, band_w, PAGE_HEIGHT, style="F")

    # In-band text is reversed: script faces are never reversed -> serif
    reversed_script = theme.role("display_title").family == "script"
    pdf.set_text_color(*WHITE)
    if theme.role("cover_year").family == "script" or reversed_script:
        pdf.set_font(theme.display, "", 26)
    else:
        theme.set_type(pdf, "cover_year")
    pdf.set_xy(0, 52)
    pdf.cell(band_w, 14, _cover_year_text(theme, ctx.year), align="C")

    shown = _shown_title(ctx, title, display_title)
    lines, size = _fit_band_title(pdf, theme, shown, 140.0)
    pdf.set_text_color(*WHITE)
    ty = 110.0
    for ln in lines:
        pdf.set_xy(15, ty)
        pdf.cell(140, size * 0.5, ln, align="L")
        ty += size * 0.5 + 2

    if subtitle:
        sub = _band_subtitle_font(pdf, theme, subtitle)
        fit_text(pdf, sub, pdf.font_family, pdf.font_style,
                 pdf.font_size_pt, 150, min_size=8)
        pdf.set_text_color(*WHITE)
        pdf.set_xy(10, 297)
        pdf.cell(band_w - 20, 8, sub, align="C")
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass

    if niche_name:
        _niche_pill(pdf, theme, niche_name, 330, right=PAGE_WIDTH - 24)
    pdf.set_text_color(*theme.rgb("text"))


def _band_top(pdf: FPDF, ctx: PageContext, title: str, display_title: str,
              subtitle: str, niche_name: str) -> None:
    """C2b (ink-on-paper): slim top band; the page below stays paper."""
    theme = ctx.theme
    pr = theme.rgb("primary")
    band_h = 64.0
    x0, x1 = 30.0, PAGE_WIDTH - 30.0

    pdf.set_fill_color(*theme.paper_c())
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, style="F")
    pdf.set_fill_color(*pr)
    pdf.rect(0, 0, PAGE_WIDTH, band_h, style="F")

    # Reversed title, left in the band
    shown = _shown_title(ctx, title, display_title)
    lines, size = _fit_band_title(pdf, theme, shown, 300.0, max_lines=2)
    pdf.set_text_color(*WHITE)
    line_h = size * 0.5
    ty = band_h / 2 - (len(lines) * (line_h + 2) - 2) / 2
    for ln in lines:
        pdf.set_xy(x0, ty)
        pdf.cell(310, line_h, ln, align="L")
        ty += line_h + 2

    # Reversed year, right in the band
    pdf.set_text_color(*WHITE)
    if theme.role("cover_year").family == "script":
        pdf.set_font(theme.display, "", 22)
    else:
        theme.set_type(pdf, "cover_year")
    pdf.set_xy(x1 - 110, band_h / 2 - 6)
    pdf.cell(110, 12, _cover_year_text(theme, ctx.year), align="R")
    try:
        pdf.set_char_spacing(0)
    except Exception:
        pass

    # Motif tick-rule riding under the band + subtitle in ink
    ctx.motif.band(pdf, theme, x0, band_h + 8, x1 - x0)
    if subtitle:
        sub = _band_subtitle_font(pdf, theme, subtitle)
        fit_text(pdf, sub, pdf.font_family, pdf.font_style,
                 pdf.font_size_pt, 300, min_size=8)
        pdf.set_text_color(*blend(theme.rgb("text"), pr, 0.4))
        pdf.set_xy(x0, band_h + 20)
        pdf.cell(300, 8, sub, align="L")
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass

    # Oversized faint year stamp anchoring the open field (typewriter
    # voice), like a ledger's date impression -- fills the middle so the
    # page no longer reads bottom-right-heavy with an empty upper-left.
    pdf.set_font("Courier", "B", 116)
    with pdf.local_context(fill_opacity=0.07):
        pdf.set_text_color(*pr)
        pdf.set_xy(x0 - 6, 150.0)
        pdf.cell(360, 74, str(ctx.year))

    # Motif triangle field as a full-width footer, grounding the page; a
    # fine rule caps it so it reads as a deliberate band, not a stray block.
    footer_top = 268.0
    ctx.motif.pattern_fill(pdf, theme, x0, footer_top, x1 - x0,
                           PAGE_HEIGHT - footer_top - 30.0,
                           seed=f"{ctx.year}-{ctx.design.motif}-band")
    pdf.set_draw_color(*blend(theme.rgb("grid_line"), pr, 0.5))
    pdf.set_line_width(0.4)
    pdf.line(x0, footer_top - 10.0, x1, footer_top - 10.0)

    if niche_name:
        _niche_pill(pdf, theme, niche_name, PAGE_HEIGHT - 21, right=x1)
    pdf.set_text_color(*theme.rgb("text"))


def _band_spine(pdf: FPDF, ctx: PageContext, title: str, display_title: str,
                subtitle: str, niche_name: str) -> None:
    """C2c (accent-pop): thin accent spine, ghost numeral TOP-right, ink
    title mid-left -- deliberately the inverse stack of the editorial
    asymmetric masthead (title top / ghost bottom) used by studio."""
    theme = ctx.theme
    pr = theme.rgb("primary")
    acc = theme.rgb("accent")
    spine_w = 22.0
    x0 = 44.0

    pdf.set_fill_color(*theme.paper_c())
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, style="F")
    pdf.set_fill_color(*acc)
    pdf.rect(0, 0, spine_w, PAGE_HEIGHT, style="F")
    pdf.set_draw_color(*pr)
    pdf.set_line_width(0.3)
    pdf.line(spine_w + 6, 0, spine_w + 6, PAGE_HEIGHT)

    # Draughtsman's tick-scale down the spine rule -- reinforces the
    # blueprint identity and fills the left gutter with precise line-work.
    tick_c = blend(theme.rgb("grid_line"), pr, 0.55)
    ty = 12.0
    i = 0
    while ty <= PAGE_HEIGHT - 12.0:
        major = (i % 5 == 0)
        pdf.set_draw_color(*(acc if major else tick_c))
        pdf.set_line_width(0.5 if major else 0.3)
        pdf.line(spine_w + 6, ty, spine_w + 6 + (6.0 if major else 3.2), ty)
        ty += 12.0
        i += 1

    # Ghost numeral top-right (honest light-color glyphs)
    ghost = blend(pr, theme.rgb("background"), 0.85)
    pdf.set_font(theme.display, "B", 150)
    pdf.set_text_color(*ghost)
    yw = pdf.get_string_width(str(ctx.year))
    pdf.set_xy(PAGE_WIDTH - 30 - yw, 34)
    pdf.cell(yw + 2, 60, str(ctx.year), align="R")

    # Title in ink on the open field, mid-page
    shown = _shown_title(ctx, title, display_title)
    lines, size = _fit_title_lines(pdf, theme, shown, 320.0, max_lines=3,
                                   min_size=18)
    pdf.set_text_color(*blend(theme.rgb("text"), pr, 0.15))
    ty = 138.0
    for ln in lines:
        pdf.set_xy(x0, ty)
        pdf.cell(340, size * 0.45, ln, align="L")
        ty += size * 0.45 + 3

    if subtitle:
        sub, _ = fit_role_text(pdf, theme, "cover_subtitle", subtitle, 300,
                               min_size=8)
        pdf.set_text_color(*blend(theme.rgb("text"), pr, 0.4))
        pdf.set_xy(x0, ty + 8)
        pdf.cell(300, 8, sub, align="L")
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass

    # Accent rule + year, anchored under the text block
    pdf.set_fill_color(*acc)
    pdf.rect(x0, ty + 26, 60, 3.5, style="F")
    pdf.set_font(theme.body, "B", 10)
    try:
        pdf.set_char_spacing(searchable_tracking(10, 2.0))
    except Exception:
        pass
    pdf.set_text_color(*blend(theme.rgb("text"), pr, 0.35))
    pdf.set_xy(x0, ty + 34)
    pdf.cell(120, 6, str(ctx.year))
    try:
        pdf.set_char_spacing(0)
    except Exception:
        pass

    # Motif pattern strip along the bottom-left
    ctx.motif.pattern_fill(pdf, theme, x0, 300.0, 240.0, 50.0,
                           seed=f"{ctx.year}-{ctx.design.motif}-band")

    if niche_name:
        _niche_pill(pdf, theme, niche_name, 336, right=PAGE_WIDTH - 30)
    pdf.set_text_color(*theme.rgb("text"))


def _band_solid(pdf: FPDF, ctx: PageContext, title: str, display_title: str,
                subtitle: str, niche_name: str) -> None:
    """C2d (filled-blocks): the whole page is the band -- solid plate.

    The validator already bars script + typewriter from filled-blocks, so
    only classic/serif/grotesk reversed type ever renders here.
    """
    theme = ctx.theme
    pr = theme.rgb("primary")
    x0 = 30.0

    pdf.set_fill_color(*pr)
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, style="F")

    # Motif ornaments read against the plate in secondary/accent
    ctx.motif.corner(pdf, theme, 12, 12, 26, "TL")
    ctx.motif.corner(pdf, theme, PAGE_WIDTH - 12, 12, 26, "TR")
    ctx.motif.corner(pdf, theme, 12, PAGE_HEIGHT - 12, 26, "BL")
    ctx.motif.corner(pdf, theme, PAGE_WIDTH - 12, PAGE_HEIGHT - 12, 26, "BR")

    # Giant ghost numeral, centered high (honest lighter-than-plate glyphs)
    ghost = blend(pr, WHITE, 0.22)
    pdf.set_font(theme.display, "B", 210)
    pdf.set_text_color(*ghost)
    yw = pdf.get_string_width(str(ctx.year))
    pdf.set_xy(PAGE_WIDTH / 2 - yw / 2, 58)
    pdf.cell(yw + 2, 84, str(ctx.year), align="C")

    # Motif strip above the title
    ctx.motif.band(pdf, theme, x0, 224.0, 200.0)

    # Reversed title, lower-left
    shown = _shown_title(ctx, title, display_title)
    lines, size = _fit_band_title(pdf, theme, shown, 360.0, max_lines=2,
                                  min_size=16)
    pdf.set_text_color(*WHITE)
    ty = 240.0
    for ln in lines:
        pdf.set_xy(x0, ty)
        pdf.cell(380, size * 0.5, ln, align="L")
        ty += size * 0.5 + 3

    if subtitle:
        sub = _band_subtitle_font(pdf, theme, subtitle)
        fit_text(pdf, sub, pdf.font_family, pdf.font_style,
                 pdf.font_size_pt, 300, min_size=8)
        pdf.set_text_color(*WHITE)
        pdf.set_xy(x0, ty + 6)
        pdf.cell(300, 8, sub, align="L")
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass

    if niche_name:
        _niche_pill(pdf, theme, niche_name, 330, right=PAGE_WIDTH - 30,
                    outline=True)
    pdf.set_text_color(*theme.rgb("text"))


def _cover_editorial(pdf: FPDF, ctx: PageContext, title: str,
                     display_title: str, subtitle: str,
                     niche_name: str) -> None:
    """C3: editorial cover family.

    MASTHEAD VARIES BY VOICE (designs.py "Cover-composition variance"):
    typewriter keeps the asymmetric left-flush stack with the ghost year
    (almanac); grotesk renders a swiss-poster composition -- lower-third
    masthead, rule blocks, corner accent plate, NO ghost (studio);
    serif/classic/script center a classical masthead between top and base
    rules (gallery).
    """
    if ctx.design.voice == "grotesk":
        _editorial_swiss(pdf, ctx, title, display_title, subtitle,
                         niche_name)
    elif ctx.design.voice == "typewriter":
        _editorial_asymmetric(pdf, ctx, title, display_title, subtitle,
                              niche_name)
    else:
        _editorial_centered(pdf, ctx, title, display_title, subtitle,
                            niche_name)


def _editorial_asymmetric(pdf: FPDF, ctx: PageContext, title: str,
                          display_title: str, subtitle: str,
                          niche_name: str) -> None:
    """C3a: left-flush masthead stack (grotesk / typewriter voices)."""
    theme = ctx.theme
    pr = theme.rgb("primary")
    x0, x1 = 30.0, PAGE_WIDTH - 30.0

    pdf.set_fill_color(*theme.paper_c())
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, style="F")

    # Top rule + niche pill sitting on it + motif strip below it
    pdf.set_draw_color(*pr)
    pdf.set_line_width(0.6)
    pdf.line(x0, 40, x1, 40)
    if niche_name:
        _niche_pill(pdf, theme, niche_name, 35.5, right=x1)
    ctx.motif.band(pdf, theme, x0, 45.0, x1 - x0 - 130)

    shown = _shown_title(ctx, title, display_title)
    lines, size = _fit_title_lines(pdf, theme, shown, x1 - x0 - 110,
                                   max_lines=2, min_size=20, max_size=54)
    pdf.set_text_color(*blend(theme.rgb("text"), pr, 0.15))
    ty = 64.0
    for ln in lines:
        pdf.set_xy(x0, ty)
        pdf.cell(x1 - x0, size * 0.45, ln, align="L")
        ty += size * 0.45 + 3

    sub_y = ty + 8
    if subtitle:
        sub, _ = fit_role_text(pdf, theme, "cover_subtitle", subtitle,
                               x1 - x0 - 120, min_size=8)
        pdf.set_text_color(*blend(theme.rgb("text"), pr, 0.4))
        pdf.set_xy(x0, sub_y)
        pdf.cell(x1 - x0 - 120, 8, sub, align="L")
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass

    ctx.motif.divider(pdf, theme, x0 + 20, sub_y + 14, 40)

    # Accent bar + year small caps, anchored to the masthead flow (a bar
    # at a fixed y floated mid-air whenever the title wrapped differently)
    bar_y = sub_y + 24
    pdf.set_fill_color(*pr)
    pdf.rect(x0, bar_y, 60, 4, style="F")
    pdf.set_font(theme.body, "B", 10)
    try:
        pdf.set_char_spacing(searchable_tracking(10, 2.0))
    except Exception:
        pass
    pdf.set_text_color(*blend(theme.rgb("text"), pr, 0.35))
    pdf.set_xy(x0, bar_y + 12)
    pdf.cell(120, 6, str(ctx.year))
    try:
        pdf.set_char_spacing(0)
    except Exception:
        pass

    # Ghost year, honest low-opacity glyphs
    pdf.set_font(theme.display, "B", 96)
    pdf.set_text_color(*pr)
    with pdf.local_context(fill_opacity=0.18):
        yw = pdf.get_string_width(str(ctx.year))
        pdf.set_xy(x1 - yw - 2, 330 - 34)
        pdf.cell(yw + 2, 36, str(ctx.year), align="R")
    pdf.set_text_color(*theme.rgb("text"))


def _editorial_swiss(pdf: FPDF, ctx: PageContext, title: str,
                     display_title: str, subtitle: str,
                     niche_name: str) -> None:
    """C3c: swiss-poster masthead (grotesk voice -- studio).

    Restraint IS the artwork: an accent plate anchoring the top-left
    corner (reversed year), a vast open field, then a full-width
    oversized tracked masthead in the lower third framed by thick rule
    blocks.  No ghost numeral -- that stays the typewriter/serif
    editorials' signature.
    """
    theme = ctx.theme
    pr = theme.rgb("primary")
    acc = theme.rgb("accent")
    x0, x1 = 30.0, PAGE_WIDTH - 30.0

    pdf.set_fill_color(*theme.paper_c())
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, style="F")

    # Accent plate flush to the top-left corner, year reversed on it
    plate = 62.0
    pdf.set_fill_color(*acc)
    pdf.rect(0, 0, plate, plate, style="F")
    pdf.set_text_color(*WHITE)
    pdf.set_font(theme.body, "B", 21)
    try:
        pdf.set_char_spacing(searchable_tracking(21, 1.5))
    except Exception:
        pass
    pdf.set_xy(0, plate / 2 - 5)
    pdf.cell(plate, 10, str(ctx.year), align="C")
    try:
        pdf.set_char_spacing(0)
    except Exception:
        pass

    if niche_name:
        _niche_pill(pdf, theme, niche_name, 26.5, right=x1)

    # Masthead block, bottom-anchored in the lower third
    shown = _shown_title(ctx, title, display_title)
    lines, size = _fit_title_lines(pdf, theme, shown, x1 - x0, max_lines=2,
                                   min_size=24, max_size=84)
    line_h = size * 0.45
    block_h = len(lines) * (line_h + 3) - 3
    ty = 312.0 - block_h

    # Thick + hairline rule blocks above the masthead
    pdf.set_fill_color(*pr)
    pdf.rect(x0, ty - 19.0, x1 - x0, 6.0, style="F")
    pdf.rect(x0, ty - 9.5, x1 - x0, 1.6, style="F")

    pdf.set_text_color(*blend(theme.rgb("text"), pr, 0.15))
    for ln in lines:
        pdf.set_xy(x0, ty)
        pdf.cell(x1 - x0, line_h, ln, align="L")
        ty += line_h + 3
    try:
        pdf.set_char_spacing(0)
    except Exception:
        pass

    # Subtitle left / year right on one row under the masthead
    row_y = 318.0
    if subtitle:
        sub, _ = fit_role_text(pdf, theme, "cover_subtitle", subtitle,
                               x1 - x0 - 140, min_size=8)
        pdf.set_text_color(*blend(theme.rgb("text"), pr, 0.4))
        pdf.set_xy(x0, row_y)
        pdf.cell(x1 - x0 - 140, 8, sub, align="L")
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass
    pdf.set_font(theme.body, "B", 10)
    try:
        pdf.set_char_spacing(searchable_tracking(10, 2.0))
    except Exception:
        pass
    pdf.set_text_color(*blend(theme.rgb("text"), pr, 0.35))
    pdf.set_xy(x1 - 120, row_y)
    pdf.cell(120, 8, str(ctx.year), align="R")
    try:
        pdf.set_char_spacing(0)
    except Exception:
        pass

    # Base bar with a small accent block keyed to its right end
    pdf.set_fill_color(*pr)
    pdf.rect(x0, 330.0, x1 - x0, 7.0, style="F")
    pdf.set_fill_color(*acc)
    pdf.rect(x1 - 7.0, 330.0, 7.0, 7.0, style="F")
    pdf.set_text_color(*theme.rgb("text"))


def _editorial_centered(pdf: FPDF, ctx: PageContext, title: str,
                        display_title: str, subtitle: str,
                        niche_name: str) -> None:
    """C3b: fine-press framed title page (serif / classic / script voice).

    A thin double frame turns the whitespace into an intentional field; the
    serif masthead sits in the upper third and a colophon rule carrying the
    year anchors the lower third, so the page reads as a crafted title page
    rather than a wireframe with a big empty middle.
    """
    theme = ctx.theme
    pr = theme.rgb("primary")
    cx = PAGE_WIDTH / 2

    pdf.set_fill_color(*theme.paper_c())
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, style="F")

    # Fine-press double frame just inside the margins
    fx0, fy0 = 24.0, 22.0
    fx1, fy1 = PAGE_WIDTH - 24.0, PAGE_HEIGHT - 22.0
    frame_c = blend(theme.rgb("grid_line"), pr, 0.55)
    pdf.set_draw_color(*frame_c)
    pdf.set_line_width(0.5)
    pdf.rect(fx0, fy0, fx1 - fx0, fy1 - fy0, style="D")
    pdf.set_line_width(0.2)
    pdf.rect(fx0 + 3.6, fy0 + 3.6, fx1 - fx0 - 7.2, fy1 - fy0 - 7.2, style="D")

    # Quiet plus-tick texture turns the open fields into considered
    # stationery ground rather than dead white; the masthead band and the
    # colophon stay clear reserves floating within that field.
    tx0, tx1 = fx0 + 16, fx1 - 16
    ctx.motif.pattern_fill(pdf, theme, tx0, 182, tx1 - tx0, 60,
                           seed="gallery-mid", scale=0.9)
    ctx.motif.pattern_fill(pdf, theme, tx0, 264, tx1 - tx0, 66,
                           seed="gallery-low", scale=0.9)

    # Fine right-angle brackets just inside the frame corners -- quiet craft
    b = 9.0
    ctx.motif.corner(pdf, theme, fx0 + b, fy0 + b, 20, "TL")
    ctx.motif.corner(pdf, theme, fx1 - b, fy0 + b, 20, "TR")
    ctx.motif.corner(pdf, theme, fx0 + b, fy1 - b, 20, "BL")
    ctx.motif.corner(pdf, theme, fx1 - b, fy1 - b, 20, "BR")

    # Niche pill riding the top frame line, centered
    if niche_name:
        _niche_pill(pdf, theme, niche_name, fy0 - 4.5, cx=cx)

    # Year kicker (small caps), centered high under the frame
    pdf.set_font(theme.body, "B", 9.5)
    try:
        pdf.set_char_spacing(searchable_tracking(9.5, 2.4))
    except Exception:
        pass
    pdf.set_text_color(*blend(theme.rgb("text"), pr, 0.42))
    pdf.set_xy(0, 78)
    pdf.cell(PAGE_WIDTH, 6, str(ctx.year), align="C")
    try:
        pdf.set_char_spacing(0)
    except Exception:
        pass

    # Centered serif title
    shown = _shown_title(ctx, title, display_title)
    lines, size = _fit_title_lines(pdf, theme, shown, fx1 - fx0 - 90,
                                   max_lines=2, min_size=20, max_size=56)
    pdf.set_text_color(*blend(theme.rgb("text"), pr, 0.12))
    ty = 104.0
    for ln in lines:
        pdf.set_xy(0, ty)
        pdf.cell(PAGE_WIDTH, size * 0.45, ln, align="C")
        ty += size * 0.45 + 3

    # Minimal divider + script subtitle
    ctx.motif.divider(pdf, theme, cx, ty + 12, 66)
    sub_y = ty + 18
    if subtitle:
        sub, _ = fit_role_text(pdf, theme, "cover_subtitle", subtitle,
                               fx1 - fx0 - 120, min_size=8)
        pdf.set_text_color(*blend(theme.rgb("text"), pr, 0.4))
        pdf.set_xy(0, sub_y)
        pdf.cell(PAGE_WIDTH, 8, sub, align="C")
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass

    # Colophon rule anchoring the lower field: a fine line broken by the
    # year set in the serif display face -- a considered detail, not a void.
    col_y = 252.0
    pdf.set_font(theme.display, "", 16)
    yr = str(ctx.year)
    yw = pdf.get_string_width(yr)
    gap = yw / 2 + 9
    pdf.set_draw_color(*frame_c)
    pdf.set_line_width(0.45)
    pdf.line(cx - 92, col_y, cx - gap, col_y)
    pdf.line(cx + gap, col_y, cx + 92, col_y)
    for ex in (cx - 92, cx + 92):
        pdf.line(ex, col_y - 2.4, ex, col_y + 2.4)   # tick ends
    pdf.set_text_color(*blend(theme.rgb("text"), pr, 0.28))
    pdf.set_xy(cx - yw / 2 - 3, col_y - 8.5)
    pdf.cell(yw + 6, 12, yr, align="C")
    pdf.set_text_color(*theme.rgb("text"))


def _cover_pattern(pdf: FPDF, ctx: PageContext, title: str,
                   display_title: str, subtitle: str,
                   niche_name: str) -> None:
    """C4: motif-pattern cover family.

    PATTERN USAGE IS KEYED ON INK (designs.py "Cover-composition
    variance"): accent-pop confines an OVERSIZED pattern crop to a bottom
    wave band and floats a bordered title card in the open field above
    (sorbet); every other ink keeps the full-bleed pattern with the
    full-width translucent title band (midnight, atelier -- whose motif
    pattern art differs).
    """
    if ctx.design.ink == "accent-pop":
        _pattern_card(pdf, ctx, title, display_title, subtitle, niche_name)
    else:
        _pattern_band(pdf, ctx, title, display_title, subtitle, niche_name)


def _pattern_band(pdf: FPDF, ctx: PageContext, title: str,
                  display_title: str, subtitle: str,
                  niche_name: str) -> None:
    """C4a: full-width translucent title band across the pattern."""
    theme = ctx.theme
    pr = theme.rgb("primary")
    bg = theme.paper_c()

    pdf.set_fill_color(*bg)
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, style="F")
    ctx.motif.pattern_fill(pdf, theme, 0, 0, PAGE_WIDTH, PAGE_HEIGHT,
                           seed=f"{ctx.year}-{ctx.design.motif}-pattern")

    # Title band
    with pdf.local_context(fill_opacity=0.94):
        pdf.set_fill_color(*bg)
        pdf.rect(0, 150, PAGE_WIDTH, 80, style="F")
    pdf.set_draw_color(*pr)
    pdf.set_line_width(0.4)
    pdf.line(0, 150, PAGE_WIDTH, 150)
    pdf.line(0, 230, PAGE_WIDTH, 230)

    pdf.set_text_color(*blend(pr, theme.rgb("text"), 0.1))
    theme.set_type(pdf, "cover_year")
    pdf.set_xy(0, 156)
    pdf.cell(PAGE_WIDTH, 12, _cover_year_text(theme, ctx.year), align="C")

    shown = _shown_title(ctx, title, display_title)
    lines, size = _fit_title_lines(pdf, theme, shown, 360.0, max_lines=2,
                                   min_size=16)
    pdf.set_text_color(*blend(theme.rgb("text"), pr, 0.25))
    ty = 176.0
    for ln in lines:
        pdf.set_xy(0, ty)
        pdf.cell(PAGE_WIDTH, size * 0.42, ln, align="C")
        ty += size * 0.42 + 2

    if subtitle:
        sub, _ = fit_role_text(pdf, theme, "cover_subtitle", subtitle, 360,
                               min_size=8)
        pdf.set_text_color(*blend(theme.rgb("text"), pr, 0.4))
        pdf.set_xy(0, max(ty + 3, 214.0))
        pdf.cell(PAGE_WIDTH, 10, sub, align="C")
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass

    if niche_name:
        _niche_pill(pdf, theme, niche_name, 320, cx=PAGE_WIDTH / 2)
    pdf.set_text_color(*theme.rgb("text"))


def _pattern_card(pdf: FPDF, ctx: PageContext, title: str,
                  display_title: str, subtitle: str,
                  niche_name: str) -> None:
    """C4b (accent-pop): oversized motif wave band + floating title card.

    The pattern is cropped to a bottom band at ~2.6x scale (half-drop
    modules read individually at thumbnail size) under a large open
    field; the accent-bordered title card floats in the open field --
    scale + coverage contrast with the full-bleed pattern covers.
    """
    theme = ctx.theme
    pr = theme.rgb("primary")
    acc = theme.rgb("accent")
    bg = theme.paper_c()
    cx = PAGE_WIDTH / 2

    pdf.set_fill_color(*bg)
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, style="F")

    # Oversized half-drop pattern confined to the bottom wave band, a
    # motif hairline riding its top edge
    band_top = 236.0
    ctx.motif.pattern_fill(pdf, theme, 0, band_top, PAGE_WIDTH,
                           PAGE_HEIGHT - band_top,
                           seed=f"{ctx.year}-{ctx.design.motif}-pattern",
                           scale=2.6)
    ctx.motif.divider(pdf, theme, cx, band_top - 7.0, PAGE_WIDTH - 76.0)

    card = Panel(PAGE_WIDTH * 0.26, 54.0, PAGE_WIDTH * 0.48, 128.0)
    pdf.set_fill_color(*bg)
    pdf.rect(card.x, card.y, card.w, card.h, style="F",
             round_corners=True, corner_radius=6)
    pdf.set_draw_color(*acc)
    pdf.set_line_width(0.8)
    pdf.rect(card.x, card.y, card.w, card.h, style="D",
             round_corners=True, corner_radius=6)
    pdf.set_draw_color(*pr)
    pdf.set_line_width(0.25)
    pdf.rect(card.x + 3, card.y + 3, card.w - 6, card.h - 6, style="D",
             round_corners=True, corner_radius=4.5)

    max_w = card.w - 30

    pdf.set_text_color(*blend(pr, theme.rgb("text"), 0.1))
    theme.set_type(pdf, "cover_year")
    pdf.set_xy(card.x, card.y + 12)
    pdf.cell(card.w, 12, _cover_year_text(theme, ctx.year), align="C")

    shown = _shown_title(ctx, title, display_title)
    lines, size = _fit_title_lines(pdf, theme, shown, max_w, max_lines=2,
                                   min_size=14)
    pdf.set_text_color(*blend(theme.rgb("text"), pr, 0.25))
    line_h = size * 0.42
    ty = card.y + 34
    for ln in lines:
        pdf.set_xy(card.x, ty)
        pdf.cell(card.w, line_h, ln, align="C")
        ty += line_h + 2

    ctx.motif.divider(pdf, theme, cx, ty + 6, 70)

    if subtitle:
        sub, _ = fit_role_text(pdf, theme, "cover_subtitle", subtitle,
                               max_w, min_size=8)
        pdf.set_text_color(*blend(theme.rgb("text"), pr, 0.4))
        pdf.set_xy(card.x, ty + 10)
        pdf.cell(card.w, 10, sub, align="C")
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass

    if niche_name:
        _niche_pill(pdf, theme, niche_name, card.y2 + 16, cx=cx)
    pdf.set_text_color(*theme.rgb("text"))


COVER_VARIANTS = {
    "arch": _cover_arch,
    "band": _cover_band,
    "editorial": _cover_editorial,
    "pattern": _cover_pattern,
}


class CoverPage:
    """Decorative full-bleed cover; composition dispatches on design.cover."""

    @staticmethod
    def render(
        pdf: FPDF,
        ctx: PageContext,
        title: str,
        display_title: str = "",
        subtitle: str = "",
        niche_name: str = "",
    ) -> None:
        pdf.add_page()
        ctx.nav.bind_link(pdf, NavigationManager.cover_key())
        add_bookmark(pdf, "Cover", level=0)
        COVER_VARIANTS[ctx.design.cover](pdf, ctx, title, display_title,
                                         subtitle, niche_name)
        pdf.set_text_color(0, 0, 0)
        pdf.set_line_width(0.2)


# ===================================================================
# 2. IndexPage
# ===================================================================

def _accent_note_font(pdf: FPDF, theme: Theme, size: float) -> None:
    """Handwriting-style accent font, coherent with the voice."""
    voice = theme.design.voice
    if voice == "grotesk":
        pdf.set_font(theme.body, "I", size * 0.75)
    elif voice == "typewriter":
        pdf.set_font("Courier", "", size * 0.75)
    else:
        pdf.set_font(theme.script, "", size)


class IndexPage:
    """Linked table of contents: yearly, monthly, niche section, custom."""

    @staticmethod
    def render(
        pdf: FPDF,
        ctx: PageContext,
        niche_name: str = "",
        niche_pages: list[dict] | None = None,
    ) -> None:
        theme = ctx.theme
        nav = ctx.nav
        begin_content_page(
            pdf, ctx,
            bind_key=NavigationManager.index_key(),
            bookmark="Index",
            active_tab="INDEX",
        )
        page_header(pdf, ctx, "INDEX", "PAGE")

        lb = ctx.geo.left_body()
        rb = ctx.geo.right_body()
        gr = theme.rule_c()
        border = theme.border_c()

        # ---- LEFT: YEARLY + MONTHLY ---------------------------------------
        y = section_label(pdf, theme, lb.x, lb.y, "Yearly", underline_w=lb.w)
        y += 1.5
        btn_w = (lb.w - 6) / 2
        outline_button(pdf, theme, lb.x, y, btn_w, 9, "Year at a Glance",
                       link=nav.get_link(NavigationManager.year_glance_key()))
        outline_button(pdf, theme, lb.x + btn_w + 6, y, btn_w, 9, "Goals",
                       link=nav.get_link(NavigationManager.goals_key()))
        y += 15

        y = section_label(pdf, theme, lb.x, y, "Monthly", underline_w=lb.w)
        y += 1.5
        rows, cols = 6, 2
        cell_w = (lb.w - 6) / cols
        cell_h = (lb.y2 - y - 42) / rows
        sub_labels = [("Cal", NavigationManager.month_key),
                      ("Plan", NavigationManager.monthly_plan_key),
                      ("Review", NavigationManager.monthly_review_key)]
        for m in range(1, 13):
            col = (m - 1) % cols
            row = (m - 1) // cols
            bx = lb.x + col * (cell_w + 6)
            by = y + row * cell_h
            box = Panel(bx, by + 1, cell_w, cell_h - 2.5)
            pdf.set_fill_color(*WHITE)
            pdf.set_draw_color(*border)
            pdf.set_line_width(0.3)
            pdf.rect(box.x, box.y, box.w, box.h, style="FD",
                     round_corners=True, corner_radius=1.6)
            # Month name (accent face) + linked sub-labels
            pdf.set_text_color(*blend(theme.rgb("text"), theme.rgb("primary"), 0.3))
            _accent_note_font(pdf, theme, 13)
            pdf.set_xy(box.x + 4, box.y)
            pdf.cell(38, box.h, _cal.month_name[m], align="L",
                     link=nav.get_link(NavigationManager.month_key(m)))
            pdf.set_font(theme.body, "", 7)
            pdf.set_text_color(*theme.rgb("text_light"))
            sx = box.x + 46
            for label, keyfn in sub_labels:
                w = pdf.get_string_width(label) + 3
                pdf.set_xy(sx, box.y)
                pdf.cell(w, box.h, label, align="C", link=nav.get_link(keyfn(m)))
                sx += w
                if label != "Review":
                    pdf.set_xy(sx, box.y)
                    pdf.cell(3, box.h, "·", align="C")
                    sx += 3

        y += rows * cell_h + 5
        y = section_label(pdf, theme, lb.x, y, "More", underline_w=lb.w)
        y += 1.5
        extras = [("Notes", NavigationManager.notes_key()),
                  ("Habit Tracker", NavigationManager.habits_key()),
                  ("Goals", NavigationManager.goals_key())]
        ew = (lb.w - 12) / 3
        for i, (label, key) in enumerate(extras):
            outline_button(pdf, theme, lb.x + i * (ew + 6), y, ew, 9, label,
                           link=nav.get_link(key))

        # ---- RIGHT: NICHE SECTION + CUSTOM ---------------------------------
        title = f"{niche_name} Sections" if niche_name else "Sections"
        y = section_label(pdf, theme, rb.x, rb.y, title, underline_w=rb.w)
        y += 1.5
        niche_pages = niche_pages or []
        row_h = 11.0
        band = theme.band_fill()
        for i, np_cfg in enumerate(niche_pages):
            key = NavigationManager.niche_page_key(np_cfg["id"])
            box = Panel(rb.x, y + i * (row_h + 3), rb.w, row_h)
            pdf.set_draw_color(*border)
            pdf.set_line_width(0.3)
            if band is not None:
                pdf.set_fill_color(*band)
                pdf.rect(box.x, box.y, box.w, box.h, style="FD",
                         round_corners=True, corner_radius=1.6)
            else:
                pdf.rect(box.x, box.y, box.w, box.h, style="D",
                         round_corners=True, corner_radius=1.6)
            pdf.set_text_color(*theme.band_text_c())
            pdf.set_font(theme.body, "B", 8.5)
            pdf.set_xy(box.x + 6, box.y)
            pdf.cell(box.w - 24, box.h, np_cfg["label"], align="L",
                     link=nav.get_link(key))
            pdf.set_font(theme.body, "", 8)
            pdf.set_text_color(*theme.rgb("text_light")
                               if band != theme.rgb("primary")
                               else WHITE)
            pdf.set_xy(box.x + box.w - 16, box.y)
            pdf.cell(10, box.h, ">", align="C", link=nav.get_link(key))
        y += len(niche_pages) * (row_h + 3) + 4

        y = section_label(pdf, theme, rb.x, y, "Custom Sections", underline_w=rb.w)
        y += 1.5
        n_custom = max(1, int((rb.y2 - y) / (row_h + 3)))
        soft = theme.box_fill()
        for i in range(n_custom):
            box = Panel(rb.x, y + i * (row_h + 3), rb.w, row_h)
            if box.y2 > rb.y2 + 1:
                break
            pdf.set_draw_color(*gr)
            pdf.set_line_width(0.3)
            if soft is not None:
                pdf.set_fill_color(*soft)
                pdf.rect(box.x, box.y, box.w, box.h, style="FD",
                         round_corners=True, corner_radius=1.6)
            else:
                pdf.rect(box.x, box.y, box.w, box.h, style="D",
                         round_corners=True, corner_radius=1.6)

        pdf.set_text_color(0, 0, 0)


# ===================================================================
# 3. YearGlancePage
# ===================================================================

class YearGlancePage:
    """12 mini month calendars, each clickable through to its month page."""

    @staticmethod
    def render(pdf: FPDF, ctx: PageContext) -> None:
        theme = ctx.theme
        nav = ctx.nav
        begin_content_page(
            pdf, ctx,
            bind_key=NavigationManager.year_glance_key(),
            bookmark="Year at a Glance",
            active_tab="CALENDAR",
        )
        page_header(pdf, ctx, str(ctx.year), "YEAR AT A GLANCE")
        render_back_link(pdf, ctx, NavigationManager.index_key(),
                         "Back to Index")

        panels = [ctx.geo.left_body(), ctx.geo.right_body()]
        for half, panel in enumerate(panels):
            for i in range(6):
                m = half * 6 + i + 1
                mm = ctx.geo.mini_month_metrics(panel.inset(0, 2), i % 2, i // 2)
                YearGlancePage._mini_month(pdf, ctx, m, mm)

        pdf.set_text_color(0, 0, 0)

    @staticmethod
    def _mini_month(pdf: FPDF, ctx: PageContext, month: int, mm) -> None:
        theme = ctx.theme
        border = theme.border_c()
        link = ctx.nav.get_link(NavigationManager.month_key(month))

        pdf.set_fill_color(*WHITE)
        pdf.set_draw_color(*border)
        pdf.set_line_width(0.3)
        pdf.rect(mm.x, mm.y, mm.w, mm.h, style="FD",
                 round_corners=True, corner_radius=1.8)
        # Title band
        band = theme.band_fill()
        if band is not None:
            pdf.set_fill_color(*band)
            pdf.rect(mm.x, mm.y, mm.w, mm.title_h, style="F",
                     round_corners=("TOP_LEFT", "TOP_RIGHT"), corner_radius=1.8)
        pdf.set_text_color(*theme.band_text_c())
        pdf.set_font(theme.body, "B", 8)
        try:
            pdf.set_char_spacing(0.6)
        except Exception:
            pass
        pdf.set_xy(mm.x, mm.y)
        pdf.cell(mm.w, mm.title_h, _cal.month_name[month].upper(), align="C")
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass

        # Weekday letters
        pdf.set_font(theme.body, "B", 5.6)
        pdf.set_text_color(*theme.rgb("text_light"))
        gy = mm.y + mm.title_h + 2.5
        for i, wd in enumerate(WEEKDAY_LABELS):
            pdf.set_xy(mm.x + i * mm.cell_w, gy)
            pdf.cell(mm.cell_w, mm.cell_h, wd, align="C")

        # Day numbers
        theme.set_type(pdf, "mini_digit")
        pdf.set_text_color(*theme.rgb("text"))
        weeks = _cal.monthcalendar(ctx.year, month)
        for r, week in enumerate(weeks):
            for c, day in enumerate(week):
                if day == 0:
                    continue
                pdf.set_xy(mm.x + c * mm.cell_w, gy + (r + 1) * mm.cell_h)
                pdf.cell(mm.cell_w, mm.cell_h, str(day), align="C")

        if link is not None:
            pdf.link(mm.x, mm.y, mm.w, mm.h, link)


# ===================================================================
# 4. MonthlyPage (calendar spread; body dispatches on design.interior)
# ===================================================================

def _monthly_boxed(pdf: FPDF, ctx: PageContext, month: int,
                   week_link_map: dict[int, int] | None) -> None:
    """I1: left 7x6 bordered grid + right rail (classic-exact)."""
    theme = ctx.theme
    nav = ctx.nav

    # ---- LEFT: calendar grid -------------------------------------------
    hx, hy, cell_w, row_h = ctx.geo.weekday_header_metrics()
    solid_header = theme.ink.band == "solid"
    if solid_header:
        pdf.set_fill_color(*theme.rgb("primary"))
        pdf.rect(hx, hy, cell_w * 7, 9, style="F")
        pdf.set_text_color(*WHITE)
    else:
        pdf.set_text_color(*blend(theme.rgb("text"), theme.rgb("primary"), 0.35))
    pdf.set_font(theme.body, "B", 8.5)
    for i, label in enumerate(WEEKDAY_LABELS):
        pdf.set_xy(hx + i * cell_w, hy)
        pdf.cell(cell_w, row_h, label, align="C")

    grid = ctx.geo.calendar_grid()
    border = theme.border_c()
    gr = theme.rule_c()
    pdf.set_draw_color(*gr)
    pdf.set_line_width(0.25)
    for row in range(grid.rows + 1):
        y = grid.y + row * grid.cell_h
        pdf.line(grid.x, y, grid.x + grid.width, y)
    for col in range(grid.cols + 1):
        x = grid.x + col * grid.cell_w
        pdf.line(x, grid.y, x, grid.y + grid.height)
    pdf.set_draw_color(*border)
    pdf.set_line_width(0.35)
    pdf.rect(grid.x, grid.y, grid.width, grid.height, style="D")

    month_cal = _cal.monthcalendar(ctx.year, month)
    theme.set_type(pdf, "calendar_digit")
    pdf.set_text_color(*theme.rgb("text"))
    for row_idx, week in enumerate(month_cal):
        for col_idx, day in enumerate(week):
            if day == 0:
                continue
            cx, cy = grid.cell_xy(col_idx, row_idx)
            pdf.set_xy(cx + 1.6, cy + 1.2)
            link_id = None
            if week_link_map and day in week_link_map:
                link_id = nav.get_link(
                    NavigationManager.week_key(week_link_map[day]))
            if link_id is not None:
                pdf.cell(8, 4.5, str(day), link=link_id)
            else:
                pdf.cell(8, 4.5, str(day))

    # ---- RIGHT: focus / priorities / key dates / notes ------------------
    rb = ctx.geo.right_body()
    secs = rb.split_v([0.16, 0.15, 0.37, 0.32], gap=6)

    labelled_box(pdf, theme, secs[0], "Main Focus for this Month", fill=True)

    y = section_label(pdf, theme, secs[1].x, secs[1].y, "Top Priorities",
                      underline_w=None)
    priority_rows(pdf, theme, ctx.motif,
                  Panel(secs[1].x, y, secs[1].w, secs[1].y2 - y))

    table(pdf, theme, secs[2], [("Date", 0.18), ("Key Dates & Events", 0.82)],
          n_rows=9)

    labelled_box(pdf, theme, secs[3], "Notes & Doodles",
                 lines_spacing=None, dots=True)
    pdf.set_text_color(0, 0, 0)


def _monthly_columns(pdf: FPDF, ctx: PageContext, month: int,
                     week_link_map: dict[int, int] | None) -> None:
    """I2: full-spread calendar -- 7 giant day columns + sidebar."""
    theme = ctx.theme
    nav = ctx.nav
    lb = ctx.geo.left_body()
    rb = ctx.geo.right_body()

    weeks = _cal.monthcalendar(ctx.year, month)
    n_rows = len(weeks)
    header_h = 9.0
    row_h = (lb.h - header_h) / n_rows
    gutter_w = 8.0
    day_w_l = (lb.w - gutter_w) / 4.0
    sidebar_w = 46.0
    day_w_r = (rb.w - sidebar_w - 6.0) / 3.0

    def col_x(i: int) -> float:
        if i < 4:
            return lb.x + gutter_w + i * day_w_l
        return rb.x + (i - 4) * day_w_r

    def col_w(i: int) -> float:
        return day_w_l if i < 4 else day_w_r

    # Weekday header
    pdf.set_text_color(*theme.band_text_c())
    solid = theme.ink.band == "solid"
    for i in range(7):
        if solid:
            pdf.set_fill_color(*theme.rgb("primary"))
            pdf.rect(col_x(i), lb.y, col_w(i), header_h, style="F")
            pdf.set_text_color(*WHITE)
        theme.set_type(pdf, "band_label", size=7.5)
        pdf.set_xy(col_x(i), lb.y)
        pdf.cell(col_w(i), header_h,
                 theme.case("band_label", WEEKDAY_NAMES[i]), align="C")
    _plain_reset(pdf, theme)

    # Grids (per panel so nothing crosses the gutter)
    grid_y = lb.y + header_h
    for panel, cols_n, x0, dw in ((lb, 4, lb.x + gutter_w, day_w_l),
                                  (rb, 3, rb.x, day_w_r)):
        pdf.set_draw_color(*theme.rule_c())
        pdf.set_line_width(0.25)
        for r in range(1, n_rows):
            pdf.line(x0, grid_y + r * row_h, x0 + cols_n * dw,
                     grid_y + r * row_h)
        for c in range(1, cols_n):
            pdf.line(x0 + c * dw, grid_y, x0 + c * dw, grid_y + n_rows * row_h)
        pdf.set_draw_color(*theme.border_c())
        pdf.set_line_width(0.35)
        pdf.rect(x0, grid_y, cols_n * dw, n_rows * row_h, style="D")

    # Week-number gutter (rotated) + day numerals + week links
    for r, week in enumerate(weeks):
        wy = grid_y + r * row_h
        wi = None
        if week_link_map:
            for d in week:
                if d and d in week_link_map:
                    wi = week_link_map[d]
                    break
        pdf.set_font(theme.body, "B", 5.5)
        pdf.set_text_color(*theme.rgb("text_light"))
        wk_label = f"WEEK {wi + 1 if wi is not None else r + 1}"
        cx = lb.x + 3.4
        cy = wy + row_h / 2
        tw = pdf.get_string_width(wk_label)
        with pdf.rotation(angle=90, x=cx, y=cy):
            pdf.set_xy(cx - tw / 2, cy - 2)
            pdf.cell(tw + 0.5, 4, wk_label, align="C")

        link_id = (nav.get_link(NavigationManager.week_key(wi))
                   if wi is not None else None)
        theme.set_type(pdf, "calendar_digit")
        pdf.set_text_color(*theme.rgb("text"))
        for c, day in enumerate(week):
            if day:
                pdf.set_xy(col_x(c) + 1.6, wy + 1.2)
                pdf.cell(8, 4.5, str(day))
            if link_id is not None:
                pdf.link(col_x(c), wy, col_w(c), row_h, link_id)
    _plain_reset(pdf, theme)

    # Sidebar quick links.  The shell's corner button already targets one
    # of these pages (recorded on ctx by render_back_link) -- skip it so
    # two identical buttons never stack on the same card edge.
    sx = rb.x + rb.w - sidebar_w
    sy = lb.y
    buttons: list[tuple[str, str]] = []
    if nav.has_link(NavigationManager.monthly_plan_key(month)):
        buttons.append(("Monthly Plan",
                        NavigationManager.monthly_plan_key(month)))
    if nav.has_link(NavigationManager.monthly_review_key(month)):
        buttons.append(("Monthly Review",
                        NavigationManager.monthly_review_key(month)))
    niche_tabs = [(lbl, key) for lbl, key in ctx.tabs
                  if key.startswith("niche_")][:2]
    buttons.extend(niche_tabs)
    buttons = [(lbl, key) for lbl, key in buttons
               if key != ctx.corner_action_key]
    for label, key in buttons:
        outline_button(pdf, theme, sx, sy, sidebar_w, 8.5, label,
                       link=nav.get_link(key))
        sy += 12.5
    ny = section_label(pdf, theme, sx, sy + 2, "Notes")
    ruled_lines(pdf, theme, Panel(sx, ny, sidebar_w, lb.y2 - ny), spacing=8)
    pdf.set_text_color(0, 0, 0)


def _monthly_airy(pdf: FPDF, ctx: PageContext, month: int,
                  week_link_map: dict[int, int] | None) -> None:
    """I4: borderless monthly -- hairlines between weeks only."""
    theme = ctx.theme
    nav = ctx.nav
    lb = ctx.geo.left_body()
    rb = ctx.geo.right_body()

    # Weekday header: letter-spaced small caps + one rule
    hx, hy, cell_w, row_h = ctx.geo.weekday_header_metrics()
    pdf.set_text_color(*blend(theme.rgb("text"), theme.rgb("primary"), 0.35))
    theme.set_type(pdf, "band_label")
    try:
        pdf.set_char_spacing(1.2)
    except Exception:
        pass
    for i, label in enumerate(WEEKDAY_LABELS):
        pdf.set_xy(hx + i * cell_w, hy)
        pdf.cell(cell_w, row_h - 2, label, align="C")
    try:
        pdf.set_char_spacing(0)
    except Exception:
        pass
    pdf.set_draw_color(*theme.structural())
    pdf.set_line_width(0.4)
    pdf.line(hx, hy + row_h - 1, hx + cell_w * 7, hy + row_h - 1)

    grid = ctx.geo.calendar_grid()
    month_cal = _cal.monthcalendar(ctx.year, month)
    # Hairlines between week rows only
    pdf.set_draw_color(*theme.rule_c())
    pdf.set_line_width(0.2)
    for r in range(1, len(month_cal)):
        y = grid.y + r * grid.cell_h
        pdf.line(grid.x, y, grid.x + grid.width, y)

    pdf.set_font(theme.body, "I", 9)   # Inter Light
    pdf.set_text_color(*theme.rgb("text"))
    for row_idx, week in enumerate(month_cal):
        for col_idx, day in enumerate(week):
            if day == 0:
                continue
            cx, cy = grid.cell_xy(col_idx, row_idx)
            pdf.set_xy(cx, cy + grid.cell_h / 2 - 2.5)
            link_id = None
            if week_link_map and day in week_link_map:
                link_id = nav.get_link(
                    NavigationManager.week_key(week_link_map[day]))
            pdf.cell(grid.cell_w, 5, str(day), align="C")
            if link_id is not None:
                pdf.link(cx, cy, grid.cell_w, grid.cell_h, link_id)

    # Right rail: priorities + notes
    secs = rb.split_v([0.30, 0.70], gap=6)
    y = section_label(pdf, theme, secs[0].x, secs[0].y, "Top Priorities")
    priority_rows(pdf, theme, ctx.motif,
                  Panel(secs[0].x, y, secs[0].w, secs[0].y2 - y))
    y = section_label(pdf, theme, secs[1].x, secs[1].y, "Notes",
                      underline_w=secs[1].w)
    fill_texture(pdf, theme, Panel(secs[1].x, y + 1, secs[1].w,
                                   secs[1].y2 - y - 2), kind="notes")
    pdf.set_text_color(0, 0, 0)


MONTHLY_VARIANTS = {
    "boxed": _monthly_boxed,
    "columns": _monthly_columns,
    "hourly": _monthly_boxed,     # I3 keeps the boxed monthly
    "airy": _monthly_airy,
}


def _plain_reset(pdf: FPDF, theme: Theme) -> None:
    try:
        pdf.set_char_spacing(0)
    except Exception:
        pass
    pdf.set_text_color(*theme.rgb("text"))


class MonthlyPage:
    """Monthly calendar spread; body dispatches on design.interior."""

    @staticmethod
    def render(
        pdf: FPDF,
        ctx: PageContext,
        month: int,
        week_link_map: dict[int, int] | None = None,
    ) -> None:
        begin_content_page(
            pdf, ctx,
            bind_key=NavigationManager.month_key(month),
            bookmark=_cal.month_name[month],
            active_tab="CALENDAR",
            current_month=month,
        )
        page_header(pdf, ctx, "MONTHLY", "CALENDAR", month=month)
        render_back_link(pdf, ctx, NavigationManager.monthly_plan_key(month),
                         "Monthly Plan")
        MONTHLY_VARIANTS[ctx.design.interior](pdf, ctx, month, week_link_map)


# ===================================================================
# 5. MonthlyPlanPage
# ===================================================================

class MonthlyPlanPage:
    """Modeled on the reference: month-at-a-glance list + focus/priorities."""

    @staticmethod
    def render(pdf: FPDF, ctx: PageContext, month: int) -> None:
        theme = ctx.theme
        begin_content_page(
            pdf, ctx,
            bind_key=NavigationManager.monthly_plan_key(month),
            bookmark=f"{_cal.month_name[month]} Plan",
            bookmark_level=1,
            active_tab="CALENDAR",
            current_month=month,
        )
        page_header(pdf, ctx, "MONTHLY", "PLAN", month=month)
        render_back_link(pdf, ctx, NavigationManager.month_key(month),
                         "Back to Month")

        # ---- LEFT: month at a glance (numbered day lines, 2 columns) -------
        lb = ctx.geo.left_body()
        y = section_label(pdf, theme, lb.x, lb.y, "Month at a Glance",
                          underline_w=None)
        glance = Panel(lb.x, y + 1, lb.w, lb.y2 - y - 1)
        border = theme.border_c()
        pdf.set_draw_color(*border)
        pdf.set_line_width(0.3)
        pdf.rect(glance.x, glance.y, glance.w, glance.h, style="D")
        n_days = _cal.monthrange(ctx.year, month)[1]
        rows = 16
        row_h = glance.h / rows
        col_w = glance.w / 2
        theme.set_type(pdf, "inline_label")
        gr = theme.rule_c()
        for d in range(1, 33):
            if d > n_days and d != 32:
                continue
            if d > n_days:
                break
            col = 0 if d <= rows else 1
            row = (d - 1) % rows
            x = glance.x + col * col_w
            cy = glance.y + row * row_h
            pdf.set_text_color(*theme.rgb("text_light"))
            pdf.set_xy(x + 2.5, cy)
            pdf.cell(8, row_h, str(d), align="L")
            pdf.set_draw_color(*gr)
            pdf.set_line_width(0.25)
            pdf.line(x + 11, cy + row_h * 0.72, x + col_w - 4, cy + row_h * 0.72)
            if row > 0:
                pdf.line(x, cy, x + col_w, cy)
        pdf.set_draw_color(*border)
        pdf.line(glance.x + col_w, glance.y, glance.x + col_w, glance.y2)

        # ---- RIGHT: focus / priorities / todo | in progress / deadlines ----
        rb = ctx.geo.right_body()
        cols = rb.cols(2, gap=8)

        left_col = cols[0].split_v([0.30, 0.17, 0.53], gap=5)
        labelled_box(pdf, theme, left_col[0], "Main Focus for this Month",
                     fill=True)
        y = section_label(pdf, theme, left_col[1].x, left_col[1].y,
                          "Top Priorities")
        _numbered_priority_lines(pdf, theme,
                                 Panel(left_col[1].x, y, left_col[1].w,
                                       left_col[1].y2 - y), n=3, size=7.5)
        y2 = section_label(pdf, theme, left_col[2].x, left_col[2].y,
                           "To Do & Errands")
        checkbox_lines(pdf, theme,
                       Panel(left_col[2].x, y2, left_col[2].w,
                             left_col[2].y2 - y2), spacing=8.6)

        right_col = cols[1].split_v([0.62, 0.38], gap=5)
        y = section_label(pdf, theme, right_col[0].x, right_col[0].y,
                          "In Progress")
        sub_h = (right_col[0].y2 - y - 6) / 3
        band = theme.band_fill()
        for i, name in enumerate(("Personal", "Professional", "Other")):
            sy = y + i * (sub_h + 3)
            pdf.set_text_color(*theme.band_text_c())
            theme.set_type(pdf, "inline_label")
            pw = pdf.get_string_width(theme.case("inline_label", name)) + 8
            if band is not None:
                pdf.set_fill_color(*band)
                pdf.rect(right_col[0].x, sy, pw, 5.5, style="F",
                         round_corners=True, corner_radius=1.2)
            else:
                pdf.set_draw_color(*theme.border_c())
                pdf.set_line_width(0.3)
                pdf.rect(right_col[0].x, sy, pw, 5.5, style="D",
                         round_corners=True, corner_radius=1.2)
            pdf.set_xy(right_col[0].x, sy)
            pdf.cell(pw, 5.5, theme.case("inline_label", name), align="C")
            _plain_reset(pdf, theme)
            ruled_lines(pdf, theme,
                        Panel(right_col[0].x, sy + 6, right_col[0].w, sub_h - 7),
                        spacing=7.5, start_offset=6)
        y = section_label(pdf, theme, right_col[1].x, right_col[1].y,
                          "Deadlines / Important Dates", underline_w=right_col[1].w)
        dl = Panel(right_col[1].x, y + 1, right_col[1].w, right_col[1].y2 - y - 1)
        n = int(dl.h / 9)
        for i in range(n):
            ly = dl.y + 6 + i * 9
            pdf.set_draw_color(*border)
            pdf.line(dl.x, ly, dl.x + 22, ly)
            pdf.set_draw_color(*gr)
            pdf.line(dl.x + 27, ly, dl.x2, ly)

        pdf.set_text_color(0, 0, 0)


# ===================================================================
# 6. MonthlyReviewPage
# ===================================================================

class MonthlyReviewPage:
    """Reflection spread: rating, wins, lessons, next-month focus."""

    @staticmethod
    def render(pdf: FPDF, ctx: PageContext, month: int) -> None:
        theme = ctx.theme
        begin_content_page(
            pdf, ctx,
            bind_key=NavigationManager.monthly_review_key(month),
            bookmark=f"{_cal.month_name[month]} Review",
            bookmark_level=1,
            active_tab="CALENDAR",
            current_month=month,
        )
        page_header(pdf, ctx, "MONTHLY", "REVIEW", month=month)
        render_back_link(pdf, ctx, NavigationManager.month_key(month),
                         "Back to Month")

        lb = ctx.geo.left_body()
        rb = ctx.geo.right_body()
        border = theme.border_c()

        # ---- LEFT: rating + went well / didn't go well ----------------------
        rate = Panel(lb.x, lb.y, lb.w, 18)
        pdf.set_draw_color(*border)
        pdf.set_line_width(0.35)
        pdf.rect(rate.x, rate.y, rate.w, rate.h, style="D",
                 round_corners=True, corner_radius=2)
        theme.set_type(pdf, "inline_label", size=7.5)
        pdf.set_text_color(*blend(theme.rgb("text"), theme.rgb("primary"), 0.3))
        pdf.set_xy(rate.x + 4, rate.y)
        pdf.cell(rate.w * 0.55, rate.h, "HOW WOULD YOU RATE THIS MONTH?",
                 align="L")
        _plain_reset(pdf, theme)
        soft = theme.box_fill() or WHITE
        for i in range(5):
            cx = rate.x + rate.w * 0.60 + i * 15
            cy = rate.y + rate.h / 2
            pdf.set_fill_color(*soft)
            pdf.ellipse(cx - 4.6, cy - 4.6, 9.2, 9.2, style="F")
            pdf.set_text_color(*blend(theme.rgb("text"), theme.rgb("primary"), 0.3))
            pdf.set_font(theme.body, "B", 8.5)
            pdf.set_xy(cx - 4.6, cy - 4.6)
            pdf.cell(9.2, 9.2, str(i + 1), align="C")

        remaining = Panel(lb.x, rate.y2 + 7, lb.w, lb.y2 - rate.y2 - 7)
        halves = remaining.rows(2, gap=7)
        y = section_label(pdf, theme, halves[0].x, halves[0].y,
                          "What Went Well This Month", underline_w=halves[0].w)
        ruled_lines(pdf, theme, Panel(halves[0].x, y, halves[0].w,
                                      halves[0].y2 - y), spacing=9)
        y = section_label(pdf, theme, halves[1].x, halves[1].y,
                          "What Didn't Go So Well", underline_w=halves[1].w)
        ruled_lines(pdf, theme, Panel(halves[1].x, y, halves[1].w,
                                      halves[1].y2 - y), spacing=9)

        # ---- RIGHT: wins / favorite moments / improve / doodles -------------
        secs = rb.split_v([0.27, 0.27, 0.26, 0.20], gap=6)
        for panel, label in zip(
            secs[:3],
            ("Biggest Wins This Month", "Most Favorite Moments",
             "How Can I Improve Next Month"),
        ):
            y = section_label(pdf, theme, panel.x, panel.y, label,
                              underline_w=panel.w)
            ruled_lines(pdf, theme, Panel(panel.x, y, panel.w, panel.y2 - y),
                        spacing=9)
        y = section_label(pdf, theme, secs[3].x, secs[3].y, "Notes & Doodles")
        fill_texture(pdf, theme,
                     Panel(secs[3].x, y, secs[3].w, secs[3].y2 - y - 1),
                     kind="notes")

        pdf.set_text_color(0, 0, 0)


# ===================================================================
# 7. WeeklyPage (body dispatches on design.interior)
# ===================================================================

def _weekly_boxed(pdf: FPDF, ctx: PageContext, week_index: int,
                  start_date: date) -> None:
    """I1: 7 labelled day cells + extras cell (classic-exact)."""
    theme = ctx.theme
    lb = ctx.geo.left_body()
    rb = ctx.geo.right_body()

    def day_box(panel: Panel, d: date) -> None:
        label = f"{d.strftime('%A').upper()}  ·  {d.day}"
        labelled_box(pdf, theme, panel, label, lines_spacing=8.2)

    # Day boxes read chronologically across the whole spread:
    #   top row     Sun Mon | Tue Wed
    #   bottom row  Thu Fri | Sat + extras
    cells = [c for row in lb.rows(2, gap=6) for c in row.cols(2, gap=6)]
    rcells = [c for row in rb.rows(2, gap=6) for c in row.cols(2, gap=6)]
    day_cells = [cells[0], cells[1], rcells[0], rcells[1],
                 cells[2], cells[3], rcells[2]]
    for i, cell in enumerate(day_cells):
        day_box(cell, start_date + timedelta(days=i))

    extras = rcells[3].split_v([0.34, 0.38, 0.28], gap=4)

    # Top priorities
    y = section_label(pdf, theme, extras[0].x, extras[0].y, "Top Priorities")
    gr = theme.rule_c()
    for i in range(3):
        ly = y + 4 + i * ((extras[0].y2 - y - 3) / 3)
        pdf.set_text_color(*theme.rgb("text_light"))
        theme.set_type(pdf, "inline_label", size=7)
        pdf.set_xy(extras[0].x + 1, ly - 3)
        pdf.cell(5, 4, f"{i + 1}.", align="L")
        pdf.set_draw_color(*gr)
        pdf.line(extras[0].x + 7, ly + 1, extras[0].x2, ly + 1)
    _plain_reset(pdf, theme)

    # Habits mini-grid
    y = section_label(pdf, theme, extras[1].x, extras[1].y, "Habits")
    _habit_mini_grid(pdf, ctx, Panel(extras[1].x, y, extras[1].w,
                                     extras[1].y2 - y - 1))

    # Next week preview
    y = section_label(pdf, theme, extras[2].x, extras[2].y, "Next Week")
    ruled_lines(pdf, theme, Panel(extras[2].x, y, extras[2].w,
                                  extras[2].y2 - y), spacing=7)
    pdf.set_text_color(0, 0, 0)


def _weekly_columns(pdf: FPDF, ctx: PageContext, week_index: int,
                    start_date: date) -> None:
    """I2: 4 full-height columns per panel, Sun..Sat + extras column."""
    theme = ctx.theme
    lb = ctx.geo.left_body()
    rb = ctx.geo.right_body()
    band_h = 9.0

    def day_column(panel: Panel, d: date) -> None:
        label = f"{d.strftime('%a').upper()} · {d.day}"
        if theme.container == "open_air":
            pdf.set_text_color(*theme.label_c())
            theme.set_type(pdf, "band_label", size=7.5)
            pdf.set_xy(panel.x, panel.y + 1.5)
            pdf.cell(panel.w, band_h - 3, theme.case("band_label", label),
                     align="C")
            _plain_reset(pdf, theme)
            pdf.set_draw_color(*theme.structural())
            pdf.set_line_width(0.3)
            pdf.line(panel.x, panel.y + band_h - 1, panel.x2,
                     panel.y + band_h - 1)
        else:
            band = theme.band_fill()
            square = theme.container == "squared_hairline"
            pdf.set_draw_color(*theme.border_c())
            pdf.set_line_width(theme.border_w())
            if band is not None:
                pdf.set_fill_color(*band)
                if square:
                    pdf.rect(panel.x, panel.y, panel.w, band_h, style="FD")
                else:
                    pdf.rect(panel.x, panel.y, panel.w, band_h, style="FD",
                             round_corners=("TOP_LEFT", "TOP_RIGHT"),
                             corner_radius=1.8)
            else:
                pdf.rect(panel.x, panel.y, panel.w, band_h, style="D")
            pdf.set_text_color(*theme.band_text_c())
            theme.set_type(pdf, "band_label", size=7.5)
            pdf.set_xy(panel.x, panel.y)
            pdf.cell(panel.w, band_h, theme.case("band_label", label),
                     align="C")
            _plain_reset(pdf, theme)
        fill_texture(pdf, theme,
                     Panel(panel.x, panel.y + band_h + 2, panel.w,
                           panel.h - band_h - 2), kind="day", spacing=8.0)

    lcols = lb.cols(4, gap=5)
    rcols = rb.cols(4, gap=5)
    for i in range(4):
        day_column(lcols[i], start_date + timedelta(days=i))
    for i in range(3):
        day_column(rcols[i], start_date + timedelta(days=4 + i))

    # Column 8: extras
    extras = rcols[3].split_v([0.25, 0.30, 0.45], gap=4)
    y = section_label(pdf, theme, extras[0].x, extras[0].y, "Priorities",
                      size=7)
    priority_rows(pdf, theme, ctx.motif,
                  Panel(extras[0].x, y, extras[0].w, extras[0].y2 - y))
    y = section_label(pdf, theme, extras[1].x, extras[1].y, "Habits", size=7)
    _habit_mini_grid(pdf, ctx, Panel(extras[1].x, y + 1, extras[1].w,
                                     extras[1].y2 - y - 2))
    y = section_label(pdf, theme, extras[2].x, extras[2].y, "Notes", size=7)
    fill_texture(pdf, theme, Panel(extras[2].x, y, extras[2].w,
                                   extras[2].y2 - y), kind="notes")
    pdf.set_text_color(0, 0, 0)


def _weekly_hourly(pdf: FPDF, ctx: PageContext, week_index: int,
                   start_date: date) -> None:
    """I3: timeline rows, 6 AM - 10 PM hour ruler per day."""
    theme = ctx.theme
    lb = ctx.geo.left_body()
    rb = ctx.geo.right_body()
    block_w = 26.0

    def hourly_row(panel: Panel, d: date, labels: bool) -> None:
        # Day block
        pdf.set_text_color(*blend(theme.rgb("text"), theme.rgb("primary"), 0.2))
        pdf.set_font(theme.display, "B", 16)
        pdf.set_xy(panel.x + 2, panel.y + 2)
        pdf.cell(20, 8, str(d.day), align="L")
        pdf.set_font(theme.body, "B", 6.5)
        pdf.set_text_color(*theme.rgb("text_light"))
        name = d.strftime("%a").upper()
        try:
            # Weekday labels are searchable: keep tracking in budget.
            pdf.set_char_spacing(searchable_tracking(6.5, 0.8))
        except Exception:
            pass
        tw = pdf.get_string_width(name)
        cx = panel.x + 3.2
        cy = panel.y + panel.h / 2 + 4
        with pdf.rotation(angle=90, x=cx, y=cy):
            pdf.set_xy(cx - tw / 2, cy - 2)
            pdf.cell(tw + 1, 4, name, align="C")
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass

        # Hour ruler: 17 ticks, 6 AM .. 10 PM
        rx = panel.x + block_w
        spacing = (panel.w - block_w) / 16.0
        pdf.set_draw_color(*theme.rule_c())
        pdf.set_line_width(0.2)
        for i in range(17):
            tx = rx + i * spacing
            pdf.line(tx, panel.y + 8, tx, panel.y2)
        if labels:
            hour_labels = ["6", "8", "10", "12", "2", "4", "6", "8", "10"]
            theme.set_type(pdf, "mini_digit", size=5)
            pdf.set_text_color(*theme.rgb("text_light"))
            for i, hl in enumerate(hour_labels):
                tx = rx + (i * 2) * spacing
                pdf.set_xy(tx - 4, panel.y + 2.5)
                pdf.cell(8, 3.5, hl, align="C")
            _plain_reset(pdf, theme)
        # Baseline under the row
        pdf.set_draw_color(*theme.border_c())
        pdf.set_line_width(0.35)
        pdf.line(panel.x, panel.y2, panel.x2, panel.y2)

    lrows = lb.rows(4, gap=4)
    rrows = rb.rows(4, gap=4)
    for i in range(4):
        hourly_row(lrows[i], start_date + timedelta(days=i), labels=i == 0)
    for i in range(3):
        hourly_row(rrows[i], start_date + timedelta(days=4 + i), labels=i == 0)

    # Extras row
    extras = rrows[3].split_h([0.34, 0.38, 0.28], gap=4)
    y = section_label(pdf, theme, extras[0].x, extras[0].y, "Priorities",
                      size=7)
    priority_rows(pdf, theme, ctx.motif,
                  Panel(extras[0].x, y, extras[0].w, extras[0].y2 - y - 2))
    y = section_label(pdf, theme, extras[1].x, extras[1].y, "Habits", size=7)
    _habit_mini_grid(pdf, ctx, Panel(extras[1].x, y + 1, extras[1].w,
                                     extras[1].y2 - y - 3))
    y = section_label(pdf, theme, extras[2].x, extras[2].y, "Next Week",
                      size=7)
    ruled_lines(pdf, theme, Panel(extras[2].x, y, extras[2].w,
                                  extras[2].y2 - y - 2), spacing=7)
    pdf.set_text_color(0, 0, 0)


def _weekly_airy(pdf: FPDF, ctx: PageContext, week_index: int,
                 start_date: date) -> None:
    """I4: zero boxes -- ledger rows with a rule per day."""
    theme = ctx.theme
    lb = ctx.geo.left_body()
    rb = ctx.geo.right_body()

    def day_section(panel: Panel, d: date) -> None:
        rule_y = panel.y + 8
        pdf.set_text_color(*blend(theme.rgb("text"), theme.rgb("primary"), 0.3))
        theme.set_type(pdf, "band_label", size=8)
        pdf.set_xy(panel.x + 0.5, rule_y - 6.5)
        pdf.cell(panel.w * 0.6, 6, theme.case("band_label", d.strftime("%A")),
                 align="L")
        _plain_reset(pdf, theme)
        pdf.set_font(theme.display, "", 13)
        pdf.set_text_color(*blend(theme.rgb("text"), theme.rgb("primary"), 0.15))
        pdf.set_xy(panel.x2 - 20, rule_y - 7.5)
        pdf.cell(20, 7, str(d.day), align="R")
        pdf.set_draw_color(*theme.structural())
        pdf.set_line_width(0.4)
        pdf.line(panel.x, rule_y, panel.x2, rule_y)
        fill_texture(pdf, theme,
                     Panel(panel.x, rule_y + 1, panel.w,
                           panel.y2 - rule_y - 2),
                     kind="day", spacing=9.0, inset=4)

    lrows = lb.rows(4, gap=6)
    rrows = rb.rows(4, gap=6)
    for i in range(4):
        day_section(lrows[i], start_date + timedelta(days=i))
    for i in range(3):
        day_section(rrows[i], start_date + timedelta(days=4 + i))

    # Summary section
    summary = rrows[3]
    top = Panel(summary.x, summary.y, summary.w, summary.h * 0.4)
    checkbox_lines(pdf, theme, top, spacing=8.0)
    bottom = Panel(summary.x, summary.y + summary.h * 0.44, summary.w,
                   summary.h * 0.56)
    table(pdf, theme, bottom, [("To-Do", 0.5), ("Notes", 0.5)], n_rows=4)
    pdf.set_text_color(0, 0, 0)


WEEKLY_VARIANTS = {
    "boxed": _weekly_boxed,
    "columns": _weekly_columns,
    "hourly": _weekly_hourly,
    "airy": _weekly_airy,
}


class WeeklyPage:
    """Two-page week spread; body dispatches on design.interior."""

    @staticmethod
    def render(
        pdf: FPDF,
        ctx: PageContext,
        week_index: int,
        start_date: date,
    ) -> None:
        end_date = start_date + timedelta(days=6)
        month = start_date.month if start_date.year == ctx.year else 1
        header = f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d')}"

        begin_content_page(
            pdf, ctx,
            bind_key=NavigationManager.week_key(week_index),
            bookmark=header,
            bookmark_level=1,
            active_tab="WEEKLY",
            current_month=month,
        )
        page_header(pdf, ctx, "WEEKLY", "PLAN", month=month, subtitle=header)
        render_back_link(pdf, ctx, NavigationManager.month_key(month),
                         "Back to Month")
        WEEKLY_VARIANTS[ctx.design.interior](pdf, ctx, week_index, start_date)


# ===================================================================
# 8. DailyPage (shared across interiors)
# ===================================================================

class DailyPage:
    """Rich daily page: schedule, focus, tasks | reviews, meals, trackers."""

    @staticmethod
    def render(pdf: FPDF, ctx: PageContext, day_date: date, month: int) -> None:
        theme = ctx.theme
        begin_content_page(
            pdf, ctx,
            bind_key=NavigationManager.daily_key(day_date.month, day_date.day),
            bookmark=day_date.strftime("%b %d"),
            bookmark_level=2,
            active_tab="WEEKLY",
            current_month=month,
        )
        page_header(pdf, ctx, str(day_date.day),
                    day_date.strftime("%A").upper(), month=month)
        render_back_link(pdf, ctx, NavigationManager.month_key(month),
                         "Back to Month")

        gr = theme.rule_c()
        lb = ctx.geo.left_body()
        lcols = lb.cols(2, gap=8)
        lcols[0] = Panel(lb.x, lb.y, lb.w * 0.42, lb.h)
        lcols[1] = Panel(lb.x + lb.w * 0.42 + 8, lb.y, lb.w * 0.58 - 8, lb.h)

        # ---- Schedule 6 AM - 10 PM ------------------------------------------
        y = section_label(pdf, theme, lcols[0].x, lcols[0].y, "Schedule")
        sched = Panel(lcols[0].x, y, lcols[0].w, lcols[0].y2 - y)
        hours = list(range(6, 23))  # 6 AM .. 10 PM
        row_h = sched.h / len(hours)
        pdf.set_line_width(0.25)
        for i, hour in enumerate(hours):
            hy = sched.y + i * row_h
            h12 = hour if hour <= 12 else hour - 12
            ampm = "AM" if hour < 12 else "PM"
            label = "NOON" if hour == 12 else f"{h12} {ampm}"
            theme.set_type(pdf, "mini_digit", size=6)
            pdf.set_text_color(*theme.rgb("text_light"))
            pdf.set_xy(sched.x, hy)
            pdf.cell(12, row_h, label, align="L")
            pdf.set_draw_color(*gr)
            pdf.line(sched.x + 13, hy + row_h, sched.x2, hy + row_h)
        _plain_reset(pdf, theme)
        pdf.set_draw_color(*theme.border_c())
        pdf.line(sched.x + 13, sched.y, sched.x2, sched.y)

        # ---- Focus / top three / tasks ---------------------------------------
        col = lcols[1].split_v([0.20, 0.22, 0.44, 0.14], gap=5)
        y = section_label(pdf, theme, col[0].x, col[0].y, "Main Focus for Today")
        soft = theme.box_fill()
        if soft is not None:
            pdf.set_fill_color(*soft)
            pdf.rect(col[0].x, y, col[0].w, col[0].y2 - y, style="F",
                     round_corners=True, corner_radius=1.6)
        else:
            pdf.set_draw_color(*theme.border_c())
            pdf.set_line_width(0.3)
            pdf.rect(col[0].x, y, col[0].w, col[0].y2 - y, style="D",
                     round_corners=True, corner_radius=1.6)

        y = section_label(pdf, theme, col[1].x, col[1].y, "Top Three")
        for i in range(3):
            ly = y + 3 + i * ((col[1].y2 - y - 2) / 3)
            ctx.motif.bullet(pdf, theme, col[1].x + 0.5, ly - 2, 4.2,
                             number=i + 1)
            pdf.set_draw_color(*gr)
            pdf.rect(col[1].x + 7.5, ly - 2.2, col[1].w - 8, 4.8, style="D",
                     round_corners=True, corner_radius=1.2)
        pdf.set_text_color(*theme.rgb("text"))

        y = section_label(pdf, theme, col[2].x, col[2].y, "Tasks")
        checkbox_lines(pdf, theme, Panel(col[2].x, y, col[2].w, col[2].y2 - y),
                       spacing=8.0)

        y = section_label(pdf, theme, col[3].x, col[3].y, "Moved to Another Day")
        if soft is not None:
            pdf.set_fill_color(*soft)
            pdf.rect(col[3].x, y, col[3].w, col[3].y2 - y, style="F",
                     round_corners=True, corner_radius=1.6)
        else:
            pdf.set_draw_color(*theme.border_c())
            pdf.set_line_width(0.3)
            pdf.rect(col[3].x, y, col[3].w, col[3].y2 - y, style="D",
                     round_corners=True, corner_radius=1.6)

        # ---- RIGHT: reviews column + trackers column -------------------------
        rb = ctx.geo.right_body()
        rcols = rb.cols(2, gap=8)

        rc = rcols[0].split_v([0.14, 0.06, 0.245, 0.06, 0.245, 0.10, 0.09], gap=3)
        # Affirmation
        y = section_label(pdf, theme, rc[0].x, rc[0].y, "Affirmation")
        if soft is not None:
            pdf.set_fill_color(*soft)
            pdf.rect(rc[0].x, y, rc[0].w, rc[0].y2 - y, style="F",
                     round_corners=True, corner_radius=1.6)
        else:
            ruled_lines(pdf, theme, Panel(rc[0].x, y, rc[0].w, rc[0].y2 - y),
                        spacing=7)

        def band(panel: Panel, text: str) -> None:
            pdf.set_fill_color(*blend(theme.structural(), WHITE, 0.12))
            pdf.rect(panel.x + panel.w * 0.12, panel.y + 1,
                     panel.w * 0.76, panel.h - 2, style="F",
                     round_corners=True, corner_radius=1.2)
            pdf.set_text_color(*WHITE)
            pdf.set_font(theme.body, "B", 7)
            try:
                pdf.set_char_spacing(0.5)
            except Exception:
                pass
            pdf.set_xy(panel.x + panel.w * 0.12, panel.y + 1)
            pdf.cell(panel.w * 0.76, panel.h - 2, text.upper(), align="C")
            try:
                pdf.set_char_spacing(0)
            except Exception:
                pass

        band(rc[1], "Morning Review")
        prompts = rc[2].rows(2, gap=2)
        for panel, label in zip(prompts, ("What I Am Excited About",
                                          "What I Am Grateful For")):
            y = section_label(pdf, theme, panel.x, panel.y, label, size=7)
            ruled_lines(pdf, theme, Panel(panel.x, y - 1, panel.w,
                                          panel.y2 - y + 1), spacing=6.8)
        band(rc[3], "Evening Review")
        prompts = rc[4].rows(2, gap=2)
        for panel, label in zip(prompts, ("What Went Well Today",
                                          "What Can I Improve Tomorrow")):
            y = section_label(pdf, theme, panel.x, panel.y, label, size=7)
            ruled_lines(pdf, theme, Panel(panel.x, y - 1, panel.w,
                                          panel.y2 - y + 1), spacing=6.8)

        # Sleep row
        y = section_label(pdf, theme, rc[5].x, rc[5].y, "Sleep", size=7)
        pdf.set_font(theme.body, "", 7)
        pdf.set_text_color(*theme.rgb("text_light"))
        half = rc[5].w / 2
        for i, lbl in enumerate(("Woke up at", "Slept at")):
            pdf.set_xy(rc[5].x + i * half, y + 1)
            pdf.cell(18, 4, lbl, align="L")
            pdf.set_draw_color(*gr)
            pdf.line(rc[5].x + i * half + 19, y + 5, rc[5].x + (i + 1) * half - 4,
                     y + 5)
        # Water intake row
        y = section_label(pdf, theme, rc[6].x, rc[6].y, "Water Intake", size=7)
        water_droplets(pdf, theme, rc[6].x + 4, y + 2, n=8, gap=7.5)

        # Trackers column
        tc = rcols[1].split_v([0.42, 0.09, 0.49], gap=4)
        y = section_label(pdf, theme, tc[0].x, tc[0].y, "Meal Log")
        meals = Panel(tc[0].x, y, tc[0].w, tc[0].y2 - y).rows(4, gap=2.5)
        for panel, label in zip(meals, ("Breakfast", "Lunch", "Dinner", "Snacks")):
            pdf.set_draw_color(*blend(gr, theme.structural(), 0.3))
            pdf.set_line_width(0.28)
            pdf.rect(panel.x, panel.y, panel.w, panel.h, style="D",
                     round_corners=True, corner_radius=1.4)
            theme.set_type(pdf, "inline_label", size=6)
            pdf.set_text_color(*theme.rgb("text_light"))
            pdf.set_xy(panel.x + 2, panel.y + 0.6)
            pdf.cell(24, 3, label.upper(), align="L")
        _plain_reset(pdf, theme)

        y = section_label(pdf, theme, tc[1].x, tc[1].y, "Mood", size=7)
        mood_faces(pdf, theme, tc[1].x + 7, y, n=5, gap=9)

        y = section_label(pdf, theme, tc[2].x, tc[2].y, "Notes & Doodles")
        fill_texture(pdf, theme, Panel(tc[2].x, y, tc[2].w, tc[2].y2 - y - 1),
                     kind="notes")

        pdf.set_text_color(0, 0, 0)


# ===================================================================
# 9. NotesPage
# ===================================================================

class NotesPage:
    """Notes spread: texture-driven free-writing panels."""

    @staticmethod
    def render(pdf: FPDF, ctx: PageContext, page_label: str = "Notes") -> None:
        theme = ctx.theme
        begin_content_page(
            pdf, ctx,
            bind_key=NavigationManager.notes_key() if page_label == "Notes" else None,
            bookmark=page_label,
            active_tab="NOTES",
        )
        page_header(pdf, ctx, "NOTES &", "IDEAS")
        render_back_link(pdf, ctx, NavigationManager.index_key(),
                         "Back to Index")

        lb = ctx.geo.left_body()
        rb = ctx.geo.right_body()
        fill_texture(pdf, theme, lb.inset(1.5), kind="notes")
        fill_texture(pdf, theme, rb, kind="day", spacing=9, start_offset=6)
        pdf.set_text_color(0, 0, 0)


# ===================================================================
# 10. HabitTrackerPage
# ===================================================================

class HabitTrackerPage:
    """Two blank month grids (write-in month), 31 day columns each."""

    @staticmethod
    def render(pdf: FPDF, ctx: PageContext) -> None:
        begin_content_page(
            pdf, ctx,
            bind_key=NavigationManager.habits_key(),
            bookmark="Habit Tracker",
            active_tab="HABITS",
        )
        page_header(pdf, ctx, "HABIT", "TRACKER")
        render_back_link(pdf, ctx, NavigationManager.index_key(),
                         "Back to Index")

        for panel in (ctx.geo.left_body(), ctx.geo.right_body()):
            HabitTrackerPage._habit_grid(pdf, ctx, panel)
        pdf.set_text_color(0, 0, 0)

    @staticmethod
    def _habit_grid(pdf: FPDF, ctx: PageContext, panel: Panel) -> None:
        theme = ctx.theme
        gr = theme.rule_c()
        border = theme.border_c()

        # "MONTH ______" write-in line
        theme.set_type(pdf, "inline_label", size=7.5)
        pdf.set_text_color(*theme.rgb("text_light"))
        pdf.set_xy(panel.x, panel.y)
        pdf.cell(16, 5, "MONTH", align="L")
        _plain_reset(pdf, theme)
        pdf.set_draw_color(*border)
        pdf.line(panel.x + 17, panel.y + 4.4, panel.x + 70, panel.y + 4.4)

        grid = Panel(panel.x, panel.y + 8, panel.w, panel.h - 8)
        label_w = 34.0
        n_days, n_rows = 31, 14
        header_h = 6.0
        cell_w = (grid.w - label_w) / n_days
        cell_h = (grid.h - header_h) / n_rows

        band = theme.band_fill()
        if band is not None:
            pdf.set_fill_color(*band)
            pdf.rect(grid.x, grid.y, grid.w, header_h, style="F")
        pdf.set_font(theme.body, "B", 6.5)
        pdf.set_text_color(*theme.band_text_c())
        pdf.set_xy(grid.x, grid.y)
        pdf.cell(label_w, header_h, "HABIT", align="C")
        pdf.set_font(theme.body, "B", 4.6)
        for d in range(n_days):
            pdf.set_xy(grid.x + label_w + d * cell_w, grid.y)
            pdf.cell(cell_w, header_h, str(d + 1), align="C")

        pdf.set_draw_color(*gr)
        pdf.set_line_width(0.2)
        for r in range(n_rows + 1):
            y = grid.y + header_h + r * cell_h
            pdf.line(grid.x, y, grid.x2, y)
        pdf.line(grid.x, grid.y, grid.x, grid.y2)
        pdf.line(grid.x2, grid.y, grid.x2, grid.y2)
        for d in range(n_days + 1):
            x = grid.x + label_w + d * cell_w
            pdf.line(x, grid.y, x, grid.y2)
        pdf.set_draw_color(*border)
        pdf.set_line_width(0.3)
        pdf.rect(grid.x, grid.y, grid.w, grid.h, style="D")


# ===================================================================
# 11. GoalSettingPage
# ===================================================================

class GoalSettingPage:
    """Four goal cards with steps, deadline, and progress bars."""

    @staticmethod
    def render(pdf: FPDF, ctx: PageContext) -> None:
        begin_content_page(
            pdf, ctx,
            bind_key=NavigationManager.goals_key(),
            bookmark="Goals",
            active_tab="GOALS",
        )
        page_header(pdf, ctx, "GOAL", "SETTING")
        render_back_link(pdf, ctx, NavigationManager.index_key(),
                         "Back to Index")

        idx = 1
        for panel in (ctx.geo.left_body(), ctx.geo.right_body()):
            for card in panel.rows(2, gap=8):
                GoalSettingPage._goal_card(pdf, ctx, card, idx)
                idx += 1
        pdf.set_text_color(0, 0, 0)

    @staticmethod
    def _goal_card(pdf: FPDF, ctx: PageContext, card: Panel, num: int) -> None:
        theme = ctx.theme
        gr = theme.rule_c()
        border = theme.border_c()

        pdf.set_fill_color(*WHITE)
        pdf.set_draw_color(*border)
        pdf.set_line_width(0.35)
        pdf.rect(card.x, card.y, card.w, card.h, style="FD",
                 round_corners=True, corner_radius=2.2)

        # Number badge (motif bullet vocabulary at card scale)
        pdf.set_fill_color(*theme.bullet_c())
        pdf.ellipse(card.x + 4, card.y + 4, 9, 9, style="F")
        pdf.set_text_color(*WHITE)
        pdf.set_font(theme.body, "B", 9)
        pdf.set_xy(card.x + 4, card.y + 4)
        pdf.cell(9, 9, str(num), align="C")

        inner = Panel(card.x + 6, card.y + 5, card.w - 12, card.h - 10)

        # Goal line
        theme.set_type(pdf, "inline_label", size=7.5)
        pdf.set_text_color(*theme.rgb("text_light"))
        pdf.set_xy(inner.x + 11, inner.y)
        pdf.cell(14, 6, "GOAL", align="L")
        _plain_reset(pdf, theme)
        pdf.set_draw_color(*gr)
        pdf.line(inner.x + 25, inner.y + 5, inner.x2, inner.y + 5)

        y = section_label(pdf, theme, inner.x, inner.y + 10, "Action Steps",
                          size=7)
        checkbox_lines(pdf, theme, Panel(inner.x, y, inner.w, 26), spacing=8.6)
        y += 30

        theme.set_type(pdf, "inline_label", size=7)
        pdf.set_text_color(*theme.rgb("text_light"))
        pdf.set_xy(inner.x, y)
        pdf.cell(20, 5, "DEADLINE", align="L")
        _plain_reset(pdf, theme)
        pdf.set_draw_color(*gr)
        pdf.line(inner.x + 21, y + 4.2, inner.x + inner.w * 0.45, y + 4.2)

        y = section_label(pdf, theme, inner.x, y + 8, "Progress", size=7)
        progress_bar(pdf, theme, inner.x + 1, y + 0.5, inner.w - 6, h=5.5)
