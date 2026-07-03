"""Motif families: ornament vocabulary for the planner design system.

A motif family provides seven pure drawing slots (no layout imports, only
``(pdf, theme, geometry-args)``):

=================  =========================================================
``corner``         ornament hugging a corner (cover frame corners)
``divider``        glyph + hairlines centered under titles
``bullet``         priority marker (returns the content start x)
``band``           thin horizontal decorative strip
``cover_hero``     cover background composition (classic arch cover)
``pattern_fill``   tiling repeat (pattern covers; ``scale`` resizes the
                   module for oversized crops -- default 1.0 is verbatim)
``ground_field``   motif elements growing from the rect's bottom edge
                   (meadow-horizon arch cover)
=================  =========================================================

Determinism: every scatter uses ``random.Random(seed)`` where the seed is
derived from year + motif + page kind, so identical specs render
identically.  The container style each motif owns lives in
``styles.CONTAINERS`` and is consumed by the widgets.
"""

from __future__ import annotations

import math
import random

from fpdf import FPDF

from src.planner.styles import Theme, WHITE, blend

PAGE_W = 482.0
PAGE_H = 361.2


def _rng(seed: str) -> random.Random:
    return random.Random(seed)


def _quadrant_dir(quadrant: str) -> tuple[int, int]:
    """Unit direction pointing from the corner into the page."""
    return ({"TL": (1, 1), "TR": (-1, 1),
             "BL": (1, -1), "BR": (-1, -1)}[quadrant])


def _number_beside(pdf: FPDF, theme: Theme, x: float, y: float, size: float,
                   number: int) -> float:
    """Draw the priority number beside a marker; return content start x."""
    pdf.set_text_color(*theme.rgb("text"))
    pdf.set_font(theme.body, "B", 6.5)
    nx = x + size + 1.2
    pdf.set_xy(nx, y + (size - 4.2) / 2)
    pdf.cell(4.5, 4.2, str(number), align="L")
    return nx + 5.3


def _number_overprint(pdf: FPDF, theme: Theme, x: float, y: float,
                      size: float, number: int) -> float:
    pdf.set_text_color(*WHITE)
    pdf.set_font(theme.body, "B", 6.5)
    pdf.set_xy(x, y)
    pdf.cell(size, size, str(number), align="C")
    return x + size + 2.6


def _wave_points(x: float, w: float, base_y: float, amp: float,
                 wavelength: float, phase: float = 0.0,
                 step: float = 2.0) -> list[tuple[float, float]]:
    pts = []
    t = 0.0
    while t <= w + 0.01:
        pts.append((x + t,
                    base_y + amp * math.sin(2 * math.pi * (t + phase) / wavelength)))
        t += step
    return pts


class MotifFamily:
    """Base motif: every slot is a safe no-op unless overridden."""

    name = "minimal"

    # -- Slot A ------------------------------------------------------------
    def corner(self, pdf: FPDF, theme: Theme, x: float, y: float,
               size: float, quadrant: str) -> None:
        pass

    # -- Slot B ------------------------------------------------------------
    def divider(self, pdf: FPDF, theme: Theme, cx: float, cy: float,
                w: float) -> None:
        pass

    # -- Slot C ------------------------------------------------------------
    def bullet(self, pdf: FPDF, theme: Theme, x: float, y: float,
               size: float, number: int | None = None) -> float:
        return x + size + 2.6

    # -- Slot D ------------------------------------------------------------
    def band(self, pdf: FPDF, theme: Theme, x: float, y: float, w: float,
             h: float = 6.0) -> None:
        pass

    # -- Slot E ------------------------------------------------------------
    def cover_hero(self, pdf: FPDF, theme: Theme, seed: str) -> None:
        pass

    # -- Slot F ------------------------------------------------------------
    def pattern_fill(self, pdf: FPDF, theme: Theme, x: float, y: float,
                     w: float, h: float, seed: str,
                     scale: float = 1.0) -> None:
        pass

    # -- Slot G ------------------------------------------------------------
    def ground_field(self, pdf: FPDF, theme: Theme, x: float, y: float,
                     w: float, h: float, seed: str) -> None:
        """Motif elements growing UP from the rect's bottom edge (the
        meadow-horizon cover).  Default: the family's own pattern."""
        self.pattern_fill(pdf, theme, x, y, w, h, seed)


# ===========================================================================
# Botanical (classic-exact where it matters)
# ===========================================================================

class BotanicalMotif(MotifFamily):
    name = "botanical"

    def bullet(self, pdf, theme, x, y, size, number=None):
        # The classic filled circle, verbatim.
        pdf.set_fill_color(*theme.bullet_c())
        pdf.ellipse(x, y, size, size, style="F")
        if number is not None:
            return _number_overprint(pdf, theme, x, y, size, number)
        return x + size + 2.6

    def divider(self, pdf, theme, cx, cy, w):
        acc = theme.rgb("accent")
        pdf.set_draw_color(*acc)
        pdf.set_line_width(0.5)
        pdf.line(cx - w / 2, cy, cx - 5, cy)
        pdf.line(cx + 5, cy, cx + w / 2, cy)
        pdf.set_fill_color(*acc)
        pdf.polygon([(cx, cy - 2.2), (cx + 2.2, cy), (cx, cy + 2.2),
                     (cx - 2.2, cy)], style="F")

    def corner(self, pdf, theme, x, y, size, quadrant):
        s = size / 22.0
        leaf_color = blend(theme.rgb("primary"), theme.rgb("text"), 0.25)
        dx, dy = _quadrant_dir(quadrant)
        angle = {(1, 1): 135, (-1, 1): -135, (1, -1): 45, (-1, -1): -45}[(dx, dy)]
        pdf.set_draw_color(*leaf_color)
        pdf.set_fill_color(*leaf_color)
        with pdf.rotation(angle=angle, x=x, y=y):
            # Branch drawn pointing straight up from the corner point,
            # rotation carries it diagonally into the page.
            pdf.set_line_width(0.7)
            pdf.line(x, y, x, y - size)
            for i in range(4):
                ly = y - (7 + i * 5) * s
                lw = (6 - i * 0.85) * s
                with pdf.local_context(fill_opacity=0.75):
                    pdf.ellipse(x - lw, ly - 1.8 * s, lw, 3.6 * s, style="F")
                    pdf.ellipse(x, ly - 3.6 * s, lw, 3.6 * s, style="F")

    def band(self, pdf, theme, x, y, w, h=6.0):
        cy = y + h / 2
        sec = theme.rgb("secondary")
        pdf.set_draw_color(*sec)
        pdf.set_line_width(0.4)
        pts = _wave_points(x, w, cy, amp=1.6, wavelength=14)
        pdf.polyline(pts, style="D")
        pdf.set_fill_color(*sec)
        # A leaf at each crest, alternating above/below
        t = 3.5   # first crest of sin at wavelength/4
        i = 0
        while t < w - 2:
            ly = cy + (-2.4 if i % 2 == 0 else 1.0)
            with pdf.local_context(fill_opacity=0.6):
                pdf.ellipse(x + t - 1.5, ly, 3.0, 1.5, style="F")
            t += 7.0
            i += 1

    def cover_hero(self, pdf, theme, seed):
        # Verbatim pre-design cover block: arches + sun arcs + branches.
        pr = theme.rgb("primary")
        sec = theme.rgb("secondary")
        acc = theme.rgb("accent")
        cx = PAGE_W / 2

        arch_specs = [
            (sec, 0.30, 235), (acc, 0.30, 195), (pr, 0.32, 155), (sec, 0.5, 118),
        ]
        base_y = PAGE_H + 55
        for color, op, radius in arch_specs:
            with pdf.local_context(fill_opacity=op):
                pdf.set_fill_color(*color)
                pdf.ellipse(cx - radius, base_y - radius, radius * 2,
                            radius * 2, style="F")

        for corner_x in (0.0, PAGE_W):
            for i, radius in enumerate((95, 70, 46)):
                with pdf.local_context(fill_opacity=0.10 + i * 0.05):
                    pdf.set_fill_color(*(sec if i % 2 == 0 else acc))
                    pdf.ellipse(corner_x - radius, -radius, radius * 2,
                                radius * 2, style="F")

        leaf_color = blend(pr, theme.rgb("text"), 0.25)
        pdf.set_draw_color(*leaf_color)
        pdf.set_fill_color(*leaf_color)

        def _branch(bx: float, by: float, angle: float) -> None:
            with pdf.rotation(angle=angle, x=bx, y=by):
                pdf.set_line_width(0.7)
                pdf.line(bx, by, bx, by - 58)
                for i in range(5):
                    ly = by - 12 - i * 10
                    lw = 11 - i * 1.6
                    with pdf.local_context(fill_opacity=0.75):
                        pdf.ellipse(bx - lw, ly - 3.2, lw, 6.4, style="F")
                        pdf.ellipse(bx, ly - 6.4, lw, 6.4, style="F")

        _branch(40, PAGE_H - 18, 14)
        _branch(PAGE_W - 40, PAGE_H - 18, -14)

    # -- Boho vector vocabulary (arch / wildflower / sun) ------------------
    # These are the earthy-botanical signatures: tall narrow nested arches
    # (3 monochrome bands with gaps + an optional sun disc) and fine
    # wildflower sprigs.  Line weights stay 0.8-1.4pt, flat matte fills,
    # slightly organic.  They live on the pattern slot (covers / band
    # panels) so the classic golden slots stay byte-for-byte unchanged.

    @staticmethod
    def _arch_points(cx: float, base_y: float, half_w: float,
                     height: float, steps: int = 11) -> list[tuple[float, float]]:
        """Points along a TALL NARROW half-arch (boho-rainbow geometry):
        up the left leg, over the top, down the right leg."""
        pts: list[tuple[float, float]] = []
        for i in range(steps + 1):
            ang = math.pi * (i / steps)          # pi .. 0 -> left..right
            pts.append((cx - half_w * math.cos(ang),
                        base_y - height * math.sin(ang)))
        return pts

    def _nested_arch(self, pdf, cx, base_y, half_w, height, scale,
                     colors, sun=False):
        """3 concentric arch bands, a gap between each, optional sun disc."""
        gap = 4.6 * scale
        lw = max(0.8, 1.25 * scale)
        pdf.set_line_width(lw)
        for i, col in enumerate(colors[:3]):
            hw = half_w - i * gap
            ht = height - i * gap
            if hw <= 1.0 or ht <= 1.0:
                break
            pdf.set_draw_color(*col)
            pdf.polyline(self._arch_points(cx, base_y, hw, ht), style="D")
        if sun:
            r = max(1.6, 3.2 * scale)
            pdf.set_fill_color(*colors[-1])
            pdf.ellipse(cx - r, base_y - height * 0.42 - r, r * 2, r * 2,
                        style="F")

    def _wildflower(self, pdf, cx, base_y, height, scale, color, petals=5):
        """Thin stem + a simple flower head (petal ellipses round a dot)."""
        pdf.set_draw_color(*color)
        pdf.set_line_width(max(0.8, 1.0 * scale))
        lean = height * 0.10
        pdf.line(cx, base_y, cx + lean, base_y - height)
        hx, hy = cx + lean, base_y - height
        pr = max(1.4, 2.3 * scale)
        pdf.set_fill_color(*color)
        for k in range(petals):
            a = 2 * math.pi * k / petals - math.pi / 2
            px, py = hx + math.cos(a) * pr, hy + math.sin(a) * pr
            pdf.ellipse(px - pr * 0.55, py - pr * 0.85, pr * 1.1, pr * 1.7,
                        style="F")
        # a couple of leaves on the stem
        lh = max(1.2, 1.9 * scale)
        for t, side in ((0.42, 1), (0.64, -1)):
            lx, ly = cx + lean * t, base_y - height * t
            pdf.ellipse(lx + (0 if side > 0 else -lh * 2.4), ly - lh / 2,
                        lh * 2.4, lh, style="F")

    def pattern_fill(self, pdf, theme, x, y, w, h, seed, scale=1.0):
        """Boho arch-repeat field: rows of tall narrow nested arches with
        fine wildflower sprigs and scattered seed dots between them."""
        rng = _rng(f"{seed}-boho-arch")
        sec = theme.rgb("secondary")
        pr = theme.rgb("primary")
        acc = theme.rgb("accent")
        stem_c = blend(pr, theme.rgb("text"), 0.2)
        band_cols = (sec, pr, acc)
        mod = 60.0 * scale
        rowh = 80.0 * scale
        half_w = mod * 0.30
        row = 0
        ry = y + rowh
        while ry <= y + h + rowh * 0.5:
            base_y = min(ry, y + h)
            offset = (mod / 2) if row % 2 else 0.0
            cx = x + half_w + offset
            col = 0
            while cx <= x + w - half_w + 0.5:
                self._nested_arch(pdf, cx, base_y, half_w, rowh * 0.60,
                                  scale, band_cols, sun=(rng.random() < 0.4))
                # motif between arches: a wildflower or a small seed cluster
                fx = cx + mod / 2
                if fx <= x + w - 3 * scale:
                    if rng.random() < 0.62:
                        self._wildflower(pdf, fx, base_y,
                                         rowh * rng.uniform(0.34, 0.5),
                                         scale, stem_c)
                    else:
                        pdf.set_fill_color(*sec)
                        for _ in range(3):
                            dx = rng.uniform(-6, 6) * scale
                            dy = rng.uniform(-rowh * 0.4, -6) * scale
                            r = 1.1 * scale
                            pdf.ellipse(fx + dx - r, base_y + dy - r,
                                        r * 2, r * 2, style="F")
                cx += mod
                col += 1
            ry += rowh
            row += 1

    def ground_field(self, pdf, theme, x, y, w, h, seed):
        """Staggered sprig/stem field rooted at the bottom edge.  Heights,
        spacing, lean, leaf phase and palette pick are all seeded --
        deliberately asymmetric (no mirrored pairs anywhere)."""
        rng = _rng(seed)
        stem_c = blend(theme.rgb("primary"), theme.rgb("text"), 0.25)
        leaf_colors = (theme.rgb("secondary"), theme.rgb("primary"))
        base_y = y + h
        tx = x + rng.uniform(3.0, 10.0)
        while tx < x + w - 3.0:
            stem_h = h * rng.uniform(0.34, 0.99)
            lean = rng.uniform(-0.16, 0.16) * stem_h
            n = max(6, int(stem_h / 6))
            pts = [(tx + lean * (i / n) ** 2, base_y - stem_h * (i / n))
                   for i in range(n + 1)]
            pdf.set_draw_color(*stem_c)
            pdf.set_line_width(0.75)
            with pdf.local_context(stroke_opacity=0.85):
                pdf.polyline(pts, style="D")
            # Leaves alternate sides going up the stem
            leaf_color = leaf_colors[rng.randrange(2)]
            leaf_w = rng.uniform(5.6, 7.6)
            step = rng.uniform(8.0, 11.0)
            side = 1 if rng.random() < 0.5 else -1
            opacity = rng.uniform(0.6, 0.85)
            pdf.set_fill_color(*leaf_color)
            d = step * 0.9
            while d < stem_h - 3.0:
                t = d / stem_h
                lx, ly = tx + lean * t * t, base_y - d
                lw, lh2 = leaf_w, leaf_w * 0.42
                with pdf.rotation(angle=side * 40, x=lx, y=ly):
                    with pdf.local_context(fill_opacity=opacity):
                        pdf.ellipse(lx if side > 0 else lx - lw,
                                    ly - lh2 / 2, lw, lh2, style="F")
                side = -side
                d += step
            # Some stems carry a seed-head bud at the tip
            if rng.random() < 0.45:
                pdf.set_fill_color(*theme.rgb("accent"))
                with pdf.local_context(fill_opacity=0.85):
                    pdf.ellipse(tx + lean - 1.9, base_y - stem_h - 1.9,
                                3.8, 3.8, style="F")
            tx += rng.uniform(13.0, 24.0)


def _frange(a: float, b: float, step: float) -> list[float]:
    out = []
    t = a
    while t <= b:
        out.append(t)
        t += step
    return out


# ===========================================================================
# Geometric
# ===========================================================================


def _geo_inks(theme: Theme) -> tuple[tuple, tuple, tuple]:
    """(line, mark, soft) ornament inks that read on the motif's cover
    surface.  On a solid primary plate (filled-blocks / noir) the ornaments
    must be lighter than the plate; on paper they sit a touch darker than
    the grid line.  ``mark`` is always the confident accent."""
    acc = theme.rgb("accent")
    if theme.ink.band == "solid":
        line = blend(theme.rgb("primary"), WHITE, 0.62)
        soft = blend(theme.rgb("primary"), WHITE, 0.32)
        return line, acc, soft
    line = blend(theme.rgb("grid_line"), theme.rgb("primary"), 0.55)
    soft = blend(theme.rgb("grid_line"), theme.rgb("primary"), 0.26)
    return line, acc, soft


class GeometricMotif(MotifFamily):
    name = "geometric"

    def bullet(self, pdf, theme, x, y, size, number=None):
        cx, cy = x + size / 2, y + size / 2
        r = size * 0.41 + 1.0   # diamond that optically matches the circle
        pdf.set_fill_color(*theme.bullet_c())
        pdf.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)],
                    style="F")
        if number is not None:
            return _number_overprint(pdf, theme, x, y, size, number)
        return x + size + 2.6

    def divider(self, pdf, theme, cx, cy, w):
        pr = theme.rgb("primary")
        acc = theme.rgb("accent")
        pdf.set_draw_color(*acc)
        pdf.set_line_width(0.4)
        pdf.line(cx - w / 2, cy, cx - 9.6, cy)
        pdf.line(cx + 9.6, cy, cx + w / 2, cy)
        for off, color, op in ((-6.4, acc, 0.6), (0.0, pr, 1.0), (6.4, acc, 0.6)):
            r = 1.2
            with pdf.local_context(fill_opacity=op):
                pdf.set_fill_color(*color)
                pdf.polygon([(cx + off, cy - r), (cx + off + r, cy),
                             (cx + off, cy + r), (cx + off - r, cy)], style="F")

    def corner(self, pdf, theme, x, y, size, quadrant):
        """Precise right-angle bracket + a single accent node.  Crisp
        line-work that reads on paper AND on the solid plate (noir), where
        the old translucent triangle stack turned muddy."""
        dx, dy = _quadrant_dir(quadrant)
        line_c, mark_c, soft_c = _geo_inks(theme)
        s = size / 22.0
        leg = 16.0 * s
        # Outer bracket hugging the corner
        pdf.set_draw_color(*line_c)
        pdf.set_line_width(0.6)
        pdf.line(x, y, x + dx * leg, y)
        pdf.line(x, y, x, y + dy * leg)
        # Finer inner bracket, offset diagonally in (drafting precision)
        off = 3.6 * s
        inner = leg * 0.52
        pdf.set_line_width(0.3)
        with pdf.local_context(stroke_opacity=0.7):
            pdf.line(x + dx * off, y + dy * off,
                     x + dx * (off + inner), y + dy * off)
            pdf.line(x + dx * off, y + dy * off,
                     x + dx * off, y + dy * (off + inner))
        # One considered accent node at the bracket vertex
        r = 2.0 * s
        nx, ny = x + dx * 0.8 * s, y + dy * 0.8 * s
        pdf.set_fill_color(*mark_c)
        pdf.polygon([(nx, ny - r), (nx + r, ny), (nx, ny + r), (nx - r, ny)],
                    style="F")

    def band(self, pdf, theme, x, y, w, h=6.0):
        """A measured tick-rule (engineer's scale): baseline + evenly
        spaced ticks, every fifth taller and in the accent."""
        line_c, mark_c, soft_c = _geo_inks(theme)
        cy = y + h / 2
        pdf.set_draw_color(*soft_c)
        pdf.set_line_width(0.3)
        pdf.line(x, cy, x + w, cy)
        step = 5.4
        t = 0.0
        i = 0
        while t <= w + 0.01:
            major = (i % 5 == 0)
            if major:
                pdf.set_draw_color(*mark_c)
                pdf.set_line_width(0.5)
                th = 2.7
            else:
                pdf.set_draw_color(*line_c)
                pdf.set_line_width(0.3)
                th = 1.4
            pdf.line(x + t, cy - th, x + t, cy + th)
            t += step
            i += 1

    def cover_hero(self, pdf, theme, seed):
        pr = theme.rgb("primary")
        sec = theme.rgb("secondary")
        acc = theme.rgb("accent")
        # Diagonal parallelogram bands
        for off, color, op in ((0, sec, 0.25), (55, acc, 0.20)):
            with pdf.local_context(fill_opacity=op):
                pdf.set_fill_color(*color)
                pdf.polygon([(0, PAGE_H * 0.55 + off),
                             (PAGE_W, PAGE_H * 0.30 + off),
                             (PAGE_W, PAGE_H * 0.30 + 90 + off),
                             (0, PAGE_H * 0.55 + 90 + off)], style="F")
        # Quarter disc at the bottom-left corner
        with pdf.local_context(fill_opacity=0.15):
            pdf.set_fill_color(*pr)
            pdf.solid_arc(-120, PAGE_H - 120, 240, 270, 360, style="F")
        # Seeded outline circles in the top-right third
        rng = _rng(seed)
        pdf.set_line_width(0.4)
        pdf.set_draw_color(*pr)
        with pdf.local_context(stroke_opacity=0.3):
            for _ in range(12):
                r = rng.uniform(3, 9)
                cx = rng.uniform(PAGE_W * 0.60, PAGE_W - 16 - r)
                cy = rng.uniform(14 + r, PAGE_H / 3)
                pdf.ellipse(cx - r, cy - r, r * 2, r * 2, style="D")

    def pattern_fill(self, pdf, theme, x, y, w, h, seed, scale=1.0):
        base, th = 32.0 * scale, 26.0 * scale
        colors = (theme.rgb("primary"), theme.rgb("accent"))
        row = 0
        ry = y - th / 2
        while ry < y + h:
            offset = (base / 2) if row % 2 else 0.0
            i = 0
            tx = x - base + offset
            while tx < x + w:
                with pdf.local_context(fill_opacity=0.22):
                    pdf.set_fill_color(*colors[i % 2])
                    pdf.polygon([(tx, ry), (tx + base, ry),
                                 (tx + base / 2, ry + th)], style="F")
                tx += base
                i += 1
            ry += th
            row += 1


# ===========================================================================
# Celestial
# ===========================================================================

class CelestialMotif(MotifFamily):
    name = "celestial"

    def _star(self, pdf, x, y, r, style="F"):
        pdf.star(x, y, r_in=r * 0.38, r_out=r, corners=4, style=style)

    def _crescent(self, pdf, theme, cx, cy, r, opacity=0.85):
        pdf.set_fill_color(*theme.rgb("primary"))
        with pdf.local_context(fill_opacity=opacity):
            pdf.ellipse(cx - r, cy - r, r * 2, r * 2, style="F")
        pdf.set_fill_color(*theme.paper_c())
        r2 = r * 0.9
        pdf.ellipse(cx - r2 + r * 0.55, cy - r2 - r * 0.30, r2 * 2, r2 * 2,
                    style="F")

    def bullet(self, pdf, theme, x, y, size, number=None):
        cx, cy = x + size / 2, y + size / 2
        pdf.set_fill_color(*theme.bullet_c())
        self._star(pdf, cx, cy, size * 0.55)
        if number is not None:
            return _number_beside(pdf, theme, x, y, size, number)
        return x + size + 2.6

    def divider(self, pdf, theme, cx, cy, w):
        self._crescent(pdf, theme, cx, cy, 2.0)
        pdf.set_fill_color(*theme.rgb("primary"))
        for side in (-1, 1):
            for i, r in enumerate((0.7, 0.5, 0.35)):
                dx = side * (5 + i * 4)
                pdf.ellipse(cx + dx - r, cy - r, r * 2, r * 2, style="F")

    def corner(self, pdf, theme, x, y, size, quadrant):
        dx, dy = _quadrant_dir(quadrant)
        s = size / 22.0
        self._crescent(pdf, theme, x + dx * 6 * s, y + dy * 6 * s, 6 * s)
        pdf.set_fill_color(*theme.rgb("accent"))
        for i, r in enumerate((2.4, 1.6, 1.2)):
            d = (10 + i * 4) * s
            jitter = (i - 1) * 3.5 * s
            self._star(pdf, x + dx * d + dy * jitter * 0.4,
                       y + dy * d + dx * jitter * 0.4, r * s * 1.4)

    def band(self, pdf, theme, x, y, w, h=6.0):
        rng = _rng(f"celestial-band-{round(x)}-{round(y)}-{round(w)}")
        cy = y + h / 2
        pts = []
        t = 2.0
        i = 0
        while t < w - 1:
            pts.append((x + t, cy + rng.uniform(-1.6, 1.6), i % 5 == 2))
            t += 6.0
            i += 1
        pdf.set_draw_color(*theme.rgb("primary"))
        pdf.set_line_width(0.2)
        with pdf.local_context(stroke_opacity=0.45):
            for (x1, y1, _), (x2, y2, _) in zip(pts, pts[1:]):
                pdf.line(x1, y1, x2, y2)
        pdf.set_fill_color(*theme.rgb("primary"))
        for px, py, is_star in pts:
            if is_star:
                self._star(pdf, px, py, 1.4)
            else:
                pdf.ellipse(px - 0.45, py - 0.45, 0.9, 0.9, style="F")

    def cover_hero(self, pdf, theme, seed):
        pr = theme.rgb("primary")
        sec = theme.rgb("secondary")
        acc = theme.rgb("accent")
        # Sky dome
        with pdf.local_context(fill_opacity=0.10):
            pdf.set_fill_color(*pr)
            pdf.ellipse(241 - 150, -30 - 150, 300, 300, style="F")
        pdf.set_line_width(0.5)
        pdf.set_draw_color(*pr)
        with pdf.local_context(stroke_opacity=0.15):
            for r in (120, 95):
                pdf.ellipse(241 - r, -30 - r, r * 2, r * 2, style="D")
        # Moon
        self._crescent(pdf, theme, 376, 79, 26)
        # Seeded stars above y=162, avoiding the title card zone
        rng = _rng(seed)
        avoid = (74, 100, 408, 246)   # x1, y1, x2, y2
        pdf.set_line_width(0.3)
        placed = 0
        attempts = 0
        while placed < 40 and attempts < 400:
            attempts += 1
            sx = rng.uniform(18, PAGE_W - 18)
            sy = rng.uniform(16, 162)
            if avoid[0] < sx < avoid[2] and avoid[1] < sy < avoid[3]:
                continue
            r = rng.uniform(0.8, 2.6)
            color = acc if rng.random() < 0.4 else pr
            pdf.set_fill_color(*color)
            with pdf.local_context(fill_opacity=0.75):
                if r > 1.6:
                    self._star(pdf, sx, sy, r)
                else:
                    pdf.ellipse(sx - r / 2, sy - r / 2, r, r, style="F")
            placed += 1
        # Horizon arc in the bottom third
        pdf.set_draw_color(*sec)
        pdf.set_line_width(0.6)
        with pdf.local_context(stroke_opacity=0.4):
            pdf.arc(241 - 260, PAGE_H - 40, 520, 255, 285, style="D")

    def pattern_fill(self, pdf, theme, x, y, w, h, seed, scale=1.0):
        pr = theme.rgb("primary")
        acc = theme.rgb("accent")
        pdf.set_line_width(0.5 * scale)
        with pdf.local_context(stroke_opacity=0.12):
            pdf.set_draw_color(*pr)
            for r in (60 * scale, 90 * scale, 120 * scale):
                pdf.ellipse(241 - r, -20 - r, r * 2, r * 2, style="D")
        rng = _rng(seed)
        for _ in range(round(140 / (scale * scale))):
            px = rng.uniform(x + 4, x + w - 4)
            py = rng.uniform(y + 4, y + h - 4)
            color = acc if rng.random() < 0.35 else pr
            pdf.set_fill_color(*color)
            with pdf.local_context(fill_opacity=0.5):
                if rng.random() < 0.30:
                    self._star(pdf, px, py, rng.uniform(1.4, 3.0) * scale)
                else:
                    r = rng.uniform(0.5, 0.9) * scale
                    pdf.ellipse(px - r, py - r, r * 2, r * 2, style="F")


# ===========================================================================
# Coastal
# ===========================================================================

class CoastalMotif(MotifFamily):
    name = "coastal"

    def bullet(self, pdf, theme, x, y, size, number=None):
        d = size * 0.95
        bx = x + (size - d) / 2
        by = y + size * 0.2
        fill = theme.box_fill() or blend(theme.paper_c(), theme.rgb("primary"), 0.08)
        pdf.set_fill_color(*fill)
        pdf.set_draw_color(*theme.bullet_c())
        pdf.set_line_width(0.35)
        # Semicircle, flat side down (top half of the circle)
        pdf.solid_arc(bx, by, d, 180, 360, style="FD")
        cx, cy = bx + d / 2, by + d / 2
        for ang in (225, 270, 315):
            a = math.radians(ang)
            pdf.line(cx, cy, cx + math.cos(a) * d * 0.32,
                     cy + math.sin(a) * d * 0.32)
        if number is not None:
            return _number_beside(pdf, theme, x, y, size, number)
        return x + size + 2.6

    def divider(self, pdf, theme, cx, cy, w):
        pdf.set_draw_color(*theme.rgb("primary"))
        pdf.set_line_width(0.45)
        pts = _wave_points(cx - w / 2, w, cy, amp=1.2, wavelength=8, step=1.0)
        pdf.polyline(pts, style="D")

    def corner(self, pdf, theme, x, y, size, quadrant):
        s = size / 22.0
        sweep = {"TL": (0, 90), "TR": (90, 180),
                 "BL": (270, 360), "BR": (180, 270)}[quadrant]
        specs = [(6 * s, theme.rgb("primary"), 0.6, 0.9),
                 (9 * s, theme.rgb("secondary"), 0.5, 0.6),
                 (12 * s, theme.rgb("accent"), 0.4, 0.4)]
        for r, color, lw, op in specs:
            pdf.set_draw_color(*color)
            pdf.set_line_width(lw)
            with pdf.local_context(stroke_opacity=op):
                pdf.arc(x - r, y - r, r * 2, sweep[0], sweep[1], style="D")

    def band(self, pdf, theme, x, y, w, h=6.0):
        d = 8.0
        fill = theme.band_fill() or blend(theme.paper_c(),
                                          theme.rgb("primary"), 0.14)
        pdf.set_fill_color(*fill)
        pdf.set_draw_color(*theme.border_c())
        pdf.set_line_width(0.35)
        t = 0.0
        while t + d <= w + 0.01:
            # flat side up: bottom half of the circle
            pdf.solid_arc(x + t, y + h / 2 - d / 2, d, 0, 180, style="FD")
            t += d

    def cover_hero(self, pdf, theme, seed):
        pr = theme.rgb("primary")
        sec = theme.rgb("secondary")
        acc = theme.rgb("accent")
        # Sun + ring
        with pdf.local_context(fill_opacity=0.45):
            pdf.set_fill_color(*acc)
            pdf.ellipse(241 - 28, 65 - 28, 56, 56, style="F")
        pdf.set_draw_color(*acc)
        pdf.set_line_width(0.5)
        with pdf.local_context(stroke_opacity=0.25):
            pdf.ellipse(241 - 34, 65 - 34, 68, 68, style="D")
        # Wave bands rising from the bottom (back to front)
        layers = [(PAGE_H - 130, sec, 0.25, 72), (PAGE_H - 100, acc, 0.28, 48),
                  (PAGE_H - 70, pr, 0.30, 24), (PAGE_H - 40, sec, 0.45, 0)]
        for top, color, op, phase in layers:
            pts = [(t, top + 7 * math.sin(2 * math.pi * (t + phase) / 96))
                   for t in _frange(0, PAGE_W, PAGE_W / 23)]
            pts += [(PAGE_W, PAGE_H), (0, PAGE_H)]
            with pdf.local_context(fill_opacity=op):
                pdf.set_fill_color(*color)
                pdf.polygon(pts, style="F")

    def pattern_fill(self, pdf, theme, x, y, w, h, seed, scale=1.0):
        r = 16.0 * scale
        module = 32.0 * scale
        colors = (theme.rgb("primary"), theme.rgb("secondary"))
        row = 0
        ry = y
        while ry < y + h + r:
            offset = (module / 2) if row % 2 else 0.0
            i = 0
            cx = x - module + offset
            while cx < x + w + module:
                with pdf.local_context(fill_opacity=0.25):
                    pdf.set_fill_color(*colors[i % 2])
                    pdf.solid_arc(cx - r, ry - r, r * 2, 0, 180, style="F")
                cx += module
                i += 1
            ry += r
            row += 1


# ===========================================================================
# Minimal
# ===========================================================================

class MinimalMotif(MotifFamily):
    """Fine editorial line-work: hairlines, a single considered mark,
    subtle framing.  Restrained but never empty -- the premium-minimal
    craft for studio + gallery."""

    name = "minimal"

    def bullet(self, pdf, theme, x, y, size, number=None):
        # A small crisp square; accent when the ink carries priority accents
        sq = 1.7
        fill = (theme.bullet_c() if theme.ink.accent_bullets
                else theme.rgb("text"))
        pdf.set_fill_color(*fill)
        pdf.rect(x + 0.4, y + (size - sq) / 2, sq, sq, style="F")
        if number is not None:
            return _number_beside(pdf, theme, x, y, size - 1, number)
        return x + size + 2.6

    def divider(self, pdf, theme, cx, cy, w):
        # Fine centered rule broken by a small node -- considered, not empty
        line_c = theme.structural()
        half = min(w, 52.0) / 2
        gap = 3.6
        pdf.set_draw_color(*line_c)
        pdf.set_line_width(0.35)
        pdf.line(cx - half, cy, cx - gap, cy)
        pdf.line(cx + gap, cy, cx + half, cy)
        r = 1.15
        pdf.set_fill_color(*line_c)
        pdf.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)],
                    style="F")

    def corner(self, pdf, theme, x, y, size, quadrant):
        # A single fine right-angle bracket -- quiet framing
        dx, dy = _quadrant_dir(quadrant)
        s = size / 22.0
        leg = 15.0 * s
        pdf.set_draw_color(*blend(theme.rgb("grid_line"),
                                  theme.rgb("text"), 0.42))
        pdf.set_line_width(0.4)
        with pdf.local_context(stroke_opacity=0.85):
            pdf.line(x, y, x + dx * leg, y)
            pdf.line(x, y, x, y + dy * leg)

    def band(self, pdf, theme, x, y, w, h=6.0):
        # Hairline carrying a few sparse nodes -- restrained rhythm
        cy = y + h / 2
        line_c = blend(theme.rgb("grid_line"), theme.rgb("primary"), 0.5)
        pdf.set_draw_color(*line_c)
        pdf.set_line_width(0.3)
        pdf.line(x, cy, x + w, cy)
        node_c = theme.structural()
        pdf.set_fill_color(*node_c)
        step = w / 6.0
        r = 0.85
        for i in range(7):
            nx = x + i * step
            pdf.rect(nx - r, cy - r, r * 2, r * 2, style="F")

    def cover_hero(self, pdf, theme, seed):
        # Fine double-frame -- premium stationery border
        pdf.set_draw_color(*blend(theme.rgb("grid_line"),
                                  theme.rgb("text"), 0.5))
        pdf.set_line_width(0.4)
        pdf.rect(14, 14, PAGE_W - 28, PAGE_H - 28, style="D")
        pdf.set_line_width(0.2)
        pdf.rect(17.5, 17.5, PAGE_W - 35, PAGE_H - 35, style="D")

    def pattern_fill(self, pdf, theme, x, y, w, h, seed, scale=1.0):
        # Very sparse fine plus-tick field -- quiet texture for a void
        c = blend(theme.rgb("grid_line"), theme.rgb("primary"), 0.42)
        pdf.set_draw_color(*c)
        pdf.set_line_width(0.25)
        step = 25.0 * scale
        arm = 1.7 * scale
        with pdf.local_context(stroke_opacity=0.6):
            gy = y + step / 2
            while gy < y + h:
                gx = x + step / 2
                while gx < x + w:
                    pdf.line(gx - arm, gy, gx + arm, gy)
                    pdf.line(gx, gy - arm, gx, gy + arm)
                    gx += step
                gy += step


MOTIFS: dict[str, MotifFamily] = {
    "botanical": BotanicalMotif(),
    "geometric": GeometricMotif(),
    "celestial": CelestialMotif(),
    "coastal": CoastalMotif(),
    "minimal": MinimalMotif(),
}
