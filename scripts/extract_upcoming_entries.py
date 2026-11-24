"""Extract the entries of the upcoming races from the startlists website.

The startlist pages of the races held from the start date are requested
(nothing is cached), then their Access races and their riders identified in
the Parquet tables of the transform. A summary is printed; the entries can be
written to a Parquet file. By default, the start date is the day after the last
race of the transform.

Usage, from the repository root, after a transform:
    python scripts/extract_upcoming_entries.py [--start-date YYYY-MM-DD] [--output PATH]
"""

import argparse
from datetime import date as Date
from pathlib import Path

import pandas as pd

from access_it.analytics.ranking_tools import get_reference_date
from access_it.common.log import setup_logging
from access_it.etl.extract.cache import (
    AFFILIATIONS_PARQUET_FILE, CLUBS_PARQUET_FILE, DEPARTEMENTS_PARQUET_FILE,
    DEPCOM_PARQUET_FILE, RACES_PARQUET_FILE, REGCOM_PARQUET_FILE, RIDERS_PARQUET_FILE
)
from access_it.etl.extract.client import make_client
from access_it.etl.extract.upcoming_startlists import extract_upcoming_startlist_pages
from access_it.etl.transform.upcoming_entries import build_upcoming_entries


def iso_date(text: str) -> str:
    """Date given as YYYY-MM-DD, checked (ValueError if invalid)."""
    return Date.fromisoformat(text).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract the entries of the upcoming races from the startlists website."
    )
    parser.add_argument(
        "--start-date", type=iso_date,
        help=(
            "first race date, as YYYY-MM-DD "
            "(default: the day after the last race of the transform)"
        )
    )
    parser.add_argument(
        "--output", type=Path, help="Parquet file to write the entries to (default: none)"
    )
    return parser.parse_args()


def extract_upcoming_entries(start_date: str | None = None) -> pd.DataFrame:
    """Extract the entries of the races held from a start date.

    The Parquet tables of the transform are read before any request, so that
    a missing table stops the script at once.

    Args:
        start_date: First race date ('YYYY-MM-DD'); if None, the day after the
            last race of the transform (see get_reference_date).

    Returns:
        The entries (see build_upcoming_entries).
    """
    if start_date is None:
        races = pd.read_parquet(RACES_PARQUET_FILE)
        start_date = get_reference_date(races).date().isoformat()
        print(f"Start date: {start_date} (the day after the last race of the transform)")
    clubs = pd.read_parquet(CLUBS_PARQUET_FILE)
    riders = pd.read_parquet(RIDERS_PARQUET_FILE)
    affiliations = pd.read_parquet(AFFILIATIONS_PARQUET_FILE)
    departements = pd.read_parquet(DEPARTEMENTS_PARQUET_FILE)
    departemental_committees = pd.read_parquet(DEPCOM_PARQUET_FILE)
    regional_committees = pd.read_parquet(REGCOM_PARQUET_FILE)
    with make_client() as client:
        pages = extract_upcoming_startlist_pages(client=client, start_date=start_date)
    print(f"{len(pages)} startlist pages read for the races from {start_date}")
    return build_upcoming_entries(
        pages, clubs, riders, affiliations, departements,
        departemental_committees, regional_committees
    )


def print_summary(entries: pd.DataFrame) -> None:
    """Print the number of races and entries, then one line per race."""
    if entries.empty:
        print("No entries")
        return
    races = (
        entries
        .groupby(["race_date", "race_id"], sort=True)
        .agg(
            riders=("rider_id", "size"),
            heading=("startlist_heading", "first"),
            title=("page_title", "first"),
        )
        .reset_index()
    )
    print(f"{len(races)} races, {len(entries)} entries")
    for race in races.itertuples():
        print(
            f"  {race.race_date.date()}  {race.race_id:16s} {race.riders:4d}  "
            f"{race.heading} | {race.title}"
        )


def main(start_date: str | None, output: Path | None = None) -> None:
    """Extract the entries of the races held from `start_date`, print them and write them.

    Args:
        start_date: First race date ('YYYY-MM-DD'); if None, the day after the
            last race of the transform.
        output: Parquet file to write the entries to, even without entries;
            nothing is written if None.
    """
    entries = extract_upcoming_entries(start_date)
    print_summary(entries)
    if output is not None:
        entries.to_parquet(output, index=False)
        print(f"Entries written to {output}")


if __name__ == "__main__":
    setup_logging()
    args = parse_args()
    main(args.start_date, args.output)
