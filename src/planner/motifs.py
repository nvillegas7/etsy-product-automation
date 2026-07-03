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

from src.planner.styles import Theme, WHITE, blend, CONTAINERS

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


# ===========================================================================
# Themed line-icon families (fitness / academic / finance / teaching / focus)
# ===========================================================================
#
# These five draw clean, flat, RECOGNISABLE line icons -- a single consistent
# ~1.0-1.6pt stroke, geometric clarity, premium adult-planner look.  Each
# icon is a module-level function ``(pdf, cx, cy, r, line_c, mark_c, lw)``
# that draws one icon centred on ``(cx, cy)`` roughly spanning the box
# ``[cx-r, cx+r] x [cy-r, cy+r]``.  ``line_c`` is the confident stroke (reads
# on paper AND on the solid plate via :func:`_geo_inks`); ``mark_c`` is the
# accent used sparingly for a single considered fill; ``lw`` is the stroke.
#
# Every family shares the slot machinery in :class:`_IconMotif`, which mirrors
# how :class:`GeometricMotif` fills the seven slots (bullet rotates the set by
# the priority number; corner is a small quadrant-aware cluster; divider is a
# centred icon between hairlines; band is an alternating strip; pattern_fill is
# a sparse SEEDED field; cover_hero is a balanced medallion + baseline
# composition; ground_field delegates to pattern_fill).


def _pen(pdf: FPDF, color: tuple, lw: float) -> None:
    pdf.set_draw_color(*color)
    pdf.set_line_width(lw)


def _icon_lw(r: float) -> float:
    """A consistent stroke that scales gently with the icon size."""
    return min(1.6, max(0.9, 0.45 + r * 0.12))


# -- Fitness icons ----------------------------------------------------------

def _i_dumbbell(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    bx = r * 0.52          # inner half-length of the bar
    wt = r * 0.40          # weight width
    ht = r * 1.00          # weight height
    pdf.line(cx - bx, cy, cx + bx, cy)
    for sx in (-1, 1):
        ex = cx + sx * bx
        pdf.rect(ex - wt / 2, cy - ht / 2, wt, ht, style="D",
                 round_corners=True, corner_radius=wt * 0.4)
        pdf.line(ex + sx * wt * 0.95, cy - ht * 0.3,
                 ex + sx * wt * 0.95, cy + ht * 0.3)


def _i_bottle(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    bw = r * 0.82
    bh = r * 1.5
    top = cy - bh * 0.42
    pdf.rect(cx - bw / 2, top, bw, bh, style="D",
             round_corners=True, corner_radius=bw * 0.34)
    cw = bw * 0.56
    pdf.rect(cx - cw / 2, top - r * 0.32, cw, r * 0.32, style="D",
             round_corners=True, corner_radius=r * 0.08)
    pdf.line(cx - bw / 2, cy + bh * 0.12, cx + bw / 2, cy + bh * 0.12)


def _i_stopwatch(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    rr = r * 0.62
    ccy = cy + r * 0.14
    pdf.circle(cx, ccy, rr, style="D")
    pdf.line(cx, ccy - rr, cx, ccy - rr - r * 0.22)
    pdf.rect(cx - r * 0.16, ccy - rr - r * 0.36, r * 0.32, r * 0.18, style="D")
    pdf.line(cx, ccy, cx, ccy - rr * 0.62)
    pdf.line(cx, ccy, cx + rr * 0.5, ccy)


def _i_heartbeat(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    pdf.polyline([(cx - r, cy), (cx - r * 0.4, cy),
                  (cx - r * 0.12, cy - r * 0.72), (cx + r * 0.12, cy + r * 0.6),
                  (cx + r * 0.4, cy), (cx + r, cy)], style="D")


def _i_medal(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    disc_cy = cy + r * 0.42
    rr = r * 0.5
    # two ribbon triangles rising from the shoulders of the disc
    pdf.polygon([(cx - r * 0.34, cy - r * 0.95), (cx - r * 0.02, cy - r * 0.05),
                 (cx - r * 0.36, cy + r * 0.02)], style="D")
    pdf.polygon([(cx + r * 0.34, cy - r * 0.95), (cx + r * 0.02, cy - r * 0.05),
                 (cx + r * 0.36, cy + r * 0.02)], style="D")
    pdf.circle(cx, disc_cy, rr, style="D")
    pdf.set_fill_color(*mark_c)
    pdf.circle(cx, disc_cy, rr * 0.34, style="F")


def _i_kettlebell(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    rb = r * 0.54
    bcy = cy + r * 0.4
    pdf.circle(cx, bcy, rb, style="D")     # round body
    # inverted-U handle sitting on the body with a visible hole
    hw = r * 0.36
    ys = cy - r * 0.32
    pdf.arc(cx - hw, ys - hw, hw * 2, 180, 360, style="D")   # top bulge
    body_top = bcy - rb
    pdf.line(cx - hw, ys, cx - hw, body_top + r * 0.02)
    pdf.line(cx + hw, ys, cx + hw, body_top + r * 0.02)


# -- Shared slot machinery --------------------------------------------------

class _IconMotif(MotifFamily):
    """Shared machinery for the flat line-icon motif families.

    Subclasses set ``name`` and ``ICONS`` -- a tuple of icon-drawing functions
    (module-level, so indexing the tuple yields the raw function, not a bound
    method).  ``ICONS[0]`` is the family's signature icon (used solo for
    divider / corner / cover medallion); ``ICONS[0]`` & ``ICONS[1]`` alternate
    in the band.
    """

    ICONS: tuple = ()

    def bullet(self, pdf, theme, x, y, size, number=None):
        line_c, mark_c, _soft = _geo_inks(theme)
        cx, cy = x + size / 2, y + size / 2
        r = size * 0.5
        idx = ((number - 1) % len(self.ICONS)) if number else 0
        self.ICONS[idx](pdf, cx, cy, r, line_c, mark_c, _icon_lw(r))
        if number is not None:
            return _number_beside(pdf, theme, x, y, size, number)
        return x + size + 2.6

    def divider(self, pdf, theme, cx, cy, w):
        line_c, mark_c, soft = _geo_inks(theme)
        r = 3.6
        gap = r + 4.6
        pdf.set_draw_color(*soft)
        pdf.set_line_width(0.4)
        pdf.line(cx - w / 2, cy, cx - gap, cy)
        pdf.line(cx + gap, cy, cx + w / 2, cy)
        self.ICONS[0](pdf, cx, cy, r, line_c, mark_c, _icon_lw(r))

    def corner(self, pdf, theme, x, y, size, quadrant):
        dx, dy = _quadrant_dir(quadrant)
        line_c, mark_c, _soft = _geo_inks(theme)
        s = size / 22.0
        r = 5.2 * s
        cx = x + dx * (r + 2.0)
        cy = y + dy * (r + 2.0)
        self.ICONS[0](pdf, cx, cy, r, line_c, mark_c, _icon_lw(r))
        r2 = r * 0.5
        self.ICONS[1 % len(self.ICONS)](pdf, cx + dx * r * 2.2,
                                        cy + dy * r * 1.7, r2, line_c, mark_c,
                                        _icon_lw(r2))

    def band(self, pdf, theme, x, y, w, h=6.0):
        line_c, mark_c, _soft = _geo_inks(theme)
        cy = y + h / 2
        r = h * 0.42
        step = r * 3.8
        t = step / 2
        i = 0
        while t <= w - r * 0.5:
            self.ICONS[i % 2](pdf, x + t, cy, r, line_c, mark_c, _icon_lw(r))
            t += step
            i += 1

    def pattern_fill(self, pdf, theme, x, y, w, h, seed, scale=1.0):
        line_c, mark_c, _soft = _geo_inks(theme)
        rng = _rng(f"{seed}-{self.name}")
        step = 52.0 * scale
        r = 7.0 * scale
        gy = y + step * 0.5
        row = 0
        while gy < y + h + r:
            offset = (step * 0.5) if row % 2 else 0.0
            gx = x + step * 0.4 + offset
            while gx < x + w - r * 0.3:
                fn = self.ICONS[rng.randrange(len(self.ICONS))]
                jx = gx + rng.uniform(-5, 5) * scale
                jy = gy + rng.uniform(-5, 5) * scale
                rr = r * rng.uniform(0.82, 1.12)
                with pdf.local_context(stroke_opacity=0.55, fill_opacity=0.55):
                    fn(pdf, jx, jy, rr, line_c, mark_c, _icon_lw(rr))
                gx += step
            gy += step
            row += 1

    def cover_hero(self, pdf, theme, seed):
        line_c, mark_c, soft = _geo_inks(theme)
        cx = PAGE_W / 2
        n = len(self.ICONS)
        # Top medallion: a fine ring around the signature icon.
        hy = 70.0
        pdf.set_draw_color(*soft)
        pdf.set_line_width(0.7)
        with pdf.local_context(stroke_opacity=0.5):
            pdf.circle(cx, hy, 32, style="D")
        self.ICONS[0](pdf, cx, hy, 16, line_c, mark_c, 1.5)
        # Symmetric flankers.
        self.ICONS[1 % n](pdf, cx - 74, hy + 2, 11, line_c, mark_c,
                          _icon_lw(11))
        self.ICONS[2 % n](pdf, cx + 74, hy + 2, 11, line_c, mark_c,
                          _icon_lw(11))
        # Bottom baseline rhythm.
        by = PAGE_H - 52.0
        pdf.set_draw_color(*soft)
        pdf.set_line_width(0.5)
        with pdf.local_context(stroke_opacity=0.4):
            pdf.line(48, by, PAGE_W - 48, by)
        count = 7
        for k in range(count):
            fx = 70 + k * (PAGE_W - 140) / (count - 1)
            self.ICONS[k % n](pdf, fx, by - 12, 9, line_c, mark_c, _icon_lw(9))


class FitnessMotif(_IconMotif):
    name = "fitness"
    ICONS = (_i_dumbbell, _i_kettlebell, _i_bottle, _i_stopwatch,
             _i_heartbeat, _i_medal)


# -- Academic + teaching shared icons ---------------------------------------

def _i_pencil(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    hh = r * 0.2
    bx0 = cx - r * 0.8
    bx1 = cx + r * 0.4
    pdf.rect(bx0, cy - hh, bx1 - bx0, hh * 2, style="D")
    pdf.polygon([(bx1, cy - hh), (cx + r * 0.85, cy), (bx1, cy + hh)],
                style="D")
    pdf.line(bx0 + r * 0.3, cy - hh, bx0 + r * 0.3, cy + hh)   # band
    pdf.set_fill_color(*mark_c)
    pdf.polygon([(cx + r * 0.66, cy - hh * 0.55), (cx + r * 0.85, cy),
                 (cx + r * 0.66, cy + hh * 0.55)], style="F")   # lead tip


def _i_star(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    pdf.star(cx, cy, r_in=r * 0.42, r_out=r * 0.86, corners=5,
             rotate_degrees=-90, style="D")


def _i_bulb(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    rr = r * 0.54
    bcy = cy - r * 0.18
    pdf.circle(cx, bcy, rr, style="D")
    bw = rr * 0.9
    basey = bcy + rr * 0.74
    pdf.rect(cx - bw / 2, basey, bw, r * 0.32, style="D")
    pdf.line(cx - bw / 2, basey + r * 0.16, cx + bw / 2, basey + r * 0.16)
    pdf.set_fill_color(*mark_c)
    pdf.circle(cx, bcy, r * 0.1, style="F")


# -- Academic-only icons ----------------------------------------------------

def _i_openbook(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    top = cy - r * 0.5
    bot = cy + r * 0.52
    pdf.line(cx, top + r * 0.06, cx, bot)                       # spine
    pdf.polygon([(cx, top + r * 0.06), (cx - r * 0.86, top + r * 0.3),
                 (cx - r * 0.86, bot - r * 0.04),
                 (cx, bot - r * 0.06)], style="D")               # left page
    pdf.polygon([(cx, top + r * 0.06), (cx + r * 0.86, top + r * 0.3),
                 (cx + r * 0.86, bot - r * 0.04),
                 (cx, bot - r * 0.06)], style="D")               # right page


def _i_gradcap(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    top = cy - r * 0.46
    pdf.polygon([(cx, top), (cx + r * 0.92, cy - r * 0.06),
                 (cx, cy + r * 0.34), (cx - r * 0.92, cy - r * 0.06)],
                style="D")                                       # mortarboard
    pdf.polygon([(cx - r * 0.36, cy + r * 0.16), (cx + r * 0.36, cy + r * 0.16),
                 (cx + r * 0.28, cy + r * 0.52),
                 (cx - r * 0.28, cy + r * 0.52)], style="D")     # cap band
    pdf.line(cx + r * 0.92, cy - r * 0.06, cx + r * 0.66, cy + r * 0.5)  # tassel
    pdf.set_fill_color(*mark_c)
    pdf.circle(cx + r * 0.66, cy + r * 0.58, r * 0.1, style="F")


def _i_ruler(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    w = r * 1.7
    hh = r * 0.34
    x0 = cx - w / 2
    pdf.rect(x0, cy - hh, w, hh * 2, style="D")
    n = 6
    for i in range(1, n):
        tx = x0 + w * i / n
        tick = hh * (1.25 if i % 2 == 0 else 0.7)
        pdf.line(tx, cy - hh, tx, cy - hh + tick)


class AcademicMotif(_IconMotif):
    name = "academic"
    ICONS = (_i_pencil, _i_openbook, _i_gradcap, _i_ruler, _i_bulb, _i_star)


# -- Finance icons ----------------------------------------------------------

def _i_coin(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    pdf.circle(cx, cy, r * 0.78, style="D")
    pdf.circle(cx, cy, r * 0.55, style="D")
    pdf.line(cx, cy - r * 0.5, cx, cy + r * 0.5)   # currency bar


def _i_coinstack(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    ew = r * 1.3
    eh = r * 0.32
    for i in range(3):
        ey = cy + r * 0.5 - i * r * 0.44
        pdf.ellipse(cx - ew / 2, ey - eh / 2, ew, eh, style="D")


def _i_piggy(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    bw = r * 1.44
    bh = r * 0.98
    pdf.ellipse(cx - bw / 2, cy - bh / 2, bw, bh, style="D")     # body
    pdf.polygon([(cx - r * 0.22, cy - bh * 0.4), (cx + r * 0.04, cy - bh * 0.78),
                 (cx + r * 0.14, cy - bh * 0.34)], style="D")    # ear
    pdf.rect(cx + bw * 0.3, cy - r * 0.02, r * 0.3, r * 0.32, style="D")  # snout
    pdf.line(cx - r * 0.16, cy - bh * 0.34, cx + r * 0.2, cy - bh * 0.34)  # slot
    pdf.line(cx - r * 0.42, cy + bh * 0.42, cx - r * 0.42, cy + bh * 0.66)  # leg
    pdf.line(cx + r * 0.26, cy + bh * 0.42, cx + r * 0.26, cy + bh * 0.66)  # leg


def _i_barchart(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    base = cy + r * 0.62
    pdf.line(cx - r * 0.82, base, cx + r * 0.82, base)
    bw = r * 0.34
    for bx, hgt in ((cx - r * 0.56, r * 0.5), (cx - r * 0.02, r * 0.86),
                    (cx + r * 0.52, r * 1.2)):
        pdf.rect(bx - bw / 2, base - hgt, bw, hgt, style="D")


def _i_uparrow(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    x1, y1 = cx + r * 0.62, cy - r * 0.58
    pdf.line(cx - r * 0.7, cy + r * 0.6, x1, y1)
    pdf.line(x1, y1, x1 - r * 0.46, y1 + r * 0.08)
    pdf.line(x1, y1, x1 - r * 0.08, y1 + r * 0.46)


def _i_wallet(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    w = r * 1.5
    h = r * 1.02
    pdf.rect(cx - w / 2, cy - h / 2, w, h, style="D",
             round_corners=True, corner_radius=r * 0.16)
    fy = cy + h * 0.04
    pdf.line(cx - w / 2, fy, cx + w / 2, fy)                     # flap seam
    pdf.set_fill_color(*mark_c)
    pdf.circle(cx + w * 0.32, fy, r * 0.13, style="F")          # clasp


class FinanceMotif(_IconMotif):
    name = "finance"
    ICONS = (_i_coin, _i_coinstack, _i_piggy, _i_barchart, _i_uparrow,
             _i_wallet)


# -- Teaching icons (apple / chalkboard / book stack / A+; reuse pencil+star)

def _i_apple(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    rr = r * 0.6
    bcy = cy + r * 0.15
    pdf.circle(cx, bcy, rr, style="D")                          # body
    pdf.line(cx, bcy - rr * 0.98, cx + r * 0.05, cy - r * 0.6)  # stem
    pdf.set_fill_color(*mark_c)
    pdf.ellipse(cx + r * 0.05, cy - r * 0.72, r * 0.36, r * 0.2,
                style="F")                                      # leaf


def _i_chalkboard(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    w = r * 1.6
    h = r * 1.1
    pdf.rect(cx - w / 2, cy - h / 2, w, h, style="D")           # frame
    ins = r * 0.16
    pdf.rect(cx - w / 2 + ins, cy - h / 2 + ins, w - 2 * ins, h - 2 * ins,
             style="D")                                          # inner board
    pdf.line(cx - w * 0.26, cy - h * 0.1, cx + w * 0.06, cy - h * 0.1)
    pdf.line(cx - w * 0.26, cy + h * 0.12, cx + w * 0.2, cy + h * 0.12)


def _i_bookstack(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    w = r * 1.5
    hh = r * 0.3
    for i, off in enumerate((-r * 0.16, r * 0.2, -r * 0.06)):
        y0 = cy + r * 0.55 - i * (hh + r * 0.08)
        pdf.rect(cx - w / 2 + off, y0 - hh, w, hh, style="D")


def _i_aplus(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    ax = cx - r * 0.25
    pdf.line(ax, cy - r * 0.6, ax - r * 0.42, cy + r * 0.55)    # left leg
    pdf.line(ax, cy - r * 0.6, ax + r * 0.42, cy + r * 0.55)    # right leg
    pdf.line(ax - r * 0.22, cy + r * 0.06, ax + r * 0.22, cy + r * 0.06)  # bar
    px, py = cx + r * 0.6, cy - r * 0.28
    _pen(pdf, mark_c, lw)
    pdf.line(px - r * 0.18, py, px + r * 0.18, py)              # plus
    pdf.line(px, py - r * 0.18, px, py + r * 0.18)


class TeachingMotif(_IconMotif):
    name = "teaching"
    ICONS = (_i_apple, _i_chalkboard, _i_bookstack, _i_pencil, _i_star,
             _i_aplus)


# -- Focus / productivity icons (reuse bulb) --------------------------------

def _i_checkbox(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    s = r * 1.2
    pdf.rect(cx - s / 2, cy - s / 2, s, s, style="D",
             round_corners=True, corner_radius=r * 0.22)
    _pen(pdf, mark_c, lw * 1.1)
    pdf.polyline([(cx - r * 0.32, cy + r * 0.02), (cx - r * 0.06, cy + r * 0.3),
                  (cx + r * 0.42, cy - r * 0.34)], style="D")


def _i_checkmark(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw * 1.15)
    pdf.polyline([(cx - r * 0.7, cy + r * 0.05), (cx - r * 0.18, cy + r * 0.55),
                  (cx + r * 0.7, cy - r * 0.5)], style="D")


def _i_arrow(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    pdf.line(cx - r * 0.75, cy, cx + r * 0.6, cy)
    pdf.line(cx + r * 0.6, cy, cx + r * 0.22, cy - r * 0.36)
    pdf.line(cx + r * 0.6, cy, cx + r * 0.22, cy + r * 0.36)


def _i_target(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    pdf.circle(cx, cy, r * 0.72, style="D")
    pdf.circle(cx, cy, r * 0.4, style="D")
    pdf.set_fill_color(*mark_c)
    pdf.circle(cx, cy, r * 0.13, style="F")


def _i_dotcluster(pdf, cx, cy, r, line_c, mark_c, lw):
    pdf.set_fill_color(*line_c)
    for dx, dy in ((-r * 0.42, -r * 0.34), (r * 0.42, -r * 0.28),
                   (-r * 0.26, r * 0.44)):
        pdf.circle(cx + dx, cy + dy, r * 0.16, style="F")
    pdf.set_fill_color(*mark_c)
    pdf.circle(cx + r * 0.34, cy + r * 0.36, r * 0.16, style="F")


class FocusMotif(_IconMotif):
    name = "focus"
    ICONS = (_i_checkbox, _i_checkmark, _i_arrow, _i_target, _i_bulb,
             _i_dotcluster)


# ===========================================================================
# Travel line-icons (suitcase / airplane / map-pin / compass / camera / globe)
# ===========================================================================

def _i_suitcase(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    bw, bh = r * 1.5, r * 1.2
    by = cy - bh * 0.34
    bx = cx - bw / 2
    pdf.rect(bx, by, bw, bh, style="D", round_corners=True,
             corner_radius=r * 0.2)
    # inverted-U handle sitting on the top edge
    hw, hh = r * 0.36, r * 0.26
    pdf.arc(cx - hw, by - hh, hw * 2, 180, 360, b=hh * 2, style="D")
    # a horizontal seam splitting lid from base + two latch dots
    pdf.line(bx, by + bh * 0.42, bx + bw, by + bh * 0.42)
    pdf.set_fill_color(*mark_c)
    for sx in (-1, 1):
        pdf.circle(cx + sx * r * 0.42, by + bh * 0.42, r * 0.1, style="F")


def _i_airplane(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    # fuselage (top-view, nose up)
    fw = r * 0.2
    pdf.ellipse(cx - fw, cy - r * 0.92, fw * 2, r * 1.84, style="D")
    # swept-back main wings
    for sx in (-1, 1):
        pdf.polygon([(cx + sx * fw * 0.4, cy - r * 0.2),
                     (cx + sx * r * 0.9, cy + r * 0.34),
                     (cx + sx * fw * 0.4, cy + r * 0.16)], style="D")
    # swept tail fins
    for sx in (-1, 1):
        pdf.polygon([(cx + sx * fw * 0.3, cy + r * 0.5),
                     (cx + sx * r * 0.34, cy + r * 0.78),
                     (cx + sx * fw * 0.3, cy + r * 0.72)], style="D")


def _i_mappin(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    hy = cy - r * 0.25
    rr = r * 0.56
    tip = (cx, cy + r)
    # two straight flanks meeting the tip + a domed top arc
    pdf.line(tip[0], tip[1], cx - rr, hy)
    pdf.line(tip[0], tip[1], cx + rr, hy)
    pdf.arc(cx - rr, hy - rr, rr * 2, 180, 360, style="D")
    pdf.circle(cx, hy, rr * 0.42, style="D")   # inner hole


def _i_compass(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    rr = r * 0.86
    pdf.circle(cx, cy, rr, style="D")
    # N-pointing diamond needle: north half filled, south half open
    n = (cx, cy - r * 0.56)
    s = (cx, cy + r * 0.56)
    e = (cx + r * 0.22, cy)
    w = (cx - r * 0.22, cy)
    pdf.set_fill_color(*mark_c)
    pdf.polygon([n, e, w], style="F")
    pdf.polygon([s, e, w], style="D")
    pdf.set_fill_color(*line_c)
    pdf.circle(cx, cy, r * 0.08, style="F")


def _i_camera(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    bw, bh = r * 1.6, r * 1.04
    by = cy - bh * 0.3
    bx = cx - bw / 2
    # viewfinder bump on the top edge
    pdf.rect(cx - r * 0.52, by - r * 0.22, r * 0.5, r * 0.22, style="D")
    pdf.rect(bx, by, bw, bh, style="D", round_corners=True,
             corner_radius=r * 0.14)
    ly = by + bh * 0.52
    pdf.circle(cx, ly, r * 0.42, style="D")
    pdf.circle(cx, ly, r * 0.22, style="D")
    pdf.set_fill_color(*mark_c)
    pdf.circle(cx + bw * 0.34, by + bh * 0.2, r * 0.1, style="F")   # flash


def _i_globe(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    rr = r * 0.85
    pdf.circle(cx, cy, rr, style="D")
    mw = rr * 0.46
    pdf.ellipse(cx - mw, cy - rr, mw * 2, rr * 2, style="D")   # meridian
    pdf.line(cx - rr, cy, cx + rr, cy)                         # equator
    off = rr * 0.5
    hw = (rr * rr - off * off) ** 0.5
    pdf.line(cx - hw, cy - off, cx + hw, cy - off)             # upper latitude
    pdf.line(cx - hw, cy + off, cx + hw, cy + off)             # lower latitude


class TravelMotif(_IconMotif):
    name = "travel"
    ICONS = (_i_suitcase, _i_airplane, _i_mappin, _i_compass, _i_camera,
             _i_globe)


# ===========================================================================
# Wedding line-icons (rings / cake / flutes / heart / arch / envelope)
# ===========================================================================

def _i_rings(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    rr = r * 0.52
    off = r * 0.4
    pdf.circle(cx - off, cy + r * 0.1, rr, style="D")
    pdf.circle(cx + off, cy + r * 0.1, rr, style="D")
    # a little solitaire gem on the right ring's crown
    pdf.set_fill_color(*mark_c)
    gy = cy + r * 0.1 - rr
    pdf.polygon([(cx + off, gy - r * 0.2), (cx + off + r * 0.12, gy),
                 (cx + off, gy + r * 0.06), (cx + off - r * 0.12, gy)],
                style="F")


def _i_cake(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    tiers = ((1.4, cy + r * 0.3, r * 0.5),
             (1.0, cy - r * 0.2, r * 0.5),
             (0.64, cy - r * 0.66, r * 0.46))
    for wf, top, h in tiers:
        w = r * wf
        pdf.rect(cx - w / 2, top, w, h, style="D", round_corners=True,
                 corner_radius=r * 0.08)
    # candle + flame topper
    pdf.line(cx, cy - r * 0.66, cx, cy - r * 0.9)
    pdf.set_fill_color(*mark_c)
    pdf.circle(cx, cy - r * 0.96, r * 0.1, style="F")


def _i_flutes(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    for sx, tilt in ((-1, -0.16), (1, 0.16)):
        fx = cx + sx * r * 0.42
        tx = fx + tilt * r         # bowl centre drifts outward (a toast)
        bw = r * 0.34
        stem_top = (fx, cy + r * 0.08)
        pdf.polygon([(tx - bw / 2, cy - r * 0.72), (tx + bw / 2, cy - r * 0.72),
                     stem_top], style="D")               # tapered bowl
        pdf.line(stem_top[0], stem_top[1], fx, cy + r * 0.62)   # stem
        pdf.line(fx - r * 0.2, cy + r * 0.62, fx + r * 0.2, cy + r * 0.62)  # foot
    pdf.set_fill_color(*mark_c)
    pdf.circle(cx, cy - r * 0.5, r * 0.08, style="F")    # a rising bubble


def _i_heart(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    lr = r * 0.4
    ty = cy - r * 0.15
    tip = (cx, cy + r * 0.82)
    pdf.arc(cx - 2 * lr, ty - lr, 2 * lr, 180, 360, style="D")   # left lobe
    pdf.arc(cx, ty - lr, 2 * lr, 180, 360, style="D")            # right lobe
    pdf.line(cx - 2 * lr, ty, tip[0], tip[1])
    pdf.line(cx + 2 * lr, ty, tip[0], tip[1])


def _i_arch(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    pw = r * 0.55
    base_y = cy + r * 0.85
    shoulder = cy - r * 0.2
    pdf.line(cx - pw, base_y, cx - pw, shoulder)
    pdf.line(cx + pw, base_y, cx + pw, shoulder)
    pdf.arc(cx - pw, shoulder - pw, pw * 2, 180, 360, style="D")   # crown
    # a few floral buds nestled on the crown
    pdf.set_fill_color(*mark_c)
    for a in (215, 250, 290, 325):
        rad = math.radians(a)
        px = cx + math.cos(rad) * pw
        py = (shoulder) + math.sin(rad) * pw
        pdf.circle(px, py, r * 0.09, style="F")


def _i_envelope(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    w, h = r * 1.5, r * 1.02
    x0, y0 = cx - w / 2, cy - h / 2
    pdf.rect(x0, y0, w, h, style="D")
    pdf.line(x0, y0, cx, cy + h * 0.06)      # flap left
    pdf.line(x0 + w, y0, cx, cy + h * 0.06)  # flap right
    pdf.set_fill_color(*mark_c)
    pdf.circle(cx, cy + h * 0.06, r * 0.1, style="F")   # wax seal


class WeddingMotif(_IconMotif):
    name = "wedding"
    ICONS = (_i_rings, _i_cake, _i_flutes, _i_heart, _i_arch, _i_envelope)


# ===========================================================================
# Meal / recipe line-icons (chef-hat / fork+knife / pot / whisk / plate /
# grocery-basket)
# ===========================================================================

def _i_chefhat(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    # band
    bw, bh = r * 1.0, r * 0.34
    pdf.rect(cx - bw / 2, cy + r * 0.2, bw, bh, style="D", round_corners=True,
             corner_radius=r * 0.06)
    # puffy top: three overlapping discs
    pdf.circle(cx, cy - r * 0.28, r * 0.44, style="D")
    pdf.circle(cx - r * 0.4, cy - r * 0.02, r * 0.32, style="D")
    pdf.circle(cx + r * 0.4, cy - r * 0.02, r * 0.32, style="D")


def _i_forkknife(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    piv = (cx, cy + r * 0.35)
    with pdf.rotation(angle=-15, x=piv[0], y=piv[1]):
        fx = cx - r * 0.2
        pdf.line(fx, cy + r * 0.82, fx, cy - r * 0.22)          # shaft
        for tx in (fx - r * 0.16, fx, fx + r * 0.16):
            pdf.line(tx, cy - r * 0.22, tx, cy - r * 0.72)      # tines
        pdf.line(fx - r * 0.16, cy - r * 0.22, fx + r * 0.16, cy - r * 0.22)
    with pdf.rotation(angle=15, x=piv[0], y=piv[1]):
        kx = cx + r * 0.2
        pdf.line(kx, cy + r * 0.82, kx, cy + r * 0.04)          # handle
        pdf.polygon([(kx, cy + r * 0.04), (kx + r * 0.15, cy - r * 0.28),
                     (kx + r * 0.1, cy - r * 0.6), (kx, cy - r * 0.72)],
                    style="D")                                  # blade


def _i_pot(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    top, bot = cy - r * 0.06, cy + r * 0.72
    pdf.polygon([(cx - r * 0.64, top), (cx + r * 0.64, top),
                 (cx + r * 0.5, bot), (cx - r * 0.5, bot)], style="D")  # body
    # bracket handles either side of the rim
    for sx in (-1, 1):
        ex = cx + sx * r * 0.64
        hx = cx + sx * r * 0.86
        pdf.line(ex, top + r * 0.04, hx, top + r * 0.04)
        pdf.line(hx, top + r * 0.04, hx, top + r * 0.24)
        pdf.line(hx, top + r * 0.24, ex, top + r * 0.24)
    # lid: rim line + central knob
    pdf.line(cx - r * 0.7, top, cx + r * 0.7, top)
    pdf.line(cx, top, cx, top - r * 0.18)
    pdf.set_fill_color(*mark_c)
    pdf.circle(cx, top - r * 0.22, r * 0.09, style="F")


def _i_whisk(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    y_top, y_bot = cy - r * 0.12, cy + r * 0.82
    pdf.line(cx, cy - r * 0.86, cx, y_top)          # handle
    for amp in (-0.42, -0.15, 0.15, 0.42):
        pts = []
        for i in range(13):
            t = i / 12
            pts.append((cx + amp * r * math.sin(math.pi * t),
                        y_top + (y_bot - y_top) * t))
        pdf.polyline(pts, style="D")                # balloon wires


def _i_plate(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    pdf.circle(cx, cy, r * 0.85, style="D")
    pdf.circle(cx, cy, r * 0.55, style="D")


def _i_basket(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    top, bot = cy - r * 0.08, cy + r * 0.74
    pdf.polygon([(cx - r * 0.7, top), (cx + r * 0.7, top),
                 (cx + r * 0.46, bot), (cx - r * 0.46, bot)], style="D")
    pdf.arc(cx - r * 0.5, top - r * 0.5, r, 180, 360, style="D")   # handle
    # weave grid
    for sx in (-0.32, 0.0, 0.32):
        pdf.line(cx + sx * r, top, cx + sx * r * 0.78, bot)
    pdf.line(cx - r * 0.6, cy + r * 0.32, cx + r * 0.6, cy + r * 0.32)


class MealMotif(_IconMotif):
    name = "meal_recipe"
    ICONS = (_i_chefhat, _i_forkknife, _i_pot, _i_whisk, _i_plate, _i_basket)


# ===========================================================================
# Self-care line-icons (lotus / crescent+stars / candle / teacup / water-drop
# / leaf)
# ===========================================================================

def _petal(pdf, base, ang_deg, length, width):
    """One pointed lotus petal growing from *base* at *ang_deg* off vertical."""
    a = math.radians(ang_deg)
    ux, uy = math.sin(a), -math.cos(a)        # up-ish direction
    px, py = -uy, ux                          # perpendicular
    tip = (base[0] + ux * length, base[1] + uy * length)
    ml = (base[0] + ux * length * 0.5 + px * width,
          base[1] + uy * length * 0.5 + py * width)
    mr = (base[0] + ux * length * 0.5 - px * width,
          base[1] + uy * length * 0.5 - py * width)
    pdf.polygon([base, ml, tip, mr], style="D")


def _i_lotus(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    base = (cx, cy + r * 0.6)
    for ang, ln in ((-52, r * 1.0), (-26, r * 1.2), (0, r * 1.35),
                    (26, r * 1.2), (52, r * 1.0)):
        _petal(pdf, base, ang, ln, r * 0.2)
    # a little waterline the blossom rests on
    pdf.line(cx - r * 0.7, cy + r * 0.66, cx + r * 0.7, cy + r * 0.66)


def _i_moonstars(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    R = r * 0.72
    off = r * 0.52
    xh = off / 2.0
    yh = (R * R - xh * xh) ** 0.5
    fu = math.degrees(math.atan2(yh, xh))      # horn half-angle
    # crescent = outer convex arc of circle O + inner concave arc of circle I;
    # both circles share radius R so the arcs meet exactly at the two horns.
    pdf.arc(cx - R, cy - R, R * 2, fu, 360 - fu, style="D")            # outer
    pdf.arc(cx + off - R, cy - R, R * 2, 180 - fu, 180 + fu, style="D")  # inner
    # little stars nestled in the opening
    pdf.set_fill_color(*mark_c)
    for sx, sy, sr in ((0.62, -0.5, 0.1), (0.86, 0.02, 0.07),
                       (0.54, 0.42, 0.08)):
        pdf.circle(cx + sx * r, cy + sy * r, sr * r, style="F")


def _i_candle(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    bw, bh = r * 0.52, r * 1.1
    top = cy - r * 0.26
    pdf.rect(cx - bw / 2, top, bw, bh, style="D", round_corners=True,
             corner_radius=r * 0.1)
    pdf.line(cx, top, cx, top - r * 0.14)      # wick
    # flame teardrop
    pdf.set_fill_color(*mark_c)
    pdf.polygon([(cx, top - r * 0.72), (cx + r * 0.15, top - r * 0.3),
                 (cx, top - r * 0.12), (cx - r * 0.15, top - r * 0.3)],
                style="F")


def _i_teacup(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    rb = r * 0.56
    rim = cy - r * 0.05
    pdf.arc(cx - rb, rim - rb, rb * 2, 0, 180, style="D")   # bowl (lower half)
    pdf.line(cx - rb, rim, cx + rb, rim)                    # rim
    # handle bracket on the right
    hx = cx + rb
    pdf.line(hx, rim + r * 0.08, hx + r * 0.28, rim + r * 0.08)
    pdf.line(hx + r * 0.28, rim + r * 0.08, hx + r * 0.28, rim + r * 0.4)
    pdf.line(hx + r * 0.28, rim + r * 0.4, hx, rim + r * 0.4)
    # saucer
    pdf.line(cx - r * 0.74, rim + rb + r * 0.06,
             cx + r * 0.74, rim + rb + r * 0.06)
    # two steam curls
    for sx in (-0.2, 0.2):
        pts = [(cx + sx * r + 0.06 * r * math.sin(math.pi * i / 3),
                rim - r * 0.18 - i * r * 0.12) for i in range(4)]
        pdf.polyline(pts, style="D")


def _i_waterdrop(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    rb = r * 0.55
    bcy = cy + r * 0.22
    tip = (cx, cy - r * 0.82)
    pdf.line(tip[0], tip[1], cx - rb, bcy)
    pdf.line(tip[0], tip[1], cx + rb, bcy)
    pdf.arc(cx - rb, bcy - rb, rb * 2, 0, 180, style="D")   # round bottom


def _i_leaf(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    with pdf.rotation(angle=-35, x=cx, y=cy):
        a_tip = (cx, cy - r * 0.82)
        b_base = (cx, cy + r * 0.82)
        amp = r * 0.4
        left = [(cx - amp * math.sin(math.pi * i / 12),
                 a_tip[1] + (b_base[1] - a_tip[1]) * i / 12) for i in range(13)]
        right = [(cx + amp * math.sin(math.pi * (12 - i) / 12),
                  b_base[1] - (b_base[1] - a_tip[1]) * i / 12)
                 for i in range(13)]
        pdf.polygon(left + right, style="D")
        pdf.line(a_tip[0], a_tip[1], b_base[0], b_base[1])   # midrib
        for t in (0.35, 0.55, 0.75):
            my = a_tip[1] + (b_base[1] - a_tip[1]) * t
            vw = amp * math.sin(math.pi * t) * 0.7
            pdf.line(cx, my, cx - vw, my + vw * 0.5)
            pdf.line(cx, my, cx + vw, my + vw * 0.5)
        # short stem past the base
        pdf.line(b_base[0], b_base[1], b_base[0], b_base[1] + r * 0.28)


class SelfCareMotif(_IconMotif):
    name = "self_care"
    ICONS = (_i_lotus, _i_moonstars, _i_candle, _i_teacup, _i_waterdrop,
             _i_leaf)


# ===========================================================================
# Home-management line-icons (house / potted-plant / broom / spray-bottle /
# key / clock)
# ===========================================================================

def _i_house(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    wall_top = cy - r * 0.04
    pdf.rect(cx - r * 0.55, wall_top, r * 1.1, r * 0.88, style="D")   # walls
    pdf.polygon([(cx - r * 0.72, wall_top), (cx, cy - r * 0.78),
                 (cx + r * 0.72, wall_top)], style="D")               # roof
    pdf.rect(cx - r * 0.16, cy + r * 0.36, r * 0.32, r * 0.48,
             style="D")                                               # door
    pdf.set_fill_color(*mark_c)
    pdf.circle(cx + r * 0.08, cy + r * 0.6, r * 0.05, style="F")      # knob


def _i_plant(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    rim = cy + r * 0.24
    pdf.polygon([(cx - r * 0.45, rim), (cx + r * 0.45, rim),
                 (cx + r * 0.3, cy + r * 0.84),
                 (cx - r * 0.3, cy + r * 0.84)], style="D")           # pot
    pdf.line(cx - r * 0.5, rim, cx + r * 0.5, rim)                    # pot rim
    base = (cx, cy + r * 0.18)
    for ang, ln in ((-36, r * 0.82), (0, r * 0.98), (36, r * 0.82)):
        _petal(pdf, base, ang, ln, r * 0.16)                         # leaves


def _i_broom(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    pdf.line(cx, cy - r * 0.85, cx, cy + r * 0.14)                   # handle
    pdf.polygon([(cx - r * 0.28, cy + r * 0.14), (cx + r * 0.28, cy + r * 0.14),
                 (cx + r * 0.44, cy + r * 0.82),
                 (cx - r * 0.44, cy + r * 0.82)], style="D")         # bristles
    pdf.line(cx - r * 0.28, cy + r * 0.3, cx + r * 0.28, cy + r * 0.3)  # band
    for f in (-0.6, -0.2, 0.2, 0.6):
        pdf.line(cx + f * r * 0.28, cy + r * 0.3,
                 cx + f * r * 0.44, cy + r * 0.82)                   # strands


def _i_spraybottle(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    pdf.rect(cx - r * 0.32, cy - r * 0.04, r * 0.64, r * 0.92, style="D",
             round_corners=True, corner_radius=r * 0.1)              # body
    pdf.rect(cx - r * 0.18, cy - r * 0.26, r * 0.36, r * 0.22, style="D")  # neck
    pdf.polygon([(cx - r * 0.18, cy - r * 0.26), (cx - r * 0.6, cy - r * 0.26),
                 (cx - r * 0.6, cy - r * 0.14),
                 (cx - r * 0.18, cy - r * 0.14)], style="D")         # nozzle
    pdf.line(cx - r * 0.18, cy - r * 0.02, cx - r * 0.42, cy + r * 0.16)  # trigger
    pdf.line(cx - r * 0.32, cy + r * 0.5, cx + r * 0.32, cy + r * 0.5)    # label
    pdf.set_fill_color(*mark_c)
    for dx, dy in ((-0.78, -0.34), (-0.82, -0.18), (-0.72, -0.02)):
        pdf.circle(cx + dx * r, cy + dy * r, r * 0.05, style="F")    # spray


def _i_key(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    ringx = cx - r * 0.42
    pdf.circle(ringx, cy, r * 0.36, style="D")
    pdf.circle(ringx, cy, r * 0.15, style="D")                      # bow hole
    pdf.line(ringx + r * 0.36, cy, cx + r * 0.78, cy)              # shaft
    pdf.line(cx + r * 0.48, cy, cx + r * 0.48, cy + r * 0.24)      # tooth
    pdf.line(cx + r * 0.68, cy, cx + r * 0.68, cy + r * 0.32)      # tooth


def _i_clock(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    rr = r * 0.82
    pdf.circle(cx, cy, rr, style="D")
    for a in (0, 90, 180, 270):
        rad = math.radians(a)
        pdf.line(cx + math.cos(rad) * rr * 0.82,
                 cy + math.sin(rad) * rr * 0.82,
                 cx + math.cos(rad) * rr * 0.96,
                 cy + math.sin(rad) * rr * 0.96)                    # ticks
    pdf.line(cx, cy, cx, cy - rr * 0.6)                            # minute hand
    pdf.line(cx, cy, cx + rr * 0.42, cy + rr * 0.16)              # hour hand
    pdf.set_fill_color(*mark_c)
    pdf.circle(cx, cy, r * 0.07, style="F")


class HomeMotif(_IconMotif):
    name = "home_management"
    ICONS = (_i_house, _i_plant, _i_broom, _i_spraybottle, _i_key, _i_clock)


# ===========================================================================
# Small-business line-icons (briefcase / growth-chart / lightbulb / laptop /
# rocket / pie-chart) -- reuses :func:`_i_bulb`.
# ===========================================================================

def _i_briefcase(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    bw, bh = r * 1.5, r * 1.04
    top = cy - r * 0.14
    pdf.rect(cx - bw / 2, top, bw, bh, style="D", round_corners=True,
             corner_radius=r * 0.12)
    hw, hh = r * 0.28, r * 0.24
    pdf.arc(cx - hw, top - hh, hw * 2, 180, 360, b=hh * 2, style="D")  # handle
    pdf.line(cx - bw / 2, cy + r * 0.14, cx + bw / 2, cy + r * 0.14)   # seam
    pdf.rect(cx - r * 0.1, cy + r * 0.05, r * 0.2, r * 0.18, style="D")  # clasp


def _i_growth(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    # L-axes
    pdf.line(cx - r * 0.72, cy - r * 0.7, cx - r * 0.72, cy + r * 0.6)
    pdf.line(cx - r * 0.72, cy + r * 0.6, cx + r * 0.78, cy + r * 0.6)
    # rising trend line + arrowhead
    pts = [(cx - r * 0.5, cy + r * 0.28), (cx - r * 0.12, cy - r * 0.1),
           (cx + r * 0.18, cy + r * 0.06), (cx + r * 0.6, cy - r * 0.5)]
    pdf.polyline(pts, style="D")
    ex, ey = pts[-1]
    pdf.line(ex, ey, ex - r * 0.34, ey + r * 0.06)
    pdf.line(ex, ey, ex - r * 0.06, ey + r * 0.34)


def _i_laptop(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    sw, sh = r * 1.1, r * 0.66
    stop = cy - r * 0.5
    pdf.rect(cx - sw / 2, stop, sw, sh, style="D", round_corners=True,
             corner_radius=r * 0.06)                              # screen
    pdf.rect(cx - sw / 2 + r * 0.1, stop + r * 0.1, sw - r * 0.2, sh - r * 0.2,
             style="D")                                           # inner glass
    pdf.polygon([(cx - r * 0.78, cy + r * 0.34), (cx + r * 0.78, cy + r * 0.34),
                 (cx + r * 0.58, cy + r * 0.16),
                 (cx - r * 0.58, cy + r * 0.16)], style="D")      # base
    pdf.line(cx - r * 0.14, cy + r * 0.25, cx + r * 0.14, cy + r * 0.25)  # pad


def _i_rocket(pdf, cx, cy, r, line_c, mark_c, lw):
    _pen(pdf, line_c, lw)
    bw = r * 0.6
    btop, bbot = cy - r * 0.34, cy + r * 0.5
    pdf.polygon([(cx, cy - r * 0.86), (cx - bw / 2, btop),
                 (cx + bw / 2, btop)], style="D")                 # nose cone
    pdf.rect(cx - bw / 2, btop, bw, bbot - btop, style="D")       # body
    for sx in (-1, 1):
        ex = cx + sx * bw / 2
        pdf.polygon([(ex, cy + r * 0.14), (ex + sx * r * 0.3, cy + r * 0.62),
                     (ex, cy + r * 0.5)], style="D")              # fins
    pdf.circle(cx, cy - r * 0.02, r * 0.15, style="D")           # window
    _pen(pdf, mark_c, lw)
    for fx in (-0.16, 0.0, 0.16):
        pdf.line(cx + fx * r, bbot, cx + fx * r * 0.5, cy + r * 0.78)  # exhaust


def _i_piechart(pdf, cx, cy, r, line_c, mark_c, lw):
    rr = r * 0.8
    pdf.set_fill_color(*mark_c)
    pdf.solid_arc(cx - rr, cy - rr, rr * 2, 300, 360, style="F")  # highlighted slice
    _pen(pdf, line_c, lw)
    pdf.circle(cx, cy, rr, style="D")
    for a in (300, 360):
        rad = math.radians(a)
        pdf.line(cx, cy, cx + math.cos(rad) * rr, cy + math.sin(rad) * rr)


class BusinessMotif(_IconMotif):
    name = "small_business"
    ICONS = (_i_briefcase, _i_growth, _i_bulb, _i_laptop, _i_rocket,
             _i_piechart)


MOTIFS: dict[str, MotifFamily] = {
    "botanical": BotanicalMotif(),
    "geometric": GeometricMotif(),
    "celestial": CelestialMotif(),
    "coastal": CoastalMotif(),
    "minimal": MinimalMotif(),
    "fitness": FitnessMotif(),
    "academic": AcademicMotif(),
    "finance": FinanceMotif(),
    "teaching": TeachingMotif(),
    "focus": FocusMotif(),
    "travel": TravelMotif(),
    "wedding": WeddingMotif(),
    "meal_recipe": MealMotif(),
    "self_care": SelfCareMotif(),
    "home_management": HomeMotif(),
    "small_business": BusinessMotif(),
}

# The container-style token per motif lives in ``styles.CONTAINERS`` (consumed
# by the widgets).  The five themed line-icon families use the crisp
# ``squared_hairline`` container.  This module owns its motif vocabulary, so it
# registers the tokens here (idempotent) rather than editing styles.py.
for _themed in ("fitness", "academic", "finance", "teaching", "focus",
                "travel", "wedding", "meal_recipe", "self_care",
                "home_management", "small_business"):
    CONTAINERS.setdefault(_themed, "squared_hairline")
