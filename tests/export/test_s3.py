"""Unit tests of the snapshot functions of the S3 storage, with a fake S3 client."""

from pathlib import Path

import pytest

from access_it.export.s3 import (
    download_latest_snapshot, download_snapshot, snapshot_key_from_name
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


@pytest.fixture
def client() -> FakeS3Client:
    return FakeS3Client([OLD_KEY, "snapshots/other.txt", NEW_KEY])


def test_snapshot_key_from_a_file_name_or_a_key():
    assert snapshot_key_from_name("snapshot_20260901T080000Z.zip") == OLD_KEY
    assert snapshot_key_from_name(OLD_KEY) == OLD_KEY


@pytest.mark.parametrize("name", ["other.txt", "snapshot_2026.zip", "snapshots/other.zip"])
def test_invalid_snapshot_names_are_rejected(name):
    with pytest.raises(ValueError):
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
