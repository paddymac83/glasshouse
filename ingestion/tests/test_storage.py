from __future__ import annotations

from datetime import date

from glasshouse_ingestion.models import FuelTypeGeneration, SettlementPrice
from glasshouse_ingestion.storage import Storage


def test_save_and_read_system_prices():
    with Storage(":memory:") as store:
        prices = [
            SettlementPrice(
                settlement_date=date(2026, 7, 22),
                settlement_period=1,
                system_sell_price=65.2,
                system_buy_price=65.2,
            ),
            SettlementPrice(
                settlement_date=date(2026, 7, 22),
                settlement_period=2,
                system_sell_price=60.1,
                system_buy_price=60.1,
            ),
        ]

        written = store.save_system_prices(prices)
        assert written == 2

        fetched = store.system_prices_for_date(date(2026, 7, 22))
        assert [p.settlement_period for p in fetched] == [1, 2]
        assert fetched[0].system_sell_price == 65.2


def test_upsert_overwrites_existing_row():
    with Storage(":memory:") as store:
        original = SettlementPrice(
            settlement_date=date(2026, 7, 22),
            settlement_period=1,
            system_sell_price=65.2,
            system_buy_price=65.2,
        )
        revised = SettlementPrice(
            settlement_date=date(2026, 7, 22),
            settlement_period=1,
            system_sell_price=70.0,
            system_buy_price=70.0,
        )

        store.save_system_prices([original])
        store.save_system_prices([revised])

        fetched = store.system_prices_for_date(date(2026, 7, 22))
        assert len(fetched) == 1
        assert fetched[0].system_sell_price == 70.0


def test_save_fuel_generation_keys_on_fuel_type():
    with Storage(":memory:") as store:
        records = [
            FuelTypeGeneration(
                settlement_date=date(2026, 7, 22),
                settlement_period=1,
                fuel_type="WIND",
                generation_mw=8213.5,
            ),
            FuelTypeGeneration(
                settlement_date=date(2026, 7, 22),
                settlement_period=1,
                fuel_type="CCGT",
                generation_mw=12000.0,
            ),
        ]

        written = store.save_fuel_generation(records)
        assert written == 2
