"""Export the entries and the forecasts of the upcoming races to the S3 storage.

Both Parquet files are uploaded with the same timestamp, the entries first, and
the 100 most recent files of each kind are kept; nothing is uploaded if the
file of the forecasts is empty (see export_upcoming_entries_and_forecasts).

Usage, from the repository root, after an extraction of the entries and a forecast:
    python scripts/export_upcoming_entries_and_forecasts_to_s3_bucket.py \
        --entries PATH --forecasts PATH
"""

import argparse
from pathlib import Path

from access_it.common.log import setup_logging
from access_it.config import get_settings
from access_it.export.upcoming import export_upcoming_entries_and_forecasts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export the entries and the forecasts of the upcoming races to the S3 storage."
    )
    parser.add_argument(
        "--entries", type=Path, required=True,
        help="Parquet file of the entries, written by extract_upcoming_entries.py"
    )
    parser.add_argument(
        "--forecasts", type=Path, required=True,
        help="Parquet file of the forecasts, written by forecast_upcoming_races.py"
    )
    return parser.parse_args()


def export_upcoming_entries_and_forecasts_to_s3_bucket(
        entries_path: Path, forecasts_path: Path
    ) -> None:
    """Upload the entries and the forecasts, then delete the old files, unless no race is forecast.

    Args:
        entries_path: Parquet file of the entries.
        forecasts_path: Parquet file of the forecasts.
    """
    exported = export_upcoming_entries_and_forecasts(
        entries_path, forecasts_path, bucket=get_settings().s3_bucket
    )
    if exported is None:
        print("No forecast: nothing exported to the S3 bucket.")
        return
    entries_uri, forecasts_uri, deleted_keys = exported
    print(f"Entries exported to {entries_uri} on the S3 bucket.")
    print(f"Forecasts exported to {forecasts_uri} on the S3 bucket.")
    for deleted_key in deleted_keys:
        print(f"File {deleted_key} got deleted from the S3 bucket.")


if __name__ == "__main__":
    setup_logging()
    args = parse_args()
    export_upcoming_entries_and_forecasts_to_s3_bucket(args.entries, args.forecasts)
