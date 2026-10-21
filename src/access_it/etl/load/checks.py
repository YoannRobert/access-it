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
from sqlalchemy import (
    Column, Connection, Engine, MetaData, Table, and_, exists, func, select
)

from access_it.common.text import normalize_string_and_fold_case
from access_it.etl.load.models import Base
from access_it.etl.transform.riders import is_valid_uci_id

MAX_EXAMPLES = 3  # example values shown in each problem message
QUERY_CHUNK_SIZE = 1_000  # values per IN (...) clause
MAX_DIAGNOSED_RIDERS = 20  # missing riders read from the database to explain the problem
CLEANING_INSTRUCTIONS = [
    "To delete the stale riders and their rows, run from the repository root:",
    "  python scripts/prune_stale_rows.py            (dry run: shows what would be deleted)",
    "  python scripts/prune_stale_rows.py --apply    (deletes)",
    "then run the load again: python scripts/load.py",
]

# Maximum relative decrease of the row count, from the database to the file.
# Only tables rebuilt from the whole cache are listed: their files hold the full
# history, so they should not shrink. Tables built from the current FFC API
# (clubs, departements, committees) are left out, since entries can disappear
# from the API while the database keeps them.
MAX_ROW_DECREASE = {
    "races": 0.0,
    "rankings": 0.0,
    "riders": 0.0,
    # Periods recomputed at every run (synchronized tables): fewer rows may be legitimate
    "affiliations": 0.05,
    "rider_categories": 0.05,
}

# Tables whose rows already in the database must all be present in the file.
# A missing row usually means that an identifier changed between two runs
# (e.g. rider_id, computed from the names and the UCI ID): the database would
# keep the old row next to the new one. affiliations and rider_categories are
# left out on purpose: their periods are recomputed at every run and synchronized.
NO_MISSING_ROWS = ["riders", "rankings"]


class DataValidationError(Exception):
    """Raised when the data to load fails at least one check."""

    def __init__(self, problems: list[str]):
        """Build the message from the list of problems."""
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

    Args:
        connection: Open connection, or None for an empty database.
        table: Table to search.
        column: Column to search.
        values: Values to look for (queried by chunks of QUERY_CHUNK_SIZE).

    Returns:
        The values found.
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


def count_rows(connection: Connection | None, table: Table) -> int:
    """Return the number of rows of the table in the database (0 without database)."""
    if connection is None:
        return 0
    return connection.execute(select(func.count()).select_from(table)).scalar_one()


def check_row_count(table: Table, df: pd.DataFrame, connection: Connection | None) -> list[str]:
    """Check that the file is not empty and has not shrunk too much compared with the database.

    Only a row count is read from the database (tables of MAX_ROW_DECREASE only).
    """
    if df.empty:
        return [f"[{table.name}] file is empty"]
    if table.name not in MAX_ROW_DECREASE:
        return []
    database_rows = count_rows(connection, table)
    tolerance = MAX_ROW_DECREASE[table.name]
    if database_rows == 0 or len(df) >= database_rows * (1 - tolerance):
        return []
    decrease = 1 - len(df) / database_rows
    return [
        f"[{table.name}] file has {len(df)} rows, database has {database_rows} "
        f"(-{decrease:.2%}, tolerance {tolerance:.0%}): possible incomplete extract or transform"
    ]


def find_missing_rows(
        connection: Connection,
        table: Table,
        df: pd.DataFrame,
        columns: list[str] | None = None,
        limit: int = MAX_EXAMPLES
    ) -> tuple[int, list[tuple]]:
    """Return the number of rows of the database table absent from the file, and some of them.

    The primary keys of the file are uploaded into a temporary table, and the
    database only sends back the count and at most `limit` missing rows.

    Args:
        connection: Open connection.
        table: Table of the database.
        df: Rows of the file.
        columns: Columns of the missing rows returned (default: the
            primary key columns).
        limit: Maximum number of missing rows returned.

    Returns:
        The number of missing rows, and at most `limit` of them (tuples).
    """
    key_columns = [column.name for column in table.primary_key.columns]
    columns = columns or key_columns
    file_keys = Table(
        f"tmp_check_{table.name}_keys",
        MetaData(),
        *(Column(name, table.c[name].type) for name in key_columns),
        prefixes=["TEMPORARY"],
    )
    file_keys.create(connection)
    try:
        records = df[key_columns].dropna().drop_duplicates().to_dict(orient="records")
        if records:
            connection.execute(file_keys.insert(), records)
        absent_from_file = ~exists().where(
            and_(*(file_keys.c[name] == table.c[name] for name in key_columns))
        )
        count = connection.execute(
            select(func.count()).select_from(table).where(absent_from_file)
        ).scalar_one()
        rows = connection.execute(
            select(*(table.c[name] for name in columns)).where(absent_from_file).limit(limit)
        )
        return count, [tuple(row) for row in rows]
    finally:
        file_keys.drop(connection)


def _names_match(db_last: str, db_first: str, file_last: str, file_first: str) -> bool:
    """Whether names of the database and of the file belong to the same person.

    Red-list riders often have their first name reduced to an initial ("J."),
    which then only has to match the first letter of the first name in the file.
    """
    db_last, db_first = fold_name(db_last), fold_name(db_first)
    file_last, file_first = fold_name(file_last), fold_name(file_first)
    if db_last != file_last or not db_first or not file_first:
        return False
    initial = db_first.rstrip(".")
    if len(initial) == 1:
        return file_first.startswith(initial)
    return db_first == file_first


def fold_name(name) -> str:
    """Name without case, accents and extra spaces ('' for a missing name)."""
    if not isinstance(name, str):
        return ""
    return " ".join(normalize_string_and_fold_case(name).split())


def explain_missing_riders(missing_riders: list[tuple], riders: pd.DataFrame) -> list[str]:
    """Explain the missing riders (rider_id, uci_id, last_name, first_name), one line each.

    Missing riders are grouped by cause: riders without valid UCI ID in the
    database now appearing with one in the file, riders whose UCI ID has another
    rider_id in the file, and riders missing for an unknown reason.
    """
    file_riders_with_uci_id = [
        (rider_id, uci_id, last_name, first_name)
        for rider_id, uci_id, last_name, first_name in zip(
            riders["rider_id"], riders["uci_id"], riders["last_name"], riders["first_name"]
        )
        if isinstance(uci_id, str) and is_valid_uci_id(uci_id)
    ]
    file_rider_id_by_uci_id = {uci_id: rider_id for rider_id, uci_id, *_ in file_riders_with_uci_id}

    gained_uci_id, same_uci_id, unknown = [], [], []
    for rider_id, uci_id, last_name, first_name in missing_riders:
        name = f"{last_name} {first_name}"
        if isinstance(uci_id, str) and uci_id in file_rider_id_by_uci_id:
            same_uci_id.append(
                f"{name}: {rider_id!r} in database -> "
                f"{file_rider_id_by_uci_id[uci_id]!r} in file (UCI ID {uci_id})"
            )
            continue
        if not (isinstance(uci_id, str) and is_valid_uci_id(uci_id)):
            matches = [
                (file_rider_id, file_uci_id)
                for file_rider_id, file_uci_id, file_last, file_first in file_riders_with_uci_id
                if _names_match(last_name, first_name, file_last, file_first)
            ]
            if len(matches) == 1:
                file_rider_id, file_uci_id = matches[0]
                status = "red list" if uci_id == "Liste Rouge" else "no UCI ID"
                gained_uci_id.append(
                    f"{name} ({status}): {rider_id!r} in database -> "
                    f"{file_rider_id!r} in file (UCI ID {file_uci_id})"
                )
                continue
        unknown.append(f"{name}: {rider_id!r} (UCI ID field: {uci_id!r})")

    lines = []
    if gained_uci_id:
        lines.append(
            f"Riders without UCI ID in the database who now appear with a UCI ID in the "
            f"file ({len(gained_uci_id)}):"
        )
        lines += [f"  {line}" for line in gained_uci_id]
    if same_uci_id:
        lines.append(f"Riders whose UCI ID has another rider_id in the file ({len(same_uci_id)}):")
        lines += [f"  {line}" for line in same_uci_id]
    if unknown:
        lines.append(
            f"Riders missing for an unknown reason, check the transform step first "
            f"({len(unknown)}):"
        )
        lines += [f"  {line}" for line in unknown]
    return lines


def check_missing_rows(table: Table, df: pd.DataFrame, connection: Connection | None) -> list[str]:
    """Check that the rows already in the database are all present in the file.

    Only applies to the tables of NO_MISSING_ROWS. For riders, every missing
    rider is explained (see explain_missing_riders) and the cleaning commands
    are given.
    """
    if connection is None or table.name not in NO_MISSING_ROWS:
        return []
    if count_rows(connection, table) == 0:
        return []
    is_riders = table.name == "riders"
    count, rows = find_missing_rows(
        connection,
        table,
        df,
        columns=["rider_id", "uci_id", "last_name", "first_name"] if is_riders else None,
        limit=MAX_DIAGNOSED_RIDERS if is_riders else MAX_EXAMPLES,
    )
    if count == 0:
        return []
    if not is_riders:
        examples = [row[0] for row in rows] if len(rows[0]) == 1 else rows
        return [
            f"[{table.name}] {count} row(s) in database missing from file, "
            f"e.g. {format_examples(examples)}: identifiers probably changed since the last load"
        ]
    lines = [
        f"[riders] {count} rider(s) in database missing from file: "
        f"identifiers probably changed since the last load"
    ]
    lines += [f"    {line}" for line in explain_missing_riders(rows, df)]
    if count > len(rows):
        lines.append(f"    ... and {count - len(rows)} other rider(s)")
    lines += [f"    {line}" for line in CLEANING_INSTRUCTIONS]
    return ["\n".join(lines)]


def run_checks(frames: dict[str, pd.DataFrame], engine: Engine | None = None) -> None:
    """Run every check on the DataFrames to load.

    The database is only read, never written.

    Args:
        frames: DataFrames to load, keyed by table name.
        engine: Engine of the database, or None for an empty database.

    Raises:
        DataValidationError: If at least one check fails (all the problems
            found are listed).
    """
    problems = []
    with (engine.connect() if engine is not None else nullcontext()) as connection:
        for table in Base.metadata.sorted_tables:
            if table.name not in frames:
                continue
            df = frames[table.name]
            problems += check_primary_key(table, df)
            problems += check_foreign_keys(table, df, frames, connection)
            problems += check_row_count(table, df, connection)
            problems += check_missing_rows(table, df, connection)
    if problems:
        raise DataValidationError(problems)
