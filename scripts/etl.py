"""Run the whole ETL: extract, transform, then load, with the synchronizations around them.

By default, the page cache is synchronized with the S3 bucket: the most recent
archive is pulled before the extract, and a new one is pushed after the load.
A snapshot of the database is then exported to the bucket, for the dashboard.
The first failure stops the steps that follow it.

Usage, from the repository root:
    python scripts/etl.py [--no-cache-sync] [--no-snapshot-export]
"""

import argparse

from access_it.common.log import setup_logging
from export_database_to_s3_bucket import export_database_to_s3_bucket
from extract import extract
from transform import transform
from load import load
from sync_cache import sync_cache


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the whole ETL.")
    parser.add_argument(
        "--no-cache-sync", action="store_true",
        help="neither pull the cache before the extract nor push it after the load"
    )
    parser.add_argument(
        "--no-snapshot-export", action="store_true",
        help="do not export a snapshot of the database after the load"
    )
    return parser.parse_args()


def etl(cache_sync: bool = True, snapshot_export: bool = True) -> None:
    """Run the steps of the ETL in this order; the first failure stops the following steps.

    Args:
        cache_sync: Whether to pull the cache before the extract and push it after the load.
        snapshot_export: Whether to export a snapshot of the database at the end.
    """
    if cache_sync:
        sync_cache("pull")
    extract()
    transform()
    load()
    if cache_sync:
        sync_cache("push")
    if snapshot_export:
        export_database_to_s3_bucket()


if __name__ == "__main__":
    setup_logging()
    args = parse_args()
    etl(cache_sync=not args.no_cache_sync, snapshot_export=not args.no_snapshot_export)
