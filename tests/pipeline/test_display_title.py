"""The short display title leads with the planner's dated span.

It headlines the first listing image, so an academic planner read "2026
Teacher Planner" beside a 2026-2027 cover (#12/#16/#20, Oct 2026).  Covers
strip a leading year/span themselves, so the cover text must not change.
"""

from __future__ import annotations

import fitz
import pytest

from src.pipeline.orchestrator import PipelineOrchestrator, _load_niches_config
from src.planner.generator import PlannerGenerator, PlannerSpec

NICHES = _load_niches_config()


@pytest.mark.parametrize("slug,expected", [
    ("teacher_planner", "2026-2027 Teacher Planner"),
    ("student_planner", "2026-2027 Student Planner"),
    ("budget_planner", "2026 Budget Planner"),
    ("adhd_planner", "2026 ADHD Planner"),
])
def test_display_title_leads_with_the_dated_span(slug, expected):
    title = PipelineOrchestrator._planner_display_title(NICHES[slug], 2026, slug)
    assert title == expected


@pytest.mark.parametrize("design", ["noir", "blush", "wildflower", "classic"])
@pytest.mark.parametrize("date_mode", ["dated", "undated"])
def test_cover_text_ignores_the_span(tmp_path, monkeypatch, design, date_mode):
    import src.planner.generator as gen_mod

    monkeypatch.setattr(gen_mod, "OUTPUT_DIR", tmp_path)
    covers = []
    for display_title in ("2026 Teacher Planner", "2026-2027 Teacher Planner"):
        spec = PlannerSpec(title="2026 Planner", display_title=display_title,
                           design=design, niche_slug="teacher_planner",
                           start_month=8, date_mode=date_mode,
                           include_weekly=False)
        doc = fitz.open(str(PlannerGenerator().generate(spec)))
        covers.append(" ".join(doc[0].get_text().split()))
        doc.close()
    assert covers[0] == covers[1]
    if date_mode == "undated":
        assert "2026" not in covers[1]
