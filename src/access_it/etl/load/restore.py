"""Restoration of the database from a snapshot (one DataFrame per table).

Unlike the load, the restoration reproduces the snapshot exactly: every row
that differs is updated, whatever the table, and every row missing from the
snapshot is deleted. Only the rows that change are written.

Safeguards:
- nothing is written if the schema of the snapshot differs from the current one
  (tables or columns);
- the changes are counted beforehand, so that they can be confirmed;
- all the writes happen in a single transaction.
"""

import logging

from dataclasses import dataclass

import pandas as pd

from sqlalchemy import (
    Column, Connection, Engine, MetaData, Table, and_, delete, exists, func, select
)

from access_it.etl.load.load import to_records, write_rows
from access_it.etl.load.models import Base

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TableChanges:
    """Rows of a table to insert, update or delete to match the snapshot."""

    inserted: int
    updated: int
    deleted: int

    @property
    def total(self) -> int:
        return self.inserted + self.updated + self.deleted


def check_snapshot_schema(tables: dict[str, pd.DataFrame]) -> None:
    """Check that the snapshot holds exactly the tables and columns of the current schema.

    Raises:
        ValueError: If a table is missing or unknown, or if the columns of a table differ.
    """
    errors = []
    expected_tables = set(Base.metadata.tables)
    missing_tables = expected_tables - set(tables)
    unknown_tables = set(tables) - expected_tables
    if missing_tables or unknown_tables:
        errors.append(
            f"missing tables {sorted(missing_tables)}, unknown tables {sorted(unknown_tables)}"
        )
    for name in sorted(expected_tables & set(tables)):
        expected_columns = set(Base.metadata.tables[name].columns.keys())
        columns = set(tables[name].columns)
        if columns != expected_columns:
            errors.append(
                f"table '{name}': missing columns {sorted(expected_columns - columns)}, "
                f"unknown columns {sorted(columns - expected_columns)}"
            )
    if errors:
        raise ValueError("Snapshot schema differs from the database schema: " + "; ".join(errors))


def _key_columns(table: Table) -> list[str]:
    return [column.name for column in table.primary_key.columns]


def _values_differ(left: pd.Series, right: pd.Series) -> pd.Series:
    """Element-wise difference of two columns, two missing values being equal."""
    left, right = left.astype(object), right.astype(object)
    both_missing = left.isna() & right.isna()
    return ~both_missing & (left.isna() | right.isna() | (left != right))


def compute_table_changes(table: Table, snapshot: pd.DataFrame, current: pd.DataFrame) -> TableChanges:
    """Count the rows to insert, update or delete so that a table matches the snapshot.

    Rows are matched on the primary key; a row is updated when at least one
    other column differs (two missing values being equal).
    """
    keys = _key_columns(table)
    others = [name for name in table.columns.keys() if name not in keys]
    merged = snapshot[keys + others].merge(
        current[keys + others], on=keys, how="outer", suffixes=("_snapshot", "_current"),
        indicator=True
    )
    inserted = int((merged["_merge"] == "left_only").sum())
    deleted = int((merged["_merge"] == "right_only").sum())
    both = merged[merged["_merge"] == "both"]
    changed = pd.Series(False, index=both.index)
    for name in others:
        changed |= _values_differ(both[f"{name}_snapshot"], both[f"{name}_current"])
    return TableChanges(inserted=inserted, updated=int(changed.sum()), deleted=deleted)


def compute_changes(
        snapshot: dict[str, pd.DataFrame],
        current: dict[str, pd.DataFrame]
    ) -> dict[str, TableChanges]:
    """Changes of every table (see compute_table_changes), in foreign-key order."""
    return {
        table.name: compute_table_changes(table, snapshot[table.name], current[table.name])
        for table in Base.metadata.sorted_tables
    }


def delete_missing_rows(connection: Connection, table: Table, df: pd.DataFrame) -> int:
    """Delete the rows of a table whose primary key is missing from the DataFrame.

    The keys of the DataFrame are uploaded into a temporary table, dropped afterwards.

    Args:
        connection: Open connection, within a transaction.
        table: Table to clean.
        df: Rows to keep.

    Returns:
        The number of rows deleted.
    """
    if df.empty:
        return connection.execute(delete(table)).rowcount

    keys = _key_columns(table)
    kept_keys = Table(
        f"tmp_{table.name}_kept_keys",
        MetaData(),
        *(Column(name, table.c[name].type) for name in keys),
        prefixes=["TEMPORARY"],
    )
    kept_keys.create(connection)
    try:
        connection.execute(kept_keys.insert(), to_records(df[keys]))
        statement = delete(table).where(
            ~exists().where(and_(*(kept_keys.c[name] == table.c[name] for name in keys)))
        )
        return connection.execute(statement).rowcount
    finally:
        kept_keys.drop(connection)


def restore_tables(engine: Engine, snapshot: dict[str, pd.DataFrame]) -> None:
    """Make the database match the snapshot, within a single transaction.

    Rows missing from the snapshot are deleted first, in reverse foreign-key
    order; the rows of the snapshot are then inserted or updated, in
    foreign-key order.

    Args:
        engine: Engine of the database.
        snapshot: Content of every table, keyed by table name (schema
            checked by check_snapshot_schema).
    """
    check_snapshot_schema(snapshot)
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            deleted = delete_missing_rows(connection, table, snapshot[table.name])
            logger.info(f"{table.name}: {deleted} deleted")
        for table in Base.metadata.sorted_tables:
            written = write_rows(connection, table, snapshot[table.name], on_conflict="update")
            logger.info(f"{table.name}: {written} written")


def count_rows(engine: Engine) -> dict[str, int]:
    """Number of rows of every table, keyed by table name."""
    with engine.connect() as connection:
        return {
            name: connection.execute(select(func.count()).select_from(table)).scalar_one()
            for name, table in Base.metadata.tables.items()
        }
