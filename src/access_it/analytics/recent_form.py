"""Recent form of the riders: share of top N finishes in their last races.

Shown in the dashboard, then reused as a feature of the models (win, podium,
top 5, top 10 and top 20 probabilities). Rules:

- the results used are selected by select_recent_results of ranking_tools
  (races strictly before the reference date, window of window_months, last
  races of each rider, order of the races of the same day): see its
  docstring for the rules of the selection;
- the tops are counted by summarize_top_n of ranking_tools: the rank is the
  absolute finish rank, a top N is finish_rank <= top_n, and tied riders all
  count; foreign riders are kept, nobody moves up;
- top_n is between 1 and MAX_TOP_N (tops at most 20), last_races and
  window_months are at least 1 (checked by check_recent_form_arguments of
  ranking_tools).

Known limit: a top N is easier in a small field.

The computation is free of any Streamlit dependency.
"""

from collections.abc import Sequence

import pandas as pd

from access_it.analytics.ranking_tools import (
    check_recent_form_arguments, select_recent_results, summarize_top_n
)


def compute_recent_form(
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        rider_ids: Sequence[str],
        reference_date: str | pd.Timestamp,
        top_n: int = 20,
        last_races: int = 10,
        window_months: int = 6
    ) -> pd.DataFrame:
    """Share of top N finishes of each rider in his last races before a date.

    See the module docstring for the rules.

    Args:
        races: Race table.
        rankings: Ranking table.
        rider_ids: Riders to compute, chosen by the caller.
        reference_date: Day of the forecast, as "YYYY-MM-DD" or a date (the
            time of day is ignored); its races are excluded.
        top_n: Last finish rank counting as a top N, from 1 to MAX_TOP_N.
        last_races: Maximum number of races used per rider, at least 1.
        window_months: Length of the window before the reference date, at
            least 1.

    Returns:
        One row per rider of rider_ids, in the same order: rider_id,
        nb_races_used, nb_top_n and top_n_rate (nb_top_n / nb_races_used,
        0 for a rider without race in the window).

    Raises:
        ValueError: If top_n is not between 1 and MAX_TOP_N, then if
            last_races is lower than 1, then if window_months is lower than 1,
            then if the reference date is missing.
    """
    check_recent_form_arguments(top_n, last_races, window_months)
    recent = select_recent_results(
        races, rankings, rider_ids, reference_date, last_races, window_months
    )
    return summarize_top_n(recent, rider_ids, top_n)
