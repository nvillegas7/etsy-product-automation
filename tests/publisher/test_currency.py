"""Unit tests for USD -> shop-currency price conversion."""

import pytest

from src.publisher.currency import CurrencyError, convert_usd


class TestConvertUsd:
    def test_usd_target_is_unchanged(self):
        assert convert_usd(5.99, "USD", {"PHP": 56.0}) == 5.99

    def test_none_or_empty_target_treated_as_usd(self):
        assert convert_usd(5.99, None, {}) == 5.99
        assert convert_usd(5.99, "", {}) == 5.99

    def test_target_is_case_insensitive(self):
        assert convert_usd(1.0, "php", {"PHP": 56.0}) == 56.0

    def test_converts_using_rate(self):
        assert convert_usd(5.99, "PHP", {"PHP": 56.0}) == round(5.99 * 56.0, 2)

    def test_rounds_to_two_decimals(self):
        # 4.99 * 56.3 = 280.937 -> 280.94
        assert convert_usd(4.99, "PHP", {"PHP": 56.3}) == 280.94

    def test_missing_rate_raises(self):
        with pytest.raises(CurrencyError, match="No USD->PHP exchange rate"):
            convert_usd(5.99, "PHP", {})

    def test_zero_or_negative_rate_raises(self):
        with pytest.raises(CurrencyError):
            convert_usd(5.99, "PHP", {"PHP": 0})
        with pytest.raises(CurrencyError):
            convert_usd(5.99, "PHP", {"PHP": -3})
