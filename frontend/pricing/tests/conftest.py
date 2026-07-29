"""Shared fixtures for pricing's tests.

Same seeded-DB approach as api/tests/conftest.py and forecast/tests/conftest.py
-- a real temp SQLite file (not :memory:), because SeasonalBaselineForecaster
opens its own connection by path. Here the DB path is threaded through via
the GLASSHOUSE_INGESTION_DB environment variable (monkeypatched per test),
since pricing.services reads it that way rather than through Django's own
settings/DB config -- Django's ORM/DATABASES setting is unrelated to this;
it's only used for Django's own internal apps (admin, auth, sessions).
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest
from rest_framework.test import APIClient

SCHEMA = """
CREATE TABLE settlement_prices (
    settlement_date   TEXT NOT NULL,
    settlement_period INTEGER NOT NULL,
    system_sell_price REAL NOT NULL,
    system_buy_price  REAL NOT NULL,
    PRIMARY KEY (settlement_date, settlement_period)
);

CREATE TABLE fuel_generation (
    settlement_date   TEXT NOT NULL,
    settlement_period INTEGER NOT NULL,
    fuel_type         TEXT NOT NULL,
    generation_mw     REAL NOT NULL,
    PRIMARY KEY (settlement_date, settlement_period, fuel_type)
);
"""


@pytest.fixture
def seeded_db_path(tmp_path: Path) -> Path:
    """8 weeks of history for 2026-08-05 (a Wednesday), periods 1/36/48
    -- enough for a confident (non-fallback) forecast at those periods.
    """
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)

    target = date(2026, 8, 5)
    for week in range(1, 9):
        d = target - timedelta(weeks=week)
        for period in (1, 36, 48):
            conn.execute(
                "INSERT INTO settlement_prices VALUES (?, ?, ?, ?)",
                (d.isoformat(), period, 40.0 + period, 40.0 + period),
            )
            conn.execute(
                "INSERT INTO fuel_generation VALUES (?, ?, ?, ?)",
                (d.isoformat(), period, "WIND", 1000.0 + period),
            )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def with_seeded_db(monkeypatch, seeded_db_path: Path) -> Path:
    monkeypatch.setenv("GLASSHOUSE_INGESTION_DB", str(seeded_db_path))
    return seeded_db_path


@pytest.fixture
def with_no_db(monkeypatch, tmp_path: Path) -> Path:
    missing = tmp_path / "does_not_exist.db"
    monkeypatch.setenv("GLASSHOUSE_INGESTION_DB", str(missing))
    return missing


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()
