"""Category changes of the riders in a season: promotions, demotions and first appearances.

Rules:

- the changes are read in the category history of the riders
  (rider_categories); the periods of unknown category (years without race,
  riders whose whole history is unknown) are ignored: each known category is
  compared with the previous known category of the rider;
- a known category higher than the previous one (e.g. A3 to A2) is a
  promotion, a lower one a demotion; the first known category of a rider is
  a first appearance, without departure category; a rider back after one or
  several years without race is shown only if his category changed, his
  departure category being his last known one before the break;
- the date of a change is the start date of its period: January 1st for a
  change between two seasons, a return or a first appearance at the first
  race of the year, the race date for a change during the season; the
  season of a change is the year of this date; a rider changing N times in
  the season has N rows;
- the first appearances of FIRST_SEASON are left out: the data start this
  season, when every rider appears for the first time;
- the club shown is the club of the rider on the date of the change
  (UNKNOWN_CLUB if unknown); with a region (one of COVERED_REGIONS), only
  the changes of the riders whose club on this date belongs to the region
  are kept, individual licensees of its committees included and unknown
  clubs left out;
- with a category, only the changes to this category are kept;
- the riders absent from the rider table are left out.

Known limits:

- the category history is partly heuristic (categories deduced from the
  results and the startlists): a change may be missing, wrong or misdated;
- the races and rankings only cover the races held in Bretagne and Pays de
  la Loire: a first appearance may be the first race of a rider in these
  regions, and the riders of the other regions are only followed on their
  races there;
- the club comes from the results only: a rider only seen on startlists has
  an unknown club.

The computation is free of any Streamlit dependency.
"""

import pandas as pd

from access_it.analytics.labels import DEMOTION, FIRST_APPEARANCE, PROMOTION
from access_it.analytics.ranking_tools import (
    add_value_on_race_date, check_category, format_category, format_club, get_region_club_ids,
    get_regional_committee_id, to_datetime
)
from access_it.common.regions import check_covered_region
from access_it.common.seasons import FIRST_SEASON, check_season

CATEGORY_CHANGE_COLUMNS = [
    "season", "change_date", "change_type", "from_category", "to_category",
    "last_name", "first_name", "club"
]

# Order of the types of change in the output
_CHANGE_TYPE_ORDER = {PROMOTION: 0, DEMOTION: 1, FIRST_APPEARANCE: 2}


def compute_category_changes(
        rider_categories: pd.DataFrame,
        riders: pd.DataFrame,
        clubs: pd.DataFrame,
        affiliations: pd.DataFrame,
        departemental_committees: pd.DataFrame,
        regional_committees: pd.DataFrame,
        season: int,
        region: str | None = None,
        category: str | None = None
    ) -> pd.DataFrame:
    """Category changes of the riders in a season (see the rules of the module).

    Args:
        rider_categories: Category history of the riders.
        riders: Rider table.
        clubs: Club table.
        affiliations: Affiliation table (club history of the riders).
        departemental_committees: Departemental committee table.
        regional_committees: Regional committee table.
        season: Calendar year of the changes.
        region: Name of the regional committee, one of COVERED_REGIONS, to
            keep the riders whose club on the date of the change belongs to
            it, or None for every rider.
        category: Category of arrival to keep ("A1" to "A4"), or None for
            every category.

    Returns:
        One row per change: the CATEGORY_CHANGE_COLUMNS, with change_date as
        datetime64, change_type PROMOTION, DEMOTION or FIRST_APPEARANCE,
        from_category and to_category "A1" to "A4" (from_category missing for
        a first appearance) and the club name (UNKNOWN_CLUB if unknown);
        sorted by change date, type of change (promotion, demotion, first
        appearance), category of arrival, last name, first name and rider_id.

    Raises:
        ValueError: If the season is before FIRST_SEASON, if the region is
            not covered or unknown, or if the category is not "A1" to "A4".
    """
    check_season(season)
    if region is not None:
        check_covered_region(region)
        region_id = get_regional_committee_id(regional_committees, region)
    if category is not None:
        check_category(category)

    history = (
        rider_categories.loc[
            rider_categories["rider_category"].notna(),
            ["rider_id", "start_date", "rider_category"]
        ]
        .assign(
            start_date=lambda df: to_datetime(df["start_date"]),
            rider_category=lambda df: df["rider_category"].astype(int)
        )
        .sort_values(["rider_id", "start_date"])
    )
    history["previous_category"] = history.groupby("rider_id")["rider_category"].shift()
    changes = history[
        history["previous_category"].isna()
        | (history["rider_category"] != history["previous_category"])
    ]
    changes = changes[changes["start_date"].dt.year == season]
    changes = changes.assign(
        change_type=pd.Series(DEMOTION, index=changes.index)
        .mask(changes["rider_category"] < changes["previous_category"], PROMOTION)
        .mask(changes["previous_category"].isna(), FIRST_APPEARANCE),
        from_category=changes["previous_category"].map(format_category),
        to_category=changes["rider_category"].map(format_category)
    )
    if season == FIRST_SEASON:
        changes = changes[changes["change_type"] != FIRST_APPEARANCE]
    if category is not None:
        changes = changes[changes["to_category"] == category]

    # Club of the rider on the date of the change
    changes = add_value_on_race_date(
        changes.rename(columns={"start_date": "race_date"}), affiliations, "club_id"
    ).rename(columns={"race_date": "change_date"})
    if region is not None:
        region_club_ids = get_region_club_ids(clubs, departemental_committees, region_id)
        changes = changes[changes["club_id"].isin(region_club_ids)]

    changes = changes.assign(
        season=season,
        club=format_club(changes["club_id"], clubs),
        change_type_order=changes["change_type"].map(_CHANGE_TYPE_ORDER)
    ).merge(riders[["rider_id", "last_name", "first_name"]], on="rider_id")
    return (
        changes.sort_values([
            "change_date", "change_type_order", "to_category", "last_name", "first_name",
            "rider_id"
        ])
        [CATEGORY_CHANGE_COLUMNS]
        .reset_index(drop=True)
    )
