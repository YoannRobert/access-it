import logging
import pandas as pd
import streamlit as st

from pathlib import Path

from access_it.config import get_settings
from access_it.etl.extract.cache import SNAPSHOTS_DIR
from access_it.export.s3 import download_latest_snapshot
from access_it.export.snapshot import read_snapshot_zip

logger = logging.getLogger(__name__)


@st.cache_resource
def download_snapshot_data() -> Path:
    settings = get_settings()
    s3_bucket = settings.s3_bucket
    snapshot_path = download_latest_snapshot(s3_bucket, SNAPSHOTS_DIR)
    return snapshot_path


@st.cache_data
def get_snapshot_data(snapshot_path: Path) -> dict[str, pd.DataFrame]:
    return read_snapshot_zip(snapshot_path)


def load_snapshot() -> tuple[Path, dict[str, pd.DataFrame]]:
    try:
        snapshot_path = download_snapshot_data()
        tables = get_snapshot_data(snapshot_path)
    except Exception:
        logger.exception("Failed to load the snapshot")
        st.error("Les données sont indisponibles pour le moment. Réessayez plus tard.")
        st.stop()
    return snapshot_path, tables
