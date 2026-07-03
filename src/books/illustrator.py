"""Shared drawing toolkit for the picture-book illustration engine.

Contains:

- :class:`BookPalette` -- kid-friendly color scheme loaded from
  ``config/books.yaml`` (with built-in fallbacks so drawing never crashes).
- :class:`Draw` -- a thin wrapper over an ``FPDF`` instance that renders
  kawaii flat-vector primitives.  When constructed with ``line_art=True``
  every fill becomes white and every outline black, so the exact same
  character/scene code produces printable coloring pages.
- Font management -- downloads the 'Baloo 2' variable font at runtime,
  instances static Regular/Bold weights with fontTools, and falls back to
  Fredoka, Quicksand, then Helvetica.  Never crashes offline.
- Text panel helper for the rounded semi-opaque story-text boxes.
"""

from __future__ import annotations

import math
import urllib.request
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import structlog
import yaml
from fpdf import FPDF

logger = structlog.get_logger()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BOOKS_CONFIG_PATH = PROJECT_ROOT / "config" / "books.yaml"
FONTS_DIR = Path(__file__).resolve().parent / "fonts"

RGB = tuple[int, int, int]

# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------


def hex_to_rgb(hex_color: str) -> RGB:
    """Convert ``'#RRGGBB'`` to an ``(r, g, b)`` tuple."""
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def mix(a: RGB, b: RGB, t: float) -> RGB:
    """Linear blend between two colors (t=0 -> a, t=1 -> b)."""
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def darken(c: RGB, t: float = 0.2) -> RGB:
    """Darken a color toward black by fraction *t*."""
    return mix(c, (0, 0, 0), t)


def lighten(c: RGB, t: float = 0.2) -> RGB:
    """Lighten a color toward white by fraction *t*."""
    return mix(c, (255, 255, 255), t)


# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BookPalette:
    """A complete color scheme for one picture book."""

    key: str
    name: str
    sky_top: RGB
    sky_bottom: RGB
    sun: RGB
    cloud: RGB
    hill: RGB
    ground: RGB
    ground_dark: RGB
    water: RGB
    accent: RGB
    accent2: RGB
    panel: RGB
    text: RGB


_FALLBACK_PALETTE = {
    "name": "Sunny Day",
    "sky_top": "#8ED8F2",
    "sky_bottom": "#DFF6FD",
    "sun": "#FFD35C",
    "cloud": "#FFFFFF",
    "hill": "#B9E48A",
    "ground": "#9FD86B",
    "ground_dark": "#7CBF4E",
    "water": "#5FC5DE",
    "accent": "#FF9F4A",
    "accent2": "#FF7B9C",
    "panel": "#FFFFFF",
    "text": "#4A3B57",
}

_book_config_cache: dict | None = None


def load_book_config() -> dict:
    """Load and cache ``config/books.yaml`` (empty dict when missing)."""
    global _book_config_cache
    if _book_config_cache is None:
        try:
            with open(BOOKS_CONFIG_PATH) as fh:
                _book_config_cache = yaml.safe_load(fh) or {}
        except OSError:
            logger.warning("books_yaml_missing", path=str(BOOKS_CONFIG_PATH))
            _book_config_cache = {}
    return _book_config_cache


def get_book_palette(name: str) -> BookPalette:
    """Return a :class:`BookPalette` by key, falling back to sunny_day."""
    palettes = (load_book_config().get("book_params") or {}).get("palettes") or {}
    raw = palettes.get(name)
    if raw is None:
        logger.warning("unknown_book_palette", palette=name)
        raw = palettes.get("sunny_day") or _FALLBACK_PALETTE
        name = "sunny_day"
    merged = {**_FALLBACK_PALETTE, **raw}
    return BookPalette(
        key=name,
        name=merged["name"],
        **{
            field: hex_to_rgb(merged[field])
            for field in (
                "sky_top", "sky_bottom", "sun", "cloud", "hill", "ground",
                "ground_dark", "water", "accent", "accent2", "panel", "text",
            )
        },
    )


def list_palette_names() -> list[str]:
    """All palette keys defined in books.yaml (sorted, stable)."""
    palettes = (load_book_config().get("book_params") or {}).get("palettes") or {}
    return sorted(palettes.keys()) or ["sunny_day"]


# ---------------------------------------------------------------------------
# Draw -- kawaii primitive renderer with a line-art mode
# ---------------------------------------------------------------------------

OUTLINE_COLOR: RGB = (45, 42, 51)


class Draw:
    """Wraps FPDF drawing primitives with fill/line-art awareness.

    In normal mode shapes are filled with their given color (optionally
    outlined).  In ``line_art`` mode every fill becomes white and every
    stroke black, producing clean coloring-page outlines while keeping
    z-order occlusion correct.
    """

    def __init__(self, pdf: FPDF, line_art: bool = False):
        self.pdf = pdf
        self.line_art = line_art
        self._round_caps()

    def _round_caps(self) -> None:
        """Use round line caps/joins so strokes look soft (limbs, smiles)."""
        try:
            self.pdf._out("1 J 1 j")
        except Exception:  # pragma: no cover - cosmetic only
            pass

    # -- style plumbing ----------------------------------------------------

    def _apply(
        self,
        fill: RGB | None,
        stroke: RGB | None,
        lw: float,
        force_fill: bool = False,
    ) -> str:
        """Set colors/width on the pdf; return the fpdf style string.

        ``force_fill`` keeps a (black) solid fill even in line-art mode --
        used for pupils and mouths so coloring-page faces stay readable.
        """
        if self.line_art:
            if fill is not None:
                fill = (30, 30, 30) if force_fill else (255, 255, 255)
            stroke = (30, 30, 30)
            lw = min(max(lw, 0.55), 1.3)  # cap: thick color strokes stay outlines
        style = ""
        if fill is not None:
            self.pdf.set_fill_color(*fill)
            style += "F"
        if stroke is not None:
            self.pdf.set_draw_color(*stroke)
            self.pdf.set_line_width(lw)
            style += "D"
        self._round_caps()
        return style or "D"

    # -- primitives ----------------------------------------------------------

    def ellipse(
        self,
        cx: float,
        cy: float,
        rx: float,
        ry: float,
        fill: RGB | None = None,
        stroke: RGB | None = None,
        lw: float = 0.5,
        force_fill: bool = False,
    ) -> None:
        """Ellipse centered at (cx, cy) with radii rx, ry."""
        style = self._apply(fill, stroke, lw, force_fill=force_fill)
        self.pdf.ellipse(cx - rx, cy - ry, rx * 2, ry * 2, style=style)

    def circle(
        self,
        cx: float,
        cy: float,
        r: float,
        fill: RGB | None = None,
        stroke: RGB | None = None,
        lw: float = 0.5,
        force_fill: bool = False,
    ) -> None:
        self.ellipse(cx, cy, r, r, fill=fill, stroke=stroke, lw=lw, force_fill=force_fill)

    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        fill: RGB | None = None,
        stroke: RGB | None = None,
        lw: float = 0.5,
        radius: float = 0.0,
    ) -> None:
        style = self._apply(fill, stroke, lw)
        if radius > 0:
            self.pdf.rect(x, y, w, h, style=style, round_corners=True, corner_radius=radius)
        else:
            self.pdf.rect(x, y, w, h, style=style)

    def polygon(
        self,
        points: list[tuple[float, float]],
        fill: RGB | None = None,
        stroke: RGB | None = None,
        lw: float = 0.5,
    ) -> None:
        style = self._apply(fill, stroke, lw)
        self.pdf.polygon(points, style=style)

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        color: RGB = OUTLINE_COLOR,
        lw: float = 0.8,
    ) -> None:
        self._apply(None, color, lw)
        self.pdf.line(x1, y1, x2, y2)

    def polyline(
        self,
        points: list[tuple[float, float]],
        color: RGB = OUTLINE_COLOR,
        lw: float = 0.8,
    ) -> None:
        self._apply(None, color, lw)
        self.pdf.polyline(points, style="D")

    def arc(
        self,
        cx: float,
        cy: float,
        r: float,
        start_deg: float,
        end_deg: float,
        color: RGB = OUTLINE_COLOR,
        lw: float = 0.8,
        ry: float | None = None,
        segments: int = 24,
    ) -> None:
        """Stroked arc via many-segment polyline (round caps).

        Angles in degrees; 0 = +x axis, positive = clockwise in page space
        (y grows downward, so 0..180 sweeps the *bottom* half -- a smile).
        """
        ry = r if ry is None else ry
        pts = []
        for i in range(segments + 1):
            a = math.radians(start_deg + (end_deg - start_deg) * i / segments)
            pts.append((cx + r * math.cos(a), cy + ry * math.sin(a)))
        self.polyline(pts, color=color, lw=lw)

    def dot(self, cx: float, cy: float, r: float, color: RGB) -> None:
        """Small filled circle (never outlined; skipped in line-art if tiny)."""
        if self.line_art and r < 0.6:
            return
        self.circle(cx, cy, r, fill=color if not self.line_art else None,
                    stroke=(30, 30, 30) if self.line_art else None, lw=0.4)

    def blush(self, cx: float, cy: float, r: float, color: RGB = (250, 160, 160)) -> None:
        """Soft blush ellipse -- omitted entirely on coloring pages."""
        if self.line_art:
            return
        with self.pdf.local_context(fill_opacity=0.45):
            self.ellipse(cx, cy, r, r * 0.62, fill=color)

    def soft_shadow(self, cx: float, cy: float, rx: float, ry: float) -> None:
        """Soft ground shadow under a character."""
        if self.line_art:
            return
        with self.pdf.local_context(fill_opacity=0.15):
            self.ellipse(cx, cy, rx, ry, fill=(40, 40, 60))


# ---------------------------------------------------------------------------
# Fonts -- Baloo 2 (variable -> static instances), Fredoka/Quicksand fallback
# ---------------------------------------------------------------------------

_FONT_SOURCES = [
    # (family, variable-font URL, regular axis value, bold axis value)
    ("Baloo2",
     "https://raw.githubusercontent.com/google/fonts/main/ofl/baloo2/Baloo2%5Bwght%5D.ttf",
     400, 700),
    ("Fredoka",
     "https://raw.githubusercontent.com/google/fonts/main/ofl/fredoka/Fredoka%5Bwdth,wght%5D.ttf",
     400, 600),
    ("Quicksand",
     "https://raw.githubusercontent.com/google/fonts/main/ofl/quicksand/Quicksand%5Bwght%5D.ttf",
     400, 700),
]


def _instance_static(data: bytes, weight: int) -> bytes:
    """Instance a static weight from variable-font bytes using fontTools."""
    from fontTools import ttLib
    from fontTools.varLib.instancer import instantiateVariableFont

    font = ttLib.TTFont(BytesIO(data))
    axes = {a.axisTag: a.defaultValue for a in font["fvar"].axes}
    axes["wght"] = weight
    instantiateVariableFont(font, axes, inplace=True)
    buf = BytesIO()
    font.save(buf)
    return buf.getvalue()


def fonts_present() -> bool:
    """True when a Regular + Bold pair already exists in ``fonts/``."""
    return (FONTS_DIR / "Book-Regular.ttf").is_file() and (
        FONTS_DIR / "Book-Bold.ttf"
    ).is_file()


def download_book_fonts() -> bool:
    """Fetch a friendly rounded font and write static Regular/Bold TTFs.

    Tries Baloo 2 first, then Fredoka, then Quicksand.  Returns True on
    success; never raises (caller falls back to Helvetica).
    """
    if fonts_present():
        return True
    FONTS_DIR.mkdir(parents=True, exist_ok=True)

    for family, url, reg_w, bold_w in _FONT_SOURCES:
        try:
            logger.info("downloading_book_font", family=family, url=url)
            req = urllib.request.Request(url, headers={"User-Agent": "etsy-planner-bot/0.1"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            (FONTS_DIR / "Book-Regular.ttf").write_bytes(_instance_static(data, reg_w))
            (FONTS_DIR / "Book-Bold.ttf").write_bytes(_instance_static(data, bold_w))
            logger.info("book_fonts_ready", family=family)
            return True
        except Exception as exc:
            logger.warning("book_font_download_failed", family=family, error=str(exc))
    return False


def setup_book_fonts(pdf: FPDF) -> str:
    """Embed the book font family into *pdf*; return the family name to use.

    Falls back to Helvetica if fonts cannot be downloaded or embedded.
    """
    if not fonts_present():
        download_book_fonts()
    if fonts_present():
        try:
            pdf.add_font("BookFont", "", str(FONTS_DIR / "Book-Regular.ttf"))
            pdf.add_font("BookFont", "B", str(FONTS_DIR / "Book-Bold.ttf"))
            return "BookFont"
        except Exception:
            logger.warning("book_font_embed_failed_falling_back", exc_info=True)
    return "Helvetica"


# ---------------------------------------------------------------------------
# Text panel
# ---------------------------------------------------------------------------


def sanitize_for_font(text: str, font_family: str) -> str:
    """Replace curly quotes/dashes when stuck on a core (latin-1) font."""
    if font_family.lower() not in ("helvetica", "times", "courier"):
        return text
    replacements = {
        "“": '"', "”": '"', "‘": "'", "’": "'",
        "—": "-", "–": "-", "…": "...", "~": "-",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text


def draw_text_panel(
    pdf: FPDF,
    font_family: str,
    text: str,
    x: float,
    y: float,
    w: float,
    font_size: float,
    text_color: RGB,
    panel_color: RGB = (255, 255, 255),
    opacity: float = 0.85,
    padding: float = 9.0,
    line_height: float = 1.45,
    align: str = "C",
    measure_only: bool = False,
) -> float:
    """Rounded semi-opaque panel with centered, wrapped story text.

    Returns the panel height so callers can stack elements around it.
    With ``measure_only=True`` nothing is drawn.
    """
    text = sanitize_for_font(text, font_family)
    pdf.set_font(font_family, "", font_size)
    inner_w = w - 2 * padding
    line_h = font_size * 0.3528 * line_height
    lines = pdf.multi_cell(
        inner_w, line_h, text, align=align, dry_run=True, output="LINES",
    )
    panel_h = len(lines) * line_h + 2 * padding
    if measure_only:
        return panel_h

    with pdf.local_context(fill_opacity=opacity):
        pdf.set_fill_color(*panel_color)
        pdf.rect(x, y, w, panel_h, style="F", round_corners=True, corner_radius=6.5)

    pdf.set_text_color(*text_color)
    pdf.set_xy(x + padding, y + padding)
    pdf.multi_cell(inner_w, line_h, text, align=align)
    return panel_h
