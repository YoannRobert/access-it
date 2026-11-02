"""Head to head of two riders: their common races and who finished ahead.

Rules:

- a race counts only if both riders are ranked in it, whatever their finish
  ranks;
- the rank is the absolute finish rank: a rider is ahead of the other if his
  finish rank is lower, and two tied riders (same finish rank) are even;
- the races are those of the seasons from FIRST_SEASON to the year of the
  reference date, strictly before the reference date (see get_rider_results
  of ranking_tools), or only those of one season if requested;
- the category and the club of each rider are those on the race date
  (UNKNOWN_CATEGORY or UNKNOWN_CLUB if unknown).

The functions select the riders by rider_id only. The computation is free of
any Streamlit dependency.
"""

from dataclasses import dataclass

import pandas as pd

from access_it.analytics.ranking_tools import check_rider, get_rider_results, to_day
from access_it.common.seasons import check_season

COMMON_RACE_COLUMNS = [
    "rider_id", "opponent_id", "race_date", "season", "race_id", "title",
    "rider_finish_rank", "rider_category", "rider_club",
    "opponent_finish_rank", "opponent_category", "opponent_club"
]
HEAD_TO_HEAD_SUMMARY_COLUMNS = [
    "rider_id", "opponent_id", "nb_common_races", "nb_rider_ahead", "nb_opponent_ahead", "nb_ties"
]


@dataclass(frozen=True)
class HeadToHead:
    """Head to head of two riders (see the functions of the module for the columns).

    Attributes:
        races: Output of get_common_races.
        summary: Output of summarize_head_to_head (one row).
    """
    races: pd.DataFrame
    summary: pd.DataFrame


def get_common_races(
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        riders: pd.DataFrame,
        clubs: pd.DataFrame,
        affiliations: pd.DataFrame,
        rider_categories: pd.DataFrame,
        rider_id: str,
        opponent_id: str,
        reference_date: str | pd.Timestamp,
        season: int | None = None
    ) -> pd.DataFrame:
    """Races where both riders are ranked, from the most recent to the oldest.

    Args:
        races: Race table.
        rankings: Ranking table.
        riders: Rider table.
        clubs: Club table.
        affiliations: Affiliation table (club history of the riders).
        rider_categories: Category history of the riders.
        rider_id: First rider.
        opponent_id: Second rider.
        reference_date: Day of the analysis, as "YYYY-MM-DD" or a date
            (get_reference_date gives the default one); its races and the
            later ones are excluded.
        season: Season of the races, or None for every season covered.

    Returns:
        One row per common race: the COMMON_RACE_COLUMNS, with the finish
        rank, the category ("A1" to "A4") and the club name of each rider on
        the race date (UNKNOWN_CATEGORY or UNKNOWN_CLUB if unknown); sorted
        by race date, then race_id, both descending.

    Raises:
        ValueError: If both riders are the same, then if one of them is not in
            the rider table, then if the season is before FIRST_SEASON, then if
            the reference date is missing, then if the season is after the year
            of the reference date, then, for the rider and then for the
            opponent, if one of his races has no date, then, if one of his
            races is kept (from FIRST_SEASON to the reference date, whatever
            the season), if one of his start dates in rider_categories is
            missing, then if one of his start dates in affiliations is missing.
    """
    if rider_id == opponent_id:
        raise ValueError(f"Same rider and opponent: {rider_id!r}")
    for rider in (rider_id, opponent_id):
        check_rider(riders, rider)
    if season is not None:
        check_season(season)
        year = to_day(reference_date).year
        if season > year:
            raise ValueError(f"Season {season} is after the year of the reference date {year}")
    keys = ["race_date", "season", "race_id", "title"]
    rider_results, opponent_results = (
        get_rider_results(
            races, rankings, clubs, affiliations, rider_categories, rider, reference_date
        )
        .drop(columns="rider_id")
        .set_index(keys)
        .add_prefix(f"{prefix}_")
        for rider, prefix in ((rider_id, "rider"), (opponent_id, "opponent"))
    )
    common = rider_results.join(opponent_results, how="inner").reset_index()
    if season is not None:
        common = common[common["season"] == season]
    return (
        common.assign(rider_id=rider_id, opponent_id=opponent_id)[COMMON_RACE_COLUMNS]
        .sort_values(["race_date", "race_id"], ascending=False)
        .reset_index(drop=True)
    )


def summarize_head_to_head(
        common_races: pd.DataFrame,
        rider_id: str,
        opponent_id: str
    ) -> pd.DataFrame:
    """Number of common races, of races where each rider finished ahead, and of ties.

    Args:
        common_races: Output of get_common_races for the two riders.
        rider_id: First rider.
        opponent_id: Second rider.

    Returns:
        One row: the HEAD_TO_HEAD_SUMMARY_COLUMNS, with integer counts (0 without common race).
    """
    rider_ranks = common_races["rider_finish_rank"]
    opponent_ranks = common_races["opponent_finish_rank"]
    summary = pd.DataFrame([{
        "rider_id": rider_id,
        "opponent_id": opponent_id,
        "nb_common_races": len(common_races),
        "nb_rider_ahead": int((rider_ranks < opponent_ranks).sum()),
        "nb_opponent_ahead": int((rider_ranks > opponent_ranks).sum()),
        "nb_ties": int((rider_ranks == opponent_ranks).sum()),
    }])
    return summary[HEAD_TO_HEAD_SUMMARY_COLUMNS]


def compute_head_to_head(
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        riders: pd.DataFrame,
        clubs: pd.DataFrame,
        affiliations: pd.DataFrame,
        rider_categories: pd.DataFrame,
        rider_id: str,
        opponent_id: str,
        reference_date: str | pd.Timestamp,
        season: int | None = None
    ) -> HeadToHead:
    """Head to head of two riders (see the module docstring for the rules).

    Args:
        races: Race table.
        rankings: Ranking table.
        riders: Rider table.
        clubs: Club table.
        affiliations: Affiliation table (club history of the riders).
        rider_categories: Category history of the riders.
        rider_id: First rider.
        opponent_id: Second rider.
        reference_date: Day of the analysis, as "YYYY-MM-DD" or a date
            (get_reference_date gives the default one).
        season: Season of the races, or None for every season covered.

    Returns:
        The HeadToHead of the two riders.

    Raises:
        ValueError: If both riders are the same, then if one of them is not in
            the rider table, then if the season is before FIRST_SEASON, then if
            the reference date is missing, then if the season is after the year
            of the reference date, then, for the rider and then for the
            opponent, if one of his races has no date, then, if one of his
            races is kept (from FIRST_SEASON to the reference date, whatever
            the season), if one of his start dates in rider_categories is
            missing, then if one of his start dates in affiliations is missing.
    """
    common_races = get_common_races(
        races, rankings, riders, clubs, affiliations, rider_categories, rider_id, opponent_id,
        reference_date, season
    )
    return HeadToHead(
        races=common_races,
        summary=summarize_head_to_head(common_races, rider_id, opponent_id),
    )
