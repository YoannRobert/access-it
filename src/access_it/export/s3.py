import boto3

from datetime import datetime, timezone
from pathlib import Path

from access_it.config import get_settings


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


def build_object_key(prefix: str = "snapshots", stem: str = "snapshot") -> str:
    """Build a timestamped S3 object key, e.g. 'snapshots/snapshot_20260926T124100Z.zip'."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}/{stem}_{timestamp}.zip"


def upload_to_s3(file_path: Path, bucket: str, key: str) -> str:
    """Upload a local file to an S3 bucket and return its S3 URI."""
    client = get_s3_client()
    client.upload_file(Filename=str(file_path), Bucket=bucket, Key=key)
    return f"s3://{bucket}/{key}"
