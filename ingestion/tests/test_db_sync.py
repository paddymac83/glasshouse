from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from glasshouse_ingestion.db_sync import download_db, upload_db


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code}}, "operation")


def test_download_db_returns_true_and_calls_s3_on_success(tmp_path: Path):
    mock_s3 = MagicMock()
    target = tmp_path / "glasshouse.db"

    with patch("glasshouse_ingestion.db_sync.boto3.client", return_value=mock_s3):
        result = download_db("my-bucket", "glasshouse.db", target)

    assert result is True
    mock_s3.download_file.assert_called_once_with("my-bucket", "glasshouse.db", str(target))


def test_download_db_returns_false_when_nothing_exists_yet(tmp_path: Path):
    mock_s3 = MagicMock()
    mock_s3.download_file.side_effect = _client_error("404")

    with patch("glasshouse_ingestion.db_sync.boto3.client", return_value=mock_s3):
        result = download_db("my-bucket", "glasshouse.db", tmp_path / "glasshouse.db")

    assert result is False


def test_download_db_reraises_unexpected_errors(tmp_path: Path):
    mock_s3 = MagicMock()
    mock_s3.download_file.side_effect = _client_error("403")

    with patch("glasshouse_ingestion.db_sync.boto3.client", return_value=mock_s3):
        with pytest.raises(ClientError):
            download_db("my-bucket", "glasshouse.db", tmp_path / "glasshouse.db")


def test_upload_db_calls_s3_with_the_right_arguments(tmp_path: Path):
    mock_s3 = MagicMock()
    local_file = tmp_path / "glasshouse.db"
    local_file.write_bytes(b"fake sqlite content")

    with patch("glasshouse_ingestion.db_sync.boto3.client", return_value=mock_s3):
        upload_db("my-bucket", "glasshouse.db", local_file)

    mock_s3.upload_file.assert_called_once_with(str(local_file), "my-bucket", "glasshouse.db")


def test_upload_db_refuses_a_file_that_does_not_exist(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        upload_db("my-bucket", "glasshouse.db", tmp_path / "does_not_exist.db")
