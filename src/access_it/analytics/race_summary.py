"""Summary of a race: header and complete ranking.

Rules:

- the ranking is the one of the race as stored, with the absolute finish
  rank: no rider is removed and no ranking by category is computed;
- the category and the club of each rider are those on the race date
  (UNKNOWN_CATEGORY or UNKNOWN_CLUB if unknown);
- tied riders are ordered by last name, first name, then rider_id;
- the header keeps every column of the race, plus the name of its
  departement and of its regional committee (empty if none).

The functions select the race by race_id only. The computation is free of any
Streamlit dependency.
"""

from dataclasses import dataclass

import pandas as pd

from access_it.analytics.ranking_tools import add_category_and_club_on_race_date, to_datetime

HEADER_EXTRA_COLUMNS = ["departement_name", "regional_committee"]
RANKING_COLUMNS = [
    "race_id", "finish_rank", "rider_id", "last_name", "first_name", "category", "club"
]


@dataclass(frozen=True)
class RaceSummary:
    """Summary of a race (see the functions of the module for the columns).

    Attributes:
        header: Output of get_race_header.
        ranking: Output of get_race_ranking.
    """
    header: pd.DataFrame
    ranking: pd.DataFrame


def _get_race(races: pd.DataFrame, race_id: str) -> pd.DataFrame:
    """Row of the race in the race table.

    Raises:
        ValueError: If the race is unknown.
    """
    race = races[races["race_id"] == race_id]
    if race.empty:
        raise ValueError(f"Unknown race: {race_id!r}")
    return race.reset_index(drop=True)


def get_race_header(
        races: pd.DataFrame,
        departements: pd.DataFrame,
        departemental_committees: pd.DataFrame,
        regional_committees: pd.DataFrame,
        race_id: str
    ) -> pd.DataFrame:
    """Header of a race.

    Args:
        races: Race table.
        departements: Departement table.
        departemental_committees: Departemental committee table.
        regional_committees: Regional committee table.
        race_id: Race to show.

    Returns:
        One row: the columns of the race table, in their order, then the
        HEADER_EXTRA_COLUMNS (name of the departement of the race and of its
        regional committee, empty if none).

    Raises:
        ValueError: If the race is unknown.
    """
    committees = (
        departemental_committees[["departement_code", "regional_committee_id"]]
        .merge(regional_committees[["regional_committee_id", "name"]], on="regional_committee_id")
        .rename(columns={"name": "regional_committee"})
    )
    header = (
        _get_race(races, race_id)
        .merge(
            departements[["departement_code", "departement_name"]],
            on="departement_code", how="left"
        )
        .merge(
            committees[["departement_code", "regional_committee"]],
            on="departement_code", how="left"
        )
    )
    return header[[*races.columns, *HEADER_EXTRA_COLUMNS]]


def get_race_ranking(
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        riders: pd.DataFrame,
        clubs: pd.DataFrame,
        affiliations: pd.DataFrame,
        rider_categories: pd.DataFrame,
        race_id: str
    ) -> pd.DataFrame:
    """Complete ranking of a race, with the absolute finish ranks as stored.

    Args:
        races: Race table.
        rankings: Ranking table.
        riders: Rider table.
        clubs: Club table.
        affiliations: Affiliation table (club history of the riders).
        rider_categories: Category history of the riders.
        race_id: Race to show.

    Returns:
        One row per ranked rider: the RANKING_COLUMNS, with the category
        ("A1" to "A4") and the club name of the rider on the race date
        (UNKNOWN_CATEGORY or UNKNOWN_CLUB if unknown); sorted by finish rank,
        then last name, first name and rider_id.

    Raises:
        ValueError: If the race is unknown.
    """
    results = (
        rankings.loc[rankings["race_id"] == race_id, ["race_id", "rider_id", "finish_rank"]]
        .merge(_get_race(races, race_id)[["race_id", "race_date"]], on="race_id")
        .assign(race_date=lambda df: to_datetime(df["race_date"]))
    )
    ranked_rider_ids = results["rider_id"]
    results = add_category_and_club_on_race_date(
        results,
        clubs,
        affiliations[affiliations["rider_id"].isin(ranked_rider_ids)],
        rider_categories[rider_categories["rider_id"].isin(ranked_rider_ids)]
    )
    return (
        results
        .merge(riders[["rider_id", "last_name", "first_name"]], on="rider_id", how="left")
        [RANKING_COLUMNS]
        .sort_values(["finish_rank", "last_name", "first_name", "rider_id"])
        .reset_index(drop=True)
    )


def compute_race_summary(
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        riders: pd.DataFrame,
        clubs: pd.DataFrame,
        departements: pd.DataFrame,
        departemental_committees: pd.DataFrame,
        regional_committees: pd.DataFrame,
        affiliations: pd.DataFrame,
        rider_categories: pd.DataFrame,
        race_id: str
    ) -> RaceSummary:
    """Summary of a race (see the module docstring for the rules).

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
        race_id: Race to show.

    Returns:
        The RaceSummary of the race.

    Raises:
        ValueError: If the race is unknown.
    """
    return RaceSummary(
        header=get_race_header(
            races, departements, departemental_committees, regional_committees, race_id
        ),
        ranking=get_race_ranking(
            races, rankings, riders, clubs, affiliations, rider_categories, race_id
        ),
    )
