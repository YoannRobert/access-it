"""Features of the riders entered in each race, known on the eve of the race.

The features feed the models of the model layer. Rules:

- the entries are given by the caller (checked by check_entries of the
  entries module): the ranked riders of past races (select_forecast_entries
  of the entries module), or the riders entered in coming races; all their
  columns are kept (the finish rank of a past race is kept, but is never a
  feature);
- the recent form of a rider is computed on the eve of the race: the results
  are selected by select_recent_results of ranking_tools with the race date
  as reference date (its races are excluded), and the tops are counted by
  summarize_top_n of ranking_tools; see their docstrings for the rules;
- the places are the best place and the mean place in the same results as
  the recent form (absolute finish ranks, even outside the top N); a rider
  without recent result gets MISSING_PLACE for both, worse than any place;
- the rating is the OpenSkill rating on the eve of the race, given by
  rate_entries_on_race_eve of the ratings module with its default settings
  (see its docstring).

The computation is free of any Streamlit dependency.
"""

import pandas as pd

from access_it.analytics.ranking_tools import (
    check_recent_form_arguments, select_recent_results, summarize_top_n
)
from access_it.features.ratings import rate_entries_on_race_eve

FEATURES = ["nb_races_used", "nb_top_n", "top_n_rate", "mu", "sigma", "best_place", "mean_place"]
MISSING_PLACE = 100


def build_race_eve_features(
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        entries: pd.DataFrame,
        top_n: int = 20,
        last_races: int = 10,
        window_months: int = 12
    ) -> pd.DataFrame:
    """Recent form, rating and places of the riders entered in each race, on the eve of the race.

    See the module docstring for the rules.

    Args:
        races: Race table.
        rankings: Ranking table.
        entries: One row per race and rider entered, with race_id, race_date
            and rider_id; any other column is kept.
        top_n: Last finish rank counting as a top N, from 1 to MAX_TOP_N.
        last_races: Maximum number of races used per rider, at least 1.
        window_months: Length of the window before each race, at least 1.

    Returns:
        The columns of the entries (race_date as datetime64[ns]), then the
        FEATURES: nb_races_used and nb_top_n (integers), top_n_rate, mu,
        sigma, best_place and mean_place (floats); sorted by race date,
        race_id and rider_id, with the index reset.

    Raises:
        ValueError: If top_n is not between 1 and MAX_TOP_N, then if
            last_races is lower than 1, then if window_months is lower than 1,
            then if there is no entry, then if a race date of the entries is
            missing, then if a rider is entered twice in a race, then if a
            race date of the seasons FIRST_SEASON to the season of the last
            entry is missing.
    """
    check_recent_form_arguments(top_n, last_races, window_months)
    rated = rate_entries_on_race_eve(races, rankings, entries)
    features = []
    for race_date, day_entries in rated.groupby("race_date"):
        rider_ids = day_entries["rider_id"].unique()
        recent = select_recent_results(
            races, rankings, rider_ids, race_date, last_races, window_months
        )
        form = summarize_top_n(recent, rider_ids, top_n)
        places = (
            recent.groupby("rider_id")["finish_rank"]
            .agg(best_place="min", mean_place="mean")
            .reindex(rider_ids)
            .astype(float)
            .fillna(float(MISSING_PLACE))
            .rename_axis("rider_id")
            .reset_index()
        )
        features.append(day_entries.merge(form, on="rider_id").merge(places, on="rider_id"))
    return (
        pd.concat(features)
        .sort_values(["race_date", "race_id", "rider_id"])
        .reset_index(drop=True)[[*entries.columns, *FEATURES]]
    )
