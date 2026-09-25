"""Load Parquet files into the database tables.

New rows are always inserted. On a primary key conflict, existing rows are
either left untouched or updated when at least one column differs,
depending on the table.
"""

from typing import Literal

import pandas as pd
from sqlalchemy import Connection, Engine, Table, or_
from sqlalchemy.dialects.postgresql import insert

from access_it.etl.extract.cache import CACHE_DIR
from access_it.etl.load.engine import get_engine
from access_it.etl.load.models import Base


CHUNK_SIZE = 1_000  # rows per INSERT statement

# Tables whose existing rows are updated when at least one column differs.
# Existing rows of all other tables are left untouched.
TABLES_TO_UPDATE = {
    "departements", "departemental_committees", "regional_committees",
    "riders", "clubs", "affiliations"
}

ConflictMode = Literal["ignore", "update"]


def read_parquet(table: Table) -> pd.DataFrame:
    """Read the Parquet file matching the table name."""
    path = CACHE_DIR / f"{table.name}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Missing Parquet file for table '{table.name}': {path}")
    return pd.read_parquet(path)


def validate_columns(df: pd.DataFrame, table: Table) -> None:
    """Check that the DataFrame columns match the table columns."""
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

    Return the number of rows inserted or updated.
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


def load_all(engine: Engine) -> None:
    """Load every table in foreign-key order, within a single transaction."""
    unknown_tables = TABLES_TO_UPDATE - set(Base.metadata.tables)
    if unknown_tables:
        raise ValueError(f"Unknown tables in TABLES_TO_UPDATE: {sorted(unknown_tables)}")

    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            on_conflict: ConflictMode = "update" if table.name in TABLES_TO_UPDATE else "ignore"
            df = read_parquet(table)
            validate_columns(df, table)
            written = write_rows(connection, table, df, on_conflict)
            print(
                f"{table.name} [{on_conflict}]: "
                f"{written} written, {len(df) - written} unchanged"
            )


if __name__ == "__main__":
    load_all(get_engine())
