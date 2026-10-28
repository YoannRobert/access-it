"""Regional Access rankings (regional challenge of the A1, A2, A3 and A4 riders).

A regional committee awards points to its riders in the Access races held in
its departements, over a calendar year. Only the Pays de la Loire challenge is
configured. Its rules:

- a rider counts if, on the race date, his club belongs to the region (for an
  individual licensee, the pseudo-club of his committee); other riders (other
  regions, foreign riders, individual licensees of unknown committee) are
  removed and the riders behind them move up;
- the place in the challenge is the place among the riders who count, all
  categories of the race together (no reranking by category); tied riders
  share the place and the next place is skipped (1, 2, 2, 4);
- points of the scale go to the first 20 places, whatever the number of
  riders ranked, and to the category of the rider on the race date;
- a rider of unknown category keeps his place but scores no points;
- a rider who changes category keeps his points and his place in the
  ranking of the former category and starts from zero in the new one;
- ties in points are broken by the numbers of 1st, 2nd... 20th places,
  then by last name and first name.

The computation is free of any Streamlit dependency; the dashboard caches
compute_regional_rankings (one call computes the four categories).
"""

import pandas as pd

from access_it.etl.extract.clubs import individual_club_id_mask

PAYS_DE_LA_LOIRE = "PAYS DE LA LOIRE"

# Points of the places 1 to 20: 30, 26, 24, 22, 20, then 15 down to 1
POINTS_SCALES = {
    PAYS_DE_LA_LOIRE: (30, 26, 24, 22, 20) + tuple(range(15, 0, -1)),
}

CATEGORIES = ("A1", "A2", "A3", "A4")

COLUMNS = ["category", "rank", "points", "last_name", "first_name", "club", "nb_scoring_races"]


def _to_datetime(s: pd.Series) -> pd.Series:
    """Dates as datetime64[ns], whatever their input type (string, date, timestamp)."""
    return pd.to_datetime(s).astype("datetime64[ns]")


def _get_region_id(regional_committees: pd.DataFrame, region: str) -> str:
    """ID of the regional committee named `region`.

    Raises:
        ValueError: If the region is unknown or has no configured points scale.
    """
    is_region = regional_committees["name"] == region
    if not is_region.any():
        raise ValueError(f"Unknown region: {region!r}")
    if region not in POINTS_SCALES:
        raise ValueError(f"No regional ranking configured for the region {region!r}")
    return regional_committees.loc[is_region, "regional_committee_id"].iloc[0]


def _add_value_on_race_date(
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
        .assign(start_date=lambda df: _to_datetime(df["start_date"]))
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


def compute_challenge_points(
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        clubs: pd.DataFrame,
        departemental_committees: pd.DataFrame,
        regional_committees: pd.DataFrame,
        affiliations: pd.DataFrame,
        rider_categories: pd.DataFrame,
        season: int,
        region: str = PAYS_DE_LA_LOIRE
    ) -> pd.DataFrame:
    """Points scored by the riders counted in the challenge, race by race.

    Args:
        races: Race table.
        rankings: Ranking table.
        clubs: Club table.
        departemental_committees: Departemental committee table.
        regional_committees: Regional committee table.
        affiliations: Affiliation table (club history of the riders).
        rider_categories: Category history of the riders.
        season: Calendar year of the challenge.
        region: Name of the regional committee, as in regional_committees.

    Returns:
        One row per counted rider and race: race_id, race_date, rider_id,
        club_id, place (in the challenge), category ("A1" to "A4", missing if
        unknown) and points (0 beyond the 20th place or if the category is unknown).

    Raises:
        ValueError: If the region is unknown or has no configured points scale.
    """
    region_id = _get_region_id(regional_committees, region)
    scale = POINTS_SCALES[region]

    # Races of the season held in the departements of the region
    region_departements = departemental_committees.loc[
        departemental_committees["regional_committee_id"] == region_id, "departement_code"
    ]
    region_races = races.loc[
        (races["season"] == season) & races["departement_code"].isin(region_departements),
        ["race_id", "race_date"]
    ].assign(race_date=lambda df: _to_datetime(df["race_date"]))

    results = rankings[["race_id", "rider_id", "finish_rank"]].merge(region_races, on="race_id")

    # Riders of the region on the race date
    results = _add_value_on_race_date(results, affiliations, "club_id")
    region_clubs = clubs.loc[
        clubs["departemental_committee_id"].isin(
            departemental_committees.loc[
                departemental_committees["regional_committee_id"] == region_id,
                "departemental_committee_id"
            ]
        ),
        "club_id"
    ]
    results = results[results["club_id"].isin(region_clubs)].copy()

    # Place in the challenge: tied riders share it, the next one is skipped
    results["place"] = (
        results.groupby("race_id")["finish_rank"].rank(method="min").astype(int)
    )

    # Category on the race date; unknown category: place kept, no points
    results = _add_value_on_race_date(results, rider_categories, "rider_category")
    results["category"] = results["rider_category"].map(
        lambda c: None if pd.isna(c) else f"A{int(c)}"
    )
    points = results["place"].map(lambda p: scale[p - 1] if p <= len(scale) else 0)
    results["points"] = points.where(results["category"].notna(), 0)

    columns = ["race_id", "race_date", "rider_id", "club_id", "place", "category", "points"]
    return results[columns].sort_values(["race_date", "race_id", "place"]).reset_index(drop=True)


def _select_club(clubs_by_date: pd.Series) -> str:
    """Club shown in the ranking: the first one of the year, unless it is an individual licence.

    In that case, the first club that follows is shown, if any.
    """
    regular_clubs = clubs_by_date[~individual_club_id_mask(clubs_by_date)]
    return regular_clubs.iloc[0] if not regular_clubs.empty else clubs_by_date.iloc[0]


def compute_regional_rankings(
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        riders: pd.DataFrame,
        clubs: pd.DataFrame,
        departemental_committees: pd.DataFrame,
        regional_committees: pd.DataFrame,
        affiliations: pd.DataFrame,
        rider_categories: pd.DataFrame,
        season: int,
        region: str = PAYS_DE_LA_LOIRE
    ) -> pd.DataFrame:
    """Regional rankings of the four Access categories (see the module docstring for the rules).

    Args:
        races: Race table.
        rankings: Ranking table.
        riders: Rider table.
        clubs: Club table.
        departemental_committees: Departemental committee table.
        regional_committees: Regional committee table.
        affiliations: Affiliation table (club history of the riders).
        rider_categories: Category history of the riders.
        season: Calendar year of the challenge.
        region: Name of the regional committee, as in regional_committees.

    Returns:
        One row per category and rider having scored points: category, rank,
        points, last_name, first_name, club (name of the first club of the year
        with which the rider scored points in the category, the first following
        one for an individual licence) and nb_scoring_races; sorted by category and rank.

    Raises:
        ValueError: If the region is unknown or has no configured points scale.
    """
    points = compute_challenge_points(
        races=races,
        rankings=rankings,
        clubs=clubs,
        departemental_committees=departemental_committees,
        regional_committees=regional_committees,
        affiliations=affiliations,
        rider_categories=rider_categories,
        season=season,
        region=region
    )
    scoring = points[points["points"] > 0]
    if scoring.empty:
        return pd.DataFrame(columns=COLUMNS)

    keys = ["category", "rider_id"]
    max_place = len(POINTS_SCALES[region])
    place_columns = [f"nb_places_{p}" for p in range(1, max_place + 1)]
    place_counts = (
        pd.crosstab([scoring["category"], scoring["rider_id"]], scoring["place"])
        .reindex(columns=range(1, max_place + 1), fill_value=0)
        .set_axis(place_columns, axis=1)
    )
    totals = scoring.groupby(keys).agg(
        points=("points", "sum"),
        nb_scoring_races=("race_id", "nunique"),
        club_id=("club_id", _select_club)  # scoring is sorted by date
    )
    ranking = (
        totals
        .join(place_counts)
        .reset_index()
        .merge(riders[["rider_id", "last_name", "first_name"]], on="rider_id", how="left")
        .merge(clubs[["club_id", "name"]].rename(columns={"name": "club"}), on="club_id", how="left")
        .sort_values(
            ["category", "points", *place_columns, "last_name", "first_name"],
            ascending=[True, False, *[False] * max_place, True, True]
        )
    )
    ranking["rank"] = ranking.groupby("category").cumcount() + 1
    return ranking[COLUMNS].reset_index(drop=True)


def get_category_ranking(regional_rankings: pd.DataFrame, category: str) -> pd.DataFrame:
    """Ranking of one category, from the output of compute_regional_rankings.

    Args:
        regional_rankings: Output of compute_regional_rankings.
        category: "A1", "A2", "A3" or "A4".

    Returns:
        The rows of the category, without the category column.

    Raises:
        ValueError: If the category is not one of "A1" to "A4".
    """
    if category not in CATEGORIES:
        raise ValueError(f"Unknown category: {category!r} (expected one of {CATEGORIES})")
    return (
        regional_rankings[regional_rankings["category"] == category]
        .drop(columns="category")
        .reset_index(drop=True)
    )
