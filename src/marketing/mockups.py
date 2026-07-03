"""Etsy listing image composer.

Renders pages from a product PDF (planner or picture book) with pymupdf and
composes five professional 2700x2025 (4:3) listing images with Pillow:

  1. Hero          -- cover angled on a soft palette-tinted background
  2. Interiors     -- fanned interior pages
  3. Close-up      -- one key page large with a feature callout strip
  4. What's inside -- palette panel listing the sections
  5. Compatibility -- device-framed cover + format badges

Never crashes on missing fonts (falls back to PIL defaults) and works for
both landscape planners and square picture books.
"""

from __future__ import annotations

import math
from pathlib import Path

import structlog
from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = structlog.get_logger()

CANVAS_W, CANVAS_H = 2700, 2025

_FONTS_DIR = Path(__file__).resolve().parent.parent / "planner" / "fonts"

_FALLBACK_PALETTE = {
    "background": (250, 246, 241),
    "primary": (139, 115, 85),
    "secondary": (196, 168, 130),
    "accent": (212, 165, 116),
    "text": (61, 48, 36),
    "text_light": (139, 115, 85),
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _blend(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(a + (b - a) * t) for a, b in zip(c1, c2))  # type: ignore[return-value]


def _palette_colors(palette_name: str | None) -> dict[str, tuple[int, int, int]]:
    """Resolve palette RGB values; never raises."""
    if palette_name:
        try:
            from src.planner.styles import get_palette

            pal = get_palette(palette_name)
            return {
                key: pal.rgb(key)
                for key in ("background", "primary", "secondary", "accent",
                            "text", "text_light")
            }
        except Exception:
            logger.warning("unknown_palette_for_mockups", palette=palette_name)
    return dict(_FALLBACK_PALETTE)


def _palette_display_name(name: str) -> str:
    """Human label for a palette (e.g. 'ocean_blue' -> 'Ocean Blue')."""
    try:
        from src.planner.styles import get_palette

        return get_palette(name).name
    except Exception:
        return name.replace("_", " ").replace("-", " ").title()


def _bundle_palettes(palettes: list[str] | None, hero: str | None) -> list[str]:
    """De-duplicated palette list (hero first) when this is a colour bundle.

    Returns ``[]`` for single-palette planners and picture books (fewer than
    two distinct palettes), which keeps their listing images unchanged.
    """
    if not palettes:
        return []
    ordered: list[str] = []
    for p in palettes:
        if p and p not in ordered:
            ordered.append(p)
    if len(ordered) < 2:
        return []
    if hero and hero in ordered:
        ordered = [hero] + [p for p in ordered if p != hero]
    return ordered


def _design_label(design_name: str | None) -> str | None:
    """Human label for a non-classic design theme; never raises.

    Classic (the historical look) gets no label so its listing images are
    unchanged; preset ids resolve through the design registry so repaired
    or unknown names collapse sensibly.
    """
    if not design_name:
        return None
    name = design_name
    try:
        from src.planner.designs import get_design

        name = get_design(design_name).name
    except Exception:
        logger.warning("design_registry_unavailable_for_mockups", design=design_name)
    if name == "classic":
        return None
    if name.startswith("custom-"):
        return "Custom"
    return name.replace("-", " ").replace("_", " ").title()


def _font(size: int, *, bold: bool = False, serif: bool = False) -> ImageFont.ImageFont:
    """Load a bundled TTF; fall back to the PIL default font."""
    candidates = []
    if serif:
        candidates += [_FONTS_DIR / "DisplaySerif-Bold.ttf",
                       _FONTS_DIR / "DisplaySerif-Regular.ttf"]
    candidates += [
        _FONTS_DIR / ("Inter-Bold.ttf" if bold else "Inter-Regular.ttf"),
        _FONTS_DIR / "Inter-Regular.ttf",
    ]
    for cand in candidates:
        try:
            if cand.is_file():
                return ImageFont.truetype(str(cand), size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size)
    except Exception:
        return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def _fit_font(draw: ImageDraw.ImageDraw, text: str, max_w: int, start: int,
              *, bold: bool = False, serif: bool = False, min_size: int = 28):
    size = start
    while size > min_size:
        font = _font(size, bold=bold, serif=serif)
        if _text_size(draw, text, font)[0] <= max_w:
            return font
        size -= 6
    return _font(min_size, bold=bold, serif=serif)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if _text_size(draw, trial, font)[0] <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def _render_page(doc, index: int, target_w: int) -> Image.Image:
    """Rasterize one PDF page to a PIL image *target_w* pixels wide."""
    import fitz  # noqa: F401 (import kept local so module import never fails)

    index = max(0, min(index, len(doc) - 1))
    page = doc[index]
    zoom = target_w / page.rect.width
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def _make_background(palette: dict) -> Image.Image:
    """Soft warm background: tinted base + big blurred palette blobs."""
    base = _blend(palette["background"], (255, 255, 255), 0.35)
    img = Image.new("RGB", (CANVAS_W, CANVAS_H), base)

    blobs = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(blobs)
    specs = [
        ((-350, -450, 900, 800), palette["secondary"], 70),
        ((CANVAS_W - 800, CANVAS_H - 700, CANVAS_W + 350, CANVAS_H + 400),
         palette["accent"], 60),
        ((CANVAS_W - 650, -400, CANVAS_W + 400, 500), palette["primary"], 40),
    ]
    for box, color, alpha in specs:
        bd.ellipse(box, fill=color + (alpha,))
    blobs = blobs.filter(ImageFilter.GaussianBlur(120))
    img.paste(blobs, (0, 0), blobs)
    return img


def _paste_with_shadow(canvas: Image.Image, page: Image.Image,
                       center: tuple[int, int], angle: float = 0.0,
                       border: bool = True) -> None:
    """Paste *page* rotated with a soft drop shadow."""
    if border:
        bordered = Image.new("RGB", (page.width + 8, page.height + 8),
                             (255, 255, 255))
        bordered.paste(page, (4, 4))
        page = bordered

    rgba = page.convert("RGBA")
    if angle:
        rgba = rgba.rotate(angle, expand=True, resample=Image.BICUBIC)

    # Shadow from the alpha silhouette
    shadow = Image.new("RGBA", (rgba.width + 120, rgba.height + 120), (0, 0, 0, 0))
    sil = Image.new("RGBA", rgba.size, (25, 18, 12, 110))
    shadow.paste(sil, (60, 60), rgba.split()[3])
    shadow = shadow.filter(ImageFilter.GaussianBlur(28))

    sx = center[0] - shadow.width // 2 + 14
    sy = center[1] - shadow.height // 2 + 26
    canvas.paste(shadow, (sx, sy), shadow)

    px = center[0] - rgba.width // 2
    py = center[1] - rgba.height // 2
    canvas.paste(rgba, (px, py), rgba)


def _badge(canvas: Image.Image, text: str, center_x: int, y: int,
           fill: tuple[int, int, int], text_color=(255, 255, 255),
           font_size: int = 52, pad_x: int = 46, pad_y: int = 24) -> None:
    draw = ImageDraw.Draw(canvas)
    font = _font(font_size, bold=True)
    tw, th = _text_size(draw, text, font)
    w, h = tw + pad_x * 2, th + pad_y * 2
    x = center_x - w // 2
    draw.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=fill)
    draw.text((center_x - tw // 2, y + pad_y - font_size * 0.12), text,
              font=font, fill=text_color)


def _swatch_chip(draw: ImageDraw.ImageDraw, x: int, y: int, size: int,
                 cols: dict, *, radius: int | None = None) -> None:
    """Draw one palette swatch: a rounded tile banded with its key colours."""
    radius = radius if radius is not None else max(8, size // 5)
    draw.rounded_rectangle([x, y, x + size, y + size], radius=radius,
                           fill=cols["primary"])
    # Bottom band of accent (reads as a two-tone swatch).
    band_top = y + int(size * 0.62)
    draw.rectangle([x, band_top, x + size, y + size - radius], fill=cols["accent"])
    # Redraw the rounded outline on top so the corners stay clean.
    draw.rounded_rectangle([x, y, x + size, y + size], radius=radius,
                           outline=(255, 255, 255), width=max(3, size // 22))


def _color_options_strip(canvas: Image.Image, palettes: list[str], x: int, y: int,
                         base_palette: dict, *, chip: int = 92, gap: int = 22) -> None:
    """Hero overlay: 'N color options included' + a row of palette swatches."""
    draw = ImageDraw.Draw(canvas)
    label = f"{len(palettes)} color options included"
    lfont = _font(44, bold=True)
    draw.text((x, y), label.upper(), font=lfont,
              fill=_blend(base_palette["text"], base_palette["primary"], 0.25))
    row_y = y + 70
    for i, name in enumerate(palettes):
        cx = x + i * (chip + gap)
        _swatch_chip(draw, cx, row_y, chip, _palette_colors(name))


# ---------------------------------------------------------------------------
# Page selection
# ---------------------------------------------------------------------------

def _select_pages(n_pages: int, product_type: str) -> dict[str, list[int] | int]:
    """Pick page indices for each mockup composition."""
    if product_type == "picture_book":
        interiors = [i for i in (1, 2, 4, 6) if i < n_pages]
        closeup = 3 if n_pages > 3 else n_pages - 1
    else:
        # planner: 0 cover, 1 index, 2 year glance, 3 monthly; niche pages
        # sit just before the closing 3 generic pages.
        niche_start = max(4, n_pages - 9)
        interiors = [1, 2, 3, niche_start]
        interiors = [i for i in interiors if i < n_pages]
        closeup = 3 if n_pages > 3 else n_pages - 1
    return {"interiors": interiors, "closeup": closeup}


# ---------------------------------------------------------------------------
# Composition 1: hero
# ---------------------------------------------------------------------------

def _compose_hero(doc, palette: dict, title: str, product_type: str,
                  design_label: str | None = None,
                  bundle_palettes: list[str] | None = None) -> Image.Image:
    canvas = _make_background(palette)
    draw = ImageDraw.Draw(canvas)

    cover = _render_page(doc, 0, 1500)
    max_h = 1560
    if cover.height > max_h:
        cover = cover.resize((round(cover.width * max_h / cover.height), max_h),
                             Image.LANCZOS)
    _paste_with_shadow(canvas, cover, (CANVAS_W - 870, CANVAS_H // 2 + 40),
                       angle=-4)

    # Left text block
    tx, max_w = 170, 780
    kicker = ("DIGITAL PLANNER" if product_type == "planner"
              else "ILLUSTRATED STORYBOOK")
    kfont = _font(54, bold=True)
    draw.text((tx, 500), kicker, font=kfont,
              fill=_blend(palette["primary"], palette["text"], 0.2))

    tfont = _font(120, bold=True, serif=True)
    lines = _wrap(draw, title, tfont, max_w)
    if len(lines) > 3:
        tfont = _font(95, bold=True, serif=True)
        lines = _wrap(draw, title, tfont, max_w)[:4]
    y = 600
    for ln in lines:
        draw.text((tx, y), ln, font=tfont, fill=palette["text"])
        y += int(tfont.size * 1.18)

    sub = ("Hyperlinked · iPad & Tablet Ready" if product_type == "planner"
           else "Print at Home · Read on Any Screen")
    draw.text((tx, y + 40), sub, font=_font(56),
              fill=_blend(palette["text"], palette["primary"], 0.4))

    _badge(canvas, "INSTANT DOWNLOAD", tx + 300, y + 190, palette["primary"])
    if design_label:
        _badge(canvas, f"{design_label.upper()} THEME", tx + 300, y + 316,
               _blend(palette["secondary"], palette["text"], 0.35), font_size=44)

    # Multi-palette bundle: sell the colour choice with a swatch strip.
    if bundle_palettes:
        _color_options_strip(canvas, bundle_palettes, tx, CANVAS_H - 250, palette)
    return canvas


# ---------------------------------------------------------------------------
# Composition 2: interior fan
# ---------------------------------------------------------------------------

def _compose_interiors(doc, palette: dict, indices: list[int],
                       product_type: str) -> Image.Image:
    canvas = _make_background(palette)
    draw = ImageDraw.Draw(canvas)

    heading = ("TAKE A LOOK INSIDE" if product_type == "planner"
               else "A PEEK BETWEEN THE PAGES")
    hfont = _font(84, bold=True, serif=True)
    tw, _ = _text_size(draw, heading, hfont)
    draw.text(((CANVAS_W - tw) // 2, 130), heading, font=hfont,
              fill=palette["text"])

    shown = indices[:4]
    n = len(shown)
    page_w = 1050 if n >= 4 else 1200
    margin = 200
    angles = [7, 2.5, -2.5, -7][:n]
    if n > 1:
        first_cx = margin + page_w // 2
        last_cx = CANVAS_W - margin - page_w // 2
        step = (last_cx - first_cx) / (n - 1)
    else:
        first_cx, step = CANVAS_W // 2, 0
    for i, idx in enumerate(shown):
        img = _render_page(doc, idx, page_w)
        cx = round(first_cx + i * step)
        cy = CANVAS_H // 2 + 160 + (28 if i % 2 else -28)
        _paste_with_shadow(canvas, img, (cx, cy), angle=angles[i])

    note = ("Fully linked tabs · 12 months · niche tracker pages"
            if product_type == "planner" else
            "Story spreads · Includes coloring pages")
    _badge(canvas, note, CANVAS_W // 2, CANVAS_H - 170,
           _blend(palette["primary"], palette["text"], 0.1), font_size=46)
    return canvas


# ---------------------------------------------------------------------------
# Composition 3: close-up + callout
# ---------------------------------------------------------------------------

def _compose_closeup(doc, palette: dict, index: int,
                     product_type: str) -> Image.Image:
    canvas = _make_background(palette)
    draw = ImageDraw.Draw(canvas)

    strip_h = 240
    page = _render_page(doc, index, 2300)
    avail_h = CANVAS_H - strip_h - 240
    if page.height > avail_h:
        page = page.resize((round(page.width * avail_h / page.height), avail_h),
                           Image.LANCZOS)
    _paste_with_shadow(canvas, page, (CANVAS_W // 2, (CANVAS_H - strip_h) // 2 + 20))

    # Callout strip
    strip_y = CANVAS_H - strip_h
    draw.rectangle([0, strip_y, CANVAS_W, CANVAS_H], fill=palette["primary"])
    text = ("Tap any tab or date — every page is hyperlinked"
            if product_type == "planner"
            else "Bright, friendly art on every spread")
    font = _fit_font(draw, text, CANVAS_W - 300, 72, bold=True)
    tw, th = _text_size(draw, text, font)
    draw.text(((CANVAS_W - tw) // 2, strip_y + (strip_h - th) // 2 - 10),
              text, font=font, fill=(255, 255, 255))
    return canvas


# ---------------------------------------------------------------------------
# Composition 4: what's inside
# ---------------------------------------------------------------------------

def _whats_inside_items(product_type: str) -> list[str]:
    if product_type == "picture_book":
        return [
            "Full illustrated story",
            "Includes coloring pages",
            "Square premium layout",
            "Print at home or read on screen",
            "High-resolution PDF",
        ]
    return [
        "12 monthly calendars & plans",
        "52 weekly spreads",
        "Year at a glance + index",
        "Niche tracker section",
        "Habit, goal & notes pages",
        "Hyperlinked tabs throughout",
    ]


def _compose_whats_inside(doc, palette: dict, title: str,
                          product_type: str) -> Image.Image:
    canvas = _make_background(palette)
    draw = ImageDraw.Draw(canvas)

    # Left: colored panel with the section list
    panel = (140, 160, 1400, CANVAS_H - 160)
    draw.rounded_rectangle(panel, radius=48,
                           fill=_blend(palette["primary"], (255, 255, 255), 0.06))
    hfont = _font(96, bold=True, serif=True)
    draw.text((panel[0] + 100, panel[1] + 110), "What's Inside", font=hfont,
              fill=(255, 255, 255))
    draw.line([panel[0] + 100, panel[1] + 260, panel[0] + 620, panel[1] + 260],
              fill=_blend(palette["accent"], (255, 255, 255), 0.4), width=6)

    ifont = _font(58)
    y = panel[1] + 340
    for item in _whats_inside_items(product_type):
        cy = y + 30
        draw.ellipse([panel[0] + 100, cy - 12, panel[0] + 124, cy + 12],
                     fill=_blend(palette["accent"], (255, 255, 255), 0.5))
        draw.text((panel[0] + 160, y), item, font=ifont, fill=(255, 255, 255))
        y += 118

    # Right: cover + one interior, stacked with slight angles
    cover = _render_page(doc, 0, 1050)
    max_h = 900
    if cover.height > max_h:
        cover = cover.resize((round(cover.width * max_h / cover.height), max_h),
                             Image.LANCZOS)
    _paste_with_shadow(canvas, cover, (2020, 640), angle=3)
    interior = _render_page(doc, min(3, len(doc) - 1), 1050)
    if interior.height > max_h:
        interior = interior.resize(
            (round(interior.width * max_h / interior.height), max_h), Image.LANCZOS)
    _paste_with_shadow(canvas, interior, (2080, 1420), angle=-3)
    return canvas


# ---------------------------------------------------------------------------
# Composition 5: compatibility / format badges
# ---------------------------------------------------------------------------

def _compose_compat(doc, palette: dict, product_type: str) -> Image.Image:
    canvas = _make_background(palette)
    draw = ImageDraw.Draw(canvas)

    heading = "WORKS EVERYWHERE YOU PLAN" if product_type == "planner" \
        else "READY FOR SCREENS & PRINT"
    hfont = _font(80, bold=True, serif=True)
    tw, _ = _text_size(draw, heading, hfont)
    draw.text(((CANVAS_W - tw) // 2, 120), heading, font=hfont,
              fill=palette["text"])

    # Device frame (tablet-ish rounded rect) around the cover render
    cover = _render_page(doc, 0, 1500)
    max_h = 1150
    if cover.height > max_h:
        cover = cover.resize((round(cover.width * max_h / cover.height), max_h),
                             Image.LANCZOS)
    bezel = 46
    frame = Image.new("RGBA", (cover.width + bezel * 2, cover.height + bezel * 2),
                      (0, 0, 0, 0))
    fd = ImageDraw.Draw(frame)
    fd.rounded_rectangle([0, 0, frame.width - 1, frame.height - 1], radius=64,
                         fill=(38, 36, 40, 255))
    fd.rounded_rectangle([10, 10, frame.width - 11, frame.height - 11], radius=56,
                         outline=(90, 88, 96, 255), width=4)
    frame.paste(cover, (bezel, bezel))
    # camera dot
    fd.ellipse([frame.width // 2 - 8, 14, frame.width // 2 + 8, 30],
               fill=(90, 88, 96, 255))
    _paste_with_shadow(canvas, frame.convert("RGB"),
                       (CANVAS_W // 2, CANVAS_H // 2 + 60), border=False)

    badges = (["iPad", "GoodNotes", "Notability", "Letter & A4 printable"]
              if product_type == "planner"
              else ["iPad & tablets", "Phone & desktop", "Letter & A4 printable",
                    "Includes coloring pages"])
    bfont = _font(48, bold=True)
    total_w = 0
    gaps = 60
    sizes = []
    for b in badges:
        tw, th = _text_size(draw, b, bfont)
        sizes.append((tw + 92, th + 48))
        total_w += tw + 92
    total_w += gaps * (len(badges) - 1)
    x = (CANVAS_W - total_w) // 2
    y = CANVAS_H - 230
    for b, (w, h) in zip(badges, sizes):
        draw.rounded_rectangle([x, y, x + w, y + h], radius=h // 2,
                               fill=(255, 255, 255),
                               outline=palette["primary"], width=4)
        tw, th = _text_size(draw, b, bfont)
        draw.text((x + (w - tw) // 2, y + (h - th) // 2 - 10), b, font=bfont,
                  fill=_blend(palette["text"], palette["primary"], 0.3))
        x += w + gaps
    return canvas


# ---------------------------------------------------------------------------
# Composition: colour options (palette bundle only)
# ---------------------------------------------------------------------------

def _compose_color_options(doc, palette: dict, palettes: list[str],
                           title: str) -> Image.Image:
    """Dedicated listing image: the cover shown in every bundled palette.

    Each palette gets a card pairing the cover render with that palette's
    key colours and its name, so buyers see exactly what colours ship in the
    one download.
    """
    canvas = _make_background(palette)
    draw = ImageDraw.Draw(canvas)

    n = len(palettes)
    heading = f"{n} COLOR OPTIONS INCLUDED"
    hfont = _font(84, bold=True, serif=True)
    tw, _ = _text_size(draw, heading, hfont)
    draw.text(((CANVAS_W - tw) // 2, 110), heading, font=hfont,
              fill=palette["text"])
    sub = "One purchase — every colour below is in your download"
    sfont = _font(46)
    tw2, _ = _text_size(draw, sub, sfont)
    draw.text(((CANVAS_W - tw2) // 2, 224), sub, font=sfont,
              fill=_blend(palette["text"], palette["primary"], 0.4))

    # Grid geometry: up to 3 cards per row.
    cols = min(n, 3)
    rows = math.ceil(n / cols)
    top = 340
    outer = 150
    gap = 60
    grid_w = CANVAS_W - outer * 2
    grid_h = CANVAS_H - top - 120
    card_w = (grid_w - gap * (cols - 1)) // cols
    card_h = (grid_h - gap * (rows - 1)) // rows

    # One cover render, reused (real recolouring lives in each palette's PDF).
    cover = _render_page(doc, 0, card_w)
    cover_max_h = int(card_h * 0.6)
    if cover.height > cover_max_h:
        cover = cover.resize(
            (round(cover.width * cover_max_h / cover.height), cover_max_h),
            Image.LANCZOS)

    nfont = _font(46, bold=True)
    for i, name in enumerate(palettes):
        r, c = divmod(i, cols)
        # Centre the last, possibly short, row.
        in_row = min(cols, n - r * cols)
        row_w = in_row * card_w + (in_row - 1) * gap
        x0 = (CANVAS_W - row_w) // 2 + c * (card_w + gap)
        y0 = top + r * (card_h + gap)

        cols_rgb = _palette_colors(name)
        # Card background tinted by the palette so each reads differently.
        draw.rounded_rectangle([x0, y0, x0 + card_w, y0 + card_h], radius=36,
                               fill=_blend(cols_rgb["background"],
                                           (255, 255, 255), 0.25),
                               outline=_blend(cols_rgb["primary"],
                                              (255, 255, 255), 0.4), width=4)
        # Cover thumbnail with a soft shadow, sitting on the card.
        cover_cy = y0 + int(card_h * 0.34)
        _paste_with_shadow(canvas, cover, (x0 + card_w // 2, cover_cy))

        # Swatch row of the palette's key colours.
        chip = max(46, card_w // 8)
        swatch_keys = ("primary", "secondary", "accent")
        row_w2 = len(swatch_keys) * chip + (len(swatch_keys) - 1) * 16
        sx = x0 + (card_w - row_w2) // 2
        sy = y0 + int(card_h * 0.66)
        for k in swatch_keys:
            draw.rounded_rectangle([sx, sy, sx + chip, sy + chip], radius=12,
                                   fill=cols_rgb[k],
                                   outline=(255, 255, 255), width=3)
            sx += chip + 16

        # Palette name (and a hero marker on the first).
        label = _palette_display_name(name)
        if i == 0:
            label = "★ " + label
        lfont = _fit_font(draw, label, card_w - 60, 46, bold=True, min_size=30)
        lw, lh = _text_size(draw, label, lfont)
        draw.text((x0 + (card_w - lw) // 2, y0 + card_h - lh - 34), label,
                  font=lfont, fill=cols_rgb["text"])

    return canvas


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_listing_images(
    pdf_path: str | Path,
    out_dir: str | Path,
    *,
    product_id: int,
    title: str,
    product_type: str = "planner",
    palette_name: str | None = None,
    palettes: list[str] | None = None,
    design_name: str | None = None,
    max_images: int = 5,
) -> list[Path]:
    """Compose up to *max_images* Etsy listing images for *pdf_path*.

    *design_name* is an optional planner design-theme name (preset id or
    resolved name); non-classic themes get a theme chip on the hero image
    so listing images stay consistent with the design.

    *palettes* is the full colour set of a planner bundle (hero first, the
    same list stored on ``product.palettes``).  When it holds two or more
    distinct palettes the hero image gains a swatch strip and a dedicated
    "colour options" image is inserted right after it, so the listing sells
    the colour choice.  Single-palette planners and picture books (``None``
    or a single palette) render exactly as before.

    Returns the list of written PNG paths
    (``product_{product_id}_mockup_{i}.png``).
    """
    import fitz

    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    if len(doc) == 0:
        raise ValueError(f"PDF has no pages: {pdf_path}")

    palette = _palette_colors(palette_name)
    design_label = _design_label(design_name)
    bundle = _bundle_palettes(palettes, palette_name)
    picks = _select_pages(len(doc), product_type)

    compositions = [
        lambda: _compose_hero(doc, palette, title, product_type, design_label,
                              bundle),
    ]
    if bundle:
        compositions.append(
            lambda: _compose_color_options(doc, palette, bundle, title)
        )
    compositions += [
        lambda: _compose_interiors(doc, palette, picks["interiors"], product_type),
        lambda: _compose_closeup(doc, palette, picks["closeup"], product_type),
        lambda: _compose_whats_inside(doc, palette, title, product_type),
        lambda: _compose_compat(doc, palette, product_type),
    ]

    written: list[Path] = []
    for i, compose in enumerate(compositions[:max_images]):
        out_path = out_dir / f"product_{product_id}_mockup_{i}.png"
        try:
            img = compose()
            img.save(out_path, "PNG", optimize=True)
            written.append(out_path)
        except Exception:
            logger.exception(
                "mockup_composition_failed", product_id=product_id, index=i
            )
    doc.close()

    logger.info(
        "listing_images_generated",
        product_id=product_id,
        count=len(written),
        out_dir=str(out_dir),
    )
    return written
