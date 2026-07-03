"""Unit tests for the ZIP bundler and the curated palette-bundle selection.

These exercise the pure pieces (no PDF generation): the bundler util zips with
clean arcnames, and _curate_palettes picks 3-4 palettes hero-first.
"""

import zipfile

import pytest

from src.marketing.bundler import bundle_files
from src.pipeline.orchestrator import PipelineOrchestrator


# ---------------------------------------------------------------------------
# bundle_files
# ---------------------------------------------------------------------------


class TestBundleFiles:
    def test_zips_files_with_clean_arcnames(self, tmp_path):
        a = tmp_path / "a.pdf"
        b = tmp_path / "b.pdf"
        a.write_bytes(b"AAA")
        b.write_bytes(b"BBBB")
        out = tmp_path / "out" / "bundle.zip"

        result = bundle_files(
            [a, b],
            out,
            arcnames=["2026_Budget_Planner_ocean_blue.pdf", "2026_Budget_Planner_soft_sage.pdf"],
        )

        assert result == out
        assert out.exists()
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
        assert names == [
            "2026_Budget_Planner_ocean_blue.pdf",
            "2026_Budget_Planner_soft_sage.pdf",
        ]

    def test_creates_parent_dirs(self, tmp_path):
        a = tmp_path / "a.pdf"
        a.write_bytes(b"x")
        out = tmp_path / "deep" / "nested" / "b.zip"
        bundle_files([a], out)
        assert out.exists()

    def test_defaults_to_basename_when_no_arcnames(self, tmp_path):
        a = tmp_path / "sub" / "planner.pdf"
        a.parent.mkdir()
        a.write_bytes(b"x")
        out = tmp_path / "b.zip"
        bundle_files([a], out)
        with zipfile.ZipFile(out) as zf:
            assert zf.namelist() == ["planner.pdf"]

    def test_never_embeds_absolute_paths(self, tmp_path):
        a = tmp_path / "a.pdf"
        a.write_bytes(b"x")
        out = tmp_path / "b.zip"
        # Pass an absolute path as the desired arcname -- must be reduced.
        bundle_files([a], out, arcnames=[str(a.resolve())])
        with zipfile.ZipFile(out) as zf:
            for name in zf.namelist():
                assert not name.startswith("/")
                assert ":" not in name  # no drive letters
        with zipfile.ZipFile(out) as zf:
            assert zf.namelist() == ["a.pdf"]

    def test_empty_paths_raises(self, tmp_path):
        with pytest.raises(ValueError):
            bundle_files([], tmp_path / "b.zip")

    def test_mismatched_arcnames_raises(self, tmp_path):
        a = tmp_path / "a.pdf"
        a.write_bytes(b"x")
        with pytest.raises(ValueError):
            bundle_files([a], tmp_path / "b.zip", arcnames=["one.pdf", "two.pdf"])

    def test_missing_input_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            bundle_files([tmp_path / "nope.pdf"], tmp_path / "b.zip")


# ---------------------------------------------------------------------------
# _curate_palettes
# ---------------------------------------------------------------------------


class TestCuratePalettes:
    def test_intersection_first_then_design_recs(self):
        # design midnight recs vs budget niche prefs
        design = ["ocean_blue", "charcoal_minimal"]
        niche = ["ocean_blue", "modern_minimal", "charcoal_minimal"]
        allp = ["neutral_beige", "soft_sage", "dusty_rose", "ocean_blue",
                "charcoal_minimal", "boho_pink", "classic_boho", "modern_minimal"]
        bundle = PipelineOrchestrator._curate_palettes(design, niche, allp)
        # hero is a design-recommended palette
        assert bundle[0] in design
        # intersection (niche prefs the design recommends) leads, niche order
        assert bundle[:2] == ["ocean_blue", "charcoal_minimal"]
        assert 3 <= len(bundle) <= 4
        assert len(bundle) == len(set(bundle))  # de-duped

    def test_tops_up_to_minimum_from_all_palettes(self):
        design = ["ocean_blue", "charcoal_minimal"]  # only 2 recs
        niche = ["ocean_blue"]  # 1 intersects
        allp = ["neutral_beige", "soft_sage", "ocean_blue", "charcoal_minimal"]
        bundle = PipelineOrchestrator._curate_palettes(design, niche, allp)
        assert len(bundle) >= 3
        assert bundle[0] == "ocean_blue"

    def test_caps_at_maximum(self):
        design = ["a", "b", "c", "d", "e", "f"]
        niche = ["a", "b", "c", "d"]
        bundle = PipelineOrchestrator._curate_palettes(design, niche, design)
        assert len(bundle) == 4

    def test_no_design_uses_niche_order(self):
        niche = ["dusty_rose", "boho_pink"]
        allp = ["neutral_beige", "soft_sage", "dusty_rose", "boho_pink"]
        bundle = PipelineOrchestrator._curate_palettes([], niche, allp)
        assert bundle[0] == "dusty_rose"
        assert len(bundle) >= 3

    def test_hero_always_recommended_when_intersection_empty(self):
        design = ["ocean_blue", "charcoal_minimal"]
        niche = ["boho_pink"]  # no overlap with design
        allp = ["neutral_beige", "ocean_blue", "charcoal_minimal", "boho_pink"]
        bundle = PipelineOrchestrator._curate_palettes(design, niche, allp)
        assert bundle[0] in design
