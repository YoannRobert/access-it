"""Unit tests of the ranking of the clubs."""

import pandas as pd
import pytest

from access_it.analytics.club_rankings import (
    CLUB_RANKING_COLUMNS, compute_club_rankings, get_club_results, rank_clubs
)
from access_it.common.regions import BRETAGNE, PAYS_DE_LA_LOIRE
from access_it.common.seasons import FIRST_SEASON
from access_it.etl.extract.constants import FOREIGN_CLUB_ID, INDIVIDUAL_CLUB_ID

SEASON = FIRST_SEASON + 1
NOT_COVERED_REGION = "NORMANDIE"

REGIONAL_COMMITTEES = pd.DataFrame({
    "regional_committee_id": ["52", "53", "54"],
    "name": [PAYS_DE_LA_LOIRE, BRETAGNE, NOT_COVERED_REGION],
})
DEPARTEMENTAL_COMMITTEES = pd.DataFrame({
    "departemental_committee_id": ["5244", "5285", "5356", "5414"],
    "regional_committee_id": ["52", "52", "53", "54"],
    "departement_code": ["44", "85", "56", "14"],
})
# The name of the departement 85 is unknown
DEPARTEMENTS = pd.DataFrame({
    "departement_code": ["44", "56", "14"],
    "departement_name": ["Loire-Atlantique", "Morbihan", "Calvados"],
})
# 5244003 disappeared before the season; 5244800, INDIVIDUAL_CLUB_ID and
# FOREIGN_CLUB_ID are pseudo-clubs
CLUBS = pd.DataFrame({
    "club_id": [
        "5244001", "5285001", "5356001", "5244002", "5244003", "5244800",
        INDIVIDUAL_CLUB_ID, FOREIGN_CLUB_ID
    ],
    "name": [
        "Club Nantes", "Club Atlantique", "Club Vannes", "Club Zero", "Club Gone",
        "Individuel 44", "Individuel", "Etranger"
    ],
    "departemental_committee_id": [
        "5244", "5285", "5356", "5244", "5244", "5244", "5244", "5244"
    ],
    "min_year": [FIRST_SEASON] * 8,
    "max_year": [SEASON, SEASON, SEASON, SEASON, FIRST_SEASON, SEASON, SEASON, SEASON],
})
# r2 is held in Bretagne, r3 in the previous season
RACES = pd.DataFrame({
    "race_id": ["r1", "r2", "r3"],
    "season": [SEASON, SEASON, FIRST_SEASON],
    "race_date": [f"{SEASON}-03-10", f"{SEASON}-06-01", f"{FIRST_SEASON}-06-01"],
    "departement_code": ["44", "56", "44"],
    "categories": ["A1,A2", "A3,A4", "A1"],
})
RANKINGS = pd.DataFrame(
    [
        ("r1", "a", 1), ("r1", "b", 2), ("r1", "c", 3), ("r1", "d", 4), ("r1", "f", 5),
        ("r2", "b", 1), ("r2", "e", 2), ("r2", "g", 3),
        ("r3", "a", 1),
    ],
    columns=["race_id", "rider_id", "finish_rank"]
)
# b moves from 5285001 to 5244001 on April 1st; d is an individual licensee,
# e a foreign rider, f in a club that disappeared; the club of g is unknown
AFFILIATIONS = pd.DataFrame({
    "rider_id": ["a", "b", "b", "c", "d", "e", "f"],
    "start_date": [
        f"{FIRST_SEASON}-01-01", f"{FIRST_SEASON}-01-01", f"{SEASON}-04-01",
        f"{FIRST_SEASON}-01-01", f"{FIRST_SEASON}-01-01", f"{FIRST_SEASON}-01-01",
        f"{FIRST_SEASON}-01-01"
    ],
    "club_id": ["5244001", "5285001", "5244001", "5356001", "5244800", FOREIGN_CLUB_ID, "5244003"],
})
# a is A1, b A3; the category of c is unknown
RIDER_CATEGORIES = pd.DataFrame({
    "rider_id": ["a", "b"],
    "start_date": [f"{FIRST_SEASON}-01-01", f"{FIRST_SEASON}-01-01"],
    "rider_category": pd.array([1, 3], dtype="Int64"),
})


def club_rankings(**kwargs) -> pd.DataFrame:
    """compute_club_rankings on the test tables, with the given optional arguments."""
    arguments = {"season": SEASON} | kwargs
    return compute_club_rankings(
        RACES, RANKINGS, CLUBS, DEPARTEMENTS, DEPARTEMENTAL_COMMITTEES, REGIONAL_COMMITTEES,
        AFFILIATIONS, RIDER_CATEGORIES, **arguments
    )


def counts(ranking: pd.DataFrame) -> list[list]:
    """Club ID, rank, wins, tops and active riders of each row."""
    columns = [
        "club_id", "rank", "nb_wins", "nb_top_3", "nb_top_5", "nb_top_10", "nb_top_20",
        "nb_active_riders"
    ]
    return ranking[columns].values.tolist()


def test_club_results_of_the_season_in_every_region_with_the_club_on_the_race_date():
    results = get_club_results(RACES, RANKINGS, AFFILIATIONS, SEASON)
    assert results.columns.tolist() == [
        "race_id", "race_date", "categories", "rider_id", "finish_rank", "club_id"
    ]
    assert results[["race_id", "rider_id", "club_id"]].fillna("?").values.tolist() == [
        ["r1", "a", "5244001"], ["r1", "b", "5285001"], ["r1", "c", "5356001"],
        ["r1", "d", "5244800"], ["r1", "f", "5244003"],
        ["r2", "b", "5244001"], ["r2", "e", FOREIGN_CLUB_ID], ["r2", "g", "?"],
    ]


def test_clubs_of_the_region_ranked_with_their_results_in_every_region():
    ranking = club_rankings(region=PAYS_DE_LA_LOIRE)
    assert ranking.columns.tolist() == CLUB_RANKING_COLUMNS
    assert counts(ranking) == [
        ["5244001", 1, 2, 2, 2, 2, 2, 2],
        ["5285001", 2, 0, 1, 1, 1, 1, 1],
        ["5244002", 3, 0, 0, 0, 0, 0, 0],
    ]
    assert ranking["club"].tolist() == ["Club Nantes", "Club Atlantique", "Club Zero"]
    assert ranking["departement_code"].tolist() == ["44", "85", "44"]
    assert ranking["departement_name"].isna().tolist() == [False, True, False]


def test_clubs_of_every_region_tied_on_every_count_share_the_rank():
    ranking = club_rankings()
    assert counts(ranking) == [
        ["5244001", 1, 2, 2, 2, 2, 2, 2],
        ["5285001", 2, 0, 1, 1, 1, 1, 1],
        ["5356001", 2, 0, 1, 1, 1, 1, 1],
        ["5244002", 4, 0, 0, 0, 0, 0, 0],
    ]


def test_active_riders_ignore_the_filter_on_the_categories_of_the_races():
    ranking = club_rankings(region=PAYS_DE_LA_LOIRE, categories=["A4", "A3"])
    assert counts(ranking) == [
        ["5244001", 1, 1, 1, 1, 1, 1, 2],
        ["5285001", 2, 0, 0, 0, 0, 0, 1],
        ["5244002", 2, 0, 0, 0, 0, 0, 0],
    ]


def test_wins_and_tops_filtered_on_the_categories_of_the_riders():
    ranking = club_rankings(region=PAYS_DE_LA_LOIRE, categories=["A3"], category_filter="rider")
    assert counts(ranking) == [
        ["5244001", 1, 1, 1, 1, 1, 1, 2],
        ["5285001", 2, 0, 1, 1, 1, 1, 1],
        ["5244002", 3, 0, 0, 0, 0, 0, 0],
    ]


def test_ranking_cut_at_max_clubs():
    ranking = club_rankings(max_clubs=2)
    assert ranking["club_id"].tolist() == ["5244001", "5285001"]


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"season": FIRST_SEASON - 1}, "before the first season"),
        ({"region": NOT_COVERED_REGION}, "Region not covered"),
        ({"category_filter": "club"}, "Unknown category filter"),
        ({"categories": ["A1", "A3"]}, "Categories not contiguous"),
        ({"max_clubs": 0}, "max_clubs must be at least 1"),
    ]
)
def test_invalid_arguments_raise(kwargs, message):
    with pytest.raises(ValueError, match=message):
        club_rankings(**kwargs)


def test_races_of_the_season_with_non_contiguous_categories_raise():
    races = RACES.assign(categories=["A1,A2", "A2,A4", "A1"])
    with pytest.raises(ValueError, match="non contiguous"):
        get_club_results(races, RANKINGS, AFFILIATIONS, SEASON)


def test_rank_clubs_without_any_result_shows_the_clubs_with_zeros():
    club_results = get_club_results(RACES, RANKINGS, AFFILIATIONS, SEASON).iloc[:0]
    ranking = rank_clubs(
        club_results, CLUBS, DEPARTEMENTS, DEPARTEMENTAL_COMMITTEES, REGIONAL_COMMITTEES,
        RIDER_CATEGORIES, SEASON, region=BRETAGNE
    )
    assert counts(ranking) == [["5356001", 1, 0, 0, 0, 0, 0, 0]]
