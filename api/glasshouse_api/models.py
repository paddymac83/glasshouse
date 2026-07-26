"""Request/response schemas.

These deliberately mirror settlement-engine's own dict shape
(bills / unmet_demand_mwh / blended_generation_price_gbp_per_mwh) --
see settlement-engine/src/lib.rs's settle_period_py -- rather than
inventing a parallel vocabulary for the same data.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class GeneratorIn(BaseModel):
    id: str
    available_mwh: float = Field(ge=0)
    cost_gbp_per_mwh: float = Field(ge=0)


class ConsumerIn(BaseModel):
    id: str
    demand_mwh: float = Field(ge=0)


class TariffAssumptionsIn(BaseModel):
    network_charge_gbp_per_mwh: float = 20.0
    policy_cost_gbp_per_mwh: float = 15.0
    platform_margin_fraction: float = 0.05


class SettleRequest(BaseModel):
    generators: list[GeneratorIn]
    consumers: list[ConsumerIn]
    tariff: TariffAssumptionsIn = TariffAssumptionsIn()


class BillLineOut(BaseModel):
    label: str
    amount_gbp: float


class ConsumerBillOut(BaseModel):
    consumer_id: str
    lines: list[BillLineOut]
    total_gbp: float


class SettleResponse(BaseModel):
    bills: list[ConsumerBillOut]
    unmet_demand_mwh: float
    blended_generation_price_gbp_per_mwh: float


class BusinessType(StrEnum):
    OFFICE = "office"
    RETAIL = "retail"
    FACTORY = "factory"
    EV_DEPOT = "ev_depot"


class QuoteResponse(BaseModel):
    settlement_date: str
    settlement_period: int
    business_type: BusinessType
    renewable_share: float
    settlement: SettleResponse
    benchmark_system_price_gbp_per_mwh: float | None
    benchmark_sample_size: int | None
    benchmark_fallback_used: bool | None
    savings_vs_benchmark_gbp_per_mwh: float | None
