"""Building blocks shared by the modules of the analytics package.

Used by the regional challenge (regional_rankings), the promotion points
(promotion_points) and the other analytics modules: default reference date,
races and clubs of a region, category and club of a rider on the race date,
places in a race, wins and tops of the riders by season, points of a scale,
ranking of the riders with its tie-breaks, and filter on a category.
"""

import pandas as pd

from access_it.analytics.labels import UNKNOWN_CATEGORY, UNKNOWN_CLUB
from access_it.etl.extract.clubs import individual_club_id_mask

CATEGORIES = ("A1", "A2", "A3", "A4")

TOP_THRESHOLDS = (3, 5, 10, 20)
SEASON_STATS_COLUMNS = [
    "rider_id", "season", "nb_races", "nb_wins", *[f"nb_top_{n}" for n in TOP_THRESHOLDS]
]


def to_datetime(s: pd.Series) -> pd.Series:
    """Dates as datetime64[ns], whatever their input type (string, date, timestamp)."""
    return pd.to_datetime(s).astype("datetime64[ns]")


def get_reference_date(races: pd.DataFrame) -> pd.Timestamp:
    """Default reference date of the analytics: the day after the last race of the table.

    Every race of the table, the last one included, is strictly before it.

    Raises:
        ValueError: If the race table is empty.
    """
    if races.empty:
        raise ValueError("No race to find the reference date from")
    return to_datetime(races["race_date"]).max().normalize() + pd.Timedelta(days=1)


def get_regional_committee_id(regional_committees: pd.DataFrame, region: str) -> str:
    """ID of the regional committee named `region` (name as in regional_committees).

    Raises:
        ValueError: If the region is unknown.
    """
    is_region = regional_committees["name"] == region
    if not is_region.any():
        raise ValueError(f"Unknown region: {region!r}")
    return regional_committees.loc[is_region, "regional_committee_id"].iloc[0]


def get_region_races(
        races: pd.DataFrame,
        departemental_committees: pd.DataFrame,
        region_id: str,
        season: int
    ) -> pd.DataFrame:
    """Races of a season held in a region: those of the departements of its committees.

    Args:
        races: Race table.
        departemental_committees: Departemental committee table.
        region_id: ID of the regional committee (see get_regional_committee_id).
        season: Calendar year of the races.

    Returns:
        The rows of the race table, with all its columns.
    """
    region_departements = departemental_committees.loc[
        departemental_committees["regional_committee_id"] == region_id, "departement_code"
    ]
    return races[
        (races["season"] == season) & races["departement_code"].isin(region_departements)
    ].reset_index(drop=True)


def get_region_club_ids(
        clubs: pd.DataFrame,
        departemental_committees: pd.DataFrame,
        region_id: str
    ) -> pd.Series:
    """IDs of the clubs of a region: those of the departemental committees of the region.

    The pseudo-clubs of the individual licensees of these committees are included.

    Args:
        clubs: Club table.
        departemental_committees: Departemental committee table.
        region_id: ID of the regional committee (see get_regional_committee_id).
    """
    region_committee_ids = departemental_committees.loc[
        departemental_committees["regional_committee_id"] == region_id,
        "departemental_committee_id"
    ]
    return clubs.loc[clubs["departemental_committee_id"].isin(region_committee_ids), "club_id"]


def add_value_on_race_date(
        results: pd.DataFrame,
        history: pd.DataFrame,
        column: str
    ) -> pd.DataFrame:
    """Add to each result the value of `column` of the period of `history` covering the race date.

    History periods (rider_id, start_date, column) start at start_date and
    end the day before the next start_date of the same rider. The value is
    missing if the race is before the first period of the rider.
    """
    history = (
        history[["rider_id", "start_date", column]]
        .assign(start_date=lambda df: to_datetime(df["start_date"]))
        .sort_values("start_date")
    )
    return pd.merge_asof(
        results.sort_values("race_date"),
        history,
        left_on="race_date",
        right_on="start_date",
        by="rider_id",
        direction="backward"
    ).drop(columns="start_date")


def add_category_on_race_date(
        results: pd.DataFrame,
        rider_categories: pd.DataFrame
    ) -> pd.DataFrame:
    """Add the category of the rider on the race date ("A1" to "A4", missing if unknown)."""
    results = add_value_on_race_date(results, rider_categories, "rider_category")
    results["category"] = results["rider_category"].map(
        lambda c: None if pd.isna(c) else f"A{int(c)}"
    )
    return results.drop(columns="rider_category")


def add_category_and_club_on_race_date(
        results: pd.DataFrame,
        clubs: pd.DataFrame,
        affiliations: pd.DataFrame,
        rider_categories: pd.DataFrame
    ) -> pd.DataFrame:
    """Add the category and the club name of the rider on the race date, as labels.

    The category is "A1" to "A4", or UNKNOWN_CATEGORY; the club is the name
    of the club, or UNKNOWN_CLUB. The results are sorted by race date.
    """
    results = add_category_on_race_date(results, rider_categories)
    results = add_value_on_race_date(results, affiliations, "club_id")
    # astype(object): a column of unknown categories only keeps the integer dtype of the history
    results["category"] = results["category"].astype(object).fillna(UNKNOWN_CATEGORY).astype(str)
    results["club"] = (
        results["club_id"].map(clubs.set_index("club_id")["name"]).fillna(UNKNOWN_CLUB)
    )
    return results.drop(columns="club_id")


def compute_places(results: pd.DataFrame) -> pd.Series:
    """Place of each result in its race, from the finish ranks of the results kept.

    The riders removed before (absent from `results`) are skipped: the riders
    behind them move up. Tied riders share the place and the next one is
    skipped (1, 2, 2, 4).
    """
    return results.groupby("race_id")["finish_rank"].rank(method="min").astype(int)


def count_wins_and_tops(rider_results: pd.DataFrame) -> pd.DataFrame:
    """Number of races, wins and tops of each rider and season.

    Args:
        rider_results: Results with rider_id, season and finish_rank, such as
            the output of get_rider_results of rider_profile (one or several riders).

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


def scale_points(results: pd.DataFrame, scale: tuple[int, ...]) -> pd.Series:
    """Points of each result: those of its place in the scale.

    A result gets 0 beyond the last place of the scale, or if its category is unknown.
    """
    points = results["place"].map(lambda p: scale[p - 1] if p <= len(scale) else 0)
    return points.where(results["category"].notna(), 0)


def select_club(clubs_by_date: pd.Series) -> str:
    """Club shown in a ranking: the first one of the year, unless it is an individual licence.

    In that case, the first club that follows is shown, if any.
    """
    regular_clubs = clubs_by_date[~individual_club_id_mask(clubs_by_date)]
    return regular_clubs.iloc[0] if not regular_clubs.empty else clubs_by_date.iloc[0]


def rank_scoring_riders(
        scoring: pd.DataFrame,
        riders: pd.DataFrame,
        clubs: pd.DataFrame,
        max_place: int
    ) -> pd.DataFrame:
    """Rank the riders of each category by their total of points.

    Ties in points are broken by the numbers of 1st, 2nd... `max_place`-th
    places, then by last name and first name.

    Args:
        scoring: Results with points (race_id, race_date, rider_id, club_id,
            place, category, points), sorted by date.
        riders: Rider table.
        clubs: Club table.
        max_place: Last place of the scale.

    Returns:
        One row per category and rider: category, rank, points, last_name,
        first_name, club (see select_club), nb_scoring_races, nb_wins, rider_id
        and club_id; sorted by category and rank.
    """
    place_columns = [f"nb_places_{p}" for p in range(1, max_place + 1)]
    place_counts = (
        pd.crosstab([scoring["category"], scoring["rider_id"]], scoring["place"])
        .reindex(columns=range(1, max_place + 1), fill_value=0)
        .set_axis(place_columns, axis=1)
    )
    totals = scoring.groupby(["category", "rider_id"]).agg(
        points=("points", "sum"),
        nb_scoring_races=("race_id", "nunique"),
        club_id=("club_id", select_club)  # scoring is sorted by date
    )
    ranking = (
        totals
        .join(place_counts)
        .reset_index()
        .merge(riders[["rider_id", "last_name", "first_name"]], on="rider_id", how="left")
        .merge(
            clubs[["club_id", "name"]].rename(columns={"name": "club"}), on="club_id", how="left"
        )
        .sort_values(
            ["category", "points", *place_columns, "last_name", "first_name"],
            ascending=[True, False, *[False] * max_place, True, True]
        )
    )
    ranking["rank"] = ranking.groupby("category").cumcount() + 1
    ranking["nb_wins"] = ranking["nb_places_1"]
    columns = [
        "category", "rank", "points", "last_name", "first_name", "club",
        "nb_scoring_races", "nb_wins", "rider_id", "club_id"
    ]
    return ranking[columns].reset_index(drop=True)


def select_category(rankings: pd.DataFrame, category: str) -> pd.DataFrame:
    """Rows of one category of rankings, without the category column.

    Raises:
        ValueError: If the category is not one of "A1" to "A4".
    """
    if category not in CATEGORIES:
        raise ValueError(f"Unknown category: {category!r} (expected one of {CATEGORIES})")
    return (
        rankings[rankings["category"] == category]
        .drop(columns="category")
        .reset_index(drop=True)
    )
