"""Snapshot of the database: one Parquet file per table in a ZIP archive (writing and reading)."""

from __future__ import annotations

import io
import pandas as pd
import tempfile
import zipfile

from pathlib import Path
from typing import TYPE_CHECKING

from access_it.etl.extract.cache import SNAPSHOTS_DIR
from access_it.export.s3 import (
    build_snapshot_key, delete_old_snapshots, get_s3_client, upload_to_s3
)

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def build_snapshot_zip(tables: dict[str, pd.DataFrame], zip_path: Path) -> Path:
    """Write each DataFrame as a Parquet file inside a single ZIP archive."""
    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_STORED) as zf:
        for table_name, df in tables.items():
            buffer = io.BytesIO()
            df.to_parquet(buffer, index=False)
            zf.writestr(f"{table_name}.parquet", buffer.getvalue())
    return zip_path


def read_snapshot_zip(zip_path: Path) -> dict[str, pd.DataFrame]:
    """Read a snapshot archive (see build_snapshot_zip) into DataFrames, by table name.

    Raises:
        ValueError: If the archive holds a file other than a Parquet file.
    """
    tables = {}
    with zipfile.ZipFile(zip_path, mode="r") as zf:
        for name in zf.namelist():
            table_name, suffix = Path(name).stem, Path(name).suffix
            if suffix != ".parquet" or Path(name).name != name:
                raise ValueError(f"Unexpected file in the snapshot {zip_path.name}: {name}")
            tables[table_name] = pd.read_parquet(io.BytesIO(zf.read(name)))
    return tables


def export_snapshot(
        tables: dict[str, pd.DataFrame],
        bucket: str,
        keep: int = 10,
        client: S3Client | None = None
    ) -> tuple[str, list[str]]:
    """Upload a snapshot of the tables to the S3 bucket, then delete the old snapshots.

    The archive is built in a temporary directory of SNAPSHOTS_DIR, deleted afterwards.

    Args:
        tables: Content of every table, keyed by table name.
        bucket: Name of the bucket.
        keep: Number of most recent snapshots kept.
        client: S3 client (created from the settings if None).

    Returns:
        The S3 URI of the uploaded snapshot and the deleted keys.
    """
    client = client or get_s3_client()
    # The cache directories may not exist yet (e.g. on a new machine)
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=SNAPSHOTS_DIR) as tmp_dir:
        zip_path = build_snapshot_zip(tables, Path(tmp_dir) / "snapshot.zip")
        s3_uri = upload_to_s3(zip_path, bucket=bucket, key=build_snapshot_key(), client=client)
    deleted_keys = delete_old_snapshots(bucket, keep=keep, client=client)
    return s3_uri, deleted_keys
