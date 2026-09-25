import pandas as pd
from sqlalchemy import Engine, Select, Table, select

from access_it.etl.load.models import Base


def _read_dataframe(engine: Engine, statement: Select) -> pd.DataFrame:
    """Execute a SELECT statement and return the result as a DataFrame."""
    with engine.connect() as connection:
        return pd.read_sql(statement, connection)


def read_table(
        engine: Engine,
        table: Table,
        first_rows: int | None = None
    ) -> pd.DataFrame:
    """Return the full content of a table."""
    statement = select(table)
    if first_rows is not None:
        statement = statement.limit(first_rows)
    return _read_dataframe(engine, statement)


def read_all_tables(
        engine: Engine,
        first_rows: int | None = None
    ) -> dict[str, pd.DataFrame]:
    """Return the full content of every table, keyed by table name."""
    return {
        name: read_table(engine, table, first_rows=first_rows)
        for name, table in Base.metadata.tables.items()
    }


if __name__ == "__main__":
    from access_it.etl.load.engine import get_engine
    limit = 2
    tables = read_all_tables(get_engine(), first_rows=limit)
    for table_name, df in tables.items():
        print(f"{table_name}:\n{df.head(5)}", end="\n\n")
