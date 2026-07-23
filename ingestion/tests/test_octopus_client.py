from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from glasshouse_ingestion.models import AgileUnitRate
from glasshouse_ingestion.octopus_client import OctopusApiError, OctopusClient


def _client_with_response(json_body: dict, status_code: int = 200) -> OctopusClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=json_body, request=request)

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport, base_url="https://api.octopus.energy/v1")
    return OctopusClient(http_client=http_client)


def test_get_standard_unit_rates_parses_fixture(octopus_rates_payload):
    client = _client_with_response(octopus_rates_payload)

    rates = client.get_standard_unit_rates(
        product_code="AGILE-24-10-01",
        tariff_code="E-1R-AGILE-24-10-01-C",
        period_from=datetime(2026, 7, 22, tzinfo=timezone.utc),
        period_to=datetime(2026, 7, 23, tzinfo=timezone.utc),
    )

    assert len(rates) == 2
    assert all(isinstance(r, AgileUnitRate) for r in rates)
    assert rates[0].unit_rate_inc_vat_pence_per_kwh == pytest.approx(19.43)


def test_non_200_response_raises_octopus_api_error(octopus_rates_payload):
    client = _client_with_response(octopus_rates_payload, status_code=404)

    with pytest.raises(OctopusApiError, match="404"):
        client.get_standard_unit_rates(
            product_code="AGILE-24-10-01",
            tariff_code="E-1R-AGILE-24-10-01-C",
            period_from=datetime(2026, 7, 22, tzinfo=timezone.utc),
            period_to=datetime(2026, 7, 23, tzinfo=timezone.utc),
        )
