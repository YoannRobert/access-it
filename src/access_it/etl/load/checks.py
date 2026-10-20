"""Data checks run before loading the Parquet files into the database.

Every check returns a list of problems (empty when the data is valid).
Checks that need the database send targeted read-only queries, so that only
a few bytes leave the database (the Neon free plan limits data transfer).
`run_checks` collects the problems of all checks and tables, then raises a
single DataValidationError listing them all, so that nothing is written to
the database as long as one problem remains.
"""

import pandas as pd

from contextlib import nullcontext
from sqlalchemy import Connection, Engine, Table, select

from access_it.etl.load.models import Base

MAX_EXAMPLES = 3  # example values shown in each problem message
QUERY_CHUNK_SIZE = 1_000  # values per IN (...) clause


class DataValidationError(Exception):
    """Raised when the data to load fails at least one check."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        message = f"{len(problems)} problem(s) found, nothing was loaded:\n"
        message += "\n".join(f"- {problem}" for problem in problems)
        super().__init__(message)


def format_examples(values: list) -> str:
    """Format the first example values of a problem message."""
    return ", ".join(repr(value) for value in values[:MAX_EXAMPLES])


def check_primary_key(table: Table, df: pd.DataFrame) -> list[str]:
    """Check that primary key columns have no missing values and no duplicates."""
    key_columns = [column.name for column in table.primary_key.columns]
    keys = df[key_columns]
    problems = []

    missing = keys.isna().any(axis=1)
    if missing.any():
        problems.append(
            f"[{table.name}] {missing.sum()} row(s) with a missing primary key value "
            f"({', '.join(key_columns)})"
        )

    duplicated = keys[~missing].duplicated(keep="first")
    if duplicated.any():
        duplicated_keys = keys[~missing][duplicated].drop_duplicates()
        examples = list(duplicated_keys.itertuples(index=False, name=None))
        if len(key_columns) == 1:
            examples = [example[0] for example in examples]
        problems.append(
            f"[{table.name}] {duplicated.sum()} duplicated primary key(s) "
            f"({', '.join(key_columns)}), e.g. {format_examples(examples)}"
        )

    return problems


def find_existing_values(
        connection: Connection | None,
        table: Table,
        column: str,
        values: list
    ) -> set:
    """Return the subset of `values` present in `table.column` of the database.

    Only the values asked for can be returned, so the transfer stays minimal.
    A None connection stands for an empty database.
    """
    if connection is None or not values:
        return set()
    found = set()
    for start in range(0, len(values), QUERY_CHUNK_SIZE):
        chunk = values[start : start + QUERY_CHUNK_SIZE]
        statement = select(table.c[column]).where(table.c[column].in_(chunk))
        found.update(connection.execute(statement).scalars())
    return found


def check_foreign_keys(
        table: Table,
        df: pd.DataFrame,
        frames: dict[str, pd.DataFrame],
        connection: Connection | None
    ) -> list[str]:
    """Check that every foreign key value exists in the file or the database of its table.

    The database is only queried for values absent from the file of the
    referred table (usually none). Missing values are reported too when the
    column does not accept them.
    """
    problems = []
    for foreign_key in sorted(table.foreign_keys, key=lambda fk: fk.parent.name):
        column = foreign_key.parent.name
        referred_table = foreign_key.column.table
        referred_column = foreign_key.column.name
        values = df[column]

        missing = values.isna()
        if missing.any() and not foreign_key.parent.nullable:
            problems.append(f"[{table.name}.{column}] {missing.sum()} missing value(s)")

        not_in_files = values[~missing]
        if referred_table.name in frames:
            file_values = frames[referred_table.name][referred_column]
            not_in_files = not_in_files[~not_in_files.isin(file_values)]
        if not_in_files.empty:
            continue

        in_database = find_existing_values(
            connection, referred_table, referred_column, not_in_files.drop_duplicates().to_list()
        )
        unknown = not_in_files[~not_in_files.isin(in_database)]
        if not unknown.empty:
            examples = unknown.drop_duplicates().to_list()
            problems.append(
                f"[{table.name}.{column}] {len(unknown)} value(s) not found in "
                f"{referred_table.name}.{referred_column}, e.g. {format_examples(examples)}"
            )
    return problems


def run_checks(frames: dict[str, pd.DataFrame], engine: Engine | None = None) -> None:
    """Run every check on the DataFrames to load, keyed by table name.

    The database is only read, never written. A None engine stands for an
    empty database. Raise a DataValidationError listing all the problems found.
    """
    problems = []
    with (engine.connect() if engine is not None else nullcontext()) as connection:
        for table in Base.metadata.sorted_tables:
            if table.name not in frames:
                continue
            df = frames[table.name]
            problems += check_primary_key(table, df)
            problems += check_foreign_keys(table, df, frames, connection)
    if problems:
        raise DataValidationError(problems)
