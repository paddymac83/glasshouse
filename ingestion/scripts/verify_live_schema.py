"""Diff the live Elexon response shape against the fixtures our parser assumes.

This is the exact check the top-level README asks you to run before
trusting `elexon_client.py` against production data. It talks to the
live API directly (bypassing ElexonClient's parsing entirely) and
compares raw JSON field names, so it catches a schema mismatch even in
cases where parsing wouldn't loudly fail -- e.g. a field that still
exists but means something subtly different.

Usage:
    uv run python scripts/verify_live_schema.py --date 2026-07-23

Exit code is 0 if the live schema matches what `_parse_system_price`
and `_parse_fuel_generation` expect, 1 if it's drifted.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

import httpx

FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures"
DEFAULT_BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"


def _first_record_keys(payload: object) -> set[str]:
    records = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not records:
        raise SystemExit("response had zero records -- try a different --date")
    return set(records[0].keys())


def _fixture_keys(fixture_name: str) -> set[str]:
    payload = json.loads((FIXTURES / fixture_name).read_text())
    return _first_record_keys(payload)


def check(label: str, url: str, params: dict, fixture_name: str) -> bool:
    response = httpx.get(url, params=params, timeout=10.0)
    response.raise_for_status()
    live_keys = _first_record_keys(response.json())
    fixture_keys = _fixture_keys(fixture_name)

    missing = fixture_keys - live_keys  # our parser needs these; live doesn't have them
    extra = live_keys - fixture_keys    # live has these; our parser ignores them

    print(f"\n{label}")
    print(f"  live keys:    {sorted(live_keys)}")
    print(f"  fixture keys: {sorted(fixture_keys)}")
    if missing:
        print(f"  MISMATCH -- fields the parser requires but the live response lacks: {sorted(missing)}")
    else:
        print("  OK -- every field the parser requires is present")
    if extra:
        print(f"  (fyi) live response also has fields we don't currently use: {sorted(extra)}")
    return not missing


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=date.today(),
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="override for testing against a mock server",
    )
    args = parser.parse_args()

    ok_prices = check(
        "System prices",
        f"{args.base_url}/balancing/settlement/system-prices/{args.date.isoformat()}",
        {},
        "elexon_system_prices.json",
    )
    ok_generation = check(
        "Fuel-type generation",
        f"{args.base_url}/datasets/FUELHH",
        {"settlementDate": args.date.isoformat()},
        "elexon_fuel_hh.json",
    )

    if ok_prices and ok_generation:
        print("\nLive schema matches what elexon_client.py assumes.")
        return 0
    print("\nSchema drift detected -- update elexon_client.py's _parse_* methods and the fixtures to match.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
