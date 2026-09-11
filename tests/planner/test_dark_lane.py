"""DARK-MODE lane (P4) + nocturne preset (P8).

The ``is_dark`` capability existed with zero palettes using it; these guard
the first three dark-ground palettes and the Gothmas preset that rides them.
"""

from __future__ import annotations

from fpdf import FPDF

from src.planner.designs import PRESET_PALETTES, PRESETS, get_design
from src.planner.styles import build_theme, get_palette, get_palettes

DARK_PALETTES = ["midnight_slate", "dark_rainbow", "gothic_plum"]


def _luma(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b


class TestDarkPalettes:
    def test_loaded_and_flagged(self):
        pals = get_palettes()
        for name in DARK_PALETTES:
            assert name in pals, name
            assert pals[name].is_dark is True, name
            assert pals[name].is_pastel is False, name

    def test_dark_plate_with_light_ink(self):
        for name in DARK_PALETTES:
            p = get_palette(name)
            assert _luma(p.rgb("background")) < 50, f"{name} ground not dark"
            assert _luma(p.rgb("text")) > 200, f"{name} ink not light"
            assert _luma(p.rgb("text_light")) > 120, name
            # Grid lines sit within the plate: visible but never a light
            # scaffold on a dark page.
            assert 30 < _luma(p.rgb("grid_line")) < 90, name

    def test_paper_is_raw_plate_on_every_shell(self):
        for name in DARK_PALETTES:
            for preset in ("classic", "studio", "nocturne", "gallery"):
                pdf = FPDF(unit="mm", format=(482.0, 361.2))
                theme = build_theme(pdf, name, get_design(preset))
                assert theme.paper_c() == get_palette(name).rgb("background")
                # labels stay light on the dark plate
                assert _luma(theme.label_c()) > 150, (name, preset)


class TestNocturne:
    def test_preset_registered_and_legal(self):
        assert "nocturne" in PRESETS
        d = get_design("nocturne")
        assert d.name == "nocturne"       # no constraint fallback renamed it
        assert d.motif == "celestial" and d.shell == "flat"

    def test_recommended_palettes_lead_with_gothic_plum(self):
        names = PRESET_PALETTES["nocturne"]
        assert names[0] == "gothic_plum"
        assert len(names) >= 4 and len(set(names)) == len(names)

    def test_dark_palettes_are_reachable_from_presets(self):
        """A palette only ships if some preset recommends it (bundle
        curation intersects niche preferences with PRESET_PALETTES)."""
        recommended = {p for names in PRESET_PALETTES.values() for p in names}
        for name in DARK_PALETTES:
            assert name in recommended, name


class TestDarkModeMerchandising:
    def test_feature_line_only_for_dark_bundles(self):
        import json

        from src.pipeline.orchestrator import PipelineOrchestrator
        from src.storage.models import Product

        dark = Product(title="t", palette_name="gothic_plum", year=2026,
                       price_usd=5.99,
                       params=json.dumps({"palettes": ["gothic_plum", "ocean_blue"]}))
        light = Product(title="t", palette_name="ocean_blue", year=2026,
                        price_usd=5.99,
                        params=json.dumps({"palettes": ["ocean_blue"]}))
        line = PipelineOrchestrator._dark_mode_feature_line(dark)
        assert line and "Dark Mode" in line and "Gothic Plum" in line
        assert PipelineOrchestrator._dark_mode_feature_line(light) is None
