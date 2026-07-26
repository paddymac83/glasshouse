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


def test_latest_system_prices_returns_most_recent_regardless_of_date():
    with Storage(":memory:") as store:
        store.save_system_prices([
            SettlementPrice(settlement_date=date(2026, 7, 20), settlement_period=48, system_sell_price=10.0, system_buy_price=10.0),
            SettlementPrice(settlement_date=date(2026, 7, 21), settlement_period=1, system_sell_price=20.0, system_buy_price=20.0),
            SettlementPrice(settlement_date=date(2026, 7, 21), settlement_period=2, system_sell_price=30.0, system_buy_price=30.0),
        ])

        latest_two = store.latest_system_prices(limit=2)

        assert len(latest_two) == 2
        # oldest-first within the returned window
        assert latest_two[0].settlement_period == 1
        assert latest_two[1].settlement_period == 2
        assert all(p.settlement_date == date(2026, 7, 21) for p in latest_two)


def test_latest_system_prices_handles_a_store_with_fewer_rows_than_the_limit():
    with Storage(":memory:") as store:
        store.save_system_prices([
            SettlementPrice(settlement_date=date(2026, 7, 21), settlement_period=1, system_sell_price=20.0, system_buy_price=20.0),
        ])

        result = store.latest_system_prices(limit=48)

        assert len(result) == 1
