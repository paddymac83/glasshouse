"""glasshouse_ingestion

Pulls public GB electricity market data into Glasshouse's local time-series
store, so the settlement engine has something real to price against.

Data sources:
  - Elexon Insights API (system prices, generation by fuel type) -- public,
    no API key required. Base URL: https://data.elexon.co.uk/bmrs/api/v1
  - Octopus Energy public tariff API (Agile / Tracker unit rates) -- public,
    no API key required for product/tariff-rate lookups. Base URL:
    https://api.octopus.energy/v1
"""

from glasshouse_ingestion.models import FuelTypeGeneration, SettlementPrice

__all__ = ["SettlementPrice", "FuelTypeGeneration"]
__version__ = "0.1.0"
