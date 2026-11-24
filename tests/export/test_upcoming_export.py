"""Unit tests of the upload of the files of the upcoming races, with a fake S3 client."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from access_it.export.s3 import KeyPattern
from access_it.export.upcoming import (
    ENTRIES_KEYS, FORECASTS_KEYS, KEEP_FILES, export_upcoming_entries_and_forecasts
)


class FakeS3Client:
    """Bucket storing the content of the uploaded files, by key, in upload order."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def upload_file(self, Filename: str, Bucket: str, Key: str) -> None:
        self.objects[Key] = Path(Filename).read_bytes()

    def get_paginator(self, name: str):
        keys = list(self.objects)

        class Paginator:
            def paginate(self, Bucket: str, Prefix: str):
                yield {"Contents": [{"Key": key} for key in keys if key.startswith(Prefix)]}

        return Paginator()

    def delete_objects(self, Bucket: str, Delete: dict) -> dict:
        for obj in Delete["Objects"]:
            del self.objects[obj["Key"]]
        return {}


def old_keys(pattern: KeyPattern, count: int) -> list[str]:
    """Keys of `count` files of a kind, one per day from 2026-01-01, from oldest to most recent."""
    start = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)
    return [pattern.build_key(start + timedelta(days=day)) for day in range(count)]


@pytest.fixture
def files(tmp_path) -> tuple[Path, Path]:
    """Files of the entries and of the forecasts of a run."""
    entries_path = tmp_path / "entries.parquet"
    forecasts_path = tmp_path / "forecasts.parquet"
    entries_path.write_bytes(b"entries")
    forecasts_path.write_bytes(b"forecasts")
    return entries_path, forecasts_path


def test_both_files_get_the_same_timestamp(files):
    client = FakeS3Client()
    export_upcoming_entries_and_forecasts(*files, "bucket", client=client)
    [entries_key, forecasts_key] = client.objects
    entries_timestamp = ENTRIES_KEYS.parse_timestamp(entries_key)
    assert entries_timestamp is not None
    assert FORECASTS_KEYS.parse_timestamp(forecasts_key) == entries_timestamp
    assert client.objects[entries_key] == b"entries"
    assert client.objects[forecasts_key] == b"forecasts"


def test_the_entries_are_uploaded_before_the_forecasts(files):
    client = FakeS3Client()
    export_upcoming_entries_and_forecasts(*files, "bucket", client=client)
    assert [key.split("/")[0] for key in client.objects] == ["entries", "forecasts"]


@pytest.mark.parametrize("missing", [0, 1], ids=["entries", "forecasts"])
def test_a_missing_file_uploads_nothing(files, missing):
    files[missing].unlink()
    client = FakeS3Client()
    with pytest.raises(FileNotFoundError, match="File not found"):
        export_upcoming_entries_and_forecasts(*files, "bucket", client=client)
    assert client.objects == {}


def test_the_most_recent_files_of_each_kind_are_kept(files):
    client = FakeS3Client()
    old_entries = old_keys(ENTRIES_KEYS, KEEP_FILES)
    old_forecasts = old_keys(FORECASTS_KEYS, 10)
    client.objects = {key: b"" for key in (*old_entries, *old_forecasts)}
    export_upcoming_entries_and_forecasts(*files, "bucket", client=client)
    kept_entries = [key for key in client.objects if key.startswith("entries/")]
    kept_forecasts = [key for key in client.objects if key.startswith("forecasts/")]
    assert len(kept_entries) == KEEP_FILES
    assert old_entries[0] not in kept_entries
    assert len(kept_forecasts) == len(old_forecasts) + 1


def test_the_uris_and_the_deleted_keys_are_returned(files):
    client = FakeS3Client()
    old_entries = old_keys(ENTRIES_KEYS, KEEP_FILES)
    client.objects = {key: b"" for key in old_entries}
    entries_uri, forecasts_uri, deleted_keys = export_upcoming_entries_and_forecasts(
        *files, "bucket", client=client
    )
    entries_key, forecasts_key = list(client.objects)[-2:]
    assert entries_uri == f"s3://bucket/{entries_key}"
    assert forecasts_uri == f"s3://bucket/{forecasts_key}"
    assert deleted_keys == [old_entries[0]]
