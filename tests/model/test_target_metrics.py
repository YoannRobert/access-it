"""Unit tests of the metrics of the forecasts of the targets: lists, probabilities, calibration."""

import math

import pandas as pd
import pytest

from access_it.model.forecasts import PROBABILITY_COLUMNS, RANK_COLUMNS
from access_it.model.target_metrics import (
    CALIBRATION_COLUMNS, LIST_METRICS, LIST_METRICS_COLUMNS, PROBABILITY_BOUND,
    PROBABILITY_METRICS_COLUMNS, compute_calibration, compute_list_metrics,
    compute_probability_metrics
)


def race_ranked(
        race_id: str, finish_ranks: list[int], race_date: str = "2024-05-01"
    ) -> pd.DataFrame:
    """Forecast of a race, the finish ranks given from rank 1 to the last one of every target."""
    positions = range(1, len(finish_ranks) + 1)
    return pd.DataFrame({
        "race_id": race_id,
        "race_date": race_date,
        "rider_id": [f"{race_id}-{i:02d}" for i in positions],
        "finish_rank": finish_ranks,
        **{rank: positions for rank in RANK_COLUMNS},
    })


def list_metric_of(forecasts: pd.DataFrame, race_id: str, metric: str) -> float:
    """List metric of a race."""
    metrics = compute_list_metrics(forecasts)
    return metrics.loc[metrics["race_id"] == race_id, metric].iloc[0]


def with_probabilities(finish_ranks: list[int], probabilities: list[float]) -> pd.DataFrame:
    """Rows of riders whose probabilities of every target are the given ones."""
    return pd.DataFrame({
        "finish_rank": finish_ranks,
        **{probability: probabilities for probability in PROBABILITY_COLUMNS},
    })


def test_recall_counts_tied_riders_who_reached_the_target():
    # Two riders tied at the 3rd place, the second one predicted 11th
    forecasts = race_ranked("r1", [1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 3, 12])
    assert list_metric_of(forecasts, "r1", "podium_recall_at_10") == pytest.approx(3 / 4)


def test_top10_list_holds_20_riders():
    # The 10th predicted 15th, the 5th predicted 16th
    forecasts = race_ranked(
        "r1", [1, 2, 3, 4, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 10, 5, 17, 18, 19, 20, 21]
    )
    assert list_metric_of(forecasts, "r1", "top10_recall_at_20") == 1.0
    assert list_metric_of(forecasts, "r1", "top5_recall_at_10") == pytest.approx(4 / 5)


@pytest.mark.parametrize("finish_ranks, expected", [
    ([2, 3, 4, 1, 5], 1 / 4),
    ([2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 1], 0.0),
    ([2, 3, 1, 4, 5, 1, 6], 1 / 3),
])
def test_reciprocal_rank_of_the_winner(finish_ranks, expected):
    forecasts = race_ranked("r1", finish_ranks)
    assert list_metric_of(forecasts, "r1", "win_rr_at_10") == pytest.approx(expected)


def test_metrics_missing_when_no_rider_reached_the_target():
    forecasts = race_ranked("r1", [2, 3, 4])
    assert pd.isna(list_metric_of(forecasts, "r1", "win_recall_at_10"))
    assert pd.isna(list_metric_of(forecasts, "r1", "win_rr_at_10"))
    assert list_metric_of(forecasts, "r1", "podium_recall_at_10") == 1.0


def test_list_metrics_output():
    forecasts = pd.concat([
        race_ranked("r2", [1, 2], "2024-05-02"),
        race_ranked("r3", [1, 2], "2024-05-01"),
        race_ranked("r1", [1, 2], "2024-05-01"),
    ])
    metrics = compute_list_metrics(forecasts)
    assert metrics.columns.tolist() == LIST_METRICS_COLUMNS
    assert metrics["race_id"].tolist() == ["r1", "r3", "r2"]
    assert metrics.index.tolist() == [0, 1, 2]
    assert metrics["race_date"].dtype == "datetime64[ns]"
    assert metrics[LIST_METRICS].dtypes.tolist() == ["float64"] * len(LIST_METRICS)
    assert compute_list_metrics(forecasts.iloc[0:0]).empty


@pytest.mark.parametrize("invalid_columns, message", [
    (["rank_win"], "Races whose rank_win are not 1 to the number of ranked riders"),
    (["rank_podium"], "Races whose rank_podium are not 1 to the number of ranked riders"),
    (
        ["rank_win", "rank_podium"],
        "Races whose rank_win are not 1 to the number of ranked riders",
    ),
])
def test_invalid_ranks_raise_in_the_order_of_the_rank_columns(invalid_columns, message):
    invalid = race_ranked("r2", [1, 2, 3]).assign(**{column: 1 for column in invalid_columns})
    forecasts = pd.concat([race_ranked("r1", [1, 2, 3]), invalid])
    with pytest.raises(ValueError, match=rf"{message}: \['r2'\]"):
        compute_list_metrics(forecasts)


def test_log_loss_and_brier_by_hand():
    win = compute_probability_metrics(with_probabilities([1, 2], [0.8, 0.2])).iloc[0]
    assert win["log_loss"] == pytest.approx(-math.log(0.8))
    assert win["brier"] == pytest.approx(0.04)
    certain_miss = compute_probability_metrics(with_probabilities([1], [0.0])).iloc[0]
    assert certain_miss["log_loss"] == pytest.approx(-math.log(PROBABILITY_BOUND))
    assert certain_miss["brier"] == 1.0


def test_probability_metrics_output():
    metrics = compute_probability_metrics(with_probabilities([1, 4, 8], [0.5, 0.3, 0.2]))
    assert metrics.columns.tolist() == PROBABILITY_METRICS_COLUMNS
    assert metrics["target"].tolist() == ["win", "podium", "top5", "top10"]
    assert metrics["nb_rows"].tolist() == [3] * 4
    empty = compute_probability_metrics(with_probabilities([], []))
    assert empty[["log_loss", "brier"]].isna().all().all()
    assert empty["nb_rows"].tolist() == [0] * 4


def test_calibration_groups_of_the_same_size():
    # The rider with probability 0.02 wins, the 19 others finish 2nd to 20th
    probabilities = [i / 100 for i in range(1, 21)]
    finish_ranks = [2, 1, *range(3, 21)]
    calibration = compute_calibration(with_probabilities(finish_ranks, probabilities))
    win = calibration[calibration["target"] == "win"]
    assert win["bin"].tolist() == list(range(10))
    assert win["nb_rows"].tolist() == [2] * 10
    assert win.iloc[0][["predicted", "observed"]].tolist() == pytest.approx([0.015, 0.5])


def test_calibration_drops_duplicated_bounds():
    calibration = compute_calibration(with_probabilities(range(1, 21), [0.1] * 10 + [0.2] * 10))
    win = calibration[calibration["target"] == "win"]
    assert win["bin"].tolist() == [0, 1]
    assert win["nb_rows"].tolist() == [10, 10]
    constant = compute_calibration(with_probabilities(range(1, 21), [0.1] * 20))
    assert constant.empty


def test_calibration_output():
    calibration = compute_calibration(with_probabilities([1, 2, 3, 4], [0.4, 0.3, 0.2, 0.1]))
    assert calibration.columns.tolist() == CALIBRATION_COLUMNS
    assert calibration["target"].drop_duplicates().tolist() == ["win", "podium", "top5", "top10"]
    assert calibration.groupby("target", sort=False)["bin"].apply(
        lambda bins: bins.is_monotonic_increasing
    ).all()
    assert calibration.index.tolist() == list(range(len(calibration)))
    empty = compute_calibration(with_probabilities([], []))
    assert empty.empty and empty.columns.tolist() == CALIBRATION_COLUMNS
