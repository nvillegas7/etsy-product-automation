"""Main pipeline orchestration -- runs one product cycle end-to-end."""

from __future__ import annotations

import json
import os
import random
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
import yaml

from src.monitoring.metrics import PipelineMetrics
from src.pipeline.state import ProductStateMachine
from src.planner.styles import humanize
from src.storage.models import Niche, Product, ProductState
from src.storage.repository import (
    NicheRepository,
    PipelineRunRepository,
    ProductRepository,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = structlog.get_logger()

# Project root (two levels up from this file: src/pipeline/ -> project root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Safe optional imports for modules being built in parallel
# ---------------------------------------------------------------------------


def _import_trends_client():
    """Lazily import TrendsClient; returns None if unavailable."""
    try:
        from src.research.trends import TrendsClient
        return TrendsClient
    except ImportError:
        return None


def _import_niche_scorer():
    try:
        from src.research.niche_scorer import NicheScorer
        return NicheScorer
    except ImportError:
        return None


def _import_keyword_expander():
    try:
        from src.research.keywords import KeywordExpander
        return KeywordExpander
    except ImportError:
        return None


def _import_listing_seo():
    try:
        from src.publisher.seo import ListingSEO
        return ListingSEO
    except ImportError:
        return None


def _import_planner_generator():
    try:
        from src.planner.generator import PlannerGenerator
        return PlannerGenerator
    except ImportError:
        return None


def _import_etsy_uploader():
    try:
        from src.publisher.uploader import EtsyUploader
        return EtsyUploader
    except ImportError:
        return None


def _import_book_generator():
    try:
        from src.books.generator import BookGenerator, BookSpec
        return BookGenerator, BookSpec
    except ImportError:
        return None


def _import_book_params():
    try:
        from src.books.params import pick_book_params
        return pick_book_params
    except ImportError:
        return None


def _import_book_seo():
    try:
        from src.books.seo import BookListingSEO
        return BookListingSEO
    except ImportError:
        return None


def _import_listing_images():
    try:
        from src.marketing.mockups import generate_listing_images
        return generate_listing_images
    except ImportError:
        return None


def _import_get_palette():
    try:
        from src.planner.styles import get_palette
        return get_palette
    except ImportError:
        return None


def _import_get_palettes():
    """Lazily import the full palette registry accessor; None if unavailable."""
    try:
        from src.planner.styles import get_palettes
        return get_palettes
    except ImportError:
        return None


def _import_bundler():
    """Lazily import the ZIP bundler; returns None if unavailable."""
    try:
        from src.marketing.bundler import bundle_files
        return bundle_files
    except ImportError:
        return None


def _import_design_system():
    """Lazily import the planner design registry; returns None if unavailable."""
    try:
        from src.planner import PRESET_PALETTES, PRESETS, get_design
        return PRESETS, PRESET_PALETTES, get_design
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_niches_config() -> dict:
    """Load niche definitions from config/niches.yaml plus config/books.yaml.

    Book niches carry ``product_type: picture_book``; planner niches omit the
    field and default to ``planner``.
    """
    niches_path = _PROJECT_ROOT / "config" / "niches.yaml"
    with open(niches_path) as fh:
        data = yaml.safe_load(fh)
    niches = data.get("niches", {})

    books_path = _PROJECT_ROOT / "config" / "books.yaml"
    if books_path.exists():
        with open(books_path) as fh:
            books_data = yaml.safe_load(fh) or {}
        for slug, cfg in (books_data.get("niches") or {}).items():
            cfg.setdefault("product_type", "picture_book")
            niches[slug] = cfg
    return niches


def _etsy_upload_enabled(config: dict) -> bool:
    """Return True if Etsy upload is enabled and credentials are configured."""
    # Check env var override first. The env var is a kill switch only: it
    # can disable uploads but never enable them.
    env_flag = os.getenv("ETSY_UPLOAD_ENABLED", "").lower()
    if env_flag in ("false", "0", "no"):
        return False
    # Check config flag. Fail closed: uploads stay disabled unless
    # etsy.upload_enabled is explicitly set to true in config.yaml.
    if not config.get("etsy", {}).get("upload_enabled", False):
        return False
    # Check credentials exist
    return bool(os.getenv("ETSY_API_KEY")) and bool(os.getenv("ETSY_SHARED_SECRET"))


# ---------------------------------------------------------------------------
# PipelineOrchestrator
# ---------------------------------------------------------------------------


class PipelineOrchestrator:
    """Run one end-to-end product pipeline cycle.

    Parameters
    ----------
    config : dict
        Parsed ``config.yaml`` contents.
    session_factory : sessionmaker
        SQLAlchemy session factory from ``get_session_factory()``.
    """

    def __init__(self, config: dict, session_factory: "sessionmaker"):
        self.config = config
        self.session_factory = session_factory
        self.state_machine = ProductStateMachine()

    # ==================================================================
    # Main entry point
    # ==================================================================

    def run_once(self, product_type: str | None = None) -> Product | None:
        """Execute a single pipeline cycle: research -> generate -> publish.

        Parameters
        ----------
        product_type : str or None
            Restrict niche selection to one product line: ``'planner'`` or
            ``'picture_book'``. None (default) rotates across both.

        Returns the Product ORM object on success, or None on failure.
        """
        if product_type not in (None, "planner", "picture_book"):
            raise ValueError(
                f"Invalid product_type {product_type!r}: "
                "expected 'planner', 'picture_book', or None."
            )

        session: Session = self.session_factory()
        run_repo = PipelineRunRepository(session)
        pipeline_run = run_repo.start_run()

        product: Product | None = None

        try:
            # Guard: daily quota (counts everything generated today,
            # regardless of review outcome)
            metrics = PipelineMetrics(session)
            max_per_day = self.config.get("pipeline", {}).get("max_products_per_day", 10)
            if metrics.generated_today() >= max_per_day:
                logger.warning(
                    "daily_quota_reached",
                    generated_today=metrics.generated_today(),
                    max_per_day=max_per_day,
                )
                run_repo.complete_run(pipeline_run.id, status="skipped", error="Daily quota reached")
                session.close()
                return None

            # ── Step 1: RESEARCH ──────────────────────────────────────
            run_repo.update_phase(pipeline_run.id, "research")
            niche_slug, niche_cfg, keywords, scored_keywords = self._step_research(
                session, product_type=product_type
            )

            product_repo = ProductRepository(session)
            niche_repo = NicheRepository(session)

            # Ensure niche record exists in DB
            niche_record = niche_repo.get_by_slug(niche_slug)
            if niche_record is None:
                niche_record = niche_repo.create(
                    name=niche_cfg.get("name") or humanize(niche_slug),
                    slug=niche_slug,
                    seed_keywords=niche_cfg.get("seed_keywords", []),
                )

            product_type = niche_cfg.get("product_type", "planner")
            year = self.config.get("planner", {}).get("year", datetime.now().year)
            price = self._price_for(product_type)

            # Select palette / parameter combination
            palettes: list[str] | None = None
            if product_type == "picture_book":
                params = self._pick_book_params(niche_cfg, session)
                palette_name = params.get("art_palette", "storybook")
                display_title = (
                    params.get("display_title")
                    or niche_cfg.get("name")
                    or humanize(niche_slug)
                )
            else:
                design_name = self._select_design(session)
                params = self._design_params(design_name) if design_name else None
                bundle_enabled = self.config.get("planner", {}).get(
                    "palette_bundle", True
                )
                if bundle_enabled:
                    # One planner product = one design theme + a curated set of
                    # 3-4 palettes. Hero = first palette (dashboard preview /
                    # hero mockup / hero PDF).
                    palettes = self._select_palette_bundle(
                        niche_cfg, design_name, session
                    )
                    palette_name = palettes[0]
                    params = dict(params or {})
                    params["palettes"] = palettes
                else:
                    palette_name = self._select_palette(
                        niche_cfg, niche_record.id, session, design=design_name
                    )
                    palettes = [palette_name]
                display_title = f"{year} {niche_cfg.get('name') or humanize(niche_slug)}"

            product = product_repo.create(
                niche_id=niche_record.id,
                product_type=product_type,
                title=niche_cfg.get("name") or humanize(niche_slug),  # placeholder, SEO updates later
                display_title=display_title,
                palette_name=palette_name,
                palettes=json.dumps(palettes) if palettes else None,
                year=year,
                params=json.dumps(params) if params else None,
                price_usd=price,
                state=ProductState.RESEARCH_PENDING,
            )
            pipeline_run.product_id = product.id
            session.commit()

            logger.info(
                "product_created",
                product_id=product.id,
                product_type=product_type,
                niche=niche_slug,
                palette=palette_name,
            )

            # Transition: RESEARCH_PENDING -> RESEARCH_COMPLETE
            self.state_machine.transition(
                product.id, ProductState.RESEARCH_COMPLETE, session
            )

            # ── Step 2: GENERATE SEO ─────────────────────────────────
            run_repo.update_phase(pipeline_run.id, "seo")
            self._step_seo(product, niche_cfg, scored_keywords, session)

            # Transition: RESEARCH_COMPLETE -> GENERATION_PENDING
            self.state_machine.transition(
                product.id, ProductState.GENERATION_PENDING, session
            )

            # ── Step 3: GENERATE PDF ─────────────────────────────────
            run_repo.update_phase(pipeline_run.id, "generate_pdf")
            self._step_generate_pdf(product, niche_cfg, session)

            # Transition: GENERATION_PENDING -> GENERATION_COMPLETE
            self.state_machine.transition(
                product.id, ProductState.GENERATION_COMPLETE, session
            )

            # ── Step 4: GENERATE MOCKUPS ─────────────────────────────
            run_repo.update_phase(pipeline_run.id, "mockups")
            self._step_generate_mockups(product, session)

            # ── Step 5: QUEUE FOR HUMAN REVIEW ───────────────────────
            # Nothing reaches Etsy without explicit approval in the
            # dashboard; the pipeline stops here.
            run_repo.update_phase(pipeline_run.id, "review")
            self.state_machine.transition(
                product.id, ProductState.REVIEW_PENDING, session
            )

            # ── Done ─────────────────────────────────────────────────
            run_repo.complete_run(pipeline_run.id, status="completed")
            logger.info(
                "pipeline_cycle_complete",
                product_id=product.id,
                state=product.state.value,
            )
            return product

        except Exception as exc:
            logger.error(
                "pipeline_cycle_failed",
                product_id=product.id if product else None,
                error=str(exc),
                exc_info=True,
            )
            if product is not None:
                try:
                    self.state_machine.transition(
                        product.id,
                        ProductState.FAILED,
                        session,
                        error_message=str(exc),
                    )
                except Exception:
                    logger.error("failed_to_mark_product_failed", product_id=product.id)
            run_repo.complete_run(pipeline_run.id, status="failed", error=str(exc))
            return None

        finally:
            session.close()

    # ==================================================================
    # Convenience runners for testing
    # ==================================================================

    def run_research_only(self, niche_slug: str | None = None) -> dict[str, Any]:
        """Run only the research phase (no generation/publish).

        Returns a dict with niche info, keywords, and scored_keywords.
        """
        session: Session = self.session_factory()
        try:
            niches_config = _load_niches_config()

            if niche_slug and niche_slug in niches_config:
                niche_cfg = niches_config[niche_slug]
            elif niche_slug:
                raise ValueError(f"Niche slug '{niche_slug}' not found in niches.yaml")
            else:
                niche_slug = random.choice(list(niches_config.keys()))
                niche_cfg = niches_config[niche_slug]

            keywords, scored_keywords = self._do_keyword_research(niche_cfg, session)

            return {
                "niche_slug": niche_slug,
                "niche_config": niche_cfg,
                "keywords": keywords,
                "scored_keywords": scored_keywords,
            }
        finally:
            session.close()

    def run_generate_only(
        self, niche_slug: str | None = None, palette_name: str | None = None
    ) -> Path | None:
        """Run only the PDF generation phase.

        Returns the path to the generated PDF, or None on failure.
        """
        session: Session = self.session_factory()
        try:
            niches_config = _load_niches_config()

            if niche_slug and niche_slug in niches_config:
                niche_cfg = niches_config[niche_slug]
            elif niche_slug:
                raise ValueError(f"Niche slug '{niche_slug}' not found in niches.yaml")
            else:
                niche_slug = random.choice(list(niches_config.keys()))
                niche_cfg = niches_config[niche_slug]

            # Resolve palette
            if palette_name is None:
                preferred = niche_cfg.get("preferred_palettes", [])
                palette_name = preferred[0] if preferred else "neutral_beige"

            year = self.config.get("planner", {}).get("year", datetime.now().year)

            # Build a minimal spec dict for the generator
            spec = self._build_planner_spec(
                title=niche_cfg.get("name") or humanize(niche_slug),
                subtitle=niche_cfg.get("subtitle", ""),
                palette_name=palette_name,
                year=year,
                features=niche_cfg.get("features", []),
                niche_slug=niche_slug,
            )

            PlannerGeneratorCls = _import_planner_generator()
            if PlannerGeneratorCls is None:
                logger.error("planner_generator_not_available")
                return None

            generator = PlannerGeneratorCls()
            pdf_path = generator.generate(spec)
            logger.info("pdf_generated", path=str(pdf_path))
            return pdf_path

        finally:
            session.close()

    # ==================================================================
    # Private step implementations
    # ==================================================================

    def _step_research(
        self, session: "Session", product_type: str | None = None
    ) -> tuple[str, dict, list[str], list[tuple[str, float]]]:
        """Step 1: Select niche and run keyword research.

        When *product_type* is given, only niches of that type are candidates.

        Returns (niche_slug, niche_config, expanded_keywords, scored_keywords).
        """
        niches_config = _load_niches_config()
        # Seed the full merged registry (planners + books) before filtering,
        # so every configured niche exists in the DB regardless of which
        # product line this run is restricted to.
        self._seed_niches(niches_config, session)

        if product_type is not None:
            niches_config = {
                slug: cfg
                for slug, cfg in niches_config.items()
                if cfg.get("product_type", "planner") == product_type
            }
            if not niches_config:
                raise ValueError(
                    f"No niches configured for product_type '{product_type}'"
                )

        niche_slug = self._select_niche(niches_config, session)
        niche_cfg = niches_config[niche_slug]

        logger.info("research_niche_selected", niche=niche_slug)

        keywords, scored_keywords = self._do_keyword_research(niche_cfg, session)

        return niche_slug, niche_cfg, keywords, scored_keywords

    def _do_keyword_research(
        self, niche_cfg: dict, session: "Session"
    ) -> tuple[list[str], list[tuple[str, float]]]:
        """Expand and score keywords for a niche config."""
        KeywordExpanderCls = _import_keyword_expander()
        if KeywordExpanderCls is None:
            logger.warning("keyword_expander_not_available_using_seeds")
            seeds = niche_cfg.get("seed_keywords", [])
            return seeds, [(kw, 0.0) for kw in seeds]

        expander = KeywordExpanderCls(niche_cfg)
        keywords = expander.expand()

        # Try to score with Trends, fall back to unsorted
        use_live_trends = self.config.get("research", {}).get("use_live_trends", True)
        TrendsClientCls = _import_trends_client()
        if use_live_trends and TrendsClientCls is not None:
            try:
                cache_ttl = self.config.get("research", {}).get("trend_cache_ttl_hours", 24)
                delay = self.config.get("rate_limits", {}).get("trends_delay_seconds", 60)
                trends_client = TrendsClientCls(
                    session=session,
                    cache_ttl_hours=cache_ttl,
                    request_delay=delay,
                )
                scored_keywords = expander.score_keywords(keywords, trends_client)
            except Exception as exc:
                logger.warning("keyword_scoring_failed_using_defaults", error=str(exc))
                scored_keywords = [(kw, 0.0) for kw in keywords]
        else:
            logger.info("trends_client_not_available_using_unsorted_keywords")
            scored_keywords = [(kw, 0.0) for kw in keywords]

        logger.info(
            "keywords_expanded",
            total=len(keywords),
            scored=len(scored_keywords),
        )
        return keywords, scored_keywords

    def _seed_niches(self, niches_config: dict, session: "Session") -> None:
        """Ensure every configured niche has a row in the niches table.

        Historically only the niche picked by a run was inserted, which left
        never-selected niches (teacher_planner, the book niches) invisible to
        DB-based selection. Seeding the whole merged registry keeps rotation
        fair.
        """
        niche_repo = NicheRepository(session)
        for slug, cfg in niches_config.items():
            if niche_repo.get_by_slug(slug) is None:
                niche_repo.create(
                    name=cfg.get("name") or humanize(slug),
                    slug=slug,
                    seed_keywords=cfg.get("seed_keywords", []),
                )
                logger.info("niche_seeded", niche=slug)

    @staticmethod
    def _last_generated_by_slug(session: "Session") -> dict[str, datetime | None]:
        """Map niche slug -> most recent products.created_at (None = never).

        Uses generation time (any product state), not niches.last_published_at:
        products parked in REVIEW_PENDING never publish, so publication time
        would starve every niche but the first one picked.
        """
        from sqlalchemy import func, select

        rows = session.execute(
            select(Niche.slug, func.max(Product.created_at))
            .outerjoin(Product, Product.niche_id == Niche.id)
            .group_by(Niche.id)
        ).all()
        return dict(rows)

    @classmethod
    def _least_recently_generated(
        cls, niches_config: dict, session: "Session"
    ) -> str | None:
        """Pick the candidate slug whose last generated product is oldest.

        Never-generated niches come first; ties keep config order.
        """
        if not niches_config:
            return None
        last_generated = cls._last_generated_by_slug(session)

        def _order(slug: str) -> tuple:
            last = last_generated.get(slug)
            return (last is not None, last or datetime.min)

        return min(niches_config.keys(), key=_order)

    def _select_niche(self, niches_config: dict, session: "Session") -> str:
        """Choose the best niche to produce next.

        Tries NicheScorer with Trends data. Falls back to a fair rotation:
        the least-recently-generated candidate (never-generated first).
        Ultimate fallback: random selection.
        """
        use_live_trends = self.config.get("research", {}).get("use_live_trends", True)
        NicheScorerCls = _import_niche_scorer()
        TrendsClientCls = _import_trends_client()

        # Attempt scored selection (only if live trends enabled)
        if use_live_trends and NicheScorerCls is not None and TrendsClientCls is not None:
            try:
                cache_ttl = self.config.get("research", {}).get("trend_cache_ttl_hours", 24)
                delay = self.config.get("rate_limits", {}).get("trends_delay_seconds", 60)
                trends_client = TrendsClientCls(
                    session=session,
                    cache_ttl_hours=cache_ttl,
                    request_delay=delay,
                )
                scorer = NicheScorerCls(trends_client=trends_client, session=session)
                avoid_days = self.config.get("research", {}).get(
                    "max_recently_published_days", 7
                )
                slug = scorer.select_best(niches_config, avoid_recent_days=avoid_days)
                logger.info("niche_selected_by_scorer", niche=slug)
                return slug
            except Exception as exc:
                logger.warning("niche_scorer_failed_falling_back", error=str(exc))

        # Fallback: fair rotation by generation recency
        slug = self._least_recently_generated(niches_config, session)
        if slug is not None:
            logger.info("niche_selected_by_rotation", niche=slug)
            return slug

        # Ultimate fallback: random
        slug = random.choice(list(niches_config.keys()))
        logger.info("niche_selected_randomly", niche=slug)
        return slug

    def _price_for(self, product_type: str) -> float:
        """Resolve the default price for a product type."""
        pricing = self.config.get("pricing", {})
        if product_type == "picture_book":
            return pricing.get("book_price_usd", pricing.get("default_price_usd", 4.99))
        return pricing.get("default_price_usd", 5.99)

    def _pick_book_params(self, niche_cfg: dict, session: "Session") -> dict:
        """Pick a fresh picture-book parameter combination.

        Delegates to src.books.params, passing the params of every existing
        book so the same (character, setting, moral) combination is not
        produced twice.
        """
        pick_book_params = _import_book_params()
        if pick_book_params is None:
            raise RuntimeError(
                "src.books.params is not available -- cannot pick book parameters."
            )

        from sqlalchemy import select
        existing_rows = session.execute(
            select(Product.params).where(Product.product_type == "picture_book")
        ).scalars().all()
        existing = []
        for raw in existing_rows:
            if not raw:
                continue
            try:
                existing.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
        return pick_book_params(niche_cfg, existing)

    def _select_design(self, session: "Session") -> str | None:
        """Sample a design preset, avoiding themes used by recent planner runs.

        Rotation rule: exclude every design used by the ``len(PRESETS) - 1``
        most recent planner products, then pick randomly among the rest --
        consecutive planners therefore always differ, and every preset gets
        used before any repeats. When all presets appear in the recent
        window, fall back to excluding only the most recent design; if even
        that empties the pool, any preset is allowed.

        Returns None when the design system is unavailable (spec defaults
        to classic).
        """
        design_system = _import_design_system()
        if design_system is None:
            logger.info("design_system_not_available_using_classic")
            return None
        presets, _, _ = design_system

        preset_ids = list(presets.keys())
        recent = self._recent_planner_designs(session, limit=len(preset_ids) - 1)
        used = set(recent)
        candidates = [p for p in preset_ids if p not in used]
        if not candidates:
            # All presets exhausted recently -- only avoid an immediate repeat.
            candidates = [p for p in preset_ids if p != recent[0]] or preset_ids

        design_name = random.choice(candidates)
        logger.info("design_selected", design=design_name, recent_designs=recent)
        return design_name

    @staticmethod
    def _recent_planner_designs(session: "Session", limit: int) -> list[str]:
        """Design names of the most recent planner products, newest first."""
        from sqlalchemy import select

        rows = session.execute(
            select(Product.params)
            .where(Product.product_type == "planner")
            .order_by(Product.created_at.desc(), Product.id.desc())
            .limit(limit)
        ).scalars().all()

        designs: list[str] = []
        for raw in rows:
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and parsed.get("design"):
                designs.append(str(parsed["design"]))
        return designs

    @staticmethod
    def _design_params(design_name: str) -> dict[str, str] | None:
        """Serialize a design preset into JSON-safe product params.

        Returns {'design', 'shell', 'interior', 'motif', 'voice', 'ink',
        'cover', 'texture'} so reviewers can see exactly what was sampled.
        """
        design_system = _import_design_system()
        if design_system is None:
            return None
        _, _, get_design = design_system
        design = get_design(design_name)
        return {"design": design.name, **design.dims()}

    def _select_palette(
        self,
        niche_cfg: dict,
        niche_id: int,
        session: "Session",
        design: str | None = None,
    ) -> str:
        """Pick a palette from the niche's preferred list, rotating through them.

        When a *design* preset is given, restrict the pool to palettes the
        design recommends (PRESET_PALETTES); niche preferences win within
        that set. Classic recommends every palette, so classic behavior is
        unchanged.
        """
        preferred = niche_cfg.get("preferred_palettes", [])
        if not preferred:
            preferred = ["neutral_beige"]

        if design is not None:
            design_system = _import_design_system()
            if design_system is not None:
                _, preset_palettes, _ = design_system
                recommended = preset_palettes.get(design, ())
                compatible = [p for p in preferred if p in recommended]
                preferred = compatible or list(recommended) or preferred

        # Count existing products for this niche to rotate palette
        product_repo = ProductRepository(session)
        # Simple rotation: count all products for this niche and modulo
        from sqlalchemy import select, func
        from src.storage.models import Product as ProductModel
        count = session.execute(
            select(func.count(ProductModel.id)).where(ProductModel.niche_id == niche_id)
        ).scalar_one()

        idx = count % len(preferred)
        return preferred[idx]

    def _select_palette_bundle(
        self,
        niche_cfg: dict,
        design: str | None,
        session: "Session",
        minimum: int = 3,
        maximum: int = 4,
    ) -> list[str]:
        """Curate the 3-4 palettes bundled with one planner product.

        Starts from the design's recommended palettes (PRESET_PALETTES)
        intersected with the niche's preferred palettes, then tops up to at
        least ``minimum`` from the design's own recommendations and finally
        from the full palette registry. The first entry is the hero palette
        and is guaranteed to be one the design recommends (when a design is
        given).
        """
        niche_preferred = list(niche_cfg.get("preferred_palettes", []) or [])

        design_recommended: list[str] = []
        if design is not None:
            design_system = _import_design_system()
            if design_system is not None:
                _, preset_palettes, _ = design_system
                design_recommended = list(preset_palettes.get(design, ()))

        get_palettes = _import_get_palettes()
        all_names = list(get_palettes().keys()) if get_palettes is not None else []

        bundle = self._curate_palettes(
            design_recommended, niche_preferred, all_names, minimum, maximum
        )
        if not bundle:
            # Never return empty; fall back to the historical default palette.
            bundle = [niche_preferred[0] if niche_preferred else "neutral_beige"]
        logger.info(
            "palette_bundle_curated",
            design=design,
            palettes=bundle,
            hero=bundle[0],
        )
        return bundle

    @staticmethod
    def _curate_palettes(
        design_recommended: list[str],
        niche_preferred: list[str],
        all_palettes: list[str],
        minimum: int = 3,
        maximum: int = 4,
    ) -> list[str]:
        """Pure curation of a de-duped, ordered palette bundle (hero first).

        Order: niche preferences the design recommends, then the design's own
        recommendations, then any palettes needed to reach ``minimum`` -- all
        capped at ``maximum``. When no design guidance exists, niche
        preferences lead.
        """
        design_recommended = list(design_recommended or [])
        niche_preferred = list(niche_preferred or [])
        ordered: list[str] = []

        def add(name: str) -> None:
            if name and name not in ordered and len(ordered) < maximum:
                ordered.append(name)

        if design_recommended:
            recommended = set(design_recommended)
            for name in niche_preferred:  # niche prefs the design recommends
                if name in recommended:
                    add(name)
            for name in design_recommended:  # then the design's own picks
                add(name)
        else:
            for name in niche_preferred:  # no design guidance: niche leads
                add(name)

        if len(ordered) < minimum:  # guarantee at least ``minimum``
            for name in all_palettes:
                if len(ordered) >= minimum:
                    break
                add(name)
        return ordered

    @staticmethod
    def _product_palettes(product: Product) -> list[str]:
        """Return the palette bundle for a product (hero first).

        Reads the ``palettes`` column, falling back to the ``params`` list
        and finally to the single hero ``palette_name``.
        """
        raw = getattr(product, "palettes", None)
        if raw:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list) and parsed:
                return [str(p) for p in parsed]
        params = PipelineOrchestrator._product_design_params(product)
        from_params = params.get("palettes")
        if isinstance(from_params, list) and from_params:
            return [str(p) for p in from_params]
        return [product.palette_name] if product.palette_name else []

    def _step_seo(
        self,
        product: Product,
        niche_cfg: dict,
        scored_keywords: list[tuple[str, float]],
        session: "Session",
    ) -> None:
        """Step 2: Generate SEO title, description, and tags."""
        if product.product_type == "picture_book":
            self._step_seo_book(product, niche_cfg, scored_keywords, session)
            return

        ListingSEOCls = _import_listing_seo()

        if ListingSEOCls is not None:
            try:
                seo = ListingSEOCls()
                niche_name = (
                    niche_cfg.get("name")
                    or humanize(niche_cfg.get("slug", ""))
                    or "Planner"
                )
                keywords = [kw for kw, _ in scored_keywords[:10]]
                title = seo.generate_title(
                    niche_name=niche_name,
                    year=product.year,
                    palette_name=product.palette_name,
                    keywords=keywords,
                )
                features = list(niche_cfg.get("features", []))
                design_line = self._design_feature_line(product)
                if design_line:
                    features.append(design_line)
                description = seo.generate_description(
                    niche_config=niche_cfg,
                    year=product.year,
                    features=features,
                )
                tags = seo.generate_tags(
                    keywords=keywords,
                    niche_name=niche_name,
                    year=product.year,
                )
            except Exception as exc:
                logger.warning("seo_generation_failed_using_defaults", error=str(exc))
                title, description, tags = self._fallback_seo(niche_cfg, product.year, scored_keywords)
        else:
            logger.info("listing_seo_not_available_using_fallback")
            title, description, tags = self._fallback_seo(niche_cfg, product.year, scored_keywords)

        product_repo = ProductRepository(session)
        product_repo.update(
            product.id,
            title=title,
            description=description,
            tags=json.dumps(tags) if isinstance(tags, list) else tags,
        )

        logger.info(
            "seo_generated",
            product_id=product.id,
            title=title,
            tag_count=len(tags) if isinstance(tags, list) else 0,
        )

    def _step_seo_book(
        self,
        product: Product,
        niche_cfg: dict,
        scored_keywords: list[tuple[str, float]],
        session: "Session",
    ) -> None:
        """SEO for picture books, via src.books.seo with a generic fallback."""
        params = json.loads(product.params) if product.params else {}
        BookListingSEOCls = _import_book_seo()

        if BookListingSEOCls is not None:
            try:
                seo = BookListingSEOCls()
                title = seo.generate_title(params, year=product.year)
                description = seo.generate_description(params)
                tags = seo.generate_tags(params, year=product.year)
            except Exception as exc:
                logger.warning("book_seo_failed_using_defaults", error=str(exc))
                title, description, tags = self._fallback_seo(
                    niche_cfg, product.year, scored_keywords
                )
        else:
            logger.info("book_seo_not_available_using_fallback")
            title, description, tags = self._fallback_seo(
                niche_cfg, product.year, scored_keywords
            )

        product_repo = ProductRepository(session)
        product_repo.update(
            product.id,
            title=title,
            description=description,
            tags=json.dumps(tags) if isinstance(tags, list) else tags,
        )
        logger.info("seo_generated", product_id=product.id, title=title)

    @staticmethod
    def _product_design_params(product: Product) -> dict:
        """Parse the design params persisted on a planner product; never raises."""
        if not product.params:
            return {}
        try:
            parsed = json.loads(product.params)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @classmethod
    def _design_feature_line(cls, product: Product) -> str | None:
        """Human-readable aesthetic note for listing copy, from product params."""
        params = cls._product_design_params(product)
        design = params.get("design")
        if not design:
            return None
        label = str(design).replace("-", " ").replace("_", " ").title()
        motif = params.get("motif")
        voice = params.get("voice")
        if motif and voice:
            return (
                f"{label} design theme -- {motif} motifs with "
                f"{str(voice).replace('-', ' ')} typography"
            )
        return f"{label} design theme"

    @staticmethod
    def _fallback_seo(
        niche_cfg: dict, year: int, scored_keywords: list[tuple[str, float]]
    ) -> tuple[str, str, list[str]]:
        """Generate basic SEO data without the ListingSEO module."""
        name = (
            niche_cfg.get("name")
            or humanize(niche_cfg.get("slug", ""))
            or "Digital Planner"
        )
        subtitle = niche_cfg.get("subtitle", "")
        features = niche_cfg.get("features", [])

        title = f"{name} {year} | Digital Planner PDF for iPad GoodNotes"
        # Truncate to Etsy's 140-character limit
        title = title[:140]

        lines = [
            f"{subtitle}\n" if subtitle else "",
            f"This {name.lower()} is designed to help you stay organized in {year}.\n",
            "",
            "Features:",
        ]
        for feat in features:
            lines.append(f"- {feat}")
        lines.extend([
            "",
            "Compatible with GoodNotes, Notability, and other PDF annotation apps.",
            "Instant digital download - no physical product will be shipped.",
        ])
        description = "\n".join(lines)

        # Tags from top scored keywords
        KeywordExpanderCls = _import_keyword_expander()
        if KeywordExpanderCls is not None and scored_keywords:
            tags = KeywordExpanderCls.generate_tags(scored_keywords)
        else:
            tags = [kw for kw, _ in scored_keywords[:13]]

        return title, description, tags

    def _step_generate_pdf(
        self, product: Product, niche_cfg: dict, session: "Session"
    ) -> None:
        """Step 3: Generate the product PDF (planner or picture book).

        Planners with a curated palette bundle generate one PDF per palette
        (same design theme, different palette) and zip them into a single
        delivery bundle. The hero palette's PDF becomes ``pdf_path`` and its
        size ``file_size_bytes``; the ZIP path is stored on ``bundle_path``.
        """
        if product.product_type == "picture_book":
            pdf_path = self._generate_book_pdf(product)
            self._persist_hero_pdf(product, pdf_path, session)
            return

        self._generate_planner_bundle(product, niche_cfg, session)

    def _persist_hero_pdf(
        self, product: Product, pdf_path: Path, session: "Session"
    ) -> None:
        file_size = pdf_path.stat().st_size if pdf_path.exists() else 0
        ProductRepository(session).update(
            product.id,
            pdf_path=str(pdf_path),
            file_size_bytes=file_size,
        )
        logger.info(
            "pdf_generated",
            product_id=product.id,
            pdf_path=str(pdf_path),
            file_size_bytes=file_size,
        )

    def _generate_planner_bundle(
        self, product: Product, niche_cfg: dict, session: "Session"
    ) -> None:
        """Generate one PDF per bundled palette and zip them for delivery."""
        palettes = self._product_palettes(product)
        # Hero always first; generate it plus one PDF per remaining palette.
        pdf_paths = [
            self._generate_planner_pdf(product, niche_cfg, palette_name=palette)
            for palette in palettes
        ]
        hero_pdf = pdf_paths[0]
        self._persist_hero_pdf(product, hero_pdf, session)

        bundle_enabled = self.config.get("planner", {}).get("palette_bundle", True)
        if not (bundle_enabled and len(pdf_paths) > 1):
            # Single-palette planner: no zip, but record the (single) palette.
            ProductRepository(session).set_bundle(product.id, palettes)
            return

        bundle_path = self._bundle_planner_pdfs(
            product, niche_cfg, palettes, pdf_paths
        )
        ProductRepository(session).set_bundle(
            product.id, palettes, bundle_path=bundle_path
        )
        logger.info(
            "palette_bundle_zipped",
            product_id=product.id,
            bundle_path=str(bundle_path),
            palette_count=len(pdf_paths),
        )

    def _bundle_planner_pdfs(
        self,
        product: Product,
        niche_cfg: dict,
        palettes: list[str],
        pdf_paths: list[Path],
    ) -> Path:
        """Zip per-palette PDFs into ``paths.bundle_dir`` with clean arcnames."""
        bundle_files = _import_bundler()
        if bundle_files is None:
            raise RuntimeError(
                "src.marketing.bundler is not available -- cannot bundle PDFs."
            )

        bundle_dir = _PROJECT_ROOT / self.config.get("paths", {}).get(
            "bundle_dir", "output/bundles"
        )
        name = (
            niche_cfg.get("name")
            or humanize(niche_cfg.get("slug", ""))
            or "Planner"
        )
        base = re.sub(r"[^A-Za-z0-9]+", "_", f"{product.year}_{name}").strip("_")
        arcnames = [f"{base}_{palette}.pdf" for palette in palettes]
        out_zip = bundle_dir / f"product_{product.id}_bundle.zip"
        return bundle_files(pdf_paths, out_zip, arcnames=arcnames)

    def _generate_planner_pdf(
        self,
        product: Product,
        niche_cfg: dict,
        palette_name: str | None = None,
    ) -> Path:
        PlannerGeneratorCls = _import_planner_generator()
        if PlannerGeneratorCls is None:
            raise RuntimeError(
                "PlannerGenerator is not available -- cannot generate PDF. "
                "Ensure src.planner.generator is implemented."
            )

        spec = self._build_planner_spec(
            title=product.title,
            display_title=product.display_title or f"{product.year} {niche_cfg.get('name') or humanize(niche_cfg.get('slug', '')) or 'Planner'}",
            subtitle=niche_cfg.get("subtitle", ""),
            palette_name=palette_name or product.palette_name,
            year=product.year,
            features=niche_cfg.get("features", []),
            niche_slug=niche_cfg.get("slug", re.sub(r'[^a-z0-9]+', '_', niche_cfg.get("name", "planner").lower()).strip('_')),
            design=self._product_design_params(product).get("design", "classic"),
        )

        generator = PlannerGeneratorCls()
        return generator.generate(spec)

    def _generate_book_pdf(self, product: Product) -> Path:
        imported = _import_book_generator()
        if imported is None:
            raise RuntimeError(
                "BookGenerator is not available -- cannot generate picture book. "
                "Ensure src.books.generator is implemented."
            )
        BookGeneratorCls, BookSpecCls = imported

        params = json.loads(product.params) if product.params else {}
        spec = BookSpecCls(
            title=product.display_title or product.title,
            subtitle=params.get("subtitle", ""),
            year=product.year,
            palette_name=product.palette_name,
            params=params,
        )
        generator = BookGeneratorCls()
        return generator.generate(spec)

    def _step_generate_mockups(
        self, product: Product, session: "Session"
    ) -> list[Path]:
        """Step 4: Compose Etsy listing images for the product.

        Prefers the marketing mockup composer (multi-image gallery); falls
        back to a plain render of the cover page. Persists the full list as
        JSON in ``product.mockup_path``.
        """
        if not product.pdf_path:
            logger.warning("no_pdf_path_for_mockups", product_id=product.id)
            return []

        mockup_dir = _PROJECT_ROOT / self.config.get("paths", {}).get(
            "mockup_dir", "output/mockups"
        )
        mockup_dir.mkdir(parents=True, exist_ok=True)

        mockup_paths: list[Path] = []
        generate_listing_images = _import_listing_images()
        if generate_listing_images is not None:
            try:
                mockup_paths = generate_listing_images(
                    product.pdf_path,
                    mockup_dir,
                    product_id=product.id,
                    title=product.display_title or product.title,
                    product_type=product.product_type,
                    palette_name=product.palette_name,
                    palettes=self._product_palettes(product),
                    design_name=self._product_design_params(product).get("design"),
                )
            except Exception as exc:
                logger.warning(
                    "listing_image_composer_failed_falling_back",
                    product_id=product.id,
                    error=str(exc),
                )

        if not mockup_paths:
            mockup_paths = self._render_cover_mockup(product, mockup_dir)

        if mockup_paths:
            product_repo = ProductRepository(session)
            product_repo.update(
                product.id,
                mockup_path=json.dumps([str(p) for p in mockup_paths]),
            )

        logger.info(
            "mockups_generated",
            product_id=product.id,
            count=len(mockup_paths),
        )
        return mockup_paths

    @staticmethod
    def _render_cover_mockup(product: Product, mockup_dir: Path) -> list[Path]:
        """Fallback: rasterize page 1 of the PDF as the only listing image."""
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(product.pdf_path)
            pix = doc[0].get_pixmap(dpi=150)
            out_path = mockup_dir / f"product_{product.id}_mockup_0.png"
            pix.save(str(out_path))
            doc.close()
            return [out_path]
        except Exception as exc:
            logger.warning(
                "mockup_generation_failed",
                product_id=product.id,
                error=str(exc),
            )
            return []

    # ==================================================================
    # Post-approval publishing (called from the dashboard)
    # ==================================================================

    def publish_approved(self, product_id: int) -> "Product":
        """Publish a single APPROVED product to Etsy.

        This is the only path that reaches Etsy, and it requires the
        product to have passed manual review. Raises with a clear message
        when upload is disabled or misconfigured so the dashboard can
        surface it.
        """
        session: Session = self.session_factory()
        try:
            product = session.get(Product, product_id)
            if product is None:
                raise ValueError(f"Product {product_id} not found")
            if product.state != ProductState.APPROVED:
                raise ValueError(
                    f"Product {product_id} is '{product.state.value}', not 'approved'. "
                    "Only approved products can be published."
                )

            if not _etsy_upload_enabled(self.config):
                raise RuntimeError(
                    "Etsy upload is disabled. Set etsy.upload_enabled: true in "
                    "config/config.yaml and provide ETSY_API_KEY / ETSY_SHARED_SECRET "
                    "(plus ETSY_TAXONOMY_ID) in .env, then run scripts/setup_oauth.py once."
                )

            from src.publisher.auth import EtsyAuth
            from src.publisher.listing import EtsyListingManager
            from src.publisher.uploader import EtsyUploader
            from src.utils.rate_limiter import TokenBucketRateLimiter

            rate_cfg = self.config.get("rate_limits", {})
            auth = EtsyAuth(
                api_key=os.environ["ETSY_API_KEY"],
                shared_secret=os.environ["ETSY_SHARED_SECRET"],
                session=session,
            )
            rate_limiter = TokenBucketRateLimiter(
                requests_per_second=float(rate_cfg.get("etsy_requests_per_second", 5)),
                requests_per_day=int(rate_cfg.get("etsy_requests_per_day", 5000)),
            )
            listing_mgr = EtsyListingManager(auth=auth, rate_limiter=rate_limiter)
            uploader = EtsyUploader(listing_manager=listing_mgr, session=session)

            taxonomy_id = int(
                os.getenv("ETSY_TAXONOMY_ID", "0")
                or self.config.get("etsy", {}).get("taxonomy_id") or 0
            )

            mockup_paths: list[str] = []
            if product.mockup_path:
                try:
                    parsed = json.loads(product.mockup_path)
                    mockup_paths = [parsed] if isinstance(parsed, str) else list(parsed)
                except (json.JSONDecodeError, TypeError):
                    mockup_paths = [product.mockup_path]

            self.state_machine.transition(
                product.id, ProductState.UPLOAD_PENDING, session
            )
            uploader.publish(product, mockup_paths, taxonomy_id=taxonomy_id or None)

            niche_repo = NicheRepository(session)
            niche_repo.mark_published(product.niche_id)
            session.refresh(product)

            logger.info("product_published_to_etsy", product_id=product.id)
            return product
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Spec builder
    # ------------------------------------------------------------------

    def _build_planner_spec(
        self,
        title: str,
        subtitle: str,
        palette_name: str,
        year: int,
        features: list[str],
        niche_slug: str,
        display_title: str | None = None,
        design: str = "classic",
        design_overrides: dict[str, str] | None = None,
    ):
        """Build a PlannerSpec consumed by PlannerGenerator.generate()."""
        planner_cfg = self.config.get("planner", {})

        # Bias the decorative motif toward the niche (student -> academic,
        # fitness -> fitness, ...) so a rotated preset's motif never mismatches
        # the product.  Preserves the rotated preset + palette bundle: only the
        # motif dimension is (possibly) overridden.
        design_overrides = self._apply_niche_motif(
            design, niche_slug, dict(design_overrides or {})
        )

        try:
            from src.planner.generator import PlannerSpec

            return PlannerSpec(
                title=title,
                display_title=display_title or title,
                subtitle=subtitle,
                palette_name=palette_name,
                year=year,
                niche_slug=niche_slug,
                include_weekly=True,
                include_daily=planner_cfg.get("include_daily_pages", False),
                include_notes=True,
                include_habits=True,
                include_goals=True,
                design=design,
                design_overrides=design_overrides,
            )
        except ImportError:
            # Fallback to dict if PlannerSpec not available
            return {
                "title": title,
                "display_title": display_title or title,
                "subtitle": subtitle,
                "palette_name": palette_name,
                "year": year,
                "niche_slug": niche_slug,
                "design": design,
                "design_overrides": design_overrides,
            }

    @staticmethod
    def _apply_niche_motif(
        design: str, niche_slug: str, design_overrides: dict[str, str]
    ) -> dict[str, str]:
        """Return *design_overrides* with a niche-matched ``motif`` entry.

        Resolves the preset + existing overrides into a concrete design, asks
        the niche->motif policy for the right motif, and injects it as a motif
        override only when the preset's motif would mismatch the niche.  A
        no-op for generic/unknown slugs, for an explicit caller motif override,
        or when the design system is unavailable (parallel-build safety).
        """
        if "motif" in design_overrides:
            return design_overrides  # respect an explicit caller override
        try:
            from src.planner.designs import get_design
            from src.planner.niche_themes import resolve_niche_motif
        except ImportError:
            return design_overrides
        base = get_design(design, design_overrides)
        themed = resolve_niche_motif(base, niche_slug)
        if themed.motif != base.motif:
            design_overrides = {**design_overrides, "motif": themed.motif}
        return design_overrides
