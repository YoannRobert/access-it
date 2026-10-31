"""Statistics of a season of Access races held in a region.

Rules:

- the races are those of the season held in the departements of the region
  (the place of the race, not the region of the riders); only the regions of
  COVERED_REGIONS are accepted; a race without any ranked rider (e.g. a
  cancelled race) is not counted;
- the categories of every race of the season and the region must be one of
  the contiguous CATEGORY_COMBINATIONS, and so must the requested categories
  (given in any order, duplicates removed);
- category_filter "race" keeps the races having at least one of the
  requested categories, with all their ranked riders; "rider" keeps the
  results of the riders whose category on the race date is requested, and a
  race counts as soon as one of these riders is ranked in it;
- the rank is the absolute finish rank; the tops are inclusive (a win also
  counts in every top) and tied riders all count;
- the most titled riders are sorted by wins, then tops 3, 5, 10 and 20, then
  last name, first name and rider_id; riders tied on every count share the
  rank; riders without a top 20 are left out and the list is cut at
  max_riders riders;
- the club of a most titled rider is the first known club of the season (see
  select_club), UNKNOWN_CLUB if none; his category is the highest one on the
  dates of the results kept, UNKNOWN_CATEGORY if unknown on all of them.

The computation is free of any Streamlit dependency.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import pandas as pd

from access_it.analytics.labels import UNKNOWN_CATEGORY, UNKNOWN_CLUB
from access_it.analytics.ranking_tools import (
    CATEGORIES, CATEGORY_COMBINATIONS, TOP_THRESHOLDS, add_category_on_race_date,
    add_value_on_race_date, check_race_categories, count_wins_and_tops,
    filter_results_by_categories, get_region_races, get_regional_committee_id, select_club,
    to_datetime
)
from access_it.common.regions import check_covered_region
from access_it.common.seasons import FIRST_SEASON

SEASON_RESULT_COLUMNS = [
    "race_id", "race_date", "departement_code", "categories", "rider_id", "finish_rank"
]
RACES_BY_MONTH_COLUMNS = ["month", "nb_races"]
RACES_BY_DEPARTEMENT_COLUMNS = ["departement_code", "departement_name", "nb_races"]
RACES_BY_CATEGORIES_COLUMNS = ["categories", "nb_races"]
RANKED_RIDERS_COLUMNS = ["nb_ranked_riders"]
MOST_TITLED_COLUMNS = [
    "rank", "last_name", "first_name", "club", "category", "nb_wins",
    *[f"nb_top_{n}" for n in TOP_THRESHOLDS], "nb_races"
]


@dataclass(frozen=True)
class SeasonSummary:
    """Statistics of a season (see the functions of the module for the columns).

    Attributes:
        races_by_month: Output of count_races_by_month.
        races_by_departement: Output of count_races_by_departement.
        races_by_categories: Output of count_races_by_categories.
        ranked_riders: Output of count_ranked_riders.
        most_titled_riders: Output of rank_most_titled_riders.
    """
    races_by_month: pd.DataFrame
    races_by_departement: pd.DataFrame
    races_by_categories: pd.DataFrame
    ranked_riders: pd.DataFrame
    most_titled_riders: pd.DataFrame


def get_season_results(
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        departemental_committees: pd.DataFrame,
        regional_committees: pd.DataFrame,
        rider_categories: pd.DataFrame,
        season: int,
        region: str,
        categories: Sequence[str] = CATEGORIES,
        category_filter: Literal["race", "rider"] = "race"
    ) -> pd.DataFrame:
    """Results kept for the statistics of a season (see the module docstring for the rules).

    Args:
        races: Race table.
        rankings: Ranking table.
        departemental_committees: Departemental committee table.
        regional_committees: Regional committee table.
        rider_categories: Category history of the riders.
        season: Calendar year of the races.
        region: Name of the regional committee, one of COVERED_REGIONS.
        categories: Requested categories, contiguous, in any order ("A1" to "A4").
        category_filter: "race" to filter on the categories of the races,
            "rider" to filter on the categories of the riders on the race dates.

    Returns:
        One row per result kept: the SEASON_RESULT_COLUMNS, with race_date
        converted by to_datetime; sorted by race date, race_id, finish rank
        and rider_id.

    Raises:
        ValueError: If the region is not covered or unknown, if the season is
            before FIRST_SEASON, if a race of the season and the region has non
            contiguous categories, if category_filter is not "race" or "rider",
            or if the requested categories are invalid.
    """
    check_covered_region(region)
    if season < FIRST_SEASON:
        raise ValueError(f"Season {season} is before the first season {FIRST_SEASON}")

    region_id = get_regional_committee_id(regional_committees, region)
    season_races = get_region_races(races, departemental_committees, region_id, season)
    check_race_categories(season_races)
    results = (
        rankings[["race_id", "rider_id", "finish_rank"]]
        .merge(
            season_races[["race_id", "race_date", "departement_code", "categories"]],
            on="race_id"
        )
        .assign(race_date=lambda df: to_datetime(df["race_date"]))
    )
    results = filter_results_by_categories(results, rider_categories, categories, category_filter)
    return (
        results[SEASON_RESULT_COLUMNS]
        .sort_values(["race_date", "race_id", "finish_rank", "rider_id"])
        .reset_index(drop=True)
    )


def count_races_by_month(season_results: pd.DataFrame) -> pd.DataFrame:
    """Number of races of each month of the season.

    Args:
        season_results: Output of get_season_results.

    Returns:
        Twelve rows, the RACES_BY_MONTH_COLUMNS: month (1 to 12) and
        nb_races (0 if none).
    """
    counts = season_results.groupby(season_results["race_date"].dt.month)["race_id"].nunique()
    return (
        counts.reindex(range(1, 13), fill_value=0).astype(int)
        .rename_axis("month").rename("nb_races").reset_index()
        [RACES_BY_MONTH_COLUMNS]
    )


def count_races_by_departement(
        season_results: pd.DataFrame,
        departements: pd.DataFrame,
        departemental_committees: pd.DataFrame,
        regional_committees: pd.DataFrame,
        region: str
    ) -> pd.DataFrame:
    """Number of races of each departement of the region.

    Args:
        season_results: Output of get_season_results.
        departements: Departement table.
        departemental_committees: Departemental committee table.
        regional_committees: Regional committee table.
        region: Name of the regional committee, one of COVERED_REGIONS.

    Returns:
        One row per departement of the region: the RACES_BY_DEPARTEMENT_COLUMNS
        (departement_name missing if unknown, nb_races 0 if none); sorted by
        departement code.

    Raises:
        ValueError: If the region is not covered or unknown.
    """
    check_covered_region(region)
    region_id = get_regional_committee_id(regional_committees, region)
    codes = departemental_committees.loc[
        departemental_committees["regional_committee_id"] == region_id, "departement_code"
    ].drop_duplicates().sort_values()
    counts = season_results.groupby("departement_code")["race_id"].nunique()
    by_departement = pd.DataFrame({"departement_code": codes.to_numpy()}).merge(
        departements[["departement_code", "departement_name"]], on="departement_code", how="left"
    )
    by_departement["nb_races"] = (
        by_departement["departement_code"].map(counts).fillna(0).astype(int)
    )
    return by_departement[RACES_BY_DEPARTEMENT_COLUMNS]


def count_races_by_categories(season_results: pd.DataFrame) -> pd.DataFrame:
    """Number of races of each combination of categories present in the season.

    Args:
        season_results: Output of get_season_results.

    Returns:
        One row per combination present: the RACES_BY_CATEGORIES_COLUMNS
        (categories as stored, e.g. "A1,A2"); in the order of CATEGORY_COMBINATIONS.
    """
    counts = season_results.groupby("categories")["race_id"].nunique()
    present = [c for c in CATEGORY_COMBINATIONS if c in counts.index]
    return (
        counts.reindex(present).astype(int)
        .rename_axis("categories").rename("nb_races").reset_index()
        [RACES_BY_CATEGORIES_COLUMNS]
    )


def count_ranked_riders(season_results: pd.DataFrame) -> pd.DataFrame:
    """Number of distinct riders ranked in the season.

    Args:
        season_results: Output of get_season_results.

    Returns:
        One row: the RANKED_RIDERS_COLUMNS (each rider counted once).
    """
    return pd.DataFrame({"nb_ranked_riders": [season_results["rider_id"].nunique()]})


def rank_most_titled_riders(
        season_results: pd.DataFrame,
        riders: pd.DataFrame,
        clubs: pd.DataFrame,
        affiliations: pd.DataFrame,
        rider_categories: pd.DataFrame,
        season: int,
        max_riders: int = 10
    ) -> pd.DataFrame:
    """Most titled riders of the season (see the module docstring for the rules).

    Args:
        season_results: Output of get_season_results.
        riders: Rider table.
        clubs: Club table.
        affiliations: Affiliation table (club history of the riders).
        rider_categories: Category history of the riders.
        season: Calendar year of the results.
        max_riders: Maximum number of riders returned.

    Returns:
        At most max_riders rows: the MOST_TITLED_COLUMNS; sorted by rank, then
        last name, first name and rider_id.

    Raises:
        ValueError: If max_riders is lower than 1.
    """
    if max_riders < 1:
        raise ValueError(f"max_riders must be at least 1, not {max_riders}")
    rider_ids = season_results["rider_id"].unique()
    results = add_category_on_race_date(
        season_results, rider_categories[rider_categories["rider_id"].isin(rider_ids)]
    )
    results = add_value_on_race_date(
        results, affiliations[affiliations["rider_id"].isin(rider_ids)], "club_id"
    ).sort_values(["race_date", "race_id"])

    # "A1" is the highest category and the smallest label
    highest_categories = (
        results.dropna(subset=["category"]).groupby("rider_id")["category"].min()
    )
    first_club_ids = (
        results.dropna(subset=["club_id"]).groupby("rider_id")["club_id"].agg(select_club)
    )
    club_names = first_club_ids.map(clubs.set_index("club_id")["name"])

    criteria = ["nb_wins", *[f"nb_top_{n}" for n in TOP_THRESHOLDS]]
    stats = count_wins_and_tops(results.assign(season=season))
    titled = (
        stats[stats[f"nb_top_{TOP_THRESHOLDS[-1]}"] > 0]
        .merge(riders[["rider_id", "last_name", "first_name"]], on="rider_id", how="left")
        .assign(
            club=lambda df: df["rider_id"].map(club_names).fillna(UNKNOWN_CLUB),
            category=lambda df: df["rider_id"].map(highest_categories).fillna(UNKNOWN_CATEGORY)
        )
        .sort_values(
            [*criteria, "last_name", "first_name", "rider_id"],
            ascending=[False] * len(criteria) + [True] * 3
        )
        .head(max_riders)
        .reset_index(drop=True)
    )
    # Riders tied on every count share the rank of the first of them
    is_first_of_tie = titled[criteria].ne(titled[criteria].shift()).any(axis=1)
    titled["rank"] = pd.Series(titled.index + 1).where(is_first_of_tie).ffill().astype(int)
    return titled[MOST_TITLED_COLUMNS]


def compute_season_summary(
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        riders: pd.DataFrame,
        clubs: pd.DataFrame,
        departements: pd.DataFrame,
        departemental_committees: pd.DataFrame,
        regional_committees: pd.DataFrame,
        affiliations: pd.DataFrame,
        rider_categories: pd.DataFrame,
        season: int,
        region: str,
        categories: Sequence[str] = CATEGORIES,
        category_filter: Literal["race", "rider"] = "race",
        max_riders: int = 10
    ) -> SeasonSummary:
    """Statistics of a season (see the module docstring for the rules).

    Args:
        races: Race table.
        rankings: Ranking table.
        riders: Rider table.
        clubs: Club table.
        departements: Departement table.
        departemental_committees: Departemental committee table.
        regional_committees: Regional committee table.
        affiliations: Affiliation table (club history of the riders).
        rider_categories: Category history of the riders.
        season: Calendar year of the races.
        region: Name of the regional committee, one of COVERED_REGIONS.
        categories: Requested categories, contiguous, in any order ("A1" to "A4").
        category_filter: "race" to filter on the categories of the races,
            "rider" to filter on the categories of the riders on the race dates.
        max_riders: Maximum number of most titled riders.

    Returns:
        The SeasonSummary of the season.

    Raises:
        ValueError: See get_season_results and rank_most_titled_riders.
    """
    season_results = get_season_results(
        races, rankings, departemental_committees, regional_committees, rider_categories,
        season, region, categories, category_filter
    )
    return SeasonSummary(
        races_by_month=count_races_by_month(season_results),
        races_by_departement=count_races_by_departement(
            season_results, departements, departemental_committees, regional_committees, region
        ),
        races_by_categories=count_races_by_categories(season_results),
        ranked_riders=count_ranked_riders(season_results),
        most_titled_riders=rank_most_titled_riders(
            season_results, riders, clubs, affiliations, rider_categories, season, max_riders
        ),
    )
