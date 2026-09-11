"""Niche-depth regression: wedding / travel / fitness planners must carry
pre-printed, niche-specific content -- not blank tables with a themed label.

Born from the 2026-09-05 rejections ("doesn't look like a wedding planner",
"I don't want a generic planner", "use the title of the planner to know the
context").  Each niche is checked for first-flip signals a buyer would look
for, extracted from the rendered PDF text.
"""

from __future__ import annotations

import fitz
import pytest

from src.planner.generator import PlannerGenerator, PlannerSpec
from src.planner.niche_pages import get_niche_pages

# (niche, palette, design, required text signals, page labels)
CASES = [
    ("wedding", "ocean_blue", "midnight",
     ["Photographer", "Florist", "Officiant", "RSVP", "Venue & site fees",
      "Catering & bar", "Save-the-dates", "First look", "Cocktail hour",
      "Tip envelopes", "Final headcount"],
     ["Our Wedding", "Countdown Checklist", "Wedding Budget",
      "Vendor Directory", "Guest List", "Day-Of Timeline", "Seating Chart"]),
    ("travel", "ocean_blue", "classic",
     ["Passport", "Visa", "Flight #", "Check-in", "Confirmation",
      "Toiletries", "Plug adapter", "Accommodation", "Local transport",
      "Travel insurance", "Online check-in", "Hours"],
     ["Trip Overview", "Daily Itinerary", "Flights & Stays", "Packing List",
      "Travel Budget", "Pre-Trip Checklist", "Places & Journal"]),
    ("fitness_planner", "ocean_blue", "blueprint",
     ["Specific", "Measurable", "RPE", "Set 1", "Push", "Deadlift",
      "Bench press", "Body fat", "Wk 12", "Protein", "Week 12"],
     ["Fitness Goals", "Workout Log", "Weekly Split", "Measurements",
      "Meals & Macros", "Personal Records", "Progress Photos"]),
]


@pytest.fixture
def out_dir(tmp_path, monkeypatch):
    import src.planner.generator as gen_mod

    monkeypatch.setattr(gen_mod, "OUTPUT_DIR", tmp_path)
    return tmp_path


def _niche_text(doc: fitz.Document, labels: list[str]) -> str:
    toc = {t[1]: t[2] - 1 for t in doc.get_toc()}
    return "\n".join(doc[toc[lbl]].get_text() for lbl in labels)


@pytest.mark.parametrize("slug,palette,design,signals,labels", CASES)
def test_niche_pages_carry_domain_content(out_dir, slug, palette, design,
                                          signals, labels):
    assert [p.label for p in get_niche_pages(slug)] == labels
    spec = PlannerSpec(title=f"2026 {slug}", display_title=f"2026 {slug}",
                       year=2026, palette_name=palette, niche_slug=slug,
                       design=design, include_weekly=False)
    doc = fitz.open(str(PlannerGenerator().generate(spec)))
    try:
        toc_labels = {t[1] for t in doc.get_toc()}
        missing_pages = [lbl for lbl in labels if lbl not in toc_labels]
        assert not missing_pages, f"{slug}: niche pages missing {missing_pages}"
        text = _niche_text(doc, labels)
        missing = [s for s in signals if s.lower() not in text.lower()]
        assert not missing, f"{slug}: pre-filled signals missing {missing}"
    finally:
        doc.close()


def test_three_reworked_niches_sit_at_the_page_bound():
    for slug in ("wedding", "travel", "fitness_planner"):
        assert len(get_niche_pages(slug)) == 7
