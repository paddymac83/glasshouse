"""Typed models for the market data Glasshouse ingests.

These are intentionally narrow -- just the fields the settlement engine
and forecaster actually need -- rather than a full mirror of the upstream
API responses. Keeping the parse step separate from these models means
a schema change upstream is a one-file fix in `elexon_client.py` or
`octopus_client.py`, not a change scattered across the codebase.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field


class SettlementPrice(BaseModel):
    """GB system sell/buy price for one half-hourly settlement period.

    Settlement periods run 1-50 (48 on a normal day, 46/50 on clock-change
    days) and represent consecutive 30-minute windows starting at 00:00
    local time on the settlement date.
    """

    settlement_date: date
    settlement_period: int = Field(ge=1, le=50)
    system_sell_price: float = Field(description="GBP/MWh")
    system_buy_price: float = Field(description="GBP/MWh")

    @property
    def period_start(self) -> datetime:
        """UTC-naive start of this settlement period (ignores DST edge cases)."""
        minutes = (self.settlement_period - 1) * 30
        return datetime.combine(self.settlement_date, datetime.min.time()) + timedelta(minutes=minutes)


class FuelType(StrEnum):
    GAS = "CCGT"
    NUCLEAR = "NUCLEAR"
    WIND = "WIND"
    SOLAR = "SOLAR"
    COAL = "COAL"
    BIOMASS = "BIOMASS"
    HYDRO = "NPSHYD"
    PUMPED_STORAGE = "PS"
    INTERCONNECTOR = "INTFR"
    OTHER = "OTHER"


class FuelTypeGeneration(BaseModel):
    """Half-hourly GB generation outturn for a single fuel type, in MW."""

    settlement_date: date
    settlement_period: int = Field(ge=1, le=50)
    fuel_type: str
    generation_mw: float


class AgileUnitRate(BaseModel):
    """A single half-hourly unit rate from an Octopus half-hourly tariff
    (Agile Octopus or Tracker), used as a real-world benchmark price.
    """

    valid_from: datetime
    valid_to: datetime
    unit_rate_inc_vat_pence_per_kwh: float
