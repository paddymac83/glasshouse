"""Integration test for the Python <-> Rust bridge.

This only runs once the extension has actually been built with
`maturin develop` (see README.md in this folder) -- it's kept separate
from the pure-Rust `cargo test` suite in ../src/lib.rs, which needs no
Python at all. If the module isn't installed, the test is skipped
rather than failed, so `pytest` at the repo root doesn't break for
someone who hasn't built the Rust side yet.
"""

import pytest

glasshouse_settlement = pytest.importorskip("glasshouse_settlement")


def test_settle_period_matches_the_rust_unit_test_case():
    result = glasshouse_settlement.settle_period_py(
        generators=[("wind_farm_1", 5.0, 30.0), ("gas_peaker", 100.0, 80.0)],
        consumers=[("bakery", 2.0), ("brewery", 8.0)],
        network_charge_gbp_per_mwh=20.0,
        policy_cost_gbp_per_mwh=15.0,
        platform_margin_fraction=0.05,
    )

    assert result["unmet_demand_mwh"] == 0.0
    assert result["blended_generation_price_gbp_per_mwh"] == pytest.approx(55.0)

    bakery = next(b for b in result["bills"] if b["consumer_id"] == "bakery")
    brewery = next(b for b in result["bills"] if b["consumer_id"] == "brewery")

    assert bakery["total_gbp"] == pytest.approx(189.0)
    assert brewery["total_gbp"] == pytest.approx(756.0)
    # Brewery uses 4x the energy of the bakery -> should pay ~4x.
    assert brewery["total_gbp"] == pytest.approx(bakery["total_gbp"] * 4, rel=1e-9)


def test_invalid_input_raises_a_python_value_error():
    with pytest.raises(ValueError, match="at least one consumer"):
        glasshouse_settlement.settle_period_py(
            generators=[("solar", 10.0, 40.0)],
            consumers=[],
            network_charge_gbp_per_mwh=20.0,
            policy_cost_gbp_per_mwh=15.0,
            platform_margin_fraction=0.05,
        )


def test_shortfall_is_reported_and_still_produces_valid_bills():
    result = glasshouse_settlement.settle_period_py(
        generators=[("wind", 5.0, 30.0)],
        consumers=[("a", 6.0), ("b", 4.0)],
        network_charge_gbp_per_mwh=20.0,
        policy_cost_gbp_per_mwh=15.0,
        platform_margin_fraction=0.05,
    )

    assert result["unmet_demand_mwh"] == pytest.approx(5.0)
    for bill in result["bills"]:
        assert bill["total_gbp"] >= 0
        assert sum(line["amount_gbp"] for line in bill["lines"]) == pytest.approx(bill["total_gbp"])
