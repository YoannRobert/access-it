"""Cached computations of the dashboard: the analytics functions run on the tables of a snapshot.

Each function takes the path of the snapshot as first argument: Streamlit caches its result
for this snapshot (st.cache_data), so that a new snapshot is computed again without clearing
the cache. See the analytics functions for the rules and the columns.
"""

import pandas as pd
import streamlit as st

from datetime import date
from pathlib import Path
from typing import Literal

from access_it.analytics.category_changes import compute_category_changes
from access_it.analytics.club_rankings import compute_club_rankings
from access_it.analytics.head_to_head import HeadToHead, compute_head_to_head
from access_it.analytics.promotion_points import compute_promotion_points, compute_promotion_rankings
from access_it.analytics.race_list import list_races
from access_it.analytics.race_summary import compute_race_summary, RaceSummary
from access_it.analytics.ranking_tools import get_region_departement_codes, get_regional_committee_id
from access_it.analytics.regional_rankings import compute_challenge_points, compute_regional_rankings
from access_it.analytics.rider_list import build_rider_list, filter_riders, get_filter_choices, RiderFilterChoices
from access_it.analytics.rider_profile import compute_rider_profile, RiderProfile
from access_it.analytics.season_stats import compute_season_summary, SeasonSummary
from access_it.common.regions import PAYS_DE_LA_LOIRE
from access_it.common.seasons import FIRST_SEASON

from data import get_snapshot_data, get_snapshot_reference_date
from settings import LAST_RACES, TOP_N, WINDOW_MONTHS


@st.cache_data
def get_season_summary(
    snapshot_path: Path,
    season: int,
    region: str,
    categories: tuple[str, ...],
    category_filter: Literal["race", "rider"],
    max_riders: int
) -> SeasonSummary:
    """Statistics of a season (see compute_season_summary)."""
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
    """Category changes of a season (see compute_category_changes)."""
    tables = get_snapshot_data(snapshot_path)
    return compute_category_changes(
        rider_categories=tables["rider_categories"], riders=tables["riders"],
        clubs=tables["clubs"], affiliations=tables["affiliations"],
        departemental_committees=tables["departemental_committees"],
        regional_committees=tables["regional_committees"],
        season=season, region=region, category=category
    )


@st.cache_data
def get_regional_rankings(
    snapshot_path: Path,
    season: int,
    region: str
) -> pd.DataFrame:
    """Regional challenge rankings of a season, all categories (see compute_regional_rankings)."""
    tables = get_snapshot_data(snapshot_path)
    return compute_regional_rankings(
        races=tables["races"], rankings=tables["rankings"], riders=tables["riders"],
        clubs=tables["clubs"], departemental_committees=tables["departemental_committees"],
        regional_committees=tables["regional_committees"], affiliations=tables["affiliations"],
        rider_categories=tables["rider_categories"], season=season, region=region
    )


@st.cache_data
def get_promotion_rankings(
    snapshot_path: Path,
    season: int
) -> pd.DataFrame:
    """National promotion rankings of a season, all categories (see compute_promotion_rankings)."""
    tables = get_snapshot_data(snapshot_path)
    return compute_promotion_rankings(
        races=tables["races"], rankings=tables["rankings"], riders=tables["riders"],
        clubs=tables["clubs"],
        departemental_committees=tables["departemental_committees"],
        regional_committees=tables["regional_committees"],
        affiliations=tables["affiliations"],
        rider_categories=tables["rider_categories"], season=season
    )


@st.cache_data
def get_club_rankings(
    snapshot_path: Path,
    season: int,
    region: str,
    categories: tuple[str, ...],
    category_filter: Literal["race", "rider"],
    max_clubs: int
) -> pd.DataFrame:
    """Club ranking of a season (see compute_club_rankings)."""
    tables = get_snapshot_data(snapshot_path)
    return compute_club_rankings(
        races=tables["races"], rankings=tables["rankings"],
        clubs=tables["clubs"], departements=tables["departements"],
        departemental_committees=tables["departemental_committees"],
        regional_committees=tables["regional_committees"],
        affiliations=tables["affiliations"],
        rider_categories=tables["rider_categories"],
        season=season, region=region, max_clubs=max_clubs,
        categories=categories, category_filter=category_filter,
    )


@st.cache_data
def get_rider_list(snapshot_path: Path) -> pd.DataFrame:
    """Riders on the reference date of the snapshot (see build_rider_list)."""
    reference_date = get_snapshot_reference_date(snapshot_path)
    tables = get_snapshot_data(snapshot_path)
    return build_rider_list(
        races=tables["races"], rankings=tables["rankings"],
        riders=tables["riders"], clubs=tables["clubs"],
        affiliations=tables["affiliations"],
        rider_categories=tables["rider_categories"],
        departements=tables["departements"],
        departemental_committees=tables["departemental_committees"],
        regional_committees=tables["regional_committees"],
        reference_date=reference_date,
    )


@st.cache_data
def get_all_promotion_points(snapshot_path: Path) -> pd.DataFrame:
    """Promotion points, race by race, of every season from FIRST_SEASON to the year of the
    reference date (see compute_promotion_points).
    """
    tables = get_snapshot_data(snapshot_path)
    reference_date = get_snapshot_reference_date(snapshot_path)
    return pd.concat(
        objs=[
            compute_promotion_points(
                races=tables["races"],
                rankings=tables["rankings"],
                affiliations=tables["affiliations"],
                rider_categories=tables["rider_categories"],
                season=season
            )
            for season in range(FIRST_SEASON, reference_date.year + 1)
        ],
        ignore_index=True
    )


@st.cache_data
def get_all_challenge_points(snapshot_path: Path) -> pd.DataFrame:
    """Points of the challenge of the Pays de la Loire, race by race, of every season from
    FIRST_SEASON to the year of the reference date (see compute_challenge_points).
    """
    tables = get_snapshot_data(snapshot_path)
    reference_date = get_snapshot_reference_date(snapshot_path)
    return pd.concat(
        objs=[
            compute_challenge_points(
                races=tables["races"],
                rankings=tables["rankings"],
                clubs=tables["clubs"],
                departemental_committees=tables["departemental_committees"],
                regional_committees=tables["regional_committees"],
                affiliations=tables["affiliations"],
                rider_categories=tables["rider_categories"],
                season=season,
                region=PAYS_DE_LA_LOIRE
            )
            for season in range(FIRST_SEASON, reference_date.year + 1)
        ],
        ignore_index=True
    )


@st.cache_data(max_entries=500)
def search_riders(
    snapshot_path: Path,
    last_name: str | None,
    first_name: str | None,
    regions: tuple[str, ...],
    departement_code: str | None,
    club_id: str | None
) -> tuple[pd.DataFrame, RiderFilterChoices]:
    """Riders kept by the filters, and the choices of each filter (see filter_riders and
    get_filter_choices); regions is a tuple, empty for no region filter.
    """
    rider_list = get_rider_list(snapshot_path)
    return (
        filter_riders(
            rider_list=rider_list,
            last_name=last_name,
            first_name=first_name,
            regions=regions,
            departement_code=departement_code,
            club_id=club_id
        ),
        get_filter_choices(
            rider_list=rider_list,
            last_name=last_name,
            first_name=first_name,
            regions=regions,
            departement_code=departement_code,
            club_id=club_id
        )
    )


@st.cache_data(max_entries=200)
def get_rider_profile(
    snapshot_path: Path,
    rider_id: str
) -> RiderProfile:
    """Profile of a rider, with the challenge of the Pays de la Loire and the recent form of
    settings.py (see compute_rider_profile).
    """
    tables = get_snapshot_data(snapshot_path)
    return compute_rider_profile(
        races=tables["races"],
        rankings=tables["rankings"],
        riders=tables["riders"],
        clubs=tables["clubs"],
        departemental_committees=tables["departemental_committees"],
        regional_committees=tables["regional_committees"],
        affiliations=tables["affiliations"],
        rider_categories=tables["rider_categories"],
        promotion_points=get_all_promotion_points(snapshot_path),
        challenge_points=get_all_challenge_points(snapshot_path),
        rider_id=rider_id,
        reference_date=get_snapshot_reference_date(snapshot_path),
        region=PAYS_DE_LA_LOIRE,
        top_n=TOP_N,
        last_races=LAST_RACES,
        window_months=WINDOW_MONTHS
    )


@st.cache_data(max_entries=200)
def get_head_to_head(
    snapshot_path: Path,
    rider_id: str,
    opponent_id: str,
    season: int | None
) -> HeadToHead:
    """Head to head of two riders, on one season or on all of them if season is None
    (see compute_head_to_head).
    """
    tables = get_snapshot_data(snapshot_path)
    return compute_head_to_head(
        races=tables["races"],
        rankings=tables["rankings"],
        riders=tables["riders"],
        clubs=tables["clubs"],
        affiliations=tables["affiliations"],
        rider_categories=tables["rider_categories"],
        rider_id=rider_id,
        opponent_id=opponent_id,
        reference_date=get_snapshot_reference_date(snapshot_path),
        season=season
    )


@st.cache_data
def get_region_departements(
    snapshot_path: Path,
    region: str
) -> pd.DataFrame:
    """Departements of a region: departement_code and departement_name, sorted by code."""
    tables = get_snapshot_data(snapshot_path)
    regional_committee_id = get_regional_committee_id(tables["regional_committees"], region)
    departement_codes = get_region_departement_codes(tables["departemental_committees"], regional_committee_id)
    departements = pd.DataFrame(departement_codes)
    departements = (
        departements
        .merge(tables["departements"], on="departement_code")
        [["departement_code", "departement_name"]]
    )
    return departements.sort_values(by="departement_code").reset_index(drop=True)


@st.cache_data(max_entries=200)
def get_race_list(
    snapshot_path: Path,
    start_date: date,
    end_date: date,
    region: str,
    departement_codes: tuple[str, ...] | None,
    categories: tuple[str, ...]
) -> pd.DataFrame:
    """Races of a region over a period, both dates included (see list_races); departement_codes
    is None for every departement of the region.
    """
    tables = get_snapshot_data(snapshot_path)
    return list_races(
        races=tables["races"],
        rankings=tables["rankings"],
        departements=tables["departements"],
        departemental_committees=tables["departemental_committees"],
        regional_committees=tables["regional_committees"],
        start_date=pd.Timestamp(start_date),
        end_date=pd.Timestamp(end_date),
        region=region,
        departement_codes=departement_codes,
        categories=categories
    )


@st.cache_data(max_entries=200)
def get_race_summary(snapshot_path: Path, race_id: str) -> RaceSummary:
    """Header and ranking of a race (see compute_race_summary)."""
    tables = get_snapshot_data(snapshot_path)
    return compute_race_summary(
        races=tables["races"],
        rankings=tables["rankings"],
        riders=tables["riders"],
        clubs=tables["clubs"],
        departements=tables["departements"],
        departemental_committees=tables["departemental_committees"],
        regional_committees=tables["regional_committees"],
        affiliations=tables["affiliations"],
        rider_categories=tables["rider_categories"],
        race_id=race_id
    )
