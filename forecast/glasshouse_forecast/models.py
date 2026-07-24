"""Typed model for a single forecast point.

Deliberately mirrors the shape of ingestion's models: a settlement date
+ period, plus a value -- but with the fields a *forecast* needs that a
historical record doesn't: how many samples it's based on, how spread
out they were, and whether the model had to fall back to a cruder
estimate for this particular period.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class ForecastPoint(BaseModel):
    settlement_date: date
    settlement_period: int = Field(ge=1, le=50)
    forecast_value: float
    sample_size: int = Field(ge=1, description="how many historical data points this average is built from")
    std_dev: float = Field(ge=0.0, description="spread of the historical samples -- a cheap confidence signal")
    fallback_used: bool = Field(
        description="True if there wasn't enough same-weekday history, so this fell back to an all-weekday average"
    )
