"""Unit tests of the functions of the S3 storage, with a fake S3 client."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from access_it.export.s3 import (
    KeyPattern, delete_old_keys, download_latest, download_latest_snapshot, download_snapshot,
    list_keys, snapshot_key_from_name
)

OLD_KEY = "snapshots/snapshot_20260901T080000Z.zip"
NEW_KEY = "snapshots/snapshot_20261001T080000Z.zip"


class FakePaginator:
    def __init__(self, keys: list[str]):
        self.keys = keys

    def paginate(self, Bucket: str, Prefix: str):
        yield {"Contents": [{"Key": key} for key in self.keys if key.startswith(Prefix)]}


class FakeS3Client:
    """Bucket holding one object per key, whose content is the key itself."""

    def __init__(self, keys: list[str]):
        self.keys = keys
        self.downloaded: list[str] = []

    def get_paginator(self, name: str) -> FakePaginator:
        assert name == "list_objects_v2"
        return FakePaginator(self.keys)

    def download_file(self, Bucket: str, Key: str, Filename: str) -> None:
        self.downloaded.append(Key)
        Path(Filename).write_text(Key)

    def delete_objects(self, Bucket: str, Delete: dict) -> dict:
        deleted = {obj["Key"] for obj in Delete["Objects"]}
        self.keys = [key for key in self.keys if key not in deleted]
        return {}


@pytest.fixture
def client() -> FakeS3Client:
    return FakeS3Client([OLD_KEY, "snapshots/other.txt", NEW_KEY])


def test_snapshot_key_from_a_file_name_or_a_key():
    assert snapshot_key_from_name("snapshot_20260901T080000Z.zip") == OLD_KEY
    assert snapshot_key_from_name(OLD_KEY) == OLD_KEY


@pytest.mark.parametrize("name", ["other.txt", "snapshot_2026.zip", "snapshots/other.zip"])
def test_invalid_snapshot_names_are_rejected(name):
    with pytest.raises(ValueError, match="Invalid snapshot name"):
        snapshot_key_from_name(name)


def test_download_a_chosen_snapshot_by_file_name(client, tmp_path):
    path = download_snapshot("bucket", "snapshot_20260901T080000Z.zip", tmp_path, client=client)
    assert path == tmp_path / "snapshot_20260901T080000Z.zip"
    assert path.read_text() == OLD_KEY


def test_download_a_missing_snapshot_raises(client, tmp_path):
    with pytest.raises(FileNotFoundError):
        download_snapshot("bucket", "snapshot_20250101T000000Z.zip", tmp_path, client=client)
    assert client.downloaded == []


def test_download_the_latest_snapshot(client, tmp_path):
    path = download_latest_snapshot("bucket", tmp_path / "new_dir", client=client)
    assert path.read_text() == NEW_KEY


def test_download_the_latest_snapshot_of_an_empty_bucket_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        download_latest_snapshot("bucket", tmp_path, client=FakeS3Client([]))


ARCHIVE_KEYS = KeyPattern(prefix="archives", stem="archive", suffix=".tar.gz")
ARCHIVE_KEYS_IN_BUCKET = [
    "archives/archive_20261001T080000Z.tar.gz",
    "archives/archive_20261003T080000Z.tar.gz",
    "archives/archive_20261002T080000Z.tar.gz",
]


@pytest.fixture
def mixed_client() -> FakeS3Client:
    """Bucket holding snapshots, archives and an unrelated object."""
    return FakeS3Client([OLD_KEY, *ARCHIVE_KEYS_IN_BUCKET, "archives/other.tar.gz", NEW_KEY])


def test_key_pattern_builds_and_parses_its_keys():
    timestamp = datetime(2026, 11, 12, 15, 0, 0, tzinfo=timezone.utc)
    key = ARCHIVE_KEYS.build_key(timestamp)
    assert key == "archives/archive_20261112T150000Z.tar.gz"
    assert ARCHIVE_KEYS.parse_timestamp(key) == timestamp


@pytest.mark.parametrize("key", [
    "archives/archive_20261112T150000Z.zip",
    "archives/archive_20261112T150000Z.tar.gz.bak",
    "snapshots/archive_20261112T150000Z.tar.gz",
    "archives/other_20261112T150000Z.tar.gz",
])
def test_key_pattern_rejects_other_keys(key):
    assert ARCHIVE_KEYS.parse_timestamp(key) is None


def test_list_keys_keeps_the_matching_keys_from_most_recent_to_oldest(mixed_client):
    assert list_keys("bucket", ARCHIVE_KEYS, client=mixed_client) == [
        "archives/archive_20261003T080000Z.tar.gz",
        "archives/archive_20261002T080000Z.tar.gz",
        "archives/archive_20261001T080000Z.tar.gz",
    ]


def test_delete_old_keys_keeps_the_most_recent_ones_only(mixed_client):
    deleted = delete_old_keys("bucket", ARCHIVE_KEYS, keep=1, client=mixed_client)
    assert deleted == [
        "archives/archive_20261002T080000Z.tar.gz",
        "archives/archive_20261001T080000Z.tar.gz",
    ]
    assert mixed_client.keys == [
        OLD_KEY, "archives/archive_20261003T080000Z.tar.gz", "archives/other.tar.gz", NEW_KEY
    ]


def test_delete_old_keys_rejects_keeping_nothing(mixed_client):
    with pytest.raises(ValueError):
        delete_old_keys("bucket", ARCHIVE_KEYS, keep=0, client=mixed_client)


def test_download_the_latest_object_of_a_pattern(mixed_client, tmp_path):
    path = download_latest("bucket", ARCHIVE_KEYS, tmp_path, client=mixed_client)
    assert path == tmp_path / "archive_20261003T080000Z.tar.gz"
    assert path.read_text() == "archives/archive_20261003T080000Z.tar.gz"
