"""Niche -> motif policy: make a planner's ornament MATCH its niche.

The design system picks a decorative :class:`~src.planner.designs.DesignTheme`
per product (preset rotation + palette bundle).  A preset carries a *motif*
family -- but a preset's motif is chosen for looks, not for niche fit, so a
botanical (flowers) preset could land on a *fitness* planner.  That reads as
a mismatch: a gym planner should show dumbbells, a student planner pencils.

This module holds the **policy** that repairs that mismatch at spec-build
time (never inside the generator's core render, so the classic golden path
stays byte-identical).  :func:`resolve_niche_motif` takes a resolved design
+ a niche slug and returns a design whose motif fits the niche:

* Themed niches (student/fitness/budget/teacher/adhd) get a themed primary
  motif (academic/fitness/finance/teaching/focus) with abstract fallbacks
  (geometric, minimal) that read fine on ANY niche.
* If the design's motif is already in the niche's allowed list it is KEPT --
  so an abstract preset (geometric/minimal) keeps its look and the catalogue
  retains variety; only a *mismatched thematic* motif (botanical/coastal/
  celestial) is replaced.
* Generic ("planner") and unknown slugs are returned UNCHANGED.

Robustness: a themed motif is only chosen when it is actually **registered**
(present in both the motif render registry and the design-dimension vocab).
Until the themed motif families land, a themed niche gracefully falls back to
the abstract ``geometric`` motif -- never to a mismatched flowers/waves motif.
"""

from __future__ import annotations

from dataclasses import replace

from src.planner.designs import DIMENSIONS, DesignTheme
from src.planner.motifs import MOTIFS

#: niche slug -> allowed motifs, themed primary first, abstract fallbacks after.
#: The first entry is the niche's *themed* motif; ``geometric``/``minimal`` are
#: abstract and acceptable for ANY niche, so they double as safe fallbacks and
#: as "keep me" values for already-abstract presets.
NICHE_MOTIFS: dict[str, tuple[str, ...]] = {
    "student_planner": ("academic", "geometric", "minimal"),
    "fitness_planner": ("fitness", "geometric", "minimal"),
    "budget_planner":  ("finance", "geometric", "minimal"),
    "teacher_planner": ("teaching", "geometric", "minimal"),
    "adhd_planner":    ("focus", "geometric", "minimal"),
    "travel":          ("travel", "geometric", "minimal"),
    "wedding":         ("wedding", "geometric", "minimal"),
    "meal_recipe":     ("meal_recipe", "geometric", "minimal"),
    "self_care":       ("self_care", "geometric", "minimal"),
    "home_management": ("home_management", "geometric", "minimal"),
    "small_business":  ("small_business", "geometric", "minimal"),
}

#: Thematic motifs that must NEVER survive on a themed niche (they carry a
#: concrete, off-topic subject: flowers / waves+shells / moons+stars).
MISMATCHED_THEMATIC_MOTIFS: frozenset[str] = frozenset(
    {"botanical", "coastal", "celestial"}
)


def _registered_motifs() -> set[str]:
    """Motif names that are safe to select: they render (present in the motif
    registry) AND validate (present in the design-dimension vocabulary), so an
    override can never be silently repaired away or raise at render time.

    Read live (not cached) so this tracks whatever motif families the design
    system currently exposes.
    """
    return set(MOTIFS) & set(DIMENSIONS.get("motif", ()))


def niche_motif_policy(niche_slug: str) -> tuple[str, ...] | None:
    """Return the allowed-motif tuple for *niche_slug*, or ``None`` if the
    slug has no themed policy (generic ``planner`` / unknown niches)."""
    return NICHE_MOTIFS.get(niche_slug)


def resolve_niche_motif(design: DesignTheme, niche_slug: str) -> DesignTheme:
    """Return *design* with a motif that MATCHES *niche_slug*.

    Policy:

    * No themed policy for the slug (generic ``planner`` / unknown) ->
      return the design UNCHANGED.
    * The design's motif is already in the niche's allowed list (its themed
      primary, or an abstract ``geometric``/``minimal``) -> KEEP it.
    * Otherwise (a mismatched thematic motif such as botanical/coastal/
      celestial) -> REPLACE it with the niche's themed primary, biasing toward
      the themed motif but only selecting one that is actually registered;
      fall through the abstract fallbacks (``geometric`` -> ``minimal``) if the
      themed family is not available yet.

    The swap uses :func:`dataclasses.replace` so the input design is never
    mutated.
    """
    allowed = NICHE_MOTIFS.get(niche_slug)
    if not allowed:
        # Generic / unknown niche: no opinion -- leave the design untouched.
        return design

    if design.motif in allowed:
        # Already themed-or-abstract for this niche: keep it (preserves the
        # abstract-preset variety the rotation gives us).
        return design

    registered = _registered_motifs()
    for motif in allowed:
        if motif in registered:
            return replace(design, motif=motif)

    # Nothing in the allowed list is registered (should never happen --
    # geometric/minimal are always present).  As an absolute last resort keep
    # the design rather than emit an unrenderable motif, but only if the
    # current motif is not a mismatched thematic one; otherwise fall back to
    # the abstract tail of the list.
    if design.motif in MISMATCHED_THEMATIC_MOTIFS:
        return replace(design, motif=allowed[-1])
    return design
