"""Ranking of the clubs by the wins and tops of their riders in a season.

Rules:

- the results of a club are those of its riders while they were in it (club
  of the rider on the race date), in the races of the season held in every
  region; the categories of every race of the season must be one of the
  contiguous CATEGORY_COMBINATIONS;
- the clubs ranked are those of the region (of every region if region is
  None; only the regions of COVERED_REGIONS are accepted) whose years
  (min_year to max_year, both included) contain the season, except the
  pseudo-clubs (individual licensees of a committee or of unknown committee,
  foreign riders); a club without any result is shown with zeros; the
  results of the other clubs are ignored;
- the wins and tops are counted on the results of the requested categories
  (contiguous, in any order, duplicates removed): category_filter "race"
  keeps the races having at least one of them, "rider" the results of the
  riders whose category on the race date is one of them;
- the rank is the absolute finish rank; the tops are inclusive (a win also
  counts in every top) and tied riders all count;
- the active riders of a club are its riders ranked in any race of the
  season, whatever the requested categories; a rider who changes club during
  the season is active in each of his clubs; they are shown only, not sorted on;
- the clubs are sorted by wins, then tops 3, 5, 10 and 20, then club name and
  club_id; clubs tied on every count share the rank; the list is cut at
  max_clubs clubs.

The computation is free of any Streamlit dependency.
"""

from collections.abc import Sequence
from typing import Literal

import pandas as pd

from access_it.analytics.ranking_tools import (
    CATEGORIES, TOP_THRESHOLDS, add_shared_rank, add_value_on_race_date, check_race_categories,
    count_wins_and_tops, filter_results_by_categories, get_region_club_ids,
    get_regional_committee_id, to_datetime
)
from access_it.common.regions import check_covered_region
from access_it.common.seasons import FIRST_SEASON, check_season
from access_it.etl.extract.clubs import individual_club_id_mask
from access_it.etl.extract.constants import FOREIGN_CLUB_ID

CLUB_RANKING_COLUMNS = [
    "rank", "club", "departement_code", "departement_name", "nb_wins",
    *[f"nb_top_{n}" for n in TOP_THRESHOLDS], "nb_active_riders", "club_id"
]


def get_club_results(
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        affiliations: pd.DataFrame,
        season: int
    ) -> pd.DataFrame:
    """Results of the season in every region, with the club of the rider on the race date.

    Args:
        races: Race table.
        rankings: Ranking table.
        affiliations: Affiliation table (club history of the riders).
        season: Calendar year of the races.

    Returns:
        One row per result: race_id, race_date (converted by to_datetime),
        categories (those of the race, as stored), rider_id, finish_rank and
        club_id (missing if unknown); sorted by race date, race_id, finish
        rank and rider_id.

    Raises:
        ValueError: If the season is before FIRST_SEASON, or if a race of the
            season has non contiguous categories.
    """
    check_season(season)
    season_races = races.loc[races["season"] == season, ["race_id", "race_date", "categories"]]
    check_race_categories(season_races)
    results = (
        rankings[["race_id", "rider_id", "finish_rank"]]
        .merge(season_races, on="race_id")
        .assign(race_date=lambda df: to_datetime(df["race_date"]))
    )
    rider_ids = results["rider_id"].unique()
    results = add_value_on_race_date(
        results, affiliations[affiliations["rider_id"].isin(rider_ids)], "club_id"
    )
    columns = ["race_id", "race_date", "categories", "rider_id", "finish_rank", "club_id"]
    return (
        results[columns]
        .sort_values(["race_date", "race_id", "finish_rank", "rider_id"])
        .reset_index(drop=True)
    )


def rank_clubs(
        club_results: pd.DataFrame,
        clubs: pd.DataFrame,
        departements: pd.DataFrame,
        departemental_committees: pd.DataFrame,
        regional_committees: pd.DataFrame,
        rider_categories: pd.DataFrame,
        season: int,
        region: str | None = None,
        categories: Sequence[str] = CATEGORIES,
        category_filter: Literal["race", "rider"] = "race",
        max_clubs: int = 10
    ) -> pd.DataFrame:
    """Ranking of the clubs (see the module docstring for the rules).

    Args:
        club_results: Output of get_club_results.
        clubs: Club table.
        departements: Departement table.
        departemental_committees: Departemental committee table.
        regional_committees: Regional committee table.
        rider_categories: Category history of the riders.
        season: Calendar year of the results.
        region: Name of the regional committee, one of COVERED_REGIONS, or
            None for the clubs of every region.
        categories: Requested categories, contiguous, in any order ("A1" to "A4").
        category_filter: "race" to filter on the categories of the races,
            "rider" to filter on the categories of the riders on the race dates.
        max_clubs: Maximum number of clubs returned.

    Returns:
        At most max_clubs rows: the CLUB_RANKING_COLUMNS (departement_code
        and departement_name missing if unknown); sorted by rank, then club
        name and club_id.

    Raises:
        ValueError: If the region is not covered or unknown, if category_filter
            is not "race" or "rider", if the requested categories are invalid,
            or if max_clubs is lower than 1.
    """
    ranked_clubs = clubs[(clubs["min_year"] <= season) & (season <= clubs["max_year"])]
    if region is not None:
        check_covered_region(region)
        region_id = get_regional_committee_id(regional_committees, region)
        region_club_ids = get_region_club_ids(clubs, departemental_committees, region_id)
        ranked_clubs = ranked_clubs[ranked_clubs["club_id"].isin(region_club_ids)]
    is_pseudo_club = (
        individual_club_id_mask(ranked_clubs["club_id"])
        | (ranked_clubs["club_id"] == FOREIGN_CLUB_ID)
    )
    ranked_clubs = ranked_clubs[~is_pseudo_club]

    results = club_results[club_results["club_id"].isin(ranked_clubs["club_id"])]
    counted = filter_results_by_categories(results, rider_categories, categories, category_filter)
    if max_clubs < 1:
        raise ValueError(f"max_clubs must be at least 1, not {max_clubs}")

    criteria = ["nb_wins", *[f"nb_top_{n}" for n in TOP_THRESHOLDS]]
    stats = count_wins_and_tops(counted, by=("club_id",)).set_index("club_id")
    nb_active_riders = results.groupby("club_id")["rider_id"].nunique()
    ranking = (
        ranked_clubs[["club_id", "name", "departemental_committee_id"]]
        .rename(columns={"name": "club"})
        .merge(
            departemental_committees[["departemental_committee_id", "departement_code"]],
            on="departemental_committee_id", how="left"
        )
        .merge(
            departements[["departement_code", "departement_name"]],
            on="departement_code", how="left"
        )
    )
    for column in criteria:
        ranking[column] = ranking["club_id"].map(stats[column]).fillna(0).astype(int)
    ranking["nb_active_riders"] = ranking["club_id"].map(nb_active_riders).fillna(0).astype(int)
    ranking = (
        ranking
        .sort_values(
            [*criteria, "club", "club_id"], ascending=[False] * len(criteria) + [True] * 2
        )
        .head(max_clubs)
    )
    return add_shared_rank(ranking, criteria)[CLUB_RANKING_COLUMNS].reset_index(drop=True)


def compute_club_rankings(
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        clubs: pd.DataFrame,
        departements: pd.DataFrame,
        departemental_committees: pd.DataFrame,
        regional_committees: pd.DataFrame,
        affiliations: pd.DataFrame,
        rider_categories: pd.DataFrame,
        season: int,
        region: str | None = None,
        categories: Sequence[str] = CATEGORIES,
        category_filter: Literal["race", "rider"] = "race",
        max_clubs: int = 10
    ) -> pd.DataFrame:
    """Ranking of the clubs in a season (see the module docstring for the rules).

    Args:
        races: Race table.
        rankings: Ranking table.
        clubs: Club table.
        departements: Departement table.
        departemental_committees: Departemental committee table.
        regional_committees: Regional committee table.
        affiliations: Affiliation table (club history of the riders).
        rider_categories: Category history of the riders.
        season: Calendar year of the races.
        region: Name of the regional committee, one of COVERED_REGIONS, or
            None for the clubs of every region.
        categories: Requested categories, contiguous, in any order ("A1" to "A4").
        category_filter: "race" to filter on the categories of the races,
            "rider" to filter on the categories of the riders on the race dates.
        max_clubs: Maximum number of clubs returned.

    Returns:
        The output of rank_clubs.

    Raises:
        ValueError: See get_club_results and rank_clubs.
    """
    club_results = get_club_results(races, rankings, affiliations, season)
    return rank_clubs(
        club_results, clubs, departements, departemental_committees, regional_committees,
        rider_categories, season, region, categories, category_filter, max_clubs
    )
