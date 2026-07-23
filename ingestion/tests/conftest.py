from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def elexon_system_prices_payload() -> dict:
    return json.loads((FIXTURES / "elexon_system_prices.json").read_text())


@pytest.fixture
def elexon_fuel_hh_payload() -> dict:
    return json.loads((FIXTURES / "elexon_fuel_hh.json").read_text())


@pytest.fixture
def octopus_rates_payload() -> dict:
    return json.loads((FIXTURES / "octopus_rates.json").read_text())
