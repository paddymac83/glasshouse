"""Sync glasshouse.db to/from S3.

This exists because the Lambda deployment's storage lives in S3 rather
than a VPC-attached EFS mount -- see infra/README.md for the reasoning
(avoiding a VPC keeps this Lambda off the NAT Gateway's flat ~$32/month
tax, since it doesn't otherwise need to be in one).

Only used by deployment glue -- the `sync_db` management command below,
and (in infra/, not yet built) the ingestion Lambda's handler. Nothing
in pricing.services or any request-handling code imports this; they
just see a plain local SQLite file path, exactly as they always have.
boto3 is only a dependency of the `deploy` extra, not the base install,
for the same reason: local dev and the test suite never need it.
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
    exists yet at that bucket/key -- a normal state for a fresh
    deployment before ingestion has ever run, not an error. Any other
    S3 error (permissions, bad bucket name, etc.) is re-raised, since
    those genuinely are something to know about.
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
