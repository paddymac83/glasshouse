"""Seasonal baseline (climatological) forecaster.

The model: for each settlement period, forecast the mean of that
period's historical value across every past date sharing the target
date's day of week -- e.g. every past Wednesday's period-17 price,
averaged, forecasts this Wednesday's period-17 price. Falls back to
averaging across *all* past days for that period (ignoring day of
week) when there isn't enough same-weekday history yet, and flags on
the result when it had to.

This is deliberately the simplest model that could plausibly work: a
baseline to sanity-check any fancier model (lightgbm, etc.) against
later, not a finished forecaster -- see ../README.md.

`seasonal_average` is pure and I/O-free on purpose: the averaging logic
is tested directly with plain in-memory data (tests/test_seasonal_average.py),
with no SQLite fixture needed for most of its test cases.
`SeasonalBaselineForecaster` is the thin, separately-tested layer that
reads real rows out of ingestion's SQLite store and hands them to it.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean, pstdev

from glasshouse_forecast.models import ForecastPoint

MIN_SAME_WEEKDAY_SAMPLES = 3
DEFAULT_PERIOD_RANGE = range(1, 49)  # a normal (non clock-change) day: periods 1-48


class InsufficientHistoryError(RuntimeError):
    """Raised when there's no historical data at all to forecast a single period from."""


def _sqlite_day_of_week(d: date) -> int:
    """0=Sunday..6=Saturday -- SQLite's strftime('%w', ...) convention.

    Python's date.weekday() uses 0=Monday..6=Sunday, so this remaps it;
    keeping everything in SQLite's convention means a raw SQL query
    against the same tables would group identically to this function.
    """
    return (d.weekday() + 1) % 7


def seasonal_average(
    history: list[tuple[date, int, float]],
    target_date: date,
    period_range: range = DEFAULT_PERIOD_RANGE,
    min_same_weekday_samples: int = MIN_SAME_WEEKDAY_SAMPLES,
) -> list[ForecastPoint]:
    """Pure averaging logic: (date, settlement_period, value) triples in,
    ForecastPoints out. No I/O, no SQLite, no Elexon -- just the model.
    See the module docstring for what the model actually is.

    Periods with zero historical data are omitted from the result
    entirely rather than fabricated as a 0.0 forecast. Raises
    InsufficientHistoryError only if *every* period in period_range
    comes back empty -- a single missing period is a normal, expected
    outcome for a mostly-populated store, not an error.
    """
    target_dow = _sqlite_day_of_week(target_date)

    by_weekday_period: dict[tuple[int, int], list[float]] = defaultdict(list)
    by_period: dict[int, list[float]] = defaultdict(list)
    for record_date, period, value in history:
        by_weekday_period[(_sqlite_day_of_week(record_date), period)].append(value)
        by_period[period].append(value)

    points: list[ForecastPoint] = []
    for period in period_range:
        same_weekday_values = by_weekday_period.get((target_dow, period), [])
        if len(same_weekday_values) >= min_same_weekday_samples:
            values, fallback_used = same_weekday_values, False
        else:
            values, fallback_used = by_period.get(period, []), True

        if not values:
            continue

        points.append(
            ForecastPoint(
                settlement_date=target_date,
                settlement_period=period,
                forecast_value=mean(values),
                sample_size=len(values),
                std_dev=pstdev(values) if len(values) > 1 else 0.0,
                fallback_used=fallback_used,
            )
        )

    if not points:
        raise InsufficientHistoryError(
            f"no historical data at all for any period in {period_range.start}-{period_range.stop - 1}"
        )
    return points


class SeasonalBaselineForecaster:
    """Reads settlement_prices / fuel_generation rows out of Glasshouse's
    SQLite store and applies `seasonal_average` to them.

    Opens the database read-only (SQLite URI mode) -- a forecaster has
    no business writing to the store ingestion owns, and this makes
    that a guarantee rather than a convention.
    """

    def __init__(self, db_path: str | Path = "glasshouse.db") -> None:
        db_path = Path(db_path)
        if not db_path.exists():
            raise FileNotFoundError(
                f"no database at {db_path} -- run ingestion first "
                f"(see ingestion/README.md) or pass the right --db path"
            )
        self._conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "SeasonalBaselineForecaster":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def forecast_system_prices(self, target_date: date) -> list[ForecastPoint]:
        history = self._load(
            "SELECT settlement_date, settlement_period, system_sell_price FROM settlement_prices"
        )
        return seasonal_average(history, target_date)

    def forecast_fuel_generation(self, target_date: date, fuel_type: str) -> list[ForecastPoint]:
        history = self._load(
            "SELECT settlement_date, settlement_period, generation_mw FROM fuel_generation WHERE fuel_type = ?",
            (fuel_type,),
        )
        return seasonal_average(history, target_date)

    def _load(self, query: str, params: tuple = ()) -> list[tuple[date, int, float]]:
        cursor = self._conn.execute(query, params)
        return [(date.fromisoformat(row[0]), row[1], row[2]) for row in cursor.fetchall()]
