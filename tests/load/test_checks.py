"""Unit tests of the checks run before loading data into the database."""

import pandas as pd
import pytest

from access_it.etl.load import load
from access_it.etl.load.checks import DataValidationError, check_primary_key, run_checks
from access_it.etl.load.models import Base

TABLES = Base.metadata.tables


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


# ---------------------------------------------------------------- run_checks

def test_run_checks_valid_data():
    run_checks(empty_frames())


def test_run_checks_collects_problems_of_all_tables():
    frames = empty_frames()
    frames["riders"] = pd.DataFrame({"rider_id": ["a", "a"]})
    frames["clubs"] = pd.DataFrame({"club_id": ["4400001", "4400001"]})
    with pytest.raises(DataValidationError) as error:
        run_checks(frames)
    assert len(error.value.problems) == 2
    assert "2 problem(s) found, nothing was loaded" in str(error.value)


# ---------------------------------------------------------------- load_all

class EngineThatMustNotBeUsed:
    def begin(self):
        raise AssertionError("The database was accessed although a check failed")


def test_load_all_writes_nothing_when_a_check_fails(monkeypatch):
    frames = empty_frames()
    frames["races"] = pd.DataFrame(
        {name: ["same_id", "same_id"] if name == "race_id" else [None, None]
         for name in TABLES["races"].columns.keys()}
    )
    monkeypatch.setattr(load, "read_parquet", lambda table: frames[table.name])
    with pytest.raises(DataValidationError):
        load.load_all(EngineThatMustNotBeUsed())
