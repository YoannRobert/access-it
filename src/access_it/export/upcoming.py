"""Entries and forecasts of the upcoming races on the S3 storage.

Each run of the forecast of the upcoming races produces two Parquet files: the
entries (written by scripts/extract_upcoming_entries.py) and the forecasts
(written by scripts/forecast_upcoming_races.py). Rules:

- the files are uploaded under keys following ENTRIES_KEYS and FORECASTS_KEYS,
  with the same UTC timestamp (the time of the upload, or a chosen time), so
  that the entries and the forecasts of a run can be paired;
- both files are checked first: if one is missing, nothing is uploaded; their
  content is not read, an empty file is uploaded like any other;
- the entries are uploaded before the forecasts, so that a file of forecasts
  proves that the entries of the same timestamp were uploaded too;
- after both uploads, only the KEEP_FILES most recent files of each kind are
  kept (entries first, then forecasts).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from access_it.export.s3 import KeyPattern, delete_old_keys, get_s3_client, upload_to_s3

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


ENTRIES_KEYS = KeyPattern(prefix="entries", stem="entries", suffix=".parquet")
FORECASTS_KEYS = KeyPattern(prefix="forecasts", stem="forecasts", suffix=".parquet")
KEEP_FILES = 100


def export_upcoming_entries_and_forecasts(
        entries_path: Path,
        forecasts_path: Path,
        bucket: str,
        client: S3Client | None = None,
        timestamp: datetime | None = None
    ) -> tuple[str, str, list[str]]:
    """Upload the entries and the forecasts of a run to the S3 bucket, then delete the old files.

    See the module docstring for the rules.

    Args:
        entries_path: Parquet file of the entries.
        forecasts_path: Parquet file of the forecasts.
        bucket: Name of the bucket.
        client: S3 client (created from the settings if None).
        timestamp: Time of the keys, converted to UTC (time of the upload if
            None).

    Returns:
        The S3 URI of the uploaded entries, the S3 URI of the uploaded
        forecasts, and the deleted keys (entries first, then forecasts).

    Raises:
        ValueError: If the timestamp has no time zone (nothing is uploaded).
        FileNotFoundError: If the file of the entries or of the forecasts does
            not exist (nothing is uploaded).
    """
    if timestamp is not None and timestamp.utcoffset() is None:
        raise ValueError(f"The timestamp has no time zone: {timestamp.isoformat()}")
    for path in (entries_path, forecasts_path):
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")
    client = client or get_s3_client()
    timestamp = (timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc)
    entries_uri = upload_to_s3(
        entries_path, bucket=bucket, key=ENTRIES_KEYS.build_key(timestamp), client=client
    )
    forecasts_uri = upload_to_s3(
        forecasts_path, bucket=bucket, key=FORECASTS_KEYS.build_key(timestamp), client=client
    )
    deleted_keys = [
        *delete_old_keys(bucket, ENTRIES_KEYS, keep=KEEP_FILES, client=client),
        *delete_old_keys(bucket, FORECASTS_KEYS, keep=KEEP_FILES, client=client),
    ]
    return entries_uri, forecasts_uri, deleted_keys
