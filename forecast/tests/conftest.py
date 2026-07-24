"""Shared fixtures for forecast's tests.

SeasonalBaselineForecaster opens its own read-only SQLite connection by
file path, so its tests need real files on disk, not :memory:. The
schema below is kept in sync by hand with
ingestion/glasshouse_ingestion/storage.py's SCHEMA -- forecast only
ever SELECTs from these tables and deliberately doesn't depend on the
ingestion package, so its tests build the same two tables locally
rather than sharing ingestion's Storage class.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest

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


@dataclass
class SeededDB:
    path: Path
    _conn: sqlite3.Connection

    def insert_price(self, d: date, period: int, sell_price: float, buy_price: float | None = None) -> None:
        self._conn.execute(
            "INSERT INTO settlement_prices VALUES (?, ?, ?, ?)",
            (d.isoformat(), period, sell_price, buy_price if buy_price is not None else sell_price),
        )
        self._conn.commit()

    def insert_generation(self, d: date, period: int, fuel_type: str, generation_mw: float) -> None:
        self._conn.execute(
            "INSERT INTO fuel_generation VALUES (?, ?, ?, ?)",
            (d.isoformat(), period, fuel_type, generation_mw),
        )
        self._conn.commit()


@pytest.fixture
def seeded_db(tmp_path: Path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()

    yield SeededDB(path=db_path, _conn=conn)

    conn.close()
