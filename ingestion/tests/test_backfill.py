from __future__ import annotations

import copy
import re
from datetime import date
from unittest.mock import patch

import httpx
import pytest

from glasshouse_ingestion.backfill import run_backfill
from glasshouse_ingestion.elexon_client import ElexonClient

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _date_tagged_handler(prices_template, generation_template, fail_dates: frozenset[str] = frozenset()):
    def handler(request: httpx.Request) -> httpx.Response:
        match = DATE_RE.search(str(request.url))
        requested_date = match.group(0) if match else None
        if requested_date in fail_dates:
            return httpx.Response(503, request=request)
        template = prices_template if "system-prices" in request.url.path else generation_template
        payload = copy.deepcopy(template)
        records = payload if isinstance(payload, list) else payload["data"]
        for record in records:
            record["settlementDate"] = requested_date
        return httpx.Response(200, json=payload, request=request)

    return handler


def _mock_client(handler) -> ElexonClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport, base_url="https://data.elexon.co.uk/bmrs/api/v1")
    return ElexonClient(http_client=http_client)


def test_run_backfill_rejects_end_before_start(tmp_path):
    with pytest.raises(ValueError, match="before"):
        run_backfill(tmp_path / "test.db", date(2026, 7, 22), date(2026, 7, 20))


def test_run_backfill_reports_totals_and_no_failures_on_a_clean_run(
    tmp_path, elexon_system_prices_payload, elexon_fuel_hh_payload
):
    handler = _date_tagged_handler(elexon_system_prices_payload, elexon_fuel_hh_payload)

    with patch("glasshouse_ingestion.backfill.ElexonClient", return_value=_mock_client(handler)):
        result = run_backfill(
            tmp_path / "test.db", date(2026, 7, 20), date(2026, 7, 22), delay_seconds=0
        )

    assert result.ok is True
    assert result.total_dates == 3
    assert result.prices_rows == 9  # 3 dates x 3 rows per fixture
    assert result.generation_rows == 9
    assert result.failures == []


def test_run_backfill_calls_on_progress_for_every_date(
    tmp_path, elexon_system_prices_payload, elexon_fuel_hh_payload
):
    handler = _date_tagged_handler(elexon_system_prices_payload, elexon_fuel_hh_payload)
    progress_calls = []

    with patch("glasshouse_ingestion.backfill.ElexonClient", return_value=_mock_client(handler)):
        run_backfill(
            tmp_path / "test.db",
            date(2026, 7, 20),
            date(2026, 7, 22),
            delay_seconds=0,
            on_progress=lambda i, n, d, outcomes: progress_calls.append((i, n, d)),
        )

    assert len(progress_calls) == 3
    assert progress_calls[0] == (0, 3, date(2026, 7, 20))
    assert progress_calls[2] == (2, 3, date(2026, 7, 22))


def test_run_backfill_reports_failures_without_raising(
    tmp_path, elexon_system_prices_payload, elexon_fuel_hh_payload
):
    handler = _date_tagged_handler(
        elexon_system_prices_payload, elexon_fuel_hh_payload, fail_dates=frozenset({"2026-07-21"})
    )

    with patch("glasshouse_ingestion.backfill.ElexonClient", return_value=_mock_client(handler)):
        result = run_backfill(
            tmp_path / "test.db", date(2026, 7, 20), date(2026, 7, 22), delay_seconds=0
        )

    assert result.ok is False
    assert len(result.failures) == 2  # both prices and generation failed for the one bad date
    assert all(f[0] == date(2026, 7, 21) for f in result.failures)
