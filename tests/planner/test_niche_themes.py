"""Niche -> motif policy: a planner's motif must MATCH its niche.

These guard the intent behind :mod:`src.planner.niche_themes`:
  * a themed niche never keeps a mismatched thematic motif (flowers on a gym
    planner, waves on a budget planner, moons on a student planner);
  * the resolved motif is always themed-or-abstract for that niche;
  * an already-abstract preset (geometric/minimal) keeps its motif so the
    rotation retains variety;
  * a generic / unknown niche is left completely untouched.

The tests are robust to whether the themed motif *families* (academic,
fitness, ...) have been registered yet: they assert the invariants that hold
either way, and only assert the exact themed primary when that family is
actually available.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.planner.designs import DIMENSIONS, PRESETS, DesignTheme, get_design
from src.planner.motifs import MOTIFS
from src.planner.niche_themes import (
    MISMATCHED_THEMATIC_MOTIFS,
    NICHE_MOTIFS,
    resolve_niche_motif,
)

THEMED_NICHES = [
    "student_planner",
    "fitness_planner",
    "budget_planner",
    "teacher_planner",
    "adhd_planner",
]

# The concrete off-topic thematic motifs that must never survive on a niche.
MISMATCHED = ["botanical", "coastal", "celestial"]

# Abstract motifs: acceptable for ANY niche, so they must be kept as-is.
ABSTRACT = ["geometric", "minimal"]


def _registered(motif: str) -> bool:
    return motif in MOTIFS and motif in set(DIMENSIONS.get("motif", ()))


class TestPolicyShape:
    def test_every_themed_niche_has_a_policy(self):
        for niche in THEMED_NICHES:
            assert niche in NICHE_MOTIFS, niche

    def test_policy_is_themed_primary_then_abstract_fallbacks(self):
        # First entry themed; tail is abstract (safe on any niche).
        for niche, allowed in NICHE_MOTIFS.items():
            assert len(allowed) >= 2, niche
            assert allowed[0] not in MISMATCHED_THEMATIC_MOTIFS, niche
            assert allowed[1:] == ("geometric", "minimal"), niche

    def test_mismatched_set_is_the_concrete_thematic_motifs(self):
        assert MISMATCHED_THEMATIC_MOTIFS == frozenset(MISMATCHED)


class TestNeverMismatched:
    @pytest.mark.parametrize("niche", THEMED_NICHES)
    @pytest.mark.parametrize("bad_motif", MISMATCHED)
    def test_mismatched_thematic_motif_is_always_replaced(self, niche, bad_motif):
        design = replace(DesignTheme(), motif=bad_motif)
        out = resolve_niche_motif(design, niche)
        assert out.motif not in MISMATCHED_THEMATIC_MOTIFS, (
            f"{niche}: {bad_motif} survived as {out.motif}"
        )
        assert out.motif in NICHE_MOTIFS[niche]

    @pytest.mark.parametrize("niche", THEMED_NICHES)
    @pytest.mark.parametrize(
        "start_motif", MISMATCHED + ABSTRACT
    )
    def test_result_is_always_themed_or_abstract(self, niche, start_motif):
        design = replace(DesignTheme(), motif=start_motif)
        out = resolve_niche_motif(design, niche)
        assert out.motif in NICHE_MOTIFS[niche]

    @pytest.mark.parametrize("niche", THEMED_NICHES)
    def test_resolved_motif_is_always_renderable(self, niche):
        # Whatever we resolve to must be a registered motif family so the
        # generator's MOTIFS[design.motif] lookup can never KeyError.
        for bad in MISMATCHED:
            out = resolve_niche_motif(replace(DesignTheme(), motif=bad), niche)
            assert out.motif in MOTIFS, out.motif


class TestKeepAbstract:
    @pytest.mark.parametrize("niche", THEMED_NICHES)
    @pytest.mark.parametrize("abstract_motif", ABSTRACT)
    def test_already_abstract_motif_is_kept(self, niche, abstract_motif):
        design = replace(DesignTheme(), motif=abstract_motif)
        out = resolve_niche_motif(design, niche)
        assert out.motif == abstract_motif, (
            f"{niche}: abstract {abstract_motif} should be preserved, "
            f"got {out.motif}"
        )


class TestThemedBias:
    @pytest.mark.parametrize("niche", THEMED_NICHES)
    def test_swaps_to_themed_primary_when_registered(self, niche):
        primary = NICHE_MOTIFS[niche][0]
        if not _registered(primary):
            pytest.skip(f"themed family '{primary}' not registered yet")
        # A mismatched thematic motif must become the themed primary.
        out = resolve_niche_motif(replace(DesignTheme(), motif="botanical"), niche)
        assert out.motif == primary

    @pytest.mark.parametrize("niche", THEMED_NICHES)
    def test_already_themed_primary_is_kept(self, niche):
        primary = NICHE_MOTIFS[niche][0]
        if primary not in DIMENSIONS.get("motif", ()):
            pytest.skip(f"themed motif '{primary}' not a valid dimension yet")
        design = replace(DesignTheme(), motif=primary)
        out = resolve_niche_motif(design, niche)
        assert out.motif == primary

    @pytest.mark.parametrize("niche", THEMED_NICHES)
    def test_falls_back_to_abstract_when_themed_unavailable(self, niche):
        primary = NICHE_MOTIFS[niche][0]
        if _registered(primary):
            pytest.skip(f"themed family '{primary}' is registered")
        # Until the themed family lands, a mismatch must fall to geometric --
        # an abstract motif that is fine on any niche, never a mismatched one.
        out = resolve_niche_motif(replace(DesignTheme(), motif="coastal"), niche)
        assert out.motif == "geometric"


class TestGenericUnchanged:
    @pytest.mark.parametrize("slug", ["planner", "", "totally_unknown_slug"])
    def test_generic_or_unknown_slug_is_untouched(self, slug):
        design = replace(DesignTheme(), motif="botanical")
        out = resolve_niche_motif(design, slug)
        # Identity: no replace, no swap -- the design is returned as-is.
        assert out is design
        assert out.motif == "botanical"

    @pytest.mark.parametrize("slug", ["planner", "unknown"])
    def test_generic_slug_keeps_any_motif(self, slug):
        for motif in MISMATCHED + ABSTRACT:
            design = replace(DesignTheme(), motif=motif)
            out = resolve_niche_motif(design, slug)
            assert out.motif == motif


class TestDoesNotMutate:
    def test_input_design_is_never_mutated(self):
        design = replace(DesignTheme(), motif="botanical")
        before = design.motif
        resolve_niche_motif(design, "fitness_planner")
        assert design.motif == before  # frozen dataclass; replace() used


class TestRealPresetsAcrossNiches:
    """End-to-end over the real preset catalogue: no themed niche ever ends up
    with a flowers/waves/moons motif, whichever preset the rotation picks."""

    @pytest.mark.parametrize("niche", THEMED_NICHES)
    @pytest.mark.parametrize("preset", sorted(PRESETS))
    def test_no_preset_leaves_a_mismatch_on_a_themed_niche(self, niche, preset):
        design = get_design(preset)
        out = resolve_niche_motif(design, niche)
        assert out.motif not in MISMATCHED_THEMATIC_MOTIFS
        assert out.motif in NICHE_MOTIFS[niche]
