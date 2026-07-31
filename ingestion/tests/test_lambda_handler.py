from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from glasshouse_ingestion.backfill import BackfillResult
from glasshouse_ingestion.lambda_handler import handler


def test_handler_downloads_backfills_and_uploads(monkeypatch):
    monkeypatch.setenv("GLASSHOUSE_S3_BUCKET", "my-bucket")
    monkeypatch.setenv("GLASSHOUSE_BACKFILL_DAYS", "3")
    fake_result = BackfillResult(total_dates=3, prices_rows=9, generation_rows=9)

    with (
        patch("glasshouse_ingestion.lambda_handler.download_db") as mock_download,
        patch("glasshouse_ingestion.lambda_handler.upload_db") as mock_upload,
        patch("glasshouse_ingestion.lambda_handler.run_backfill", return_value=fake_result) as mock_backfill,
    ):
        result = handler({}, None)

    mock_download.assert_called_once()
    mock_backfill.assert_called_once()
    mock_upload.assert_called_once()
    assert result["ok"] is True
    assert result["prices_rows"] == 9
    assert result["generation_rows"] == 9


def test_handler_uploads_before_raising_when_backfill_has_failures(monkeypatch):
    """Partial fresh data is still worth keeping -- the upload must
    happen before the handler surfaces the failure, not be skipped
    because of it.
    """
    monkeypatch.setenv("GLASSHOUSE_S3_BUCKET", "my-bucket")
    fake_result = BackfillResult(
        total_dates=3,
        prices_rows=6,
        generation_rows=6,
        failures=[(date(2026, 1, 1), "prices", "503 error")],
    )

    with (
        patch("glasshouse_ingestion.lambda_handler.download_db"),
        patch("glasshouse_ingestion.lambda_handler.upload_db") as mock_upload,
        patch("glasshouse_ingestion.lambda_handler.run_backfill", return_value=fake_result),
    ):
        with pytest.raises(RuntimeError, match="1 date/dataset"):
            handler({}, None)

    mock_upload.assert_called_once()


def test_handler_requires_bucket_env_var(monkeypatch):
    monkeypatch.delenv("GLASSHOUSE_S3_BUCKET", raising=False)

    with pytest.raises(KeyError):
        handler({}, None)


def test_handler_backfill_window_is_configurable(monkeypatch):
    monkeypatch.setenv("GLASSHOUSE_S3_BUCKET", "my-bucket")
    monkeypatch.setenv("GLASSHOUSE_BACKFILL_DAYS", "7")
    fake_result = BackfillResult(total_dates=7)

    with (
        patch("glasshouse_ingestion.lambda_handler.download_db"),
        patch("glasshouse_ingestion.lambda_handler.upload_db"),
        patch("glasshouse_ingestion.lambda_handler.run_backfill", return_value=fake_result) as mock_backfill,
    ):
        handler({}, None)

    call_kwargs = mock_backfill.call_args.kwargs
    assert (call_kwargs["end"] - call_kwargs["start"]).days == 6  # 7 days inclusive


def test_handler_uses_default_backfill_window_when_unset(monkeypatch):
    monkeypatch.setenv("GLASSHOUSE_S3_BUCKET", "my-bucket")
    monkeypatch.delenv("GLASSHOUSE_BACKFILL_DAYS", raising=False)
    fake_result = BackfillResult(total_dates=5)

    with (
        patch("glasshouse_ingestion.lambda_handler.download_db"),
        patch("glasshouse_ingestion.lambda_handler.upload_db"),
        patch("glasshouse_ingestion.lambda_handler.run_backfill", return_value=fake_result) as mock_backfill,
    ):
        handler({}, None)

    call_kwargs = mock_backfill.call_args.kwargs
    assert (call_kwargs["end"] - call_kwargs["start"]).days == 4  # default 5 days inclusive
