"""Profile of a rider: results, categories, clubs, season statistics, points and recent form.

Rules:

- the profile covers the seasons from FIRST_SEASON to the year of the
  reference date, and only the dates strictly before the reference date (by
  default, the day after the last race of the table: see get_reference_date);
- the rank is the absolute finish rank; the tops are inclusive (a win also
  counts in every top) and tied riders all count;
- a period of category or club started before FIRST_SEASON starts on the
  first day of FIRST_SEASON; an ongoing period has no end date;
- the points come from the race by race outputs of compute_promotion_points
  and compute_challenge_points, computed by the caller (and cached by the
  dashboard); a season has one total per category held by the rider in the
  season (his category on the dates of his races), empty for the other categories;
- a rider is concerned by the regional challenge in a season if, on the date
  of one of his races of the season, his club belongs to the region;
  otherwise his challenge points are empty and the challenge column is
  "not applicable".

The functions select the riders by rider_id only; compute_season_stats and
compute_season_points also work on the results of several riders. The
computation is free of any Streamlit dependency.
"""

from dataclasses import dataclass

import pandas as pd

from access_it.analytics.ranking_tools import (
    CATEGORIES, add_category_on_race_date, add_value_on_race_date, get_region_club_ids,
    get_regional_committee_id, to_datetime
)
from access_it.analytics.recent_form import compute_recent_form
from access_it.analytics.regional_rankings import PAYS_DE_LA_LOIRE
from access_it.common.seasons import FIRST_SEASON

UNKNOWN_CATEGORY = "unknown category"
UNKNOWN_CLUB = "unknown club"
NOT_APPLICABLE = "not applicable"

TOP_THRESHOLDS = (3, 5, 10, 20)

RESULT_COLUMNS = [
    "rider_id", "race_date", "season", "race_id", "title", "finish_rank", "category", "club"
]
SEASON_STATS_COLUMNS = [
    "rider_id", "season", "nb_races", "nb_wins", *[f"nb_top_{n}" for n in TOP_THRESHOLDS]
]
SEASON_POINTS_COLUMNS = [
    "rider_id", "season",
    *[f"promotion_points_{c.lower()}" for c in CATEGORIES],
    *[f"challenge_points_{c.lower()}" for c in CATEGORIES],
    "challenge"
]


@dataclass(frozen=True)
class RiderProfile:
    """Profile of a rider (see the functions of the module for the columns).

    Attributes:
        results: Output of get_rider_results.
        categories: Output of get_rider_categories.
        clubs: Output of get_rider_clubs.
        season_stats: Output of compute_season_stats.
        season_points: Output of compute_season_points.
        recent_form: Output of compute_recent_form (one row).
    """
    results: pd.DataFrame
    categories: pd.DataFrame
    clubs: pd.DataFrame
    season_stats: pd.DataFrame
    season_points: pd.DataFrame
    recent_form: pd.DataFrame


def _to_day(reference_date: str | pd.Timestamp) -> pd.Timestamp:
    """Reference date as a timestamp at midnight."""
    return to_datetime(pd.Series([reference_date])).dt.normalize().iloc[0]


def get_rider_results(
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        clubs: pd.DataFrame,
        affiliations: pd.DataFrame,
        rider_categories: pd.DataFrame,
        rider_id: str,
        reference_date: str | pd.Timestamp
    ) -> pd.DataFrame:
    """Results of a rider, from the most recent to the oldest.

    Two races of the same day are ordered by finish rank (best place first),
    then by race_id, as in compute_recent_form.

    Args:
        races: Race table.
        rankings: Ranking table.
        clubs: Club table.
        affiliations: Affiliation table (club history of the riders).
        rider_categories: Category history of the riders.
        rider_id: Rider to show.
        reference_date: Day of the profile, as "YYYY-MM-DD" or a date; its
            races and the later ones are excluded.

    Returns:
        One row per race of the rider: the RESULT_COLUMNS, with the category
        ("A1" to "A4") and the club name of the rider on the race date
        (UNKNOWN_CATEGORY or UNKNOWN_CLUB if unknown).
    """
    day = _to_day(reference_date)
    results = (
        rankings.loc[rankings["rider_id"] == rider_id, ["race_id", "rider_id", "finish_rank"]]
        .merge(races[["race_id", "race_date", "season", "title"]], on="race_id")
        .assign(race_date=lambda df: to_datetime(df["race_date"]))
    )
    results = results[
        results["season"].between(FIRST_SEASON, day.year) & (results["race_date"] < day)
    ]
    results = add_category_on_race_date(
        results, rider_categories[rider_categories["rider_id"] == rider_id]
    )
    results = add_value_on_race_date(
        results, affiliations[affiliations["rider_id"] == rider_id], "club_id"
    )
    # astype(object): a column of unknown categories only keeps the integer dtype of the history
    results["category"] = results["category"].astype(object).fillna(UNKNOWN_CATEGORY).astype(str)
    results["club"] = (
        results["club_id"].map(clubs.set_index("club_id")["name"]).fillna(UNKNOWN_CLUB)
    )
    return (
        results[RESULT_COLUMNS]
        .sort_values(["race_date", "finish_rank", "race_id"], ascending=[False, True, False])
        .reset_index(drop=True)
    )


def _get_periods(
        history: pd.DataFrame,
        column: str,
        rider_id: str,
        reference_date: str | pd.Timestamp
    ) -> pd.DataFrame:
    """Periods of a history (rider_id, start_date, column) of a rider, from the oldest.

    Each period ends the day before the next start_date (end_date missing if
    the next period does not start before the reference date). Only the
    periods between the first day of FIRST_SEASON and the day before the
    reference date are kept, and their start_date is moved to the first day
    of FIRST_SEASON if earlier.
    """
    day = _to_day(reference_date)
    first_day = pd.Timestamp(year=FIRST_SEASON, month=1, day=1)
    periods = (
        history.loc[history["rider_id"] == rider_id, ["rider_id", "start_date", column]]
        .assign(start_date=lambda df: to_datetime(df["start_date"]))
        .sort_values("start_date")
    )
    periods["end_date"] = periods["start_date"].shift(-1) - pd.Timedelta(days=1)
    periods = periods[
        (periods["start_date"] < day)
        & (periods["end_date"].isna() | (periods["end_date"] >= first_day))
    ].copy()
    periods["start_date"] = periods["start_date"].clip(lower=first_day)
    # The end is known only if the next period starts before the reference date
    next_start = periods["end_date"] + pd.Timedelta(days=1)
    periods["end_date"] = periods["end_date"].where(next_start < day)
    return periods.reset_index(drop=True)  # sorted by start_date


def get_rider_categories(
        rider_categories: pd.DataFrame,
        rider_id: str,
        reference_date: str | pd.Timestamp
    ) -> pd.DataFrame:
    """Successive categories of a rider, from the oldest (see _get_periods).

    Args:
        rider_categories: Category history of the riders.
        rider_id: Rider to show.
        reference_date: Day of the profile, as "YYYY-MM-DD" or a date.

    Returns:
        One row per period: rider_id, start_date, end_date and category ("A1"
        to "A4", or UNKNOWN_CATEGORY).
    """
    periods = _get_periods(rider_categories, "rider_category", rider_id, reference_date)
    periods["category"] = periods["rider_category"].map(
        lambda c: UNKNOWN_CATEGORY if pd.isna(c) else f"A{int(c)}"
    ).astype(str)
    return periods[["rider_id", "start_date", "end_date", "category"]]


def get_rider_clubs(
        clubs: pd.DataFrame,
        affiliations: pd.DataFrame,
        rider_id: str,
        reference_date: str | pd.Timestamp
    ) -> pd.DataFrame:
    """Successive clubs of a rider, from the oldest (see _get_periods).

    Args:
        clubs: Club table.
        affiliations: Affiliation table (club history of the riders).
        rider_id: Rider to show.
        reference_date: Day of the profile, as "YYYY-MM-DD" or a date.

    Returns:
        One row per period: rider_id, start_date, end_date and club (name, or
        UNKNOWN_CLUB).
    """
    periods = _get_periods(affiliations, "club_id", rider_id, reference_date)
    periods["club"] = (
        periods["club_id"].map(clubs.set_index("club_id")["name"]).fillna(UNKNOWN_CLUB)
    )
    return periods[["rider_id", "start_date", "end_date", "club"]]


def compute_season_stats(rider_results: pd.DataFrame) -> pd.DataFrame:
    """Number of races, wins and tops of each rider and season.

    Args:
        rider_results: Results with rider_id, season and finish_rank, such as
            the output of get_rider_results (one or several riders).

    Returns:
        One row per rider and season with a race: the SEASON_STATS_COLUMNS
        (inclusive tops); sorted by rider and from the oldest season.
    """
    stats = rider_results.assign(
        is_win=rider_results["finish_rank"] <= 1,
        **{f"is_top_{n}": rider_results["finish_rank"] <= n for n in TOP_THRESHOLDS}
    ).groupby(["rider_id", "season"]).agg(
        nb_races=("race_id", "size"),
        nb_wins=("is_win", "sum"),
        **{f"nb_top_{n}": (f"is_top_{n}", "sum") for n in TOP_THRESHOLDS}
    ).astype(int).reset_index()
    return (
        stats[SEASON_STATS_COLUMNS]
        .sort_values(["rider_id", "season"])
        .reset_index(drop=True)
    )


def _sum_points_by_category(
        points: pd.DataFrame,
        rider_results: pd.DataFrame,
        prefix: str
    ) -> pd.DataFrame:
    """Total points of each rider, season and category held, one column per category.

    The categories held in a season are those of the rider on the dates of
    his races (0 if no points); the others are empty. Only the races of
    rider_results count.
    """
    keys = ["rider_id", "season"]
    held = rider_results.loc[rider_results["category"].isin(CATEGORIES), keys + ["category"]]
    scored = points[["race_id", "rider_id", "category", "points"]].merge(
        rider_results[["race_id", "rider_id", "season"]], on=["race_id", "rider_id"]
    )
    return (
        pd.concat([held.assign(points=0), scored[keys + ["category", "points"]]])
        .groupby(keys + ["category"])["points"].sum()
        .unstack("category")
        .reindex(columns=list(CATEGORIES))
        .astype("Int64")
        .rename(columns=lambda c: f"{prefix}_{c.lower()}")
        .rename_axis(columns=None)
    )


def compute_season_points(
        rider_results: pd.DataFrame,
        promotion_points: pd.DataFrame,
        challenge_points: pd.DataFrame,
        clubs: pd.DataFrame,
        departemental_committees: pd.DataFrame,
        regional_committees: pd.DataFrame,
        affiliations: pd.DataFrame,
        region: str = PAYS_DE_LA_LOIRE
    ) -> pd.DataFrame:
    """Promotion and challenge points of each rider and season, by category.

    Args:
        rider_results: Output of get_rider_results (one or several riders).
        promotion_points: Outputs of compute_promotion_points of the seasons,
            concatenated.
        challenge_points: Outputs of compute_challenge_points of the seasons
            for `region`, concatenated.
        clubs: Club table.
        departemental_committees: Departemental committee table.
        regional_committees: Regional committee table.
        affiliations: Affiliation table (club history of the riders).
        region: Name of the regional committee of the challenge.

    Returns:
        One row per rider and season with a race: the SEASON_POINTS_COLUMNS
        (points as Int64, empty for a category not held, and for every
        category of the challenge if the rider is not concerned; challenge:
        NOT_APPLICABLE or missing); sorted by rider and from the oldest season.

    Raises:
        ValueError: If the region is unknown.
    """
    keys = ["rider_id", "season"]
    region_id = get_regional_committee_id(regional_committees, region)
    region_clubs = get_region_club_ids(clubs, departemental_committees, region_id)
    on_date = add_value_on_race_date(
        rider_results[keys + ["race_date"]],
        affiliations[affiliations["rider_id"].isin(rider_results["rider_id"])],
        "club_id"
    )
    is_concerned = on_date["club_id"].isin(region_clubs).groupby(
        [on_date["rider_id"], on_date["season"]]
    ).any()
    seasons = pd.MultiIndex.from_frame(rider_results[keys].drop_duplicates())
    promotion = _sum_points_by_category(promotion_points, rider_results, "promotion_points")
    challenge = _sum_points_by_category(challenge_points, rider_results, "challenge_points")
    season_points = promotion.join(challenge, how="outer").reindex(seasons)
    is_concerned = is_concerned.reindex(seasons, fill_value=False)
    season_points.loc[~is_concerned, challenge.columns] = pd.NA
    season_points["challenge"] = pd.Series(NOT_APPLICABLE, index=seasons).where(~is_concerned)
    return (
        season_points.reset_index()[SEASON_POINTS_COLUMNS]
        .sort_values(keys)
        .reset_index(drop=True)
    )


def compute_rider_profile(
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        clubs: pd.DataFrame,
        departemental_committees: pd.DataFrame,
        regional_committees: pd.DataFrame,
        affiliations: pd.DataFrame,
        rider_categories: pd.DataFrame,
        promotion_points: pd.DataFrame,
        challenge_points: pd.DataFrame,
        rider_id: str,
        reference_date: str | pd.Timestamp,
        region: str = PAYS_DE_LA_LOIRE,
        top_n: int = 20,
        last_races: int = 10,
        window_months: int = 6
    ) -> RiderProfile:
    """Profile of a rider (see the module docstring for the rules).

    Args:
        races: Race table.
        rankings: Ranking table.
        clubs: Club table.
        departemental_committees: Departemental committee table.
        regional_committees: Regional committee table.
        affiliations: Affiliation table (club history of the riders).
        rider_categories: Category history of the riders.
        promotion_points: Outputs of compute_promotion_points of the seasons,
            concatenated.
        challenge_points: Outputs of compute_challenge_points of the seasons
            for `region`, concatenated.
        rider_id: Rider to show.
        reference_date: Day of the profile, as "YYYY-MM-DD" or a date
            (get_reference_date gives the default one).
        region: Name of the regional committee of the challenge.
        top_n: Last finish rank counting as a top N in the recent form.
        last_races: Maximum number of races used by the recent form.
        window_months: Length of the window of the recent form.

    Returns:
        The RiderProfile of the rider.

    Raises:
        ValueError: If the region is unknown.
    """
    results = get_rider_results(
        races, rankings, clubs, affiliations, rider_categories, rider_id, reference_date
    )
    return RiderProfile(
        results=results,
        categories=get_rider_categories(rider_categories, rider_id, reference_date),
        clubs=get_rider_clubs(clubs, affiliations, rider_id, reference_date),
        season_stats=compute_season_stats(results),
        season_points=compute_season_points(
            results, promotion_points, challenge_points, clubs, departemental_committees,
            regional_committees, affiliations, region
        ),
        recent_form=compute_recent_form(
            races, rankings, [rider_id], reference_date, top_n, last_races, window_months
        ),
    )
