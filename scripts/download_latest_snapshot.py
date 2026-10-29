"""Download the most recent snapshot of the database from the S3 storage.

The snapshot is downloaded into the current directory by default, into an
existing directory with --dst-dir, or into the snapshot directory of the cache
(SNAPSHOTS_DIR, created if missing) with --cache. Nothing is downloaded if the
file already exists in the destination directory.

Usage, from the repository root:
    python scripts/download_latest_snapshot.py [--dst-dir DIRECTORY | --cache]
"""

import argparse

from pathlib import Path

from access_it.common.log import setup_logging
from access_it.config import get_settings
from access_it.etl.extract.cache import SNAPSHOTS_DIR
from access_it.export.s3 import download_snapshot, get_s3_client, list_snapshot_keys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download the most recent snapshot of the database.")
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument(
        "-d", "--dst-dir", type=Path, help="existing directory where the snapshot is downloaded"
    )
    destination.add_argument(
        "-c", "--cache", action="store_true", help="download into the snapshot directory of the cache"
    )
    return parser.parse_args()


def download_latest_snapshot(dst_dir: Path | None, cache: bool) -> None:
    """Download the most recent snapshot into the destination directory.

    Args:
        dst_dir: Existing destination directory (current directory if None).
        cache: Whether to download into SNAPSHOTS_DIR, created if missing.

    Raises:
        FileNotFoundError: If `dst_dir` is not an existing directory, or if
            the bucket holds no snapshot.
    """
    if cache:
        dst_dir = SNAPSHOTS_DIR
        dst_dir.mkdir(parents=True, exist_ok=True)
    elif dst_dir is None:
        dst_dir = Path.cwd()
    elif not dst_dir.is_dir():
        raise FileNotFoundError(f"Destination directory not found: {dst_dir}")

    bucket = get_settings().s3_bucket
    client = get_s3_client()
    keys = list_snapshot_keys(bucket, client=client)
    if not keys:
        raise FileNotFoundError(f"No snapshot found in the bucket {bucket}")
    local_path = dst_dir / Path(keys[0]).name
    if local_path.exists():
        print(f"{local_path} already exists: nothing downloaded.")
        return
    download_snapshot(bucket, keys[0], dst_dir, client=client)
    print(f"Snapshot downloaded to {local_path}.")


if __name__ == "__main__":
    setup_logging()
    args = parse_args()
    download_latest_snapshot(args.dst_dir, args.cache)
