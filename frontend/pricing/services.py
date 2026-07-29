"""Shared business logic, called directly by both the DRF API views and
the template-rendering dashboard view -- so the dashboard never makes
an HTTP request to this same project's own API. See README.md's "why
this doesn't call itself over HTTP" note for the reasoning; it's the
same in-process-over-HTTP-hop principle as
docs/adr/0001-python-rust-boundary.md, just applied one layer up.

This is a deliberate parallel implementation of api/glasshouse_api's
quote.py + main.py's helper functions, not a wrapper around them --
see frontend/README.md for why api/ (FastAPI) still exists separately
rather than being retired or called from here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime
from pathlib import Path

import glasshouse_settlement
from glasshouse_forecast import InsufficientHistoryError, SeasonalBaselineForecaster
from glasshouse_ingestion.storage import Storage

DEFAULT_DB_PATH = "../ingestion/glasshouse.db"


def get_ingestion_db_path() -> Path:
    return Path(os.environ.get("GLASSHOUSE_INGESTION_DB", DEFAULT_DB_PATH))


# Illustrative half-hourly demand per business, in MWh -- there's no
# real per-business meter feeding this project. Same figures as
# api/glasshouse_api/quote.py, kept in sync by hand -- see that file's
# module docstring for the reasoning (capacity mix, not a literal
# GB-wide MW figure).
BUSINESS_DEMAND_MWH: dict[str, float] = {
    "office": 1.5,
    "retail": 2.5,
    "factory": 6.0,
    "ev_depot": 4.0,
}
BUSINESS_TYPE_CHOICES: list[str] = list(BUSINESS_DEMAND_MWH.keys())

WIND_COST_GBP_PER_MWH = 30.0
GAS_COST_GBP_PER_MWH = 80.0
CAPACITY_HEADROOM = 1.15


class SettlementInputError(ValueError):
    """Invalid input, whether caught before reaching the Rust engine
    (e.g. an unknown business_type) or raised by the engine itself
    (e.g. an empty consumer list) -- one exception type either way, so
    callers only need to catch one thing.
    """


def default_settlement_period(now: datetime | None = None) -> int:
    """Which settlement period covers "right now": period 1 is
    00:00-00:30, period 48 is 23:30-00:00, on a normal (non
    clock-change) day.
    """
    now = now or datetime.now()
    return (now.hour * 2) + (1 if now.minute >= 30 else 0) + 1


def build_portfolio(business_type: str, renewable_share: float) -> tuple[list[dict], list[dict]]:
    """One consumer (sized to the business type's illustrative demand)
    plus two generators (wind + gas), with `renewable_share` controlling
    the capacity mix. See module docstring re: this being illustrative.
    """
    if business_type not in BUSINESS_DEMAND_MWH:
        raise SettlementInputError(
            f"unknown business_type {business_type!r}, expected one of {BUSINESS_TYPE_CHOICES}"
        )
    if not 0.0 <= renewable_share <= 1.0:
        raise SettlementInputError(f"renewable_share must be between 0 and 1, got {renewable_share}")

    demand_mwh = BUSINESS_DEMAND_MWH[business_type]
    total_capacity = demand_mwh * CAPACITY_HEADROOM

    generators = [
        {
            "id": "wind_portfolio",
            "available_mwh": total_capacity * renewable_share,
            "cost_gbp_per_mwh": WIND_COST_GBP_PER_MWH,
        },
        {
            "id": "gas_portfolio",
            "available_mwh": total_capacity * (1 - renewable_share),
            "cost_gbp_per_mwh": GAS_COST_GBP_PER_MWH,
        },
    ]
    consumers = [{"id": business_type, "demand_mwh": demand_mwh}]
    return generators, consumers


def settle(
    generators: list[dict],
    consumers: list[dict],
    network_charge_gbp_per_mwh: float = 20.0,
    policy_cost_gbp_per_mwh: float = 15.0,
    platform_margin_fraction: float = 0.05,
) -> dict:
    """Direct, in-process call into the Rust settlement engine -- same
    package (glasshouse_settlement), same pattern as api/, just called
    from a different Python process.
    """
    try:
        return glasshouse_settlement.settle_period_py(
            generators=[(g["id"], g["available_mwh"], g["cost_gbp_per_mwh"]) for g in generators],
            consumers=[(c["id"], c["demand_mwh"]) for c in consumers],
            network_charge_gbp_per_mwh=network_charge_gbp_per_mwh,
            policy_cost_gbp_per_mwh=policy_cost_gbp_per_mwh,
            platform_margin_fraction=platform_margin_fraction,
        )
    except ValueError as exc:
        raise SettlementInputError(str(exc)) from exc


@dataclass
class Benchmark:
    price_gbp_per_mwh: float
    sample_size: int
    fallback_used: bool


def get_benchmark(
    target_date: date_type, settlement_period: int, db_path: Path | None = None
) -> Benchmark | None:
    """Seasonal-baseline forecast for one period, or None if there's no
    history yet (or no DB at all) -- not an error, same design choice
    as api/'s /quote endpoint (see api/README.md).
    """
    db_path = db_path or get_ingestion_db_path()
    if not db_path.exists():
        return None
    with SeasonalBaselineForecaster(db_path) as forecaster:
        try:
            points = forecaster.forecast_system_prices(target_date)
        except InsufficientHistoryError:
            return None
    match = next((p for p in points if p.settlement_period == settlement_period), None)
    if match is None:
        return None
    return Benchmark(
        price_gbp_per_mwh=match.forecast_value,
        sample_size=match.sample_size,
        fallback_used=match.fallback_used,
    )


def get_quote(
    business_type: str,
    renewable_share: float,
    target_date: date_type,
    settlement_period: int | None = None,
    db_path: Path | None = None,
) -> dict:
    """The one-click quote: build a portfolio, settle it, benchmark it
    against real forecast history. Django-side port of api/'s /quote.
    """
    period = settlement_period or default_settlement_period()
    generators, consumers = build_portfolio(business_type, renewable_share)
    settlement_result = settle(generators, consumers)

    benchmark = get_benchmark(target_date, period, db_path=db_path)
    savings = (
        benchmark.price_gbp_per_mwh - settlement_result["blended_generation_price_gbp_per_mwh"]
        if benchmark is not None
        else None
    )

    return {
        "settlement_date": target_date.isoformat(),
        "settlement_period": period,
        "business_type": business_type,
        "renewable_share": renewable_share,
        "settlement": settlement_result,
        "benchmark_system_price_gbp_per_mwh": benchmark.price_gbp_per_mwh if benchmark else None,
        "benchmark_sample_size": benchmark.sample_size if benchmark else None,
        "benchmark_fallback_used": benchmark.fallback_used if benchmark else None,
        "savings_vs_benchmark_gbp_per_mwh": savings,
    }


def get_latest_prices(limit: int = 48, db_path: Path | None = None) -> list[dict]:
    db_path = db_path or get_ingestion_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"no ingestion database at {db_path} -- see ingestion/README.md")
    with Storage(db_path) as store:
        prices = store.latest_system_prices(limit=limit)
    return [p.model_dump(mode="json") for p in prices]


def get_forecast_system_prices(target_date: date_type, db_path: Path | None = None) -> list[dict]:
    db_path = db_path or get_ingestion_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"no ingestion database at {db_path} -- see ingestion/README.md")
    with SeasonalBaselineForecaster(db_path) as forecaster:
        points = forecaster.forecast_system_prices(target_date)  # may raise InsufficientHistoryError
    return [p.model_dump(mode="json") for p in points]


def get_forecast_fuel_generation(
    target_date: date_type, fuel_type: str, db_path: Path | None = None
) -> list[dict]:
    db_path = db_path or get_ingestion_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"no ingestion database at {db_path} -- see ingestion/README.md")
    with SeasonalBaselineForecaster(db_path) as forecaster:
        points = forecaster.forecast_fuel_generation(target_date, fuel_type)  # may raise InsufficientHistoryError
    return [p.model_dump(mode="json") for p in points]
