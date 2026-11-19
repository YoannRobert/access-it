"""Evaluation of a forecast: predicted ranks from a score, then metrics of selected races.

Every forecast method is evaluated the same way. Rules:

- a method gives a score to each ranked rider of a race (the higher, the
  better); the predicted rank orders the riders of each race by decreasing
  score, then by rider_id, so that it is unique (1 to the number of ranked
  riders); a missing score is an error;
- the races evaluated are those with more than TOP_N ranked riders (TOP_N of
  the metrics module; in the races with fewer, the start list is mostly the
  actual top 20), held from start_date to end_date (both included), and in the
  given months if any; the number of ranked riders of a race is its number of
  rows in the forecasts;
- the metrics of these races are those of compute_race_metrics of the
  metrics module (see its docstring); their means are given by
  summarize_metrics.

The computation is free of any Streamlit dependency.
"""

from collections.abc import Sequence

import pandas as pd

from access_it.analytics.ranking_tools import to_datetime, to_day
from access_it.model.metrics import TOP_N, compute_race_metrics


def add_predicted_rank(forecasts: pd.DataFrame, score: str) -> pd.DataFrame:
    """Forecasts with the predicted rank of each rider from a score.

    See the module docstring for the rules.

    Args:
        forecasts: One row per race and ranked rider, with race_id, race_date,
            rider_id and the score column.
        score: Name of the score column (the higher, the better).

    Returns:
        A copy of the forecasts with predicted_rank added (or replaced),
        sorted by race date, race_id and predicted rank, with the index
        reset.

    Raises:
        ValueError: If a score is missing.
    """
    if forecasts[score].isna().any():
        raise ValueError("Missing scores in the forecasts")
    ranked = forecasts.sort_values(
        ["race_id", score, "rider_id"], ascending=[True, False, True]
    ).copy()
    ranked["predicted_rank"] = ranked.groupby("race_id").cumcount() + 1
    return ranked.sort_values(["race_date", "race_id", "predicted_rank"]).reset_index(drop=True)


def evaluate_forecasts(
        forecasts: pd.DataFrame,
        start_date: str | pd.Timestamp,
        end_date: str | pd.Timestamp,
        months: Sequence[int] | None = None
    ) -> pd.DataFrame:
    """Metrics of each race evaluated, selected by number of ranked riders and date.

    See the module docstring for the rules.

    Args:
        forecasts: One row per race and ranked rider, with race_id,
            race_date, finish_rank and predicted_rank, as returned by
            add_predicted_rank or rank_by_recent_form.
        start_date: First day of the races evaluated, as "YYYY-MM-DD" or a
            date (the time of day is ignored).
        end_date: Last day of the races evaluated, same format.
        months: Months (1 to 12) of the races evaluated; None for all of
            them.

    Returns:
        The metrics of the races evaluated, as returned by
        compute_race_metrics.

    Raises:
        ValueError: If start_date is missing, then if end_date is missing,
            then if start_date is after end_date, then if a month is not
            between 1 and 12, then if the predicted ranks of some races
            evaluated are not 1 to their number of ranked riders.
    """
    start = to_day(start_date, "start date")
    end = to_day(end_date, "end date")
    if start > end:
        raise ValueError(f"Start date {start.date()} is after end date {end.date()}")
    if months is not None and not all(1 <= month <= 12 for month in months):
        raise ValueError(f"Months must be between 1 and 12, not {list(months)}")
    race_dates = to_datetime(forecasts["race_date"])
    nb_ranked_riders = forecasts.groupby("race_id")["race_id"].transform("size")
    is_evaluated = (nb_ranked_riders > TOP_N) & race_dates.between(start, end)
    if months is not None:
        is_evaluated &= race_dates.dt.month.isin(months)
    return compute_race_metrics(forecasts[is_evaluated])
