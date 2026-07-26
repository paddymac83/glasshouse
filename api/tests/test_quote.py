from __future__ import annotations


def test_quote_ties_settlement_and_benchmark_together(client):
    response = client.get(
        "/quote",
        params={
            "date": "2026-08-05",
            "business_type": "factory",
            "renewable_share": 0.5,
            "settlement_period": 36,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["settlement_period"] == 36
    assert body["settlement"]["blended_generation_price_gbp_per_mwh"] > 0
    # seeded fixture has real history at period 36 -> benchmark should be populated
    assert body["benchmark_system_price_gbp_per_mwh"] is not None
    assert body["benchmark_fallback_used"] is False
    assert body["savings_vs_benchmark_gbp_per_mwh"] is not None


def test_quote_still_works_with_no_ingestion_history_at_all(client_with_no_db):
    """Missing forecast history shouldn't take down the whole endpoint --
    the settlement result is useful on its own even with no benchmark.
    """
    response = client_with_no_db.get(
        "/quote",
        params={"date": "2026-08-05", "business_type": "office", "settlement_period": 10},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["settlement"]["blended_generation_price_gbp_per_mwh"] > 0
    assert body["benchmark_system_price_gbp_per_mwh"] is None
    assert body["savings_vs_benchmark_gbp_per_mwh"] is None


def test_quote_higher_renewable_share_gives_a_cheaper_blended_price(client):
    """Wind is modelled cheaper than gas (see quote.py) -- more wind in
    the mix should never make the blended price go up.
    """
    all_gas = client.get(
        "/quote",
        params={"date": "2026-08-05", "business_type": "retail", "renewable_share": 0.0, "settlement_period": 1},
    ).json()
    all_wind = client.get(
        "/quote",
        params={"date": "2026-08-05", "business_type": "retail", "renewable_share": 1.0, "settlement_period": 1},
    ).json()

    assert (
        all_wind["settlement"]["blended_generation_price_gbp_per_mwh"]
        < all_gas["settlement"]["blended_generation_price_gbp_per_mwh"]
    )


def test_quote_defaults_settlement_period_to_something_valid_when_omitted(client):
    response = client.get("/quote", params={"date": "2026-08-05", "business_type": "office"})

    assert response.status_code == 200
    assert 1 <= response.json()["settlement_period"] <= 48


def test_quote_rejects_out_of_range_renewable_share(client):
    response = client.get(
        "/quote",
        params={"date": "2026-08-05", "business_type": "office", "renewable_share": 1.5},
    )

    assert response.status_code == 422
