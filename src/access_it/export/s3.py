"""Timestamped objects on an S3 storage: upload, listing, rotation, download.

The keys of a kind of object follow a KeyPattern, '<prefix>/<stem>_<UTC timestamp><suffix>'.
Snapshot keys are 'snapshots/snapshot_<UTC timestamp>.zip' (SNAPSHOT_KEYS).
"""

from __future__ import annotations

import boto3
import re

from dataclasses import dataclass
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

_DELETE_BATCH_SIZE = 1000  # S3 limit for delete_objects


@dataclass(frozen=True)
class KeyPattern:
    """Keys of a kind of timestamped object: '<prefix>/<stem>_<UTC timestamp><suffix>'.

    Attributes:
        prefix: Folder of the objects in the bucket, e.g. 'snapshots'.
        stem: Start of the file names, e.g. 'snapshot'.
        suffix: Extension of the file names, e.g. '.zip'.
    """

    prefix: str
    stem: str
    suffix: str

    def build_key(self, timestamp: datetime | None = None) -> str:
        """Build a key timestamped with `timestamp` (now, in UTC, if None)."""
        timestamp = timestamp or datetime.now(timezone.utc)
        return f"{self.prefix}/{self.stem}_{timestamp.strftime(TIMESTAMP_FORMAT)}{self.suffix}"

    def parse_timestamp(self, key: str) -> datetime | None:
        """Extract the UTC timestamp from a key or return None if the key does not match."""
        pattern = (
            rf"^{re.escape(self.prefix)}/{re.escape(self.stem)}_(\d{{8}}T\d{{6}}Z)"
            rf"{re.escape(self.suffix)}$"
        )
        match = re.match(pattern, key)
        if match is None:
            return None
        return datetime.strptime(match.group(1), TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)


SNAPSHOT_KEYS = KeyPattern(prefix=SNAPSHOT_PREFIX, stem=SNAPSHOT_STEM, suffix=".zip")


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
    return SNAPSHOT_KEYS.build_key(timestamp)


def parse_snapshot_timestamp(key: str) -> datetime | None:
    """Extract the UTC timestamp from a snapshot key or return None if the key does not match."""
    return SNAPSHOT_KEYS.parse_timestamp(key)


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


def list_keys(bucket: str, pattern: KeyPattern, client: S3Client | None = None) -> list[str]:
    """List the keys matching `pattern` in the bucket, sorted from most recent to oldest.

    Objects whose name does not match the pattern are ignored.
    """
    client = client or get_s3_client()
    paginator = client.get_paginator("list_objects_v2")

    objects: list[tuple[datetime, str]] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=f"{pattern.prefix}/"):
        for obj in page.get("Contents", []):
            timestamp = pattern.parse_timestamp(obj["Key"])
            if timestamp is not None:
                objects.append((timestamp, obj["Key"]))

    objects.sort(reverse=True)
    return [key for _, key in objects]


def list_snapshot_keys(bucket: str, client: S3Client | None = None) -> list[str]:
    """List snapshot keys in the bucket, sorted from most recent to oldest.

    Objects whose name does not match the snapshot pattern are ignored.
    """
    return list_keys(bucket, SNAPSHOT_KEYS, client=client)


def delete_old_keys(
        bucket: str,
        pattern: KeyPattern,
        keep: int,
        client: S3Client | None = None
    ) -> list[str]:
    """Delete all objects matching `pattern` except the `keep` most recent ones.

    Args:
        bucket: S3 bucket.
        pattern: Pattern of the keys.
        keep: Number of most recent objects kept.
        client: S3 client (created from the settings if None).

    Returns:
        The deleted keys.

    Raises:
        ValueError: If `keep` is less than 1.
        RuntimeError: If some objects could not be deleted.
    """
    if keep < 1:
        raise ValueError(f"'keep' must be >= 1, got {keep}.")

    client = client or get_s3_client()
    keys_to_delete = list_keys(bucket, pattern, client=client)[keep:]

    for start in range(0, len(keys_to_delete), _DELETE_BATCH_SIZE):
        batch = keys_to_delete[start: start + _DELETE_BATCH_SIZE]
        objects: list[ObjectIdentifierTypeDef] = [{"Key": key} for key in batch]
        response = client.delete_objects(
            Bucket=bucket,
            Delete={"Objects": objects, "Quiet": True},
        )
        errors = response.get("Errors", [])
        if errors:
            raise RuntimeError(f"Failed to delete some objects: {errors}")

    return keys_to_delete


def delete_old_snapshots(
        bucket: str,
        keep: int = 10,
        client: S3Client | None = None
    ) -> list[str]:
    """Delete all snapshots except the `keep` most recent ones (see delete_old_keys)."""
    return delete_old_keys(bucket, SNAPSHOT_KEYS, keep=keep, client=client)


def snapshot_key_from_name(name: str) -> str:
    """Snapshot key from a key or a file name, e.g. 'snapshot_20260926T124100Z.zip'.

    Raises:
        ValueError: If the name does not match the snapshot pattern.
    """
    key = name if name.startswith(f"{SNAPSHOT_PREFIX}/") else f"{SNAPSHOT_PREFIX}/{name}"
    if SNAPSHOT_KEYS.parse_timestamp(key) is None:
        raise ValueError(
            f"Invalid snapshot name '{name}' (expected e.g. '{Path(SNAPSHOT_KEYS.build_key()).name}')"
        )
    return key


def download_key(
        bucket: str,
        pattern: KeyPattern,
        key: str,
        dest_dir: Path,
        client: S3Client | None = None
    ) -> Path:
    """Download the object of a key matching `pattern` into `dest_dir` and return the local path.

    Args:
        bucket: Name of the bucket.
        pattern: Pattern of the keys.
        key: Key of the object.
        dest_dir: Local directory, created if missing.
        client: S3 client (created from the settings if None).

    Raises:
        FileNotFoundError: If the bucket holds no object matching `pattern` with this key.
    """
    client = client or get_s3_client()
    if key not in list_keys(bucket, pattern, client=client):
        raise FileNotFoundError(f"Object not found: s3://{bucket}/{key}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    local_path = dest_dir / Path(key).name
    client.download_file(Bucket=bucket, Key=key, Filename=str(local_path))
    return local_path


def download_latest(
        bucket: str,
        pattern: KeyPattern,
        dest_dir: Path,
        client: S3Client | None = None
    ) -> Path:
    """Download the most recent object matching `pattern` into `dest_dir`; return the local path.

    Raises:
        FileNotFoundError: If the bucket holds no object matching `pattern`.
    """
    client = client or get_s3_client()
    keys = list_keys(bucket, pattern, client=client)
    if not keys:
        raise FileNotFoundError(f"No object found in s3://{bucket}/{pattern.prefix}/")
    return download_key(bucket, pattern, keys[0], dest_dir, client=client)


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
    return download_key(bucket, SNAPSHOT_KEYS, snapshot_key_from_name(key), dest_dir, client=client)


def download_latest_snapshot(
        bucket: str,
        dest_dir: Path,
        client: S3Client | None = None
    ) -> Path:
    """Download the most recent snapshot into `dest_dir` and return the local file path.

    Raises:
        FileNotFoundError: If the bucket holds no snapshot.
    """
    return download_latest(bucket, SNAPSHOT_KEYS, dest_dir, client=client)
