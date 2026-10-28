"""Building blocks shared by the rankings of the analytics package.

Used by the regional challenge (regional_rankings) and by the promotion points
(promotion_points): category and club of a rider on the race date, places in
a race, points of a scale, ranking of the riders with its tie-breaks, and
filter on a category.
"""

import pandas as pd

from access_it.etl.extract.clubs import individual_club_id_mask

CATEGORIES = ("A1", "A2", "A3", "A4")


def to_datetime(s: pd.Series) -> pd.Series:
    """Dates as datetime64[ns], whatever their input type (string, date, timestamp)."""
    return pd.to_datetime(s).astype("datetime64[ns]")


def get_regional_committee_id(regional_committees: pd.DataFrame, region: str) -> str:
    """ID of the regional committee named `region` (name as in regional_committees).

    Raises:
        ValueError: If the region is unknown.
    """
    is_region = regional_committees["name"] == region
    if not is_region.any():
        raise ValueError(f"Unknown region: {region!r}")
    return regional_committees.loc[is_region, "regional_committee_id"].iloc[0]


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


def compute_places(results: pd.DataFrame) -> pd.Series:
    """Place of each result in its race, from the finish ranks of the results kept.

    The riders removed before (absent from `results`) are skipped: the riders
    behind them move up. Tied riders share the place and the next one is
    skipped (1, 2, 2, 4).
    """
    return results.groupby("race_id")["finish_rank"].rank(method="min").astype(int)


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
