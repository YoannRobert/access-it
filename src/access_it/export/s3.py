from __future__ import annotations

import boto3
import re

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from access_it.config import get_settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


SNAPSHOT_PREFIX = "snapshots"
SNAPSHOT_STEM = "snapshot"
TIMESTAMP_FORMAT = "%Y%m%dT%H%M%SZ"

_SNAPSHOT_KEY_PATTERN = re.compile(
    rf"^{re.escape(SNAPSHOT_PREFIX)}/{re.escape(SNAPSHOT_STEM)}_(\d{{8}}T\d{{6}}Z)\.zip$"
)


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
