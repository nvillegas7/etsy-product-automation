"""BOHO + PASTEL lanes: new palettes, presets, and the ground-legibility
flags added alongside them.

These guard the two intents that motivated the lanes:
  * pastel palettes must keep their labels on a DARK ink (never wash out);
  * a dark-ground palette (``is_dark``) must render its ground raw on every
    shell, not blended 65% toward white.
Existing light palettes must be byte-for-byte unchanged (the golden test
covers classic; here we assert the flag defaults leave the old maths intact).
"""

from __future__ import annotations

from dataclasses import replace

from fpdf import FPDF

from src.planner.designs import PRESET_PALETTES, PRESETS, get_design
from src.planner.styles import (
    INKS,
    ColorPalette,
    Theme,
    WHITE,
    blend,
    build_theme,
    get_palette,
    get_palettes,
)

NEW_PRESETS = ["terracotta", "wildflower", "lavender", "confetti", "blush"]
BOHO_PALETTES = ["terracotta_clay", "sage_linen", "dusty_adobe"]
PASTEL_PALETTES = ["lavender_haze", "mint_cream", "blush_butter"]
NEW_PALETTES = BOHO_PALETTES + PASTEL_PALETTES + ["patina_blue"]


def _luma(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b


class TestNewPalettes:
    def test_palettes_load(self):
        pals = get_palettes()
        for name in NEW_PALETTES:
            assert name in pals, name

    def test_pastels_flagged_and_boho_are_not(self):
        for name in PASTEL_PALETTES:
            assert get_palette(name).is_pastel is True, name
        for name in BOHO_PALETTES:
            assert get_palette(name).is_pastel is False, name

    def test_grounds_are_never_pure_white(self):
        # Boho + pastel grounds are warm/tinted off-white, never #FFFFFF.
        for name in NEW_PALETTES:
            assert get_palette(name).background.upper() != "#FFFFFF", name

    def test_text_ink_is_dark_enough_to_read(self):
        # Every new palette pins body/label text to a genuinely dark ink.
        for name in NEW_PALETTES:
            assert _luma(get_palette(name).rgb("text")) < 110, name


class TestNewPresets:
    def test_presets_registered_and_legal(self):
        for name in NEW_PRESETS:
            assert name in PRESETS
            d = get_design(name)
            assert d.name == name  # validates unchanged (no fallback rename)

    def test_recommended_palettes_are_curated(self):
        for name in NEW_PRESETS:
            names = PRESET_PALETTES[name]
            assert len(names) >= 4, f"{name} needs >=4 recommended palettes"
            assert len(set(names)) == len(names), f"{name} has dupes"


class TestLegibilityFlags:
    def _theme(self, palette: ColorPalette, shell: str = "binder") -> Theme:
        pdf = FPDF(unit="mm", format=(482.0, 361.2))
        pdf.set_auto_page_break(auto=False)
        pdf.set_margin(0)
        base = build_theme(pdf, "neutral_beige")
        design = get_design("classic", {"shell": shell})
        return replace(base, palette=palette, design=design,
                       ink=INKS[design.ink])

    def test_pastel_labels_stay_darker_than_classic_mix(self):
        # A pale primary must not lift the label off the dark floor: the
        # pastel mix leans far closer to `text` than the classic 0.3 mix.
        pastel = get_palette("lavender_haze")
        t = self._theme(pastel)
        pastel_label = t.label_c()
        classic_mix = blend(pastel.rgb("text"), pastel.rgb("primary"), 0.3)
        assert _luma(pastel_label) <= _luma(classic_mix)
        assert _luma(pastel_label) < 130  # comfortably dark on a pale ground

    def test_light_palette_label_math_unchanged(self):
        # Non-pastel palettes keep the historical 0.3 text/primary mix.
        pal = get_palette("neutral_beige")
        t = self._theme(pal)
        assert t.label_c() == blend(pal.rgb("text"), pal.rgb("primary"), 0.3)

    def test_dark_ground_returns_raw_plate_on_binder(self):
        # A synthetic dark palette must NOT be blended toward white on the
        # binder shell (that would grey the plate out); poster already did.
        dark = ColorPalette(
            name="synthetic_dark", background="#1C2A4A", primary="#F0EBD8",
            secondary="#6E7B9C", accent="#C9A84C", text="#F0EBD8",
            text_light="#A8B0C4", grid_line="#33405E", tab_active="#C9A84C",
            tab_inactive="#33405E", is_dark=True,
        )
        t = self._theme(dark, shell="binder")
        assert t.paper_c() == dark.rgb("background")

    def test_light_palette_paper_still_lifts_toward_white(self):
        pal = get_palette("neutral_beige")
        t = self._theme(pal, shell="binder")
        assert t.paper_c() == blend(pal.rgb("background"), WHITE, 0.65)
