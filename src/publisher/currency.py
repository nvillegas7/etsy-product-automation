"""Convert USD-authored prices into an Etsy shop's own currency.

Etsy prices every listing in the shop's currency: ``createDraftListing`` and
``updateListing`` take a bare ``price`` number that Etsy interprets in
``shop.currency_code``. Product prices in this project are authored in USD
(``Product.price_usd``), so when the connected shop is not USD-denominated the
price MUST be converted at publish time -- otherwise a $5.99 planner lists as
e.g. PHP 5.99 (~$0.10) in a PHP shop.
"""

from __future__ import annotations


class CurrencyError(Exception):
    """Raised when a price cannot be converted to the shop currency."""


def convert_usd(amount_usd: float, target_currency: str, fx_rates: dict) -> float:
    """Convert a USD amount into *target_currency*.

    Parameters
    ----------
    amount_usd:
        The price authored in USD.
    target_currency:
        ISO code of the shop currency (e.g. ``"USD"``, ``"PHP"``). ``None`` or
        empty is treated as USD.
    fx_rates:
        Mapping of ISO currency code -> units of that currency per 1 USD, e.g.
        ``{"PHP": 56.0}``.

    Returns
    -------
    float
        The converted price, rounded to 2 decimals (Etsy's price precision).

    Raises
    ------
    CurrencyError
        When a non-USD target has no configured (positive) rate. Failing loudly
        beats silently listing the raw USD number in the wrong currency.
    """
    target = (target_currency or "USD").upper()
    if target == "USD":
        return round(float(amount_usd), 2)

    rate = (fx_rates or {}).get(target)
    if not rate or float(rate) <= 0:
        raise CurrencyError(
            f"No USD->{target} exchange rate configured. Add "
            f"pricing.fx_rates.{target} to config.yaml "
            f"(units of {target} per 1 USD)."
        )
    return round(float(amount_usd) * float(rate), 2)
