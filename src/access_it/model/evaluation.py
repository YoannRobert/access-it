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
  summarize_metrics; the rows of these races are selected by
  select_evaluated_forecasts, and can be given to the metrics of the
  target_metrics module as well;
- two forecasts are compared race by race (compare_race_metrics): for each
  metric, on the races where both values are defined, the mean difference,
  its standard error (standard deviation of the differences, with ddof = 1,
  divided by the square root of the number of races) and their ratio (a ratio
  above about 2 in absolute value shows a real difference); the standard
  error and the ratio are missing with fewer than 2 races, the ratio also
  with a null standard error, and the difference without race.

The computation is free of any Streamlit dependency.
"""

from collections.abc import Sequence

import numpy as np
import pandas as pd

from access_it.analytics.ranking_tools import to_datetime, to_day
from access_it.model.metrics import TOP_N, compute_race_metrics

COMPARISON_COLUMNS = ["metric", "difference", "std_error", "ratio", "nb_races"]


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


def select_evaluated_forecasts(
        forecasts: pd.DataFrame,
        start_date: str | pd.Timestamp,
        end_date: str | pd.Timestamp,
        months: Sequence[int] | None = None
    ) -> pd.DataFrame:
    """Rows of the races evaluated, selected by number of ranked riders and date.

    See the module docstring for the rules.

    Args:
        forecasts: One row per race and ranked rider, with race_id and
            race_date.
        start_date: First day of the races evaluated, as "YYYY-MM-DD" or a
            date (the time of day is ignored).
        end_date: Last day of the races evaluated, same format.
        months: Months (1 to 12) of the races evaluated; None for all of
            them.

    Returns:
        The rows of the races evaluated, with their original index, in
        their original order.

    Raises:
        ValueError: If start_date is missing, then if end_date is missing,
            then if start_date is after end_date, then if a month is not
            between 1 and 12.
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
    return forecasts[is_evaluated]


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
    return compute_race_metrics(
        select_evaluated_forecasts(forecasts, start_date, end_date, months)
    )


def compare_race_metrics(
        race_metrics: pd.DataFrame,
        reference: pd.DataFrame,
        metrics: Sequence[str]
    ) -> pd.DataFrame:
    """Mean difference race by race between the metrics of two forecasts, with its standard error.

    See the module docstring for the rules.

    Args:
        race_metrics: Metrics of each race of the forecast compared, with
            race_id and the metrics.
        reference: Metrics of each race of the reference forecast, same
            columns.
        metrics: Columns of the metrics to compare, in the output order.

    Returns:
        One row per metric, with the COMPARISON_COLUMNS: metric, difference
        (race_metrics minus reference), std_error, ratio and nb_races, with
        the index reset.
    """
    paired = race_metrics.merge(reference, on="race_id", suffixes=("", "_reference"))
    rows = []
    for metric in metrics:
        differences = (paired[metric] - paired[f"{metric}_reference"]).dropna()
        nb_races = len(differences)
        std_error = differences.std() / np.sqrt(nb_races) if nb_races >= 2 else np.nan
        difference = differences.mean()
        rows.append({
            "metric": metric,
            "difference": difference,
            "std_error": std_error,
            "ratio": difference / std_error if std_error > 0 else np.nan,
            "nb_races": nb_races,
        })
    return pd.DataFrame(rows, columns=COMPARISON_COLUMNS)
