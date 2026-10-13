"""Legibility regression: the reviewer's font comments stay applied.

Born from the 2026-07 / 2026-09 rejections of #15 and #16:
  * "Year at a glance page - letters and numbers are too small."
  * "index page, class schedule: ... Fonts are too small. Use the space so it
    doesn't have too many blank space but make sure not to overdo it."
  * "Avoid hard to read font."
  * "Exam tracker: ... add a date, time, subject and check box column."

The page is 1366 x 1024 pt and shows ~1:1 on an iPad, so sizes below are
checked in PDF points straight from the rendered spans.
"""

from __future__ import annotations

import re

import fitz
import pytest

from src.planner.generator import PlannerGenerator, PlannerSpec
from src.planner.styles import VOICES

# One preset per voice, each with niche pages (the student/script pair is the
# exact design the reviewer rejected).
PRESETS = [
    ("classic", "travel"),
    ("midnight", "wedding"),        # serif
    ("blueprint", "fitness_planner"),  # grotesk
    ("wildflower", "student_planner"),  # script
    ("almanac", "budget_planner"),  # typewriter
]

_DIGITS = re.compile(r"^\d{1,2}$")


def _is_cursive(font: str) -> bool:
    return "GreatVibes" in font or "Script" in font


def _spans(page: fitz.Page):
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                text = span["text"].strip()
                if text:
                    yield text, span


@pytest.fixture(scope="module")
def docs(tmp_path_factory):
    import src.planner.generator as gen_mod

    out = tmp_path_factory.mktemp("legibility")
    original = gen_mod.OUTPUT_DIR
    gen_mod.OUTPUT_DIR = out
    opened = {}
    try:
        for design, slug in PRESETS:
            spec = PlannerSpec(title="2026 Planner", design=design,
                               niche_slug=slug, palette_name="neutral_beige")
            opened[design] = fitz.open(str(PlannerGenerator().generate(spec)))
        yield opened
    finally:
        gen_mod.OUTPUT_DIR = original
        for doc in opened.values():
            doc.close()


def _page(doc: fitz.Document, title: str) -> fitz.Page:
    toc = {t: p for _, t, p in doc.get_toc()}
    return doc[toc[title] - 1]


def test_voice_tables_meet_the_type_scale():
    for voice, roles in VOICES.items():
        for role in ("page_subtitle", "section_label", "band_label",
                     "inline_label", "mini_digit"):
            assert roles[role].size >= 9, f"{voice}.{role} below 9 pt"
        assert roles["calendar_digit"].size >= 12, voice
        for role, spec in roles.items():
            # Inter Light ("I") is too thin to read at small sizes.
            if spec.family == "body" and spec.style == "I":
                assert spec.size >= 12, f"{voice}.{role}: Light at {spec.size}"
            if spec.family == "script":
                assert role == "cover_year", f"{voice}.{role} is cursive"


@pytest.mark.parametrize("design", [d for d, _ in PRESETS])
def test_year_at_a_glance_numbers_are_large(docs, design):
    page = _page(docs[design], "Year at a Glance")
    digits = [s["size"] for t, s in _spans(page) if _DIGITS.match(t)]
    assert len(digits) >= 365
    assert min(digits) >= 11.5, f"{design}: YAG day numbers {min(digits)} pt"
    letters = [s["size"] for t, s in _spans(page) if t in "SMTWF"]
    assert letters and min(letters) >= 9, f"{design}: YAG weekday letters"


@pytest.mark.parametrize("design", [d for d, _ in PRESETS])
def test_index_is_readable(docs, design):
    page = _page(docs[design], "Index")
    spans = list(_spans(page))
    months = [s for t, s in spans if t in ("January", "August")]
    assert months, f"{design}: month names missing from the index"
    for s in months:
        assert s["size"] >= 13, f"{design}: index month name {s['size']} pt"
        assert not _is_cursive(s["font"]), f"{design}: cursive month name"
    for label in ("Calendar", "At a Glance", "Review"):
        sizes = [s["size"] for t, s in spans if t == label]
        assert len(sizes) == 12, f"{design}: {label!r} link per month"
        assert min(sizes) >= 9, f"{design}: {label!r} at {min(sizes)} pt"


@pytest.mark.parametrize("design", [d for d, _ in PRESETS])
def test_no_cursive_outside_the_cover_year(docs, design):
    doc = docs[design]
    for pno, page in enumerate(doc):
        for text, span in _spans(page):
            if _is_cursive(span["font"]):
                assert pno == 0 and re.fullmatch(r"[\d\s\-–]+", text), (
                    f"{design} p{pno + 1}: cursive text {text!r}")


@pytest.mark.parametrize("design", [d for d, _ in PRESETS])
def test_functional_text_floor(docs, design):
    """Nothing drops below 6.5 pt; only dense micro-grids (31-day habit
    headers, hour ticks) and the decorative footer sit below 8 pt."""
    doc = docs[design]
    for pno, page in enumerate(doc):
        for text, span in _spans(page):
            assert span["size"] >= 6.5, (
                f"{design} p{pno + 1}: {text!r} at {span['size']:.1f} pt")


def test_class_schedule_fonts(docs):
    page = _page(docs["wildflower"], "Class Schedule")
    spans = list(_spans(page))
    hours = [s["size"] for t, s in spans if re.fullmatch(r"\d{1,2}:00", t)]
    days = [s["size"] for t, s in spans
            if t in ("MON", "TUE", "WED", "THU", "FRI", "SAT")]
    assert len(hours) == 22 and min(hours) >= 10
    assert len(days) == 6 and min(days) >= 10.5


def test_exam_schedule_has_a_checkbox_column(docs):
    page = _page(docs["wildflower"], "Exam Schedule")
    done = [fitz.Rect(s["bbox"]) for t, s in _spans(page) if t == "Done"]
    assert done, "Done column header missing"
    col_x = (done[0].x0 + done[0].x1) / 2
    boxes = 0
    for drawing in page.get_drawings():   # rounded boxes are curve paths
        r = drawing["rect"]
        if 6 < r.width < 12 and abs(r.width - r.height) < 0.5 \
                and abs((r.x0 + r.x1) / 2 - col_x) < 3:
            boxes += 1
    assert boxes >= 16, f"only {boxes} checkboxes in the Done column"


def _niche_slugs() -> list[str]:
    from src.planner.niche_pages import _niches

    return list(_niches())


@pytest.mark.parametrize("slug", _niche_slugs())
def test_every_niche_renders_in_the_typewriter_voice(tmp_path, monkeypatch,
                                                     slug):
    """Courier is a latin-1 core font: niche content must avoid characters
    such as em dashes or arrows, or a typewriter-voice build crashes."""
    import src.planner.generator as gen_mod

    monkeypatch.setattr(gen_mod, "OUTPUT_DIR", tmp_path)
    spec = PlannerSpec(title="2026 Planner", design="almanac", niche_slug=slug,
                       include_weekly=False)
    assert PlannerGenerator().generate(spec).exists()


@pytest.mark.parametrize("design", ["meadow", "riviera", "wildflower"])
def test_script_voice_cover_title_keeps_acronyms(tmp_path, monkeypatch,
                                                 design):
    """The readable cover title must not title-case 'ADHD' into 'Adhd'."""
    import src.planner.generator as gen_mod

    monkeypatch.setattr(gen_mod, "OUTPUT_DIR", tmp_path)
    spec = PlannerSpec(title="2026 ADHD Planner", display_title="2026 ADHD Planner",
                       design=design, niche_slug="adhd_planner",
                       include_weekly=False)
    doc = fitz.open(str(PlannerGenerator().generate(spec)))
    try:
        cover = doc[0].get_text()
        assert "ADHD" in cover and "Adhd" not in cover
    finally:
        doc.close()
