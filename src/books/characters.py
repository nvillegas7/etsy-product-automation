"""Kawaii flat-vector character drawing built on fpdf2 primitives.

Every character is drawn through :func:`draw_character` with a common
anchor convention:

- ``(x, y)`` is the **bottom-center** (ground contact point).
- ``scale``  is the total character height in millimetres.
- ``facing`` is ``1`` (facing right) or ``-1`` (facing left).

Proportions follow the kawaii bar: big rounded body/head (~60 % head),
tiny limbs, eyes in the lower half of the face with white highlight dots,
soft blush, small smile arcs.  The same code with ``line_art=True``
produces black-outline coloring-page versions.
"""

from __future__ import annotations

import math

from fpdf import FPDF

from src.books.illustrator import (
    Draw,
    OUTLINE_COLOR,
    RGB,
    darken,
    lighten,
)

INK: RGB = (60, 48, 60)
WHITE: RGB = (255, 255, 255)

EXPRESSIONS = (
    "happy", "sad", "surprised", "sleepy",
    "excited", "worried", "curious", "giggling",
)
POSES = ("stand", "arms_up", "wave", "point", "hug", "jump", "walk", "slump")

# ---------------------------------------------------------------------------
# Per-age-band character knobs (Kindchenschema / baby-schema)
# ---------------------------------------------------------------------------
# The book's age band is tagged onto the Draw instance by ``draw_character``
# and read here, so a single call threads age all the way into the face and
# limbs without changing 28 body-function signatures.
#
# Younger (2-4): eyes bigger and set LOWER in the head (the tall-forehead cue),
# bolder outlines, rounder cheeks, simplest face.  Older (6-8): relatively
# smaller eyes on the vertical midline, thinner outlines, a second eye sparkle
# for a touch more detail.  Grounded in Glocker et al. baby-schema proportions
# and the age-engagement dossier's per-band eye-size / contrast guidance.
_AGE_FACE: dict[str, dict[str, float]] = {
    #        eye-size  low-eye  stroke  catchlight  2nd-sparkle  blush
    "2-4": {"eye": 1.14, "drop": 0.055, "stroke": 1.35, "catch": 0.42, "sparkle": 0, "blush": 1.12},
    "4-6": {"eye": 1.00, "drop": 0.028, "stroke": 1.00, "catch": 0.34, "sparkle": 0, "blush": 1.00},
    "6-8": {"eye": 0.88, "drop": 0.000, "stroke": 0.85, "catch": 0.28, "sparkle": 1, "blush": 0.90},
}
# Limb build: toddlers get short, thick extremities; early readers slimmer.
_AGE_ARMS: dict[str, dict[str, float]] = {
    "2-4": {"lw": 0.075, "hand": 0.056, "reach": 0.88},
    "4-6": {"lw": 0.055, "hand": 0.045, "reach": 1.00},
    "6-8": {"lw": 0.048, "hand": 0.040, "reach": 1.06},
}


def _face_knobs(d: "Draw") -> dict[str, float]:
    return _AGE_FACE.get(getattr(d, "age_band", "4-6"), _AGE_FACE["4-6"])


def _arm_knobs(d: "Draw") -> dict[str, float]:
    return _AGE_ARMS.get(getattr(d, "age_band", "4-6"), _AGE_ARMS["4-6"])


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _q(
    p0: tuple[float, float],
    c: tuple[float, float],
    p1: tuple[float, float],
    n: int = 10,
) -> list[tuple[float, float]]:
    """Sample *n+1* points along a quadratic bezier."""
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        pts.append(
            (
                u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0],
                u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1],
            )
        )
    return pts


def _leaf(
    d: Draw,
    cx: float,
    cy: float,
    length: float,
    width: float,
    angle_deg: float,
    color: RGB,
) -> None:
    """Pointed-oval leaf centered on its base at (cx, cy), rotated."""
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    tip = (cx + length * ca, cy + length * sa)
    # control points perpendicular to the leaf axis at the midpoint
    mx, my = cx + 0.5 * length * ca, cy + 0.5 * length * sa
    px, py = -sa, ca
    c1 = (mx + width * px, my + width * py)
    c2 = (mx - width * px, my - width * py)
    pts = _q((cx, cy), c1, tip) + _q(tip, c2, (cx, cy))
    d.polygon(pts, fill=color)


# ---------------------------------------------------------------------------
# Face
# ---------------------------------------------------------------------------


def _face(
    d: Draw,
    cx: float,
    cy: float,
    fw: float,
    expr: str = "happy",
    facing: int = 1,
    ink: RGB = INK,
    blush: bool = True,
) -> None:
    """Kawaii face centered at (cx, cy); *fw* is the face width unit.

    Eyes sit on the horizontal center line (callers place *cy* in the
    lower half of the head), pupils get white highlight dots, mouth is a
    small arc, blush is soft ellipses.
    """
    k = _face_knobs(d)
    eo = fw * 0.30                  # eye x-offset
    er = fw * 0.105 * k["eye"]      # eye radius (bigger for toddlers)
    if expr in ("surprised", "excited", "curious"):
        er *= 1.2
    ey = cy + fw * k["drop"]        # low-set eyes = tall-forehead baby schema
    sk = k["stroke"]               # outline-weight scale (bolder for toddlers)

    flat_eyes = expr == "sleepy"
    happy_closed = expr == "giggling"       # ^ ^ delighted closed eyes
    for sx in (-1, 1):
        ex = cx + sx * eo
        if flat_eyes:
            d.arc(ex, ey, er * 1.3, 20, 160, color=ink, lw=max(fw * 0.032 * sk, 0.5))
        elif happy_closed:
            d.arc(ex, ey + er * 0.35, er * 1.3, 200, 340, color=ink,
                  lw=max(fw * 0.038 * sk, 0.55))
        else:
            d.circle(ex, ey, er, fill=ink, force_fill=True)
            if not d.line_art:
                d.dot(ex - er * 0.3, ey - er * 0.35, er * k["catch"], WHITE)
                if k["sparkle"]:        # older kids: a second tiny highlight
                    d.dot(ex + er * 0.32, ey + er * 0.30, er * 0.16, WHITE)

    # eyebrows (ride the eye line so they stay above low-set toddler eyes)
    if expr in ("sad", "worried"):
        for sx in (-1, 1):        # up-inner slant = concern
            x0 = cx + sx * (eo - er * 0.9)
            x1 = cx + sx * (eo + er * 0.9)
            d.line(x0, ey - er * 2.1, x1, ey - er * 1.5, color=ink, lw=max(fw * 0.03 * sk, 0.45))
    elif expr in ("surprised", "excited"):
        for sx in (-1, 1):        # both brows lifted
            d.arc(cx + sx * eo, ey - er * 2.0, er * 0.85, 200, 340,
                  color=ink, lw=max(fw * 0.03 * sk, 0.45))
    elif expr == "curious":
        # a single quizzically-raised brow on the facing side
        d.arc(cx + facing * eo, ey - er * 2.2, er * 0.9, 200, 340,
              color=ink, lw=max(fw * 0.03 * sk, 0.45))

    # blush (rounder, fuller cheeks for the youngest band)
    if blush:
        base = fw * 0.135 if expr in ("giggling", "excited") else fw * 0.115
        br = base * k["blush"]
        d.blush(cx - eo - fw * 0.17, cy + fw * 0.16, br)
        d.blush(cx + eo + fw * 0.17, cy + fw * 0.16, br)

    # mouth
    my = cy + fw * 0.24
    mlw = max(fw * 0.035 * sk, 0.5)
    if expr in ("happy", "curious"):
        d.arc(cx, my - fw * 0.04, fw * 0.15, 25, 155, color=ink, lw=mlw, ry=fw * 0.13)
    elif expr == "giggling":
        d.arc(cx, my - fw * 0.06, fw * 0.19, 22, 158, color=ink, lw=mlw, ry=fw * 0.17)
    elif expr == "excited":
        # wide open grin: filled mouth with a little tongue
        d.ellipse(cx, my + fw * 0.03, fw * 0.13, fw * 0.14,
                  fill=(120, 62, 74), force_fill=True)
        if not d.line_art:
            d.ellipse(cx, my + fw * 0.09, fw * 0.075, fw * 0.055, fill=(240, 128, 140))
    elif expr == "sad":
        d.arc(cx, my + fw * 0.12, fw * 0.13, 205, 335, color=ink, lw=mlw, ry=fw * 0.11)
    elif expr == "worried":
        d.arc(cx, my + fw * 0.09, fw * 0.10, 205, 335, color=ink, lw=mlw, ry=fw * 0.07)
    elif expr == "surprised":
        d.ellipse(cx, my + fw * 0.02, fw * 0.075, fw * 0.10,
                  fill=(120, 62, 74), force_fill=True)
    elif expr == "sleepy":
        d.arc(cx, my, fw * 0.09, 25, 155, color=ink, lw=mlw, ry=fw * 0.08)


# ---------------------------------------------------------------------------
# Limbs
# ---------------------------------------------------------------------------


def _arms(
    d: Draw,
    cx: float,
    cy: float,
    rx: float,
    h: float,
    pose: str,
    color: RGB,
    facing: int = 1,
) -> None:
    """Tiny stick arms with hand dots.  *cy* = shoulder height, *rx* = body
    half-width at the shoulders."""
    k = _arm_knobs(d)
    lw = h * k["lw"]                # thicker, stubbier limbs for toddlers
    hand_r = h * k["hand"]
    rf = k["reach"]                # slightly shorter reach for the youngest
    for sx in (-1, 1):
        x0 = cx + sx * rx * 0.92
        raised = pose in ("arms_up", "jump") or (pose == "wave" and sx == facing)
        if raised:
            x1 = cx + sx * (rx * 0.92 + h * 0.13 * rf)
            y1 = cy - h * 0.16
        elif pose == "point" and sx == facing:
            # one arm flung out ahead, slightly raised
            x1 = cx + sx * (rx * 0.92 + h * 0.21 * rf)
            y1 = cy - h * 0.03
        elif pose == "hug":
            # both arms curl inward-forward, as if wrapping a friend
            x1 = cx + sx * rx * 0.50
            y1 = cy + h * 0.21
        elif pose == "slump":
            # dropped, defeated shoulders -- arms hang low and limp,
            # tucked close to the body (pairs with a sad/worried face)
            x1 = cx + sx * rx * 0.70
            y1 = cy + h * 0.24
        elif pose == "walk":
            # a walking swing: facing arm forward-low, trailing arm back-low
            fwd = sx == facing
            x1 = cx + sx * (rx * 0.92 + h * 0.11 * rf)
            y1 = cy + (h * 0.05 if fwd else h * 0.21)
        else:
            x1 = cx + sx * (rx * 0.92 + h * 0.10 * rf)
            y1 = cy + h * 0.14
        d.line(x0, cy, x1, y1, color=color, lw=lw)
        d.dot(x1, y1, hand_r, color)


def _feet(d: Draw, x: float, y: float, h: float, color: RGB, spread: float = 0.16) -> None:
    """Two stubby oval feet at the ground anchor."""
    fr = h * 0.085
    for sx in (-1, 1):
        d.ellipse(x + sx * h * spread, y - fr * 0.5, fr, fr * 0.62, fill=color)


# ---------------------------------------------------------------------------
# Character color tables
# ---------------------------------------------------------------------------

COLORS: dict[str, dict[str, RGB]] = {
    "apple":      {"body": (236, 90, 84), "leaf": (116, 190, 92), "stem": (146, 100, 62)},
    "banana":     {"body": (250, 212, 90), "tip": (150, 110, 62)},
    "strawberry": {"body": (240, 90, 106), "leaf": (104, 182, 88), "seed": (255, 235, 190)},
    "orange":     {"body": (247, 158, 66), "leaf": (116, 190, 92)},
    "pear":       {"body": (190, 210, 92), "leaf": (104, 182, 88), "stem": (146, 100, 62)},
    "watermelon": {"body": (120, 190, 100), "stripe": (84, 150, 74)},
    "carrot":     {"body": (245, 140, 66), "leaf": (110, 186, 90)},
    "broccoli":   {"body": (168, 208, 110), "crown": (96, 160, 82)},
    "tomato":     {"body": (238, 100, 78), "leaf": (104, 176, 88)},
    "corn":       {"body": (250, 214, 96), "husk": (140, 196, 104)},
    "pea_pod":    {"body": (120, 184, 96), "pea": (172, 220, 130)},
    "fox":        {"body": (240, 140, 82), "belly": (255, 244, 230), "ear": (250, 232, 220)},
    "bunny":      {"body": (238, 232, 228), "ear": (250, 190, 196)},
    "bear":       {"body": (188, 140, 100), "muzzle": (232, 206, 178)},
    "owl":        {"body": (176, 138, 110), "belly": (240, 222, 198), "beak": (240, 165, 70)},
    "hedgehog":   {"body": (238, 208, 172), "spikes": (162, 118, 86)},
    "cow":        {"body": (248, 244, 238), "patch": (90, 80, 88), "muzzle": (248, 190, 186)},
    "pig":        {"body": (248, 180, 184), "snout": (238, 142, 150)},
    "chick":      {"body": (252, 216, 94), "beak": (245, 150, 66)},
    "sheep":      {"body": (246, 240, 232), "face": (222, 190, 164)},
    "octopus":    {"body": (196, 138, 208)},
    "turtle":     {"body": (140, 198, 118), "shell": (176, 138, 96), "shell2": (206, 170, 122)},
    "crab":       {"body": (238, 108, 92)},
    "fish":       {"body": (110, 180, 224), "fin": (76, 146, 196)},
    "cat":        {"body": (242, 190, 140), "ear": (250, 214, 208)},
    "dog":        {"body": (216, 178, 134), "ear": (172, 130, 92), "patch": (245, 234, 218)},
    "hamster":    {"body": (244, 196, 130), "belly": (252, 238, 216)},
    "bee":        {"body": (250, 210, 84), "stripe": (110, 88, 60), "wing": (230, 240, 252)},
    "squirrel":   {"body": (198, 138, 92), "belly": (244, 224, 200), "ear": (224, 176, 132),
                   "tail": (176, 118, 76)},
    "ladybug":    {"body": (226, 78, 74), "spot": (58, 46, 54), "head": (58, 46, 54),
                   "wing": (236, 240, 250)},
    "snail":      {"body": (232, 196, 168), "shell": (232, 156, 96), "shell2": (250, 206, 150),
                   "horn": (150, 110, 86)},
    # -- arctic --
    "penguin":    {"body": (72, 84, 108), "belly": (250, 250, 252), "beak": (247, 158, 66),
                   "foot": (245, 150, 66)},
    "seal":       {"body": (156, 166, 184), "belly": (226, 231, 239), "flipper": (128, 138, 158),
                   "nose": (72, 66, 78)},
    "polar_bear": {"body": (247, 248, 251), "muzzle": (228, 233, 242), "nose": (78, 72, 84)},
    # -- jungle / savanna --
    "elephant":   {"body": (176, 174, 200), "ear": (192, 190, 214), "belly": (208, 206, 226),
                   "tusk": (250, 246, 236)},
    "lion":       {"body": (246, 192, 118), "mane": (224, 150, 74), "muzzle": (251, 234, 202),
                   "ear": (240, 210, 168)},
    "monkey":     {"body": (168, 122, 84), "face": (238, 206, 166), "ear": (238, 206, 166),
                   "belly": (240, 210, 172)},
    # -- pond friends --
    "frog":       {"body": (140, 200, 110), "belly": (216, 236, 172), "spot": (104, 168, 82),
                   "foot": (118, 178, 92)},
    "duck":       {"body": (249, 249, 251), "wing": (232, 234, 240), "beak": (245, 168, 72),
                   "foot": (245, 150, 66)},
    # -- cozy / woodland --
    "panda":      {"body": (250, 250, 250), "patch": (60, 56, 66), "muzzle": (244, 244, 246)},
    "koala":      {"body": (172, 178, 188), "belly": (224, 228, 236), "ear": (196, 202, 212),
                   "nose": (84, 78, 90)},
    "deer":       {"body": (198, 148, 102), "belly": (240, 224, 200), "spot": (245, 234, 214),
                   "antler": (172, 134, 94), "ear": (216, 178, 138), "nose": (86, 70, 74)},
    "raccoon":    {"body": (152, 160, 172), "belly": (226, 230, 238), "mask": (66, 62, 74),
                   "ear": (176, 182, 194), "tail": (108, 114, 128)},
    # -- mythical --
    "unicorn":    {"body": (250, 244, 250), "mane": (250, 178, 206), "horn": (255, 214, 120),
                   "hoof": (222, 204, 234), "muzzle": (250, 236, 242)},
    "dragon":     {"body": (150, 206, 150), "belly": (232, 240, 196), "wing": (200, 168, 218),
                   "spike": (110, 172, 112), "horn": (240, 224, 180)},
    "dino":       {"body": (150, 196, 224), "belly": (224, 238, 198), "plate": (118, 168, 204),
                   "cheek": (250, 196, 150)},
}


# ---------------------------------------------------------------------------
# Individual character bodies
# ---------------------------------------------------------------------------
# Every function: (d, x, y, h, expr, pose, facing) with the shared anchor.


def _round_food(
    d: Draw, x: float, y: float, h: float, expr: str, pose: str, facing: int,
    body: RGB, rx_f: float = 0.42, ry_f: float = 0.40,
) -> tuple[float, float, float]:
    """Shared round fruit/veg body.  Returns (cx, cy, rx) of the body."""
    rx, ry = h * rx_f, h * ry_f
    cy = y - ry - h * 0.06
    _feet(d, x, y, h, darken(body, 0.25))
    _arms(d, x, cy + ry * 0.15, rx, h, pose, darken(body, 0.25), facing)
    d.ellipse(x, cy, rx, ry, fill=body)
    return x, cy, rx


def _apple(d, x, y, h, expr, pose, facing):
    c = COLORS["apple"]
    cx, cy, rx = _round_food(d, x, y, h, expr, pose, facing, c["body"])
    top = cy - h * 0.40
    d.line(cx, top + h * 0.02, cx + facing * h * 0.03, top - h * 0.09,
           color=c["stem"], lw=h * 0.045)
    _leaf(d, cx + facing * h * 0.04, top - h * 0.07, h * 0.16, h * 0.05,
          -25 if facing > 0 else 205, c["leaf"])
    if not d.line_art:
        d.dot(cx - rx * 0.45, cy - h * 0.22, h * 0.05, lighten(c["body"], 0.35))
    _face(d, cx + facing * h * 0.02, cy + h * 0.03, h * 0.52, expr, facing)


def _orange(d, x, y, h, expr, pose, facing):
    c = COLORS["orange"]
    cx, cy, rx = _round_food(d, x, y, h, expr, pose, facing, c["body"])
    _leaf(d, cx + h * 0.02, cy - h * 0.40, h * 0.15, h * 0.05,
          -35 if facing > 0 else 215, c["leaf"])
    if not d.line_art:
        for ang in (200, 240, 320):
            a = math.radians(ang)
            d.dot(cx + rx * 0.7 * math.cos(a), cy + rx * 0.68 * math.sin(a),
                  h * 0.018, darken(c["body"], 0.18))
    _face(d, cx + facing * h * 0.02, cy + h * 0.03, h * 0.52, expr, facing)


def _tomato(d, x, y, h, expr, pose, facing):
    c = COLORS["tomato"]
    cx, cy, rx = _round_food(d, x, y, h, expr, pose, facing, c["body"], 0.44, 0.37)
    top = cy - h * 0.34
    for ang in (-150, -110, -70, -30):
        _leaf(d, cx, top + h * 0.02, h * 0.15, h * 0.05, ang, c["leaf"])
    d.line(cx, top, cx, top - h * 0.07, color=darken(c["leaf"], 0.2), lw=h * 0.04)
    _face(d, cx + facing * h * 0.02, cy + h * 0.05, h * 0.52, expr, facing)


def _watermelon(d, x, y, h, expr, pose, facing):
    c = COLORS["watermelon"]
    rx, ry = h * 0.44, h * 0.41
    cy = y - ry - h * 0.05
    _feet(d, x, y, h, darken(c["body"], 0.25))
    _arms(d, x, cy + ry * 0.15, rx, h, pose, darken(c["body"], 0.25), facing)
    d.ellipse(x, cy, rx, ry, fill=c["body"])
    if not d.line_art:
        for fx in (-0.55, 0.0, 0.55):
            dx = fx * rx
            sry = ry * math.sqrt(max(0.0, 1 - (dx / rx) ** 2)) * 0.92
            d.ellipse(x + dx, cy, rx * 0.075, sry, fill=c["stripe"])
    _face(d, x + facing * h * 0.02, cy + h * 0.04, h * 0.5, expr, facing)


def _strawberry(d, x, y, h, expr, pose, facing):
    c = COLORS["strawberry"]
    w = h * 0.42
    top_y = y - h * 0.80
    cy = y - h * 0.45
    _feet(d, x, y, h, darken(c["body"], 0.25), spread=0.13)
    _arms(d, x, cy, w * 0.9, h, pose, darken(c["body"], 0.25), facing)
    # teardrop body: dome top + curved sides converging to a rounded bottom
    left = _q((x - w, cy - h * 0.06), (x - w * 0.82, y - h * 0.16), (x - w * 0.22, y - h * 0.015))
    bottom = _q((x - w * 0.22, y - h * 0.015), (x, y + h * 0.03), (x + w * 0.22, y - h * 0.015))
    right = _q((x + w * 0.22, y - h * 0.015), (x + w * 0.82, y - h * 0.16), (x + w, cy - h * 0.06))
    dome = []
    for i in range(13):  # from right edge over the top back to the left edge
        a = -i * math.pi / 12
        dome.append((x + w * math.cos(a), (cy - h * 0.06) + (h * 0.32) * math.sin(a)))
    d.polygon(left + bottom + right + dome, fill=c["body"])
    # leafy crown
    for ang in (-155, -115, -90, -65, -25):
        _leaf(d, x, top_y + h * 0.03, h * 0.16, h * 0.055, ang, c["leaf"])
    # seeds along the outer flanks, away from the face
    if not d.line_art:
        for sx, sy in ((-0.66, -0.02), (0.66, -0.02), (-0.52, 0.30), (0.52, 0.30),
                       (-0.2, 0.55), (0.2, 0.55)):
            d.dot(x + sx * w, cy + sy * h * 0.42, h * 0.015, c["seed"])
    _face(d, x + facing * h * 0.02, cy - h * 0.02, h * 0.5, expr, facing)


def _pear(d, x, y, h, expr, pose, facing):
    c = COLORS["pear"]
    rl, rly = h * 0.40, h * 0.32
    cyl = y - rly - h * 0.05
    ru = h * 0.24
    cyu = y - h * 0.72
    _feet(d, x, y, h, darken(c["body"], 0.25))
    _arms(d, x, cyl, rl, h, pose, darken(c["body"], 0.25), facing)
    d.ellipse(x, cyl, rl, rly, fill=c["body"])
    d.ellipse(x, cyu, ru, ru * 1.05, fill=c["body"])
    d.line(x, cyu - ru, x + facing * h * 0.04, cyu - ru - h * 0.09,
           color=c["stem"], lw=h * 0.04)
    _leaf(d, x + facing * h * 0.05, cyu - ru - h * 0.07, h * 0.14, h * 0.05,
          -20 if facing > 0 else 200, c["leaf"])
    _face(d, x + facing * h * 0.02, cyl - h * 0.05, h * 0.48, expr, facing)


def _banana(d, x, y, h, expr, pose, facing):
    c = COLORS["banana"]
    # crescent: outer/inner arcs around a center offset opposite the facing
    ccx = x - facing * h * 0.30
    ccy = y - h * 0.44
    R, r = h * 0.52, h * 0.24
    outer, inner = [], []
    a0, a1 = -70, 70
    for i in range(19):
        a = math.radians(a0 + (a1 - a0) * i / 18)
        outer.append((ccx + facing * R * math.cos(a), ccy + R * math.sin(a)))
    for i in range(19):
        a = math.radians(a1 - (a1 - a0) * i / 18)
        inner.append((ccx + facing * r * math.cos(a) + facing * h * 0.10,
                      ccy + r * math.sin(a) * 0.9))
    d.polygon(outer + inner, fill=c["body"])
    d.dot(ccx + facing * (R - h * 0.02) * math.cos(math.radians(a0)),
          ccy + (R - h * 0.02) * math.sin(math.radians(a0)), h * 0.035, c["tip"])
    d.dot(ccx + facing * (R - h * 0.02) * math.cos(math.radians(a1)),
          ccy + (R - h * 0.02) * math.sin(math.radians(a1)), h * 0.035, c["tip"])
    _feet(d, x, y, h, darken(c["body"], 0.3), spread=0.12)
    _arms(d, x + facing * h * 0.05, y - h * 0.38, h * 0.16, h, pose,
          darken(c["body"], 0.3), facing)
    _face(d, ccx + facing * (R - r) * 0.72, ccy, h * 0.42, expr, facing)


def _carrot(d, x, y, h, expr, pose, facing):
    c = COLORS["carrot"]
    w = h * 0.30
    top_y = y - h * 0.78
    _arms(d, x, y - h * 0.45, w * 0.95, h, pose, darken(c["body"], 0.22), facing)
    left = _q((x - w, top_y + h * 0.06), (x - w * 0.55, y - h * 0.28), (x - h * 0.05, y - h * 0.01))
    tip = _q((x - h * 0.05, y - h * 0.01), (x, y + h * 0.03), (x + h * 0.05, y - h * 0.01))
    right = _q((x + h * 0.05, y - h * 0.01), (x + w * 0.55, y - h * 0.28), (x + w, top_y + h * 0.06))
    cap = []
    for i in range(13):
        a = math.pi + i * math.pi / 12
        cap.append((x + w * math.cos(a), top_y + h * 0.06 + h * 0.10 * math.sin(a)))
    d.polygon(left + tip + right + cap, fill=c["body"])
    for ang in (-125, -90, -55):
        _leaf(d, x, top_y + h * 0.015, h * 0.20, h * 0.05, ang, c["leaf"])
    _face(d, x + facing * h * 0.02, y - h * 0.52, h * 0.44, expr, facing)


def _broccoli(d, x, y, h, expr, pose, facing):
    c = COLORS["broccoli"]
    # stem
    d.rect(x - h * 0.11, y - h * 0.42, h * 0.22, h * 0.42, fill=c["body"], radius=h * 0.07)
    _feet(d, x, y, h, darken(c["body"], 0.2), spread=0.12)
    _arms(d, x, y - h * 0.30, h * 0.13, h, pose, darken(c["body"], 0.2), facing)
    # crown: cluster of puffs
    ccy = y - h * 0.62
    for px, py, pr in ((-0.22, 0.02, 0.17), (0.22, 0.02, 0.17), (-0.12, -0.15, 0.16),
                       (0.12, -0.15, 0.16), (0.0, 0.03, 0.20)):
        d.circle(x + px * h, ccy + py * h, pr * h, fill=c["crown"])
    _face(d, x + facing * h * 0.015, ccy + h * 0.02, h * 0.42, expr, facing)


def _corn(d, x, y, h, expr, pose, facing):
    c = COLORS["corn"]
    rx, ry = h * 0.26, h * 0.45
    cy = y - ry - h * 0.04
    _feet(d, x, y, h, darken(c["body"], 0.25), spread=0.12)
    _arms(d, x, cy + ry * 0.2, rx, h, pose, darken(c["body"], 0.25), facing)
    d.ellipse(x, cy, rx, ry, fill=c["body"])
    if not d.line_art:
        for gy in (-0.28, -0.13, 0.02):
            for gx in (-0.5, 0.0, 0.5):
                d.dot(x + gx * rx, cy + (gy + 0.38) * ry, h * 0.022, darken(c["body"], 0.14))
    _leaf(d, x - rx * 0.75, y - h * 0.18, h * 0.34, h * 0.09, -115, c["husk"])
    _leaf(d, x + rx * 0.75, y - h * 0.18, h * 0.34, h * 0.09, -65, c["husk"])
    _face(d, x + facing * h * 0.015, cy - ry * 0.30, h * 0.42, expr, facing)


def _pea_pod(d, x, y, h, expr, pose, facing):
    c = COLORS["pea_pod"]
    rx, ry = h * 0.24, h * 0.46
    cy = y - ry - h * 0.04
    _feet(d, x, y, h, darken(c["body"], 0.2), spread=0.11)
    _arms(d, x, cy + ry * 0.15, rx, h, pose, darken(c["body"], 0.2), facing)
    d.ellipse(x, cy, rx, ry, fill=c["body"])
    pr = h * 0.13
    for i, py in enumerate((-0.52, 0.0, 0.52)):
        d.circle(x, cy + py * ry, pr, fill=c["pea"])
    _face(d, x + facing * h * 0.01, cy, h * 0.34, expr, facing)


def _fox(d, x, y, h, expr, pose, facing):
    c = COLORS["fox"]
    hr = h * 0.30                       # head radius
    hcy = y - h * 0.62                  # head center
    bry = h * 0.34
    bcy = y - bry + h * 0.02
    # tail: swooping leaf behind body, cream tip tucked inside the point
    tail_ang = -145 if facing > 0 else -35
    _leaf(d, x - facing * h * 0.24, y - h * 0.10, h * 0.44, h * 0.14, tail_ang, c["body"])
    ta = math.radians(tail_ang)
    d.dot(x - facing * h * 0.24 + h * 0.34 * math.cos(ta),
          y - h * 0.10 + h * 0.34 * math.sin(ta), h * 0.055, c["belly"])
    # body
    d.ellipse(x, bcy, h * 0.28, bry, fill=c["body"])
    d.ellipse(x, bcy + h * 0.08, h * 0.17, h * 0.20, fill=c["belly"])
    _feet(d, x, y, h, darken(c["body"], 0.28), spread=0.15)
    _arms(d, x, bcy - h * 0.02, h * 0.26, h, pose, darken(c["body"], 0.18), facing)
    # ears
    for sx in (-1, 1):
        ex = x + sx * hr * 0.62
        d.polygon([(ex - hr * 0.30, hcy - hr * 0.55), (ex, hcy - hr * 1.30),
                   (ex + hr * 0.30, hcy - hr * 0.55)], fill=c["body"])
        d.polygon([(ex - hr * 0.14, hcy - hr * 0.62), (ex, hcy - hr * 1.08),
                   (ex + hr * 0.14, hcy - hr * 0.62)], fill=c["ear"])
    # head + muzzle patch
    d.circle(x, hcy, hr, fill=c["body"])
    d.ellipse(x, hcy + hr * 0.42, hr * 0.62, hr * 0.42, fill=c["belly"])
    _face(d, x + facing * h * 0.015, hcy + hr * 0.10, h * 0.42, expr, facing)
    d.dot(x + facing * h * 0.015, hcy + hr * 0.42, h * 0.028, INK)


def _bunny(d, x, y, h, expr, pose, facing):
    c = COLORS["bunny"]
    hr = h * 0.26
    hcy = y - h * 0.50
    # ears
    for sx in (-1, 1):
        ex = x + sx * hr * 0.45
        d.ellipse(ex, hcy - hr * 1.55, hr * 0.24, hr * 0.85, fill=c["body"])
        d.ellipse(ex, hcy - hr * 1.52, hr * 0.11, hr * 0.60, fill=c["ear"])
    # body
    bry = h * 0.28
    bcy = y - bry + h * 0.02
    d.ellipse(x, bcy, h * 0.25, bry, fill=c["body"])
    d.dot(x - facing * h * 0.24, y - h * 0.16, h * 0.07, lighten(c["body"], 0.3))
    _feet(d, x, y, h, darken(c["body"], 0.15), spread=0.14)
    _arms(d, x, bcy - h * 0.03, h * 0.23, h, pose, darken(c["body"], 0.12), facing)
    # head
    d.circle(x, hcy, hr, fill=c["body"])
    _face(d, x + facing * h * 0.012, hcy + hr * 0.18, h * 0.40, expr, facing)
    d.dot(x + facing * h * 0.012, hcy + hr * 0.44, h * 0.022, (232, 150, 160))


def _bear(d, x, y, h, expr, pose, facing):
    c = COLORS["bear"]
    hr = h * 0.30
    hcy = y - h * 0.58
    # ears
    for sx in (-1, 1):
        d.circle(x + sx * hr * 0.72, hcy - hr * 0.72, hr * 0.30, fill=c["body"])
        d.circle(x + sx * hr * 0.72, hcy - hr * 0.72, hr * 0.15, fill=c["muzzle"])
    # body
    bry = h * 0.32
    bcy = y - bry + h * 0.02
    d.ellipse(x, bcy, h * 0.29, bry, fill=c["body"])
    d.ellipse(x, bcy + h * 0.07, h * 0.18, h * 0.20, fill=c["muzzle"])
    _feet(d, x, y, h, darken(c["body"], 0.25), spread=0.16)
    _arms(d, x, bcy - h * 0.02, h * 0.27, h, pose, darken(c["body"], 0.15), facing)
    # head + muzzle
    d.circle(x, hcy, hr, fill=c["body"])
    d.ellipse(x, hcy + hr * 0.42, hr * 0.48, hr * 0.34, fill=c["muzzle"])
    _face(d, x + facing * h * 0.012, hcy + hr * 0.08, h * 0.42, expr, facing)
    d.dot(x + facing * h * 0.012, hcy + hr * 0.38, h * 0.028, INK)


def _owl(d, x, y, h, expr, pose, facing):
    c = COLORS["owl"]
    rx, ry = h * 0.34, h * 0.42
    cy = y - ry - h * 0.04
    # ear tufts
    for sx in (-1, 1):
        ex = x + sx * rx * 0.62
        d.polygon([(ex - h * 0.06, cy - ry * 0.72), (ex + sx * h * 0.045, cy - ry * 1.18),
                   (ex + h * 0.06, cy - ry * 0.75)], fill=c["body"])
    # body
    d.ellipse(x, cy, rx, ry, fill=c["body"])
    # wings
    for sx in (-1, 1):
        d.ellipse(x + sx * rx * 0.88, cy + ry * 0.10, h * 0.09, h * 0.22,
                  fill=darken(c["body"], 0.15))
    # belly
    d.ellipse(x, cy + ry * 0.35, rx * 0.58, ry * 0.48, fill=c["belly"])
    if not d.line_art:
        for by in (0.28, 0.48):
            for bx in (-0.22, 0.22):
                d.arc(x + bx * rx, cy + ry * (by + 0.14), h * 0.035, 25, 155,
                      color=darken(c["belly"], 0.2), lw=h * 0.014)
    _feet(d, x, y, h, c["beak"], spread=0.13)
    # eye discs + face
    fw = h * 0.46
    fcy = cy - ry * 0.28
    for sx in (-1, 1):
        d.circle(x + sx * fw * 0.30, fcy, fw * 0.20, fill=WHITE if not d.line_art else None,
                 stroke=None if not d.line_art else (30, 30, 30), lw=0.55)
    _face(d, x, fcy, fw, expr, facing, blush=False)
    d.polygon([(x - h * 0.035, fcy + fw * 0.18), (x + h * 0.035, fcy + fw * 0.18),
               (x, fcy + fw * 0.34)], fill=c["beak"])
    d.blush(x - fw * 0.52, fcy + fw * 0.30, fw * 0.11)
    d.blush(x + fw * 0.52, fcy + fw * 0.30, fw * 0.11)


def _hedgehog(d, x, y, h, expr, pose, facing):
    c = COLORS["hedgehog"]
    bcx = x - facing * h * 0.04
    bcy = y - h * 0.38
    # spikes: fan across the back and top only (never under the chin)
    n = 8
    for i in range(n):
        a = 155 + i * (335 - 155) / (n - 1)
        if facing < 0:
            a = 180 - a
        a = math.radians(a)
        tip = (bcx + h * 0.55 * math.cos(a), bcy + h * 0.55 * math.sin(a))
        pa = a + math.radians(12)
        pb = a - math.radians(12)
        d.polygon([(bcx + h * 0.30 * math.cos(pa), bcy + h * 0.30 * math.sin(pa)),
                   tip,
                   (bcx + h * 0.30 * math.cos(pb), bcy + h * 0.30 * math.sin(pb))],
                  fill=c["spikes"])
    d.circle(bcx, bcy, h * 0.35, fill=c["spikes"])
    # face/body front
    d.ellipse(x + facing * h * 0.10, y - h * 0.30, h * 0.30, h * 0.29, fill=c["body"])
    _feet(d, x + facing * h * 0.06, y, h, darken(c["body"], 0.3), spread=0.13)
    _arms(d, x + facing * h * 0.10, y - h * 0.32, h * 0.19, h * 0.8, pose,
          darken(c["body"], 0.3), facing)
    _face(d, x + facing * h * 0.14, y - h * 0.33, h * 0.38, expr, facing)
    d.dot(x + facing * h * 0.14, y - h * 0.33 + h * 0.38 * 0.42, h * 0.026, INK)


def _cow(d, x, y, h, expr, pose, facing):
    c = COLORS["cow"]
    hr = h * 0.30
    hcy = y - h * 0.58
    # horns + ears
    for sx in (-1, 1):
        d.ellipse(x + sx * hr * 0.85, hcy - hr * 0.65, h * 0.055, h * 0.035,
                  fill=(228, 214, 186))
        d.ellipse(x + sx * hr * 0.95, hcy - hr * 0.15, h * 0.09, h * 0.05,
                  fill=c["muzzle"])
    # body
    bry = h * 0.32
    bcy = y - bry + h * 0.02
    d.ellipse(x, bcy, h * 0.29, bry, fill=c["body"])
    d.ellipse(x - facing * h * 0.10, bcy + h * 0.02, h * 0.10, h * 0.08, fill=c["patch"])
    _feet(d, x, y, h, c["patch"], spread=0.16)
    _arms(d, x, bcy - h * 0.02, h * 0.27, h, pose, darken(c["body"], 0.2), facing)
    # head, patch, muzzle
    d.circle(x, hcy, hr, fill=c["body"])
    d.ellipse(x + facing * hr * 0.55, hcy - hr * 0.5, hr * 0.32, hr * 0.26, fill=c["patch"])
    _face(d, x, hcy - hr * 0.02, h * 0.40, expr, facing)
    d.ellipse(x, hcy + hr * 0.52, hr * 0.46, hr * 0.28, fill=c["muzzle"])
    d.dot(x - hr * 0.16, hcy + hr * 0.50, h * 0.02, darken(c["muzzle"], 0.35))
    d.dot(x + hr * 0.16, hcy + hr * 0.50, h * 0.02, darken(c["muzzle"], 0.35))


def _pig(d, x, y, h, expr, pose, facing):
    c = COLORS["pig"]
    rx, ry = h * 0.40, h * 0.38
    cy = y - ry - h * 0.05
    for sx in (-1, 1):
        ex = x + sx * rx * 0.62
        d.polygon([(ex - h * 0.07, cy - ry * 0.62), (ex + sx * h * 0.03, cy - ry * 1.02),
                   (ex + h * 0.07, cy - ry * 0.66)], fill=darken(c["body"], 0.08))
    _feet(d, x, y, h, darken(c["body"], 0.2))
    _arms(d, x, cy + ry * 0.15, rx, h, pose, darken(c["body"], 0.15), facing)
    d.ellipse(x, cy, rx, ry, fill=c["body"])
    _face(d, x, cy - h * 0.06, h * 0.5, expr, facing, blush=True)
    d.ellipse(x, cy + h * 0.10, h * 0.10, h * 0.068, fill=c["snout"])
    d.dot(x - h * 0.035, cy + h * 0.10, h * 0.016, darken(c["snout"], 0.35))
    d.dot(x + h * 0.035, cy + h * 0.10, h * 0.016, darken(c["snout"], 0.35))


def _chick(d, x, y, h, expr, pose, facing):
    c = COLORS["chick"]
    r = h * 0.40
    cy = y - r - h * 0.06
    # head tuft
    for ang in (-115, -90, -65):
        _leaf(d, x, cy - r * 0.92, h * 0.10, h * 0.03, ang, c["beak"])
    # wings
    for sx in (-1, 1):
        d.ellipse(x + sx * r * 0.92, cy + r * 0.05, h * 0.09, h * 0.16,
                  fill=darken(c["body"], 0.12))
    d.circle(x, cy, r, fill=c["body"])
    _feet(d, x, y, h, c["beak"], spread=0.13)
    _face(d, x, cy - h * 0.02, h * 0.46, expr, facing)
    d.polygon([(x - h * 0.035, cy + h * 0.085), (x + h * 0.035, cy + h * 0.085),
               (x, cy + h * 0.15)], fill=c["beak"])


def _sheep(d, x, y, h, expr, pose, facing):
    c = COLORS["sheep"]
    r = h * 0.36
    cy = y - r - h * 0.07
    # wool: ring of puffs
    for i in range(10):
        a = math.radians(i * 36)
        d.circle(x + r * 0.85 * math.cos(a), cy + r * 0.82 * math.sin(a),
                 r * 0.34, fill=c["body"])
    d.circle(x, cy, r * 0.95, fill=c["body"])
    _feet(d, x, y, h, darken(c["face"], 0.3), spread=0.14)
    _arms(d, x, cy + r * 0.4, r * 0.95, h, pose, darken(c["face"], 0.15), facing)
    # face
    fcy = cy + h * 0.015
    for sx in (-1, 1):
        d.ellipse(x + sx * r * 0.62, fcy - h * 0.01, h * 0.075, h * 0.045, fill=c["face"])
    d.ellipse(x, fcy, r * 0.56, r * 0.52, fill=c["face"])
    d.circle(x - r * 0.28, fcy - r * 0.52, r * 0.22, fill=c["body"])
    d.circle(x + r * 0.28, fcy - r * 0.52, r * 0.22, fill=c["body"])
    _face(d, x, fcy + h * 0.008, h * 0.36, expr, facing)


def _octopus(d, x, y, h, expr, pose, facing):
    c = COLORS["octopus"]
    rx, ry = h * 0.40, h * 0.36
    cy = y - ry - h * 0.10
    # legs: row of bumps along the bottom
    lr = h * 0.105
    for i, lx in enumerate((-0.62, -0.22, 0.22, 0.62)):
        d.circle(x + lx * rx * 1.15, y - lr * 0.9, lr, fill=darken(c["body"], 0.08))
    d.ellipse(x, cy, rx, ry, fill=c["body"])
    d.rect(x - rx * 0.92, cy + ry * 0.35, rx * 1.84, ry * 0.75, fill=c["body"], radius=h * 0.06)
    _arms(d, x, cy + ry * 0.2, rx, h, pose, darken(c["body"], 0.15), facing)
    _face(d, x + facing * h * 0.015, cy + h * 0.02, h * 0.5, expr, facing)


def _turtle(d, x, y, h, expr, pose, facing):
    c = COLORS["turtle"]
    # shell dome behind
    scx = x - facing * h * 0.10
    d.ellipse(scx, y - h * 0.34, h * 0.34, h * 0.30, fill=c["shell"])
    if not d.line_art:
        for px, py in ((-0.14, -0.42), (0.1, -0.5), (-0.02, -0.24)):
            d.circle(scx + px * h, y + py * h, h * 0.055, fill=c["shell2"])
    # head
    hr = h * 0.24
    hcx = x + facing * h * 0.18
    hcy = y - h * 0.62
    d.rect(hcx - h * 0.075 - (facing < 0) * 0, hcy, h * 0.15, h * 0.35, fill=c["body"],
           radius=h * 0.06)
    d.circle(hcx, hcy, hr, fill=c["body"])
    _feet(d, x + facing * h * 0.05, y, h, darken(c["body"], 0.2), spread=0.17)
    _arms(d, scx, y - h * 0.30, h * 0.32, h, pose, darken(c["body"], 0.12), facing)
    _face(d, hcx + facing * h * 0.01, hcy + hr * 0.12, h * 0.34, expr, facing)


def _crab(d, x, y, h, expr, pose, facing):
    c = COLORS["crab"]
    rx, ry = h * 0.42, h * 0.30
    cy = y - ry - h * 0.10
    # legs
    for sx in (-1, 1):
        for i in range(3):
            lx0 = x + sx * rx * 0.7
            ly0 = cy + ry * (0.3 + i * 0.25)
            d.line(lx0, ly0, lx0 + sx * h * 0.14, ly0 + h * 0.09,
                   color=darken(c["body"], 0.15), lw=h * 0.035)
    # claw arms
    up = pose in ("arms_up", "wave")
    for sx in (-1, 1):
        raised = up and (pose == "arms_up" or sx == facing)
        ax = x + sx * (rx + h * 0.10)
        ay = cy - ry * (0.9 if raised else 0.1)
        d.line(x + sx * rx * 0.85, cy - ry * 0.2, ax, ay,
               color=darken(c["body"], 0.15), lw=h * 0.045)
        d.circle(ax, ay - h * 0.035, h * 0.085, fill=c["body"])
        d.polygon([(ax - h * 0.03, ay - h * 0.10), (ax + h * 0.03, ay - h * 0.10),
                   (ax, ay - h * 0.028)], fill=WHITE if not d.line_art else None,
                  stroke=(30, 30, 30) if d.line_art else None, lw=0.5)
    d.ellipse(x, cy, rx, ry, fill=c["body"])
    _feet(d, x, y, h, darken(c["body"], 0.25), spread=0.15)
    _face(d, x, cy - h * 0.01, h * 0.46, expr, facing)


def _fish(d, x, y, h, expr, pose, facing):
    c = COLORS["fish"]
    rx, ry = h * 0.40, h * 0.30
    cy = y - h * 0.42
    # tail
    tx = x - facing * rx * 1.02
    d.polygon([(tx, cy), (tx - facing * h * 0.20, cy - h * 0.17),
               (tx - facing * h * 0.14, cy), (tx - facing * h * 0.20, cy + h * 0.17)],
              fill=c["fin"])
    # top fin
    d.polygon([(x - facing * h * 0.10, cy - ry * 0.85), (x + facing * h * 0.06, cy - ry * 1.35),
               (x + facing * h * 0.16, cy - ry * 0.8)], fill=c["fin"])
    d.ellipse(x, cy, rx, ry, fill=c["body"])
    # side fin
    d.ellipse(x - facing * h * 0.05, cy + ry * 0.35, h * 0.10, h * 0.05, fill=c["fin"])
    if not d.line_art:
        d.ellipse(x - facing * rx * 0.55, cy, rx * 0.22, ry * 0.8,
                  fill=lighten(c["body"], 0.22))
    # bubbles
    if not d.line_art:
        d.circle(x + facing * (rx + h * 0.12), cy - ry * 1.1, h * 0.03, stroke=lighten(c["body"], 0.1), lw=0.4)
    _face(d, x + facing * rx * 0.42, cy, h * 0.36, expr, facing)


def _cat(d, x, y, h, expr, pose, facing):
    c = COLORS["cat"]
    hr = h * 0.28
    hcy = y - h * 0.56
    # tail
    d.arc(x - facing * h * 0.30, y - h * 0.22, h * 0.14, 90 if facing > 0 else 0,
          200 if facing > 0 else 90, color=c["body"], lw=h * 0.06)
    # ears
    for sx in (-1, 1):
        ex = x + sx * hr * 0.66
        d.polygon([(ex - hr * 0.30, hcy - hr * 0.55), (ex + sx * hr * 0.05, hcy - hr * 1.25),
                   (ex + hr * 0.30, hcy - hr * 0.58)], fill=c["body"])
        d.polygon([(ex - hr * 0.14, hcy - hr * 0.65), (ex + sx * hr * 0.02, hcy - hr * 1.05),
                   (ex + hr * 0.14, hcy - hr * 0.67)], fill=c["ear"])
    # body
    bry = h * 0.30
    bcy = y - bry + h * 0.02
    d.ellipse(x, bcy, h * 0.26, bry, fill=c["body"])
    d.ellipse(x, bcy + h * 0.06, h * 0.15, h * 0.18, fill=lighten(c["body"], 0.3))
    _feet(d, x, y, h, darken(c["body"], 0.22), spread=0.14)
    _arms(d, x, bcy - h * 0.03, h * 0.24, h, pose, darken(c["body"], 0.15), facing)
    # head
    d.circle(x, hcy, hr, fill=c["body"])
    _face(d, x + facing * h * 0.012, hcy + hr * 0.14, h * 0.40, expr, facing)
    d.dot(x + facing * h * 0.012, hcy + hr * 0.40, h * 0.02, (232, 150, 160))
    # whiskers
    for sx in (-1, 1):
        for wy in (-0.02, 0.06):
            d.line(x + sx * hr * 0.55, hcy + hr * (0.25 + wy),
                   x + sx * hr * 1.05, hcy + hr * (0.18 + wy * 2.4),
                   color=darken(c["body"], 0.3), lw=h * 0.012)


def _dog(d, x, y, h, expr, pose, facing):
    c = COLORS["dog"]
    hr = h * 0.29
    hcy = y - h * 0.57
    # tail
    d.arc(x - facing * h * 0.28, y - h * 0.24, h * 0.13, 100 if facing > 0 else -20,
          200 if facing > 0 else 80, color=c["body"], lw=h * 0.055)
    # body
    bry = h * 0.30
    bcy = y - bry + h * 0.02
    d.ellipse(x, bcy, h * 0.27, bry, fill=c["body"])
    d.ellipse(x, bcy + h * 0.06, h * 0.16, h * 0.19, fill=c["patch"])
    _feet(d, x, y, h, darken(c["body"], 0.25), spread=0.15)
    _arms(d, x, bcy - h * 0.03, h * 0.25, h, pose, darken(c["body"], 0.15), facing)
    # head first, then long floppy ears hanging in front of the head edges
    d.circle(x, hcy, hr, fill=c["body"])
    for sx in (-1, 1):
        d.ellipse(x + sx * hr * 0.88, hcy + hr * 0.12, hr * 0.28, hr * 0.72, fill=c["ear"])
    d.ellipse(x + facing * h * 0.01, hcy + hr * 0.42, hr * 0.46, hr * 0.34, fill=c["patch"])
    _face(d, x + facing * h * 0.012, hcy + hr * 0.10, h * 0.42, expr, facing)
    d.dot(x + facing * h * 0.012, hcy + hr * 0.40, h * 0.028, INK)


def _hamster(d, x, y, h, expr, pose, facing):
    c = COLORS["hamster"]
    rx, ry = h * 0.40, h * 0.40
    cy = y - ry - h * 0.04
    # ears
    for sx in (-1, 1):
        d.circle(x + sx * rx * 0.62, cy - ry * 0.78, h * 0.09, fill=c["body"])
        d.circle(x + sx * rx * 0.62, cy - ry * 0.78, h * 0.045, fill=darken(c["body"], 0.12))
    d.ellipse(x, cy, rx, ry, fill=c["body"])
    # belly + cheek puffs
    d.ellipse(x, cy + ry * 0.42, rx * 0.48, ry * 0.42, fill=c["belly"])
    for sx in (-1, 1):
        d.circle(x + sx * rx * 0.55, cy + ry * 0.12, h * 0.10, fill=c["belly"])
    _feet(d, x, y, h, darken(c["body"], 0.22), spread=0.14)
    _arms(d, x, cy + ry * 0.15, rx, h, pose, darken(c["body"], 0.18), facing)
    _face(d, x, cy - h * 0.05, h * 0.46, expr, facing)


def _bee(d, x, y, h, expr, pose, facing):
    """Friendly mentor bee: round head at the front, striped body behind.

    Anchor is still bottom-center; the bee floats slightly above it
    (callers draw it at a raised y for a hovering look)."""
    c = COLORS["bee"]
    cy = y - h * 0.46
    bcx = x - facing * h * 0.14          # body (abdomen) center
    hcx = x + facing * h * 0.16          # head center
    brx, bry = h * 0.26, h * 0.22
    # wings above the body
    wing_stroke = (170, 190, 214)
    if not d.line_art:
        with d.pdf.local_context(fill_opacity=0.8):
            d.ellipse(bcx - h * 0.07, cy - bry - h * 0.09, h * 0.14, h * 0.10,
                      fill=c["wing"], stroke=wing_stroke, lw=0.4)
            d.ellipse(bcx + h * 0.10, cy - bry - h * 0.07, h * 0.12, h * 0.085,
                      fill=c["wing"], stroke=wing_stroke, lw=0.4)
    else:
        d.ellipse(bcx - h * 0.07, cy - bry - h * 0.09, h * 0.14, h * 0.10)
        d.ellipse(bcx + h * 0.10, cy - bry - h * 0.07, h * 0.12, h * 0.085)
    # rounded stinger
    d.polygon([(bcx - facing * brx * 0.92, cy - h * 0.035),
               (bcx - facing * (brx + h * 0.10), cy),
               (bcx - facing * brx * 0.92, cy + h * 0.035)], fill=c["stripe"])
    # body + stripes (kept behind the head)
    d.ellipse(bcx, cy, brx, bry, fill=c["body"])
    if not d.line_art:
        for fx in (-0.35, 0.15):
            dx = fx * brx * facing
            sry = bry * math.sqrt(max(0.0, 1 - (fx) ** 2)) * 0.94
            d.ellipse(bcx + dx, cy, brx * 0.13, sry, fill=c["stripe"])
    # head
    hr = h * 0.21
    d.circle(hcx, cy - h * 0.02, hr, fill=c["body"])
    # antennae
    for k in (-0.5, 0.5):
        ax = hcx + k * hr
        d.line(ax, cy - h * 0.02 - hr * 0.85, ax + k * hr * 0.5, cy - h * 0.02 - hr * 1.6,
               color=c["stripe"], lw=h * 0.022)
        d.dot(ax + k * hr * 0.5, cy - h * 0.02 - hr * 1.6, h * 0.026, c["stripe"])
    _face(d, hcx + facing * hr * 0.05, cy - h * 0.01, h * 0.30, expr, facing)


def _squirrel(d, x, y, h, expr, pose, facing):
    """Woodland mentor: bushy-tailed and wise."""
    c = COLORS["squirrel"]
    hr = h * 0.27
    hcy = y - h * 0.55
    # big bushy tail curling up behind the back (opposite the facing side)
    tail_base_x = x - facing * h * 0.20
    tail_ang = 118 if facing > 0 else 62
    _leaf(d, tail_base_x, y - h * 0.14, h * 0.62, h * 0.27, tail_ang, c["tail"])
    _leaf(d, tail_base_x, y - h * 0.14, h * 0.44, h * 0.15, tail_ang, lighten(c["tail"], 0.22))
    # body
    bry = h * 0.30
    bcy = y - bry + h * 0.02
    d.ellipse(x, bcy, h * 0.24, bry, fill=c["body"])
    d.ellipse(x, bcy + h * 0.07, h * 0.15, h * 0.18, fill=c["belly"])
    _feet(d, x, y, h, darken(c["body"], 0.22), spread=0.13)
    _arms(d, x, bcy - h * 0.02, h * 0.23, h, pose, darken(c["body"], 0.15), facing)
    # tufted ears
    for sx in (-1, 1):
        ex = x + sx * hr * 0.62
        d.polygon([(ex - hr * 0.26, hcy - hr * 0.5), (ex, hcy - hr * 1.18),
                   (ex + hr * 0.26, hcy - hr * 0.5)], fill=c["body"])
        d.polygon([(ex - hr * 0.12, hcy - hr * 0.58), (ex, hcy - hr * 0.98),
                   (ex + hr * 0.12, hcy - hr * 0.58)], fill=c["ear"])
    # head + cheek puffs
    d.circle(x, hcy, hr, fill=c["body"])
    for sx in (-1, 1):
        d.circle(x + sx * hr * 0.5, hcy + hr * 0.34, hr * 0.30, fill=c["belly"])
    _face(d, x + facing * h * 0.012, hcy + hr * 0.14, h * 0.40, expr, facing)
    d.dot(x + facing * h * 0.012, hcy + hr * 0.44, h * 0.022, INK)


def _ladybug(d, x, y, h, expr, pose, facing):
    """Little flying mentor -- a friendly polka-dot ladybug (hovers like the bee)."""
    c = COLORS["ladybug"]
    cy = y - h * 0.44
    r = h * 0.36
    # gauzy wings peeking behind the shell
    if not d.line_art:
        with d.pdf.local_context(fill_opacity=0.7):
            for sx in (-1, 1):
                d.ellipse(x + sx * r * 0.55, cy - r * 0.12, r * 0.5, r * 0.72,
                          fill=c["wing"], stroke=(182, 198, 222), lw=0.4)
    else:
        for sx in (-1, 1):
            d.ellipse(x + sx * r * 0.55, cy - r * 0.12, r * 0.5, r * 0.72)
    # red domed shell
    d.ellipse(x, cy, r, r * 0.92, fill=c["body"])
    # wing-split line + spots (upper shell, clear of the face)
    d.line(x, cy - r * 0.9, x, cy - r * 0.02, color=darken(c["body"], 0.3), lw=h * 0.022)
    for sxp, syp, sr in ((-0.5, -0.42, 0.12), (0.5, -0.42, 0.12),
                         (-0.42, -0.04, 0.10), (0.42, -0.04, 0.10)):
        d.circle(x + sxp * r, cy + syp * r, sr * h, fill=c["spot"])
    # head bump + antennae
    hx = x + facing * r * 0.05
    d.circle(hx, cy - r * 0.9, h * 0.12, fill=c["head"])
    for k in (-0.5, 0.5):
        ax = hx + k * h * 0.07
        d.line(ax, cy - r * 0.9 - h * 0.07, ax + k * h * 0.05, cy - r * 0.9 - h * 0.17,
               color=c["head"], lw=h * 0.02)
        d.dot(ax + k * h * 0.05, cy - r * 0.9 - h * 0.17, h * 0.026, c["head"])
    # kawaii face on the lower shell
    _face(d, x + facing * h * 0.01, cy + r * 0.30, h * 0.34, expr, facing)


def _snail(d, x, y, h, expr, pose, facing):
    """Slow-and-steady mentor -- a spiral-shelled snail (perfect for patience)."""
    c = COLORS["snail"]
    # soft gliding foot
    d.rect(x - h * 0.38, y - h * 0.14, h * 0.76, h * 0.15, fill=c["body"], radius=h * 0.075)
    d.ellipse(x + facing * h * 0.30, y - h * 0.05, h * 0.12, h * 0.05, fill=c["body"])
    # spiral shell on the back (away from the facing side)
    ssx = x - facing * h * 0.12
    ssy = y - h * 0.35
    for rr, col in ((0.32, c["shell"]), (0.23, c["shell2"]), (0.14, c["shell"]),
                    (0.07, c["shell2"])):
        d.circle(ssx + facing * (0.32 - rr) * h * 0.5, ssy, rr * h, fill=col)
    # neck + head rising at the front
    hx = x + facing * h * 0.30
    d.rect(hx - h * 0.075, y - h * 0.44, h * 0.15, h * 0.36, fill=c["body"], radius=h * 0.06)
    d.circle(hx, y - h * 0.46, h * 0.15, fill=c["body"])
    # eye stalks
    for k in (0.35, -0.35):
        sx2 = hx + facing * k * h * 0.10
        d.line(sx2, y - h * 0.58, sx2 + facing * h * 0.03, y - h * 0.70,
               color=c["horn"], lw=h * 0.028)
        d.dot(sx2 + facing * h * 0.03, y - h * 0.71, h * 0.033, c["horn"])
    _face(d, hx + facing * h * 0.01, y - h * 0.45, h * 0.24, expr, facing)


# ---------------------------------------------------------------------------
# Extended kawaii cast: arctic, jungle, pond, cozy/woodland, mythical
# ---------------------------------------------------------------------------
# A faint outline keeps pale/white species readable on light backgrounds
# (snow, sky) in full colour; line-art mode overrides it with a black stroke.
_PALE = (214, 216, 224)


def _pale_stroke(d: "Draw", c: RGB | None = None) -> RGB | None:
    return None if d.line_art else (c or _PALE)


def _eye_whites(d: Draw, cx: float, cy: float, fw: float) -> None:
    """White backing discs under the eyes so pupils read on a dark patch."""
    eo = fw * 0.30
    for sx in (-1, 1):
        d.circle(cx + sx * eo, cy, fw * 0.17,
                 fill=WHITE if not d.line_art else None,
                 stroke=(30, 30, 30) if d.line_art else None, lw=0.5)


def _penguin(d, x, y, h, expr, pose, facing):
    c = COLORS["penguin"]
    rx, ry = h * 0.31, h * 0.43
    cy = y - ry - h * 0.03
    _feet(d, x, y, h, c["foot"], spread=0.13)
    d.ellipse(x, cy, rx, ry, fill=c["body"])
    # white belly / face panel
    d.ellipse(x, cy + ry * 0.10, rx * 0.70, ry * 0.82, fill=c["belly"])
    # flippers
    for sx in (-1, 1):
        d.ellipse(x + sx * rx * 0.99, cy + ry * 0.08, h * 0.075, h * 0.21, fill=c["body"])
    fcy = cy - ry * 0.24
    _face(d, x + facing * h * 0.01, fcy, h * 0.40, expr, facing)
    d.polygon([(x - h * 0.05, fcy + h * 0.085), (x + h * 0.05, fcy + h * 0.085),
               (x, fcy + h * 0.17)], fill=c["beak"])


def _seal(d, x, y, h, expr, pose, facing):
    c = COLORS["seal"]
    rx, ry = h * 0.35, h * 0.40
    cy = y - ry - h * 0.01
    # tail flippers spreading at the ground
    for sx in (-1, 1):
        d.polygon([(x + sx * rx * 0.15, y - h * 0.12),
                   (x + sx * rx * 0.95, y - h * 0.005),
                   (x + sx * rx * 0.30, y - h * 0.16)], fill=c["flipper"])
    d.ellipse(x, cy, rx, ry, fill=c["body"])
    d.ellipse(x, cy + ry * 0.24, rx * 0.62, ry * 0.58, fill=c["belly"])
    # front flippers
    for sx in (-1, 1):
        d.ellipse(x + sx * rx * 0.84, cy + ry * 0.30, h * 0.11, h * 0.06,
                  fill=c["flipper"])
    fcy = cy - ry * 0.06
    _face(d, x + facing * h * 0.01, fcy, h * 0.44, expr, facing)
    d.dot(x + facing * h * 0.01, fcy + h * 0.44 * 0.20, h * 0.03, c["nose"])
    for sx in (-1, 1):
        d.line(x + sx * h * 0.05, fcy + h * 0.10, x + sx * h * 0.17, fcy + h * 0.08,
               color=darken(c["body"], 0.28), lw=h * 0.012)


def _polar_bear(d, x, y, h, expr, pose, facing):
    c = COLORS["polar_bear"]
    hr = h * 0.31
    hcy = y - h * 0.58
    for sx in (-1, 1):
        d.circle(x + sx * hr * 0.74, hcy - hr * 0.74, hr * 0.28, fill=c["body"],
                 stroke=_pale_stroke(d), lw=0.4)
    bry = h * 0.33
    bcy = y - bry + h * 0.02
    d.ellipse(x, bcy, h * 0.30, bry, fill=c["body"], stroke=_pale_stroke(d), lw=0.4)
    _feet(d, x, y, h, (224, 228, 238), spread=0.16)
    _arms(d, x, bcy - h * 0.02, h * 0.28, h, pose, (220, 224, 234), facing)
    d.circle(x, hcy, hr, fill=c["body"], stroke=_pale_stroke(d), lw=0.4)
    d.ellipse(x, hcy + hr * 0.44, hr * 0.50, hr * 0.36, fill=c["muzzle"])
    _face(d, x + facing * h * 0.012, hcy + hr * 0.04, h * 0.42, expr, facing)
    d.dot(x + facing * h * 0.012, hcy + hr * 0.32, h * 0.03, c["nose"])


def _elephant(d, x, y, h, expr, pose, facing):
    c = COLORS["elephant"]
    hr = h * 0.30
    hcy = y - h * 0.55
    # big flappy ears behind the head
    for sx in (-1, 1):
        d.ellipse(x + sx * hr * 1.02, hcy + hr * 0.08, hr * 0.56, hr * 0.68, fill=c["ear"])
    bry = h * 0.32
    bcy = y - bry + h * 0.02
    d.ellipse(x, bcy, h * 0.30, bry, fill=c["body"])
    d.ellipse(x, bcy + h * 0.08, h * 0.18, h * 0.18, fill=c["belly"])
    _feet(d, x, y, h, darken(c["body"], 0.14), spread=0.17)
    _arms(d, x, bcy - h * 0.02, h * 0.28, h, pose, darken(c["body"], 0.12), facing)
    d.circle(x, hcy, hr, fill=c["body"])
    _face(d, x + facing * h * 0.015, hcy - hr * 0.08, h * 0.40, expr, facing)
    # trunk hanging down between the eyes, curling toward the facing side
    tx = x + facing * h * 0.015
    ty = hcy + hr * 0.22
    d.rect(tx - h * 0.05, ty, h * 0.10, h * 0.20, fill=c["body"], radius=h * 0.045)
    d.circle(tx + facing * h * 0.02, ty + h * 0.21, h * 0.052, fill=c["body"])
    d.circle(tx + facing * h * 0.055, ty + h * 0.235, h * 0.044, fill=c["body"])
    # short curved tusks tucked at the trunk base, tips turning outward
    for sx in (-1, 1):
        d.polygon([(tx + sx * h * 0.055, ty + h * 0.05),
                   (tx + sx * h * 0.10, ty + h * 0.115),
                   (tx + sx * h * 0.115, ty + h * 0.085),
                   (tx + sx * h * 0.075, ty + h * 0.035)], fill=c["tusk"])


def _lion(d, x, y, h, expr, pose, facing):
    c = COLORS["lion"]
    hr = h * 0.24
    hcy = y - h * 0.54
    # tail with a tuft
    d.arc(x - facing * h * 0.28, y - h * 0.24, h * 0.14, 90 if facing > 0 else 0,
          200 if facing > 0 else 90, color=c["body"], lw=h * 0.05)
    d.dot(x - facing * h * 0.40, y - h * 0.20, h * 0.05, c["mane"])
    bry = h * 0.30
    bcy = y - bry + h * 0.02
    d.ellipse(x, bcy, h * 0.26, bry, fill=c["body"])
    d.ellipse(x, bcy + h * 0.06, h * 0.15, h * 0.18, fill=c["muzzle"])
    _feet(d, x, y, h, darken(c["body"], 0.2), spread=0.15)
    _arms(d, x, bcy - h * 0.02, h * 0.24, h, pose, darken(c["body"], 0.14), facing)
    # ears
    for sx in (-1, 1):
        d.circle(x + sx * hr * 0.7, hcy - hr * 0.5, hr * 0.24, fill=c["ear"])
    # shaggy mane ring
    for i in range(12):
        a = math.radians(i * 360 / 12)
        d.circle(x + hr * 1.06 * math.cos(a), hcy + hr * 1.06 * math.sin(a),
                 hr * 0.34, fill=c["mane"])
    d.circle(x, hcy, hr, fill=c["body"])
    d.ellipse(x, hcy + hr * 0.42, hr * 0.60, hr * 0.44, fill=c["muzzle"])
    _face(d, x + facing * h * 0.012, hcy + hr * 0.06, h * 0.40, expr, facing)
    d.dot(x + facing * h * 0.012, hcy + hr * 0.36, h * 0.026, (120, 80, 70))


def _monkey(d, x, y, h, expr, pose, facing):
    c = COLORS["monkey"]
    hr = h * 0.28
    hcy = y - h * 0.55
    # curling tail
    d.arc(x - facing * h * 0.24, y - h * 0.24, h * 0.16, 60 if facing > 0 else 60,
          260 if facing > 0 else 260, color=c["body"], lw=h * 0.045)
    # big round side ears
    for sx in (-1, 1):
        d.circle(x + sx * hr * 1.02, hcy + hr * 0.05, hr * 0.34, fill=c["body"])
        d.circle(x + sx * hr * 1.02, hcy + hr * 0.05, hr * 0.19, fill=c["ear"])
    bry = h * 0.30
    bcy = y - bry + h * 0.02
    d.ellipse(x, bcy, h * 0.25, bry, fill=c["body"])
    d.ellipse(x, bcy + h * 0.07, h * 0.15, h * 0.18, fill=c["belly"])
    _feet(d, x, y, h, darken(c["body"], 0.2), spread=0.14)
    _arms(d, x, bcy - h * 0.02, h * 0.24, h, pose, darken(c["body"], 0.14), facing)
    d.circle(x, hcy, hr, fill=c["body"])
    # tan face patch (heart shape from two lobes + a chin)
    d.ellipse(x, hcy + hr * 0.16, hr * 0.72, hr * 0.66, fill=c["face"])
    d.circle(x - hr * 0.30, hcy - hr * 0.06, hr * 0.30, fill=c["face"])
    d.circle(x + hr * 0.30, hcy - hr * 0.06, hr * 0.30, fill=c["face"])
    _face(d, x + facing * h * 0.012, hcy + hr * 0.14, h * 0.40, expr, facing)
    d.dot(x + facing * h * 0.012, hcy + hr * 0.40, h * 0.02, (120, 82, 60))


def _frog(d, x, y, h, expr, pose, facing):
    c = COLORS["frog"]
    rx, ry = h * 0.42, h * 0.33
    cy = y - ry - h * 0.06
    # splayed back feet
    for sx in (-1, 1):
        d.ellipse(x + sx * rx * 0.72, y - h * 0.03, h * 0.12, h * 0.06, fill=c["foot"])
    _arms(d, x, cy + ry * 0.28, rx * 0.96, h, pose, c["foot"], facing)
    d.ellipse(x, cy, rx, ry, fill=c["body"])
    d.ellipse(x, cy + ry * 0.30, rx * 0.66, ry * 0.58, fill=c["belly"])
    # eye bumps riding on top of the head
    for sx in (-1, 1):
        ex, ey = x + sx * rx * 0.44, cy - ry * 0.80
        d.circle(ex, ey, h * 0.115, fill=c["body"])
        d.circle(ex, ey, h * 0.066, fill=WHITE if not d.line_art else None,
                 stroke=(30, 30, 30) if d.line_art else None, lw=0.5)
        d.circle(ex, ey + h * 0.006, h * 0.033, fill=INK, force_fill=True)
        if not d.line_art:
            d.dot(ex - h * 0.018, ey - h * 0.020, h * 0.016, WHITE)
    # wide happy mouth across the body
    my = cy - h * 0.02
    if expr in ("sad", "worried"):
        d.arc(x, my + h * 0.10, rx * 0.40, 200, 340, color=INK, lw=h * 0.03, ry=ry * 0.32)
    else:
        d.arc(x, my - h * 0.02, rx * 0.42, 18, 162, color=INK, lw=h * 0.032, ry=ry * 0.42)
    d.dot(x - rx * 0.16, cy - ry * 0.36, h * 0.016, darken(c["body"], 0.25))
    d.dot(x + rx * 0.16, cy - ry * 0.36, h * 0.016, darken(c["body"], 0.25))
    if not d.line_art:
        d.blush(x - rx * 0.5, cy + ry * 0.02, h * 0.06)
        d.blush(x + rx * 0.5, cy + ry * 0.02, h * 0.06)


def _duck(d, x, y, h, expr, pose, facing):
    c = COLORS["duck"]
    rx, ry = h * 0.35, h * 0.41
    cy = y - ry - h * 0.05
    # rounded tail lifting at the back
    d.ellipse(x - facing * rx * 0.92, cy + ry * 0.34, h * 0.12, h * 0.085,
              fill=c["wing"], stroke=_pale_stroke(d), lw=0.4)
    _feet(d, x, y, h, c["foot"], spread=0.13)
    d.ellipse(x, cy, rx, ry, fill=c["body"], stroke=_pale_stroke(d), lw=0.4)
    # tucked wing
    d.ellipse(x - facing * rx * 0.52, cy + ry * 0.16, h * 0.13, h * 0.22,
              fill=c["wing"], stroke=_pale_stroke(d), lw=0.4)
    # little head-feather sprig
    for ang in (-108, -90, -72):
        _leaf(d, x, cy - ry * 0.94, h * 0.10, h * 0.028, ang, c["wing"])
    _face(d, x + facing * h * 0.02, cy - ry * 0.24, h * 0.40, expr, facing)
    # broad rounded bill centred just below the eyes
    d.ellipse(x + facing * h * 0.02, cy - ry * 0.02, h * 0.165, h * 0.075, fill=c["beak"])
    d.line(x - h * 0.11 + facing * h * 0.02, cy - ry * 0.02,
           x + h * 0.11 + facing * h * 0.02, cy - ry * 0.02,
           color=darken(c["beak"], 0.28), lw=h * 0.014)
    d.dot(x + facing * h * 0.02 - h * 0.05, cy - ry * 0.055, h * 0.012, darken(c["beak"], 0.3))
    d.dot(x + facing * h * 0.02 + h * 0.05, cy - ry * 0.055, h * 0.012, darken(c["beak"], 0.3))


def _panda(d, x, y, h, expr, pose, facing):
    c = COLORS["panda"]
    hr = h * 0.31
    hcy = y - h * 0.57
    for sx in (-1, 1):
        d.circle(x + sx * hr * 0.72, hcy - hr * 0.72, hr * 0.28, fill=c["patch"])
    bry = h * 0.32
    bcy = y - bry + h * 0.02
    d.ellipse(x, bcy, h * 0.30, bry, fill=c["body"], stroke=_pale_stroke(d), lw=0.4)
    _feet(d, x, y, h, c["patch"], spread=0.16)
    _arms(d, x, bcy - h * 0.02, h * 0.28, h, pose, c["patch"], facing)
    d.circle(x, hcy, hr, fill=c["body"], stroke=_pale_stroke(d), lw=0.4)
    fcy = hcy + hr * 0.06
    fw = h * 0.42
    eo = fw * 0.30
    # slanted black eye patches, white eye backing, then the shared face
    for sx in (-1, 1):
        d.ellipse(x + sx * eo, fcy + h * 0.004, hr * 0.30, hr * 0.36, fill=c["patch"])
    _eye_whites(d, x, fcy, fw)
    _face(d, x, fcy, fw, expr, facing)
    d.dot(x, fcy + fw * 0.20, h * 0.026, c["patch"])


def _koala(d, x, y, h, expr, pose, facing):
    c = COLORS["koala"]
    hr = h * 0.30
    hcy = y - h * 0.55
    # big fluffy side ears
    for sx in (-1, 1):
        d.circle(x + sx * hr * 0.94, hcy - hr * 0.10, hr * 0.42, fill=c["body"],
                 stroke=_pale_stroke(d), lw=0.4)
        d.circle(x + sx * hr * 0.94, hcy - hr * 0.10, hr * 0.24, fill=c["ear"])
    bry = h * 0.32
    bcy = y - bry + h * 0.02
    d.ellipse(x, bcy, h * 0.28, bry, fill=c["body"], stroke=_pale_stroke(d), lw=0.4)
    d.ellipse(x, bcy + h * 0.08, h * 0.16, h * 0.17, fill=c["belly"])
    _feet(d, x, y, h, darken(c["body"], 0.18), spread=0.15)
    _arms(d, x, bcy - h * 0.02, h * 0.26, h, pose, darken(c["body"], 0.14), facing)
    d.circle(x, hcy, hr, fill=c["body"], stroke=_pale_stroke(d), lw=0.4)
    _face(d, x + facing * h * 0.012, hcy - hr * 0.02, h * 0.40, expr, facing)
    # big spoon-shaped nose
    d.ellipse(x, hcy + hr * 0.28, hr * 0.26, hr * 0.34, fill=c["nose"])


def _deer(d, x, y, h, expr, pose, facing):
    c = COLORS["deer"]
    hr = h * 0.26
    hcy = y - h * 0.56
    # branching antlers
    for sx in (-1, 1):
        bx, by = x + sx * hr * 0.5, hcy - hr * 0.72
        tip = (bx + sx * h * 0.06, by - h * 0.20)
        d.line(bx, by, *tip, color=c["antler"], lw=h * 0.032)
        d.line(bx + sx * h * 0.02, by - h * 0.07, bx + sx * h * 0.13, by - h * 0.10,
               color=c["antler"], lw=h * 0.026)
        d.line(bx + sx * h * 0.045, by - h * 0.14, bx + sx * h * 0.14, by - h * 0.16,
               color=c["antler"], lw=h * 0.024)
        d.dot(*tip, h * 0.02, c["antler"])
    # ears
    for sx in (-1, 1):
        d.ellipse(x + sx * hr * 0.86, hcy - hr * 0.18, h * 0.055, h * 0.11, fill=c["ear"])
    bry = h * 0.30
    bcy = y - bry + h * 0.02
    d.ellipse(x, bcy, h * 0.25, bry, fill=c["body"])
    d.ellipse(x, bcy + h * 0.07, h * 0.15, h * 0.18, fill=c["belly"])
    if not d.line_art:
        for sx, sy in ((-0.4, -0.1), (0.4, -0.1), (0.0, 0.18)):
            d.dot(x + sx * h * 0.2, bcy + sy * h, h * 0.02, c["spot"])
    _feet(d, x, y, h, darken(c["body"], 0.2), spread=0.14)
    _arms(d, x, bcy - h * 0.02, h * 0.23, h, pose, darken(c["body"], 0.14), facing)
    d.circle(x, hcy, hr, fill=c["body"])
    d.ellipse(x, hcy + hr * 0.44, hr * 0.5, hr * 0.36, fill=c["belly"])
    _face(d, x + facing * h * 0.012, hcy + hr * 0.06, h * 0.40, expr, facing)
    d.dot(x + facing * h * 0.012, hcy + hr * 0.36, h * 0.026, c["nose"])


def _raccoon(d, x, y, h, expr, pose, facing):
    c = COLORS["raccoon"]
    hr = h * 0.28
    hcy = y - h * 0.55
    # ringed tail curling behind the body
    tail_base_x = x - facing * h * 0.20
    tail_ang = 120 if facing > 0 else 60
    _leaf(d, tail_base_x, y - h * 0.12, h * 0.54, h * 0.20, tail_ang, c["tail"])
    for frac, col in ((0.72, c["belly"]), (0.48, c["tail"]), (0.26, c["belly"])):
        a = math.radians(tail_ang)
        d.circle(tail_base_x + frac * h * 0.54 * math.cos(a),
                 (y - h * 0.12) + frac * h * 0.54 * math.sin(a), h * 0.06, fill=col)
    # ears
    for sx in (-1, 1):
        ex = x + sx * hr * 0.66
        d.polygon([(ex - hr * 0.28, hcy - hr * 0.5), (ex, hcy - hr * 1.12),
                   (ex + hr * 0.28, hcy - hr * 0.5)], fill=c["body"])
        d.polygon([(ex - hr * 0.13, hcy - hr * 0.58), (ex, hcy - hr * 0.96),
                   (ex + hr * 0.13, hcy - hr * 0.58)], fill=c["ear"])
    bry = h * 0.30
    bcy = y - bry + h * 0.02
    d.ellipse(x, bcy, h * 0.26, bry, fill=c["body"])
    d.ellipse(x, bcy + h * 0.07, h * 0.16, h * 0.18, fill=c["belly"])
    _feet(d, x, y, h, darken(c["body"], 0.22), spread=0.14)
    _arms(d, x, bcy - h * 0.02, h * 0.24, h, pose, darken(c["body"], 0.16), facing)
    d.circle(x, hcy, hr, fill=c["body"])
    fcy = hcy + hr * 0.08
    fw = h * 0.40
    eo = fw * 0.30
    # black bandit mask across both eyes
    for sx in (-1, 1):
        d.ellipse(x + sx * eo, fcy, hr * 0.30, hr * 0.34, fill=c["mask"])
    d.rect(x - eo, fcy - hr * 0.1, eo * 2, hr * 0.22, fill=c["mask"])
    d.ellipse(x, hcy + hr * 0.44, hr * 0.5, hr * 0.34, fill=c["belly"])
    _eye_whites(d, x, fcy, fw)
    _face(d, x, fcy, fw, expr, facing)
    d.dot(x, fcy + fw * 0.22, h * 0.024, c["mask"])


def _unicorn(d, x, y, h, expr, pose, facing):
    c = COLORS["unicorn"]
    hr = h * 0.27
    hcy = y - h * 0.55
    # golden horn
    d.polygon([(x - h * 0.032, hcy - hr * 0.82), (x, hcy - hr * 1.55),
               (x + h * 0.032, hcy - hr * 0.82)], fill=c["horn"])
    # ears
    for sx in (-1, 1):
        ex = x + sx * hr * 0.62
        d.polygon([(ex - hr * 0.18, hcy - hr * 0.55), (ex, hcy - hr * 1.02),
                   (ex + hr * 0.18, hcy - hr * 0.55)], fill=c["body"])
    # flowing mane down the back side of the head
    for i, rr in enumerate((0.26, 0.22, 0.18, 0.15)):
        d.circle(x - facing * hr * (0.62 + i * 0.18), hcy - hr * (0.35 - i * 0.28),
                 hr * rr, fill=c["mane"])
    bry = h * 0.30
    bcy = y - bry + h * 0.02
    d.ellipse(x, bcy, h * 0.25, bry, fill=c["body"], stroke=_pale_stroke(d), lw=0.4)
    # tail
    for i, rr in enumerate((0.16, 0.14, 0.12)):
        d.circle(x - facing * (h * 0.24 + i * h * 0.06), y - h * 0.22 + i * h * 0.06,
                 h * rr, fill=c["mane"])
    _feet(d, x, y, h, c["hoof"], spread=0.14)
    _arms(d, x, bcy - h * 0.02, h * 0.23, h, pose, darken(c["body"], 0.08), facing)
    d.circle(x, hcy, hr, fill=c["body"], stroke=_pale_stroke(d), lw=0.4)
    # forelock tuft between the ears
    d.circle(x + facing * hr * 0.28, hcy - hr * 0.55, hr * 0.22, fill=c["mane"])
    d.ellipse(x, hcy + hr * 0.44, hr * 0.5, hr * 0.34, fill=c["muzzle"])
    _face(d, x + facing * h * 0.012, hcy + hr * 0.06, h * 0.40, expr, facing)
    d.dot(x + facing * h * 0.012, hcy + hr * 0.38, h * 0.022, (196, 150, 176))


def _dragon(d, x, y, h, expr, pose, facing):
    c = COLORS["dragon"]
    hr = h * 0.27
    hcy = y - h * 0.55
    bry = h * 0.31
    bcy = y - bry + h * 0.02
    # wings behind the body
    for sx in (-1, 1):
        d.polygon([(x + sx * h * 0.14, bcy - h * 0.06),
                   (x + sx * h * 0.40, bcy - h * 0.22),
                   (x + sx * h * 0.36, bcy + h * 0.04),
                   (x + sx * h * 0.42, bcy + h * 0.02),
                   (x + sx * h * 0.30, bcy + h * 0.14)], fill=c["wing"])
    # curling tail with an arrow tip
    d.arc(x - facing * h * 0.26, y - h * 0.22, h * 0.14, 90 if facing > 0 else 0,
          210 if facing > 0 else 90, color=c["body"], lw=h * 0.05)
    d.polygon([(x - facing * h * 0.40, y - h * 0.16),
               (x - facing * h * 0.52, y - h * 0.10),
               (x - facing * h * 0.40, y - h * 0.24)], fill=c["spike"])
    # back spikes
    for sx in (-1, 1):
        d.polygon([(x + sx * h * 0.05, bcy - bry * 0.7),
                   (x + sx * h * 0.11, bcy - bry * 1.02),
                   (x + sx * h * 0.15, bcy - bry * 0.6)], fill=c["spike"])
    d.ellipse(x, bcy, h * 0.26, bry, fill=c["body"])
    d.ellipse(x, bcy + h * 0.07, h * 0.16, h * 0.18, fill=c["belly"])
    _feet(d, x, y, h, darken(c["body"], 0.2), spread=0.15)
    _arms(d, x, bcy - h * 0.02, h * 0.24, h, pose, darken(c["body"], 0.14), facing)
    # little horns
    for sx in (-1, 1):
        ex = x + sx * hr * 0.5
        d.polygon([(ex - h * 0.02, hcy - hr * 0.78), (ex, hcy - hr * 1.14),
                   (ex + h * 0.02, hcy - hr * 0.78)], fill=c["horn"])
    d.circle(x, hcy, hr, fill=c["body"])
    d.ellipse(x, hcy + hr * 0.42, hr * 0.5, hr * 0.34, fill=c["belly"])
    _face(d, x + facing * h * 0.012, hcy + hr * 0.04, h * 0.40, expr, facing)
    for sx in (-1, 1):
        d.dot(x + sx * h * 0.03, hcy + hr * 0.40, h * 0.016, darken(c["body"], 0.3))


def _dino(d, x, y, h, expr, pose, facing):
    c = COLORS["dino"]
    rx, ry = h * 0.31, h * 0.40
    cy = y - ry - h * 0.02
    # thick curving tail behind
    d.arc(x - facing * h * 0.24, y - h * 0.20, h * 0.16, 100 if facing > 0 else -30,
          210 if facing > 0 else 80, color=c["body"], lw=h * 0.08)
    # row of back plates up the spine
    for i, (px, py, s) in enumerate(((-0.28, 0.30, 0.9), (-0.12, 0.62, 1.1),
                                     (0.06, 0.72, 1.15), (0.24, 0.55, 1.0))):
        bx = x - facing * px * rx * 1.2
        byy = cy - py * ry
        d.polygon([(bx - h * 0.05 * s, byy + h * 0.06), (bx, byy - h * 0.09 * s),
                   (bx + h * 0.05 * s, byy + h * 0.06)], fill=c["plate"])
    _feet(d, x, y, h, darken(c["body"], 0.2), spread=0.16)
    _arms(d, x, cy + ry * 0.34, rx * 0.9, h, pose, darken(c["body"], 0.14), facing)
    d.ellipse(x, cy, rx, ry, fill=c["body"])
    d.ellipse(x, cy + ry * 0.28, rx * 0.66, ry * 0.6, fill=c["belly"])
    _face(d, x + facing * h * 0.015, cy - ry * 0.14, h * 0.44, expr, facing)
    # nostrils
    for sx in (-1, 1):
        d.dot(x + sx * h * 0.03, cy - ry * 0.02, h * 0.014, darken(c["body"], 0.3))


def _blob(d, x, y, h, expr, pose, facing):
    """Fallback character so an unknown key never crashes a build."""
    body = (180, 180, 210)
    cx, cy, rx = _round_food(d, x, y, h, expr, pose, facing, body)
    _face(d, cx, cy, h * 0.5, expr, facing)


# ---------------------------------------------------------------------------
# Registry + public API
# ---------------------------------------------------------------------------

_REGISTRY = {
    "apple": _apple,
    "banana": _banana,
    "strawberry": _strawberry,
    "orange": _orange,
    "pear": _pear,
    "watermelon": _watermelon,
    "carrot": _carrot,
    "broccoli": _broccoli,
    "tomato": _tomato,
    "corn": _corn,
    "pea_pod": _pea_pod,
    "fox": _fox,
    "bunny": _bunny,
    "bear": _bear,
    "owl": _owl,
    "hedgehog": _hedgehog,
    "cow": _cow,
    "pig": _pig,
    "chick": _chick,
    "sheep": _sheep,
    "octopus": _octopus,
    "turtle": _turtle,
    "crab": _crab,
    "fish": _fish,
    "cat": _cat,
    "dog": _dog,
    "hamster": _hamster,
    "bee": _bee,
    "squirrel": _squirrel,
    "ladybug": _ladybug,
    "snail": _snail,
    "penguin": _penguin,
    "seal": _seal,
    "polar_bear": _polar_bear,
    "elephant": _elephant,
    "lion": _lion,
    "monkey": _monkey,
    "frog": _frog,
    "duck": _duck,
    "panda": _panda,
    "koala": _koala,
    "deer": _deer,
    "raccoon": _raccoon,
    "unicorn": _unicorn,
    "dragon": _dragon,
    "dino": _dino,
}


def available_characters() -> list[str]:
    """All drawable character keys."""
    return sorted(_REGISTRY.keys())


def draw_character(
    pdf: FPDF,
    key: str,
    x: float,
    y: float,
    scale: float,
    expression: str = "happy",
    pose: str = "stand",
    line_art: bool = False,
    facing: int = 1,
    age_band: str = "4-6",
) -> None:
    """Draw the character *key* with its feet at (x, y), *scale* mm tall.

    ``expression``: happy | sad | surprised | sleepy | excited | worried |
                    curious | giggling
    ``pose``:       stand | arms_up | wave | point | hug | jump | walk | slump
    ``facing``:     1 faces right, -1 faces left
    ``line_art``:   black outlines / white fills for coloring pages
    ``age_band``:   2-4 | 4-6 | 6-8 -- tunes eye size/height, outline weight
                    and limb thickness (Kindchenschema by age)
    """
    d = Draw(pdf, line_art=line_art)
    d.age_band = age_band
    fn = _REGISTRY.get(key, _blob)
    # "jump" lifts the whole body off the ground; the shadow stays put and
    # shrinks a touch so the character reads as airborne.
    lift = scale * 0.12 if pose == "jump" else 0.0
    if not line_art:
        shadow_rx = scale * 0.34 * (0.78 if pose == "jump" else 1.0)
        d.soft_shadow(x, y + scale * 0.012, shadow_rx, scale * 0.05)
    fn(d, x, y - lift, scale, expression, pose, int(facing) or 1)
