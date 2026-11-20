"""Metrics of a forecast, computed race by race, then averaged over the races.

The forecast of a race ranks its ranked riders (the start list of a past race)
with a unique predicted rank, from 1 to the number of ranked riders; each
model turns its own score into such a rank before the evaluation. Rules:

- the precision at 20 is the share of the 20 first predicted riders who
  finished in the top 20 (finish_rank <= 20, tied riders all count); it is
  only computed for the races with more than 20 ranked riders;
- the NDCG at 10 uses a relevance graded on the top 20, max(0, 21 -
  finish_rank) (tied riders get the same one), with a linear gain and a
  log2(position + 1) discount; it is computed on the first min(10, number of
  ranked riders) positions, and is missing if no rider finished in the top
  20;
- the Spearman correlation is the Pearson correlation between the actual
  ranks, tied riders getting their average rank, and the predicted ranks (1
  for a perfect forecast); it is missing with fewer than 2 ranked riders or if
  all of them are tied;
- the mean of a metric is not weighted and ignores the races where the metric
  is missing; summarize_metrics also averages other metrics computed race by
  race (the lists of the target_metrics module).

The computation is free of any Streamlit dependency.
"""

from collections.abc import Sequence

import numpy as np
import pandas as pd

from access_it.analytics.ranking_tools import to_datetime

TOP_N = 20  # N of the precision and last finish rank with a relevance in the NDCG
NDCG_K = 10
METRICS = ["precision_at_20", "ndcg_at_10", "spearman"]
RACE_METRICS_COLUMNS = ["race_id", "race_date", *METRICS]
SUMMARY_COLUMNS = ["metric", "mean", "nb_races"]


def compute_race_metrics(forecasts: pd.DataFrame) -> pd.DataFrame:
    """Precision at 20, NDCG at 10 and Spearman correlation of the forecast of each race.

    See the module docstring for the rules.

    Args:
        forecasts: One row per race and ranked rider, with race_id,
            race_date, finish_rank (the actual one) and predicted_rank, as
            returned by rank_by_recent_form of the features layer.

    Returns:
        One row per race with the RACE_METRICS_COLUMNS: race_id, race_date
        (datetime64[ns]), precision_at_20, ndcg_at_10 and spearman (floats,
        missing where the metric is not defined); sorted by race date and
        race_id, with the index reset.

    Raises:
        ValueError: If the predicted ranks of some races are not 1 to their
            number of ranked riders (their race_id are given in the message).
    """
    ranks = forecasts[["race_id", "race_date", "finish_rank", "predicted_rank"]].sort_values(
        ["race_id", "predicted_rank"]
    )
    is_valid = ranks["predicted_rank"].eq(ranks.groupby("race_id").cumcount() + 1)
    if not is_valid.all():
        race_ids = ranks.loc[~is_valid, "race_id"].drop_duplicates().tolist()
        raise ValueError(
            f"Races whose predicted ranks are not 1 to the number of ranked riders: {race_ids!r}"
        )
    relevance = (TOP_N + 1 - ranks["finish_rank"]).clip(lower=0)
    ideal_position = relevance.groupby(ranks["race_id"]).rank(method="first", ascending=False)
    terms = ranks.assign(
        is_hit=(ranks["predicted_rank"] <= TOP_N) & (ranks["finish_rank"] <= TOP_N),
        dcg=(relevance / np.log2(ranks["predicted_rank"] + 1)).where(
            ranks["predicted_rank"] <= NDCG_K, 0.0
        ),
        ideal_dcg=(relevance / np.log2(ideal_position + 1)).where(ideal_position <= NDCG_K, 0.0),
        actual_rank=ranks.groupby("race_id")["finish_rank"].rank(method="average"),
    )
    # Deviations from the race means, for the Pearson correlation of the ranks
    by_race = terms.groupby("race_id")
    actual_deviation = terms["actual_rank"] - by_race["actual_rank"].transform("mean")
    predicted_deviation = terms["predicted_rank"] - by_race["predicted_rank"].transform("mean")
    metrics = terms.assign(
        covariance=actual_deviation * predicted_deviation,
        actual_variance=actual_deviation**2,
        predicted_variance=predicted_deviation**2,
    ).groupby("race_id").agg(
        race_date=("race_date", "first"),
        nb_ranked_riders=("predicted_rank", "size"),
        nb_hits=("is_hit", "sum"),
        dcg=("dcg", "sum"),
        ideal_dcg=("ideal_dcg", "sum"),
        covariance=("covariance", "sum"),
        actual_variance=("actual_variance", "sum"),
        predicted_variance=("predicted_variance", "sum"),
    )
    variances = metrics["actual_variance"] * metrics["predicted_variance"]
    metrics = metrics.assign(
        race_date=to_datetime(metrics["race_date"]),
        precision_at_20=(metrics["nb_hits"] / TOP_N).where(metrics["nb_ranked_riders"] > TOP_N),
        ndcg_at_10=(metrics["dcg"] / metrics["ideal_dcg"]).where(metrics["ideal_dcg"] > 0),
        spearman=(metrics["covariance"] / np.sqrt(variances)).where(variances > 0),
    )
    return (
        metrics.reset_index()
        .sort_values(["race_date", "race_id"])
        .reset_index(drop=True)[RACE_METRICS_COLUMNS]
    )


def summarize_metrics(
        race_metrics: pd.DataFrame,
        metrics: Sequence[str] = tuple(METRICS)
    ) -> pd.DataFrame:
    """Mean of each metric over the races where it is defined.

    Args:
        race_metrics: Metrics of each race, as returned by
            compute_race_metrics (or compute_list_metrics of the
            target_metrics module).
        metrics: Columns of the metrics to average, in the output order.

    Returns:
        One row per metric, in the order of metrics, with the
        SUMMARY_COLUMNS: metric, mean (missing if no race has the metric) and
        nb_races (number of races where the metric is defined).
    """
    values = race_metrics[list(metrics)]
    return pd.DataFrame(
        {
            "metric": list(metrics),
            "mean": values.mean().to_numpy(),
            "nb_races": values.count().to_numpy(),
        }
    )[SUMMARY_COLUMNS]
