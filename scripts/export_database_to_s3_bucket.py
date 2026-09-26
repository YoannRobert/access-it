import tempfile

from pathlib import Path

from access_it.config import get_settings
from access_it.export.s3 import upload_to_s3, build_object_key
from access_it.etl.extract.cache import CACHE_DIR
from access_it.etl.load.engine import get_engine
from access_it.etl.load.queries import read_all_tables
from access_it.export.snapshot import build_snapshot_zip


def export_database_to_s3_bucket():
    settings = get_settings()
    s3_bucket = settings.s3_bucket
    engine = get_engine()
    tables = read_all_tables(engine)
    with tempfile.TemporaryDirectory(dir=CACHE_DIR) as tmp_dir:
        zip_path = build_snapshot_zip(tables, Path(tmp_dir) / "snapshot.zip")
        s3_uri = upload_to_s3(zip_path, bucket=s3_bucket, key=build_object_key())
        print(f"Snapshot exported to {s3_uri} on the S3 bucket.")


if __name__ == "__main__":
    export_database_to_s3_bucket()
