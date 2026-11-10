"""Snapshot of the database shown by the dashboard: download, reading and fixed-time checks.

The latest snapshot is downloaded at the first display after the start; a background thread
then checks the bucket at CHECK_HOURS (Paris time) and downloads a snapshot only if it
changed. No action of a visitor triggers a download.
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
from access_it.etl.extract.cache import SNAPSHOTS_DIR
from access_it.export.s3 import download_latest_snapshot, download_snapshot, list_snapshot_keys
from access_it.export.snapshot import read_snapshot_zip


CHECK_HOURS = (0, 6, 12, 18)
PARIS = ZoneInfo("Europe/Paris")
DEFAULT_REGION = PAYS_DE_LA_LOIRE

logger = logging.getLogger(__name__)


@dataclass
class SnapshotHolder:
    """Path of the snapshot shown, shared by the sessions and replaced by the checking thread."""
    path: Path


@st.cache_resource
def get_snapshot_holder() -> SnapshotHolder:
    """Download the latest snapshot and start the checking thread, once per process.

    If the download fails, nothing is cached and the next display tries again.
    """
    settings = get_settings()
    s3_bucket = settings.s3_bucket
    snapshot_path = download_latest_snapshot(s3_bucket, SNAPSHOTS_DIR)
    snapshot_holder = SnapshotHolder(snapshot_path)
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


def get_next_check_time(now: datetime) -> datetime:
    """Next check time: the next hour of CHECK_HOURS, or midnight of the next day.

    Args:
        now: Current time, in Paris time.

    Returns:
        The first check time strictly after now, in the time zone of now.
    """
    next_check_time = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    for hour in CHECK_HOURS:
        check_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if check_time > now:
            next_check_time = check_time
            break
    return next_check_time


def check_for_new_snapshot(holder: SnapshotHolder) -> None:
    """Download the latest snapshot of the bucket if it is not the one shown, and show it.

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
    holder.path = new_snapshot_path


def watch_snapshots(snapshot_holder: SnapshotHolder) -> None:
    """Loop of the checking thread: wait for the next check time, then check the bucket.

    A failed check is logged with its trace; the snapshot shown is kept until the next check.
    """
    while True:
        now = datetime.now(PARIS)
        waiting_time = (get_next_check_time(now) - now).total_seconds()
        time.sleep(waiting_time)
        try:
            check_for_new_snapshot(snapshot_holder)
        except Exception:
            logger.exception("Failed to check for a new snapshot")


@st.cache_data
def get_snapshot_reference_date(snapshot_path: Path) -> pd.Timestamp:
    """Reference date of a snapshot: the day after its last race (see get_reference_date)."""
    tables = get_snapshot_data(snapshot_path)
    return get_reference_date(tables["races"])
