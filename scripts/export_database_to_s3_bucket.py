import tempfile

from pathlib import Path

from access_it.config import get_settings
from access_it.export.s3 import (
    get_s3_client, upload_to_s3, build_snapshot_key,
    delete_old_snapshots
)
from access_it.etl.extract.cache import SNAPSHOTS_DIR
from access_it.etl.load.engine import get_engine
from access_it.etl.load.queries import read_all_tables
from access_it.export.snapshot import build_snapshot_zip


def export_database_to_s3_bucket():
    settings = get_settings()
    s3_bucket = settings.s3_bucket
    engine = get_engine()
    client = get_s3_client()
    tables = read_all_tables(engine)
    with tempfile.TemporaryDirectory(dir=SNAPSHOTS_DIR) as tmp_dir:
        zip_path = build_snapshot_zip(tables, Path(tmp_dir) / "snapshot.zip")
        s3_uri = upload_to_s3(
            zip_path,
            bucket=s3_bucket,
            key=build_snapshot_key(),
            client=client
        )
        print(f"Snapshot exported to {s3_uri} on the S3 bucket.")
    deleted_keys = delete_old_snapshots(s3_bucket, keep=10, client=client)
    for deleted_key in deleted_keys:
        print(f"Snapshot {deleted_key} got deleted from the S3 bucket.")


if __name__ == "__main__":
    export_database_to_s3_bucket()
