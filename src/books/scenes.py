"""Layered, depth-rich storybook scenes for picture-book pages.

Every scene is built from real illustrative layers so a spread reads like a
painted storybook page rather than a flat backdrop:

    sky (soft gradient, time-of-day aware)
      -> sun / moon / clouds
      -> BACKGROUND CAST (distant gulls, butterflies, a hazy far tree-line)
      -> rolling hills
      -> textured ground band
      -> MIDGROUND props, chosen by the page's *zone* (a sub-location of the
         same world -- e.g. the farm's barnyard / field / duck-pond)
      -> FOREGROUND framing (overhanging leaves, a cropped bush, tall grass
         or reeds near the "camera") for depth.

Two dials drive per-page variety inside one coherent world:

``shot``  -- the camera framing: ``establish`` (wide, lots of sky),
            ``wide``, ``corner`` (framed by foreground), ``path``,
            ``close`` (intimate, high horizon) or ``hill`` (a vista).
``zone``  -- which sub-location of the setting we are looking at.

The same code with ``line_art=True`` produces clean coloring-page outlines
(sky, texture, foreground and background cast are skipped so the printable
line art stays uncluttered).
"""

from __future__ import annotations

import math
import random
import zlib

from fpdf import FPDF

from src.books.characters import _leaf
from src.books.illustrator import (
    BookPalette,
    Draw,
    RGB,
    darken,
    lighten,
    mix,
)

PAGE_W = 215.9
PAGE_H = 215.9

SETTINGS = ("park", "forest", "zoo", "city", "farm", "beach", "school", "garden")

# Which sub-locations ("zones") each world can show.  The first is the
# "home" zone used on covers, coloring pages and establishing shots.
SETTING_ZONES: dict[str, tuple[str, ...]] = {
    "park":   ("greens", "pond", "play"),
    "forest": ("grove", "clearing", "brook"),
    "zoo":    ("gate", "safari", "pond"),
    "city":   ("street", "plaza", "greenway"),
    "farm":   ("barnyard", "field", "pond"),
    "beach":  ("shore", "tidepool", "cove"),
    "school": ("yard", "playground", "garden"),
    "garden": ("beds", "veg", "pond"),
}

# Horizon height (fraction of page) implied by each camera shot.
SHOT_HORIZON: dict[str, float] = {
    "establish": 0.60,
    "wide": 0.63,
    "corner": 0.63,
    "path": 0.64,
    "close": 0.72,
    "hill": 0.66,
}

# Foreground framing styles available per world (near-camera layer).
_FG_KINDS: dict[str, tuple[str, ...]] = {
    "park":   ("branch", "bush", "grass", "flowers"),
    "forest": ("branch", "bush", "grass"),
    "zoo":    ("bush", "grass", "branch"),
    "city":   ("bush", "grass"),
    "farm":   ("grass", "bush", "flowers"),
    "beach":  ("grass", "reeds"),
    "school": ("bush", "grass", "flowers"),
    "garden": ("flowers", "reeds", "bush", "grass"),
}


def _seed(setting: str, variant: int, shot: str, zone: str) -> int:
    """Deterministic RNG seed (stable across processes, unlike ``hash``)."""
    key = f"{setting}|{variant}|{shot}|{zone}".encode()
    return zlib.crc32(key)


def _resolve_zone(setting: str, zone: str) -> str:
    zones = SETTING_ZONES.get(setting, ("greens",))
    return zone if zone in zones else zones[0]


# ---------------------------------------------------------------------------
# Small shared props
# ---------------------------------------------------------------------------


def _cloud(d: Draw, cx: float, cy: float, s: float, color: RGB) -> None:
    if d.line_art:
        return  # overlapping outlines look messy on coloring pages
    d.ellipse(cx, cy, s * 1.15, s * 0.5, fill=color)
    d.circle(cx - s * 0.5, cy - s * 0.12, s * 0.42, fill=color)
    d.circle(cx + s * 0.35, cy - s * 0.2, s * 0.5, fill=color)


def _sun(d: Draw, cx: float, cy: float, r: float, color: RGB) -> None:
    for i in range(8):
        a = math.radians(i * 45)
        d.line(cx + (r * 1.25) * math.cos(a), cy + (r * 1.25) * math.sin(a),
               cx + (r * 1.6) * math.cos(a), cy + (r * 1.6) * math.sin(a),
               color=color, lw=r * 0.14)
    d.circle(cx, cy, r, fill=color)


def _moon(d: Draw, cx: float, cy: float, r: float, sky: RGB) -> None:
    d.circle(cx, cy, r, fill=(250, 243, 214))
    if not d.line_art:
        d.circle(cx + r * 0.45, cy - r * 0.25, r * 0.82, fill=sky)


def _star(d: Draw, cx: float, cy: float, r: float, color: RGB) -> None:
    if d.line_art:
        return
    d.dot(cx, cy, r, color)


def _round_tree(d: Draw, x: float, gy: float, s: float, pal: BookPalette) -> None:
    trunk = (150, 108, 74)
    green = darken(pal.ground, 0.08)
    d.rect(x - s * 0.07, gy - s * 0.55, s * 0.14, s * 0.55, fill=trunk, radius=s * 0.04)
    d.circle(x, gy - s * 0.78, s * 0.34, fill=green)
    d.circle(x - s * 0.24, gy - s * 0.62, s * 0.26, fill=green)
    d.circle(x + s * 0.24, gy - s * 0.62, s * 0.26, fill=green)
    if not d.line_art:
        d.dot(x - s * 0.12, gy - s * 0.82, s * 0.045, lighten(green, 0.25))
        d.dot(x + s * 0.16, gy - s * 0.68, s * 0.04, lighten(green, 0.25))


def _pine(d: Draw, x: float, gy: float, s: float, pal: BookPalette) -> None:
    trunk = (128, 92, 64)
    green = darken(pal.hill, 0.22)
    d.rect(x - s * 0.05, gy - s * 0.28, s * 0.10, s * 0.28, fill=trunk)
    for i, (w, yy) in enumerate(((0.42, 0.25), (0.34, 0.52), (0.24, 0.76))):
        d.polygon([(x - s * w, gy - s * yy), (x + s * w, gy - s * yy), (x, gy - s * (yy + 0.36))],
                  fill=green if i % 2 == 0 else darken(green, 0.08))


def _flower(d: Draw, x: float, y: float, s: float, petal: RGB, center: RGB) -> None:
    if d.line_art and s < 2.0:
        return
    for i in range(5):
        a = math.radians(i * 72 - 90)
        d.circle(x + s * 0.5 * math.cos(a), y + s * 0.5 * math.sin(a), s * 0.32, fill=petal)
    d.circle(x, y, s * 0.28, fill=center)


def _fence(d: Draw, x0: float, x1: float, gy: float, s: float, color: RGB) -> None:
    n = max(2, int((x1 - x0) / (s * 1.5)))
    for i in range(n + 1):
        px = x0 + i * (x1 - x0) / n
        d.rect(px - s * 0.09, gy - s, s * 0.18, s, fill=color, radius=s * 0.08)
        d.circle(px, gy - s, s * 0.10, fill=color)
    for ry in (0.35, 0.7):
        d.rect(x0, gy - s * ry - s * 0.06, x1 - x0, s * 0.12, fill=darken(color, 0.08))


def _window(d: Draw, x: float, y: float, w: float, h: float, color: RGB) -> None:
    d.rect(x, y, w, h, fill=color, radius=w * 0.15)


def _bush(d: Draw, x: float, gy: float, s: float, color: RGB, berries: RGB | None = None) -> None:
    """A leafy bush clump sitting on the ground."""
    for dx, dy, r in ((0, 0, 1.0), (-0.62, 0.18, 0.68), (0.62, 0.16, 0.7),
                      (-0.28, -0.28, 0.66), (0.3, -0.24, 0.64)):
        d.circle(x + dx * s, gy - r * s * 0.5 + dy * s, r * s * 0.5, fill=color)
    if berries and not d.line_art:
        for bx, by in ((-0.3, -0.1), (0.32, -0.16), (0.05, -0.34)):
            d.dot(x + bx * s, gy - s * 0.5 + by * s, s * 0.08, berries)


def _mushroom(d: Draw, x: float, gy: float, s: float) -> None:
    d.rect(x - s * 0.16, gy - s * 0.4, s * 0.32, s * 0.4, fill=(242, 232, 214), radius=s * 0.1)
    d.ellipse(x, gy - s * 0.44, s * 0.44, s * 0.26, fill=(226, 96, 92))
    if not d.line_art:
        d.dot(x - s * 0.14, gy - s * 0.52, s * 0.07, (255, 240, 240))
        d.dot(x + s * 0.15, gy - s * 0.46, s * 0.06, (255, 240, 240))


def _log(d: Draw, x: float, gy: float, s: float) -> None:
    wood = (168, 122, 82)
    d.rect(x - s, gy - s * 0.34, s * 2, s * 0.44, fill=wood, radius=s * 0.18)
    d.ellipse(x - s, gy - s * 0.12, s * 0.24, s * 0.22, fill=lighten(wood, 0.16))
    if not d.line_art:
        d.circle(x - s, gy - s * 0.12, s * 0.09, stroke=darken(wood, 0.25), lw=0.5)


def _rock(d: Draw, x: float, gy: float, s: float, color: RGB = (176, 176, 186)) -> None:
    d.polygon([(x - s, gy + s * 0.2), (x - s * 0.7, gy - s * 0.5),
               (x, gy - s * 0.75), (x + s * 0.72, gy - s * 0.48),
               (x + s, gy + s * 0.2)], fill=color)
    if not d.line_art:
        d.polygon([(x - s * 0.7, gy - s * 0.5), (x, gy - s * 0.75),
                   (x - s * 0.1, gy - s * 0.3)], fill=lighten(color, 0.16))


def _pond(d: Draw, cx: float, gy: float, rw: float, pal: BookPalette,
          rng: random.Random, lilies: int = 0) -> None:
    """A little pond nestled into the ground band."""
    rh = rw * 0.36
    cy = gy + rh * 0.7
    if not d.line_art:
        d.ellipse(cx, cy, rw, rh, fill=pal.water)
        d.ellipse(cx, cy - rh * 0.16, rw * 0.9, rh * 0.72, fill=lighten(pal.water, 0.16))
        for _ in range(3):
            wx = cx + rng.uniform(-rw * 0.5, rw * 0.5)
            wy = cy + rng.uniform(-rh * 0.3, rh * 0.4)
            d.arc(wx, wy, rw * 0.14, 200, 340, color=lighten(pal.water, 0.4), lw=0.8, ry=rh * 0.14)
    else:
        d.ellipse(cx, cy, rw, rh)
    for i in range(lilies):
        lx = cx + (i - (lilies - 1) / 2) * rw * 0.5
        _lilypad(d, lx, cy - rh * 0.1, rw * 0.16, pal)


def _lilypad(d: Draw, x: float, y: float, s: float, pal: BookPalette) -> None:
    green = darken(pal.ground, 0.06)
    d.circle(x, y, s, fill=green)
    if not d.line_art:
        d.polygon([(x, y), (x + s * 0.9, y - s * 0.3), (x + s * 0.9, y + s * 0.3)],
                  fill=lighten(pal.water, 0.16))
    d.circle(x - s * 0.2, y - s * 0.5, s * 0.34, fill=pal.accent2)


def _reeds(d: Draw, x: float, gy: float, s: float, color: RGB, n: int = 5) -> None:
    """Cattail reeds rising from the water's edge."""
    for i in range(n):
        rx = x + (i - n / 2) * s * 0.5
        rh = s * random.Random(int(rx * 7)).uniform(0.8, 1.25)
        d.line(rx, gy + s * 0.1, rx, gy - rh, color=color, lw=s * 0.06)
        if i % 2 == 0:
            d.rect(rx - s * 0.07, gy - rh, s * 0.14, s * 0.34, fill=darken(color, 0.15),
                   radius=s * 0.06)


def _duck(d: Draw, x: float, gy: float, s: float, facing: int = 1) -> None:
    body = (250, 244, 232)
    beak = (245, 170, 70)
    cy = gy + s * 0.08
    d.ellipse(x, cy, s * 0.5, s * 0.3, fill=body)
    d.circle(x + facing * s * 0.42, cy - s * 0.28, s * 0.2, fill=body)
    d.polygon([(x + facing * s * 0.6, cy - s * 0.3), (x + facing * s * 0.82, cy - s * 0.24),
               (x + facing * s * 0.6, cy - s * 0.18)], fill=beak)
    d.dot(x + facing * s * 0.46, cy - s * 0.32, s * 0.04, (50, 44, 52))
    d.polygon([(x - facing * s * 0.5, cy - s * 0.1), (x - facing * s * 0.2, cy - s * 0.14),
               (x - facing * s * 0.3, cy + s * 0.06)], fill=lighten(body, 0.02))


def _bench(d: Draw, bx: float, by: float) -> None:
    wood = (176, 128, 84)
    d.rect(bx - 14, by - 8, 28, 3, fill=wood, radius=1)
    d.rect(bx - 14, by - 16, 28, 2.6, fill=wood, radius=1)
    for sx in (-11, 11):
        d.rect(bx + sx - 1.2, by - 8, 2.4, 8, fill=darken(wood, 0.2))


def _ball(d: Draw, x: float, gy: float, s: float, pal: BookPalette) -> None:
    d.circle(x, gy - s * 0.5, s * 0.5, fill=pal.accent2)
    if not d.line_art:
        d.arc(x, gy - s * 0.5, s * 0.5, 200, 340, color=lighten(pal.accent2, 0.4), lw=0.7, ry=s * 0.24)
        d.arc(x, gy - s * 0.5, s * 0.5, 20, 160, color=darken(pal.accent2, 0.2), lw=0.7, ry=s * 0.24)


def _flag(d: Draw, fx: float, gy: float, h: float, color: RGB) -> None:
    d.line(fx, gy + 4, fx, gy - h, color=(120, 120, 132), lw=1.1)
    d.polygon([(fx, gy - h), (fx + 12, gy - h + 3), (fx, gy - h + 6)], fill=color)


def _swing(d: Draw, x: float, gy: float, pal: BookPalette) -> None:
    frame = (150, 120, 96)
    top = gy - 34
    d.line(x - 14, gy, x, top, color=frame, lw=1.8)
    d.line(x + 14, gy, x, top, color=frame, lw=1.8)
    d.line(x - 16, gy, x + 4, top, color=frame, lw=1.8)
    d.line(x - 5, top, x - 5, gy - 12, color=(120, 120, 132), lw=0.8)
    d.line(x + 3, top, x + 3, gy - 12, color=(120, 120, 132), lw=0.8)
    d.rect(x - 7, gy - 13, 12, 2.4, fill=pal.accent, radius=1)


def _scarecrow(d: Draw, x: float, gy: float, pal: BookPalette) -> None:
    post = (150, 108, 74)
    d.rect(x - 1.3, gy - 40, 2.6, 44, fill=post)
    d.rect(x - 15, gy - 30, 30, 2.4, fill=post)
    shirt = pal.accent
    d.polygon([(x - 12, gy - 30), (x + 12, gy - 30), (x + 8, gy - 12), (x - 8, gy - 12)], fill=shirt)
    d.circle(x, gy - 34, 5.5, fill=(236, 208, 150))
    hat = darken(pal.accent2, 0.1)
    d.polygon([(x - 8, gy - 37), (x + 8, gy - 37), (x, gy - 46)], fill=hat)
    d.rect(x - 8, gy - 38, 16, 2, fill=hat, radius=1)
    if not d.line_art:
        d.dot(x - 2, gy - 34, 0.8, (60, 48, 60))
        d.dot(x + 2, gy - 34, 0.8, (60, 48, 60))
        for sx in (-1, 1):        # straw hands
            d.line(x + sx * 14, gy - 29, x + sx * 17, gy - 25, color=(228, 196, 120), lw=0.7)


def _crop_rows(d: Draw, gy: float, x0: float, x1: float, pal: BookPalette) -> None:
    soil = darken(pal.ground, 0.14)
    for r in range(3):
        yy = gy + 6 + r * 6.5
        if not d.line_art:
            d.line(x0, yy, x1, yy, color=soil, lw=1.0)
        for c in range(6):
            px = x0 + (x1 - x0) * (c + 0.5) / 6
            d.circle(px, yy - 1.4, 1.7, fill=darken(pal.ground, 0.02))


def _umbrella(d: Draw, x: float, gy: float, pal: BookPalette) -> None:
    d.line(x, gy + 2, x, gy - 26, color=(120, 110, 120), lw=1.0)
    top = gy - 26
    stripes = [pal.accent, (255, 255, 255)]
    for i in range(4):
        a0 = 180 + i * 45
        a1 = a0 + 45
        pts = [(x, top)]
        for k in range(6):
            a = math.radians(a0 + (a1 - a0) * k / 5)
            pts.append((x + 20 * math.cos(a), top + 12 * math.sin(a) + 12))
        d.polygon(pts, fill=stripes[i % 2] if not d.line_art else None,
                  stroke=(30, 30, 30) if d.line_art else None, lw=0.5)


def _fountain(d: Draw, x: float, gy: float, pal: BookPalette) -> None:
    stone = (200, 200, 208)
    d.ellipse(x, gy + 2, 20, 7, fill=stone)
    d.ellipse(x, gy + 1, 16, 5, fill=pal.water if not d.line_art else None,
              stroke=(30, 30, 30) if d.line_art else None, lw=0.5)
    d.rect(x - 2, gy - 16, 4, 16, fill=stone, radius=1)
    d.ellipse(x, gy - 16, 8, 3, fill=stone)
    if not d.line_art:
        for sx in (-1, 0, 1):
            d.arc(x, gy - 16, 6, 200 + sx * 20, 340 + sx * 20,
                  color=lighten(pal.water, 0.3), lw=0.7, ry=6)


def _trellis(d: Draw, x: float, gy: float, pal: BookPalette) -> None:
    wood = (222, 206, 176)
    d.rect(x - 12, gy - 30, 24, 30, fill=None, stroke=wood, lw=1.4)
    for gx in (-4, 4):
        d.line(x + gx, gy, x + gx, gy - 30, color=wood, lw=1.0)
    for gyy in (-10, -20):
        d.line(x - 12, gy + gyy, x + 12, gy + gyy, color=wood, lw=1.0)
    for _ in range(4):
        fx = x + (hash((x, _)) % 20 - 10)
        _flower(d, fx, gy - 6 - (hash((_, x)) % 20), 4.0, pal.accent2, pal.sun)


def _planter(d: Draw, x: float, gy: float, pal: BookPalette) -> None:
    box = (176, 130, 92)
    d.rect(x - 12, gy - 6, 24, 8, fill=box, radius=1.5)
    for i in range(3):
        fx = x + (i - 1) * 8
        d.line(fx, gy - 6, fx, gy - 13, color=darken(pal.ground, 0.2), lw=0.8)
        _flower(d, fx, gy - 15, 4.2, [pal.accent, pal.accent2, pal.sun][i], (255, 255, 255))


def _flamingo(d: Draw, x: float, gy: float) -> None:
    pink = (244, 158, 180)
    d.line(x, gy, x, gy - 16, color=pink, lw=1.4)
    d.ellipse(x, gy - 20, 5.5, 4, fill=pink)
    d.polyline([(x, gy - 22), (x + 3, gy - 26), (x + 1, gy - 22)], color=pink, lw=1.4)
    d.circle(x + 1.5, gy - 27, 2.4, fill=pink)
    if not d.line_art:
        d.polygon([(x + 3, gy - 26), (x + 6, gy - 25), (x + 3, gy - 24)], fill=(60, 48, 60))


def _tent(d: Draw, x: float, gy: float, pal: BookPalette) -> None:
    top = gy - 30
    left = (pal.accent, (255, 255, 255))
    for i in range(4):
        x0 = x - 20 + i * 10
        d.polygon([(x0, gy), (x0 + 10, gy), (x, top)],
                  fill=left[i % 2] if not d.line_art else None,
                  stroke=(30, 30, 30) if d.line_art else None, lw=0.5)
    d.circle(x, top, 1.8, fill=pal.accent2)


def _seashell(d: Draw, x: float, gy: float, s: float, color: RGB) -> None:
    d.polygon([(x, gy), (x - s, gy - s * 0.9), (x - s * 0.4, gy - s * 1.05),
               (x, gy - s * 0.7), (x + s * 0.4, gy - s * 1.05), (x + s, gy - s * 0.9)],
              fill=color)
    if not d.line_art:
        for k in (-0.5, 0, 0.5):
            d.line(x, gy - s * 0.1, x + k * s * 0.8, gy - s * 0.9,
                   color=darken(color, 0.18), lw=0.4)


def _starfish(d: Draw, x: float, gy: float, s: float, color: RGB) -> None:
    for i in range(5):
        a = math.radians(i * 72 - 90)
        d.ellipse(x + s * math.cos(a), gy + s * math.sin(a), s * 0.42, s * 0.24, fill=color)
    d.circle(x, gy, s * 0.34, fill=color)
    if not d.line_art:
        d.dot(x, gy, s * 0.12, lighten(color, 0.35))


def _palm(d: Draw, px: float, gy: float, pal: BookPalette) -> None:
    trunk = (166, 120, 82)
    d.polyline([(px, gy + 6), (px - 1.5, gy - 8), (px - 4.5, gy - 22)], color=trunk, lw=3.2)
    for ang in (-165, -125, -85, -45, -10):
        _leaf(d, px - 4.5, gy - 23, 22, 5.5, ang, darken(pal.hill, 0.12))
    if not d.line_art:
        for cx2, cy2 in ((px - 6, gy - 20), (px - 2, gy - 21)):
            d.circle(cx2, cy2, 1.6, fill=(150, 110, 70))


def _sailboat(d: Draw, sbx: float, sea_top: float) -> None:
    d.polygon([(sbx - 7, sea_top + 3), (sbx + 7, sea_top + 3), (sbx + 4, sea_top + 7),
               (sbx - 4, sea_top + 7)], fill=(210, 120, 96))
    d.line(sbx, sea_top + 3, sbx, sea_top - 9, color=(120, 90, 70), lw=0.8)
    d.polygon([(sbx, sea_top - 9), (sbx + 6.5, sea_top - 1), (sbx, sea_top - 1)],
              fill=(250, 245, 232))


# ---------------------------------------------------------------------------
# Background cast + far detail (depth)
# ---------------------------------------------------------------------------


def _bird(d: Draw, cx: float, cy: float, s: float, color: RGB) -> None:
    d.polyline([(cx - s, cy + s * 0.35), (cx - s * 0.25, cy - s * 0.12), (cx, cy + s * 0.05)],
               color=color, lw=max(s * 0.14, 0.5))
    d.polyline([(cx, cy + s * 0.05), (cx + s * 0.25, cy - s * 0.12), (cx + s, cy + s * 0.35)],
               color=color, lw=max(s * 0.14, 0.5))


def _butterfly(d: Draw, cx: float, cy: float, s: float, wing: RGB) -> None:
    for sx in (-1, 1):
        d.ellipse(cx + sx * s * 0.5, cy - s * 0.2, s * 0.5, s * 0.66, fill=wing)
        d.ellipse(cx + sx * s * 0.4, cy + s * 0.45, s * 0.36, s * 0.44, fill=lighten(wing, 0.12))
    d.ellipse(cx, cy, s * 0.16, s * 0.7, fill=(90, 80, 90))


def _searchbug(d: Draw, cx: float, cy: float, s: float, body: RGB) -> None:
    """A tiny findable ladybug -- the recurring 'search critter' for the
    oldest band's seek-and-find spreads."""
    d.ellipse(cx, cy, s, s * 0.86, fill=body)
    d.line(cx, cy - s * 0.86, cx, cy + s * 0.78, color=darken(body, 0.4),
           lw=max(s * 0.10, 0.4))
    d.circle(cx, cy - s * 0.92, s * 0.4, fill=(52, 46, 54))
    for dx, dy in ((-0.42, -0.16), (0.42, -0.16), (-0.34, 0.36), (0.34, 0.36)):
        d.dot(cx + dx * s, cy + dy * s, s * 0.16, (44, 40, 48))
    for kx in (-0.4, 0.4):
        d.line(cx + kx * s * 0.28, cy - s * 0.92, cx + kx * s * 0.62, cy - s * 1.28,
               color=(52, 46, 54), lw=max(s * 0.08, 0.35))


def _search_critter(
    d: Draw, pal: BookPalette, horizon: float, rng: random.Random,
) -> None:
    """Plant one small critter to 'find' on the page.  Its spot is driven by
    the per-page scene rng, so it hides somewhere different each spread --
    sustained-attention seek-and-find for early readers (6-8).  Colour-only:
    coloring pages stay clean."""
    if d.line_art:
        return
    if rng.random() < 0.5:
        # up in the sky/treetops
        cx = rng.uniform(PAGE_W * 0.10, PAGE_W * 0.90)
        cy = rng.uniform(20, max(28.0, horizon * 0.5))
    else:
        # tucked low against one side, clear of the center where text/heroes go
        cx = (rng.uniform(PAGE_W * 0.05, PAGE_W * 0.17) if rng.random() < 0.5
              else rng.uniform(PAGE_W * 0.83, PAGE_W * 0.95))
        cy = rng.uniform(horizon * 0.58, horizon - 6)
    _searchbug(d, cx, cy, 4.0, (222, 74, 68))


def _far_treeline(d: Draw, pal: BookPalette, horizon: float, rng: random.Random) -> None:
    """A hazy row of distant trees hugging the horizon (atmospheric depth)."""
    if d.line_art:
        return
    haze = mix(pal.hill, (255, 255, 255), 0.34)
    x = -4.0
    while x < PAGE_W + 4:
        bw = rng.uniform(9, 17)
        bh = rng.uniform(5, 11)
        d.circle(x, horizon - bh * 0.35, bw * 0.5, fill=haze)
        x += bw * 0.66
    d.pdf.set_fill_color(*haze)
    d.pdf.rect(0, horizon - 1.5, PAGE_W, 2.6, style="F")


def _background_cast(
    d: Draw, pal: BookPalette, horizon: float, rng: random.Random,
    time_of_day: str, setting: str, sun_x: float, sky_offset: float,
) -> None:
    """Distant living detail: a gull flock and a butterfly or two."""
    if d.line_art:
        return
    off = sky_offset
    if time_of_day != "night":
        # a small skein of gulls, kept away from the sun
        side = -1 if sun_x > PAGE_W * 0.5 else 1
        fx = PAGE_W * (0.22 if side < 0 else 0.62) + rng.uniform(-8, 8)
        fy = 26 + off + rng.uniform(0, 12)
        bird_c = mix(pal.text, (255, 255, 255), 0.25)
        for i in range(rng.randint(2, 4)):
            _bird(d, fx + i * 9.5, fy + (i % 2) * 4 - 2, rng.uniform(3.4, 4.6), bird_c)
    if setting in ("garden", "park", "school", "forest", "farm") and time_of_day in ("day", "morning"):
        for _ in range(rng.randint(1, 2)):
            bx = rng.uniform(PAGE_W * 0.2, PAGE_W * 0.8)
            by = rng.uniform(horizon * 0.55, horizon * 0.85)
            _butterfly(d, bx, by, rng.uniform(2.6, 3.6), pal.accent2)


# ---------------------------------------------------------------------------
# Sky / ground / hills
# ---------------------------------------------------------------------------


def _sky_colors(pal: BookPalette, time_of_day: str) -> tuple[RGB, RGB]:
    if time_of_day == "sunset":
        return (mix(pal.sky_top, (250, 150, 110), 0.55),
                mix(pal.sky_bottom, (255, 214, 150), 0.6))
    if time_of_day == "morning":
        return (mix(pal.sky_top, (255, 206, 156), 0.34),
                mix(pal.sky_bottom, (255, 238, 206), 0.42))
    if time_of_day == "overcast":
        return (mix(pal.sky_top, (178, 184, 194), 0.6),
                mix(pal.sky_bottom, (208, 212, 218), 0.55))
    if time_of_day == "night":
        return (56, 62, 110), (110, 112, 160)
    return pal.sky_top, pal.sky_bottom


def _sky(d: Draw, pal: BookPalette, horizon: float, time_of_day: str) -> None:
    if d.line_art:
        return
    top, bottom = _sky_colors(pal, time_of_day)
    n = 28
    band_h = horizon / n
    for i in range(n):
        d.pdf.set_fill_color(*mix(top, bottom, i / (n - 1)))
        d.pdf.rect(0, i * band_h - 0.2, PAGE_W, band_h + 0.4, style="F")


def _ground(
    d: Draw, pal: BookPalette, horizon: float, rng: random.Random,
    color: RGB | None = None, flowers: bool = True,
) -> None:
    ground = color or pal.ground
    if not d.line_art:
        d.pdf.set_fill_color(*ground)
        d.pdf.rect(0, horizon, PAGE_W, PAGE_H - horizon, style="F")
        d.pdf.set_fill_color(*lighten(ground, 0.12))
        d.pdf.rect(0, horizon, PAGE_W, 2.2, style="F")
    else:
        d.line(0, horizon, PAGE_W, horizon, lw=0.6)
    for _ in range(9):
        tx = rng.uniform(8, PAGE_W - 8)
        ty = rng.uniform(horizon + 8, PAGE_H - 10)
        kind = rng.random()
        if kind < 0.4 and flowers:
            _flower(d, tx, ty, rng.uniform(2.2, 3.4), pal.accent2, pal.sun)
        elif kind < 0.8:
            if not d.line_art:
                for k in (-1, 0, 1):
                    d.line(tx + k * 1.1, ty, tx + k * 1.8, ty - rng.uniform(2.5, 4),
                           color=darken(ground, 0.18), lw=0.5)
        else:
            if not d.line_art:
                d.dot(tx, ty, rng.uniform(0.6, 1.1), darken(ground, 0.12))


def _hills(d: Draw, pal: BookPalette, horizon: float, rng: random.Random, shot: str) -> None:
    if d.line_art:
        return
    if shot == "hill":
        # a single broad rise the characters can crown -- a storybook vista
        d.ellipse(PAGE_W * 0.5, horizon + 30, PAGE_W * 0.72, 52, fill=pal.hill)
        d.ellipse(PAGE_W * 0.16, horizon + 8, PAGE_W * 0.36, 20, fill=lighten(pal.hill, 0.16))
        d.ellipse(PAGE_W * 0.86, horizon + 10, PAGE_W * 0.32, 18, fill=darken(pal.hill, 0.06))
        return
    d.ellipse(PAGE_W * 0.22, horizon + 12, PAGE_W * 0.42, 26, fill=pal.hill)
    d.ellipse(PAGE_W * 0.80, horizon + 14, PAGE_W * 0.40, 22, fill=lighten(pal.hill, 0.15))


def _sky_objects(
    d: Draw, pal: BookPalette, rng: random.Random, time_of_day: str,
    horizon: float, sky_offset: float = 0.0,
) -> float:
    """Sun/moon + clouds.  Returns the sun's x so the background cast can keep
    the gulls clear of it.  ``sky_offset`` pushes everything lower so a top
    text panel never hides the sun."""
    off = sky_offset
    sun_x = rng.uniform(30, PAGE_W - 30)
    if time_of_day == "night":
        _moon(d, sun_x, 34 + off, 12, (56, 62, 110))
        for _ in range(9):
            _star(d, rng.uniform(10, PAGE_W - 10),
                  rng.uniform(12 + off, horizon * 0.55 + off * 0.4),
                  rng.uniform(0.7, 1.3), (250, 240, 200))
    elif time_of_day == "overcast":
        sun_x = PAGE_W * 0.5    # (hidden) keep gulls centered-away
    elif time_of_day == "morning":
        sun = mix(pal.sun, (255, 176, 110), 0.4)
        _sun(d, sun_x, 40 + off, 12, sun)
    else:
        sun = pal.sun if time_of_day == "day" else mix(pal.sun, (255, 170, 90), 0.5)
        _sun(d, sun_x, 34 + off, 11, sun)
    if time_of_day == "overcast":
        cloud_c = mix(pal.cloud, (196, 200, 206), 0.7)
        n_clouds = rng.randint(3, 4)
    else:
        cloud_c = pal.cloud if time_of_day != "night" else (150, 150, 190)
        n_clouds = rng.randint(2, 3)
    lo, hi = 18 + off, max(horizon * 0.5, 26 + off)
    for _ in range(n_clouds):
        cx = rng.uniform(20, PAGE_W - 20)
        for _try in range(6):
            if abs(cx - sun_x) > 42 or time_of_day == "overcast":
                break
            cx = rng.uniform(20, PAGE_W - 20)
        _cloud(d, cx, rng.uniform(lo, hi), rng.uniform(8, 13), cloud_c)
    return sun_x


# ---------------------------------------------------------------------------
# Setting-specific midground props (zone-aware)
# ---------------------------------------------------------------------------


def _park(d, pal, gy, rng, sparse, zone, shot) -> None:
    zone = _resolve_zone("park", zone)
    if zone == "pond":
        _round_tree(d, 26, gy + 6, 44, pal)
        _pond(d, PAGE_W * 0.6, gy, 40, pal, rng, lilies=2)
        _reeds(d, PAGE_W * 0.34, gy, 12, darken(pal.ground, 0.18), n=5)
        _duck(d, PAGE_W * 0.66, gy + 8, 9, facing=-1)
        _bush(d, PAGE_W * 0.86, gy + 2, 9, darken(pal.ground, 0.1))
    elif zone == "play":
        _swing(d, PAGE_W * 0.24, gy + 2, pal)
        _round_tree(d, PAGE_W - 26, gy + 4, 42, pal)
        _ball(d, PAGE_W * 0.6, gy + 2, 11, pal)
        if not sparse:
            _bench(d, PAGE_W * 0.8, gy + 2)
    else:  # greens
        _round_tree(d, 28, gy + 6, 46, pal)
        if not sparse:
            _round_tree(d, PAGE_W - 24, gy + 4, 38, pal)
            _bench(d, PAGE_W * 0.72, gy + 2)
        _bush(d, PAGE_W * 0.44, gy + 2, 9, darken(pal.ground, 0.1))


def _forest(d, pal, gy, rng, sparse, zone, shot) -> None:
    zone = _resolve_zone("forest", zone)
    if zone == "clearing":
        _round_tree(d, 26, gy + 6, 44, pal)
        _round_tree(d, PAGE_W - 28, gy + 4, 40, pal)
        _log(d, PAGE_W * 0.6, gy + 4, 12)
        for mx in (PAGE_W * 0.34, PAGE_W * 0.46):
            _mushroom(d, mx, gy + 4, 9)
    elif zone == "brook":
        _pine(d, 24, gy + 6, 50, pal)
        _pond(d, PAGE_W * 0.56, gy, 46, pal, rng)
        for sx in (0.36, 0.5, 0.66):
            _rock(d, PAGE_W * sx, gy + 6, 5)
        _mushroom(d, PAGE_W * 0.86, gy + 3, 8)
    else:  # grove
        _pine(d, 24, gy + 6, 52, pal)
        _pine(d, PAGE_W - 30, gy + 4, 60, pal)
        if not sparse:
            _pine(d, 58, gy + 2, 36, pal)
            _round_tree(d, PAGE_W - 66, gy + 2, 34, pal)
        for mx in (PAGE_W * 0.36, PAGE_W * 0.60):
            _mushroom(d, mx, gy + 3, 8)


def _zoo(d, pal, gy, rng, sparse, zone, shot) -> None:
    zone = _resolve_zone("zoo", zone)
    if zone == "safari":
        _fence(d, 8, PAGE_W * 0.4, gy + 4, 11, (196, 150, 100))
        _palm(d, PAGE_W - 30, gy + 6, pal)
        _tent(d, PAGE_W * 0.62, gy + 2, pal)
        _bush(d, PAGE_W * 0.2, gy + 2, 8, darken(pal.ground, 0.1))
    elif zone == "pond":
        _pond(d, PAGE_W * 0.58, gy, 42, pal, rng, lilies=1)
        _reeds(d, PAGE_W * 0.34, gy, 12, darken(pal.ground, 0.18))
        _flamingo(d, PAGE_W * 0.6, gy + 4)
        _flamingo(d, PAGE_W * 0.7, gy + 6)
        _round_tree(d, 26, gy + 6, 42, pal)
    else:  # gate
        _fence(d, 10, PAGE_W * 0.44, gy + 4, 12, (196, 150, 100))
        _round_tree(d, PAGE_W - 26, gy + 4, 42, pal)
        sx = PAGE_W * 0.68
        post = (150, 108, 74)
        for px in (sx - 16, sx + 16):
            d.rect(px - 1.5, gy - 26, 3, 30, fill=post)
        d.rect(sx - 19, gy - 32, 38, 9, fill=pal.accent, radius=3)
        if not d.line_art:
            d.pdf.set_font("Helvetica", "B", 13)
            d.pdf.set_text_color(255, 255, 255)
            d.pdf.text(sx - 7.5, gy - 25.4, "ZOO")
        d.line(sx + 30, gy - 2, sx + 32, gy - 16, color=darken(pal.accent2, 0.2), lw=0.5)
        d.circle(sx + 32, gy - 19, 4, fill=pal.accent2)


def _city(d, pal, gy, rng, sparse, zone, shot) -> None:
    zone = _resolve_zone("city", zone)
    bcolors = [mix(pal.hill, pal.accent2, 0.25), lighten(pal.hill, 0.2),
               mix(pal.hill, pal.accent, 0.3), lighten(pal.hill, 0.05)]

    def skyline(y_lift: float, scale: float) -> None:
        xs = 6.0
        i = 0
        while xs < PAGE_W - 10:
            bw = rng.uniform(22, 34) * scale
            bh = rng.uniform(26, 52) * scale
            color = bcolors[i % len(bcolors)]
            d.rect(xs, gy - bh + 4 - y_lift, bw, bh, fill=color, radius=1.5)
            if not d.line_art:
                wcol = lighten(pal.sky_bottom, 0.3)
                for wy in range(int(bh // 12)):
                    for wx in range(max(1, int(bw // 10))):
                        _window(d, xs + 4 + wx * 9, gy - bh + 9 + wy * 11 - y_lift, 4.6, 5.6, wcol)
            xs += bw + rng.uniform(3, 7)
            i += 1

    if zone == "greenway":
        skyline(14, 0.7)
        _round_tree(d, 30, gy + 4, 40, pal)
        _round_tree(d, PAGE_W - 34, gy + 4, 36, pal)
        _bench(d, PAGE_W * 0.6, gy + 2)
    elif zone == "plaza":
        skyline(6, 0.9)
        _fountain(d, PAGE_W * 0.62, gy + 2, pal)
        lx = PAGE_W * 0.2
        d.rect(lx - 1, gy - 24, 2, 28, fill=(90, 90, 104), radius=0.8)
        d.circle(lx, gy - 26, 3.2, fill=pal.sun)
    else:  # street
        skyline(0, 1.0)
        lx = PAGE_W * 0.82
        d.rect(lx - 1, gy - 24, 2, 28, fill=(90, 90, 104), radius=0.8)
        d.circle(lx, gy - 26, 3.2, fill=pal.sun)


def _farm(d, pal, gy, rng, sparse, zone, shot) -> None:
    zone = _resolve_zone("farm", zone)

    def barn(bx: float, scale: float) -> None:
        bw, bh = 62.0 * scale, 40.0 * scale
        red = (206, 92, 78)
        d.rect(bx, gy - bh + 6, bw, bh, fill=red, radius=2)
        d.polygon([(bx - 4, gy - bh + 8), (bx + bw + 4, gy - bh + 8),
                   (bx + bw * 0.5, gy - bh - 14 * scale)], fill=darken(red, 0.25))
        d.rect(bx + bw * 0.38, gy - 16 * scale, bw * 0.24, 22 * scale, fill=darken(red, 0.35), radius=2)
        if not d.line_art and scale > 0.8:
            d.line(bx + bw * 0.40, gy - 14, bx + bw * 0.60, gy + 2, color=(240, 225, 200), lw=1.1)
            d.line(bx + bw * 0.60, gy - 14, bx + bw * 0.40, gy + 2, color=(240, 225, 200), lw=1.1)
        _window(d, bx + bw * 0.12, gy - bh + 14 * scale, 9 * scale, 9 * scale, (250, 240, 214))
        _window(d, bx + bw * 0.72, gy - bh + 14 * scale, 9 * scale, 9 * scale, (250, 240, 214))

    def hay(hx: float) -> None:
        d.circle(hx, gy + 1, 6.5, fill=(238, 206, 120))
        if not d.line_art:
            d.circle(hx, gy + 1, 3.4, stroke=darken((238, 206, 120), 0.25), lw=0.7)

    if zone == "field":
        _crop_rows(d, gy, 12, PAGE_W - 12, pal)
        _scarecrow(d, PAGE_W * 0.3, gy, pal)
        _fence(d, PAGE_W * 0.62, PAGE_W - 8, gy + 4, 11, (222, 214, 200))
        hay(PAGE_W * 0.8)
    elif zone == "pond":
        barn(PAGE_W - 62, 0.62)
        _pond(d, PAGE_W * 0.42, gy, 44, pal, rng)
        _reeds(d, PAGE_W * 0.2, gy, 12, darken(pal.ground, 0.18))
        _duck(d, PAGE_W * 0.48, gy + 8, 9)
        hay(PAGE_W * 0.86)
    else:  # barnyard
        barn(16.0, 1.0)
        _fence(d, PAGE_W * 0.52, PAGE_W - 8, gy + 4, 11, (222, 214, 200))
        hay(PAGE_W * 0.62)


def _sea(d, pal, gy, rng, sea_depth: float = 28) -> float:
    sea_top = gy - sea_depth
    if not d.line_art:
        d.pdf.set_fill_color(*pal.water)
        d.pdf.rect(0, sea_top, PAGE_W, gy - sea_top + 2, style="F")
        for _ in range(5):
            wx = rng.uniform(14, PAGE_W - 14)
            wy = rng.uniform(sea_top + 5, gy - 4)
            d.arc(wx, wy, 5, 200, 340, color=lighten(pal.water, 0.35), lw=0.9, ry=2.6)
    else:
        d.line(0, sea_top, PAGE_W, sea_top, lw=0.6)
        for wx, wy in ((40, sea_top + 10), (110, sea_top + 18), (175, sea_top + 8)):
            d.arc(wx, wy, 5, 200, 340, lw=0.6, ry=2.6)
    return sea_top


def _beach(d, pal, gy, rng, sparse, zone, shot) -> None:
    zone = _resolve_zone("beach", zone)
    sea_top = _sea(d, pal, gy, rng)
    if zone == "tidepool":
        _sailboat(d, rng.uniform(PAGE_W * 0.5, PAGE_W * 0.7), sea_top)
        _palm(d, 26, gy + 6, pal)
        _rock(d, PAGE_W * 0.66, gy + 8, 12, (168, 164, 176))
        _rock(d, PAGE_W * 0.78, gy + 6, 8, (184, 180, 190))
        _starfish(d, PAGE_W * 0.6, gy + 20, 3.6, pal.accent)
        _seashell(d, PAGE_W * 0.86, gy + 20, 4, lighten(pal.accent2, 0.3))
        _seashell(d, PAGE_W * 0.2, gy + 22, 3.4, (250, 236, 220))
    elif zone == "cove":
        _sailboat(d, rng.uniform(PAGE_W * 0.55, PAGE_W * 0.78), sea_top)
        _rock(d, PAGE_W * 0.16, gy - 6, 16, (168, 164, 176))
        _palm(d, PAGE_W - 28, gy + 6, pal)
        _umbrella(d, PAGE_W * 0.5, gy + 6, pal)
        _seashell(d, PAGE_W * 0.72, gy + 20, 4, (250, 236, 220))
    else:  # shore
        _sailboat(d, rng.uniform(PAGE_W * 0.55, PAGE_W * 0.8), sea_top)
        _palm(d, 26, gy + 6, pal)
        _starfish(d, PAGE_W * 0.74, gy + 18, 3.8, pal.accent)


def _school(d, pal, gy, rng, sparse, zone, shot) -> None:
    zone = _resolve_zone("school", zone)

    def schoolhouse(bx: float) -> None:
        bw, bh = 58.0, 38.0
        wall = (238, 196, 130)
        roof = (198, 100, 88)
        d.rect(bx, gy - bh + 6, bw, bh, fill=wall, radius=2)
        d.polygon([(bx - 4, gy - bh + 8), (bx + bw + 4, gy - bh + 8),
                   (bx + bw * 0.5, gy - bh - 12)], fill=roof)
        d.circle(bx + bw * 0.5, gy - bh - 1, 4.2, fill=(252, 248, 238))
        if not d.line_art:
            d.line(bx + bw * 0.5, gy - bh - 1, bx + bw * 0.5, gy - bh - 3.6, color=(90, 80, 90), lw=0.5)
            d.line(bx + bw * 0.5, gy - bh - 1, bx + bw * 0.5 + 2, gy - bh - 0.4, color=(90, 80, 90), lw=0.5)
        d.rect(bx + bw * 0.40, gy - 14, bw * 0.20, 20, fill=(150, 104, 74), radius=2)
        _window(d, bx + bw * 0.10, gy - bh + 14, 10, 10, (216, 236, 248))
        _window(d, bx + bw * 0.72, gy - bh + 14, 10, 10, (216, 236, 248))

    if zone == "playground":
        _swing(d, PAGE_W * 0.24, gy + 2, pal)
        _ball(d, PAGE_W * 0.54, gy + 2, 11, pal)
        _round_tree(d, PAGE_W - 26, gy + 4, 40, pal)
        if not d.line_art:      # hopscotch chalk
            for i in range(4):
                d.rect(PAGE_W * 0.66 + i * 7, gy + 8 + i * 3, 6, 6,
                       stroke=(250, 250, 250), lw=0.8)
    elif zone == "garden":
        _fence(d, 8, PAGE_W - 8, gy + 2, 12, (232, 226, 214))
        _planter(d, PAGE_W * 0.28, gy, pal)
        _planter(d, PAGE_W * 0.6, gy, pal)
        _round_tree(d, PAGE_W - 26, gy + 4, 36, pal)
    else:  # yard
        schoolhouse(20.0)
        _flag(d, 20.0 + 58 + 14, gy, 34, pal.accent)
        _ball(d, PAGE_W * 0.78, gy + 3, 10, pal)


def _garden(d, pal, gy, rng, sparse, zone, shot) -> None:
    zone = _resolve_zone("garden", zone)
    if zone == "veg":
        _fence(d, 8, PAGE_W - 8, gy + 2, 12, (232, 226, 214))
        _trellis(d, PAGE_W * 0.24, gy, pal)
        for i in range(4):
            mx = PAGE_W * 0.5 + (i - 1.5) * 16
            d.ellipse(mx, gy + 14, 8, 3.4, fill=darken(pal.ground_dark, 0.15))
            for k in (-1, 0, 1):
                d.line(mx + k * 2.6, gy + 12, mx + k * 3.4, gy + 8.5,
                       color=darken(pal.ground, 0.25), lw=0.8)
        _flower(d, PAGE_W - 30, gy - 4, 7.0, pal.accent, pal.sun)
    elif zone == "pond":
        _fence(d, 8, PAGE_W * 0.34, gy + 2, 12, (232, 226, 214))
        _pond(d, PAGE_W * 0.58, gy, 42, pal, rng, lilies=2)
        for fx, fs, pc in ((30, 7.0, pal.accent2), (PAGE_W - 34, 7.5, pal.accent)):
            stem = darken(pal.ground, 0.15)
            d.line(fx, gy + 8, fx, gy - fs * 1.6, color=stem, lw=1.2)
            _flower(d, fx, gy - fs * 1.9, fs, pc, pal.sun)
    else:  # beds
        _fence(d, 8, PAGE_W - 8, gy + 2, 13, (232, 226, 214))
        for fx, fs, pc in ((34, 8.0, pal.accent2), (56, 6.0, pal.accent),
                           (PAGE_W - 40, 8.5, pal.accent), (PAGE_W - 62, 6.0, pal.accent2)):
            stem = darken(pal.ground, 0.15)
            d.line(fx, gy + 8, fx, gy - fs * 1.6, color=stem, lw=1.2)
            _leaf(d, fx, gy - 2, 6, 2, -160, stem)
            _flower(d, fx, gy - fs * 1.9, fs, pc, pal.sun)
        for i in range(3):
            mx = PAGE_W * 0.5 + (i - 1) * 20
            d.ellipse(mx, gy + 14, 9, 3.6, fill=darken(pal.ground_dark, 0.15))
            for k in (-1, 0, 1):
                d.line(mx + k * 3, gy + 12, mx + k * 4, gy + 8.5,
                       color=darken(pal.ground, 0.25), lw=0.8)


_PROPS = {
    "park": _park,
    "forest": _forest,
    "zoo": _zoo,
    "city": _city,
    "farm": _farm,
    "beach": _beach,
    "school": _school,
    "garden": _garden,
}


# ---------------------------------------------------------------------------
# Foreground framing (near-camera layer, partly cropped off the page)
# ---------------------------------------------------------------------------


def _fg_grass(d: Draw, pal: BookPalette, rng: random.Random, side: int, big: bool) -> None:
    base_x = PAGE_W * 0.5 + side * PAGE_W * (0.42 if big else 0.46)
    by = PAGE_H + 2
    col = darken(pal.ground_dark, 0.12)
    n = 8 if big else 4
    step = 6.0 if big else 5.0
    maxh = 36 if big else 20
    for i in range(n):
        bx = base_x + (i - n / 2) * step + rng.uniform(-1.2, 1.2)
        bh = maxh * rng.uniform(0.68, 1.05)
        lean = rng.uniform(-5, 5)
        d.polygon([(bx - 1.8, by), (bx + 1.8, by), (bx + lean, by - bh)],
                  fill=col if not d.line_art else None,
                  stroke=(30, 30, 30) if d.line_art else None, lw=0.6)


def _fg_bush(d: Draw, pal: BookPalette, rng: random.Random, side: int) -> None:
    base_x = PAGE_W * 0.5 + side * PAGE_W * 0.47
    by = PAGE_H + 8
    col = darken(pal.ground, 0.13)
    for dx, dy, r in ((0, 0, 30), (-18, 8, 20), (18, 6, 21), (-8, -12, 18), (10, -10, 17)):
        d.circle(base_x + dx, by + dy - 18, r, fill=col if not d.line_art else None,
                 stroke=(30, 30, 30) if d.line_art else None, lw=0.7)
    if not d.line_art:
        for bx, by2 in ((-8, -14), (12, -12), (0, -22)):
            d.dot(base_x + bx, by + by2 - 18, 1.8, pal.accent2)


def _fg_branch(d: Draw, pal: BookPalette, rng: random.Random, side: int) -> None:
    """A leafy branch overhanging from a top corner -- classic page framing."""
    cx = 0.0 if side < 0 else PAGE_W
    cy = -4.0
    inward = 1 if side < 0 else -1
    bx2 = cx + inward * PAGE_W * 0.36
    by2 = PAGE_H * 0.22
    d.line(cx, cy, bx2, by2, color=(96, 70, 52), lw=3.4)
    leaf_c = darken(pal.ground, 0.14)
    for t in (0.32, 0.5, 0.68, 0.86, 1.0):
        lx = cx + (bx2 - cx) * t
        ly = cy + (by2 - cy) * t
        for ang in (inward * 40, inward * 90, inward * 140):
            _leaf(d, lx, ly, 15, 4.2, ang, leaf_c)
    if not d.line_art:
        d.circle(bx2, by2, 3.0, fill=pal.accent2)


def _fg_flowers(d: Draw, pal: BookPalette, rng: random.Random, side: int) -> None:
    base_x = PAGE_W * 0.5 + side * PAGE_W * 0.44
    by = PAGE_H + 4
    stem = darken(pal.ground_dark, 0.14)
    for i in range(3):
        fx = base_x + (i - 1) * 14 + rng.uniform(-3, 3)
        fh = rng.uniform(26, 40)
        d.line(fx, by, fx, by - fh, color=stem, lw=1.6)
        _leaf(d, fx, by - fh * 0.5, 8, 2.6, -150 if i % 2 else -30, stem)
        _flower(d, fx, by - fh, rng.uniform(8, 11),
                [pal.accent, pal.accent2, pal.sun][i % 3], (255, 255, 255))


def _fg_reeds(d: Draw, pal: BookPalette, rng: random.Random, side: int) -> None:
    base_x = PAGE_W * 0.5 + side * PAGE_W * 0.45
    by = PAGE_H + 4
    col = darken(pal.ground_dark, 0.14)
    for i in range(6):
        rx = base_x + (i - 3) * 6 + rng.uniform(-1.5, 1.5)
        rh = rng.uniform(34, 52)
        d.line(rx, by, rx, by - rh, color=col, lw=2.0)
        if i % 2 == 0:
            d.rect(rx - 2.0, by - rh, 4.0, 12, fill=darken(col, 0.12) if not d.line_art else None,
                   stroke=(30, 30, 30) if d.line_art else None, lw=0.6, radius=1.6)


def _foreground(
    d: Draw, setting: str, pal: BookPalette, horizon: float,
    rng: random.Random, shot: str, line_art: bool,
) -> None:
    if line_art:
        return  # coloring pages stay clean; foreground is a color-only layer
    if shot == "close":
        # a whisper of grass in one corner keeps close-ups from feeling empty
        _fg_grass(d, pal, rng, side=rng.choice((-1, 1)), big=False)
        return
    kinds = _FG_KINDS.get(setting, ("grass", "bush", "branch"))
    kind = kinds[rng.randrange(len(kinds))]
    side = rng.choice((-1, 1))
    if kind == "branch":
        _fg_branch(d, pal, rng, side=rng.choice((-1, 1)))
        _fg_grass(d, pal, rng, side=-side, big=True)
    elif kind == "bush":
        _fg_bush(d, pal, rng, side=side)
        _fg_grass(d, pal, rng, side=-side, big=False)
    elif kind == "reeds":
        _fg_reeds(d, pal, rng, side=side)
    elif kind == "flowers":
        _fg_flowers(d, pal, rng, side=side)
        _fg_grass(d, pal, rng, side=-side, big=False)
    else:  # grass on both sides
        _fg_grass(d, pal, rng, side=1, big=True)
        _fg_grass(d, pal, rng, side=-1, big=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def draw_scene(
    pdf: FPDF,
    setting: str,
    palette: BookPalette,
    line_art: bool = False,
    time_of_day: str = "day",
    variant: int = 0,
    sparse: bool = False,
    horizon: float | None = None,
    sky_offset: float = 0.0,
    shot: str = "wide",
    zone: str = "",
    foreground: bool = True,
    background_cast: bool = True,
    age_band: str = "4-6",
) -> float:
    """Draw a full-bleed, layered storybook scene.

    Parameters
    ----------
    shot : camera framing (``establish``/``wide``/``corner``/``path``/
           ``close``/``hill``) -- sets the horizon when ``horizon`` is None
           and how heavy the foreground is.
    zone : which sub-location of the world to show (see ``SETTING_ZONES``);
           empty selects the world's home zone.
    foreground / background_cast : toggle the near/far depth layers (both are
           colour-only and always skipped in ``line_art`` mode).
    age_band : ``2-4`` | ``4-6`` | ``6-8`` -- scene complexity by age.
           2-4 strips the far cast and thins the midground props for a bold,
           uncluttered, high-contrast page (one dominant subject).  6-8 keeps
           the full depth stack and adds a recurring seek-and-find critter.

    Returns the y of the ground line where characters should stand.
    """
    d = Draw(pdf, line_art=line_art)
    rng = random.Random(_seed(setting, variant, shot, zone))

    if horizon is None:
        horizon = SHOT_HORIZON.get(shot, 0.63) * PAGE_H
    if line_art:
        sky_offset = max(sky_offset, 28.0)  # keep sky props below the header mask

    # Toddler pages: fewer, bolder shapes and no distant clutter.
    if age_band == "2-4" and not line_art:
        sparse = True
        background_cast = False

    _sky(d, palette, horizon, time_of_day)
    sun_x = _sky_objects(d, palette, rng, time_of_day, horizon, sky_offset)

    if background_cast and not line_art:
        if setting not in ("beach", "city"):
            _far_treeline(d, palette, horizon, rng)
        _background_cast(d, palette, horizon, rng, time_of_day, setting, sun_x, sky_offset)

    if setting not in ("beach", "city"):
        _hills(d, palette, horizon, rng, shot)

    ground_color = palette.ground
    flowers = True
    if setting == "beach":
        ground_color = mix(palette.ground, (242, 216, 160), 0.75)
        flowers = False
    elif setting == "city":
        ground_color = mix(palette.ground, (190, 186, 196), 0.45)
        flowers = False

    _ground(d, palette, horizon, rng, color=ground_color, flowers=flowers)

    prop_fn = _PROPS.get(setting, _park)
    prop_fn(d, palette, horizon, rng, sparse, zone, shot)

    if foreground:
        _foreground(d, setting, palette, horizon, rng, shot, line_art)

    # Early-reader seek-and-find: a little critter hiding in a new spot each
    # spread.  Drawn last so it sits on top and is findable; never on toddler
    # pages (keep them simple) or coloring pages (keep them clean).
    if age_band == "6-8":
        _search_critter(d, palette, horizon, rng)

    return horizon + (PAGE_H - horizon) * 0.42
