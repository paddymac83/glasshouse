"""Local time-series storage for ingested market data.

SQLite for now -- it's zero-ops and perfectly fine for a single-node MVP.
The schema below is deliberately close to what a Postgres/TimescaleDB
migration would look like later (see docs/adr/0002-storage.md), so
swapping the backend is a `storage.py` rewrite, not a data-model rewrite.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from glasshouse_ingestion.models import AgileUnitRate, FuelTypeGeneration, SettlementPrice

SCHEMA = """
CREATE TABLE IF NOT EXISTS settlement_prices (
    settlement_date   TEXT NOT NULL,
    settlement_period INTEGER NOT NULL,
    system_sell_price REAL NOT NULL,
    system_buy_price  REAL NOT NULL,
    PRIMARY KEY (settlement_date, settlement_period)
);

CREATE TABLE IF NOT EXISTS fuel_generation (
    settlement_date   TEXT NOT NULL,
    settlement_period INTEGER NOT NULL,
    fuel_type         TEXT NOT NULL,
    generation_mw     REAL NOT NULL,
    PRIMARY KEY (settlement_date, settlement_period, fuel_type)
);

CREATE TABLE IF NOT EXISTS agile_rates (
    product_code                     TEXT NOT NULL,
    tariff_code                      TEXT NOT NULL,
    valid_from                       TEXT NOT NULL,
    valid_to                         TEXT NOT NULL,
    unit_rate_inc_vat_pence_per_kwh  REAL NOT NULL,
    PRIMARY KEY (tariff_code, valid_from)
);
"""


class Storage:
    """Owns one SQLite connection and knows how to upsert each record type."""

    def __init__(self, db_path: str | Path = "glasshouse.db") -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def save_system_prices(self, prices: list[SettlementPrice]) -> int:
        rows = [
            (p.settlement_date.isoformat(), p.settlement_period, p.system_sell_price, p.system_buy_price)
            for p in prices
        ]
        self._conn.executemany(
            "INSERT OR REPLACE INTO settlement_prices "
            "(settlement_date, settlement_period, system_sell_price, system_buy_price) "
            "VALUES (?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()
        return len(rows)

    def save_fuel_generation(self, records: list[FuelTypeGeneration]) -> int:
        rows = [
            (r.settlement_date.isoformat(), r.settlement_period, r.fuel_type, r.generation_mw)
            for r in records
        ]
        self._conn.executemany(
            "INSERT OR REPLACE INTO fuel_generation "
            "(settlement_date, settlement_period, fuel_type, generation_mw) "
            "VALUES (?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()
        return len(rows)

    def save_agile_rates(
        self, rates: list[AgileUnitRate], product_code: str, tariff_code: str
    ) -> int:
        rows = [
            (
                product_code,
                tariff_code,
                r.valid_from.isoformat(),
                r.valid_to.isoformat(),
                r.unit_rate_inc_vat_pence_per_kwh,
            )
            for r in rates
        ]
        self._conn.executemany(
            "INSERT OR REPLACE INTO agile_rates "
            "(product_code, tariff_code, valid_from, valid_to, unit_rate_inc_vat_pence_per_kwh) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()
        return len(rows)

    def system_prices_for_date(self, settlement_date: date) -> list[SettlementPrice]:
        cursor = self._conn.execute(
            "SELECT settlement_date, settlement_period, system_sell_price, system_buy_price "
            "FROM settlement_prices WHERE settlement_date = ? ORDER BY settlement_period",
            (settlement_date.isoformat(),),
        )
        return [
            SettlementPrice(
                settlement_date=row[0],
                settlement_period=row[1],
                system_sell_price=row[2],
                system_buy_price=row[3],
            )
            for row in cursor.fetchall()
        ]
