"""Flask app factory for the 'Product Studio' manual-approval dashboard.

Every generated product parks in REVIEW_PENDING; a human reviews it here,
approves or rejects it, and only APPROVED products can be pushed to Etsy
via PipelineOrchestrator.publish_approved().

Security note: file-serving routes never accept raw paths from the client.
Only integer product ids (and integer page/mockup indices) are accepted,
and every path is resolved server-side through the database.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import structlog
import yaml
from flask import (
    Flask,
    Response,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from src.monitoring.metrics import PipelineMetrics
from src.pipeline.state import ProductStateMachine
from src.storage.database import get_session_factory, init_db
from src.storage.models import Niche, Product, ProductState
from src.storage.repository import (
    EtsyListingRepository,
    ProductRepository,
    ReviewEventRepository,
)

# Rejection reason categories offered in the review form (value, label). The
# free-text comment is always captured too; these just make patterns countable.
REVIEW_REASONS: list[tuple[str, str]] = [
    ("design", "Design / visual"),
    ("title_seo", "Title / SEO / keywords"),
    ("quality", "Quality / errors"),
    ("mismatch", "Off-brand / niche mismatch"),
    ("pricing", "Pricing"),
    ("other", "Other"),
]
_REVIEW_REASON_LABELS = dict(REVIEW_REASONS)
_DECISION_LABELS = {
    "approved": "Approved",
    "rejected": "Rejected",
    "re_review": "Re-opened",
}

logger = structlog.get_logger()

# Project root (two levels up from this file: src/dashboard/ -> project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Guard so only one background generation cycle runs at a time.
_generation_lock = threading.Lock()

# States that are neither terminal nor awaiting a human decision.
IN_PROGRESS_STATES: frozenset[ProductState] = frozenset(
    {
        ProductState.RESEARCH_PENDING,
        ProductState.RESEARCH_COMPLETE,
        ProductState.GENERATION_PENDING,
        ProductState.GENERATION_COMPLETE,
        ProductState.UPLOAD_PENDING,
    }
)

# Filter key -> single ProductState (in_progress is handled separately).
STATE_FILTERS: dict[str, ProductState] = {
    "review_pending": ProductState.REVIEW_PENDING,
    "approved": ProductState.APPROVED,
    "rejected": ProductState.REJECTED,
    "published": ProductState.PUBLISHED,
    "failed": ProductState.FAILED,
}

# state -> (label, css badge class)
_BADGES: dict[ProductState, tuple[str, str]] = {
    ProductState.REVIEW_PENDING: ("Review pending", "amber"),
    ProductState.APPROVED: ("Approved", "green"),
    ProductState.REJECTED: ("Rejected", "rose"),
    ProductState.PUBLISHED: ("Published", "blue"),
    ProductState.FAILED: ("Failed", "gray"),
}

PREVIEW_PAGE_LIMIT = 12
PREVIEW_EXTRA_SAMPLES = 4
PREVIEW_DPI = 80


# ---------------------------------------------------------------------------
# Path resolution helpers
# ---------------------------------------------------------------------------


def resolve_product_file(path_str: str | None, kind: str) -> Path | None:
    """Resolve a stored file path, tolerating paths from another machine.

    The database may contain absolute paths recorded elsewhere (e.g.
    ``/Users/neilalvinvillegas/...``).  If the stored path does not exist,
    fall back to looking the basename up in this project's output folders.

    Parameters
    ----------
    path_str : str or None
        Raw path from the database.
    kind : str
        ``"pdf"`` or ``"mockup"`` -- selects which output folders to search.

    Returns
    -------
    Path or None
        An existing file path, or None if the file cannot be found.
    """
    if not path_str:
        return None
    path = Path(path_str)
    if path.is_file():
        return path
    fallback_dirs = {
        "pdf": ("output/planners", "output/books"),
        "mockup": ("output/mockups",),
        "bundle": ("output/bundles",),
    }.get(kind, ())
    for rel in fallback_dirs:
        candidate = PROJECT_ROOT / rel / path.name
        if candidate.is_file():
            return candidate
    return None


def _parse_json(raw: str | None, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default


# Etsy listing limits enforced when a reviewer edits tags.
MAX_TAGS = 13
MAX_TAG_LEN = 20


def _parse_tags(raw: str) -> tuple[list[str], str | None]:
    """Parse a comma/newline-separated tag input into a clean JSON-ready list.

    Trims each tag, drops empties and case-insensitive duplicates (first
    spelling wins, order preserved). Returns ``(tags, error)``: on any
    Etsy-limit violation (>13 tags, or a tag over 20 chars) ``error`` is a
    human-readable message and the tag list should not be saved.
    """
    pieces = [
        part.strip()
        for chunk in (raw or "").replace("\r", "\n").split("\n")
        for part in chunk.split(",")
    ]
    tags: list[str] = []
    seen: set[str] = set()
    for tag in pieces:
        if not tag:
            continue
        if len(tag) > MAX_TAG_LEN:
            return [], f"Each tag must be {MAX_TAG_LEN} characters or fewer — '{tag}' is too long."
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        tags.append(tag)
    if len(tags) > MAX_TAGS:
        return [], f"Etsy allows at most {MAX_TAGS} tags (you entered {len(tags)})."
    return tags, None


def mockup_path_list(product: Product) -> list[str]:
    """Return the mockup paths for a product (JSON list or single path)."""
    raw = product.mockup_path
    if not raw:
        return []
    parsed = _parse_json(raw, raw)
    if isinstance(parsed, str):
        return [parsed]
    if isinstance(parsed, list):
        return [str(p) for p in parsed]
    return []


def product_palettes(product: Product) -> list[str]:
    """Full colour set for a product (hero first), de-duplicated.

    Canonical source is the ``palettes`` column; falls back to
    ``params['palettes']`` and finally the single hero ``palette_name``.
    """
    raw = _parse_json(product.palettes, None)
    names: list[str] = []
    if isinstance(raw, list) and raw:
        names = [str(p) for p in raw]
    else:
        params = _parse_json(product.params, {})
        from_params = params.get("palettes") if isinstance(params, dict) else None
        if isinstance(from_params, list) and from_params:
            names = [str(p) for p in from_params]
        elif product.palette_name:
            names = [product.palette_name]
    # De-dup, order preserved.
    ordered: list[str] = []
    for n in names:
        if n and n not in ordered:
            ordered.append(n)
    return ordered


def palette_swatches(names: list[str]) -> list[dict]:
    """Display name + a few hex swatch colours for each palette.

    Never raises: unknown palettes collapse to a title-cased label with no
    swatch colours.
    """
    out: list[dict] = []
    for name in names:
        display = name.replace("_", " ").replace("-", " ").title()
        colors: list[str] = []
        try:
            from src.planner.styles import get_palette

            pal = get_palette(name)
            display = pal.name
            colors = [pal.primary, pal.secondary, pal.accent, pal.background]
        except Exception:
            colors = []
        out.append({"key": name, "name": display, "colors": colors})
    return out


def state_badge(state: ProductState) -> tuple[str, str]:
    """Return (label, css class) for a product state badge."""
    if state in _BADGES:
        return _BADGES[state]
    return state.value.replace("_", " ").capitalize(), "purple"


# ---------------------------------------------------------------------------
# View models
# ---------------------------------------------------------------------------


@dataclass
class ProductView:
    """Template-friendly wrapper around a Product row."""

    product: Product
    niche_name: str | None = None
    mockup_indices: list[int] = field(default_factory=list)
    thumb_index: int | None = None
    pdf_available: bool = False
    params: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    state_label: str = ""
    badge_class: str = ""
    params_summary: str = ""
    palettes: list[dict] = field(default_factory=list)
    bundle_available: bool = False

    @property
    def title(self) -> str:
        return self.product.display_title or self.product.title

    @property
    def type_label(self) -> str:
        return "Picture book" if self.product.product_type == "picture_book" else "Planner"

    @property
    def is_bundle(self) -> bool:
        """True when this product ships two or more palette colourways."""
        return len(self.palettes) >= 2

    @property
    def color_count(self) -> int:
        return len(self.palettes)


def build_product_view(product: Product, niche_names: dict[int, str]) -> ProductView:
    """Assemble the derived fields a template needs for one product."""
    resolved_mockups = [
        i
        for i, raw in enumerate(mockup_path_list(product))
        if resolve_product_file(raw, "mockup") is not None
    ]
    label, badge = state_badge(product.state)
    params = _parse_json(product.params, {})
    if not isinstance(params, dict):
        params = {}
    tags = _parse_json(product.tags, [])
    if not isinstance(tags, list):
        tags = []
    summary = ""
    if product.product_type == "picture_book" and params:
        bits = [str(params[k]) for k in ("character", "setting", "moral") if params.get(k)]
        summary = " • ".join(bits)
    swatches = palette_swatches(product_palettes(product))
    bundle_available = (
        len(swatches) >= 2
        and resolve_product_file(product.bundle_path, "bundle") is not None
    )
    return ProductView(
        product=product,
        niche_name=niche_names.get(product.niche_id),
        mockup_indices=resolved_mockups,
        thumb_index=resolved_mockups[0] if resolved_mockups else None,
        pdf_available=resolve_product_file(product.pdf_path, "pdf") is not None,
        params=params,
        tags=[str(t) for t in tags],
        state_label=label,
        badge_class=badge,
        params_summary=summary,
        palettes=swatches,
        bundle_available=bundle_available,
    )


# ---------------------------------------------------------------------------
# PDF page previews
# ---------------------------------------------------------------------------


def select_preview_pages(page_count: int) -> list[int]:
    """Pick 1-based page numbers to preview: the first pages + a later spread."""
    pages = list(range(1, min(PREVIEW_PAGE_LIMIT, page_count) + 1))
    if page_count > PREVIEW_PAGE_LIMIT:
        step = max((page_count - PREVIEW_PAGE_LIMIT) // PREVIEW_EXTRA_SAMPLES, 1)
        extra = range(PREVIEW_PAGE_LIMIT + step, page_count + 1, step)
        pages.extend(list(extra)[:PREVIEW_EXTRA_SAMPLES])
    return sorted(set(pages))


def ensure_previews(product_id: int, pdf_path: Path, preview_root: Path) -> list[int]:
    """Render cached PNG previews for a product's PDF.

    Pages already rendered are skipped. Returns the sorted list of 1-based
    page numbers that have preview images on disk.
    """
    import fitz  # PyMuPDF

    out_dir = preview_root / f"product_{product_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    try:
        pages = select_preview_pages(doc.page_count)
        for number in pages:
            target = out_dir / f"page_{number}.png"
            if target.is_file():
                continue
            pixmap = doc[number - 1].get_pixmap(dpi=PREVIEW_DPI)
            pixmap.save(str(target))
        return pages
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Background generation
# ---------------------------------------------------------------------------


def _run_generation(
    config: dict, session_factory, product_type: str | None = None
) -> None:
    """Thread target: run one pipeline cycle, always releasing the lock."""
    from src.pipeline.orchestrator import PipelineOrchestrator

    try:
        PipelineOrchestrator(config, session_factory).run_once(
            product_type=product_type
        )
    except Exception as exc:  # noqa: BLE001 - background thread must not die loudly
        logger.error("dashboard_generation_failed", error=str(exc), exc_info=True)
    finally:
        _generation_lock.release()


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def _load_default_config() -> dict:
    config_path = PROJECT_ROOT / "config" / "config.yaml"
    with open(config_path) as fh:
        return yaml.safe_load(fh) or {}


def _database_url(config: dict) -> str | None:
    db_path = config.get("paths", {}).get("database")
    if not db_path:
        return None
    resolved = Path(db_path)
    if not resolved.is_absolute():
        resolved = PROJECT_ROOT / resolved
    return f"sqlite:///{resolved}"


def create_app(config: dict | None = None) -> Flask:
    """Create the dashboard Flask app.

    Parameters
    ----------
    config : dict or None
        Parsed config.yaml contents. Defaults to loading
        ``{project_root}/config/config.yaml``.
    """
    if config is None:
        config = _load_default_config()

    app = Flask(__name__)
    app.secret_key = config.get("dashboard", {}).get("secret_key", "product-studio-local")

    # init_db also applies lightweight column migrations for older DBs.
    init_db(_database_url(config))
    session_factory = get_session_factory()

    preview_root = Path(config.get("paths", {}).get("preview_dir", "output/previews"))
    if not preview_root.is_absolute():
        preview_root = PROJECT_ROOT / preview_root

    app.config["APP_CONFIG"] = config
    app.config["SESSION_FACTORY"] = session_factory
    app.config["PREVIEW_ROOT"] = preview_root

    # ---------------- optional password protection ----------------
    # When the dashboard is bound to the LAN (host 0.0.0.0) every device on the
    # WiFi can reach the approve/reject/publish controls. Set DASHBOARD_PASSWORD
    # (and optionally DASHBOARD_USER, default "admin") to require HTTP Basic
    # Auth. If no password is set the dashboard is open -- fine for localhost,
    # risky on a shared network.
    dash_password = os.getenv("DASHBOARD_PASSWORD", "").strip()
    dash_user = os.getenv("DASHBOARD_USER", "admin").strip()

    @app.before_request
    def _require_auth():
        if not dash_password:
            return None
        auth = request.authorization
        if auth and auth.username == dash_user and auth.password == dash_password:
            return None
        return Response(
            "Authentication required.",
            401,
            {"WWW-Authenticate": 'Basic realm="Product Studio"'},
        )

    # ---------------- session per request ----------------

    @app.before_request
    def _open_session() -> None:
        g.db = session_factory()

    @app.teardown_appcontext
    def _close_session(_exc) -> None:
        session = g.pop("db", None)
        if session is not None:
            session.close()

    # ---------------- shared helpers ----------------

    def _niche_names() -> dict[int, str]:
        return {niche.id: niche.name for niche in g.db.query(Niche).all()}

    def _get_product_or_404(product_id: int) -> Product:
        product = ProductRepository(g.db).get(product_id)
        if product is None:
            abort(404)
        return product

    def _safe_next() -> str:
        """Only allow same-app relative redirect targets."""
        target = request.form.get("next", "")
        if target.startswith("/") and not target.startswith("//"):
            return target
        return url_for("index")

    _DECISION_FOR_STATE = {
        ProductState.APPROVED: "approved",
        ProductState.REJECTED: "rejected",
        ProductState.REVIEW_PENDING: "re_review",
    }

    def _apply_review_transition(
        product: Product, new_state: ProductState
    ) -> str | None:
        """Flip state, persist the note, and append a review-feedback event.

        A rejection MUST carry a comment — that reviewer feedback is the
        signal used later to improve generation, so we refuse an empty one.
        """
        note = (request.form.get("note") or "").strip()
        reason = (request.form.get("reason") or "").strip() or None
        if new_state == ProductState.REJECTED and not note:
            return (
                "Please add a comment explaining the rejection — reviewer "
                "feedback is collected to improve future products."
            )
        try:
            ProductStateMachine.transition(product.id, new_state, g.db)
        except ValueError as exc:
            return str(exc)
        ProductRepository(g.db).update(
            product.id,
            review_note=note or product.review_note,
            reviewed_at=datetime.now(timezone.utc),
        )
        # Append-only feedback log (keeps history across re-review cycles).
        try:
            snapshot = json.dumps(
                {
                    "product_type": product.product_type,
                    "title": product.display_title or product.title,
                    "palette": product.palette_name,
                    "params": json.loads(product.params) if product.params else None,
                },
                default=str,
            )
        except (TypeError, ValueError):
            snapshot = None
        ReviewEventRepository(g.db).add(
            product.id,
            _DECISION_FOR_STATE.get(new_state, new_state.value),
            product_type=product.product_type,
            reason=reason,
            comment=note or None,
            params_snapshot=snapshot,
        )
        return None

    def _review_action(
        product_id: int, new_state: ProductState, verb: str
    ) -> "Response":  # noqa: F821 - flask Response
        product = _get_product_or_404(product_id)
        error = _apply_review_transition(product, new_state)
        if error is not None:
            flash(error, "error")
        else:
            flash(f"'{product.display_title or product.title}' {verb}.", "success")
        return redirect(_safe_next())

    def _restore_approved(product_id: int, error: str) -> None:
        """Put a product back to APPROVED after a failed publish-on-approve.

        A failed upload can leave the product UPLOAD_PENDING or FAILED;
        restoring APPROVED keeps the manual Publish button usable as a
        retry.  This moves the product *away* from Etsy (APPROVED is still
        behind the upload gate), so writing the state directly here is safe.
        """
        g.db.expire_all()
        fresh = g.db.get(Product, product_id)
        if fresh is not None and fresh.state != ProductState.APPROVED:
            fresh.state = ProductState.APPROVED
            fresh.error_message = error
            g.db.commit()

    # ---------------- pages ----------------

    @app.get("/")
    def index():
        state_key = request.args.get("state", "all")
        ptype_key = request.args.get("ptype", "all")
        type_filter = ptype_key if ptype_key in ("planner", "picture_book") else None

        repo = ProductRepository(g.db)
        if state_key in STATE_FILTERS:
            products = repo.list_products(
                state=STATE_FILTERS[state_key], product_type=type_filter
            )
        elif state_key == "in_progress":
            products = [
                p
                for p in repo.list_products(product_type=type_filter)
                if p.state in IN_PROGRESS_STATES
            ]
        else:
            state_key = "all"
            products = repo.list_products(product_type=type_filter)

        counts = PipelineMetrics(g.db).count_by_state()
        chips = [
            ("all", "All", sum(counts.values())),
            ("review_pending", "Review pending", counts.get("review_pending", 0)),
            ("approved", "Approved", counts.get("approved", 0)),
            ("rejected", "Rejected", counts.get("rejected", 0)),
            ("published", "Published", counts.get("published", 0)),
            ("failed", "Failed", counts.get("failed", 0)),
            (
                "in_progress",
                "In progress",
                sum(counts.get(s.value, 0) for s in IN_PROGRESS_STATES),
            ),
        ]

        niche_names = _niche_names()
        views = [build_product_view(p, niche_names) for p in products]
        return render_template(
            "index.html",
            views=views,
            chips=chips,
            state_filter=state_key,
            ptype_filter=ptype_key,
            generation_running=_generation_lock.locked(),
            ProductState=ProductState,
        )

    @app.get("/product/<int:product_id>")
    def product_detail(product_id: int):
        product = _get_product_or_404(product_id)
        view = build_product_view(product, _niche_names())

        preview_pages: list[int] = []
        pdf_path = resolve_product_file(product.pdf_path, "pdf")
        if pdf_path is not None:
            try:
                preview_pages = ensure_previews(product.id, pdf_path, preview_root)
            except Exception as exc:  # noqa: BLE001 - preview failure must not 500
                logger.warning(
                    "preview_render_failed", product_id=product.id, error=str(exc)
                )

        pdf_size = None
        if pdf_path is not None:
            pdf_size = pdf_path.stat().st_size
        elif product.file_size_bytes:
            pdf_size = product.file_size_bytes

        listing = EtsyListingRepository(g.db).get_by_product(product.id)
        history = ReviewEventRepository(g.db).list_for_product(product.id)
        return render_template(
            "detail.html",
            view=view,
            p=product,
            preview_pages=preview_pages,
            pdf_size=pdf_size,
            listing=listing,
            history=history,
            review_reasons=REVIEW_REASONS,
            reason_labels=_REVIEW_REASON_LABELS,
            decision_labels=_DECISION_LABELS,
            ProductState=ProductState,
        )

    @app.get("/feedback")
    def feedback():
        """Collected reviewer feedback across all products — the log to mine
        later (especially rejections) to improve generation."""
        decision_key = request.args.get("decision", "rejected")
        valid = {"approved", "rejected", "re_review"}
        decision = decision_key if decision_key in valid else None
        repo = ReviewEventRepository(g.db)
        events = repo.list_all(decision=decision, limit=500)
        counts = repo.counts_by_decision()
        niche_names = _niche_names()
        products = {p.id: p for p in ProductRepository(g.db).list_products()}
        rows = []
        for ev in events:
            prod = products.get(ev.product_id)
            rows.append(
                {
                    "event": ev,
                    "title": (
                        (prod.display_title or prod.title)
                        if prod is not None
                        else f"Product #{ev.product_id}"
                    ),
                    "niche": (
                        niche_names.get(prod.niche_id, "") if prod is not None else ""
                    ),
                    "reason_label": _REVIEW_REASON_LABELS.get(ev.reason or "", ev.reason or ""),
                    "decision_label": _DECISION_LABELS.get(ev.decision, ev.decision),
                }
            )
        chips = [
            ("rejected", "Rejected", counts.get("rejected", 0)),
            ("approved", "Approved", counts.get("approved", 0)),
            ("re_review", "Re-opened", counts.get("re_review", 0)),
            ("all", "All", sum(counts.values())),
        ]
        return render_template(
            "feedback.html",
            rows=rows,
            chips=chips,
            decision_filter=decision_key if decision else "all",
        )

    # ---------------- review actions ----------------

    @app.post("/product/<int:product_id>/approve")
    def approve(product_id: int):
        """Approve a product; approval is the manual gate before Etsy.

        When uploads are enabled and etsy.publish_on_approve is true, the
        product is published in the same request. Any publish failure leaves
        it APPROVED so the manual Publish button works as a retry.
        """
        product = _get_product_or_404(product_id)
        error = _apply_review_transition(product, ProductState.APPROVED)
        if error is not None:
            flash(error, "error")
            return redirect(_safe_next())

        title = product.display_title or product.title

        from src.pipeline.orchestrator import (
            PipelineOrchestrator,
            _etsy_upload_enabled,
        )

        if not _etsy_upload_enabled(config):
            flash(
                f"'{title}' approved. Etsy uploads are currently disabled — "
                "the product will need publishing once Etsy access is enabled.",
                "info",
            )
            return redirect(_safe_next())

        if not config.get("etsy", {}).get("publish_on_approve", True):
            flash(f"'{title}' approved.", "success")
            return redirect(_safe_next())

        orchestrator = PipelineOrchestrator(config, session_factory)
        try:
            orchestrator.publish_approved(product_id)
        except Exception as exc:  # noqa: BLE001 - approval must survive publish failures
            logger.warning(
                "publish_on_approve_failed", product_id=product_id, error=str(exc)
            )
            _restore_approved(product_id, str(exc))
            flash(
                f"'{title}' approved, but publishing failed: {exc} "
                "Use the Publish button to retry.",
                "warning",
            )
            return redirect(_safe_next())

        g.db.expire_all()  # publish used its own session; drop stale state
        listing = EtsyListingRepository(g.db).get_by_product(product_id)
        if listing is not None and listing.etsy_url:
            flash(
                f"'{title}' approved and published to Etsy: {listing.etsy_url}",
                "success",
            )
        else:
            flash(f"'{title}' approved and published to Etsy.", "success")
        return redirect(_safe_next())

    @app.post("/product/<int:product_id>/reject")
    def reject(product_id: int):
        return _review_action(product_id, ProductState.REJECTED, "rejected")

    @app.post("/product/<int:product_id>/re-review")
    def re_review(product_id: int):
        return _review_action(
            product_id, ProductState.REVIEW_PENDING, "sent back for review"
        )

    @app.post("/product/<int:product_id>/edit")
    def edit_listing(product_id: int):
        """Let the reviewer edit the Etsy listing fields before publishing.

        Editable only while REVIEW_PENDING or APPROVED — never after the
        product is PUBLISHED. The reviewer's tags (etc.) are what publishing
        later sends to Etsy, so this input wins over the auto-generated SEO.
        """
        product = _get_product_or_404(product_id)
        detail_url = url_for("product_detail", product_id=product_id)

        if product.state not in (ProductState.REVIEW_PENDING, ProductState.APPROVED):
            flash(
                "Listing details can only be edited while a product is "
                "pending review or approved.",
                "error",
            )
            return redirect(detail_url)

        title = (request.form.get("title") or "").strip()
        description = (request.form.get("description") or "").strip()
        raw_tags = request.form.get("tags") or ""
        raw_price = (request.form.get("price_usd") or "").strip()

        if not title:
            flash("Title is required.", "error")
            return redirect(detail_url)
        if len(title) > 140:
            flash("Title must be 140 characters or fewer.", "error")
            return redirect(detail_url)

        tags, tag_error = _parse_tags(raw_tags)
        if tag_error is not None:
            flash(tag_error, "error")
            return redirect(detail_url)

        try:
            price = float(raw_price)
        except (TypeError, ValueError):
            flash("Price must be a number greater than 0.", "error")
            return redirect(detail_url)
        if price <= 0:
            flash("Price must be greater than 0.", "error")
            return redirect(detail_url)

        ProductRepository(g.db).update(
            product.id,
            title=title,
            description=description,
            tags=json.dumps(tags),
            price_usd=price,
        )
        flash("Listing details updated.", "success")
        return redirect(detail_url)

    @app.post("/product/<int:product_id>/publish")
    def publish(product_id: int):
        product = _get_product_or_404(product_id)
        if product.state != ProductState.APPROVED:
            flash("Only approved products can be published.", "error")
            return redirect(url_for("product_detail", product_id=product_id))

        from src.pipeline.orchestrator import PipelineOrchestrator

        orchestrator = PipelineOrchestrator(config, session_factory)
        try:
            orchestrator.publish_approved(product_id)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the reviewer
            logger.warning("publish_failed", product_id=product_id, error=str(exc))
            flash(str(exc), "error")
            return redirect(url_for("product_detail", product_id=product_id))

        g.db.expire_all()  # publish used its own session; drop stale state
        listing = EtsyListingRepository(g.db).get_by_product(product_id)
        if listing is not None and listing.etsy_url:
            flash(f"Published to Etsy: {listing.etsy_url}", "success")
        else:
            flash("Published to Etsy.", "success")
        return redirect(url_for("product_detail", product_id=product_id))

    # ---------------- generation ----------------

    @app.post("/generate")
    def generate():
        raw_type = (request.form.get("type") or "").strip()
        product_type = raw_type if raw_type in ("planner", "picture_book") else None
        if not _generation_lock.acquire(blocking=False):
            flash("Generation is already running — give it a minute.", "info")
            return redirect(url_for("index"))
        thread = threading.Thread(
            target=_run_generation,
            args=(config, session_factory, product_type),
            daemon=True,
            name="dashboard-generate",
        )
        thread.start()
        label = {"planner": "Planner", "picture_book": "Picture book"}.get(
            product_type, "Product"
        )
        flash(f"{label} generation started — refresh in a minute.", "success")
        return redirect(url_for("index"))

    # ---------------- file serving (integer ids only) ----------------

    @app.get("/files/pdf/<int:product_id>")
    def serve_pdf(product_id: int):
        product = _get_product_or_404(product_id)
        pdf_path = resolve_product_file(product.pdf_path, "pdf")
        if pdf_path is None:
            abort(404)
        return send_file(
            pdf_path,
            mimetype="application/pdf",
            as_attachment=False,
            download_name=pdf_path.name,
        )

    @app.get("/files/bundle/<int:product_id>")
    def serve_bundle(product_id: int):
        """Download the multi-palette colour bundle ZIP (read-only)."""
        product = _get_product_or_404(product_id)
        bundle_path = resolve_product_file(product.bundle_path, "bundle")
        if bundle_path is None:
            abort(404)
        return send_file(
            bundle_path,
            mimetype="application/zip",
            as_attachment=True,
            download_name=bundle_path.name,
        )

    @app.get("/files/mockup/<int:product_id>/<int:idx>")
    def serve_mockup(product_id: int, idx: int):
        product = _get_product_or_404(product_id)
        mockups = mockup_path_list(product)
        if idx < 0 or idx >= len(mockups):
            abort(404)
        mockup_path = resolve_product_file(mockups[idx], "mockup")
        if mockup_path is None:
            abort(404)
        return send_file(mockup_path)

    @app.get("/files/preview/<int:product_id>/<int:page>")
    def serve_preview(product_id: int, page: int):
        _get_product_or_404(product_id)
        target = preview_root / f"product_{product_id}" / f"page_{page}.png"
        if not target.is_file():
            abort(404)
        return send_file(target)

    return app
