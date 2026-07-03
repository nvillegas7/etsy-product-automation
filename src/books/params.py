"""Book parameter selection: picks a fresh, deterministic parameter combo.

``pick_book_params`` chooses a (character, setting, moral) combination that
has never been produced before (given the params dicts of all existing
picture-book products), constrained by the niche config from
``config/books.yaml``.
"""

from __future__ import annotations

import random

import structlog

from src.books.illustrator import load_book_config

logger = structlog.get_logger()

# Display-title template per moral.
MORAL_TITLES: dict[str, str] = {
    "kindness": "{name} Learns to Be Kind",
    "honesty": "{name} Tells the Truth",
    "sharing": "{name} Learns to Share",
    "patience": "{name} Learns to Wait",
    "courage": "{name} Finds Courage",
    "obedience": "{name} Learns to Listen",
    "politeness": "{name} Minds Manners",
    "gratitude": "{name} Says Thank You",
    "teamwork": "{name} Joins the Team",
    "perseverance": "{name} Never Gives Up",
}

# Palettes that especially suit a setting (soft preference, not a rule).
_SETTING_PALETTES: dict[str, list[str]] = {
    "beach": ["ocean_breeze", "sunny_day", "sunset_glow"],
    "forest": ["spring_meadow", "autumn_cozy", "sunny_day"],
    "garden": ["spring_meadow", "berry_sweet", "sunny_day"],
    "farm": ["sunny_day", "autumn_cozy", "sunset_glow"],
    "park": ["sunny_day", "spring_meadow", "berry_sweet"],
    "school": ["sunny_day", "spring_meadow", "berry_sweet"],
    "city": ["berry_sweet", "sunset_glow", "sunny_day"],
    "zoo": ["sunny_day", "spring_meadow", "sunset_glow"],
}


def _species_label(key: str) -> str:
    return key.replace("_", " ").title()


def pick_book_params(
    niche_cfg: dict, existing: list[dict], seed: int | None = None
) -> dict:
    """Pick a parameter combination for a new picture book.

    Parameters
    ----------
    niche_cfg : dict
        One niche entry from ``config/books.yaml`` (may constrain
        ``allowed_themes``, ``preferred_settings``, ``preferred_morals``).
    existing : list[dict]
        Params dicts of every previously produced book; the returned
        (character_key, setting, moral) triple will not repeat any of them.
    seed : int | None
        Deterministic seed.  When None a fresh random seed is drawn.

    Returns
    -------
    dict with at least: character_theme, character_key, character_name,
    setting, moral, age_band, narrative_style, page_count, art_palette,
    display_title, subtitle, seed.
    """
    bp = load_book_config().get("book_params") or {}
    themes: dict = bp.get("themes") or {}
    theme_settings: dict = bp.get("theme_settings") or {}
    all_settings: list = bp.get("settings") or ["park"]
    all_morals: list = bp.get("morals") or ["sharing"]
    names: dict = bp.get("character_names") or {}
    age_bands: list = bp.get("age_bands") or ["4-6"]
    styles: list = bp.get("narrative_styles") or ["prose"]
    page_counts: list = bp.get("page_counts") or [12]
    palette_names: list = sorted((bp.get("palettes") or {"sunny_day": {}}).keys())

    if seed is None:
        seed = random.SystemRandom().randrange(2**31)
    rng = random.Random(seed)

    allowed_themes = [t for t in (niche_cfg.get("allowed_themes") or list(themes)) if t in themes]
    if not allowed_themes:
        allowed_themes = list(themes) or ["forest_animals"]

    preferred_settings = niche_cfg.get("preferred_settings") or []
    morals = [m for m in (niche_cfg.get("preferred_morals") or all_morals) if m in all_morals]
    if not morals:
        morals = all_morals

    used_triples = {
        (p.get("character_key"), p.get("setting"), p.get("moral"))
        for p in existing
        if isinstance(p, dict)
    }

    def _settings_for(theme: str) -> list[str]:
        pool = theme_settings.get(theme) or all_settings
        narrowed = [s for s in pool if s in preferred_settings] if preferred_settings else []
        return narrowed or list(pool)

    choice: tuple[str, str, str, str] | None = None
    for _ in range(400):
        theme = rng.choice(allowed_themes)
        character = rng.choice(list(themes.get(theme, {}).get("characters") or ["bunny"]))
        setting = rng.choice(_settings_for(theme))
        moral = rng.choice(morals)
        if (character, setting, moral) not in used_triples:
            choice = (theme, character, setting, moral)
            break

    if choice is None:
        # exhaustive deterministic scan for any unused combination
        combos = [
            (t, c, s, m)
            for t in allowed_themes
            for c in (themes.get(t, {}).get("characters") or [])
            for s in _settings_for(t)
            for m in morals
        ]
        rng.shuffle(combos)
        for t, c, s, m in combos:
            if (c, s, m) not in used_triples:
                choice = (t, c, s, m)
                break

    if choice is None:
        # parameter space exhausted: accept a repeat but log loudly
        theme = rng.choice(allowed_themes)
        character = rng.choice(list(themes.get(theme, {}).get("characters") or ["bunny"]))
        choice = (theme, character, rng.choice(_settings_for(theme)), rng.choice(morals))
        logger.warning("book_param_space_exhausted", triple=choice[1:])

    theme, character, setting, moral = choice
    name_pool = list(names.get(character) or [_species_label(character)])
    character_name = rng.choice(name_pool)
    full_name = f"{character_name} the {_species_label(character)}"

    age_band = rng.choice(list(age_bands))
    narrative_style = rng.choice(list(styles))
    page_count = int(rng.choice(list(page_counts)))

    palette_prefs = [p for p in _SETTING_PALETTES.get(setting, []) if p in palette_names]
    art_palette = rng.choice(palette_prefs or palette_names)

    display_title = MORAL_TITLES.get(moral, "{name}'s Big Day").format(name=full_name)
    subtitle = f"A warm little story about {moral}"

    params = {
        "character_theme": theme,
        "character_key": character,
        "character_name": character_name,
        "character_full_name": full_name,
        "setting": setting,
        "moral": moral,
        "age_band": age_band,
        "narrative_style": narrative_style,
        "page_count": page_count,
        "art_palette": art_palette,
        "display_title": display_title,
        "subtitle": subtitle,
        "seed": seed,
    }
    logger.info(
        "book_params_picked",
        character=character, setting=setting, moral=moral,
        style=narrative_style, age_band=age_band, palette=art_palette,
    )
    return params
