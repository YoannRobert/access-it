"""Check how the riders of the startlists are identified (read-only).

The riders of the startlists are identified by their exact full name, or
failing that by a red-list name (last name and initial of the first name) or
by a broader search (names contained in the rider names). These two
fallback searches could give the category of a rider to a homonym of the
same club: this script lists their matches for review. Nothing is written.

Usage, from the repository root, after a transform:
python scripts/check_startlist_matches.py
"""

from collections import Counter

import pandas as pd

from access_it.etl.extract.cache import (
    AFFILIATIONS_PARQUET_FILE, CLUBS_PARQUET_FILE, DEPCOM_PARQUET_FILE,
    REGCOM_PARQUET_FILE, RIDERS_PARQUET_FILE
)
from access_it.etl.transform.startlists import identify_riders_categories_on_startlists

FALLBACK_METHODS = ["red list", "broader"]


def check_startlist_matches():
    """Print the number of identifications by search, and the fallback matches."""
    riders = pd.read_parquet(RIDERS_PARQUET_FILE)
    matches = identify_riders_categories_on_startlists(
        clubs=pd.read_parquet(CLUBS_PARQUET_FILE),
        riders=riders,
        affiliations=pd.read_parquet(AFFILIATIONS_PARQUET_FILE),
        departemental_committees=pd.read_parquet(DEPCOM_PARQUET_FILE),
        regional_committees=pd.read_parquet(REGCOM_PARQUET_FILE),
        details=True
    )
    rider_names = {
        row.rider_id: f"{row.last_name} {row.first_name} ({row.uci_id or 'no UCI ID'})"
        for row in riders.itertuples()
    }
    print("\nIdentifications by search:")
    for method, count in Counter(matches["match_method"]).most_common():
        print(f"  {method:8s}: {count}")
    for method in FALLBACK_METHODS:
        pairs = Counter(
            (row.full_name, row.rider_id)
            for row in matches[matches["match_method"] == method].itertuples()
        )
        print(f"\n{method} matches ({len(pairs)} distinct), startlist name -> rider:")
        for (full_name, rider_id), count in sorted(pairs.items()):
            print(f"  {full_name} -> {rider_names.get(rider_id, rider_id)}  x {count}")


if __name__ == "__main__":
    check_startlist_matches()
