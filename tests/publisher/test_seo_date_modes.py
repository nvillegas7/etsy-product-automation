"""P2: SEO reflects the date-mode trio (title span, undated tag, date section).

``date_label=None`` keeps the single-year output (covered by the other SEO
tests); these pin the academic / trio behavior.
"""

from src.publisher.seo import ListingSEO


class TestTitle:
    def test_span_leads_title_for_trio(self):
        seo = ListingSEO()
        title = seo.generate_title(
            "Teacher Planner", 2026,
            keywords=["teacher planner 2026-2027"],
            date_label="2026-2027 2027-2028 & Undated",
        )
        assert title.startswith("Hyperlinked 2026-2027 2027-2028 & Undated Teacher Planner")
        assert len(title) <= 140

    def test_default_title_leads_with_hyperlinked(self):
        seo = ListingSEO()
        assert seo.generate_title("Budget Planner", 2026).startswith(
            "Hyperlinked 2026 Budget Planner Digital Planner"
        )


class TestTags:
    def test_undated_tag_present_for_trio(self):
        seo = ListingSEO()
        tags = seo.generate_tags(
            ["teacher planner"], "Teacher Planner", 2026,
            date_label="2026-2027 2027-2028 & Undated",
        )
        assert "undated planner" in tags
        assert len(tags) == 13

    def test_no_undated_tag_without_date_label(self):
        seo = ListingSEO()
        tags = seo.generate_tags(["budget planner"], "Budget Planner", 2026)
        assert "undated planner" not in tags

    def test_sticker_tag_added(self):
        seo = ListingSEO()
        tags = seo.generate_tags(["teacher planner"], "Teacher Planner", 2026,
                                 with_stickers=True)
        assert "digital stickers" in tags

    def test_year_span_keyword_stays_searchable(self):
        # Hyphenated span keywords must degrade to "2026 2027", never "20262027".
        seo = ListingSEO()
        tags = seo.generate_tags(
            ["2026-2027 student planner"], "Student Planner", 2026,
            date_label="2026-2027 2027-2028 & Undated",
        )
        assert not any("20262027" in t for t in tags)
        assert "2026 2027" in tags


class TestStickers:
    def test_title_gains_sticker_segment_within_cap(self):
        seo = ListingSEO()
        title = seo.generate_title(
            "Teacher Planner", 2026,
            keywords=["lesson planner"],
            date_label="2026-2027 2027-2028 & Undated",
            with_stickers=True,
        )
        assert "With Digital Stickers" in title
        assert len(title) <= 140

    def test_stickers_outrank_extra_keyword_when_tight(self):
        # A long extra keyword must be dropped before the sticker segment.
        seo = ListingSEO()
        title = seo.generate_title(
            "Teacher Planner", 2026,
            keywords=["a very long tail keyword phrase for lesson planning teachers"],
            date_label="2026-2027 2027-2028 & Undated",
            with_stickers=True,
        )
        assert "With Digital Stickers" in title
        assert len(title) <= 140

    def test_title_unchanged_without_stickers(self):
        seo = ListingSEO()
        assert "Stickers" not in seo.generate_title("Budget Planner", 2026)

    def test_description_sticker_section(self):
        seo = ListingSEO()
        desc = seo.generate_description(
            {"name": "Teacher Planner", "features": []}, 2026,
            sticker_count=244,
        )
        assert "DIGITAL STICKERS" in desc
        assert "244+" in desc

    def test_description_without_stickers_unchanged(self):
        seo = ListingSEO()
        desc = seo.generate_description(
            {"name": "Budget Planner", "features": []}, 2026)
        assert "DIGITAL STICKERS" not in desc


class TestDescription:
    def test_date_options_section_for_trio(self):
        seo = ListingSEO()
        desc = seo.generate_description(
            {"name": "Teacher Planner", "features": ["Lesson planning"]},
            2026, date_label="2026-2027 2027-2028 & Undated",
        )
        assert "DATE OPTIONS" in desc
        assert "2026-2027 2027-2028 & Undated" in desc
        assert "(12 months)" in desc

    def test_default_description_says_jan_dec(self):
        seo = ListingSEO()
        desc = seo.generate_description(
            {"name": "Budget Planner", "features": ["Expense tracking"]}, 2026
        )
        assert "(Jan - Dec)" in desc
        assert "DATE OPTIONS" not in desc
