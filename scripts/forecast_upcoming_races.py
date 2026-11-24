"""Forecast the riders entered in the upcoming races.

The entries are read from a Parquet file written by extract_upcoming_entries.py,
then forecast from the race and ranking tables of the transform (see
forecast_upcoming_entries). A summary is printed; the forecasts can be written
to a Parquet file.

Usage, from the repository root, after a transform and an extraction of the entries:
    python scripts/forecast_upcoming_races.py --entries PATH [--output PATH]
"""

import argparse
from pathlib import Path

import pandas as pd

from access_it.common.log import setup_logging
from access_it.etl.extract.cache import RACES_PARQUET_FILE, RANKINGS_PARQUET_FILE
from access_it.model.upcoming import forecast_upcoming_entries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Forecast the riders entered in the upcoming races."
    )
    parser.add_argument(
        "--entries", type=Path, required=True,
        help="Parquet file of the entries, written by extract_upcoming_entries.py"
    )
    parser.add_argument(
        "--output", type=Path, help="Parquet file to write the forecasts to (default: none)"
    )
    return parser.parse_args()


def forecast_upcoming_races(entries_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Forecast the entries of a Parquet file.

    Args:
        entries_path: Parquet file of the entries.

    Returns:
        The entries, then their forecasts (see forecast_upcoming_entries).
    """
    races = pd.read_parquet(RACES_PARQUET_FILE)
    rankings = pd.read_parquet(RANKINGS_PARQUET_FILE)
    entries = pd.read_parquet(entries_path)
    return entries, forecast_upcoming_entries(races, rankings, entries)


def print_summary(entries: pd.DataFrame, forecasts: pd.DataFrame) -> None:
    """Print the numbers of races and entries, then one line per race, forecast or not."""
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
        .assign(forecast=lambda df: df["race_id"].isin(forecasts["race_id"]))
    )
    nb_forecast = races["forecast"].sum()
    print(
        f"{len(races)} races, {len(entries)} entries: {nb_forecast} races forecast, "
        f"{len(races) - nb_forecast} not forecast"
    )
    for race in races.itertuples():
        status = "forecast" if race.forecast else "not forecast"
        print(
            f"  {race.race_date.date()}  {race.race_id:16s} {race.riders:4d}  {status:12s}  "
            f"{race.heading} | {race.title}"
        )


def main(entries_path: Path, output: Path | None = None) -> None:
    """Forecast the entries of `entries_path`, print a summary and write the forecasts.

    Args:
        entries_path: Parquet file of the entries.
        output: Parquet file to write the forecasts to, even without forecast;
            nothing is written if None.
    """
    entries, forecasts = forecast_upcoming_races(entries_path)
    print_summary(entries, forecasts)
    if output is not None:
        forecasts.to_parquet(output, index=False)
        print(f"Forecasts written to {output}")


if __name__ == "__main__":
    setup_logging()
    args = parse_args()
    main(args.entries, args.output)
