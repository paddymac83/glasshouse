# forecast/

Day-ahead demand and generation forecasting, so the settlement engine
can price a portfolio *before* actual half-hourly outturn data exists
for that period -- which is the situation any real supplier is
actually in.

## The model: seasonal baseline

For each settlement period, the forecast is the mean of that period's
historical value across every past date sharing the target date's day
of week -- every past Wednesday's period-17 price, averaged, forecasts
this Wednesday's period-17 price. If there isn't at least 3 same-weekday
samples yet, it falls back to averaging across *all* past days for that
period, and flags the result so callers can tell a confident forecast
from a "we don't have enough data yet" one.

This is deliberately the simplest model that could plausibly work,
not a finished forecaster. Two things it gets right that matter more
than sophistication at this stage:

- **The averaging logic is pure and untangled from I/O** (`seasonal_average`
  in `seasonal_baseline.py`), so it's tested directly with plain
  in-memory data -- no SQLite fixture needed for most cases. The thin
  SQLite-reading layer (`SeasonalBaselineForecaster`) is tested
  separately, against a real temp database.
- **It never fabricates data.** A settlement period with zero history
  is omitted from the result, not silently forecast as `0.0`. A date
  with *no* history at all raises `InsufficientHistoryError` rather
  than returning an empty, misleadingly-successful result.

Once there's enough real history collected to make it worthwhile, the
natural next step is a gradient-boosted model (`lightgbm`) trained on
the same store, benchmarked against this baseline -- if it can't beat
a same-weekday average, it isn't earning its complexity.

## Usage

```bash
cd forecast
uv venv && uv pip install -e ".[dev]"
uv run pytest -v                # 12 tests: 7 pure-logic, 5 against real SQLite

# Assumes ../ingestion/glasshouse.db already has a few weeks of history
# (see ingestion/README.md):
uv run glasshouse-forecast --db ../ingestion/glasshouse.db system-prices --date 2026-08-05
uv run glasshouse-forecast --db ../ingestion/glasshouse.db fuel-generation --fuel-type WIND --date 2026-08-05
```

Note the `--db` flag comes *before* the subcommand (`system-prices` /
`fuel-generation`) -- it's a top-level argument, same pattern as
`ingestion`'s CLI.

As a library, from `api/` or anywhere else:

```python
from datetime import date
from glasshouse_forecast import SeasonalBaselineForecaster

with SeasonalBaselineForecaster("../ingestion/glasshouse.db") as forecaster:
    points = forecaster.forecast_system_prices(date(2026, 8, 5))
    # [ForecastPoint(settlement_period=1, forecast_value=35.7, sample_size=8, ...), ...]
```

## Why this doesn't depend on the `ingestion` package

`forecast` only ever reads two tables (`settlement_prices`,
`fuel_generation`) that `ingestion` happens to own. Rather than add a
package dependency for that, the schema is treated as a shared,
documented contract -- `forecast`'s own tests build the same two
tables locally (see `tests/conftest.py`, kept in sync by hand with
`ingestion/glasshouse_ingestion/storage.py`). If `ingestion` ever
switches to Postgres/TimescaleDB, only its own `Storage` class and
`forecast`'s read queries need to change -- not a shared dependency
graph between two otherwise-independent services.

## A worked example

Seeding 8 weeks of synthetic-but-realistic price data (cheap overnight,
an evening peak around 6pm) and forecasting a Wednesday recovers the
shape correctly, with every period using the confident same-weekday
path (`n=8`, no fallback) rather than the coarser all-days average:

```
period    forecast    ±stdev     n  fallback?
     1       35.71      1.97     8
    ...
    36       74.73      2.13     8
    37       76.11      1.12     8
    38       72.64      1.68     8
    ...
    48       41.62      1.69     8
```
