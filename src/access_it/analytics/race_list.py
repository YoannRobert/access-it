"""List of the races held in a region over a period, for the choice of a race.

Rules:

- the races are those held in the departements of the region (the place of
  the race, not the region of the riders), all of them or only the requested
  ones; only the regions of COVERED_REGIONS are accepted;
- the period may cover several seasons; both dates are included; it must not
  start before the first season FIRST_SEASON;
- a race without any ranked rider (e.g. a cancelled race) is left out;
- a race is kept if it has at least one of the requested categories; the
  requested categories must be contiguous (given in any order, duplicates
  removed), and so must the categories of the ranked races of the period;
- no statistic on the size of the field is given.

The race_id of each race leads to its summary (see race_summary). The
computation is free of any Streamlit dependency.
"""

from collections.abc import Sequence

import pandas as pd

from access_it.analytics.ranking_tools import (
    CATEGORIES, check_categories, check_race_categories, check_race_dates,
    get_region_departement_codes, get_regional_committee_id, has_requested_category,
    to_datetime, to_day
)
from access_it.common.regions import check_covered_region
from access_it.common.seasons import check_season

RACE_LIST_COLUMNS = [
    "race_date", "title", "categories", "departement_code", "departement_name", "race_id"
]


def _check_departement_codes(
        departement_codes: Sequence[str] | None,
        region_codes: pd.Series
    ) -> pd.Series:
    """Codes of the departements kept: all those of the region, or the requested ones.

    Raises:
        ValueError: If no departement is requested, then if a requested
            departement is not one of the region.
    """
    if departement_codes is None:
        return region_codes
    if len(departement_codes) == 0:
        raise ValueError("No departement requested")
    outside = sorted(set(departement_codes) - set(region_codes))
    if outside:
        raise ValueError(f"Departements not in the region: {outside!r}")
    return region_codes[region_codes.isin(departement_codes)]


def list_races(
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        departements: pd.DataFrame,
        departemental_committees: pd.DataFrame,
        regional_committees: pd.DataFrame,
        start_date: str | pd.Timestamp,
        end_date: str | pd.Timestamp,
        region: str,
        departement_codes: Sequence[str] | None = None,
        categories: Sequence[str] = CATEGORIES
    ) -> pd.DataFrame:
    """Races held in a region over a period (see the module docstring for the rules).

    Args:
        races: Race table.
        rankings: Ranking table.
        departements: Departement table.
        departemental_committees: Departemental committee table.
        regional_committees: Regional committee table.
        start_date: First day of the period (included), as a string or a timestamp.
        end_date: Last day of the period (included), as a string or a timestamp.
        region: Name of the regional committee, one of COVERED_REGIONS.
        departement_codes: Codes of the requested departements of the region,
            in any order, duplicates allowed; None for all of them.
        categories: Requested categories, contiguous, in any order ("A1" to "A4").

    Returns:
        One row per race kept: the RACE_LIST_COLUMNS, with race_date converted
        by to_datetime and departement_name missing if unknown; sorted from
        the most recent race to the oldest one, then by race_id in descending
        order; empty if no race is kept.

    Raises:
        ValueError: If the region is not covered, then if the start date,
            then the end date, is missing, then if the end date is before the
            start date, then if the start date is before the first season
            FIRST_SEASON, then if the region is unknown, then if
            departement_codes is empty, then if one of them is not a
            departement of the region, then if the requested categories are
            invalid (see check_categories), then if a ranked race of the kept
            departements has no date, then if a ranked race of the period and
            of these departements has non contiguous categories.
    """
    check_covered_region(region)
    start = to_day(start_date, "start date")
    end = to_day(end_date, "end date")
    if end < start:
        raise ValueError(f"End date {end.date()} is before the start date {start.date()}")
    check_season(start.year)
    region_id = get_regional_committee_id(regional_committees, region)
    region_codes = get_region_departement_codes(departemental_committees, region_id)
    kept_codes = _check_departement_codes(departement_codes, region_codes)
    requested = check_categories(categories)

    ranked = races[
        races["departement_code"].isin(kept_codes) & races["race_id"].isin(rankings["race_id"])
    ]
    ranked = ranked.assign(race_date=to_datetime(ranked["race_date"]))
    check_race_dates(ranked["race_date"])
    period = ranked[ranked["race_date"].between(start, end)]
    check_race_categories(period)
    kept = period[has_requested_category(period["categories"], requested)]
    return (
        kept
        .merge(
            departements[["departement_code", "departement_name"]],
            on="departement_code", how="left"
        )
        [RACE_LIST_COLUMNS]
        .sort_values(["race_date", "race_id"], ascending=False)
        .reset_index(drop=True)
    )
