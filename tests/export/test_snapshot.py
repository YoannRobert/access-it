"""Unit tests of the snapshot archive: writing then reading."""

import zipfile

import pandas as pd
import pytest

from access_it.export.snapshot import build_snapshot_zip, read_snapshot_zip


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
