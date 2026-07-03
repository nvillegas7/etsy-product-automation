"""Landscape iPad-optimized page dimensions for the open-binder layout.

All values are in **millimetres** (mm) matching FPDF's unit setting.

Target device : iPad Pro 12.9" in **landscape** orientation
Page size     : 1366 x 1024 pt  =  482.0 mm x 361.2 mm  (width x height)

The page is drawn as an *open ring binder* photographed from above:

    ┌────────────────────────[TAB][TAB][TAB][TAB][TAB]──(HOME)─┐
    │  ┌──────────────────────╥╥──────────────────────┐ ┌JAN┐  │
    │  │                      ║║                      │ ├FEB┤  │
    │  │      LEFT PAGE       ║║      RIGHT PAGE      │ ├...┤  │
    │  │      (paper)       coil║      (paper)        │ ├DEC┤  │
    │  └──────────────────────╨╨──────────────────────┘ └───┘  │
    │            desk background (darker tone)                 │
    └───────────────────────────────────────────────────────────┘

Month tabs *migrate*: on a page belonging to month m, tabs for months
before m sit on the LEFT page edge (they look "used"), months m..12 stay
on the RIGHT edge.
"""

from __future__ import annotations

from dataclasses import dataclass

# ═══════════════════════════════════════════════════════════════════════
# Page dimensions  (1366 x 1024 pt  →  mm at 72 dpi: pt * 25.4 / 72)
# ═══════════════════════════════════════════════════════════════════════
PAGE_WIDTH: float = 482.0   # mm  (1366 pt)
PAGE_HEIGHT: float = 361.2  # mm  (1024 pt)

# ═══════════════════════════════════════════════════════════════════════
# Paper sheet (the open binder pages) on the desk background
# ═══════════════════════════════════════════════════════════════════════
PAPER_X: float = 13.0
PAPER_X2: float = PAGE_WIDTH - 13.0
PAPER_Y: float = 11.0
PAPER_Y2: float = PAGE_HEIGHT - 7.5
PAPER_WIDTH: float = PAPER_X2 - PAPER_X
PAPER_HEIGHT: float = PAPER_Y2 - PAPER_Y

# ═══════════════════════════════════════════════════════════════════════
# Top category tab bar (sits on the desk, tucked behind the paper top edge)
# ═══════════════════════════════════════════════════════════════════════
TOP_TAB_HEIGHT: float = 12.5           # visible tab height (top rounded)
TOP_TAB_Y: float = 0.8
TOP_TAB_X_START: float = PAGE_WIDTH * 0.40
TOP_TAB_X_END: float = PAGE_WIDTH - 27.0   # leave room for the HOME circle
TOP_TAB_CORNER_RADIUS: float = 2.2
TOP_TAB_GAP: float = 1.2

# HOME circle button (top right, on the desk)
HOME_CX: float = PAGE_WIDTH - 13.5
HOME_CY: float = 6.6
HOME_R: float = 5.2

# ═══════════════════════════════════════════════════════════════════════
# Month tab strips (left + right paper edges, migrating)
# ═══════════════════════════════════════════════════════════════════════
MONTH_TAB_WIDTH: float = 11.0        # protrusion beyond the paper edge
MONTH_TAB_ACTIVE_EXTRA: float = 2.6  # active tab sticks out a bit more
MONTH_TAB_TOP: float = PAPER_Y + 14.0
MONTH_TAB_BOTTOM: float = PAPER_Y2 - 6.0
MONTH_TAB_SLOTS: int = 13            # 1 "YEAR" slot + 12 months
MONTH_TAB_SLOT_H: float = (MONTH_TAB_BOTTOM - MONTH_TAB_TOP) / MONTH_TAB_SLOTS
MONTH_TAB_GAP: float = 1.4
MONTH_TAB_CORNER_RADIUS: float = 2.2

# ═══════════════════════════════════════════════════════════════════════
# Spiral coil (vertical centre)
# ═══════════════════════════════════════════════════════════════════════
SPIRAL_WIDTH: float = 14.0
SPIRAL_X: float = (PAGE_WIDTH - SPIRAL_WIDTH) / 2.0
SPIRAL_LOOPS: int = 26

# ═══════════════════════════════════════════════════════════════════════
# Content panels (left page / right page of the open binder)
# ═══════════════════════════════════════════════════════════════════════
PANEL_PAD: float = 8.0     # inner margin from paper edge / coil clearance
COIL_CLEARANCE: float = 5.0

LEFT_CONTENT_X: float = PAPER_X + PANEL_PAD                      # 21.0
LEFT_CONTENT_RIGHT: float = SPIRAL_X - COIL_CLEARANCE            # 229.0
LEFT_CONTENT_WIDTH: float = LEFT_CONTENT_RIGHT - LEFT_CONTENT_X  # 208.0

RIGHT_CONTENT_X: float = SPIRAL_X + SPIRAL_WIDTH + COIL_CLEARANCE  # 253.0
RIGHT_CONTENT_RIGHT: float = PAPER_X2 - PANEL_PAD                  # 461.0
RIGHT_CONTENT_WIDTH: float = RIGHT_CONTENT_RIGHT - RIGHT_CONTENT_X  # 208.0

# Vertical zones
HEADER_Y: float = PAPER_Y + 5.0        # top of the header zone
HEADER_HEIGHT: float = 26.0            # pennant / title zone height
BODY_Y: float = HEADER_Y + HEADER_HEIGHT   # 42.0
BODY_BOTTOM: float = PAPER_Y2 - 9.0        # leave room for footer text
BODY_HEIGHT: float = BODY_BOTTOM - BODY_Y

# Convenience aliases used throughout page renderers
LEFT_CONTENT_Y: float = HEADER_Y
LEFT_CONTENT_HEIGHT: float = BODY_BOTTOM - HEADER_Y
LEFT_BODY_Y: float = BODY_Y
LEFT_BODY_HEIGHT: float = BODY_HEIGHT
RIGHT_CONTENT_Y: float = HEADER_Y
RIGHT_CONTENT_HEIGHT: float = BODY_BOTTOM - HEADER_Y
RIGHT_BODY_Y: float = BODY_Y
RIGHT_BODY_HEIGHT: float = BODY_HEIGHT

# "Full" span -- kept for compatibility; most renderers should use the
# left/right panels so content respects the coil.
FULL_CONTENT_X: float = LEFT_CONTENT_X
FULL_CONTENT_Y: float = HEADER_Y
FULL_CONTENT_WIDTH: float = RIGHT_CONTENT_RIGHT - LEFT_CONTENT_X
FULL_CONTENT_HEIGHT: float = BODY_BOTTOM - HEADER_Y
FULL_BODY_Y: float = BODY_Y
FULL_BODY_HEIGHT: float = BODY_HEIGHT

CONTENT_X: float = FULL_CONTENT_X
CONTENT_Y: float = FULL_CONTENT_Y
CONTENT_WIDTH: float = FULL_CONTENT_WIDTH
CONTENT_HEIGHT: float = FULL_CONTENT_HEIGHT

# Footer (small text inside the paper bottom edge -- not a bar)
FOOTER_Y: float = PAPER_Y2 - 6.5
FOOTER_HEIGHT: float = 5.0
FOOTER_X: float = LEFT_CONTENT_X
FOOTER_WIDTH: float = FULL_CONTENT_WIDTH

# ═══════════════════════════════════════════════════════════════════════
# Pennant month badge (hangs from the paper top edge, left panel)
# ═══════════════════════════════════════════════════════════════════════
PENNANT_X: float = LEFT_CONTENT_X
PENNANT_Y: float = PAPER_Y
PENNANT_W: float = 30.0
PENNANT_H: float = 27.0
PENNANT_NOTCH: float = 6.0

# Month tab labels
MONTH_TAB_LABELS: list[str] = [
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
]
MONTH_TAB_COUNT: int = 12

# Legacy names still referenced elsewhere
MARGIN_LEFT: float = PAPER_X
MARGIN_RIGHT: float = PAGE_WIDTH - PAPER_X2
MARGIN_TOP: float = TOP_TAB_Y
MARGIN_BOTTOM: float = PAGE_HEIGHT - PAPER_Y2
MONTH_TAB_X: float = PAPER_X2
TAB_STRIP_WIDTH: float = MONTH_TAB_WIDTH
TAB_STRIP_X: float = MONTH_TAB_X
TAB_COUNT: int = MONTH_TAB_COUNT
TAB_HEIGHT: float = MONTH_TAB_SLOT_H
TAB_CORNER_RADIUS: float = MONTH_TAB_CORNER_RADIUS
TOP_TAB_X: float = TOP_TAB_X_START
TOP_TAB_COUNT: int = 7
TOP_TAB_LABELS: list[str] = [
    "INDEX", "CALENDAR", "MONTHLY PLAN", "WEEKLY", "NOTES", "HABITS", "GOALS",
]
MONTH_TAB_ITEM_HEIGHT: float = MONTH_TAB_SLOT_H


# ═══════════════════════════════════════════════════════════════════════
# Dataclasses
# ═══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class GridMetrics:
    """Pre-calculated positions for a regular grid."""

    x: float       # left edge
    y: float       # top edge
    width: float   # total grid width
    height: float  # total grid height
    cols: int
    rows: int
    cell_w: float
    cell_h: float

    def cell_xy(self, col: int, row: int) -> tuple[float, float]:
        """Return the top-left corner (x, y) of cell (col, row)."""
        return self.x + col * self.cell_w, self.y + row * self.cell_h


@dataclass(frozen=True)
class Panel:
    """A rectangular content region (one page of the open binder)."""

    x: float
    y: float
    w: float
    h: float

    @property
    def x2(self) -> float:
        return self.x + self.w

    @property
    def y2(self) -> float:
        return self.y + self.h

    def cols(self, n: int, gap: float = 5.0) -> list["Panel"]:
        """Split into *n* equal columns with *gap* between them."""
        col_w = (self.w - gap * (n - 1)) / n
        return [
            Panel(self.x + i * (col_w + gap), self.y, col_w, self.h)
            for i in range(n)
        ]

    def rows(self, n: int, gap: float = 5.0) -> list["Panel"]:
        """Split into *n* equal rows with *gap* between them."""
        row_h = (self.h - gap * (n - 1)) / n
        return [
            Panel(self.x, self.y + i * (row_h + gap), self.w, row_h)
            for i in range(n)
        ]

    def split_v(self, fractions: list[float], gap: float = 5.0) -> list["Panel"]:
        """Split vertically into rows sized by *fractions* (must sum to ~1)."""
        usable = self.h - gap * (len(fractions) - 1)
        out: list[Panel] = []
        y = self.y
        for f in fractions:
            h = usable * f
            out.append(Panel(self.x, y, self.w, h))
            y += h + gap
        return out

    def split_h(self, fractions: list[float], gap: float = 5.0) -> list["Panel"]:
        """Split horizontally into columns sized by *fractions*."""
        usable = self.w - gap * (len(fractions) - 1)
        out: list[Panel] = []
        x = self.x
        for f in fractions:
            w = usable * f
            out.append(Panel(x, self.y, w, self.h))
            x += w + gap
        return out

    def inset(self, dx: float, dy: float | None = None) -> "Panel":
        dy = dx if dy is None else dy
        return Panel(self.x + dx, self.y + dy, self.w - 2 * dx, self.h - 2 * dy)


def left_body() -> Panel:
    """Left page body region (below header)."""
    return Panel(LEFT_CONTENT_X, BODY_Y, LEFT_CONTENT_WIDTH, BODY_HEIGHT)


def right_body() -> Panel:
    """Right page body region (below header)."""
    return Panel(RIGHT_CONTENT_X, BODY_Y, RIGHT_CONTENT_WIDTH, BODY_HEIGHT)


def left_full() -> Panel:
    """Left page including the header zone."""
    return Panel(LEFT_CONTENT_X, HEADER_Y, LEFT_CONTENT_WIDTH, LEFT_CONTENT_HEIGHT)


def right_full() -> Panel:
    """Right page including the header zone."""
    return Panel(RIGHT_CONTENT_X, HEADER_Y, RIGHT_CONTENT_WIDTH, RIGHT_CONTENT_HEIGHT)


# ═══════════════════════════════════════════════════════════════════════
# Calendar grid (monthly view) -- fits in LEFT panel body
# ═══════════════════════════════════════════════════════════════════════
CALENDAR_COLS: int = 7
CALENDAR_ROWS: int = 6


def calendar_grid() -> GridMetrics:
    """Monthly calendar grid inside the left panel body."""
    weekday_header_h = 9.0
    body = left_body()
    grid_y = body.y + weekday_header_h
    grid_h = body.h - weekday_header_h
    return GridMetrics(
        x=body.x,
        y=grid_y,
        width=body.w,
        height=grid_h,
        cols=CALENDAR_COLS,
        rows=CALENDAR_ROWS,
        cell_w=body.w / CALENDAR_COLS,
        cell_h=grid_h / CALENDAR_ROWS,
    )


def weekday_header_metrics() -> tuple[float, float, float, float]:
    """Return (x, y, cell_w, row_h) for the weekday header row."""
    body = left_body()
    return body.x, body.y, body.w / CALENDAR_COLS, 9.0


# ═══════════════════════════════════════════════════════════════════════
# Mini month calendar (year-at-a-glance)
# ═══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class MiniMonthMetrics:
    x: float
    y: float
    w: float
    h: float
    title_h: float
    cell_w: float
    cell_h: float


def mini_month_metrics(panel: Panel, col: int, row: int,
                       cols: int = 2, rows: int = 3,
                       gap_x: float = 10.0, gap_y: float = 8.0) -> MiniMonthMetrics:
    """Layout for one mini month card inside a 2x3 grid on *panel*."""
    w = (panel.w - gap_x * (cols - 1)) / cols
    h = (panel.h - gap_y * (rows - 1)) / rows
    x = panel.x + col * (w + gap_x)
    y = panel.y + row * (h + gap_y)
    title_h = 8.0
    return MiniMonthMetrics(
        x=x, y=y, w=w, h=h, title_h=title_h,
        cell_w=w / 7.0,
        cell_h=(h - title_h - 6.0) / 7.0,   # 1 weekday row + 6 week rows
    )


# ═══════════════════════════════════════════════════════════════════════
# Dot grid helper
# ═══════════════════════════════════════════════════════════════════════
DOT_SPACING: float = 5.0  # mm


def dot_grid_positions(panel: Panel, spacing: float = DOT_SPACING) -> list[tuple[float, float]]:
    """Return (x, y) dot positions filling *panel*."""
    positions: list[tuple[float, float]] = []
    x = panel.x
    while x <= panel.x2:
        y = panel.y
        while y <= panel.y2:
            positions.append((x, y))
            y += spacing
        x += spacing
    return positions


# ═══════════════════════════════════════════════════════════════════════
# Shell geometry (design-parameter system)
# ═══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Geometry:
    """Per-shell page geometry: panels, header/body/footer zones.

    Every renderer takes its rectangles from here instead of the module
    constants; ``build_geometry("binder")`` reproduces the constants above
    exactly (there is a test asserting that).
    """

    page_w: float
    page_h: float
    header_y: float
    header_h: float
    body_y: float
    body_bottom: float
    footer_y: float
    left_x: float
    left_w: float
    right_x: float
    right_w: float
    gutter_center: float
    header_style: str          # "pennant" | "script-month" | "plain"
    pennant_x: float = PENNANT_X
    pennant_y: float = PENNANT_Y

    @property
    def body_h(self) -> float:
        return self.body_bottom - self.body_y

    # -- Panels ----------------------------------------------------------

    def left_body(self) -> Panel:
        return Panel(self.left_x, self.body_y, self.left_w, self.body_h)

    def right_body(self) -> Panel:
        return Panel(self.right_x, self.body_y, self.right_w, self.body_h)

    def left_full(self) -> Panel:
        return Panel(self.left_x, self.header_y, self.left_w,
                     self.body_bottom - self.header_y)

    def right_full(self) -> Panel:
        return Panel(self.right_x, self.header_y, self.right_w,
                     self.body_bottom - self.header_y)

    # -- Calendar helpers --------------------------------------------------

    def calendar_grid(self) -> GridMetrics:
        weekday_header_h = 9.0
        body = self.left_body()
        grid_y = body.y + weekday_header_h
        grid_h = body.h - weekday_header_h
        return GridMetrics(
            x=body.x, y=grid_y, width=body.w, height=grid_h,
            cols=CALENDAR_COLS, rows=CALENDAR_ROWS,
            cell_w=body.w / CALENDAR_COLS,
            cell_h=grid_h / CALENDAR_ROWS,
        )

    def weekday_header_metrics(self) -> tuple[float, float, float, float]:
        body = self.left_body()
        return body.x, body.y, body.w / CALENDAR_COLS, 9.0

    def mini_month_metrics(self, panel: Panel, col: int, row: int,
                           cols: int = 2, rows: int = 3,
                           gap_x: float = 10.0, gap_y: float = 8.0) -> MiniMonthMetrics:
        return mini_month_metrics(panel, col, row, cols=cols, rows=rows,
                                  gap_x=gap_x, gap_y=gap_y)


_GEOMETRIES: dict[str, Geometry] = {
    # S1 binder -- the current layout, verbatim (see the constants above).
    "binder": Geometry(
        page_w=PAGE_WIDTH, page_h=PAGE_HEIGHT,
        header_y=HEADER_Y, header_h=HEADER_HEIGHT,
        body_y=BODY_Y, body_bottom=BODY_BOTTOM, footer_y=FOOTER_Y,
        left_x=LEFT_CONTENT_X, left_w=LEFT_CONTENT_WIDTH,
        right_x=RIGHT_CONTENT_X, right_w=RIGHT_CONTENT_WIDTH,
        gutter_center=PAGE_WIDTH / 2,
        header_style="pennant",
        pennant_x=PENNANT_X, pennant_y=PENNANT_Y,
    ),
    # S2 cards -- two floating cards on the desk, coin month tabs.
    "cards": Geometry(
        page_w=PAGE_WIDTH, page_h=PAGE_HEIGHT,
        header_y=25.0, header_h=19.0,
        body_y=48.0, body_bottom=336.0, footer_y=349.0,
        left_x=25.0, left_w=201.0,
        right_x=256.0, right_w=201.0,
        gutter_center=241.0,
        header_style="pennant",
        pennant_x=25.0, pennant_y=16.0,
    ),
    # S3 flat -- the page IS the paper; file-folder month tabs on top.
    "flat": Geometry(
        page_w=PAGE_WIDTH, page_h=PAGE_HEIGHT,
        header_y=20.0, header_h=24.0,
        body_y=48.0, body_bottom=341.0, footer_y=349.0,
        left_x=22.0, left_w=211.0,
        right_x=249.0, right_w=211.0,
        gutter_center=241.0,
        header_style="script-month",
    ),
    # S4 poster -- raw palette exposure, inline month strip.
    "poster": Geometry(
        page_w=PAGE_WIDTH, page_h=PAGE_HEIGHT,
        header_y=18.0, header_h=26.0,
        body_y=58.0, body_bottom=338.0, footer_y=348.0,
        left_x=30.0, left_w=199.0,
        right_x=253.0, right_w=199.0,
        gutter_center=241.0,
        header_style="plain",
    ),
}


def build_geometry(shell: str) -> Geometry:
    """Return the (cached, immutable) geometry for *shell*."""
    return _GEOMETRIES.get(shell, _GEOMETRIES["binder"])
