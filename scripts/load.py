"""Load step: write the Parquet files of the transform step into the database.

Missing tables are created; the files are checked before any write (see
access_it.etl.load.checks).

Usage, from the repository root: python scripts/load.py
"""

from access_it.common.log import setup_logging
from access_it.etl.load.engine import get_engine
from access_it.etl.load.load import load_all
from access_it.etl.load.schema import create_tables


def load():
    """Run the load step."""
    engine = get_engine()
    create_tables(engine)
    load_all(engine)


if __name__ == "__main__":
    setup_logging()
    load()
