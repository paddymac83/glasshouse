"""glasshouse_forecast

Day-ahead demand/generation forecasting, so the settlement engine can
price a portfolio *before* real half-hourly outturn data exists for
that period -- which is the situation any real supplier is actually in.

Currently a seasonal baseline (climatological average by day-of-week
and settlement period) -- see seasonal_baseline.py and ../README.md
for why that's a deliberate starting point, not the final model.
"""

from glasshouse_forecast.models import ForecastPoint
from glasshouse_forecast.seasonal_baseline import (
    InsufficientHistoryError,
    SeasonalBaselineForecaster,
    seasonal_average,
)

__all__ = [
    "ForecastPoint",
    "SeasonalBaselineForecaster",
    "InsufficientHistoryError",
    "seasonal_average",
]
__version__ = "0.1.0"
