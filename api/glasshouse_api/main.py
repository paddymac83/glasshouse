"""Glasshouse API: wires ingestion, forecast, and settlement-engine
together behind FastAPI.

    GET  /health
    GET  /prices/latest?limit=48
    GET  /forecast/system-prices?date=2026-08-05
    GET  /forecast/fuel-generation?fuel_type=WIND&date=2026-08-05
    POST /settle
    GET  /quote?date=2026-08-05&business_type=factory&renewable_share=0.6

Run it:
    uv run uvicorn glasshouse_api.main:app --reload

`/settle` and `/quote` call `glasshouse_settlement.settle_period_py`
directly, in-process -- no HTTP hop to a separate service. See
docs/adr/0001-python-rust-boundary.md for why.
"""

from __future__ import annotations

from datetime import date as date_type
from pathlib import Path

import glasshouse_settlement
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from glasshouse_forecast import ForecastPoint, InsufficientHistoryError, SeasonalBaselineForecaster
from glasshouse_ingestion.models import SettlementPrice
from glasshouse_ingestion.storage import Storage

from glasshouse_api.config import get_ingestion_db_path
from glasshouse_api.models import BusinessType, QuoteResponse, SettleRequest, SettleResponse
from glasshouse_api.quote import build_portfolio, default_settlement_period

app = FastAPI(
    title="Glasshouse API",
    description=(
        "Half-hourly settlement pricing engine demo. This is a simulation "
        "using public reference data -- not a licensed energy supplier, "
        "not a real tariff. See the repo README."
    ),
    version="0.1.0",
)

# Wide open for local dev against a dashboard on a different port.
# Tighten this before this is ever exposed anywhere but localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/prices/latest", response_model=list[SettlementPrice])
def latest_prices(
    limit: int = Query(48, ge=1, le=336),
    db_path: Path = Depends(get_ingestion_db_path),
) -> list[SettlementPrice]:
    _require_db(db_path)
    with Storage(db_path) as store:
        return store.latest_system_prices(limit=limit)


@app.get("/forecast/system-prices", response_model=list[ForecastPoint])
def forecast_system_prices(
    date: date_type,
    db_path: Path = Depends(get_ingestion_db_path),
) -> list[ForecastPoint]:
    _require_db(db_path)
    with SeasonalBaselineForecaster(db_path) as forecaster:
        try:
            return forecaster.forecast_system_prices(date)
        except InsufficientHistoryError as exc:
            raise HTTPException(404, str(exc)) from exc


@app.get("/forecast/fuel-generation", response_model=list[ForecastPoint])
def forecast_fuel_generation(
    date: date_type,
    fuel_type: str,
    db_path: Path = Depends(get_ingestion_db_path),
) -> list[ForecastPoint]:
    _require_db(db_path)
    with SeasonalBaselineForecaster(db_path) as forecaster:
        try:
            return forecaster.forecast_fuel_generation(date, fuel_type)
        except InsufficientHistoryError as exc:
            raise HTTPException(404, str(exc)) from exc


@app.post("/settle", response_model=SettleResponse)
def settle(request: SettleRequest) -> dict:
    return _call_settlement_engine(request)


@app.get("/quote", response_model=QuoteResponse)
def quote(
    date: date_type,
    business_type: BusinessType,
    renewable_share: float = Query(0.5, ge=0.0, le=1.0),
    settlement_period: int | None = Query(None, ge=1, le=48),
    db_path: Path = Depends(get_ingestion_db_path),
) -> QuoteResponse:
    """The "one click, get a live price" endpoint: builds a synthetic
    portfolio for the given business type, settles it through the Rust
    engine, and benchmarks the result against a seasonal-baseline
    forecast of the real GB system price for the same period.

    Missing forecast history is not an error here (unlike the
    /forecast/* endpoints) -- the settlement result is still useful on
    its own, so the benchmark fields just come back null rather than
    the whole request failing.
    """
    period = settlement_period or default_settlement_period()

    generators, consumers = build_portfolio(business_type, renewable_share)
    settlement_result = _call_settlement_engine(SettleRequest(generators=generators, consumers=consumers))

    benchmark_price = benchmark_sample_size = benchmark_fallback = None
    if db_path.exists():
        with SeasonalBaselineForecaster(db_path) as forecaster:
            try:
                points = forecaster.forecast_system_prices(date)
                match = next((p for p in points if p.settlement_period == period), None)
                if match is not None:
                    benchmark_price = match.forecast_value
                    benchmark_sample_size = match.sample_size
                    benchmark_fallback = match.fallback_used
            except InsufficientHistoryError:
                pass

    savings = (
        benchmark_price - settlement_result["blended_generation_price_gbp_per_mwh"]
        if benchmark_price is not None
        else None
    )

    return QuoteResponse(
        settlement_date=date.isoformat(),
        settlement_period=period,
        business_type=business_type,
        renewable_share=renewable_share,
        settlement=settlement_result,
        benchmark_system_price_gbp_per_mwh=benchmark_price,
        benchmark_sample_size=benchmark_sample_size,
        benchmark_fallback_used=benchmark_fallback,
        savings_vs_benchmark_gbp_per_mwh=savings,
    )


def _require_db(db_path: Path) -> None:
    if not db_path.exists():
        raise HTTPException(404, f"no ingestion database at {db_path} -- see ingestion/README.md")


def _call_settlement_engine(request: SettleRequest) -> dict:
    try:
        return glasshouse_settlement.settle_period_py(
            generators=[(g.id, g.available_mwh, g.cost_gbp_per_mwh) for g in request.generators],
            consumers=[(c.id, c.demand_mwh) for c in request.consumers],
            network_charge_gbp_per_mwh=request.tariff.network_charge_gbp_per_mwh,
            policy_cost_gbp_per_mwh=request.tariff.policy_cost_gbp_per_mwh,
            platform_margin_fraction=request.tariff.platform_margin_fraction,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
