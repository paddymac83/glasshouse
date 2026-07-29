from __future__ import annotations


def test_latest_prices_returns_seeded_data(api_client, with_seeded_db):
    response = api_client.get("/api/prices/latest/", {"limit": 3})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3
    assert all("system_sell_price" in row for row in body)


def test_latest_prices_respects_the_limit_param(api_client, with_seeded_db):
    response = api_client.get("/api/prices/latest/", {"limit": 1})

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_latest_prices_404s_cleanly_when_no_db_exists(api_client, with_no_db):
    response = api_client.get("/api/prices/latest/")

    assert response.status_code == 404
    assert "ingestion" in response.json()["detail"].lower()
