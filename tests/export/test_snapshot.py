"""Unit tests of the snapshot archive: writing then reading."""

import zipfile

import pandas as pd
import pytest

from access_it.export import snapshot as snapshot_module
from access_it.export.snapshot import build_snapshot_zip, export_snapshot, read_snapshot_zip


def test_snapshot_round_trip(tmp_path):
    tables = {
        "riders": pd.DataFrame({"rider_id": ["a", "b"], "uci_id": ["1", None]}),
        "races": pd.DataFrame({"race_id": ["r"], "season": [2026]}),
        "empty": pd.DataFrame({"x": pd.Series([], dtype="int64")}),
    }
    zip_path = build_snapshot_zip(tables, tmp_path / "snapshot.zip")
    read = read_snapshot_zip(zip_path)
    assert read.keys() == tables.keys()
    for name, df in tables.items():
        pd.testing.assert_frame_equal(read[name], df)


def test_unexpected_file_in_the_snapshot_raises(tmp_path):
    zip_path = tmp_path / "snapshot.zip"
    with zipfile.ZipFile(zip_path, mode="w") as zf:
        zf.writestr("notes.txt", "x")
    with pytest.raises(ValueError):
        read_snapshot_zip(zip_path)


class FakeS3Client:
    """Bucket holding the given keys; uploads add keys, deletions remove them."""

    def __init__(self, keys: list[str]):
        self.keys = list(keys)
        self.uploaded: dict[str, bytes] = {}

    def upload_file(self, Filename: str, Bucket: str, Key: str) -> None:
        with open(Filename, "rb") as f:
            self.uploaded[Key] = f.read()
        self.keys.append(Key)

    def get_paginator(self, name: str):
        keys = self.keys

        class Paginator:
            def paginate(self, Bucket: str, Prefix: str):
                yield {"Contents": [{"Key": key} for key in keys if key.startswith(Prefix)]}

        return Paginator()

    def delete_objects(self, Bucket: str, Delete: dict) -> dict:
        for obj in Delete["Objects"]:
            self.keys.remove(obj["Key"])
        return {}


def test_export_snapshot_uploads_then_keeps_the_most_recent(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot_module, "SNAPSHOTS_DIR", tmp_path / "snapshots")
    old_keys = ["snapshots/snapshot_20250101T000000Z.zip", "snapshots/snapshot_20250201T000000Z.zip"]
    client = FakeS3Client(old_keys)
    tables = {"riders": pd.DataFrame({"rider_id": ["a"]})}

    s3_uri, deleted_keys = export_snapshot(tables, bucket="bucket", keep=2, client=client)

    (new_key,) = client.uploaded
    assert s3_uri == f"s3://bucket/{new_key}"
    assert deleted_keys == [old_keys[0]]
    assert client.keys == [old_keys[1], new_key]
    zip_path = tmp_path / "check.zip"
    zip_path.write_bytes(client.uploaded[new_key])
    pd.testing.assert_frame_equal(read_snapshot_zip(zip_path)["riders"], tables["riders"])
    assert list((tmp_path / "snapshots").iterdir()) == []
