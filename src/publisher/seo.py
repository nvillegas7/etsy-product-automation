"""SEO optimization for Etsy listings — titles, descriptions, and tags."""

from __future__ import annotations

import re
from datetime import datetime

import structlog

logger = structlog.get_logger()

# Etsy limits
MAX_TITLE_LENGTH = 140
MAX_TAG_LENGTH = 20
REQUIRED_TAG_COUNT = 13


def _palette_display_name(name: str) -> str:
    """Human label for a palette key (e.g. 'ocean_blue' -> 'Ocean Blue')."""
    try:
        from src.planner.styles import get_palette

        return get_palette(name).name
    except Exception:
        return name.replace("_", " ").replace("-", " ").title()


def _distinct_palettes(palettes: list[str] | None) -> list[str]:
    """De-duplicated palette list, order preserved (hero first)."""
    if not palettes:
        return []
    ordered: list[str] = []
    for p in palettes:
        if p and p not in ordered:
            ordered.append(p)
    return ordered


class ListingSEO:
    """Generates SEO-optimized listing metadata for Etsy digital planners."""

    # ------------------------------------------------------------------
    # Title generation
    # ------------------------------------------------------------------

    def generate_title(
        self,
        niche_name: str,
        year: int,
        palette_name: str | None = None,
        keywords: list[str] | None = None,
    ) -> str:
        """Generate an SEO-optimized listing title (max 140 chars).

        Front-loads the most important keywords.  Template:
            {Year} {Niche} Digital Planner | {Keyword} | iPad GoodNotes Notability

        Args:
            niche_name: Human-readable niche, e.g. "ADHD Planner".
            year: Publication year.
            palette_name: Optional colour palette name for visual appeal.
            keywords: Additional niche keywords to weave in.

        Returns:
            Title string, guaranteed <= 140 characters.
        """
        # Core part (always present)
        core = f"{year} {niche_name} Digital Planner"
        suffix = "iPad GoodNotes Notability"

        # Pick the best extra keyword that isn't already covered by the niche
        extra = ""
        if keywords:
            niche_lower = niche_name.lower()
            for kw in keywords:
                if kw.lower() not in niche_lower and niche_lower not in kw.lower():
                    extra = kw.strip().title()
                    break

        # Try longest form first, then progressively shorten
        if extra:
            candidate = f"{core} | {extra} | {suffix}"
            if len(candidate) <= MAX_TITLE_LENGTH:
                return candidate

        # Without extra keyword
        candidate = f"{core} | {suffix}"
        if len(candidate) <= MAX_TITLE_LENGTH:
            return candidate

        # Just core — truncate if somehow still too long
        if len(core) > MAX_TITLE_LENGTH:
            core = core[: MAX_TITLE_LENGTH - 3].rstrip() + "..."
        return core

    # ------------------------------------------------------------------
    # Description generation
    # ------------------------------------------------------------------

    def generate_description(
        self,
        niche_config: dict,
        year: int,
        features: list[str] | None = None,
        palettes: list[str] | None = None,
    ) -> str:
        """Generate a rich, SEO-friendly listing description.

        Args:
            niche_config: Dict from niches.yaml with keys like name,
                subtitle, features, seed_keywords.
            year: Publication year.
            features: Override features list; falls back to niche_config.
            palettes: Full colour set of a planner bundle (hero first, the
                same list stored on ``product.palettes``).  When it holds two
                or more distinct palettes a "COLOR OPTIONS" section is added
                naming every colourway.  Single-palette planners and picture
                books (``None`` or one palette) are described as before.

        Returns:
            Multi-section description string ready for Etsy.
        """
        name = niche_config.get("name", "Digital Planner")
        subtitle = niche_config.get("subtitle", "")
        feat_list = features or niche_config.get("features", [])
        keywords = niche_config.get("seed_keywords", [])

        sections: list[str] = []

        # --- Hook line ---
        hook = f"Plan your best year yet with the {year} {name}!"
        if subtitle:
            hook += f" {subtitle}."
        sections.append(hook)

        # --- Colour options (multi-palette bundle only) ---
        distinct = _distinct_palettes(palettes)
        if len(distinct) >= 2:
            joined = ", ".join(_palette_display_name(p) for p in distinct)
            sections.append(
                "COLOR OPTIONS:\n"
                f"  {len(distinct)} color options included: {joined}\n"
                "  Every colourway is bundled in one download — use your "
                "favourite or switch between them all."
            )

        # --- Features ---
        if feat_list:
            feature_lines = [f"  - {f}" for f in feat_list]
            sections.append(
                "WHAT'S INSIDE:\n" + "\n".join(feature_lines)
            )

        # --- Included pages ---
        included = [
            "Hyperlinked yearly overview",
            "Monthly calendar spreads (Jan - Dec)",
            "Weekly planning pages",
            "Notes & brain-dump pages",
            "Goal-setting worksheets",
        ]
        sections.append(
            "WHAT'S INCLUDED:\n" + "\n".join(f"  - {item}" for item in included)
        )

        # --- Compatibility ---
        compat_apps = [
            "GoodNotes 5 / GoodNotes 6",
            "Notability",
            "Noteshelf",
            "Xodo",
            "Any PDF annotation app",
        ]
        sections.append(
            "COMPATIBLE WITH:\n" + "\n".join(f"  - {app}" for app in compat_apps)
        )

        # --- How to use ---
        steps = [
            "Purchase and download the PDF file.",
            "Import into your favourite PDF annotation app (GoodNotes, Notability, etc.).",
            "Open in read-only mode for the best hyperlink experience.",
            "Start planning! Use your Apple Pencil or stylus to write on the pages.",
        ]
        sections.append(
            "HOW TO USE:\n"
            + "\n".join(f"  {i+1}. {step}" for i, step in enumerate(steps))
        )

        # --- Devices ---
        sections.append(
            "WORKS ON:\n"
            "  - iPad (all models)\n"
            "  - Android tablets\n"
            "  - Mac / PC (with a PDF reader)"
        )

        # --- Call to action ---
        cta = (
            "Add to cart now and start planning your most productive year! "
            "If you have any questions, feel free to message us."
        )
        sections.append(cta)

        # --- Keyword footer (helps Etsy search) ---
        if keywords:
            kw_line = ", ".join(keywords[:6])
            sections.append(f"Keywords: {kw_line}")

        description = "\n\n".join(sections)
        logger.debug(
            "seo_description_generated",
            niche=name,
            length=len(description),
        )
        return description

    # ------------------------------------------------------------------
    # Tag generation
    # ------------------------------------------------------------------

    def generate_tags(
        self,
        keywords: list[str],
        niche_name: str,
        year: int | None = None,
    ) -> list[str]:
        """Generate exactly 13 unique, lowercase tags (each <= 20 chars).

        Combines broad platform terms, niche-specific keywords, and the
        publication year.  Deduplicates and avoids near-duplicate tags.

        Args:
            keywords: Seed / niche keywords.
            niche_name: E.g. "ADHD Planner".
            year: Optional publication year to include as a tag.

        Returns:
            List of exactly 13 tag strings.
        """
        year = year or datetime.now().year
        raw_tags: list[str] = []

        # Niche-derived tags
        niche_lower = niche_name.lower().strip()
        raw_tags.append(niche_lower)
        raw_tags.append(f"{year} {niche_lower}")

        # Keyword tags
        for kw in keywords:
            raw_tags.append(kw.lower().strip())

        # Broad platform / category tags
        broad = [
            "digital planner",
            f"{year} planner",
            "goodnotes planner",
            "ipad planner",
            "notability planner",
            "digital download",
            "pdf planner",
            "planner template",
            f"{year} digital planner",
        ]
        raw_tags.extend(broad)

        # Clean and enforce per-tag limits
        cleaned: list[str] = []
        seen_normalised: set[str] = set()
        for tag in raw_tags:
            tag = re.sub(r"[^\w\s]", "", tag).strip()
            if len(tag) > MAX_TAG_LENGTH:
                tag = tag[:MAX_TAG_LENGTH].rstrip()
            if not tag:
                continue

            normalised = re.sub(r"\s+", " ", tag.lower())
            if normalised in seen_normalised:
                continue

            # Skip near-duplicates (one tag is a substring of another already added)
            is_near_dup = False
            for existing in list(seen_normalised):
                if normalised in existing or existing in normalised:
                    # Keep the shorter one — more diverse
                    if len(normalised) >= len(existing):
                        is_near_dup = True
                        break
                    else:
                        # Replace longer with shorter
                        seen_normalised.discard(existing)
                        cleaned = [c for c in cleaned if re.sub(r"\s+", " ", c.lower()) != existing]
                        break

            if is_near_dup:
                continue

            seen_normalised.add(normalised)
            cleaned.append(normalised)

        # Pad if we have fewer than 13
        filler_tags = [
            "planner printable",
            "weekly planner",
            "monthly planner",
            "daily planner",
            "digital journal",
            "planning pages",
            "hyperlinked planner",
            "tablet planner",
            "yearly planner",
            "planner pdf",
            "goal planner",
            "minimalist planner",
            "study planner",
        ]
        for filler in filler_tags:
            if len(cleaned) >= REQUIRED_TAG_COUNT:
                break
            filler_norm = re.sub(r"\s+", " ", filler.lower())
            if filler_norm not in seen_normalised and len(filler_norm) <= MAX_TAG_LENGTH:
                seen_normalised.add(filler_norm)
                cleaned.append(filler_norm)

        # Trim to exactly 13
        tags = cleaned[:REQUIRED_TAG_COUNT]

        logger.debug("seo_tags_generated", count=len(tags), tags=tags)
        return tags

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_listing(
        self,
        title: str,
        description: str,
        tags: list[str],
    ) -> list[str]:
        """Validate listing metadata against Etsy requirements.

        Returns:
            List of issue strings.  Empty list means the listing is valid.
        """
        issues: list[str] = []

        # Title checks
        if not title:
            issues.append("Title is empty.")
        elif len(title) > MAX_TITLE_LENGTH:
            issues.append(
                f"Title too long: {len(title)} chars (max {MAX_TITLE_LENGTH})."
            )

        # Description checks
        if not description:
            issues.append("Description is empty.")

        # Tag checks
        if len(tags) != REQUIRED_TAG_COUNT:
            issues.append(
                f"Expected {REQUIRED_TAG_COUNT} tags, got {len(tags)}."
            )
        for i, tag in enumerate(tags):
            if len(tag) > MAX_TAG_LENGTH:
                issues.append(
                    f"Tag #{i+1} too long: '{tag}' ({len(tag)} chars, max {MAX_TAG_LENGTH})."
                )
            if tag != tag.lower():
                issues.append(f"Tag #{i+1} is not lowercase: '{tag}'.")

        # Check for duplicate tags
        seen: set[str] = set()
        for tag in tags:
            if tag in seen:
                issues.append(f"Duplicate tag: '{tag}'.")
            seen.add(tag)

        if issues:
            logger.warning("seo_validation_failed", issues=issues)
        else:
            logger.debug("seo_validation_passed")

        return issues
