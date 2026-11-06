import pandas as pd
import streamlit as st

from pathlib import Path
from typing import Literal

from access_it.analytics.category_changes import compute_category_changes
from access_it.analytics.season_stats import compute_season_summary, SeasonSummary
from data import get_snapshot_data


@st.cache_data
def get_season_summary(
        snapshot_path: Path,
        season: int,
        region: str,
        categories: tuple[str, ...],
        category_filter: Literal["race", "rider"],
        max_riders: int
) -> SeasonSummary:
    tables = get_snapshot_data(snapshot_path)
    return compute_season_summary(
        races=tables["races"], rankings=tables["rankings"], riders=tables["riders"],
        clubs=tables["clubs"], departements=tables["departements"],
        departemental_committees=tables["departemental_committees"],
        regional_committees=tables["regional_committees"],
        affiliations=tables["affiliations"],
        rider_categories=tables["rider_categories"],
        season=season, region=region, categories=categories,
        category_filter=category_filter, max_riders=max_riders
    )


@st.cache_data
def get_category_changes(
        snapshot_path: Path,
        season: int,
        region: str | None,
        category: str | None
) -> pd.DataFrame:
    tables = get_snapshot_data(snapshot_path)
    return compute_category_changes(
        rider_categories=tables["rider_categories"], riders=tables["riders"],
        clubs=tables["clubs"], affiliations=tables["affiliations"],
        departemental_committees=tables["departemental_committees"],
        regional_committees=tables["regional_committees"],
        season=season, region=region, category=category
    )
