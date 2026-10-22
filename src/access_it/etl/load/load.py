"""Load Parquet files into the database tables.

New rows are always inserted. On a primary key conflict, existing rows are
either left untouched or updated when at least one column differs,
depending on the table.

For synchronized tables, the Parquet file holds the full set of rows of
every group it contains (e.g. the full history of a rider): rows of these
groups that are missing from the file are deleted. Groups absent from the
file are left untouched.
"""

import logging
import pandas as pd

from typing import Literal
from sqlalchemy import (
    Connection, Engine, Table, or_,
    Column, MetaData, and_, delete, exists, select
)
from sqlalchemy.dialects.postgresql import insert

from access_it.etl.extract.cache import DATA_DIR
from access_it.etl.load.checks import run_checks
from access_it.etl.load.models import Base

logger = logging.getLogger(__name__)


CHUNK_SIZE = 1_000  # rows per INSERT statement

# Tables whose existing rows are updated when at least one column differs.
# Existing rows of all other tables are left untouched.
TABLES_TO_UPDATE = {
    "departements", "departemental_committees", "regional_committees",
    "riders", "clubs", "affiliations", "rider_categories"
}

# Synchronized tables, mapped to their group column: for every group present
# in the Parquet file, rows missing from the file are deleted.
TABLES_TO_SYNC = {"rider_categories": "rider_id", "affiliations": "rider_id"}

ConflictMode = Literal["ignore", "update"]


def read_parquet(table: Table) -> pd.DataFrame:
    """Read the Parquet file of a table, in the data directory of the cache.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    path = DATA_DIR / f"{table.name}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Missing Parquet file for table '{table.name}': {path}")
    return pd.read_parquet(path)


def validate_columns(df: pd.DataFrame, table: Table) -> None:
    """Check that the DataFrame columns match the table columns.

    Raises:
        ValueError: If a column is unknown, or a required column is missing.
    """
    unexpected = set(df.columns) - set(table.columns.keys())
    required = {
        column.name
        for column in table.columns
        if not column.nullable and column.server_default is None
    }
    missing = required - set(df.columns)
    if unexpected or missing:
        raise ValueError(
            f"Table '{table.name}': unexpected columns {sorted(unexpected)}, "
            f"missing columns {sorted(missing)}"
        )


def to_records(df: pd.DataFrame) -> list[dict]:
    """Convert a DataFrame to a list of dicts, replacing NaN/NaT with None."""
    return df.astype(object).where(df.notna(), None).to_dict(orient="records")


def write_rows(
    connection: Connection, table: Table, df: pd.DataFrame, on_conflict: ConflictMode
) -> int:
    """Insert new rows; on a primary key conflict, ignore the row or update it if changed.

    Rows are written by chunks of CHUNK_SIZE; an existing row is updated only
    if at least one column differs.

    Args:
        connection: Open connection, within a transaction.
        table: Table to write.
        df: Rows to write.
        on_conflict: "ignore" to leave existing rows untouched, "update" to
            update them when they differ.

    Returns:
        The number of rows inserted or updated.
    """
    key_columns = [column.name for column in table.primary_key.columns]
    update_columns = [name for name in df.columns if name not in key_columns]
    records = to_records(df)
    written = 0

    for start in range(0, len(records), CHUNK_SIZE):
        statement = insert(table).values(records[start : start + CHUNK_SIZE])

        if on_conflict == "update" and update_columns:
            statement = statement.on_conflict_do_update(
                index_elements=key_columns,
                set_={name: statement.excluded[name] for name in update_columns},
                where=or_(
                    *(
                        table.c[name].is_distinct_from(statement.excluded[name])
                        for name in update_columns
                    )
                ),
            )
        else:
            statement = statement.on_conflict_do_nothing(index_elements=key_columns)

        statement = statement.returning(*table.primary_key.columns)
        written += len(connection.execute(statement).fetchall())

    return written


def delete_stale_rows(
    connection: Connection, table: Table, df: pd.DataFrame, group_column: str
) -> int:
    """Delete the rows of the groups present in the DataFrame whose key is missing from it.

    Groups absent from the DataFrame are left untouched. The keys of the
    DataFrame are uploaded into a temporary table, dropped afterwards.

    Args:
        connection: Open connection, within a transaction.
        table: Synchronized table.
        df: Rows of the file.
        group_column: Primary key column defining the groups (e.g. rider_id).

    Returns:
        The number of rows deleted.

    Raises:
        ValueError: If `group_column` is not part of the primary key.
    """
    if df.empty:
        return 0

    key_columns = [column.name for column in table.primary_key.columns]
    if group_column not in key_columns:
        raise ValueError(
            f"Table '{table.name}': group column '{group_column}' "
            f"is not part of the primary key {key_columns}"
        )

    # Temporary table holding the keys of the DataFrame
    new_keys = Table(
        f"tmp_{table.name}_keys",
        MetaData(),
        *(Column(name, table.c[name].type) for name in key_columns),
        prefixes=["TEMPORARY"],
    )
    new_keys.create(connection)
    try:
        connection.execute(new_keys.insert(), to_records(df[key_columns]))
        statement = delete(table).where(
            table.c[group_column].in_(select(new_keys.c[group_column])),
            ~exists().where(
                and_(*(new_keys.c[name] == table.c[name] for name in key_columns))
            ),
        )
        return connection.execute(statement).rowcount
    finally:
        new_keys.drop(connection)


def load_all(engine: Engine) -> None:
    """Load every table in foreign-key order, within a single transaction.

    All the Parquet files are read and checked first (see checks.py): if a
    check fails, nothing is written to the database.

    Args:
        engine: Engine of the database.

    Raises:
        ValueError: If TABLES_TO_UPDATE or TABLES_TO_SYNC names an unknown
            table, or if the columns of a file do not match its table.
        DataValidationError: If a check fails.
    """
    unknown_tables = TABLES_TO_UPDATE - set(Base.metadata.tables)
    if unknown_tables:
        raise ValueError(f"Unknown tables in TABLES_TO_UPDATE: {sorted(unknown_tables)}")
    unknown_sync_tables = TABLES_TO_SYNC.keys() - set(Base.metadata.tables)
    if unknown_sync_tables:
        raise ValueError(f"Unknown tables in TABLES_TO_SYNC: {sorted(unknown_sync_tables)}")

    # Read and check all the files first, against each other and against the
    # database (read-only queries): nothing is written if one check fails
    frames = {}
    for table in Base.metadata.sorted_tables:
        df = read_parquet(table)
        validate_columns(df, table)
        frames[table.name] = df
    run_checks(frames, engine)

    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            on_conflict: ConflictMode = "update" if table.name in TABLES_TO_UPDATE else "ignore"
            df = frames[table.name]
            if table.name in TABLES_TO_SYNC:
                deleted = delete_stale_rows(
                    connection, table, df, TABLES_TO_SYNC[table.name]
                )
                logger.info(f"{table.name} [sync]: {deleted} deleted")
            written = write_rows(connection, table, df, on_conflict)
            logger.info(
                f"{table.name} [{on_conflict}]: "
                f"{written} written, {len(df) - written} unchanged"
            )
