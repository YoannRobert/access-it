"""Unit tests of the metrics of a forecast, race by race and averaged over the races."""

from math import log2, sqrt

import pandas as pd
import pytest

from access_it.model.metrics import (
    METRICS, RACE_METRICS_COLUMNS, SUMMARY_COLUMNS, compute_race_metrics, summarize_metrics
)
from access_it.model.target_metrics import LIST_METRICS


def race_of(race_id: str, finish_ranks: list[int], race_date: str = "2024-05-01") -> pd.DataFrame:
    """Forecast of a race, the finish ranks being given from predicted rank 1 to the last one."""
    return pd.DataFrame({
        "race_id": race_id,
        "race_date": race_date,
        "rider_id": [f"{race_id}-{i}" for i in range(1, len(finish_ranks) + 1)],
        "finish_rank": finish_ranks,
        "predicted_rank": range(1, len(finish_ranks) + 1),
    })


def metric_of(forecasts: pd.DataFrame, race_id: str, metric: str) -> float:
    """Metric of a race."""
    metrics = compute_race_metrics(forecasts)
    return metrics.loc[metrics["race_id"] == race_id, metric].iloc[0]


def test_precision_counts_every_rider_tied_at_the_20th_place():
    # 17 riders well placed, then 2 riders tied at the 20th place, then 22nd, 18th and 19th
    forecasts = race_of("r1", [*range(1, 18), 20, 20, 22, 18, 19])
    assert metric_of(forecasts, "r1", "precision_at_20") == pytest.approx(19 / 20)


def test_precision_missing_for_a_race_of_20_ranked_riders():
    forecasts = race_of("r1", list(range(1, 21)))
    assert pd.isna(metric_of(forecasts, "r1", "precision_at_20"))


def test_ndcg_on_the_first_10_positions_or_fewer():
    forecasts = pd.concat([
        race_of("small", [2, 1, 3]),
        race_of("large", [*range(2, 12), 1, 12]),
    ])
    small = (19 + 20 / log2(3) + 18 / log2(4)) / (20 + 19 / log2(3) + 18 / log2(4))
    large = (
        sum((20 - p) / log2(p + 1) for p in range(1, 11))
        / sum((21 - p) / log2(p + 1) for p in range(1, 11))
    )
    assert metric_of(forecasts, "small", "ndcg_at_10") == pytest.approx(small)
    assert metric_of(forecasts, "large", "ndcg_at_10") == pytest.approx(large)


def test_ndcg_gives_the_same_relevance_to_tied_riders():
    forecasts = race_of("r1", [1, 2, 2])
    assert metric_of(forecasts, "r1", "ndcg_at_10") == pytest.approx(1.0)


def test_ndcg_missing_if_no_rider_finished_in_the_top_20():
    forecasts = race_of("r1", [21, 22])
    assert pd.isna(metric_of(forecasts, "r1", "ndcg_at_10"))


def test_spearman_gives_their_average_rank_to_tied_riders():
    # Actual ranks 1, 2.5, 4, 2.5 against the predicted ranks 1 to 4
    forecasts = race_of("r1", [1, 2, 4, 2])
    assert metric_of(forecasts, "r1", "spearman") == pytest.approx(3 / sqrt(22.5))


def test_spearman_missing_with_a_single_ranked_rider():
    forecasts = race_of("r1", [1])
    assert pd.isna(metric_of(forecasts, "r1", "spearman"))


def test_race_metrics_columns_and_order():
    forecasts = pd.concat([
        race_of("r3", [1, 2], "2024-06-01"),
        race_of("r2", [1, 2], "2024-05-01"),
        race_of("r1", [1, 2], "2024-05-01"),
    ])
    metrics = compute_race_metrics(forecasts)
    assert metrics.columns.tolist() == RACE_METRICS_COLUMNS
    assert metrics["race_id"].tolist() == ["r1", "r2", "r3"]
    assert metrics["race_date"].dtype == "datetime64[ns]"
    assert metrics.index.tolist() == [0, 1, 2]


@pytest.mark.parametrize("predicted_ranks", [[1, 1, 3], [1, 2, 4], [0, 1, 2]])
def test_error_if_the_predicted_ranks_are_not_1_to_the_number_of_ranked_riders(predicted_ranks):
    forecasts = pd.concat([
        race_of("r1", [1, 2, 3]),
        race_of("r2", [1, 2, 3]).assign(predicted_rank=predicted_ranks),
    ])
    with pytest.raises(
        ValueError,
        match=r"Races whose predicted ranks are not 1 to the number of ranked riders: \['r2'\]"
    ):
        compute_race_metrics(forecasts)


def test_summary_ignores_the_missing_values():
    race_metrics = pd.DataFrame({
        "race_id": ["r1", "r2", "r3"],
        "race_date": pd.to_datetime(["2024-05-01", "2024-05-02", "2024-05-03"]),
        "precision_at_20": [0.5, None, None],
        "ndcg_at_10": [0.2, 0.4, 0.9],
        "spearman": [0.1, None, 0.3],
    })
    summary = summarize_metrics(race_metrics)
    assert summary["mean"].tolist() == pytest.approx([0.5, 0.5, 0.2])
    assert summary["nb_races"].tolist() == [1, 3, 2]


def test_summary_columns_and_order():
    summary = summarize_metrics(compute_race_metrics(race_of("r1", [1, 2])))
    assert summary.columns.tolist() == SUMMARY_COLUMNS
    assert summary["metric"].tolist() == METRICS


def test_summary_of_an_empty_forecast():
    summary = summarize_metrics(compute_race_metrics(race_of("r1", [1]).iloc[0:0]))
    assert summary["mean"].isna().all()
    assert summary["nb_races"].tolist() == [0, 0, 0]


def test_summary_of_the_given_metrics():
    list_metrics = pd.DataFrame({
        "race_id": ["r1", "r2"],
        **{metric: [1.0, 0.5] for metric in LIST_METRICS},
        "win_rr_at_10": [0.25, None],
    })
    summary = summarize_metrics(list_metrics, LIST_METRICS)
    assert summary.columns.tolist() == SUMMARY_COLUMNS
    assert summary["metric"].tolist() == LIST_METRICS
    assert summary.set_index("metric").loc["win_rr_at_10"].tolist() == [0.25, 1]
    assert summary.set_index("metric").loc["top5_recall_at_10"].tolist() == [0.75, 2]
