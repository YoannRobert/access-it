"""Unit tests of the head to head of two riders."""

import pandas as pd
import pytest

from access_it.analytics.head_to_head import (
    COMMON_RACE_COLUMNS, HEAD_TO_HEAD_SUMMARY_COLUMNS, HeadToHead, compute_head_to_head,
    get_common_races
)
from access_it.common.seasons import FIRST_SEASON

SEASON = FIRST_SEASON + 1
REFERENCE_DATE = f"{SEASON}-10-01"

RIDERS = pd.DataFrame({"rider_id": ["a", "b", "c"]})
CLUBS = pd.DataFrame({"club_id": ["5244001", "5385001"], "name": ["Club Nantes", "Club Vannes"]})
AFFILIATIONS = pd.DataFrame({
    "rider_id": ["a", "b"],
    "start_date": [f"{FIRST_SEASON}-01-01"] * 2,
    "club_id": ["5244001", "5385001"],
})
RIDER_CATEGORIES = pd.DataFrame({
    "rider_id": ["a", "b"],
    "start_date": [f"{FIRST_SEASON}-01-01"] * 2,
    "rider_category": pd.array([2, 3], dtype="Int64"),
})


def make_tables(races: list[tuple], results: list[tuple]) -> dict:
    """Race and ranking tables from (race_id, race_date) and (race_id, rider_id, finish_rank)."""
    races = pd.DataFrame(races, columns=["race_id", "race_date"])
    return {
        "races": races.assign(
            season=pd.to_datetime(races["race_date"]).dt.year, title=races["race_id"] + " title"
        ),
        "rankings": pd.DataFrame(results, columns=["race_id", "rider_id", "finish_rank"]),
    }


def head_to_head_of(
        tables: dict,
        rider_id: str = "a",
        opponent_id: str = "b",
        reference_date: str = REFERENCE_DATE,
        season: int | None = None
    ) -> HeadToHead:
    """Head to head of two riders of the tables."""
    return compute_head_to_head(
        tables["races"], tables["rankings"], RIDERS, CLUBS, AFFILIATIONS, RIDER_CATEGORIES,
        rider_id, opponent_id, reference_date, season
    )


def test_common_races_keep_only_the_races_of_both_riders():
    tables = make_tables(
        races=[("r1", f"{SEASON}-03-01"), ("r2", f"{SEASON}-04-01"), ("r3", f"{SEASON}-05-01")],
        results=[("r1", "a", 3), ("r1", "b", 8), ("r2", "a", 1), ("r3", "b", 2)],
    )
    common_races = head_to_head_of(tables).races
    assert common_races.columns.tolist() == COMMON_RACE_COLUMNS
    assert common_races.drop(columns="race_date").values.tolist() == [
        ["a", "b", SEASON, "r1", "r1 title", 3, "A2", "Club Nantes", 8, "A3", "Club Vannes"]
    ]


def test_summary_counts_the_riders_ahead_and_the_ties_whatever_the_ranks():
    tables = make_tables(
        races=[(f"r{i}", f"{SEASON}-0{i}-01") for i in range(1, 5)],
        results=[
            ("r1", "a", 2), ("r1", "b", 5), ("r2", "a", 1), ("r2", "b", 150),
            ("r3", "a", 7), ("r3", "b", 3), ("r4", "a", 4), ("r4", "b", 4),
        ],
    )
    summary = head_to_head_of(tables).summary
    assert summary.columns.tolist() == HEAD_TO_HEAD_SUMMARY_COLUMNS
    assert summary.values.tolist() == [["a", "b", 4, 2, 1, 1]]


def test_common_races_from_the_most_recent_then_by_race_id():
    tables = make_tables(
        races=[("r1", f"{SEASON}-03-01"), ("r2", f"{SEASON}-06-01"), ("r3", f"{SEASON}-06-01")],
        results=[
            (r, rider, rank) for r in ("r1", "r2", "r3") for rider, rank in (("a", 1), ("b", 2))
        ],
    )
    assert head_to_head_of(tables).races["race_id"].tolist() == ["r3", "r2", "r1"]


def test_common_races_of_a_season_before_the_reference_date():
    tables = make_tables(
        races=[
            ("r1", f"{FIRST_SEASON}-06-01"), ("r2", f"{SEASON}-06-01"), ("r3", REFERENCE_DATE)
        ],
        results=[
            (r, rider, rank) for r in ("r1", "r2", "r3") for rider, rank in (("a", 1), ("b", 2))
        ],
    )
    assert head_to_head_of(tables).races["race_id"].tolist() == ["r2", "r1"]
    assert head_to_head_of(tables, season=SEASON).races["race_id"].tolist() == ["r2"]
    assert head_to_head_of(tables, season=FIRST_SEASON).races["race_id"].tolist() == ["r1"]


def test_no_common_race_gives_an_empty_list_and_a_zero_summary():
    tables = make_tables(
        races=[("r1", f"{SEASON}-03-01"), ("r2", f"{SEASON}-04-01")],
        results=[("r1", "a", 1), ("r2", "b", 1)],
    )
    head_to_head = head_to_head_of(tables, opponent_id="c")
    assert head_to_head.races.empty
    assert head_to_head.races.columns.tolist() == COMMON_RACE_COLUMNS
    assert head_to_head.summary.values.tolist() == [["a", "c", 0, 0, 0, 0]]


@pytest.mark.parametrize(("rider_id", "opponent_id", "season", "message"), [
    ("a", "a", None, "Same rider and opponent"),
    ("x", "b", None, "Unknown rider: 'x'"),
    ("a", "x", None, "Unknown rider: 'x'"),
    ("a", "b", FIRST_SEASON - 1, "is before the first season"),
    ("a", "b", SEASON + 1, "is after the year of the reference date"),
])
def test_invalid_arguments_raise(rider_id, opponent_id, season, message):
    tables = make_tables(races=[("r1", f"{SEASON}-03-01")], results=[("r1", "a", 1)])
    with pytest.raises(ValueError, match=message):
        get_common_races(
            tables["races"], tables["rankings"], RIDERS, CLUBS, AFFILIATIONS, RIDER_CATEGORIES,
            rider_id, opponent_id, REFERENCE_DATE, season
        )


MISSING_DATES = [
    ("races", "race_date", "Missing race dates in the results"),
    ("rider_categories", "start_date", "Missing start dates in the history"),
    ("affiliations", "start_date", "Missing start dates in the history"),
]


def head_to_head_tables() -> dict:
    """Tables of one race of riders a and b."""
    tables = make_tables(
        races=[("r1", f"{SEASON}-03-01")], results=[("r1", "a", 1), ("r1", "b", 2)]
    )
    return tables | {
        "affiliations": AFFILIATIONS.copy(), "rider_categories": RIDER_CATEGORIES.copy()
    }


def head_to_head_args(tables: dict) -> tuple:
    """Positional arguments of get_common_races and compute_head_to_head for riders a and b."""
    return (
        tables["races"], tables["rankings"], RIDERS, CLUBS, tables["affiliations"],
        tables["rider_categories"], "a", "b", REFERENCE_DATE
    )


@pytest.mark.parametrize("table, column, message", MISSING_DATES)
def test_common_races_missing_date_raises(table, column, message):
    tables = head_to_head_tables()
    tables[table].loc[0, column] = None
    with pytest.raises(ValueError, match=message):
        get_common_races(*head_to_head_args(tables))


def test_common_races_missing_race_date_raises_before_missing_start_date():
    tables = head_to_head_tables()
    tables["races"].loc[0, "race_date"] = None
    tables["rider_categories"].loc[0, "start_date"] = None
    with pytest.raises(ValueError, match="Missing race dates in the results"):
        get_common_races(*head_to_head_args(tables))


@pytest.mark.parametrize("table, column, message", MISSING_DATES)
def test_head_to_head_missing_date_raises(table, column, message):
    tables = head_to_head_tables()
    tables[table].loc[0, column] = None
    with pytest.raises(ValueError, match=message):
        compute_head_to_head(*head_to_head_args(tables))


def test_head_to_head_missing_race_date_raises_before_missing_start_date():
    tables = head_to_head_tables()
    tables["races"].loc[0, "race_date"] = None
    tables["rider_categories"].loc[0, "start_date"] = None
    with pytest.raises(ValueError, match="Missing race dates in the results"):
        compute_head_to_head(*head_to_head_args(tables))


@pytest.mark.parametrize("table", ["rider_categories", "affiliations"])
def test_common_races_without_a_kept_race_ignore_the_missing_start_dates(table):
    tables = head_to_head_tables()
    tables["races"].loc[0, "race_date"] = f"{SEASON}-11-01"
    tables[table].loc[0, "start_date"] = None
    assert get_common_races(*head_to_head_args(tables)).empty


@pytest.mark.parametrize("table", ["rider_categories", "affiliations"])
def test_head_to_head_without_a_kept_race_ignores_the_missing_start_dates(table):
    tables = head_to_head_tables()
    tables["races"].loc[0, "race_date"] = f"{SEASON}-11-01"
    tables[table].loc[0, "start_date"] = None
    head_to_head = compute_head_to_head(*head_to_head_args(tables))
    assert head_to_head.races.empty
    counts = ["nb_common_races", "nb_rider_ahead", "nb_opponent_ahead", "nb_ties"]
    assert head_to_head.summary.loc[0, counts].tolist() == [0, 0, 0, 0]
