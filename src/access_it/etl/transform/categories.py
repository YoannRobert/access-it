"""Access categories of races and riders: categories of the rankings, and category history.

The Access categories range from A1 (highest level) to A4. A race is open to
one or several consecutive categories; the category of a rider is inferred
from the races he takes part in (results and startlists), then aggregated
into a history of periods (one row per period, starting at start_date).
"""

import logging
import pandas as pd

from datetime import datetime
from typing import Literal, Any
from access_it.common.access_categories import find_access_categories_from_name
from access_it.common.seasons import FIRST_SEASON

logger = logging.getLogger(__name__)


def find_ranking_categories(organization_data: dict[str, Any]) -> dict[str, dict[int, bool]]:
    """Assign Access categories to each ranking of an organization (a result page).

    The rules are applied by decreasing confidence:
    0. One ranking only, and categories in the title of the organization: the
       ranking gets these categories.
    1. Every ranking name holds categories: each ranking gets its own.
    2. All the rankings but one hold categories: the last one gets the
       categories of the title not taken by the others.
    3. N categories in the title, none in the N ranking names: one category
       per ranking, in their order of appearance.
    4. N categories in the title, none in the M ranking names (M < N, N a
       multiple of M): N/M categories per ranking, in order (e.g. A1-A2 then
       A3-A4 for two rankings).

    Args:
        organization_data: Parsed result page (see
            parse_results_from_organization_page), with 'title' and 'rankings'.

    Returns:
        Categories ({1: bool, ..., 4: bool}) by ranking ID. Rankings for which
        no rule applies are missing, or have no category.
    """
    org_name = organization_data["title"]
    org_categories = find_access_categories_from_name(org_name)
    nb_org_categories = sum([int(v) for v in org_categories.values()])
    rankings = organization_data["rankings"]
    nb_rankings = len(rankings)
    nb_rankings_categorized = 0
    ranking_categories = {}
    empty_cat = {k: False for k in range(1, 5)}

    # Finding categories by level of confidence from best to worst

    # 0) "Absolute" confidence: 1+ category(ies) found in the title and only one ranking in the organization
    if nb_org_categories > 0 and len(rankings) == 1:
        ranking_id = list(rankings.keys())[0]
        ranking_categories[ranking_id] = org_categories.copy()
        return ranking_categories

    # 1) All categories are written in the ranking names (whatever the organization name)
    found = {}
    for ranking_id in rankings.keys():
        found[ranking_id] = False
        ranking_name = rankings[ranking_id]["name"]
        categories = find_access_categories_from_name(ranking_name)
        if sum([int(v) for v in categories.values()]) > 0:
            ranking_categories[ranking_id] = categories
            found[ranking_id] = True
            nb_rankings_categorized += 1
    if all(found.values()):
        return ranking_categories

    # 2) Only one ranking lacks of categorization, and it can be deduced from the organization name
    if nb_rankings - nb_rankings_categorized == 1:
        uncategorized_ranking_id = [rk_id for rk_id, rk_value in found.items() if not rk_value][0]
        found_categories = []
        for ranking_id in ranking_categories.keys():
            for cat in ranking_categories[ranking_id]:
                cat_found = ranking_categories[ranking_id][cat]
                if cat_found and cat not in found_categories:
                    found_categories.append(cat)
        ranking_categories[uncategorized_ranking_id] = {
            cat: ((cat not in found_categories) and org_categories[cat]) for cat in range(1, 5)
        }
        return ranking_categories

    # 3) N categories found in the organization name but none in its N ranking names,
    # so each ranking category is guessed (order of their appearance matters)
    if (nb_org_categories > 1) and (nb_rankings == nb_org_categories):
        cat = 0
        for ranking_id in rankings.keys():
            ranking_categories[ranking_id] = empty_cat.copy()
            cat += 1
            while cat <= 4:
                if org_categories[cat]:
                    ranking_categories[ranking_id][cat] = True
                    break
                cat += 1
        return ranking_categories

    # 4) N categories found in the organization name but none in its M ranking names,
    # so Q = N/M categories are guessed for each ranking (order of their appearance matters)
    # Only case where it can happen:
    # A1, A2, A3 and A4 are found in the organization name and there are 2 rankings,
    # so the first ranking has the categories A1 and A2, the second ranking has the categories A3 and A4.
    if (
        nb_org_categories > 1
        and nb_rankings < nb_org_categories
        and nb_org_categories % nb_rankings == 0
    ):
        cat = 0
        nb_categories_per_ranking = nb_org_categories // nb_rankings
        while cat <= 4:
            for ranking_id in rankings.keys():
                ranking_categories[ranking_id] = empty_cat.copy()
                nb_inserted_categories = 0
                while nb_inserted_categories < nb_categories_per_ranking:
                    cat += 1
                    if org_categories[cat]:
                        ranking_categories[ranking_id][cat] = True
                        nb_inserted_categories += 1
            cat += 1  # ensuring getting out of the loop in case of no rankings at all
        return ranking_categories

    return ranking_categories


def convert_categories_from_dict_to_list(categories: dict[int, bool]) -> list[str]:
    """Categories found, as a list of labels (e.g. ["A1", "A2"])."""
    return [f"A{i}" for i, v in categories.items() if v]


def to_optional_int(value: Any) -> int | None:
    """Convert a pandas scalar to int, mapping missing values (None, NaN, pd.NA) to None."""
    return None if pd.isna(value) else int(value)


def remove_conflicting_observations(observations: pd.DataFrame) -> pd.DataFrame:
    """Remove the observations of a rider on a day when their categories cannot all be true.

    A rider ranked in two races of disjoint categories on the same day (e.g.
    A1-A2 and A3-A4), or read on a startlist in a category of none of the
    races he is ranked in that day, holds an error of the source. All the
    observations of that rider and day are removed: his category on that day
    is then filled from his other races. The conflicts are logged.

    Args:
        observations: Observations (rider_id, race_date, categories, race_hc,
            race_lc), race_hc and race_lc being the highest and lowest category
            of each observation (e.g. 1 and 2 for "A1,A2").

    Returns:
        The observations without the conflicting ones.
    """
    by_rider_and_day = observations.groupby(["rider_id", "race_date"])
    # The ranges [race_hc, race_lc] have a common category if the highest
    # lowest category is not above the lowest highest one
    is_conflict = by_rider_and_day["race_hc"].transform("max") > by_rider_and_day["race_lc"].transform("min")
    if is_conflict.any():
        conflicts = observations[is_conflict]
        lines = [
            f"observations removed for {conflicts.groupby(['rider_id', 'race_date']).ngroups} "
            f"rider(s) and day(s) with conflicting categories (rider_id, date: categories):"
        ]
        for (rider_id, race_date), categories in conflicts.groupby(["rider_id", "race_date"])["categories"]:
            lines.append(
                f"  {rider_id}, {pd.Timestamp(race_date).strftime('%Y-%m-%d')}: {' / '.join(categories)}"
            )
        logger.info("\n".join(lines))
    return observations[~is_conflict]


def search_rider_category(
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        categories_from_startlists: pd.DataFrame,
        after: str | None = None
    ) -> pd.DataFrame:
    """Infer the Access category of each rider at each race date.

    Observations are the results (the race categories, e.g. "A1,A2", and the
    finish rank) and the startlists (a single category), from `after` on.
    Observations of a rider on a day with conflicting categories are removed
    first (see remove_conflicting_observations). The races of a rider bound his category: his possible range [hc, lc] (highest
    and lowest category, A1 being the highest) is narrowed race after race, and
    moved when he enters races of other categories (category change). A win in
    a race whose highest category is above his range moves him up at the next
    race. The category is known when the range holds one category only.

    Unknown categories are then filled:
    1. backward propagation of the known categories, within each range;
    2. riders with no known category at all get A1 when limited to A1-A2, A3
       when limited to A3-A4, A1 otherwise; other unknown categories get A1;
    3. forward then backward propagation.

    Args:
        races: Race table (race_id, categories, race_date).
        rankings: Ranking table (race_id, rider_id, finish_rank).
        categories_from_startlists: Categories read on the startlists
            (rider_id, race_date, category).
        after: First date taken into account ('YYYY-MM-DD'; default January 1st
            of FIRST_SEASON).

    Returns:
        One row per observation: rider_id, race_date, rider_category (1 to 4).
    """
    def forward_search(df_rider: pd.DataFrame) -> pd.DataFrame:
        """Narrow the category range of one rider, race after race (rows sorted by date).

        Fills the columns rider_hc, rider_lc and event, and rider_category when the
        range holds one category only.
        """
        rider_hc_prev, rider_lc_prev = 100, -100
        first_index = df_rider.index[0]
        rider_hc_next, rider_lc_next = None, None
        # Values are collected in lists and written once at the end
        # (row-by-row .loc assignments were slow)
        rider_hc_values, rider_lc_values, events = [], [], []
        rider_categories = df_rider["rider_category"].to_list()
        for k, row in enumerate(df_rider.itertuples()):
            i = row.Index
            event = ""
            if not isinstance(row.race_hc, int) or not isinstance(row.race_lc, int):
                raise TypeError("Invalid types for categories")
            race_hc, race_lc = row.race_hc, row.race_lc
            if (not isinstance(row.race_hc, int)) and (row.finish_rank is not None):
                raise TypeError("Invalid types for finish rank")
            finish_rank = row.finish_rank

            # Default case: keep category range
            rider_hc = rider_hc_prev
            rider_lc = rider_lc_prev
            if (rider_hc_next is not None) and (rider_lc_next is not None):
                rider_hc, rider_lc = rider_hc_next, rider_lc_next
                rider_hc_prev, rider_lc_prev = rider_hc_next, rider_lc_next
                rider_hc_next, rider_lc_next = None, None

            # Change of category
            # ---- category upgrade
            if race_lc < rider_hc_prev:
                rider_hc, rider_lc = race_hc, race_lc
            elif race_hc < rider_hc and finish_rank == 1:
                rider_hc_next, rider_lc_next = race_hc, race_hc
            # ---- category downgrade
            elif race_hc > rider_lc_prev:
                rider_hc, rider_lc = race_hc, race_lc

            # Reduce category range
            if race_hc > rider_hc_prev:
                rider_hc = race_hc
                event += "↓HC, "
            if race_lc < rider_lc_prev:
                rider_lc = race_lc
                event += "↑LC, "

            if rider_lc < rider_hc_prev:
                event += "↑cat, "
            if rider_hc > rider_lc_prev:
                event += "↓cat, "

            rider_hc_values.append(rider_hc)
            rider_lc_values.append(rider_lc)
            if i == first_index:
                event = ""
            events.append(event.strip(", "))
            if rider_hc == rider_lc:
                rider_categories[k] = rider_hc

            rider_hc_prev, rider_lc_prev = rider_hc, rider_lc

        df_rider["rider_hc"] = rider_hc_values
        df_rider["rider_lc"] = rider_lc_values
        df_rider["event"] = events
        df_rider["rider_category"] = pd.Series(rider_categories, index=df_rider.index, dtype=object)
        return df_rider

    def propagation(
            mode: Literal["forward", "backward"],
            df_rider: pd.DataFrame,
            step: int
        ) -> pd.DataFrame:
        """Fill the unknown categories of one rider from the last known one.

        The known category is moved forward or backward (`mode`) and clipped to the
        range [rider_hc, rider_lc] of each row; `step` is written in the event column.
        """
        last_known_category = None
        direction = 1 if mode == "forward" else -1

        for row in df_rider.iloc[::direction].itertuples():
            i = row.Index
            category = to_optional_int(row.rider_category)
            if category is not None:
                if isinstance(category, int):
                    last_known_category = category
                else:
                    raise TypeError("rider_category must be an integer")
                continue
            if last_known_category is None:
                continue
            if not isinstance(row.rider_hc, int) or not isinstance(row.rider_lc, int):
                raise TypeError("rider_hc and rider_lc must be integers")
            rider_hc, rider_lc = row.rider_hc, row.rider_lc
            if rider_hc <= last_known_category <= rider_lc:
                filled_category = last_known_category
            elif last_known_category < rider_hc:
                filled_category = rider_hc
            elif last_known_category > rider_lc:
                filled_category = rider_lc
            else:
                continue
            df_rider.at[i, "rider_category"] = filled_category
            df_rider.at[i, "event"] = f"{row.event}, FWP({step})".strip(", ")
            last_known_category = filled_category
        return df_rider

    def backward_propagation(df_rider: pd.DataFrame, step: int) -> pd.DataFrame:
        """Propagate the known categories backward (see propagation)."""
        return propagation(mode="backward", df_rider=df_rider, step=step)

    def forward_propagation(df_rider: pd.DataFrame, step: int) -> pd.DataFrame:
        """Propagate the known categories forward (see propagation)."""
        return propagation(mode="forward", df_rider=df_rider, step=step)


    categories_from_startlists = categories_from_startlists.rename(columns={"category": "categories"})
    categories_from_startlists["finish_rank"] = None
    categories_from_startlists["race_date"] = pd.to_datetime(categories_from_startlists["race_date"], format="%Y-%m-%d")

    categories_from_results = rankings.merge(races, on="race_id")[["rider_id", "categories", "race_date", "finish_rank"]]
    categories_from_results["race_date"] = pd.to_datetime(categories_from_results["race_date"], format="%Y-%m-%d")

    df = pd.concat([categories_from_startlists, categories_from_results], ignore_index=True)
    if after is None:
        after = pd.Timestamp(year=FIRST_SEASON, month=1, day=1)
    else:
        try:
            after = pd.to_datetime(after, format="%Y-%m-%d")
        except ValueError as e:
            raise e
    df = df[df["race_date"] >= pd.Timestamp(after)]
    df = df.sort_values(by=["rider_id", "race_date", "finish_rank"], na_position="first").reset_index(drop=True)

    df["race_hc"] = df["categories"].str.replace("A", "").str.split(",").str[0].astype(int)
    df["race_lc"] = df["categories"].str.replace("A", "").str.split(",").str[-1].astype(int)
    df = remove_conflicting_observations(df)
    df["rider_hc"] = 100
    df["rider_lc"] = -100
    df["rider_category"] = None
    df["event"] = ""

    # One pass per rider over its own rows (groupby avoids a full-table mask per rider)
    processed_riders = []
    for _, df_rider in df.groupby("rider_id", sort=True):
        df_rider = df_rider.copy()

        df_rider = forward_search(df_rider)
        df_rider = backward_propagation(df_rider, step=1)

        # For the remaining undefined categories:
        # If all rows have an undefined category, then
        # - riders limited to A1-A2 are assigned to A1,
        # - riders limited to A3-A4 are assigned to A3,
        # - and the remaining riders are assigned to A1.
        # If only a part of the rows has an undefined category, then A1 is assigned.
        missing_categories = df_rider["rider_category"].isna()
        if missing_categories.all():
            mask_a1a2 = df_rider["rider_lc"] <= 2
            mask_a3a4 = df_rider["rider_hc"] >= 3
            mask_remaining = ~mask_a1a2 & ~mask_a3a4
            df_rider.loc[mask_a1a2, "rider_category"] = 1
            df_rider.loc[mask_a1a2, "event"] += ", ForceA1(A1-A2):all missing"
            df_rider.loc[mask_a3a4, "rider_category"] = 3
            df_rider.loc[mask_a3a4, "event"] += ", ForceA3(A3-A4):all missing"
            df_rider.loc[mask_remaining, "rider_category"] = 1
            df_rider.loc[mask_remaining, "event"] += ", ForceA1(others):all missing"
            df_rider.loc[:, "event"] = df_rider.loc[:, "event"].str.strip(", ")
        else:
            df_rider.loc[missing_categories, "rider_category"] = 1
            df_rider.loc[missing_categories, "event"] += ", ForceA1:some missing"

        df_rider = forward_propagation(df_rider, step=1)
        df_rider = backward_propagation(df_rider, step=2)

        processed_riders.append(df_rider)

    if processed_riders:
        processed = pd.concat(processed_riders)
        updated_columns = ["rider_hc", "rider_lc", "rider_category", "event"]
        df.loc[processed.index, updated_columns] = processed[updated_columns]
    return df.loc[:, ["rider_id", "race_date", "rider_category"]].reset_index(drop=True)


def compute_category_history(category_at_given_times: pd.DataFrame) -> pd.DataFrame:
    """Compute rider category history, that is the aggregated data,
    taking as input a DataFrame with columns rider_id, race_date, rider_category,
    and returning a DataFrame with columns rider_id, start_date, rider_category."""

    df = category_at_given_times.copy()
    df["race_date"] = pd.to_datetime(df["race_date"])
    df = df.sort_values(["rider_id", "race_date"])
    category_history_tmp: list[dict] = []
    for rider_id, df_rider in df.groupby("rider_id", sort=False):
        # initializations
        first_index = df_rider.index[0]
        start_date_prev = df_rider.loc[first_index, "race_date"]
        category_prev = to_optional_int(df_rider.loc[first_index, "rider_category"])
        last_index = df_rider.index[-1]
        for row in df_rider.itertuples():
            race_date = row.race_date
            category = row.rider_category
            if category != category_prev:
                # Separation of the two tests is intended, since adding two lines can be needed.
                category_history_tmp.append(
                    {
                        "rider_id": rider_id,
                        "start_date": start_date_prev,
                        "rider_category": category_prev,
                    }
                )
                start_date_prev = race_date# + pd.Timedelta(days=1)
            if row.Index == last_index:
                category_history_tmp.append(
                    {
                        "rider_id": rider_id,
                        "start_date": start_date_prev,
                        "rider_category": category,
                    }
                )
            category_prev = category

    return (
        pd.DataFrame(category_history_tmp)
        .sort_values(by=["rider_id", "start_date"])
        .reset_index(drop=True)
    )


def advance_start_dates_in_category_history(
        category_history: pd.DataFrame,
        category_at_given_times: pd.DataFrame
    ) -> pd.DataFrame:
    """Move to January 1st the periods starting at the first race of a rider in a year.

    A category is valid for the whole season: a period observed first in April
    starts on January 1st when April is the first race of the rider that year.
    A period starting later in the year (category change during the season,
    after races in the former category) keeps its start date, so that the
    former category still covers the beginning of the year. So does a second
    period starting on the same day as the first one of the year (left to
    delete_rows_for_riders_having_duplicated_keys, as before).

    Args:
        category_history: Category history (rider_id, start_date, rider_category).
        category_at_given_times: Observations the history was computed from
            (rider_id, race_date, rider_category).

    Returns:
        The category history, with the start dates moved.
    """
    df = category_history.copy()
    df["start_date"] = pd.to_datetime(df["start_date"])
    df = df.sort_values(["rider_id", "start_date"])
    race_dates = pd.to_datetime(category_at_given_times["race_date"])
    first_race_dates = race_dates.groupby(
        [category_at_given_times["rider_id"], race_dates.dt.year]
    ).min()
    years = df["start_date"].dt.year
    # Rows being sorted by date within each rider, only the first row of each
    # (rider, year) pair may move (a second period starting the same day keeps it)
    first_row_of_year = ~pd.DataFrame({"rider_id": df["rider_id"], "year": years}).duplicated()
    first_race_of_year = pd.Series(
        list(zip(df["rider_id"], years)), index=df.index
    ).map(first_race_dates)
    moved = first_row_of_year & (df["start_date"] == first_race_of_year)
    df.loc[moved, "start_date"] = pd.to_datetime(
        years[moved].astype(str) + "-01-01", format="%Y-%m-%d"
    )
    return df


def add_unknown_years_in_category_history(
        category_history: pd.DataFrame,
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        categories_from_startlists: pd.DataFrame,
        after_year: int = FIRST_SEASON,
        current_year: int | None = None
    ) -> pd.DataFrame:
    """Add the periods of unknown category, for the years without observation.

    - A rider first observed after `after_year` gets an unknown category from
      January 1st of `after_year`.
    - A year without any race of the rider starts an unknown category period
      on January 1st (once, until his next race).
    - A rider racing again after such a year gets back his last known category
      on January 1st of the year of his return, if no period starts that year,
      or if he raced that year before the first period (category change during
      the season).

    The current year is not complete: a rider without race yet this year keeps
    his last period, and gets an unknown category from January 1st of this
    year only once the year is over. The history of the riders is thus not
    changed at the start of each year.

    Args:
        category_history: Category history (rider_id, start_date, rider_category).
        races: Race table, for the race dates.
        rankings: Ranking table, for the races of each rider.
        categories_from_startlists: Categories read on the startlists, for
            the startlist dates of each rider.
        after_year: First year of the history.
        current_year: Current year (default: the year of the current date).

    Returns:
        The completed history, rider_category as a nullable integer (Int8).

    Raises:
        ValueError: If `after_year` is before FIRST_SEASON or after the current year.
    """
    this_year = current_year if current_year is not None else datetime.now().year
    if after_year < FIRST_SEASON or after_year > this_year:
        raise ValueError(
            f"'after_year' must be greater than or equal to {FIRST_SEASON}"
            f" and less than or equal to {this_year}"
        )

    df = (
        category_history.copy()
        .sort_values(by=["rider_id", "start_date"])
        .reset_index(drop=True)
    )
    df["year"] = pd.to_datetime(df["start_date"], format="%Y-%m-%d").dt.year

    categories_from_startlists = categories_from_startlists[["rider_id", "race_date"]]
    categories_from_results = rankings.merge(races, on="race_id")[["rider_id", "race_date"]]
    known_dates = (
        pd.concat([categories_from_startlists, categories_from_results], ignore_index=True)
        .sort_values(by=["rider_id", "race_date"])
        .drop_duplicates()
        .reset_index(drop=True)
    )
    known_dates["year"] = pd.to_datetime(known_dates["race_date"], format="%Y-%m-%d").dt.year

    category_history_tmp: list[dict] = []

    # First known race date of each rider and year
    first_known_date_by_rider_and_year = (
        known_dates
        .assign(race_date=pd.to_datetime(known_dates["race_date"], format="%Y-%m-%d"))
        .groupby(["rider_id", "year"])["race_date"].min()
        .to_dict()
    )

    # Years with known race dates, per rider (computed once instead of once per rider)
    years_in_known_dates_by_rider = {
        rider_id: set(years.dropna())
        for rider_id, years in known_dates.groupby("rider_id")["year"]
    }

    for rider_id, df_rider in df.groupby("rider_id", sort=False):
        first_index = df_rider.index[0]
        first_year = df_rider.loc[first_index, "start_date"].year
        last_known_category = df_rider.loc[first_index, "rider_category"]
        if first_year > after_year:
            category_history_tmp.append(
                {
                    "rider_id": rider_id,
                    "start_date": pd.to_datetime(arg=f"{after_year}-01-01", format="%Y-%m-%d"),
                    "rider_category": None,
                }
            )
        years_in_known_dates = years_in_known_dates_by_rider.get(rider_id, set())
        years_in_category_history = set(df_rider["year"])
        years = list[int](range(first_year, this_year + 1))
        missing_category_line_already_added = False
        for year in years:
            categories_this_year = (
                df_rider[df_rider["year"] == year]
                .sort_values(by="start_date", ascending=False, ignore_index=True)
                ["rider_category"]
            )
            if len(categories_this_year) > 0:
                last_known_category_this_year = categories_this_year.iloc[0]
            else:
                last_known_category_this_year = None
            category_before_this_year = last_known_category
            if last_known_category_this_year is not None:
                last_known_category = last_known_category_this_year
            if year in years_in_category_history:
                first_start_date = df_rider.loc[df_rider["year"] == year, "start_date"].min()
                first_known_date = first_known_date_by_rider_and_year.get((rider_id, year))
                if (
                    missing_category_line_already_added
                    and first_known_date is not None
                    and first_known_date < first_start_date
                ):
                    # Return after a year without race, with races in the former
                    # category before a category change during the season
                    category_history_tmp.append(
                        {
                            "rider_id": rider_id,
                            "start_date": pd.to_datetime(arg=f"{year}-01-01", format="%Y-%m-%d"),
                            "rider_category": category_before_this_year,
                        }
                    )
                category_history_tmp.extend(
                    df_rider[df_rider["year"] == year]
                    .loc[:, ["rider_id", "start_date", "rider_category"]]
                    .to_dict(orient="records")
                )
                missing_category_line_already_added = False
            else:
                if year in years_in_known_dates:
                    if missing_category_line_already_added:
                        category_history_tmp.append(
                            {
                                "rider_id": rider_id,
                                "start_date": pd.to_datetime(arg=f"{year}-01-01", format="%Y-%m-%d"),
                                "rider_category": last_known_category,
                            }
                        )
                        missing_category_line_already_added = False
                elif year < this_year:  # the current year is not over
                    if not missing_category_line_already_added:
                        category_history_tmp.append(
                            {
                                "rider_id": rider_id,
                                "start_date": pd.to_datetime(arg=f"{year}-01-01", format="%Y-%m-%d"),
                                "rider_category": None,
                            }
                        )
                        missing_category_line_already_added = True

    category_history = (
        pd.DataFrame(category_history_tmp)
        .sort_values(by=["rider_id", "start_date"])
        .reset_index(drop=True)
    )
    category_history["rider_category"] = category_history["rider_category"].astype("Int8")
    return category_history


def delete_rows_for_riders_having_duplicated_keys(
        category_history: pd.DataFrame,
        add_unknown_category_row: bool = True,
        after_year: int = FIRST_SEASON
    ) -> pd.DataFrame:
    """Replace the category history of riders having duplicated keys by an unknown category.

    Duplicated keys (two periods starting on the same day) come from two
    classifications on the same day with different categories, which only
    happens to women riders (a mixed race and a women's ranking of the same
    organization). The riders concerned and their duplicated dates are logged,
    so that any unexpected case is noticed.
    """
    df = category_history.copy()
    duplicated_keys = df.duplicated(["rider_id", "start_date"], keep=False)
    riders_removed = df.loc[duplicated_keys, "rider_id"].drop_duplicates().to_list()
    if riders_removed:
        lines = [
            f"category history replaced by an unknown category for {len(riders_removed)} "
            f"rider(s) with duplicated keys (rider_id: duplicated start dates):"
        ]
        dates_by_rider = df[duplicated_keys].groupby("rider_id")["start_date"]
        for rider_id, dates in dates_by_rider:
            dates = sorted(pd.to_datetime(dates).dt.strftime("%Y-%m-%d").unique())
            lines.append(f"  {rider_id}: {', '.join(dates)}")
        logger.info("\n".join(lines))
    df = df[~df["rider_id"].isin(riders_removed)]
    if not add_unknown_category_row:
        return df
    modifs = []
    start_date = pd.to_datetime(arg=f"{after_year}-01-01", format="%Y-%m-%d")
    for rider_id in riders_removed:
        modifs.append(
            {
                "rider_id": rider_id,
                "start_date": start_date,
                "rider_category": None,
            }
        )
    df = (
        pd.concat(objs=[df, pd.DataFrame(modifs)], ignore_index=True)
        .sort_values(by=["rider_id", "start_date"])
    )
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df is not a pandas DataFrame")
    return df


def create_category_table(
    races: pd.DataFrame,
    rankings: pd.DataFrame,
    categories_from_startlists: pd.DataFrame
    ) -> pd.DataFrame:
    """Create the category history of the riders (table rider_categories).

    Steps: search_rider_category, compute_category_history,
    advance_start_dates_in_category_history, add_unknown_years_in_category_history,
    then delete_rows_for_riders_having_duplicated_keys.

    Args:
        races: Race table.
        rankings: Ranking table.
        categories_from_startlists: Categories read on the startlists.

    Returns:
        One row per rider and period: rider_id, start_date, rider_category (a
        period ends the day before the next start_date of the rider).
    """
    category_at_given_times = search_rider_category(
        races=races,
        rankings=rankings,
        categories_from_startlists=categories_from_startlists,
    )
    category_history = compute_category_history(category_at_given_times)
    category_history = advance_start_dates_in_category_history(
        category_history=category_history,
        category_at_given_times=category_at_given_times
    )
    category_history = add_unknown_years_in_category_history(
        category_history=category_history,
        races=races,
        rankings=rankings,
        categories_from_startlists=categories_from_startlists
    )
    category_history = delete_rows_for_riders_having_duplicated_keys(category_history)
    return category_history
