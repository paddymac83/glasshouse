from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from glasshouse_api.main import app

client = TestClient(app)


def test_settle_returns_the_known_worked_example():
    """Same numbers as settlement-engine's own Rust unit tests and the
    Python bridge test -- this is the full stack (HTTP -> FastAPI ->
    PyO3 -> Rust) producing the identical, already-verified result.
    """
    response = client.post(
        "/settle",
        json={
            "generators": [
                {"id": "wind_farm_1", "available_mwh": 5.0, "cost_gbp_per_mwh": 30.0},
                {"id": "gas_peaker", "available_mwh": 100.0, "cost_gbp_per_mwh": 80.0},
            ],
            "consumers": [
                {"id": "bakery", "demand_mwh": 2.0},
                {"id": "brewery", "demand_mwh": 8.0},
            ],
            "tariff": {
                "network_charge_gbp_per_mwh": 20.0,
                "policy_cost_gbp_per_mwh": 15.0,
                "platform_margin_fraction": 0.05,
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["blended_generation_price_gbp_per_mwh"] == pytest.approx(55.0)
    assert body["unmet_demand_mwh"] == 0.0

    bakery = next(b for b in body["bills"] if b["consumer_id"] == "bakery")
    brewery = next(b for b in body["bills"] if b["consumer_id"] == "brewery")
    assert bakery["total_gbp"] == pytest.approx(189.0)
    assert brewery["total_gbp"] == pytest.approx(756.0)


def test_settle_uses_default_tariff_when_omitted():
    response = client.post(
        "/settle",
        json={
            "generators": [{"id": "solar", "available_mwh": 10.0, "cost_gbp_per_mwh": 40.0}],
            "consumers": [{"id": "shop", "demand_mwh": 5.0}],
        },
    )

    assert response.status_code == 200


def test_settle_rejects_an_empty_consumer_list_with_422_not_500():
    """The Rust engine raises a ValueError for this; the API should
    surface it as a client error (422), not an unhandled 500.
    """
    response = client.post(
        "/settle",
        json={
            "generators": [{"id": "solar", "available_mwh": 10.0, "cost_gbp_per_mwh": 40.0}],
            "consumers": [],
        },
    )

    assert response.status_code == 422
    assert "consumer" in response.json()["detail"].lower()


def test_settle_rejects_negative_demand_at_the_schema_level():
    """This one should be rejected by pydantic validation before it
    ever reaches the Rust engine -- ge=0 on demand_mwh.
    """
    response = client.post(
        "/settle",
        json={
            "generators": [{"id": "solar", "available_mwh": 10.0, "cost_gbp_per_mwh": 40.0}],
            "consumers": [{"id": "shop", "demand_mwh": -5.0}],
        },
    )

    assert response.status_code == 422
