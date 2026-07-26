from __future__ import annotations


def test_forecast_system_prices_returns_points_for_seeded_history(client):
    response = client.get("/forecast/system-prices", params={"date": "2026-08-05"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3  # seeded fixture only has periods 1, 36, 48
    period_36 = next(p for p in body if p["settlement_period"] == 36)
    assert period_36["fallback_used"] is False
    assert period_36["sample_size"] == 8


def test_forecast_system_prices_404s_when_theres_no_history_at_all(client_with_no_db):
    response = client_with_no_db.get("/forecast/system-prices", params={"date": "2026-08-05"})

    assert response.status_code == 404


def test_forecast_fuel_generation_returns_wind_points(client):
    response = client.get(
        "/forecast/fuel-generation", params={"date": "2026-08-05", "fuel_type": "WIND"}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3
    assert all(p["forecast_value"] > 0 for p in body)


def test_forecast_fuel_generation_404s_for_a_fuel_type_with_no_history(client):
    response = client.get(
        "/forecast/fuel-generation", params={"date": "2026-08-05", "fuel_type": "SOLAR"}
    )

    assert response.status_code == 404
