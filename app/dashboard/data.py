"""Snapshot of the database and forecasts shown by the dashboard: download, reading and checks.

The latest snapshot and the forecasts of the bucket (with their entries) are downloaded at the
first display after the start; a background thread then checks the bucket at CHECK_HOURS
(Paris time), downloads a snapshot only if it changed, then deletes the replaced one, and
downloads the missing forecasts. A failure on the forecasts is logged and never stops the
snapshot. No action of a visitor triggers a download.
"""

import logging
import pandas as pd
import streamlit as st
import threading
import time

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from access_it.analytics.ranking_tools import get_reference_date
from access_it.common.regions import PAYS_DE_LA_LOIRE
from access_it.config import get_settings
from access_it.etl.extract.cache import SNAPSHOTS_DIR, UPCOMING_DIR
from access_it.export.s3 import download_latest_snapshot, download_snapshot, list_snapshot_keys
from access_it.export.snapshot import read_snapshot_zip
from access_it.export.upcoming import UpcomingFiles, download_upcoming_entries_and_forecasts


CHECK_HOURS = (7, 9, 11, 13, 15, 17, 19, 21, 23)
PARIS = ZoneInfo("Europe/Paris")
DEFAULT_REGION = PAYS_DE_LA_LOIRE
FORECASTS_ERROR = "Les prévisions sont indisponibles pour le moment. Réessayez plus tard."

logger = logging.getLogger(__name__)


@dataclass
class SnapshotHolder:
    """Snapshot and forecasts shown, shared by the sessions and replaced by the checking thread.

    upcoming_files is None while the forecasts could not be downloaded, and empty if the bucket
    holds no forecast.
    """
    path: Path
    upcoming_files: tuple[UpcomingFiles, ...] | None = None


@st.cache_resource
def get_snapshot_holder() -> SnapshotHolder:
    """Download the latest snapshot and the forecasts, then start the checking thread, once.

    If the download of the snapshot fails, nothing is cached and the next display tries again.
    If the download of the forecasts fails, it is logged and the forecasts stay unavailable
    until a check succeeds.
    """
    settings = get_settings()
    s3_bucket = settings.s3_bucket
    snapshot_path = download_latest_snapshot(s3_bucket, SNAPSHOTS_DIR)
    snapshot_holder = SnapshotHolder(snapshot_path)
    try:
        update_forecasts(snapshot_holder)
    except Exception:
        logger.exception("Failed to download the forecasts")
    threading.Thread(
        target=watch_snapshots,
        args=(snapshot_holder,),
        daemon=True,
        name="snapshot-watcher"
    ).start()
    return snapshot_holder


@st.cache_data
def get_snapshot_data(snapshot_path: Path) -> dict[str, pd.DataFrame]:
    """Tables of a snapshot archive, by table name."""
    return read_snapshot_zip(snapshot_path)


@st.cache_data
def get_forecast_data(
        upcoming_files: tuple[UpcomingFiles, ...]
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Forecasts and entries of all the runs, each row with the run_time of its run.

    Without any file of entries, the entries are an empty table with the columns of the
    forecasts.
    """
    forecasts = pd.concat(
        [pd.read_parquet(files.forecasts_path).assign(run_time=files.timestamp)
         for files in upcoming_files],
        ignore_index=True,
    )
    entries_frames = [
        pd.read_parquet(files.entries_path).assign(run_time=files.timestamp)
        for files in upcoming_files if files.entries_path is not None
    ]
    entries = pd.concat(entries_frames, ignore_index=True) if entries_frames else forecasts.iloc[:0]
    return forecasts, entries


def load_snapshot() -> tuple[Path, dict[str, pd.DataFrame]]:
    """Path and tables of the snapshot shown.

    If they cannot be loaded, the error is logged with its trace, the visitor sees a message
    and the page stops.
    """
    try:
        snapshot_holder = get_snapshot_holder()
        snapshot_path = snapshot_holder.path
        tables = get_snapshot_data(snapshot_path)
    except Exception:
        logger.exception("Failed to load the snapshot")
        st.error("Les données sont indisponibles pour le moment. Réessayez plus tard.")
        st.stop()
    return snapshot_path, tables


def load_forecasts() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Forecasts and entries of all the runs (see get_forecast_data).

    If the forecasts are unavailable or cannot be read, the visitor sees an error message; if
    the bucket holds no forecast, an information message; the page stops in both cases.
    """
    upcoming_files = get_snapshot_holder().upcoming_files
    if upcoming_files is None:
        st.error(FORECASTS_ERROR)
        st.stop()
    if not upcoming_files:
        st.info("Aucune prévision n'est disponible pour le moment.")
        st.stop()
    try:
        return get_forecast_data(upcoming_files)
    except Exception:
        logger.exception("Failed to read the forecasts")
        st.error(FORECASTS_ERROR)
        st.stop()


def get_next_check_time(now: datetime) -> datetime:
    """Next check time: the next hour of CHECK_HOURS, or the first of them on the next day.

    Args:
        now: Current time, in Paris time.

    Returns:
        The first check time strictly after now, in the time zone of now.
    """
    next_check_time = (now + timedelta(days=1)).replace(
        hour=CHECK_HOURS[0], minute=0, second=0, microsecond=0
    )
    for hour in CHECK_HOURS:
        check_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if check_time > now:
            next_check_time = check_time
            break
    return next_check_time


def check_for_new_snapshot(holder: SnapshotHolder) -> None:
    """Download the latest snapshot of the bucket if it is not the one shown, and show it.

    The previous snapshot is then deleted from the disk.

    Args:
        holder: Snapshot shown, updated when a new one is downloaded.
    """
    bucket = get_settings().s3_bucket
    keys = list_snapshot_keys(bucket)
    if not keys:
        logger.info("No snapshot available")
        return
    if Path(keys[0]).name == holder.path.name:
        logger.info("No new snapshot available")
        return
    new_snapshot_path = download_snapshot(bucket, keys[0], SNAPSHOTS_DIR)
    logger.info("New snapshot downloaded: %s", new_snapshot_path)
    previous_snapshot_path = holder.path
    holder.path = new_snapshot_path
    previous_snapshot_path.unlink(missing_ok=True)
    logger.info("Previous snapshot deleted: %s", previous_snapshot_path)


def update_forecasts(holder: SnapshotHolder) -> None:
    """Download the forecasts of the bucket missing from UPCOMING_DIR, and show all of them.

    Errors are not caught: the forecasts shown are kept by the callers.

    Args:
        holder: Forecasts shown, replaced by those of the bucket.
    """
    bucket = get_settings().s3_bucket
    holder.upcoming_files = tuple(download_upcoming_entries_and_forecasts(bucket, UPCOMING_DIR))
    logger.info("Forecasts available: %d runs", len(holder.upcoming_files))


def watch_snapshots(snapshot_holder: SnapshotHolder) -> None:
    """Loop of the checking thread: wait for the next check time, then check the bucket.

    The snapshot then the forecasts are checked; a failed check is logged with its trace, and
    the snapshot or forecasts shown are kept until the next check.
    """
    while True:
        now = datetime.now(PARIS)
        waiting_time = (get_next_check_time(now) - now).total_seconds()
        time.sleep(waiting_time)
        try:
            check_for_new_snapshot(snapshot_holder)
        except Exception:
            logger.exception("Failed to check for a new snapshot")
        try:
            update_forecasts(snapshot_holder)
        except Exception:
            logger.exception("Failed to check for new forecasts")


@st.cache_data
def get_snapshot_reference_date(snapshot_path: Path) -> pd.Timestamp:
    """Reference date of a snapshot: the day after its last race (see get_reference_date)."""
    tables = get_snapshot_data(snapshot_path)
    return get_reference_date(tables["races"])
