"""Reusable drawing widgets for planner pages.

Every helper takes the ``Theme`` (palette + fonts + design) and draws with
real fpdf2 primitives.  Widgets dispatch on ``theme.container`` (owned by
the motif) and read all colors through the Theme's ink methods -- with the
default (classic) design every code path below reproduces the pre-design
rendering exactly.
"""

from __future__ import annotations

import logging

from fpdf import FPDF

from src.planner.layout import Panel
from src.planner.styles import (
    BLACK,
    SEARCHABLE_ROLES,
    WHITE,
    ColorPalette,
    Theme,
    blend,
    searchable_tracking,
)

logger = logging.getLogger(__name__)

__all__ = [
    "blend", "WHITE", "BLACK",
    "paper_color", "desk_color", "header_fill", "soft_fill",
    "fit_text", "wrap_text", "fit_role_text",
    "section_label", "duo_title", "page_title",
    "rounded_box", "ruled_lines", "checkbox_lines", "dot_grid", "graph_grid",
    "fill_texture", "table", "labelled_box", "stat_boxes", "progress_bar",
    "water_droplets", "mood_faces", "outline_button", "priority_rows",
]


# ---------------------------------------------------------------------------
# Deprecated palette-only color helpers (kept for compatibility; new code
# should use the Theme ink methods: band_fill/box_fill/border_c/... )
# ---------------------------------------------------------------------------

def paper_color(palette: ColorPalette) -> tuple[int, int, int]:
    """Near-white paper tinted by the palette background."""
    return blend(palette.rgb("background"), WHITE, 0.65)


def desk_color(palette: ColorPalette) -> tuple[int, int, int]:
    """Darker desk tone behind the open binder."""
    return blend(palette.rgb("background"), palette.rgb("secondary"), 0.75)


def header_fill(palette: ColorPalette) -> tuple[int, int, int]:
    """Light tinted fill for table header bands."""
    return blend(paper_color(palette), palette.rgb("primary"), 0.14)


def soft_fill(palette: ColorPalette) -> tuple[int, int, int]:
    """Very light tinted fill for writing boxes."""
    return blend(paper_color(palette), palette.rgb("primary"), 0.08)


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def fit_text(pdf: FPDF, text: str, family: str, style: str,
             max_size: float, max_width: float, min_size: float = 6.0) -> float:
    """Return the largest font size <= max_size at which *text* fits."""
    size = max_size
    while size > min_size:
        pdf.set_font(family, style, size)
        if pdf.get_string_width(text) <= max_width:
            return size
        size -= 0.5
    return min_size


def fit_role_text(pdf: FPDF, theme: Theme, role: str, text: str,
                  max_width: float, min_size: float = 6.0,
                  max_size: float | None = None) -> tuple[str, float]:
    """Case-transform *text* for *role* and find the largest fitting size.

    Sets the role's tracking before measuring (``get_string_width``
    accounts for char spacing).  Returns ``(cased_text, size)`` and leaves
    the font selected at that size.
    """
    spec = theme.role(role)
    cased = theme.case(role, text)
    size = max_size if max_size is not None else spec.size
    tracking = spec.tracking
    if role in SEARCHABLE_ROLES:
        tracking = searchable_tracking(size, tracking)
    try:
        pdf.set_char_spacing(tracking)
    except Exception:
        pass
    fam = theme._family(spec.family)
    while size > min_size:
        pdf.set_font(fam, spec.style, size)
        if pdf.get_string_width(cased) <= max_width:
            return cased, size
        size -= 0.5
    pdf.set_font(fam, spec.style, min_size)
    return cased, min_size


def wrap_text(pdf: FPDF, text: str, family: str, style: str,
              size: float, max_width: float) -> list[str]:
    """Greedy word-wrap of *text* to *max_width* at the given font."""
    pdf.set_font(family, style, size)
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if pdf.get_string_width(trial) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _reset_tracking(pdf: FPDF) -> None:
    try:
        pdf.set_char_spacing(0)
    except Exception:
        pass


def section_label(pdf: FPDF, theme: Theme, x: float, y: float, text: str,
                  w: float | None = None, underline_w: float | None = None,
                  size: float | None = None, align: str = "L") -> float:
    """Small-caps letter-spaced section heading (voice-aware).

    Returns the y coordinate just below the label (content start).
    """
    voice = theme.design.voice
    spec = theme.set_type(pdf, "section_label", size=size)
    size = size if size is not None else spec.size
    tr, tg, tb = blend(theme.rgb("text"), theme.rgb("primary"), 0.35)
    pdf.set_text_color(tr, tg, tb)
    h = size * 0.55
    label = theme.case("section_label", text)
    tx = x

    if voice == "grotesk":
        # Filled square marker instead of an underline
        sq = 3.2
        pdf.set_fill_color(*theme.structural())
        pdf.rect(x, y + (h - sq) / 2, sq, sq, style="F")
        tx = x + 5
    elif voice == "typewriter":
        # Leading "> " in the accent color
        pdf.set_text_color(*theme.rgb("accent"))
        pdf.set_xy(x, y)
        prompt_w = pdf.get_string_width("> ") + 0.5
        pdf.cell(prompt_w, h, "> ")
        pdf.set_text_color(tr, tg, tb)
        tx = x + prompt_w

    pdf.set_xy(tx, y)
    pdf.cell(w if w is not None else pdf.get_string_width(label) + 4,
             h, label, align=align)
    _reset_tracking(pdf)

    if underline_w and voice not in ("grotesk", "typewriter"):
        pdf.set_draw_color(*theme.structural())
        pdf.set_line_width(0.2 if voice == "script" else 0.25)
        pdf.line(x, y + h + 1.2, x + underline_w, y + h + 1.2)
    pdf.set_text_color(*theme.rgb("text"))
    return y + h + 3.0


def page_title(pdf: FPDF, theme: Theme, x: float, y: float,
               light: str, bold: str, size: float | None = None) -> float:
    """Voice-aware page title.  Returns the x just after the title text.

    classic/grotesk: light first word + bold remainder (duo weights);
    serif/typewriter: single face, duo via color; script: one joined run.
    """
    voice = theme.design.voice
    spec = theme.role("page_title")
    size = size if size is not None else spec.size
    h = size * 0.55
    tr, tg, tb = theme.rgb("text")
    lr, lg, lb = theme.rgb("text_light")

    if voice == "script":
        joined = theme.case("page_title", f"{light} {bold}".strip())
        theme.set_type(pdf, "page_title", size=size)
        pdf.set_text_color(*blend((tr, tg, tb), theme.rgb("primary"), 0.15))
        pdf.set_xy(x, y - size * 0.18)   # script face sits high; optical fix
        tw = pdf.get_string_width(joined)
        pdf.cell(tw + 2, h, joined)
        _reset_tracking(pdf)
        pdf.set_text_color(tr, tg, tb)
        return x + tw + 2

    if voice == "classic":
        # Exact pre-design behavior (duo_title)
        pdf.set_xy(x, y)
        pdf.set_font(theme.body, "I", size)   # light weight registered as I
        pdf.set_text_color(lr, lg, lb)
        cx = x
        if light:
            wl = pdf.get_string_width(light) + 1.5
            pdf.cell(wl, h, light)
            cx += wl
        pdf.set_font(theme.body, "B", size)
        pdf.set_text_color(tr, tg, tb)
        wb = pdf.get_string_width(bold) + 2
        pdf.cell(wb, h, bold)
        return cx + wb

    light_c = theme.case("page_title", light) if light else ""
    bold_c = theme.case("page_title", bold)
    fam = theme._family(spec.family)
    light_style = "I" if voice == "grotesk" else spec.style
    theme.set_type(pdf, "page_title", size=size)
    cx = x
    if light_c:
        pdf.set_font(fam, light_style, size)
        pdf.set_text_color(lr, lg, lb)
        pdf.set_xy(cx, y)
        wl = pdf.get_string_width(light_c) + 1.5
        pdf.cell(wl, h, light_c)
        cx += wl
    pdf.set_font(fam, spec.style, size)
    pdf.set_text_color(tr, tg, tb)
    pdf.set_xy(cx, y)
    wb = pdf.get_string_width(bold_c) + 2
    pdf.cell(wb, h, bold_c)
    _reset_tracking(pdf)
    return cx + wb


def duo_title(pdf: FPDF, theme: Theme, x: float, y: float,
              light: str, bold: str, size: float | None = None) -> None:
    """Deprecated alias -- use :func:`page_title`."""
    page_title(pdf, theme, x, y, light, bold, size=size)


# ---------------------------------------------------------------------------
# Boxes / tables / lines
# ---------------------------------------------------------------------------

def _container_radius(theme: Theme, default: float) -> float:
    if theme.container == "squared_hairline":
        return 0.0
    return default


def _rect_maybe_round(pdf: FPDF, x: float, y: float, w: float, h: float,
                      style: str, radius: float,
                      corners: bool | tuple = True) -> None:
    """rect() wrapper: fpdf2 rejects round_corners with corner_radius=0."""
    if radius <= 0:
        pdf.rect(x, y, w, h, style=style)
    else:
        pdf.rect(x, y, w, h, style=style, round_corners=corners,
                 corner_radius=radius)


def rounded_box(pdf: FPDF, theme: Theme, panel: Panel,
                fill: tuple[int, int, int] | None = None,
                border: tuple[int, int, int] | None = None,
                radius: float = 1.8, line_width: float = 0.3) -> None:
    """Filled and/or stroked rounded rectangle (square under geometric)."""
    style = ""
    if fill is not None:
        pdf.set_fill_color(*fill)
        style += "F"
    if border is not None:
        pdf.set_draw_color(*border)
        pdf.set_line_width(line_width)
        style += "D"
    if not style:
        return
    _rect_maybe_round(pdf, panel.x, panel.y, panel.w, panel.h, style,
                      _container_radius(theme, radius))


def ruled_lines(pdf: FPDF, theme: Theme, panel: Panel,
                spacing: float = 8.0, inset: float = 2.0,
                start_offset: float | None = None) -> None:
    """Horizontal writing lines filling *panel*."""
    gr, gg, gb = theme.rule_c()
    pdf.set_draw_color(gr, gg, gb)
    pdf.set_line_width(0.28)
    y = panel.y + (start_offset if start_offset is not None else spacing)
    while y <= panel.y2 + 0.1:
        pdf.line(panel.x + inset, y, panel.x2 - inset, y)
        y += spacing


def checkbox_lines(pdf: FPDF, theme: Theme, panel: Panel,
                   spacing: float = 8.5, box_size: float = 3.4,
                   inset: float = 1.5) -> None:
    """Checkbox + writing line rows filling *panel*."""
    gr, gg, gb = theme.rule_c()
    fill = theme.box_fill() or WHITE
    n = max(1, int((panel.h - 2) / spacing))
    pdf.set_line_width(0.28)
    radius = _container_radius(theme, 0.7)
    for i in range(n):
        y = panel.y + 2 + i * spacing
        pdf.set_fill_color(*fill)
        pdf.set_draw_color(*blend(theme.rgb("grid_line"), theme.structural(), 0.25))
        _rect_maybe_round(pdf, panel.x + inset, y, box_size, box_size, "FD",
                          radius)
        pdf.set_draw_color(gr, gg, gb)
        pdf.line(panel.x + inset + box_size + 3, y + box_size,
                 panel.x2 - inset, y + box_size)


def dot_grid(pdf: FPDF, theme: Theme, panel: Panel, spacing: float = 4.6,
             dot_r: float = 0.28) -> None:
    """Dot-grid area filling *panel*.

    Dots are drawn as tiny squares (one PDF op each instead of four for an
    ellipse) -- indistinguishable at this size and 4x smaller output.
    """
    dr, dg, db = blend(theme.rgb("grid_line"), theme.structural(), 0.25)
    pdf.set_fill_color(dr, dg, db)
    x = panel.x
    while x <= panel.x2:
        y = panel.y
        while y <= panel.y2:
            pdf.rect(x - dot_r, y - dot_r, dot_r * 2, dot_r * 2, style="F")
            y += spacing
        x += spacing


def graph_grid(pdf: FPDF, theme: Theme, panel: Panel,
               spacing: float = 5.0) -> None:
    """Graph-paper fill: 5 mm squares, every 4th line heavier."""
    c = theme.rule_c()
    pdf.set_draw_color(*c)
    n_x = int(panel.w / spacing)
    n_y = int(panel.h / spacing)
    x2 = panel.x + n_x * spacing
    y2 = panel.y + n_y * spacing

    def _lines(major: bool) -> None:
        for i in range(n_x + 1):
            if (i % 4 == 0) == major:
                x = panel.x + i * spacing
                pdf.line(x, panel.y, x, y2)
        for i in range(n_y + 1):
            if (i % 4 == 0) == major:
                y = panel.y + i * spacing
                pdf.line(panel.x, y, x2, y)

    with pdf.local_context(stroke_opacity=0.6):
        pdf.set_line_width(0.16)
        _lines(major=False)
    pdf.set_line_width(0.24)
    _lines(major=True)


def fill_texture(pdf: FPDF, theme: Theme, panel: Panel, kind: str = "notes",
                 spacing: float | None = None,
                 start_offset: float | None = None,
                 inset: float = 2.0) -> None:
    """Texture-token dispatch for free-writing areas.

    ``kind`` is "notes" (doodle areas) or "day" (day/task areas).  With the
    default ``dot`` texture this reproduces today's mix exactly: notes get
    the dot grid, day areas get ruled lines at the caller's spacing.
    """
    tex = theme.design.texture
    if tex == "graph":
        graph_grid(pdf, theme, panel)
        return
    if tex == "blank" and kind == "notes":
        return   # day areas are never blank
    if tex == "dot" and kind == "notes":
        dot_grid(pdf, theme, panel)
        return
    default = 9.0 if kind == "notes" else 8.0
    ruled_lines(pdf, theme, panel, spacing=spacing or default,
                start_offset=start_offset, inset=inset)


def table(pdf: FPDF, theme: Theme, panel: Panel,
          columns: list[tuple[str, float]], n_rows: int,
          header_h: float = 7.5, zebra: bool = False,
          row_labels: list[str] | None = None,
          font_size: float | None = None) -> float:
    """Reference-style table: header band + thin ruled grid.

    *columns* is ``[(label, width_fraction), ...]``.  Returns row height.
    """
    font_size = font_size or theme.fonts.size_small
    band = theme.band_fill()
    br, bg_, bb = theme.border_c()
    tr, tg, tb = theme.band_text_c()

    # Header band
    pdf.set_draw_color(br, bg_, bb)
    pdf.set_line_width(theme.border_w())
    if band is not None:
        pdf.set_fill_color(*band)
        pdf.rect(panel.x, panel.y, panel.w, header_h, style="FD")
    else:
        pdf.rect(panel.x, panel.y, panel.w, header_h, style="D")

    pdf.set_text_color(tr, tg, tb)
    theme.set_type(pdf, "band_label", size=font_size - 1)
    x = panel.x
    col_ws = [panel.w * f for _, f in columns]
    for (label, _), cw in zip(columns, col_ws):
        pdf.set_xy(x, panel.y)
        pdf.cell(cw, header_h, theme.case("band_label", label), align="C")
        x += cw
    _reset_tracking(pdf)

    # Rows
    body_h = panel.h - header_h
    row_h = body_h / n_rows
    gr, gg, gb = theme.rule_c()

    if zebra or theme.ink.zebra:
        zfill = theme.box_fill() or blend(theme.paper_c(), theme.rgb("text"), 0.045)
        pdf.set_fill_color(*zfill)
        for i in range(n_rows):
            if i % 2 == 1:
                pdf.rect(panel.x, panel.y + header_h + i * row_h,
                         panel.w, row_h, style="F")

    pdf.set_draw_color(gr, gg, gb)
    pdf.set_line_width(0.25)
    for i in range(1, n_rows):
        y = panel.y + header_h + i * row_h
        pdf.line(panel.x, y, panel.x2, y)
    x = panel.x
    for cw in col_ws[:-1]:
        x += cw
        pdf.line(x, panel.y, x, panel.y2)

    if row_labels:
        theme.set_type(pdf, "mini_digit", size=font_size - 1)
        pdf.set_text_color(*theme.rgb("text_light"))
        for i, lbl in enumerate(row_labels[:n_rows]):
            pdf.set_xy(panel.x + 1.5, panel.y + header_h + i * row_h)
            pdf.cell(col_ws[0] - 2, row_h, lbl, align="L")
        _reset_tracking(pdf)

    # Outer border
    pdf.set_draw_color(br, bg_, bb)
    pdf.set_line_width(theme.border_w())
    pdf.rect(panel.x, panel.y, panel.w, panel.h, style="D")
    pdf.set_text_color(*theme.rgb("text"))
    return row_h


def _labelled_box_inner(pdf: FPDF, theme: Theme, inner: Panel, fill: bool,
                        lines_spacing: float | None, dots: bool) -> None:
    if fill:
        f = theme.box_fill()
        if f is not None:
            pdf.set_fill_color(*f)
            pdf.rect(inner.x, inner.y, inner.w, inner.h, style="F")
    elif dots:
        fill_texture(pdf, theme, inner.inset(1.5), kind="notes")
    elif lines_spacing:
        fill_texture(pdf, theme, inner, kind="day", spacing=lines_spacing)


def labelled_box(pdf: FPDF, theme: Theme, panel: Panel, label: str,
                 label_h: float = 7.0, fill: bool = False,
                 lines_spacing: float | None = 8.0,
                 dots: bool = False) -> Panel:
    """Box with a label band on top; returns the inner content panel.

    The rendering dispatches on the motif's container style
    (``theme.container``); ``soft_rounded`` is the classic path.
    """
    container = theme.container
    band = theme.band_fill()
    br, bg_, bb = theme.border_c()
    tr, tg, tb = theme.band_text_c()
    label_cased = theme.case("band_label", label)
    left_band = theme.design.voice == "grotesk"   # band labels left-aligned

    if container == "open_air":
        # Small-caps label + full-width underline; open content below.
        pdf.set_text_color(*theme.label_c())
        theme.set_type(pdf, "band_label")
        pdf.set_xy(panel.x + 0.5, panel.y)
        pdf.cell(panel.w - 1, label_h - 1.5, label_cased, align="L")
        _reset_tracking(pdf)
        pdf.set_draw_color(*theme.structural())
        pdf.set_line_width(0.3)
        pdf.line(panel.x, panel.y + label_h - 0.5, panel.x2,
                 panel.y + label_h - 0.5)
        inner = Panel(panel.x + 1, panel.y + label_h + 1.5,
                      panel.w - 2, panel.h - label_h - 3.0)
        _labelled_box_inner(pdf, theme, inner, fill, lines_spacing, dots)
        pdf.set_text_color(*theme.rgb("text"))
        return inner

    if container == "squared_hairline":
        # Label above the box + doubled top edge, square corners.
        pdf.set_text_color(*theme.label_c())
        theme.set_type(pdf, "band_label")
        pdf.set_xy(panel.x + 0.5, panel.y)
        pdf.cell(panel.w - 1, 4.5, label_cased, align="L")
        _reset_tracking(pdf)
        box = Panel(panel.x, panel.y + 5.5, panel.w, panel.h - 5.5)
        pdf.set_draw_color(br, bg_, bb)
        pdf.set_line_width(0.2)
        pdf.rect(box.x, box.y, box.w, box.h, style="D")
        pdf.set_line_width(0.3)
        pdf.line(box.x, box.y, box.x2, box.y)
        pdf.set_line_width(0.2)
        pdf.line(box.x, box.y + 0.7, box.x2, box.y + 0.7)
        inner = Panel(box.x + 2, box.y + 2.4, box.w - 4, box.h - 4.4)
        _labelled_box_inner(pdf, theme, inner, fill, lines_spacing, dots)
        pdf.set_text_color(*theme.rgb("text"))
        return inner

    if container == "ticked_corners":
        # Corner ticks instead of a border; centered label with hairlines.
        pdf.set_draw_color(*theme.structural())
        pdf.set_line_width(0.5)
        leg = 3.5
        for cx, cy, dx, dy in ((panel.x, panel.y, 1, 1),
                               (panel.x2, panel.y, -1, 1),
                               (panel.x, panel.y2, 1, -1),
                               (panel.x2, panel.y2, -1, -1)):
            pdf.line(cx, cy, cx + dx * leg, cy)
            pdf.line(cx, cy, cx, cy + dy * leg)
        pdf.set_text_color(*theme.label_c())
        theme.set_type(pdf, "band_label")
        tw = pdf.get_string_width(label_cased)
        pdf.set_xy(panel.x, panel.y + 0.6)
        pdf.cell(panel.w, label_h - 1.2, label_cased, align="C")
        _reset_tracking(pdf)
        mid_y = panel.y + 0.6 + (label_h - 1.2) / 2
        pdf.set_line_width(0.25)
        cx = panel.x + panel.w / 2
        pdf.line(cx - tw / 2 - 8, mid_y, cx - tw / 2 - 2, mid_y)
        pdf.line(cx + tw / 2 + 2, mid_y, cx + tw / 2 + 8, mid_y)
        inner = Panel(panel.x + 2, panel.y + label_h + 1.5,
                      panel.w - 4, panel.h - label_h - 3.5)
        _labelled_box_inner(pdf, theme, inner, fill, lines_spacing, dots)
        pdf.set_text_color(*theme.rgb("text"))
        return inner

    # -- soft_rounded (classic-exact) ------------------------------------
    pdf.set_draw_color(br, bg_, bb)
    pdf.set_line_width(theme.border_w())
    pdf.rect(panel.x, panel.y, panel.w, panel.h, style="D",
             round_corners=True, corner_radius=1.6)
    if band is not None:
        pdf.set_fill_color(*band)
        pdf.rect(panel.x, panel.y, panel.w, label_h, style="F",
                 round_corners=("TOP_LEFT", "TOP_RIGHT"), corner_radius=1.6)

    pdf.set_text_color(tr, tg, tb)
    theme.set_type(pdf, "band_label")
    pdf.set_xy(panel.x + (4 if left_band else 0), panel.y)
    pdf.cell(panel.w - (4 if left_band else 0), label_h, label_cased,
             align="L" if left_band else "C")
    _reset_tracking(pdf)

    inner = Panel(panel.x + 2, panel.y + label_h + 1.5,
                  panel.w - 4, panel.h - label_h - 3.5)
    _labelled_box_inner(pdf, theme, inner, fill, lines_spacing, dots)
    pdf.set_text_color(*theme.rgb("text"))
    return inner


def stat_boxes(pdf: FPDF, theme: Theme, panel: Panel,
               labels: list[str], gap: float = 5.0) -> None:
    """Row of summary stat boxes: label band + empty value area."""
    boxes = panel.cols(len(labels), gap=gap)
    for box, label in zip(boxes, labels):
        labelled_box(pdf, theme, box, label, label_h=6.5, lines_spacing=None)


def progress_bar(pdf: FPDF, theme: Theme, x: float, y: float, w: float,
                 h: float = 6.0, ticks: int = 10) -> None:
    """Thermometer-style empty progress bar with % ticks."""
    br, bg_, bb = blend(theme.rgb("grid_line"), theme.structural(), 0.5)
    pdf.set_draw_color(br, bg_, bb)
    pdf.set_line_width(0.35)
    fill = theme.box_fill() or WHITE
    pdf.set_fill_color(*fill)
    radius = _container_radius(theme, h / 2)
    _rect_maybe_round(pdf, x, y, w, h, "FD", radius)
    pdf.set_draw_color(*blend(theme.rgb("grid_line"), theme.structural(), 0.3))
    pdf.set_line_width(0.25)
    for i in range(1, ticks):
        tx = x + w * i / ticks
        pdf.line(tx, y + 1.2, tx, y + h - 1.2)
    # Percent labels at ends
    theme.set_type(pdf, "mini_digit", size=5.5)
    pdf.set_text_color(*theme.rgb("text_light"))
    pdf.set_xy(x - 2, y + h + 0.6)
    pdf.cell(10, 3, "0%", align="L")
    pdf.set_xy(x + w - 8, y + h + 0.6)
    pdf.cell(10, 3, "100%", align="R")
    _reset_tracking(pdf)
    pdf.set_text_color(*theme.rgb("text"))


def water_droplets(pdf: FPDF, theme: Theme, x: float, y: float,
                   n: int = 8, size: float = 3.2, gap: float = 6.0) -> None:
    """Row of outline water droplets (circle + top triangle)."""
    pr, pg_, pb = blend(theme.rgb("secondary"), theme.rgb("primary"), 0.3)
    pdf.set_draw_color(pr, pg_, pb)
    pdf.set_line_width(0.35)
    for i in range(n):
        cx = x + i * gap
        # circle body
        pdf.ellipse(cx - size / 2, y, size, size, style="D")
        # droplet tip
        pdf.polygon(
            [(cx - size * 0.32, y + size * 0.22),
             (cx, y - size * 0.55),
             (cx + size * 0.32, y + size * 0.22)],
            style="D",
        )


def mood_faces(pdf: FPDF, theme: Theme, x: float, y: float,
               n: int = 5, r: float = 2.6, gap: float = 8.0) -> None:
    """Row of outline smiley faces (varying mouths)."""
    pr, pg_, pb = blend(theme.rgb("secondary"), theme.rgb("primary"), 0.3)
    pdf.set_draw_color(pr, pg_, pb)
    pdf.set_line_width(0.32)
    for i in range(n):
        cx = x + i * gap
        cy = y + r
        pdf.ellipse(cx - r, cy - r, r * 2, r * 2, style="D")
        # eyes
        pdf.set_fill_color(pr, pg_, pb)
        for ex in (-0.9, 0.9):
            pdf.ellipse(cx + ex - 0.25, cy - 0.9, 0.5, 0.5, style="F")
        # mouth: from smile to frown depending on i
        t = i / max(1, n - 1)          # 0 happy .. 1 sad
        my = cy + 0.9
        curve = 0.8 - 1.6 * t          # +0.8 smile .. -0.8 frown
        pdf.line(cx - 1.1, my - curve * 0.3, cx, my + curve * 0.5)
        pdf.line(cx, my + curve * 0.5, cx + 1.1, my - curve * 0.3)


def outline_button(pdf: FPDF, theme: Theme, x: float, y: float, w: float,
                   h: float, text: str, link: int | None = None) -> None:
    """White rounded button with border, like 'BACK TO CALENDAR' in the ref."""
    br, bg_, bb = blend(theme.rgb("text"), theme.structural(), 0.5)
    pdf.set_fill_color(*WHITE)
    pdf.set_draw_color(br, bg_, bb)
    pdf.set_line_width(0.4)
    radius = 1.0 if theme.container == "squared_hairline" else h / 2
    pdf.rect(x, y, w, h, style="FD", round_corners=True, corner_radius=radius)
    pdf.set_text_color(*blend(theme.rgb("text"), theme.structural(), 0.3))
    pdf.set_font(theme.body, "B", 7)   # chrome is always Inter
    try:
        pdf.set_char_spacing(0.4)
    except Exception:
        pass
    pdf.set_xy(x, y)
    if link is not None:
        pdf.cell(w, h, text.upper(), align="C", link=link)
    else:
        pdf.cell(w, h, text.upper(), align="C")
    _reset_tracking(pdf)
    pdf.set_text_color(*theme.rgb("text"))


def priority_rows(pdf: FPDF, theme: Theme, motif, panel: Panel,
                  n: int = 3, bullet_size: float = 4.4) -> None:
    """Numbered priority rows: motif bullet + writing line.

    With the botanical motif this reproduces the classic filled-circle
    rows exactly (circle at panel.x+0.5, line from panel.x+7.5).
    """
    gr = theme.rule_c()
    line_gap = (panel.y2 - panel.y - 2) / n
    for i in range(n):
        ly = panel.y + (i + 1) * line_gap
        content_x = motif.bullet(pdf, theme, panel.x + 0.5, ly - bullet_size,
                                 bullet_size, number=i + 1)
        pdf.set_draw_color(*gr)
        pdf.set_line_width(0.3)
        pdf.line(content_x, ly, panel.x2, ly)
    pdf.set_text_color(*theme.rgb("text"))
