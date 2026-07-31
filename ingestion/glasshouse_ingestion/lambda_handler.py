"""AWS Lambda handler for the scheduled ingestion job.

Triggered by EventBridge (infra/, not yet built) on a schedule.
Downloads the current glasshouse.db from S3 (or starts fresh),
backfills the last GLASSHOUSE_BACKFILL_DAYS days for both datasets
(re-running a day that's already there is harmless -- Storage upserts
on primary key), uploads the result back to S3.

Deployment-only glue, packaged into its own Lambda container image
(infra/docker/ingestion.Dockerfile) -- nothing in the CLI or the rest
of the package imports this; it's only ever invoked by AWS Lambda
itself. See db_sync.py and infra/README.md for why S3 rather than EFS.
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from glasshouse_ingestion.backfill import run_backfill
from glasshouse_ingestion.db_sync import download_db, upload_db

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEFAULT_BACKFILL_DAYS = 5
DEFAULT_LOCAL_DB_PATH = "/tmp/glasshouse.db"
DEFAULT_S3_KEY = "glasshouse.db"


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    bucket = os.environ["GLASSHOUSE_S3_BUCKET"]
    key = os.environ.get("GLASSHOUSE_S3_KEY", DEFAULT_S3_KEY)
    local_path = Path(os.environ.get("GLASSHOUSE_INGESTION_DB", DEFAULT_LOCAL_DB_PATH))
    backfill_days = int(os.environ.get("GLASSHOUSE_BACKFILL_DAYS", DEFAULT_BACKFILL_DAYS))

    download_db(bucket, key, local_path)

    end = date.today()
    start = end - timedelta(days=backfill_days - 1)
    logger.info("Backfilling %s to %s (dataset=both)", start, end)

    result = run_backfill(local_path, start=start, end=end, dataset="both", delay_seconds=0.1)

    # Upload whatever was gathered even if some dates failed -- partial
    # fresh data beats none, and this runs on a schedule, so a failed
    # date gets another chance next run regardless.
    upload_db(bucket, key, local_path)

    summary = {
        "ok": result.ok,
        "total_dates": result.total_dates,
        "prices_rows": result.prices_rows,
        "generation_rows": result.generation_rows,
        "failures": [
            {"date": d.isoformat(), "dataset": ds, "message": msg} for d, ds, msg in result.failures
        ],
    }

    if not result.ok:
        logger.error("Backfill had %d failure(s): %s", len(result.failures), summary["failures"])
        # Raising (rather than just returning ok=False) means this
        # shows up in Lambda's own error metrics/CloudWatch alarms,
        # not just in a log line someone has to go looking for.
        raise RuntimeError(f"{len(result.failures)} date/dataset combination(s) failed: {summary['failures']}")

    logger.info("Backfill complete: %s", summary)
    return summary
