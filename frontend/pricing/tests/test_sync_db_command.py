from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


def test_sync_db_requires_bucket_env_var(monkeypatch):
    monkeypatch.delenv("GLASSHOUSE_S3_BUCKET", raising=False)

    with pytest.raises(CommandError, match="GLASSHOUSE_S3_BUCKET"):
        call_command("sync_db", "download")


def test_sync_db_download_reports_success(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GLASSHOUSE_S3_BUCKET", "my-bucket")
    monkeypatch.setenv("GLASSHOUSE_INGESTION_DB", str(tmp_path / "glasshouse.db"))
    out = StringIO()

    with patch("pricing.management.commands.sync_db.download_db", return_value=True) as mock_download:
        call_command("sync_db", "download", stdout=out)

    mock_download.assert_called_once_with("my-bucket", "glasshouse.db", tmp_path / "glasshouse.db")
    assert "Downloaded" in out.getvalue()


def test_sync_db_download_reports_a_fresh_store_without_erroring(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GLASSHOUSE_S3_BUCKET", "my-bucket")
    monkeypatch.setenv("GLASSHOUSE_INGESTION_DB", str(tmp_path / "glasshouse.db"))
    out = StringIO()

    with patch("pricing.management.commands.sync_db.download_db", return_value=False):
        call_command("sync_db", "download", stdout=out)

    assert "starting with an empty store" in out.getvalue()


def test_sync_db_upload_reports_success(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GLASSHOUSE_S3_BUCKET", "my-bucket")
    monkeypatch.setenv("GLASSHOUSE_INGESTION_DB", str(tmp_path / "glasshouse.db"))
    out = StringIO()

    with patch("pricing.management.commands.sync_db.upload_db") as mock_upload:
        call_command("sync_db", "upload", stdout=out)

    mock_upload.assert_called_once_with("my-bucket", "glasshouse.db", tmp_path / "glasshouse.db")
    assert "Uploaded" in out.getvalue()


def test_sync_db_upload_surfaces_a_missing_file_as_a_command_error(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GLASSHOUSE_S3_BUCKET", "my-bucket")
    monkeypatch.setenv("GLASSHOUSE_INGESTION_DB", str(tmp_path / "glasshouse.db"))

    with patch("pricing.management.commands.sync_db.upload_db", side_effect=FileNotFoundError("nope")):
        with pytest.raises(CommandError, match="nope"):
            call_command("sync_db", "upload")


def test_sync_db_uses_custom_key_when_set(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GLASSHOUSE_S3_BUCKET", "my-bucket")
    monkeypatch.setenv("GLASSHOUSE_S3_KEY", "custom/path/glasshouse.db")
    monkeypatch.setenv("GLASSHOUSE_INGESTION_DB", str(tmp_path / "glasshouse.db"))

    with patch("pricing.management.commands.sync_db.download_db", return_value=True) as mock_download:
        call_command("sync_db", "download")

    mock_download.assert_called_once_with("my-bucket", "custom/path/glasshouse.db", tmp_path / "glasshouse.db")
