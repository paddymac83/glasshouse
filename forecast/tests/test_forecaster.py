from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from glasshouse_forecast.seasonal_baseline import InsufficientHistoryError, SeasonalBaselineForecaster


def test_forecast_system_prices_reads_from_sqlite(seeded_db):
    target = date(2026, 8, 5)
    for offset, price in zip((1, 2, 3), (61.0, 62.0, 63.0)):
        seeded_db.insert_price(target - timedelta(weeks=offset), period=17, sell_price=price)

    with SeasonalBaselineForecaster(seeded_db.path) as forecaster:
        points = forecaster.forecast_system_prices(target)

    period_17 = next(p for p in points if p.settlement_period == 17)
    assert period_17.forecast_value == pytest.approx(62.0)
    assert period_17.sample_size == 3
    assert period_17.fallback_used is False


def test_forecast_fuel_generation_filters_by_fuel_type(seeded_db):
    target = date(2026, 8, 5)
    for offset in (1, 2, 3):
        d = target - timedelta(weeks=offset)
        seeded_db.insert_generation(d, period=5, fuel_type="WIND", generation_mw=1000.0)
        seeded_db.insert_generation(d, period=5, fuel_type="CCGT", generation_mw=5000.0)

    with SeasonalBaselineForecaster(seeded_db.path) as forecaster:
        wind_points = forecaster.forecast_fuel_generation(target, "WIND")

    period_5 = next(p for p in wind_points if p.settlement_period == 5)
    # Must be the WIND-only average (1000), not blended with CCGT's 5000.
    assert period_5.forecast_value == pytest.approx(1000.0)


def test_missing_db_file_raises_a_clear_error(tmp_path):
    missing = tmp_path / "does_not_exist.db"

    with pytest.raises(FileNotFoundError, match="run ingestion first"):
        SeasonalBaselineForecaster(missing)


def test_empty_db_raises_insufficient_history(seeded_db):
    with SeasonalBaselineForecaster(seeded_db.path) as forecaster:
        with pytest.raises(InsufficientHistoryError):
            forecaster.forecast_system_prices(date(2026, 8, 5))


def test_forecaster_cannot_write_to_the_store(seeded_db):
    with SeasonalBaselineForecaster(seeded_db.path) as forecaster:
        with pytest.raises(sqlite3.OperationalError):
            forecaster._conn.execute(
                "INSERT INTO settlement_prices VALUES ('2026-01-01', 1, 1.0, 1.0)"
            )
