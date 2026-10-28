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

from access_it.analytics.ranking_tools import (
    CATEGORIES, add_category_on_race_date, add_value_on_race_date, compute_places,
    get_regional_committee_id, rank_scoring_riders, scale_points, select_category, to_datetime
)

PAYS_DE_LA_LOIRE = "PAYS DE LA LOIRE"

# Points of the places 1 to 20: 30, 26, 24, 22, 20, then 15 down to 1
POINTS_SCALES = {
    PAYS_DE_LA_LOIRE: (30, 26, 24, 22, 20) + tuple(range(15, 0, -1)),
}

COLUMNS = ["category", "rank", "points", "last_name", "first_name", "club", "nb_scoring_races"]

__all__ = [
    "CATEGORIES", "COLUMNS", "PAYS_DE_LA_LOIRE", "POINTS_SCALES", "compute_challenge_points",
    "compute_regional_rankings", "get_category_ranking"
]


def _get_region_id(regional_committees: pd.DataFrame, region: str) -> str:
    """ID of the regional committee named `region`.

    Raises:
        ValueError: If the region is unknown or has no configured points scale.
    """
    region_id = get_regional_committee_id(regional_committees, region)
    if region not in POINTS_SCALES:
        raise ValueError(f"No regional ranking configured for the region {region!r}")
    return region_id


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

    # Races of the season held in the departements of the region
    region_departements = departemental_committees.loc[
        departemental_committees["regional_committee_id"] == region_id, "departement_code"
    ]
    region_races = races.loc[
        (races["season"] == season) & races["departement_code"].isin(region_departements),
        ["race_id", "race_date"]
    ].assign(race_date=lambda df: to_datetime(df["race_date"]))

    results = rankings[["race_id", "rider_id", "finish_rank"]].merge(region_races, on="race_id")

    # Riders of the region on the race date
    results = add_value_on_race_date(results, affiliations, "club_id")
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

    # Place in the challenge; category on the race date; unknown category: place kept, no points
    results["place"] = compute_places(results)
    results = add_category_on_race_date(results, rider_categories)
    results["points"] = scale_points(results, POINTS_SCALES[region])

    columns = ["race_id", "race_date", "rider_id", "club_id", "place", "category", "points"]
    return results[columns].sort_values(["race_date", "race_id", "place"]).reset_index(drop=True)


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
    ranking = rank_scoring_riders(scoring, riders, clubs, max_place=len(POINTS_SCALES[region]))
    return ranking[COLUMNS]


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
    return select_category(regional_rankings, category)
