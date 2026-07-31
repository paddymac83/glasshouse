"""Custom manage.py command: sync glasshouse.db to/from S3.

    python manage.py sync_db download   # pull from S3 to local path (container startup)
    python manage.py sync_db upload     # push local path back to S3 (after ingestion writes)

Deployment-only glue -- nothing else in this app depends on it. See
pricing/db_sync.py's module docstring and infra/README.md for why S3
rather than EFS.
"""

from __future__ import annotations

import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from pricing.db_sync import download_db, upload_db


class Command(BaseCommand):
    help = "Download or upload glasshouse.db to/from S3 (deployment glue, not used in local dev)"

    def add_arguments(self, parser):
        parser.add_argument("direction", choices=["download", "upload"])

    def handle(self, *args, **options):
        bucket = os.environ.get("GLASSHOUSE_S3_BUCKET")
        if not bucket:
            raise CommandError("GLASSHOUSE_S3_BUCKET is not set")
        key = os.environ.get("GLASSHOUSE_S3_KEY", "glasshouse.db")
        local_path = Path(os.environ.get("GLASSHOUSE_INGESTION_DB", "/tmp/glasshouse.db"))

        if options["direction"] == "download":
            found = download_db(bucket, key, local_path)
            if found:
                self.stdout.write(self.style.SUCCESS(f"Downloaded s3://{bucket}/{key} to {local_path}"))
            else:
                self.stdout.write(
                    self.style.WARNING(f"No s3://{bucket}/{key} yet -- starting with an empty store")
                )
        else:
            try:
                upload_db(bucket, key, local_path)
            except FileNotFoundError as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(self.style.SUCCESS(f"Uploaded {local_path} to s3://{bucket}/{key}"))
