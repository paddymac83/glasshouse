"""Pure logic for turning a business type + renewable-share knob into a
one-period portfolio the settlement engine can price.

Kept separate from main.py (no FastAPI import here at all) so it's
testable with plain function calls -- same pure-logic-vs-glue split as
settlement-engine's `settle_period` and forecast's `seasonal_average`.
"""

from __future__ import annotations

from datetime import datetime

from glasshouse_api.models import BusinessType, ConsumerIn, GeneratorIn

# Illustrative half-hourly demand for a single business, in MWh. There's
# no real per-business meter feeding this project -- these are stylised,
# roughly plausible figures for a single settlement period, not measured
# data. See api/README.md.
BUSINESS_DEMAND_MWH: dict[BusinessType, float] = {
    BusinessType.OFFICE: 1.5,
    BusinessType.RETAIL: 2.5,
    BusinessType.FACTORY: 6.0,
    BusinessType.EV_DEPOT: 4.0,
}

# Illustrative marginal costs, GBP/MWh -- wind is cheap and dispatched
# first in merit order; gas is the flexible, more expensive top-up. Not
# derived from live data (unlike the /forecast endpoints' prices).
WIND_COST_GBP_PER_MWH = 30.0
GAS_COST_GBP_PER_MWH = 80.0

# Small headroom over demand so the portfolio can actually cover it
# rather than sitting exactly on the edge every time.
CAPACITY_HEADROOM = 1.15


def build_portfolio(
    business_type: BusinessType, renewable_share: float
) -> tuple[list[GeneratorIn], list[ConsumerIn]]:
    """One consumer (sized to the business type's illustrative demand)
    plus two generators (wind + gas), with `renewable_share` controlling
    what fraction of capacity is wind vs gas.

    This is a *capacity mix* knob, not a literal GB-wide MW figure --
    plugging raw national wind-generation forecasts in directly would
    make wind trivially cover any single small consumer's demand every
    time, making the renewable_share knob meaningless. Scaling capacity
    to the consumer's own size keeps the merit-order trade-off real.
    """
    if not 0.0 <= renewable_share <= 1.0:
        raise ValueError(f"renewable_share must be between 0 and 1, got {renewable_share}")

    demand_mwh = BUSINESS_DEMAND_MWH[business_type]
    total_capacity = demand_mwh * CAPACITY_HEADROOM

    generators = [
        GeneratorIn(
            id="wind_portfolio",
            available_mwh=total_capacity * renewable_share,
            cost_gbp_per_mwh=WIND_COST_GBP_PER_MWH,
        ),
        GeneratorIn(
            id="gas_portfolio",
            available_mwh=total_capacity * (1 - renewable_share),
            cost_gbp_per_mwh=GAS_COST_GBP_PER_MWH,
        ),
    ]
    consumers = [ConsumerIn(id=business_type.value, demand_mwh=demand_mwh)]
    return generators, consumers


def default_settlement_period(now: datetime | None = None) -> int:
    """Which settlement period covers "right now": period 1 is
    00:00-00:30, period 48 is 23:30-00:00, on a normal (non
    clock-change) day.
    """
    now = now or datetime.now()
    return (now.hour * 2) + (1 if now.minute >= 30 else 0) + 1
