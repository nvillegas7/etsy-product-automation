"""Design-parameter registry for the planner: 6 dimensions + texture token.

A :class:`DesignTheme` is a frozen bundle of one variant per dimension:

=========  =============================================================
shell      page architecture with its nav system fused in
interior   weekly + monthly body structure (paired)
motif      ornament family incl. container treatment
voice      typographic role system incl. its per-role sizes
ink        palette architecture (how color is deployed)
cover      cover composition
texture    free-writing-area fill (minor token)
=========  =============================================================

The registry is code (not yaml) because every variant is backed by code:
renderers, geometry builders, type tables.  The pipeline selects a preset
by **id string** (:data:`PRESETS`) and may override single dimensions;
:func:`validate_design` silently repairs illegal combinations (it never
raises) so a bad pick can never break a build.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, fields, replace
from typing import Literal

logger = logging.getLogger(__name__)

Shell = Literal["binder", "cards", "flat", "poster"]
Interior = Literal["boxed", "columns", "hourly", "airy"]
Motif = Literal["botanical", "geometric", "celestial", "coastal", "minimal"]
Voice = Literal["classic", "serif", "grotesk", "script", "typewriter"]
Ink = Literal["soft-wash", "ink-on-paper", "filled-blocks", "accent-pop"]
Cover = Literal["arch", "band", "editorial", "pattern"]
Texture = Literal["dot", "ruled", "graph", "blank"]

#: dimension name -> allowed values (dashboard dropdowns read this)
DIMENSIONS: dict[str, tuple[str, ...]] = {
    "shell": ("binder", "cards", "flat", "poster"),
    "interior": ("boxed", "columns", "hourly", "airy"),
    "motif": ("botanical", "geometric", "celestial", "coastal", "minimal"),
    "voice": ("classic", "serif", "grotesk", "script", "typewriter"),
    "ink": ("soft-wash", "ink-on-paper", "filled-blocks", "accent-pop"),
    "cover": ("arch", "band", "editorial", "pattern"),
    "texture": ("dot", "ruled", "graph", "blank"),
}


@dataclass(frozen=True)
class DesignTheme:
    """One resolved design: a name + one variant per dimension.

    ``DesignTheme()`` with all defaults **is** the classic design and
    renders exactly today's planner.
    """

    name: str = "classic"
    shell: Shell = "binder"
    interior: Interior = "boxed"
    motif: Motif = "botanical"
    voice: Voice = "classic"
    ink: Ink = "soft-wash"
    cover: Cover = "arch"
    texture: Texture = "dot"

    def dims(self) -> dict[str, str]:
        """All dimension values (everything except ``name``)."""
        return {f.name: getattr(self, f.name)
                for f in fields(self) if f.name != "name"}


# ---------------------------------------------------------------------------
# Curated presets
# ---------------------------------------------------------------------------

def _p(name: str, shell: str, interior: str, motif: str, voice: str,
       ink: str, cover: str, texture: str) -> DesignTheme:
    return DesignTheme(name=name, shell=shell, interior=interior, motif=motif,
                       voice=voice, ink=ink, cover=cover, texture=texture)


PRESETS: dict[str, DesignTheme] = {
    "classic":   _p("classic",   "binder", "boxed",   "botanical", "classic",    "soft-wash",     "arch",      "dot"),
    "meadow":    _p("meadow",    "binder", "columns", "botanical", "script",     "soft-wash",     "arch",      "ruled"),
    "midnight":  _p("midnight",  "binder", "hourly",  "celestial", "serif",      "soft-wash",     "pattern",   "blank"),
    "almanac":   _p("almanac",   "binder", "boxed",   "celestial", "typewriter", "ink-on-paper",  "editorial", "ruled"),
    "atelier":   _p("atelier",   "cards",  "boxed",   "coastal",   "serif",      "soft-wash",     "pattern",   "dot"),
    "riviera":   _p("riviera",   "cards",  "columns", "coastal",   "script",     "soft-wash",     "band",      "ruled"),
    "sorbet":    _p("sorbet",    "cards",  "airy",    "coastal",   "serif",      "accent-pop",    "pattern",   "dot"),
    "studio":    _p("studio",    "flat",   "columns", "minimal",   "grotesk",    "accent-pop",    "editorial", "graph"),
    "ledger":    _p("ledger",    "flat",   "boxed",   "geometric", "typewriter", "ink-on-paper",  "band",      "graph"),
    "blueprint": _p("blueprint", "flat",   "hourly",  "geometric", "grotesk",    "accent-pop",    "band",      "graph"),
    "gallery":   _p("gallery",   "poster", "airy",    "minimal",   "serif",      "ink-on-paper",  "editorial", "dot"),
    "noir":      _p("noir",      "poster", "boxed",   "geometric", "grotesk",    "filled-blocks", "band",      "blank"),
    # --- BOHO lane (earthy botanical, warm; boho arch/wildflower pattern) ---
    "terracotta": _p("terracotta", "binder", "boxed",   "botanical", "serif",   "soft-wash",   "pattern", "dot"),
    "wildflower": _p("wildflower", "binder", "columns", "botanical", "script",  "soft-wash",   "band",    "ruled"),
    # --- PASTEL lane (soft tonal, legible; is_pastel palettes keep ink dark) -
    "lavender":   _p("lavender",   "cards",  "airy",    "botanical", "serif",   "accent-pop",  "pattern", "dot"),
    "confetti":   _p("confetti",   "cards",  "boxed",   "geometric", "grotesk", "soft-wash",   "pattern", "dot"),
    "blush":      _p("blush",      "cards",  "boxed",   "botanical", "serif",   "ink-on-paper","band",    "ruled"),
}

# ---------------------------------------------------------------------------
# Cover-composition variance (D6 sub-structures)
# ---------------------------------------------------------------------------
# A cover id alone does not pin the whole composition: so that any two
# PRESET covers read as different products at thumbnail size (hue alone
# never counts), each cover family varies its structure on a second design
# dimension, and every family renders motif artwork.  The renderers in
# ``pages.py`` implement this mapping:
#
#   band       structure keyed on INK (palette architecture = how the solid
#              band is deployed).  The four band presets carry four
#              different inks, giving four visibly different structures:
#                soft-wash     (riviera)   wide left band; motif pattern
#                                          field on the open panel; no
#                                          ghost numeral; niche tab right
#                ink-on-paper  (ledger)    slim top band with reversed
#                                          title; motif strips + pattern
#                                          block on paper; no ghost numeral
#                accent-pop    (blueprint) thin accent spine; ghost numeral
#                                          top-right; ink title mid-left
#                                          (inverse of the editorial
#                                          masthead); motif strip bottom
#                filled-blocks (noir)      full-bleed solid plate; giant
#                                          centered ghost numeral; reversed
#                                          title; motif corner ornaments
#   arch       composition keyed on VOICE: the classic voice keeps the
#              golden double-rectangle frame + rounded title card + hero
#              artwork verbatim (classic); every other voice renders the
#              'meadow horizon' instead -- staggered motif field growing
#              from a rolling ground band, open sky, high centered title,
#              no frame / corner ornaments / bottom badge (meadow).
#   pattern    pattern USAGE keyed on INK: accent-pop crops an oversized
#              (2.6x) pattern to a bottom wave band and floats a bordered
#              title card in the open field above (sorbet); all other
#              inks keep the full-bleed pattern + full-width translucent
#              title band (midnight, atelier -- whose motif pattern art
#              differs: starfield vs scallops).
#   editorial  masthead keyed on VOICE: typewriter keeps the asymmetric
#              left-flush masthead with the ghost year (almanac, which is
#              further set apart by its celestial motif strip/divider);
#              grotesk renders a swiss poster -- lower-third full-width
#              masthead between thick rule blocks, corner accent plate,
#              no ghost numeral (studio); serif/classic/script center a
#              classical masthead between top and base rules (gallery).
#
# The constraint validator stays consistent with this mapping: the band
# dispatch is total over the four inks, and the existing voice rules
# (script never reversed in solid bands, typewriter never on
# filled-blocks) already exclude the illegible combinations from the
# reversed band structures.

#: preset id -> recommended palette names (advisory, for the pipeline)
PRESET_PALETTES: dict[str, tuple[str, ...]] = {
    "classic": ("neutral_beige", "soft_sage", "dusty_rose", "ocean_blue",
                "charcoal_minimal", "boho_pink", "classic_boho",
                "modern_minimal", "terracotta_clay", "sage_linen"),
    "meadow": ("soft_sage", "classic_boho", "sage_linen", "terracotta_clay"),
    "midnight": ("ocean_blue", "charcoal_minimal"),
    "almanac": ("neutral_beige", "charcoal_minimal"),
    "atelier": ("dusty_rose", "neutral_beige"),
    "riviera": ("ocean_blue", "boho_pink"),
    "sorbet": ("boho_pink", "dusty_rose"),
    "studio": ("modern_minimal", "charcoal_minimal"),
    "ledger": ("neutral_beige", "charcoal_minimal"),
    "blueprint": ("ocean_blue", "charcoal_minimal"),
    "gallery": ("modern_minimal", "neutral_beige"),
    "noir": ("modern_minimal", "charcoal_minimal"),
    "terracotta": ("terracotta_clay", "dusty_adobe", "classic_boho",
                   "sage_linen"),
    "wildflower": ("sage_linen", "terracotta_clay", "classic_boho",
                   "soft_sage"),
    "lavender": ("lavender_haze", "mint_cream", "blush_butter", "patina_blue"),
    "confetti": ("blush_butter", "mint_cream", "lavender_haze", "dusty_rose"),
    "blush": ("blush_butter", "dusty_adobe", "dusty_rose", "patina_blue"),
}


# ---------------------------------------------------------------------------
# Constraint matrix (hard rules + automatic fallbacks), applied IN ORDER
# ---------------------------------------------------------------------------

# (predicate-fields, fallback-field, fallback-value, reason)
_RULES: list[tuple[dict[str, str], str, str, str]] = [
    ({"voice": "script", "shell": "poster"}, "voice", "serif",
     "script titles are illegible in poster's plain header"),
    ({"voice": "script", "ink": "filled-blocks"}, "ink", "soft-wash",
     "script reversed in solid bands is illegible"),
    ({"voice": "typewriter", "ink": "filled-blocks"}, "ink", "ink-on-paper",
     "reversed Courier in solid bands muddies"),
    ({"cover": "pattern", "motif": "minimal"}, "cover", "editorial",
     "minimal has no pattern vocabulary"),
    ({"interior": "airy", "ink": "filled-blocks"}, "ink", "soft-wash",
     "solid bands contradict the borderless interior"),
    ({"motif": "minimal", "texture": "blank"}, "texture", "ruled",
     "open-air boxes with no texture become invisible"),
    ({"interior": "airy", "texture": "blank"}, "texture", "ruled",
     "ledger weekly needs visible structure"),
    ({"motif": "celestial", "texture": "graph"}, "texture", "dot",
     "constellation band + graph = noise"),
]


def resolve_design(d: DesignTheme) -> tuple[DesignTheme, list[str]]:
    """Apply the constraint matrix; return (legal theme, substitution notes)."""
    subs: list[str] = []

    # Unknown dimension values (e.g. typo'd overrides) fall back to classic.
    repairs: dict[str, str] = {}
    for dim, allowed in DIMENSIONS.items():
        value = getattr(d, dim)
        if value not in allowed:
            fallback = getattr(DesignTheme(), dim)
            repairs[dim] = fallback
            subs.append(f"{dim}='{value}' is unknown -> '{fallback}'")
    if repairs:
        d = replace(d, **repairs)

    for predicate, fb_field, fb_value, reason in _RULES:
        if all(getattr(d, k) == v for k, v in predicate.items()):
            combo = " x ".join(f"{k}={v}" for k, v in predicate.items())
            subs.append(f"{combo}: {reason} -> {fb_field}='{fb_value}'")
            d = replace(d, **{fb_field: fb_value})
    return d, subs


def validate_design(d: DesignTheme) -> DesignTheme:
    """Apply the fallback rules in order, logging each substitution.

    Never raises (pipeline robustness); always returns a legal DesignTheme.
    """
    legal, subs = resolve_design(d)
    for note in subs:
        logger.info("design '%s': %s", d.name, note)
    return legal


def get_design(preset: str = "classic",
               overrides: dict[str, str] | None = None) -> DesignTheme:
    """Resolve *preset* + per-dimension *overrides*, then validate.

    Unknown presets fall back to classic; unknown override keys/values are
    repaired.  A combination that no longer matches its preset is renamed
    ``custom-{shell}-{interior}-{motif}-{voice}-{ink}-{cover}``.
    """
    base = PRESETS.get(preset)
    if base is None:
        logger.warning("Unknown design preset '%s' -- using classic", preset)
        base = PRESETS["classic"]

    d = base
    if overrides:
        clean = {}
        for key, value in overrides.items():
            if key not in DIMENSIONS:
                logger.warning("Unknown design dimension '%s' -- ignored", key)
                continue
            clean[key] = value
        if clean:
            d = replace(d, **clean)

    d = validate_design(d)

    if d.dims() != base.dims():
        d = replace(d, name=(f"custom-{d.shell}-{d.interior}-{d.motif}"
                             f"-{d.voice}-{d.ink}-{d.cover}"))
    return d
