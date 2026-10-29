"""Unit tests of the restoration of the database from a snapshot."""

import pandas as pd
import pytest

from sqlalchemy import create_engine, insert, select

from access_it.etl.load.models import Base
from access_it.etl.load.restore import (
    TableChanges, check_snapshot_schema, compute_changes, compute_table_changes,
    delete_missing_rows
)

TABLES = Base.metadata.tables
RIDERS = TABLES["riders"]


def empty_tables() -> dict[str, pd.DataFrame]:
    """One empty DataFrame per table, with the columns of the current schema."""
    return {name: pd.DataFrame(columns=list(table.columns.keys())) for name, table in TABLES.items()}


def riders(*rows: tuple) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["rider_id", "uci_id", "last_name", "first_name"])


def test_snapshot_with_the_current_schema_is_accepted():
    check_snapshot_schema(empty_tables())


def test_snapshot_with_a_missing_table_is_rejected():
    tables = empty_tables()
    del tables["riders"]
    with pytest.raises(ValueError, match="missing tables"):
        check_snapshot_schema(tables)


@pytest.mark.parametrize("change", ["extra", "missing"])
def test_snapshot_with_other_columns_is_rejected(change):
    tables = empty_tables()
    if change == "extra":
        tables["riders"]["nickname"] = []
    else:
        tables["riders"] = tables["riders"].drop(columns="uci_id")
    with pytest.raises(ValueError, match="table 'riders'"):
        check_snapshot_schema(tables)


def test_changes_of_a_table():
    snapshot = riders(
        ("r1", "1", "A", "a"),     # unchanged
        ("r2", "2", "B", "b"),     # updated (last name)
        ("r3", None, "C", "c"),    # unchanged, missing value on both sides
        ("r4", "4", "D", "d"),     # inserted
    )
    current = riders(
        ("r1", "1", "A", "a"),
        ("r2", "2", "BB", "b"),
        ("r3", None, "C", "c"),
        ("r5", "5", "E", "e"),     # deleted
    )
    assert compute_table_changes(RIDERS, snapshot, current) == TableChanges(1, 1, 1)


def test_missing_value_on_one_side_is_a_change():
    snapshot, current = riders(("r1", None, "A", "a")), riders(("r1", "1", "A", "a"))
    assert compute_table_changes(RIDERS, snapshot, current) == TableChanges(0, 1, 0)


def test_no_change_between_identical_tables():
    tables = empty_tables()
    tables["riders"] = riders(("r1", "1", "A", "a"))
    changes = compute_changes(tables, {name: df.copy() for name, df in tables.items()})
    assert list(changes) == [table.name for table in Base.metadata.sorted_tables]
    assert sum(change.total for change in changes.values()) == 0


def database_with_riders(*rider_ids: str):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(RIDERS),
            [{"rider_id": r, "uci_id": "", "last_name": "X", "first_name": "x"} for r in rider_ids],
        )
    return engine


def rider_ids(engine) -> list[str]:
    with engine.connect() as connection:
        return sorted(connection.execute(select(RIDERS.c.rider_id)).scalars())


def test_rows_missing_from_the_snapshot_are_deleted():
    engine = database_with_riders("r1", "r2", "r3")
    with engine.begin() as connection:
        deleted = delete_missing_rows(connection, RIDERS, riders(("r1", "", "X", "x"), ("r3", "", "X", "x")))
    assert deleted == 1
    assert rider_ids(engine) == ["r1", "r3"]


def test_empty_snapshot_table_empties_the_table():
    engine = database_with_riders("r1", "r2")
    with engine.begin() as connection:
        deleted = delete_missing_rows(connection, RIDERS, riders())
    assert deleted == 2
    assert rider_ids(engine) == []
