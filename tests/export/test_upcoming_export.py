"""Unit tests of the upload and download of the files of the upcoming races, with a fake S3
client."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest

from access_it.export.s3 import KeyPattern
from access_it.export.upcoming import (
    ENTRIES_KEYS,
    FORECASTS_KEYS,
    KEEP_FILES,
    UpcomingFiles,
    download_upcoming_entries_and_forecasts,
    export_upcoming_entries_and_forecasts,
)


class FakeS3Client:
    """Bucket storing the content of the uploaded files, by key, in upload order."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.downloaded: list[str] = []

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

    def download_file(self, Bucket: str, Key: str, Filename: str) -> None:
        self.downloaded.append(Key)
        Path(Filename).write_bytes(self.objects[Key])


def old_keys(pattern: KeyPattern, count: int) -> list[str]:
    """Keys of `count` files of a kind, one per day from 2026-01-01, from oldest to most recent."""
    start = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)
    return [pattern.build_key(start + timedelta(days=day)) for day in range(count)]


@pytest.fixture
def files(tmp_path) -> tuple[Path, Path]:
    """Files of the entries (not read, so not a Parquet file) and of the forecasts of a run."""
    entries_path = tmp_path / "entries.parquet"
    forecasts_path = tmp_path / "forecasts.parquet"
    entries_path.write_bytes(b"entries")
    pd.DataFrame({"race_id": ["race"]}).to_parquet(forecasts_path, index=False)
    return entries_path, forecasts_path


def test_both_files_get_the_same_timestamp(files):
    client = FakeS3Client()
    export_upcoming_entries_and_forecasts(*files, "bucket", client=client)
    [entries_key, forecasts_key] = client.objects
    entries_timestamp = ENTRIES_KEYS.parse_timestamp(entries_key)
    assert entries_timestamp is not None
    assert FORECASTS_KEYS.parse_timestamp(forecasts_key) == entries_timestamp
    assert client.objects[entries_key] == b"entries"
    assert client.objects[forecasts_key] == files[1].read_bytes()


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


@pytest.mark.parametrize(
    "timestamp",
    [
        datetime(2026, 5, 10, 18, tzinfo=timezone.utc),
        datetime(2026, 5, 10, 20, tzinfo=timezone(timedelta(hours=2))),
    ],
    ids=["utc", "utc+2"],
)
def test_a_chosen_timestamp_is_used_in_utc_for_both_files(files, timestamp):
    client = FakeS3Client()
    export_upcoming_entries_and_forecasts(*files, "bucket", client=client, timestamp=timestamp)
    assert list(client.objects) == [
        "entries/entries_20260510T180000Z.parquet",
        "forecasts/forecasts_20260510T180000Z.parquet",
    ]


def test_a_timestamp_without_time_zone_uploads_nothing(files):
    client = FakeS3Client()
    with pytest.raises(ValueError, match="no time zone"):
        export_upcoming_entries_and_forecasts(
            *files, "bucket", client=client, timestamp=datetime(2026, 5, 10, 20)
        )
    assert client.objects == {}


def test_empty_forecasts_upload_nothing_and_delete_nothing(files):
    pd.DataFrame({"race_id": pd.Series(dtype=str)}).to_parquet(files[1], index=False)
    client = FakeS3Client()
    old_entries = old_keys(ENTRIES_KEYS, KEEP_FILES)
    client.objects = {key: b"" for key in old_entries}
    assert export_upcoming_entries_and_forecasts(*files, "bucket", client=client) is None
    assert list(client.objects) == old_entries


def test_an_unreadable_file_of_forecasts_uploads_nothing(files):
    files[1].write_bytes(b"forecasts")
    client = FakeS3Client()
    with pytest.raises(pa.ArrowInvalid):
        export_upcoming_entries_and_forecasts(*files, "bucket", client=client)
    assert client.objects == {}


# Download

def run_keys(day: int) -> tuple[datetime, str, str]:
    """Timestamp, forecasts key and entries key of a run on day `day` of January 2026."""
    timestamp = datetime(2026, 1, day, 19, 30, tzinfo=timezone.utc)
    return timestamp, FORECASTS_KEYS.build_key(timestamp), ENTRIES_KEYS.build_key(timestamp)


def test_the_runs_are_downloaded_from_the_most_recent(tmp_path):
    (old_time, old_forecasts, old_entries), (new_time, new_forecasts, new_entries) = (
        run_keys(1), run_keys(2)
    )
    client = FakeS3Client()
    client.objects = {
        old_entries: b"old entries", old_forecasts: b"old forecasts",
        new_entries: b"new entries", new_forecasts: b"new forecasts",
    }
    runs = download_upcoming_entries_and_forecasts("bucket", tmp_path, client=client)
    assert runs == [
        UpcomingFiles(
            new_time, tmp_path / Path(new_forecasts).name, tmp_path / Path(new_entries).name
        ),
        UpcomingFiles(
            old_time, tmp_path / Path(old_forecasts).name, tmp_path / Path(old_entries).name
        ),
    ]
    assert runs[0].forecasts_path.read_bytes() == b"new forecasts"
    assert runs[0].entries_path.read_bytes() == b"new entries"


def test_forecasts_without_entries_are_returned_alone_with_a_warning(tmp_path, caplog):
    timestamp, forecasts_key, _ = run_keys(1)
    client = FakeS3Client()
    client.objects = {forecasts_key: b"forecasts"}
    runs = download_upcoming_entries_and_forecasts("bucket", tmp_path, client=client)
    assert runs == [UpcomingFiles(timestamp, tmp_path / Path(forecasts_key).name, None)]
    assert f"No entries for the forecasts {forecasts_key}" in caplog.text


def test_entries_without_forecasts_are_ignored(tmp_path):
    _, _, entries_key = run_keys(1)
    client = FakeS3Client()
    client.objects = {entries_key: b"entries"}
    assert download_upcoming_entries_and_forecasts("bucket", tmp_path, client=client) == []
    assert client.downloaded == []
    assert list(tmp_path.iterdir()) == []


def test_a_file_already_present_is_not_downloaded_again(tmp_path):
    _, forecasts_key, entries_key = run_keys(1)
    client = FakeS3Client()
    client.objects = {forecasts_key: b"forecasts", entries_key: b"entries"}
    download_upcoming_entries_and_forecasts("bucket", tmp_path, client=client)
    download_upcoming_entries_and_forecasts("bucket", tmp_path, client=client)
    assert sorted(client.downloaded) == sorted([forecasts_key, entries_key])


def test_the_local_files_absent_from_the_bucket_are_deleted(tmp_path):
    _, old_forecasts, old_entries = run_keys(1)
    _, forecasts_key, entries_key = run_keys(2)
    client = FakeS3Client()
    client.objects = {
        old_forecasts: b"", old_entries: b"", forecasts_key: b"", entries_key: b"",
    }
    download_upcoming_entries_and_forecasts("bucket", tmp_path, client=client)
    del client.objects[old_forecasts], client.objects[old_entries]
    (tmp_path / f"{Path(forecasts_key).name}.part").write_bytes(b"orphan")
    download_upcoming_entries_and_forecasts("bucket", tmp_path, client=client)
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted(
        [Path(entries_key).name, Path(forecasts_key).name]
    )


def test_a_failed_download_leaves_no_file_under_its_final_name(tmp_path):
    _, forecasts_key, _ = run_keys(1)

    class FailingS3Client(FakeS3Client):
        def download_file(self, Bucket: str, Key: str, Filename: str) -> None:
            Path(Filename).write_bytes(b"partial")
            raise ConnectionError("Download interrupted")

    client = FailingS3Client()
    client.objects = {forecasts_key: b"forecasts"}
    with pytest.raises(ConnectionError):
        download_upcoming_entries_and_forecasts("bucket", tmp_path, client=client)
    assert not (tmp_path / Path(forecasts_key).name).exists()


def test_an_empty_bucket_gives_no_run_and_creates_the_directory(tmp_path):
    dest_dir = tmp_path / "upcoming"
    assert download_upcoming_entries_and_forecasts("bucket", dest_dir, client=FakeS3Client()) == []
    assert dest_dir.is_dir()
