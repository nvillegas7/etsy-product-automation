"""Generate a sample picture book and render its pages to PNG for review.

Usage
-----
    .venv/bin/python scripts/generate_book_sample.py \
        --theme fruits --character strawberry --setting park \
        --moral sharing --style prose --age 4-6 --palette sunny_day --seed 42

Outputs the PDF under output/books/ and page PNGs under
output/previews/book_samples/<slug>/.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.books.generator import BookGenerator, BookSpec  # noqa: E402
from src.books.params import pick_book_params  # noqa: E402
from src.books.seo import BookListingSEO  # noqa: E402
from src.books.story import build_story  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a sample picture book")
    parser.add_argument("--theme", default=None, help="character theme (e.g. fruits)")
    parser.add_argument("--character", default=None, help="character key (e.g. strawberry)")
    parser.add_argument("--setting", default=None, help="setting (e.g. park)")
    parser.add_argument("--moral", default=None, help="moral (e.g. sharing)")
    parser.add_argument("--style", default=None, choices=[None, "prose", "rhyme"],
                        help="narrative style")
    parser.add_argument("--age", default=None, choices=[None, "2-4", "4-6", "6-8"],
                        help="age band")
    parser.add_argument("--palette", default=None, help="art palette name")
    parser.add_argument("--pages", type=int, default=None, choices=[12, 16],
                        help="story page count")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dpi", type=int, default=72)
    parser.add_argument("--no-render", action="store_true", help="skip PNG rendering")
    args = parser.parse_args()

    niche_cfg = {"allowed_themes": [args.theme] if args.theme else None}
    niche_cfg = {k: v for k, v in niche_cfg.items() if v}
    params = pick_book_params(niche_cfg, existing=[], seed=args.seed)

    overrides = {
        "character_theme": args.theme,
        "character_key": args.character,
        "setting": args.setting,
        "moral": args.moral,
        "narrative_style": args.style,
        "age_band": args.age,
        "art_palette": args.palette,
        "page_count": args.pages,
    }
    params.update({k: v for k, v in overrides.items() if v})

    if args.character:
        # keep name + title consistent with an overridden character/moral
        from src.books.params import MORAL_TITLES, _species_label
        from src.books.illustrator import load_book_config

        names = (load_book_config().get("book_params") or {}).get("character_names", {})
        pool = names.get(params["character_key"]) or [params["character_key"].title()]
        params["character_name"] = pool[args.seed % len(pool)]
        full = f"{params['character_name']} the {_species_label(params['character_key'])}"
        params["character_full_name"] = full
        params["display_title"] = MORAL_TITLES.get(
            params["moral"], "{name}'s Big Day"
        ).format(name=full)
        params["subtitle"] = f"A warm little story about {params['moral']}"

    story = build_story(params)
    print(f"=== {story.title} ({params['narrative_style']}, ages {params['age_band']}, "
          f"{params['page_count']} story pages) ===")
    for i, page in enumerate(story.pages, 1):
        flat = page.text.replace("\n", " / ")
        print(f"  p{i:>2} [{page.beat:<14}] {flat}")

    seo = BookListingSEO()
    print("\nSEO title:", seo.generate_title(params, 2026))
    print("SEO tags :", seo.generate_tags(params, 2026))

    spec = BookSpec(
        title=params["display_title"],
        subtitle=params.get("subtitle", ""),
        year=2026,
        palette_name=params["art_palette"],
        params=params,
    )
    pdf_path = BookGenerator().generate(spec)
    print(f"\nPDF: {pdf_path}")

    if args.no_render:
        return

    import fitz  # PyMuPDF

    out_dir = PROJECT_ROOT / "output" / "previews" / "book_samples" / pdf_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf_path))
    for i, page in enumerate(doc):
        png = out_dir / f"page_{i + 1:02d}.png"
        page.get_pixmap(dpi=args.dpi).save(str(png))
    doc.close()
    print(f"PNGs: {out_dir} ({len(list(out_dir.glob('*.png')))} pages)")


if __name__ == "__main__":
    main()
