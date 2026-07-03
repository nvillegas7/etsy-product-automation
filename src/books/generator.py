"""Picture-book PDF generator: assembles cover, story, lesson, coloring
pages and back matter into a square 8.5 x 8.5 in PDF.

Usage
-----
    from src.books.generator import BookGenerator, BookSpec

    spec = BookSpec(title="Penny the Pear Learns to Share",
                    palette_name="sunny_day",
                    params={...})           # from pick_book_params()
    path = BookGenerator().generate(spec)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import structlog
from fpdf import FPDF

from src.books.characters import draw_character
from src.books.illustrator import (
    BookPalette,
    Draw,
    darken,
    draw_text_panel,
    get_book_palette,
    lighten,
    mix,
    sanitize_for_font,
    setup_book_fonts,
)
from src.books.scenes import PAGE_H, PAGE_W, SETTING_ZONES, draw_scene
from src.books.story import Story, StoryPage, build_story

logger = structlog.get_logger()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output" / "books"

# story-text sizes per age band (pt)
TEXT_SIZES = {"2-4": 26, "4-6": 22, "6-8": 20}

_DEFAULT_PARAMS = {
    "character_theme": "forest_animals",
    "character_key": "bunny",
    "character_name": "Bella",
    "setting": "park",
    "moral": "sharing",
    "age_band": "4-6",
    "narrative_style": "prose",
    "page_count": 12,
    "art_palette": "sunny_day",
    "seed": 7,
}


# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------


@dataclass
class BookSpec:
    """Specification for one picture-book PDF."""

    title: str
    subtitle: str = ""
    year: int = 2026
    palette_name: str = "sunny_day"
    params: dict = field(default_factory=dict)
    output_dir: str | Path | None = None


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class BookGenerator:
    """Generates a complete picture-book PDF from a :class:`BookSpec`."""

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def generate(self, spec: BookSpec) -> Path:
        """Build the book and write it to disk.  Returns the output path."""
        params = {**_DEFAULT_PARAMS, **(spec.params or {})}
        params.setdefault("display_title", spec.title)
        if spec.subtitle:
            params.setdefault("subtitle", spec.subtitle)

        palette = get_book_palette(spec.palette_name or params.get("art_palette", "sunny_day"))
        story = build_story(params)

        pdf = FPDF(unit="mm", format=(PAGE_W, PAGE_H))
        pdf.set_auto_page_break(auto=False)
        pdf.set_margin(0)
        pdf.set_title(spec.title)
        pdf.set_author("Little Lessons Books")
        pdf.set_creator("etsy-planner-bot / fpdf2")

        font = setup_book_fonts(pdf)
        text_size = TEXT_SIZES.get(params["age_band"], 22)

        self._render_cover(pdf, font, palette, story, params)
        self._render_title_page(pdf, font, palette, story)

        for i, page in enumerate(story.pages):
            self._render_story_page(pdf, font, palette, story, page, i, text_size)

        self._render_moral_page(pdf, font, palette, story)
        for i, (with_friend, with_mentor, pose) in enumerate(
            [(False, False, "stand"), (True, False, "arms_up"),
             (False, True, "stand"), (True, False, "wave")]
        ):
            self._render_coloring_page(pdf, font, story, i, with_friend, with_mentor, pose)
        self._render_end_page(pdf, font, palette, story)

        out_dir = Path(spec.output_dir) if spec.output_dir else DEFAULT_OUTPUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "_", spec.title.lower()).strip("_") or "book"
        out_path = out_dir / f"book_{spec.year}_{slug}_{palette.key}.pdf"
        pdf.output(str(out_path))

        logger.info(
            "book_generated",
            path=str(out_path),
            pages=pdf.pages_count,
            character=story.character_key,
            setting=story.setting,
            moral=story.moral,
            size_kb=round(out_path.stat().st_size / 1024, 1),
        )
        return out_path

    # ------------------------------------------------------------------
    # text helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _wrap_lines(pdf: FPDF, text: str, max_w: float) -> list[str]:
        """Greedy word wrap using the current font metrics."""
        lines: list[str] = []
        for raw in text.split("\n"):
            words = raw.split()
            cur = ""
            for w in words:
                trial = f"{cur} {w}".strip()
                if pdf.get_string_width(trial) <= max_w or not cur:
                    cur = trial
                else:
                    lines.append(cur)
                    cur = w
            if cur:
                lines.append(cur)
        return lines

    def _halo_title(
        self,
        pdf: FPDF,
        font: str,
        text: str,
        cx: float,
        y: float,
        size: float,
        color: tuple,
        halo: tuple = (255, 255, 255),
        max_w: float = PAGE_W - 30,
        line_gap: float = 1.12,
    ) -> float:
        """Centered bold title with a soft white halo.  Returns bottom y."""
        text = sanitize_for_font(text, font)
        pdf.set_font(font, "B", size)
        lines = self._wrap_lines(pdf, text, max_w)
        line_h = size * 0.3528 * line_gap
        yy = y
        for line in lines:
            lw = pdf.get_string_width(line)
            x = cx - lw / 2
            pdf.set_text_color(*halo)
            for dx, dy in ((-0.5, 0), (0.5, 0), (0, -0.5), (0, 0.5),
                           (-0.35, -0.35), (0.35, -0.35), (-0.35, 0.35), (0.35, 0.35)):
                pdf.text(x + dx, yy + dy, line)
            pdf.set_text_color(*color)
            pdf.text(x, yy, line)
            yy += line_h
        return yy

    @staticmethod
    def _center_text(
        pdf: FPDF, font: str, text: str, y: float, size: float,
        color: tuple, style: str = "", max_w: float = PAGE_W - 40,
    ) -> float:
        text = sanitize_for_font(text, font)
        pdf.set_font(font, style, size)
        pdf.set_text_color(*color)
        line_h = size * 0.3528 * 1.4
        lines = BookGenerator._wrap_lines(pdf, text, max_w)
        yy = y
        for line in lines:
            pdf.text(PAGE_W / 2 - pdf.get_string_width(line) / 2, yy, line)
            yy += line_h
        return yy

    # ------------------------------------------------------------------
    # pages
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # cover: five distinct shelf layouts, chosen by the book seed
    # ------------------------------------------------------------------

    def _render_cover(
        self, pdf: FPDF, font: str, pal: BookPalette, story: Story, params: dict
    ) -> None:
        pdf.add_page()
        seed = int(params.get("seed", 0) or 0)
        layouts = (
            self._cover_sunny_banner,
            self._cover_storybook_frame,
            self._cover_side_panel,
            self._cover_bottom_spotlight,
            self._cover_matted_postcard,
        )
        layouts[seed % len(layouts)](pdf, font, pal, story, seed)

    # -- cover building blocks -----------------------------------------

    def _cover_zones(self, story: Story) -> tuple[str, str, str]:
        """(home, away1, away2) sub-locations for staging cover backdrops."""
        zones = SETTING_ZONES.get(story.setting, ("",))
        home = zones[0] if zones else ""
        away1 = zones[1] if len(zones) > 1 else home
        away2 = zones[2] if len(zones) > 2 else away1
        return home, away1, away2

    def _title_panel_h(self, pdf: FPDF, font: str, title: str, size: float,
                       max_w: float) -> float:
        pdf.set_font(font, "B", size)
        n = len(self._wrap_lines(pdf, sanitize_for_font(title, font), max_w))
        return 9 + n * size * 0.3528 * 1.12 + 7

    def _titled_panel(self, pdf: FPDF, font: str, pal: BookPalette, title: str,
                      cx: float, top_y: float, size: float, max_w: float,
                      opacity: float = 0.58) -> float:
        """Soft white rounded panel sized to the title, with a haloed title.
        Returns the panel's bottom y."""
        panel_h = self._title_panel_h(pdf, font, title, size, max_w)
        panel_w = max_w + 24
        with pdf.local_context(fill_opacity=opacity):
            pdf.set_fill_color(255, 255, 255)
            pdf.rect(cx - panel_w / 2, top_y, panel_w, panel_h, style="F",
                     round_corners=True, corner_radius=8)
        self._halo_title(pdf, font, title, cx, top_y + 9 + size * 0.3528, size,
                         darken(pal.text, 0.1), max_w=max_w)
        return top_y + panel_h

    def _cover_ribbon(self, pdf: FPDF, font: str, pal: BookPalette, text: str,
                      cx: float, y: float, color: tuple | None = None) -> None:
        color = color or pal.accent
        pdf.set_font(font, "B", 15)
        rw = pdf.get_string_width(text) + 18
        pdf.set_fill_color(*color)
        pdf.rect(cx - rw / 2, y, rw, 12.5, style="F", round_corners=True, corner_radius=6)
        pdf.set_text_color(255, 255, 255)
        pdf.text(cx - pdf.get_string_width(text) / 2, y + 8.4, text)

    def _bonus_seal(self, pdf: FPDF, font: str, pal: BookPalette,
                    bx: float, by: float, br: float = 17) -> None:
        """Round 'medal' bonus badge with a thin ring."""
        pdf.set_fill_color(*pal.accent2)
        pdf.ellipse(bx - br, by - br, br * 2, br * 2, style="F")
        pdf.set_draw_color(255, 255, 255)
        pdf.set_line_width(1.1)
        pdf.ellipse(bx - br + 2.4, by - br + 2.4, (br - 2.4) * 2, (br - 2.4) * 2, style="D")
        pdf.set_font(font, "B", 9.5)
        pdf.set_text_color(255, 255, 255)
        for j, line in enumerate(("4 BONUS", "COLORING", "PAGES!")):
            pdf.text(bx - pdf.get_string_width(line) / 2, by - 3.5 + j * 4.4, line)

    def _bonus_star(self, pdf: FPDF, font: str, pal: BookPalette,
                    bx: float, by: float, br: float = 20) -> None:
        """Star-burst 'seal' bonus badge."""
        import math as _m
        d = Draw(pdf)
        spikes = 12
        pts = []
        for i in range(spikes * 2):
            ang = _m.radians(i * (180 / spikes) - 90)
            rr = br if i % 2 == 0 else br * 0.74
            pts.append((bx + rr * _m.cos(ang), by + rr * _m.sin(ang)))
        d.polygon(pts, fill=pal.accent2)
        d.circle(bx, by, br * 0.70, fill=lighten(pal.accent2, 0.12))
        pdf.set_font(font, "B", 9)
        pdf.set_text_color(255, 255, 255)
        for j, line in enumerate(("4 BONUS", "COLORING", "PAGES!")):
            pdf.text(bx - pdf.get_string_width(line) / 2, by - 3.2 + j * 4.2, line)

    def _bonus_pill(self, pdf: FPDF, font: str, pal: BookPalette,
                    cx: float, y: float) -> None:
        """Wide rounded banner spelling out the bonus selling point."""
        text = "4 BONUS COLORING PAGES!"
        pdf.set_font(font, "B", 12)
        w = pdf.get_string_width(text) + 18
        pdf.set_fill_color(*pal.accent2)
        pdf.rect(cx - w / 2, y, w, 12.5, style="F", round_corners=True, corner_radius=6.2)
        pdf.set_text_color(255, 255, 255)
        pdf.text(cx - pdf.get_string_width(text) / 2, y + 8.6, text)

    def _imprint(self, pdf: FPDF, font: str, pal: BookPalette,
                 y: float = PAGE_H - 6, color: tuple | None = None) -> None:
        pdf.set_font(font, "", 11)
        pdf.set_text_color(*(color or darken(pal.text, 0.05)))
        txt = "A Little Lessons Book"
        pdf.text(PAGE_W / 2 - pdf.get_string_width(txt) / 2, y, txt)

    # -- layout 0: sunny top banner (hero right, friend left) ----------

    def _cover_sunny_banner(self, pdf, font, pal, story, seed) -> None:
        draw_scene(pdf, story.setting, pal, variant=seed % 97, sparse=True,
                   shot="establish", horizon=PAGE_H * 0.64)
        draw_character(pdf, story.character_key, PAGE_W * 0.64, PAGE_H * 0.90, 98,
                       expression="excited", pose="wave", facing=-1)
        draw_character(pdf, story.friend_key, PAGE_W * 0.16, PAGE_H * 0.915, 58,
                       expression="happy", pose="stand", facing=1)
        self._titled_panel(pdf, font, pal, story.title, PAGE_W / 2, 12, 30, PAGE_W - 44)
        self._cover_ribbon(pdf, font, pal, f"A story about {story.moral}", PAGE_W / 2, 73)
        self._bonus_seal(pdf, font, pal, PAGE_W - 30, 96, 17)
        self._imprint(pdf, font, pal)

    # -- layout 1: framed storybook (center hero on a hill, star seal) --

    def _cover_storybook_frame(self, pdf, font, pal, story, seed) -> None:
        draw_scene(pdf, story.setting, pal, variant=seed % 97 + 11, sparse=True,
                   shot="hill", horizon=PAGE_H * 0.66)
        draw_character(pdf, story.character_key, PAGE_W * 0.53, PAGE_H * 0.90, 96,
                       expression="excited", pose="arms_up", facing=1)
        draw_character(pdf, story.friend_key, PAGE_W * 0.21, PAGE_H * 0.915, 58,
                       expression="happy", pose="wave", facing=1)
        d = Draw(pdf)
        d.rect(9, 9, PAGE_W - 18, PAGE_H - 18, stroke=pal.accent, lw=1.6, radius=11)
        d.rect(12.5, 12.5, PAGE_W - 25, PAGE_H - 25, stroke=pal.accent2, lw=0.7, radius=9)
        for cx, cy in ((9, 9), (PAGE_W - 9, 9), (9, PAGE_H - 9), (PAGE_W - 9, PAGE_H - 9)):
            d.circle(cx, cy, 4.5, fill=pal.accent2)
        self._titled_panel(pdf, font, pal, story.title, PAGE_W / 2, 18, 27, PAGE_W - 60)
        self._cover_ribbon(pdf, font, pal, f"A story about {story.moral}", PAGE_W / 2, 74)
        self._bonus_star(pdf, font, pal, PAGE_W - 33, PAGE_H - 33, 20)
        self._imprint(pdf, font, pal)

    # -- layout 2: magazine side panel (title stack left, hero right) ---

    def _cover_side_panel(self, pdf, font, pal, story, seed) -> None:
        _, away1, _ = self._cover_zones(story)
        draw_scene(pdf, story.setting, pal, variant=seed % 97 + 23, sparse=True,
                   shot="wide", zone=away1, time_of_day="sunset")
        draw_character(pdf, story.friend_key, PAGE_W * 0.53, PAGE_H * 0.915, 52,
                       expression="happy", pose="stand", facing=1)
        draw_character(pdf, story.character_key, PAGE_W * 0.77, PAGE_H * 0.90, 92,
                       expression="excited", pose="wave", facing=-1)
        pw = PAGE_W * 0.44
        with pdf.local_context(fill_opacity=0.90):
            pdf.set_fill_color(*lighten(pal.accent, 0.42))
            pdf.rect(0, 0, pw, PAGE_H, style="F")
        Draw(pdf).line(pw, 0, pw, PAGE_H, color=pal.accent, lw=1.6)
        cx = pw / 2

        def panel_lines(txt, y, size, style="", color=None, gap=1.28):
            pdf.set_font(font, style, size)
            pdf.set_text_color(*(color or pal.text))
            for line in self._wrap_lines(pdf, sanitize_for_font(txt, font), pw - 16):
                pdf.text(cx - pdf.get_string_width(line) / 2, y, line)
                y += size * 0.3528 * gap
            return y

        y = self._halo_title(pdf, font, story.title, cx, 52, 24,
                             darken(pal.text, 0.12), max_w=pw - 16)
        y = panel_lines(story.subtitle, y + 6, 12, color=pal.text)
        self._cover_ribbon(pdf, font, pal, f"about {story.moral}", cx, y + 8)
        self._bonus_seal(pdf, font, pal, cx, PAGE_H - 42, 18)
        self._imprint(pdf, font, pal, y=PAGE_H - 14, color=darken(pal.text, 0.1))

    # -- layout 3: bottom banner, hero leaping center-stage -------------

    def _cover_bottom_spotlight(self, pdf, font, pal, story, seed) -> None:
        _, away1, _ = self._cover_zones(story)
        draw_scene(pdf, story.setting, pal, variant=seed % 97 + 37, sparse=True,
                   shot="path", zone=away1, time_of_day="morning")
        draw_character(pdf, story.friend_key, PAGE_W * 0.19, PAGE_H * 0.80, 56,
                       expression="happy", pose="wave", facing=1)
        draw_character(pdf, story.character_key, PAGE_W * 0.50, PAGE_H * 0.74, 104,
                       expression="excited", pose="jump", facing=1)
        if story.mentor_key == "bee":
            draw_character(pdf, story.mentor_key, PAGE_W * 0.83, PAGE_H * 0.74, 40,
                           expression="happy", pose="stand", facing=-1)
        else:
            draw_character(pdf, story.mentor_key, PAGE_W * 0.83, PAGE_H * 0.80, 54,
                           expression="happy", pose="stand", facing=-1)
        ph = self._title_panel_h(pdf, font, story.title, 26, PAGE_W - 52)
        top = PAGE_H - ph - 11
        self._cover_ribbon(pdf, font, pal, f"A story about {story.moral}",
                           PAGE_W / 2, top - 16)
        self._titled_panel(pdf, font, pal, story.title, PAGE_W / 2, top, 26, PAGE_W - 52)
        self._bonus_seal(pdf, font, pal, 32, 32, 17)
        self._imprint(pdf, font, pal, y=13)

    # -- layout 4: matted postcard (thick colored frame holds the type) -

    def _cover_matted_postcard(self, pdf, font, pal, story, seed) -> None:
        home, _, _ = self._cover_zones(story)
        draw_scene(pdf, story.setting, pal, variant=seed % 97 + 53, sparse=True,
                   shot="corner", zone=home, horizon=PAGE_H * 0.62)
        draw_character(pdf, story.character_key, PAGE_W * 0.60, PAGE_H * 0.80, 88,
                       expression="happy", pose="wave", facing=-1)
        draw_character(pdf, story.friend_key, PAGE_W * 0.31, PAGE_H * 0.82, 56,
                       expression="excited", pose="stand", facing=1)
        mat = lighten(pal.accent2, 0.34)
        top_h, bot_h, side = 50, 34, 13
        pdf.set_fill_color(*mat)
        for x, y, w, h in ((0, 0, PAGE_W, top_h), (0, PAGE_H - bot_h, PAGE_W, bot_h),
                           (0, 0, side, PAGE_H), (PAGE_W - side, 0, side, PAGE_H)):
            pdf.rect(x, y, w, h, style="F")
        Draw(pdf).rect(side, top_h, PAGE_W - 2 * side, PAGE_H - top_h - bot_h,
                       stroke=pal.accent, lw=1.5, radius=8)
        self._halo_title(pdf, font, story.title, PAGE_W / 2, 23, 22,
                         darken(pal.text, 0.12), max_w=PAGE_W - 40)
        self._cover_ribbon(pdf, font, pal, f"A story about {story.moral}",
                           PAGE_W / 2, top_h + 6)
        self._bonus_pill(pdf, font, pal, PAGE_W / 2, PAGE_H - 24)

    def _render_title_page(self, pdf: FPDF, font: str, pal: BookPalette, story: Story) -> None:
        pdf.add_page()
        pdf.set_fill_color(*lighten(pal.sky_bottom, 0.35))
        pdf.rect(0, 0, PAGE_W, PAGE_H, style="F")
        d = Draw(pdf)
        # dotted border frame
        d.rect(10, 10, PAGE_W - 20, PAGE_H - 20, stroke=pal.accent, lw=0.9, radius=8)
        for cx, cy in ((10, 10), (PAGE_W - 10, 10), (10, PAGE_H - 10), (PAGE_W - 10, PAGE_H - 10)):
            d.circle(cx, cy, 4.5, fill=pal.accent2)

        y = self._center_text(pdf, font, story.title, 46, 27, darken(pal.text, 0.1), "B",
                              max_w=PAGE_W - 56)
        self._center_text(pdf, font, story.subtitle, y + 4, 14, pal.text)

        draw_character(pdf, story.character_key, PAGE_W / 2, 142, 62,
                       expression="happy", pose="stand", facing=1)

        self._center_text(pdf, font, "~ written for little dreamers ~", 158, 12, pal.text)
        self._center_text(pdf, font, "This book belongs to", 178, 15, darken(pal.text, 0.1), "B")
        d.line(PAGE_W / 2 - 42, 192, PAGE_W / 2 + 42, 192, color=pal.accent, lw=0.8)

    def _render_story_page(
        self,
        pdf: FPDF,
        font: str,
        pal: BookPalette,
        story: Story,
        page: StoryPage,
        index: int,
        text_size: float,
    ) -> None:
        pdf.add_page()
        variant = int(story.context.get("seed", 0) or 0) + index * 13 + 5
        panel_on_top = page.composition in ("center", "closeup")
        # Camera framing + sub-location travel per beat: page.shot sets the
        # horizon and foreground weight, page.zone walks the book through 2-3
        # related spots of one world (barn -> field -> pond) so no two spreads
        # look alike.  Close-ups get a lighter background so the big character
        # reads; wide/vista beats keep the full depth stack.
        draw_scene(pdf, story.setting, pal, time_of_day=page.time_of_day,
                   variant=variant, shot=page.shot, zone=page.zone,
                   background_cast=page.composition != "closeup",
                   sky_offset=52.0 if panel_on_top else 0.0)

        # -- characters ------------------------------------------------
        if page.composition == "closeup":
            draw_character(pdf, story.character_key, PAGE_W / 2, 232, 200,
                           expression=page.expression, pose=page.pose, facing=1)
        else:
            stand_y = PAGE_H * 0.72 if not panel_on_top else PAGE_H * 0.88
            positions = {"left": (PAGE_W * 0.30, 1), "right": (PAGE_W * 0.70, -1),
                         "center": (PAGE_W * 0.50, 1)}
            cx, facing = positions.get(page.composition, (PAGE_W * 0.5, 1))

            others = int(page.show_friend) + int(page.show_mentor)
            if others and page.composition == "center":
                cx = PAGE_W * (0.38 if others == 1 else 0.50)

            draw_character(pdf, story.character_key, cx, stand_y, 84,
                           expression=page.expression, pose=page.pose, facing=facing)

            side = -1 if cx > PAGE_W / 2 else 1
            slot_x = cx + side * PAGE_W * 0.30
            if page.show_friend:
                draw_character(pdf, story.friend_key, slot_x, stand_y, 66,
                               expression=page.friend_expression, pose="stand",
                               facing=-side)
                slot_x = cx - side * PAGE_W * 0.26 if page.show_mentor else slot_x
            if page.show_mentor:
                mx = slot_x if not page.show_friend else cx - side * PAGE_W * 0.26
                if story.mentor_key == "bee":
                    draw_character(pdf, story.mentor_key, mx, stand_y - 26, 42,
                                   expression="happy", pose="stand", facing=-side)
                else:
                    draw_character(pdf, story.mentor_key, mx, stand_y, 58,
                                   expression="happy", pose="stand", facing=-side)

        # -- text panel --------------------------------------------------
        panel_w = PAGE_W - 32
        if panel_on_top:
            draw_text_panel(pdf, font, page.text, 16, 12, panel_w, text_size, pal.text,
                            panel_color=pal.panel)
        else:
            # measure first, then bottom-anchor
            h = draw_text_panel(pdf, font, page.text, 16, 12, panel_w,
                                text_size, pal.text, measure_only=True)
            draw_text_panel(pdf, font, page.text, 16, PAGE_H - h - 9, panel_w,
                            text_size, pal.text, panel_color=pal.panel)

        # page number pebble
        pdf.set_font(font, "B", 10)
        pdf.set_fill_color(*pal.accent)
        num = str(index + 1)
        nx = PAGE_W - 14 if not panel_on_top else PAGE_W - 14
        ny = 14 if not panel_on_top else PAGE_H - 14
        pdf.ellipse(nx - 5, ny - 5, 10, 10, style="F")
        pdf.set_text_color(255, 255, 255)
        pdf.text(nx - pdf.get_string_width(num) / 2, ny + 1.3, num)

    def _render_moral_page(self, pdf: FPDF, font: str, pal: BookPalette, story: Story) -> None:
        pdf.add_page()
        pdf.set_fill_color(*lighten(pal.sky_bottom, 0.3))
        pdf.rect(0, 0, PAGE_W, PAGE_H, style="F")
        d = Draw(pdf)
        d.rect(13, 13, PAGE_W - 26, PAGE_H - 26, stroke=pal.accent, lw=1.1, radius=10)
        d.rect(16.5, 16.5, PAGE_W - 33, PAGE_H - 33, stroke=pal.accent2, lw=0.5, radius=8)
        # corner flowers
        for cx, cy in ((24, 24), (PAGE_W - 24, 24), (24, PAGE_H - 24), (PAGE_W - 24, PAGE_H - 24)):
            for k in range(5):
                import math as _m
                a = _m.radians(k * 72 - 90)
                d.circle(cx + 3.4 * _m.cos(a), cy + 3.4 * _m.sin(a), 2.2, fill=pal.accent2)
            d.circle(cx, cy, 2.0, fill=pal.sun)

        self._center_text(pdf, font, story.lesson_heading, 52, 25, darken(pal.accent, 0.25), "B")
        # divider hearts
        pdf.set_font(font, "", 13)
        pdf.set_text_color(*pal.accent2)
        div = "* * *"
        pdf.text(PAGE_W / 2 - pdf.get_string_width(div) / 2, 63, div)

        self._center_text(pdf, font, story.lesson_text, 84, 17, pal.text,
                          max_w=PAGE_W - 66)

        draw_character(pdf, story.character_key, PAGE_W / 2, 182, 58,
                       expression="happy", pose="arms_up", facing=1)
        self._center_text(pdf, font, f"~ {story.character_full_name} ~", 196, 12, pal.text)

    def _render_coloring_page(
        self, pdf: FPDF, font: str, story: Story, index: int,
        with_friend: bool, with_mentor: bool, pose: str,
    ) -> None:
        pdf.add_page()
        pdf.set_fill_color(255, 255, 255)
        pdf.rect(0, 0, PAGE_W, PAGE_H, style="F")

        pal = get_book_palette("sunny_day")  # colors unused in line-art mode
        draw_scene(pdf, story.setting, pal, line_art=True, variant=index * 31 + 3,
                   horizon=PAGE_H * 0.60)
        if with_friend:
            draw_character(pdf, story.character_key, PAGE_W * 0.36, PAGE_H * 0.78, 86,
                           expression="happy", pose=pose, line_art=True, facing=1)
            draw_character(pdf, story.friend_key, PAGE_W * 0.68, PAGE_H * 0.78, 70,
                           expression="happy", pose="stand", line_art=True, facing=-1)
        elif with_mentor:
            draw_character(pdf, story.character_key, PAGE_W * 0.36, PAGE_H * 0.78, 86,
                           expression="happy", pose=pose, line_art=True, facing=1)
            y_off = 26 if story.mentor_key == "bee" else 0
            draw_character(pdf, story.mentor_key, PAGE_W * 0.68, PAGE_H * 0.78 - y_off,
                           50 if story.mentor_key == "bee" else 64,
                           expression="happy", pose="stand", line_art=True, facing=-1)
        else:
            draw_character(pdf, story.character_key, PAGE_W * 0.5, PAGE_H * 0.80, 96,
                           expression="happy", pose=pose, line_art=True, facing=1)

        # mask overflow + frame + header
        pdf.set_fill_color(255, 255, 255)
        for x, y, w, h in ((0, 0, PAGE_W, 30), (0, PAGE_H - 8, PAGE_W, 8),
                           (0, 0, 8, PAGE_H), (PAGE_W - 8, 0, 8, PAGE_H)):
            pdf.rect(x, y, w, h, style="F")
        pdf.set_draw_color(30, 30, 30)
        pdf.set_line_width(0.7)
        pdf.rect(8, 30, PAGE_W - 16, PAGE_H - 38, style="D", round_corners=True,
                 corner_radius=6)
        pdf.set_font(font, "B", 24)
        pdf.set_text_color(30, 30, 30)
        header = "Color me!"
        pdf.text(PAGE_W / 2 - pdf.get_string_width(header) / 2, 20, header)
        pdf.set_font(font, "", 11)
        sub = f"Bonus coloring page {index + 1} of 4"
        pdf.text(PAGE_W / 2 - pdf.get_string_width(sub) / 2, 27, sub)

    def _render_end_page(self, pdf: FPDF, font: str, pal: BookPalette, story: Story) -> None:
        pdf.add_page()
        # soft gradient background
        n = 24
        for i in range(n):
            pdf.set_fill_color(*mix(lighten(pal.sky_top, 0.25), lighten(pal.sky_bottom, 0.4),
                                    i / (n - 1)))
            pdf.rect(0, i * PAGE_H / n - 0.2, PAGE_W, PAGE_H / n + 0.4, style="F")
        d = Draw(pdf)
        d.pdf.set_fill_color(*pal.ground)
        d.pdf.rect(0, PAGE_H * 0.82, PAGE_W, PAGE_H * 0.18, style="F")

        self._halo_title(pdf, font, "The End", PAGE_W / 2, 84, 42, darken(pal.text, 0.1))
        self._center_text(pdf, font, "Thank you for reading!", 102, 15, pal.text)

        draw_character(pdf, story.character_key, PAGE_W / 2, PAGE_H * 0.845, 74,
                       expression="happy", pose="wave", facing=1)
        self._center_text(
            pdf, font,
            f"Come back soon and visit {story.character_name} again.",
            PAGE_H - 12, 11, darken(pal.text, 0.05),
        )
