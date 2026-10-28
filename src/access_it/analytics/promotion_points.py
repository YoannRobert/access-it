"""Promotion points of the Access riders (points counting for a move up of category).

The points are shown only: they never serve to find or apply a change of
category, which comes from the category history of the riders. Rules:

- every Access race of the season counts, whatever its place or type; the
  points are counted nationally, from the races in the tables (Bretagne and
  Pays de la Loire);
- foreign riders are removed and the riders behind them move up; nobody else
  is removed (riders of any region, individual licensees of unknown committee);
- the first 5 places of each race score 6, 4, 3, 2 and 1 points; tied riders
  share the place and the next place is skipped (1, 2, 2, 4);
- the points go to the category of the rider on the race date: a rider has a
  total in each category he had during the season, and a race adds points to
  one total only; a rider of unknown category keeps his place but scores no points;
- ties in points are broken by the numbers of 1st, 2nd... 5th places, then
  by last name and first name.

A rider belongs to the regions of his clubs on the dates of all his races of
the season, all categories together (individual licensees of unknown
committee belong to none). The region shown is the first one of the season;
the ranking of a region shows the riders of that region with their national
total, ranked again among themselves.

The computation is free of any Streamlit dependency; the dashboard caches
compute_promotion_rankings (one call computes the four categories).
"""

import pandas as pd

from access_it.analytics.ranking_tools import (
    add_category_on_race_date, add_value_on_race_date, compute_places,
    get_regional_committee_id, rank_scoring_riders, scale_points, select_category, to_datetime
)
from access_it.etl.extract.constants import FOREIGN_CLUB_ID, INDIVIDUAL_CLUB_ID

PROMOTION_SCALE = (6, 4, 3, 2, 1)

COLUMNS = [
    "category", "rank", "points", "last_name", "first_name", "club",
    "nb_scoring_races", "nb_wins", "region"
]


def compute_promotion_points(
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        affiliations: pd.DataFrame,
        rider_categories: pd.DataFrame,
        season: int
    ) -> pd.DataFrame:
    """Promotion points of the riders, race by race.

    Args:
        races: Race table.
        rankings: Ranking table.
        affiliations: Affiliation table (club history of the riders).
        rider_categories: Category history of the riders.
        season: Calendar year.

    Returns:
        One row per result of a rider who is not foreign: race_id, race_date,
        rider_id, club_id (on the race date, missing if unknown), place,
        category ("A1" to "A4", missing if unknown) and points (0 beyond the
        5th place or if the category is unknown); sorted by date, race and place.
    """
    season_races = races.loc[races["season"] == season, ["race_id", "race_date"]].assign(
        race_date=lambda df: to_datetime(df["race_date"])
    )
    results = rankings[["race_id", "rider_id", "finish_rank"]].merge(season_races, on="race_id")
    results = add_value_on_race_date(results, affiliations, "club_id")
    results = results[results["club_id"] != FOREIGN_CLUB_ID].copy()
    results["place"] = compute_places(results)
    results = add_category_on_race_date(results, rider_categories)
    results["points"] = scale_points(results, PROMOTION_SCALE)
    columns = ["race_id", "race_date", "rider_id", "club_id", "place", "category", "points"]
    return results[columns].sort_values(["race_date", "race_id", "place"]).reset_index(drop=True)


def _regions_of_riders(
        points: pd.DataFrame,
        clubs: pd.DataFrame,
        departemental_committees: pd.DataFrame,
        regional_committees: pd.DataFrame
    ) -> pd.DataFrame:
    """Regions of each rider: rider_id, region (first one of the season) and regions (all).

    The regions are those of the clubs of the rider on the dates of all his
    races of the season (`points` is sorted by date); individual licensees of
    unknown committee have no region.
    """
    region_name_by_committee = (
        departemental_committees[["departemental_committee_id", "regional_committee_id"]]
        .merge(regional_committees[["regional_committee_id", "name"]], on="regional_committee_id")
        .set_index("departemental_committee_id")["name"]
    )
    df = points[["rider_id", "club_id"]].merge(
        clubs[["club_id", "departemental_committee_id"]], on="club_id", how="left", sort=False
    )
    df["region"] = df["departemental_committee_id"].map(region_name_by_committee)
    df.loc[df["club_id"] == INDIVIDUAL_CLUB_ID, "region"] = None
    df = df.dropna(subset=["region"])
    return df.groupby("rider_id", sort=False).agg(
        region=("region", "first"),
        regions=("region", lambda s: tuple(dict.fromkeys(s)))
    ).reset_index()


def compute_promotion_rankings(
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        riders: pd.DataFrame,
        clubs: pd.DataFrame,
        departemental_committees: pd.DataFrame,
        regional_committees: pd.DataFrame,
        affiliations: pd.DataFrame,
        rider_categories: pd.DataFrame,
        season: int
    ) -> pd.DataFrame:
    """National rankings of the promotion points of the four Access categories.

    See the module docstring for the rules.

    Args:
        races: Race table.
        rankings: Ranking table.
        riders: Rider table.
        clubs: Club table.
        departemental_committees: Departemental committee table.
        regional_committees: Regional committee table.
        affiliations: Affiliation table (club history of the riders).
        rider_categories: Category history of the riders.
        season: Calendar year.

    Returns:
        One row per category and rider having scored points: the COLUMNS
        (club as in the regional rankings, region: first region of the
        season, missing if none) and regions (tuple of all the regions of the
        rider, used by get_promotion_ranking); sorted by category and rank.
    """
    points = compute_promotion_points(races, rankings, affiliations, rider_categories, season)
    scoring = points[points["points"] > 0]
    if scoring.empty:
        return pd.DataFrame(columns=COLUMNS + ["regions"])
    ranking = rank_scoring_riders(scoring, riders, clubs, max_place=len(PROMOTION_SCALE))
    regions = _regions_of_riders(points, clubs, departemental_committees, regional_committees)
    ranking = ranking.merge(regions, on="rider_id", how="left")
    ranking["regions"] = ranking["regions"].map(lambda r: r if isinstance(r, tuple) else ())
    return ranking[COLUMNS + ["regions"]]


def get_promotion_ranking(
        promotion_rankings: pd.DataFrame,
        category: str,
        region: str | None = None,
        regional_committees: pd.DataFrame | None = None
    ) -> pd.DataFrame:
    """Ranking of one category, nationally or for the riders of one region.

    Args:
        promotion_rankings: Output of compute_promotion_rankings.
        category: "A1", "A2", "A3" or "A4".
        region: Name of a regional committee, as in regional_committees, or
            None for the national ranking.
        regional_committees: Regional committee table, to check the region
            name (required with `region`).

    Returns:
        The rows of the category (and of the riders of the region, with their
        national total and a rank among them), without the category and regions columns.

    Raises:
        ValueError: If the category or the region is unknown.
    """
    ranking = select_category(promotion_rankings, category)
    if region is not None:
        if regional_committees is None:
            raise ValueError("regional_committees is required to filter on a region")
        get_regional_committee_id(regional_committees, region)
        ranking = ranking[ranking["regions"].map(lambda regions: region in regions)].copy()
        ranking["rank"] = range(1, len(ranking) + 1)
    return ranking.drop(columns="regions").reset_index(drop=True)
