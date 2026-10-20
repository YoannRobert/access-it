"""Unit tests of the checks run before loading data into the database."""

import pandas as pd
import pytest

from sqlalchemy import create_engine, insert

from access_it.etl.load import load
from access_it.etl.load.checks import (
    DataValidationError, check_foreign_keys, check_primary_key, find_existing_values, run_checks
)
from access_it.etl.load.models import Base

TABLES = Base.metadata.tables


def sqlite_engine_with_riders(rider_ids: list[str]):
    """In-memory SQLite database with all tables, holding the given riders."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    if not rider_ids:
        return engine
    with engine.begin() as connection:
        connection.execute(
            insert(TABLES["riders"]),
            [{"rider_id": r, "uci_id": "", "last_name": "X", "first_name": "Y"} for r in rider_ids],
        )
    return engine


class ConnectionThatMustNotBeQueried:
    def execute(self, *args, **kwargs):
        raise AssertionError("The database was queried although it was not needed")


def empty_frames() -> dict[str, pd.DataFrame]:
    """One empty DataFrame per table, with all the table columns."""
    return {
        name: pd.DataFrame(columns=list(table.columns.keys()))
        for name, table in TABLES.items()
    }


# ---------------------------------------------------------------- check_primary_key

def test_primary_key_valid():
    df = pd.DataFrame(
        {"rider_id": ["a", "b"], "uci_id": ["", ""], "last_name": "X", "first_name": "Y"}
    )
    assert check_primary_key(TABLES["riders"], df) == []


def test_primary_key_duplicates_single_column():
    df = pd.DataFrame({"rider_id": ["a", "a", "b", "b", "b", "c"]})
    problems = check_primary_key(TABLES["riders"], df)
    assert len(problems) == 1
    assert "[riders] 3 duplicated primary key(s) (rider_id)" in problems[0]
    assert "'a', 'b'" in problems[0]


def test_primary_key_duplicates_composite_key():
    df = pd.DataFrame({
        "race_id": ["r1", "r1", "r1", "r2"],
        "rider_id": ["a", "a", "b", "a"],
        "finish_rank": [1, 1, 2, 1],
    })
    problems = check_primary_key(TABLES["rankings"], df)
    assert len(problems) == 1
    assert "[rankings] 1 duplicated primary key(s) (race_id, rider_id)" in problems[0]
    assert "('r1', 'a')" in problems[0]


def test_same_rank_for_two_riders_is_allowed():
    # Ties are possible: only (race_id, rider_id) must be unique
    df = pd.DataFrame({"race_id": ["r1", "r1"], "rider_id": ["a", "b"], "finish_rank": [1, 1]})
    assert check_primary_key(TABLES["rankings"], df) == []


def test_primary_key_missing_values():
    df = pd.DataFrame(
        {"rider_id": ["a", None, "a"], "start_date": [pd.NaT, pd.Timestamp("2025-01-01"), None]}
    )
    problems = check_primary_key(TABLES["rider_categories"], df)
    assert any("3 row(s) with a missing primary key value" in p for p in problems)


# ---------------------------------------------------------------- find_existing_values

def test_find_existing_values_returns_only_asked_values_present_in_database():
    engine = sqlite_engine_with_riders(["r1", "r2", "r3"])
    with engine.connect() as connection:
        found = find_existing_values(connection, TABLES["riders"], "rider_id", ["r1", "r9"])
    assert found == {"r1"}


def test_find_existing_values_without_database():
    assert find_existing_values(None, TABLES["riders"], "rider_id", ["r1"]) == set()


# ---------------------------------------------------------------- check_foreign_keys

def affiliations(club_ids: list) -> pd.DataFrame:
    n = len(club_ids)
    return pd.DataFrame({
        "affiliation_id": [f"f{k}" for k in range(n)],
        "rider_id": ["r1"] * n,
        "club_id": club_ids,
        "start_date": pd.Timestamp("2025-01-01"),
        "end_date": pd.Timestamp("2025-01-01"),
    })


def test_foreign_keys_found_in_files_without_querying_database():
    frames = empty_frames()
    frames["riders"] = pd.DataFrame({"rider_id": ["r1"]})
    frames["clubs"] = pd.DataFrame({"club_id": ["4400001"]})
    df = affiliations(["4400001"])
    connection = ConnectionThatMustNotBeQueried()
    assert check_foreign_keys(TABLES["affiliations"], df, frames, connection) == []


def test_foreign_keys_found_in_database_only():
    frames = empty_frames()
    frames["clubs"] = pd.DataFrame({"club_id": ["4400001"]})
    df = affiliations(["4400001"])
    engine = sqlite_engine_with_riders(["r1"])
    with engine.connect() as connection:
        assert check_foreign_keys(TABLES["affiliations"], df, frames, connection) == []


def test_foreign_keys_unknown_values():
    frames = empty_frames()
    frames["riders"] = pd.DataFrame({"rider_id": ["r1"]})
    frames["clubs"] = pd.DataFrame({"club_id": ["4400001"]})
    df = affiliations(["4400001", "4499999", "4499999", "3500002"])
    problems = check_foreign_keys(TABLES["affiliations"], df, frames, None)
    assert problems == [
        "[affiliations.club_id] 3 value(s) not found in clubs.club_id, e.g. '4499999', '3500002'"
    ]


def test_foreign_keys_missing_values():
    frames = empty_frames()
    frames["riders"] = pd.DataFrame({"rider_id": ["r1"]})
    df = affiliations([None])
    problems = check_foreign_keys(TABLES["affiliations"], df, frames, None)
    assert problems == ["[affiliations.club_id] 1 missing value(s)"]


def test_foreign_keys_composite_primary_key_table():
    frames = empty_frames()
    frames["races"] = pd.DataFrame({"race_id": ["race1"]})
    df = pd.DataFrame(
        {"race_id": ["race1", "race2", "race1"], "rider_id": ["r1", "r2", "r3"], "finish_rank": 1}
    )
    engine = sqlite_engine_with_riders(["r1"])
    with engine.connect() as connection:
        problems = check_foreign_keys(TABLES["rankings"], df, frames, connection)
    assert problems == [
        "[rankings.race_id] 1 value(s) not found in races.race_id, e.g. 'race2'",
        "[rankings.rider_id] 2 value(s) not found in riders.rider_id, e.g. 'r2', 'r3'",
    ]


# ---------------------------------------------------------------- run_checks

def test_run_checks_valid_data():
    run_checks(empty_frames())


def test_run_checks_collects_problems_of_all_tables():
    frames = empty_frames()
    frames["riders"] = pd.DataFrame({"rider_id": ["a", "a"]})
    frames["clubs"] = pd.DataFrame(
        {"club_id": ["4400001", "4400001"], "departemental_committee_id": ["5244", "9999"]}
    )
    with pytest.raises(DataValidationError) as error:
        run_checks(frames)
    assert len(error.value.problems) == 3  # 2 duplicated keys + 1 unknown foreign key column
    assert "3 problem(s) found, nothing was loaded" in str(error.value)


# ---------------------------------------------------------------- load_all

class EngineThatMustNotWrite:
    """Engine allowing read-only connections only (begin opens a write transaction)."""

    def __init__(self):
        self.engine = sqlite_engine_with_riders([])

    def connect(self):
        return self.engine.connect()

    def begin(self):
        raise AssertionError("A write transaction was opened although a check failed")


def test_load_all_writes_nothing_when_a_check_fails(monkeypatch):
    frames = empty_frames()
    frames["races"] = pd.DataFrame(
        {name: ["same_id", "same_id"] if name == "race_id" else [None, None]
         for name in TABLES["races"].columns.keys()}
    )
    monkeypatch.setattr(load, "read_parquet", lambda table: frames[table.name])
    with pytest.raises(DataValidationError):
        load.load_all(EngineThatMustNotWrite())
