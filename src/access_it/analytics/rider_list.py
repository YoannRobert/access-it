"""List of the riders on the reference date, its filters and the choices of each filter.

Rules:

- the list has one row per rider with at least one result of a season from
  FIRST_SEASON, strictly before the reference date (by default, the day after
  the last race of the table: see get_reference_date);
- the category and the club of a rider are those of his last periods started
  strictly before the reference date (UNKNOWN_CATEGORY or UNKNOWN_CLUB if
  unknown); the departement and the region are those of the club, missing if
  the club is unknown or belongs to a fictitious committee (individual
  licensees of unknown committee, foreign riders);
- the list is sorted by normalized last name, normalized first name, then
  rider_id; a name is normalized without case nor accents, hyphens and
  apostrophes replaced by a space, runs of spaces reduced to one, and without
  leading or trailing space;
- the last name filter keeps the riders whose normalized last name contains
  the normalized text; the first name, departement and club filters keep the
  equal values; the region filter keeps the requested regions (only those of
  COVERED_REGIONS are accepted); no region or an empty list of regions means
  no region filter;
- as soon as a region, a departement or a club is requested, only the riders
  of a region of COVERED_REGIONS are kept; without these filters, the riders
  of an unknown club or of another region are kept;
- the choices of a filter (faceted filters) are the values of the riders kept
  by all the other filters, without its own; the choices of region,
  departement and club are limited to the riders of COVERED_REGIONS.

The rider_id of each row leads to the profile of the rider (see
rider_profile). The computation is free of any Streamlit dependency.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from access_it.analytics.labels import UNKNOWN_CATEGORY
from access_it.analytics.ranking_tools import (
    add_category_on_race_date, add_club_location, add_value_on_race_date, check_race_dates,
    format_club, to_datetime, to_day
)
from access_it.common.regions import COVERED_REGIONS, check_covered_region
from access_it.common.seasons import FIRST_SEASON
from access_it.common.text import collapse_spaces, normalize_string_and_fold_case
from access_it.etl.extract.constants import FOREIGN_CLUB_ID, INDIVIDUAL_CLUB_ID

RIDER_LIST_COLUMNS = [
    "last_name", "first_name", "category", "club", "departement_code", "departement_name",
    "region", "club_id", "rider_id"
]

# Regional committees of the pseudo-clubs without a real committee
FICTITIOUS_REGIONAL_COMMITTEE_IDS = (INDIVIDUAL_CLUB_ID[:2], FOREIGN_CLUB_ID[:2])


@dataclass(frozen=True)
class RiderFilterChoices:
    """Choices of each filter of the rider list (see get_filter_choices).

    Attributes:
        first_names: First names, sorted by normalized first name, then as stored.
        regions: Regions, in the order of COVERED_REGIONS.
        departements: departement_code and departement_name, sorted by code.
        clubs: club_id and club, sorted by normalized club name, then club_id.
    """
    first_names: tuple[str, ...]
    regions: tuple[str, ...]
    departements: pd.DataFrame
    clubs: pd.DataFrame


def _normalize_name(name: str) -> str:
    """Name without case nor accents, hyphens and apostrophes replaced by a space,
    runs of spaces reduced to one, without leading or trailing space."""
    return collapse_spaces(
        normalize_string_and_fold_case(re.sub(r"[-'’]", " ", name))
    ).strip()


def build_rider_list(
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        riders: pd.DataFrame,
        clubs: pd.DataFrame,
        affiliations: pd.DataFrame,
        rider_categories: pd.DataFrame,
        departements: pd.DataFrame,
        departemental_committees: pd.DataFrame,
        regional_committees: pd.DataFrame,
        reference_date: str | pd.Timestamp
    ) -> pd.DataFrame:
    """Riders on the reference date (see the module docstring for the rules).

    Args:
        races: Race table.
        rankings: Ranking table.
        riders: Rider table.
        clubs: Club table.
        affiliations: Affiliation table (club history of the riders).
        rider_categories: Category history of the riders.
        departements: Departement table.
        departemental_committees: Departemental committee table.
        regional_committees: Regional committee table.
        reference_date: Day of the analysis, as "YYYY-MM-DD" or a date; its
            races and the later ones are excluded.

    Returns:
        One row per rider kept: the RIDER_LIST_COLUMNS, with the category
        ("A1" to "A4" or UNKNOWN_CATEGORY), the club name (or UNKNOWN_CLUB),
        the departement and the region (name of the regional committee),
        missing if unknown, and the club_id, missing if unknown; sorted by
        normalized last name, normalized first name, then rider_id; empty if
        no rider is kept.

    Raises:
        ValueError: If the reference date is missing, then if a ranked race
            has no date, then if a start date of a rider kept in
            rider_categories is missing, then if a start date of a rider kept
            in affiliations is missing.
    """
    day = to_day(reference_date)
    results = rankings[["race_id", "rider_id"]].merge(
        races[["race_id", "race_date", "season"]], on="race_id"
    )
    race_dates = to_datetime(results["race_date"])
    check_race_dates(race_dates)
    rider_ids = results.loc[
        (results["season"] >= FIRST_SEASON) & (race_dates < day), "rider_id"
    ].unique()

    # The day before the reference date gives the last periods started strictly before it
    riders_on_day = pd.DataFrame({"rider_id": rider_ids, "race_date": day - pd.Timedelta(days=1)})
    riders_on_day = add_category_on_race_date(riders_on_day, rider_categories)
    riders_on_day = add_value_on_race_date(riders_on_day, affiliations, "club_id")
    # astype(object): a column of unknown categories only keeps the integer dtype of the history
    riders_on_day["category"] = (
        riders_on_day["category"].astype(object).fillna(UNKNOWN_CATEGORY).astype(str)
    )
    riders_on_day["club"] = format_club(riders_on_day["club_id"], clubs)

    rider_list = add_club_location(riders_on_day, clubs, departements, departemental_committees)
    is_fictitious = rider_list["regional_committee_id"].isin(FICTITIOUS_REGIONAL_COMMITTEE_IDS)
    location = ["departement_code", "departement_name", "regional_committee_id"]
    rider_list[location] = rider_list[location].astype(object).where(~is_fictitious, None)
    rider_list["region"] = rider_list["regional_committee_id"].map(
        regional_committees.set_index("regional_committee_id")["name"]
    )
    rider_list = rider_list.merge(
        riders[["rider_id", "last_name", "first_name"]], on="rider_id", how="left"
    )

    rider_list["sort_last_name"] = rider_list["last_name"].map(_normalize_name)
    rider_list["sort_first_name"] = rider_list["first_name"].map(_normalize_name)
    return (
        rider_list
        .sort_values(["sort_last_name", "sort_first_name", "rider_id"])
        [RIDER_LIST_COLUMNS]
        .reset_index(drop=True)
    )


def filter_riders(
        rider_list: pd.DataFrame,
        last_name: str | None = None,
        first_name: str | None = None,
        regions: Sequence[str] | None = None,
        departement_code: str | None = None,
        club_id: str | None = None
    ) -> pd.DataFrame:
    """Riders of the list kept by the filters (see the module docstring for the rules).

    Args:
        rider_list: Output of build_rider_list.
        last_name: Text to find in the last name; None or a text empty once
            normalized for no filter.
        first_name: First name, as stored; None for no filter.
        regions: Requested regions, among COVERED_REGIONS; None or an empty
            list for no filter.
        departement_code: Code of the requested departement; None for no filter.
        club_id: ID of the requested club; None for no filter.

    Returns:
        The rows kept, with all the columns, in the order of `rider_list`,
        with the index reset; empty if no rider is kept.

    Raises:
        ValueError: If a requested region is not covered.
    """
    for region in regions or ():
        check_covered_region(region)
    keep = pd.Series(True, index=rider_list.index)
    if last_name is not None and (text := _normalize_name(last_name)):
        keep &= rider_list["last_name"].map(_normalize_name).str.contains(text, regex=False)
    if first_name is not None:
        keep &= rider_list["first_name"].eq(first_name).fillna(False)
    if regions:
        keep &= rider_list["region"].isin(regions)
    if regions or departement_code is not None or club_id is not None:
        keep &= rider_list["region"].isin(COVERED_REGIONS)
    if departement_code is not None:
        keep &= rider_list["departement_code"].eq(departement_code).fillna(False)
    if club_id is not None:
        keep &= rider_list["club_id"].eq(club_id).fillna(False)
    return rider_list[keep.astype(bool)].reset_index(drop=True)


def get_filter_choices(
        rider_list: pd.DataFrame,
        last_name: str | None = None,
        first_name: str | None = None,
        regions: Sequence[str] | None = None,
        departement_code: str | None = None,
        club_id: str | None = None
    ) -> RiderFilterChoices:
    """Choices of each filter, given the other filters (see the module docstring for the rules).

    Args:
        rider_list: Output of build_rider_list.
        last_name: See filter_riders.
        first_name: See filter_riders.
        regions: See filter_riders.
        departement_code: See filter_riders.
        club_id: See filter_riders.

    Returns:
        The choices of each filter, computed by filter_riders without that
        filter; empty if no rider is kept.

    Raises:
        ValueError: If a requested region is not covered.
    """
    filters = {
        "last_name": last_name, "first_name": first_name, "regions": regions,
        "departement_code": departement_code, "club_id": club_id,
    }

    def kept_without(name: str, covered_only: bool) -> pd.DataFrame:
        """Riders kept by all the filters except `name`, of the covered regions if requested."""
        kept = filter_riders(rider_list, **(filters | {name: None}))
        return kept[kept["region"].isin(COVERED_REGIONS)] if covered_only else kept

    first_names = kept_without("first_name", covered_only=False)["first_name"].drop_duplicates()
    regions_kept = set(kept_without("regions", covered_only=True)["region"])
    departements = (
        kept_without("departement_code", covered_only=True)
        [["departement_code", "departement_name"]]
        .drop_duplicates("departement_code")
        .sort_values("departement_code")
        .reset_index(drop=True)
    )
    clubs = (
        kept_without("club_id", covered_only=True)[["club_id", "club"]]
        .drop_duplicates("club_id")
        .assign(sort_club=lambda df: df["club"].map(_normalize_name))
        .sort_values(["sort_club", "club_id"])
        .drop(columns="sort_club")
        .reset_index(drop=True)
    )
    return RiderFilterChoices(
        first_names=tuple(sorted(first_names, key=lambda name: (_normalize_name(name), name))),
        regions=tuple(region for region in COVERED_REGIONS if region in regions_kept),
        departements=departements,
        clubs=clubs,
    )
