from __future__ import annotations


def test_latest_prices_returns_seeded_data(client):
    response = client.get("/prices/latest", params={"limit": 3})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3
    assert all("system_sell_price" in row for row in body)


def test_latest_prices_respects_the_limit_param(client):
    response = client.get("/prices/latest", params={"limit": 1})

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_latest_prices_404s_cleanly_when_no_db_exists(client_with_no_db):
    response = client_with_no_db.get("/prices/latest")

    assert response.status_code == 404
    assert "ingestion" in response.json()["detail"].lower()
