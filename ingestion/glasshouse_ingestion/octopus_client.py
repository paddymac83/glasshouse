"""Client for Octopus Energy's public REST API.

Product and tariff-rate endpoints are public and unauthenticated -- see
https://docs.octopus.energy/rest/guides/endpoints/. This is used purely
as a real-world benchmark: Glasshouse computes its own "should-cost"
half-hourly price and compares it against what a real published dynamic
tariff (Agile Octopus) charged for the same period.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from glasshouse_ingestion.models import AgileUnitRate

DEFAULT_BASE_URL = "https://api.octopus.energy/v1"


class OctopusApiError(RuntimeError):
    """Raised when the Octopus API returns an unexpected shape or status."""


class OctopusClient:
    """Thin wrapper around the public product/tariff-rate endpoints."""

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

    def __enter__(self) -> "OctopusClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def get_standard_unit_rates(
        self,
        product_code: str,
        tariff_code: str,
        period_from: datetime,
        period_to: datetime,
    ) -> list[AgileUnitRate]:
        """Half-hourly unit rates (inc. VAT, pence/kWh) for a tariff.

        Example: product_code="AGILE-24-10-01",
        tariff_code="E-1R-AGILE-24-10-01-C" (region C = London).
        """
        url = (
            f"/products/{product_code}/electricity-tariffs/"
            f"{tariff_code}/standard-unit-rates/"
        )
        response = self._client.get(
            url,
            params={
                "period_from": period_from.strftime("%Y-%m-%dT%H:%MZ"),
                "period_to": period_to.strftime("%Y-%m-%dT%H:%MZ"),
            },
        )
        records = self._unwrap(response)
        return [self._parse_rate(record) for record in records]

    @staticmethod
    def _unwrap(response: httpx.Response) -> list[dict[str, Any]]:
        if response.status_code != 200:
            raise OctopusApiError(
                f"Octopus API returned {response.status_code} for {response.url}: "
                f"{response.text[:300]}"
            )
        payload = response.json()
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            raise OctopusApiError(f"Unexpected Octopus response shape: {str(payload)[:300]}")
        return results

    @staticmethod
    def _parse_rate(record: dict[str, Any]) -> AgileUnitRate:
        try:
            return AgileUnitRate(
                valid_from=record["valid_from"],
                valid_to=record["valid_to"],
                unit_rate_inc_vat_pence_per_kwh=record["value_inc_vat"],
            )
        except KeyError as exc:
            raise OctopusApiError(f"Missing expected field {exc} in rate record: {record}") from exc
