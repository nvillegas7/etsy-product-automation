# etsy-planner-bot

Autonomous digital-product factory for Etsy. It researches a niche, generates a
finished PDF product with mockups and SEO copy, then parks it in a **manual
review queue**. A human approves or rejects every product in a local dashboard;
**nothing is ever uploaded to Etsy without explicit approval**.

## Product lines

**Digital planners** — GoodNotes-style hyperlinked PDFs sized for iPad
(clickable month/week tabs, index, niche-specific pages).

- 5 niches from `config/niches.yaml`: ADHD, Budget, Student, Fitness, Teacher —
  each with seed keywords, feature lists, and 6 niche pages (e.g. Brain Dump,
  Debt Payoff, Grade Log, Workout Log, Lesson Plans).
- 8 color palettes from `config/templates.yaml` (soft_sage, ocean_blue,
  dusty_rose, ...); each niche declares its preferred palettes.

**Children's picture books** — parameterized illustrated story PDFs from
`config/books.yaml`:

- 6 character themes (fruits, vegetables, forest_animals, farm_animals, ocean,
  pets) with named characters (e.g. Stella the Strawberry, Fiona the Fox)
- 8 settings, constrained per theme (`theme_settings` — ocean friends stay at
  the beach)
- 10 morals (kindness, honesty, sharing, courage, ...)
- 3 age bands (2-4, 4-6, 6-8) x prose/rhyme x 12 or 16 story pages x 6 art
  palettes, plus bonus coloring pages and a personalization page.

Three book niches (`kids_book_animals`, `kids_book_fruits_veggies`,
`kids_book_bedtime`) are merged into the same niche registry as the planners,
so one pipeline serves both product lines.

## Install

```bash
python3.13 -m venv .venv
.venv/bin/pip install -e .          # add ".[dev]" to get pytest
cp .env.example .env                # then fill in values as needed
```

## Quick demo (no Etsy account needed)

```bash
# Generate products (default 5 cycles, 60s apart; pass a count to change it)
.venv/bin/python scripts/run_demo.py 3

# Review them in the dashboard
.venv/bin/python scripts/run_dashboard.py
# -> http://127.0.0.1:5001
```

Every generated product lands in `REVIEW_PENDING`. In the dashboard you can
page through PDF previews and mockups, approve, reject (with a note), or
publish approved items — until Etsy is configured, Publish safely refuses with
an "upload is disabled" error (see go-live checklist).

One-off samples without touching the pipeline/DB:
`scripts/generate_sample.py` (planner) and `scripts/generate_book_sample.py`
(book) — both accept `--help`.

## State machine and the approval gate

Transitions are enforced by `src/pipeline/state.py`; illegal moves raise.

```
RESEARCH_PENDING -> RESEARCH_COMPLETE -> GENERATION_PENDING -> GENERATION_COMPLETE
    -> REVIEW_PENDING -> APPROVED | REJECTED
       APPROVED -> UPLOAD_PENDING -> PUBLISHED
       APPROVED -> REJECTED          (reviewer changes their mind before upload)
       REJECTED -> REVIEW_PENDING    (send back for another look)
       any state -> FAILED
```

The gate is structural, not procedural: `GENERATION_COMPLETE` has exactly one
outgoing transition, `REVIEW_PENDING`, and only the dashboard moves products to
`APPROVED`. Upload happens solely via
`PipelineOrchestrator.publish_approved()`, which the dashboard's Publish button
calls for approved products. There is no code path from generation to Etsy that
skips a human.

## Production

```bash
.venv/bin/python -m src.pipeline.scheduler
```

Runs an APScheduler loop calling one pipeline cycle per tick (plus one
immediately at startup).

**Demo-mode warning:** `config/config.yaml` ships with
`pipeline.cadence_seconds: 60` and `max_products_per_day: 100` — one product
per minute is a demo setting. Retune both before pointing this at a real shop.

## Etsy go-live checklist

1. Get Etsy API approval at developers.etsy.com; put `ETSY_API_KEY` and
   `ETSY_SHARED_SECRET` in `.env`.
2. One-time OAuth (PKCE, local callback on port 3003):
   `.venv/bin/python scripts/setup_oauth.py` — tokens are saved to the DB.
3. Find your category:
   `.venv/bin/python scripts/explore_taxonomy.py` and set `ETSY_TAXONOMY_ID`
   in `.env` (required — the uploader refuses to publish without it).
4. Set `etsy.shop_name` and the taxonomy/shipping settings under `etsy:` in
   `config/config.yaml`.
5. Flip `etsy.upload_enabled: true` in `config/config.yaml`. The
   `ETSY_UPLOAD_ENABLED` env var is a kill switch only: `false`/`0`/`no`
   forces uploads off, but no env value can turn them on.

## Ops notes

- **Database**: SQLite at `data/planner.db`. `paths.database` in
  `config/config.yaml` is the source of truth for the dashboard and scheduler;
  the `DATABASE_URL` env var is what library callers (and `run_demo.py`)
  default to. **They must point at the same file**, or you will generate into
  one DB and review another.
- **Dashboard security**: binds `127.0.0.1:5001` and has **no
  authentication**. Keep it local; do not expose it.
- **Trends**: `research.use_live_trends: false` locally, so niche selection
  falls back to rotation instead of hitting Google Trends.
- Outputs land under `output/` (`planners/`, `books/`, `mockups/`,
  `previews/`); logs go to stderr (`LOG_LEVEL`, `LOG_FORMAT=json`).

## Layout

```
config/           config.yaml (pipeline/etsy/paths), niches.yaml, templates.yaml, books.yaml
scripts/          run_demo.py, run_dashboard.py, setup_oauth.py, explore_taxonomy.py,
                  generate_sample.py, generate_book_sample.py
src/
  pipeline/       orchestrator.py (one full cycle), scheduler.py, state.py (state machine)
  planner/        hyperlinked planner PDF generator (pages, navigation, styles, widgets)
  books/          picture-book generator (params, story, scenes, illustrator, seo)
  research/       trends, keywords, niche scoring
  publisher/      Etsy OAuth, listing manager, uploader, SEO
  marketing/      mockup renderer
  dashboard/      Flask review/approval app ("Product Studio")
  storage/        SQLAlchemy models, repositories, SQLite engine
  monitoring/     structlog setup, metrics
  utils/          rate limiter, retry
data/planner.db   SQLite database
output/           generated PDFs, mockups, previews
tests/            pytest suite
```

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```
