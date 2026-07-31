"""Core backfill loop: given a date range, ingest both (or one)
datasets for every date, keep going past a single failed date, and
report exactly what happened.

Extracted out of cli.py so there's exactly one place that owns this
loop -- both `glasshouse-ingest elexon-backfill` and the ingestion
Lambda's handler (glasshouse_ingestion/lambda_handler.py) call this
directly rather than each keeping a copy that could quietly drift
apart from the other.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

from glasshouse_ingestion.elexon_client import ElexonApiError, ElexonClient
from glasshouse_ingestion.storage import Storage

ProgressCallback = Callable[[int, int, date, list[str]], None]


@dataclass
class BackfillResult:
    total_dates: int
    prices_rows: int = 0
    generation_rows: int = 0
    failures: list[tuple[date, str, str]] = field(default_factory=list)

    @property
    def total_rows(self) -> int:
        return self.prices_rows + self.generation_rows

    @property
    def ok(self) -> bool:
        return not self.failures


def run_backfill(
    db_path: str | Path,
    start: date,
    end: date,
    dataset: str = "both",
    delay_seconds: float = 0.25,
    on_progress: ProgressCallback | None = None,
) -> BackfillResult:
    """Ingest every date in [start, end] (inclusive).

    Continues past a single date/dataset failure rather than aborting
    -- see BackfillResult.failures for what to retry. Re-running any
    part of this is always safe: Storage upserts on primary key, so it
    never duplicates rows, only overwrites with (hopefully) fresher data.
    """
    if end < start:
        raise ValueError(f"end ({end}) is before start ({start})")

    num_days = (end - start).days + 1
    target_dates = [start + timedelta(days=i) for i in range(num_days)]
    datasets = ("prices", "generation") if dataset == "both" else (dataset,)

    result = BackfillResult(total_dates=num_days)

    with ElexonClient() as client, Storage(db_path) as store:
        for i, target_date in enumerate(target_dates):
            outcomes: list[str] = []

            if "prices" in datasets:
                try:
                    written = store.save_system_prices(client.get_system_prices(target_date))
                    result.prices_rows += written
                    outcomes.append(f"prices {written}")
                except ElexonApiError as exc:
                    result.failures.append((target_date, "prices", str(exc)))
                    outcomes.append("prices FAILED")

            if "generation" in datasets:
                try:
                    written = store.save_fuel_generation(client.get_fuel_type_generation(target_date))
                    result.generation_rows += written
                    outcomes.append(f"generation {written}")
                except ElexonApiError as exc:
                    result.failures.append((target_date, "generation", str(exc)))
                    outcomes.append("generation FAILED")

            if on_progress:
                on_progress(i, num_days, target_date, outcomes)

            # Be a polite citizen of a free, public API -- especially
            # over a backfill of many weeks, which is a lot of requests
            # in a row.
            if delay_seconds and i < num_days - 1:
                time.sleep(delay_seconds)

    return result
