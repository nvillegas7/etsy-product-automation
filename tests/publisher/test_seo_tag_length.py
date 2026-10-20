"""Tags longer than Etsy's 20-char limit are shortened on word boundaries.

The old hard cut produced fragments such as "kindle scribe teache" and
"notability teacher p" on every planner listing -- 4-5 of 13 tags wasted.
"""

import pytest

from src.pipeline.orchestrator import _load_niches_config
from src.publisher.seo import MAX_TAG_LENGTH, ListingSEO, _fit_tag


@pytest.mark.parametrize("raw,expected", [
    ("teacher planner", "teacher planner"),
    ("2026 teacher planner", "2026 teacher planner"),       # exactly 20
    ("digital teacher planner", "digital teacher"),
    ("notability teacher planner", "notability teacher"),
    ("kindle scribe teacher planner", "kindle scribe"),
    ("kindle scribe adhd planner", "kindle scribe adhd"),
    ("accountabilitypartnership", ""),                       # one long word
    ("organisational planner", ""),                          # would leave 1 word
])
def test_fit_tag(raw, expected):
    assert _fit_tag(raw) == expected


def _planner_niches():
    return [cfg for cfg in _load_niches_config().values()
            if cfg.get("product_type", "planner") == "planner"]


@pytest.mark.parametrize("niche_cfg", _planner_niches(),
                         ids=lambda cfg: cfg["slug"])
def test_no_tag_is_cut_mid_word(niche_cfg):
    keywords = list(niche_cfg.get("seed_keywords", []))
    keywords += [f"{prefix} {niche_cfg['name'].lower()}"
                 for prefix in ("digital", "printable", "goodnotes",
                                "notability", "kindle scribe")]
    tags = ListingSEO().generate_tags(
        keywords=keywords, niche_name=niche_cfg["name"], year=2026,
        date_label="2026-2027 2027-2028 & Undated", with_stickers=True,
    )
    assert len(tags) == 13 and len(set(tags)) == 13
    source_words = {w for text in keywords + [niche_cfg["name"]]
                    for w in text.lower().replace("-", " ").split()}
    for tag in tags:
        assert len(tag) <= MAX_TAG_LENGTH, tag
        for word in tag.split():
            # A cut word is a strict prefix of a source word ("teache").
            assert word in source_words or not any(
                src.startswith(word) for src in source_words), (
                f"{niche_cfg['slug']}: fragment {word!r} in tag {tag!r}")
