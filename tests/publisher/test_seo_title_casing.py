"""Title keyword casing: research keywords arrive lowercase, and the listing
title must not mangle them ("adhd daily planner" became "Adhd Daily
Planner" on product #15 via ``str.title()``)."""

import pytest

from src.publisher.seo import ListingSEO


def _extra(title: str) -> str:
    """The keyword segment between the core and the stickers/suffix."""
    return title.split(" | ")[1]


@pytest.mark.parametrize("niche,keyword,expected", [
    ("ADHD Planner", "adhd daily planner", "ADHD Daily Planner"),
    ("Teacher Planner", "teacher's lesson planner", "Teacher's Lesson Planner"),
    ("Self-Care Planner", "self-care journal", "Self-Care Journal"),
    ("Budget Planner", "goodnotes budget template", "GoodNotes Budget Template"),
    ("Student Planner", "ipad study planner", "iPad Study Planner"),
    ("Fitness Planner", "workout planner", "Workout Planner"),
])
def test_extra_keyword_is_cased_like_a_title(niche, keyword, expected):
    title = ListingSEO().generate_title(niche, 2026, keywords=[keyword])
    assert _extra(title) == expected


def test_acronym_from_the_niche_name_is_kept():
    # Any all-caps word in the niche name keeps its casing in the keyword.
    title = ListingSEO().generate_title("OCD Planner", 2026,
                                        keywords=["ocd tracker"])
    assert _extra(title) == "OCD Tracker"
