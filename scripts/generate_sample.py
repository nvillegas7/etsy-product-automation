#!/usr/bin/env python3
"""CLI entry point to generate a sample planner PDF.

Usage examples
--------------
    # Minimal -- neutral beige, 2026, monthly + weekly + notes + habits + goals
    python -m scripts.generate_sample

    # Choose palette and year
    python -m scripts.generate_sample --palette soft_sage --year 2026

    # Include daily pages (warning: large PDF)
    python -m scripts.generate_sample --daily

    # Custom title
    python -m scripts.generate_sample --title "My 2026 Planner" --palette dusty_rose

    # Pick a design theme (see --list-themes for the 12 presets)
    python -m scripts.generate_sample --design studio --palette modern_minimal

    # Free per-dimension overrides on top of a preset
    python -m scripts.generate_sample --design classic --override ink=accent-pop
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path so ``src.*`` imports work when
# invoked as ``python scripts/generate_sample.py`` from the project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.planner.designs import DIMENSIONS, PRESET_PALETTES, PRESETS
from src.planner.generator import PlannerGenerator, PlannerSpec
from src.planner.styles import get_palettes, humanize


def _print_themes() -> None:
    print(f"{'preset':<11} {'shell':<7} {'interior':<8} {'motif':<10} "
          f"{'voice':<11} {'ink':<14} {'cover':<10} {'texture':<7} palettes")
    print("-" * 110)
    for name, d in PRESETS.items():
        pals = ", ".join(PRESET_PALETTES.get(name, ()))
        print(f"{name:<11} {d.shell:<7} {d.interior:<8} {d.motif:<10} "
              f"{d.voice:<11} {d.ink:<14} {d.cover:<10} {d.texture:<7} {pals}")
    print()
    print("Dimensions for --override key=value:")
    for dim, values in DIMENSIONS.items():
        print(f"  {dim}: {', '.join(values)}")


def main() -> None:
    palette_names = list(get_palettes().keys())

    parser = argparse.ArgumentParser(
        description="Generate a sample digital planner PDF.",
    )
    parser.add_argument(
        "--palette",
        choices=palette_names,
        default="neutral_beige",
        help="Color palette to use (default: neutral_beige)",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2026,
        help="Planner year (default: 2026)",
    )
    parser.add_argument(
        "--title",
        type=str,
        default=None,
        help='Planner title (default: "<YEAR> Planner")',
    )
    parser.add_argument(
        "--subtitle",
        type=str,
        default="",
        help="Subtitle shown on the cover page",
    )
    parser.add_argument(
        "--weekly",
        action="store_true",
        default=True,
        help="Include weekly spread pages (default: True)",
    )
    parser.add_argument(
        "--no-weekly",
        action="store_true",
        default=False,
        help="Exclude weekly spread pages",
    )
    parser.add_argument(
        "--daily",
        action="store_true",
        default=False,
        help="Include daily pages (creates a much larger file)",
    )
    parser.add_argument(
        "--slug",
        type=str,
        default="planner",
        help="Niche slug (e.g. budget_planner) -- selects niche pages "
             "from config/niches.yaml and is used in the filename",
    )
    parser.add_argument(
        "--display-title",
        type=str,
        default=None,
        help="Short human title for the cover (falls back to --title)",
    )
    parser.add_argument(
        "--no-niche-pages",
        action="store_true",
        default=False,
        help="Exclude the niche-specific page section",
    )
    parser.add_argument(
        "--design", "--theme",
        dest="design",
        choices=sorted(PRESETS.keys()),
        default="classic",
        help="Design theme preset (default: classic -- today's look)",
    )
    parser.add_argument(
        "--override",
        action="append",
        default=[],
        metavar="DIM=VALUE",
        help="Per-dimension design override, e.g. --override ink=accent-pop "
             "(repeatable; illegal combos are auto-repaired)",
    )
    parser.add_argument(
        "--list-themes",
        action="store_true",
        default=False,
        help="List the design theme presets and dimensions, then exit",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Enable verbose / debug logging",
    )

    args = parser.parse_args()

    if args.list_themes:
        _print_themes()
        return

    overrides: dict[str, str] = {}
    for item in args.override:
        if "=" not in item:
            parser.error(f"--override expects DIM=VALUE, got {item!r}")
        key, _, value = item.partition("=")
        overrides[key.strip()] = value.strip()

    # Logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    # Fall back to a HUMANIZED slug ("fitness_planner" -> "Fitness Planner")
    # so a raw underscore-slug can never leak onto the cover as the title.
    title = args.title or f"{args.year} {humanize(args.slug) or 'Planner'}"
    include_weekly = args.weekly and not args.no_weekly

    # Derive a friendly display title / subtitle from the niche config
    try:
        from src.planner.niche_pages import get_niche_config
        niche_cfg = get_niche_config(args.slug)
    except Exception:
        niche_cfg = {}
    display_title = args.display_title or (
        f"{args.year} {niche_cfg['name']}" if niche_cfg.get("name") else title
    )
    subtitle = args.subtitle or niche_cfg.get("subtitle", "")

    # Bias the decorative motif toward the niche so e.g. --slug fitness_planner
    # renders gym motifs instead of whatever the preset happened to carry.
    # Only fires for themed niches and when the caller didn't pin a motif; a
    # generic/unknown slug leaves the design untouched.
    if "motif" not in overrides:
        from src.planner.designs import get_design
        from src.planner.niche_themes import resolve_niche_motif
        _base = get_design(args.design, overrides)
        _themed = resolve_niche_motif(_base, args.slug)
        if _themed.motif != _base.motif:
            overrides = {**overrides, "motif": _themed.motif}

    spec = PlannerSpec(
        title=title,
        display_title=display_title,
        subtitle=subtitle,
        year=args.year,
        palette_name=args.palette,
        include_weekly=include_weekly,
        include_daily=args.daily,
        include_notes=True,
        include_habits=True,
        include_goals=True,
        include_niche_pages=not args.no_niche_pages,
        niche_slug=args.slug,
        design=args.design,
        design_overrides=overrides,
    )

    print(f"Generating planner: {spec.title}")
    print(f"  Year:    {spec.year}")
    print(f"  Palette: {spec.palette_name}")
    print(f"  Design:  {spec.design}"
          + (f"  (overrides: {overrides})" if overrides else ""))
    print(f"  Weekly:  {spec.include_weekly}")
    print(f"  Daily:   {spec.include_daily}")
    print()

    t0 = time.perf_counter()
    generator = PlannerGenerator()
    output_path = generator.generate(spec)
    elapsed = time.perf_counter() - t0

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"Done in {elapsed:.1f}s")
    print(f"Output: {output_path}")
    print(f"Size:   {size_mb:.2f} MB")

    if size_mb > 20:
        print("WARNING: File exceeds 20 MB Etsy upload limit!")


if __name__ == "__main__":
    main()
