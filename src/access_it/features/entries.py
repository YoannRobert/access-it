"""Races forecast and their start lists, shared by the forecast methods.

Each forecast method (baseline, ratings...) forecasts the same races with the
same start lists, so that their evaluations can be compared. Rules:

- the races forecast are those of the seasons FIRST_SEASON to last_season
  held from first_race_date on, with at least one ranked rider;
- the start list of a race is made of its ranked riders (riders who did not
  finish are absent, an accepted limit);
- the arguments are checked first, then the race dates of these seasons, then
  the presence of a race to forecast.

The computation is free of any Streamlit dependency.
"""

import pandas as pd

from access_it.analytics.ranking_tools import check_race_dates, to_datetime, to_day
from access_it.common.seasons import FIRST_SEASON, check_season

COLUMNS = ["race_id", "race_date", "rider_id", "finish_rank"]


def select_forecast_entries(
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        last_season: int,
        first_race_date: str | pd.Timestamp
    ) -> pd.DataFrame:
    """Ranked riders of the races forecast from a date to the end of a season.

    See the module docstring for the rules.

    Args:
        races: Race table.
        rankings: Ranking table.
        last_season: Last season forecast, as a calendar year, not before
            FIRST_SEASON.
        first_race_date: Day of the first races forecast, as "YYYY-MM-DD" or
            a date (the time of day is ignored), in the seasons FIRST_SEASON
            to last_season.

    Returns:
        One row per race forecast and ranked rider, with the COLUMNS:
        race_id, race_date (datetime64[ns]), rider_id and finish_rank.

    Raises:
        ValueError: If last_season is before FIRST_SEASON, then if
            first_race_date is missing, then if it is not in the seasons
            FIRST_SEASON to last_season, then if a race date of these seasons
            is missing, then if no race with a ranked rider is held from
            first_race_date to the end of last_season.
    """
    check_season(last_season)
    first_day = to_day(first_race_date, "first race date")
    if not FIRST_SEASON <= first_day.year <= last_season:
        raise ValueError(
            f"First race date {first_day.date()} is not in the seasons "
            f"{FIRST_SEASON} to {last_season}"
        )
    season_races = races.loc[
        races["season"].between(FIRST_SEASON, last_season), ["race_id", "race_date"]
    ].assign(race_date=lambda df: to_datetime(df["race_date"]))
    check_race_dates(season_races["race_date"])
    entries = season_races[season_races["race_date"] >= first_day].merge(
        rankings[["race_id", "rider_id", "finish_rank"]], on="race_id"
    )
    if entries.empty:
        raise ValueError(
            f"No race to forecast from {first_day.date()} to the season {last_season}"
        )
    return entries[COLUMNS]
