from __future__ import annotations

import copy
import re
from datetime import date
from unittest.mock import patch

import httpx

from glasshouse_ingestion.cli import main
from glasshouse_ingestion.elexon_client import ElexonClient
from glasshouse_ingestion.storage import Storage

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _date_tagged_handler(prices_template, generation_template, fail_dates: frozenset[str] = frozenset()):
    """Builds a mock handler whose response is tagged with whatever date
    was actually requested, like the real API -- a static fixture would
    make every date in a backfill loop overwrite the same stored row.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        match = DATE_RE.search(str(request.url))
        requested_date = match.group(0) if match else None

        if requested_date in fail_dates:
            return httpx.Response(503, request=request)

        template = prices_template if "system-prices" in request.url.path else generation_template
        payload = copy.deepcopy(template)
        for record in payload["data"]:
            record["settlementDate"] = requested_date
        return httpx.Response(200, json=payload, request=request)

    return handler


def _mock_client(handler) -> ElexonClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport, base_url="https://data.elexon.co.uk/bmrs/api/v1")
    return ElexonClient(http_client=http_client)


def test_elexon_backfill_ingests_every_date_in_the_range(
    tmp_path, elexon_system_prices_payload, elexon_fuel_hh_payload
):
    db_path = tmp_path / "backfill.db"
    handler = _date_tagged_handler(elexon_system_prices_payload, elexon_fuel_hh_payload)

    with patch("glasshouse_ingestion.cli.ElexonClient", return_value=_mock_client(handler)):
        exit_code = main(
            [
                "--db", str(db_path),
                "elexon-backfill",
                "--start", "2026-07-20",
                "--end", "2026-07-22",
                "--delay-seconds", "0",
            ]
        )

    assert exit_code == 0
    with Storage(db_path) as store:
        # 3 dates in range, each fixture has 3 rows -> every date should
        # have been ingested independently, not just the last one.
        for d in (date(2026, 7, 20), date(2026, 7, 21), date(2026, 7, 22)):
            assert len(store.system_prices_for_date(d)) == 3


def test_elexon_backfill_continues_past_a_failed_date_and_reports_it(
    tmp_path, elexon_system_prices_payload, elexon_fuel_hh_payload
):
    db_path = tmp_path / "backfill.db"
    handler = _date_tagged_handler(
        elexon_system_prices_payload, elexon_fuel_hh_payload, fail_dates=frozenset({"2026-07-21"})
    )

    with patch("glasshouse_ingestion.cli.ElexonClient", return_value=_mock_client(handler)):
        exit_code = main(
            [
                "--db", str(db_path),
                "elexon-backfill",
                "--start", "2026-07-20",
                "--end", "2026-07-22",
                "--delay-seconds", "0",
            ]
        )

    # A failure anywhere in the range means a non-zero exit...
    assert exit_code == 1
    with Storage(db_path) as store:
        # ...but the dates either side of the failure were NOT skipped.
        assert len(store.system_prices_for_date(date(2026, 7, 20))) == 3
        assert len(store.system_prices_for_date(date(2026, 7, 22))) == 3
        # The failed date genuinely has nothing -- not partial, not fabricated.
        assert len(store.system_prices_for_date(date(2026, 7, 21))) == 0


def test_elexon_backfill_rejects_end_before_start(tmp_path):
    db_path = tmp_path / "backfill.db"

    exit_code = main(
        [
            "--db", str(db_path),
            "elexon-backfill",
            "--start", "2026-07-22",
            "--end", "2026-07-20",
        ]
    )

    assert exit_code == 1


def test_elexon_backfill_respects_dataset_filter(tmp_path, elexon_system_prices_payload, elexon_fuel_hh_payload):
    db_path = tmp_path / "backfill.db"
    tagged_handler = _date_tagged_handler(elexon_system_prices_payload, elexon_fuel_hh_payload)

    def handler(request: httpx.Request) -> httpx.Response:
        # If this ever gets called for generation, the test should fail
        # loudly rather than silently returning something plausible.
        assert "FUELHH" not in request.url.path, "generation should not be fetched when --dataset=prices"
        return tagged_handler(request)

    with patch("glasshouse_ingestion.cli.ElexonClient", return_value=_mock_client(handler)):
        exit_code = main(
            [
                "--db", str(db_path),
                "elexon-backfill",
                "--start", "2026-07-20",
                "--end", "2026-07-20",
                "--dataset", "prices",
                "--delay-seconds", "0",
            ]
        )

    assert exit_code == 0
    with Storage(db_path) as store:
        assert len(store.system_prices_for_date(date(2026, 7, 20))) == 3
