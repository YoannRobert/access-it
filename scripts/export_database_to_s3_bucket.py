"""Export a snapshot of the database to the S3 storage, keeping the 10 most recent ones.

The whole database is read (data transfer of a few megabytes).

Usage, from the repository root: python scripts/export_database_to_s3_bucket.py
"""

from access_it.common.log import setup_logging
from access_it.config import get_settings
from access_it.etl.load.engine import get_engine
from access_it.etl.load.queries import read_all_tables
from access_it.export.snapshot import export_snapshot


def export_database_to_s3_bucket():
    """Export a snapshot of every table, then delete the old snapshots."""
    tables = read_all_tables(get_engine())
    s3_uri, deleted_keys = export_snapshot(tables, bucket=get_settings().s3_bucket)
    print(f"Snapshot exported to {s3_uri} on the S3 bucket.")
    for deleted_key in deleted_keys:
        print(f"Snapshot {deleted_key} got deleted from the S3 bucket.")


if __name__ == "__main__":
    setup_logging()
    export_database_to_s3_bucket()
