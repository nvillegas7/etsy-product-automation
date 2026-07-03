"""Color palettes, font configuration, and the design-aware Theme.

The :class:`Theme` bundles palette + fonts + the resolved
:class:`~src.planner.designs.DesignTheme` and exposes:

* **type roles** (``set_type`` / ``text``): every voice's family / size /
  case / tracking table lives here -- including the two font hacks that
  must never leak out (Inter Light is registered under style ``"I"``, and
  ``PlannerDisplay "B"`` maps to the same glyphs as Regular).
* **ink methods** (``band_fill`` / ``box_fill`` / ``border_c`` / ``rule_c``
  / ``structural`` / ``desk_c`` / ``paper_c``): the palette-architecture
  layer that replaces the old free color helpers in ``widgets.py``.
"""

import logging
import urllib.request
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

import yaml

from src.planner.designs import DesignTheme

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Color primitives (canonical home; widgets re-exports for compatibility)
# ---------------------------------------------------------------------------

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)


def blend(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    """Linear blend between two RGB tuples.  t=0 -> c1, t=1 -> c2."""
    return (
        round(c1[0] + (c2[0] - c1[0]) * t),
        round(c1[1] + (c2[1] - c1[1]) * t),
        round(c1[2] + (c2[2] - c1[2]) * t),
    )

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES_PATH = PROJECT_ROOT / "config" / "templates.yaml"
FONTS_DIR = PROJECT_ROOT / "src" / "planner" / "fonts"

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ColorPalette:
    """A complete color scheme for a planner."""

    name: str
    background: str
    primary: str
    secondary: str
    accent: str
    text: str
    text_light: str
    grid_line: str
    tab_active: str
    tab_inactive: str

    # Convenience helpers ------------------------------------------------

    @staticmethod
    def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
        """Convert '#RRGGBB' to (r, g, b) ints."""
        h = hex_color.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    def rgb(self, field: str) -> tuple[int, int, int]:
        """Return the RGB tuple for a named color field."""
        return self.hex_to_rgb(getattr(self, field))


@dataclass(frozen=True)
class FontConfig:
    """Font family + standard sizes."""

    family: str
    regular_file: str
    bold_file: str
    light_file: str
    size_title: int
    size_subtitle: int
    size_heading: int
    size_body: int
    size_small: int
    size_tab: int
    # Display / script accents (with safe defaults for older templates.yaml)
    display_family: str = "PlannerDisplay"
    display_regular_file: str = "DisplaySerif-Regular.ttf"
    display_bold_file: str = "DisplaySerif-Bold.ttf"
    script_family: str = "PlannerScript"
    script_regular_file: str = "ScriptAccent-Regular.ttf"
    size_display_title: float = 46
    size_page_title: float = 19
    size_section: float = 8.5
    size_pennant: float = 15


# ---------------------------------------------------------------------------
# Ink specs (palette architecture)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InkSpec:
    """How color is deployed: band/box fills, borders, structural color."""

    name: str
    band: str            # "wash" | "none" | "solid" | "grey"
    box: str             # "wash" | "none" | "deep"
    border_mix: str      # "primary" | "text" | "solid-primary"
    border_t: float      # blend amount for grid_line -> border_mix
    border_width: float
    rules: str           # "grid" | "text-mix"
    zebra: bool
    structural: str      # "primary" | "text"
    desk_t: float        # blend amount background -> secondary for the desk
    accent_bullets: bool  # priority bullets carry the accent color
    accent_active: bool   # active nav pill/tab uses solid accent


INKS: dict[str, InkSpec] = {
    "soft-wash": InkSpec("soft-wash", band="wash", box="wash",
                         border_mix="primary", border_t=0.35, border_width=0.3,
                         rules="grid", zebra=False, structural="primary",
                         desk_t=0.75, accent_bullets=False, accent_active=False),
    "ink-on-paper": InkSpec("ink-on-paper", band="none", box="none",
                            border_mix="text", border_t=0.45, border_width=0.35,
                            rules="text-mix", zebra=False, structural="text",
                            desk_t=0.45, accent_bullets=False, accent_active=False),
    "filled-blocks": InkSpec("filled-blocks", band="solid", box="deep",
                             border_mix="solid-primary", border_t=0.0,
                             border_width=0.3, rules="grid", zebra=True,
                             structural="primary", desk_t=0.85,
                             accent_bullets=False, accent_active=True),
    "accent-pop": InkSpec("accent-pop", band="grey", box="none",
                          border_mix="text", border_t=0.35, border_width=0.3,
                          rules="grid", zebra=False, structural="text",
                          desk_t=0.75, accent_bullets=True, accent_active=True),
}


#: motif -> container style consumed by widgets
CONTAINERS: dict[str, str] = {
    "botanical": "soft_rounded",
    "geometric": "squared_hairline",
    "celestial": "ticked_corners",
    "coastal": "soft_rounded",
    "minimal": "open_air",
}


# ---------------------------------------------------------------------------
# Voice role tables (typography)
# ---------------------------------------------------------------------------

#: Extraction-safe tracking budget, as a fraction of the font size.
#:
#: Empirical (fpdf2 2.8.7 + PyMuPDF 1.28, all embedded faces + Courier,
#: sizes 5.5-44 pt): MuPDF splits a run into per-glyph "words" once
#: ``set_char_spacing`` exceeds ~0.142 x font size -- 'January' then
#: extracts as 'J A N U A R Y' and ``search_for('January')`` gets zero
#: hits.  0.12 keeps a ~15% safety margin below the observed break point.
#:
#: SEARCHABLE text (page titles, month names, weekday/date labels,
#: section/band labels) must stay at or below this ratio; purely
#: decorative labels that duplicate no unique content (footer category
#: rows, cover taglines, the letterspaced cover display title) may
#: exceed it.
SEARCHABLE_TRACKING_RATIO = 0.12

#: Roles whose text buyers search for (GoodNotes search / storefront
#: keywords): tracking on these is clamped in :meth:`Theme.set_type`.
#: ``display_title`` / ``cover_subtitle`` stay decorative by design.
SEARCHABLE_ROLES = frozenset({
    "page_title", "page_subtitle", "section_label", "band_label",
    "calendar_digit", "mini_digit", "inline_label", "cover_year",
})


def searchable_tracking(size: float, tracking: float) -> float:
    """Clamp *tracking* to the extraction-safe budget for *size*."""
    return min(tracking, SEARCHABLE_TRACKING_RATIO * size)


@dataclass(frozen=True)
class RoleSpec:
    """One type role: family key, fpdf style, size pt, case, tracking pt."""

    family: str    # "body" | "display" | "script" | "courier"
    style: str     # "" | "B" | "I"  ("I" means Inter Light for body)
    size: float
    case: str = "as-given"   # "upper" | "lower" | "title" | "as-given"
    tracking: float = 0.0


def _v(fam: str, style: str, size: float, case: str = "as-given",
       tracking: float = 0.0) -> RoleSpec:
    return RoleSpec(fam, style, size, case, tracking)


# 12 roles per voice ("pennant" and "chrome" are handled by their widgets;
# chrome is ALWAYS Inter for fit/legibility).
VOICES: dict[str, dict[str, RoleSpec]] = {
    "classic": {
        "page_title":     _v("body", "B", 19),
        "page_subtitle":  _v("body", "", 8.5),
        "section_label":  _v("body", "B", 8.5, "upper", 0.45),
        "band_label":     _v("body", "B", 8.5, "upper", 0.4),
        "calendar_digit": _v("body", "", 8),
        "mini_digit":     _v("body", "", 5.8),
        "inline_label":   _v("body", "B", 7),
        "display_title":  _v("display", "B", 46),
        "cover_year":     _v("script", "", 30),
        "cover_subtitle": _v("script", "", 17),
    },
    "serif": {
        "page_title":     _v("display", "", 21, "title"),
        "page_subtitle":  _v("body", "", 8.5),
        "section_label":  _v("body", "B", 8, "upper", 0.8),
        "band_label":     _v("body", "B", 8, "upper", 0.4),
        "calendar_digit": _v("display", "", 8.5),
        "mini_digit":     _v("body", "", 5.8),
        "inline_label":   _v("body", "B", 7),
        "display_title":  _v("display", "B", 50),
        "cover_year":     _v("script", "", 30),
        "cover_subtitle": _v("script", "", 17),
    },
    # Grotesk tracking sits at the SEARCHABLE_TRACKING_RATIO budget for the
    # searchable roles (0.12 x size); the editorial look above that budget
    # comes from case/weight, not spacing (extraction stays word-intact).
    "grotesk": {
        "page_title":     _v("body", "B", 17, "upper", 1.2),
        "page_subtitle":  _v("body", "", 8, "upper", 0.8),
        "section_label":  _v("body", "B", 7.5, "upper", 0.9),
        "band_label":     _v("body", "B", 7.5, "upper", 0.9),
        "calendar_digit": _v("body", "B", 8),
        "mini_digit":     _v("body", "", 5.8),
        "inline_label":   _v("body", "B", 7, "as-given", 0.8),
        "display_title":  _v("body", "I", 44, "upper", 4.0),
        "cover_year":     _v("body", "I", 26, "as-given", 3.1),
        "cover_subtitle": _v("body", "", 10, "upper", 2.5),
    },
    "script": {
        "page_title":     _v("script", "", 26, "title"),
        "page_subtitle":  _v("body", "I", 9),
        "section_label":  _v("body", "I", 9, "lower", 0.8),
        "band_label":     _v("body", "", 8, "title", 0.6),
        "calendar_digit": _v("body", "I", 8.5),
        "mini_digit":     _v("body", "I", 6),
        "inline_label":   _v("body", "", 7.5),
        "display_title":  _v("script", "", 54),
        "cover_year":     _v("display", "", 22),
        "cover_subtitle": _v("body", "I", 8, "upper", 2.5),
    },
    "typewriter": {
        "page_title":     _v("courier", "B", 16, "upper"),
        "page_subtitle":  _v("courier", "", 8),
        "section_label":  _v("courier", "B", 8, "upper"),
        "band_label":     _v("courier", "", 7.5, "upper"),
        "calendar_digit": _v("courier", "", 8),
        "mini_digit":     _v("courier", "", 5.4),
        "inline_label":   _v("courier", "B", 7),
        "display_title":  _v("courier", "B", 40, "upper"),
        "cover_year":     _v("courier", "", 18),
        "cover_subtitle": _v("courier", "", 9),
    },
}


def apply_case(case: str, s: str) -> str:
    """Case transform for a role: upper / lower / title / as-given."""
    if case == "upper":
        return s.upper()
    if case == "lower":
        return s.lower()
    if case == "title":
        return " ".join(w if w.isdigit() else w.capitalize()
                        for w in s.split(" "))
    return s


@dataclass(frozen=True)
class Theme:
    """Everything a page renderer needs: colors, sizes, registered families.

    ``body`` / ``display`` / ``script`` are family names that are guaranteed
    to be usable with ``pdf.set_font`` (they fall back to core fonts when
    the TTF downloads are unavailable).  ``design`` / ``ink`` / ``container``
    carry the resolved design-parameter system; the defaults reproduce the
    classic planner exactly.
    """

    palette: ColorPalette
    fonts: FontConfig
    body: str = "Helvetica"
    display: str = "Helvetica"
    script: str = "Helvetica"
    design: DesignTheme = field(default_factory=DesignTheme)
    ink: InkSpec = field(default_factory=lambda: INKS["soft-wash"])
    container: str = "soft_rounded"

    # Convenience wrappers -------------------------------------------------

    def rgb(self, field: str) -> tuple[int, int, int]:
        return self.palette.rgb(field)

    # -- Type roles ---------------------------------------------------------

    def role(self, role: str) -> RoleSpec:
        return VOICES[self.design.voice][role]

    def _family(self, key: str) -> str:
        if key == "body":
            return self.body
        if key == "display":
            return self.display
        if key == "script":
            return self.script
        if key == "courier":
            return "Courier"
        return self.body

    def set_type(self, pdf, role: str, size: float | None = None) -> RoleSpec:
        """Select the font + tracking for *role* (size overridable).

        Owns the ``"I"``-is-Light and Display-``"B"``-is-Regular hacks and
        the ``set_char_spacing`` try/except -- call sites never hardcode
        style letters for these faces.  Tracking on SEARCHABLE_ROLES is
        clamped to the extraction-safe budget for the *effective* size, so
        call-site size overrides can never re-break word extraction.
        """
        spec = self.role(role)
        use_size = size if size is not None else spec.size
        pdf.set_font(self._family(spec.family), spec.style, use_size)
        tracking = spec.tracking
        if role in SEARCHABLE_ROLES:
            tracking = searchable_tracking(use_size, tracking)
        try:
            pdf.set_char_spacing(tracking)
        except Exception:
            pass
        return spec

    def case(self, role: str, s: str) -> str:
        return apply_case(self.role(role).case, s)

    def text(self, pdf, role: str, x: float, y: float, w: float, h: float,
             s: str, align: str = "L", link=None,
             color: tuple[int, int, int] | None = None,
             size: float | None = None) -> None:
        """Set type, apply the role's case transform, draw one cell."""
        self.set_type(pdf, role, size=size)
        if color is not None:
            pdf.set_text_color(*color)
        pdf.set_xy(x, y)
        if link is not None:
            pdf.cell(w, h, self.case(role, s), align=align, link=link)
        else:
            pdf.cell(w, h, self.case(role, s), align=align)
        try:
            pdf.set_char_spacing(0)
        except Exception:
            pass

    # -- Ink (palette architecture) ------------------------------------------

    def paper_c(self) -> tuple[int, int, int]:
        """Page surface color (raw background on the poster shell)."""
        if self.design.shell == "poster":
            return self.rgb("background")
        return blend(self.rgb("background"), WHITE, 0.65)

    def desk_c(self) -> tuple[int, int, int]:
        return blend(self.rgb("background"), self.rgb("secondary"),
                     self.ink.desk_t)

    def band_fill(self) -> tuple[int, int, int] | None:
        """Label-band fill; None means unfilled (border does the work)."""
        if self.ink.band == "wash":
            return blend(self.paper_c(), self.rgb("primary"), 0.14)
        if self.ink.band == "solid":
            return self.rgb("primary")
        if self.ink.band == "grey":
            return blend(self.paper_c(), self.rgb("text"), 0.06)
        return None

    def box_fill(self) -> tuple[int, int, int] | None:
        """Writing-box fill; None means open (no fill)."""
        if self.ink.box == "wash":
            return blend(self.paper_c(), self.rgb("primary"), 0.08)
        if self.ink.box == "deep":
            return blend(self.paper_c(), self.rgb("primary"), 0.12)
        return None

    def border_c(self) -> tuple[int, int, int]:
        if self.ink.border_mix == "solid-primary":
            return self.rgb("primary")
        return blend(self.rgb("grid_line"), self.rgb(self.ink.border_mix),
                     self.ink.border_t)

    def border_w(self) -> float:
        return self.ink.border_width

    def rule_c(self) -> tuple[int, int, int]:
        if self.ink.rules == "text-mix":
            return blend(self.rgb("grid_line"), self.rgb("text"), 0.35)
        return self.rgb("grid_line")

    def structural(self) -> tuple[int, int, int]:
        """Underlines, active nav, title rules, pennant fill."""
        return self.rgb(self.ink.structural)

    def band_text_c(self) -> tuple[int, int, int]:
        """Label color when the text sits ON a band fill."""
        if self.ink.band == "solid":
            return WHITE
        return blend(self.rgb("text"), self.rgb("primary"), 0.3)

    def label_c(self) -> tuple[int, int, int]:
        """Label color when the text sits directly on the paper."""
        return blend(self.rgb("text"), self.rgb("primary"), 0.3)

    def bullet_c(self) -> tuple[int, int, int]:
        return self.rgb("accent" if self.ink.accent_bullets else "primary")

    def active_tab_c(self) -> tuple[int, int, int]:
        return self.rgb("accent" if self.ink.accent_active else "tab_active")


# ---------------------------------------------------------------------------
# Load YAML ---------------------------------------------------------------
# ---------------------------------------------------------------------------

def _load_templates() -> dict:
    with open(TEMPLATES_PATH) as fh:
        return yaml.safe_load(fh)


_TEMPLATES: dict | None = None


def _templates() -> dict:
    global _TEMPLATES
    if _TEMPLATES is None:
        _TEMPLATES = _load_templates()
    return _TEMPLATES


# ---------------------------------------------------------------------------
# Palette registry ---------------------------------------------------------
# ---------------------------------------------------------------------------

def _build_palettes() -> dict[str, ColorPalette]:
    raw = _templates()["palettes"]
    palettes: dict[str, ColorPalette] = {}
    for key, vals in raw.items():
        palettes[key] = ColorPalette(
            name=vals["name"],
            background=vals["background"],
            primary=vals["primary"],
            secondary=vals["secondary"],
            accent=vals["accent"],
            text=vals["text"],
            text_light=vals["text_light"],
            grid_line=vals["grid_line"],
            tab_active=vals["tab_active"],
            tab_inactive=vals["tab_inactive"],
        )
    return palettes


PALETTES: dict[str, ColorPalette] | None = None


def get_palettes() -> dict[str, ColorPalette]:
    global PALETTES
    if PALETTES is None:
        PALETTES = _build_palettes()
    return PALETTES


def get_palette(name: str) -> ColorPalette:
    """Return a palette by key name.  Raises KeyError if unknown."""
    palettes = get_palettes()
    if name not in palettes:
        available = ", ".join(palettes.keys())
        raise KeyError(f"Unknown palette '{name}'. Available: {available}")
    return palettes[name]


# ---------------------------------------------------------------------------
# Font config --------------------------------------------------------------
# ---------------------------------------------------------------------------

def get_font_config() -> FontConfig:
    f = _templates()["fonts"]
    display = f.get("display", {})
    script = f.get("script", {})
    sizes = f["sizes"]
    return FontConfig(
        family=f["primary"]["family"],
        regular_file=f["primary"]["regular"],
        bold_file=f["primary"]["bold"],
        light_file=f["primary"]["light"],
        size_title=sizes["title"],
        size_subtitle=sizes["subtitle"],
        size_heading=sizes["heading"],
        size_body=sizes["body"],
        size_small=sizes["small"],
        size_tab=sizes["tab"],
        display_family=display.get("family", "PlannerDisplay"),
        display_regular_file=display.get("regular", "DisplaySerif-Regular.ttf"),
        display_bold_file=display.get("bold", "DisplaySerif-Bold.ttf"),
        script_family=script.get("family", "PlannerScript"),
        script_regular_file=script.get("regular", "ScriptAccent-Regular.ttf"),
        size_display_title=sizes.get("display_title", 46),
        size_page_title=sizes.get("page_title", 19),
        size_section=sizes.get("section", 8.5),
        size_pennant=sizes.get("pennant", 15),
    )


# ---------------------------------------------------------------------------
# Font download ------------------------------------------------------------
# ---------------------------------------------------------------------------

_INTER_ZIP_URL = (
    "https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip"
)

# Mapping from our expected filenames to the paths inside the zip archive
_ZIP_FONT_PATHS = {
    "Inter-Regular.ttf": "Inter-4.1/extras/ttf/Inter-Regular.ttf",
    "Inter-Bold.ttf": "Inter-4.1/extras/ttf/Inter-Bold.ttf",
    "Inter-Light.ttf": "Inter-4.1/extras/ttf/Inter-Light.ttf",
}


def fonts_present() -> bool:
    """Check whether all three Inter TTF files exist locally."""
    cfg = get_font_config()
    for fname in (cfg.regular_file, cfg.bold_file, cfg.light_file):
        if not (FONTS_DIR / fname).is_file():
            return False
    return True


def download_inter_fonts() -> bool:
    """Download Inter font TTF files from GitHub releases.

    Returns True on success, False on failure (caller should fall back to
    Helvetica).
    """
    if fonts_present():
        logger.info("Inter fonts already present in %s", FONTS_DIR)
        return True

    FONTS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        logger.info("Downloading Inter fonts from %s ...", _INTER_ZIP_URL)
        req = urllib.request.Request(
            _INTER_ZIP_URL,
            headers={"User-Agent": "etsy-planner-bot/0.1"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()

        with zipfile.ZipFile(BytesIO(data)) as zf:
            for target_name, zip_path in _ZIP_FONT_PATHS.items():
                try:
                    font_data = zf.read(zip_path)
                except KeyError:
                    # Try alternative path patterns
                    found = False
                    for name in zf.namelist():
                        if name.endswith(target_name):
                            font_data = zf.read(name)
                            found = True
                            break
                    if not found:
                        logger.warning("Font %s not found in zip", target_name)
                        continue

                dest = FONTS_DIR / target_name
                dest.write_bytes(font_data)
                logger.info("Saved %s (%d bytes)", dest, len(font_data))

        if fonts_present():
            logger.info("All Inter fonts downloaded successfully.")
            return True
        else:
            logger.warning("Some Inter font files are still missing.")
            return False

    except Exception:
        logger.exception("Failed to download Inter fonts")
        return False


# ---------------------------------------------------------------------------
# Display / script font download ---------------------------------------------
# ---------------------------------------------------------------------------

def _download_first_available(urls: list[str], dest: Path) -> bool:
    """Try each URL in order; save the first successful response to *dest*."""
    for url in urls:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "etsy-planner-bot/0.1"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            if not data or len(data) < 10_000:  # sanity: a TTF is > 10 KB
                continue
            dest.write_bytes(data)
            logger.info("Saved %s (%d bytes) from %s", dest, len(data), url)
            return True
        except Exception:
            logger.debug("Font URL failed: %s", url)
            continue
    return False


def _display_font_candidates() -> dict[str, dict[str, list[str]]]:
    """Return {'display': {'regular': [...], 'bold': [...]}, 'script': ...}."""
    f = _templates()["fonts"]
    out: dict[str, dict[str, list[str]]] = {}
    for key in ("display", "script"):
        cfg = f.get(key, {})
        out[key] = cfg.get("candidates", {}) or {}
    return out


def display_fonts_present() -> bool:
    """Check whether the display + script TTFs exist locally."""
    cfg = get_font_config()
    needed = [
        cfg.display_regular_file,
        cfg.display_bold_file,
        cfg.script_regular_file,
    ]
    return all((FONTS_DIR / n).is_file() for n in needed)


def download_display_fonts() -> bool:
    """Download the serif display + script accent fonts.

    Tries Playfair Display static files first, then DM Serif Display, and
    Great Vibes for the script face.  Never raises -- returns False when
    offline so callers can fall back to Inter / Helvetica.
    """
    if display_fonts_present():
        return True

    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    cfg = get_font_config()
    candidates = _display_font_candidates()

    ok = True
    plan = [
        (cfg.display_regular_file, candidates.get("display", {}).get("regular", [])),
        (cfg.display_bold_file, candidates.get("display", {}).get("bold", [])),
        (cfg.script_regular_file, candidates.get("script", {}).get("regular", [])),
    ]
    for fname, urls in plan:
        dest = FONTS_DIR / fname
        if dest.is_file():
            continue
        if not urls or not _download_first_available(urls, dest):
            logger.warning("Could not download font %s -- will fall back.", fname)
            ok = False
    return ok


# ---------------------------------------------------------------------------
# Theme / font embedding ------------------------------------------------------
# ---------------------------------------------------------------------------

def embed_theme_fonts(pdf, cfg: FontConfig | None = None) -> tuple[str, str, str]:
    """Register body, display, and script fonts on *pdf*.

    Returns ``(body_family, display_family, script_family)`` -- each entry is
    a family name that is safe to pass to ``pdf.set_font`` (falls back to
    core Helvetica / Times when TTFs are unavailable).  Never raises.
    """
    cfg = cfg or get_font_config()

    # -- Body (Inter) --------------------------------------------------------
    body = "Helvetica"
    if not fonts_present():
        download_inter_fonts()
    if fonts_present():
        try:
            pdf.add_font(cfg.family, "", str(FONTS_DIR / cfg.regular_file))
            pdf.add_font(cfg.family, "B", str(FONTS_DIR / cfg.bold_file))
            pdf.add_font(cfg.family, "I", str(FONTS_DIR / cfg.light_file))
            body = cfg.family
        except Exception:
            logger.exception("Failed to embed Inter -- Helvetica fallback")

    # -- Display serif ---------------------------------------------------------
    display = "Times" if body == "Helvetica" else body
    if not display_fonts_present():
        download_display_fonts()
    try:
        reg = FONTS_DIR / cfg.display_regular_file
        bold = FONTS_DIR / cfg.display_bold_file
        if reg.is_file():
            pdf.add_font(cfg.display_family, "", str(reg))
            pdf.add_font(
                cfg.display_family, "B", str(bold if bold.is_file() else reg)
            )
            display = cfg.display_family
    except Exception:
        logger.exception("Failed to embed display font -- falling back")

    # -- Script accent ---------------------------------------------------------
    script = display
    try:
        sreg = FONTS_DIR / cfg.script_regular_file
        if sreg.is_file():
            pdf.add_font(cfg.script_family, "", str(sreg))
            pdf.add_font(cfg.script_family, "B", str(sreg))
            script = cfg.script_family
    except Exception:
        logger.exception("Failed to embed script font -- falling back")

    return body, display, script


def build_theme(pdf, palette_name: str,
                design: DesignTheme | None = None) -> Theme:
    """Resolve palette + fonts + design and register fonts on *pdf*.

    ``design=None`` means classic (today's planner, unchanged).  Courier is
    a core font and needs no ``add_font`` call.
    """
    palette = get_palette(palette_name)
    cfg = get_font_config()
    body, display, script = embed_theme_fonts(pdf, cfg)
    design = design if design is not None else DesignTheme()
    return Theme(
        palette=palette, fonts=cfg,
        body=body, display=display, script=script,
        design=design,
        ink=INKS[design.ink],
        container=CONTAINERS[design.motif],
    )
