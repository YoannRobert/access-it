"""Forecasts of the races, for the choice of a date and a race.

The forecasts and the entries of the runs of the forecast of the upcoming
races are given as two tables, each with a run_time column (UTC timestamp of
the run). Rules:

- each race is shown with a single run: the most recent run that forecasts
  it; a race forecast by no run is a race without forecast, shown with the
  most recent run of its entries, without probabilities, ranks nor features;
- the dates offered are the race dates with at least one forecast race; the
  default date is the first of them from today on, or else the last one;
- the races of a day are sorted by page title, then by rank of their table in
  the page (the number at the end of the race_id);
- the riders entered in a forecast race are sorted by rank of win; those of a
  race without forecast by last name, first name and rider_id; their name,
  club and category come from the rider list.

The column names of the forecasts are written out, so that the module imports
neither the features nor the model layer. The computation is free of any
Streamlit dependency.
"""

from collections.abc import Sequence

import pandas as pd

from access_it.analytics.ranking_tools import to_datetime, to_day

FORECAST_VALUE_COLUMNS = [
    "p_win", "p_podium", "p_top5", "p_top10", "rank_win", "nb_races_used", "top_n_rate",
    "best_place",
]
RACE_RUN_COLUMNS = [
    "race_id", "race_date", "page_title", "startlist_heading", "run_time", "has_forecast",
    "rider_id", *FORECAST_VALUE_COLUMNS,
]
DAY_RACE_COLUMNS = ["race_id", "page_title", "startlist_heading", "has_forecast", "run_time"]
RACE_ENTRY_COLUMNS = [
    "rank_win", "last_name", "first_name", "club", "category", "p_win", "p_podium", "p_top5",
    "p_top10", "nb_races_used", "top_n_rate", "best_place", "rider_id",
]


def select_race_runs(forecasts: pd.DataFrame, entries: pd.DataFrame) -> pd.DataFrame:
    """Rows of the run shown for each race (see the module docstring for the rules).

    Args:
        forecasts: Forecasts of all the runs, with their run_time.
        entries: Entries of all the runs, with their run_time.

    Returns:
        One row per race and rider entered: the RACE_RUN_COLUMNS, with
        race_date converted by to_datetime and has_forecast False (and the
        FORECAST_VALUE_COLUMNS missing) for a race without forecast; sorted by
        race date, race_id, rank of win and rider_id; empty if both tables are.
    """
    forecasts = forecasts[
        forecasts["run_time"] == forecasts.groupby("race_id")["run_time"].transform("max")
    ]
    entries = entries[~entries["race_id"].isin(forecasts["race_id"])]
    entries = entries[
        entries["run_time"] == entries.groupby("race_id")["run_time"].transform("max")
    ]
    frames = [
        frame for frame in (
            forecasts.assign(has_forecast=True)[RACE_RUN_COLUMNS],
            entries.assign(has_forecast=False).reindex(columns=RACE_RUN_COLUMNS),
        )
        if not frame.empty
    ]
    if not frames:
        return pd.DataFrame(columns=RACE_RUN_COLUMNS)
    race_runs = pd.concat(frames, ignore_index=True)
    race_runs["race_date"] = to_datetime(race_runs["race_date"])
    return race_runs.sort_values(
        ["race_date", "race_id", "rank_win", "rider_id"]
    ).reset_index(drop=True)


def list_forecast_dates(race_runs: pd.DataFrame) -> list[pd.Timestamp]:
    """Race dates with at least one forecast race.

    Args:
        race_runs: Rows of the run shown for each race, as returned by
            select_race_runs.

    Returns:
        The distinct dates, from the oldest to the most recent.
    """
    dates = race_runs.loc[race_runs["has_forecast"].astype(bool), "race_date"]
    return [pd.Timestamp(date) for date in sorted(dates.unique())]


def get_default_forecast_date(
        dates: Sequence[pd.Timestamp],
        today: str | pd.Timestamp
    ) -> pd.Timestamp | None:
    """Date offered by default: the first date from today on, or else the last one.

    Args:
        dates: Race dates with at least one forecast race, sorted from the
            oldest to the most recent, as returned by list_forecast_dates.
        today: Current day, as a string or a timestamp.

    Returns:
        The default date, or None if there is no date.

    Raises:
        ValueError: If today is missing.
    """
    day = to_day(today, "today")
    if not dates:
        return None
    return next((date for date in dates if date >= day), dates[-1])


def list_day_races(race_runs: pd.DataFrame, race_date: str | pd.Timestamp) -> pd.DataFrame:
    """Races of a day, for the choice of a race.

    Args:
        race_runs: Rows of the run shown for each race, as returned by
            select_race_runs.
        race_date: Day of the races, as a string or a timestamp.

    Returns:
        One row per race of the day: the DAY_RACE_COLUMNS, sorted by page title,
        then by rank of the table in the page; empty if no race is held that day.

    Raises:
        ValueError: If the race date is missing.
    """
    day = to_day(race_date, "race date")
    races = race_runs.loc[race_runs["race_date"] == day, DAY_RACE_COLUMNS]
    races = races.drop_duplicates("race_id")
    table_rank = races["race_id"].str.rsplit("-", n=1).str[-1].astype(int)
    return (
        races.assign(table_rank=table_rank)
        .sort_values(["page_title", "table_rank"])
        .drop(columns="table_rank")
        .reset_index(drop=True)
    )


def get_race_entries(
        race_runs: pd.DataFrame,
        race_id: str,
        rider_list: pd.DataFrame
    ) -> pd.DataFrame:
    """Riders entered in a race, with their forecast if any, their name, club and category.

    Args:
        race_runs: Rows of the run shown for each race, as returned by
            select_race_runs.
        race_id: Race to show.
        rider_list: List of the riders, as returned by build_rider_list.

    Returns:
        One row per rider entered: the RACE_ENTRY_COLUMNS, with the name, club
        and category missing for a rider absent from the rider list; sorted by
        rank of win for a forecast race, by last name, first name and rider_id
        for a race without forecast.

    Raises:
        ValueError: If the race is not in race_runs.
    """
    race = race_runs[race_runs["race_id"] == race_id]
    if race.empty:
        raise ValueError(f"Unknown race: {race_id!r}")
    names = rider_list[["rider_id", "last_name", "first_name", "club", "category"]]
    race_entries = race.merge(names, on="rider_id", how="left")
    order = (
        ["rank_win"] if race["has_forecast"].iloc[0]
        else ["last_name", "first_name", "rider_id"]
    )
    return race_entries.sort_values(order)[RACE_ENTRY_COLUMNS].reset_index(drop=True)
