from __future__ import annotations

from datetime import date

import httpx
import pytest

from glasshouse_ingestion.elexon_client import ElexonApiError, ElexonClient
from glasshouse_ingestion.models import FuelTypeGeneration, SettlementPrice


def _client_with_response(json_body: dict | list, status_code: int = 200) -> ElexonClient:
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


def test_get_fuel_type_generation_hits_the_stream_endpoint_with_a_date_range():
    """Regression test for a real bug found against the live API on
    2026-07-25: /datasets/FUELHH (no /stream) silently ignores any date
    filter and just returns whatever is most recent, regardless of what
    was requested -- confirmed by querying two very different historical
    dates and getting today's date back both times. Only
    /datasets/FUELHH/stream actually filters historically, and it wants
    a settlementDateFrom/settlementDateTo range rather than a single
    settlementDate. This test pins the request shape itself (not just
    response parsing), so a regression here fails immediately rather
    than silently reintroducing the original bug.
    """
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=[], request=request)

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport, base_url="https://data.elexon.co.uk/bmrs/api/v1")
    client = ElexonClient(http_client=http_client)

    client.get_fuel_type_generation(date(2026, 5, 1))

    assert captured["path"] == "/bmrs/api/v1/datasets/FUELHH/stream"
    assert captured["params"]["settlementDateFrom"] == "2026-05-01"
    assert captured["params"]["settlementDateTo"] == "2026-05-01"


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
