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
    path: Path


@st.cache_resource
def get_snapshot_holder() -> SnapshotHolder:
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
    return read_snapshot_zip(snapshot_path)


def load_snapshot() -> tuple[Path, dict[str, pd.DataFrame]]:
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
    next_check_time = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    for hour in CHECK_HOURS:
        check_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if check_time > now:
            next_check_time = check_time
            break
    return next_check_time


def check_for_new_snapshot(holder: SnapshotHolder) -> None:
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
    tables = get_snapshot_data(snapshot_path)
    return get_reference_date(tables["races"])
