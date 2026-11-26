"""Unit tests of the snapshot and forecasts of the dashboard and of their checks
(app/dashboard/data.py)."""

import pandas as pd
import pytest

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

import data
from access_it.export.upcoming import UpcomingFiles
from data import (
    PARIS, SnapshotHolder, check_for_new_snapshot, get_forecast_data, get_next_check_time,
    update_forecasts
)


def paris(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    """Time of day in Paris."""
    return datetime(year, month, day, hour, minute, tzinfo=PARIS)


@pytest.mark.parametrize("now, expected", [
    (paris(2026, 11, 10, 3, 15), paris(2026, 11, 10, 7)),
    (paris(2026, 11, 10, 8, 59), paris(2026, 11, 10, 9)),
    (paris(2026, 11, 10, 9), paris(2026, 11, 10, 11)),
    (paris(2026, 11, 10, 23, 1), paris(2026, 11, 11, 7)),
    (paris(2026, 11, 10, 0), paris(2026, 11, 10, 7)),
    (paris(2026, 1, 31, 23, 30), paris(2026, 2, 1, 7)),
    (paris(2026, 12, 31, 23, 59), paris(2027, 1, 1, 7)),
], ids=[
    "before_7", "just_before_9", "on_a_check_time", "after_23",
    "at_midnight", "end_of_month", "end_of_year",
])
def test_next_check_time_is_the_next_fixed_hour(now, expected):
    assert get_next_check_time(now) == expected


@pytest.mark.parametrize("now, expected, offset_hours", [
    (paris(2026, 3, 29, 1), paris(2026, 3, 29, 7), 2),
    (paris(2026, 10, 25, 1), paris(2026, 10, 25, 7), 1),
], ids=["summer_time", "winter_time"])
def test_next_check_time_keeps_the_paris_time_on_a_clock_change(now, expected, offset_hours):
    next_check_time = get_next_check_time(now)
    assert next_check_time == expected
    assert next_check_time.utcoffset().total_seconds() == offset_hours * 3600


@pytest.fixture
def s3(monkeypatch):
    """Replace the S3 calls of data.py; record the downloaded keys.

    The forecasts are fake.runs, or fake.error is raised if set.
    """
    fake = SimpleNamespace(keys=[], downloaded=[], runs=[], error=None)

    def download_snapshot(bucket: str, key: str, dest_dir: Path) -> Path:
        fake.downloaded.append(key)
        if fake.error is not None:
            raise fake.error
        return dest_dir / Path(key).name

    def download_upcoming_entries_and_forecasts(bucket: str, dest_dir: Path) -> list:
        if fake.error is not None:
            raise fake.error
        return fake.runs

    monkeypatch.setattr(data, "get_settings", lambda: SimpleNamespace(s3_bucket="bucket"))
    monkeypatch.setattr(data, "list_snapshot_keys", lambda bucket: fake.keys)
    monkeypatch.setattr(data, "download_snapshot", download_snapshot)
    monkeypatch.setattr(
        data, "download_upcoming_entries_and_forecasts", download_upcoming_entries_and_forecasts
    )
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


def test_new_snapshot_deletes_the_previous_one(s3, tmp_path):
    previous = tmp_path / CURRENT.name
    previous.write_bytes(b"snapshot")
    s3.keys = ["snapshots/snapshot_20261110T120000Z.zip"]
    holder = SnapshotHolder(previous)
    check_for_new_snapshot(holder)
    assert holder.path.name == "snapshot_20261110T120000Z.zip"
    assert not previous.exists()


def test_failed_download_of_a_snapshot_keeps_the_previous_one(s3, tmp_path):
    previous = tmp_path / CURRENT.name
    previous.write_bytes(b"snapshot")
    s3.keys = ["snapshots/snapshot_20261110T120000Z.zip"]
    s3.error = ConnectionError("Download interrupted")
    holder = SnapshotHolder(previous)
    with pytest.raises(ConnectionError):
        check_for_new_snapshot(holder)
    assert holder.path == previous
    assert previous.exists()


# Forecasts

RUN_TIME = datetime(2026, 3, 13, tzinfo=timezone.utc)
FILES = UpcomingFiles(RUN_TIME, Path("forecasts.parquet"), Path("entries.parquet"))


def test_update_of_the_forecasts_shows_those_of_the_bucket(s3, caplog):
    s3.runs = [FILES, FILES]
    holder = SnapshotHolder(CURRENT)
    with caplog.at_level("INFO"):
        update_forecasts(holder)
    assert holder.upcoming_files == (FILES, FILES)
    assert "Forecasts available: 2 runs" in caplog.text


def test_failed_forecasts_at_the_start_keep_the_snapshot(s3, monkeypatch, caplog):
    s3.error = ConnectionError("Bucket unreachable")
    monkeypatch.setattr(data, "download_latest_snapshot", lambda bucket, dest_dir: CURRENT)
    monkeypatch.setattr(
        data.threading, "Thread", lambda **kwargs: SimpleNamespace(start=lambda: None)
    )
    data.get_snapshot_holder.clear()
    try:
        holder = data.get_snapshot_holder()
    finally:
        data.get_snapshot_holder.clear()
    assert holder.path == CURRENT
    assert holder.upcoming_files is None
    assert "Failed to download the forecasts" in caplog.text


def write_run(tmp_path: Path, day: int, with_entries: bool) -> UpcomingFiles:
    """Files of a run on day `day` of March 2026, with one forecast race of one rider."""
    timestamp = datetime(2026, 3, day, tzinfo=timezone.utc)
    forecasts_path = tmp_path / f"forecasts_{day}.parquet"
    entries_path = tmp_path / f"entries_{day}.parquet"
    pd.DataFrame({"race_id": [f"vpc-{day}-1"], "rider_id": ["r1"], "p_win": [0.5]}).to_parquet(
        forecasts_path
    )
    pd.DataFrame({"race_id": [f"vpc-{day}-1"], "rider_id": ["r1"]}).to_parquet(entries_path)
    return UpcomingFiles(timestamp, forecasts_path, entries_path if with_entries else None)


def test_forecast_data_has_the_run_time_of_each_row(tmp_path):
    runs = (write_run(tmp_path, 13, with_entries=True), write_run(tmp_path, 6, with_entries=False))
    forecasts, entries = get_forecast_data(runs)
    assert forecasts["race_id"].tolist() == ["vpc-13-1", "vpc-6-1"]
    assert forecasts["run_time"].tolist() == [run.timestamp for run in runs]
    assert entries["race_id"].tolist() == ["vpc-13-1"]
    assert entries["run_time"].tolist() == [runs[0].timestamp]


def forecasts_app() -> None:
    """App loading the forecasts, then writing their number of rows."""
    import streamlit as st

    from data import load_forecasts

    forecasts, _ = load_forecasts()
    st.write(f"{len(forecasts)} forecasts")


@pytest.mark.parametrize("upcoming_files, element, message", [
    (None, "error", data.FORECASTS_ERROR),
    ((), "info", "Aucune prévision n'est disponible pour le moment."),
], ids=["unavailable", "no_forecast"])
def test_load_forecasts_shows_a_message_and_stops(monkeypatch, upcoming_files, element, message):
    monkeypatch.setattr(
        data, "get_snapshot_holder", lambda: SnapshotHolder(CURRENT, upcoming_files)
    )
    app = AppTest.from_function(forecasts_app).run()
    assert not app.exception
    assert [item.value for item in app.get(element)] == [message]
    assert not app.markdown


def test_unreadable_forecasts_show_the_error_message(monkeypatch, tmp_path):
    forecasts_path = tmp_path / "forecasts.parquet"
    forecasts_path.write_bytes(b"not a Parquet file")
    files = (UpcomingFiles(RUN_TIME, forecasts_path, None),)
    monkeypatch.setattr(data, "get_snapshot_holder", lambda: SnapshotHolder(CURRENT, files))
    app = AppTest.from_function(forecasts_app).run()
    assert not app.exception
    assert [item.value for item in app.error] == [data.FORECASTS_ERROR]
