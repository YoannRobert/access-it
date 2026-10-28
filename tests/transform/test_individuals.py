"""Unit tests of the committee of the individual licensees of unknown committee."""

import pandas as pd

from access_it.etl.extract.constants import INDIVIDUAL_CLUB_ID
from access_it.etl.transform.individuals import (
    DEDUCED_FROM_RACES, OBSERVED_IN_NEAREST_SEASON, OBSERVED_IN_SEASON,
    assign_individual_committees, resolve_individual_committees
)

REGION_BY_COMMITTEE = {"5244": "52", "5285": "52", "4356": "43", "4950": "49"}


def observations(*rows: tuple) -> pd.DataFrame:
    """Observations from (season, date, location, observed) tuples of the rider r1."""
    return pd.DataFrame(
        [
            {
                "rider_id": "r1", "season": s, "race_date": pd.Timestamp(d),
                "location": loc, "observed": obs,
            }
            for s, d, loc, obs in rows
        ],
        columns=["rider_id", "season", "race_date", "location", "observed"],
    )


def resolve(*rows: tuple, season: int = 2026):
    found = resolve_individual_committees(
        observations(*rows), {("r1", season)}, REGION_BY_COMMITTEE
    )
    return found.get(("r1", season))


def test_committee_observed_in_the_season_comes_first():
    assert resolve(
        (2025, "2025-05-01", "5244", "5285"),
        (2026, "2026-05-01", "5244", None),
        (2026, "2026-06-01", "4950", "4950"),
    ) == ("4950", OBSERVED_IN_SEASON)


def test_committee_observed_in_the_nearest_season_prefers_the_previous_one():
    assert resolve(
        (2024, "2024-05-01", "5244", "5285"),
        (2025, "2025-05-01", "5244", "4356"),
        (2026, "2026-05-01", "5244", None),
        (2027, "2027-05-01", "5244", "4950"),
    ) == ("4356", OBSERVED_IN_NEAREST_SEASON)


def test_committee_deduced_from_the_region_then_the_committee_where_he_raced_most():
    # Pays de la Loire: 3 races (2 in 5285), Bretagne: 2 races
    assert resolve(
        (2026, "2026-03-01", "5244", None),
        (2026, "2026-04-01", "5285", None),
        (2026, "2026-05-01", "5285", None),
        (2026, "2026-06-01", "4356", None),
        (2026, "2026-07-01", "4356", None),
    ) == ("5285", DEDUCED_FROM_RACES)


def test_tie_between_regions_is_broken_by_all_seasons_then_by_the_most_recent_race():
    # Tie in the season, Normandie first over all the seasons
    assert resolve(
        (2025, "2025-05-01", "4950", None),
        (2026, "2026-05-01", "5244", None),
        (2026, "2026-06-01", "4950", None),
    ) == ("4950", DEDUCED_FROM_RACES)
    # Tie in the season and over all the seasons: region of the most recent race
    assert resolve(
        (2026, "2026-05-01", "4950", None),
        (2026, "2026-06-01", "5244", None),
    ) == ("5244", DEDUCED_FROM_RACES)


def test_rider_without_any_result_is_not_found():
    assert resolve_individual_committees(observations(), {("r1", 2026)}, REGION_BY_COMMITTEE) == {}


# ---------------------------------------------------------------- assign_individual_committees

DEPARTEMENTS = pd.DataFrame({
    "departement_code": ["44", "85", "56", "50"],
    "departement_name": ["Loire-Atlantique", "Vendée", "Morbihan", "Manche"],
})
COMMITTEES = pd.DataFrame({
    "departemental_committee_id": ["5244", "5285", "4356", "4950"],
    "name": ["LOIRE-ATLANTIQUE", "VENDEE", "MORBIHAN", "MANCHE"],
    "regional_committee_id": ["52", "52", "43", "49"],
    "departement_code": ["44", "85", "56", "50"],
})
CLUBS = pd.DataFrame({
    "club_id": [INDIVIDUAL_CLUB_ID],
    "name": ["Individuel"],
    "departemental_committee_id": ["9898"],
    "min_year": [2026],
    "max_year": [2026],
    "alternative_names": [""],
})


def national_race(race_id: str, departement: str, *results: tuple) -> dict:
    """Race of another region with (uci_id, last_name, first_name, club) results."""
    return {
        "race_id": race_id, "season": 2026, "race_date": "2026-06-01", "departement": departement,
        "ranking_data": [
            {"finish_rank": k + 1, "uci_id": u, "last_name": ln, "first_name": fn, "club": c}
            for k, (u, ln, fn, c) in enumerate(results)
        ],
    }


def test_results_of_unknown_committee_get_the_pseudo_club_of_the_committee_found():
    results = pd.DataFrame({
        "race_id": ["a", "b", "c"],
        "rider_id": ["r1", "r1", "r2"],
        "season": [2026, 2026, 2026],
        "race_date": ["2026-05-01", "2026-05-08", "2026-05-01"],
        "club_id": [INDIVIDUAL_CLUB_ID, INDIVIDUAL_CLUB_ID, INDIVIDUAL_CLUB_ID],
        "uci_id": ["10000000001", "10000000001", ""],
        "last_name": ["DUPONT", "DUPONT", "MARTIN"],
        "first_name": ["Jean", "Jean", "Paul"],
        "finish_rank": [1, 2, 3],
    })
    races = pd.DataFrame({"race_id": ["a", "b", "c"], "departement_code": ["44", "44", "56"]})
    national = [
        # r1 races three times in Manche: his region is Normandie
        national_race("n1", "Manche", ("10000000001", "DUPONT", "Jean", "Individuel")),
        national_race("n2", "Manche", ("10000000001", "DUPONT", "Jean", "Individuel")),
        national_race("n3", "Manche", ("10000000001", "DUPONT", "Jean", "Individuel")),
        # r2 is matched by names and holds an individual license ID of Vendée
        national_race("n4", "Manche", ("", "Martin", "PAUL", "5285800 - COMITE DE VENDEE")),
        # a race already in the race table is skipped
        national_race("a", "Manche", ("", "MARTIN", "Paul", "4950800")),
    ]
    df, clubs = assign_individual_committees(
        results, races, national, CLUBS, DEPARTEMENTS, COMMITTEES
    )
    assert df["club_id"].tolist() == ["4950800", "4950800", "5285800"]
    added = clubs.set_index("club_id").loc[
        ["4950800", "5285800"], ["name", "departemental_committee_id"]
    ]
    assert added.values.tolist() == [["Individuel 50", "4950"], ["Individuel 85", "5285"]]
