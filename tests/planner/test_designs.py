"""Design registry integrity + constraint matrix + themed generation smoke.

Runtime discipline: themed planners are generated once per module (small
spec, no weeklies) and shared across the assertion tests.
"""

from __future__ import annotations

import calendar as _cal

import fitz
import pytest

from src.planner.designs import (
    DIMENSIONS,
    PRESET_PALETTES,
    PRESETS,
    DesignTheme,
    get_design,
    resolve_design,
    validate_design,
)
from src.planner.generator import PlannerGenerator, PlannerSpec
from src.planner.layout import build_geometry
from src.planner.motifs import MOTIFS
from src.planner.styles import CONTAINERS, INKS, VOICES


# ---------------------------------------------------------------------------
# Registry integrity
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_default_design_is_classic(self):
        assert DesignTheme() == PRESETS["classic"]
        assert get_design("classic") == DesignTheme()
        assert get_design() == DesignTheme()

    def test_all_presets_validate_unchanged(self):
        for name, preset in PRESETS.items():
            assert validate_design(preset) == preset, (
                f"preset '{name}' hits a constraint fallback"
            )

    def test_all_presets_resolve_by_id(self):
        for name in PRESETS:
            d = get_design(name)
            assert d.name == name

    def test_preset_dimensions_are_legal(self):
        for name, preset in PRESETS.items():
            for dim, allowed in DIMENSIONS.items():
                assert getattr(preset, dim) in allowed, f"{name}.{dim}"

    def test_every_variant_is_backed_by_code(self):
        from src.planner.navigation import SHELLS
        from src.planner.pages import (
            COVER_VARIANTS,
            MONTHLY_VARIANTS,
            WEEKLY_VARIANTS,
        )

        assert set(DIMENSIONS["shell"]) == set(SHELLS)
        assert set(DIMENSIONS["interior"]) == set(WEEKLY_VARIANTS)
        assert set(DIMENSIONS["interior"]) == set(MONTHLY_VARIANTS)
        assert set(DIMENSIONS["motif"]) == set(MOTIFS) == set(CONTAINERS)
        assert set(DIMENSIONS["voice"]) == set(VOICES)
        assert set(DIMENSIONS["ink"]) == set(INKS)
        assert set(DIMENSIONS["cover"]) == set(COVER_VARIANTS)
        for shell in DIMENSIONS["shell"]:
            geo = build_geometry(shell)
            assert geo.left_w >= 190 and geo.right_w >= 190

    def test_recommended_palettes_exist(self):
        from src.planner.styles import get_palettes

        palettes = get_palettes()
        assert set(PRESET_PALETTES) == set(PRESETS)
        for names in PRESET_PALETTES.values():
            for n in names:
                assert n in palettes

    def test_binder_geometry_matches_module_constants(self):
        import src.planner.layout as L

        geo = build_geometry("binder")
        assert geo.header_y == L.HEADER_Y
        assert geo.header_h == L.HEADER_HEIGHT
        assert geo.body_y == L.BODY_Y
        assert geo.body_bottom == L.BODY_BOTTOM
        assert geo.footer_y == L.FOOTER_Y
        assert geo.left_x == L.LEFT_CONTENT_X
        assert geo.left_w == L.LEFT_CONTENT_WIDTH
        assert geo.right_x == L.RIGHT_CONTENT_X
        assert geo.right_w == L.RIGHT_CONTENT_WIDTH
        assert geo.left_body() == L.left_body()
        assert geo.right_body() == L.right_body()
        assert geo.calendar_grid() == L.calendar_grid()
        assert geo.weekday_header_metrics() == L.weekday_header_metrics()


# ---------------------------------------------------------------------------
# Constraint matrix
# ---------------------------------------------------------------------------

class TestConstraints:
    @pytest.mark.parametrize(
        "illegal,expected_field,expected_value",
        [
            (dict(voice="script", shell="poster"), "voice", "serif"),
            (dict(voice="script", ink="filled-blocks"), "ink", "soft-wash"),
            (dict(voice="typewriter", ink="filled-blocks"), "ink", "ink-on-paper"),
            (dict(cover="pattern", motif="minimal"), "cover", "editorial"),
            (dict(interior="airy", ink="filled-blocks"), "ink", "soft-wash"),
            (dict(motif="minimal", texture="blank"), "texture", "ruled"),
            (dict(interior="airy", texture="blank"), "texture", "ruled"),
            (dict(motif="celestial", texture="graph"), "texture", "dot"),
        ],
    )
    def test_each_rule_falls_back(self, illegal, expected_field, expected_value):
        d = DesignTheme(**illegal)
        fixed, subs = resolve_design(d)
        assert getattr(fixed, expected_field) == expected_value
        assert len(subs) >= 1

    def test_validate_never_raises_on_garbage(self):
        d = DesignTheme(shell="spaceship", voice="yodel", texture="fur")
        fixed = validate_design(d)
        assert fixed.shell == "binder"
        assert fixed.voice == "classic"
        assert fixed.texture == "dot"

    def test_get_design_repairs_bad_overrides(self):
        d = get_design("classic", {"ink": "molten-lava", "bogus_dim": "x"})
        assert d.ink == "soft-wash"

    def test_custom_combo_gets_custom_name(self):
        d = get_design("classic", {"shell": "poster"})
        assert d.name.startswith("custom-poster-")

    def test_deliberately_illegal_combo_chain(self):
        # script+poster+filled-blocks+pattern+minimal -> 3+ substitutions
        d = DesignTheme(voice="script", shell="poster", ink="filled-blocks",
                        cover="pattern", motif="minimal")
        fixed, subs = resolve_design(d)
        assert fixed.voice == "serif"          # rule 1
        assert fixed.cover == "editorial"      # rule 4
        assert fixed.ink == "filled-blocks"    # rules 2/3 no longer match
        assert len(subs) >= 2
        assert validate_design(fixed) == fixed  # result is stable/legal


# ---------------------------------------------------------------------------
# Themed generation smoke (module-scoped builds, small spec)
# ---------------------------------------------------------------------------

SMOKE_PRESETS = ["classic", "atelier", "studio", "gallery", "noir"]


def _small_spec(**kwargs) -> PlannerSpec:
    base = dict(
        title="2026 Budget Planner",
        display_title="2026 Budget Planner",
        subtitle="Plan | Track | Achieve",
        year=2026,
        palette_name="classic_boho",
        include_weekly=False,
        include_daily=False,
        niche_slug="budget_planner",
    )
    base.update(kwargs)
    return PlannerSpec(**base)


@pytest.fixture(scope="module")
def themed_docs(tmp_path_factory):
    """{preset: (path, fitz.Document)} for the smoke presets."""
    import src.planner.generator as gen_mod

    out_dir = tmp_path_factory.mktemp("themed")
    original = gen_mod.OUTPUT_DIR
    gen_mod.OUTPUT_DIR = out_dir
    docs = {}
    try:
        for preset in SMOKE_PRESETS:
            path = PlannerGenerator().generate(_small_spec(design=preset))
            docs[preset] = (path, fitz.open(str(path)))
    finally:
        gen_mod.OUTPUT_DIR = original
    yield docs
    for _path, doc in docs.values():
        doc.close()


class TestThemedGeneration:
    def test_page_counts_match_classic(self, themed_docs):
        classic_len = len(themed_docs["classic"][1])
        assert classic_len == 3 + 36 + 6 + 3
        for preset, (_p, doc) in themed_docs.items():
            assert len(doc) == classic_len, preset

    def test_filenames(self, themed_docs):
        assert themed_docs["classic"][0].name == \
            "2026_budget_planner_classic_boho.pdf"
        assert themed_docs["studio"][0].name == \
            "2026_budget_planner_classic_boho_studio.pdf"

    def test_page_size_and_file_size(self, themed_docs):
        for preset, (path, doc) in themed_docs.items():
            assert path.stat().st_size < 20 * 1024 * 1024, preset
            for page in doc:
                assert abs(page.rect.width - 1366) < 0.5
                assert abs(page.rect.height - 1024) < 0.5

    def test_every_page_has_valid_links(self, themed_docs):
        for preset, (_p, doc) in themed_docs.items():
            for idx in range(1, len(doc)):   # cover has none by design
                links = [l for l in doc[idx].get_links()
                         if l["kind"] == fitz.LINK_GOTO]
                assert len(links) > 0, f"{preset} page {idx} has no links"
                for link in links:
                    assert 0 <= link["page"] < len(doc), f"{preset} p{idx}"
                    r = link["from"]
                    assert 0 <= r.x0 <= r.x1 <= 1366.5
                    assert 0 <= r.y0 <= r.y1 <= 1024.5

    def test_index_and_year_glance_targets(self, themed_docs):
        for preset, (_p, doc) in themed_docs.items():
            for page_idx in (1, 2):
                targets = {
                    l["page"] for l in doc[page_idx].get_links()
                    if l["kind"] == fitz.LINK_GOTO
                }
                assert len(targets) >= 12, f"{preset} page {page_idx}"

    def test_outline_counts_match_classic(self, themed_docs):
        classic_toc = themed_docs["classic"][1].get_toc()
        assert len(classic_toc) > 0
        for preset, (_p, doc) in themed_docs.items():
            toc = doc.get_toc()
            assert len(toc) == len(classic_toc), preset
            for _lvl, _title, page in toc:
                assert 1 <= page <= len(doc), preset

    def test_text_extraction_clean(self, themed_docs):
        for preset, (_p, doc) in themed_docs.items():
            march_idx = 3 + 2 * 3   # cover/index/year + 2 month blocks
            march_text = doc[march_idx].get_text()
            # Letter-spaced small caps may extract with spaces between
            # glyphs (honest tracking, not corruption) -- normalize.
            squashed = march_text.replace(" ", "")
            assert "March" in march_text or "MARCH" in squashed, preset
            for idx in (0, 1, march_idx):
                text = doc[idx].get_text()
                assert "�" not in text, f"{preset} page {idx}"
            cover_squashed = doc[0].get_text().replace(" ", "")
            assert "BudgetPlanner" in cover_squashed \
                or "BUDGETPLANNER" in cover_squashed, preset

    def test_month_names_in_outline(self, themed_docs):
        for preset, (_p, doc) in themed_docs.items():
            titles = [t[1] for t in doc.get_toc()]
            assert "Cover" in titles
            for m in range(1, 13):
                assert _cal.month_name[m] in titles, preset


# ---------------------------------------------------------------------------
# Search integrity: tracking must never break word extraction
# ---------------------------------------------------------------------------
#
# Empirical (see styles.SEARCHABLE_TRACKING_RATIO): MuPDF splits words once
# char spacing exceeds ~0.142 x font size, so 'January' extracts as
# 'J A N U A R Y' and buyer search gets zero hits.


class TestSearchableTracking:
    def test_voice_tables_within_budget(self):
        from src.planner.styles import (
            SEARCHABLE_ROLES,
            SEARCHABLE_TRACKING_RATIO,
        )

        for voice, roles in VOICES.items():
            for role, spec in roles.items():
                if role in SEARCHABLE_ROLES:
                    assert spec.tracking <= (
                        SEARCHABLE_TRACKING_RATIO * spec.size + 1e-9
                    ), (f"{voice}.{role}: tracking {spec.tracking} breaks "
                        f"extraction at {spec.size}pt")

    def test_helper_clamps_above_budget_only(self):
        from src.planner.styles import searchable_tracking

        assert searchable_tracking(7, 1.2) == pytest.approx(0.84)
        assert searchable_tracking(10, 0.5) == 0.5


@pytest.fixture(scope="module")
def january_docs(tmp_path_factory):
    """{preset: fitz.Document} -- trimmed builds (no weeklies/extras) with
    monthly plan + review kept, one per preset.  Page 3 is the January
    monthly calendar and page 4 the January monthly plan."""
    import src.planner.generator as gen_mod

    out_dir = tmp_path_factory.mktemp("january")
    original = gen_mod.OUTPUT_DIR
    gen_mod.OUTPUT_DIR = out_dir
    docs = {}
    try:
        for preset in PRESETS:
            spec = _small_spec(
                design=preset,
                palette_name=PRESET_PALETTES[preset][0],
                include_notes=False, include_habits=False,
                include_goals=False, include_niche_pages=False,
            )
            path = PlannerGenerator().generate(spec)
            docs[preset] = fitz.open(str(path))
    finally:
        gen_mod.OUTPUT_DIR = original
    yield docs
    for doc in docs.values():
        doc.close()


JAN_MONTHLY = 3   # cover, index, year glance, January monthly calendar
JAN_PLAN = 4


class TestJanuarySearchable:
    """Buyers must be able to search month names on every theme."""

    @pytest.mark.parametrize("preset", sorted(PRESETS))
    def test_search_finds_january_on_monthly_page(self, january_docs, preset):
        page = january_docs[preset][JAN_MONTHLY]
        assert len(page.search_for("January")) > 0, (
            f"{preset}: search_for('January') has no hit on the January "
            f"monthly page -- letter-spaced title split the word?")

    @pytest.mark.parametrize("preset", sorted(PRESETS))
    def test_january_extracts_word_intact(self, january_docs, preset):
        text = january_docs[preset][JAN_MONTHLY].get_text()
        assert "January" in text or "JANUARY" in text, (
            f"{preset}: 'January' not word-intact in extraction")


class TestQuickLinkDedupe:
    """The corner action button and any quick-link stack must not render
    two buttons targeting the same page on one card edge."""

    @pytest.mark.parametrize("preset", sorted(PRESETS))
    def test_single_link_to_monthly_plan(self, january_docs, preset):
        page = january_docs[preset][JAN_MONTHLY]
        to_plan = [l for l in page.get_links()
                   if l["kind"] == fitz.LINK_GOTO and l["page"] == JAN_PLAN]
        assert len(to_plan) == 1, (
            f"{preset}: {len(to_plan)} links to the monthly plan on the "
            f"monthly page (corner button + duplicate quick link?)")


# ---------------------------------------------------------------------------
# Cover composition: any two preset covers must read as different products
# ---------------------------------------------------------------------------


def _cover_only_pdf(preset: str) -> bytes:
    """Render just the cover page for *preset* (fast, no full build)."""
    from fpdf import FPDF

    from src.planner.navigation import NavigationManager
    from src.planner.pages import CoverPage, PageContext
    from src.planner.styles import build_theme

    pdf = FPDF(unit="mm", format=(482.0, 361.2))
    pdf.set_auto_page_break(auto=False)
    pdf.set_margin(0)
    design = get_design(preset)
    theme = build_theme(pdf, PRESET_PALETTES[preset][0], design)
    nav = NavigationManager()
    ctx = PageContext(theme=theme, nav=nav, tabs=[], year=2026,
                      design=design, geo=build_geometry(design.shell),
                      motif=MOTIFS[design.motif])
    nav.register_link(pdf, NavigationManager.cover_key())
    CoverPage.render(pdf, ctx, title="2026 Budget Planner",
                     display_title="2026 Budget Planner",
                     subtitle="Plan | Track | Achieve",
                     niche_name="Budget Planner")
    return bytes(pdf.output())


@pytest.fixture(scope="module")
def cover_docs():
    docs = {p: fitz.open(stream=_cover_only_pdf(p), filetype="pdf")
            for p in PRESETS}
    yield docs
    for doc in docs.values():
        doc.close()


def _ink_mask(doc) -> list[bool]:
    """Hue-blind ink map: which low-res pixels depart from the page's
    dominant tone.  Recolors of one composition produce ~identical masks."""
    pix = doc[0].get_pixmap(dpi=8, colorspace=fitz.csGRAY)
    px = list(pix.samples)
    median = sorted(px)[len(px) // 2]
    return [abs(p - median) > 28 for p in px]


class TestCoverCompositions:
    def test_all_pairs_visually_distinct(self, cover_docs):
        """Ink-mask Jaccard distance between every pair of preset covers.

        Recolors of one composition score < 0.05 (the pre-fix band covers
        scored 0.00-0.02); the closest legitimate pair (atelier vs
        midnight, which share the pattern-band skeleton but differ in
        motif artwork: scallop tile vs starfield) scores ~0.31.  Hue
        difference alone can never pass this."""
        import itertools

        masks = {p: _ink_mask(d) for p, d in cover_docs.items()}
        for a, b in itertools.combinations(sorted(PRESETS), 2):
            inter = sum(1 for x, y in zip(masks[a], masks[b]) if x and y)
            union = sum(1 for x, y in zip(masks[a], masks[b]) if x or y)
            distance = 1 - (inter / union if union else 0.0)
            assert distance > 0.2, (
                f"covers '{a}' and '{b}' share a near-identical composition "
                f"(ink-mask Jaccard distance {distance:.3f})")

    @staticmethod
    def _primary_fills(doc, palette_name: str, field: str = "primary"):
        from src.planner.styles import get_palette

        want = tuple(v / 255 for v in get_palette(palette_name).rgb(field))
        out = []
        for d in doc[0].get_drawings():
            fill = d.get("fill")
            if fill is not None and all(
                    abs(x - y) <= 0.02 for x, y in zip(fill, want)):
                out.append(d["rect"])
        return out

    def test_band_covers_have_four_structures(self, cover_docs):
        """The ink-keyed band mapping (designs.py): left band / top band /
        accent spine / full-bleed plate -- page is 1366.3 x 1024.1 pt."""
        rects = self._primary_fills(cover_docs["riviera"],
                                    PRESET_PALETTES["riviera"][0])
        assert any(r.x0 < 2 and 460 < r.x1 < 500 and r.y1 > 1015
                   for r in rects), "riviera: wide left band missing"

        rects = self._primary_fills(cover_docs["ledger"],
                                    PRESET_PALETTES["ledger"][0])
        assert any(r.y0 < 2 and 150 < r.y1 < 210 and r.x1 > 1360
                   for r in rects), "ledger: slim top band missing"

        rects = self._primary_fills(cover_docs["blueprint"],
                                    PRESET_PALETTES["blueprint"][0],
                                    field="accent")
        assert any(r.x0 < 2 and 50 < r.x1 < 75 and r.y1 > 1015
                   for r in rects), "blueprint: accent spine missing"

        rects = self._primary_fills(cover_docs["noir"],
                                    PRESET_PALETTES["noir"][0])
        assert any(r.x1 > 1360 and r.y1 > 1015
                   for r in rects), "noir: full-bleed plate missing"

    @pytest.mark.parametrize("preset,floor", [
        ("riviera", 150), ("ledger", 70), ("blueprint", 20), ("noir", 25),
    ])
    def test_band_covers_render_motif_artwork(self, cover_docs, preset,
                                              floor):
        """Band covers must express the motif family visibly (measured
        against calibrated vector-item counts: 291/141/31/47)."""
        n = len(cover_docs[preset][0].get_drawings())
        assert n >= floor, (
            f"{preset} cover renders too little artwork ({n} vector items "
            f"< {floor}) -- motif dimension invisible?")


# ---------------------------------------------------------------------------
# Motif slots: every slot draws without raising, within op budgets
# ---------------------------------------------------------------------------

class TestMotifSlots:
    @pytest.fixture(scope="class")
    def scratch_pdf(self):
        from fpdf import FPDF

        from src.planner.styles import build_theme

        pdf = FPDF(unit="mm", format=(482.0, 361.2))
        pdf.set_auto_page_break(auto=False)
        pdf.set_margin(0)
        theme = build_theme(pdf, "neutral_beige")
        return pdf, theme

    def _ops(self, pdf) -> int:
        return bytes(pdf.pages[pdf.page].contents).count(b"\n")

    @pytest.mark.parametrize("motif_name", sorted(MOTIFS))
    def test_slots_draw_within_budget(self, scratch_pdf, motif_name):
        pdf, theme = scratch_pdf
        motif = MOTIFS[motif_name]
        pdf.add_page()
        pdf.set_font(theme.body, "", 8)

        before = self._ops(pdf)
        motif.corner(pdf, theme, 12, 12, 22, "TL")
        motif.corner(pdf, theme, 470, 349, 22, "BR")
        motif.divider(pdf, theme, 241, 100, 84)
        motif.bullet(pdf, theme, 30, 120, 4.4, number=1)
        motif.band(pdf, theme, 21, 140, 208)
        assert self._ops(pdf) - before < 800, "slot ops runaway"

        before = self._ops(pdf)
        motif.cover_hero(pdf, theme, seed="2026-test-cover")
        assert self._ops(pdf) - before < 1500, "cover hero ops runaway"

        before = self._ops(pdf)
        motif.pattern_fill(pdf, theme, 0, 0, 482.0, 361.2,
                           seed="2026-test-pattern")
        assert self._ops(pdf) - before < 4000, "pattern ops runaway"

    def test_scatter_is_deterministic(self):
        # Same seed in two fresh documents -> identical drawing ops.
        # (Graphics-state names increment per document, so the comparison
        # must use separate FPDF instances.)
        from fpdf import FPDF

        from src.planner.styles import build_theme

        def draw() -> bytes:
            pdf = FPDF(unit="mm", format=(482.0, 361.2))
            pdf.set_auto_page_break(auto=False)
            pdf.set_margin(0)
            theme = build_theme(pdf, "neutral_beige")
            pdf.add_page()
            MOTIFS["celestial"].pattern_fill(pdf, theme, 0, 0, 482.0, 361.2,
                                             seed="2026-x")
            return bytes(pdf.pages[pdf.page].contents)

        assert draw() == draw()
