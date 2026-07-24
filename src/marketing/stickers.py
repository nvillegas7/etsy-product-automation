"""Digital sticker assets rasterized from the planner's own vector art.

Verified July-2026 research: top planner listings bundle pre-cropped PNG
stickers *inside* the planner purchase ("With Digital Stickers" titles are
table stakes).  This module renders a per-palette printable sticker-sheet PDF
from our existing icon/widget vectors and rasterizes every element to a
pre-cropped transparent PNG at 300 dpi -- buyers import the PNGs into
GoodNotes/Notability or print the sheet.

Themes lead with palette-matched FUNCTIONAL planner elements (weekday chips,
label chips, checkboxes, habit strips) plus our flat line icons -- the
research found adult planner-decoration themes carry the top listings, not
kids/kawaii art.

Zero marginal cost: everything is drawn from vectors already in the repo.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import structlog
from fpdf import FPDF

logger = structlog.get_logger()

# US Letter, portrait (printable at home; also imports fine on tablets).
SHEET_W, SHEET_H = 215.9, 279.4
MARGIN = 14.0
DPI = 300
_MM_TO_PT = 72.0 / 25.4

WEEKDAY_CHIPS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY",
                 "FRIDAY", "SATURDAY", "SUNDAY"]
LABEL_CHIPS = ["TO DO", "GOALS", "NOTES", "PRIORITY", "HABITS", "REMEMBER"]

# Curated icon subset: recognisable, planner-functional, one namespace across
# all 11 motif families (each fn signature: (pdf, cx, cy, r, line_c, mark_c, lw)).
_ICON_NAMES = [
    # focus / tasks
    "checkbox", "checkmark", "arrow", "target", "dotcluster",
    # academic + teaching
    "pencil", "star", "bulb", "openbook", "gradcap", "ruler",
    "apple", "chalkboard", "bookstack", "aplus",
    # finance
    "coin", "coinstack", "piggy", "barchart", "uparrow", "wallet",
    # fitness
    "dumbbell", "bottle", "stopwatch", "heartbeat", "medal",
    # self-care
    "lotus", "moonstars", "candle", "teacup", "waterdrop", "leaf",
    # travel
    "airplane", "mappin", "camera",
    # kitchen / home
    "chefhat", "forkknife", "house", "plant", "key", "clock",
    # business / celebration
    "rocket", "growth", "heart", "cake",
]

# Widget strips rendered as wide stickers (name only; drawn in _draw_strip).
_STRIPS = ["progress_bar", "mood_faces", "water_droplets"]

#: Stickers per colorway -- deterministic so SEO copy can be computed before
#: generation (icons + weekday chips + label chips + widget strips).
STICKERS_PER_PALETTE = len(_ICON_NAMES) + len(WEEKDAY_CHIPS) + len(LABEL_CHIPS) + len(_STRIPS)


def sticker_count_for(n_palettes: int) -> int:
    """Total sticker count for a bundle of *n_palettes* colorways."""
    return STICKERS_PER_PALETTE * max(0, n_palettes)


@dataclass
class StickerAssets:
    """Result of one palette's sticker generation."""

    palette: str
    sheet_pdf: Path
    png_paths: list[Path]

    @property
    def count(self) -> int:
        return len(self.png_paths)


def _icon_fn(name: str):
    import src.planner.motifs as motifs
    return getattr(motifs, f"_i_{name}")


def _chip(pdf: FPDF, theme, x: float, y: float, w: float, h: float,
          label: str) -> None:
    """Rounded label chip in the palette primary with reversed text."""
    pdf.set_fill_color(*theme.rgb("primary"))
    pdf.rect(x, y, w, h, style="F", round_corners=True, corner_radius=h / 2)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(theme.body, "B", 9)
    pdf.set_xy(x, y)
    pdf.cell(w, h, label, align="C")


def _draw_strip(pdf: FPDF, theme, kind: str, x: float, y: float,
                w: float, h: float) -> None:
    """One habit-tracker strip sticker (progress bar / mood row / droplets)."""
    from src.planner.widgets import mood_faces, progress_bar, water_droplets

    cy = y + h / 2
    if kind == "progress_bar":
        progress_bar(pdf, theme, x + 2, cy - 3, w - 4, h=6.0)
    elif kind == "mood_faces":
        mood_faces(pdf, theme, x + 5, cy - 2.6, n=5, r=2.8, gap=(w - 12) / 4)
    else:  # water_droplets
        water_droplets(pdf, theme, x + 5, cy - 1.8, n=8, size=3.4,
                       gap=(w - 12) / 7)


def generate_sticker_assets(
    palette_name: str,
    out_dir: str | Path,
    *,
    include_pngs: bool = True,
) -> StickerAssets:
    """Render one palette's sticker sheet PDF + pre-cropped transparent PNGs.

    The sheet draws every element inside a recorded cell rect; light cut
    guides sit OUTSIDE those rects so the rasterized PNGs stay clean.  PNGs
    are clipped per-cell at 300 dpi with alpha (unpainted page = transparent).
    """
    import fitz

    from src.planner.designs import get_design
    from src.planner.motifs import _geo_inks, _icon_lw
    from src.planner.styles import build_theme

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pdf = FPDF(unit="mm", format=(SHEET_W, SHEET_H))
    pdf.set_auto_page_break(auto=False)
    pdf.set_margin(0)
    pdf.set_title(f"Digital Stickers - {palette_name}")
    theme = build_theme(pdf, palette_name, get_design("classic"))

    cells: list[tuple[int, tuple[float, float, float, float], str]] = []
    page_no = -1
    y = 0.0

    def new_page(first: bool = False) -> None:
        nonlocal page_no, y
        pdf.add_page()
        page_no += 1
        y = MARGIN
        pdf.set_text_color(*theme.rgb("text_light"))
        pdf.set_font(theme.body, "B", 9)
        pdf.set_xy(MARGIN, y)
        title = "DIGITAL STICKERS" if not first else \
            "DIGITAL STICKERS  ·  print this sheet or import the PNGs"
        pdf.cell(SHEET_W - 2 * MARGIN, 5, title)
        y += 10

    def cell_rect(w: float, h: float) -> tuple[float, float]:
        """Advance the flow layout; returns the (x, y) of a new cell row slot."""
        nonlocal y
        if y + h + MARGIN > SHEET_H:
            new_page()
        return MARGIN, y

    new_page(first=True)
    line_c, mark_c, _soft = _geo_inks(theme)

    # ---- Icon grid: 7 columns ------------------------------------------
    cols, cell, gap = 7, 24.0, 2.6
    per_row = cols
    for i, name in enumerate(_ICON_NAMES):
        col = i % per_row
        if col == 0:
            _x, row_y = cell_rect(cell, cell + gap)
            y = row_y + cell + gap
        x = MARGIN + col * (cell + gap)
        # Cut guide OUTSIDE the recorded rect
        pdf.set_draw_color(*theme.rule_c())
        pdf.set_line_width(0.15)
        pdf.rect(x - 0.8, row_y - 0.8, cell + 1.6, cell + 1.6, style="D")
        cx, cy = x + cell / 2, row_y + cell / 2
        r = cell * 0.34
        _icon_fn(name)(pdf, cx, cy, r, line_c, mark_c, _icon_lw(r))
        cells.append((page_no, (x, row_y, cell, cell), name))

    # ---- Weekday + label chips: 3 per row ------------------------------
    chip_w, chip_h = 58.0, 11.0
    chips = [*WEEKDAY_CHIPS, *LABEL_CHIPS]
    for i, label in enumerate(chips):
        col = i % 3
        if col == 0:
            _x, row_y = cell_rect(chip_w, chip_h + gap)
            y = row_y + chip_h + gap
        x = MARGIN + col * (chip_w + gap * 3)
        pdf.set_draw_color(*theme.rule_c())
        pdf.set_line_width(0.15)
        pdf.rect(x - 0.8, row_y - 0.8, chip_w + 1.6, chip_h + 1.6, style="D")
        _chip(pdf, theme, x, row_y, chip_w, chip_h, label)
        slug = label.lower().replace(" ", "_")
        cells.append((page_no, (x, row_y, chip_w, chip_h), f"chip_{slug}"))

    # ---- Habit-tracker strips: 1 per row --------------------------------
    strip_w, strip_h = 80.0, 12.0
    for kind in _STRIPS:
        _x, row_y = cell_rect(strip_w, strip_h + gap)
        y = row_y + strip_h + gap
        x = MARGIN
        pdf.set_draw_color(*theme.rule_c())
        pdf.set_line_width(0.15)
        pdf.rect(x - 0.8, row_y - 0.8, strip_w + 1.6, strip_h + 1.6, style="D")
        _draw_strip(pdf, theme, kind, x, row_y, strip_w, strip_h)
        cells.append((page_no, (x, row_y, strip_w, strip_h), kind))

    sheet_pdf = out_dir / f"Digital_Stickers_{palette_name}.pdf"
    pdf.output(str(sheet_pdf))

    # ---- Rasterize each cell to a pre-cropped transparent PNG ----------
    png_paths: list[Path] = []
    if include_pngs:
        png_dir = out_dir / palette_name
        png_dir.mkdir(parents=True, exist_ok=True)
        doc = fitz.open(str(sheet_pdf))
        zoom = DPI / 72.0
        for idx, (pno, (x, ry, w, h), name) in enumerate(cells):
            clip = fitz.Rect(x * _MM_TO_PT, ry * _MM_TO_PT,
                             (x + w) * _MM_TO_PT, (ry + h) * _MM_TO_PT)
            pix = doc[pno].get_pixmap(
                matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=True
            )
            png_path = png_dir / f"{idx + 1:02d}_{name}.png"
            pix.save(str(png_path))
            png_paths.append(png_path)
        doc.close()

    logger.info(
        "sticker_assets_generated",
        palette=palette_name,
        count=len(cells),
        pngs=len(png_paths),
        sheet=str(sheet_pdf),
    )
    return StickerAssets(palette=palette_name, sheet_pdf=sheet_pdf,
                         png_paths=png_paths)
