"""Sync glasshouse.db to/from S3.

Deployment-only glue for the ingestion Lambda (infra/docker/ingestion.Dockerfile,
glasshouse_ingestion/lambda_handler.py) -- the CLI never touches this,
it always reads/writes a plain local file path. boto3 is only a
dependency of the `deploy` extra, not the base install, for the same
reason: local dev and the test suite never need it there either.

This is a deliberate near-duplicate of frontend/pricing/db_sync.py
rather than a shared dependency between the two packages -- same
reasoning as forecast/ not depending on ingestion for its schema:
avoiding a coupling between two otherwise-independent deployables for
~30 lines of code isn't a good trade.
"""

from __future__ import annotations

import logging
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

_NOT_FOUND_CODES = {"404", "NoSuchKey"}


def download_db(bucket: str, key: str, local_path: Path) -> bool:
    """Download glasshouse.db from S3 to local_path.

    Returns True if a file was actually downloaded, False if none
    exists yet at that bucket/key -- a normal state for the very first
    run, before any backfill has ever completed. Any other S3 error is
    re-raised.
    """
    s3 = boto3.client("s3")
    local_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        s3.download_file(bucket, key, str(local_path))
        logger.info("Downloaded s3://%s/%s to %s", bucket, key, local_path)
        return True
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in _NOT_FOUND_CODES:
            logger.warning("No s3://%s/%s yet -- starting with an empty store", bucket, key)
            return False
        raise


def upload_db(bucket: str, key: str, local_path: Path) -> None:
    if not local_path.exists():
        raise FileNotFoundError(f"{local_path} does not exist -- nothing to upload")
    s3 = boto3.client("s3")
    s3.upload_file(str(local_path), bucket, key)
    logger.info("Uploaded %s to s3://%s/%s", local_path, bucket, key)
