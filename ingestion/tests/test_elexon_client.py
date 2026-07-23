from __future__ import annotations

from datetime import date

import httpx
import pytest

from glasshouse_ingestion.elexon_client import ElexonApiError, ElexonClient
from glasshouse_ingestion.models import FuelTypeGeneration, SettlementPrice


def _client_with_response(json_body: dict, status_code: int = 200) -> ElexonClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=json_body, request=request)

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport, base_url="https://data.elexon.co.uk/bmrs/api/v1")
    return ElexonClient(http_client=http_client)


def test_get_system_prices_parses_fixture(elexon_system_prices_payload):
    client = _client_with_response(elexon_system_prices_payload)

    prices = client.get_system_prices(date(2026, 7, 22))

    assert len(prices) == 3
    assert all(isinstance(p, SettlementPrice) for p in prices)
    assert prices[0].settlement_period == 1
    assert prices[0].system_sell_price == pytest.approx(65.20)
    # settlement period 3 covers a negative-price half hour -- oversupply
    # happens often enough on a windy day that the model must allow it.
    assert prices[2].system_sell_price < 0


def test_get_fuel_type_generation_parses_fixture(elexon_fuel_hh_payload):
    client = _client_with_response(elexon_fuel_hh_payload)

    records = client.get_fuel_type_generation(date(2026, 7, 22))

    assert len(records) == 3
    assert all(isinstance(r, FuelTypeGeneration) for r in records)
    wind = next(r for r in records if r.fuel_type == "WIND")
    assert wind.generation_mw == pytest.approx(8213.5)


def test_non_200_response_raises_elexon_api_error(elexon_system_prices_payload):
    client = _client_with_response(elexon_system_prices_payload, status_code=503)

    with pytest.raises(ElexonApiError, match="503"):
        client.get_system_prices(date(2026, 7, 22))


def test_missing_field_raises_elexon_api_error():
    client = _client_with_response({"data": [{"settlementDate": "2026-07-22"}]})

    with pytest.raises(ElexonApiError, match="settlementPeriod"):
        client.get_system_prices(date(2026, 7, 22))


def test_unexpected_shape_raises_elexon_api_error():
    client = _client_with_response({"unexpected": "shape"})

    with pytest.raises(ElexonApiError, match="Unexpected"):
        client.get_system_prices(date(2026, 7, 22))
