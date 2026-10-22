"""Delete from the database the riders missing from the riders file (stale rider IDs).

Usage (from the repository root):
    python scripts/prune_stale_rows.py           # dry run: shows what would be deleted
    python scripts/prune_stale_rows.py --apply   # deletes, in a single transaction

Then run the load again: python scripts/load.py
"""

import argparse
import sys

from access_it.common.log import setup_logging
from access_it.etl.load.engine import get_engine
from access_it.etl.load.load import read_parquet
from access_it.etl.load.models import Base
from access_it.etl.load.prune import (
    MAX_STALE_RIDERS, TooManyStaleRiders, format_report, prune_stale_riders,
    tables_referring_to_riders
)


def prune_stale_rows() -> None:
    """Parse the arguments, then delete (or count) the stale riders."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="delete the rows (default: dry run)")
    parser.add_argument(
        "--max-riders",
        type=int,
        default=MAX_STALE_RIDERS,
        help=f"refuse to act above this number of stale riders (default: {MAX_STALE_RIDERS})",
    )
    args = parser.parse_args()

    riders = read_parquet(Base.metadata.tables["riders"])
    frames = {table.name: read_parquet(table) for table in tables_referring_to_riders()}
    try:
        report = prune_stale_riders(
            get_engine(), riders, frames, apply=args.apply, max_riders=args.max_riders
        )
    except TooManyStaleRiders as error:
        print(f"Error: {error}")
        sys.exit(1)
    print(format_report(report))


if __name__ == "__main__":
    setup_logging()
    prune_stale_rows()
