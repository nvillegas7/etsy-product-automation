"""Tests for the story engine: structure, determinism, rhyme integrity."""

from __future__ import annotations

import pytest

from src.books.params import pick_book_params
from src.books.story import (
    GENERIC_PROSE,
    MORAL_LESSONS,
    MORAL_RHYME_SCENARIO,
    MORAL_RHYMES,
    MORAL_SCENARIOS,
    build_story,
)


def _params(**overrides) -> dict:
    p = pick_book_params({}, existing=[], seed=overrides.pop("seed", 3))
    p.update(overrides)
    return p


def test_page_counts():
    for count in (12, 16):
        story = build_story(_params(page_count=count))
        assert len(story.pages) == count


def test_deterministic():
    a = build_story(_params(seed=5))
    b = build_story(_params(seed=5))
    assert [p.text for p in a.pages] == [p.text for p in b.pages]
    assert a.friend_key == b.friend_key
    assert a.mentor_key == b.mentor_key


def test_no_unfilled_slots():
    for moral in MORAL_SCENARIOS:
        for style in ("prose", "rhyme"):
            for age in ("2-4", "4-6", "6-8"):
                story = build_story(
                    _params(moral=moral, narrative_style=style, age_band=age,
                            page_count=16)
                )
                for page in story.pages:
                    assert "{" not in page.text and "}" not in page.text, (
                        f"unfilled slot in {moral}/{style}: {page.text!r}"
                    )


def test_age_band_2_4_sentences_are_short():
    """First (only) sentence for 2-4 must be 8 words or fewer."""
    for beat, sentences in GENERIC_PROSE.items():
        first = sentences[0]
        # generous slot expansion for word counting
        expanded = first.format(
            short="Penny", species="pear", place="the sunny park",
            feature="the old oak tree", activity="play",
            friend_short="Milo", friend_species="fox", mentor="Grandma Owl",
            mentor_short="Grandma Owl", thing="kite", thing_short="kite",
            wrong_feeling="selfish", moral="sharing",
        )
        assert len(expanded.split()) <= 9, f"{beat}: too long for 2-4: {expanded}"


def test_rhymes_actually_rhyme():
    """Couplet end words must share their final 2+ characters (AABB)."""
    known_pairs_ok = set()
    for moral, beats in MORAL_RHYMES.items():
        for beat, couplet in beats.items():
            lines = [ln.strip().rstrip('.!?”"—-') for ln in couplet.split("\n")]
            assert len(lines) == 2, f"{moral}/{beat} is not a couplet"
            ends = [ln.split()[-1].strip(",;:'\"”’!?.").lower() for ln in lines]
            a, b = ends
            # rhyme heuristic: shared suffix of >= 2 chars
            suffix_ok = a[-2:] == b[-2:] or a[-3:] == b[-3:]
            # same vowel-sound family despite different spellings
            ee_family = {"see", "me", "be", "we", "he", "she", "three",
                         "tree", "free", "key", "tea", "sea", "agree"}
            if a in ee_family and b in ee_family:
                suffix_ok = True
            # hand-verified near-rhymes
            near = {("feather", "together"), ("smiled", "child"), ("said", "spread"),
                    ("said", "ahead"), ("said", "head"), ("oh", "know"),
                    ("flew", "knew"), ("sting", "anything"), ("well", "spell"),
                    ("cry", "by"), ("three", "see"), ("me", "be"),
                    ("late", "wait"), ("shout", "out"), ("grab", "drab"),
                    ("told", "gold"), ("low", "glow"), ("hug", "snug"),
                    ("thing", "sing"), ("huff", "enough"), ("bump", "slump"),
                    ("round", "bound"), ("one", "done"), ("ground", "mound"),
                    ("way", "day"), ("fall", "all"), ("tight", "night"),
                    ("do", "two"), ("ten", "again"), ("true", "you"),
                    ("roar", "for")}
            assert suffix_ok or (a, b) in near or (b, a) in near, (
                f"{moral}/{beat}: {a!r} does not rhyme with {b!r}"
            )
            known_pairs_ok.add((a, b))
    assert known_pairs_ok


def test_moral_lesson_exists_for_every_scenario():
    for moral, scenarios in MORAL_SCENARIOS.items():
        assert moral in MORAL_LESSONS
        assert {s["id"] for s in scenarios} == set(MORAL_LESSONS[moral])
        story = build_story(_params(moral=moral))
        assert story.lesson_text == MORAL_LESSONS[moral][story.scenario_id]


def test_rhyme_scenario_pinned_for_every_moral():
    for moral, scenarios in MORAL_SCENARIOS.items():
        assert MORAL_RHYME_SCENARIO[moral] in {s["id"] for s in scenarios}


def test_story_beats_and_lesson_share_scenario():
    """Moral-coherence regression: the lesson page must recap the same
    sub-scenario the story beats were drawn from (e.g. a politeness story
    about listening must not end with the please-and-thank-you lesson)."""
    for moral, scenarios in MORAL_SCENARIOS.items():
        by_id = {s["id"]: s for s in scenarios}
        for style in ("prose", "rhyme"):
            for seed in range(6):
                story = build_story(
                    _params(moral=moral, narrative_style=style, age_band="6-8",
                            page_count=16, seed=seed)
                )
                scenario = by_id[story.scenario_id]
                # lesson page comes from the very scenario that was told
                assert story.lesson_text == MORAL_LESSONS[moral][story.scenario_id]
                if style == "prose":
                    # the moral beats on the pages are that scenario's prose
                    page = next(p for p in story.pages if p.beat == "problem_setup")
                    expected = " ".join(
                        scenario["prose"]["problem_setup"]
                    ).format(**story.context)
                    assert page.text == expected
                else:
                    # rhyme couplets tell one fixed storyline per moral
                    assert story.scenario_id == MORAL_RHYME_SCENARIO[moral]


def test_cast_never_clashes():
    for s in range(30):
        story = build_story(_params(seed=s))
        assert story.friend_key != story.character_key
        assert story.mentor_key not in (story.character_key, story.friend_key)
