from __future__ import annotations

from django.test import Client
import pytest


@pytest.fixture
def client() -> Client:
    return Client()


def test_dashboard_renders_the_empty_form_with_no_date_given(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"Get live price" in response.content
    assert b"Blended generation price" not in response.content  # no result yet


def test_dashboard_renders_a_quote_when_a_date_is_given(client, with_seeded_db):
    response = client.get(
        "/", {"date": "2026-08-05", "business_type": "factory", "renewable_share": "0.5"}
    )

    assert response.status_code == 200
    assert b"Blended generation price" in response.content
    assert b"factory" in response.content


def test_dashboard_respects_an_explicit_settlement_period(client, with_seeded_db):
    """Regression test: the dashboard form originally had no way to
    specify settlement_period at all, silently defaulting to "right
    now" -- which for sparse seeded/real data often matches nothing,
    showing "no benchmark" even when real history exists for other
    periods. Caught by manually checking the rendered HTML against a
    live server before shipping; this pins it down permanently.
    """
    response = client.get(
        "/",
        {
            "date": "2026-08-05",
            "business_type": "factory",
            "renewable_share": "0.5",
            "settlement_period": "36",
        },
    )

    assert response.status_code == 200
    assert b"Forecast system price" in response.content
    assert b"Vs. benchmark" in response.content


def test_dashboard_shows_an_error_for_an_invalid_date(client):
    response = client.get("/", {"date": "not-a-date", "business_type": "office"})

    assert response.status_code == 200
    assert b"Couldn" in response.content  # "Couldn't compute a quote"


def test_dashboard_shows_no_benchmark_message_with_no_history(client, with_no_db):
    response = client.get(
        "/", {"date": "2026-08-05", "business_type": "office", "renewable_share": "0.5"}
    )

    assert response.status_code == 200
    assert b"No forecast history yet" in response.content
