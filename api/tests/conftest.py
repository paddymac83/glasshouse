"""Shared fixtures for api's tests.

Same reasoning as forecast/tests/conftest.py: the seeded DB is a real
SQLite file (not :memory:) with ingestion's schema built locally rather
than depending on the ingestion package for it, since api only ever
reads it through Storage/SeasonalBaselineForecaster, which already have
their own test coverage in their own packages.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from glasshouse_api.config import get_ingestion_db_path
from glasshouse_api.main import app

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
    """8 weeks of history for a fixed target date (2026-08-05, a
    Wednesday), for both system prices and WIND generation -- enough
    for a confident (non-fallback) forecast, matching the shape used
    throughout forecast/README.md's worked example.
    """
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)

    target = date(2026, 8, 5)
    for week in range(1, 9):
        d = target - timedelta(weeks=week)
        for period in (1, 36, 48):  # a few representative periods, not all 48
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
def client(seeded_db_path: Path) -> TestClient:
    app.dependency_overrides[get_ingestion_db_path] = lambda: seeded_db_path
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def client_with_no_db(tmp_path: Path) -> TestClient:
    """A client pointed at a DB path that deliberately doesn't exist --
    for testing the "no history yet" paths.
    """
    app.dependency_overrides[get_ingestion_db_path] = lambda: tmp_path / "does_not_exist.db"
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()
