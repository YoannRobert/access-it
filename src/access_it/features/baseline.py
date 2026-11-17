"""Baseline of the forecast: riders of each race ranked by their recent form.

Each past race is forecast with the results of the previous days only. Rules:

- the races forecast are those of the seasons FIRST_SEASON to last_season
  held from first_race_date on, with at least one ranked rider; the races
  before first_race_date are not forecast, but their results count in the
  recent form of the next races;
- the start list of a race is made of its ranked riders (riders who did not
  finish are absent, an accepted limit);
- the recent form of a rider is computed on the eve of the race: the results
  are selected by select_recent_results of ranking_tools with the race date
  as reference date (its races are excluded), and the tops are counted by
  summarize_top_n of ranking_tools; see their docstrings for the rules;
- the riders are ranked by share of top N, from the highest to the lowest;
  ties are broken by their best places in the same races, compared one after
  the other (absolute finish ranks, even outside the top N: 8, 12, 21 is
  ahead of 8, 12, 23), a missing place being worse than any place (the rider
  who finished more races is ahead), then by rider_id; the predicted rank is
  unique;
- an error is raised if there is no race to forecast;
- a race whose riders have no recent form is kept: its riders are then
  ranked by rider_id only.

The computation is free of any Streamlit dependency.
"""

import pandas as pd

from access_it.analytics.ranking_tools import (
    check_race_dates, check_recent_form_arguments, select_recent_results, summarize_top_n,
    to_datetime, to_day
)
from access_it.common.seasons import FIRST_SEASON, check_season

COLUMNS = [
    "race_id", "race_date", "rider_id", "finish_rank",
    "nb_races_used", "nb_top_n", "top_n_rate", "predicted_rank"
]


def rank_by_recent_form(
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        last_season: int,
        first_race_date: str | pd.Timestamp,
        top_n: int = 20,
        last_races: int = 10,
        window_months: int = 6
    ) -> pd.DataFrame:
    """Riders of each race ranked by their recent form on the eve of the race.

    See the module docstring for the rules.

    Args:
        races: Race table.
        rankings: Ranking table.
        last_season: Last season forecast, as a calendar year, not before
            FIRST_SEASON.
        first_race_date: Day of the first races forecast, as "YYYY-MM-DD" or
            a date (the time of day is ignored), in the seasons FIRST_SEASON
            to last_season.
        top_n: Last finish rank counting as a top N, from 1 to MAX_TOP_N.
        last_races: Maximum number of races used per rider, at least 1.
        window_months: Length of the window before each race, at least 1.

    Returns:
        One row per race forecast and ranked rider: race_id, race_date
        (datetime64[ns]), rider_id, finish_rank (the actual one),
        nb_races_used, nb_top_n, top_n_rate and predicted_rank (1 to the
        number of ranked riders of the race); sorted by race date, race_id
        and predicted rank, with the index reset.

    Raises:
        ValueError: If top_n is not between 1 and MAX_TOP_N, then if
            last_races is lower than 1, then if window_months is lower than 1,
            then if last_season is before FIRST_SEASON, then if
            first_race_date is missing, then if it is not in the seasons
            FIRST_SEASON to last_season, then if a race date of these seasons
            is missing, then if no race with a ranked rider is held from
            first_race_date to the end of last_season.
    """
    check_recent_form_arguments(top_n, last_races, window_months)
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
    place_columns = [f"place_{i}" for i in range(1, last_races + 1)]
    forecasts = []
    for race_date, day_entries in entries.groupby("race_date"):
        rider_ids = day_entries["rider_id"].unique()
        recent = select_recent_results(
            races, rankings, rider_ids, race_date, last_races, window_months
        )
        form = summarize_top_n(recent, rider_ids, top_n)
        # Places of each rider from the best one to the worst one, a missing place being the worst
        places = (
            recent.sort_values(["rider_id", "finish_rank"])
            .assign(position=lambda df: df.groupby("rider_id").cumcount())
            .pivot(index="rider_id", columns="position", values="finish_rank")
            .reindex(index=rider_ids, columns=range(last_races))
            .set_axis(place_columns, axis=1)
            .astype(float)
            .fillna(float("inf"))
            .rename_axis("rider_id")
            .reset_index()
        )
        ranked = (
            day_entries.merge(form, on="rider_id")
            .merge(places, on="rider_id")
            .sort_values(
                ["race_id", "top_n_rate", *place_columns, "rider_id"],
                ascending=[True, False, *[True] * last_races, True]
            )
        )
        ranked["predicted_rank"] = ranked.groupby("race_id").cumcount() + 1
        forecasts.append(ranked[COLUMNS])
    return (
        pd.concat(forecasts)
        .sort_values(["race_date", "race_id", "predicted_rank"])
        .reset_index(drop=True)
    )
