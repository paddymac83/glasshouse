from __future__ import annotations

from datetime import date, datetime

import pytest

from pricing.services import (
    SettlementInputError,
    build_portfolio,
    default_settlement_period,
    get_benchmark,
    get_quote,
)


def test_build_portfolio_rejects_unknown_business_type():
    with pytest.raises(SettlementInputError, match="unknown business_type"):
        build_portfolio("spaceport", 0.5)


def test_build_portfolio_rejects_out_of_range_renewable_share():
    with pytest.raises(SettlementInputError, match="renewable_share"):
        build_portfolio("office", 1.5)


def test_build_portfolio_splits_capacity_by_renewable_share():
    generators, consumers = build_portfolio("factory", 0.25)

    wind = next(g for g in generators if g["id"] == "wind_portfolio")
    gas = next(g for g in generators if g["id"] == "gas_portfolio")

    assert wind["available_mwh"] == pytest.approx(gas["available_mwh"] / 3, rel=1e-6)
    assert consumers[0]["demand_mwh"] > 0


def test_default_settlement_period_covers_midnight_and_just_before():
    assert default_settlement_period(datetime(2026, 8, 5, 0, 0)) == 1
    assert default_settlement_period(datetime(2026, 8, 5, 0, 29)) == 1
    assert default_settlement_period(datetime(2026, 8, 5, 0, 30)) == 2
    assert default_settlement_period(datetime(2026, 8, 5, 23, 45)) == 48


def test_get_benchmark_returns_none_when_db_missing(with_no_db):
    result = get_benchmark(date(2026, 8, 5), 36)
    assert result is None


def test_get_benchmark_returns_a_confident_forecast_with_seeded_history(with_seeded_db):
    result = get_benchmark(date(2026, 8, 5), 36)

    assert result is not None
    assert result.sample_size == 8
    assert result.fallback_used is False


def test_get_quote_still_works_with_no_history_at_all(with_no_db):
    quote = get_quote("office", 0.5, date(2026, 8, 5), settlement_period=10)

    assert quote["settlement"]["blended_generation_price_gbp_per_mwh"] > 0
    assert quote["benchmark_system_price_gbp_per_mwh"] is None
    assert quote["savings_vs_benchmark_gbp_per_mwh"] is None


def test_get_quote_populates_benchmark_with_seeded_history(with_seeded_db):
    quote = get_quote("factory", 0.5, date(2026, 8, 5), settlement_period=36)

    assert quote["benchmark_system_price_gbp_per_mwh"] is not None
    assert quote["savings_vs_benchmark_gbp_per_mwh"] is not None
