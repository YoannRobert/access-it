"""Unit tests of the summary of a race."""

import pandas as pd
import pytest

from access_it.analytics.labels import UNKNOWN_CATEGORY, UNKNOWN_CLUB
from access_it.analytics.race_summary import (
    HEADER_EXTRA_COLUMNS, RANKING_COLUMNS, RaceSummary, compute_race_summary, get_race_header,
    get_race_ranking
)
from access_it.common.seasons import FIRST_SEASON

RACE_DATE = f"{FIRST_SEASON}-06-01"

RACES = pd.DataFrame({
    "race_id": ["r1", "r2", "r3"],
    "title": ["r1 title", "r2 title", "r3 title"],
    "season": [FIRST_SEASON] * 3,
    "race_date": [RACE_DATE, RACE_DATE, f"{FIRST_SEASON}-07-01"],
    "departement_code": ["44", "44", "999"],
})
DEPARTEMENTS = pd.DataFrame({
    "departement_code": ["44", "999"],
    "departement_name": ["Departement 44", "Other"],
})
DEPARTEMENTAL_COMMITTEES = pd.DataFrame({
    "departemental_committee_id": ["5244"],
    "regional_committee_id": ["52"],
    "departement_code": ["44"],
})
REGIONAL_COMMITTEES = pd.DataFrame({"regional_committee_id": ["52"], "name": ["Region 52"]})
CLUBS = pd.DataFrame({"club_id": ["5244001"], "name": ["Club Nantes"]})
RIDERS = pd.DataFrame({
    "rider_id": ["a", "b", "c", "d", "e"],
    "last_name": ["B", "A", "A", "A", "C"],
    "first_name": ["x", "y", "x", "x", "x"],
})
RANKINGS = pd.DataFrame({
    "race_id": ["r1"] * 5 + ["r2"],
    "rider_id": ["e", "a", "b", "d", "c", "a"],
    "finish_rank": [5, 2, 2, 2, 2, 1],
})
AFFILIATIONS = pd.DataFrame({
    "rider_id": ["a", "a", "b"],
    "start_date": [f"{FIRST_SEASON}-01-01", f"{FIRST_SEASON}-07-01", f"{FIRST_SEASON}-01-01"],
    "club_id": ["5244001", "5244002", "5244001"],
})
RIDER_CATEGORIES = pd.DataFrame({
    "rider_id": ["a", "a", "b", "c"],
    "start_date": [
        f"{FIRST_SEASON}-01-01", f"{FIRST_SEASON}-07-01", f"{FIRST_SEASON}-01-01",
        f"{FIRST_SEASON}-01-01"
    ],
    "rider_category": pd.array([3, 2, 4, None], dtype="Int64"),
})


def ranking_of(race_id: str) -> pd.DataFrame:
    """Ranking of a race of the tables."""
    return get_race_ranking(
        RACES, RANKINGS, RIDERS, CLUBS, AFFILIATIONS, RIDER_CATEGORIES, race_id
    )


def header_of(race_id: str) -> pd.DataFrame:
    """Header of a race of the tables."""
    return get_race_header(
        RACES, DEPARTEMENTS, DEPARTEMENTAL_COMMITTEES, REGIONAL_COMMITTEES, race_id
    )


def test_ranking_keeps_the_stored_finish_ranks_and_orders_ties_by_names_then_rider_id():
    ranking = ranking_of("r1")
    assert ranking.columns.tolist() == RANKING_COLUMNS
    assert ranking[["rider_id", "finish_rank"]].values.tolist() == [
        ["c", 2], ["d", 2], ["b", 2], ["a", 2], ["e", 5]
    ]
    assert (ranking["race_id"] == "r1").all()


def test_ranking_with_category_and_club_on_the_race_date_and_unknown_labels():
    ranking = ranking_of("r1").set_index("rider_id")
    assert ranking.loc[["a", "b", "c", "e"], ["category", "club"]].values.tolist() == [
        ["A3", "Club Nantes"], ["A4", "Club Nantes"], [UNKNOWN_CATEGORY, UNKNOWN_CLUB],
        [UNKNOWN_CATEGORY, UNKNOWN_CLUB]
    ]


def test_header_adds_the_departement_and_the_regional_committee():
    header = header_of("r1")
    assert header.columns.tolist() == [*RACES.columns, *HEADER_EXTRA_COLUMNS]
    assert header[["race_id", *HEADER_EXTRA_COLUMNS]].values.tolist() == [
        ["r1", "Departement 44", "Region 52"]
    ]


def test_header_without_regional_committee_is_empty():
    header = header_of("r3")
    assert header["departement_name"].iloc[0] == "Other"
    assert pd.isna(header["regional_committee"].iloc[0])


def test_unknown_race_raises():
    with pytest.raises(ValueError, match="Unknown race"):
        header_of("r9")
    with pytest.raises(ValueError, match="Unknown race"):
        ranking_of("r9")


def test_summary_gathers_the_header_and_the_ranking():
    summary = compute_race_summary(
        RACES, RANKINGS, RIDERS, CLUBS, DEPARTEMENTS, DEPARTEMENTAL_COMMITTEES,
        REGIONAL_COMMITTEES, AFFILIATIONS, RIDER_CATEGORIES, "r1"
    )
    assert isinstance(summary, RaceSummary)
    pd.testing.assert_frame_equal(summary.header, header_of("r1"))
    pd.testing.assert_frame_equal(summary.ranking, ranking_of("r1"))
