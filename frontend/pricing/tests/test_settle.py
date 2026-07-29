from __future__ import annotations

import pytest


def test_settle_returns_the_known_worked_example(api_client):
    """Same numbers as settlement-engine's own Rust tests, the Python
    bridge test, and api/'s equivalent test -- this is a fourth
    independent confirmation of the same result, this time through
    Django + DRF + Rust.
    """
    response = api_client.post(
        "/api/settle/",
        {
            "generators": [
                {"id": "wind_farm_1", "available_mwh": 5.0, "cost_gbp_per_mwh": 30.0},
                {"id": "gas_peaker", "available_mwh": 100.0, "cost_gbp_per_mwh": 80.0},
            ],
            "consumers": [
                {"id": "bakery", "demand_mwh": 2.0},
                {"id": "brewery", "demand_mwh": 8.0},
            ],
        },
        format="json",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["blended_generation_price_gbp_per_mwh"] == pytest.approx(55.0)

    bakery = next(b for b in body["bills"] if b["consumer_id"] == "bakery")
    brewery = next(b for b in body["bills"] if b["consumer_id"] == "brewery")
    assert bakery["total_gbp"] == pytest.approx(189.0)
    assert brewery["total_gbp"] == pytest.approx(756.0)


def test_settle_uses_default_tariff_when_omitted(api_client):
    response = api_client.post(
        "/api/settle/",
        {
            "generators": [{"id": "solar", "available_mwh": 10.0, "cost_gbp_per_mwh": 40.0}],
            "consumers": [{"id": "shop", "demand_mwh": 5.0}],
        },
        format="json",
    )

    assert response.status_code == 200


def test_settle_rejects_an_empty_consumer_list_with_422_not_500(api_client):
    """DRF's serializer happily accepts an empty list (many=True doesn't
    imply non-empty) -- the Rust engine is what actually rejects this,
    surfaced as a 422 via SettlementInputError, not an unhandled 500.
    """
    response = api_client.post(
        "/api/settle/",
        {
            "generators": [{"id": "solar", "available_mwh": 10.0, "cost_gbp_per_mwh": 40.0}],
            "consumers": [],
        },
        format="json",
    )

    assert response.status_code == 422
    assert "consumer" in response.json()["detail"].lower()


def test_settle_rejects_negative_demand_at_the_serializer_level(api_client):
    """This one's caught by DRF's FloatField(min_value=0) before it ever
    reaches the settlement engine -- a 400, not a 422.
    """
    response = api_client.post(
        "/api/settle/",
        {
            "generators": [{"id": "solar", "available_mwh": 10.0, "cost_gbp_per_mwh": 40.0}],
            "consumers": [{"id": "shop", "demand_mwh": -5.0}],
        },
        format="json",
    )

    assert response.status_code == 400
