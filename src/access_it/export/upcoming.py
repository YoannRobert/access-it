"""Entries and forecasts of the upcoming races on the S3 storage.

Each run of the forecast of the upcoming races produces two Parquet files: the
entries (written by scripts/extract_upcoming_entries.py) and the forecasts
(written by scripts/forecast_upcoming_races.py). Rules:

- the files are uploaded under keys following ENTRIES_KEYS and FORECASTS_KEYS,
  with the same UTC timestamp (the time of the upload, or a chosen time), so
  that the entries and the forecasts of a run can be paired;
- both files are checked first: if one is missing, nothing is uploaded;
- if the file of the forecasts has no row (read from its Parquet metadata),
  nothing is uploaded either, so that every pair on the bucket has forecasts;
  the file of the entries is not read;
- the entries are uploaded before the forecasts, so that a file of forecasts
  proves that the entries of the same timestamp were uploaded too;
- after both uploads, only the KEEP_FILES most recent files of each kind are
  kept (entries first, then forecasts).

The files are downloaded back into a local directory reserved for them, with
these rules:

- the keys of each kind are listed once; each file of forecasts is paired with
  the entries of the same timestamp, if any (the entries without forecasts are
  ignored);
- only the files missing from the directory are downloaded, first under a
  temporary .part name, then renamed, so that a file under its final name is
  always complete;
- every other file of the directory (files no longer on the bucket, .part
  files left by an interrupted download) is deleted;
- the errors of the S3 client are not caught: the files already downloaded
  stay and are reused by the next call.
"""

from __future__ import annotations

import logging

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import pyarrow.parquet as pq

from access_it.export.s3 import (
    KeyPattern, delete_old_keys, get_s3_client, list_keys, upload_to_s3
)

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


ENTRIES_KEYS = KeyPattern(prefix="entries", stem="entries", suffix=".parquet")
FORECASTS_KEYS = KeyPattern(prefix="forecasts", stem="forecasts", suffix=".parquet")
KEEP_FILES = 100

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UpcomingFiles:
    """Local files of a run: forecasts and entries of the same timestamp."""
    timestamp: datetime
    forecasts_path: Path
    entries_path: Path | None


def export_upcoming_entries_and_forecasts(
        entries_path: Path,
        forecasts_path: Path,
        bucket: str,
        client: S3Client | None = None,
        timestamp: datetime | None = None
    ) -> tuple[str, str, list[str]] | None:
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
        forecasts, and the deleted keys (entries first, then forecasts), or
        None if the file of the forecasts has no row (nothing is uploaded).

    Raises:
        ValueError: If the timestamp has no time zone (nothing is uploaded).
        FileNotFoundError: If the file of the entries or of the forecasts does
            not exist (nothing is uploaded).
        pyarrow.ArrowInvalid: If the file of the forecasts is not a Parquet
            file (nothing is uploaded).
    """
    if timestamp is not None and timestamp.utcoffset() is None:
        raise ValueError(f"The timestamp has no time zone: {timestamp.isoformat()}")
    for path in (entries_path, forecasts_path):
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")
    if pq.read_metadata(forecasts_path).num_rows == 0:
        return None
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


def download_upcoming_entries_and_forecasts(
        bucket: str,
        dest_dir: Path,
        client: S3Client | None = None
    ) -> list[UpcomingFiles]:
    """Download the forecasts and their entries missing from `dest_dir`, then delete the others.

    See the module docstring for the rules.

    Args:
        bucket: Name of the bucket.
        dest_dir: Local directory reserved for these files, created if missing.
        client: S3 client (created from the settings if None).

    Returns:
        The files of each run with forecasts, from the most recent to the
        oldest; entries_path is None (with a warning in the log) if the bucket
        holds no entries of the same timestamp.
    """
    client = client or get_s3_client()
    dest_dir.mkdir(parents=True, exist_ok=True)
    forecasts_keys = list_keys(bucket, FORECASTS_KEYS, client=client)
    entries_keys = {
        ENTRIES_KEYS.parse_timestamp(key): key
        for key in list_keys(bucket, ENTRIES_KEYS, client=client)
    }
    runs = []
    for forecasts_key in forecasts_keys:
        timestamp = FORECASTS_KEYS.parse_timestamp(forecasts_key)
        entries_key = entries_keys.get(timestamp)
        if entries_key is None:
            logger.warning("No entries for the forecasts %s", forecasts_key)
        runs.append((timestamp, forecasts_key, entries_key))
    keys = [key for _, *run_keys in runs for key in run_keys if key is not None]
    for key in keys:
        local_path = dest_dir / Path(key).name
        if not local_path.is_file():
            part_path = local_path.with_name(f"{local_path.name}.part")
            client.download_file(Bucket=bucket, Key=key, Filename=str(part_path))
            part_path.replace(local_path)
    kept = {dest_dir / Path(key).name for key in keys}
    for path in dest_dir.iterdir():
        if path.is_file() and path not in kept:
            path.unlink()
    return [
        UpcomingFiles(
            timestamp=timestamp,
            forecasts_path=dest_dir / Path(forecasts_key).name,
            entries_path=dest_dir / Path(entries_key).name if entries_key else None,
        )
        for timestamp, forecasts_key, entries_key in runs
    ]
