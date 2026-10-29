"""Snapshots of the database on an S3 storage: upload, listing, rotation, download.

Snapshot keys are 'snapshots/snapshot_<UTC timestamp>.zip'.
"""

from __future__ import annotations

import boto3
import re

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from access_it.config import get_settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client
    from mypy_boto3_s3.type_defs import ObjectIdentifierTypeDef


SNAPSHOT_PREFIX = "snapshots"
SNAPSHOT_STEM = "snapshot"
TIMESTAMP_FORMAT = "%Y%m%dT%H%M%SZ"

_SNAPSHOT_KEY_PATTERN = re.compile(
    rf"^{re.escape(SNAPSHOT_PREFIX)}/{re.escape(SNAPSHOT_STEM)}_(\d{{8}}T\d{{6}}Z)\.zip$"
)
_DELETE_BATCH_SIZE = 1000  # S3 limit for delete_objects


def get_s3_client():
    """Create an S3 client from environment variables."""
    settings = get_settings()
    return boto3.client(
        service_name="s3",
        endpoint_url=settings.aws_endpoint_url_s3,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )


def build_snapshot_key(timestamp: datetime | None = None) -> str:
    """Build a timestamped snapshot key, e.g. 'snapshots/snapshot_20260926T124100Z.zip'."""
    timestamp = timestamp or datetime.now(timezone.utc)
    return f"{SNAPSHOT_PREFIX}/{SNAPSHOT_STEM}_{timestamp.strftime(TIMESTAMP_FORMAT)}.zip"


def parse_snapshot_timestamp(key: str) -> datetime | None:
    """Extract the UTC timestamp from a snapshot key or return None if the key does not match."""
    match = _SNAPSHOT_KEY_PATTERN.match(key)
    if match is None:
        return None
    return datetime.strptime(match.group(1), TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)


def upload_to_s3(
        file_path: Path,
        bucket: str,
        key: str,
        client: S3Client | None = None
    ) -> str:
    """Upload a local file to an S3 bucket and return its S3 URI."""
    client = client or get_s3_client()
    client.upload_file(Filename=str(file_path), Bucket=bucket, Key=key)
    return f"s3://{bucket}/{key}"


def list_snapshot_keys(bucket: str, client: S3Client | None = None) -> list[str]:
    """List snapshot keys in the bucket, sorted from most recent to oldest.

    Objects whose name does not match the snapshot pattern are ignored.
    """
    client = client or get_s3_client()
    paginator = client.get_paginator("list_objects_v2")

    snapshots: list[tuple[datetime, str]] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=f"{SNAPSHOT_PREFIX}/"):
        for obj in page.get("Contents", []):
            timestamp = parse_snapshot_timestamp(obj["Key"])
            if timestamp is not None:
                snapshots.append((timestamp, obj["Key"]))

    snapshots.sort(reverse=True)
    return [key for _, key in snapshots]


def delete_old_snapshots(
        bucket: str,
        keep: int = 10,
        client: S3Client | None = None
    ) -> list[str]:
    """Delete all snapshots except the `keep` most recent ones.

    Args:
        bucket: S3 bucket.
        keep: Number of most recent snapshots kept.
        client: S3 client (created from the settings if None).

    Returns:
        The deleted keys.

    Raises:
        ValueError: If `keep` is less than 1.
        RuntimeError: If some snapshots could not be deleted.
    """
    if keep < 1:
        raise ValueError(f"'keep' must be >= 1, got {keep}.")

    client = client or get_s3_client()
    keys_to_delete = list_snapshot_keys(bucket, client=client)[keep:]

    for start in range(0, len(keys_to_delete), _DELETE_BATCH_SIZE):
        batch = keys_to_delete[start: start + _DELETE_BATCH_SIZE]
        objects: list[ObjectIdentifierTypeDef] = [{"Key": key} for key in batch]
        response = client.delete_objects(
            Bucket=bucket,
            Delete={"Objects": objects, "Quiet": True},
        )
        errors = response.get("Errors", [])
        if errors:
            raise RuntimeError(f"Failed to delete some snapshots: {errors}")

    return keys_to_delete


def snapshot_key_from_name(name: str) -> str:
    """Snapshot key from a key or a file name, e.g. 'snapshot_20260926T124100Z.zip'.

    Raises:
        ValueError: If the name does not match the snapshot pattern.
    """
    key = name if name.startswith(f"{SNAPSHOT_PREFIX}/") else f"{SNAPSHOT_PREFIX}/{name}"
    if parse_snapshot_timestamp(key) is None:
        raise ValueError(
            f"Invalid snapshot name '{name}' (expected e.g. '{Path(build_snapshot_key()).name}')"
        )
    return key


def download_snapshot(
        bucket: str,
        key: str,
        dest_dir: Path,
        client: S3Client | None = None
    ) -> Path:
    """Download a snapshot into `dest_dir` and return the local file path.

    Args:
        bucket: Name of the bucket.
        key: Snapshot key, or file name (see snapshot_key_from_name).
        dest_dir: Local directory, created if missing.
        client: S3 client (created from the settings if None).

    Raises:
        ValueError: If the name does not match the snapshot pattern.
        FileNotFoundError: If the bucket holds no snapshot with this key.
    """
    client = client or get_s3_client()
    key = snapshot_key_from_name(key)
    if key not in list_snapshot_keys(bucket, client=client):
        raise FileNotFoundError(f"Snapshot not found: s3://{bucket}/{key}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    local_path = dest_dir / Path(key).name
    client.download_file(Bucket=bucket, Key=key, Filename=str(local_path))
    return local_path


def download_latest_snapshot(
        bucket: str,
        dest_dir: Path,
        client: S3Client | None = None
    ) -> Path:
    """Download the most recent snapshot into `dest_dir` and return the local file path.

    Raises:
        FileNotFoundError: If the bucket holds no snapshot.
    """
    client = client or get_s3_client()
    keys = list_snapshot_keys(bucket, client=client)
    if not keys:
        raise FileNotFoundError(f"No snapshot found in s3://{bucket}/{SNAPSHOT_PREFIX}/")
    return download_snapshot(bucket, keys[0], dest_dir, client=client)
