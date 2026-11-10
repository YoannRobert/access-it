"""Unit tests of the fixed-time checks of the snapshot (app/dashboard/data.py)."""

import pytest

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import data
from data import PARIS, SnapshotHolder, check_for_new_snapshot, get_next_check_time


def paris(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    """Time of day in Paris."""
    return datetime(year, month, day, hour, minute, tzinfo=PARIS)


@pytest.mark.parametrize("now, expected", [
    (paris(2026, 11, 10, 3, 15), paris(2026, 11, 10, 6)),
    (paris(2026, 11, 10, 11, 59), paris(2026, 11, 10, 12)),
    (paris(2026, 11, 10, 12), paris(2026, 11, 10, 18)),
    (paris(2026, 11, 10, 18, 1), paris(2026, 11, 11, 0)),
    (paris(2026, 11, 10, 0), paris(2026, 11, 10, 6)),
    (paris(2026, 1, 31, 20), paris(2026, 2, 1, 0)),
    (paris(2026, 12, 31, 23, 59), paris(2027, 1, 1, 0)),
], ids=[
    "between_midnight_and_6", "just_before_noon", "on_a_check_time", "after_18",
    "at_midnight", "end_of_month", "end_of_year",
])
def test_next_check_time_is_the_next_fixed_hour(now, expected):
    assert get_next_check_time(now) == expected


@pytest.mark.parametrize("now, expected, offset_hours", [
    (paris(2026, 3, 29, 1), paris(2026, 3, 29, 6), 2),
    (paris(2026, 10, 25, 1), paris(2026, 10, 25, 6), 1),
], ids=["summer_time", "winter_time"])
def test_next_check_time_keeps_the_paris_time_on_a_clock_change(now, expected, offset_hours):
    next_check_time = get_next_check_time(now)
    assert next_check_time == expected
    assert next_check_time.utcoffset().total_seconds() == offset_hours * 3600


@pytest.fixture
def s3(monkeypatch):
    """Replace the S3 calls of data.py; record the downloaded keys."""
    fake = SimpleNamespace(keys=[], downloaded=[])

    def download_snapshot(bucket: str, key: str, dest_dir: Path) -> Path:
        fake.downloaded.append(key)
        return dest_dir / Path(key).name

    monkeypatch.setattr(data, "get_settings", lambda: SimpleNamespace(s3_bucket="bucket"))
    monkeypatch.setattr(data, "list_snapshot_keys", lambda bucket: fake.keys)
    monkeypatch.setattr(data, "download_snapshot", download_snapshot)
    return fake


CURRENT = Path("/cache/snapshots/snapshot_20261110T060000Z.zip")


def test_no_snapshot_keeps_the_current_one(s3, caplog):
    holder = SnapshotHolder(CURRENT)
    with caplog.at_level("INFO"):
        check_for_new_snapshot(holder)
    assert holder.path == CURRENT
    assert s3.downloaded == []
    assert "No snapshot available" in caplog.text


def test_same_snapshot_is_not_downloaded(s3, caplog):
    s3.keys = ["snapshots/snapshot_20261110T060000Z.zip", "snapshots/snapshot_20261109T060000Z.zip"]
    holder = SnapshotHolder(CURRENT)
    with caplog.at_level("INFO"):
        check_for_new_snapshot(holder)
    assert holder.path == CURRENT
    assert s3.downloaded == []
    assert "No new snapshot available" in caplog.text


def test_new_snapshot_is_downloaded_and_shown(s3, caplog):
    s3.keys = ["snapshots/snapshot_20261110T120000Z.zip", "snapshots/snapshot_20261110T060000Z.zip"]
    holder = SnapshotHolder(CURRENT)
    with caplog.at_level("INFO"):
        check_for_new_snapshot(holder)
    assert s3.downloaded == ["snapshots/snapshot_20261110T120000Z.zip"]
    assert holder.path.name == "snapshot_20261110T120000Z.zip"
    assert "New snapshot downloaded" in caplog.text
