"""Restore the database from a snapshot of the S3 storage.

Steps: download of the snapshot (the most recent one by default), check of its
schema, count of the rows to insert, update or delete, confirmation, snapshot
of the current database (the 10 most recent snapshots are kept), restoration
within a single transaction, then check of the number of rows of every table.
Nothing is done if the schema differs or if the database already matches the
snapshot. The whole database is read (data transfer of a few megabytes).

Usage, from the repository root:
    python scripts/restore_database_from_s3_bucket.py --list
    python scripts/restore_database_from_s3_bucket.py [--key snapshot_<timestamp>.zip] [--yes]
"""

import argparse
import sys
import tempfile

from pathlib import Path

from access_it.common.log import setup_logging
from access_it.config import get_settings
from access_it.etl.extract.cache import SNAPSHOTS_DIR
from access_it.etl.load.engine import get_engine
from access_it.etl.load.queries import read_all_tables
from access_it.etl.load.restore import (
    check_snapshot_schema, compute_changes, count_rows, restore_tables
)
from access_it.export.s3 import (
    download_latest_snapshot, download_snapshot, get_s3_client, list_snapshot_keys
)
from access_it.export.snapshot import export_snapshot, read_snapshot_zip


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Restore the database from a snapshot of the S3 storage.")
    parser.add_argument("--list", action="store_true", help="list the snapshots, then stop")
    parser.add_argument("--key", help="file name of the snapshot (default: the most recent one)")
    parser.add_argument("--yes", action="store_true", help="restore without confirmation")
    return parser.parse_args()


def restore_database_from_s3_bucket(key: str | None, assume_yes: bool) -> int:
    """Restore the database from a snapshot; return the exit code of the script."""
    bucket = get_settings().s3_bucket
    client = get_s3_client()

    # The cache directories may not exist yet (e.g. on a new machine)
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=SNAPSHOTS_DIR) as tmp_dir:
        if key is None:
            zip_path = download_latest_snapshot(bucket, Path(tmp_dir), client=client)
        else:
            zip_path = download_snapshot(bucket, key, Path(tmp_dir), client=client)
        snapshot = read_snapshot_zip(zip_path)
    print(f"Snapshot {zip_path.name} downloaded.")

    try:
        check_snapshot_schema(snapshot)
    except ValueError as error:
        print(f"{error}\nNothing done.")
        return 1

    engine = get_engine()
    current = read_all_tables(engine)
    changes = compute_changes(snapshot, current)
    print(f"{'table':<26}{'inserted':>10}{'updated':>10}{'deleted':>10}")
    for name, change in changes.items():
        print(f"{name:<26}{change.inserted:>10}{change.updated:>10}{change.deleted:>10}")
    if sum(change.total for change in changes.values()) == 0:
        print("The database already matches the snapshot: nothing done.")
        return 0

    if not assume_yes:
        answer = input(f"Type 'yes' to restore the database from {zip_path.name}: ")
        if answer.strip() != "yes":
            print("Restoration cancelled: nothing done.")
            return 0

    s3_uri, deleted_keys = export_snapshot(current, bucket=bucket, client=client)
    print(f"Current database saved to {s3_uri} on the S3 bucket.")
    for deleted_key in deleted_keys:
        print(f"Snapshot {deleted_key} got deleted from the S3 bucket.")

    restore_tables(engine, snapshot)

    counts = count_rows(engine)
    mismatches = {
        name: (len(df), counts[name]) for name, df in snapshot.items() if counts[name] != len(df)
    }
    if mismatches:
        for name, (expected, found) in mismatches.items():
            print(f"Table '{name}': {found} rows in the database, {expected} in the snapshot.")
        print("Restoration done, but the number of rows differs from the snapshot.")
        return 1
    print(f"Database restored from {zip_path.name}: the number of rows of every table matches.")
    return 0


def main() -> None:
    args = parse_args()
    if args.list:
        for snapshot_key in list_snapshot_keys(get_settings().s3_bucket):
            print(Path(snapshot_key).name)
        return
    sys.exit(restore_database_from_s3_bucket(args.key, args.yes))


if __name__ == "__main__":
    setup_logging()
    main()
