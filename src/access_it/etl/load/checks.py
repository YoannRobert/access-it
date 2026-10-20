"""Data checks run before loading the Parquet files into the database.

Every check returns a list of problems (empty when the data is valid).
`run_checks` collects the problems of all checks and tables, then raises a
single DataValidationError listing them all, so that nothing is written to
the database as long as one problem remains.
"""

import pandas as pd

from sqlalchemy import Table

from access_it.etl.load.models import Base

MAX_EXAMPLES = 3  # example values shown in each problem message


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


def run_checks(frames: dict[str, pd.DataFrame]) -> None:
    """Run every check on the DataFrames to load, keyed by table name.

    Raise a DataValidationError listing all the problems found.
    """
    problems = []
    for table in Base.metadata.sorted_tables:
        if table.name not in frames:
            continue
        problems += check_primary_key(table, frames[table.name])
    if problems:
        raise DataValidationError(problems)
