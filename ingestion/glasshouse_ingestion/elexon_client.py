"""Client for Elexon's Insights Solution API.

The API is public and requires no key: https://developer.data.elexon.co.uk/

NOTE ON SCHEMA ASSUMPTIONS: the field names below (`settlementDate`,
`settlementPeriod`, `systemSellPrice`, `systemBuyPrice`, `fuelType`,
`generation`) are taken from Elexon's published API docs and the
community `elexonpy` client's response models, not from a live call --
this environment's network allowlist doesn't include data.elexon.co.uk.
Before relying on this against production data, run
`glasshouse-ingest elexon-prices --date <today>` once against the real
API and diff the raw JSON against `tests/fixtures/elexon_system_prices.json`.
If a field has moved, `_parse_system_price` / `_parse_fuel_generation`
are the only two places you need to touch.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from glasshouse_ingestion.models import FuelTypeGeneration, SettlementPrice

DEFAULT_BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"


class ElexonApiError(RuntimeError):
    """Raised when the Elexon API returns an unexpected shape or status."""


class ElexonClient:
    """Thin, typed wrapper around the handful of Elexon endpoints Glasshouse needs."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        http_client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._client = http_client or httpx.Client(base_url=base_url, timeout=timeout)
        self._owns_client = http_client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "ElexonClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- public API ---------------------------------------------------

    def get_system_prices(self, settlement_date: date) -> list[SettlementPrice]:
        """Half-hourly system sell/buy prices for a given settlement date."""
        response = self._client.get(
            "/balancing/settlement/system-prices/" + settlement_date.isoformat(),
        )
        records = self._unwrap(response)
        return [self._parse_system_price(record) for record in records]

    def get_fuel_type_generation(self, settlement_date: date) -> list[FuelTypeGeneration]:
        """Half-hourly generation outturn by fuel type for a given date."""
        response = self._client.get(
            "/datasets/FUELHH",
            params={"settlementDate": settlement_date.isoformat()},
        )
        records = self._unwrap(response)
        return [self._parse_fuel_generation(record) for record in records]

    # -- parsing --------------------------------------------------------

    @staticmethod
    def _unwrap(response: httpx.Response) -> list[dict[str, Any]]:
        if response.status_code != 200:
            raise ElexonApiError(
                f"Elexon API returned {response.status_code} for {response.url}: "
                f"{response.text[:300]}"
            )
        payload = response.json()
        # The Insights API wraps results in {"data": [...]}. Some legacy
        # endpoints return a bare list -- support both defensively.
        if isinstance(payload, dict) and "data" in payload:
            records = payload["data"]
        elif isinstance(payload, list):
            records = payload
        else:
            raise ElexonApiError(
                f"Unexpected Elexon response shape (keys: "
                f"{list(payload.keys()) if isinstance(payload, dict) else type(payload)})"
            )
        if not isinstance(records, list):
            raise ElexonApiError(f"Expected a list of records, got {type(records)}")
        return records

    @staticmethod
    def _parse_system_price(record: dict[str, Any]) -> SettlementPrice:
        try:
            return SettlementPrice(
                settlement_date=record["settlementDate"],
                settlement_period=record["settlementPeriod"],
                system_sell_price=record["systemSellPrice"],
                system_buy_price=record["systemBuyPrice"],
            )
        except KeyError as exc:
            raise ElexonApiError(f"Missing expected field {exc} in system price record: {record}") from exc

    @staticmethod
    def _parse_fuel_generation(record: dict[str, Any]) -> FuelTypeGeneration:
        try:
            return FuelTypeGeneration(
                settlement_date=record["settlementDate"],
                settlement_period=record["settlementPeriod"],
                fuel_type=record["fuelType"],
                generation_mw=record["generation"],
            )
        except KeyError as exc:
            raise ElexonApiError(f"Missing expected field {exc} in fuel generation record: {record}") from exc
