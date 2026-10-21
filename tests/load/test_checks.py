"""Unit tests of the checks run before loading data into the database."""

import pandas as pd
import pytest

from sqlalchemy import create_engine, insert

from access_it.etl.load import load
from access_it.etl.load.checks import (
    DataValidationError, check_foreign_keys, check_missing_rows, check_primary_key,
    check_row_count, find_existing_values, find_missing_rows, run_checks
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


def valid_frames() -> dict[str, pd.DataFrame]:
    """One consistent row per table, passing every check."""
    date = pd.Timestamp("2025-04-12")
    rows = {
        "departements": {"departement_code": "44", "departement_name": "Loire-Atlantique"},
        "regional_committees": {"regional_committee_id": "52", "name": "PAYS DE LA LOIRE"},
        "departemental_committees": {
            "departemental_committee_id": "5244", "name": "CD 44",
            "regional_committee_id": "52", "departement_code": "44",
        },
        "clubs": {
            "club_id": "5244001", "name": "VC Test", "departemental_committee_id": "5244",
            "min_year": 2025, "max_year": 2025, "alternative_names": "",
        },
        "riders": {"rider_id": "r1", "uci_id": "", "last_name": "X", "first_name": "Y"},
        "races": {
            "race_id": "race1", "title": "Test", "categories": "A1", "season": 2025,
            "discipline": "Route", "race_date": date, "departement_code": "44",
            "organization_code": "C5244001001", "race_type": "R", "organizer": "VC Test",
            "duration": "1 jour", "race_code": "1.27.1",
        },
        "rankings": {"race_id": "race1", "rider_id": "r1", "finish_rank": 1},
        "affiliations": {"rider_id": "r1", "start_date": date, "club_id": "5244001"},
        "rider_categories": {"rider_id": "r1", "start_date": date, "rider_category": 1},
    }
    return {name: pd.DataFrame([row]) for name, row in rows.items()}


def sqlite_engine_with_rows(rows_by_table: dict[str, list[dict]]):
    """In-memory SQLite database with all tables, holding the given rows."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        for table_name, rows in rows_by_table.items():
            connection.execute(insert(TABLES[table_name]), rows)
    return engine


def rider_row(rider_id: str, uci_id: str = "") -> dict:
    return {"rider_id": rider_id, "uci_id": uci_id, "last_name": "X", "first_name": "Y"}


def sqlite_engine_with_rider_categories(n_rows: int):
    """In-memory SQLite database with all tables, holding n_rows category rows."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(TABLES["rider_categories"]),
            [
                {"rider_id": f"r{k}", "start_date": pd.Timestamp("2025-01-01").date(),
                 "rider_category": 1}
                for k in range(n_rows)
            ],
        )
    return engine


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
        "rider_id": ["r1"] * n,
        "start_date": pd.date_range("2023-01-01", periods=n, freq="YS"),
        "club_id": club_ids,
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


# ---------------------------------------------------------------- check_row_count

def rider_categories(n_rows: int) -> pd.DataFrame:
    return pd.DataFrame({
        "rider_id": [f"r{k}" for k in range(n_rows)],
        "start_date": pd.Timestamp("2025-01-01"),
        "rider_category": 1,
    })


def test_row_count_empty_file():
    df = empty_frames()["clubs"]
    assert check_row_count(TABLES["clubs"], df, None) == ["[clubs] file is empty"]


def test_row_count_no_decrease_allowed():
    engine = sqlite_engine_with_riders(["r1", "r2", "r3"])
    df = pd.DataFrame({"rider_id": ["r1", "r2"]})
    with engine.connect() as connection:
        problems = check_row_count(TABLES["riders"], df, connection)
    assert problems == [
        "[riders] file has 2 rows, database has 3 (-33.33%, tolerance 0%): "
        "possible incomplete extract or transform"
    ]


def test_row_count_increase_is_allowed():
    engine = sqlite_engine_with_riders(["r1"])
    df = pd.DataFrame({"rider_id": ["r1", "r2"]})
    with engine.connect() as connection:
        assert check_row_count(TABLES["riders"], df, connection) == []


def test_row_count_decrease_within_tolerance():
    engine = sqlite_engine_with_rider_categories(100)
    with engine.connect() as connection:
        assert check_row_count(TABLES["rider_categories"], rider_categories(95), connection) == []
        problems = check_row_count(TABLES["rider_categories"], rider_categories(94), connection)
    assert problems == [
        "[rider_categories] file has 94 rows, database has 100 (-6.00%, tolerance 5%): "
        "possible incomplete extract or transform"
    ]


def test_row_count_not_checked_for_tables_built_from_the_api():
    df = valid_frames()["clubs"]
    connection = ConnectionThatMustNotBeQueried()
    assert check_row_count(TABLES["clubs"], df, connection) == []


def test_row_count_without_database():
    assert check_row_count(TABLES["riders"], valid_frames()["riders"], None) == []


# ---------------------------------------------------------------- check_missing_rows

UCI_ID_1, UCI_ID_2 = "10012345656", "10012345757"  # valid check digits (modulo 97)


def named_rider(rider_id: str, uci_id: str, last_name: str, first_name: str) -> dict:
    return {
        "rider_id": rider_id, "uci_id": uci_id, "last_name": last_name, "first_name": first_name
    }


def missing_riders_message(database_riders: list[dict], file_riders: list[dict]) -> str:
    engine = sqlite_engine_with_rows({"riders": database_riders})
    with engine.connect() as connection:
        problems = check_missing_rows(TABLES["riders"], pd.DataFrame(file_riders), connection)
    assert len(problems) == 1
    return problems[0]


def test_missing_rows_none():
    engine = sqlite_engine_with_rows({"riders": [rider_row("r1"), rider_row("r2")]})
    df = pd.DataFrame([rider_row("r1"), rider_row("r2"), rider_row("r3")])
    with engine.connect() as connection:
        assert check_missing_rows(TABLES["riders"], df, connection) == []


def test_missing_rider_who_now_has_a_uci_id():
    message = missing_riders_message(
        [named_rider("r1", UCI_ID_1, "DUPONT", "Paul"), named_rider("r_old", "", "MARTIN", "Jean")],
        [named_rider("r1", UCI_ID_1, "DUPONT", "Paul"),
         named_rider("r_new", UCI_ID_2, "Martin", "Jean")],
    )
    assert message.splitlines()[:3] == [
        "[riders] 1 rider(s) in database missing from file: "
        "identifiers probably changed since the last load",
        "    Riders without UCI ID in the database who now appear with a UCI ID in the file (1):",
        "      MARTIN Jean (no UCI ID): 'r_old' in database -> 'r_new' in file "
        f"(UCI ID {UCI_ID_2})",
    ]
    assert "python scripts/prune_stale_rows.py --apply" in message
    assert "python scripts/load.py" in message


def test_missing_red_list_rider_who_now_has_a_uci_id():
    message = missing_riders_message(
        [named_rider("r_old", "Liste Rouge", "MARTIN", "J.")],
        [named_rider("r_new", UCI_ID_2, "MARTIN", "Jean")],
    )
    assert (
        f"MARTIN J. (red list): 'r_old' in database -> 'r_new' in file (UCI ID {UCI_ID_2})"
        in message
    )


def test_missing_rider_with_same_uci_id_under_another_rider_id():
    message = missing_riders_message(
        [named_rider("r_old", UCI_ID_1, "DUPONT", "Paul")],
        [named_rider("r_new", UCI_ID_1, "DUPOND", "Paul")],
    )
    assert "Riders whose UCI ID has another rider_id in the file (1):" in message
    assert f"DUPONT Paul: 'r_old' in database -> 'r_new' in file (UCI ID {UCI_ID_1})" in message


def test_missing_rider_for_an_unknown_reason():
    message = missing_riders_message(
        [named_rider("r1", UCI_ID_1, "DUPONT", "Paul"), named_rider("r2", "", "BERNARD", "Luc")],
        [named_rider("r1", UCI_ID_1, "DUPONT", "Paul")],
    )
    assert "Riders missing for an unknown reason, check the transform step first (1):" in message
    assert "BERNARD Luc: 'r2' (UCI ID field: '')" in message


def test_homonyms_with_a_uci_id_are_not_guessed():
    message = missing_riders_message(
        [named_rider("r_old", "", "MARTIN", "Jean")],
        [
            named_rider("a", UCI_ID_1, "MARTIN", "Jean"),
            named_rider("b", UCI_ID_2, "MARTIN", "Jean"),
        ],
    )
    assert "unknown reason" in message
    assert "now appear with a UCI ID" not in message


def test_missing_rows_composite_key():
    engine = sqlite_engine_with_rows({
        "rankings": [
            {"race_id": "race1", "rider_id": "r1", "finish_rank": 1},
            {"race_id": "race1", "rider_id": "r2", "finish_rank": 2},
        ]
    })
    df = pd.DataFrame({"race_id": ["race1"], "rider_id": ["r1"], "finish_rank": [1]})
    with engine.connect() as connection:
        problems = check_missing_rows(TABLES["rankings"], df, connection)
    assert problems == [
        "[rankings] 1 row(s) in database missing from file, e.g. ('race1', 'r2'): "
        "identifiers probably changed since the last load"
    ]


def test_missing_rows_temporary_table_is_dropped():
    engine = sqlite_engine_with_rows({"riders": [rider_row("r1"), rider_row("r2")]})
    df = pd.DataFrame([rider_row("r1")])
    with engine.connect() as connection:
        assert find_missing_rows(connection, TABLES["riders"], df) == (1, [("r2",)])
        assert find_missing_rows(connection, TABLES["riders"], df) == (1, [("r2",)])


def test_missing_rows_not_checked_for_affiliations():
    connection = ConnectionThatMustNotBeQueried()
    df = affiliations(["4400001"])
    assert check_missing_rows(TABLES["affiliations"], df, connection) == []


def test_missing_rows_not_checked_for_rider_categories():
    connection = ConnectionThatMustNotBeQueried()
    df = rider_categories(1)
    assert check_missing_rows(TABLES["rider_categories"], df, connection) == []


def test_missing_rows_empty_database():
    engine = sqlite_engine_with_rows({})
    with engine.connect() as connection:
        df = pd.DataFrame([rider_row("r1")])
        assert check_missing_rows(TABLES["riders"], df, connection) == []


def test_missing_rows_without_database():
    assert check_missing_rows(TABLES["riders"], pd.DataFrame([rider_row("r1")]), None) == []


# ---------------------------------------------------------------- run_checks

def test_run_checks_valid_data():
    run_checks(valid_frames())


def test_run_checks_valid_data_with_database():
    run_checks(valid_frames(), sqlite_engine_with_riders(["r1"]))


def test_run_checks_collects_problems_of_all_tables():
    frames = valid_frames()
    frames["riders"] = pd.concat([frames["riders"]] * 2)
    clubs = pd.concat([frames["clubs"]] * 2, ignore_index=True)
    clubs.loc[1, "departemental_committee_id"] = "9999"
    frames["clubs"] = clubs
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
