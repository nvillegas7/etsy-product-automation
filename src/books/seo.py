"""Etsy listing SEO for picture books: title, description, and 13 tags."""

from __future__ import annotations

import structlog

logger = structlog.get_logger()

TITLE_MAX = 140
TAG_MAX_LEN = 20
TAG_COUNT = 13


class BookListingSEO:
    """Generates Etsy listing copy from a book params dict."""

    # ------------------------------------------------------------- title

    def generate_title(self, params: dict, year: int) -> str:
        """Etsy SEO title, at most 140 characters."""
        display = params.get("display_title") or "A Little Lesson Story"
        moral = (params.get("moral") or "kindness").title()
        age = params.get("age_band", "2-6")
        parts = [
            "Kids Picture Book PDF",
            display,
            f"Printable {moral} Story Ages {age}",
            "Bedtime Story Instant Download",
        ]
        title = " | ".join(parts)
        while len(title) > TITLE_MAX and len(parts) > 2:
            parts.pop()
            title = " | ".join(parts)
        return title[:TITLE_MAX]

    # ------------------------------------------------------- description

    def generate_description(self, params: dict) -> str:
        """Rich multi-section description for the Etsy listing."""
        display = params.get("display_title", "this little story")
        name = params.get("character_full_name") or params.get("character_name", "a little friend")
        moral = params.get("moral", "kindness")
        setting = params.get("setting", "park").replace("_", " ")
        age = params.get("age_band", "2-6")
        style = params.get("narrative_style", "prose")
        page_count = int(params.get("page_count", 12))
        total_pages = page_count + 8  # cover, title, moral, 4 coloring, end
        style_line = (
            "told in bouncy rhyming couplets that are a joy to read aloud"
            if style == "rhyme"
            else "told in warm, simple prose that is a joy to read aloud"
        )

        return "\n".join(
            [
                f"{display.upper()} - PRINTABLE CHILDREN'S PICTURE BOOK (PDF)",
                "",
                f"Meet {name}! In this sweet story set in the {setting}, your little one "
                f"follows along as {name} learns a gentle lesson about {moral} - "
                f"{style_line}.",
                "",
                "WHAT'S INSIDE",
                f"- {page_count} full-color illustrated story pages",
                "- Adorable full-bleed cover and personalization page ('This book belongs to...')",
                f"- 'The Lesson of the Story' page - perfect for talking about {moral} together",
                "- BONUS: 4 coloring pages of favorite scenes from the story",
                f"- {total_pages} pages total, 8.5 x 8.5 inch square format",
                "",
                "PERFECT FOR",
                f"- Children ages {age}",
                "- Bedtime stories, quiet time, and early readers",
                "- Homeschool and classroom character lessons",
                "- Thoughtful, screen-free gifts (print + bind at home!)",
                "",
                "HOW IT WORKS",
                "1. Purchase and download the PDF instantly - no shipping, no waiting",
                "2. Read on any tablet or computer, or print at home / a print shop",
                "3. Print the bonus coloring pages as many times as your family likes",
                "",
                "PLEASE NOTE",
                "- This is a DIGITAL DOWNLOAD. No physical item will be shipped.",
                "- For PERSONAL USE only: enjoy it with your family and classroom;",
                "  resale or redistribution of the files is not permitted.",
                "- Colors may vary slightly between screens and printers.",
                "",
                "Thank you for supporting small, story-loving makers!",
            ]
        )

    # -------------------------------------------------------------- tags

    def generate_tags(self, params: dict, year: int) -> list[str]:
        """Exactly 13 lowercase tags, each 20 characters or fewer."""
        moral = params.get("moral", "kindness")
        species = (params.get("character_key") or "animal").replace("_", " ")
        age = params.get("age_band", "2-6")
        style = params.get("narrative_style", "prose")

        candidates = [
            "kids picture book",
            "printable kids book",
            "bedtime story pdf",
            f"{moral} story",
            f"ages {age} book",
            "kids book download",
            f"{species} book",
            "story with moral",
            "coloring pages kids",
            "rhyming story book" if style == "rhyme" else "read aloud story",
            "toddler story book",
            f"kids book {year}",
            "digital kids book",
            # padding pool
            "instant download",
            "picture book pdf",
            "moral story kids",
            "preschool book",
            "homeschool reading",
            "cute animal story",
            "printable story",
        ]

        tags: list[str] = []
        for tag in candidates:
            tag = tag.lower().strip()
            if len(tag) > TAG_MAX_LEN or not tag or tag in tags:
                continue
            tags.append(tag)
            if len(tags) == TAG_COUNT:
                break

        # Safety: pad with numbered generic tags if somehow short.
        i = 1
        while len(tags) < TAG_COUNT:
            filler = f"kids story {i}"
            if filler not in tags:
                tags.append(filler)
            i += 1
        return tags[:TAG_COUNT]
